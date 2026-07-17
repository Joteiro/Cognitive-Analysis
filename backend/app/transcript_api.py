# app/transcript_api.py
"""
Cliente para la API de transcripts de Supadata (https://supadata.ai).
Resuelve el bloqueo de YouTube a las IPs de datacenter: Supadata obtiene el
transcript por su cuenta (subtítulos nativos, con fallback a Whisper si el
video no tiene captions).

Si SUPADATA_API_KEY no está configurada, devuelve None sin crashear.
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

SUPADATA_URL = "https://api.supadata.ai/v1/transcript"


def fetch_transcript(video_url: str, video_id: str | None = None) -> str | None:
    """
    Pide el transcript de un video a Supadata y devuelve el texto plano.
    Devuelve None si no hay key, si falla, o si el video no tiene transcript.
    """
    api_key = os.getenv("SUPADATA_API_KEY")
    if not api_key:
        logger.warning("SUPADATA_API_KEY no configurada — se omite el transcript.")
        return None

    try:
        resp = requests.get(
            SUPADATA_URL,
            params={"url": video_url, "text": "true"},   # text=true → texto plano
            headers={"x-api-key": api_key},
            timeout=45,   # el fallback Whisper puede tardar en videos largos
        )
    except Exception as exc:
        logger.warning(f"Error al pedir transcript a Supadata para {video_id}: {exc}")
        return None

    if resp.status_code != 200:
        logger.warning(
            f"Supadata devolvió {resp.status_code} para {video_id}: {resp.text[:200]}"
        )
        return None

    try:
        data = resp.json()
    except ValueError:
        logger.warning(f"Respuesta no-JSON de Supadata para {video_id}")
        return None

    return _extract_text(data)


def _extract_text(data: dict) -> str | None:
    """
    Normaliza la respuesta a texto plano.
    Con text=true, `content` viene como string; sin él, como lista de segmentos.
    Si viene un jobId (fallback Whisper asíncrono), por ahora se omite.
    """
    content = data.get("content")

    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(seg.get("text", "") for seg in content if isinstance(seg, dict))
    else:
        # Respuesta asíncrona (job) u otro formato: no soportado en esta versión.
        if data.get("jobId"):
            logger.info("Supadata devolvió un job asíncrono; se omite (sin polling).")
        return None

    text = " ".join(text.split()).strip()
    return text or None
