#!/usr/bin/env python3
"""
DSPy-based prompt optimizer for story generation (local Ollama LM).

Goal: automatically improve the story-generation prompt so output scores better
on the model-free quality metrics in ``engine/metrics.py`` (lower AI-artifact
score, better variety/readability → higher overall).

How it works:
  1. Configure DSPy to use a local Ollama model as the LM.
  2. Define a ``StorySignature`` (premise/genre/style → story_text).
  3. Use ``StoryMetrics.overall`` as a reference-free optimization metric.
  4. ``BootstrapFewShot`` bootstraps high-scoring generations into few-shot
     demonstrations (keeping only those above a quality threshold).
  5. Compare the optimized program against the unoptimized baseline on held-out
     premises and report the change in average quality.
  6. Save the optimized program (instructions + demos) to JSON.

DSPy API note: DSPy 3.x removed ``dspy.OllamaLocal``. The current integration is
``dspy.LM("ollama_chat/<model>", api_base=..., think=False)`` (litellm under the
hood). ``think=False`` keeps qwen3/nemotron reasoning out of the parsed output.

Usage::

    python engine/optimizer.py                         # qwen3:latest
    OPTIMIZER_MODEL=nemotron-3-nano:4b python engine/optimizer.py   # fast loop
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.metrics import StoryMetrics

URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")
MODEL = os.environ.get("OPTIMIZER_MODEL", "qwen3:latest")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_output")
OPTIMIZED_PATH = os.path.join(OUT_DIR, "optimized_story_program.json")

_METRICS = StoryMetrics()

# Training premises (no gold story — the metric scores generations directly).
TRAIN_PREMISES = [
    ("A retired diver returns to the wreck that killed his brother.", "literary", "atmospheric"),
    ("A child trades shadows with a stranger at a winter fair.", "fantasy", "poetic"),
    ("A night nurse notices the same patient in three different beds.", "horror", "minimalist"),
    ("A translator realizes the letters she renders are writing her life.", "literary", "descriptive"),
    ("A lighthouse keeper races a storm she may have summoned.", "thriller", "cinematic"),
]

# Held-out premises used only for the before/after comparison.
TEST_PREMISES = [
    ("A cartographer maps a town that is not on any other map.", "literary", "atmospheric"),
    ("A boy inherits a coat whose pockets hold other people's memories.", "fantasy", "poetic"),
    ("A detective interrogates a suspect who answers only in weather.", "noir", "minimalist"),
]


def _build_signature(dspy):
    class StorySignature(dspy.Signature):
        """Write a vivid ~250-word short story section in the given genre and style.
        Use concrete sensory detail and real interiority. Avoid cliché and AI
        crutch transitions (however/moreover/furthermore). Vary sentence length.
        Output only the story prose."""

        premise = dspy.InputField(desc="Story premise / seed idea")
        genre = dspy.InputField(desc="Target genre")
        style = dspy.InputField(desc="Prose style")
        story_text = dspy.OutputField(desc="The generated story prose, ~250 words, no preamble")

    return StorySignature


def quality_metric(example, pred, trace=None) -> float:
    """Reference-free quality score in [0, 1] from StoryMetrics.overall.

    Used both as the optimization objective and (via threshold) as the
    bootstrap gate that decides which generations become demonstrations.
    """
    text = getattr(pred, "story_text", "") or ""
    if len(text.split()) < 40:
        return 0.0
    return _METRICS.compute(text)["overall"] / 10.0


def _evaluate(program, premises, label: str) -> dict:
    """Run a program over premises, return aggregate metrics + per-item rows."""
    rows = []
    total_overall = 0.0
    total_artifact = 0.0
    t0 = time.time()
    for premise, genre, style in premises:
        pred = program(premise=premise, genre=genre, style=style)
        text = getattr(pred, "story_text", "") or ""
        m = _METRICS.compute(text)
        rows.append({"premise": premise, "metrics": m})
        total_overall += m["overall"]
        total_artifact += m["ai_artifact_score"]
    n = max(1, len(premises))
    return {
        "label": label,
        "avg_overall": total_overall / n,
        "avg_artifact": total_artifact / n,
        "elapsed": time.time() - t0,
        "rows": rows,
    }


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"\n=== DSPy story-prompt optimizer (model={MODEL}, {URL}) ===\n")

    try:
        import dspy
    except ImportError:
        print("✗ dspy not installed. Run: pip install dspy")
        return 1

    # 1. Configure the local LM.
    try:
        lm = dspy.LM(
            f"ollama_chat/{MODEL}",
            api_base=URL,
            api_key="",
            temperature=0.7,
            max_tokens=600,
            think=False,
        )
        dspy.configure(lm=lm)
        # Smoke-test connectivity early with a clear error if the model is down.
        _ = lm("Reply with the single word: ready")
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Could not reach Ollama/DSPy LM: {exc}")
        print("  (Is the model pulled and the server reachable?)")
        return 1

    Signature = _build_signature(dspy)
    baseline = dspy.Predict(Signature)

    # 2. Baseline evaluation.
    print("Evaluating BASELINE (unoptimized prompt) on held-out premises...")
    before = _evaluate(baseline, TEST_PREMISES, "baseline")
    print(f"  baseline avg overall: {before['avg_overall']:.2f}/10  "
          f"(artifact {before['avg_artifact']:.2f})  [{before['elapsed']:.0f}s]\n")

    # 3. Optimize with BootstrapFewShot (keep only high-scoring demos).
    print("Optimizing with BootstrapFewShot (this bootstraps good demos)...")
    trainset = [
        dspy.Example(premise=p, genre=g, style=s).with_inputs("premise", "genre", "style")
        for (p, g, s) in TRAIN_PREMISES
    ]
    try:
        optimizer = dspy.BootstrapFewShot(
            metric=quality_metric,
            metric_threshold=0.65,        # only generations scoring >= 6.5/10 become demos
            max_bootstrapped_demos=2,
            max_labeled_demos=0,          # our examples carry no gold story
            max_rounds=1,
        )
        optimized = optimizer.compile(baseline, trainset=trainset)
    except Exception as exc:  # noqa: BLE001
        print(f"✗ Optimization failed: {exc}")
        print("  Reporting baseline only; see DSPy docs for local-model tuning.")
        return 1

    n_demos = len(getattr(optimized, "demos", []) or
                  getattr(getattr(optimized, "predictors", lambda: [])()[0], "demos", []) if False else [])
    try:
        n_demos = len(optimized.predictors()[0].demos)
    except Exception:
        n_demos = 0
    print(f"  optimization complete — {n_demos} few-shot demo(s) selected\n")

    # 4. Optimized evaluation.
    print("Evaluating OPTIMIZED program on the same held-out premises...")
    after = _evaluate(optimized, TEST_PREMISES, "optimized")
    print(f"  optimized avg overall: {after['avg_overall']:.2f}/10  "
          f"(artifact {after['avg_artifact']:.2f})  [{after['elapsed']:.0f}s]\n")

    # 5. Report.
    delta = after["avg_overall"] - before["avg_overall"]
    art_delta = after["avg_artifact"] - before["avg_artifact"]
    print("═" * 60)
    print(" OPTIMIZATION RESULT")
    print("═" * 60)
    print(f"  avg overall : {before['avg_overall']:.2f}  →  {after['avg_overall']:.2f}  "
          f"({'+' if delta >= 0 else ''}{delta:.2f})")
    print(f"  avg artifact: {before['avg_artifact']:.2f}  →  {after['avg_artifact']:.2f}  "
          f"({'+' if art_delta >= 0 else ''}{art_delta:.2f})  (lower is better)")
    verdict = ("✓ optimized prompt improved quality" if delta > 0.05
               else "≈ no significant change (small local model; try MIPROv2 or more demos)"
               if abs(delta) <= 0.05 else "✗ optimized prompt scored lower this run")
    print(f"  verdict     : {verdict}")
    print("═" * 60)

    # 6. Persist the optimized program.
    try:
        optimized.save(OPTIMIZED_PATH)
        print(f"\n  saved optimized program → {os.path.normpath(OPTIMIZED_PATH)}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n  (could not save optimized program: {exc})")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
