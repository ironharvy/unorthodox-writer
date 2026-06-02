#!/usr/bin/env python3
"""
DSPy story-prompt optimizer — v2 (instruction optimization with gold demos).

Why v2 exists
-------------
v1 ran ``BootstrapFewShot`` with a small local model (qwen3:latest, 8B). It
bootstrapped that *weak* model's own mediocre generations into "good"
demonstrations, which simply taught the model to produce more of the same
artifacts. Quality regressed (8.01 → 7.79).

v2 fixes the two root causes:

  1. **High-quality gold demonstrations.** Instead of bootstrapping a weak
     model's output, we generate the demonstration stories with DeepSeek
     (cloud, strong) via :class:`engine.backends.cloud.CloudBackend`, score them
     with :class:`engine.metrics.StoryMetrics`, and keep only the best
     (overall ≥ 7.5). Those become DSPy ``Example`` rows carrying a *gold*
     ``story_text``, so the optimizer can show the local model genuinely good
     prose as labeled few-shot demos — not its own recycled artifacts.

  2. **Few-shot selection, not instruction search.** An earlier cut of v2 used
     ``MIPROv2`` to also optimize the *instruction*, but the Dreamer's telemetry
     analysis (idea 20260602-2002-001) showed that search actively degraded
     quality (composite Δ -0.011 across 3 seeds). We now use a simple
     :class:`FewShotOptimizer`: it ranks the gold demos by composite score,
     attaches the best 4 as labeled few-shot examples, and freezes the
     instruction. Deterministic — no Bayesian search, no ``optuna``.

Composite metric
----------------
The optimization objective is reference-free and balances overall quality,
artifact-cleanliness, and paragraph-level coherence::

    composite = 0.6 * (overall / 10)
              + 0.3 * (1 - ai_artifact_score / 10)
              + 0.1 * (coherence / 10)

It is a *fast heuristic signal* for prompt search, not a literary judgment —
see the ``--editorial`` flag and the note saved in the run report.

Model strategy
--------------
  * Demo generation : DeepSeek (paid quality) — the gold training stories.
  * Optimization LM : qwen3.6:27b (best local quality) — generates stories with
                      the selected few-shot demos at evaluation/inference time.

If DeepSeek is unavailable *or unreachable*, demo generation falls back to the
local model with a higher quality bar (≥ 8.5).

Robustness / reproducibility
----------------------------
  * Config is read at *runtime* (after ``.env`` loading) into a :class:`Config`
    dataclass, so ``.env`` values actually take effect.
  * Few-shot selection is deterministic, so the run is reproducible: the report
    carries the exact baseline → optimized delta and a verdict that only claims
    improvement when the composite delta is positive.

Outputs (written to ``test_output/``)
-------------------------------------
  * ``optimized_v2.json``        — the optimized DSPy program (best 4 demos).
  * ``optimized_v2_report.json`` — full run report: baseline + optimized scores,
                                    per-premise breakdowns, the baseline→optimized
                                    delta + verdict, demo provenance + which demos
                                    were selected, model id, timestamp, runtime.
  * ``optimized_v2_editorial.md`` — only with ``--editorial``: baseline vs
                                    optimized prose, side by side, for a human
                                    editorial review slice.

Usage::

    PYTHONPATH=. python engine/optimizer.py [--editorial]

Tunable via env: ``OLLAMA_URL``, ``OPTIMIZER_TASK_MODEL`` (default qwen3.6:27b),
``OPTIMIZER_DEMO_THRESHOLD`` (default 7.5).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.metrics import StoryMetrics
from engine.backends.cloud import CloudBackend
from engine.backends.ollama import OllamaBackend

# ── Static defaults (overridable via env at runtime; see Config) ─────────────
DEFAULT_URL = "http://192.168.1.20:11434"
DEFAULT_TASK_MODEL = "qwen3.6:27b"
# Demo quality bar. Lowered 8.0 → 7.5 (Dreamer idea 20260602-2002-002): the
# 8.0 cutoff discarded 6-7 DeepSeek demos scoring 7.4-7.9 — still well above the
# task model's own baseline — which starved the few-shot pool and made the
# prompt brittle across seeds. 7.5 retains those diverse, above-baseline demos.
DEFAULT_DEMO_THRESHOLD = 7.5
DEMO_THRESHOLD_FALLBACK = 8.5  # stricter bar when demos come from the local model
N_GOLD_DEMOS = 8        # size of the scored gold-demo pool to keep
N_FEWSHOT_DEMOS = 4     # how many of the pool become labeled few-shot examples
GEN_MAX_TOKENS = 512
# Below this parameter count a task model is too instruction-sensitive for
# reliable prompt optimization (Dreamer idea 20260602-2002-005).
MIN_OPTIMIZATION_PARAM_B = 10.0

_METRICS = StoryMetrics()

_EDITORIAL_NOTE = (
    "Metric scores are fast heuristic signals for prompt optimization, not "
    "literary judgments. Crutch-word counting can reward prompts that merely "
    "avoid specific phrases rather than tell better stories. Optimized outputs "
    "should pass a human editorial review slice (see --editorial) before "
    "deployment."
)


# ── Runtime configuration (issue #1: populated AFTER .env is loaded) ─────────
@dataclass
class Config:
    """All tunables, read from the environment at runtime.

    Built by :meth:`from_env` *after* ``_load_env_from_dotenv()`` runs, so values
    placed in the repo ``.env`` actually take effect (the old module-level
    constants were bound at import time, before the ``.env`` was sourced).
    """

    url: str
    task_model: str
    demo_threshold: float
    demo_threshold_fallback: float
    n_gold_demos: int
    n_fewshot_demos: int
    gen_max_tokens: int
    editorial: bool
    out_dir: Path
    optimized_path: Path
    report_path: Path
    editorial_path: Path = field(default=None)  # type: ignore[assignment]

    @classmethod
    def from_env(cls, *, editorial: bool = False) -> "Config":
        out_dir = REPO_ROOT / "test_output"
        return cls(
            url=os.environ.get("OLLAMA_URL", DEFAULT_URL),
            task_model=os.environ.get("OPTIMIZER_TASK_MODEL", DEFAULT_TASK_MODEL),
            demo_threshold=float(os.environ.get("OPTIMIZER_DEMO_THRESHOLD",
                                                 str(DEFAULT_DEMO_THRESHOLD))),
            demo_threshold_fallback=DEMO_THRESHOLD_FALLBACK,
            n_gold_demos=N_GOLD_DEMOS,
            n_fewshot_demos=N_FEWSHOT_DEMOS,
            gen_max_tokens=GEN_MAX_TOKENS,
            editorial=editorial,
            out_dir=out_dir,
            optimized_path=out_dir / "optimized_v2.json",
            report_path=out_dir / "optimized_v2_report.json",
            editorial_path=out_dir / "optimized_v2_editorial.md",
        )


# Parameter-size token in a model tag, e.g. the "27b" in "qwen3.6:27b" or the
# "4b" in "nemotron-3-nano:4b". Only the tag *after* the colon is inspected so
# the "3" in "qwen3" is never mistaken for a parameter count.
_PARAM_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def _model_param_billions(model: str) -> float | None:
    """Best-effort parameter count (in billions) parsed from a model tag.

    ``qwen3.6:27b`` → 27.0, ``nemotron-3-nano:4b`` → 4.0, ``qwen3:latest`` →
    None (no size encoded in the tag).
    """
    tag = model.split(":", 1)[1] if ":" in model else model
    m = _PARAM_SIZE_RE.search(tag)
    return float(m.group(1)) if m else None


def _warn_if_small_task_model(cfg: "Config") -> None:
    """Warn when the optimization task model is too small to be reliable.

    Dreamer idea 20260602-2002-005: the qwen3:latest (8B) verify run regressed
    while the qwen3.6:27b run did not — small models are too sensitive to
    instruction changes for the optimizer to trust their deltas.
    """
    size = _model_param_billions(cfg.task_model)
    if size is not None and size < MIN_OPTIMIZATION_PARAM_B:
        print(
            f"  ⚠ Warning: models under {MIN_OPTIMIZATION_PARAM_B:g}B parameters "
            f"(task_model '{cfg.task_model}' is ~{size:g}B) may be too sensitive "
            "to instruction changes for reliable optimization. Consider using "
            "qwen3.6:27b or larger for optimization runs.\n"
        )


# ── Training / validation / test premises ───────────────────
# Specific protagonist + concrete setting + an unusual constraint, with an
# emotional hook that demands interiority and sensory detail. Deliberately
# diverse in genre, voice, and story shape (no "X discovers Y" formulas).
TRAIN_PREMISES = [
    ("A glassblower who has gone deaf shapes a vase meant to hold the last sound she remembers: her mother's laugh.", "literary", "lyrical"),
    ("On the night shift at a 24-hour laundromat, an insomniac folds strangers' clothes and finds a wedding dress that fits her exactly.", "literary", "intimate"),
    ("A border-town radio DJ takes a midnight song request from a caller who has been dead for nine years.", "magical realism", "warm"),
    ("A bomb-disposal veteran now works as a marriage counselor, until a couple sets a literal ticking box on his desk.", "dark comedy", "wry"),
    ("A lighthouse keeper's daughter learns to read the names of drowned sailors in the patterns of the foam.", "fantasy", "atmospheric"),
    ("A subway busker plays a cello missing one string and swears the gap is where the best notes live.", "literary", "musical"),
    ("In a village where everyone shares a single communal memory, a girl is born remembering things no one else does.", "speculative", "spare"),
    ("A taxidermist falls for the widow who keeps bringing in the same sparrow to be remounted.", "gothic", "tender"),
    ("A retired astronaut waters the tomatoes on his balcony, counting the seconds the way he once counted re-entry.", "literary", "quiet"),
    ("A short-order cook at a desert-edge diner serves a stranger who orders only what he ate the day his daughter was born.", "noir", "lean"),
    ("A girl who collects lightning in mason jars must decide whether to free the storm that took her brother.", "fantasy", "vivid"),
    ("A tribunal translator begins dreaming in the language of the man whose war crimes she is condemning.", "literary", "tense"),
    ("A night-train conductor punches tickets for passengers boarding at stations that no longer exist.", "magical realism", "haunting"),
    ("An ice-road trucker hauls a sealed cargo she is forbidden to open, and the knocking inside keeps time with her heart.", "thriller", "cinematic"),
]

# A held-out validation slice (no gold needed — the metric is reference-free),
# distinct from train and test. Retained for ad-hoc validation; the
# FewShotOptimizer's demo selection is deterministic and needs no val search.
VAL_PREMISES = [
    ("A clockmaker repairs a pocket watch that runs backward and finds himself aging in reverse with it.", "fantasy", "atmospheric"),
    ("A hospice nurse teaches a dying sailor to tie the knots he can no longer see.", "literary", "tender"),
    ("A street magician's final trick is to make himself forgotten by the city that once loved him.", "magical realism", "wistful"),
    ("A beekeeper among glass towers realizes her bees are mapping a language in their dance.", "speculative", "lyrical"),
    ("A diner waitress still recites the orders of regulars who vanished in a flood ten years ago.", "literary", "spare"),
]

# Held-out, never seen by the optimizer — used only for the before/after report.
# Issue #6: 10 test premises (was 5) so per-premise variance is visible.
TEST_PREMISES = [
    ("A cartographer is hired to map a town that appears on no other map.", "literary", "atmospheric"),
    ("A boy inherits a coat whose pockets hold other people's memories.", "fantasy", "poetic"),
    ("A detective interrogates a suspect who answers only in descriptions of the weather.", "noir", "minimalist"),
    ("A widowed organist plays the cathedral empty every midnight for an audience of one he won't name.", "gothic", "haunting"),
    ("A deep-sea welder repairs a pipeline and hears, in the dark, singing that matches his late wife's hum.", "literary", "cinematic"),
    ("A florist who is losing her sense of smell presses one last bouquet for a wedding she was not invited to.", "literary", "tender"),
    ("A war photographer develops a roll of film and finds a face in the crowd that has followed her across three countries.", "thriller", "tense"),
    ("On the last day of a dying carousel, the ticket-taker lets a girl ride the one horse that was never bolted down.", "magical realism", "wistful"),
    ("A locksmith who can open any door is asked to lock one shut forever, and is paid not to ask why.", "noir", "lean"),
    ("A beekeeper's son tends the hives through the winter his father stopped speaking, listening for what the bees might say back.", "literary", "quiet"),
]


# System prompt that steers DeepSeek toward prose the metric rates highly:
# concrete sensing, interiority, varied sentence length, a little natural
# dialogue, and none of the AI crutch markers the artifact detector punishes.
DEMO_SYSTEM = (
    "You are an award-winning literary short-fiction writer. Write a single, "
    "self-contained ~250-word story section (240-275 words). Requirements:\n"
    "- Structure it as 4 to 5 paragraphs of ROUGHLY EQUAL length (even pacing).\n"
    "- Include 3 to 5 short lines of natural dialogue, totaling about a quarter "
    "to a third of the words (25-35%). Give the speakers distinct, human voices.\n"
    "- Ground every paragraph in concrete, specific sensory detail (sight, "
    "sound, smell, touch) and real interiority — what the character notices, "
    "fears, wants.\n"
    "- Vary sentence length sharply: mix short, punchy sentences with longer "
    "flowing ones.\n"
    "- Use plain, vivid, accessible language (a general adult reader should "
    "follow it easily); avoid dense, over-latinate sentences.\n"
    "- NEVER use these crutch words/phrases: however, moreover, furthermore, "
    "delve, tapestry, testament to, indeed, palpable, a symphony of, intricate, "
    "woven, navigate the complexities, in the realm of, little did.\n"
    "- Avoid the passive voice, avoid em-dash overuse, and never repeat a "
    "distinctive phrase.\n"
    "- Do not exceed the word limit. If you approach it, finish the current "
    "sentence cleanly. Never truncate mid-sentence or mid-paragraph.\n"
    "- Open in the middle of a moment. Output ONLY the story prose — no title, "
    "no preamble, no notes."
)


def _demo_user_prompt(premise: str, genre: str, style: str) -> str:
    return (
        f"Premise: {premise}\n"
        f"Genre: {genre}\n"
        f"Style: {style}\n\n"
        "Write the story section now."
    )


# ── Metric ──────────────────────────────────────────────────
def composite_metric(example, pred, trace=None) -> float:
    """Reference-free objective in [0, 1].

    Composite of overall quality, an inverted artifact penalty, and paragraph-
    level semantic coherence, so the optimizer is rewarded for good prose, the
    absence of AI crutches, AND non-recycled paragraph phrasing::

        0.6 * (overall / 10) + 0.3 * (1 - ai_artifact_score / 10) + 0.1 * (coherence / 10)

    Dreamer idea 20260602-2002-004: the artifact weight dropped 0.4 → 0.3
    because crutch-word counting rewards surface patterns rather than better
    stories; the freed 0.1 now rewards the new coherence metric, which catches
    paragraph-level recycling the crutch-word detector cannot see.
    """
    text = getattr(pred, "story_text", "") or ""
    if len(text.split()) < 40:
        return 0.0
    m = _METRICS.compute(text)
    artifact_penalty = 1.0 - (m["ai_artifact_score"] / 10.0)
    coherence = m["coherence_score"] / 10.0
    return 0.6 * (m["overall"] / 10.0) + 0.3 * artifact_penalty + 0.1 * coherence


# ── DSPy signature ──────────────────────────────────────────
def _build_signature(dspy):
    class StorySignature(dspy.Signature):
        """Write a vivid ~250-word short story section in the given genre and
        style. Use concrete sensory detail and real interiority. Avoid cliché
        and AI crutch transitions (however/moreover/furthermore). Vary sentence
        length. Do not exceed the word limit; if you approach it, finish the
        current sentence cleanly — never truncate mid-sentence or mid-paragraph.
        Output only the story prose."""

        premise = dspy.InputField(desc="Story premise / seed idea")
        genre = dspy.InputField(desc="Target genre")
        style = dspy.InputField(desc="Prose style")
        story_text = dspy.OutputField(desc="The generated story prose, ~250 words, no preamble")

    return StorySignature


# ── DeepSeek (or local) gold-demo generation ────────────────
async def _generate_demos(backend, premises, label: str) -> list[dict]:
    """Generate one story per premise concurrently, score each with StoryMetrics.

    Per-item failures are swallowed (and counted) so a few flaky calls do not
    abort the batch. The caller treats an *empty* result as "this backend is
    unusable" and falls back (issue #2).
    """
    sem = asyncio.Semaphore(6)
    failures = 0

    async def one(idx, premise, genre, style):
        nonlocal failures
        async with sem:
            try:
                text = await backend.generate_full(
                    _demo_user_prompt(premise, genre, style), system_prompt=DEMO_SYSTEM
                )
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"    [{idx + 1}/{len(premises)}] generation failed: {exc}")
                return None
        text = (text or "").strip()
        if len(text.split()) < 40:
            return None
        m = _METRICS.compute(text)
        comp = composite_metric(None, type("P", (), {"story_text": text})())
        print(
            f"    [{idx + 1}/{len(premises)}] overall={m['overall']:.2f} "
            f"artifact={m['ai_artifact_score']:.2f} dialogue={m['dialogue_ratio'] * 100:.0f}% "
            f"words={m['word_count']} comp={comp:.3f}"
        )
        return {
            "premise": premise, "genre": genre, "style": style,
            "text": text, "metrics": m, "composite": comp,
        }

    print(f"  generating {len(premises)} demo stories with {label}...")
    try:
        results = await asyncio.gather(*(one(i, p, g, s) for i, (p, g, s) in enumerate(premises)))
    finally:
        await backend.close()
    if failures:
        print(f"  ({failures}/{len(premises)} {label} generations failed)")
    return [r for r in results if r is not None]


def _gather_gold_demos(cfg: Config) -> tuple[list[dict], str, float]:
    """Generate the gold demonstration stories, with a working DeepSeek fallback.

    Returns ``(scored_demos, source_label, threshold_used)``.

    Issue #2: the fallback to the local model now fires whenever DeepSeek yields
    *no usable demos* — whether the key is absent OR the key is present but the
    API is unreachable/erroring — not only when the key is missing.
    """
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        print("  attempting DeepSeek (cloud) for gold demos...")
        backend = CloudBackend(provider="deepseek", max_tokens=600)
        try:
            scored = asyncio.run(_generate_demos(backend, TRAIN_PREMISES, "DeepSeek"))
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠ DeepSeek demo generation raised: {exc}")
            scored = []
        if scored:
            return scored, "DeepSeek", cfg.demo_threshold
        print("  ⚠ DeepSeek produced no usable demos (key set but API "
              "unreachable/erroring).")
        print(f"    Falling back to local {cfg.task_model} with stricter bar "
              f"{cfg.demo_threshold_fallback:.1f}.")
    else:
        print(f"  (no DEEPSEEK_API_KEY — using local {cfg.task_model} for demos, "
              f"bar {cfg.demo_threshold_fallback:.1f})")

    backend = OllamaBackend(base_url=cfg.url, model=cfg.task_model,
                            temperature=0.8, num_ctx=8192, think=False)
    scored = asyncio.run(_generate_demos(backend, TRAIN_PREMISES, cfg.task_model))
    return scored, cfg.task_model, cfg.demo_threshold_fallback


def _select_top_demos(scored: list[dict], threshold: float, k: int) -> list[dict]:
    """Keep stories at/above the quality bar, best composite first, up to k.

    Issue #3: if fewer than ``k`` clear the bar we top up with the next-best
    below-threshold demos, but we now print an explicit warning AND tag each
    filler demo with ``below_threshold=True`` so the saved metadata makes the
    compromise auditable. Gold demos are tagged ``below_threshold=False``.
    """
    passing = [r for r in scored if r["metrics"]["overall"] >= threshold]
    passing.sort(key=lambda r: r["composite"], reverse=True)
    for r in passing:
        r["below_threshold"] = False

    if len(passing) >= k:
        return passing[:k]

    rest = [r for r in scored if r not in passing]
    rest.sort(key=lambda r: r["composite"], reverse=True)
    filler = rest[: k - len(passing)]
    for r in filler:
        r["below_threshold"] = True

    if filler:
        print(f"  ⚠ {len(filler)} demo(s) below threshold {threshold:.1f}/10 used as "
              f"filler — these are NOT gold quality.")
        for r in filler:
            print(f"      filler: overall={r['metrics']['overall']:.2f} "
                  f"comp={r['composite']:.3f} | {r['premise'][:58]}…")
    return passing + filler


# ── Evaluation ──────────────────────────────────────────────
def _evaluate(program, premises, label: str) -> dict:
    """Run the program on every premise and score the prose.

    Rows retain ``story_text`` so the ``--editorial`` slice can dump real prose;
    the JSON report strips the text and keeps only the scalar metrics.
    """
    rows, total_overall, total_artifact, total_comp = [], 0.0, 0.0, 0.0
    t0 = time.time()
    for premise, genre, style in premises:
        try:
            pred = program(premise=premise, genre=genre, style=style)
            text = getattr(pred, "story_text", "") or ""
        except Exception as exc:  # noqa: BLE001
            print(f"    [eval:{label}] generation failed for «{premise[:48]}…»: {exc}")
            text = ""
        m = _METRICS.compute(text)
        comp = composite_metric(None, type("P", (), {"story_text": text})())
        rows.append({"premise": premise, "genre": genre, "style": style,
                     "story_text": text, "metrics": m, "composite": comp})
        total_overall += m["overall"]
        total_artifact += m["ai_artifact_score"]
        total_comp += comp
    n = max(1, len(premises))
    return {
        "label": label,
        "avg_overall": total_overall / n,
        "avg_artifact": total_artifact / n,
        "avg_composite": total_comp / n,
        "elapsed": time.time() - t0,
        "rows": rows,
    }


def _per_premise(ev: dict) -> list[dict]:
    """Serializable per-premise scores (no prose) for the report (issue #6)."""
    return [
        {
            "premise": r["premise"],
            "overall": round(r["metrics"]["overall"], 2),
            "artifact": round(r["metrics"]["ai_artifact_score"], 2),
            "coherence": round(r["metrics"]["coherence_score"], 2),
            "truncated": bool(r["metrics"].get("truncated", False)),
            "composite": round(r["composite"], 4),
        }
        for r in ev["rows"]
    ]


def _count_truncated(ev: dict) -> int:
    """Number of stories in an evaluation that were clipped mid-sentence."""
    return sum(1 for r in ev["rows"] if r["metrics"].get("truncated"))


# ── Few-shot optimizer (replaces MIPROv2; Dreamer idea 20260602-2002-001) ──
class FewShotOptimizer:
    """Few-shot-only prompt optimizer.

    MIPROv2's instruction search *degraded* the composite objective (Δ -0.011
    across 3 seeds), so this optimizer drops the instruction search entirely and
    keeps only what worked — the gold DeepSeek demos. It ranks the gold demos by
    their composite score, attaches the best ``k`` as labeled few-shot examples,
    and freezes the signature instruction. Deterministic given the demo set: no
    Bayesian search, no ``optuna``.
    """

    def __init__(self, dspy_mod, signature, *, k: int = N_FEWSHOT_DEMOS):
        self._dspy = dspy_mod
        self._signature = signature
        self.k = k
        self.selected: list = []          # the chosen few-shot Example rows

    @staticmethod
    def _demo_composite(example) -> float:
        """Composite score of a demo's gold story (the ranking key)."""
        text = getattr(example, "story_text", "") or ""
        return composite_metric(None, type("P", (), {"story_text": text})())

    def compile(self, trainset: list):
        """Rank ``trainset`` by demo composite, attach the best ``k`` as demos.

        Returns a :class:`dspy.Predict` program carrying the selected demos; it
        uses the frozen signature instruction at inference time.
        """
        ranked = sorted(trainset, key=self._demo_composite, reverse=True)
        self.selected = ranked[: self.k]
        program = self._dspy.Predict(self._signature)
        program.demos = list(self.selected)
        return program


# ── Verdict ─────────────────────────────────────────────────
def _verdict(comp_mean: float, comp_std: float, n_seeds: int) -> tuple[str, bool]:
    """Only claim improvement if the mean delta > 0 AND the spread clears zero.

    Few-shot selection is deterministic, so the normal call is a single
    comparison (``comp_std=0``, ``n_seeds=1``) and the verdict turns purely on
    the sign of the exact composite delta.
    """
    reliable = comp_mean > 0 and (comp_mean - comp_std) > 0
    spread = "deterministic — no variance" if n_seeds < 2 else f"±{comp_std:.3f}"
    if reliable:
        return (f"✓ optimized prompt reliably improved the composite objective "
                f"(Δ {comp_mean:+.3f} {spread})", True)
    if comp_mean > 0.005:
        return (f"≈ composite improved on average (Δ {comp_mean:+.3f} {spread}) but "
                f"the spread crosses zero — NOT a reliable improvement", False)
    if abs(comp_mean) <= 0.005:
        return (f"≈ no significant change (composite Δ {comp_mean:+.3f} {spread})", False)
    return (f"✗ optimized prompt scored lower (composite Δ {comp_mean:+.3f} {spread})", False)


# ── Editorial slice (issue #8) ──────────────────────────────
def _write_editorial(path: Path, before: dict, after: dict, cfg: Config,
                     demo_source: str) -> None:
    """Dump baseline vs optimized prose, side by side, for a human review pass."""
    lines = [
        "# Optimized v2 — editorial review slice",
        "",
        f"> {_EDITORIAL_NOTE}",
        "",
        f"- task_model: `{cfg.task_model}`  ·  demo source: `{demo_source}`  ·  "
        f"optimizer: `FewShotOptimizer (best {cfg.n_fewshot_demos} demos)`",
        "- Read each pair below and judge the *prose*, not the numbers. The "
        "metric guided the search; it does not certify the result.",
        "",
        "---",
        "",
    ]
    for b, a in zip(before["rows"], after["rows"]):
        lines.append(f"## {b['premise']}")
        lines.append("")
        lines.append(f"_genre: {b['genre']} · style: {b['style']}_")
        lines.append("")
        lines.append(f"**Baseline** — overall {b['metrics']['overall']:.2f}, "
                     f"artifact {b['metrics']['ai_artifact_score']:.2f}, "
                     f"composite {b['composite']:.3f}")
        lines.append("")
        lines.append((b["story_text"].strip() or "_(empty generation)_"))
        lines.append("")
        lines.append(f"**Optimized** — overall {a['metrics']['overall']:.2f}, "
                     f"artifact {a['metrics']['ai_artifact_score']:.2f}, "
                     f"composite {a['composite']:.3f}")
        lines.append("")
        lines.append((a["story_text"].strip() or "_(empty generation)_"))
        lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Main ────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _load_env_from_dotenv()
    cfg = Config.from_env(editorial=args.editorial)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)  # issue #5: ensure dir exists

    t_start = time.time()
    print(f"\n=== DSPy story-prompt optimizer v2 — FewShotOptimizer "
          f"(task_model={cfg.task_model}, {cfg.url}) ===")
    print(f"    demo_threshold={cfg.demo_threshold:.1f}  "
          f"few-shot demos={cfg.n_fewshot_demos}  editorial={cfg.editorial}\n")
    _warn_if_small_task_model(cfg)

    try:
        import dspy
    except ImportError:
        print("✗ dspy not installed. Run: pip install dspy")
        return 1

    # 1. Gold demonstration stories ----------------------------------------
    print("STEP 1 — generate gold demonstration stories")
    scored, demo_source, demo_threshold = _gather_gold_demos(cfg)
    if not scored:
        print("✗ no demo stories were generated (DeepSeek and local both failed); "
              "cannot proceed.")
        return 1
    gold = _select_top_demos(scored, demo_threshold, cfg.n_gold_demos)
    avg_gold = sum(r["metrics"]["overall"] for r in gold) / len(gold)
    n_filler = sum(1 for r in gold if r.get("below_threshold"))
    print(f"  → kept {len(gold)} demo(s) from {demo_source}; avg overall "
          f"{avg_gold:.2f}/10 (bar {demo_threshold:.1f}); {n_filler} below-bar filler\n")

    # 2. Configure the local optimization LM -------------------------------
    print("STEP 2 — configure optimization LM")
    task_model_id = f"ollama_chat/{cfg.task_model}"
    try:
        task_lm = dspy.LM(
            task_model_id, api_base=cfg.url, api_key="",
            temperature=0.0, max_tokens=cfg.gen_max_tokens, think=False,
            num_ctx=8192,  # headroom so few-shot demos are never truncated
        )
        dspy.configure(lm=task_lm)
        _ = task_lm("Reply with the single word: ready")  # connectivity smoke test
        print(f"  ✓ {cfg.task_model} reachable at {cfg.url}\n")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not reach Ollama/DSPy LM: {exc}")
        print("  (Is the model pulled and the server reachable?)")
        return 1

    # FewShotOptimizer does not propose instructions, so no separate prompt LM
    # is needed — DeepSeek is used only for gold demo generation (STEP 1).
    Signature = _build_signature(dspy)

    # 3. Baseline evaluation (deterministic — computed once) ----------------
    print("STEP 3 — evaluate BASELINE (unoptimized prompt) on held-out premises")
    baseline = dspy.Predict(Signature)
    before = _evaluate(baseline, TEST_PREMISES, "baseline")
    print(f"  baseline avg overall: {before['avg_overall']:.2f}/10  "
          f"(artifact {before['avg_artifact']:.2f}, composite {before['avg_composite']:.3f})  "
          f"[{before['elapsed']:.0f}s]\n")

    # 4. Few-shot optimization (deterministic: rank gold demos, keep best k) -
    k = min(cfg.n_fewshot_demos, len(gold))
    print(f"STEP 4 — FewShotOptimizer: rank {len(gold)} gold demo(s), keep best {k}")
    trainset = [
        dspy.Example(premise=r["premise"], genre=r["genre"], style=r["style"],
                     story_text=r["text"]).with_inputs("premise", "genre", "style")
        for r in gold
    ]
    optimizer = FewShotOptimizer(dspy, Signature, k=k)
    optimized = optimizer.compile(trainset)
    selected_premises = {ex.premise for ex in optimizer.selected}
    print(f"  selected {len(optimizer.selected)} few-shot demo(s) by composite score:")
    for ex in optimizer.selected:
        print(f"      comp={FewShotOptimizer._demo_composite(ex):.3f} | {ex.premise[:60]}…")
    print()

    # 5. Evaluate baseline vs optimized + verdict --------------------------
    print("STEP 5 — evaluate OPTIMIZED program (best-demo few-shot) on held-out premises")
    after = _evaluate(optimized, TEST_PREMISES, "optimized")
    d_overall = after["avg_overall"] - before["avg_overall"]
    d_artifact = after["avg_artifact"] - before["avg_artifact"]
    d_comp = after["avg_composite"] - before["avg_composite"]
    verdict, reliable = _verdict(d_comp, 0.0, 1)
    n_trunc_base = _count_truncated(before)
    n_trunc_opt = _count_truncated(after)
    n_test = len(TEST_PREMISES)

    print("═" * 68)
    print(" BASELINE → OPTIMIZED (held-out test set)")
    print("═" * 68)
    print(f"  overall  : {before['avg_overall']:.2f} → {after['avg_overall']:.2f}  "
          f"(Δ {d_overall:+.2f})")
    print(f"  artifact : {before['avg_artifact']:.2f} → {after['avg_artifact']:.2f}  "
          f"(Δ {d_artifact:+.2f})   (lower is better)")
    print(f"  composite: {before['avg_composite']:.3f} → {after['avg_composite']:.3f}  "
          f"(Δ {d_comp:+.3f})")
    print(f"  truncated: baseline {n_trunc_base}/{n_test} → optimized {n_trunc_opt}/{n_test} "
          f"clipped mid-sentence")
    print(f"  verdict  : {verdict}")
    print("═" * 68)
    print(f"  note: {_EDITORIAL_NOTE}")
    print("═" * 68 + "\n")

    # 6. Persist the optimized program + full report -----------------------
    try:
        optimized.save(str(cfg.optimized_path))
        print(f"  saved optimized program → {cfg.optimized_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not save optimized program: {exc})")

    report = {
        "schema": "optimized_v2_report/2",
        "optimizer": "FewShotOptimizer",
        "generated_at": _utc_now_iso(),
        "total_runtime_sec": round(time.time() - t_start, 1),
        "note": _EDITORIAL_NOTE,
        "config": {
            "task_model": cfg.task_model,
            "task_model_id": task_model_id,
            "ollama_url": cfg.url,
            "demo_threshold": demo_threshold,
            "n_fewshot_demos": k,
            "n_train_premises": len(TRAIN_PREMISES),
            "n_test_premises": n_test,
        },
        "demos": {
            "source": demo_source,
            "count": len(gold),
            "avg_overall": round(avg_gold, 3),
            "threshold": demo_threshold,
            "n_below_threshold": n_filler,
            "items": [
                {
                    "premise": r["premise"],
                    "genre": r["genre"],
                    "style": r["style"],
                    "overall": round(r["metrics"]["overall"], 2),
                    "artifact": round(r["metrics"]["ai_artifact_score"], 2),
                    "coherence": round(r["metrics"]["coherence_score"], 2),
                    "composite": round(r["composite"], 4),
                    "below_threshold": bool(r.get("below_threshold", False)),
                    "selected": r["premise"] in selected_premises,
                }
                for r in gold
            ],
        },
        "baseline": {
            "avg_overall": round(before["avg_overall"], 3),
            "avg_artifact": round(before["avg_artifact"], 3),
            "avg_composite": round(before["avg_composite"], 4),
            "elapsed_sec": round(before["elapsed"], 1),
            "n_truncated": n_trunc_base,
            "per_premise": _per_premise(before),
        },
        "optimized": {
            "avg_overall": round(after["avg_overall"], 3),
            "avg_artifact": round(after["avg_artifact"], 3),
            "avg_composite": round(after["avg_composite"], 4),
            "elapsed_sec": round(after["elapsed"], 1),
            "n_truncated": n_trunc_opt,
            "per_premise": _per_premise(after),
        },
        "delta": {
            "overall": round(d_overall, 3),
            "artifact": round(d_artifact, 3),
            "composite": round(d_comp, 4),
        },
        "reliable_improvement": reliable,
        "verdict": verdict,
    }
    try:
        cfg.report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
        print(f"  saved run report → {cfg.report_path}")
    except OSError as exc:
        print(f"  (could not save run report: {exc})")

    # 7. Editorial slice (issue #8) ----------------------------------------
    if cfg.editorial:
        try:
            _write_editorial(cfg.editorial_path, before, after, cfg, demo_source)
            print(f"  saved editorial review slice → {cfg.editorial_path}")
        except OSError as exc:
            print(f"  (could not save editorial slice: {exc})")

    print()
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DSPy story-prompt optimizer v2 (FewShotOptimizer + gold demos)."
    )
    parser.add_argument(
        "--editorial", action="store_true",
        help="Also save optimized vs baseline prose to "
             "test_output/optimized_v2_editorial.md for a human review pass.",
    )
    return parser.parse_args(argv)


def _load_env_from_dotenv() -> None:
    """Load DEEPSEEK_* / OLLAMA_URL from the repo .env if not already set.

    Mirrors ``source .env`` for the few keys this script needs, so the optimizer
    runs the same way under a bare ``PYTHONPATH=. python engine/optimizer.py``.
    Runs BEFORE :meth:`Config.from_env`, so .env values reach the config (issue #1).
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    wanted = {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "OLLAMA_URL"}
    try:
        for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key in wanted and not os.environ.get(key):
                os.environ[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
