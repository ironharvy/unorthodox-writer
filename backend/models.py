"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    tier = Column(String, nullable=False, default="free")  # "free" or "paid"
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    stories = relationship("Story", back_populates="user", order_by="Story.created_at.desc()")


class Story(Base):
    __tablename__ = "stories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=True)
    prompt = Column(Text, nullable=False)
    full_text = Column(Text, nullable=True)
    genre = Column(String, nullable=True)
    style = Column(String, nullable=True)
    pov = Column(String, nullable=True)
    # Requested target length, captured at creation. Drives free/paid routing
    # and (for paid) whether the short-story or novel pipeline runs.
    max_words = Column(Integer, nullable=False, default=200)
    word_count = Column(Integer, default=0)
    status = Column(String, nullable=False, default="generating")  # generating | complete | failed
    created_at = Column(DateTime, nullable=False, default=_utcnow)

    user = relationship("User", back_populates="stories")
