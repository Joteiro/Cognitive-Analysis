# app/youtube_api.py
"""
Cliente para la YouTube Data API v3.
Obtiene descripción, tags, categoría y estadísticas de un video.
Si YOUTUBE_API_KEY no está configurada, devuelve None sin crashear.
"""
import os
import logging
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


def fetch_video_metadata(youtube_id: str) -> dict | None:
    """
    Llama a videos.list con parts=snippet,statistics.
    Devuelve un dict con los campos enriquecidos, o None si falla.
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
                "part": "snippet,statistics",
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
        cat_id   = snippet.get("categoryId", "")

        return {
            "description":   snippet.get("description", ""),
            "tags":          snippet.get("tags", []),          # lista de strings
            "category_id":   cat_id,
            "category_name": CATEGORY_MAP.get(cat_id, "Other"),
            "view_count":    int(stats.get("viewCount",    0) or 0),
            "like_count":    int(stats.get("likeCount",    0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
        }

    except Exception as exc:
        logger.warning(f"Error al enriquecer {youtube_id} vía YouTube API: {exc}")
        return None
