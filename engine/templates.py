"""
Prompt templates for each stage of the story generation pipeline.

Each template supports python .format(**kwargs) with keys:
  - prompt: user's raw input
  - genre: story genre
  - style: prose style
  - pov: point of view
  - max_words: target word count
"""

# ──────────────────────────────────────────────
# Shared anti-artifact / prose-quality guardrails
# ──────────────────────────────────────────────
# Injected into the drafting and polishing templates so short stories get the
# same anti-cliché discipline the NovelPipeline applies to chapter prose.
# Contains no ``{}`` placeholders, so it is safe to concatenate into templates
# that are later rendered with str.format(**kwargs).

PROSE_RULES = """PROSE GUARDRAILS (apply throughout — these matter as much as the plot):
- Vary sentence length and rhythm; never settle into a uniform cadence.
- Do NOT use AI crutch transitions: "however", "moreover", "furthermore", "in conclusion", "indeed", "it was then that".
- Avoid cliché and purple metaphor pile-ups (e.g. "tapestry", "testament to", "navigate the complexities", "delve").
- Do not lean on three-part anaphora (three consecutive sentences/clauses opening the same way).
- Keep dialogue spoken-sounding, not expository.
- Reuse no distinctive image, metaphor, or phrase more than once — fresh language each time."""


# ──────────────────────────────────────────────
# Stage 1: EXPAND
# Takes raw user input (fragment, idea, lyrics) → story premise
# ──────────────────────────────────────────────

EXPAND_TEMPLATE = """You are a master storyteller and creative writer. Your task is to take the user's raw input — which may be a fragment, a single idea, song lyrics, a mood, or anything — and expand it into a rich, compelling story premise.

User input: {prompt}
Target genre: {genre}
Prose style: {style}
Point of view: {pov}

Your response must follow this structure:

TITLE: [A compelling 2-6 word title for the story]

CHARACTERS:
- [Character name]: [1-2 sentence description of who they are, their role, their key trait or flaw]

SETTING: [2-3 sentences describing the world, time period, location, and atmosphere]

CONFLICT: [2-3 sentences describing the central struggle, what's at stake, and why it matters]

PREMISE: [250-400 words of narrative prose. Write this as the opening of the story would be written — in the specified style and POV. Introduce the world, the protagonist, and hint at the conflict. End with a hook that makes the reader want more. Do NOT summarize the plot — write actual prose.]

Write directly. Do not include meta-commentary or labels beyond those specified above."""

EXPAND_TEMPLATE_COMPACT = """You are a master storyteller. Expand the user's input into a story premise with characters, setting, and conflict.

User input: {prompt}
Genre: {genre}
Style: {style}
POV: {pov}

Return:
TITLE: [title]
CHARACTERS: [character descriptions]
SETTING: [setting description]
CONFLICT: [central conflict]
PREMISE: [250-400 words of actual narrative prose in the specified style and POV — not a summary, but the opening of the story itself]"""


# ──────────────────────────────────────────────
# Stage 2: OUTLINE
# Takes premise → structured story outline
# ──────────────────────────────────────────────

OUTLINE_TEMPLATE = """You are a professional story architect. Given the story premise below, create a structured outline that will guide the writing of a {max_words}-word story.

Genre: {genre}
Style: {style}
Point of view: {pov}

Story premise:
{premise}

IMPORTANT: This is a {max_words}-word story. Scale the number of sections accordingly:
- Under 1000 words: 4-6 sections
- 1000-3000 words: 6-12 sections
- 3000-5000 words: 10-18 sections
- 5000+ words: 15-25 sections

Each section should be roughly 200-400 words. Do the math: {max_words} words ÷ ~300 words per section = roughly {min_sections} sections minimum.

Create that many sections. Follow classic story structure:
1. First sections: OPENING — establish world, protagonist, inciting incident
2. Middle sections: RISING ACTION — complications, setbacks, revelations, subplots
3. Penultimate sections: CLIMAX — point of highest tension
4. Final sections: RESOLUTION — consequences, character change, closing image

For each section, provide:
- A title (2-5 words)
- A one-paragraph summary of what happens (3-5 sentences)
- The emotional arc of that section (what the reader should feel)
- Key plot points that MUST be included

Format your response as:

SECTIONS: [number]

SECTION 1: [title]
SUMMARY: [paragraph]
EMOTION: [emotional arc]
KEY POINTS: [bullet points]

SECTION 2: [title]
...

End with a TONE note describing the overall mood to maintain throughout."""

OUTLINE_TEMPLATE_COMPACT = """You are a story architect. Create a structured outline for a {max_words}-word {genre} story in {style} style, {pov} POV.

Premise:
{premise}

Scale sections to word count: under 1000→4-6, 1000-3000→6-12, 3000-5000→10-18, 5000+→15-25. Target: {min_sections}+ sections at ~300 words each. Follow classic structure (opening, rising action, climax, resolution). For each section provide: title, summary paragraph, emotional arc, and key plot points.

Format:
SECTIONS: [number]
SECTION N: [title]
SUMMARY: [paragraph]
EMOTION: [arc]
KEY POINTS: [bullets]
..."""


# ──────────────────────────────────────────────
# Stage 3: DRAFT (per-section)
# Takes section context + previous sections → drafted prose
# ──────────────────────────────────────────────

DRAFT_SECTION_TEMPLATE = """You are a talented {genre} writer. You are writing a {style} story in {pov} point of view. Write the following section of the story. Write vivid, engaging prose. Do NOT summarize — write the actual story text.

Overall story context:
Title: {title}
Genre: {genre}
Style: {style}
POV: {pov}

Full outline:
{full_outline}

Previous sections (already written):
{previous_text}

NOW WRITE: {section_title}
Section summary: {section_summary}
Emotional arc: {section_emotion}
Key points to include: {key_points}

CRITICAL LENGTH REQUIREMENT: You MUST write at least {section_words} words for this section. This is non-negotiable. If you write less, the story will be incomplete. Count your words after writing. Use rich description, dialogue, internal monologue, and sensory detail to reach the target. Do not pad — every word should advance the story.

""" + PROSE_RULES + """

Write this section now. Maintain consistent tone, character voices, and pacing with what came before. End with a natural transition or hook. Do not include section headers or meta-commentary — just the prose."""

DRAFT_SECTION_TEMPLATE_COMPACT = """Write the next section of a {genre} story in {style} style, {pov} POV.

Title: {title}
Full outline: {full_outline}
Previous sections: {previous_text}

Now write: {section_title}
Summary: {section_summary}
Emotion: {section_emotion}
Key points: {key_points}

""" + PROSE_RULES + """

Write around {section_words} words of actual prose. No headers. Just the story."""


# ──────────────────────────────────────────────
# Stage 4: POLISH
# Takes assembled draft → polished final story
# ──────────────────────────────────────────────

POLISH_TEMPLATE = """You are a meticulous story editor. Your task is to polish and refine the following story draft. Improve the prose quality while preserving the original story, characters, and plot.

Genre: {genre}
Style: {style}
Point of view: {pov}
Target length: ~{max_words} words

Things to improve:
- Sentence variety and rhythm
- Vivid sensory details and imagery
- Consistent character voice and tone
- Smooth transitions between sections
- Eliminate repetition and clunky phrasing
- Strengthen the opening hook and closing image
- Ensure the {style} style is consistent throughout

Do NOT:
- Change the plot or add new major plot points
- Add or remove characters
- Change the point of view
- Add section headers or commentary

""" + PROSE_RULES + """

Return the complete polished story. The story must flow as one continuous narrative.

Draft to polish:
{draft}"""

POLISH_TEMPLATE_COMPACT = """Polish this {genre} story draft. Improve prose quality, rhythm, imagery, and consistency. Maintain {style} style and {pov} POV. Target ~{max_words} words. Return the complete polished story as one continuous narrative.

Do not change the plot, characters, or POV.

""" + PROSE_RULES + """

Draft:
{draft}"""


# ──────────────────────────────────────────────
# Genre-specific tone guidance
# ──────────────────────────────────────────────

GENRE_GUIDANCE = {
    "fantasy": "Evoke wonder and magic. Use rich, sensory language. Build an immersive world with consistent rules. Themes of heroism, destiny, and the battle between light and dark.",
    "scifi": "Ground speculation in believable science. Explore the human impact of technology. Clean, precise prose with moments of cosmic awe. Themes of progress, identity, and what it means to be human.",
    "noir": "Hard-boiled, cynical, and atmospheric. Short, punchy sentences. Shadows, rain, and moral ambiguity. A world-weary protagonist navigating corruption. Use first-person or tight third-person.",
    "romance": "Focus on emotional interiority and chemistry between characters. Sensory details of touch, glance, and unspoken tension. Build toward emotional catharsis. Hopeful or bittersweet tone.",
    "horror": "Build dread slowly. Use sensory details to create unease — sounds, smells, things just out of sight. The horror should feel personal. Restraint is scarier than gore.",
    "literary": "Prioritize beautiful sentences and psychological depth. Subtext is as important as text. Experiment with structure and time. Character-driven with thematic resonance.",
    "comedy": "Timing is everything. Use contrast, surprise, and voice. Characters take themselves seriously while the world proves them wrong. Witty dialogue and situational humor.",
    "thriller": "Tension on every page. Short chapters, cliffhangers, high stakes. The protagonist is active and resourceful. Pacing is relentless. Twists should feel earned.",
    "mystery": "Plant clues carefully. The detective (professional or amateur) drives the investigation. Atmosphere matters. The solution should be surprising but inevitable in retrospect.",
    "adventure": "Forward momentum. Exotic locations, physical challenges, and daring escapes. The protagonist grows through action. Sense of discovery and wonder. Clear stakes and rewards.",
}

STYLE_GUIDANCE = {
    "descriptive": "Rich sensory details. Paint the world fully. Use metaphor and simile. Let scenes breathe. Prioritize immersion over pace.",
    "minimalist": "Every word must earn its place. Short sentences. Subtext over explanation. Let the reader fill gaps. Hemingway-esque economy.",
    "poetic": "Rhythm, imagery, and musicality of language. Metaphor and symbolism. Sentences that reward being read aloud. Lyrical without being purple.",
    "cinematic": "Visual and kinetic. Write as if describing a film. Strong visual compositions. Action that moves. Dialogue-driven scenes. Jump cuts and montage welcome.",
    "conversational": "As if the narrator is speaking directly to the reader. Natural, unpretentious voice. May break the fourth wall. Intimate and immediate.",
    "literary": "Prioritize craft and depth. Complex sentences, layered meaning. Psychological realism. Language as an end as well as a means.",
}

POV_GUIDANCE = {
    "first_person": "Use 'I' narration. The narrator is a character in the story with limited knowledge. Voice is paramount — every sentence should sound like this specific person speaking/thinking.",
    "third_person_limited": "Use 'he/she/they' narration. Stick close to one character's perspective per scene. The reader knows only what this character knows, sees, and feels.",
    "third_person_omniscient": "Use 'he/she/they' narration with full access to all characters' thoughts and feelings. Can reveal information no single character knows. Use a distinct narrative voice.",
    "second_person": "Use 'you' narration. The reader is the protagonist. Creates immediacy and immersion. Works well for horror, interactive-feeling stories, and literary experiments.",
}


def get_system_prompt(stage: str, genre: str = "", style: str = "", pov: str = "") -> str:
    """Build a system prompt for a given pipeline stage incorporating genre/style/POV guidance."""
    genre_note = GENRE_GUIDANCE.get(genre.lower(), "")
    style_note = STYLE_GUIDANCE.get(style.lower(), "")
    pov_note = POV_GUIDANCE.get(pov.lower(), "")

    guidance_parts = []
    if genre_note:
        guidance_parts.append(f"Genre guidance ({genre}): {genre_note}")
    if style_note:
        guidance_parts.append(f"Style guidance ({style}): {style_note}")
    if pov_note:
        guidance_parts.append(f"POV guidance ({pov}): {pov_note}")

    guidance_block = "\n\n".join(guidance_parts) if guidance_parts else ""

    stage_prompts = {
        "expand": f"""You are a master storyteller and creative writer. You help users develop story ideas into rich, compelling premises.

{guidance_block}

Always respond with the requested structure. Write actual narrative prose for the premise section — not a summary, but the opening of the story itself.""",

        "outline": f"""You are a professional story architect and developmental editor. You build structured outlines that guide powerful storytelling.

{guidance_block}

Create outlines with clear section breaks that follow classic story structure. Each section must advance the plot meaningfully.""",

        "draft": f"""You are a talented fiction writer specializing in {genre or 'various genres'}. You write vivid, engaging prose that brings stories to life.

{guidance_block}

Write actual story prose — never summarize. Maintain consistent character voices, tone, and pacing. Each section you write should feel like part of a unified whole.""",

        "polish": f"""You are a meticulous story editor with an ear for beautiful prose. You refine drafts into polished, publishable work.

{guidance_block}

Preserve the original story, characters, and plot. Improve the prose — sentence variety, sensory detail, rhythm, transitions. The story must flow as one continuous narrative.""",
    }

    return stage_prompts.get(stage, stage_prompts["expand"])


def get_stage_template(stage: str, compact: bool = False) -> str:
    """Get the prompt template for a given pipeline stage."""
    templates = {
        "expand": EXPAND_TEMPLATE_COMPACT if compact else EXPAND_TEMPLATE,
        "outline": OUTLINE_TEMPLATE_COMPACT if compact else OUTLINE_TEMPLATE,
        "draft": DRAFT_SECTION_TEMPLATE_COMPACT if compact else DRAFT_SECTION_TEMPLATE,
        "polish": POLISH_TEMPLATE_COMPACT if compact else POLISH_TEMPLATE,
    }
    return templates.get(stage, EXPAND_TEMPLATE)
