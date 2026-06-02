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
     (overall ≥ 8.0). Those become DSPy ``Example`` rows carrying a *gold*
     ``story_text``, so MIPROv2 can show the local model genuinely good prose as
     labeled few-shot demos — not its own recycled artifacts.

  2. **Optimize the instructions, not just the demos.** We use ``MIPROv2``
     (Bayesian search over proposed instruction candidates + demo sets) rather
     than ``BootstrapFewShot`` (which only selects demos). Instruction
     proposals are written by DeepSeek (the ``prompt_model``); the story task
     itself runs on the local optimization LM (qwen3.6:27b, the ``task_model``).
     MIPROv2 only adopts a candidate if it scores better on a held-out
     validation set, so the search cannot regress below the baseline there.

Composite metric
----------------
The optimization objective is reference-free and weights artifact-cleanliness
heavily, because AI crutches are exactly what we want to drive out::

    composite = 0.6 * (overall / 10) + 0.4 * (1 - ai_artifact_score / 10)

It is a *fast heuristic signal* for prompt search, not a literary judgment —
see the ``--editorial`` flag and the note saved in the run report.

Model strategy
--------------
  * Demo generation : DeepSeek (paid quality) — the gold training stories.
  * Optimization LM : qwen3.6:27b (best local quality) — generates stories
                      during the search and at final inference; this is the LM
                      whose prompt we are optimizing.
  * Instruction LM  : DeepSeek (MIPROv2 ``prompt_model``) — writing strong
                      meta-instructions benefits most from a strong model. Falls
                      back to the optimization LM if DeepSeek is unavailable.

If DeepSeek is unavailable *or unreachable*, demo generation falls back to the
local model with a higher quality bar (≥ 8.5) and the local model also proposes
instructions.

Robustness / reproducibility
----------------------------
  * Config is read at *runtime* (after ``.env`` loading) into a :class:`Config`
    dataclass, so ``.env`` values actually take effect.
  * The optimization runs over multiple seeds (``OPTIMIZER_SEEDS``); the report
    carries the per-seed deltas and the mean ± std, so "improved" is only
    claimed when the mean delta is positive *and* the spread does not cross zero.

Outputs (written to ``test_output/``)
-------------------------------------
  * ``optimized_v2.json``        — the best-seed optimized DSPy program.
  * ``optimized_v2_report.json`` — full run report: baseline + per-seed
                                    optimized scores, per-premise breakdowns,
                                    trial history, selected instruction, demo
                                    provenance, model ids, timestamp, runtime.
  * ``optimized_v2_editorial.md`` — only with ``--editorial``: baseline vs
                                    optimized prose, side by side, for a human
                                    editorial review slice.

Usage::

    PYTHONPATH=. python engine/optimizer.py [--editorial]

Tunable via env: ``OLLAMA_URL``, ``OPTIMIZER_TASK_MODEL`` (default qwen3.6:27b),
``OPTIMIZER_TRIALS`` (default 7), ``OPTIMIZER_CANDIDATES`` (default 7),
``OPTIMIZER_DEMO_THRESHOLD`` (default 8.0), ``OPTIMIZER_SEEDS`` (default 3;
either a count like ``3`` or an explicit list like ``9,17,23``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
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
DEMO_THRESHOLD_FALLBACK = 8.5  # stricter bar when demos come from the local model
N_GOLD_DEMOS = 8
GEN_MAX_TOKENS = 512

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
    num_trials: int
    num_candidates: int
    demo_threshold: float
    demo_threshold_fallback: float
    n_gold_demos: int
    gen_max_tokens: int
    seeds: list[int]
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
            num_trials=int(os.environ.get("OPTIMIZER_TRIALS", "7")),
            num_candidates=int(os.environ.get("OPTIMIZER_CANDIDATES", "7")),
            demo_threshold=float(os.environ.get("OPTIMIZER_DEMO_THRESHOLD", "8.0")),
            demo_threshold_fallback=DEMO_THRESHOLD_FALLBACK,
            n_gold_demos=N_GOLD_DEMOS,
            gen_max_tokens=GEN_MAX_TOKENS,
            seeds=_parse_seeds(os.environ.get("OPTIMIZER_SEEDS", "3")),
            editorial=editorial,
            out_dir=out_dir,
            optimized_path=out_dir / "optimized_v2.json",
            report_path=out_dir / "optimized_v2_report.json",
            editorial_path=out_dir / "optimized_v2_editorial.md",
        )


def _parse_seeds(raw: str) -> list[int]:
    """Parse ``OPTIMIZER_SEEDS``: a count (``"3"``) or explicit list (``"9,17,23"``).

    A bare count ``N`` expands to a deterministic, well-spread seed sequence so
    repeated runs are reproducible while still exploring distinct MIPROv2 search
    trajectories.
    """
    raw = (raw or "").strip()
    if not raw:
        return [9, 23, 37]
    if "," in raw:
        seeds = [int(tok) for tok in raw.split(",") if tok.strip()]
        return seeds or [9]
    n = max(1, int(raw))
    return [9 + 14 * i for i in range(n)]


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

# Held back for MIPROv2's internal validation search (no gold needed — the
# metric is reference-free). Distinct from train and test.
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

    Composite of overall quality and an inverted artifact penalty, so the
    optimizer is rewarded for both good prose *and* the absence of AI crutches::

        0.6 * (overall / 10) + 0.4 * (1 - ai_artifact_score / 10)
    """
    text = getattr(pred, "story_text", "") or ""
    if len(text.split()) < 40:
        return 0.0
    m = _METRICS.compute(text)
    artifact_penalty = 1.0 - (m["ai_artifact_score"] / 10.0)
    return 0.6 * (m["overall"] / 10.0) + 0.4 * artifact_penalty


# ── DSPy signature ──────────────────────────────────────────
def _build_signature(dspy):
    class StorySignature(dspy.Signature):
        """Write a vivid ~250-word short story section in the given genre and
        style. Use concrete sensory detail and real interiority. Avoid cliché
        and AI crutch transitions (however/moreover/furthermore). Vary sentence
        length. Output only the story prose."""

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
            "composite": round(r["composite"], 4),
        }
        for r in ev["rows"]
    ]


# ── Trial-history extraction (issue #4) ─────────────────────
def _program_instruction(program) -> str | None:
    try:
        preds = program.predictors()
        if preds:
            return getattr(preds[0].signature, "instructions", None)
    except Exception:  # noqa: BLE001
        return None
    return None


def _extract_trial_info(optimizer, optimized) -> dict:
    """Pull what MIPROv2 exposes about the search, defensively across versions.

    Returns selected instruction text, number of trials actually run, the
    per-trial scores it logged, and the best trial score — so the saved report
    *proves* an optimization happened rather than just storing the demos.
    """
    info: dict = {
        "num_trials_run": None,
        "best_trial_score": None,
        "trial_scores": [],
        "selected_instruction": _program_instruction(optimized),
    }

    score = getattr(optimized, "score", None)
    if isinstance(score, (int, float)):
        info["best_trial_score"] = float(score)

    logs = getattr(optimizer, "trial_logs", None) or getattr(optimized, "trial_logs", None)
    if isinstance(logs, dict):
        info["num_trials_run"] = len(logs)
        scores: list[float] = []
        for entry in logs.values():
            if not isinstance(entry, dict):
                continue
            for key in ("score", "full_eval_score", "full_minibatch_eval_score", "val_score"):
                val = entry.get(key)
                if isinstance(val, (int, float)):
                    scores.append(float(val))
                    break
        info["trial_scores"] = [round(s, 4) for s in scores]
        candidates = scores + ([info["best_trial_score"]] if info["best_trial_score"] is not None else [])
        if candidates:
            info["best_trial_score"] = round(max(candidates), 4)
    return info


# ── Per-seed optimization run (issue #7) ────────────────────
def _run_seed(cfg, dspy, Signature, trainset, valset, task_lm, prompt_lm,
              seed, before) -> dict | None:
    """Run one MIPROv2 optimization at ``seed`` and evaluate it on the test set.

    Returns the per-seed result dict, or ``None`` if this seed's optimization
    failed (so the other seeds still contribute to the report).
    """
    from dspy.teleprompt import MIPROv2

    print(f"  ── seed {seed} ──")
    student = dspy.Predict(Signature)
    try:
        optimizer = MIPROv2(
            metric=composite_metric,
            prompt_model=prompt_lm,
            task_model=task_lm,
            auto=None,
            num_candidates=cfg.num_candidates,
            init_temperature=1.0,
            max_bootstrapped_demos=2,   # a couple of metric-gated bootstrapped demos
            max_labeled_demos=4,        # plus up to 4 GOLD DeepSeek stories
            metric_threshold=0.70,      # only strong generations may be bootstrapped
            num_threads=4,
            verbose=True,
            seed=seed,
        )
        optimized = optimizer.compile(
            student,
            trainset=trainset,
            valset=valset,
            num_trials=cfg.num_trials,
            minibatch=False,                  # valset is small — full eval each trial
            requires_permission_to_run=False, # non-interactive
            provide_traceback=True,
        )
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"  ✗ seed {seed} optimization failed: {exc}")
        traceback.print_exc()
        return None

    after = _evaluate(optimized, TEST_PREMISES, f"optimized(seed={seed})")
    trial = _extract_trial_info(optimizer, optimized)
    print(f"  seed {seed}: overall {before['avg_overall']:.2f} → {after['avg_overall']:.2f} "
          f"(Δ {after['avg_overall'] - before['avg_overall']:+.2f})  | "
          f"composite {before['avg_composite']:.3f} → {after['avg_composite']:.3f} "
          f"(Δ {after['avg_composite'] - before['avg_composite']:+.3f})  "
          f"[{after['elapsed']:.0f}s]\n")
    return {
        "seed": seed,
        "after": after,
        "trial": trial,
        "program": optimized,
        "delta_overall": after["avg_overall"] - before["avg_overall"],
        "delta_artifact": after["avg_artifact"] - before["avg_artifact"],
        "delta_composite": after["avg_composite"] - before["avg_composite"],
    }


# ── Aggregate + verdict (issue #7) ──────────────────────────
def _mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    mean = sum(values) / n
    if n == 1:
        return (mean, 0.0)
    var = sum((v - mean) ** 2 for v in values) / n  # population std
    return (mean, math.sqrt(var))


def _verdict(comp_mean: float, comp_std: float, n_seeds: int) -> tuple[str, bool]:
    """Only claim improvement if the mean delta > 0 AND the spread clears zero."""
    reliable = comp_mean > 0 and (comp_mean - comp_std) > 0
    spread = "single seed — no variance" if n_seeds < 2 else f"±{comp_std:.3f}"
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
def _write_editorial(path: Path, before: dict, best: dict, cfg: Config,
                     demo_source: str) -> None:
    """Dump baseline vs optimized prose, side by side, for a human review pass."""
    lines = [
        "# Optimized v2 — editorial review slice",
        "",
        f"> {_EDITORIAL_NOTE}",
        "",
        f"- task_model: `{cfg.task_model}`  ·  demo source: `{demo_source}`  ·  "
        f"best seed: `{best['seed']}`",
        "- Read each pair below and judge the *prose*, not the numbers. The "
        "metric guided the search; it does not certify the result.",
        "",
        "---",
        "",
    ]
    for b, a in zip(before["rows"], best["after"]["rows"]):
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
    print(f"\n=== DSPy story-prompt optimizer v2 "
          f"(task_model={cfg.task_model}, {cfg.url}) ===")
    print(f"    seeds={cfg.seeds}  trials={cfg.num_trials}  "
          f"candidates={cfg.num_candidates}  editorial={cfg.editorial}\n")

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

    # Instruction proposer: DeepSeek when available (strong meta-prompts),
    # otherwise reuse the local LM.
    prompt_lm = task_lm
    prompt_model_id = task_model_id
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        try:
            cand = dspy.LM("deepseek/deepseek-chat", api_key=deepseek_key,
                           temperature=0.9, max_tokens=1500)
            _ = cand("Reply with the single word: ready")
            prompt_lm = cand
            prompt_model_id = "deepseek/deepseek-chat"
            print("  ✓ using DeepSeek as the MIPROv2 instruction proposer (prompt_model)\n")
        except Exception as exc:  # noqa: BLE001
            print(f"  (DeepSeek prompt_model unavailable: {exc}; using {cfg.task_model})\n")

    Signature = _build_signature(dspy)

    # 3. Baseline evaluation (deterministic — computed once) ----------------
    print("STEP 3 — evaluate BASELINE (unoptimized prompt) on held-out premises")
    baseline = dspy.Predict(Signature)
    before = _evaluate(baseline, TEST_PREMISES, "baseline")
    print(f"  baseline avg overall: {before['avg_overall']:.2f}/10  "
          f"(artifact {before['avg_artifact']:.2f}, composite {before['avg_composite']:.3f})  "
          f"[{before['elapsed']:.0f}s]\n")

    # 4. MIPROv2 optimization across seeds ---------------------------------
    print(f"STEP 4 — optimize prompt INSTRUCTIONS with MIPROv2 over "
          f"{len(cfg.seeds)} seed(s)")
    trainset = [
        dspy.Example(premise=r["premise"], genre=r["genre"], style=r["style"],
                     story_text=r["text"]).with_inputs("premise", "genre", "style")
        for r in gold
    ]
    valset = [
        dspy.Example(premise=p, genre=g, style=s).with_inputs("premise", "genre", "style")
        for (p, g, s) in VAL_PREMISES
    ]

    seed_results = []
    for seed in cfg.seeds:
        res = _run_seed(cfg, dspy, Signature, trainset, valset, task_lm, prompt_lm,
                        seed, before)
        if res is not None:
            seed_results.append(res)
    if not seed_results:
        print("✗ every seed's optimization failed; cannot report.")
        return 1
    print("  ✓ optimization complete\n")

    # 5. Aggregate + report -------------------------------------------------
    print("STEP 5 — evaluate OPTIMIZED programs (per-seed deltas)")
    print("═" * 68)
    print(" PER-SEED RESULTS (held-out test set, baseline → optimized)")
    print("═" * 68)
    print(f"  baseline : overall {before['avg_overall']:.2f}  "
          f"artifact {before['avg_artifact']:.2f}  composite {before['avg_composite']:.3f}")
    print("─" * 68)
    for r in seed_results:
        a = r["after"]
        print(f"  seed {r['seed']:>4} : overall {a['avg_overall']:.2f} "
              f"(Δ {r['delta_overall']:+.2f})  "
              f"artifact {a['avg_artifact']:.2f} (Δ {r['delta_artifact']:+.2f})  "
              f"composite {a['avg_composite']:.3f} (Δ {r['delta_composite']:+.3f})")
    print("═" * 68)

    overall_after = [r["after"]["avg_overall"] for r in seed_results]
    artifact_after = [r["after"]["avg_artifact"] for r in seed_results]
    comp_after = [r["after"]["avg_composite"] for r in seed_results]
    d_overall = [r["delta_overall"] for r in seed_results]
    d_artifact = [r["delta_artifact"] for r in seed_results]
    d_comp = [r["delta_composite"] for r in seed_results]

    om, osd = _mean_std(overall_after)
    am, asd = _mean_std(artifact_after)
    cm, csd = _mean_std(comp_after)
    dom, dosd = _mean_std(d_overall)
    dam, dasd = _mean_std(d_artifact)
    dcm, dcsd = _mean_std(d_comp)

    verdict, reliable = _verdict(dcm, dcsd, len(seed_results))

    print(f"  overall  : {before['avg_overall']:.2f} → {om:.2f} ± {osd:.2f}  "
          f"(Δ {dom:+.2f} ± {dosd:.2f})")
    print(f"  artifact : {before['avg_artifact']:.2f} → {am:.2f} ± {asd:.2f}  "
          f"(Δ {dam:+.2f} ± {dasd:.2f})   (lower is better)")
    print(f"  composite: {before['avg_composite']:.3f} → {cm:.3f} ± {csd:.3f}  "
          f"(Δ {dcm:+.3f} ± {dcsd:.3f})")
    print(f"  verdict  : {verdict}")
    print("═" * 68)
    print(f"  note: {_EDITORIAL_NOTE}")
    print("═" * 68 + "\n")

    # Best seed = largest composite delta (this program is the one we persist).
    best = max(seed_results, key=lambda r: r["delta_composite"])

    # 6. Persist the optimized program + full report -----------------------
    try:
        best["program"].save(str(cfg.optimized_path))
        print(f"  saved optimized program (seed {best['seed']}) → {cfg.optimized_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (could not save optimized program: {exc})")

    report = {
        "schema": "optimized_v2_report/1",
        "generated_at": _utc_now_iso(),
        "total_runtime_sec": round(time.time() - t_start, 1),
        "note": _EDITORIAL_NOTE,
        "config": {
            "task_model": cfg.task_model,
            "task_model_id": task_model_id,
            "prompt_model_id": prompt_model_id,
            "ollama_url": cfg.url,
            "num_trials": cfg.num_trials,
            "num_candidates": cfg.num_candidates,
            "demo_threshold": demo_threshold,
            "seeds": cfg.seeds,
            "n_train_premises": len(TRAIN_PREMISES),
            "n_val_premises": len(VAL_PREMISES),
            "n_test_premises": len(TEST_PREMISES),
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
                    "composite": round(r["composite"], 4),
                    "below_threshold": bool(r.get("below_threshold", False)),
                }
                for r in gold
            ],
        },
        "baseline": {
            "avg_overall": round(before["avg_overall"], 3),
            "avg_artifact": round(before["avg_artifact"], 3),
            "avg_composite": round(before["avg_composite"], 4),
            "elapsed_sec": round(before["elapsed"], 1),
            "per_premise": _per_premise(before),
        },
        "seeds": [
            {
                "seed": r["seed"],
                "optimized": {
                    "avg_overall": round(r["after"]["avg_overall"], 3),
                    "avg_artifact": round(r["after"]["avg_artifact"], 3),
                    "avg_composite": round(r["after"]["avg_composite"], 4),
                    "elapsed_sec": round(r["after"]["elapsed"], 1),
                    "per_premise": _per_premise(r["after"]),
                },
                "delta": {
                    "overall": round(r["delta_overall"], 3),
                    "artifact": round(r["delta_artifact"], 3),
                    "composite": round(r["delta_composite"], 4),
                },
                "num_trials_run": r["trial"]["num_trials_run"],
                "best_trial_score": r["trial"]["best_trial_score"],
                "trial_scores": r["trial"]["trial_scores"],
                "selected_instruction": r["trial"]["selected_instruction"],
            }
            for r in seed_results
        ],
        "aggregate": {
            "n_seeds": len(seed_results),
            "best_seed": best["seed"],
            "optimized_overall_mean": round(om, 3),
            "optimized_overall_std": round(osd, 3),
            "optimized_artifact_mean": round(am, 3),
            "optimized_artifact_std": round(asd, 3),
            "optimized_composite_mean": round(cm, 4),
            "optimized_composite_std": round(csd, 4),
            "delta_overall_mean": round(dom, 3),
            "delta_overall_std": round(dosd, 3),
            "delta_artifact_mean": round(dam, 3),
            "delta_artifact_std": round(dasd, 3),
            "delta_composite_mean": round(dcm, 4),
            "delta_composite_std": round(dcsd, 4),
            "reliable_improvement": reliable,
            "verdict": verdict,
        },
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
            _write_editorial(cfg.editorial_path, before, best, cfg, demo_source)
            print(f"  saved editorial review slice → {cfg.editorial_path}")
        except OSError as exc:
            print(f"  (could not save editorial slice: {exc})")

    print()
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DSPy story-prompt optimizer v2 (MIPROv2 + gold demos)."
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
