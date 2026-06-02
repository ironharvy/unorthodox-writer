"""
Expansion + targeted-fix pass (Phase 6b) for "The Keeper of the Last Light".

deepseek-chat drafts ~1,000-word chapters regardless of the requested target, which lands
the book near 14k — and the draft also inherited a few defects from its source material
(the Chapter 7 shipwreck paradox, an early hand-hold in Ch4, "violet" overuse, a banned
aging cliché). This pass ENRICHES each drafted chapter to ~1,850 words AND applies the
remaining editor fixes, chapter by chapter, without altering plot or canon.

Per-chapter FIX_NOTES below carry the surgical corrections. CH7 gets a full causal rewrite:
the old "beam steady / didn't see the boat" logic is replaced with the coherent chain in
which Elias's own hand on the glass (reaching for Mira at the apex) guts the beam to dark
and drowns the unseen fishing boat.

Reuses the canon digest, style mandate, titles/targets/ends_on from novel_revise2.py.
Sequential, with the previous expanded chapter's tail for seamless transitions. Resumable
from revised2_expanded.json. Writes the final novel.md.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from novel_revise2 import (
    CANON,
    STYLE_MANDATE,
    NEW_CHAPTERS,
    REVISE_SYSTEM,
    TITLE,
    TAIL_CHARS,
    chat,
    word_count,
    assemble,
    client,
    ROOT,
)

DRAFTED = ROOT / "revised2_chapters.json"
EXPANDED = ROOT / "revised2_expanded.json"

DIRECTIVE_BY_NUM = {c["number"]: dict(c) for c in NEW_CHAPTERS}

# ── CH7: full causal rewrite of the shipwreck (the #1 critical fix) ──────────
CH7_DIRECTIVE_OVERRIDE = """The storm — the emotional crux — and the FIX for the shipwreck
paradox. The draft you are given has the WRONG causal chain and you must REPLACE it: it has the
beam "steady," Elias "keeping the light burning" and "saving them," and then a boat wrecking only
because he "did not see it." That makes his guilt nonsense. Discard that. Build instead this exact,
physically coherent chain, and make the new cause unmistakable on the page:

  (1) Because the ash has grown and he has crossed so many times, the portal is now EAGER: at every
      apex during the storm it strains open, and while it is open the shimmer SWALLOWS the beam — for
      those two or three seconds the warning light, pointed straight out to sea, GUTS TO BLACK and
      ships see nothing. His own trespass has poisoned his light.
  (2) He realises the portal only blooms FULLY (and darkens the beam) when he gives it himself — his
      hand on the glass, his eyes, his attention. If he stays hard at the mechanism, hands locked on
      the winding handle, refusing to look at Mira at the apex, the shimmer only flickers and the beam
      mostly holds.
  (3) He saves the FIRST foundering ship by brute discipline — forcing himself NOT to go to Mira
      pressed pleading to the glass, holding the beam clean through each apex until that ship claws off
      the rocks.
  (4) Then his will breaks. Mira, dying, begs him; at the next apex he goes to her and presses his
      hand to the warm glass (longing, anguish, the wish to touch her). The portal blooms fully; the
      beam guts to black for those few seconds, aimed full out to sea — and in exactly that black gap
      the second, unseen fishing boat, steering by the sweep, loses the light and drives onto the rocks
      at the tower's base. He tears his hand away; the portal closes; too late.
  (5) His guilt is now EARNED and he KNOWS it precisely: he did not fail to keep the flame lit — his
      divided heart darkened the beam. He chose her for three seconds, and three seconds drowned them.

After the storm he finds a single torn boot in the shallows. He sends Mira away, his voice breaking.
Do NOT resolve it. Advance the aging hard under the strain (sight fogging like salt-glass; hands that
will barely close). End on a man who kept faith with neither world, for a reason he understands exactly."""

CH7_ENDS_ON_OVERRIDE = (
    "Elias alone in the stilled, dripping lantern room, the torn boot on the table — knowing it was "
    "his own hand on the glass, his three seconds of reaching for Mira, that guttered the beam and "
    "drowned them, and that he has failed both worlds at once."
)

DIRECTIVE_BY_NUM[7]["directive"] = CH7_DIRECTIVE_OVERRIDE
DIRECTIVE_BY_NUM[7]["ends_on"] = CH7_ENDS_ON_OVERRIDE

# ── surgical fixes to apply while expanding each chapter ─────────────────────
FIX_NOTES = {
    1: "Name his wife HANNE at least once (naturally, in the grief that already runs through the "
       "chapter). Keep 'violet' out entirely if you can; the draft's 'Not violet—not yet' beat is good.",
    3: "Use the word 'violet' AT MOST ONCE in the whole chapter (the draft overuses it). Keep the "
       "hard-won, fearful, multi-night resistance before the first crossing exactly as established.",
    4: "TWO required fixes: (a) REMOVE any moment where Mira takes his hand / leads him by the hand — "
       "there must be NO physical hand-holding or tenderness in this chapter; they are still wary near-"
       "strangers and the bond is not yet earned (it is earned only after the Ch6 clash). Replace such a "
       "beat with her walking ahead and him following, or a look, not touch. (b) DELETE the cliché aging "
       "lines 'the veins standing up' and 'the gray had spread to my wrists' (gray hair does not spread "
       "to wrists) — render the cost only through the trade (hands stiff as cold tackle on the bone, a "
       "grind in the knuckles), advanced a little, not tallied.",
    5: "Use 'violet' at most once. Keep the full Stilled-town wander and Mira's dead — her mother and "
       "her twelve-year-old brother whom she could not carry out and now kneels to re-map — and the quiet "
       "parallel to Elias's own vigil. This chapter must feel complete and devastating.",
    6: "Use 'violet' AT MOST ONCE (the draft overuses it). Make the CLASH sharp and real — they truly "
       "fight over conflicting duties before any softening; Elias's wound (Hanne, the misread storm) is "
       "his reason; Mira weaponises his guilt and her desperation shows. 'I have been alone longer than "
       "you' lands only after the fight, as the first crack of a hard-won bond — not easy intimacy.",
    8: "Expand fully (the draft is thin). Land, ONCE and with weight, the true price (he pours his "
       "stored light and years in, dies, stays forever, the lighthouse goes dark) AND Mira's CONFESSION "
       "that she knew this from the start and hid it — let Elias be furious at the betrayal, then let her "
       "try to RELEASE him (tell him not to do it), and let him choose it anyway for his own reasons. "
       "Keep her cost as the Stilling (cracks, cold, fading), never graying. He does NOT cross here.",
    9: "Do NOT use the word 'bruise'/'bruised' anywhere (the draft has one). Keep the fixed, coherent "
       "sabotage exactly: oil font drained to a measured remainder; wrench wedged so the gears seize at "
       "the apex (lens locked facing the sea, portal held open, flame still burning); they cross; the "
       "STARVED flame guts out within the minute; when the light dies the portal collapses and seals.",
    10: "Use 'violet' AT MOST ONCE. Keep the corrected ending exactly: NO line that declares Elias's "
        "feeling, and absolutely no 'I did not regret a thing.' End on the IMAGE of the few distant "
        "keeper-lights steady in the thinning sky above the blooming plain.",
}


async def expand_chapter(ch_meta: dict, draft_text: str, rolling: str, prev_tail: str) -> str:
    target = max(1850, ch_meta["target"] + 100)
    floor = int(target * 0.88)
    fix = FIX_NOTES.get(ch_meta["number"], "")
    fix_block = f"\nSURGICAL FIXES FOR THIS CHAPTER (apply exactly):\n{fix}\n" if fix else ""
    prev_block = (
        "VERBATIM END OF THE PREVIOUS (already-expanded) CHAPTER — your first line must follow "
        f"from it in the same voice; do NOT repeat it:\n\"\"\"\n{prev_tail}\n\"\"\""
        if prev_tail else "This is the opening chapter of the novel."
    )
    story_so_far = rolling or "Nothing yet — this is the beginning."

    user = f"""{CANON}

{STYLE_MANDATE}

THE STORY SO FAR (for continuity; never contradict):
{story_so_far}

{prev_block}

You are EXPANDING, DEEPENING, and CORRECTING the existing draft of Chapter {ch_meta['number']}:
"{ch_meta['title']}". The draft below is good in places but too thin and carries defects to fix.
Re-compose it into a fuller, publication-ready chapter of about {target} words (NO FEWER THAN {floor}).

HOW TO WORK (enrichment, not padding):
  - Keep EVERY event, fact, image, and good line that belongs. Do not change the plot, the canon, or
    the chapter's purpose, except where the fixes below tell you to. Keep the chapter's FINAL beat.
  - Add depth, not repetition: more precise sensory detail (smell, silence, cold, texture, the quality
    of the light, the sounds of the mechanism and the sea), more of Elias's interiority and memory,
    more lived specificity in dialogue and place.
  - Honour this chapter's full intent:
{ch_meta['directive']}
{fix_block}
  - Obey every prose rule above: ration "violet" to at most once and NEVER use "bruise"; render aging
    only through the keeper's trade (driftwood-dry hands, joints grinding like un-oiled gears, sight
    fogging like salt-glass) and advanced a little at a time — never "veins like cord," "knuckles
    swollen," "papery skin," or a gray-hair tally; no three-part anaphora; no filler echo-dialogue; no
    generic similes; keep Elias's and Mira's voices distinct. The chapter must feel COMPLETE.

End the chapter on: {ch_meta['ends_on']}

Output ONLY the finished, expanded chapter prose — no title, header, notes, or markdown.

=== DRAFT TO EXPAND AND CORRECT (Chapter {ch_meta['number']}) ===
{draft_text}"""

    return await chat(REVISE_SYSTEM, user, max_tokens=6000, temperature=0.82)


async def main() -> None:
    drafted = {d["number"]: d for d in json.loads(DRAFTED.read_text(encoding="utf-8"))}

    done = json.loads(EXPANDED.read_text(encoding="utf-8")) if EXPANDED.exists() else []
    done_nums = {d["number"] for d in done}
    out: list[dict] = list(done)
    rolling = "".join(f"\nCh{d['number']} ({d['title']}): {d.get('recap','')}" for d in done)
    prev_tail = done[-1]["text"][-TAIL_CHARS:] if done else ""

    if done:
        print(f"[expand] resuming — {sorted(done_nums)} already expanded", flush=True)

    for n in sorted(drafted):
        if n in done_nums:
            continue
        ch_meta = DIRECTIVE_BY_NUM[n]
        draft = drafted[n]
        print(f"  → expanding Ch{n}: {ch_meta['title']} (from {word_count(draft['text'])} w) ...",
              flush=True)
        prose = (await expand_chapter(ch_meta, draft["text"], rolling, prev_tail)).strip()
        print(f"    ✓ expanded to {word_count(prose)} w", flush=True)

        entry = {"number": n, "title": ch_meta["title"], "text": prose,
                 "recap": draft.get("recap", "")}
        out.append(entry)
        rolling += f"\nCh{n} ({ch_meta['title']}): {draft.get('recap','')}"
        prev_tail = prose[-TAIL_CHARS:]
        EXPANDED.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    ordered = sorted(out, key=lambda x: x["number"])
    total = sum(word_count(d["text"]) for d in ordered)
    print(f"\n[expand] done — {len(ordered)} chapters, {total} words", flush=True)
    for d in ordered:
        print(f"   Ch{d['number']:>2} {d['title']:<28} {word_count(d['text']):>5} w", flush=True)

    joined = "\n".join(d["text"] for d in ordered)
    low = joined.lower()
    print("\n[expand] lint:", flush=True)
    print(f"   'violet' : {low.count('violet')}", flush=True)
    print(f"   'bruise' : {low.count('bruise')}   (target 0)", flush=True)
    print(f"   'however': {low.count('however')}", flush=True)
    print(f"   'veins standing' : {low.count('veins standing')}   (target 0)", flush=True)
    print(f"   'i did not regret': {low.count('i did not regret')}   (target 0)", flush=True)
    print("   per-chapter violet: " +
          ", ".join(f"Ch{d['number']}={d['text'].lower().count('violet')}" for d in ordered),
          flush=True)

    (ROOT / "novel.md").write_text(assemble(ordered), encoding="utf-8")
    print(f"\n[expand] wrote novel.md ({total} words)", flush=True)
    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
