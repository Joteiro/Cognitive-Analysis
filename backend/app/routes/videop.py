# app/routes/videop.py
"""
Registro de videos y enriquecimiento en background.

QUE CAMBIA EN ESTA VERSION
--------------------------
Las filas que enriquecia Render quedaban a medias comparadas con las del
worker local: channel_id, video_language, upload_date y enrichment_status en
null. No era un bug de una sola causa sino de tres, y conviene tenerlas
separadas porque se arreglan distinto:

  - channel_id / video_language / upload_date: la YouTube API SIEMPRE los
    devolvia, en la misma respuesta que ya se pagaba. fetch_video_metadata
    simplemente no los leia. Se arregla en youtube_api.py.

  - enrichment_status: era el estado de la cola del worker local. El camino de
    Render no es una cola — enriquece en linea — asi que nunca lo tocaba.
    Ahora lo escribe con el MISMO vocabulario (ok / no_subs / exhausted /
    error), para que una fila de Render y una del worker se puedan contar
    juntas. Lo que las distingue es enricher_version.

  - transcript_source / lang / word_count: ya arreglado, dependia de que
    transcript_api.py devolviera metadatos y no solo texto.

Por que importa para la memoria: sin enricher_version no se puede saber con
que instrumento se midio cada fila, y "el instrumento se filtra en la medida"
es justamente el patron que atraviesa todo el trabajo.
"""
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import SessionLocal
# El scorer v1 (letra A-E) quedo retirado: ver el bloque de abajo.
# La tabla content_scores se conserva como evidencia historica de lo que
# se reemplazo, pero no se escribe mas.
from ..scorer import SCORER_VERSION  # noqa: F401  (solo para /score historico)
from ..youtube_api import fetch_video_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["videos"])

# Identifica al instrumento. El worker local usa numeros ("2.0", "3.0"); el
# prefijo 'render-' hace que una consulta pueda separarlos sin ambiguedad.
ENRICHER_VERSION = "render-1.0"

# Traduce el estado que devuelve Supadata al vocabulario que ya vive en la
# columna enrichment_status. Se reusa el vocabulario existente en vez de
# inventar uno nuevo: si el backend dijera "sin_creditos" y el worker
# "exhausted" para lo mismo, cualquier GROUP BY futuro mentiria.
ESTADO_A_ENRICHMENT = {
    "ok":               "ok",
    "whisper_evitado":  "no_subs",    # no tiene subtitulos nativos
    "vacio":            "no_subs",
    "sin_creditos":     "exhausted",
    "sin_api_key":      "error",
}


def _cap(valor, n: int):
    """Recorta antes de que lo haga Postgres — que no trunca, aborta.

    El 2026-08-11 se perdio un transcript de 9.289 palabras porque
    transcript_lang era varchar(10) y el valor media 14 caracteres. Un idioma
    recortado es un defecto menor; perder la fila entera no lo es.
    """
    if valor is None:
        return None
    s = str(valor).strip()
    return (s[:n] if len(s) > n else s) or None


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

def run_enrichment(content_item_id: int):
    """
    Descarga transcript + metadata de YouTube API y los guarda en el
    content_item. Corre en background.

    Es la UNICA parte del sistema que llama a Supadata. El endpoint /panel
    solo lee de la base: si llamara tambien, cada video nuevo costaria dos
    creditos en vez de uno, y con un plan de 100 eso se nota.
    """
    db = SessionLocal()
    estado_tr = "ok"
    detalle_error = None
    try:
        item = db.query(models.ContentItem).filter(
            models.ContentItem.id == content_item_id
        ).first()
        if not item:
            return

        # ── Transcript ────────────────────────────────────────────────────────
        transcript_text = item.transcript
        if transcript_text:
            # Vino en el payload de la extension. Se deja constancia de la
            # fuente igual: una transcripcion del DOM y una de Supadata no son
            # el mismo instrumento, y sin esta marca no hay forma de separarlas
            # despues.
            if not item.transcript_source:
                item.transcript_source = "extension"
                item.transcript_word_count = len(transcript_text.split())
        else:
            from ..transcript_api import fetch_transcript_detallado
            tr = fetch_transcript_detallado(item.url, item.external_id)
            transcript_text = tr.get("texto")
            estado_tr = tr.get("estado", "desconocido")
            if transcript_text:
                item.transcript = transcript_text
                item.transcript_fetched_at = datetime.now(timezone.utc)
                # Estas columnas quedaban en null. Sin transcript_lang, el
                # calculo de descriptores asume espanol y le puede aplicar los
                # lexicos espanoles a un texto en ingles; sin transcript_source
                # no se puede filtrar por instrumento al analizar, que es una
                # regla del proyecto.
                item.transcript_source     = _cap(tr.get("source"), 20)
                item.transcript_lang       = _cap(tr.get("lang"), 40)
                item.transcript_word_count = tr.get("palabras")
                # Supadata no informa si la pista es automatica o humana.
                # Se deja en null a proposito en vez de inventar un valor:
                # et_calidad_dato depende de esto y un dato falso es peor que
                # un dato ausente.
                item.transcript_is_generated = None
                if not tr.get("es_espanol"):
                    logger.warning(
                        f"{item.external_id}: transcripcion en '{tr.get('lang')}', "
                        f"no en espanol. La escala de referencia es en espanol.")
            else:
                detalle_error = estado_tr
                logger.warning(
                    f"Transcript no disponible para {item.external_id}: {estado_tr}")

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

            # ── los tres que faltaban ──────────────────────────────────────
            item.channel_id     = yt_meta.get("channel_id")
            item.video_language = yt_meta.get("video_language")
            if yt_meta.get("upload_date") and not item.upload_date:
                item.upload_date = yt_meta["upload_date"]
            if not item.channel and yt_meta.get("channel_title"):
                item.channel = yt_meta["channel_title"]

            # La duracion de la API le gana a la del reproductor: es la misma
            # fuente con la que se construyo el corpus de referencia, y
            # palabras_por_minuto divide por este numero. Que las dos midan
            # distinto es normal (el reproductor cuenta lo reproducible), pero
            # una diferencia grande suele ser un vivo o un anuncio, y conviene
            # que quede en el log.
            dur_api = yt_meta.get("duration_seconds")
            if dur_api:
                if item.duration_seconds and abs(dur_api - item.duration_seconds) > max(
                        5, 0.05 * dur_api):
                    logger.info(
                        f"{item.external_id}: duracion extension "
                        f"{item.duration_seconds}s vs API {dur_api}s — se usa la API.")
                item.duration_seconds = dur_api

            logger.info(f"YT metadata: {item.external_id} → {yt_meta['category_name']}")
        elif estado_tr == "ok" and not transcript_text:
            detalle_error = "yt_api_sin_respuesta"

        # ── Estado del enriquecimiento ─────────────────────────────────────────
        # Mismo vocabulario que el worker local, para que las filas de los dos
        # caminos se puedan contar juntas. enricher_version es lo que las
        # distingue.
        item.enrichment_status = _cap(
            ESTADO_A_ENRICHMENT.get(estado_tr, "error"), 20)
        item.enrichment_error  = detalle_error
        item.enriched_at       = datetime.now(timezone.utc)
        item.enricher_version  = _cap(ENRICHER_VERSION, 20)

        # ── Score ─────────────────────────────────────────────────────────────
        # RETIRADO el 2026-08-13. Antes aca se calculaba una letra A-E y se
        # escribia en content_scores.
        #
        # Por que se saco: una letra agregada sobre ocho medidas ponderadas a
        # criterio transmite una autoridad que el sistema no tiene, y ademas se
        # demostro que el score v1 correlacionaba 0,73 con log(duracion) — la
        # mitad de su varianza era, literalmente, cuanto duraba el video.
        # Lo reemplaza el panel de descriptores (/panel), que muestra cada
        # medida por separado como percentil y nunca las combina.
        #
        # La tabla content_scores NO se borra: es la evidencia de lo que habia
        # antes y sostiene el capitulo de la memoria donde se explica por que se
        # cambio. Simplemente dejo de crecer.
        db.commit()
        logger.info(
            f"Enriquecido '{item.title}' [{item.enrichment_status}] "
            f"({'con' if transcript_text else 'sin'} transcripcion)")

    except Exception as e:
        logger.error(f"Error enriqueciendo content_item_id={content_item_id}: {e}")
        db.rollback()
        # Segunda transaccion, chica, solo para dejar registrado que fallo. Si
        # se escribiera en la misma que se acaba de revertir, el error seria
        # invisible y la fila quedaria para siempre en null, indistinguible de
        # una que nunca se intento.
        try:
            db.query(models.ContentItem).filter(
                models.ContentItem.id == content_item_id
            ).update({
                "enrichment_status": "error",
                "enrichment_error": str(e)[:500],
                "enriched_at": datetime.now(timezone.utc),
                "enricher_version": ENRICHER_VERSION,
            })
            db.commit()
        except Exception:
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
    """Recibe el payload de la extensión, guarda raw_event + content_item y lanza el enriquecimiento en background."""
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
        # Si quedo a medias de un intento anterior (sin transcripcion y sin
        # estado, o con estado de error), se reintenta. No gasta creditos de
        # mas: fetch_transcript_detallado solo llama a Supadata si no hay texto.
        if not existing.transcript and existing.enrichment_status in (None, "error"):
            background_tasks.add_task(run_enrichment, existing.id)
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
        transcript=video.transcript,
        transcript_fetched_at=datetime.now(timezone.utc) if video.transcript else None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    background_tasks.add_task(run_enrichment, item.id)
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
    """Score historico (letra A-E). RETIRADO: no se escriben filas nuevas.
    Se conserva para poder consultar lo que el sistema decia antes del cambio."""
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
        "retirado":        True,
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
