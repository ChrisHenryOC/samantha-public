"""Analyze tiered model routing using existing evaluation data.

Loads per-step decisions from evaluation databases (READ-ONLY) for three
models, applies step classifications from classify_steps.py, and simulates
a tiered routing strategy where a fast model handles deterministic steps
and a capable model handles judgment-requiring steps.

Outputs results/tiered_routing_analysis.md with comparison tables.

Usage:
    uv run python scripts/classify_steps.py   # run first
    uv run python scripts/analyze_tiered_routing.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CLASSIFICATIONS_PATH = _PROJECT_ROOT / "data" / "step_classifications.json"
_OUTPUT_PATH = _PROJECT_ROOT / "results" / "tiered_routing_analysis.md"

# Evaluation databases (opened READ-ONLY)
_DB_PATHS = {
    "Gemma 3 27B": _PROJECT_ROOT / "results" / "h2h_gemma_27b_screening" / "evaluation.db",
    "Qwen2.5 Coder 32B": _PROJECT_ROOT / "results" / "h2h_coder_screening" / "evaluation.db",
    "Qwen3 Coder 30B-A3B": _PROJECT_ROOT / "results" / "qwen3_coder_30b_full" / "evaluation.db",
}

# Screening set scenario IDs (must match classify_steps.py)
SCREENING_IDS = frozenset(
    {
        "SC-003",
        "SC-005",
        "SC-006",
        "SC-009",
        "SC-010",
        "SC-011",
        "SC-012",
        "SC-013",
        "SC-014",
        "SC-016",
        "SC-019",
        "SC-020",
        "SC-024",
        "SC-026",
        "SC-028",
        "SC-038",
        "SC-045",
        "SC-081",
        "SC-082",
        "SC-087",
        "SC-088",
        "SC-100",
        "SC-101",
        "SC-102",
        "SC-103",
        "SC-106",
        "SC-107",
        "SC-108",
        "SC-109",
        "SC-110",
        "SC-111",
        "SC-112",
        "SC-113",
    }
)

# Pattern to extract scenario ID and step from decision_id
# e.g. "run-qwen2.5-coder-32b-1-af48cc26-SC-019-S2"
_DECISION_ID_RE = re.compile(r"(SC-\d+)-S(\d+)$")


@dataclass
class StepDecision:
    """One step's evaluation result from the database."""

    scenario_id: str
    step: int
    run_number: int
    state_correct: bool
    rules_correct: bool
    flags_correct: bool
    latency_ms: int


def load_decisions(db_path: Path) -> list[StepDecision]:
    """Load per-step decisions from an evaluation.db (READ-ONLY)."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT d.decision_id, r.run_number, d.state_correct, "
            "d.rules_correct, d.flags_correct, d.latency_ms "
            "FROM decisions d JOIN runs r ON d.run_id = r.run_id"
        ).fetchall()
    finally:
        conn.close()

    decisions = []
    for decision_id, run_number, state_ok, rules_ok, flags_ok, latency in rows:
        match = _DECISION_ID_RE.search(decision_id)
        if not match:
            continue
        scenario_id = match.group(1)
        step = int(match.group(2))
        # Filter to screening set
        if scenario_id not in SCREENING_IDS:
            continue
        decisions.append(
            StepDecision(
                scenario_id=scenario_id,
                step=step,
                run_number=run_number,
                state_correct=bool(state_ok),
                rules_correct=bool(rules_ok),
                flags_correct=bool(flags_ok),
                latency_ms=latency,
            )
        )
    return decisions


def compute_metrics(
    decisions: list[StepDecision],
) -> dict[str, float]:
    """Compute accuracy metrics from a list of step decisions."""
    if not decisions:
        return {
            "state_acc": 0,
            "rule_acc": 0,
            "flag_acc": 0,
            "mean_latency": 0,
            "p50_latency": 0,
            "count": 0,
        }
    n = len(decisions)
    state_acc = sum(d.state_correct for d in decisions) / n * 100
    rule_acc = sum(d.rules_correct for d in decisions) / n * 100
    flag_acc = sum(d.flags_correct for d in decisions) / n * 100
    latencies = sorted(d.latency_ms for d in decisions)
    mean_lat = sum(latencies) / n
    p50_lat = latencies[n // 2]
    return {
        "state_acc": round(state_acc, 1),
        "rule_acc": round(rule_acc, 1),
        "flag_acc": round(flag_acc, 1),
        "mean_latency": round(mean_lat),
        "p50_latency": p50_lat,
        "count": n,
    }


def main() -> int:
    # Load step classifications
    if not _CLASSIFICATIONS_PATH.exists():
        print(
            f"ERROR: {_CLASSIFICATIONS_PATH} not found. Run scripts/classify_steps.py first.",
            file=sys.stderr,
        )
        return 1

    with open(_CLASSIFICATIONS_PATH) as f:
        classifications = json.load(f)

    step_types: dict[str, str] = {}
    for key, info in classifications["steps"].items():
        step_types[key] = info["classification"]

    summary = classifications["summary"]
    print(
        f"Loaded {summary['total_steps']} step classifications "
        f"({summary['deterministic']} deterministic, {summary['judgment']} judgment)"
    )

    # Load decisions from all three models
    all_decisions: dict[str, list[StepDecision]] = {}
    for model_name, db_path in _DB_PATHS.items():
        if not db_path.exists():
            print(f"ERROR: {db_path} not found", file=sys.stderr)
            return 1
        decisions = load_decisions(db_path)
        all_decisions[model_name] = decisions
        print(f"Loaded {len(decisions)} decisions for {model_name}")

    # Split decisions by step type
    def split_by_type(
        decisions: list[StepDecision],
    ) -> tuple[list[StepDecision], list[StepDecision]]:
        det, jud = [], []
        for d in decisions:
            key = f"{d.scenario_id}-S{d.step}"
            stype = step_types.get(key, "deterministic")
            if stype == "judgment":
                jud.append(d)
            else:
                det.append(d)
        return det, jud

    # Table 1: Accuracy by step classification
    table1_rows = []
    for model_name in _DB_PATHS:
        det, jud = split_by_type(all_decisions[model_name])
        det_m = compute_metrics(det)
        jud_m = compute_metrics(jud)
        table1_rows.append((model_name, "Deterministic", det_m))
        table1_rows.append((model_name, "Judgment", jud_m))

    # Table 2: Simulated tiered routing
    # For each fast model candidate, simulate: use fast model on deterministic,
    # Coder 32B on judgment
    coder_decisions = all_decisions["Qwen2.5 Coder 32B"]
    coder_by_key_run: dict[tuple[str, int], StepDecision] = {}
    for d in coder_decisions:
        coder_by_key_run[(f"{d.scenario_id}-S{d.step}", d.run_number)] = d

    table2_rows = []
    for model_name in _DB_PATHS:
        m = compute_metrics(all_decisions[model_name])
        table2_rows.append((f"{model_name} only", m))

    # Tiered simulations
    fast_models = ["Gemma 3 27B", "Qwen3 Coder 30B-A3B"]
    for fast_name in fast_models:
        fast_decisions = all_decisions[fast_name]
        tiered: list[StepDecision] = []
        missing = 0
        for d in fast_decisions:
            key = f"{d.scenario_id}-S{d.step}"
            stype = step_types.get(key, "deterministic")
            if stype == "judgment":
                # Use Coder 32B's answer
                coder_d = coder_by_key_run.get((key, d.run_number))
                if coder_d:
                    tiered.append(coder_d)
                else:
                    missing += 1
                    tiered.append(d)  # Fallback to fast model
            else:
                tiered.append(d)
        if missing:
            print(f"  Warning: {missing} judgment steps missing Coder 32B data for {fast_name}")
        m = compute_metrics(tiered)
        table2_rows.append((f"Tiered ({fast_name} + Coder 32B)", m))

    # Generate markdown report
    lines = [
        "# Tiered Model Routing Analysis",
        "",
        "Simulated tiered routing using existing evaluation data.",
        f"Screening set: {len(SCREENING_IDS)} scenarios, {summary['total_steps']} total steps.",
        "",
        "## Table 1: Accuracy by Step Classification",
        "",
        "| Model | Step Type | Count | State Acc | Rule Acc | Flag Acc |",
        "|-------|-----------|-------|-----------|----------|----------|",
    ]
    for model_name, step_type, m in table1_rows:
        lines.append(
            f"| {model_name} | {step_type} | {m['count']} | "
            f"{m['state_acc']}% | {m['rule_acc']}% | {m['flag_acc']}% |"
        )

    lines.extend(
        [
            "",
            "## Table 2: Simulated Tiered Routing vs Baselines",
            "",
            "| Approach | State Acc | Rule Acc | Flag Acc | Mean Latency | p50 Latency |",
            "|----------|-----------|----------|----------|-------------|------------|",
        ]
    )
    for label, m in table2_rows:
        lines.append(
            f"| {label} | {m['state_acc']}% | {m['rule_acc']}% | "
            f"{m['flag_acc']}% | {m['mean_latency']}ms | {m['p50_latency']}ms |"
        )

    lines.extend(
        [
            "",
            "## Table 3: Step Classification Summary",
            "",
            "| Category | Count | Percentage |",
            "|----------|-------|------------|",
            f"| Deterministic | {summary['deterministic']} | {summary['deterministic_pct']}% |",
            f"| Judgment | {summary['judgment']} | {summary['judgment_pct']}% |",
            f"| **Total** | **{summary['total_steps']}** | **100%** |",
            "",
            "## Success Criteria Assessment",
            "",
        ]
    )

    # Assess success criteria
    for fast_name in fast_models:
        det, _ = split_by_type(all_decisions[fast_name])
        det_m = compute_metrics(det)
        lines.append(f"### {fast_name}")
        lines.append("")
        lines.append(
            f"1. Deterministic step accuracy: **{det_m['state_acc']}%** "
            f"({'PASS' if det_m['state_acc'] >= 98 else 'FAIL'} — threshold: >= 98%)"
        )
        # Find tiered result
        for label, m in table2_rows:
            if fast_name in label and "Tiered" in label:
                coder_m = compute_metrics(coder_decisions)
                gap = abs(m["state_acc"] - coder_m["state_acc"])
                lines.append(
                    f"2. Tiered accuracy gap vs Coder 32B: **{gap}pp** "
                    f"({'PASS' if gap <= 1 else 'FAIL'} — threshold: <= 1pp)"
                )
                lat_pass = m["mean_latency"] < coder_m["mean_latency"]
                lines.append(
                    f"3. Tiered mean latency: **{m['mean_latency']}ms** vs "
                    f"Coder 32B {coder_m['mean_latency']}ms "
                    f"({'PASS' if lat_pass else 'FAIL'} — must be lower)"
                )
                break
        lines.append("")

    lines.append(f"Judgment rules evaluated: {', '.join(summary['judgment_rules'])}")
    lines.append("")

    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_PATH, "w") as f:
        f.write("\n".join(lines))

    print(f"\nOutput: {_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
