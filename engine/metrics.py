#!/usr/bin/env python3
"""
Automated quality metrics for generated stories.

These are cheap, deterministic, model-free heuristics — not a substitute for an
editorial read, but a fast signal for regression-testing prose quality and for
driving the DSPy optimizer (``engine/optimizer.py``). Every metric is computed
from the text alone (optionally informed by the story bible / critique).

Scores are reported on a 0-10 scale per dimension, plus a weighted ``overall``
(higher = better). A few raw interpretable values are exposed alongside the
sub-scores (Flesch-Kincaid grade, dialogue %, pacing coefficient of variation)
because they are more meaningful un-normalized.

CLI::

    python engine/metrics.py path/to/story.md
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from typing import Any, Optional


# ── Known AI "crutch" markers ───────────────────────────────
# Words/phrases that disproportionately mark machine-generated prose. Drawn
# from the task brief and the editor (AGY) feedback.
AI_CRUTCH_WORDS = [
    "however", "moreover", "furthermore", "delve", "tapestry",
    "testament to", "it was then that", "indeed", "in conclusion",
    "navigate the complexities", "navigate the complex", "a myriad of",
    "in the realm of", "needless to say", "at the end of the day",
    "little did", "ever-present", "palpable", "stark reminder",
    "sent shivers", "shiver down", "can't help but", "couldn't help but",
    "a symphony of", "dance of", "weave a", "woven", "intricate",
]

# Common auxiliary verbs used in the passive-voice heuristic.
_BE_FORMS = {"is", "are", "was", "were", "be", "been", "being", "am"}
_DIALOGUE_QUOTE_RE = re.compile(r"[“”\"]([^“”\"]+)[“”\"]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])[\"”\)\]]?\s+(?=[\"“\(\[A-Z0-9])")
_WORD_RE = re.compile(r"[A-Za-z']+")
# A clean ending: sentence-final punctuation (incl. an ellipsis), optionally
# followed by closing quotes/brackets, at the very end of the text. Stories
# that end without this were almost certainly clipped by a token limit
# mid-sentence (the "[clipped]" failure the optimizer was producing).
_SENTENCE_FINAL_RE = re.compile(r"[.!?…][\"”’'\)\]]*$")
# Points docked from ``overall`` when a story is detected as truncated.
TRUNCATION_PENALTY = 2.5
_CHAPTER_HEADER_RE = re.compile(r"^#{1,3}\s+(?:chapter\b|ch\.?\s*\d)", re.IGNORECASE | re.MULTILINE)
# Past-participle-ish: a word ending in -ed or a common irregular participle.
_IRREGULAR_PARTICIPLES = {
    "taken", "given", "seen", "done", "made", "held", "told", "found",
    "left", "kept", "built", "broken", "spoken", "written", "driven",
    "known", "shown", "thrown", "grown", "drawn", "worn", "torn", "born",
}


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _sentences(text: str) -> list[str]:
    """Split prose into sentences (good-enough heuristic)."""
    # Drop markdown headers/blank structure so they don't count as sentences.
    cleaned = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.MULTILINE)
    parts = _SENTENCE_SPLIT_RE.split(cleaned.strip())
    return [p.strip() for p in parts if p.strip()]


def _count_syllables(word: str) -> int:
    """Heuristic syllable count for a single word."""
    word = word.lower()
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    # Silent trailing 'e' (but not 'le' endings like "subtle").
    if word.endswith("e") and not word.endswith(("le", "ie", "ee")):
        count -= 1
    return max(1, count)


def _clamp(x: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, x))


class StoryMetrics:
    """Automated quality assessment for generated stories."""

    # Weights for the overall score (sub-scores are all 0-10, higher = better).
    WEIGHTS = {
        "artifact": 0.28,
        "readability": 0.15,
        "variety": 0.17,
        "dialogue": 0.13,
        "pacing": 0.12,
        "repetition": 0.15,
    }

    def compute(
        self,
        text: str,
        bible: Optional[dict] = None,
        critique: Optional[list] = None,
        chapter_word_counts: Optional[list[int]] = None,
    ) -> dict[str, Any]:
        """Return a metrics dict. Scores are 0-10 unless noted.

        Args:
            text: the full story / novel text.
            bible: optional story bible (unused for scoring but accepted for
                API symmetry / future use).
            critique: optional critique issue list; if provided, the count of
                ``prose``-category issues nudges the artifact score up.
            chapter_word_counts: explicit per-chapter word counts for pacing;
                if omitted, chapters are detected from ``## Chapter`` headers.
        """
        text = text or ""
        artifact = self._check_artifacts(text, critique)
        readability_grade = self._flesch_kincaid(text)
        variety_std = self._sentence_variance(text)
        dialogue_ratio = self._dialogue_ratio(text)
        pacing_cv = self._chapter_balance(text, chapter_word_counts)
        repetition = self._check_repetition(text)
        coherence = self._semantic_coherence(text)
        truncated = self._truncation_check(text)

        subscores = {
            "artifact": 10.0 - artifact,                       # lower artifact -> higher score
            "readability": self._readability_subscore(readability_grade),
            "variety": self._variety_subscore(variety_std),
            "dialogue": self._dialogue_subscore(dialogue_ratio),
            "pacing": self._pacing_subscore(pacing_cv),
            "repetition": 10.0 - repetition,                   # lower repetition -> higher score
        }
        overall = sum(subscores[k] * w for k, w in self.WEIGHTS.items())
        # A story clipped mid-sentence is unusable regardless of its prose
        # scores, so dock the overall directly (truncation is a hard failure,
        # not just one weighted dimension among many).
        if truncated:
            overall -= TRUNCATION_PENALTY

        return {
            "ai_artifact_score": round(artifact, 2),           # 0 clean .. 10 riddled (lower better)
            "readability": round(readability_grade, 2),        # Flesch-Kincaid grade level
            "sentence_variety": round(variety_std, 2),         # std dev of sentence length (words)
            "dialogue_ratio": round(dialogue_ratio, 3),        # fraction of words inside quotes
            "pacing_balance": (round(pacing_cv, 3) if pacing_cv is not None else None),  # CV (lower better)
            "repetition_score": round(repetition, 2),          # 0 none .. 10 heavy (lower better)
            "coherence_score": round(coherence, 2),            # 0 recycled .. 10 diverse (higher better)
            "truncated": truncated,                            # True if clipped mid-sentence
            "subscores": {k: round(v, 2) for k, v in subscores.items()},
            "overall": round(_clamp(overall), 2),              # weighted 0-10 (higher better)
            "word_count": len(_words(text)),
        }

    # ── AI artifact detection ───────────────────────────────

    def _check_artifacts(self, text: str, critique: Optional[list] = None) -> float:
        """Score 0 (clean) to 10 (riddled with AI artifacts)."""
        words = _words(text)
        n_words = max(1, len(words))
        lower = text.lower()

        # 1. Crutch word/phrase density (per 1000 words).
        crutch_hits = 0
        for marker in AI_CRUTCH_WORDS:
            crutch_hits += lower.count(marker)
        crutch_density = crutch_hits / n_words * 1000.0
        crutch_score = min(4.0, crutch_density * 1.3)          # ~3 per 1k words -> ~4

        # 2. Three-part anaphora: 3+ consecutive sentences with same opener.
        anaphora_score = min(2.0, self._anaphora_count(text) * 0.7)

        # 3. Em-dash overuse (per 1000 words).
        em_dashes = text.count("—") + text.count(" - ")
        em_density = em_dashes / n_words * 1000.0
        em_score = min(2.0, max(0.0, (em_density - 4.0)) * 0.4)  # tolerate ~4/1k

        # 4. Passive voice percentage.
        passive_pct = self._passive_ratio(text)
        passive_score = min(2.0, max(0.0, (passive_pct - 0.10)) * 12.0)  # tolerate ~10%

        # 5. Critique signal (if an editorial pass already flagged prose issues).
        critique_score = 0.0
        if critique:
            prose_issues = sum(
                1 for it in critique
                if isinstance(it, dict) and "prose" in str(it.get("category", "")).lower()
            )
            critique_score = min(1.0, prose_issues * 0.3)

        return _clamp(crutch_score + anaphora_score + em_score + passive_score + critique_score)

    def _anaphora_count(self, text: str) -> int:
        """Count runs of 3+ consecutive sentences sharing the same first word."""
        sents = _sentences(text)
        starters = []
        for s in sents:
            m = _WORD_RE.search(s)
            starters.append(m.group(0).lower() if m else "")
        runs = 0
        i = 0
        while i < len(starters):
            j = i
            while j + 1 < len(starters) and starters[j + 1] == starters[i] and starters[i]:
                j += 1
            if j - i + 1 >= 3:
                runs += 1
            i = j + 1
        return runs

    def _passive_ratio(self, text: str) -> float:
        """Fraction of sentences containing a be-form + past participle."""
        sents = _sentences(text)
        if not sents:
            return 0.0
        passive = 0
        for s in sents:
            toks = [w.lower() for w in _words(s)]
            for k in range(len(toks) - 1):
                if toks[k] in _BE_FORMS:
                    nxt = toks[k + 1]
                    if nxt.endswith("ed") or nxt in _IRREGULAR_PARTICIPLES:
                        passive += 1
                        break
        return passive / len(sents)

    # ── Readability ─────────────────────────────────────────

    def _flesch_kincaid(self, text: str) -> float:
        """Flesch-Kincaid grade level."""
        sents = _sentences(text)
        words = _words(text)
        if not sents or not words:
            return 0.0
        syllables = sum(_count_syllables(w) for w in words)
        wps = len(words) / len(sents)
        spw = syllables / len(words)
        return _clamp(0.39 * wps + 11.8 * spw - 15.59, 0.0, 20.0)

    def _readability_subscore(self, grade: float) -> float:
        """Reward a grade level in the comfortable-fiction band (~6-11)."""
        if grade <= 0:
            return 0.0
        if 6.0 <= grade <= 11.0:
            return 10.0
        if grade < 6.0:
            return _clamp(10.0 - (6.0 - grade) * 1.5)
        return _clamp(10.0 - (grade - 11.0) * 1.2)

    # ── Sentence variety ────────────────────────────────────

    def _sentence_variance(self, text: str) -> float:
        """Standard deviation of sentence lengths (in words)."""
        lengths = [len(_words(s)) for s in _sentences(text)]
        lengths = [l for l in lengths if l > 0]
        if len(lengths) < 2:
            return 0.0
        mean = sum(lengths) / len(lengths)
        var = sum((l - mean) ** 2 for l in lengths) / len(lengths)
        return math.sqrt(var)

    def _variety_subscore(self, std: float) -> float:
        """Reward varied sentence length; ideal std dev roughly 6-14 words."""
        if std <= 0:
            return 0.0
        if 6.0 <= std <= 16.0:
            return 10.0
        if std < 6.0:
            return _clamp(std / 6.0 * 10.0)
        return _clamp(10.0 - (std - 16.0) * 0.5)

    def short_long_ratio(self, text: str) -> tuple[int, int]:
        """(count of short <10-word sentences, count of long >30-word sentences)."""
        lengths = [len(_words(s)) for s in _sentences(text)]
        return sum(1 for l in lengths if l < 10), sum(1 for l in lengths if l > 30)

    # ── Dialogue ────────────────────────────────────────────

    def _dialogue_ratio(self, text: str) -> float:
        """Fraction of words that sit inside quotation marks."""
        words_total = max(1, len(_words(text)))
        in_quotes = 0
        for m in _DIALOGUE_QUOTE_RE.finditer(text):
            in_quotes += len(_words(m.group(1)))
        return in_quotes / words_total

    def _dialogue_subscore(self, ratio: float) -> float:
        """Ideal fiction dialogue ratio is roughly 15-40%."""
        if 0.15 <= ratio <= 0.40:
            return 10.0
        if ratio < 0.15:
            return _clamp(ratio / 0.15 * 10.0)
        return _clamp(10.0 - (ratio - 0.40) * 16.0)

    # ── Pacing ──────────────────────────────────────────────

    def _split_chapters(self, text: str) -> list[str]:
        """Split a novel into chapter bodies on markdown chapter headers."""
        if not _CHAPTER_HEADER_RE.search(text):
            return []
        # Split keeping content after each header line.
        chunks = re.split(r"^#{1,3}\s+.*$", text, flags=re.MULTILINE)
        return [c.strip() for c in chunks if c.strip()]

    def _chapter_balance(self, text: str, chapter_word_counts: Optional[list[int]]) -> Optional[float]:
        """Coefficient of variation of chapter (or paragraph) word counts.

        Lower = more even pacing. Returns None if there is no usable structure.
        """
        if chapter_word_counts:
            counts = [c for c in chapter_word_counts if c > 0]
        else:
            chapters = self._split_chapters(text)
            if chapters:
                counts = [len(_words(c)) for c in chapters]
            else:
                # Fall back to paragraph spread for unstructured short stories.
                paras = [p for p in re.split(r"\n\s*\n", text) if len(_words(p)) > 5]
                counts = [len(_words(p)) for p in paras]
        if len(counts) < 2:
            return None
        mean = sum(counts) / len(counts)
        if mean == 0:
            return None
        std = math.sqrt(sum((c - mean) ** 2 for c in counts) / len(counts))
        return std / mean

    def _pacing_subscore(self, cv: Optional[float]) -> float:
        """CV under ~0.3 is well-balanced; reward that, penalize spread."""
        if cv is None:
            return 6.0  # neutral when structure is unknown
        if cv <= 0.30:
            return 10.0
        return _clamp(10.0 - (cv - 0.30) * 14.0)

    # ── Repetition ──────────────────────────────────────────

    def _check_repetition(self, text: str, n: int = 6) -> float:
        """Detect distinctive multi-word phrases repeated across the text.

        Scores 0 (no repetition) to 10 (heavy). Targets the exact-phrase
        recycling the editor flagged (e.g. an atmospheric triplet repeated 7x).
        """
        words = [w.lower() for w in _words(text)]
        n_words = max(1, len(words))
        if len(words) < n * 2:
            return 0.0

        grams = Counter()
        for i in range(len(words) - n + 1):
            gram = tuple(words[i : i + n])
            # Skip grams that are almost all stopwords / structural filler.
            if sum(1 for w in gram if len(w) > 3) < 3:
                continue
            grams[gram] += 1

        # Weight by how often a distinctive phrase recurs beyond the first use.
        excess = 0
        repeated_phrases = 0
        for gram, count in grams.items():
            if count >= 2:
                excess += (count - 1)
                repeated_phrases += 1

        # Normalize against length: a repeat per ~250 words is already notable.
        density = excess / n_words * 250.0
        return _clamp(density * 2.2)

    def repeated_phrases(self, text: str, n: int = 6, min_count: int = 2) -> list[tuple[str, int]]:
        """Return the distinctive n-gram phrases repeated >= min_count times."""
        words = _words(text)
        lower = [w.lower() for w in words]
        grams = Counter()
        for i in range(len(lower) - n + 1):
            gram = tuple(lower[i : i + n])
            if sum(1 for w in gram if len(w) > 3) < 3:
                continue
            grams[gram] += 1
        out = [(" ".join(g), c) for g, c in grams.items() if c >= min_count]
        return sorted(out, key=lambda x: -x[1])

    # ── Truncation ──────────────────────────────────────────

    def _truncation_check(self, text: str) -> bool:
        """True if the story was clipped mid-sentence (no terminal punctuation).

        A token limit hit mid-thought leaves prose that ends without sentence-
        final punctuation (often mid-word or mid-clause). Such output is
        unusable in production, so it is flagged and penalized in ``overall``.
        An empty generation is not "truncated" — it is handled as a failure
        elsewhere — so it returns False.
        """
        stripped = (text or "").rstrip()
        if not stripped:
            return False
        return _SENTENCE_FINAL_RE.search(stripped) is None

    # ── Semantic coherence (paragraph-level n-gram diversity) ─

    def _semantic_coherence(self, text: str) -> float:
        """Paragraph-level bigram diversity, 0 (heavy recycling) .. 10 (diverse).

        Measures how much adjacent paragraphs recycle each other's phrasing via
        the Jaccard distance between their word-bigram sets: 1.0 means the two
        paragraphs share no bigrams (fully distinct), 0.0 means identical
        phrasing. The score is the mean distance across all adjacent pairs,
        scaled to 0-10. This catches paragraph-level recycling that the
        surface crutch-word metric misses, without needing BERTScore.

        Returns a neutral-good 10.0 when there are fewer than two comparable
        paragraphs (nothing to recycle).
        """
        paras = [p for p in re.split(r"\n\s*\n", text or "") if len(_words(p)) >= 10]
        if len(paras) < 2:
            return 10.0

        def _bigrams(p: str) -> set[tuple[str, str]]:
            ws = [w.lower() for w in _words(p)]
            return set(zip(ws, ws[1:]))

        grams = [_bigrams(p) for p in paras]
        distances = []
        for a, b in zip(grams, grams[1:]):
            union = a | b
            if not union:
                continue
            distances.append(1.0 - len(a & b) / len(union))   # Jaccard distance
        if not distances:
            return 10.0
        return _clamp(sum(distances) / len(distances) * 10.0)


# ── CLI report ──────────────────────────────────────────────


def format_report(text: str, metrics: dict[str, Any], *, label: str = "") -> str:
    sm = StoryMetrics()
    short, long = sm.short_long_ratio(text)
    pacing = metrics["pacing_balance"]
    pacing_str = f"{pacing:.3f}" if pacing is not None else "n/a"
    lines = [
        f"{'═' * 56}",
        f" STORY METRICS{(' — ' + label) if label else ''}",
        f"{'═' * 56}",
        f"  Words                : {metrics['word_count']}",
        f"  AI artifact score    : {metrics['ai_artifact_score']:.1f}/10   (lower is better)",
        f"  Readability (FK grade): {metrics['readability']:.1f}",
        f"  Sentence variety (σ) : {metrics['sentence_variety']:.1f} words   "
        f"(short<10: {short}, long>30: {long})",
        f"  Dialogue ratio       : {metrics['dialogue_ratio'] * 100:.1f}%",
        f"  Pacing balance (CV)  : {pacing_str}   (lower is better)",
        f"  Repetition score     : {metrics['repetition_score']:.1f}/10   (lower is better)",
        f"  Coherence score      : {metrics['coherence_score']:.1f}/10   (higher is better)",
        f"  Truncated mid-sentence: {'YES — clipped!' if metrics['truncated'] else 'no'}",
        f"{'─' * 56}",
        "  Sub-scores (0-10, higher better):",
    ]
    for k, v in metrics["subscores"].items():
        lines.append(f"    {k:<12}: {v:.1f}")
    lines += [
        f"{'─' * 56}",
        f"  OVERALL              : {metrics['overall']:.1f}/10",
        f"{'═' * 56}",
    ]
    repeats = sm.repeated_phrases(text, min_count=3)
    if repeats:
        lines.append("  Repeated phrases (>=3x):")
        for phrase, count in repeats[:6]:
            lines.append(f"    {count}x  \"{phrase}\"")
        lines.append(f"{'═' * 56}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python engine/metrics.py <story.md> [more.md ...]", file=sys.stderr)
        return 2
    sm = StoryMetrics()
    for path in argv[1:]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            print(f"cannot read {path}: {exc}", file=sys.stderr)
            continue
        metrics = sm.compute(text)
        print(format_report(text, metrics, label=path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
