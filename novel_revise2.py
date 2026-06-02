"""
Revision pass v2 (Phase 6) for "The Keeper of the Last Light".

Addresses the second editor's Revise & Resubmit brief (revision_brief.md):

  CRITICAL FIXES
  1. Shipwreck paradox — the portal's shimmer SWALLOWS the beam at the apex, so
     while Elias is entangled with Umbra his light guts to dark for those seconds.
     The fishing boat strikes during one of those dark apexes. Guilt made logical.
  2. Sabotage mechanics — seizing gears does NOT kill an oil flame. New, coherent
     rig: he STARVES the oil font to a measured remainder AND wedges the gear train
     to seize at the apex (lens locked facing the sea, portal held open while the
     flame still burns). They cross; the starved flame guts out a minute later; when
     the light dies the portal collapses, sealing behind them.
  3. Pacing — real friction/fear/disbelief before the first crossing; Umbra is
     EXPERIENCED before it is explained; Elias and Mira CLASH over conflicting duties
     before any tenderness. No hand-holding until the bond is earned.

  CHARACTER DEPTH
  4. Mira is a person: she lost her brother Sten and her mother to the Stilling; she
     compulsively maps the dead (mirroring Elias's compulsive light-keeping); she has
     anger, despair, defiance; her flaw/agency is that she WITHHOLDS the true price
     (that reigniting the Light kills the keeper) until Ch8.
  5. Elias's grief haunts from page one. Wife = Hanne. The "sameness" of the tower is
     prison AND shield: the routine walls him off from the one memory he can't bear.
     A full chapter (Ch2) renders the life before the ash.

  PROSE
  6. "violet"/"bruise" rationed hard; Umbra built from smell, silence, cold, texture,
     the dry crackle, the quality of sourceless light.
  7. Aging rendered through his PROFESSION (driftwood-dry hands, joints grinding like
     un-oiled gears, eyes fogging like salt-crusted glass, navigating by touch as he
     once navigated by light) — and progressed page by page, not dumped at once.
  8. Final line "I did not regret a thing" CUT. Ends on the IMAGE of the distant
     keeper-lights in the thinning sky.

  EXPANSION to ~15,000-20,000 words: 10 chapters, each complete (~1,600-1,900 words).
  Adds: a full life-before chapter; a wander through a Stilled town; an earned clash;
  the physical cost paid out page by page.

Machinery reuses novel_revise.py: bible digest + rolling synopsis + verbatim prev-tail,
chapter by chapter through deepseek-chat. Resumable from revised2_chapters.json.
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
TAIL_CHARS = 1200
CHECKPOINT = ROOT / "revised2_chapters.json"
TITLE = "The Keeper of the Last Light"

client = AsyncOpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url=BASE_URL)


async def chat(system: str, user: str, *, max_tokens: int, temperature: float,
               retries: int = 6) -> str:
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
            wait = 5 * (attempt + 1)
            print(f"    ! API error (attempt {attempt + 1}/{retries}): {exc} — retrying in {wait}s",
                  flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"DeepSeek call failed after {retries} attempts: {last_err}")


def word_count(text: str) -> int:
    return len(text.split())


def load_chapters(filename: str) -> dict[int, str]:
    text = (ROOT / filename).read_text(encoding="utf-8")
    parts = re.split(r"\n##\s+Chapter\s+(\d+):[^\n]*\n", text)
    chapters: dict[int, str] = {}
    for i in range(1, len(parts), 2):
        num = int(parts[i])
        chapters[num] = parts[i + 1].strip()
    return chapters


# ── canon digest (with the editor's fixes baked in as hard rules) ──────────

CANON = """TITLE: The Keeper of the Last Light
LOGLINE: A lighthouse keeper discovers the beam he tends is a portal to a dying world,
and must choose between saving a stranger and losing himself.

VOICE/POV: First person, past tense, narrated by Elias Voss, 52, keeper of Grave Point
Light on an isolated coast, ambiguous late-19th/early-20th century. He is blunt,
self-deprecating, exact; he reads the world in light and weather. His narration is
haunted from the first page by a grief he circles and only slowly names.

ELIAS'S WOUND (must haunt the prose from Chapter 1, not arrive late):
  Fourteen years ago his wife, HANNE, drowned in a storm he misread. He told her the
  weather would hold; it did not; the sea took her while he stood in the light and
  could only watch. He has not left the tower since. The brass gauge that marks the
  wick-height was set the year she died. The logbook entries never change because
  sameness is the only thing that keeps the memory at arm's length. The routine is at
  once his PRISON and his SHIELD: every measured task is a wall against the one memory.
  There is a chair by the window he does not sit in. There are small objects of hers in
  the tower he steers around without looking at. He answers the Maritime Authority's
  forms and the supply-boat manifests in clipped lines; the letters from Hanne's sister
  he no longer opens.

MIRA — cartographer of the dying, of Umbra (a real person, NOT an exposition device):
  Voice: formal, navigational, metaphors of mapping, bearing, depth, measurement —
  distinct from Elias's. She is exhausted and fierce. She lost her younger brother STEN
  and her mother to the Stilling years ago; she did not save them, she MAPPED them —
  drew their last positions instead of pulling them free. She still walks out alone and
  re-draws Sten's frozen figure, unable to stop — exactly as Elias trims the wick to the
  same height for fourteen years. This parallel is the spine of their bond: two people
  frozen in a ritual of penance for someone they could not save. She has anger, despair,
  and defiance (she refuses to lie down and be Stilled; she will walk through the Stilling
  itself rather than wait). Her FLAW and her AGENCY: she knows from the start that
  reigniting the Last Light kills the keeper who feeds it — and she WITHHOLDS this,
  weaponising Elias's guilt, because she is desperate to save her world. She confesses it
  only in Chapter 8, and the confession is a real betrayal that must be reckoned with.

UMBRA: a world of perpetual dim twilight. Atmosphere must be built from MANY senses, not
  one color: the enormous pressing silence; air that tastes of copper and cold stone and
  the faint sweet rot of dying things; ground of packed ancient ash, slate-hard underfoot
  in places, powder-fine elsewhere, that crackles dry like broken bread and settles on the
  tongue; a cold that is not temperature but absence; light that is sourceless, flat,
  shadowless or wrongly shadowed. (The sky's color may be named "violet" AT MOST ONCE per
  chapter; the word "bruise"/"bruised" is BANNED — find other ways.)

THE STILLING: not a quick death. When the light leaves a place, people slow — blood,
  breath, thought all cooling — and stand frozen for weeks, mid-gesture, before the last
  spark goes. A wall/line of cold advances across the land, swallowing towns. Umbra's sun,
  the LAST LIGHT, is a dying ember caged in lashed human bone and sinew; it has failed for
  generations.

PORTAL RULES (never contradict):
  - The portal opens only at the beam's apex — the few seconds the rotating lens faces
    full out to sea — and only there.
  - Only living things touching the lens at that instant may pass.
  - CRITICAL (the shipwreck logic): while the portal is open, the shimmer SWALLOWS the
    beam — the light guts to the strange dark/shimmer-colour for those seconds and is
    invisible to ships. The more Elias is entangled with Umbra (the ash grown, the portal
    eager, his hand on the glass, Mira pleading), the more the beam falters at the apex.
    His guilt for the wreck is therefore EARNED: it was his trespass that ate his light at
    the one moment a boat needed it — not a clean failure of duty.
  - Each crossing drains the keeper's vitality — rendered as AGING, and only as aging:
    hands going dry as driftwood, joints grinding like un-oiled gears, sight fogging like
    salt-crusted glass. (Mira's affliction is the Stilling — cracks, translucence, cold —
    NEVER graying. Keep the two cost-systems strictly separate.)
  - REIGNITING THE LAST LIGHT: the keeper must pour his stored light and years into the
    ember — all of them. It kills him; he ages to a husk and stays in Umbra; the lighthouse
    goes dark for good. (Revealed only in Ch8.)

THE FINAL SABOTAGE (Ch9) — physically coherent, FIXED:
  Seizing gears does NOT put out an oil flame. So Elias does two separate things. (a) He
  drains the oil font down to a measured remainder — "enough for the last climb and a
  hundred breaths after" (in character: a man of exact measures). (b) He wedges the wrench
  into the gear train so it will SEIZE the instant the lens completes its climb — locking
  the lens AT the apex, facing the sea, portal held open, flame still burning. He and Mira
  touch the glass and cross in those held-open seconds. From Umbra, through the glass, he
  watches the starved flame in the locked lens shrink and gut out within the minute; the
  instant the light dies the portal COLLAPSES and the glass goes black, sealed. The seized
  mechanism and dry font mean no replacement keeper can simply relight a working,
  rotating beam. This is the single permanent crossing in the book.

MOTIFS (use sparingly, never mechanically): the rhythm of the lens rotation; salt crust on
  glass; the foghorn; ash and dust; maps drawn on shifting skin."""


STYLE_MANDATE = """You are composing a chapter of a finished literary fantasy novel for
publication. Write rich, restrained, atmospheric prose — every chapter must feel COMPLETE
and unhurried. Do NOT paraphrase the source line by line; re-compose it into fresh prose,
keeping its events, its strongest images, and the established voice and canon.

KEEP: first-person past tense; Elias's weathered, precise, self-deprecating voice; Mira's
distinct formal-navigational cadence; concrete sensory specificity.

HARD PROSE RULES (the editor flagged these):
  1. ATMOSPHERIC PALETTE. Build Umbra from many senses — smell, silence, cold, texture,
     the dry crackle, the quality of sourceless light. Use "violet" AT MOST ONCE in the
     whole chapter. NEVER use "bruise" or "bruised." Vary how you evoke the dimness.
  2. AGING THROUGH PROFESSION. When the crossing-cost shows on Elias, render it in the
     vocabulary of his trade — hands dry as driftwood or weathered as seaward shingles;
     joints grinding like un-oiled gears or a mainspring losing its temper; eyes clouding
     like salt-fogged glass; finding the stairs by touch as he once read the sea by light.
     Do NOT write "veins like cord," "knuckles swollen," or "skin papery and lined."
     Let the decay advance a little at a time, never dumped all at once.
  3. NO three-part anaphora ("I hated X. I hated Y. I hated Z." / "I thought of A. I
     thought of B. I thought of C."). At most ONE such device in the whole chapter; prefer
     none. Vary sentence length and rhythm.
  4. NO filler call-and-echo dialogue ("Weeks?"/"Yes." / "It is done."/"It is done.").
     Exchanges must carry real weight and vary in shape; dialogue must sound spoken.
  5. NO generic similes ("steady as a heartbeat," "deep as wells," "like a living thing"),
     no em-dash reveal tic used more than once ("Not a flicker—I knew flickers."), no
     "however/moreover/furthermore/indeed."
  6. Do NOT tally Elias's gray hairs. Note the aging only where it genuinely lands.

Output ONLY the finished chapter prose — no title, no header, no notes, no markdown."""


REVISE_SYSTEM = (
    "You are a meticulous literary novelist and line editor who writes atmospheric, "
    "restrained fantasy in the tradition of writers who care about sentences. You build "
    "mood through precise sensory detail, you give every character interiority, you never "
    "pad, and you never flatten voice. You return only finished prose."
)


# ── the new 10-chapter plan ────────────────────────────────────────────────
# sources: (filename, chapter_number) pairs to feed as raw material.
#   "C" = current novel.md, "D" = novel_draft.md

NEW_CHAPTERS = [
    {
        "number": 1,
        "title": "The Light That Never Sleeps",
        "sources": [("C", 1)],
        "target": 1600,
        "directive": """Elias's nightly ritual and the first sign of the portal. Preserve the
specificity of the mechanism (salt-crusted glass, oil reservoir, the wick trimmed to a mark on
the brass gauge, winding the mainspring one-to-twelve-never-thirteen, the rotating lens, the
logbook). Keep the first SHIMMER at the apex and the discovery of the warm gray ASH at the base
of the lens that will not brush off and pulses faintly, like a second heartbeat in the floor.
NEW, CRITICAL: grief for HANNE must haunt this opening page. Establish without over-explaining
that the wick-mark and the unchanging logbook date to the year she drowned; that the sameness of
the work is the only wall holding the memory off; that there is a chair he does not sit in and
small things of hers he steers around. The routine is both prison and shield — show this, do not
state it baldly. Begin the aging-through-profession motif very lightly (e.g. hands gone dry as
driftwood at the winding). Make the opening line earn attention without purple strain.""",
        "ends_on": "Elias kneeling by the warm ash he refuses to sweep away, half-admitting to himself that he has nowhere else to go — the first thing in fourteen years that is not the same.",
    },
    {
        "number": 2,
        "title": "The Sameness",
        "sources": [("C", 1), ("C", 4)],
        "target": 1750,
        "directive": """A FULL chapter of the life the ash interrupted — the texture of fourteen
years. This is mostly interiority and memory, anchored to the present days in which Elias REFUSES
to touch the ash (it grows from a teaspoon to a fist over days; he circles it, frightened,
explaining it away as salt-fever and sleeplessness — establishing real friction and a rational
man's disbelief BEFORE any crossing). Render: the daily round and correspondence (the supply
boat, the Maritime Authority forms answered in clipped lines, the unopened letters from Hanne's
sister); who HANNE was and how they two lived in the tower together — small concrete habits, her
warmth against his exactness; and, finally and fully, THE DAY OF THE STORM: he misread the falling
glass and the wrong-quarter wind, told her it would hold, and the sea took her while he stood
helpless in the light. Show how each measured task since has been built to keep that single memory
at bay — the routine as prison and shield, dramatised, not declared. Advance the aging a little
(stiffening joints like a mainspring losing its temper). Mira does NOT appear; the portal is not
yet crossed.""",
        "ends_on": "Elias back at the ash at the base of the lens — the one thing in fourteen years that has changed — looking at it with dread and, against everything in him, the faint disquieting pull of wanting.",
    },
    {
        "number": 3,
        "title": "The Door That Was Not a Door",
        "sources": [("C", 2), ("D", 2)],
        "target": 1750,
        "directive": """The first crossing — and it must be HARD-WON and FRIGHTENING, not casual.
Honour fourteen years of rigid routine: he resists for nights; he tests the shimmer like a
sceptic; he reaches for the glass and pulls back more than once; fear and disbelief precede every
inch. When he finally crosses, let it be driven by a night when Hanne's memory is unbearable and
the cold pull of the strange door is the first NEW thing in fourteen years — the crossing won
against real terror, not stepped through lightly. On the far side, Elias EXPERIENCES Umbra before
anything is explained: the pressing silence, the copper-and-cold-stone air, the dry crackle of
packed ash, the sourceless dim light, the floating disc of his own beam where the tower should be.
He SEES the Stilled first — frozen figures mid-gesture — and feels their wrongness in his body
before any word like "Stilling" is spoken. He meets MIRA, who is GUARDED, terse, and suspicious of
him, NOT a tour-guide dumping exposition; she gives almost nothing away beyond her name and that
his crossing should be impossible. He retreats in fear. Establish the aging cost with ONE clean
image at the mirror (a single gray hair / sight briefly fogging) — no tally.""",
        "ends_on": "Elias back in the lantern room at the small mirror, finding the first mark the crossing left on him and not looking away — his own face the second thing in fourteen years to change.",
    },
    {
        "number": 4,
        "title": "The Cartographer of the Dying",
        "sources": [("C", 3), ("D", 3)],
        "target": 1800,
        "directive": """Elias returns across several nights, drawn back by the not-sameness as much
as by curiosity; he times the portal (open only at the apex, a few seconds each rotation). Develop
MIRA AS A PERSON, slowly thawing from suspicion to wary tolerance — give her interiority, dry wit,
flashes of anger and exhaustion; let her be doing her own work (mapping on shifting skin) rather
than waiting to explain things to him. She leads him to the LAST LIGHT — the dying ember caged in
lashed human bone and sinew. This is the ONE full, vivid description of the cage before the climax;
make it singular and unforgettable so it need not be re-described later. She lays out, piecemeal and
guardedly, only what she chooses to: the Stilling, that the Last Light is failing, and that his
beam — not of her world — might reignite it. She does NOT yet reveal the true price (that feeding it
kills the keeper); she is already withholding. Keep their distance — NO tenderness, NO hand-holding
yet. Advance the aging through how his hands MOVE on the cold bone, not by counting hairs.""",
        "ends_on": "Mira's flat, certain claim that his beam could reignite the Last Light — and Elias's first unease at how much she is plainly not telling him.",
    },
    {
        "number": 5,
        "title": "The Stilled Town",
        "sources": [("D", 6), ("C", 7)],
        "target": 1900,
        "directive": """The set-piece that makes Umbra's tragedy PALPABLE — show, never tell. Mira
takes Elias (or he insists on seeing more, and she relents) into a town the Stilling has already
claimed. Let him WANDER its streets among the frozen people caught MID-GESTURE: a baker's arm still
reaching into a cold oven; a mother stopped half-turned with a child's name still shaped on her
mouth; two men frozen over a board game; someone caught wiping ash from a doorstep. The cold, the
silence, the dust on open eyes — make the stakes land in the body. THIS is where Mira becomes fully
human: among these dead she shows him her own — her mother, and her younger brother STEN, frozen
years ago; we learn she did not pull them free, she MAPPED them, and she still comes out alone to
re-draw Sten's position, unable to stop. Let her anger and despair and defiance break through here.
Draw the explicit parallel (lightly) between her endless re-mapping of the dead and Elias trimming
the same wick for fourteen years — two penances. No romance yet; what passes between them is
recognition. Advance the aging (a joint grinding like an un-oiled gear; the dim starting to fog his
sight as salt fogs glass).""",
        "ends_on": "Elias and Mira leaving the frozen town in silence, the recognition between them unspoken — each seeing in the other a person who keeps a vigil for someone they could not save.",
    },
    {
        "number": 6,
        "title": "Two Duties",
        "sources": [("C", 3), ("D", 3), ("D", 6)],
        "target": 1800,
        "directive": """The CLASH — they must argue before they bond. The bargain forces their
conflicting duties into the open: Elias's beam is needed in Umbra, but bringing it here means the
lighthouse goes dark and ships will wreck. Surface Elias's WOUND concretely here in his own voice
(the storm he misread, Hanne, the fourteen years of atonement) — it is WHY he cannot abandon the
sea. Mira pushes hard, even cruelly, weaponising his guilt; she argues that the ships have other
lights and other harbours while her world has only this one failing ember; her desperation and a
flash of the thing she is hiding show through. They genuinely fight; he refuses; she is furious;
they part badly. But end on the first earned crack of understanding between two stubborn,
grief-locked people — let her line "I have been alone longer than you" land HERE, now that they have
collided, as the beginning of a hard-won bond, NOT as easy intimacy. Still no hand-holding; the
turn is recognition deepening toward trust. Advance the aging (hands dry as driftwood; a stiffness
he must work out before he can grip the winding handle).""",
        "ends_on": "After the fight, a fragile truce — Mira's 'I have been alone longer than you,' and Elias, for the first time, not turning away from her or from the choice she has set before him.",
    },
    {
        "number": 7,
        "title": "What the Sea Takes",
        "sources": [("C", 4), ("D", 4)],
        "target": 1850,
        "directive": """The storm — the emotional crux — and the FIX for the shipwreck paradox. A
storm drives ships toward the rocks while the portal grows eager. CRITICAL MECHANICS: every time
the lens climbs to the apex during the storm, the portal tries to open and the shimmer SWALLOWS the
beam — the light guts to the strange dark for those seconds, invisible to ships. Mira pleads through
the glass; the Stilling is spreading toward her city; Elias is torn between forcing the mechanism
and reaching for her. He fights to keep the beam clean and saves one foundering ship — but at one
apex, entangled (his hand on the warm glass, Mira's face there, the portal yawning), the beam guts
to dark for those few seconds, and in exactly that dark a second, unseen fishing boat strikes the
rocks at the tower's base and is lost with all aboard. His guilt is EARNED and LOGICAL: it was his
trespass into Umbra that ate his light at the one moment a boat needed it. After the storm he finds
a single torn boot in the shallows. He sends Mira away, his voice breaking. Do NOT resolve it — end
on a man who kept faith with neither world. Advance the aging hard here under the strain (sight
fogging; hands that will barely close).""",
        "ends_on": "Elias alone in the stilled, dripping lantern room, the torn boot on the table, knowing his own crossing-shadow guttered the light and that he has failed both worlds at once.",
    },
    {
        "number": 8,
        "title": "The Weight of Ash",
        "sources": [("C", 5), ("D", 5)],
        "target": 1850,
        "directive": """The turning point. For days Elias refuses the portal and polishes the lens in
grief and self-hatred, the torn boot on the table. Then MIRA crosses into HIS world — she came
through an unguarded apex and the crossing is killing her faster: translucent, her skin cracking,
the Stilling rooted in her chest, days left. (Her cost is the Stilling — cracks, cold, fading — NOT
graying; keep it distinct from his aging.) HERE, for the FIRST AND ONLY time, the true price is
revealed — and it is also Mira's CONFESSION: to reignite the Last Light he must pour his stored
light and years into it, which kills him; he stays in Umbra forever and the lighthouse goes dark for
good — and she has KNOWN this from the start and hidden it, weaponising his guilt. Let him be
furious at the betrayal; let it nearly break what they have built. Then the real turn: now that it
costs her nothing to lie and everything to be honest, she tries to RELEASE him — tells him not to do
it, that she should never have come — and he chooses it anyway, for his own reasons (the years he
has burned in atonement; that the light is already in his blood; that for once he can choose whom he
fails to save). He decides. CRITICAL: he does NOT cross in this chapter. End on resolve, not
departure — he sends Mira down to wait at the base of the tower while he sets his own house in
order.""",
        "ends_on": "Elias deciding — sending Mira down to wait at the base of the tower while he settles what he must leave behind. No crossing yet; only resolve.",
    },
    {
        "number": 9,
        "title": "The Last Winding",
        "sources": [("C", 6), ("D", 7)],
        "target": 1800,
        "directive": """The confession letter and the FIXED, physically-coherent sabotage. Elias
writes the letter to the Maritime Authority (keep its quiet weight; UPDATE its mechanics to match
below). Then the FIX, exactly: (a) he DRAINS the oil font down to a measured remainder — enough for
the last climb and a hundred breaths after (a man of exact measures metering his own light's death);
(b) he wedges the wrench into the gear train so it will SEIZE the instant the lens completes its
climb, locking the lens AT the apex, facing the sea, portal held open while the flame still burns.
He winds the mainspring a last time; the lens climbs; the gears seize at the apex (lens locked,
portal open, flame burning). He and Mira touch the glass and cross in those held-open seconds. From
Umbra, through the glass, he watches the starved flame in the locked lens shrink and gut out within
the minute — and the instant the light DIES, the portal COLLAPSES and the glass goes black, sealed
behind them. (Make crystal clear: seizing the gears did not kill the flame; STARVING THE OIL did,
after the crossing; and the dead flame is what closes the portal.) Keep the quiet beat: from Umbra,
a ship later passes the unlit Grave Point safely by moonlight. This is the single permanent crossing.
Advance the aging (the crossing tearing rather than parting; landing hard on grinding joints).""",
        "ends_on": "Elias on the cold ground of Umbra, watching through the blackening glass as the starved flame dies, the portal seals — and, far below on the sea, a ship passing the dark tower safely by moonlight.",
    },
    {
        "number": 10,
        "title": "The Last Light",
        "sources": [("C", 7), ("D", 8)],
        "target": 1800,
        "directive": """The climax and ending. Elias ALREADY knows the cage (do not re-explain the
bargain or re-describe the cage as if new) — now he sees it dying, smaller than before, the ember
shrunk near to nothing. He crosses the plain (you may fold in the eerie footprints of those who came
before, kept spare), enters the cage, and presses his palm to the shrinking ember. His stored light
and years pour out of him; render the aging FULLY here through his profession (hands going to
driftwood, joints to ungreased gears, sight fogging to salt-glass until he reads the world by touch)
— he ages to a frail husk, but at peace. The ember swells into a small steady sun; the ash becomes
soil; phosphorescent blooms spread; MIRA solidifies, the cracks sealing, healed and warm. Keep the
final scale INTIMATE — NOT thousands of lights: a few distant points of light on the far plain and in
the thinning sky, other keepers from other worlds who came before; he is one quiet entry in a long
lineage, not the first. CRITICAL ENDING: DELETE the old final line "I did not regret a thing." Do
NOT declare an emotion. End instead on the IMAGE — the few distant keeper-lights steady in the
thinning sky above the blooming dark — and let the image carry everything. The last sentence must be
a picture, not a statement of feeling.""",
        "ends_on": "An IMAGE, not a declaration: the few distant keeper-lights burning steady across the thinning sky above the blooming plain, Mira beside him. (Absolutely no closing line that names how Elias feels; no 'I did not regret a thing.')",
    },
]


async def revise_chapter(ch: dict, all_sources: dict[str, dict[int, str]],
                         rolling: str, prev_tail: str) -> str:
    source_blocks = "\n\n".join(
        f"=== RAW MATERIAL ({'current novel' if tag == 'C' else 'earlier draft'}, "
        f"Chapter {n}) ===\n{all_sources[tag][n]}"
        for tag, n in ch["sources"]
    )
    prev_block = (
        "VERBATIM END OF THE PREVIOUS (already-revised) CHAPTER — continue seamlessly in the same "
        f"voice and register; do NOT repeat it:\n\"\"\"\n{prev_tail}\n\"\"\""
        if prev_tail else "This is the opening chapter of the novel."
    )
    story_so_far = rolling or "Nothing yet — this is the beginning."

    user = f"""{CANON}

{STYLE_MANDATE}

THE STORY SO FAR (revised chapters already written — for continuity; never contradict):
{story_so_far}

{prev_block}

NOW WRITE THE REVISED CHAPTER {ch['number']}: "{ch['title']}"

REVISION DIRECTIVE:
{ch['directive']}

End the chapter on: {ch['ends_on']}

Target length: about {ch['target']} words — and NO FEWER THAN {int(ch['target'] * 0.85)}. Do not rush;
let the chapter breathe and feel complete. Use the raw material below for events, strongest images,
and continuity, but RE-COMPOSE freely into clean, varied prose obeying every style rule above.
Output ONLY the finished chapter prose.

{source_blocks}"""

    return await chat(REVISE_SYSTEM, user, max_tokens=5200, temperature=0.85)


RECAP_SYSTEM = "You summarize fiction tightly and factually for continuity tracking. No flourish."


async def recap(ch_title: str, ch_number: int, prose: str) -> str:
    user = (
        f"Summarize the revised Chapter {ch_number} (\"{ch_title}\") in 3-5 plain sentences: only "
        f"what happened, what changed, and any facts established (names, places, rules, objects, the "
        f"state of Elias's aging and Mira's Stilling). For continuity, not blurb.\n\n{prose}"
    )
    return await chat(RECAP_SYSTEM, user, max_tokens=320, temperature=0.2)


def assemble(chapters: list[dict]) -> str:
    parts = [f"# {TITLE}\n"]
    for d in chapters:
        parts.append(f"\n## Chapter {d['number']}: {d['title']}\n\n{d['text']}\n")
    return "\n".join(parts)


def load_checkpoint() -> list[dict]:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return []


async def main() -> None:
    sources = {"C": load_chapters("novel.md"), "D": load_chapters("novel_draft.md")}

    done = load_checkpoint()
    done_nums = {d["number"] for d in done}
    revised: list[dict] = list(done)
    rolling = "".join(f"\nCh{d['number']} ({d['title']}): {d.get('recap','')}" for d in done)
    prev_tail = done[-1]["text"][-TAIL_CHARS:] if done else ""

    if done:
        print(f"[revise2] resuming — {len(done)} chapter(s) already done: {sorted(done_nums)}",
              flush=True)

    print(f"[revise2] target {len(NEW_CHAPTERS)} chapters, ~15-20k words", flush=True)

    for ch in NEW_CHAPTERS:
        n = ch["number"]
        if n in done_nums:
            continue
        print(f"  → Chapter {n}: {ch['title']} (sources {ch['sources']}) ...", flush=True)
        prose = (await revise_chapter(ch, sources, rolling, prev_tail)).strip()
        wc = word_count(prose)
        print(f"    ✓ drafted ({wc} words)", flush=True)

        r = (await recap(ch["title"], n, prose)).strip()
        entry = {"number": n, "title": ch["title"], "text": prose, "recap": r}
        revised.append(entry)
        rolling += f"\nCh{n} ({ch['title']}): {r}"
        prev_tail = prose[-TAIL_CHARS:]

        CHECKPOINT.write_text(json.dumps(revised, indent=2, ensure_ascii=False), encoding="utf-8")

    total = sum(word_count(d["text"]) for d in revised)
    print(f"[revise2] all chapters done — {len(revised)} chapters, {total} words", flush=True)

    # Per-chapter table + simple lint of the editor's banned patterns.
    print("\n[revise2] chapter word counts:", flush=True)
    for d in sorted(revised, key=lambda x: x["number"]):
        print(f"   Ch{d['number']:>2} {d['title']:<28} {word_count(d['text']):>5} w", flush=True)

    joined = "\n".join(d["text"] for d in sorted(revised, key=lambda x: x["number"]))
    low = joined.lower()
    print("\n[revise2] lint (should be low / zero):", flush=True)
    print(f"   'violet'  : {low.count('violet')}", flush=True)
    print(f"   'bruise'  : {low.count('bruise')}   (target 0)", flush=True)
    print(f"   'however' : {low.count('however')}", flush=True)
    print(f"   'i did not regret' : {low.count('i did not regret')}   (target 0)", flush=True)

    print(f"\n[revise2] writing novel.md ({total} words)", flush=True)
    (ROOT / "novel.md").write_text(assemble(sorted(revised, key=lambda x: x["number"])),
                                   encoding="utf-8")
    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
