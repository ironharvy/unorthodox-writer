"""
Multi-stage story generation pipeline.

Orchestrates the four-stage process:
  1. Expand  – user input → story premise
  2. Outline – premise → structured outline
  3. Draft   – outline sections → streamed prose (per section)
  4. Polish  – assembled draft → polished final story

Model-agnostic: works with OllamaBackend or CloudBackend.
"""

from __future__ import annotations

import logging
import re
from typing import Any, AsyncIterator, Optional, Literal

from engine.templates import get_stage_template, get_system_prompt
from engine.backends.ollama import OllamaBackend
from engine.backends.cloud import CloudBackend

logger = logging.getLogger(__name__)

Tier = Literal["free", "paid"]
Backend = OllamaBackend | CloudBackend

# ── helper: parse outline into sections ─────────────────────

_OUTLINE_SECTION_RE = re.compile(
    r"SECTION\s+(\d+):\s*(.+?)\n"
    r"SUMMARY:\s*(.+?)\n"
    r"EMOTION:\s*(.+?)\n"
    r"KEY POINTS:\s*(.+?)(?=\nSECTION|\nSECTIONS:|\nTONE|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _parse_outline(text: str) -> list[dict[str, str]]:
    """Parse an outline text into a list of section dicts."""
    sections: list[dict[str, str]] = []
    for match in _OUTLINE_SECTION_RE.finditer(text):
        sections.append({
            "num": match.group(1),
            "title": match.group(2).strip(),
            "summary": match.group(3).strip(),
            "emotion": match.group(4).strip(),
            "key_points": match.group(5).strip(),
        })
    return sections


def _estimate_section_words(total_words: int, section_count: int) -> int:
    """Estimate words per section, reserving ~15% for polish adjustments."""
    draft_pool = int(total_words * 0.85)
    return max(80, draft_pool // max(section_count, 1))


def _count_words(text: str) -> int:
    return len(text.split())


# ── Pipeline ────────────────────────────────────────────────


class StoryPipeline:
    """Orchestrates multi-stage story generation.

    Usage:
        pipeline = StoryPipeline(tier="free")
        async for event in pipeline.generate(
            prompt="A detective in a world without color...",
            genre="noir",
            style="descriptive",
            max_words=800,
            pov="first_person",
        ):
            print(event)
    """

    def __init__(
        self,
        tier: Tier = "free",
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
        cloud_provider: Literal["claude", "openai", "deepseek"] = "claude",
        cloud_model: Optional[str] = None,
        cloud_max_tokens: int = 4096,
        compact_prompts: bool = False,
    ):
        """
        Args:
            tier: "free" for Ollama, "paid" for cloud APIs.
            ollama_url: Override Ollama server URL.
            ollama_model: Override Ollama model name.
            cloud_provider: "claude" or "openai".
            cloud_model: Override cloud model name.
            cloud_max_tokens: Max tokens for cloud LLM calls.
            compact_prompts: Use shorter prompt templates (saves tokens, may reduce quality).
        """
        self.tier: Tier = tier
        self.compact_prompts = compact_prompts

        if tier == "free":
            self._backend: Backend = OllamaBackend(
                base_url=ollama_url,
                model=ollama_model,
            )
        else:
            self._backend = CloudBackend(
                provider=cloud_provider,
                model=cloud_model,
                max_tokens=cloud_max_tokens,
            )
        self._backend_instance = self._backend  # keep ref for cleanup

    async def close(self) -> None:
        """Release backend resources."""
        await self._backend.close()

    # ── public API ─────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        genre: str = "literary",
        style: str = "descriptive",
        max_words: int = 1000,
        pov: str = "third_person_limited",
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the full story generation pipeline.

        Yields event dicts:
            {"type": "progress", "stage": "...", "message": "..."}
            {"type": "chunk", "text": "..."}           # streaming prose
            {"type": "complete", "title": "...", "full_text": "...", "word_count": N, ...}
            {"type": "error", "message": "..."}
        """
        # Normalise inputs
        genre = genre.lower()
        style = style.lower()
        pov = pov.lower()

        try:
            # ── Stage 1: Expand ──────────────────────────
            yield {
                "type": "progress",
                "stage": "expand",
                "message": "Expanding your idea into a story premise...",
            }

            expand_prompt = get_stage_template("expand", self.compact_prompts).format(
                prompt=prompt, genre=genre, style=style, pov=pov,
            )
            expand_system = get_system_prompt("expand", genre, style, pov)

            premise_text = await self._backend.generate_full(expand_prompt, expand_system)

            # Parse premise: extract title, characters, setting, conflict, premise body
            title = self._extract_field(premise_text, "TITLE", "Untitled")
            characters = self._extract_field(premise_text, "CHARACTERS", "")
            setting = self._extract_field(premise_text, "SETTING", "")
            conflict = self._extract_field(premise_text, "CONFLICT", "")
            premise_body = self._extract_field(premise_text, "PREMISE", premise_text)

            yield {
                "type": "progress",
                "stage": "expand",
                "message": f"Premise ready — story titled \"{title}\"",
                "data": {
                    "title": title,
                    "characters": characters,
                    "setting": setting,
                    "conflict": conflict,
                },
            }

            # ── Stage 2: Outline ─────────────────────────
            yield {
                "type": "progress",
                "stage": "outline",
                "message": "Building story structure and outline...",
            }

            outline_prompt = get_stage_template("outline", self.compact_prompts).format(
                premise=premise_body,
                genre=genre,
                style=style,
                pov=pov,
                max_words=max_words,
                min_sections=(max_words + 299) // 300,
            )
            outline_system = get_system_prompt("outline", genre, style, pov)

            outline_text = await self._backend.generate_full(outline_prompt, outline_system)
            sections = _parse_outline(outline_text)

            if not sections:
                yield {
                    "type": "error",
                    "message": "Failed to parse story outline. The model returned an unexpected format.",
                }
                return

            section_count = len(sections)
            yield {
                "type": "progress",
                "stage": "outline",
                "message": f"Outline complete — {section_count} sections planned",
                "data": {
                    "section_count": section_count,
                    "section_titles": [s["title"] for s in sections],
                },
            }

            # ── Stage 3: Draft ───────────────────────────
            section_words = _estimate_section_words(max_words, section_count)
            drafted_sections: list[str] = []
            full_outline_text = self._format_outline_for_context(sections)

            for i, section in enumerate(sections):
                sec_title = section["title"]
                yield {
                    "type": "progress",
                    "stage": "draft",
                    "message": f"Writing section {i + 1}/{section_count}: {sec_title}...",
                }

                # Build context from previous sections
                previous_text = "\n\n".join(drafted_sections) if drafted_sections else "(This is the beginning of the story.)"

                draft_prompt = get_stage_template("draft", self.compact_prompts).format(
                    title=title,
                    genre=genre,
                    style=style,
                    pov=pov,
                    full_outline=full_outline_text,
                    previous_text=previous_text,
                    section_title=sec_title,
                    section_summary=section["summary"],
                    section_emotion=section["emotion"],
                    key_points=section["key_points"],
                    section_words=section_words,
                )
                draft_system = get_system_prompt("draft", genre, style, pov)

                # Stream this section's prose token by token
                section_buffer: list[str] = []
                async for token in self._backend.generate(draft_prompt, draft_system):
                    section_buffer.append(token)
                    yield {"type": "chunk", "text": token}

                drafted_sections.append("".join(section_buffer))

                # Small separator between sections (yielded as chunk so frontend can add spacing)
                if i < section_count - 1:
                    yield {"type": "chunk", "text": "\n\n"}

            draft_full = "\n\n".join(drafted_sections)

            # ── Stage 4: Polish ──────────────────────────
            yield {
                "type": "progress",
                "stage": "polish",
                "message": "Polishing prose and refining the story...",
            }

            polish_prompt = get_stage_template("polish", self.compact_prompts).format(
                draft=draft_full,
                genre=genre,
                style=style,
                pov=pov,
                max_words=max_words,
            )
            polish_system = get_system_prompt("polish", genre, style, pov)

            # For polish, we stream the final result too
            polished_buffer: list[str] = []
            async for token in self._backend.generate(polish_prompt, polish_system):
                polished_buffer.append(token)
                yield {"type": "chunk", "text": token}

            final_text = "".join(polished_buffer)
            final_word_count = _count_words(final_text)

            yield {
                "type": "complete",
                "title": title,
                "full_text": final_text,
                "word_count": final_word_count,
                "section_count": section_count,
                "genre": genre,
                "style": style,
                "pov": pov,
            }

        except RuntimeError as exc:
            yield {"type": "error", "message": str(exc)}
        except Exception as exc:
            logger.exception("Pipeline failed")
            yield {
                "type": "error",
                "message": f"Unexpected error during story generation: {exc}",
            }

    # ── helpers ──────────────────────────────────────────

    @staticmethod
    def _extract_field(text: str, field: str, default: str = "") -> str:
        """Extract a labeled field from generated text."""
        # Try "FIELD: content"
        pattern = rf"^{field}:\s*(.+?)(?=\n[A-Z]|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.MULTILINE | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return default

    @staticmethod
    def _format_outline_for_context(sections: list[dict[str, str]]) -> str:
        """Format sections into a compact context string for draft prompts."""
        lines: list[str] = []
        for s in sections:
            lines.append(
                f"SECTION {s['num']}: {s['title']}\n"
                f"  Summary: {s['summary']}\n"
                f"  Emotion: {s['emotion']}\n"
                f"  Key points: {s['key_points']}"
            )
        return "\n\n".join(lines)
