"""
Revision pass (Phase 4) for "The Keeper of the Last Light".

Takes the first draft (novel_draft.md, 8 chapters) and the canonical bible,
and produces a restructured, line-edited 7-chapter final via deepseek-chat.

What this pass fixes (see evaluation.md):
  - Timeline contradiction: old Ch5 ended with a permanent crossing ("I was gone"),
    yet old Ch7 reopened in the lighthouse. The new order crosses exactly once.
  - Redundant old Ch6 ("The Dying Sun") re-explained the cage + sacrifice already
    given in Ch3 and enacted in Ch8. It is cut; its best imagery is salvaged into
    the new climax.
  - Plot hole: smashing the clockwork yet the portal still opening. The new Ch6
    sabotages the mechanism so it seizes AFTER the final apex carries them through.
  - Triple cage reveal -> one foreshadow (Ch3) + one payoff (Ch7).
  - AI prose tics: anaphoric triplets, one-word call-and-echo dialogue, repeated
    set-images ("ash like bones", "fingers left no mark", gray-hair tallies).

Continuity is preserved exactly as in the generator: a compact bible digest is
always present, plus a rolling synopsis of already-revised chapters and the
verbatim tail of the previous revised chapter.

Artifacts:
  - revised_chapters.json   (checkpoint)
  - novel.md                (assembled final; also re-polished by hand afterward)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parent
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com/v1"
TAIL_CHARS = 1100

client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)


async def chat(system: str, user: str, *, max_tokens: int, temperature: float,
               retries: int = 5) -> str:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 — broad for backoff
            last_err = exc
            wait = 4 * (attempt + 1)
            print(f"    ! API error (attempt {attempt + 1}/{retries}): {exc} — retrying in {wait}s",
                  flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"DeepSeek call failed after {retries} attempts: {last_err}")


def word_count(text: str) -> int:
    return len(text.split())


def load_old_chapters() -> dict[int, str]:
    text = (ROOT / "novel_draft.md").read_text(encoding="utf-8")
    parts = re.split(r"\n##\s+Chapter\s+(\d+):[^\n]*\n", text)
    # parts[0] is the title preamble; then alternating (num, body)
    chapters: dict[int, str] = {}
    for i in range(1, len(parts), 2):
        num = int(parts[i])
        body = parts[i + 1].strip()
        chapters[num] = body
    return chapters


# ── canon digest (pov-safe) ─────────────────────────────────

def bible_digest(bible: dict) -> str:
    p = bible["protagonist"]
    s = bible["setting"]
    chars = "\n".join(
        f"  - {c['name']} ({c['role']}): voice — {c['voice']}; wants — {c['want']}"
        for c in bible.get("characters", [])
    )
    rules = "\n".join(f"  - {r}" for r in s.get("portal_rules", []))
    return f"""TITLE: {bible['title']}
LOGLINE: {bible['logline']}
TONE: {bible['tone']}
POV/TENSE: first person, past tense, narrated by Elias the keeper.

NARRATOR — {p['name']}, age {p.get('age','?')}.
  Voice: {p['voice']}
  Wound: {p['wound']} | Want: {p['want']} | Need: {p['need']}
  Arc: {p['arc']}

OTHER CHARACTERS:
{chars or '  (none)'}

SETTING:
  Lighthouse: {s['lighthouse_name']} — {s['location_era']}
  The other world: {s['the_other_world']}
  PORTAL RULES (never contradict these):
{rules}

MOTIFS (use sparingly, never mechanically): {", ".join(bible.get('motifs', []))}"""


# ── global style mandate ────────────────────────────────────

STYLE_MANDATE = """You are revising a finished literary fantasy novel for publication. The story,
voice, and events are already good. Your job is to RE-COMPOSE the supplied chapter so the prose
is fresh and the structure is sound — not to paraphrase it line by line, and not to invent new plot.

Keep: first-person past tense; Elias's weathered, precise, self-deprecating voice; the concrete
sensory detail; the best individual images and lines from the source; all canon and portal rules.

ELIMINATE these patterns from the draft (they read as machine-written):
  1. Three-part anaphora ("I hated the light. I hated the tower. I hated the sea."; "I thought of X.
     I thought of Y. I thought of Z."; "I did not A. I did not B. I did not C."). Use AT MOST ONE such
     device in the whole chapter, and prefer none. Replace the rest with varied, connected sentences.
  2. One-word call-and-echo dialogue used as filler ("Weeks?" / "Yes." / "It is done." "It is done.").
     Let exchanges carry real weight; vary their shape.
  3. Recycled set-images. Do NOT keep describing ash as sounding "like bones / grinding bone / crushed
     shells / powdered bone" — choose one fresh comparison per chapter at most. Do not repeat "her
     fingers left no mark/smudge on the glass." Do not tally Elias's gray hairs every chapter — note
     the aging only when it genuinely lands, in fresh language.
  4. The em-dash reveal tic ("Not a flicker—I knew flickers." / "Not broke. Opened.") more than once.
  5. Generic similes ("steady as a heartbeat", "deep as wells", "like a living thing"). Cut or replace.

Vary sentence length and rhythm deliberately. Dialogue must sound spoken, not recited. Output ONLY the
chapter prose — no title, no header, no notes, no markdown."""


REVISE_SYSTEM = (
    "You are a meticulous literary novelist and line editor. You write atmospheric, restrained "
    "fantasy in the tradition of writers who care about sentences. You revise without flattening "
    "voice, and you never pad. You return only finished prose."
)


# ── the new 7-chapter plan ──────────────────────────────────
# Each entry: number, title, sources (old chapter numbers to draw from),
# target words, and a precise directive (what to keep / cut / fix / end on).

NEW_CHAPTERS = [
    {
        "number": 1,
        "title": "The Light That Never Sleeps",
        "sources": [1],
        "target": 1000,
        "directive": """Revise the source chapter (Elias's nightly ritual; the first shimmer in the
beam at the apex; the warm gray ash found at the base of the lens). Preserve the quiet dread and the
specificity of the mechanism (oil reservoir, trimmed wick, winding the mainspring twelve turns never
thirteen, the rotating lens). Keep the discovery of the ash that will not brush off and pulses with
faint heat. Trim the anaphora ("Some things you do not improve upon. Some things you only maintain.")
to a single clean beat. This is the reader's first page — make the opening line earn attention without
purple strain.""",
        "ends_on": "Elias kneeling by the warm ash he refuses to sweep away, half-admitting he has nowhere else to go.",
    },
    {
        "number": 2,
        "title": "The Cartographer of the Dying",
        "sources": [2],
        "target": 1000,
        "directive": """Revise the first crossing. Elias presses his hand to the lens at the apex; it
parts like water; he stumbles into Umbra — violet sky, packed-ash ground, the floating disc of his own
beam where the tower should be. He sees the Stilled standing frozen and meets Mira, the cartographer of
the dying, with her shifting ink-map drawn on skin. She names Umbra, the Stilling, and the Last Light,
and says his beam — not of her world — might reignite the sun. Elias retreats. Keep Mira's formal,
navigational cadence distinct from Elias's. Establish the aging cost with ONE clean image (a single gray
hair at his temple), not a tally.""",
        "ends_on": "Elias back in the lantern room at the mirror, finding the first gray hair and not looking away.",
    },
    {
        "number": 3,
        "title": "The Cage of Bone",
        "sources": [3],
        "target": 1050,
        "directive": """Revise the bargain chapter. Elias returns across several nights, timing the
portal (open only at the apex, a few seconds each rotation). Mira leads him to the Last Light: a dying
ember caged in bone and sinew. This is the ONLY full description of the cage before the climax — make it
vivid and singular so it can be paid off later, NOT re-described. She lays out the price in plain terms:
the beam could reignite the ember, but bringing it here leaves the lighthouse dark and ships will wreck.
Surface Elias's wound concretely once: the storm he misread, the wife he failed, the fourteen years of
atonement. Deepen the bond — end on Mira's line "I have been alone longer than you," and Elias not pulling
away. Show the aging cost through how his hands move, not by counting hairs. Do not let Mira fully spell
out the SELF-sacrifice (pouring himself in / staying forever) yet — that revelation belongs to Chapter 5;
here she only knows the beam is needed.""",
        "ends_on": "Mira's hand on his, 'I have been alone longer than you,' and Elias not pulling away.",
    },
    {
        "number": 4,
        "title": "What the Sea Takes",
        "sources": [4],
        "target": 1050,
        "directive": """Revise the storm chapter — the emotional crux. A storm forces the impossible
choice: the portal opens only at the apex, and while it is open the beam is invisible to ships. Mira
pleads through the glass; the Stilling is spreading toward her city. Elias chooses the sea. He saves one
foundering ship — then a second, unseen fishing boat strikes the rocks at the tower's base and is lost
with all aboard. After the storm he finds a single torn boot in the shallows. He sends Mira away, his
voice breaking. Keep the dramatic irony (he kept the light and still failed). Cut the repeated "her
fingers left no smudge." End on him alone, having failed both worlds — do NOT resolve it.""",
        "ends_on": "Elias alone in the stilled lantern room, the boot on the table, knowing he kept the light and failed both worlds anyway.",
    },
    {
        "number": 5,
        "title": "The Weight of Ash",
        "sources": [5],
        "target": 1050,
        "directive": """Revise the turning point. For days Elias refuses the portal and polishes the
lens in grief and self-hatred. Then Mira crosses to HIS world — she came through an unguarded apex and
the crossing is killing her faster; she is translucent, her skin cracking, the Stilling rooted in her
chest, days left. HERE she reveals the full price for the first time, plainly and only once: to reignite
the Last Light he must pour his stored light and years into it, which means he stays in Umbra forever and
the lighthouse goes dark for good. He has already given Umbra years; the light is in his blood now. This
is the ONE place the self-sacrifice is explained — make it land. He decides. CRITICAL: he does NOT cross
in this chapter. End on resolve, not departure: he tells Mira to wait, and turns to set his own house in
order. (Remove the old ending where he places his hand on the lens and is "gone.")""",
        "ends_on": "Elias deciding — telling Mira to wait at the base of the tower while he settles what he must leave behind. No crossing yet.",
    },
    {
        "number": 6,
        "title": "The Last Winding",
        "sources": [7],
        "target": 1000,
        "directive": """Revise the old 'Keeper's Choice' chapter and FIX its mechanics. Elias writes a
confession letter to the Maritime Authority (keep the letter, lightly tightened). He makes his final round
and winds the mainspring for the last time so the lens will turn to the apex. CRITICAL FIX for the plot
hole: he must NOT break the mechanism before crossing, or the portal could never open. Instead, as the lens
climbs toward the apex he wedges the wrench into the gear train so the mechanism will seize the instant the
rotation completes — the lens reaches the apex (portal opens), he and Mira cross while both touch the lens,
and behind them the gears grind and lock forever. The light dies because he abandons it and the mechanism
jams; it can never be relit. Keep the quiet beat of a ship later passing safely by moonlight, seen from
Umbra. This is the single permanent crossing in the book.""",
        "ends_on": "Elias on the ash of Umbra, watching from across the dark as a ship passes the unlit Grave Point safely by moonlight.",
    },
    {
        "number": 7,
        "title": "The Last Light",
        "sources": [8, 6],
        "target": 1050,
        "directive": """Revise the climax and ending. Use the vivid arrival/approach imagery from BOTH
source chapters but do NOT re-explain the bargain (already given) or re-describe the cage as if new — Elias
already knows it; now he sees it dying, smaller. He enters the cage and presses his palm to the shrinking
ember; his stored light and years pour out; the ember swells into a small steady sun. The ash becomes soil;
phosphorescent blooms spread; Mira solidifies, healed; Elias ages into a frail old man, at peace. For the
final image, KEEP IT INTIMATE per the book's intent — not "thousands of lights." A few distant points of
light on the far plain and in the thinning sky: other keepers, from other worlds, who came before. He is not
the first; he is part of a quiet lineage. End on Mira's smile and 'I did not regret a thing' — earned, not
sentimental. You may fold in the eerie detail of many footprints leading to the cage, and that others came
before, but keep it spare.""",
        "ends_on": "Elias old and spent in the bloom-light, the few distant keeper-lights across the dark, Mira's smile, and 'I did not regret a thing.'",
    },
]


async def revise_chapter(digest: str, ch: dict, old_chapters: dict[int, str],
                         rolling: str, prev_tail: str) -> str:
    source_blocks = "\n\n".join(
        f"=== SOURCE (original Chapter {n}) ===\n{old_chapters[n]}"
        for n in ch["sources"]
    )
    prev_block = (
        f"VERBATIM END OF THE PREVIOUS (already-revised) CHAPTER — continue seamlessly, do not repeat it:\n"
        f'"""\n{prev_tail}\n"""'
        if prev_tail else "This is the opening chapter."
    )
    story_so_far = rolling or "Nothing yet — this is the beginning."

    user = f"""{digest}

{STYLE_MANDATE}

THE STORY SO FAR (revised chapters already written, for continuity — do not contradict):
{story_so_far}

{prev_block}

NOW WRITE THE REVISED CHAPTER {ch['number']}: "{ch['title']}"

REVISION DIRECTIVE:
{ch['directive']}

End the chapter on: {ch['ends_on']}

Target length: about {ch['target']} words (no fewer than 900). Use the source material below as your raw
material — its events, its strongest images and lines — but re-compose freely into clean, varied prose that
obeys the style mandate. Output ONLY the finished chapter prose.

{source_blocks}"""

    return await chat(REVISE_SYSTEM, user, max_tokens=3400, temperature=0.8)


RECAP_SYSTEM = "You summarize fiction tightly and factually for continuity tracking. No flourish."


async def recap(ch_title: str, ch_number: int, prose: str) -> str:
    user = (
        f"Summarize the revised Chapter {ch_number} (\"{ch_title}\") in 3-4 plain sentences: only what "
        f"happened, what changed, and any facts established (names, places, rules, objects). For "
        f"continuity, not blurb.\n\n{prose}"
    )
    return await chat(RECAP_SYSTEM, user, max_tokens=300, temperature=0.2)


def assemble(title: str, chapters: list[dict]) -> str:
    parts = [f"# {title}\n"]
    for d in chapters:
        parts.append(f"\n## Chapter {d['number']}: {d['title']}\n\n{d['text']}\n")
    return "\n".join(parts)


async def main() -> None:
    bible = json.loads((ROOT / "bible.json").read_text())
    digest = bible_digest(bible)
    old_chapters = load_old_chapters()
    title = bible["title"]

    print(f"[revise] {len(NEW_CHAPTERS)} chapters, restructured from {len(old_chapters)} draft chapters",
          flush=True)

    revised: list[dict] = []
    rolling = ""
    prev_tail = ""

    for ch in NEW_CHAPTERS:
        n = ch["number"]
        print(f"  → Chapter {n}: {ch['title']} (from old {ch['sources']}) ...", flush=True)
        prose = (await revise_chapter(digest, ch, old_chapters, rolling, prev_tail)).strip()
        wc = word_count(prose)
        print(f"    ✓ revised ({wc} words)", flush=True)
        revised.append({"number": n, "title": ch["title"], "text": prose})

        r = (await recap(ch["title"], n, prose)).strip()
        rolling += f"\nCh{n} ({ch['title']}): {r}"
        prev_tail = prose[-TAIL_CHARS:]

        (ROOT / "revised_chapters.json").write_text(
            json.dumps(revised, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (ROOT / "novel.md").write_text(assemble(title, revised), encoding="utf-8")

    total = sum(word_count(d["text"]) for d in revised)
    print(f"[revise] Done — {len(revised)} chapters, {total} words → novel.md", flush=True)
    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
