#!/usr/bin/env python3
"""
Full integration test: both pipelines on Ollama, scored by the metrics module.

  1. Short story  : StoryPipeline,  ~300 words
  2. Novel (Ollama): NovelPipeline, ~500 words / 3 chapters
  3. Metrics on both outputs
  4. A one-glance summary report.

Usage::

    python test_integration.py
    OLLAMA_MODEL=qwen3.6:27b python test_integration.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.backends.ollama import OllamaBackend
from engine.pipeline import StoryPipeline
from engine.novel import NovelPipeline
from engine.metrics import StoryMetrics

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:latest")
URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")


async def _run_short() -> dict:
    pipe = StoryPipeline(tier="free", ollama_url=URL, ollama_model=MODEL)
    complete = None
    async for ev in pipe.generate(
        prompt="A lighthouse keeper trades one memory a night to keep the lamp lit.",
        genre="literary", style="atmospheric", max_words=300, pov="first_person",
    ):
        if ev.get("type") == "complete":
            complete = ev
        elif ev.get("type") == "error":
            await pipe.close()
            raise RuntimeError(ev["message"])
    await pipe.close()
    if not complete:
        raise RuntimeError("short pipeline produced no complete event")
    return complete


async def _run_novel() -> dict:
    backend = OllamaBackend(base_url=URL, model=MODEL)
    pipe = NovelPipeline(backend, max_chapters=3, target_words=500,
                         n_chapters=3, min_words_per_chapter=120)
    complete = None
    bible = None
    critique = None
    chapter_counts = []
    async for ev in pipe.generate(
        prompt="Two sisters inherit a house where the rooms remember who hurt in them.",
        genre="literary", style="atmospheric", pov="third_person_limited",
    ):
        t = ev.get("type")
        if t == "bible":
            bible = ev["bible"]
        elif t == "chapter_complete":
            chapter_counts.append(ev["word_count"])
        elif t == "critique":
            critique = ev["issues"]
        elif t == "complete":
            complete = ev
        elif t == "error":
            await pipe.close()
            raise RuntimeError(ev["message"])
    await pipe.close()
    if not complete:
        raise RuntimeError("novel pipeline produced no complete event")
    complete["_bible"] = bible
    complete["_critique"] = critique
    complete["_chapter_counts"] = chapter_counts
    return complete


async def main() -> int:
    print(f"\n=== Integration test × Ollama (model={MODEL}) ===\n")

    backend = OllamaBackend(base_url=URL, model=MODEL)
    if not await backend.health_check():
        print(f"✗ Ollama not reachable at {URL}")
        await backend.close()
        return 1
    await backend.close()

    sm = StoryMetrics()

    print("Generating short story (StoryPipeline, ~300 words)...")
    short = await _run_short()
    short_m = sm.compute(short["full_text"])

    print("Generating novel (NovelPipeline, ~500 words / 3 chapters)...")
    novel = await _run_novel()
    novel_m = sm.compute(
        novel["full_text"], bible=novel.get("_bible"), critique=novel.get("_critique"),
        chapter_word_counts=novel.get("_chapter_counts"),
    )

    print("\n" + "═" * 64)
    print(" INTEGRATION SUMMARY")
    print("═" * 64)
    print(
        f"Short Story: {short_m['word_count']} words, "
        f"artifact score: {short_m['ai_artifact_score']:.1f}/10, "
        f"readability: {short_m['readability']:.1f}, "
        f"overall: {short_m['overall']:.1f}/10"
    )
    pacing = novel_m["pacing_balance"]
    pacing_str = f"{pacing:.2f}" if pacing is not None else "n/a"
    print(
        f"Novel (Ollama): {novel['chapter_count']} chapters, {novel_m['word_count']} words, "
        f"artifact score: {novel_m['ai_artifact_score']:.1f}/10, "
        f"pacing: {pacing_str}, "
        f"overall: {novel_m['overall']:.1f}/10"
    )
    print("═" * 64)

    ok = (
        short_m["word_count"] > 50
        and novel["chapter_count"] == 3
        and novel_m["word_count"] > 200
    )
    print(("✓ All pipelines operational with Ollama" if ok
           else "✗ Integration check failed") + "\n")
    return 0 if ok else 1


def test_integration():
    import httpx
    import pytest
    try:
        if httpx.get(f"{URL}/api/tags", timeout=3.0).status_code != 200:
            pytest.skip("Ollama not reachable")
    except Exception:
        pytest.skip("Ollama not reachable")
    assert asyncio.run(main()) == 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
