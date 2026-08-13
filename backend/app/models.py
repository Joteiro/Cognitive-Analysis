# app/models.py
"""
Modelos SQLAlchemy.

POR QUE ESTE ARCHIVO ESTABA ROTO (2026-08-13)
---------------------------------------------
La tabla content_items tiene 44 columnas en Postgres. Este modelo declaraba
20. Las otras 24 se agregaron por migraciones SQL y el worker local las usa
con psycopg2 crudo, asi que nunca hizo falta declararlas aca... hasta que el
backend empezo a escribirlas.

SQLAlchemy no avisa. Trata a una columna no declarada de dos maneras, y las
dos son trampas:

  - ESCRIBIR  item.transcript_source = "supadata"
    No falla. Crea un atributo de Python cualquiera, como si el objeto fuera
    un diccionario. El commit sale bien y la columna queda en null. Es la
    razon real por la que transcript_source, transcript_lang y
    transcript_word_count seguian vacias despues de "arreglarlas": el arreglo
    estaba bien, el mensaje nunca llegaba a la base.

  - LEER      if not item.upload_date:
    Eso SI falla, con AttributeError. Y como la lectura estaba adentro del
    try/except del enriquecimiento, el except hacia rollback y se llevaba
    puesto TODO lo demas: transcripcion, descripcion, categoria, vistas. Por
    eso las filas de las 17:34, 17:48 y 18:03 quedaron completamente vacias,
    sin siquiera un enrichment_status que dijera que algo habia fallado.

La imagen es la de una carta con la direccion incompleta: el cartero no vuelve
a decirte que no la pudo entregar, simplemente no llega. Y si ademas pedis
acuse de recibo de una direccion que no existe, ahi si se rompe todo.

Ahora el modelo declara las 44 columnas y coincide con la base.

NOTA sobre create_all() en main.py: solo CREA tablas que faltan, nunca altera
las que ya existen. Agregar columnas aca no toca la base — solo le ensena a
SQLAlchemy que existen.
"""
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text,
    DateTime, Date, Float, Boolean, JSON, ForeignKey
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class RawEvent(Base):
    """Ingesta cruda e inmutable. Guarda el payload exacto que manda la extensión."""
    __tablename__ = "raw_events"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    source      = Column(String(20), nullable=False, default="youtube")
    payload     = Column(JSON, nullable=False)


class ContentItem(Base):
    """Un ítem de contenido único (un video de YouTube). Datos enriquecidos y limpios."""
    __tablename__ = "content_items"

    # ── identidad y metadatos base ────────────────────────────────────────
    id                    = Column(BigInteger, primary_key=True, autoincrement=True)
    source                = Column(String(20), nullable=False, default="youtube")
    external_id           = Column(String(100), unique=True, nullable=False, index=True)
    url                   = Column(Text, nullable=False)
    title                 = Column(Text, nullable=False)
    channel               = Column(Text)
    duration_seconds      = Column(Integer)
    description           = Column(Text)
    tags                  = Column(JSONB)          # lista de strings
    category_id           = Column(String(10))
    category_name         = Column(String(50))
    view_count            = Column(BigInteger)
    like_count            = Column(Integer)
    comment_count         = Column(Integer)
    stats_fetched_at      = Column(DateTime(timezone=True))
    watched_at            = Column(DateTime(timezone=True))
    created_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # ── canal e idioma (migracion 003) ────────────────────────────────────
    # video_language es el idioma que DECLARA el canal. No es lo mismo que
    # transcript_lang, que es el de la pista que efectivamente se bajo, y por
    # eso son dos columnas y no una: en un video con audio en espanol y
    # subtitulo manual en ingles, difieren, y el lexico lo tiene que decidir
    # el segundo.
    upload_date           = Column(Date)
    channel_id            = Column(String(50))
    video_language        = Column(String(40))

    # ── transcripcion (migraciones 002 y 006) ─────────────────────────────
    transcript            = Column(Text)
    transcript_fetched_at = Column(DateTime(timezone=True))
    transcript_source     = Column(String(20))   # youtube_auto | youtube_manual | supadata | extension
    transcript_lang       = Column(String(40))   # varchar(40) desde la 006: 'es-uYU-mmqFLq8' medía 14
    transcript_is_generated = Column(Boolean)    # null = no se sabe, y es preferible a inventarlo
    transcript_word_count = Column(Integer)
    transcript_segments   = Column(JSONB)
    chapters              = Column(JSONB)
    n_chapters            = Column(Integer)

    # ── estado del enriquecimiento (migracion 004) ────────────────────────
    # Vocabulario compartido entre el worker local y el backend:
    # ok | no_subs | exhausted | geo_blocked | partial | error.
    # enricher_version es lo que distingue quien la escribio.
    enrichment_status     = Column(String(20))
    enrichment_error      = Column(Text)
    enriched_at           = Column(DateTime(timezone=True))
    enricher_version      = Column(String(20))
    attempts              = Column(Integer)
    next_attempt_at       = Column(DateTime(timezone=True))
    last_attempt_at       = Column(DateTime(timezone=True))

    # ── corpus de referencia (migracion 005) ──────────────────────────────
    # 'historial' = lo que mira Juan. 'referencia' = la muestra publica con la
    # que se construyo la escala. NO se mezclan: los percentiles se calculan
    # solo sobre 'referencia', porque medir el historial contra si mismo seria
    # circular.
    corpus                = Column(String(20))
    sampling_source       = Column(String(40))
    sampling_seed         = Column(Text)
    stratum_format        = Column(String(40))
    stratum_duration      = Column(String(40))
    sampled_at            = Column(DateTime(timezone=True))
    sampling_frame_version = Column(String(40))

    scores = relationship(
        "ContentScore",
        back_populates="content_item",
        order_by="desc(ContentScore.scored_at)",
        cascade="all, delete-orphan",
    )


class ContentScore(Base):
    """Historial de scores (letra A-E).

    RETIRADO el 2026-08-13: no se escriben filas nuevas. Se conserva porque es
    la evidencia de lo que el sistema decia antes del cambio, y sostiene el
    capitulo de la memoria donde se explica por que se reemplazo por el panel.
    """
    __tablename__ = "content_scores"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    content_item_id = Column(
        BigInteger,
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scorer_version  = Column(String(20), nullable=False, default="1.0")
    score_letter    = Column(String(1))
    score_numeric   = Column(Float)
    score_labels    = Column(JSON)    # lista de strings
    score_details   = Column(JSON)    # dict con breakdown de señales
    scored_at       = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    content_item = relationship("ContentItem", back_populates="scores")
