#!/usr/bin/env python3
"""
Standalone proof that the NovelPipeline works end-to-end against Ollama.

Runs a deliberately tiny novel (3 short chapters, ~500 words) with the fast
``qwen3:latest`` model and asserts every phase fires:

    bible → drafting (chapter_complete x3) → critique → revision → complete

Output is written to ``test_output/ollama_novel_smoke.md`` together with the
story bible and a metrics report.

Usage::

    python engine/test_novel_ollama.py            # qwen3:latest (fast)
    OLLAMA_MODEL=qwen3.6:27b python engine/test_novel_ollama.py
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backends.ollama import OllamaBackend
from engine.novel import NovelPipeline
from engine.metrics import StoryMetrics, format_report

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:latest")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_output")


async def run() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"\n=== NovelPipeline × Ollama smoke test (model={MODEL}) ===\n")

    backend = OllamaBackend(model=MODEL)
    if not await backend.health_check():
        print("✗ Ollama not reachable — cannot run smoke test.")
        await backend.close()
        return 1
    print(f"✓ Ollama reachable, models: {await backend.list_models()}")

    pipeline = NovelPipeline(
        backend,
        max_chapters=3,
        target_words=500,
        n_chapters=3,
        min_words_per_chapter=120,
    )
    print(f"✓ Pipeline: {pipeline.n_chapters} chapters × ~{pipeline.words_per_chapter} words\n")

    seen_phases: set[str] = set()
    seen_event_types: set[str] = set()
    chapters_completed: list[int] = []
    bible_data = None
    critique_issues = None
    revised = None
    complete = None

    t0 = time.time()
    async for ev in pipeline.generate(
        prompt="A night-shift lighthouse keeper realizes the light is answering something out in the dark.",
        genre="literary",
        style="atmospheric",
        pov="first_person",
    ):
        et = ev.get("type")
        seen_event_types.add(et)
        if et == "progress":
            phase = ev.get("phase", "?")
            seen_phases.add(phase)
            print(f"  [{phase}] {ev.get('message','')}")
        elif et == "bible":
            bible_data = ev["bible"]
        elif et == "chapter_complete":
            chapters_completed.append(ev["chapter"])
            print(f"    ✓ chapter {ev['chapter']} complete — {ev['word_count']} words")
        elif et == "critique":
            critique_issues = ev["issues"]
            print(f"    ✓ critique — {len(critique_issues)} issue(s)")
        elif et == "revision":
            revised = ev
            print(f"    ✓ revised chapter {ev['chapter']} — {ev['word_count']} words")
        elif et == "complete":
            complete = ev
        elif et == "error":
            print(f"  ✗ ERROR: {ev['message']}")
            await pipeline.close()
            return 1
    elapsed = time.time() - t0

    await pipeline.close()

    # ── assertions ──────────────────────────────────────────
    print(f"\n--- verification (took {elapsed:.0f}s) ---")
    ok = True

    def check(cond: bool, msg: str):
        nonlocal ok
        print(("  ✓ " if cond else "  ✗ ") + msg)
        ok = ok and cond

    check(bible_data is not None and bool(bible_data.get("chapters")), "bible generated with chapters")
    check("bible" in seen_phases, "bible phase fired")
    check("drafting" in seen_phases, "drafting phase fired")
    check(len(chapters_completed) == 3, f"all 3 chapters drafted (got {len(chapters_completed)})")
    check("critique" in seen_phases, "critique phase fired")
    check(critique_issues is not None, "critique produced an issues list")
    check("revising" in seen_phases, "revision phase fired")
    check(complete is not None, "complete event fired")
    if complete:
        wc = complete.get("word_count", 0)
        check(wc > 200, f"final word count reasonable ({wc} words)")

    if complete:
        out_md = os.path.join(OUT_DIR, "ollama_novel_smoke.md")
        with open(out_md, "w", encoding="utf-8") as fh:
            fh.write(complete["full_text"])
        with open(os.path.join(OUT_DIR, "ollama_novel_smoke_bible.json"), "w", encoding="utf-8") as fh:
            json.dump(bible_data, fh, indent=2, ensure_ascii=False)
        print(f"\n  saved → {out_md}")

        metrics = StoryMetrics().compute(
            complete["full_text"], bible=bible_data, critique=critique_issues,
        )
        print("\n" + format_report(complete["full_text"], metrics, label="ollama novel smoke"))

    print("\n" + ("✓ SMOKE TEST PASSED" if ok else "✗ SMOKE TEST FAILED") + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
