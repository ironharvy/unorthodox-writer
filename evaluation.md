# Evaluation Report — *The Keeper of the Last Light*

**Premise:** A lighthouse keeper discovers the light is actually a portal to another world.
**Final form:** 7 chapters, ~7,060 words, first-person past tense.
**Verdict:** Publishable novella-in-miniature. Every chapter earns its place; the arc is complete and the prose is clean. The issues below were found in the first draft and have all been resolved in the final `novel.md`.

---

## 1. Architecture decision (Phase 1)

I read `engine/pipeline.py` and `engine/backends/cloud.py`. The stock `StoryPipeline` (expand → outline → draft → polish) is built for a **single short story**: its final *polish* stage re-writes the entire assembled text in one pass, which collapses long-form structure and cannot hold novel-length continuity. `CloudBackend` already supports DeepSeek via the OpenAI client (`base_url=https://api.deepseek.com/v1`, `model=deepseek-chat`).

**Chosen approach: Option C — a synopsis-driven generator with a canonical story bible.** This is the correct choice for long-form coherence, and it produced a complete first draft:

1. **Bible** — one call generates the canonical blueprint (characters, ironclad portal rules, motifs, an 8-beat chapter sheet) as JSON.
2. **Draft** — each chapter is written against (a) the always-present bible digest, (b) a *rolling synopsis* of prior chapters, and (c) the *verbatim tail* of the previous chapter for voice/transition continuity.
3. **Recap** — after each chapter a tight factual summary is folded into the rolling synopsis, so context stays bounded and canon stays consistent.

The fix/revision pass (Phase 4) reuses the same machinery: a restructured 7-chapter plan, line-edited chapter-by-chapter through `deepseek-chat` with the bible digest + rolling synopsis + previous-chapter tail, then a hand-verified polish pass.

---

## 2. Plot & Structure

**Strengths.** Clear shape: ordinary world + uncanny discovery (Ch1–2) → escalating bargain and intimacy (Ch3) → the impossible-choice crux (Ch4) → refusal and turning point (Ch5) → point of no return (Ch6) → climactic sacrifice and resolution (Ch7). Stakes stay intimate (one keeper, one dying woman, the drowned strangers on his conscience) rather than ballooning into save-the-world melodrama, exactly as the premise wanted.

**Issues found in the first draft — all fixed:**

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| P1 | **Timeline contradiction.** Old Ch5 ended with a *permanent* crossing ("I stepped through… the beam died… And I was gone"), yet old Ch7 reopened with Elias back in the lighthouse writing a letter — with no coherent way back, since the portal needs the lighthouse beam lit. | Critical | Restructured. The book now crosses **exactly once, permanently**, in the new Ch6. Old Ch5 ends on *resolve* (he sends Mira down, sets down the cloth, goes to write the letter), not departure. |
| P2 | **Redundant chapter.** Old Ch6 ("The Dying Sun") re-introduced the bone cage and re-explained the self-sacrifice already implied in Ch3 and enacted in Ch8 — a filler chapter of pure exposition. | High | **Cut.** Its strongest arrival imagery was salvaged into the new climax (Ch7). The cage is now revealed *once* (Ch3, foreshadow) and paid off *once* (Ch7). |
| P3 | **Plot hole: the self-defeating sabotage.** Old Ch7 had Elias smash the clockwork *and then* cross through the lens — but a smashed clockwork means the lens can't rotate to the apex, so the portal could never open. | High | Re-mechanised. He now **wedges the wrench so the gear train seizes the instant the rotation completes** — the lens reaches the apex (portal opens), he and Mira cross, and only *then* do the gears shear and lock. The confession letter is updated to match ("The lens is intact, but the clockwork will seize at the apex"). |
| P4 | **Over-explained mechanic.** The "pour yourself in / stay forever / lighthouse goes dark" rule was stated in three separate chapters. | Medium | Consolidated. The full price is explained **once**, by Mira in Ch5, where it carries the most weight; Ch6–7 *enact* it without re-stating. |
| P5 | **Pacing.** Old Ch3 ran long (1,312 words) and old Ch6 dragged as static exposition. | Medium | Ch6 cut; lengths now balanced (see §6). |

No remaining contradictions: portal rules (opens only at the beam's apex; only living things touching the lens may pass; while open the beam is invisible to ships; each crossing ages the keeper) hold across all seven chapters.

---

## 3. Characters

**Elias Voss (narrator).** Consistent voice — blunt, self-deprecating, reading the world in light and weather. His arc (guilt-paralysed routine → a single deliberate, costly act of trust) is complete and motivated. His wound (he misread the storm that killed his wife; fourteen years of atonement at the lens) is now surfaced **once, concretely** in Ch3, instead of being gestured at vaguely; it powers every subsequent choice.

**Mira, cartographer of the dying.** Distinct register preserved — formal, navigational, metaphors of mapping and measurement. Her want (a new light for a freezing world) is clear and never collapses into Elias's voice.

**Issue fixed (C1):** In the draft, Mira was once given "gray streaks in her hair" — but graying is *Elias's* crossing-cost, while *her* affliction is the Stilling (cracks, translucence, cold). This conflated the two cost-systems. Fixed: that line now describes the cracks reaching her jaw and the color bleeding from her eyes — her own failure mode, not his.

Secondary "cast" (the frozen Stilled, the off-page drowned sailors, the single torn boot) function as pressure and conscience rather than as characters, which suits a novella of this length.

---

## 4. Prose & Style

**Tense/POV:** First-person past throughout. Verified consistent — no slips.

**AI artifacts & telltale patterns — scanned and removed:**

- **"However / moreover / furthermore / it was then that / indeed":** none present (verified by search).
- **Three-part anaphora** (the draft's signature tic): "I hated the light. I hated the tower. I hated the sea."; "I thought of X. I thought of Y. I thought of Z."; "I did not polish the glass. I did not wind the spring. I did not check the oil."; "I looked at the lights. I looked at the blooms. I looked at the sun." — **all broken** into varied, connected sentences. Exactly **one** such device is deliberately retained, at the final emotional beat ("They were warm. They were patient. They were watching."), where the cadence is earned.
- **Recycled set-images:** the draft repeatedly described ash as sounding "like bones / grinding bone / crushed shells / powdered bone." Reduced to a single fresh comparison per occurrence. Duplicated phrases collapsed to one instance each: "her fingers left no mark" (was 2×), "no larger than a walnut" (was 2×).
- **Mechanical aging-tally:** the draft counted Elias's gray hairs/lines in nearly every chapter, sometimes incoherently ("gray spread to my wrists"). Thinned to land only where it carries feeling, and corrected so the cost reads as *aging of the hands* (lines, slack skin, ache) rather than literal gray hair on the wrists.
- **Em-dash reveal tic** and a "tore/tore/tear" pile-up in the crossing scene: smoothed.

**Dialogue:** Mira and Elias speak in distinct rhythms; exchanges were tightened so one-word call-and-echo beats ("Weeks?" / "Yes.") are used sparingly and for deliberate effect (e.g., the escalating "Yes." / "Yes." / *silence* when Elias names the cost of leaving the light dark), not as filler.

**Sentence variety:** Deliberately mixed — short declaratives for the keeper's routine, longer breath for the crossings and the sea.

---

## 5. Worldbuilding & Consistency

- **Setting details hold:** Grave Point Light, the twelve-turns-never-thirteen winding, the salt crust, the foghorn, oil reservoir and trimmed wick recur consistently. Umbra is specific and strange (violet permanent dusk, packed-ash ground, the Stilling, the Last Light caged in human bone, maps drawn on shifting skin) rather than generic high fantasy, and it mirrors the keeper's own wound (a slow cold that follows misjudgment).
- **Internal logic:** The portal rules are now obeyed without exception, including the final crossing (§P3). The one deliberate rule-bend — Mira crossing *into* Elias's world in Ch5 — is explicitly framed as a desperate, self-killing alternative ("I walked through the Stilling… until my body began to follow the same pattern"), not a free pass.
- **No dangling elements:** the ash, the boot, the letter, the wedged wrench, and the foreshadowed cage all pay off.

---

## 6. Pacing & Length

| Ch | Title | Words | Function |
|----|-------|------:|----------|
| 1 | The Light That Never Sleeps | 849 | Discovery — ash & shimmer |
| 2 | The Cartographer of the Dying | 838 | First crossing; Mira; the ask |
| 3 | The Cage of Bone | 1,223 | The bargain, the cost, the bond |
| 4 | What the Sea Takes | 1,212 | The storm; the impossible choice; the wreck |
| 5 | The Weight of Ash | 946 | Grief; Mira's fading; the decision |
| 6 | The Last Winding | 881 | The letter; the sabotage; the crossing |
| 7 | The Last Light | 1,114 | The sacrifice; the bloom; the ending |

**Total: ~7,060 words.** Within the 5,000–10,000 target; every chapter sits in the ~800–1,200 band and advances the plot. No filler.

---

## 7. Emotional Impact

The stakes are concrete and escalating: a private guilt (the dead wife), then strangers' lives weighed against a stranger's world, then the keeper's own remaining years spent like fuel. The Ch4 storm delivers a genuine gut-punch — he keeps the light *and still* fails (the unseen fishing boat), which earns his later refusal and his eventual choice. The ending is bittersweet rather than triumphant: he is aged to a husk, the light is out, ships must fend for themselves — but Umbra blooms, and a handful of distant keeper-lights reframe his sacrifice as one quiet entry in a long lineage. The closing line ("I did not regret a thing") is earned, not sentimental. The final-image scale was deliberately pulled back from the draft's "thousands of lights" to "a dozen, perhaps," keeping the intimacy the premise calls for.

---

## 8. Summary of changes made (Phase 4–5)

1. Restructured 8 chapters → **7**, cutting the redundant "Dying Sun" exposition chapter.
2. Fixed the **Ch5→Ch7 timeline contradiction** (one permanent crossing, correctly placed).
3. Fixed the **clockwork/portal plot hole** (mechanism seizes *after* the apex; letter updated to match).
4. Consolidated the **self-sacrifice mechanic** to a single explanation (Ch5).
5. Fixed the **cost-system conflation** on Mira (cracks/Stilling, not graying).
6. Removed **AI prose tics**: anaphora triplets, recycled ash/bone similes, duplicate phrases, em-dash reveals, the gray-hair tally; verified absence of "however/moreover"-type connectives.
7. Rebalanced chapter lengths; nudged Ch1 over 800 words with an in-voice logbook beat that deepens the routine-as-atonement theme.
8. Sharpened chapter titles ("The Storm Season" → "What the Sea Takes"; "The Keeper's Choice" → "The Last Winding"; "The Ash and the Map" → "The Cartographer of the Dying").

Final novel: `novel.md`.
