# app/transcript_api.py
"""
Cliente de Supadata para transcripciones.

TRES COSAS QUE ESTA VERSION ARREGLA
-----------------------------------
1. PIDE EL IDIOMA. Antes no lo especificaba y Supadata elegia la pista que
   quisiera: en un video con subtitulo manual en ingles y automatico en
   espanol, devolvia el ingles. Y como el idioma no se guardaba, el calculo de
   descriptores asumia espanol y le aplicaba los lexicos espanoles a un texto
   en ingles. Los conectores, la atribucion y lo promocional de ese video salian
   sin sentido, sin que nada avisara.

2. mode=native. Prohibe el fallback a Whisper, que cobra POR MINUTO DE AUDIO.
   El 2026-08-12 una sola llamada asi consumio 134 creditos y agoto el plan.
   Un 202 es la senal de que Supadata arranco Whisper.

3. DEVUELVE METADATOS, no solo texto. El idioma real, la fuente y el conteo de
   palabras hacen falta para llenar transcript_lang, transcript_source y
   transcript_word_count, que hasta ahora quedaban en null.

Si SUPADATA_API_KEY no esta configurada, devuelve un resultado vacio sin
romper nada.
"""
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

SUPADATA_URL = "https://api.supadata.ai/v1/transcript"

# Orden de preferencia. El corpus de referencia y toda la escala estan en
# espanol, asi que una transcripcion en ingles no es equivalente: se acepta
# como ultimo recurso pero queda marcada para poder filtrarla despues.
IDIOMAS = ["es", None]      # None = lo que Supadata tenga


def _texto_de(data: dict) -> str:
    c = data.get("content")
    if isinstance(c, str):
        t = c
    elif isinstance(c, list):
        t = " ".join(s.get("text", "") for s in c if isinstance(s, dict))
    else:
        return ""
    return " ".join(t.split()).strip()


def _pedir(video_url: str, api_key: str, lang: str | None, timeout: int) -> dict:
    params = {"url": video_url, "text": "true", "mode": "native"}
    if lang:
        params["lang"] = lang
    try:
        r = requests.get(SUPADATA_URL, params=params,
                         headers={"x-api-key": api_key}, timeout=timeout)
    except Exception as e:
        return {"estado": f"error_red: {e}"}

    if r.status_code == 202:
        # Whisper arrancado pese a mode=native: el video no tiene subtitulos
        # nativos. No se espera el job — esos videos quedan fuera de la escala
        # igual, y esperarlo cuesta creditos por minuto de audio.
        return {"estado": "whisper_evitado"}

    if r.status_code == 429:
        # 429 significa DOS cosas distintas y hasta ahora las tratabamos como
        # una sola, con el mensaje mas alarmante de los dos:
        #
        #   - Se acabo el saldo del plan  -> no hay nada que hacer hasta que
        #     se reponga.
        #   - Demasiadas peticiones por minuto -> el saldo esta intacto y con
        #     esperar unos segundos alcanza.
        #
        # Decirle a alguien que se quedo sin creditos cuando le sobran es
        # peor que no decir nada: manda a resolver el problema equivocado.
        # La unica forma de distinguirlos es leer el cuerpo de la respuesta.
        cuerpo = (r.text or "")[:300]
        low = cuerpo.lower()

        # Supadata usa el MISMO codigo `limit-exceeded` para los dos casos.
        # Lo que los separa esta en `details`:
        #
        #   "Request rate limit on current plan was exceeded."  -> ritmo
        #   (algo sobre cuota mensual / creditos)               -> saldo
        #
        # Un primer intento de clasificar esto busco "limit-exceeded" y "plan"
        # como senales de saldo agotado. Las dos aparecen tambien en el error
        # de ritmo, asi que clasificaba mal justo el caso frecuente. Hay que
        # mirar "rate limit" primero: es la frase que solo aparece en uno.
        es_ritmo = "rate limit" in low or "too many requests" in low
        return {"estado": "rate_limit" if es_ritmo else "sin_creditos",
                "detalle": cuerpo,
                "reintentar_en": int(r.headers.get("retry-after") or 0)}

    if r.status_code != 200:
        return {"estado": f"http_{r.status_code}", "detalle": r.text[:150]}
    try:
        d = r.json()
    except ValueError:
        return {"estado": "respuesta_no_json"}

    texto = _texto_de(d)
    if not texto:
        return {"estado": "vacio"}
    return {"estado": "ok", "texto": texto,
            "lang": d.get("lang") or lang,
            "disponibles": d.get("availableLangs")}


def fetch_transcript_detallado(video_url: str, video_id: str | None = None,
                               timeout: int = 45) -> dict:
    """Devuelve un dict siempre, nunca lanza:

        {"texto": str|None, "lang": str|None, "source": "supadata"|None,
         "palabras": int, "estado": str, "es_espanol": bool}

    Prueba primero en espanol; si no hay pista en espanol, acepta la que haya
    pero lo deja registrado en `lang` para que se pueda filtrar despues.
    """
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        logger.warning("SUPADATA_API_KEY no configurada — se omite el transcript.")
        return {"texto": None, "estado": "sin_api_key", "palabras": 0}

    ultimo = {}
    for lang in IDIOMAS:
        res = _pedir(video_url, api_key, lang, timeout)

        # Rate limit: el saldo esta bien, sobran peticiones por minuto. Se
        # espera y se vuelve a probar UNA vez. Abrir tres videos seguidos en
        # el navegador dispara varias llamadas casi simultaneas y es
        # exactamente el caso que hay que sobrevivir.
        if res.get("estado") == "rate_limit":
            espera = min(max(res.get("reintentar_en") or 0, 20), 45)
            logger.warning(f"{video_id}: Supadata limito el ritmo, "
                           f"reintento en {espera}s. {res.get('detalle', '')[:120]}")
            time.sleep(espera)
            res = _pedir(video_url, api_key, lang, timeout)

        ultimo = res
        if res.get("estado") == "ok":
            devuelto = (res.get("lang") or "").lower()
            if lang == "es" and devuelto and not devuelto.startswith("es"):
                # Pedimos espanol y nos dio otra cosa: no insistir, pero avisar.
                logger.warning(f"{video_id}: se pidio 'es' y devolvio '{devuelto}'")
            texto = res["texto"]
            return {
                "texto": texto,
                "lang": devuelto or (lang or "desconocido"),
                "source": "supadata",
                "palabras": len(texto.split()),
                "estado": "ok",
                "es_espanol": devuelto.startswith("es") if devuelto else (lang == "es"),
                "disponibles": res.get("disponibles"),
            }
        # No tiene sentido reintentar en otro idioma si el problema es de cuota
        # o de que el video directamente no tiene subtitulos nativos.
        if res.get("estado") in ("sin_creditos", "whisper_evitado", "rate_limit"):
            break

    logger.warning(f"Transcript no disponible para {video_id}: "
                   f"{ultimo.get('estado')} {str(ultimo.get('detalle') or '')[:150]}")
    return {"texto": None, "estado": ultimo.get("estado", "desconocido"),
            "detalle": ultimo.get("detalle"), "palabras": 0}


def fetch_transcript(video_url: str, video_id: str | None = None) -> str | None:
    """Compatibilidad con el codigo viejo: solo el texto."""
    return fetch_transcript_detallado(video_url, video_id).get("texto")
