# Pipeline Stage Gates and Self-Review Checks

This document defines per-stage quality gates for `StoryPipeline` and `NovelPipeline`. It extends the manuscript evaluation framework in `MANUSCRIPT_EVALUATION_GUIDE.md` by moving the checks earlier in the generation process, where failures are cheaper to recover from.

The gates are not intended to prove literary quality. They catch broken structure, unusable artifacts, canon drift, truncation, and AI-specific failure modes early enough that the pipeline can retry only the failed stage.

## Gate Contract

Every gate should return a normalized result:

```json
{
  "stage": "outline",
  "check_type": "PROGRAMMATIC",
  "status": "pass|warn|retry|abort",
  "score": 1,
  "strictness": "free|paid|debug",
  "reasons": ["section_count below minimum"],
  "metrics": {"word_count": 842},
  "retry_hint": "Regenerate outline with 6-8 sections and explicit climax/resolution."
}
```

Statuses:

| Status | Meaning | Pipeline Action |
|---|---|---|
| `pass` | Artifact is usable. | Continue. |
| `warn` | Artifact has non-critical weakness. | Continue and log; paid tier may route to review. |
| `retry` | Stage output is recoverably broken. | Retry the same stage with the previous valid input plus `retry_hint`. |
| `abort` | Output cannot be recovered locally or repeated retries failed. | Stop and surface an error. |

Check types:

| Type | Definition | Default Use |
|---|---|---|
| `PROGRAMMATIC` | Pure code, no model call. | Always run first. |
| `SELF_REVIEW` | Same model reviews its own output. | Paid tier by default; free tier only for critical stages or debug. |
| `EXTERNAL_REVIEW` | Different or stronger model reviews the output. | Paid/debug for high-risk artifacts, final QA, or after warnings. |

## Strictness Profiles

| Profile | Programmatic Gates | Self-Review | External Review | Retry Budget |
|---|---|---|---|---|
| `free` | Required critical checks only. | Outline and final story optional; skip draft section review unless gate warns. | Off. | 1 retry per stage. |
| `paid` | All programmatic checks. | All phase/stage self-reviews. | Bible, whole-draft critique, final polish when scores are weak. | 2 retries per stage/phase. |
| `debug` | All checks plus verbose metric capture. | All. | All major artifacts. | 2 retries, then abort with full diagnostics. |

Recommended thresholds:

| Result | Programmatic Trigger | Self-Review Trigger |
|---|---|---|
| `pass` | Critical fields present; counts in range; no hard red flags. | Overall score `>= 4` and no fail item. |
| `warn` | Minor range miss, mild repetition, low but usable density. | Overall score `3`; no critical fail. |
| `retry` | Missing required structure, severe truncation, wrong format, impossible count. | Overall score `<= 2`, or any critical checklist item fails. |
| `abort` | Parser failure after retries, empty output, unsafe impossible state. | Repeated review failure after retry budget. |

## Global Metrics

Log these for every stage/phase:

| Metric | Notes |
|---|---|
| `pipeline_kind` | `short` or `novel`. |
| `stage_or_phase` | `expand`, `outline`, `draft_section`, `polish`, `bible`, `draft_chapter`, `critique`, `revision`. |
| `artifact_id` | Section/chapter number where applicable. |
| `attempt` | Retry number starting at 1. |
| `started_at`, `finished_at`, `duration_ms` | Wall-clock timing. |
| `backend_provider`, `backend_model` | If available. |
| `prompt_tokens`, `completion_tokens`, `total_tokens` | If backend exposes usage. |
| `input_word_count`, `output_word_count` | Always computable. |
| `gate_status`, `gate_score`, `gate_reasons` | Programmatic result. |
| `self_review_score`, `self_review_failures` | If review ran. |
| `external_review_score`, `external_review_failures` | If review ran. |
| `retry_hint` | Used for regeneration prompt. |

Shared text metrics:

| Metric Family | Examples |
|---|---|
| Length | word count, sentence count, paragraph count, section/chapter variance. |
| Dialogue | quote ratio, dialogue line count, unattributed quote runs, long monologues. |
| Prose | average sentence length, sentence length variance, repeated sentence openings, passive markers. |
| AI artifacts | crutch phrase hits, cliché hits, repeated n-grams, template phrase count. |
| Structure | required field coverage, arc marker presence, climax/resolution placement. |
| Continuity | entity names, rules mentioned, contradictions flagged, object/location drift. |

Suggested AI crutch phrase families to count: `however`, `moreover`, `furthermore`, `in conclusion`, `testament to`, `in that moment`, `as if the world held its breath`, `not just`, `but also`, repeated three-part anaphora, repeated reflective endings.

## StoryPipeline Gates

### Stage 1: Expand

User prompt becomes a story premise with title, characters, setting, conflict, and narrative premise.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Required fields parse | `PROGRAMMATIC` | `TITLE`, `CHARACTERS`, `SETTING`, `CONFLICT`, `PREMISE` extracted. | One non-premise field thin but present. | Retry if title or premise missing; abort after parser retry budget. |
| Premise length | `PROGRAMMATIC` | Premise body 150-550 words. | 100-149 or 551-700 words. | Retry if `<100`, `>700`, or output is mostly labels. |
| User seed retention | `PROGRAMMATIC` | At least one salient noun/name/concept from user prompt appears or has a close variant. | Weak retention. | Retry if the premise ignores the prompt. |
| Conflict presence | `PROGRAMMATIC` | Conflict contains stakes, obstacle, and personal consequence markers. | Stakes are vague. | Retry if no central struggle can be detected. |
| Opening-prose requirement | `PROGRAMMATIC` | Premise includes scene-like prose: concrete nouns plus action/sensory verbs. | Leans summary but usable. | Retry if it is only synopsis, bullet list, or meta-commentary. |
| Originality and specificity | `SELF_REVIEW` | Score `>=4`; premise has specific protagonist, setting, desire, pressure, hook. | Score `3`. | Retry if score `<=2` or reviewer says generic/cliché. |
| Seed-fidelity review | `EXTERNAL_REVIEW` | Paid/debug only when self-review warns. | Minor mismatch. | Retry if external model says the premise does not honor the prompt. |

Critical blockers: missing premise, missing conflict, no protagonist, no setting, or output in the wrong format.

#### B) Self-Review Prompt

```text
Review the story premise you just generated.

Check:
1. It preserves the user's seed idea.
2. It has a specific protagonist, setting, conflict, stakes, and hook.
3. The PREMISE reads like opening story prose, not plot summary.
4. The genre/style/POV are compatible with the request.
5. It avoids generic AI texture, clichés, and vague abstractions.

Score 1-5:
1 broken or off-prompt; 2 weak/generic; 3 usable but thin; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" if score <=2 or any required story component is missing.
```

#### C) Metrics Collection

Log required-field coverage, premise word count, title length, character count, setting word count, conflict word count, seed-term overlap, genre/style/POV requested vs detected, crutch phrase hits, cliché hits, self-review score, retry count, timing, and token usage.

### Stage 2: Outline

Premise becomes structured sections with summary, emotion, and key points.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Parser success | `PROGRAMMATIC` | `_parse_outline` returns sections. | N/A | Retry if zero sections; abort after retry budget. |
| Section count vs target | `PROGRAMMATIC` | Under 1000 words: 4-6; 1000-3000: 6-12; 3000-5000: 10-18; 5000+: 15-25. | Off by 1-2 sections. | Retry if far outside range or less than 3. |
| Required fields per section | `PROGRAMMATIC` | Every section has title, summary, emotion, key points. | One field thin in one section. | Retry if any section lacks summary or key points. |
| Arc coverage | `PROGRAMMATIC` | Opening, complication/rising action, climax, resolution signals present. | Climax/resolution implied but not explicit. | Retry if no climax or no resolution section. |
| Event progression | `PROGRAMMATIC` | Summaries contain state-changing verbs and consequences. | Some sections feel static. | Retry if most sections are atmosphere-only. |
| Word allocation sanity | `PROGRAMMATIC` | Estimated section words `>=80`; total draft pool can meet target. | Mild variance risk. | Retry if section count makes target impossible. |
| Structural self-review | `SELF_REVIEW` | Score `>=4`; clear causality, escalation, character agency. | Score `3`. | Retry if score `<=2`, missing climax/resolution, or protagonist is passive. |
| External structure review | `EXTERNAL_REVIEW` | Paid/debug when target `>3000` or self-review warns. | Minor pacing issue. | Retry if broken arc or major causality issue. |

Critical blockers: unparseable outline, no resolution, no climax, section count too low for target, or sections do not advance events.

#### B) Self-Review Prompt

```text
Review the outline you just generated.

Check:
1. Section count fits the word target.
2. Every section has title, summary, emotional arc, and key plot points.
3. The outline has setup, inciting incident, escalation, climax, and resolution.
4. Each section changes stakes, knowledge, relationship, or options.
5. The protagonist has agency in major turns.
6. No section is filler, pure mood, or redundant.

Score 1-5:
1 broken; 2 structurally weak; 3 usable but uneven; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" if the arc is incomplete, section count is wrong, or causality is weak.
```

#### C) Metrics Collection

Log section count, expected section count range, fields missing per section, summary word counts, key point counts, emotion label diversity, detected arc markers, protagonist agency markers, repeated section titles, section summary similarity, self-review score, external-review score if any, timing, and token usage.

### Stage 3: Draft

Each outline section becomes streamed prose. Gates should run per section and once on the assembled draft.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Section non-empty | `PROGRAMMATIC` | Section has `>=60` words and no headers/meta notes. | Slightly short but scene-like. | Retry if empty, mostly prompt echo, or contains "I cannot". |
| Section word target | `PROGRAMMATIC` | Within 50%-180% of estimated section target. | 40%-50% or 180%-220%. | Retry if `<40%`, `>220%`, or clearly truncated. |
| Truncation detection | `PROGRAMMATIC` | Ends with punctuation, completed sentence, no dangling label. | Abrupt but readable. | Retry if ends mid-sentence, with unmatched quote, or with outline labels. |
| Scene/prose density | `PROGRAMMATIC` | Contains action or dialogue plus concrete sensory/detail markers. | Low dialogue/action but prose is acceptable for reflective scene. | Retry if pure synopsis or exposition. |
| Required beat inclusion | `PROGRAMMATIC` | Section title/summary/key point terms are represented. | One minor key point missing. | Retry if central section event is absent. |
| Continuity with previous section | `PROGRAMMATIC` | No immediate repeated paragraph; opening does not restart story. | Mild transition issue. | Retry if repeats previous section or contradicts immediate prior facts. |
| AI artifact scan | `PROGRAMMATIC` | Crutch/cliché/repetition counts below configured thresholds. | Mild artifact density. | Retry if high exact repetition, template endings, or prose is mechanically patterned. |
| Section craft review | `SELF_REVIEW` | Paid/debug or when programmatic gate warns. Score `>=4`. | Score `3`. | Retry if score `<=2`, section is summary, missing beat, or voice/POV breaks. |
| External prose review | `EXTERNAL_REVIEW` | Debug or paid final draft sample. | Local line-level issues. | Retry flagged sections if model finds severe truncation, canon break, or non-prose. |

Assembled draft checks:

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Full draft word count | `PROGRAMMATIC` | 60%-140% of target before polish. | 50%-60% or 140%-160%. | Retry shortest/missing sections if `<50%`; warn if long but coherent. |
| Section count preserved | `PROGRAMMATIC` | Drafted section count equals outline count. | N/A | Retry missing section. |
| Duplicate section detection | `PROGRAMMATIC` | No near-duplicate section pair over similarity threshold. | One repeated motif. | Retry duplicate section. |
| POV consistency | `PROGRAMMATIC` | Pronoun profile compatible with requested POV. | Mixed but possibly intentional. | Retry if sustained wrong POV. |

Critical blockers: empty section, severe truncation, prompt echo, missing core beat, repeated previous section, wrong language/format, or wrong POV throughout.

#### B) Self-Review Prompt

```text
Review this drafted story section against its outline beat.

Check:
1. It is actual scene prose, not summary or notes.
2. It includes the required section event and key points.
3. It continues from previous text without contradiction or restart.
4. POV, tense, tone, and character voice stay consistent.
5. It contains concrete action, sensory detail, interiority, or dialogue as appropriate.
6. It avoids repetition, clichés, crutch transitions, and AI-template phrasing.
7. It does not look truncated.

Score 1-5:
1 unusable; 2 retry needed; 3 usable with warnings; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" for truncation, missing beat, summary-only prose, contradiction, or wrong POV.
```

#### C) Metrics Collection

Per section, log word count, target ratio, sentence count, paragraph count, quote ratio, action verb density, sensory lexicon count, concrete noun ratio, direct emotion label count, crutch phrase count, repeated n-grams, sentence opening entropy, passive marker rate, key-point coverage, previous-section similarity, punctuation/truncation flags, self-review score, retry count, timing, and token usage.

For assembled draft, log total word count, section word variance, min/max section size, duplicate section pairs, estimated dialogue ratio, POV pronoun profile, repeated phrase top list, artifact density per 1,000 words, and warnings carried into polish.

### Stage 4: Polish

Assembled draft becomes the final short story.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Final non-empty | `PROGRAMMATIC` | Final text exists and is longer than 50% of draft. | 50%-70% but coherent. | Retry if empty, meta-output, or severe compression. |
| Target word count | `PROGRAMMATIC` | 70%-130% of requested `max_words`. | 55%-70% or 130%-160%. | Retry if `<55%` or `>160%` unless user requested flexible length. |
| Plot preservation | `PROGRAMMATIC` | Named characters, setting terms, and major section events still represented. | Minor event loss. | Retry if polish removes protagonist, conflict, climax, or ending. |
| No headers/commentary | `PROGRAMMATIC` | No section labels, critique notes, or model commentary. | N/A | Retry if output includes editorial notes instead of story. |
| Prose improvement signals | `PROGRAMMATIC` | Repetition/artifact counts do not worsen; sentence variety acceptable. | No measurable improvement but usable. | Retry if artifacts worsen sharply or text becomes repetitive. |
| Final story self-review | `SELF_REVIEW` | Score `>=4` across arc, character, prose, continuity. | Score `3`. | Retry polish if score `<=2` or red-flag override appears. |
| External final review | `EXTERNAL_REVIEW` | Paid/debug; or when final self-review warns. | Continue with warnings for minor craft notes. | Retry polish or abort if broken arc, canon drift, or severe AI artifacts. |

Critical blockers: final is shorter than half the draft, dropped ending, added commentary, severe repetition, wrong POV throughout, or no narrative arc.

#### B) Self-Review Prompt

```text
Review the polished short story.

Check:
1. It preserves the draft's plot, characters, conflict, climax, and ending.
2. It has a complete narrative arc with consequence or deliberate closure.
3. Character motivation and agency are clear.
4. POV, tense, tone, and genre remain consistent.
5. Prose is more specific and rhythmic than the draft.
6. It avoids repeated phrases, clichés, summary-heavy emotion, and AI artifacts.
7. It is not truncated and contains no notes, labels, or commentary.

Score 1-5:
1 broken; 2 retry; 3 functional with warnings; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" for lost plot, missing ending, severe repetition, wrong POV, or truncation.
```

#### C) Metrics Collection

Log final word count, target ratio, draft-to-final compression ratio, character/entity preservation, section-beat preservation, arc marker presence, quote ratio, sentence length mean/variance, repeated n-grams, crutch phrase counts, cliché counts, passive rate, lexical diversity, self-review scores by category if returned, external-review decision, final gate result, timing, and token usage.

## NovelPipeline Gates

### Phase 0: Bible

The user prompt becomes a canonical blueprint: title, logline, POV, tone, themes, protagonist, secondary characters, setting/world rules, motifs, and chapter beat sheet.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| JSON parse/schema | `PROGRAMMATIC` | Parses to `StoryBible`; required top-level fields populated. | Optional fields thin. | Retry if invalid JSON after strict re-ask; abort after retry budget. |
| Chapter count | `PROGRAMMATIC` | Exactly `self.n_chapters`, numbered 1..N. | N/A after normalization only if raw count was close. | Retry if raw chapter count differs or chapters missing. |
| Chapter beat completeness | `PROGRAMMATIC` | Every beat has title, synopsis, emotional beat, `must_include`, `ends_on`, word target. | One thin field. | Retry if synopsis, title, or `ends_on` missing in any chapter. |
| Word targets | `PROGRAMMATIC` | Chapter word targets within 75%-125% of `words_per_chapter`; total within 80%-120% of target. | Mild variance. | Retry if many targets missing/impossible. |
| Protagonist sheet | `PROGRAMMATIC` | Name plus flaw/wound, want, need, voice, arc. | One field thin. | Retry if no protagonist arc or no want/need. |
| Secondary character distinctiveness | `PROGRAMMATIC` | 1-3 characters with role, voice, want. | Missing voice for one character. | Retry if cast empty when premise implies cast, or all voices/wants duplicate. |
| Setting and rules | `PROGRAMMATIC` | At least 2 concrete world rules and location/era/atmosphere. | Rules vague but present. | Retry if no rules, rules contradict each other lexically, or setting absent. |
| Arc shape | `PROGRAMMATIC` | Beat sheet has inciting incident, midpoint/escalation, climax/hard choice, resolution/closing image. | One arc marker implicit. | Retry if no climax, no ending, or chapters are episodic filler. |
| Prompt fidelity | `PROGRAMMATIC` | Salient seed terms retained. | Weak retention. | Retry if bible ignores prompt. |
| Bible self-review | `SELF_REVIEW` | Score `>=4`; no critical failures. | Score `3`. | Retry if score `<=2`, weak arc, contradictory rules, or passive protagonist. |
| External canon review | `EXTERNAL_REVIEW` | Paid/debug by default. | Continue with warnings for minor thinness. | Retry if external model flags contradiction, missing arc, or unusable rules. |

Critical blockers: invalid schema, wrong chapter count, missing protagonist, no world rules, no ending, no chapter beat sheet, or prompt ignored.

#### B) Self-Review Prompt

```text
Review the story bible you just generated.

Check:
1. JSON fields are complete: title, logline, POV, tone, themes, protagonist, characters, setting, motifs, chapters.
2. Chapter count is exactly {n_chapters}, numbered 1..{n_chapters}.
3. Each chapter has synopsis, emotional beat, must_include, ends_on, and word_target.
4. The beat sheet forms a full arc: setup, inciting incident, escalation, midpoint, climax, resolution.
5. The protagonist has want, need, flaw/wound, voice, agency, and an earned arc.
6. Secondary characters have distinct roles, voices, and wants.
7. World rules are concrete, non-contradictory, and capable of generating stakes.
8. The bible preserves the user's seed idea and avoids generic plotting.

Score 1-5:
1 broken; 2 retry; 3 usable with warnings; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" for wrong chapter count, missing arc, contradictory rules, absent protagonist arc, or off-prompt bible.
```

#### C) Metrics Collection

Log JSON parse attempts, schema coverage percentage, chapter count, raw chapter numbering errors, total planned words, chapter word target variance, protagonist field coverage, secondary character count, character voice/want uniqueness, world rule count, possible contradiction pairs, location count, motif count, arc marker coverage, seed-term overlap, self-review score, external-review score, retry count, timing, and token usage.

### Phase 1: Drafting

Each chapter is drafted against the bible digest, rolling synopsis, and previous chapter tail. Gates run after every chapter and after the complete draft.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Chapter non-empty | `PROGRAMMATIC` | Chapter has substantial prose and no headers/notes. | N/A | Retry if empty, prompt echo, or model refusal. |
| Chapter word count | `PROGRAMMATIC` | 50%-160% of `beat.word_target`. | 40%-50% or 160%-200%. | Retry if `<40%`, `>200%`, or below configured hard floor. |
| Truncation | `PROGRAMMATIC` | Ends cleanly, balanced quotes, no dangling markdown. | Abrupt but complete sentence. | Retry if mid-sentence, unmatched quotes, or "continue" artifact. |
| Beat coverage | `PROGRAMMATIC` | Synopsis and `must_include` events represented. | One minor beat thin. | Retry if central beat missing. |
| Ends-on hook | `PROGRAMMATIC` | Closing paragraphs reflect requested `ends_on` turn/hook. | Hook weaker than planned. | Warn or retry if chapter role depends on it. |
| Scene quality | `PROGRAMMATIC` | Contains action/dialogue/interiority/sensory detail; not pure recap. | Low dialogue acceptable for interior chapter. | Retry if summary-only. |
| Bible canon adherence | `PROGRAMMATIC` | Names, POV, setting, rules, character facts consistent with bible digest. | Possible minor drift. | Retry if protagonist name/POV/rule changes. |
| Previous-tail continuity | `PROGRAMMATIC` | Does not duplicate previous tail; opening continues plausibly. | Mild repeated line. | Retry if previous ending is copied or contradicted. |
| Rolling synopsis update | `PROGRAMMATIC` | Recap generated; rolling synopsis under cap and includes changed facts. | Recap thin. | Retry recap, not chapter, if recap is bad. |
| AI artifact and repetition scan | `PROGRAMMATIC` | Below thresholds for crutch phrases, repeated n-grams, template endings. | Mild artifact density. | Retry if severe patterning or repeated paragraphs. |
| Chapter self-review | `SELF_REVIEW` | Paid/debug per chapter; free only on warns. Score `>=4`. | Score `3`. | Retry if score `<=2`, missing beat, canon drift, or truncation. |
| External chapter review | `EXTERNAL_REVIEW` | Paid/debug for first chapter, midpoint, climax, final chapter, or warnings. | Minor line issues. | Retry chapter if broken canon, missing beat, or wrong POV. |

Whole-draft checks after all chapters:

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Chapter completeness | `PROGRAMMATIC` | Drafted chapters exactly match bible chapters. | N/A | Draft missing chapters before critique. |
| Full word target | `PROGRAMMATIC` | 70%-130% of `target_words`. | 55%-70% or 130%-160%. | Retry shortest chapters if `<55%`; warn if long. |
| Chapter variance | `PROGRAMMATIC` | Coefficient of variation within configured limit, no extreme outliers. | One outlier. | Retry outlier if it damages structure. |
| Canon ledger drift | `PROGRAMMATIC` | No hard name/rule/relationship contradictions. | Possible soft drift. | Retry affected chapter before critique. |
| Duplicate chapter scan | `PROGRAMMATIC` | No near-duplicate chapter pairs. | Reused motif only. | Retry duplicate chapter. |

Critical blockers: missing chapter, severe truncation, wrong POV, central bible rule contradicted, repeated previous chapter, missing chapter beat, or summary-only chapter.

#### B) Self-Review Prompt

```text
Review the chapter you just drafted.

Check:
1. It follows Chapter {chapter_number}'s synopsis, emotional beat, must_include list, and ends_on hook.
2. It is full scene prose, not recap, outline, or notes.
3. It preserves bible canon: names, world rules, relationships, POV, tone, and character facts.
4. It continues from the story-so-far and previous chapter tail without repetition or contradiction.
5. It has concrete action, sensory grounding, interiority, and dialogue where natural.
6. It advances stakes, knowledge, relationship, or character arc.
7. It avoids AI artifacts, repeated phrases, clichés, and mechanical transitions.
8. It is complete and not truncated.

Score 1-5:
1 unusable; 2 retry; 3 usable with warnings; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" for canon drift, missing beat, summary-only prose, duplicated previous text, wrong POV, or truncation.
```

#### C) Metrics Collection

Per chapter, log word count, target ratio, paragraph count, sentence count, quote ratio, action/dialogue/interiority/sensory density, direct emotion label rate, passive rate, sentence length variance, crutch phrase count, repeated n-grams, previous-tail overlap, beat coverage score, `must_include` coverage, `ends_on` coverage, bible entity matches, rule mentions, possible canon drift flags, recap word count, rolling synopsis word count, compression count, self-review score, external-review score, retry count, timing, and token usage.

Whole draft metrics: total word count, chapter count, chapter word variance, shortest/longest chapters, draft-to-bible entity consistency, world rule contradiction flags, repeated phrases across chapters, dialogue ratio by chapter, pacing outliers, setup/payoff candidates, and carried warnings.

### Phase 2: Critique

The full draft receives a structural editorial pass that returns chapter-specific issues.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| JSON parse/schema | `PROGRAMMATIC` | Parses to object with `issues` list. | N/A | Retry strict JSON if parse fails; abort after retry budget. |
| Issue count | `PROGRAMMATIC` | 3-10 issues, matching prompt. | 1-2 issues only if draft programmatic metrics are excellent. | Retry if zero issues or more than 10 unprioritized issues. |
| Chapter references | `PROGRAMMATIC` | Every issue has valid integer chapter. | One cross-chapter issue mapped imperfectly. | Retry if most issues lack valid chapter references. |
| Severity validity | `PROGRAMMATIC` | Severity in `high|medium|low`; not all low unless metrics are clean. | All medium acceptable. | Retry if invalid severities or all low despite known warnings. |
| Category coverage | `PROGRAMMATIC` | Categories map to plot/character/pacing/prose/general; major known warnings represented. | Limited coverage but actionable. | Retry if only vague prose notes and structural warnings exist. |
| Quote/evidence | `PROGRAMMATIC` | Each issue has short quote/evidence or specific location. | One missing quote. | Retry if most lack evidence. |
| Actionable fix | `PROGRAMMATIC` | Each issue has concrete rewrite instruction. | One generic fix. | Retry if fixes are vague praise or non-actions. |
| Critique self-review | `SELF_REVIEW` | Score `>=4`; issues are specific, prioritized, and actionable. | Score `3`. | Retry if score `<=2`, vague, missing known problems, or no high/medium issue. |
| External critique review | `EXTERNAL_REVIEW` | Paid/debug preferred: stronger/different model audits critique quality. | Continue with warnings if critique is thin but usable. | Retry critique if external model says it missed major structural failures. |

Critical blockers: unparseable JSON, zero issues, no valid chapter references, no actionable fixes, or critique ignores known programmatic red flags.

Note: a perfect draft should still receive at least a small number of concrete refinement issues because the current critique prompt requires 3-10. If future behavior allows "no material issues", adjust this gate to accept zero only with strong independent metrics and external review.

#### B) Self-Review Prompt

```text
Review the critique issues you just produced.

Check:
1. There are 3-10 issues.
2. Every issue has valid chapter, category, severity, issue, quote/evidence, and fix.
3. Issues are concrete and revision-worthy, not vague praise or generic advice.
4. At least one issue addresses structural risk if the draft has plot, pacing, character, or canon problems.
5. Severity distribution is credible; not all low unless the draft is unusually clean.
6. Fixes tell the revision pass exactly what to change.
7. Cross-chapter problems are assigned to the best chapter to rewrite.

Score 1-5:
1 unusable; 2 retry; 3 usable with warnings; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "fix_instruction": "..."}

Use "retry" for vague issues, invalid chapters, missing fixes/evidence, or missed major known warnings.
```

#### C) Metrics Collection

Log issue count, valid chapter reference count, issues per chapter, severity distribution, category distribution, quote length, quote found-in-draft boolean, fix word count, vague-fix markers, known programmatic warning coverage, self-review score, external-review score, retry count, timing, and token usage.

### Phase 3: Revision

Only chapters flagged by critique are rewritten, then the book is reassembled.

#### A) Quality Gate

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Revised chapter non-empty | `PROGRAMMATIC` | Revised text exists and is prose only. | N/A | Retry if empty, notes, or prompt echo. |
| Word count range | `PROGRAMMATIC` | 50%-180% of original and 50%-160% of beat target. | Slightly outside one range. | Retry if severe expansion/compression. |
| Non-identical rewrite | `PROGRAMMATIC` | Text differs meaningfully from original; similarity below configured ceiling. | Mostly same but issue was small. | Retry if nearly identical while issues require change. |
| Issue coverage | `PROGRAMMATIC` | Evidence/fix terms addressed; problematic quote removed or contextualized. | One low-severity issue weakly handled. | Retry if high/medium issue still appears unchanged. |
| Canon preservation | `PROGRAMMATIC` | Bible facts, chapter role, surrounding continuity preserved. | Minor continuity risk. | Retry if new contradiction introduced. |
| Previous/following continuity | `PROGRAMMATIC` | Opening works after previous chapter; ending still supports next chapter. | Transition could be smoother. | Retry if surrounding continuity breaks. |
| Prose quality delta | `PROGRAMMATIC` | Artifact/repetition metrics do not worsen materially. | Minor line issue. | Retry if revision introduces severe artifacts. |
| Revision self-review | `SELF_REVIEW` | Score `>=4`; all flagged issues fixed. | Score `3`. | Retry if score `<=2` or any high/medium issue unresolved. |
| External revision review | `EXTERNAL_REVIEW` | Paid/debug for high-severity revisions. | Continue with warning for minor remaining issues. | Retry if external model finds issue unresolved or new canon drift. |

Final assembled book checks:

| Check | Type | Pass | Warn | Retry/Abort |
|---|---|---|---|---|
| Chapter count preserved | `PROGRAMMATIC` | Matches bible chapter count. | N/A | Abort or recover missing chapter before complete event. |
| Full word count | `PROGRAMMATIC` | 70%-130% of target. | 55%-70% or 130%-160%. | Warn or retry worst outliers depending strictness. |
| Revised chapter list | `PROGRAMMATIC` | Every valid critique chapter revised once. | Low-only skipped if configured. | Retry missing high/medium chapter. |
| Remaining issue scan | `PROGRAMMATIC` | High/medium issue quotes no longer appear unchanged. | Some quotes remain but context changed. | External review or retry. |
| Final external review | `EXTERNAL_REVIEW` | Paid/debug: whole manuscript score `>=3.4` using guide dimensions, no red-flag override. | Score 2.7-3.3: complete with warnings. | Abort or mark needs further revision if `<2.7` or red flag persists. |

Critical blockers: revised text identical to original, unresolved high-severity issue, new canon contradiction, missing chapter, or final assembly loses chapters.

#### B) Self-Review Prompt

```text
Review the revised chapter against the original and the editor's issues.

Check:
1. Every listed issue is fixed, especially high/medium severity items.
2. The revised chapter still fulfills the bible beat, emotional beat, must_include list, and ends_on hook.
3. It preserves established canon, character facts, POV, tone, and surrounding continuity.
4. It is meaningfully revised, not nearly identical to the original.
5. It does not introduce new plot holes, contradictions, or pacing damage.
6. Prose is at least as strong as before and avoids AI artifacts.
7. It is complete, scene-based prose with no notes or commentary.

Score 1-5:
1 unusable; 2 retry; 3 usable with warnings; 4 strong; 5 excellent.

Return JSON only:
{"score": 1, "status": "pass|warn|retry", "failures": [], "unfixed_issue_indexes": [], "fix_instruction": "..."}

Use "retry" if any high/medium issue remains, the chapter is nearly identical, continuity breaks, or prose is truncated.
```

#### C) Metrics Collection

Per revised chapter, log original word count, revised word count, target ratio, similarity score, changed paragraph count, issue coverage by issue index, old quote still present, new contradiction flags, previous-chapter overlap, next-chapter transition flags, crutch phrase delta, repetition delta, dialogue ratio delta, self-review score, external-review score, retry count, timing, and token usage.

For final assembly, log final word count, chapter count, revised chapter list, skipped issue list, remaining quote list, chapter variance, manuscript-level artifact counts, canon drift flags, final external score if run, final status, timing, and token usage.

## Recovery Rules

1. Run `PROGRAMMATIC` checks before any LLM review.
2. If a programmatic gate returns `pass`, only run self-review if strictness requires it.
3. If a programmatic gate returns `warn`, run self-review in paid/debug; free tier may continue unless the warning is on outline, final polish, bible, critique, or revision.
4. If a gate returns `retry`, regenerate only that artifact:
   - Expand: regenerate premise from user prompt.
   - Outline: regenerate outline from accepted premise.
   - Draft section: regenerate only failed section using prior accepted sections.
   - Polish: rerun polish from accepted assembled draft.
   - Bible: regenerate bible from user prompt.
   - Draft chapter: regenerate only failed chapter using bible, rolling synopsis, and previous tail.
   - Critique: rerun critique over accepted full draft.
   - Revision: rerun only failed revised chapter.
5. Pass `retry_hint` into the regeneration prompt as an explicit correction instruction.
6. After retry budget is exhausted, return `abort` for hard failures and `warn` for non-critical quality concerns, depending on strictness.
7. Never let a missing bible, broken outline, missing chapter, or unparseable critique proceed.

## Red-Flag Overrides

These override numeric averages from self-review:

| Red Flag | Action |
|---|---|
| Missing or unparseable structural artifact | `retry`, then `abort`. |
| No protagonist agency in outline or bible | `retry`. |
| No climax or no resolution | `retry`. |
| Persistent canon drift across chapters | `retry` affected chapters; paid/debug external review. |
| Chapter or section is summary-only prose | `retry`. |
| Severe truncation | `retry`. |
| Repeated section/chapter copied from earlier text | `retry`. |
| Critique has zero actionable issues under current prompt contract | `retry`. |
| Revision leaves high-severity issue unresolved | `retry`. |
| Final story/manuscript loses major plot, protagonist, ending, or chapters | `abort` after retry budget. |

## Implementation Notes

The gates should live close to pipeline orchestration but remain model-agnostic. A practical shape is:

```text
engine/gates.py
  GateResult
  Strictness
  run_story_expand_gate(...)
  run_story_outline_gate(...)
  run_story_draft_section_gate(...)
  run_story_polish_gate(...)
  run_novel_bible_gate(...)
  run_novel_chapter_gate(...)
  run_novel_critique_gate(...)
  run_novel_revision_gate(...)

engine/metrics.py
  word_count, sentence_stats, quote_ratio, repetition, crutch phrases,
  field coverage, chapter variance, entity/rule ledgers
```

Do not make LLM self-review responsible for basic format validation. The model can miss obvious parse failures; code should decide whether the artifact is structurally usable before spending tokens on review.

When a self-review returns `retry`, append a compact repair instruction to the next attempt:

```text
Previous attempt failed quality gate:
- Missing explicit climax and resolution.
- Section 4 was pure summary.

Regenerate the outline only. Keep the accepted premise. Fix the failures above.
```

For paid/debug external review, use a separate model or at least a separate backend configuration. Its job is not to rewrite; it returns a gate result and concise reasons.

