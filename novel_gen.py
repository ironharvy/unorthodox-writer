"""
Synopsis-driven novel generator (Option C).

Generates a coherent long-form novel with deepseek-chat via the OpenAI client.

Pipeline:
  1. BIBLE   — one call produces the canonical story bible + full beat sheet (JSON).
  2. DRAFT   — each chapter is drafted sequentially against the bible, a rolling
               synopsis of prior chapters, and the verbatim tail of the previous
               chapter (for voice/transition continuity).
  3. RECAP   — after each chapter, a short summary is generated and folded into the
               rolling synopsis so context stays bounded and canon stays consistent.

Artifacts written to the project root:
  - bible.json            (canonical story bible + beat sheet)
  - chapter_summaries.json
  - novel_draft.md        (assembled draft with chapter titles)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com/v1"
PREMISE = "A lighthouse keeper discovers the light is actually a portal to another world"
N_CHAPTERS = 8
TARGET_WORDS = 1000
TAIL_CHARS = 1200  # verbatim tail of previous chapter handed to the next


def load_key() -> str:
    if os.environ.get("DEEPSEEK_API_KEY"):
        return os.environ["DEEPSEEK_API_KEY"]
    env = Path.home() / ".hermes" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DEEPSEEK_API_KEY not found in env or ~/.hermes/.env")


client = AsyncOpenAI(api_key=load_key(), base_url=BASE_URL)


async def chat(system: str, user: str, *, max_tokens: int, temperature: float,
               json_mode: bool = False, retries: int = 4) -> str:
    """One chat completion with retry/backoff (DeepSeek can be slow/flaky)."""
    kwargs: dict = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 — broad on purpose for backoff
            last_err = exc
            wait = 4 * (attempt + 1)
            print(f"    ! API error (attempt {attempt + 1}/{retries}): {exc} — retrying in {wait}s",
                  flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"DeepSeek call failed after {retries} attempts: {last_err}")


def word_count(text: str) -> int:
    return len(text.split())


# ── Stage 1: Story bible ────────────────────────────────────

BIBLE_SYSTEM = (
    "You are a novelist and story architect with the instincts of a literary editor. "
    "You design tight, character-driven, atmospheric fantasy with grounded emotional stakes. "
    "You avoid cliché, melodrama, and generic 'chosen one' plotting. You always return valid JSON."
)

BIBLE_USER = f"""Design the complete blueprint (a "story bible") for a short literary fantasy novel of {N_CHAPTERS} chapters, each about {TARGET_WORDS} words.

Premise: "{PREMISE}"

Constraints and taste:
- First-person, past tense, narrated by the lighthouse keeper. The voice is weathered, precise, a little haunted; observant about light, weather, and the sea.
- Ground it. The portal must have concrete, consistent RULES (when it opens, what it costs, what can pass through, what happens to the lighthouse light when it's open). Decide these now and keep them iron-clad.
- The other world should be specific and strange, not generic high fantasy. Give it a name, a logic, and a wound of its own that mirrors the keeper's.
- The keeper must have a personal wound and an arc — a reason this discovery matters to *them*, not just "a portal exists." Avoid save-the-world stakes; keep stakes intimate and escalating.
- One or two secondary characters, each with a distinct voice and their own want. No interchangeable extras.
- A real ending: a costly choice, consequence, and a closing image. Not a neat bow, not a cheap twist.

Return ONLY a JSON object with this exact shape:
{{
  "title": "...",
  "logline": "one sentence",
  "pov": "first person, past tense, the keeper",
  "tone": "2-3 sentences on mood and prose texture",
  "themes": ["...", "..."],
  "protagonist": {{"name": "...", "age": 0, "voice": "how they sound on the page", "wound": "...", "want": "...", "need": "...", "arc": "from X to Y"}},
  "characters": [{{"name": "...", "role": "...", "voice": "...", "want": "..."}}],
  "setting": {{"lighthouse_name": "...", "location_era": "...", "the_other_world": "name + what it is", "portal_rules": ["concrete rule", "concrete rule", "concrete rule", "concrete rule"]}},
  "motifs": ["recurring image/object", "..."],
  "chapters": [
    {{"number": 1, "title": "evocative 2-4 words", "synopsis": "3-4 sentences of what actually happens", "emotional_beat": "what the reader feels", "must_include": ["concrete plot point", "concrete plot point"], "ends_on": "the hook or turn that closes the chapter"}}
  ]
}}

The "chapters" array must have exactly {N_CHAPTERS} entries forming a clear arc: ordinary world + inciting discovery, escalating exploration and complication, a midpoint reversal, rising cost, a climax built on a hard choice, and a resolution with a closing image. Each chapter must advance plot — no filler."""


async def make_bible() -> dict:
    print("[1/3] Generating story bible...", flush=True)
    raw = await chat(BIBLE_SYSTEM, BIBLE_USER, max_tokens=4096, temperature=0.6, json_mode=True)
    bible = json.loads(raw)
    chs = bible.get("chapters", [])
    if len(chs) != N_CHAPTERS:
        print(f"    ! bible returned {len(chs)} chapters (wanted {N_CHAPTERS}); proceeding anyway",
              flush=True)
    (ROOT / "bible.json").write_text(json.dumps(bible, indent=2, ensure_ascii=False))
    print(f"    ✓ \"{bible.get('title')}\" — {len(chs)} chapters planned", flush=True)
    return bible


# ── Stage 2: Chapter drafting ───────────────────────────────

def bible_digest(bible: dict) -> str:
    """Compact, always-present canon for every chapter prompt."""
    p = bible["protagonist"]
    s = bible["setting"]
    chars = "\n".join(
        f"  - {c['name']} ({c['role']}): voice — {c['voice']}; wants — {c['want']}"
        for c in bible.get("characters", [])
    )
    rules = "\n".join(f"  - {r}" for r in s.get("portal_rules", []))
    beats = "\n".join(
        f"  Ch{c['number']}. {c['title']}: {c['synopsis']}"
        for c in bible["chapters"]
    )
    return f"""TITLE: {bible['title']}
LOGLINE: {bible['logline']}
TONE: {bible['tone']}
POV/TENSE: {bible['pov']}

NARRATOR — {p['name']}, age {p.get('age','?')}.
  Voice: {p['voice']}
  Wound: {p['wound']} | Want: {p['want']} | Need: {p['need']}
  Arc: {p['arc']}

OTHER CHARACTERS:
{chars or '  (none yet)'}

SETTING:
  Lighthouse: {s['lighthouse_name']} — {s['location_era']}
  The other world: {s['the_other_world']}
  PORTAL RULES (never contradict these):
{rules}

MOTIFS: {", ".join(bible.get('motifs', []))}

FULL BEAT SHEET (for continuity; only WRITE the current chapter):
{beats}"""


DRAFT_SYSTEM = (
    "You are a literary novelist writing atmospheric fantasy in the tradition of writers who care about "
    "sentences. You write in first-person past tense as the lighthouse keeper. You write actual scene-prose "
    "with concrete sensory detail, real dialogue, and interiority — never summary. You resist cliché, "
    "purple metaphor pile-ups, and tidy moralizing. You vary sentence length and rhythm. "
    "You never use chapter headings, bullet points, or meta-commentary — only the story itself."
)


async def draft_chapter(bible: dict, ch: dict, digest: str,
                        rolling_summary: str, prev_tail: str) -> str:
    must = "\n".join(f"  - {m}" for m in ch.get("must_include", []))
    prev_block = (
        f"VERBATIM END OF THE PREVIOUS CHAPTER (continue seamlessly from this; do not repeat it):\n\"\"\"\n{prev_tail}\n\"\"\""
        if prev_tail else "This is the opening chapter of the novel."
    )
    story_so_far = rolling_summary or "Nothing yet — this is the beginning."

    user = f"""{digest}

THE STORY SO FAR (summary of chapters already written):
{story_so_far}

{prev_block}

NOW WRITE CHAPTER {ch['number']}: "{ch['title']}"
What must happen: {ch['synopsis']}
Emotional beat: {ch['emotional_beat']}
Concrete plot points to land:
{must}
End the chapter on: {ch['ends_on']}

Write the full chapter now — about {TARGET_WORDS} words (no fewer than 850). First-person past tense, the keeper's voice. Open in a scene, not with a summary. Use specific sensory detail and at least some dialogue where natural. Keep every canon and portal rule consistent. Close on the specified hook. Output ONLY the chapter prose — no title, no headers, no notes."""

    return await chat(DRAFT_SYSTEM, user, max_tokens=3000, temperature=0.85)


RECAP_SYSTEM = "You summarize fiction tightly and factually for continuity tracking. No flourish."


async def recap_chapter(ch_title: str, ch_number: int, prose: str) -> str:
    user = (
        f"Summarize Chapter {ch_number} (\"{ch_title}\") in 3-4 plain sentences capturing only what "
        f"happened, what changed, and any new facts established (names, places, rules, objects). "
        f"This is for continuity, not blurb.\n\n{prose}"
    )
    return await chat(RECAP_SYSTEM, user, max_tokens=300, temperature=0.2)


# ── Orchestration ───────────────────────────────────────────

async def main() -> None:
    bible = await make_bible()
    digest = bible_digest(bible)
    chapters = bible["chapters"]

    print(f"[2/3] Drafting {len(chapters)} chapters...", flush=True)
    drafted: list[dict] = []
    summaries: list[dict] = []
    rolling = ""
    prev_tail = ""

    for ch in chapters:
        n = ch["number"]
        print(f"  → Chapter {n}: {ch['title']} ...", flush=True)
        prose = await draft_chapter(bible, ch, digest, rolling, prev_tail)
        prose = prose.strip()
        wc = word_count(prose)
        print(f"    ✓ drafted ({wc} words)", flush=True)
        drafted.append({"number": n, "title": ch["title"], "text": prose})

        # update rolling context
        recap = (await recap_chapter(ch["title"], n, prose)).strip()
        summaries.append({"number": n, "title": ch["title"], "recap": recap})
        rolling += f"\nCh{n} ({ch['title']}): {recap}"
        prev_tail = prose[-TAIL_CHARS:]

        # checkpoint after every chapter so nothing is lost
        (ROOT / "chapter_summaries.json").write_text(
            json.dumps(summaries, indent=2, ensure_ascii=False)
        )
        _write_draft(bible, drafted)

    print("[3/3] Draft assembled.", flush=True)
    total = sum(word_count(d["text"]) for d in drafted)
    print(f"    ✓ {len(drafted)} chapters, {total} words → novel_draft.md", flush=True)
    await client.close()


def _write_draft(bible: dict, drafted: list[dict]) -> None:
    parts = [f"# {bible['title']}\n"]
    for d in drafted:
        parts.append(f"\n## Chapter {d['number']}: {d['title']}\n\n{d['text']}\n")
    (ROOT / "novel_draft.md").write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
