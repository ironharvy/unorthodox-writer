"""
StoryPipeline tests.

Keeps the original template-rendering and outline-parser unit tests, and adds
live Ollama smoke tests for the full single-pass pipeline.
"""

import pytest

from engine import StoryPipeline
from engine.pipeline import _parse_outline, _estimate_section_words
from engine.templates import (
    get_stage_template,
    get_system_prompt,
    GENRE_GUIDANCE,
    STYLE_GUIDANCE,
    POV_GUIDANCE,
    PROSE_RULES,
    EXPAND_TEMPLATE,
    OUTLINE_TEMPLATE,
    DRAFT_SECTION_TEMPLATE,
    POLISH_TEMPLATE,
)
from .conftest import OLLAMA_URL, SMALL_MODEL


# ── Templates (no network) ──────────────────────────────────


def test_expand_template_renders():
    out = EXPAND_TEMPLATE.format(
        prompt="A cat discovers it can teleport",
        genre="fantasy", style="descriptive", pov="third_person_limited",
    )
    assert "A cat discovers it can teleport" in out
    assert "fantasy" in out.lower()


def test_draft_and_polish_templates_have_prose_rules():
    draft = DRAFT_SECTION_TEMPLATE.format(
        title="T", genre="noir", style="cinematic", pov="first_person",
        full_outline="o", previous_text="p", section_title="The Encounter",
        section_summary="s", section_emotion="e", key_points="k", section_words=200,
    )
    assert "The Encounter" in draft
    assert "PROSE GUARDRAILS" in draft
    assert 'however' in PROSE_RULES  # the rules name the crutch words

    polish = POLISH_TEMPLATE.format(
        draft="A story draft", genre="horror", style="minimalist",
        pov="first_person", max_words=800,
    )
    assert "A story draft" in polish
    assert "PROSE GUARDRAILS" in polish


def test_all_templates_render_for_both_compact_modes():
    kwargs = dict(
        prompt="x", genre="noir", style="descriptive", pov="first_person",
        premise="p", max_words=500, min_sections=2, title="T", full_outline="fo",
        previous_text="pt", section_title="st", section_summary="ss",
        section_emotion="se", key_points="kp", section_words=200, draft="d",
    )
    for compact in (False, True):
        for stage in ("expand", "outline", "draft", "polish"):
            rendered = get_stage_template(stage, compact).format(**kwargs)
            assert rendered and "{" not in rendered.split("PROSE")[0][-3:]


def test_system_prompts_include_guidance():
    for stage in ("expand", "outline", "draft", "polish"):
        sp = get_system_prompt(stage, "fantasy", "poetic", "first_person")
        assert len(sp) > 20


def test_guidance_dictionaries():
    assert len(GENRE_GUIDANCE) == 10
    assert len(STYLE_GUIDANCE) == 6
    assert len(POV_GUIDANCE) == 4


# ── Outline parser (no network) ─────────────────────────────

_SAMPLE_OUTLINE = """SECTIONS: 4

SECTION 1: The Arrival
SUMMARY: A stranger walks into town at dusk. The townsfolk eye him with suspicion. He checks into the only inn.
EMOTION: Unease and curiosity
KEY POINTS: - Stranger appears - Town described - Inn check-in

SECTION 2: The Investigation
SUMMARY: The stranger begins asking questions about the old mine. He discovers it's been closed for 50 years. The mayor warns him off.
EMOTION: Tension building, defiance
KEY POINTS: - Mine history revealed - Mayor confrontation

SECTION 3: The Descent
SUMMARY: Against all warnings, the stranger enters the mine. Something stirs in the darkness.
EMOTION: Dread, discovery, terror
KEY POINTS: - Mine exploration - Creature revealed

SECTION 4: The Reckoning
SUMMARY: The stranger emerges changed. He confronts the mayor with the truth.
EMOTION: Catharsis, resolution
KEY POINTS: - Confrontation scene - Truth revealed

TONE: Atmospheric dread with moments of human warmth."""


def test_outline_parser():
    sections = _parse_outline(_SAMPLE_OUTLINE)
    assert len(sections) == 4
    assert sections[0]["title"] == "The Arrival"
    assert sections[2]["emotion"] == "Dread, discovery, terror"
    assert "Creature revealed" in sections[2]["key_points"]


def test_estimate_section_words():
    assert _estimate_section_words(900, 3) > 0
    assert _estimate_section_words(900, 3) >= 80  # floor


# ── Instantiation (no network) ──────────────────────────────


def test_pipeline_instantiation():
    free = StoryPipeline(tier="free")
    assert free.tier == "free"
    paid = StoryPipeline(tier="paid", cloud_provider="deepseek")
    assert paid.tier == "paid"


# ── Live Ollama smoke ───────────────────────────────────────


@pytest.fixture(scope="module")
def short_story():
    """Run the single-pass pipeline once (200 words) and collect all events."""
    import asyncio
    from .conftest import OLLAMA_AVAILABLE
    if not OLLAMA_AVAILABLE:
        pytest.skip("Ollama not reachable")

    async def _run():
        pipeline = StoryPipeline(tier="free", ollama_url=OLLAMA_URL, ollama_model=SMALL_MODEL)
        events = []
        async for ev in pipeline.generate(
            prompt="A diver finds a city that should not exist beneath the ice.",
            genre="literary", style="descriptive", max_words=200, pov="third_person_limited",
        ):
            events.append(ev)
        await pipeline.close()
        return events

    return asyncio.run(_run())


def _types(events, t):
    return [e for e in events if e.get("type") == t]


def test_pipeline_ollama_no_error(short_story):
    errors = _types(short_story, "error")
    assert not errors, f"pipeline errored: {errors[0]['message'] if errors else ''}"


def test_pipeline_ollama_smoke(short_story):
    completes = _types(short_story, "complete")
    assert completes, "no complete event"
    c = completes[0]
    assert c["full_text"].strip()
    assert c["word_count"] > 50
    assert c["title"]
    assert c["section_count"] >= 1


def test_pipeline_ollama_streaming(short_story):
    # progress events for each stage, chunk events for prose, one complete.
    assert _types(short_story, "progress"), "no progress events"
    assert _types(short_story, "chunk"), "no streamed chunks"
    stages = {e.get("stage") for e in _types(short_story, "progress")}
    assert {"expand", "outline", "draft", "polish"} & stages
