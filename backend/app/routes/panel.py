# app/routes/panel.py
"""
Endpoint del panel: dado un video de YouTube, devuelve los 8 descriptores
ubicados en la escala de referencia.

SOLO LEE. NO GASTA CREDITOS.
----------------------------
Este endpoint no llama a Supadata. La unica parte del sistema que lo hace es el
enriquecimiento en background que dispara POST /videos. Si el panel llamara
tambien, cada video nuevo costaria dos creditos en vez de uno — con un plan de
100, eso es la mitad del presupuesto tirado.

Entonces hay tres respuestas posibles:
  apto = true   -> la fila esta en la base y pasa el gate. Se devuelve el panel.
  apto = null   -> "procesando": todavia no hay transcripcion. La extension
                   reintenta cada pocos segundos hasta que el enriquecimiento
                   termine.
  apto = false  -> hay transcripcion pero no alcanza (musica, gameplay sin
                   comentario, tomas sin voz). "Sin datos suficientes", nunca
                   un cero y nunca una letra.

POR QUE EL CALCULO VIVE ACA Y NO EN EL NAVEGADOR
------------------------------------------------
Reutiliza nutriscore_features.py, el mismo modulo con el que se construyo la
escala. Si se reimplementaran los lexicos en JavaScript, el panel y el estudio
empezarian a medir cosas distintas apenas alguien afinara una definicion. Un
solo cuerpo de reglas, sin copias.

EQUIVALENCIA DE FUENTES: verificada, no supuesta
------------------------------------------------
La escala se construyo con subtitulos de YouTube y el enriquecimiento usa
Supadata. Se comparo pareado sobre 7 videos: correlaciones de 0,996 a 1,000 y
0 % de los videos cambian de tramo en los 8 descriptores. Son el mismo
instrumento. Detalle en docs/calibracion_supadata.md.

SI DEJA CONSTANCIA: content_features
------------------------------------
Leer no cuesta creditos, pero calcular y olvidar cuesta otra cosa: hasta esta
version el sistema media ocho descriptores por cada video visto y no guardaba
ninguno. content_features tenia 0 filas. Eso significaba que no habia forma de
responder "como se distribuyo mi historial", que es media memoria del TFM.

Ahora cada calculo hace upsert en content_features (una fila por video, se
pisa al recalcular). Se guardan tambien los NO aptos: el hallazgo de que los
formatos difieren mas en si se pueden medir que en como puntuan se sostiene
justamente sobre esas filas.

La escritura esta aislada en un try/except propio. Si falla, el panel igual se
devuelve: no mostrarle nada al usuario porque no se pudo guardar una fila
seria cambiar un problema chico por uno grande.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..database import engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/panel", tags=["panel"])

FEATURES_VERSION = "panel-1.0"

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
    # El idioma del LEXICO sale de la transcripcion, no del video: es el texto
    # que se va a medir. video_language dice que idioma declara el canal, que no
    # siempre es el de la pista que se bajo.
    idioma = str(r.get("transcript_lang") or r.get("video_language") or "es").lower()
    lang = "en" if idioma.startswith("en") else "es"
    val = nf.capa0_validez(r, toks)
    ind = nf.indicadores(r, toks, tnorm, lang, val)
    eti = nf.etiquetas(r, ind, val, lang)
    # _lang viaja con el resultado para que quien persista no tenga que
    # recalcular la misma regla y arriesgarse a que las dos se separen.
    return {**val, **ind, **eti, "_lang": lang}


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
    SELECT id, external_id, title, channel, description, tags, category_id,
           category_name, duration_seconds, transcript, transcript_source,
           transcript_is_generated, transcript_lang, transcript_word_count,
           transcript_segments, chapters, n_chapters, video_language,
           stratum_format, corpus,
           enrichment_status, enrichment_error, created_at
      FROM content_items
     WHERE external_id = :vid
""")

# Cuanto se espera al enriquecimiento antes de dar el video por perdido.
# Es generoso a proposito: Render en plan gratuito se duerme y el arranque en
# frio puede comerse medio minuto antes de que la tarea siquiera empiece.
ESPERA_MAXIMA_SEG = 150

# Por que no hay transcripcion, en castellano. La clave es enrichment_status,
# que ahora escribe el backend con el mismo vocabulario que el worker local.
MOTIVOS = {
    "no_subs": ("sin_subtitulos",
                "Este video no tiene subtítulos disponibles, así que no hay "
                "texto que medir."),
    "exhausted": ("sin_creditos",
                  "Se agotó el crédito del servicio de transcripción. El video "
                  "queda pendiente: cuando se reponga, el panel aparece solo."),
    "error": ("error_de_transcripcion",
              "Hubo un error al obtener la transcripción de este video."),
}


def de_la_base(vid: str) -> dict | None:
    """Devuelve la fila exista o no la transcripcion.

    Antes devolvia None cuando no habia texto, y el endpoint interpretaba eso
    como "todavia procesando". Resultado: un video sin subtitulos dejaba la
    etiqueta girando indefinidamente y despues desapareciendo sin decir nada.
    Distinguir "todavia no" de "no va a haber" es justamente lo que hace
    falta, asi que esa decision sube al endpoint, que tiene con que tomarla.
    """
    with engine.connect() as c:
        row = c.execute(SQL, {"vid": vid}).mappings().first()
    return dict(row) if row else None


def _sin_transcripcion(fila: dict, frame: str) -> dict:
    """Que contestar cuando la fila existe pero no tiene texto."""
    estado = (fila.get("enrichment_status") or "").lower()

    if estado in MOTIVOS:
        motivo, mensaje = MOTIVOS[estado]
        return {"apto": False, "motivo": motivo, "mensaje": mensaje,
                "estado_enriquecimiento": estado,
                "detalle": fila.get("enrichment_error"),
                "frame_version": frame}

    # Sin estado registrado: o esta corriendo, o murio sin dejar rastro. La
    # edad de la fila desempata.
    creado = fila.get("created_at")
    edad = None
    if creado is not None:
        if creado.tzinfo is None:
            creado = creado.replace(tzinfo=timezone.utc)
        edad = (datetime.now(timezone.utc) - creado).total_seconds()

    if edad is not None and edad > ESPERA_MAXIMA_SEG:
        return {"apto": False, "motivo": "enriquecimiento_incompleto",
                "mensaje": "El análisis no llegó a completarse. Suele ser el "
                           "servicio de transcripción caído o sin crédito.",
                "estado_enriquecimiento": None,
                "frame_version": frame}

    return {"apto": None, "estado": "procesando", "registrado": True,
            "mensaje": "Analizando el video…", "frame_version": frame}


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
    """NO se usa desde el endpoint. Se conserva por si alguna vez hace falta un
    modo "calcular ahora" explicito, y como documentacion de que mode=native es
    obligatorio. Si se reactiva, recordar que duplica el gasto de creditos."""
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


# --------------------------------------------------------------- persistencia

# Los 8 descriptores vigentes. Se listan explicitamente y no se toman del
# JSON de la escala para que un cambio en la escala no empiece a escribir en
# columnas que no existen sin que nadie se entere.
DESCRIPTORES_COL = ["ritmo_ppm", "cifras_100w", "atribucion_1000w", "mattr_200",
                    "conectores_1000w", "enlaces_externos", "promocional_1000w",
                    "cobertura_titulo"]

UPSERT = text("""
INSERT INTO content_features (
    content_item_id, features_version, computed_at, frame_version, formato,
    apto, cobertura_transcripcion, motivo_no_apto, panel,
    n_words, duration_seconds, lang, transcript_source,
    has_description, has_tags,
    ritmo_ppm, ritmo_ppm_pct, cifras_100w, cifras_100w_pct,
    atribucion_1000w, atribucion_1000w_pct, mattr_200, mattr_200_pct,
    conectores_1000w, conectores_1000w_pct, enlaces_externos, enlaces_externos_pct,
    promocional_1000w, promocional_1000w_pct, cobertura_titulo, cobertura_titulo_pct
) VALUES (
    :content_item_id, :features_version, :computed_at, :frame_version, :formato,
    :apto, :cobertura_transcripcion, :motivo_no_apto, CAST(:panel AS jsonb),
    :n_words, :duration_seconds, :lang, :transcript_source,
    :has_description, :has_tags,
    :ritmo_ppm, :ritmo_ppm_pct, :cifras_100w, :cifras_100w_pct,
    :atribucion_1000w, :atribucion_1000w_pct, :mattr_200, :mattr_200_pct,
    :conectores_1000w, :conectores_1000w_pct, :enlaces_externos, :enlaces_externos_pct,
    :promocional_1000w, :promocional_1000w_pct, :cobertura_titulo, :cobertura_titulo_pct
)
ON CONFLICT (content_item_id) DO UPDATE SET
    features_version = EXCLUDED.features_version,
    computed_at      = EXCLUDED.computed_at,
    frame_version    = EXCLUDED.frame_version,
    formato          = EXCLUDED.formato,
    apto             = EXCLUDED.apto,
    cobertura_transcripcion = EXCLUDED.cobertura_transcripcion,
    motivo_no_apto   = EXCLUDED.motivo_no_apto,
    panel            = EXCLUDED.panel,
    n_words          = EXCLUDED.n_words,
    duration_seconds = EXCLUDED.duration_seconds,
    lang             = EXCLUDED.lang,
    transcript_source= EXCLUDED.transcript_source,
    has_description  = EXCLUDED.has_description,
    has_tags         = EXCLUDED.has_tags,
    ritmo_ppm             = EXCLUDED.ritmo_ppm,
    ritmo_ppm_pct         = EXCLUDED.ritmo_ppm_pct,
    cifras_100w           = EXCLUDED.cifras_100w,
    cifras_100w_pct       = EXCLUDED.cifras_100w_pct,
    atribucion_1000w      = EXCLUDED.atribucion_1000w,
    atribucion_1000w_pct  = EXCLUDED.atribucion_1000w_pct,
    mattr_200             = EXCLUDED.mattr_200,
    mattr_200_pct         = EXCLUDED.mattr_200_pct,
    conectores_1000w      = EXCLUDED.conectores_1000w,
    conectores_1000w_pct  = EXCLUDED.conectores_1000w_pct,
    enlaces_externos      = EXCLUDED.enlaces_externos,
    enlaces_externos_pct  = EXCLUDED.enlaces_externos_pct,
    promocional_1000w     = EXCLUDED.promocional_1000w,
    promocional_1000w_pct = EXCLUDED.promocional_1000w_pct,
    cobertura_titulo      = EXCLUDED.cobertura_titulo,
    cobertura_titulo_pct  = EXCLUDED.cobertura_titulo_pct
""")


def _num(v):
    """A float de Python, o None.

    Tres cosas se cuelan si no se filtra aca: los float64 de numpy, que
    psycopg2 no sabe adaptar; los NaN, que Postgres acepta en real y despues
    envenenan cualquier AVG(); y los bool, que en Python son int y entrarian
    como 1.0 sin querer.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def guardar(fila: dict, desc: dict, filas_panel: list[dict], fmt: str | None,
            lang: str, apto: bool, motivo: str | None) -> None:
    """Upsert del panel en content_features. Nunca propaga una excepcion:
    el panel es lo que el usuario pidio, la fila es contabilidad interna."""
    escala = cargar_escala()
    pct = {f["clave"]: f.get("percentil") for f in filas_panel}

    p = {
        "content_item_id": fila.get("id"),
        "features_version": FEATURES_VERSION,
        "computed_at": datetime.now(timezone.utc),
        "frame_version": escala.get("frame_version"),
        "formato": fmt,
        "apto": bool(apto),
        "cobertura_transcripcion": _num(desc.get("v_cobertura_transcripcion")),
        "motivo_no_apto": motivo,
        "panel": json.dumps(filas_panel, ensure_ascii=False, default=str),
        "n_words": fila.get("transcript_word_count")
                   or len((fila.get("transcript") or "").split()) or None,
        "duration_seconds": fila.get("duration_seconds"),
        "lang": lang,
        "transcript_source": fila.get("transcript_source"),
        "has_description": bool((fila.get("description") or "").strip()),
        "has_tags": bool(fila.get("tags")),
    }
    for k in DESCRIPTORES_COL:
        p[k] = _num(desc.get(k))
        p[f"{k}_pct"] = _num(pct.get(k))

    if not p["content_item_id"]:
        return
    try:
        with engine.begin() as c:
            c.execute(UPSERT, p)
    except Exception as e:
        logger.warning(f"no se pudo guardar content_features de "
                       f"{fila.get('external_id')}: {e}")


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
        # NO se llama a Supadata desde aca. El enriquecimiento en background
        # que dispara POST /videos ya lo hace, y es la unica parte del sistema
        # que gasta creditos. Si el panel tambien llamara, cada video nuevo
        # costaria dos en vez de uno.
        #
        # La fila todavia no existe: el POST de la extension no llego o no
        # termino. Vale la pena esperar, porque llega en un segundo.
        return {"video_id": video_id, "apto": None, "estado": "procesando",
                "registrado": False,
                "mensaje": "Analizando el video…",
                "frame_version": escala["frame_version"]}

    if not (fila.get("transcript") or "").strip():
        # La fila existe pero no hay texto. Puede ser que el enriquecimiento
        # siga corriendo, o que ya haya terminado sin conseguir nada. No es lo
        # mismo y no se puede contestar igual: girar para siempre es la peor
        # de las respuestas posibles, porque no se distingue de estar roto.
        return {"video_id": video_id,
                **_sin_transcripcion(fila, escala["frame_version"])}

    desc = calcular_descriptores(fila)
    fmt = fila.get("stratum_format") or _formato(fila.get("category_id"))
    lang = desc.get("_lang") or "es"

    if not desc.get("v_apto_panel"):
        # Se guarda igual. Un video que no se puede medir es un dato, no un
        # vacio: la parte mas fuerte del estudio compara justamente cuantos
        # videos de cada formato caen aca.
        guardar(fila, desc, ubicar(desc, fmt), fmt, lang, False,
                "cobertura_de_habla_insuficiente")
        return {"video_id": video_id, "apto": False,
                "motivo": "cobertura_de_habla_insuficiente",
                "cobertura": desc.get("v_cobertura_transcripcion"),
                "mensaje": "Sin datos suficientes para mostrar el panel.",
                "frame_version": escala["frame_version"]}

    filas_panel = ubicar(desc, fmt)
    guardar(fila, desc, filas_panel, fmt, lang, True, None)

    return {
        "video_id": video_id,
        "apto": True,
        "origen_transcripcion": origen,
        "formato": fmt,
        "frame_version": escala["frame_version"],
        "descriptores": filas_panel,
        # La escala de referencia se construyo con 344 videos en espanol. Si el
        # texto medido esta en otro idioma, los percentiles siguen calculandose
        # pero comparan contra una poblacion que no le corresponde. Se avisa en
        # vez de ocultarlo.
        "aviso_idioma": (None if str(fila.get("transcript_lang") or "es").lower().startswith("es")
                         else f"La transcripción está en '{fila.get('transcript_lang')}'. "
                              "La escala de referencia es de videos en español: "
                              "los percentiles no son estrictamente comparables."),
        "etiquetas": {k: v for k, v in desc.items() if k.startswith("et_")},
        "nota": ("Los percentiles son relativos al corpus de referencia de "
                 "YouTube en espanol, agosto 2026. No son una calificacion."),
    }
