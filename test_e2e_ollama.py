#!/usr/bin/env python3
"""
End-to-end verification of both pipelines against Ollama (engine-direct).

Runs entirely through the engine — no FastAPI server, no DB:

  1. Short story  : StoryPipeline, ~400 words      → expects a `complete` event.
  2. Novel mode   : NovelPipeline, ~800 words / 3 ch → expects bible,
                    chapter_complete (x3), critique, revision phase, complete.

Exit code 0 iff every assertion holds. Uses the fast 8B model by default.

Usage::

    python test_e2e_ollama.py
    OLLAMA_MODEL=qwen3.6:27b python test_e2e_ollama.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.backends.ollama import OllamaBackend
from engine.pipeline import StoryPipeline
from engine.novel import NovelPipeline

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:latest")
URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")


def _collect_types(events):
    by_type = {}
    for ev in events:
        by_type.setdefault(ev.get("type"), []).append(ev)
    return by_type


async def run_short() -> tuple[bool, str]:
    pipe = StoryPipeline(tier="free", ollama_url=URL, ollama_model=MODEL)
    events = []
    async for ev in pipe.generate(
        prompt="A radio operator on a polar base starts receiving her own voice from tomorrow.",
        genre="thriller", style="cinematic", max_words=400, pov="third_person_limited",
    ):
        events.append(ev)
    await pipe.close()

    bt = _collect_types(events)
    if bt.get("error"):
        return False, f"short story errored: {bt['error'][0]['message']}"
    completes = bt.get("complete", [])
    if not completes:
        return False, "short story produced no complete event"
    c = completes[0]
    if not c.get("full_text", "").strip():
        return False, "short story complete event had no text"
    if not bt.get("chunk"):
        return False, "short story streamed no chunks"
    return True, f'"{c.get("title")}" — {c.get("word_count")} words, {c.get("section_count")} sections'


async def run_novel() -> tuple[bool, str]:
    backend = OllamaBackend(base_url=URL, model=MODEL)
    pipe = NovelPipeline(backend, max_chapters=3, target_words=800,
                         n_chapters=3, min_words_per_chapter=150)
    events = []
    async for ev in pipe.generate(
        prompt="A cartographer maps a city that quietly rearranges itself every night.",
        genre="literary", style="atmospheric", pov="third_person_limited",
    ):
        events.append(ev)
    await pipe.close()

    bt = _collect_types(events)
    if bt.get("error"):
        return False, f"novel errored: {bt['error'][0]['message']}"

    problems = []
    if not bt.get("bible"):
        problems.append("no bible event")
    n_chapters = len(bt.get("chapter_complete", []))
    if n_chapters != 3:
        problems.append(f"expected 3 chapters, got {n_chapters}")
    if not bt.get("critique"):
        problems.append("no critique event")
    revising = [e for e in events if e.get("type") == "progress" and e.get("phase") == "revising"]
    if not revising:
        problems.append("revision phase did not run")
    if not bt.get("complete"):
        problems.append("no complete event")

    if problems:
        return False, "; ".join(problems)

    c = bt["complete"][0]
    crit = bt["critique"][0]["issues"]
    revs = bt.get("revision", [])
    return True, (
        f'"{c.get("title")}" — {c.get("word_count")} words, {n_chapters} chapters, '
        f"{len(crit)} critique issue(s), {len(revs)} chapter(s) revised"
    )


async def main() -> int:
    print(f"\n=== E2E (engine-direct) × Ollama (model={MODEL}) ===\n")

    backend = OllamaBackend(base_url=URL, model=MODEL)
    if not await backend.health_check():
        print(f"✗ Ollama not reachable at {URL}")
        await backend.close()
        return 1
    await backend.close()

    all_ok = True
    print("1) Short story (StoryPipeline, ~400 words)...")
    ok, detail = await run_short()
    print(("   ✓ " if ok else "   ✗ ") + detail)
    all_ok = all_ok and ok

    print("\n2) Novel mode (NovelPipeline, ~800 words / 3 chapters)...")
    ok, detail = await run_novel()
    print(("   ✓ " if ok else "   ✗ ") + detail)
    all_ok = all_ok and ok

    print("\n" + ("✓ E2E PASSED — both pipelines operational with Ollama"
                  if all_ok else "✗ E2E FAILED") + "\n")
    return 0 if all_ok else 1


# pytest entry point (skips cleanly when Ollama is down)
def test_e2e_ollama():
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
