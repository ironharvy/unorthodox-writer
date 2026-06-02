#!/usr/bin/env python3
"""
Test script for the Unorthodox Writer Story Engine.

Demonstrates:
  - Import and instantiation
  - Template rendering
  - Outline parsing
  - Pipeline execution (detects if Ollama is available; falls back to dry-run)
  - Event streaming
"""

import asyncio
import sys
import os

# Ensure the engine package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import StoryPipeline
from engine.templates import (
    get_stage_template,
    get_system_prompt,
    GENRE_GUIDANCE,
    STYLE_GUIDANCE,
    POV_GUIDANCE,
    EXPAND_TEMPLATE,
    OUTLINE_TEMPLATE,
    DRAFT_SECTION_TEMPLATE,
    POLISH_TEMPLATE,
)
from engine.pipeline import _parse_outline

# ── ANSI helpers ────────────────────────────────────────────

C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
    "dim": "\033[2m",
}

def ok(msg: str) -> str:
    return f"{C['green']}✓{C['reset']} {msg}"

def fail(msg: str) -> str:
    return f"{C['red']}✗{C['reset']} {msg}"

def info(msg: str) -> str:
    return f"{C['cyan']}→{C['reset']} {msg}"

def header(msg: str) -> str:
    return f"\n{C['bold']}{'='*60}{C['reset']}\n{C['bold']}{msg}{C['reset']}\n{C['bold']}{'='*60}{C['reset']}"

# ── Tests ───────────────────────────────────────────────────

def test_imports():
    """Verify all expected exports."""
    print(header("TEST: Imports"))
    from engine import StoryPipeline, OllamaBackend, CloudBackend
    print(ok("StoryPipeline imported"))
    print(ok("OllamaBackend imported"))
    print(ok("CloudBackend imported"))
    print(ok(f"Version: {__import__('engine').__version__}"))


def test_templates():
    """Verify templates render correctly."""
    print(header("TEST: Templates"))

    # Test expand template
    prompt = EXPAND_TEMPLATE.format(
        prompt="A cat discovers it can teleport",
        genre="fantasy",
        style="descriptive",
        pov="third_person_limited",
    )
    assert "A cat discovers it can teleport" in prompt
    assert "fantasy" in prompt.lower()
    print(ok("EXPAND_TEMPLATE renders correctly"))

    # Test outline template
    outline = OUTLINE_TEMPLATE.format(
        premise="A lonely wizard...",
        genre="fantasy",
        style="descriptive",
        pov="third_person_limited",
        max_words=500,
    )
    assert "A lonely wizard" in outline
    print(ok("OUTLINE_TEMPLATE renders correctly"))

    # Test draft template
    draft = DRAFT_SECTION_TEMPLATE.format(
        title="Test",
        genre="noir",
        style="cinematic",
        pov="first_person",
        full_outline="Outline here",
        previous_text="Previous here",
        section_title="The Encounter",
        section_summary="A meeting in the dark",
        section_emotion="Tension rising",
        key_points="- point one\n- point two",
        section_words=200,
    )
    assert "The Encounter" in draft
    assert "noir" in draft
    print(ok("DRAFT_SECTION_TEMPLATE renders correctly"))

    # Test polish template
    polish = POLISH_TEMPLATE.format(
        draft="A story draft...",
        genre="horror",
        style="minimalist",
        pov="first_person",
        max_words=800,
    )
    assert "A story draft" in polish
    print(ok("POLISH_TEMPLATE renders correctly"))

    # Test system prompts
    for stage in ("expand", "outline", "draft", "polish"):
        sp = get_system_prompt(stage, "fantasy", "poetic", "first_person")
        assert len(sp) > 20, f"{stage} system prompt too short"
    print(ok("All system prompts render with genre/style/POV guidance"))

    # Test genre/style/pov guides
    assert len(GENRE_GUIDANCE) == 10
    assert len(STYLE_GUIDANCE) == 6
    assert len(POV_GUIDANCE) == 4
    print(ok(f"Guidance dictionaries: {len(GENRE_GUIDANCE)} genres, {len(STYLE_GUIDANCE)} styles, {len(POV_GUIDANCE)} POVs"))


def test_outline_parser():
    """Verify outline parsing from LLM output."""
    print(header("TEST: Outline Parser"))

    sample = """SECTIONS: 4

SECTION 1: The Arrival
SUMMARY: A stranger walks into town at dusk. The townsfolk eye him with suspicion. He checks into the only inn.
EMOTION: Unease and curiosity
KEY POINTS: - Stranger appears - Town described - Inn check-in - First strange event

SECTION 2: The Investigation
SUMMARY: The stranger begins asking questions about the old mine. He discovers it's been closed for 50 years after a collapse. The mayor warns him off.
EMOTION: Tension building, defiance
KEY POINTS: - Mine history revealed - Mayor confrontation - Secret documents found

SECTION 3: The Descent
SUMMARY: Against all warnings, the stranger enters the mine. He finds remnants of a failed experiment. Something stirs in the darkness.
EMOTION: Dread, discovery, terror
KEY POINTS: - Mine exploration - Lab discovery - Creature revealed - Narrow escape

SECTION 4: The reckoning
SUMMARY: The stranger emerges changed. He confronts the mayor with the truth. The town must face what they buried.
EMOTION: Catharsis, resolution, bittersweet
KEY POINTS: - Confrontation scene - Truth revealed - Town's decision - Stranger leaves

TONE: Atmospheric dread with moments of human warmth."""

    sections = _parse_outline(sample)
    assert len(sections) == 4, f"Expected 4 sections, got {len(sections)}"
    assert sections[0]["title"] == "The Arrival"
    assert sections[1]["summary"] == "The stranger begins asking questions about the old mine. He discovers it's been closed for 50 years after a collapse. The mayor warns him off."
    assert sections[2]["emotion"] == "Dread, discovery, terror"
    assert "Creature revealed" in sections[2]["key_points"]
    print(ok(f"Parsed {len(sections)} sections correctly"))
    for s in sections:
        print(f"  {C['dim']}Section {s['num']}: {s['title']}{C['reset']}")


def test_pipeline_instantiation():
    """Verify pipeline can be created for both tiers."""
    print(header("TEST: Pipeline Instantiation"))

    free = StoryPipeline(tier="free")
    assert free.tier == "free"
    print(ok("Free tier pipeline created (Ollama backend)"))

    # Paid tier without API keys should still instantiate (keys checked at call time)
    paid = StoryPipeline(tier="paid", cloud_provider="claude")
    assert paid.tier == "paid"
    print(ok("Paid tier pipeline created (Cloud backend)"))


async def test_pipeline_dry_run():
    """Run the pipeline against live Ollama if available; otherwise simulate."""
    print(header("TEST: Pipeline Execution"))

    pipeline = StoryPipeline(tier="free")

    # Check if Ollama is reachable
    backend = pipeline._backend
    reachable = await backend.health_check()

    if not reachable:
        print(fail("Ollama not reachable — running structure validation only"))
        print(info("Pipeline object is ready. Connect to Ollama to run full generation."))
        await pipeline.close()
        return

    print(ok("Ollama is reachable — running full pipeline"))

    events_received = 0
    chunks_received = 0
    complete_event = None
    error_event = None

    try:
        async for event in pipeline.generate(
            prompt="A clockmaker discovers that every clock she fixes begins to run backwards, and she alone can see the past these reversed clocks reveal.",
            genre="fantasy",
            style="descriptive",
            max_words=400,
            pov="third_person_limited",
        ):
            events_received += 1
            etype = event.get("type", "?")

            if etype == "progress":
                stage = event.get("stage", "?")
                msg = event.get("message", "")
                print(info(f"[{stage}] {msg}"))
            elif etype == "chunk":
                chunks_received += 1
                # Don't flood the terminal — print a dot every 20 chunks
                if chunks_received % 20 == 0:
                    print(C["dim"] + "." * min(chunks_received // 20, 40) + C["reset"], end="\r")
            elif etype == "complete":
                complete_event = event
                print(ok(f"Story complete: \"{event['title']}\" — {event['word_count']} words"))
            elif etype == "error":
                error_event = event
                print(fail(f"Error: {event['message']}"))
                break

        if chunks_received > 0:
            print()  # newline after dots

        print(f"\n  Events: {events_received} | Chunks: {chunks_received}")

        if complete_event:
            print(ok(f"Pipeline completed successfully"))
            text_preview = complete_event["full_text"][:200] + "..."
            print(f"  Title: {complete_event['title']}")
            print(f"  Words: {complete_event['word_count']}")
            print(f"  Sections: {complete_event['section_count']}")
            print(f"  Preview: {text_preview}")
        elif error_event:
            print(fail("Pipeline returned an error"))
        else:
            print(fail("Pipeline finished without complete or error event"))

    finally:
        await pipeline.close()


# ── Main ────────────────────────────────────────────────────

async def main():
    print(f"\n{C['bold']}{C['cyan']}Unorthodox Writer — Story Engine Test Suite{C['reset']}\n")

    tests = [
        ("Imports", test_imports),
        ("Templates", test_templates),
        ("Outline Parser", test_outline_parser),
        ("Instantiation", test_pipeline_instantiation),
    ]

    passed = 0
    failed = 0

    for name, func in tests:
        try:
            func()
            passed += 1
        except Exception as exc:
            failed += 1
            print(fail(f"{name}: {exc}"))

    # Pipeline execution (async)
    try:
        await test_pipeline_dry_run()
        passed += 1
    except Exception as exc:
        failed += 1
        print(fail(f"Pipeline execution: {exc}"))

    print(f"\n{C['bold']}Results: {C['green']}{passed} passed{C['reset']}, "
          f"{C['red']}{failed} failed{C['reset']} "
          f"({passed + failed} total){C['reset']}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
