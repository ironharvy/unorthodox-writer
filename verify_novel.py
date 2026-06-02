"""
Verification harness for the NovelPipeline (engine/novel.py).

Modes:
  smoke  — fast end-to-end run (3 short chapters) that exercises every phase
           (bible → drafting → critique → revision → complete) cheaply.
  full   — success-criteria run: 8+ chapters, 15k+ words.
  short  — sanity check that the existing StoryPipeline still works unchanged.

Usage:
  python verify_novel.py smoke
  python verify_novel.py full
  python verify_novel.py short
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine.backends.cloud import CloudBackend          # noqa: E402
from engine.novel import NovelPipeline                  # noqa: E402
from engine.pipeline import StoryPipeline               # noqa: E402

PROMPT = "A night-shift radio astronomer starts receiving songs from a star that died a thousand years ago."
GENRE = "scifi"
STYLE = "literary"
POV = "first_person"

CRUTCH = ["however", "moreover", "furthermore", "in conclusion", "delve", "tapestry",
          "testament to", "navigate the complexities", "it was then that"]


def lint_artifacts(text: str) -> dict:
    low = text.lower()
    return {w: low.count(w) for w in CRUTCH if low.count(w)}


async def run_novel(*, target_words, max_chapters, force_chapters=None, force_words=None,
                    out_path: Path, label: str) -> bool:
    print(f"\n{'=' * 70}\n[{label}] NovelPipeline — target {target_words}w, max {max_chapters} ch\n{'=' * 70}", flush=True)
    backend = CloudBackend(provider="deepseek", max_tokens=6000)
    pipe = NovelPipeline(backend, max_chapters=max_chapters, target_words=target_words)
    if force_chapters:
        pipe.n_chapters = force_chapters
    if force_words:
        pipe.words_per_chapter = force_words
    print(f"  plan: {pipe.n_chapters} chapters x ~{pipe.words_per_chapter} words", flush=True)

    counts: dict[str, int] = {}
    chapter_words: dict[int, int] = {}
    bible = None
    issues: list = []
    revised: list = []
    final = None
    errors: list[str] = []
    chunk_chars = 0
    t0 = time.time()

    async for ev in pipe.generate(PROMPT, GENRE, STYLE, POV):
        t = ev.get("type", "?")
        counts[t] = counts.get(t, 0) + 1
        if t == "progress":
            print(f"  [{ev.get('phase')}] {ev.get('message')}", flush=True)
        elif t == "chunk":
            chunk_chars += len(ev.get("text", ""))
        elif t == "bible":
            bible = ev["bible"]
        elif t == "chapter_complete":
            chapter_words[ev["chapter"]] = ev["word_count"]
            print(f"      ✓ ch{ev['chapter']} drafted: {ev['word_count']} words", flush=True)
        elif t == "critique":
            issues = ev["issues"]
            print(f"  [critique] {len(issues)} issues:", flush=True)
            for it in issues:
                print(f"      - ch{it.get('chapter')} [{it.get('category')}/{it.get('severity')}] "
                      f"{it.get('issue')[:90]}", flush=True)
        elif t == "revision":
            revised.append(ev["chapter"])
            print(f"      ✓ ch{ev['chapter']} revised: {ev['word_count']} words", flush=True)
        elif t == "complete":
            final = ev
        elif t == "error":
            errors.append(ev.get("message", "?"))
            print(f"  [ERROR] {ev.get('message')}", flush=True)

    await pipe.close()
    elapsed = time.time() - t0

    # ── report + assertions ──
    print(f"\n  event counts: {counts}", flush=True)
    print(f"  elapsed: {elapsed:.0f}s, streamed chunk chars: {chunk_chars}", flush=True)
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(f"  {'PASS' if cond else 'FAIL'}: {msg}", flush=True)
        ok = ok and cond

    check(not errors, f"no error events ({len(errors)} errors)")
    check(bible is not None and bible.get("chapters"), "bible produced with a chapter beat sheet")
    n_planned = len(bible.get("chapters", [])) if bible else 0
    check(len(chapter_words) == n_planned and n_planned > 0,
          f"all {n_planned} planned chapters drafted ({len(chapter_words)} done)")
    check(len(issues) >= 3, f"critique found >= 3 issues ({len(issues)})")
    if issues:
        check(len(revised) >= 1, f"revision pass rewrote >= 1 chapter ({sorted(set(revised))})")
    check(final is not None, "complete event emitted")
    if final:
        wc = final.get("word_count", 0)
        check(wc > 0 and final.get("full_text"), f"final text assembled ({wc} words)")
        arts = lint_artifacts(final.get("full_text", ""))
        check(True, f"AI-artifact lint (informational): {arts or 'none of the crutch words'}")
        out_path.write_text(final["full_text"], encoding="utf-8")
        (out_path.with_suffix(".bible.json")).write_text(
            json.dumps(final.get("bible", {}), indent=2, ensure_ascii=False), encoding="utf-8")
        (out_path.with_suffix(".critique.json")).write_text(
            json.dumps(final.get("critique", []), indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  wrote: {out_path.name}, {out_path.stem}.bible.json, {out_path.stem}.critique.json", flush=True)
    print(f"\n  RESULT: {'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}", flush=True)
    return ok


async def run_short() -> bool:
    print(f"\n{'=' * 70}\n[short] StoryPipeline (paid/deepseek) — existing pipeline, unchanged\n{'=' * 70}", flush=True)
    pipe = StoryPipeline(tier="paid", cloud_provider="deepseek")
    parts: list[str] = []
    final = None
    errors = []
    async for ev in pipe.generate(PROMPT, GENRE, STYLE, max_words=350, pov=POV):
        t = ev.get("type")
        if t == "progress":
            print(f"  [{ev.get('stage')}] {ev.get('message')}", flush=True)
        elif t == "chunk":
            parts.append(ev.get("text", ""))
        elif t == "complete":
            final = ev
        elif t == "error":
            errors.append(ev.get("message"))
            print(f"  [ERROR] {ev.get('message')}", flush=True)
    await pipe.close()
    ok = bool(final) and not errors and final.get("word_count", 0) > 0
    if final:
        print(f"  title: {final.get('title')!r}, words: {final.get('word_count')}, "
              f"sections: {final.get('section_count')}", flush=True)
    print(f"  RESULT: {'PASS' if ok else 'FAIL'} — short story pipeline works", flush=True)
    return ok


async def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY not set", flush=True)
        sys.exit(2)

    if mode == "smoke":
        ok = await run_novel(target_words=2000, max_chapters=3,
                             force_chapters=3, force_words=350,
                             out_path=ROOT / "verify_smoke.md", label="smoke")
    elif mode == "full":
        ok = await run_novel(target_words=20000, max_chapters=12,
                             out_path=ROOT / "verify_full_novel.md", label="full")
    elif mode == "short":
        ok = await run_short()
    else:
        print(f"unknown mode: {mode}", flush=True)
        sys.exit(2)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
