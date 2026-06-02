"""
The Dreamer — an Auto-Think research agent.

Inspired by Graeme's Buildroom "Hermes" architecture
(https://gkisokay.substack.com/p/how-to-build-a-hermes-agent-that), the Dreamer
reads this project's telemetry (everything under ``test_output/``), notices
patterns across model comparisons, optimizer runs, editorial reviews and metric
trends, and proposes a handful of structured *candidate idea contracts* for a
human to review.

Safety invariants (enforced in code, not just by prompt):

  * The Dreamer NEVER modifies code or config. Its only side effect is writing
    idea contracts under ``test_output/ideas/``.
  * The Dreamer NEVER approves its own ideas. Every contract is emitted with
    ``status == "proposed"``; the field is overwritten by the Dreamer regardless
    of what the model returns.
  * Every contract must cite at least one *real* evidence file the Dreamer
    actually read. References to files that do not exist are stripped, and a
    contract left with no evidence is discarded — hallucinated evidence cannot
    survive to disk.
  * Runs are idempotent: a new idea that is a near-duplicate of one already on
    disk is dropped, so re-running does not pile up the same proposals.

Reasoning is done by DeepSeek via :class:`engine.backends.cloud.CloudBackend`,
which provides the analytical horsepower the local task models lack.

Usage::

    PYTHONPATH=. python engine/dreamer.py            # produce a fresh batch
    PYTHONPATH=. python engine/dreamer.py --dry-run   # build the digest only, no API call
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.backends.cloud import CloudBackend  # noqa: E402

# ── Static config ────────────────────────────────────────────────────────────

TEST_OUTPUT_DIR = REPO_ROOT / "test_output"
IDEAS_DIR = TEST_OUTPUT_DIR / "ideas"
SCHEMA_PATH = REPO_ROOT / "schemas" / "idea-contract.schema.json"

# Which evidence files the Dreamer reads.
EVIDENCE_SUFFIXES = {".json", ".md", ".log"}

# Digest budget — keep the prompt compact while preserving line references.
HEAD_LINES = 55          # numbered lines shown from the top of a long file
TAIL_LINES = 25          # numbered lines shown from the bottom of a long file
FULL_IF_UNDER = 90       # files at or under this many lines are shown in full
MAX_LINE_CHARS = 320     # individual long lines are clipped to this width

# Near-duplicate detection: ideas whose (signal + proposal) text is at least this
# similar to an existing idea are treated as duplicates and dropped.
DUP_THRESHOLD = 0.82

# Fields the Dreamer owns and always sets itself, ignoring anything the model
# returns for them. ``status`` in particular is a hard safety rule.
DREAMER_OWNED_FIELDS = {
    "schema_version",
    "idea_id",
    "generated_at",
    "generated_by",
    "model_used",
    "status",
}

CATEGORY_ENUM = {
    "model_selection",
    "prompt_engineering",
    "pipeline_architecture",
    "quality_gate",
    "tier_policy",
    "new_feature",
}
LOW_MED_HIGH = {"low", "medium", "high"}
EFFORT_ENUM = {"small", "medium", "large"}


# ── Evidence gathering ───────────────────────────────────────────────────────


@dataclass
class Evidence:
    """A single telemetry file the Dreamer read."""

    rel_path: str          # path relative to repo root, e.g. test_output/foo.json
    name: str              # bare filename
    line_count: int
    byte_size: int
    digest: str            # numbered, possibly head+tail-truncated excerpt


def _clip(line: str) -> str:
    if len(line) <= MAX_LINE_CHARS:
        return line
    return line[:MAX_LINE_CHARS] + " …[clipped]"


def _number_lines(lines: list[str], start: int = 1) -> list[str]:
    return [f"{start + i:>5}\t{_clip(line)}" for i, line in enumerate(lines)]


def _build_digest(lines: list[str]) -> str:
    """Render a numbered excerpt of a file.

    Short files are shown in full. Long files show a numbered head and a numbered
    tail (with the file's real line numbers preserved) separated by an elision
    marker, so the model can still cite accurate line references.
    """
    n = len(lines)
    if n <= FULL_IF_UNDER:
        return "\n".join(_number_lines(lines, 1))
    head = _number_lines(lines[:HEAD_LINES], 1)
    tail_start = n - TAIL_LINES + 1
    tail = _number_lines(lines[-TAIL_LINES:], tail_start)
    elided = n - HEAD_LINES - TAIL_LINES
    marker = f"      …  [{elided} line(s) elided] …"
    return "\n".join(head + [marker] + tail)


def gather_evidence(test_output_dir: Path) -> list[Evidence]:
    """Read every ``.json``/``.md``/``.log`` file under ``test_output/``.

    The Dreamer's own past output (``test_output/ideas/``) is skipped here — those
    contracts are loaded separately, only for duplicate detection, and must not be
    fed back in as fresh evidence.
    """
    items: list[Evidence] = []
    if not test_output_dir.is_dir():
        return items

    for path in sorted(test_output_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in EVIDENCE_SUFFIXES:
            continue
        if IDEAS_DIR in path.parents or path.parent == IDEAS_DIR:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"  ⚠ could not read {path}: {exc}")
            continue
        lines = text.splitlines()
        rel = path.relative_to(REPO_ROOT).as_posix()
        items.append(
            Evidence(
                rel_path=rel,
                name=path.name,
                line_count=len(lines),
                byte_size=len(text.encode("utf-8")),
                digest=_build_digest(lines),
            )
        )
    return items


def render_context(evidence: list[Evidence]) -> str:
    """Assemble the compact, line-numbered evidence digest sent to the model."""
    manifest_lines = [
        f"  - {e.rel_path}  ({e.line_count} lines, {e.byte_size} bytes)"
        for e in evidence
    ]
    blocks = []
    for e in evidence:
        blocks.append(
            f"===== FILE: {e.rel_path}  ({e.line_count} lines) =====\n"
            f"{e.digest}\n"
            f"===== END {e.rel_path} ====="
        )
    return (
        "AVAILABLE EVIDENCE FILES (these are the ONLY files you may cite):\n"
        + "\n".join(manifest_lines)
        + "\n\n"
        + "FILE CONTENTS (line numbers shown on the left are real and citable):\n\n"
        + "\n\n".join(blocks)
    )


# ── Prompting ────────────────────────────────────────────────────────────────

DREAMER_SYSTEM = """\
You are the Dreamer: a product-minded research engineer for an AI text-to-story
service called Unorthodox Writer. You read the project's telemetry and propose
improvements. You are an ANALYST and PROPOSER only — you never write code, never
change configuration, and never decide anything. Humans review every idea you
produce.

You reason like a senior engineer triaging signals:
  * What is working well and should be reinforced?
  * What is underperforming and should be fixed?
  * What is missing and should be built?
  * What single change has the best impact-to-effort ratio?

Hard rules:
  * Ground every claim in the evidence provided. Cite specific files and line
    numbers from the digest. If you cannot support a pattern with the evidence in
    front of you, do NOT propose it — say less rather than inventing.
  * Only cite files listed in "AVAILABLE EVIDENCE FILES". Never invent a path,
    a line number, or a metric value.
  * Be concrete. "Improve the prompt" is useless; "Add a repetition guard that
    rejects any 6-gram repeated across paragraphs, per the recycled triplet in
    AGY_FEEDBACK.md" is useful.
"""

# The exact JSON contract the model must emit. The Dreamer fills in the
# bookkeeping fields (idea_id, timestamps, status, etc.) afterwards, so the model
# is told NOT to produce them.
USER_PROMPT_TEMPLATE = """\
Below is the full telemetry digest for the Unorthodox Writer project. Study it,
find real patterns, and propose {min_n}-{max_n} candidate improvements.

{context}

Return ONLY a JSON array (no prose, no markdown fences) of {min_n}-{max_n} objects.
Each object MUST have exactly these fields:

  "signal":            string  — the specific pattern you observed (be falsifiable)
  "proposal":          string  — the concrete, actionable change to consider
  "category":          one of ["model_selection","prompt_engineering",
                               "pipeline_architecture","quality_gate",
                               "tier_policy","new_feature"]
  "evidence":          array of strings — file refs with line numbers, e.g.
                       "test_output/optimized_v2_report.json:104-107". Use ONLY
                       files from the AVAILABLE EVIDENCE FILES list. >=1 required.
  "confidence":        one of ["high","medium","low"]  — how well evidence supports it
  "risk_band":         one of ["low","medium","high"]   — risk of adopting the change
  "estimated_effort":  one of ["small","medium","large"]
  "impact":            one of ["low","medium","high"]
  "non_goals":         array of strings — what this proposal explicitly does NOT cover
  "related_ideas":     array of strings — leave as [] (no prior ideas to reference)

Do NOT include idea_id, generated_at, generated_by, model_used, schema_version, or
status — those are added automatically.

Rank your ideas best-first by impact-to-effort ratio. Prefer fewer, well-evidenced
ideas over many weak ones. Output the JSON array and nothing else.
"""


def build_user_prompt(context: str, min_n: int, max_n: int) -> str:
    return USER_PROMPT_TEMPLATE.format(context=context, min_n=min_n, max_n=max_n)


# ── Model output parsing ─────────────────────────────────────────────────────


def _strip_code_fences(text: str) -> str:
    """Remove a leading ```json / ``` fence and its closing fence, if present."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def parse_ideas(raw: str) -> list[dict[str, Any]]:
    """Extract a list of idea dicts from the model's raw response.

    Tolerant of code fences, leading prose, and a top-level ``{"ideas": [...]}``
    wrapper. Returns an empty list if nothing parseable is found.
    """
    text = _strip_code_fences(raw)

    def _coerce(obj: Any) -> list[dict[str, Any]]:
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict):
            for key in ("ideas", "contracts", "proposals", "items"):
                if isinstance(obj.get(key), list):
                    return [x for x in obj[key] if isinstance(x, dict)]
            # A single bare object — treat as a one-item batch.
            return [obj]
        return []

    # Fast path: the whole thing is valid JSON.
    try:
        return _coerce(json.loads(text))
    except json.JSONDecodeError:
        pass

    # Fallback: carve out the outermost [...] or {...} and parse that.
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return _coerce(json.loads(text[start : end + 1]))
            except json.JSONDecodeError:
                continue
    return []


# ── Normalisation, evidence checking, contract assembly ──────────────────────


def _norm_enum(value: Any) -> str:
    return str(value).strip().lower() if value is not None else ""


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _evidence_path_token(ref: str) -> str:
    """Pull the file path out of an evidence reference.

    Handles "path", "path:120", "path:10-20", and "path (lines 10-20)".
    """
    token = ref.strip()
    # Cut at the first ':' that is not part of a drive/scheme (none expected here).
    for sep in (":", "(", " "):
        idx = token.find(sep)
        if idx > 0:
            token = token[:idx]
    return token.strip().strip(",").rstrip("/")


def filter_evidence(refs: list[str], known: dict[str, str]) -> tuple[list[str], list[str]]:
    """Split evidence refs into (valid, invalid).

    ``known`` maps both relative paths and bare filenames to the canonical
    relative path. A ref is valid iff its path token resolves to a known file.
    """
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        token = _evidence_path_token(ref)
        key = token.lstrip("./")
        canonical = known.get(key) or known.get(Path(key).name)
        if canonical and ref not in seen:
            valid.append(ref)
            seen.add(ref)
        elif not canonical:
            invalid.append(ref)
    return valid, invalid


def assemble_contract(
    raw_idea: dict[str, Any],
    *,
    idea_id: str,
    generated_at: str,
    model_used: str,
    known_files: dict[str, str],
) -> tuple[Optional[dict[str, Any]], list[str]]:
    """Turn a raw model idea into a finished contract.

    Returns ``(contract, problems)``. ``contract`` is ``None`` when the idea is
    unusable (e.g. no valid evidence survives). ``problems`` collects
    human-readable notes about anything that was repaired or rejected.
    """
    problems: list[str] = []

    valid_evidence, invalid_evidence = filter_evidence(
        _as_str_list(raw_idea.get("evidence")), known_files
    )
    if invalid_evidence:
        problems.append(
            "dropped unknown evidence refs: " + ", ".join(invalid_evidence)
        )
    if not valid_evidence:
        problems.append("no valid evidence references — discarded")
        return None, problems

    contract = {
        "schema_version": 1,
        "idea_id": idea_id,
        "generated_at": generated_at,
        "generated_by": "dreamer",
        "model_used": model_used,
        "signal": str(raw_idea.get("signal", "")).strip(),
        "proposal": str(raw_idea.get("proposal", "")).strip(),
        "category": _norm_enum(raw_idea.get("category")),
        "evidence": valid_evidence,
        "confidence": _norm_enum(raw_idea.get("confidence")),
        "risk_band": _norm_enum(raw_idea.get("risk_band")),
        "estimated_effort": _norm_enum(raw_idea.get("estimated_effort")),
        "impact": _norm_enum(raw_idea.get("impact")),
        "non_goals": _as_str_list(raw_idea.get("non_goals")),
        "related_ideas": _as_str_list(raw_idea.get("related_ideas")),
        # SAFETY: the Dreamer never approves its own ideas.
        "status": "proposed",
    }
    return contract, problems


# ── Validation ───────────────────────────────────────────────────────────────


def load_validator():
    """Return a function ``validate(contract) -> list[str]`` of error messages.

    Uses ``jsonschema`` if installed; otherwise falls back to a minimal built-in
    check so the Dreamer still refuses to write malformed contracts.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    try:
        import jsonschema
        from jsonschema import Draft202012Validator

        validator = Draft202012Validator(schema)

        def validate(contract: dict[str, Any]) -> list[str]:
            return [
                f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
                for err in sorted(validator.iter_errors(contract), key=str)
            ]

        return validate
    except ImportError:
        print("  ⚠ jsonschema not installed — using built-in fallback validation.")
        return _fallback_validate


def _fallback_validate(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "idea_id", "generated_at", "generated_by", "model_used",
        "signal", "proposal", "category", "evidence", "confidence", "risk_band",
        "estimated_effort", "impact", "non_goals", "related_ideas", "status",
    }
    missing = required - contract.keys()
    if missing:
        errors.append(f"missing fields: {', '.join(sorted(missing))}")
    if contract.get("status") != "proposed":
        errors.append("status must be 'proposed'")
    if contract.get("generated_by") != "dreamer":
        errors.append("generated_by must be 'dreamer'")
    if contract.get("category") not in CATEGORY_ENUM:
        errors.append(f"category not in enum: {contract.get('category')!r}")
    if contract.get("confidence") not in LOW_MED_HIGH:
        errors.append(f"confidence not in enum: {contract.get('confidence')!r}")
    if contract.get("risk_band") not in LOW_MED_HIGH:
        errors.append(f"risk_band not in enum: {contract.get('risk_band')!r}")
    if contract.get("impact") not in LOW_MED_HIGH:
        errors.append(f"impact not in enum: {contract.get('impact')!r}")
    if contract.get("estimated_effort") not in EFFORT_ENUM:
        errors.append(f"estimated_effort not in enum: {contract.get('estimated_effort')!r}")
    if not isinstance(contract.get("evidence"), list) or not contract.get("evidence"):
        errors.append("evidence must be a non-empty array")
    if not re.match(r"^[0-9]{8}-[0-9]{4}-[0-9]{3}$", str(contract.get("idea_id", ""))):
        errors.append("idea_id must match YYYYMMDD-HHMM-NNN")
    return errors


# ── Near-duplicate detection ─────────────────────────────────────────────────


def _dup_key(contract: dict[str, Any]) -> str:
    text = f"{contract.get('signal', '')} {contract.get('proposal', '')}".lower()
    return re.sub(r"\s+", " ", text).strip()


def load_existing_contracts(ideas_dir: Path) -> list[dict[str, Any]]:
    """Load every contract previously written under ``ideas_dir``."""
    existing: list[dict[str, Any]] = []
    if not ideas_dir.is_dir():
        return existing
    for path in sorted(ideas_dir.glob("idea-contract-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            existing.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            if isinstance(data.get("ideas"), list):
                existing.extend(x for x in data["ideas"] if isinstance(x, dict))
            else:
                existing.append(data)
    return existing


def is_near_duplicate(
    candidate: dict[str, Any],
    corpus_keys: list[tuple[str, str]],
    threshold: float = DUP_THRESHOLD,
) -> Optional[str]:
    """Return the idea_id of a near-duplicate in ``corpus_keys`` or ``None``.

    ``corpus_keys`` is a list of ``(idea_id, dup_key)`` pairs.
    """
    cand_key = _dup_key(candidate)
    if not cand_key:
        return None
    for idea_id, key in corpus_keys:
        if not key:
            continue
        if SequenceMatcher(None, cand_key, key).ratio() >= threshold:
            return idea_id
    return None


# ── DeepSeek call ────────────────────────────────────────────────────────────


async def _call_deepseek(prompt: str, max_tokens: int) -> tuple[str, str]:
    """Send the prompt to DeepSeek and return ``(text, model_id)``."""
    backend = CloudBackend(provider="deepseek", max_tokens=max_tokens)
    try:
        text = await backend.generate_full(prompt, system_prompt=DREAMER_SYSTEM)
        return text, backend.model
    finally:
        await backend.close()


# ── Orchestration ────────────────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _unique_output_path(ideas_dir: Path, stamp_minute: str) -> Path:
    """Pick an output filename, falling back to seconds precision on collision."""
    path = ideas_dir / f"idea-contract-{stamp_minute}.json"
    if not path.exists():
        return path
    stamp_second = _now_utc().strftime("%Y%m%d-%H%M%S")
    return ideas_dir / f"idea-contract-{stamp_second}.json"


def run(
    *,
    test_output_dir: Path = TEST_OUTPUT_DIR,
    ideas_dir: Path = IDEAS_DIR,
    min_ideas: int = 3,
    max_ideas: int = 5,
    max_tokens: int = 4096,
    dup_threshold: float = DUP_THRESHOLD,
    dry_run: bool = False,
) -> int:
    print("=== Dreamer (Auto-Think) — telemetry → candidate idea contracts ===\n")

    # 1) Gather evidence ------------------------------------------------------
    print(f"STEP 1 — scanning {test_output_dir.relative_to(REPO_ROOT)} for telemetry")
    evidence = gather_evidence(test_output_dir)
    if not evidence:
        print("  ✗ no evidence files found — nothing to analyse.")
        return 1
    for e in evidence:
        print(f"  • {e.rel_path}  ({e.line_count} lines, {e.byte_size} bytes)")
    known_files: dict[str, str] = {}
    for e in evidence:
        known_files[e.rel_path] = e.rel_path
        known_files[e.name] = e.rel_path
    context = render_context(evidence)
    print(f"  → digest assembled: {len(context)} chars from {len(evidence)} files\n")

    if dry_run:
        print("STEP 2 — DRY RUN: skipping DeepSeek call and write.")
        print("\n----- evidence digest preview (first 60 lines) -----")
        print("\n".join(context.splitlines()[:60]))
        return 0

    # 2) Generate ideas with DeepSeek ----------------------------------------
    print("STEP 2 — asking DeepSeek to identify patterns and propose ideas")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("  ✗ DEEPSEEK_API_KEY not set. Source the repo .env or export the key.")
        return 2
    prompt = build_user_prompt(context, min_ideas, max_ideas)
    try:
        raw, model_used = asyncio.run(_call_deepseek(prompt, max_tokens))
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ DeepSeek call failed: {exc}")
        return 3
    print(f"  ✓ DeepSeek ({model_used}) returned {len(raw)} chars")

    raw_ideas = parse_ideas(raw)
    if not raw_ideas:
        print("  ✗ could not parse any idea objects from the model response.")
        print("\n----- raw response (first 1200 chars) -----")
        print(raw[:1200])
        return 4
    print(f"  → parsed {len(raw_ideas)} candidate idea(s)\n")

    # 3) Assemble + validate contracts ---------------------------------------
    print("STEP 3 — assembling, validating and de-duplicating contracts")
    validate = load_validator()
    existing = load_existing_contracts(ideas_dir)
    corpus_keys: list[tuple[str, str]] = [
        (c.get("idea_id", "?"), _dup_key(c)) for c in existing
    ]
    if existing:
        print(f"  (loaded {len(existing)} prior contract(s) for duplicate checking)")

    now = _now_utc()
    generated_at = now.isoformat()
    stamp_minute = now.strftime("%Y%m%d-%H%M")

    accepted: list[dict[str, Any]] = []
    seq = 0
    for i, raw_idea in enumerate(raw_ideas, start=1):
        idea_id = f"{stamp_minute}-{seq + 1:03d}"
        contract, problems = assemble_contract(
            raw_idea,
            idea_id=idea_id,
            generated_at=generated_at,
            model_used=model_used,
            known_files=known_files,
        )
        label = f"  [{i}/{len(raw_ideas)}]"
        if contract is None:
            print(f"{label} ✗ rejected — {'; '.join(problems)}")
            continue
        for note in problems:
            print(f"{label} ⚠ {note}")

        errors = validate(contract)
        if errors:
            print(f"{label} ✗ schema validation failed:")
            for err in errors:
                print(f"        - {err}")
            continue

        dup_of = is_near_duplicate(contract, corpus_keys, dup_threshold)
        if dup_of:
            print(f"{label} ⊘ near-duplicate of {dup_of} (similarity ≥ {dup_threshold}) — skipped")
            continue

        # Accept: claim this idea_id, and add to the corpus so later ideas in the
        # same batch are also de-duplicated against it.
        seq += 1
        corpus_keys.append((idea_id, _dup_key(contract)))
        accepted.append(contract)
        cat = contract["category"]
        print(
            f"{label} ✓ {idea_id}  [{cat}]  "
            f"impact={contract['impact']} effort={contract['estimated_effort']} "
            f"risk={contract['risk_band']} conf={contract['confidence']}"
        )

    print(f"\n  → {len(accepted)} contract(s) accepted "
          f"out of {len(raw_ideas)} parsed\n")

    if not accepted:
        print("STEP 4 — nothing new to write (all ideas were invalid or duplicates).")
        return 0

    # 4) Save -----------------------------------------------------------------
    ideas_dir.mkdir(parents=True, exist_ok=True)
    out_path = _unique_output_path(ideas_dir, stamp_minute)
    out_path.write_text(json.dumps(accepted, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"STEP 4 — wrote {len(accepted)} contract(s) to "
          f"{out_path.relative_to(REPO_ROOT)}")
    for c in accepted:
        print(f"  • {c['idea_id']}  {c['signal'][:78]}")
    return 0


# ── .env loading (mirror of the optimizer) ───────────────────────────────────


def _load_env_from_dotenv() -> None:
    """Load DEEPSEEK_* / OLLAMA_URL from the repo .env if not already set.

    Mirrors ``source .env`` for the keys the Dreamer needs, so it runs the same
    way under a bare ``PYTHONPATH=. python engine/dreamer.py``.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    wanted = {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"}
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


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="The Dreamer — read project telemetry and propose candidate "
                    "idea contracts for human review. Read-only except for writing "
                    "contracts under test_output/ideas/.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="build the evidence digest only; no API call, no write")
    parser.add_argument("--min-ideas", type=int, default=3,
                        help="minimum ideas to request (default: 3)")
    parser.add_argument("--max-ideas", type=int, default=5,
                        help="maximum ideas to request (default: 5)")
    parser.add_argument("--max-tokens", type=int, default=4096,
                        help="max output tokens for DeepSeek (default: 4096)")
    parser.add_argument("--dup-threshold", type=float, default=DUP_THRESHOLD,
                        help=f"near-duplicate similarity cutoff (default: {DUP_THRESHOLD})")
    parser.add_argument("--test-output", type=Path, default=TEST_OUTPUT_DIR,
                        help="telemetry directory to scan (default: test_output/)")
    args = parser.parse_args(argv)

    _load_env_from_dotenv()
    return run(
        test_output_dir=args.test_output,
        ideas_dir=(args.test_output / "ideas"),
        min_ideas=args.min_ideas,
        max_ideas=args.max_ideas,
        max_tokens=args.max_tokens,
        dup_threshold=args.dup_threshold,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
