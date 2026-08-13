# app/youtube_api.py
"""
Cliente para la YouTube Data API v3.
Obtiene descripción, tags, categoría, estadísticas y datos del canal.
Si YOUTUBE_API_KEY no está configurada, devuelve None sin crashear.

QUE CAMBIO (2026-08-13)
-----------------------
Esta función pedía `part=snippet,statistics` y después tiraba a la basura la
mitad del snippet. channelId, defaultAudioLanguage y publishedAt venían en la
MISMA respuesta y no se leían: por eso channel_id, video_language y
upload_date quedaban en null en toda fila enriquecida por Render, mientras que
las del worker local sí los tenían.

No cuesta cuota extra: videos.list vale 1 unidad sin importar cuántos `part`
pidas. Es información que ya se estaba pagando y descartando.
"""
import os
import re
import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

# Mapa de categoryId → nombre legible
CATEGORY_MAP = {
    "1":  "Film & Animation",
    "2":  "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "19": "Travel & Events",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
}


def _cap(valor, n: int):
    """Recorta a n caracteres antes de que lo haga Postgres.

    El 2026-08-11 se perdió un transcript de 9.289 palabras porque
    transcript_lang era varchar(10) y el valor medía 14: Postgres no trunca,
    aborta la transacción entera. Un idioma recortado es un defecto menor;
    perder la fila no lo es.
    """
    if valor is None:
        return None
    s = str(valor).strip()
    return (s[:n] if len(s) > n else s) or None


def _duracion_iso(txt: str | None) -> int | None:
    """PT1H2M3S → 3723 segundos. YouTube devuelve la duración en ISO-8601."""
    if not txt:
        return None
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", txt)
    if not m:
        return None
    h, mi, s = (int(g or 0) for g in m.groups())
    return (h * 3600 + mi * 60 + s) or None


def fetch_video_metadata(youtube_id: str) -> dict | None:
    """
    Llama a videos.list y devuelve los campos enriquecidos, o None si falla.

    video_language es el idioma que DECLARA el canal, que no es lo mismo que
    el idioma de la pista que bajó Supadata: por eso se guarda aparte de
    transcript_lang y no se pisan entre sí.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        logger.warning("YOUTUBE_API_KEY no configurada — se omite enriquecimiento de la API.")
        return None

    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "id":   youtube_id,
                # contentDetails se agrega para tener la duración desde la
                # fuente. La que manda la extensión sale del reproductor y en
                # vivos o anuncios puede venir mal, y palabras_por_minuto
                # divide por ese número.
                "part": "snippet,statistics,contentDetails",
                "key":  api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            logger.warning(f"YouTube API no devolvió resultados para {youtube_id}")
            return None

        item     = items[0]
        snippet  = item.get("snippet", {})
        stats    = item.get("statistics", {})
        detalles = item.get("contentDetails", {})
        cat_id   = snippet.get("categoryId", "")

        # publishedAt viene como '2024-03-15T14:22:01Z'. La columna es date,
        # así que alcanza con los diez primeros caracteres.
        pub = snippet.get("publishedAt") or ""
        try:
            subida = date.fromisoformat(pub[:10]) if len(pub) >= 10 else None
        except ValueError:
            subida = None

        return {
            "description":   snippet.get("description", ""),
            "tags":          snippet.get("tags", []),          # lista de strings
            "category_id":   cat_id,
            "category_name": CATEGORY_MAP.get(cat_id, "Other"),
            "view_count":    int(stats.get("viewCount",    0) or 0),
            "like_count":    int(stats.get("likeCount",    0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),

            # ── lo que faltaba ────────────────────────────────────────────
            "channel_id":    _cap(snippet.get("channelId"), 50),
            "channel_title": snippet.get("channelTitle"),
            # defaultAudioLanguage es el idioma del audio; defaultLanguage el
            # de los metadatos. El primero es el que importa para elegir el
            # léxico, así que va primero.
            "video_language": _cap(
                snippet.get("defaultAudioLanguage")
                or snippet.get("defaultLanguage"), 40),
            "upload_date":      subida,
            "duration_seconds": _duracion_iso(detalles.get("duration")),
        }

    except Exception as exc:
        logger.warning(f"Error al enriquecer {youtube_id} vía YouTube API: {exc}")
        return None
