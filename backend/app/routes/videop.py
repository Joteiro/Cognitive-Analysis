# app/routes/videop.py
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import SessionLocal
from ..scorer import compute_score

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── BACKGROUND TASK ──────────────────────────────────────────────────────────

def run_scoring(video_id: int):
    """
    Descarga el transcript, calcula el score y lo persiste en la DB.
    Se ejecuta en background despues de guardar el video.
    """
    db = SessionLocal()
    try:
        video = db.query(models.Video).filter(models.Video.id == video_id).first()
        if not video:
            return

        transcript_text = None
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            entries = YouTubeTranscriptApi.get_transcript(
                video.youtube_id, languages=["es", "en", "auto"]
            )
            transcript_text = " ".join(e["text"] for e in entries)
            video.transcript = transcript_text
        except Exception as e:
            logger.warning(f"Transcript no disponible para {video.youtube_id}: {e}")

        result = compute_score(
            title=video.title,
            duration_seconds=video.duration,
            transcript=transcript_text,
        )

        video.score_letter  = result["letter"]
        video.score_numeric = result["numeric"]
        video.score_labels  = json.dumps(result["labels"], ensure_ascii=False)
        video.score_details = json.dumps(result["details"], ensure_ascii=False)

        db.commit()
        logger.info(f"Score calculado para '{video.title}': {result['letter']} ({result['numeric']})")

    except Exception as e:
        logger.error(f"Error en scoring para video_id={video_id}: {e}")
    finally:
        db.close()


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@router.post("", response_model=schemas.VideoRead, status_code=201)
def create_video(
    video: schemas.VideoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Recibe el payload de la extension, guarda el video y lanza scoring en background."""
    existing = db.query(models.Video).filter(
        models.Video.youtube_id == video.video_id
    ).first()
    if existing:
        return existing

    db_video = models.Video(
        youtube_id=video.video_id,
        title=video.title,
        url=video.url,
        channel=video.channel,
        duration=video.duration_seconds,
        watched_at=video.tracked_at,
    )
    db.add(db_video)
    db.commit()
    db.refresh(db_video)

    background_tasks.add_task(run_scoring, db_video.id)

    return db_video


@router.get("", response_model=List[schemas.VideoRead])
def list_videos(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Devuelve los videos guardados, ordenados del mas reciente al mas antiguo."""
    return (
        db.query(models.Video)
        .order_by(models.Video.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


# IMPORTANTE: esta ruta debe ir ANTES de /{video_id} para evitar conflictos de matching
@router.get("/by-youtube/{youtube_id}/score")
def get_score_by_youtube_id(youtube_id: str, db: Session = Depends(get_db)):
    """
    Devuelve el score de un video por su youtube_id.
    La extension usa este endpoint para mostrar el badge.
    """
    video = db.query(models.Video).filter(
        models.Video.youtube_id == youtube_id
    ).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")

    scoring_done = video.score_letter is not None

    return {
        "video_id":     video.id,
        "youtube_id":   video.youtube_id,
        "score_letter":  video.score_letter,
        "score_numeric": video.score_numeric,
        "score_labels":  json.loads(video.score_labels)  if video.score_labels  else None,
        "score_details": json.loads(video.score_details) if video.score_details else None,
        "scoring_done":  scoring_done,
    }


@router.get("/{video_id}", response_model=schemas.VideoRead)
def get_video(video_id: int, db: Session = Depends(get_db)):
    """Devuelve un video por su ID interno."""
    video = db.query(models.Video).filter(models.Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    return video
