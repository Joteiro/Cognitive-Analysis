# app/schemas.py
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class VideoCreate(BaseModel):
    """Payload que envia la extension de Chrome."""
    video_id: str
    title: str
    url: str
    channel: Optional[str] = None
    duration_seconds: Optional[int] = None
    view_count_raw: Optional[str] = None
    tracked_at: Optional[datetime] = None


class VideoRead(BaseModel):
    """Schema de respuesta con todos los campos del modelo."""
    id: int
    youtube_id: str
    title: str
    url: str
    channel: Optional[str] = None
    duration: Optional[int] = None
    watched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # YouTube API enrichment
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    tags: Optional[str] = None           # JSON string
    # Nutri-Score
    score_letter: Optional[str] = None
    score_numeric: Optional[float] = None
    score_labels: Optional[str] = None   # JSON string
    score_details: Optional[str] = None  # JSON string

    class Config:
        from_attributes = True


class ScoreRead(BaseModel):
    """Score de un video, listo para consumir desde la extension."""
    video_id: int
    youtube_id: str
    score_letter: Optional[str] = None
    score_numeric: Optional[float] = None
    score_labels: Optional[list] = None
    score_details: Optional[dict] = None
    scoring_done: bool = False
