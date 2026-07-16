# app/schemas.py
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class VideoCreate(BaseModel):
    """Payload que envía la extensión de Chrome. Sin cambios para mantener compatibilidad."""
    video_id: str
    title: str
    url: str
    channel: Optional[str] = None
    duration_seconds: Optional[int] = None
    view_count_raw: Optional[str] = None
    tracked_at: Optional[datetime] = None


class ContentItemRead(BaseModel):
    """Respuesta de la API: content item + su score más reciente."""
    id: int
    source: str
    external_id: str
    url: str
    title: str
    channel: Optional[str] = None
    duration_seconds: Optional[int] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    watched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # Score del content_scores más reciente
    score_letter: Optional[str] = None
    score_numeric: Optional[float] = None
    score_labels: Optional[List[str]] = None
    scoring_done: bool = False

    class Config:
        from_attributes = True


class ScoreRead(BaseModel):
    """Score de un ítem, listo para consumir desde la extensión."""
    content_item_id: int
    youtube_id: str
    score_letter: Optional[str] = None
    score_numeric: Optional[float] = None
    score_labels: Optional[List[str]] = None
    score_details: Optional[Any] = None
    scoring_done: bool = False
    scorer_version: Optional[str] = None
