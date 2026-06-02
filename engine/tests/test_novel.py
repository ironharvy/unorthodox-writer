"""
NovelPipeline tests.

Unit tests for the bible dataclasses, JSON parsing, chapter-derivation logic
and the revision word-count guard run without a network. One live Ollama run
(tiny 3-chapter novel) is executed once per module and asserted on by the
phase-specific tests.
"""

import asyncio

import pytest

from engine.novel import NovelPipeline, StoryBible, ChapterBeat, _parse_json, _count_words
from engine.backends.ollama import OllamaBackend
from .conftest import OLLAMA_URL, SMALL_MODEL, OLLAMA_AVAILABLE


# ── JSON parsing (no network) ───────────────────────────────


def test_parse_json_clean():
    assert _parse_json('{"a": 1}') == {"a": 1}


def test_parse_json_fenced():
    assert _parse_json('```json\n{"a": 1, "b": [2,3]}\n```') == {"a": 1, "b": [2, 3]}


def test_parse_json_embedded_in_prose():
    assert _parse_json('Sure! Here it is: {"title": "X"} — enjoy.') == {"title": "X"}


def test_parse_json_failure():
    assert _parse_json("not json at all") is None
    assert _parse_json("") is None


# ── Bible dataclasses (no network) ──────────────────────────


def _sample_bible_dict() -> dict:
    return {
        "title": "The Tin Coast",
        "logline": "A wrecker learns the sea keeps its promises.",
        "pov": "first person, past tense",
        "tone": "salt-bleached and elegiac",
        "themes": ["grief", "tides"],
        "protagonist": {"name": "Mara", "age": 34, "flaw": "won't grieve", "want": "the wreck", "voice": "clipped"},
        "characters": [{"name": "Ide", "role": "brother", "voice": "warm", "want": "to leave"}],
        "setting": {"world_name": "Tinmouth", "locations": ["the cove", "the light"],
                    "atmosphere": "fog", "world_rules": ["the tide always returns what it takes"]},
        "motifs": ["rusted bell"],
        "chapters": [
            {"number": 1, "title": "Low Water", "synopsis": "Mara finds the wreck.",
             "emotional_beat": "dread", "must_include": ["the bell"], "ends_on": "a hand in the surf", "word_target": 200},
            {"number": 2, "title": "Slack", "synopsis": "Ide arrives.",
             "emotional_beat": "tension", "must_include": ["argument"], "ends_on": "a decision", "word_target": 200},
        ],
    }


def test_storybible_from_dict():
    bible = StoryBible.from_dict(_sample_bible_dict(), words_per_chapter=200)
    assert bible.title == "The Tin Coast"
    assert len(bible.chapters) == 2
    assert bible.chapters[0].title == "Low Water"
    assert bible.chapters[0].number == 1
    assert bible.protagonist["name"] == "Mara"


def test_storybible_digest_contains_world_rules():
    bible = StoryBible.from_dict(_sample_bible_dict(), words_per_chapter=200)
    digest = bible.digest()
    assert "the tide always returns what it takes" in digest
    assert "Mara" in digest
    assert "Low Water" in digest


def test_storybible_roundtrip_json():
    bible = StoryBible.from_dict(_sample_bible_dict(), words_per_chapter=200)
    data = bible.to_dict()
    again = StoryBible.from_dict(data, words_per_chapter=200)
    assert again.title == bible.title
    assert len(again.chapters) == len(bible.chapters)


def test_chapterbeat_fallbacks():
    beat = ChapterBeat.from_dict({"title": "X"}, fallback_number=3, fallback_words=500)
    assert beat.number == 3
    assert beat.word_target == 500
    # must_include accepts a string and splits it
    beat2 = ChapterBeat.from_dict(
        {"title": "Y", "key_points": "a; b\nc"}, fallback_number=1, fallback_words=100,
    )
    assert beat2.must_include == ["a", "b", "c"]


def test_chapter_renumbering():
    d = {"chapters": [{"number": 9, "title": "A"}, {"number": 4, "title": "B"}]}
    bible = StoryBible.from_dict(d, words_per_chapter=300)
    assert [c.number for c in bible.chapters] == [1, 2]


# ── Chapter-count derivation (no network) ───────────────────


def test_default_chapter_derivation():
    p = NovelPipeline(backend=None, max_chapters=20, target_words=20000)
    assert p.target_words == 20000
    assert 2 <= p.n_chapters <= 20
    assert p.words_per_chapter >= 400


def test_small_target_is_floored_by_default():
    p = NovelPipeline(backend=None, target_words=500)
    assert p.target_words == 2000  # floored
    assert p.n_chapters >= 2


def test_explicit_n_chapters_opts_out_of_floors():
    p = NovelPipeline(backend=None, max_chapters=3, target_words=500,
                      n_chapters=3, min_words_per_chapter=120)
    assert p.target_words == 500
    assert p.n_chapters == 3
    assert p.words_per_chapter == max(120, 500 // 3)


def test_n_chapters_clamped_to_max():
    p = NovelPipeline(backend=None, max_chapters=4, target_words=900, n_chapters=10)
    assert p.n_chapters == 4


# ── Revision word-count guard (no network) ──────────────────


def test_revision_guard_rejects_truncated():
    original = " ".join(["word"] * 200)
    too_short = " ".join(["word"] * 50)   # 25% of original
    assert NovelPipeline._revision_acceptable(original, too_short) is False


def test_revision_guard_accepts_full_rewrite():
    original = " ".join(["word"] * 200)
    full = " ".join(["word"] * 190)
    assert NovelPipeline._revision_acceptable(original, full) is True


def test_revision_guard_rejects_blank():
    assert NovelPipeline._revision_acceptable("a b c d", "") is False


# ── Live Ollama smoke (one run per module) ──────────────────


@pytest.fixture(scope="module")
def novel_run():
    if not OLLAMA_AVAILABLE:
        pytest.skip("Ollama not reachable")

    async def _once():
        backend = OllamaBackend(base_url=OLLAMA_URL, model=SMALL_MODEL)
        pipeline = NovelPipeline(
            backend, max_chapters=3, target_words=500,
            n_chapters=3, min_words_per_chapter=120,
        )
        events = []
        async for ev in pipeline.generate(
            prompt="A clockmaker who can hear time running out in the gears she repairs.",
            genre="literary", style="atmospheric", pov="first_person",
        ):
            events.append(ev)
        await pipeline.close()
        return events

    async def _run():
        # Small models are occasionally non-deterministic; retry once on a hard
        # error so a rare bad bible doesn't flake the whole module.
        for _ in range(2):
            events = await _once()
            if not any(e.get("type") == "error" for e in events):
                return events
        return events

    return asyncio.run(_run())


def _types(events, t):
    return [e for e in events if e.get("type") == t]


def test_novel_no_error(novel_run):
    errors = _types(novel_run, "error")
    assert not errors, f"novel errored: {errors[0]['message'] if errors else ''}"


def test_bible_generation(novel_run):
    bibles = _types(novel_run, "bible")
    assert bibles, "no bible event"
    bible = bibles[0]["bible"]
    assert bible["title"]
    assert bible["chapters"], "bible has no chapters"
    assert len(bible["chapters"]) == 3


def test_chapter_drafting(novel_run):
    completes = _types(novel_run, "chapter_complete")
    assert len(completes) == 3
    for c in completes:
        assert c["word_count"] > 0
        assert c["title"]


def test_critique_generation(novel_run):
    crit = _types(novel_run, "critique")
    assert crit, "no critique event"
    assert isinstance(crit[0]["issues"], list)


def test_revision_phase_ran(novel_run):
    revising = [e for e in novel_run
                if e.get("type") == "progress" and e.get("phase") == "revising"]
    assert revising, "revision phase did not run"


def test_full_novel_smoke(novel_run):
    completes = _types(novel_run, "complete")
    assert completes, "no complete event"
    c = completes[0]
    assert c["full_text"].strip()
    assert c["chapter_count"] == 3
    assert c["word_count"] > 200
    assert _count_words(c["full_text"]) > 200
