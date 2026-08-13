# app/routes/panel.py
"""
Endpoint del panel: dado un video de YouTube, devuelve los 8 descriptores
ubicados en la escala de referencia.

ORDEN DE BUSQUEDA DEL TEXTO — importa, y es lo que hace que esto sea barato
--------------------------------------------------------------------------
1. La base. Los ~500 videos ya enriquecidos salen gratis y al instante.
2. Supadata con mode=native. Un credito. SOLO si no estaba en la base.
3. Nada: se responde "sin datos suficientes". Nunca un cero, nunca una letra.

Por que mode=native es obligatorio: sin el, un video cuyos subtitulos nativos
Supadata no logra bajar se transcribe con Whisper, que cobra por minuto de
audio. El 2026-08-12 una sola llamada asi consumio 134 creditos y agoto el plan
entero. Con mode=native cada video cuesta 1.

POR QUE EL CALCULO VIVE ACA Y NO EN EL NAVEGADOR
------------------------------------------------
Reutiliza nutriscore_features.py, el mismo modulo con el que se construyo la
escala. Si se reimplementaran los lexicos en JavaScript, el panel y el estudio
empezarian a medir cosas distintas apenas alguien afinara una definicion. Un
solo cuerpo de reglas, sin copias.

EQUIVALENCIA DE FUENTES: verificada, no supuesta
------------------------------------------------
La escala se construyo con subtitulos de YouTube y el panel puede usar Supadata.
Se comparo pareado sobre 7 videos: correlaciones de 0,996 a 1,000 y 0 % de los
videos cambian de tramo en los 8 descriptores. Son el mismo instrumento.
Detalle en docs/calibracion_supadata.md.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..database import engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/panel", tags=["panel"])

SUPADATA_URL = "https://api.supadata.ai/v1/transcript"
YT_API = "https://www.googleapis.com/youtube/v3/videos"

# La escala se busca en varios lugares: en local esta en docs/, y en Render
# conviene copiarla dentro del paquete para que viaje con el deploy.
CANDIDATOS_ESCALA = [
    Path(os.getenv("ESCALA_PATH", "")) if os.getenv("ESCALA_PATH") else None,
    Path(__file__).resolve().parents[1] / "escala_referencia.json",
    Path(__file__).resolve().parents[3] / "docs" / "escala_referencia.json",
]


@lru_cache(maxsize=1)
def cargar_escala() -> dict:
    for p in CANDIDATOS_ESCALA:
        if p and p.exists():
            logger.info(f"escala cargada de {p}")
            return json.loads(p.read_text(encoding="utf-8"))
    raise RuntimeError(
        "No se encontro escala_referencia.json. Copiala a backend/app/ o "
        "define ESCALA_PATH.")


# --------------------------------------------------------------- descriptores

@lru_cache(maxsize=1)
def _features_mod():
    """Se importa tarde y una sola vez: arrastra pandas y numpy, y no conviene
    pagar eso en el arranque en frio de Render si el endpoint no se usa."""
    import sys
    ruta = Path(__file__).resolve().parents[2] / "scripts"
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))
    import nutriscore_features as nf
    return nf


def calcular_descriptores(fila: dict) -> dict:
    nf = _features_mod()
    r = dict(fila)
    for c in ("transcript", "description", "title", "tags", "transcript_segments",
              "chapters", "transcript_source", "category_name", "video_language",
              "transcript_lang", "channel"):
        if not isinstance(r.get(c), str):
            r[c] = json.dumps(r[c]) if isinstance(r.get(c), (list, dict)) else ""
    tnorm = nf.norm(r.get("transcript") or "")
    toks = nf.words(tnorm)
    lang = "en" if str(r.get("video_language") or "es").startswith("en") else "es"
    val = nf.capa0_validez(r, toks)
    ind = nf.indicadores(r, toks, tnorm, lang, val)
    eti = nf.etiquetas(r, ind, val, lang)
    return {**val, **ind, **eti}


def percentil(valor, grid: list | None) -> float | None:
    """Posicion del valor en la grilla de 101 percentiles. Acotado a 0-100: un
    video mas lento que el mas lento del corpus esta en el percentil 0, no en
    un percentil negativo."""
    if not grid or valor is None:
        return None
    lo, hi = 0, len(grid) - 1
    while lo < hi:
        m = (lo + hi) // 2
        if grid[m] <= valor:
            lo = m + 1
        else:
            hi = m
    return float(min(100, max(0, lo - 1 if grid[lo] > valor else lo)))


def ubicar(desc: dict, formato: str | None) -> list[dict]:
    """Traduce los 8 numeros crudos a como se muestran.

    Continuos -> percentil. De presencia -> tiene / no tiene, y si tiene, el
    percentil entre los que tienen. Nunca un adjetivo: el percentil describe,
    'alto' juzga."""
    escala = cargar_escala()
    salida = []
    for k, cfg in escala["descriptores"].items():
        ref = cfg.get("referencia") or {}
        if cfg.get("ambito") == "por_formato":
            ref = ref.get(formato) or ref.get("_todos") or {}
        v = desc.get(k)
        item = {"clave": k, "unidad": cfg.get("unidad"), "valor": v,
                "tipo": cfg.get("tipo"), "ambito": cfg.get("ambito")}
        if v is None or not ref:
            item.update(estado="sin_dato")
        elif cfg.get("tipo") == "presencia":
            item["p_ausencia"] = ref.get("p_ausencia")
            if v > 0:
                item.update(estado="presente",
                            percentil=percentil(v, ref.get("grid_presentes")),
                            n_presentes=ref.get("n_presentes"))
            else:
                item.update(estado="ausente")
        else:
            item.update(estado="medido", percentil=percentil(v, ref.get("grid")),
                        mediana_corpus=ref.get("p50"))
        salida.append(item)
    return salida


# --------------------------------------------------------------- obtencion

SQL = text("""
    SELECT external_id, title, channel, description, tags, category_id,
           category_name, duration_seconds, transcript, transcript_source,
           transcript_is_generated, transcript_lang, transcript_word_count,
           transcript_segments, chapters, n_chapters, video_language,
           stratum_format, corpus
      FROM content_items
     WHERE external_id = :vid
""")


def de_la_base(vid: str) -> dict | None:
    with engine.connect() as c:
        row = c.execute(SQL, {"vid": vid}).mappings().first()
    if not row:
        return None
    d = dict(row)
    return d if (d.get("transcript") or "").strip() else None


def metadatos_youtube(vid: str) -> dict:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        return {}
    try:
        r = requests.get(YT_API, params={
            "part": "snippet,contentDetails", "id": vid, "key": key}, timeout=15)
        it = (r.json().get("items") or [None])[0]
        if not it:
            return {}
        sn, cd = it.get("snippet", {}), it.get("contentDetails", {})
        import re
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", cd.get("duration", ""))
        seg = (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60
               + int(m.group(3) or 0)) if m else None
        return {"title": sn.get("title"), "channel": sn.get("channelTitle"),
                "description": sn.get("description"), "tags": sn.get("tags") or [],
                "category_id": sn.get("categoryId"), "duration_seconds": seg,
                "video_language": (sn.get("defaultAudioLanguage") or "es")}
    except Exception as e:
        logger.warning(f"metadatos de {vid}: {e}")
        return {}


def de_supadata(vid: str) -> tuple[str | None, str]:
    key = os.getenv("SUPADATA_API_KEY")
    if not key:
        return None, "sin_api_key"
    try:
        r = requests.get(SUPADATA_URL, params={
            "url": f"https://www.youtube.com/watch?v={vid}",
            "text": "true", "mode": "native"},   # native: NUNCA Whisper
            headers={"x-api-key": key}, timeout=45)
    except Exception as e:
        return None, f"error_red: {e}"

    if r.status_code == 202:
        return None, "whisper_evitado"   # el video no tiene subtitulos nativos
    if r.status_code == 429:
        return None, "sin_creditos"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    c = r.json().get("content")
    t = c if isinstance(c, str) else " ".join(
        s.get("text", "") for s in (c or []) if isinstance(s, dict))
    t = " ".join((t or "").split()).strip()
    return (t or None), ("ok" if t else "vacio")


# --------------------------------------------------------------- endpoint

def _formato(cat_id) -> str | None:
    import sys
    ruta = Path(__file__).resolve().parents[2] / "scripts"
    if str(ruta) not in sys.path:
        sys.path.insert(0, str(ruta))
    import build_reference_corpus as brc   # mismas reglas que el muestreo
    return brc.bucket_formato(cat_id)


@router.get("/{video_id}")
def panel(video_id: str):
    escala = cargar_escala()
    fila, origen = de_la_base(video_id), "base"

    if fila is None:
        meta = metadatos_youtube(video_id)
        if not meta:
            raise HTTPException(404, "No se pudieron obtener los metadatos del video.")
        texto, estado = de_supadata(video_id)
        if not texto:
            # Es la respuesta honesta, no un error: hay videos que no admiten
            # panel. Musica, gameplay sin comentario, tomas aereas.
            return {"video_id": video_id, "apto": False, "motivo": estado,
                    "mensaje": "Sin datos suficientes para mostrar el panel.",
                    "frame_version": escala["frame_version"]}
        fila = {**meta, "external_id": video_id, "transcript": texto,
                "transcript_source": "supadata", "transcript_lang": "es",
                "transcript_segments": None, "chapters": None, "n_chapters": None}
        origen = "supadata"

    desc = calcular_descriptores(fila)
    if not desc.get("v_apto_panel"):
        return {"video_id": video_id, "apto": False,
                "motivo": "cobertura_de_habla_insuficiente",
                "cobertura": desc.get("v_cobertura_transcripcion"),
                "mensaje": "Sin datos suficientes para mostrar el panel.",
                "frame_version": escala["frame_version"]}

    fmt = fila.get("stratum_format") or _formato(fila.get("category_id"))
    return {
        "video_id": video_id,
        "apto": True,
        "origen_transcripcion": origen,
        "formato": fmt,
        "frame_version": escala["frame_version"],
        "descriptores": ubicar(desc, fmt),
        "etiquetas": {k: v for k, v in desc.items() if k.startswith("et_")},
        "nota": ("Los percentiles son relativos al corpus de referencia de "
                 "YouTube en espanol, agosto 2026. No son una calificacion."),
    }
