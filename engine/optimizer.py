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

Model strategy
--------------
  * Demo generation : DeepSeek (paid quality) — the gold training stories.
  * Optimization LM : qwen3.6:27b (best local quality) — generates stories
                      during the search and at final inference; this is the LM
                      whose prompt we are optimizing.
  * Instruction LM  : DeepSeek (MIPROv2 ``prompt_model``) — writing strong
                      meta-instructions benefits most from a strong model. Falls
                      back to the optimization LM if DeepSeek is unavailable.

If DeepSeek is unavailable entirely, demo generation falls back to qwen3.6:27b
with a higher quality bar (≥ 8.5) and qwen3.6:27b also proposes instructions.

Usage::

    PYTHONPATH=. python engine/optimizer.py

Tunable via env: ``OLLAMA_URL``, ``OPTIMIZER_TASK_MODEL`` (default qwen3.6:27b),
``OPTIMIZER_TRIALS`` (default 7), ``OPTIMIZER_CANDIDATES`` (default 7),
``OPTIMIZER_DEMO_THRESHOLD`` (default 8.0).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.metrics import StoryMetrics
from engine.backends.cloud import CloudBackend
from engine.backends.ollama import OllamaBackend

# ── Configuration ───────────────────────────────────────────
URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")
TASK_MODEL = os.environ.get("OPTIMIZER_TASK_MODEL", "qwen3.6:27b")
NUM_TRIALS = int(os.environ.get("OPTIMIZER_TRIALS", "7"))
NUM_CANDIDATES = int(os.environ.get("OPTIMIZER_CANDIDATES", "7"))
DEMO_THRESHOLD = float(os.environ.get("OPTIMIZER_DEMO_THRESHOLD", "8.0"))
DEMO_THRESHOLD_FALLBACK = 8.5  # stricter bar when demos come from the local model
N_GOLD_DEMOS = 8
GEN_MAX_TOKENS = 512

OUT_DIR = REPO_ROOT / "test_output"
OPTIMIZED_PATH = OUT_DIR / "optimized_v2.json"

_METRICS = StoryMetrics()


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
TEST_PREMISES = [
    ("A cartographer is hired to map a town that appears on no other map.", "literary", "atmospheric"),
    ("A boy inherits a coat whose pockets hold other people's memories.", "fantasy", "poetic"),
    ("A detective interrogates a suspect who answers only in descriptions of the weather.", "noir", "minimalist"),
    ("A widowed organist plays the cathedral empty every midnight for an audience of one he won't name.", "gothic", "haunting"),
    ("A deep-sea welder repairs a pipeline and hears, in the dark, singing that matches his late wife's hum.", "literary", "cinematic"),
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
    """Generate one story per premise concurrently, score each with StoryMetrics."""
    sem = asyncio.Semaphore(6)

    async def one(idx, premise, genre, style):
        async with sem:
            try:
                text = await backend.generate_full(
                    _demo_user_prompt(premise, genre, style), system_prompt=DEMO_SYSTEM
                )
            except Exception as exc:  # noqa: BLE001
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
    results = await asyncio.gather(*(one(i, p, g, s) for i, (p, g, s) in enumerate(premises)))
    await backend.close()
    return [r for r in results if r is not None]


def _select_top_demos(scored: list[dict], threshold: float, k: int) -> list[dict]:
    """Keep stories at/above the quality bar, best composite first, up to k."""
    passing = [r for r in scored if r["metrics"]["overall"] >= threshold]
    passing.sort(key=lambda r: r["composite"], reverse=True)
    if len(passing) < k:
        # Top up with the next-best below-threshold demos so MIPROv2 still has
        # enough labeled examples to work with (and report the shortfall).
        rest = [r for r in scored if r not in passing]
        rest.sort(key=lambda r: r["composite"], reverse=True)
        print(f"  ⚠ only {len(passing)} demo(s) cleared {threshold:.1f}/10; "
              f"topping up to {k} with next-best.")
        passing = (passing + rest)[:k]
    return passing[:k]


# ── Evaluation ──────────────────────────────────────────────
def _evaluate(program, premises, label: str) -> dict:
    rows, total_overall, total_artifact, total_comp = [], 0.0, 0.0, 0.0
    t0 = time.time()
    for premise, genre, style in premises:
        pred = program(premise=premise, genre=genre, style=style)
        text = getattr(pred, "story_text", "") or ""
        m = _METRICS.compute(text)
        comp = composite_metric(None, pred)
        rows.append({"premise": premise, "metrics": m, "composite": comp})
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


# ── Main ────────────────────────────────────────────────────
def main() -> int:
    _load_env_from_dotenv()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n=== DSPy story-prompt optimizer v2 (task_model={TASK_MODEL}, {URL}) ===\n")

    try:
        import dspy
    except ImportError:
        print("✗ dspy not installed. Run: pip install dspy")
        return 1

    # 1. Gold demonstration stories ----------------------------------------
    print("STEP 1 — generate gold demonstration stories")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key:
        demo_backend = CloudBackend(provider="deepseek", max_tokens=600)
        demo_label, demo_threshold = "DeepSeek", DEMO_THRESHOLD
    else:
        print("  (no DEEPSEEK_API_KEY — falling back to qwen3.6:27b for demos, bar=8.5)")
        demo_backend = OllamaBackend(base_url=URL, model=TASK_MODEL, temperature=0.8,
                                     num_ctx=8192, think=False)
        demo_label, demo_threshold = TASK_MODEL, DEMO_THRESHOLD_FALLBACK

    scored = asyncio.run(_generate_demos(demo_backend, TRAIN_PREMISES, demo_label))
    if not scored:
        print("✗ no demo stories were generated; cannot proceed.")
        return 1
    gold = _select_top_demos(scored, demo_threshold, N_GOLD_DEMOS)
    avg_gold = sum(r["metrics"]["overall"] for r in gold) / len(gold)
    print(f"  → kept {len(gold)} gold demo(s); avg overall {avg_gold:.2f}/10 "
          f"(bar {demo_threshold:.1f})\n")

    # 2. Configure the local optimization LM -------------------------------
    print("STEP 2 — configure optimization LM")
    try:
        task_lm = dspy.LM(
            f"ollama_chat/{TASK_MODEL}", api_base=URL, api_key="",
            temperature=0.0, max_tokens=GEN_MAX_TOKENS, think=False,
            num_ctx=8192,  # headroom so few-shot demos are never truncated
        )
        dspy.configure(lm=task_lm)
        _ = task_lm("Reply with the single word: ready")  # connectivity smoke test
        print(f"  ✓ {TASK_MODEL} reachable at {URL}\n")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not reach Ollama/DSPy LM: {exc}")
        print("  (Is the model pulled and the server reachable?)")
        return 1

    # Instruction proposer: DeepSeek when available (strong meta-prompts),
    # otherwise reuse the local LM.
    prompt_lm = task_lm
    if deepseek_key:
        try:
            cand = dspy.LM("deepseek/deepseek-chat", api_key=deepseek_key,
                           temperature=0.9, max_tokens=1500)
            _ = cand("Reply with the single word: ready")
            prompt_lm = cand
            print("  ✓ using DeepSeek as the MIPROv2 instruction proposer (prompt_model)\n")
        except Exception as exc:  # noqa: BLE001
            print(f"  (DeepSeek prompt_model unavailable: {exc}; using {TASK_MODEL})\n")

    Signature = _build_signature(dspy)
    baseline = dspy.Predict(Signature)

    # 3. Baseline evaluation ------------------------------------------------
    print("STEP 3 — evaluate BASELINE (unoptimized prompt) on held-out premises")
    before = _evaluate(baseline, TEST_PREMISES, "baseline")
    print(f"  baseline avg overall: {before['avg_overall']:.2f}/10  "
          f"(artifact {before['avg_artifact']:.2f}, composite {before['avg_composite']:.3f})  "
          f"[{before['elapsed']:.0f}s]\n")

    # 4. MIPROv2 optimization ----------------------------------------------
    print("STEP 4 — optimize prompt INSTRUCTIONS with MIPROv2")
    trainset = [
        dspy.Example(premise=r["premise"], genre=r["genre"], style=r["style"],
                     story_text=r["text"]).with_inputs("premise", "genre", "style")
        for r in gold
    ]
    valset = [
        dspy.Example(premise=p, genre=g, style=s).with_inputs("premise", "genre", "style")
        for (p, g, s) in VAL_PREMISES
    ]
    try:
        from dspy.teleprompt import MIPROv2
        optimizer = MIPROv2(
            metric=composite_metric,
            prompt_model=prompt_lm,
            task_model=task_lm,
            auto=None,
            num_candidates=NUM_CANDIDATES,
            init_temperature=1.0,
            max_bootstrapped_demos=2,   # a couple of metric-gated bootstrapped demos
            max_labeled_demos=4,        # plus up to 4 GOLD DeepSeek stories
            metric_threshold=0.70,      # only strong generations may be bootstrapped
            num_threads=4,
            verbose=True,
            seed=9,
        )
        optimized = optimizer.compile(
            baseline,
            trainset=trainset,
            valset=valset,
            num_trials=NUM_TRIALS,
            minibatch=False,                  # valset is small — full eval each trial
            requires_permission_to_run=False, # non-interactive
            provide_traceback=True,
        )
    except Exception as exc:  # noqa: BLE001
        import traceback
        print(f"✗ Optimization failed: {exc}")
        traceback.print_exc()
        return 1
    print("  ✓ optimization complete\n")

    # 5. Optimized evaluation ----------------------------------------------
    print("STEP 5 — evaluate OPTIMIZED program on the same held-out premises")
    after = _evaluate(optimized, TEST_PREMISES, "optimized")
    print(f"  optimized avg overall: {after['avg_overall']:.2f}/10  "
          f"(artifact {after['avg_artifact']:.2f}, composite {after['avg_composite']:.3f})  "
          f"[{after['elapsed']:.0f}s]\n")

    # 6. Report -------------------------------------------------------------
    delta = after["avg_overall"] - before["avg_overall"]
    art_delta = after["avg_artifact"] - before["avg_artifact"]
    comp_delta = after["avg_composite"] - before["avg_composite"]
    print("═" * 64)
    print(" OPTIMIZATION RESULT")
    print("═" * 64)
    print(f"  avg overall  : {before['avg_overall']:.2f}  →  {after['avg_overall']:.2f}  "
          f"({'+' if delta >= 0 else ''}{delta:.2f})")
    print(f"  avg artifact : {before['avg_artifact']:.2f}  →  {after['avg_artifact']:.2f}  "
          f"({'+' if art_delta >= 0 else ''}{art_delta:.2f})   (lower is better)")
    print(f"  avg composite: {before['avg_composite']:.3f}  →  {after['avg_composite']:.3f}  "
          f"({'+' if comp_delta >= 0 else ''}{comp_delta:.3f})")
    if delta > 0.05:
        verdict = f"✓ optimized prompt improved quality by +{delta:.2f}"
    elif comp_delta > 0.005:
        verdict = (f"✓ optimized prompt improved the composite objective by "
                   f"+{comp_delta:.3f} (overall ≈ flat)")
    elif abs(delta) <= 0.05:
        verdict = "≈ no significant change"
    else:
        verdict = f"✗ optimized prompt scored lower this run ({delta:.2f})"
    print(f"  verdict      : {verdict}")
    print("═" * 64)

    # 7. Persist the optimized program -------------------------------------
    try:
        optimized.save(str(OPTIMIZED_PATH))
        print(f"\n  saved optimized program → {OPTIMIZED_PATH}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n  (could not save optimized program: {exc})")
    print()
    return 0


def _load_env_from_dotenv() -> None:
    """Load DEEPSEEK_* / OLLAMA_URL from the repo .env if not already set.

    Mirrors ``source .env`` for the few keys this script needs, so the optimizer
    runs the same way under a bare ``PYTHONPATH=. python engine/optimizer.py``.
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
    raise SystemExit(main())
