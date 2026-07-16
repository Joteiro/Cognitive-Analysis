# app/models.py
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text,
    DateTime, Float, JSON, ForeignKey
)
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

    id                    = Column(BigInteger, primary_key=True, autoincrement=True)
    source                = Column(String(20), nullable=False, default="youtube")
    external_id           = Column(String(100), unique=True, nullable=False, index=True)
    url                   = Column(Text, nullable=False)
    title                 = Column(Text, nullable=False)
    channel               = Column(String)
    duration_seconds      = Column(Integer)
    description           = Column(Text)
    tags                  = Column(JSON)           # lista de strings
    category_id           = Column(String(10))
    category_name         = Column(String(50))
    view_count            = Column(BigInteger)
    like_count            = Column(Integer)
    comment_count         = Column(Integer)
    stats_fetched_at      = Column(DateTime(timezone=True))
    transcript            = Column(Text)
    transcript_fetched_at = Column(DateTime(timezone=True))
    watched_at            = Column(DateTime(timezone=True))
    created_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at            = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scores = relationship(
        "ContentScore",
        back_populates="content_item",
        order_by="desc(ContentScore.scored_at)",
        cascade="all, delete-orphan",
    )


class ContentScore(Base):
    """Historial de scores. Una fila por cada vez que se corre el scorer."""
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
