# Guide to Evaluating AI-Generated Manuscripts

This guide defines a practical evaluation framework for AI-generated fiction manuscripts. It is designed for two uses:

1. Human editorial review: structured assessment of story quality, craft, originality, and reader impact.
2. Automated metrics: computable signals that can flag likely weaknesses for `engine/metrics.py`.

The framework uses a 1-5 scale throughout. A score of 3 means "publishable draft quality with visible revision needs," not "average AI output." Scores should be assigned after reading the entire manuscript, with automated reports used as evidence rather than final judgment.

## Core Scoring Scale

| Score | Anchor |
|---:|---|
| 1 | Broken or absent. The issue repeatedly prevents comprehension, credibility, or reader investment. |
| 2 | Weak. The element exists but is inconsistent, mechanical, thin, or frequently contradicted. |
| 3 | Functional. The element works in the main line of the story but has notable gaps, unevenness, or generic execution. |
| 4 | Strong. The element is clear, controlled, and mostly effective, with only local revision needs. |
| 5 | Excellent. The element is integrated, specific, emotionally effective, and resilient under close reading. |

## Evaluation Procedure

1. Read the manuscript once without scoring. Mark confusion, boredom, surprise, emotional response, and questions.
2. Build a story ledger: chapters/scenes, POV, location, timeline, named characters, stated facts, promises/setups, and unresolved threads.
3. Run automated text metrics: word counts, sentence lengths, repetition, lexical diversity, dialogue ratios, passive constructions, named-entity consistency, and chapter-level variance.
4. Score each criterion using both the human reading and automated flags.
5. Reconcile: a machine flag lowers a score only when the editor confirms that it damages the reader experience.

## 1. Plot & Structure

| Criterion | Definition | Why It Matters | Human Review Checklist | Automatable Signals | 1-5 Rubric |
|---|---|---|---|---|---|
| Narrative arc completeness | The manuscript contains a legible setup, rising complications, climax, and resolution or deliberately unresolved ending. | Readers need orientation, escalation, consequence, and closure. A missing arc makes the manuscript feel like generated scenes rather than a story. | Identify inciting incident, major turning points, climax, and final state. Confirm the protagonist's external and internal problems are introduced and changed by the end. | Chapter-level event extraction; sentiment/tension curve; position of inciting incident and climax; unresolved named plot goals near ending. | 1 = no coherent arc; 2 = partial sequence with missing climax or resolution; 3 = complete but flat or formulaic; 4 = clear, escalating, satisfying; 5 = arc feels inevitable yet surprising. |
| Plot hole detection | Contradictions between chapters, scenes, facts, timelines, abilities, relationships, or stated constraints. | Contradictions break trust and force readers to repair the story mentally. AI drafts often forget earlier canon. | Maintain a contradiction log. Check dates, ages, distances, injuries, abilities, rules, relationships, object locations, and revealed secrets. | Entity-state tracking; timeline extraction; contradiction detection using NLI; repeated fact triples with conflicting values; impossible travel/time gaps. | 1 = major contradictions drive the plot; 2 = frequent contradictions; 3 = several local contradictions but main plot survives; 4 = rare minor issues; 5 = internally coherent under close audit. |
| Cause-and-effect chain integrity | Events arise logically from prior actions, constraints, choices, and consequences. | Plot feels meaningful when actions cause outcomes. Weak causality makes events feel arbitrary or prompt-driven. | For each major scene, ask: What caused this? What changed? What new pressure follows? Remove scenes that do not alter stakes, knowledge, relationships, or options. | Scene dependency graph; high rate of scenes without state changes; sudden goal changes; conjunction patterns like "suddenly" or "then" replacing causal connectors. | 1 = events are random; 2 = weak or missing causal links; 3 = main chain works with conveniences; 4 = most turns are motivated; 5 = every major event is earned by prior setup. |
| Pacing balance | The distribution of narrative time, chapter/scene length, action, reflection, exposition, and emotional beats. | Readers disengage when scenes drag, rush, or flatten into the same rhythm. | Mark scenes as action, dialogue, exposition, reflection, transition, or climax. Check whether major emotional moments get enough space and low-stakes sections overstay. | Chapter and scene word-count variance; dialogue/exposition ratios; average sentence length by chapter; event density; tension curve; long summary blocks. | 1 = unreadably stalled or rushed; 2 = persistent imbalance; 3 = serviceable but uneven; 4 = controlled variation; 5 = rhythm amplifies suspense, emotion, and genre expectations. |
| Foreshadowing and payoff | Meaningful setups, clues, promises, motifs, and questions are resolved, transformed, or intentionally left open. | Payoff creates satisfaction and makes the story feel designed rather than improvised. | Track promises: mysteries, prophecies, objects, vows, fears, skills, motifs, and relationship tensions. Confirm each has payoff, complication, or explicit deferral. | Setups mentioned early but absent later; repeated motif terms without late recurrence; named objects with low final-third presence; unresolved question marks or goals. | 1 = setups vanish; 2 = many dangling threads; 3 = main promises resolve but side promises drift; 4 = most setups pay off cleanly; 5 = payoffs recontextualize earlier material. |
| Subplot integration | Side plots support, complicate, mirror, or pressure the main story rather than distracting from it. | Subplots add depth only when they affect stakes, theme, character, or final outcome. | For each subplot, define its function: mirror theme, reveal character, create obstacle, supply resource, or alter ending. Cut or merge unsupported side threads. | Subplot character/keyword clusters disconnected from main conflict; low reappearance after introduction; scenes whose named entities never affect climax. | 1 = side plots derail the manuscript; 2 = mostly decorative; 3 = some useful links; 4 = integrated into character/theme/plot; 5 = subplots deepen and sharpen the central arc. |

## 2. Characters

| Criterion | Definition | Why It Matters | Human Review Checklist | Automatable Signals | 1-5 Rubric |
|---|---|---|---|---|---|
| Consistency of voice | Each major character has stable diction, rhythm, priorities, silence patterns, humor, and emotional register. | Distinct voice lets readers believe characters exist beyond plot function. | Read dialogue without tags. Note vocabulary, sentence length, formality, recurring concerns, and subtext per character. Check for unexplained voice shifts. | Speaker-level lexical profiles; average sentence length per speaker; function-word distribution; embedding similarity between speakers; stylometric drift. | 1 = interchangeable voices; 2 = occasional distinct lines; 3 = main characters partly distinct; 4 = consistent major voices; 5 = characters are recognizable by dialogue alone. |
| Background adherence | Characters act in ways consistent with established history, skills, trauma, culture, values, and knowledge. | Readers need behavior to feel psychologically and socially grounded. | Build a character bible. For each major action, ask whether the character knows enough, cares enough, and is capable enough to do it. | Character fact ledger; skill/knowledge contradictions; sudden expertise; entity-state changes not introduced; emotion/action mismatch flags. | 1 = characters ignore their own histories; 2 = frequent convenience behavior; 3 = plausible with gaps; 4 = actions mostly fit background; 5 = history actively shapes choices. |
| Arc progression | Characters change meaningfully through pressure, choice, failure, insight, or cost. | Change gives the story emotional movement. Static characters can work only when deliberately designed. | Identify starting belief, desire, flaw, wound, test, reversal, final choice, and final self-understanding. Confirm growth is earned by scenes, not declared. | Sentiment and goal trajectory; repeated self-descriptions; late-stage belief statements; scene-level decisions by protagonist; arc milestone detection. | 1 = no arc or false arc; 2 = change is asserted; 3 = visible but underdeveloped; 4 = earned progression; 5 = change is specific, costly, and dramatically embodied. |
| Motivation clarity | The reader understands why characters pursue goals, avoid truths, make choices, and change tactics. | Motivation converts action into drama. Without it, readers see motion but not meaning. | At each major choice, write the character's goal, fear, pressure, and alternative. If this cannot be inferred from the text, motivation is unclear. | Goal verbs near character names; desire/fear statements; abrupt action changes; scenes with actions but no prior motive cues. | 1 = motives absent; 2 = motives generic or contradictory; 3 = understandable in main plot; 4 = clear and layered; 5 = motives create tension between desire, fear, and value. |
| Agency | Characters make consequential choices that alter the plot, rather than being moved by coincidence, exposition, or external rescue. | Agency creates investment because readers track decisions and consequences. | List major plot turns and who causes them. Confirm the protagonist makes decisions that cannot be removed without changing the story. | Ratio of protagonist-caused turning points; passive constructions around protagonist; deus-ex-machina markers; high coincidence terms. | 1 = plot happens to characters; 2 = agency is rare; 3 = protagonist drives some turns; 4 = choices shape most outcomes; 5 = climax depends on character's earned decision. |
| Distinctiveness | Characters are separable in role, desire, worldview, voice, and relationship to the central conflict. | A crowded cast becomes tiring when characters blur together. | Create one-sentence contrast statements for each major character. Test whether removing or merging a character changes plot, theme, or emotional texture. | Dialogue classification accuracy by speaker; overlapping vocabulary/traits; low unique scene functions; similar named-entity co-occurrence networks. | 1 = characters are functionally identical; 2 = many could be merged; 3 = leads are distinct, side cast blurs; 4 = clear cast differentiation; 5 = each major character has unique dramatic pressure. |

## 3. Worldbuilding & Setting

| Criterion | Definition | Why It Matters | Human Review Checklist | Automatable Signals | 1-5 Rubric |
|---|---|---|---|---|---|
| Rule consistency | Magic, technology, politics, economics, social norms, geography, and genre rules remain stable unless explicitly changed. | Rules create stakes. If rules bend for convenience, suspense collapses. | Write all explicit rules and implied constraints. Check every violation for setup, cost, exception, or explanation. | Rule statement extraction; contradiction detection; inconsistent ability outcomes; term drift; unexplained exceptions near climax. | 1 = rules change constantly; 2 = rules bend for plot; 3 = core rules hold with exceptions; 4 = stable and consequential; 5 = rules generate conflict and payoff. |
| Sensory grounding | Settings use specific, varied sensory details: sight, sound, smell, touch, taste, temperature, spatial relation, and motion. | Concrete detail helps readers inhabit scenes and distinguish locations. | Highlight sensory details per scene. Check whether each location has at least two specific, non-generic details and whether details affect action or mood. | Sensory lexicon counts by scene; adjective specificity; concrete noun ratio; location description length; repeated generic descriptors. | 1 = abstract or blank settings; 2 = generic visual description; 3 = adequate but repetitive; 4 = varied, concrete grounding; 5 = sensory detail shapes mood, action, and memory. |
| Economy of exposition | Worldbuilding is delivered through action, conflict, dialogue subtext, objects, and consequences rather than long explanation. | Info-dumps slow narrative and make the world feel like a database. | Mark exposition blocks over 150 words. Ask whether the same information could be dramatized through choice, obstacle, ritual, cost, or conflict. | Long paragraphs with low action/dialogue density; high proper-noun density; encyclopedia-style syntax; "as you know" dialogue; exposition-to-scene ratio. | 1 = frequent info-dumps halt story; 2 = heavy explanation; 3 = mixed showing and telling; 4 = mostly embedded in scenes; 5 = world knowledge arrives exactly when needed through drama. |
| Setting as character | The world actively shapes available choices, conflicts, values, risks, and outcomes. | Strong settings do more than decorate; they create story logic. | For each major setting, identify what it prevents, enables, tempts, reveals, or costs. Replace location hypothetically; if nothing changes, setting is weak. | Location-event dependency; scene outcomes tied to setting terms; environmental constraints near decisions; low interchangeable-room descriptions. | 1 = backdrop only; 2 = occasional atmosphere; 3 = setting affects some scenes; 4 = setting shapes plot and character; 5 = story could not happen the same way elsewhere. |

## 4. Prose & Style

| Criterion | Definition | Why It Matters | Human Review Checklist | Automatable Signals | 1-5 Rubric |
|---|---|---|---|---|---|
| AI artifact detection | Recurrent patterns associated with generic AI prose: crutch phrases, balanced triplets, abstract summaries, over-neat transitions, cliché metaphors, and inflated emotional labeling. | These artifacts make prose feel synthetic, predictable, and emotionally unearned. | Flag repeated rhetorical shapes: "not just X, but Y," three-item anaphora, "as if the world held its breath," "a testament to," "in that moment," and summary morals. Confirm whether they feel intentional or stale. | Crutch phrase list; n-gram repetition; cliché lexicon; paragraph template detection; repeated sentence openings; semantic similarity between emotional beats. | 1 = pervasive synthetic texture; 2 = frequent distracting artifacts; 3 = noticeable but revisable; 4 = mostly natural prose; 5 = style feels authored, specific, and controlled. |
| Sentence variety | Distribution of sentence length, syntax, rhythm, openings, punctuation, and paragraph structure. | Variation controls energy, clarity, and emphasis. Monotony produces fatigue. | Read a page aloud. Mark repeated openings, same-length sentences, overbalanced clauses, and lack of short emphasis lines after long passages. | Sentence length mean/variance; parse-tree diversity; repeated POS patterns; sentence opening entropy; punctuation distribution. | 1 = monotonous or chaotic; 2 = limited variation; 3 = adequate rhythm with patterns; 4 = varied and readable; 5 = sentence rhythm supports scene emotion and genre. |
| Dialogue naturalness | Dialogue sounds like purposeful speech between people, not exposition, summary, or author explanation. | Readers believe relationships through speech, evasion, interruption, subtext, and conflict. | Check whether characters say what they already know, explain world rules unnaturally, or state feelings too directly. Look for interruption, implication, tension, and silence. | Dialogue-to-narration ratio; exposition terms inside quotes; long monologues; question/answer chains; speaker turn length; "as you know" patterns. | 1 = dialogue is exposition delivery; 2 = stiff and overexplicit; 3 = functional but plain; 4 = natural with subtext; 5 = dialogue reveals character, conflict, and hidden pressure. |
| Show vs. tell ratio | Balance between dramatized action/sensation/behavior and summarized emotion/events/backstory. | Telling can move quickly, but overuse prevents readers from experiencing the story. | Highlight direct emotion labels and summary passages. For key scenes, confirm feelings are visible through action, image, decision, and consequence. | Emotion adjective density; summary verbs; scene/action verb ratio; sensory and concrete noun counts; paragraph spans without dialogue/action. | 1 = mostly summary; 2 = key emotions told; 3 = mixed; 4 = important moments dramatized; 5 = narration selects telling strategically while scenes carry emotion. |
| Tonal consistency | Voice, mood, intensity, diction, humor, and genre expectations remain controlled across the manuscript. | Unmotivated tonal shifts break immersion and confuse reader expectations. | Mark tone per scene. Check whether comedy, melodrama, horror, lyricism, or irony enters at appropriate moments and from compatible POVs. | Sentiment variance; genre-keyword drift; formality shifts; sudden profanity/register changes; stylistic embedding drift by chapter. | 1 = tone is incoherent; 2 = frequent accidental shifts; 3 = mostly stable with rough patches; 4 = controlled shifts; 5 = tone evolves deliberately with stakes and POV. |
| Lexical range | Breadth, specificity, and precision of vocabulary without needless thesaurus inflation or repetition. | Word choice shapes texture, clarity, and memorability. Repetition can feel mechanical unless purposeful. | Track repeated descriptors, generic nouns, and vague intensifiers. Check whether key images use precise language suited to character and genre. | Type-token ratio; MTLD; HD-D; word frequency bands; repeated lemma counts; adjective/noun specificity; rare-word misuse flags. | 1 = repetitive, vague, or inflated; 2 = limited range; 3 = adequate but generic; 4 = precise and varied; 5 = vocabulary is distinctive, economical, and character-aware. |

## 5. Thematic Depth

| Criterion | Definition | Why It Matters | Human Review Checklist | Automatable Signals | 1-5 Rubric |
|---|---|---|---|---|---|
| Thematic coherence | The story explores a central idea, question, tension, or value conflict through plot, character, image, and consequence. | Theme gives events cumulative meaning beyond "things happened." | State the manuscript's central question in one sentence. Check whether major scenes pressure that question rather than merely mention it. | Keyword/motif clusters; semantic recurrence across beginning/middle/end; theme-related terms tied to major turning points; topic drift. | 1 = no discernible theme; 2 = theme is stated but unsupported; 3 = theme appears intermittently; 4 = coherent exploration; 5 = theme emerges through choices and consequences. |
| Subtext and symbolism | Meaning exists beneath literal action through implication, image systems, motifs, objects, silences, and contrast. | Subtext rewards rereading and lets readers infer rather than receive lectures. | Identify recurring objects/images and what they change to mean. Check whether scenes contain unsaid stakes or only explicit statements. | Motif recurrence; symbolic object tracking; dialogue subtext proxies such as indirect answers; repeated image networks; low direct-theme statement ratio. | 1 = only surface meaning; 2 = obvious or accidental symbolism; 3 = some meaningful motifs; 4 = layered subtext; 5 = symbols and silences deepen without overexplaining. |
| Moral complexity | Conflicts involve competing values, costs, partial truths, and believable opposition rather than simple virtue versus stupidity or evil. | Complexity increases credibility and emotional engagement. | Give every major side its strongest argument. Check whether antagonists have understandable goals and whether protagonists face real tradeoffs. | Sentiment imbalance by faction; antagonist motive depth; moralizing phrase density; binary evaluative language; distribution of costs across choices. | 1 = simplistic moral binary; 2 = thin opposition; 3 = some nuance; 4 = credible competing values; 5 = conflict remains emotionally and ethically alive after resolution. |
| Emotional resonance | Key moments produce felt response through preparation, specificity, consequence, and restraint. | Readers remember what they feel. AI drafts often label emotion without earning it. | Mark intended emotional peaks. Check setup, stakes, embodied reaction, cost, aftermath, and whether the scene trusts the reader. | Sentiment peaks aligned with plot peaks; emotion word density; sensory/action support around emotion; aftermath scene presence; beta-reader response tags. | 1 = emotionally inert or manipulative; 2 = feelings asserted; 3 = some effective moments; 4 = strong earned response; 5 = emotional beats are specific, surprising, and lasting. |

## 6. Technical Quality: AI-Specific

| Criterion | Definition | Why It Matters | Human Review Checklist | Automatable Signals | 1-5 Rubric |
|---|---|---|---|---|---|
| Repetition detection | Exact or near-exact reuse of phrases, sentence shapes, paragraphs, emotional beats, descriptions, or scene functions. | Repetition makes AI-generated text feel padded and reduces novelty. | Track repeated phrases and scene summaries. Decide whether repetition is intentional motif, useful callback, or accidental recycling. | N-gram frequency; fuzzy paragraph similarity; embedding similarity; repeated sentence openings; duplicate dialogue beats; compression ratio. | 1 = extensive recycling; 2 = frequent distracting repetition; 3 = noticeable but fixable; 4 = minor non-damaging repetition; 5 = repetition is purposeful or absent. |
| Hallucination/canon drift | Established facts change later without explanation: names, ages, locations, rules, relationships, timeline, objects, injuries, or backstory. | Canon drift is one of the clearest signs that a generated manuscript lacks durable memory. | Maintain a canon ledger. Audit all late references to early facts and all climactic uses of rules, objects, and relationships. | Entity-state database; coreference resolution; NLI contradiction checks; named-entity aliases; timeline consistency; object possession tracking. | 1 = core canon unstable; 2 = many factual drifts; 3 = several local drifts; 4 = rare minor drift; 5 = stable internal canon. |
| Template patterns | Paragraphs repeatedly follow predictable AI structures: abstract topic sentence, balanced elaboration, emotional summary, neat closing reflection. | Template prose flattens voice and makes chapters feel algorithmic. | Mark paragraph roles and shapes. Look for repeated reflective endings, symmetrical phrasing, and scenes that close with generalized insight. | Paragraph-shape clustering; repeated discourse markers; sentence count per paragraph; rhetorical template regexes; semantic role sequence similarity. | 1 = manuscript reads template-generated; 2 = frequent patterned paragraphs; 3 = visible but not constant; 4 = mostly organic structure; 5 = form varies with scene need and POV. |
| Dialogue attribution balance | Effective mix of clear tags, action beats, silence, and untagged exchanges without overusing said-isms or confusing bare quotes. | Attribution controls clarity and pace. Overdone tags distract; underdone tags confuse. | In dialogue-heavy scenes, verify speaker clarity every 3-5 exchanges. Check whether action beats reveal character rather than replace emotion labels. | Tag frequency; non-"said" tag ratio; action beat ratio; unattributed quote runs; adverbial tag count; speaker ambiguity. | 1 = confusing or intrusive attribution; 2 = frequent said-ism/adverb clutter or bare quote confusion; 3 = clear but mechanical; 4 = balanced; 5 = attribution is invisible, rhythmic, and character-revealing. |
| Passive voice overuse | Excessive constructions where subjects receive actions, especially when they obscure agency or weaken immediacy. | Passive voice is not always wrong, but overuse can drain urgency and hide responsibility. | Review passive constructions in action, conflict, and revelation scenes. Keep passive where focus on the acted-upon subject is intentional. | Passive dependency patterns; "was/were + past participle"; passive rate per 1,000 words; passive concentration in action scenes. | 1 = passive voice repeatedly obscures action; 2 = frequent weakening; 3 = moderate and sometimes useful; 4 = mostly active with intentional passive; 5 = voice choice is precise and scene-aware. |

## Human-Only, Automated, and Hybrid Criteria

### Human-Only

These require literary, psychological, or reader-response judgment. Automation can provide notes but should not assign final scores.

| Criterion | Reason |
|---|---|
| Emotional resonance | Requires felt response, context, taste, and genre expectation. |
| Moral complexity | Requires judgment about values, tradeoffs, and credibility. |
| Subtext and symbolism | Machines can detect recurrence but not reliably interpret meaning. |
| Arc progression | Tools can identify change language, but "earned growth" is editorial judgment. |
| Agency | Automation can count causal turns, but meaningful agency depends on interpretation. |
| Setting as character | Requires deciding whether setting materially shapes the story. |

### Automatable

These can be computed directly from text. Human review should still interpret whether the metric matters.

| Criterion | Useful Metrics |
|---|---|
| Chapter/scene length variance | Word counts, coefficient of variation, outlier chapters, scene density. |
| Sentence variety | Sentence length distribution, parse-tree diversity, repeated openings, punctuation distribution. |
| Lexical range | TTR, MTLD, HD-D, lemma repetition, word frequency bands. |
| Exact repetition | N-grams, duplicate sentences, fuzzy paragraph similarity, compression ratio. |
| Dialogue attribution balance | Tag counts, attribution verbs, adverbial tags, unattributed quote runs. |
| Passive voice rate | Dependency parses, passive auxiliary patterns, passive percentage by chapter. |

### Hybrid

These are best handled by machine flags followed by human confirmation.

| Criterion | Machine Role | Human Role |
|---|---|---|
| Plot holes | Flag contradictions, timeline issues, and entity-state conflicts. | Decide whether contradiction is real, intentional, or explained. |
| Cause-and-effect chain | Build scene dependency and goal-state graphs. | Judge whether causality feels dramatically earned. |
| Foreshadowing/payoff | Track setups, motifs, objects, and unresolved questions. | Decide whether payoff is satisfying or intentionally open. |
| Character voice | Measure stylometric separation by speaker. | Judge whether differences are meaningful and in character. |
| Background adherence | Track stated traits, knowledge, and skills. | Decide whether deviations are growth, stress response, or error. |
| Rule consistency | Extract and compare world rules. | Judge whether exceptions are justified. |
| AI artifacts/template patterns | Flag cliché phrases and repeated rhetorical shapes. | Decide whether prose feels artificial or stylistically deliberate. |
| Show vs. tell | Count emotion labels, summary blocks, sensory/action density. | Judge whether telling is efficient or flattening. |

## Recommended Overall Quality Formula

Use weighted dimension scores. Each dimension score is the mean of its criteria unless the editorial team chooses to mark a criterion "not applicable" for a specific genre or form.

| Dimension | Weight | Rationale |
|---|---:|---|
| Plot & Structure | 22% | Structural failure damages the whole reading experience and is costly to repair late. |
| Characters | 22% | Character credibility and agency drive reader investment across genres. |
| Worldbuilding & Setting | 12% | Important for all fiction, especially speculative, historical, and place-driven work. |
| Prose & Style | 18% | Style determines readability, voice, and perceived authorship. |
| Thematic Depth | 14% | Theme and emotional meaning separate a functional draft from a resonant manuscript. |
| Technical AI-Specific Quality | 12% | AI artifacts, repetition, and canon drift are high-signal revision risks. |

Overall score:

```text
overall = 0.22 * plot_structure
        + 0.22 * characters
        + 0.12 * worldbuilding_setting
        + 0.18 * prose_style
        + 0.14 * thematic_depth
        + 0.12 * technical_ai_quality
```

Suggested interpretation:

| Overall Score | Interpretation |
|---:|---|
| 1.0-1.9 | Not developmentally coherent. Requires full reconception or regeneration. |
| 2.0-2.6 | Major developmental edit required. The manuscript has recoverable pieces but weak continuity, agency, or prose control. |
| 2.7-3.3 | Functional draft. Suitable for structured revision with targeted plot, character, and prose passes. |
| 3.4-4.1 | Strong draft. Needs editorial refinement, continuity audit, and line-level polish. |
| 4.2-5.0 | High-quality manuscript. Ready for advanced editorial review, beta testing, or submission-focused revision. |

## Red-Flag Overrides

Some failures should override a decent numerical average:

| Red Flag | Recommended Action |
|---|---|
| Major unresolved plot contradiction in climax | Cap overall score at 3.0 until fixed. |
| Protagonist has no meaningful agency | Cap Plot & Structure and Characters at 3.0. |
| Persistent canon drift | Cap Technical AI-Specific Quality at 2.5. |
| Extensive paragraph-level recycling | Cap Prose & Style and Technical AI-Specific Quality at 2.5. |
| Dialogue voices are indistinguishable across all major characters | Cap Characters at 3.0. |
| Emotional climax is summarized rather than dramatized | Cap Thematic Depth at 3.5 unless genre intentionally avoids emotional immersion. |

## Measurement Notes for `engine/metrics.py`

The automated metrics engine should produce flags, not final literary judgments. Recommended output fields:

| Metric Family | Example Outputs |
|---|---|
| Structure | chapter word counts, scene count, chapter variance, possible climax position, unresolved named goals. |
| Continuity | entity-state table, timeline table, contradictions, aliases, object possession changes. |
| Causality | scene goals, scene outcomes, dependency edges, state-change count per scene. |
| Character | speaker profiles, dialogue distinctiveness, protagonist action ratio, motivation markers. |
| Worldbuilding | rule statements, rule exceptions, exposition density, sensory density by scene. |
| Style | sentence length stats, parse-pattern diversity, repeated openings, cliché/crutch phrase counts. |
| AI artifacts | paragraph-shape clusters, n-gram repetition, semantic duplicate passages, template phrase hits. |
| Dialogue | quote ratio, tag ratio, attribution verbs, action beats, unattributed runs. |
| Readability | Flesch-Kincaid, Gunning Fog, average sentence length, syntactic complexity, lexical diversity. |

For each flag, include:

```text
criterion
severity: low | medium | high
location: chapter/scene/paragraph
evidence: short excerpt or metric value
recommendation: what a human editor should inspect
```

## Research and Framework References

This guide synthesizes established fiction-editing practice with computable text-quality research:

- Literary craft and criticism: common narrative-rubric standards emphasize exposition/setup, rising action, climax, resolution, character development, setting, sensory detail, theme, point of view, organization, and language control. These align with school and workshop narrative rubrics such as the Narrative Writing Rubric's focus on narrative arc and sensory development, and The Flame Literary Journal rubric's emphasis on emotion, imagery, symbolism, theme, sentence construction, and revision evidence.
- NaNoWriMo revision practice: NaNoWriMo-adjacent revision advice often begins with reading the full manuscript, identifying pacing problems, inconsistencies, and overly rough draft sections before line editing. This supports whole-manuscript continuity and pacing passes before prose polish.
- Clarkesworld/Neil Clarke editorial context: Clarkesworld's widely reported flood of AI-generated submissions in 2023 is a useful editorial warning: fluent AI text can overwhelm submission systems while still failing publication-level standards. For this framework, the practical lesson is to evaluate AI manuscripts on story coherence, originality, prose specificity, and continuity rather than relying on surface fluency.
- NLP and text-quality research: automated readability and linguistic-quality assessment commonly uses lexical diversity, syntactic complexity, sentence length, readability formulas, parse features, cohesion, and repetition measures. Relevant metrics include TTR, MTLD, HD-D, Flesch-Kincaid, Gunning Fog, dependency-based passive detection, syntactic diversity, n-gram repetition, and semantic similarity.

Useful source links:

- Narrative arc and sensory-detail rubric example: https://d21royfkw9g4l6.cloudfront.net/Narrative_Writing_Rubric_G5_WAYHPB.pdf
- Literary scene rubric emphasizing emotion, symbolism, imagery, sentence construction, and revision: https://websterenglish.weebly.com/uploads/8/6/3/2/8632131/narrative_scene_rubric.pdf
- Literary review criteria including cause-and-effect sequence, plot holes, setting, theme, and style: https://franjo.us/literary-review-criteria/
- NaNoWriMo revision advice on whole-manuscript rereading, pacing, and inconsistencies: https://www.wow-womenonwriting.com/48-How2-ReviseAfterNaNoWriMo.html
- Clarkesworld AI-submission context: https://techcrunch.com/2023/02/21/clarkesworld-ai-generated-submissions/
- Clarkesworld/Clarke Award context: https://www.clarkeaward.com/
- Lexical diversity, syntactic complexity, and readability research on ChatGPT text: https://www.frontiersin.org/articles/10.3389/feduc.2025.1616935/full
- IBM research on statistical readability assessment and lexical-spread features: https://research.ibm.com/publications/statistical-measures-for-readability-assessment
- Readability features including lexical, syntactic, and discourse measures: https://pmc.ncbi.nlm.nih.gov/articles/PMC5644354/
- Passive voice and sentence complexity as readability factors: https://pmc.ncbi.nlm.nih.gov/articles/PMC1560876/

