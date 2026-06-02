"""
Driver: reuse the existing (good) bible.json and run only the drafting stage.

Imports the generation helpers from novel_gen. The only bug in novel_gen was
bible_digest reading bible['pov'] directly; we sidestep it by ensuring the loaded
bible carries a 'pov' key before passing it in.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import novel_gen as ng

ROOT = Path(__file__).resolve().parent


async def run() -> None:
    bible = json.loads((ROOT / "bible.json").read_text())
    bible.setdefault("pov", "first person, past tense, narrated by the keeper")

    digest = ng.bible_digest(bible)
    chapters = bible["chapters"]

    print(f"[draft] Drafting {len(chapters)} chapters from existing bible...", flush=True)
    drafted: list[dict] = []
    summaries: list[dict] = []
    rolling = ""
    prev_tail = ""

    for ch in chapters:
        n = ch["number"]
        print(f"  → Chapter {n}: {ch['title']} ...", flush=True)
        prose = (await ng.draft_chapter(bible, ch, digest, rolling, prev_tail)).strip()
        wc = ng.word_count(prose)
        print(f"    ✓ drafted ({wc} words)", flush=True)
        drafted.append({"number": n, "title": ch["title"], "text": prose})

        recap = (await ng.recap_chapter(ch["title"], n, prose)).strip()
        summaries.append({"number": n, "title": ch["title"], "recap": recap})
        rolling += f"\nCh{n} ({ch['title']}): {recap}"
        prev_tail = prose[-ng.TAIL_CHARS:]

        (ROOT / "chapter_summaries.json").write_text(
            json.dumps(summaries, indent=2, ensure_ascii=False)
        )
        ng._write_draft(bible, drafted)

    total = sum(ng.word_count(d["text"]) for d in drafted)
    print(f"[draft] Done — {len(drafted)} chapters, {total} words → novel_draft.md", flush=True)
    await ng.client.close()


if __name__ == "__main__":
    asyncio.run(run())
