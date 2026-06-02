"""Story CRUD and SSE streaming endpoints."""

import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from auth import get_current_user
from config import FREE_MAX_SAVED_STORIES
from database import get_db
from middleware.tier import check_story_creation, enforce_read_limits
from models import User, Story

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stories", tags=["stories"])

# Paid-tier stories longer than this switch from the short-story pipeline to
# the multi-phase, canon-tracked novel pipeline.
NOVEL_WORD_THRESHOLD = 2000


# ── Schemas ──────────────────────────────────────────────

class StoryCreate(BaseModel):
    prompt: str
    genre: str | None = None
    style: str | None = None
    max_words: int = 200
    pov: str | None = None


class StoryOut(BaseModel):
    id: str
    user_id: str
    title: str | None
    prompt: str
    full_text: str | None
    genre: str | None
    style: str | None
    pov: str | None
    max_words: int
    word_count: int
    status: str
    created_at: str

    model_config = {"from_attributes": True}


def _serialize_story(s: Story) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "title": s.title,
        "prompt": s.prompt,
        "full_text": s.full_text,
        "text": s.full_text,  # Added for frontend compatibility
        "genre": s.genre,
        "style": s.style,
        "pov": s.pov,
        "max_words": s.max_words,
        "word_count": s.word_count,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


# ── Engine stub  ─────────────────────────────────────────
# Import the real engine if available, otherwise use a demo stub.

try:
    from engine.pipeline import StoryPipeline
    from engine.novel import NovelPipeline
    from engine.backends.cloud import CloudBackend
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False
    logger.warning("engine not found — using demo SSE stub")


def _build_pipeline(tier: str, max_words: int):
    """Pick the right pipeline for this story.

    - Free tier, or paid short stories (<= NOVEL_WORD_THRESHOLD): the existing
      single-pass StoryPipeline (Ollama for free, DeepSeek for paid).
    - Paid tier with max_words > NOVEL_WORD_THRESHOLD: the multi-phase
      NovelPipeline driving DeepSeek.

    Returns ``(pipeline, kind)`` where kind is "novel" or "short".
    """
    if tier != "free" and max_words > NOVEL_WORD_THRESHOLD:
        backend = CloudBackend(provider="deepseek", max_tokens=6000)
        pipeline = NovelPipeline(backend, max_chapters=20, target_words=max_words)
        return pipeline, "novel"

    pipeline = StoryPipeline(tier=tier, cloud_provider="deepseek")
    return pipeline, "short"


async def _generate_story_events(
    story_id: str,
    prompt: str,
    genre: str | None,
    style: str | None,
    max_words: int,
    pov: str | None,
    tier: str,
    db_session_factory,
) -> AsyncIterator[dict]:
    """Generate story events via the real engine (short or novel) or a demo stub.

    Both pipelines yield SSE-friendly event dicts; the only divergence is the
    novel pipeline's richer event types (bible/critique/revision/chapter_*),
    which pass straight through to the client. The finished story is persisted
    from the authoritative ``complete`` event.
    """
    if not ENGINE_AVAILABLE:
        async for event in _demo_events(story_id, prompt, genre, style, pov, db_session_factory):
            yield event
        return

    pipeline, kind = _build_pipeline(tier, max_words)

    # Coalesce optional fields to sensible defaults (the pipelines lower-case them).
    g = genre or "literary"
    s = style or "descriptive"
    p = pov or "third_person_limited"

    if kind == "novel":
        stream = pipeline.generate(prompt, g, s, p)
    else:
        stream = pipeline.generate(prompt, g, s, max_words, p)

    full_text_parts: list[str] = []

    try:
        async for event in stream:
            etype = event.get("type", "unknown")
            if etype == "chunk":
                full_text_parts.append(event.get("text", ""))
            elif etype == "complete":
                final_text = event.get("full_text") or "".join(full_text_parts)
                final_word_count = event.get("word_count") or len(final_text.split())
                _save_story(
                    db_session_factory, story_id,
                    full_text=final_text, word_count=final_word_count,
                    title=event.get("title"), status="complete",
                )
            elif etype == "error":
                _save_story(db_session_factory, story_id, status="failed")

            yield event
    finally:
        close = getattr(pipeline, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001 — cleanup must not mask the real result
                logger.debug("pipeline close failed", exc_info=True)


def _save_story(
    db_session_factory,
    story_id: str,
    *,
    full_text: str | None = None,
    word_count: int | None = None,
    title: str | None = None,
    status: str | None = None,
) -> None:
    """Persist generation results for a story (best-effort)."""
    db = db_session_factory()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            return
        if full_text is not None:
            story.full_text = full_text
        if word_count is not None:
            story.word_count = word_count
        if title:
            story.title = title
        elif full_text is not None and not story.title:
            story.title = _auto_title(full_text)
        if status is not None:
            story.status = status
        db.commit()
    finally:
        db.close()


async def _demo_events(
    story_id: str,
    prompt: str,
    genre: str | None,
    style: str | None,
    pov: str | None,
    db_session_factory,
) -> AsyncIterator[dict]:
    """Demo stub — simulates generation when the engine isn't importable."""
    demo_text = (
        f"Once upon a time, a writer set out to create something unorthodox. "
        f"The prompt was: '{prompt}'. "
        f"This story explores {genre or 'the unknown'} with a {style or 'unique'} style, "
        f"from a {pov or 'third-person'} point of view. "
        f"Each word builds a world, each sentence deepens the mystery. "
        f"Characters emerge, conflicts arise, and resolutions unfold in unexpected ways. "
        f"The journey continues until the very last word completes the tale. "
        f"— THE END —"
    )
    words = demo_text.split()
    chunk_size = max(1, len(words) // 10)
    chunks = [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]

    for i, chunk in enumerate(chunks):
        await asyncio.sleep(0.3)
        yield {"type": "chunk", "text": chunk + " "}
        if i % 3 == 0:
            yield {
                "type": "progress",
                "stage": f"writing section {i + 1}/{len(chunks)}",
                "message": f"Generating... ({min(100, int((i + 1) / len(chunks) * 100))}%)",
            }

    wc = len(demo_text.split())
    yield {"type": "complete", "text": "", "word_count": wc, "full_text": demo_text}
    _save_story(
        db_session_factory, story_id,
        full_text=demo_text, word_count=wc, status="complete",
    )


def _auto_title(text: str, max_len: int = 60) -> str:
    """Derive a simple title from the first sentence or first few words."""
    if not text:
        return "Untitled"
    # Skip a leading markdown title line if present (novel output starts with "# Title").
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:max_len] or "Untitled"
        if stripped:
            break
    first_sentence = text.split(".")[0].strip()
    if len(first_sentence) > max_len:
        first_sentence = first_sentence[:max_len].rsplit(" ", 1)[0] + "..."
    return first_sentence or "Untitled"


# ── Endpoints ────────────────────────────────────────────

@router.post("", response_model=StoryOut, status_code=status.HTTP_201_CREATED)
def create_story(
    body: StoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Enforce tier limits
    check_story_creation(
        prompt_length=len(body.prompt),
        max_words=body.max_words,
        current_user=current_user,
        db=db,
    )

    story = Story(
        user_id=current_user.id,
        prompt=body.prompt,
        genre=body.genre,
        style=body.style,
        pov=body.pov,
        max_words=body.max_words,
        word_count=0,
        status="generating",
    )
    db.add(story)
    db.commit()
    db.refresh(story)

    return _serialize_story(story)


@router.get("", response_model=list[StoryOut])
def list_stories(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Story)
        .filter(Story.user_id == current_user.id)
        .order_by(Story.created_at.desc())
    )

    # Free tier: only show last 3
    if current_user.tier == "free":
        query = query.limit(FREE_MAX_SAVED_STORIES)

    return [_serialize_story(s) for s in query.all()]


@router.get("/{story_id}", response_model=StoryOut)
def get_story(
    story_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.query(Story).filter(Story.id == story_id, Story.user_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return _serialize_story(story)


@router.get("/{story_id}/stream")
async def stream_story(
    story_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE endpoint — streams story generation events."""
    story = db.query(Story).filter(Story.id == story_id, Story.user_id == current_user.id).first()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # We need a session factory for the background task to write to DB
    from database import SessionLocal

    # Snapshot the fields we need before the request session is torn down.
    s_id = story.id
    s_prompt = story.prompt
    s_genre = story.genre
    s_style = story.style
    s_pov = story.pov
    s_max_words = story.max_words or 200
    tier = current_user.tier

    async def event_generator():
        try:
            async for event in _generate_story_events(
                story_id=s_id,
                prompt=s_prompt,
                genre=s_genre,
                style=s_style,
                max_words=s_max_words,
                pov=s_pov,
                tier=tier,
                db_session_factory=SessionLocal,
            ):
                # If client disconnects, stop
                if await request.is_disconnected():
                    break
                yield {"data": json.dumps(event)}
        except Exception as e:
            logger.exception("Story generation failed")
            yield {"data": json.dumps({"type": "error", "message": str(e)})}

    return EventSourceResponse(event_generator())
