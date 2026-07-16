# app/routes/videop.py
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import SessionLocal
from ..scorer import compute_score, SCORER_VERSION
from ..youtube_api import fetch_video_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])


# ─── DB SESSION ───────────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _latest_score(content_item_id: int, db: Session) -> models.ContentScore | None:
    return (
        db.query(models.ContentScore)
        .filter(models.ContentScore.content_item_id == content_item_id)
        .order_by(models.ContentScore.scored_at.desc())
        .first()
    )


def _to_read(item: models.ContentItem, db: Session) -> schemas.ContentItemRead:
    score = _latest_score(item.id, db)
    return schemas.ContentItemRead(
        id=item.id,
        source=item.source,
        external_id=item.external_id,
        url=item.url,
        title=item.title,
        channel=item.channel,
        duration_seconds=item.duration_seconds,
        category_id=item.category_id,
        category_name=item.category_name,
        view_count=item.view_count,
        like_count=item.like_count,
        comment_count=item.comment_count,
        watched_at=item.watched_at,
        created_at=item.created_at,
        score_letter=score.score_letter   if score else None,
        score_numeric=score.score_numeric if score else None,
        score_labels=score.score_labels   if score else None,
        scoring_done=score is not None,
    )


# ─── BACKGROUND TASK ──────────────────────────────────────────────────────────

def run_scoring(content_item_id: int):
    """
    Descarga transcript + metadata de YouTube API, calcula el score
    y lo guarda en content_scores. Se ejecuta en background.
    """
    db = SessionLocal()
    try:
        item = db.query(models.ContentItem).filter(
            models.ContentItem.id == content_item_id
        ).first()
        if not item:
            return

        # ── Transcript ────────────────────────────────────────────────────────
        transcript_text = None
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            entries = YouTubeTranscriptApi.get_transcript(
                item.external_id, languages=["es", "en", "auto"]
            )
            transcript_text = " ".join(e["text"] for e in entries)
            item.transcript = transcript_text
            item.transcript_fetched_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.warning(f"Transcript no disponible para {item.external_id}: {e}")

        # ── YouTube API metadata ───────────────────────────────────────────────
        yt_meta = fetch_video_metadata(item.external_id)
        if yt_meta:
            item.description      = yt_meta["description"]
            item.tags             = yt_meta["tags"]
            item.category_id      = yt_meta["category_id"]
            item.category_name    = yt_meta["category_name"]
            item.view_count       = yt_meta["view_count"]
            item.like_count       = yt_meta["like_count"]
            item.comment_count    = yt_meta["comment_count"]
            item.stats_fetched_at = datetime.now(timezone.utc)
            logger.info(f"YT metadata: {item.external_id} → {yt_meta['category_name']}")

        # ── Score ─────────────────────────────────────────────────────────────
        result = compute_score(
            title=item.title,
            duration_seconds=item.duration_seconds,
            transcript=transcript_text,
            category_id=yt_meta["category_id"]    if yt_meta else None,
            view_count=yt_meta["view_count"]       if yt_meta else None,
            like_count=yt_meta["like_count"]       if yt_meta else None,
            comment_count=yt_meta["comment_count"] if yt_meta else None,
            description=yt_meta["description"]     if yt_meta else None,
        )

        score = models.ContentScore(
            content_item_id=item.id,
            scorer_version=SCORER_VERSION,
            score_letter=result["letter"],
            score_numeric=result["numeric"],
            score_labels=result["labels"],
            score_details=result["details"],
        )
        db.add(score)
        db.commit()
        logger.info(
            f"Score '{item.title}': {result['letter']} ({result['numeric']}) [v{SCORER_VERSION}]"
        )

    except Exception as e:
        logger.error(f"Error en scoring content_item_id={content_item_id}: {e}")
        db.rollback()
    finally:
        db.close()


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@router.post("", response_model=schemas.ContentItemRead, status_code=201)
def create_video(
    video: schemas.VideoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Recibe el payload de la extensión, guarda raw_event + content_item y lanza scoring."""
    # Siempre guardamos el raw event (auditoría)
    raw_event = models.RawEvent(
        source="chrome_extension",
        payload=video.model_dump(mode="json"),
    )
    db.add(raw_event)

    # Deduplicar: si el video ya existe, devolvemos el existente
    existing = db.query(models.ContentItem).filter(
        models.ContentItem.external_id == video.video_id
    ).first()
    if existing:
        db.commit()
        return _to_read(existing, db)

    # Nuevo content item
    item = models.ContentItem(
        source="youtube",
        external_id=video.video_id,
        url=video.url,
        title=video.title,
        channel=video.channel,
        duration_seconds=video.duration_seconds,
        watched_at=video.tracked_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    background_tasks.add_task(run_scoring, item.id)
    return _to_read(item, db)


@router.get("", response_model=List[schemas.ContentItemRead])
def list_videos(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    """Lista los ítems de contenido ordenados del más reciente al más antiguo."""
    items = (
        db.query(models.ContentItem)
        .order_by(models.ContentItem.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_to_read(item, db) for item in items]


# IMPORTANTE: esta ruta va ANTES de /{item_id} para evitar conflictos de matching
@router.get("/by-youtube/{youtube_id}/score")
def get_score_by_youtube_id(youtube_id: str, db: Session = Depends(get_db)):
    """Devuelve el score más reciente de un video por su youtube_id. Usado por la extensión."""
    item = db.query(models.ContentItem).filter(
        models.ContentItem.external_id == youtube_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video no encontrado")

    score = _latest_score(item.id, db)

    return {
        "content_item_id": item.id,
        "youtube_id":      item.external_id,
        "score_letter":    score.score_letter   if score else None,
        "score_numeric":   score.score_numeric  if score else None,
        "score_labels":    score.score_labels   if score else None,
        "score_details":   score.score_details  if score else None,
        "scoring_done":    score is not None,
        "scorer_version":  score.scorer_version if score else None,
    }


@router.get("/{item_id}", response_model=schemas.ContentItemRead)
def get_video(item_id: int, db: Session = Depends(get_db)):
    """Devuelve un ítem por su ID interno."""
    item = db.query(models.ContentItem).filter(
        models.ContentItem.id == item_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video no encontrado")
    return _to_read(item, db)
