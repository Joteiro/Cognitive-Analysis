from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from .database import Base

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    youtube_id = Column(String, unique=True, index=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    channel = Column(String)
    duration = Column(Integer)
    description = Column(Text)
    watched_at = Column(DateTime)
    transcript = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # YouTube API enrichment
    view_count    = Column(Integer, nullable=True)
    like_count    = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)
    category_id   = Column(String(10), nullable=True)
    category_name = Column(String(50), nullable=True)
    tags          = Column(Text, nullable=True)         # JSON: ["tag1", "tag2", ...]

    # Nutri-Score
    score_letter  = Column(String(1), nullable=True)   # A / B / C / D / E
    score_numeric = Column(Float, nullable=True)        # 0-100
    score_labels  = Column(Text, nullable=True)         # JSON: ["⚡ Alto estímulo", ...]
    score_details = Column(Text, nullable=True)         # JSON: breakdown de señales
