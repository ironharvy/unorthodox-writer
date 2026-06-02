"""Tier enforcement middleware and helpers."""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import FREE_MAX_WORDS, FREE_MAX_DAILY_STORIES, FREE_MAX_SAVED_STORIES
from database import get_db
from models import User, Story
from auth import get_current_user


def check_story_creation(
    prompt_length: int,
    max_words: int,
    current_user: User,
    db: Session,
) -> None:
    """Raise HTTPException if the user's tier forbids this story."""

    if current_user.tier != "free":
        return  # paid — no limits

    # Word count check
    if max_words > FREE_MAX_WORDS:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Free tier limited to {FREE_MAX_WORDS} words per story. Upgrade for longer stories.",
        )

    # Daily rate limit
    today = datetime.now(timezone.utc).date()
    start_of_day = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    stories_today = (
        db.query(Story)
        .filter(Story.user_id == current_user.id, Story.created_at >= start_of_day)
        .count()
    )
    if stories_today >= FREE_MAX_DAILY_STORIES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Free tier limited to {FREE_MAX_DAILY_STORIES} stories per day. You've reached today's limit.",
        )

    # Saved stories check
    total_saved = (
        db.query(Story)
        .filter(Story.user_id == current_user.id, Story.status == "complete")
        .count()
    )
    if total_saved >= FREE_MAX_SAVED_STORIES:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Free tier limited to {FREE_MAX_SAVED_STORIES} saved stories. Delete some to create new ones.",
        )


def enforce_read_limits(
    current_user: User,
    db: Session,
) -> None:
    """Enforce limits on reading stories (free: only last 3). Not a hard error, just used by the route."""
    pass  # Logic is applied in the route itself
