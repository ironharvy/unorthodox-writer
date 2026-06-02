# Engine Upgrade: Novel Mode

## Context
The Unorthodox Writer engine at /home/lameradze/projects/unorthodox-writer/engine/ currently has `StoryPipeline` — a 4-stage pipeline (expand → outline → draft → polish) that works well for short stories (<2000 words) but collapses for novel-length work because:
- No story bible / canon tracking
- All sections drafted in one pass, context degrades
- No editorial review step
- Single pass, no revision loop

We just proved a multi-agent process works: Claude generated a synopsis+bible, drafted chapters with rolling context, got critiqued by agy, revised, and scored 9.6/10.

## Goal
Build a **NovelPipeline** (or extend StoryPipeline) that supports paid-tier novel generation with these capabilities:

### 1. Story Bible (Phase 0)
Before any prose, generate a canonical blueprint via one LLM call:
- Full character sheets (names, traits, flaws, arcs, voice notes)
- Setting bible (locations, rules, atmosphere)
- Portal/magic system rules (must be ironclad, no contradictions)
- Chapter-by-chapter beat sheet (what happens in each chapter, emotional arc, word target)
- Output as structured JSON

### 2. Chapter-by-Chapter Generation (Phase 1)
For each chapter:
- Always include the full bible digest in context (it's small)
- Include a rolling synopsis of all prior chapters (compressed, never exceeds ~500 words)
- Include the verbatim last ~100 words of previous chapter (for voice/transition continuity)
- Generate with a "write exactly this chapter" prompt
- After each chapter, append a factual recap to the rolling synopsis

### 3. Auto-Critique (Phase 2)
After all chapters are drafted, run a structural review:
- Check for plot holes (contradictions between chapters)
- Check character consistency (voice, motivation, physical details)
- Check pacing (word count per chapter, does anything drag?)
- Check prose quality (AI artifacts, repeated phrases, clichés)
- Output a structured critique with specific line references

### 4. Revision Loop (Phase 3)
Based on the critique:
- Rewrite chapters that have issues
- Fix contradictions
- Polish weak prose
- Regenerate only the affected chapters, not the whole book
- Run a final assembly pass

## Technical Requirements
- Lives in /home/lameradze/projects/unorthodox-writer/engine/novel.py
- Reuses existing backends (OllamaBackend, CloudBackend with deepseek)
- Async streaming — yield progress events so the frontend can show status
- Works with the existing backend routes (just wire it in for paid tier)
- Bible should be a Python dataclass, serializable to JSON
- Rolling synopsis should be a compact string, never growing beyond ~500 words
- Use deepseek-chat via the OpenAI client (base_url https://api.deepseek.com/v1, key in DEEPSEEK_API_KEY env var)

## API Design
```python
class NovelPipeline:
    def __init__(self, backend, max_chapters: int = 15, target_words: int = 20000):
        ...
    
    async def generate(self, prompt, genre, style, pov) -> AsyncIterator[dict]:
        # Yields: {"type": "progress", "phase": "bible|drafting|critique|revising", ...}
        #         {"type": "chunk", "chapter": N, "text": "..."}
        #         {"type": "chapter_complete", "chapter": N, "word_count": ...}
        #         {"type": "critique", "issues": [...]}
        #         {"type": "revision", "chapter": N, "fixed": "..."}
        #         {"type": "complete", "title": "...", "full_text": "...", ...}
```

## Integration
After building novel.py, wire it into /home/lameradze/projects/unorthodox-writer/backend/routes/stories.py so that:
- Free tier: uses existing StoryPipeline (short story mode)
- Paid tier with max_words > 2000: uses NovelPipeline
- Both stream SSE events to the frontend

## Success Criteria
1. Generate a complete novel (8+ chapters, 15K+ words) with coherent plot
2. Bible captures all canon — no contradictions in the final text
3. Critique pass finds at least 3 real issues
4. Revision pass fixes them
5. Final output is clean, no AI artifacts
6. Existing short story pipeline still works unchanged
