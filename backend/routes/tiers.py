"""Tier status route."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_user
from config import FREE_MAX_DAILY_STORIES, FREE_MAX_SAVED_STORIES
from database import get_db
from models import User, Story

router = APIRouter(prefix="/api/tiers", tags=["tiers"])


class TierStatusOut(BaseModel):
    tier: str
    stories_today: int
    daily_limit: int | None  # None for paid
    stories_saved: int
    max_saved: int | None  # None for paid


@router.get("/status", response_model=TierStatusOut)
def tier_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = datetime.now(timezone.utc).date()
    start_of_day = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)

    stories_today = (
        db.query(Story)
        .filter(Story.user_id == current_user.id, Story.created_at >= start_of_day)
        .count()
    )
    stories_saved = (
        db.query(Story)
        .filter(Story.user_id == current_user.id, Story.status == "complete")
        .count()
    )

    if current_user.tier == "free":
        return TierStatusOut(
            tier=current_user.tier,
            stories_today=stories_today,
            daily_limit=FREE_MAX_DAILY_STORIES,
            stories_saved=stories_saved,
            max_saved=FREE_MAX_SAVED_STORIES,
        )
    else:
        return TierStatusOut(
            tier=current_user.tier,
            stories_today=stories_today,
            daily_limit=None,
            stories_saved=stories_saved,
            max_saved=None,
        )
