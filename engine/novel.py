"""
Novel-length generation pipeline (paid tier).

Where :class:`engine.pipeline.StoryPipeline` does a single-pass
expand → outline → draft → polish run (great for <2000-word short stories),
this module runs a multi-phase, canon-tracked process that stays coherent
across a whole book:

  Phase 0 — BIBLE     One LLM call produces a canonical blueprint (characters,
                      setting, ironclad world/system rules, and a chapter-by-
                      chapter beat sheet) as structured JSON → :class:`StoryBible`.
  Phase 1 — DRAFTING  Each chapter is written in turn. Every chapter prompt
                      always carries the (small) bible digest, a rolling
                      synopsis of everything so far (compressed, capped at
                      ~500 words), and the verbatim tail of the previous
                      chapter for voice/transition continuity.
  Phase 2 — CRITIQUE  A structural editorial pass over the whole draft finds
                      plot holes, character inconsistencies, pacing problems
                      and prose/AI artifacts, returned as structured issues
                      with concrete references.
  Phase 3 — REVISION  Only the chapters flagged by the critique are rewritten
                      (continuity-aware), then the book is reassembled.

It is model-agnostic — it drives whatever backend it's handed (typically a
:class:`engine.backends.cloud.CloudBackend` configured for deepseek-chat) via
that backend's public ``generate`` / ``generate_full`` / ``close`` API, so the
existing short-story pipeline and backends are reused untouched.

Usage::

    from engine.backends.cloud import CloudBackend
    from engine.novel import NovelPipeline

    backend = CloudBackend(provider="deepseek", max_tokens=6000)
    pipeline = NovelPipeline(backend, max_chapters=12, target_words=20000)
    async for event in pipeline.generate(prompt, genre, style, pov):
        ...  # see generate() for the event protocol
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

logger = logging.getLogger(__name__)

# How much of the previous chapter is handed verbatim to the next, for
# seamless voice/transition continuity.
TAIL_CHARS = 1200
# The rolling synopsis is compressed back under this many words whenever it
# grows past it, so chapter context stays bounded no matter how long the book.
MAX_SYNOPSIS_WORDS = 500


def _count_words(text: str) -> int:
    return len(text.split())


def _parse_json(text: str) -> Optional[dict[str, Any]]:
    """Best-effort parse of a JSON object from a model reply.

    Handles clean JSON, ```json fenced blocks, and JSON embedded in prose by
    extracting the outermost balanced ``{...}``. Returns None on failure.
    """
    if not text:
        return None
    s = text.strip()

    # Strip a leading/trailing markdown code fence if present.
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

    def _try(candidate: str) -> Optional[dict[str, Any]]:
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None

    obj = _try(s)
    if obj is not None:
        return obj

    # Fall back to the outermost balanced brace span.
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return _try(s[start : end + 1])
    return None


# ── Bible dataclasses ───────────────────────────────────────


@dataclass
class ChapterBeat:
    """One chapter's slot in the beat sheet (the plan, not the prose)."""

    number: int
    title: str
    synopsis: str = ""
    emotional_beat: str = ""
    must_include: list[str] = field(default_factory=list)
    ends_on: str = ""
    word_target: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any], *, fallback_number: int, fallback_words: int) -> "ChapterBeat":
        must = d.get("must_include") or d.get("key_points") or []
        if isinstance(must, str):
            must = [m.strip() for m in re.split(r"[\n;]+", must) if m.strip()]
        try:
            number = int(d.get("number", fallback_number))
        except (TypeError, ValueError):
            number = fallback_number
        try:
            word_target = int(d.get("word_target") or fallback_words)
        except (TypeError, ValueError):
            word_target = fallback_words
        return cls(
            number=number,
            title=str(d.get("title") or f"Chapter {number}").strip(),
            synopsis=str(d.get("synopsis") or d.get("summary") or "").strip(),
            emotional_beat=str(d.get("emotional_beat") or d.get("emotion") or "").strip(),
            must_include=[str(m).strip() for m in must if str(m).strip()],
            ends_on=str(d.get("ends_on") or "").strip(),
            word_target=word_target,
        )


@dataclass
class StoryBible:
    """The canonical blueprint for the whole novel. Serializable to JSON."""

    title: str = "Untitled"
    logline: str = ""
    pov: str = ""
    tone: str = ""
    themes: list[str] = field(default_factory=list)
    protagonist: dict[str, Any] = field(default_factory=dict)
    characters: list[dict[str, Any]] = field(default_factory=list)
    setting: dict[str, Any] = field(default_factory=dict)
    motifs: list[str] = field(default_factory=list)
    chapters: list[ChapterBeat] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any], *, words_per_chapter: int) -> "StoryBible":
        raw_chapters = d.get("chapters") or []
        chapters: list[ChapterBeat] = []
        for i, ch in enumerate(raw_chapters, start=1):
            if isinstance(ch, dict):
                chapters.append(
                    ChapterBeat.from_dict(ch, fallback_number=i, fallback_words=words_per_chapter)
                )
        # Normalise chapter numbering to 1..N regardless of what the model returned.
        for i, ch in enumerate(chapters, start=1):
            ch.number = i
            if ch.word_target <= 0:
                ch.word_target = words_per_chapter
        return cls(
            title=str(d.get("title") or "Untitled").strip(),
            logline=str(d.get("logline") or "").strip(),
            pov=str(d.get("pov") or "").strip(),
            tone=str(d.get("tone") or "").strip(),
            themes=[str(t).strip() for t in (d.get("themes") or []) if str(t).strip()],
            protagonist=d.get("protagonist") or {},
            characters=[c for c in (d.get("characters") or []) if isinstance(c, dict)],
            setting=d.get("setting") or {},
            motifs=[str(m).strip() for m in (d.get("motifs") or []) if str(m).strip()],
            chapters=chapters,
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    # ── digest used in every chapter prompt (small, always-present canon) ──

    def digest(self) -> str:
        p = self.protagonist or {}
        s = self.setting or {}

        def line(label: str, value: Any) -> str:
            value = ("" if value is None else str(value)).strip()
            return f"  {label}: {value}" if value else ""

        prot_lines = "\n".join(
            x for x in (
                line("Voice", p.get("voice")),
                line("Traits", p.get("traits")),
                line("Flaw", p.get("flaw") or p.get("wound")),
                line("Want", p.get("want")),
                line("Need", p.get("need")),
                line("Arc", p.get("arc")),
            ) if x
        )
        prot_name = str(p.get("name") or "(unnamed protagonist)").strip()
        prot_age = p.get("age")
        prot_header = f"NARRATOR/PROTAGONIST — {prot_name}" + (f", age {prot_age}" if prot_age else "")

        others = []
        for c in self.characters:
            name = str(c.get("name") or "?").strip()
            role = str(c.get("role") or "").strip()
            voice = str(c.get("voice") or "").strip()
            want = str(c.get("want") or "").strip()
            bits = "; ".join(b for b in (
                f"voice — {voice}" if voice else "",
                f"wants — {want}" if want else "",
            ) if b)
            head = f"  - {name}" + (f" ({role})" if role else "")
            others.append(f"{head}: {bits}" if bits else head)
        others_block = "\n".join(others) if others else "  (none)"

        rules = s.get("world_rules") or s.get("portal_rules") or s.get("rules") or []
        if isinstance(rules, str):
            rules = [rules]
        rules_block = "\n".join(f"  - {str(r).strip()}" for r in rules if str(r).strip()) or "  (none specified)"

        locations = s.get("locations") or []
        if isinstance(locations, str):
            locations = [locations]
        loc_str = ", ".join(str(l).strip() for l in locations if str(l).strip())

        beats = "\n".join(
            f"  Ch{ch.number}. {ch.title}: {ch.synopsis}" for ch in self.chapters
        )

        return f"""TITLE: {self.title}
LOGLINE: {self.logline}
TONE: {self.tone}
POV/TENSE: {self.pov}
THEMES: {", ".join(self.themes) if self.themes else "(unspecified)"}

{prot_header}
{prot_lines or "  (no protagonist sheet)"}

OTHER CHARACTERS:
{others_block}

SETTING:
  World/era: {str(s.get("world_name") or s.get("era") or s.get("location_era") or "").strip()}
  Locations: {loc_str or "(unspecified)"}
  Atmosphere: {str(s.get("atmosphere") or s.get("the_other_world") or "").strip()}
  IRONCLAD WORLD RULES (never contradict these):
{rules_block}

MOTIFS: {", ".join(self.motifs) if self.motifs else "(none)"}

FULL BEAT SHEET (for continuity; only WRITE the current chapter):
{beats}"""


# ── Pipeline ────────────────────────────────────────────────


class NovelPipeline:
    """Multi-phase, canon-tracked novel generator (paid tier).

    Args:
        backend: any object exposing ``generate(prompt, system)`` (async
            token iterator), ``generate_full(prompt, system)`` (coroutine →
            str) and ``close()``. Typically a deepseek-configured
            :class:`CloudBackend`.
        max_chapters: upper bound on chapters in the beat sheet.
        target_words: total word target for the finished book; chapter count
            and per-chapter targets are derived from it.
    """

    def __init__(
        self,
        backend,
        max_chapters: int = 15,
        target_words: int = 20000,
        n_chapters: Optional[int] = None,
        min_words_per_chapter: int = 400,
    ):
        self.backend = backend
        self.max_chapters = max(2, int(max_chapters))

        # By default this is a novel-length engine: the target is floored at
        # 2000 words and the chapter count is derived at ~1800 words/chapter.
        # Passing an explicit ``n_chapters`` opts out of both floors so a small,
        # fast multi-chapter run can be produced (free-tier/test smoke runs that
        # want e.g. 3 short chapters totalling 500 words).
        if n_chapters is not None:
            self.target_words = max(1, int(target_words))
            self.n_chapters = max(2, min(self.max_chapters, int(n_chapters)))
        else:
            self.target_words = max(2000, int(target_words))
            # ~1800 words/chapter feels like a chapter; clamp to [2, max_chapters].
            approx = round(self.target_words / 1800) or 1
            self.n_chapters = max(2, min(self.max_chapters, approx))
        self.words_per_chapter = max(int(min_words_per_chapter), self.target_words // self.n_chapters)

        self.retries = 5
        # Does this backend's generate_full accept a json_mode kwarg?
        try:
            self._supports_json = "json_mode" in inspect.signature(
                backend.generate_full
            ).parameters
        except (TypeError, ValueError, AttributeError):
            self._supports_json = False

    async def close(self) -> None:
        close = getattr(self.backend, "close", None)
        if close is not None:
            await close()

    # ── public API ──────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        genre: str = "literary",
        style: str = "descriptive",
        pov: str = "third_person_limited",
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the full novel pipeline, yielding event dicts.

        Event protocol::

            {"type": "progress", "phase": "bible|drafting|critique|revising", "message": ..., ...}
            {"type": "chunk", "chapter": N, "text": "..."}              # streaming prose
            {"type": "chapter_complete", "chapter": N, "title": ..., "word_count": ...}
            {"type": "bible", "bible": {...}}                           # the canonical blueprint
            {"type": "critique", "issues": [...]}
            {"type": "revision", "chapter": N, "fixed": "...", "word_count": ...}
            {"type": "complete", "title": ..., "full_text": ..., "word_count": ..., ...}
            {"type": "error", "message": "..."}
        """
        genre = (genre or "literary").lower()
        style = (style or "descriptive").lower()
        pov = (pov or "third_person_limited").lower()

        try:
            # ── Phase 0: Bible ───────────────────────────────
            yield {
                "type": "progress",
                "phase": "bible",
                "message": "Designing the story bible — characters, world rules, and chapter beats...",
            }
            bible = await self._build_bible(prompt, genre, style, pov)
            if not bible.chapters:
                yield {"type": "error", "message": "Story bible came back without a chapter beat sheet."}
                return

            digest = bible.digest()
            yield {"type": "bible", "bible": bible.to_dict()}
            yield {
                "type": "progress",
                "phase": "bible",
                "message": f'Bible ready — "{bible.title}", {len(bible.chapters)} chapters planned.',
                "data": {
                    "title": bible.title,
                    "logline": bible.logline,
                    "chapter_count": len(bible.chapters),
                    "chapter_titles": [c.title for c in bible.chapters],
                },
            }

            # ── Phase 1: Chapter-by-chapter drafting ─────────
            # chapters[n] holds prose; recaps[n] holds the factual continuity recap.
            chapters: dict[int, str] = {}
            recaps: dict[int, str] = {}
            rolling = ""           # rolling synopsis (compressed, <= MAX_SYNOPSIS_WORDS)
            prev_tail = ""

            for beat in bible.chapters:
                n = beat.number
                yield {
                    "type": "progress",
                    "phase": "drafting",
                    "chapter": n,
                    "message": f'Writing chapter {n}/{len(bible.chapters)}: "{beat.title}"...',
                }

                prose = ""
                async for ev in self._draft_chapter(beat, genre, style, pov, digest, rolling, prev_tail):
                    if ev["type"] == "chunk":
                        prose += ev["text"]
                        yield {"type": "chunk", "chapter": n, "text": ev["text"]}
                    elif ev["type"] == "_final":
                        prose = ev["text"]
                    else:
                        yield ev

                prose = prose.strip()
                chapters[n] = prose
                wc = _count_words(prose)
                yield {
                    "type": "chapter_complete",
                    "chapter": n,
                    "title": beat.title,
                    "word_count": wc,
                }

                # Fold this chapter into the rolling continuity context.
                recap = await self._recap(beat, prose)
                recaps[n] = recap
                rolling = await self._extend_synopsis(rolling, n, beat.title, recap)
                prev_tail = prose[-TAIL_CHARS:]

            # ── Phase 2: Auto-critique ───────────────────────
            yield {
                "type": "progress",
                "phase": "critique",
                "message": "Running a structural editorial pass over the full draft...",
            }
            issues = await self._critique(bible, chapters, genre, style, pov)
            yield {"type": "critique", "issues": issues}
            yield {
                "type": "progress",
                "phase": "critique",
                "message": f"Critique complete — {len(issues)} issue(s) flagged.",
            }

            # ── Phase 3: Revision loop (only affected chapters) ──
            issues_by_chapter = self._group_issues(issues, valid=set(chapters))
            if issues_by_chapter:
                yield {
                    "type": "progress",
                    "phase": "revising",
                    "message": (
                        f"Revising {len(issues_by_chapter)} chapter(s) with flagged issues: "
                        f"{', '.join(str(n) for n in sorted(issues_by_chapter))}."
                    ),
                }
                for n in sorted(issues_by_chapter):
                    beat = bible.chapters[n - 1]
                    ch_issues = issues_by_chapter[n]
                    yield {
                        "type": "progress",
                        "phase": "revising",
                        "chapter": n,
                        "message": f"Rewriting chapter {n} to fix {len(ch_issues)} issue(s)...",
                    }
                    story_so_far = self._synopsis_up_to(bible, recaps, n)
                    prev_tail = chapters[n - 1][-TAIL_CHARS:] if n - 1 in chapters else ""

                    fixed = ""
                    async for ev in self._revise_chapter(
                        beat, genre, style, pov, digest, story_so_far, prev_tail,
                        chapters[n], ch_issues,
                    ):
                        if ev["type"] == "chunk":
                            fixed += ev["text"]
                            yield {"type": "chunk", "chapter": n, "text": ev["text"]}
                        elif ev["type"] == "_final":
                            fixed = ev["text"]
                        else:
                            yield ev

                    fixed = fixed.strip()
                    # Guard against a model that returns blank or truncated
                    # prose: a revision must never destroy a chapter. If the
                    # rewrite comes back under half the original's length, keep
                    # the original chapter (and its recap) untouched.
                    original_wc = _count_words(chapters[n])
                    fixed_wc = _count_words(fixed)
                    if not self._revision_acceptable(chapters[n], fixed):
                        logger.warning(
                            "Chapter %d revision rejected: %d words vs original %d "
                            "(<50%%) — keeping original.", n, fixed_wc, original_wc,
                        )
                        yield {
                            "type": "progress",
                            "phase": "revising",
                            "chapter": n,
                            "message": (
                                f"Revision of chapter {n} came back too short "
                                f"({fixed_wc} vs {original_wc} words) — keeping the original."
                            ),
                        }
                        continue

                    chapters[n] = fixed
                    recaps[n] = await self._recap(beat, fixed)
                    yield {
                        "type": "revision",
                        "chapter": n,
                        "fixed": fixed,
                        "word_count": fixed_wc,
                    }
            else:
                yield {
                    "type": "progress",
                    "phase": "revising",
                    "message": "No chapter-specific issues to revise.",
                }

            # ── Final assembly ───────────────────────────────
            full_text = self._assemble(bible, chapters)
            yield {
                "type": "complete",
                "title": bible.title,
                "full_text": full_text,
                "word_count": _count_words(full_text),
                "chapter_count": len(chapters),
                "genre": genre,
                "style": style,
                "pov": pov,
                "bible": bible.to_dict(),
                "critique": issues,
                "revised_chapters": sorted(issues_by_chapter) if issues_by_chapter else [],
            }

        except RuntimeError as exc:
            logger.exception("Novel pipeline runtime error")
            yield {"type": "error", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001 — surface anything to the client
            logger.exception("Novel pipeline failed")
            yield {"type": "error", "message": f"Unexpected error during novel generation: {exc}"}

    # ── Phase 0 helpers ─────────────────────────────────────

    async def _build_bible(self, prompt: str, genre: str, style: str, pov: str) -> StoryBible:
        system = (
            "You are a novelist and story architect with the instincts of a literary editor. "
            "You design tight, character-driven, atmospheric fiction with grounded, escalating "
            "stakes. You avoid cliché, melodrama, and generic plotting. You always return valid JSON."
        )
        user = f"""Design the complete blueprint (a "story bible") for a {genre} novel of {self.n_chapters} chapters, each about {self.words_per_chapter} words (~{self.target_words} words total).

Seed idea / premise: "{prompt}"

Craft constraints:
- Point of view / tense: {pov}. Prose style: {style}. Commit to these and keep them consistent.
- Decide the IRONCLAD RULES of this story's world or system now (how its central conceit / magic / technology / social order works — when, at what cost, with what limits) and keep them free of contradiction. Concrete, not vague.
- Give the protagonist a real wound/flaw, a want, a need, and an arc — a reason this story matters to *them*. Keep stakes intimate and escalating, not generic "save the world".
- One to three secondary characters, each with a distinct voice and their own want. No interchangeable extras.
- A real ending: a costly choice, a consequence, and a closing image — not a neat bow, not a cheap twist.
- The chapter beat sheet must form a clear arc (ordinary world + inciting incident, escalating complication, a midpoint turn, rising cost, a climax built on a hard choice, a resolution with a closing image). Every chapter advances the story — no filler.

Return ONLY a JSON object, no prose or markdown, with EXACTLY this shape:
{_BIBLE_SHAPE}

The "chapters" array MUST contain exactly {self.n_chapters} entries, numbered 1..{self.n_chapters}, each with a "word_target" near {self.words_per_chapter}."""

        data = await self._json_call(system, user)
        return StoryBible.from_dict(data, words_per_chapter=self.words_per_chapter)

    # ── Phase 1 helpers ─────────────────────────────────────

    def _draft_chapter(
        self, beat: ChapterBeat, genre: str, style: str, pov: str,
        digest: str, rolling: str, prev_tail: str,
    ) -> AsyncIterator[dict[str, Any]]:
        must = "\n".join(f"  - {m}" for m in beat.must_include) or "  (use the synopsis)"
        prev_block = (
            "VERBATIM END OF THE PREVIOUS CHAPTER (continue seamlessly from this; do NOT repeat it):\n"
            f'"""\n{prev_tail}\n"""'
            if prev_tail else "This is the opening chapter of the novel."
        )
        story_so_far = rolling or "Nothing yet — this is the beginning."
        target = beat.word_target or self.words_per_chapter
        floor = int(target * 0.85)

        user = f"""{digest}

THE STORY SO FAR (summary of chapters already written — never contradict it):
{story_so_far}

{prev_block}

NOW WRITE CHAPTER {beat.number}: "{beat.title}"
What must happen: {beat.synopsis}
Emotional beat: {beat.emotional_beat}
Concrete plot points to land:
{must}
End the chapter on: {beat.ends_on or "a hook or turn that pulls the reader onward"}

Write the full chapter now — about {target} words (no fewer than {floor}). {_POV_LINE.format(pov=pov)} Open in a scene, not a summary. Use concrete sensory detail, real dialogue where natural, and interiority. Keep every canon and world rule consistent. {_PROSE_RULES} Output ONLY the chapter prose — no title, no header, no notes."""

        return self._stream(_DRAFT_SYSTEM.format(genre=genre, style=style), user, label=f"draft ch{beat.number}")

    async def _recap(self, beat: ChapterBeat, prose: str) -> str:
        system = "You summarize fiction tightly and factually for continuity tracking. No flourish, no blurb."
        user = (
            f'Summarize Chapter {beat.number} ("{beat.title}") in 2-4 plain sentences capturing only '
            f"what happened, what changed, and any new facts established (names, places, rules, objects, "
            f"the state of each character). This is for continuity, not marketing.\n\n{prose}"
        )
        return (await self._full(system, user)).strip()

    async def _extend_synopsis(self, rolling: str, n: int, title: str, recap: str) -> str:
        combined = (rolling + f"\nCh{n} ({title}): {recap}").strip()
        if _count_words(combined) <= MAX_SYNOPSIS_WORDS:
            return combined
        return await self._compress_synopsis(combined)

    async def _compress_synopsis(self, synopsis: str) -> str:
        system = "You compress story-so-far notes for continuity. Keep every plot-critical fact; drop only prose."
        user = (
            f"Compress the following running summary to at most {MAX_SYNOPSIS_WORDS - 50} words. "
            "Preserve every fact needed for continuity — names, places, established rules, objects, "
            "the current state of each character and the plot. Drop adjectives and atmosphere, keep events. "
            "Write it as a tight chronological digest.\n\n"
            f"{synopsis}"
        )
        out = (await self._full(system, user)).strip()
        # Hard cap in case the model overshoots.
        words = out.split()
        if len(words) > MAX_SYNOPSIS_WORDS:
            out = " ".join(words[:MAX_SYNOPSIS_WORDS])
        return out

    def _synopsis_up_to(self, bible: StoryBible, recaps: dict[int, str], n: int) -> str:
        parts = [
            f"Ch{ch.number} ({ch.title}): {recaps.get(ch.number, ch.synopsis)}"
            for ch in bible.chapters if ch.number < n
        ]
        text = "\n".join(parts) if parts else "Nothing yet — this is the beginning."
        if _count_words(text) > MAX_SYNOPSIS_WORDS:
            words = text.split()
            text = " ".join(words[-MAX_SYNOPSIS_WORDS:])
        return text

    # ── Phase 2 helpers ─────────────────────────────────────

    async def _critique(
        self, bible: StoryBible, chapters: dict[int, str], genre: str, style: str, pov: str,
    ) -> list[dict[str, Any]]:
        book = "\n\n".join(
            f"### CHAPTER {n}: {bible.chapters[n - 1].title}\n{chapters[n]}"
            for n in sorted(chapters)
        )
        system = (
            "You are a ruthless but fair developmental editor and line editor. You read a full novel "
            "draft and surface its real, concrete problems — not vague praise. You always return valid JSON."
        )
        user = f"""Below is a complete {genre} novel draft ({pov} POV, {style} style). Review the WHOLE book and report its most important, concrete problems.

Check for, at minimum:
- PLOT HOLES: contradictions or continuity breaks BETWEEN chapters; setups with no payoff; broken world rules.
- CHARACTER: inconsistent voice, motivation, or physical/biographical details; flat or interchangeable characters.
- PACING: chapters that drag or rush; a sagging middle; an unearned or abrupt climax.
- PROSE: clichés, purple prose, repeated phrases/crutch words, AI artifacts ("however/moreover/furthermore/in conclusion", robotic transitions, three-part anaphora), stilted dialogue.

Return AT LEAST 3 and at most 10 issues — the ones a revision should actually fix. Each issue MUST point to a specific place.

Return ONLY a JSON object, no markdown:
{_CRITIQUE_SHAPE}

"chapter" must be the integer chapter number the fix applies to (1..{len(chapters)}); use the single most relevant chapter for cross-chapter issues. "quote" is a short verbatim snippet (<=20 words) from the draft locating the problem. "fix" is a concrete, actionable instruction for the rewrite.

THE DRAFT:
{book}"""

        data = await self._json_call(system, user)
        issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(issues, list):
            issues = []
        cleaned: list[dict[str, Any]] = []
        for it in issues:
            if not isinstance(it, dict):
                continue
            cleaned.append({
                "chapter": it.get("chapter"),
                "category": str(it.get("category") or "general").strip(),
                "severity": str(it.get("severity") or "medium").strip(),
                "issue": str(it.get("issue") or it.get("description") or "").strip(),
                "quote": str(it.get("quote") or it.get("evidence") or "").strip(),
                "fix": str(it.get("fix") or it.get("suggestion") or "").strip(),
            })
        return [c for c in cleaned if c["issue"]]

    @staticmethod
    def _group_issues(issues: list[dict[str, Any]], valid: set[int]) -> dict[int, list[dict[str, Any]]]:
        grouped: dict[int, list[dict[str, Any]]] = {}
        for it in issues:
            ch = it.get("chapter")
            try:
                ch = int(ch)
            except (TypeError, ValueError):
                continue
            if ch in valid:
                grouped.setdefault(ch, []).append(it)
        return grouped

    # ── Phase 3 helpers ─────────────────────────────────────

    def _revise_chapter(
        self, beat: ChapterBeat, genre: str, style: str, pov: str,
        digest: str, story_so_far: str, prev_tail: str,
        original: str, ch_issues: list[dict[str, Any]],
    ) -> AsyncIterator[dict[str, Any]]:
        issue_block = "\n".join(
            f"  - [{it['category']}/{it['severity']}] {it['issue']}"
            + (f'\n      where: "{it["quote"]}"' if it["quote"] else "")
            + (f"\n      fix: {it['fix']}" if it["fix"] else "")
            for it in ch_issues
        )
        prev_block = (
            "VERBATIM END OF THE PREVIOUS (already-finalized) CHAPTER — continue seamlessly from it; do NOT repeat it:\n"
            f'"""\n{prev_tail}\n"""'
            if prev_tail else "This is the opening chapter of the novel."
        )
        target = beat.word_target or self.words_per_chapter
        floor = int(target * 0.85)

        user = f"""{digest}

THE STORY SO FAR (finalized chapters before this one — never contradict it):
{story_so_far}

{prev_block}

You are REVISING Chapter {beat.number}: "{beat.title}". An editor flagged these issues:
{issue_block}

Rewrite the WHOLE chapter, fixing every issue above. Keep the chapter's events, its role in the arc, and continuity with the surrounding chapters; preserve what already works. End the chapter on: {beat.ends_on or "its existing hook"}.

About {target} words (no fewer than {floor}). {_POV_LINE.format(pov=pov)} {_PROSE_RULES} Output ONLY the finished chapter prose — no title, no header, no notes.

CURRENT VERSION OF THE CHAPTER (revise this):
{original}"""

        return self._stream(_REVISE_SYSTEM.format(genre=genre, style=style), user, label=f"revise ch{beat.number}")

    @staticmethod
    def _revision_acceptable(original: str, fixed: str, min_ratio: float = 0.5) -> bool:
        """A revision is accepted only if it retains at least ``min_ratio`` of
        the original chapter's word count. Blank or truncated rewrites are
        rejected so a bad revision can never destroy a chapter.
        """
        return _count_words(fixed) >= max(1, _count_words(original)) * min_ratio

    # ── assembly ─────────────────────────────────────────────

    @staticmethod
    def _assemble(bible: StoryBible, chapters: dict[int, str]) -> str:
        parts = [f"# {bible.title}\n"]
        for n in sorted(chapters):
            title = bible.chapters[n - 1].title if n - 1 < len(bible.chapters) else f"Chapter {n}"
            parts.append(f"\n## Chapter {n}: {title}\n\n{chapters[n]}\n")
        return "\n".join(parts)

    # ── backend plumbing (retry / JSON / streaming) ──────────

    async def _full(self, system: str, user: str, *, json_mode: bool = False) -> str:
        """Non-streaming call with retry/backoff (DeepSeek can be slow/flaky)."""
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                if json_mode and self._supports_json:
                    return await self.backend.generate_full(user, system, json_mode=True)
                return await self.backend.generate_full(user, system)
            except Exception as exc:  # noqa: BLE001 — broad on purpose for backoff
                last_err = exc
                wait = 3 * (attempt + 1)
                logger.warning("backend call failed (attempt %d/%d): %s — retrying in %ss",
                               attempt + 1, self.retries, exc, wait)
                await asyncio.sleep(wait)
        raise RuntimeError(f"Backend call failed after {self.retries} attempts: {last_err}")

    async def _stream(self, system: str, user: str, *, label: str) -> AsyncIterator[dict[str, Any]]:
        """Stream tokens as chunk events, retrying the whole call on failure.

        Yields ``{"type": "chunk", "text": ...}`` per token and a final
        ``{"type": "_final", "text": <full prose>}`` (internal; consumed by
        generate()). The full prose is authoritative; live chunks are best-effort.
        """
        last_err: Optional[Exception] = None
        for attempt in range(self.retries):
            buffer: list[str] = []
            try:
                async for token in self.backend.generate(user, system):
                    buffer.append(token)
                    yield {"type": "chunk", "text": token}
                yield {"type": "_final", "text": "".join(buffer)}
                return
            except Exception as exc:  # noqa: BLE001 — broad for backoff/retry
                last_err = exc
                wait = 3 * (attempt + 1)
                logger.warning("%s stream failed (attempt %d/%d): %s — retrying in %ss",
                               label, attempt + 1, self.retries, exc, wait)
                yield {
                    "type": "progress",
                    "phase": "drafting",
                    "message": f"({label}) hiccup — retrying ({attempt + 1}/{self.retries})...",
                }
                await asyncio.sleep(wait)
        raise RuntimeError(f"{label} failed after {self.retries} attempts: {last_err}")

    async def _json_call(self, system: str, user: str) -> dict[str, Any]:
        """Call the model and parse a JSON object, with one strict re-ask."""
        raw = await self._full(system, user, json_mode=True)
        parsed = _parse_json(raw)
        if parsed is not None:
            return parsed
        strict = user + (
            "\n\nIMPORTANT: your previous reply was not valid JSON. Reply with ONLY a single valid "
            "JSON object — no markdown fences, no commentary before or after."
        )
        raw = await self._full(system, strict, json_mode=True)
        parsed = _parse_json(raw)
        if parsed is None:
            raise RuntimeError("Model did not return parseable JSON after a retry.")
        return parsed


# ── prompt fragments shared across phases ───────────────────

_DRAFT_SYSTEM = (
    "You are a literary novelist writing {genre} in a {style} register, in the tradition of writers who "
    "care about sentences. You write actual scene-prose with concrete sensory detail, real dialogue, and "
    "interiority — never summary. You resist cliché, purple metaphor pile-ups, and tidy moralizing. You "
    "vary sentence length and rhythm. You never use chapter headings, bullet points, or meta-commentary — "
    "only the story itself."
)

_REVISE_SYSTEM = (
    "You are a meticulous literary novelist and line editor working in {genre}, {style} register. You "
    "rewrite prose to fix specific editorial notes without flattening voice or padding, you keep continuity "
    "exact, and you return only finished prose — no headers, no notes."
)

_POV_LINE = "Maintain {pov} point of view and a consistent tense throughout."

_PROSE_RULES = (
    "Vary sentence length; avoid clichés and crutch transitions (no \"however/moreover/furthermore/in "
    "conclusion\"); do not lean on three-part anaphora; keep dialogue spoken-sounding; no AI artifacts."
)

# JSON skeletons kept out of f-strings to avoid brace-escaping noise.
_BIBLE_SHAPE = """{
  "title": "...",
  "logline": "one sentence",
  "pov": "point of view and tense",
  "tone": "2-3 sentences on mood and prose texture",
  "themes": ["...", "..."],
  "protagonist": {"name": "...", "age": 0, "traits": "...", "flaw": "...", "voice": "how they sound on the page", "want": "...", "need": "...", "arc": "from X to Y"},
  "characters": [{"name": "...", "role": "...", "traits": "...", "voice": "...", "want": "..."}],
  "setting": {"world_name": "...", "era": "...", "locations": ["...", "..."], "atmosphere": "...", "world_rules": ["concrete ironclad rule", "concrete ironclad rule", "concrete ironclad rule"]},
  "motifs": ["recurring image/object", "..."],
  "chapters": [
    {"number": 1, "title": "evocative 2-4 words", "synopsis": "3-4 sentences of what actually happens", "emotional_beat": "what the reader feels", "must_include": ["concrete plot point", "concrete plot point"], "ends_on": "the hook or turn that closes the chapter", "word_target": 1800}
  ]
}"""

_CRITIQUE_SHAPE = """{
  "issues": [
    {"chapter": 1, "category": "plot_hole|character|pacing|prose", "severity": "high|medium|low", "issue": "what is wrong, concretely", "quote": "short verbatim snippet locating it", "fix": "a concrete instruction for the rewrite"}
  ]
}"""


__all__ = ["NovelPipeline", "StoryBible", "ChapterBeat"]
