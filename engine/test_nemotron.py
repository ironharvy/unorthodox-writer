#!/usr/bin/env python3
"""
Quality + speed comparison: nemotron-3-nano:4b vs qwen3:latest vs qwen3.6:27b.

Generates the same ~300-word story prompt on all three models, scores each with
the metrics module, measures words/second, and prints a comparison table.

Why this matters:
  * nemotron-3-nano:4b — 2.8 GB, 256K context, Mamba-2/Attention hybrid. The
    huge context window means a whole novel fits in memory for long-range
    coherence — no other model on our server can do that.
  * qwen3:latest        — 8B, the current free-tier default.
  * qwen3.6:27b         — 27B, the quality reference.

Usage::

    python engine/test_nemotron.py
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.backends.ollama import OllamaBackend
from engine.metrics import StoryMetrics

URL = os.environ.get("OLLAMA_URL", "http://192.168.1.20:11434")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_output")

MODELS = ["nemotron-3-nano:4b", "qwen3:latest", "qwen3.6:27b"]

SYSTEM = (
    "You are a literary fiction writer with a spare, atmospheric voice. You write "
    "real scene-prose with concrete sensory detail and interiority. You avoid cliché "
    "and AI crutch transitions. Output only the story prose — no preamble, no notes."
)
PROMPT = (
    "Write a complete ~300-word short story in third-person limited POV.\n\n"
    "Premise: A woman returns to her childhood home to find the orchard her father "
    "planted has grown overnight into a forest she does not recognize.\n\n"
    "Open in a scene. Land an image of unease, a small discovery, and a quiet, "
    "earned ending. About 300 words."
)


async def generate_one(model: str) -> dict:
    backend = OllamaBackend(base_url=URL, model=model)
    available = await backend.list_models()
    if model not in available:
        await backend.close()
        return {"model": model, "skipped": f"not on server (have {available})"}

    t0 = time.time()
    text = await backend.generate_full(PROMPT, SYSTEM)
    elapsed = time.time() - t0
    await backend.close()

    text = text.strip()
    metrics = StoryMetrics().compute(text)
    wc = metrics["word_count"]
    return {
        "model": model,
        "text": text,
        "elapsed": elapsed,
        "wps": (wc / elapsed) if elapsed else 0.0,
        "metrics": metrics,
    }


def print_table(results: list[dict]) -> None:
    print("\n" + "═" * 86)
    print(" MODEL COMPARISON — same ~300-word prompt")
    print("═" * 86)
    header = (
        f"{'model':<22}{'words':>6}{'sec':>7}{'w/s':>7}"
        f"{'artifact↓':>11}{'read':>6}{'variety':>8}{'dialog%':>8}{'rep↓':>6}{'overall↑':>9}"
    )
    print(header)
    print("─" * 86)
    for r in results:
        if r.get("skipped"):
            print(f"{r['model']:<22}  SKIPPED — {r['skipped']}")
            continue
        m = r["metrics"]
        print(
            f"{r['model']:<22}"
            f"{m['word_count']:>6}"
            f"{r['elapsed']:>7.1f}"
            f"{r['wps']:>7.1f}"
            f"{m['ai_artifact_score']:>11.1f}"
            f"{m['readability']:>6.1f}"
            f"{m['sentence_variety']:>8.1f}"
            f"{m['dialogue_ratio'] * 100:>8.1f}"
            f"{m['repetition_score']:>6.1f}"
            f"{m['overall']:>9.1f}"
        )
    print("═" * 86)
    print(" ↓ lower is better   ↑ higher is better")


def print_recommendations(results: list[dict]) -> None:
    scored = [r for r in results if not r.get("skipped")]
    if not scored:
        return
    by_overall = sorted(scored, key=lambda r: -r["metrics"]["overall"])
    by_speed = sorted(scored, key=lambda r: -r["wps"])
    # quality-to-speed: overall * wps (rewards models that are both)
    by_ratio = sorted(scored, key=lambda r: -(r["metrics"]["overall"] * r["wps"]))
    print("\nRECOMMENDATIONS")
    print(f"  Best quality (overall)     : {by_overall[0]['model']} "
          f"({by_overall[0]['metrics']['overall']:.1f}/10)")
    print(f"  Fastest (words/sec)        : {by_speed[0]['model']} "
          f"({by_speed[0]['wps']:.1f} w/s)")
    print(f"  Best quality-to-speed      : {by_ratio[0]['model']}")
    print("\n  Suggested roles:")
    print(f"    Free-tier short stories  : {by_ratio[0]['model']}")
    print(f"    Free-tier novel work     : {by_overall[0]['model']}  "
          "(or nemotron-3-nano:4b for 256K-context long-range coherence)")
    print(f"    DSPy optimization loop   : {by_speed[0]['model']}  (fast iterations)")
    print()


async def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"\n=== Nemotron vs qwen3 vs qwen3.6 ({URL}) ===")

    probe = OllamaBackend(base_url=URL)
    if not await probe.health_check():
        print(f"✗ Ollama not reachable at {URL}")
        await probe.close()
        return 1
    await probe.close()

    results = []
    for model in MODELS:
        print(f"  generating with {model} ...")
        results.append(await generate_one(model))

    print_table(results)
    print_recommendations(results)

    # Save the outputs for manual inspection.
    for r in results:
        if r.get("skipped"):
            continue
        safe = r["model"].replace(":", "_").replace("/", "_")
        with open(os.path.join(OUT_DIR, f"compare_{safe}.md"), "w", encoding="utf-8") as fh:
            fh.write(f"# {r['model']}\n\n{r['text']}\n")
    print(f"  outputs saved under {os.path.normpath(OUT_DIR)}/compare_*.md\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
