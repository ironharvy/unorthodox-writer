# Novel Generation Task

## Goal
Generate a complete, polished short novel (5-10 chapters, ~1000 words each = 5000-10000 words total) using the provided story engine. Then evaluate it rigorously and fix all issues.

## Premise
"A lighthouse keeper discovers the light is actually a portal to another world"

## Technical Context
- The engine lives at: /home/lameradze/projects/unorthodox-writer/engine/
- DeepSeek API is available via OpenAI-compatible client:
  - base_url: https://api.deepseek.com/v1
  - model: deepseek-chat
  - key is in env: DEEPSEEK_API_KEY
- The engine's pipeline.py has StoryPipeline with a 4-stage process: expand → outline → draft → polish
- But for novel-length, you'll likely want to generate chapter-by-chapter with a synopsis-first approach

## Phase 1: Architecture Decision
Read the existing engine/pipeline.py and engine/backends/cloud.py. Decide the best approach for novel-length generation:
- Option A: Modify the pipeline to support multi-chapter output with a chapter planner stage
- Option B: Write a novel orchestrator script that calls the pipeline per-chapter with shared context
- Option C: Write a standalone novel generator using direct API calls with a synopsis-driven approach

Pick the approach that will produce the most coherent long-form story.

## Phase 2: Generate the Novel
Generate all chapters. Each chapter should:
- Be ~800-1200 words
- Advance the plot meaningfully
- End with a hook or transition
- Maintain consistent character voice, setting details, and tone
- Be numbered and titled

## Phase 3: Comprehensive Evaluation
After generating, evaluate the ENTIRE novel on these dimensions:

### Plot & Structure
- Does each chapter advance the story? Any filler chapters?
- Is there a clear beginning, rising action, climax, and resolution?
- Are there plot holes or contradictions between chapters?
- Does the pacing work — any chapters that drag or rush?

### Characters
- Are characters consistent in voice, motivation, and behavior?
- Does the protagonist have a clear arc?
- Are secondary characters distinct or interchangeable?
- Do character decisions make sense given their established traits?

### Prose & Style
- Any clichés, purple prose, or weak sentences?
- Consistent tense and POV throughout?
- Varied sentence structure or repetitive patterns?
- Any AI artifacts (overuse of "however", "moreover", "it was then that", etc.)?
- Dialogue that sounds natural vs. stilted?

### Worldbuilding & Consistency
- Setting details consistent across chapters?
- Any unexplained elements that need resolution?
- Internal logic holds up?

### Emotional Impact
- Does the story evoke genuine feeling?
- Are the stakes clear and escalating?
- Satisfying ending?

## Phase 4: Fix Everything
Based on the evaluation, rewrite/revise the novel to fix ALL identified issues. Be ruthless. Cut weak chapters entirely if needed. Rewrite inconsistent sections. Polish prose.

## Phase 5: Final Polish
- Remove all AI artifacts and telltale patterns
- Ensure every chapter earns its place
- Read the whole thing end-to-end and fix any remaining flow issues
- Add chapter titles that intrigue

## Output
Save the final novel to: /home/lameradze/projects/unorthodox-writer/novel.md

Format as:
```
# [Novel Title]

## Chapter 1: [Title]
[chapter text]

## Chapter 2: [Title]
[chapter text]
...
```

Also save a separate evaluation report to: /home/lameradze/projects/unorthodox-writer/evaluation.md

## Constraints
- Use deepseek-chat via the OpenAI client with base_url https://api.deepseek.com/v1
- Key is DEEPSEEK_API_KEY from env
- Be patient with API calls — DeepSeek can be slower than OpenAI
- Output the final novel as clean markdown
- Do NOT include meta-commentary in the novel file — it should read as a finished book
