"""Benchmark local Ollama models for feasibility validation.

Measures inference speed and JSON parsability for each
candidate model. Results are written to
results/model_feasibility/<YYYY-MM-DD_HH-MM>/<prompt>/.

Usage:
    uv run python scripts/benchmark_models.py
    uv run python scripts/benchmark_models.py --models llama3.1:8b mistral:7b
    uv run python scripts/benchmark_models.py --runs 3
    uv run python scripts/benchmark_models.py --prompt baseline enriched --skip-pull
    uv run python scripts/benchmark_models.py --prompt enriched --skip-pull
"""

from __future__ import annotations

import json
import signal
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CANDIDATE_MODELS: list[str] = [
    "llama3.1:8b",
    "mistral:7b",
    "phi3:latest",
    "gemma2:27b",
    "Qwen2.5:32b-instruct-q4_K_M",
]

RUNS_PER_MODEL = 3

BASELINE_PROMPT = """\
You are a laboratory workflow routing engine for breast cancer specimens.
Given the current order state and a new event, determine the next workflow
state by matching rules from the rule catalog.

Current order state: ACCESSIONING
New event: order_received

Order details:
- specimen_type: core_biopsy
- anatomic_site: left_breast
- fixative: 10pct_nbf
- fixation_time_hours: 12
- patient_name: Jane Doe
- patient_sex: female
- mrn: MRN-12345
- date_of_birth: 1965-03-15
- ordering_physician: Dr. Smith
- clinical_history: Suspicious mass, BI-RADS 5
- insurance_info: BlueCross-1234

All required fields are present and valid.

Respond with ONLY a JSON object in this exact format, no other text:
{
  "next_state": "<state>",
  "applied_rules": ["<rule_id>"],
  "flags": [],
  "reasoning": "<brief explanation>"
}
"""

ENRICHED_PROMPT = """\
You are a laboratory workflow routing engine for breast cancer specimens.
Your job is to match rules from the rule catalog and produce the correct
next state. You MUST only use states and rule IDs from the lists below.

## Valid Workflow States

ACCESSIONING, ACCEPTED, MISSING_INFO_HOLD, MISSING_INFO_PROCEED,
DO_NOT_PROCESS, SAMPLE_PREP_PROCESSING, SAMPLE_PREP_EMBEDDING,
SAMPLE_PREP_SECTIONING, SAMPLE_PREP_QC, HE_STAINING, HE_QC,
PATHOLOGIST_HE_REVIEW, IHC_STAINING, IHC_QC, IHC_SCORING,
SUGGEST_FISH_REFLEX, FISH_SEND_OUT, RESULTING_HOLD, RESULTING,
PATHOLOGIST_SIGNOUT, REPORT_GENERATION, ORDER_COMPLETE,
ORDER_TERMINATED, ORDER_TERMINATED_QNS

## Accessioning Rules (evaluated for current step)

All accessioning rules are evaluated on every order. Multiple rules can
fire simultaneously. The highest-severity outcome wins:
DO_NOT_PROCESS > MISSING_INFO_HOLD > MISSING_INFO_PROCEED > ACCEPTED.
Report ALL matching rules in applied_rules.

| Rule ID | Trigger | Action | Severity |
|---------|---------|--------|----------|
| ACC-001 | Patient name missing | MISSING_INFO_HOLD | HOLD |
| ACC-002 | Patient sex missing | MISSING_INFO_HOLD | HOLD |
| ACC-003 | Anatomic site not breast-cancer-relevant | DO_NOT_PROCESS | REJECT |
| ACC-004 | Specimen type incompatible with histology (e.g. FNA) | DO_NOT_PROCESS | REJECT |
| ACC-005 | HER2 ordered + fixative is not formalin | DO_NOT_PROCESS | REJECT |
| ACC-006 | HER2 ordered + fixation time outside 6-72 hours | DO_NOT_PROCESS | REJECT |
| ACC-007 | Billing info missing | MISSING_INFO_PROCEED | PROCEED |
| ACC-008 | All validations pass | ACCEPTED | ACCEPT |

## Valid Flags

MISSING_INFO_PROCEED, FIXATION_WARNING, RECUT_REQUESTED,
HER2_FIXATION_REJECT, FISH_SUGGESTED

## Current Situation

Current order state: ACCESSIONING
New event: order_received

Order details:
- specimen_type: core_biopsy
- anatomic_site: left_breast
- fixative: 10pct_nbf
- fixation_time_hours: 12
- patient_name: Jane Doe
- patient_sex: female
- mrn: MRN-12345
- date_of_birth: 1965-03-15
- ordering_physician: Dr. Smith
- clinical_history: Suspicious mass, BI-RADS 5
- insurance_info: BlueCross-1234
- tests_ordered: ER, PR, HER2, Ki-67

All required fields are present. Specimen type is valid for histology.
Anatomic site is breast. Fixative is formalin. Fixation time is 12 hours
(within 6-72 range). Billing info is present.

Respond with ONLY a JSON object in this exact format, no other text:
{
  "next_state": "<state from valid states list>",
  "applied_rules": ["<rule_id from table above>"],
  "flags": [],
  "reasoning": "<brief explanation of which rules matched and why>"
}
"""

PROMPTS: dict[str, str] = {
    "baseline": BASELINE_PROMPT,
    "enriched": ENRICHED_PROMPT,
}

EXPECTED_STATES = {
    "ACCESSIONING",
    "ACCEPTED",
    "MISSING_INFO_HOLD",
    "MISSING_INFO_PROCEED",
    "DO_NOT_PROCESS",
    "SAMPLE_PREP_PROCESSING",
    "SAMPLE_PREP_EMBEDDING",
    "SAMPLE_PREP_SECTIONING",
    "SAMPLE_PREP_QC",
    "HE_STAINING",
    "HE_QC",
    "PATHOLOGIST_HE_REVIEW",
    "IHC_STAINING",
    "IHC_QC",
    "IHC_SCORING",
    "SUGGEST_FISH_REFLEX",
    "FISH_SEND_OUT",
    "RESULTING_HOLD",
    "RESULTING",
    "PATHOLOGIST_SIGNOUT",
    "REPORT_GENERATION",
    "ORDER_COMPLETE",
    "ORDER_TERMINATED",
    "ORDER_TERMINATED_QNS",
}

RULE_ID_PREFIXES = {"ACC", "SP", "HE", "IHC", "RES"}

OUTPUT_DIR = Path("results/model_feasibility")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Result of a single model inference run."""

    run_number: int
    time_to_first_token_s: float | None
    total_duration_s: float
    tokens_per_second: float | None
    json_valid: bool
    has_valid_state: bool
    has_valid_rules: bool
    raw_output: str
    parsed_output: dict[str, object] | None


@dataclass
class ModelResult:
    """Aggregated results for a single model."""

    model_name: str
    pull_success: bool
    model_size_gb: float | None
    runs: list[RunResult] = field(default_factory=list)

    @property
    def avg_total_duration_s(self) -> float | None:
        durations = [r.total_duration_s for r in self.runs]
        return sum(durations) / len(durations) if durations else None

    @property
    def avg_tokens_per_second(self) -> float | None:
        rates = [r.tokens_per_second for r in self.runs if r.tokens_per_second]
        return sum(rates) / len(rates) if rates else None

    @property
    def json_success_rate(self) -> float:
        if not self.runs:
            return 0.0
        return sum(1 for r in self.runs if r.json_valid) / len(self.runs)

    @property
    def valid_state_rate(self) -> float:
        if not self.runs:
            return 0.0
        return sum(1 for r in self.runs if r.has_valid_state) / len(self.runs)

    @property
    def valid_rules_rate(self) -> float:
        if not self.runs:
            return 0.0
        return sum(1 for r in self.runs if r.has_valid_rules) / len(self.runs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_command(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    """Run a shell command and return the result."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def check_ollama_running() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        result = run_command(["ollama", "list"], timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pull_model(model_name: str) -> bool:
    """Pull a model via ollama pull. Returns True on success."""
    print(f"  Pulling {model_name}...")
    try:
        result = run_command(["ollama", "pull", model_name], timeout=1800)
    except subprocess.TimeoutExpired:
        print(f"  ERROR pulling {model_name}: timed out after 30 minutes")
        return False
    if result.returncode != 0:
        print(f"  ERROR pulling {model_name}: {result.stderr.strip()}")
        return False
    print(f"  Successfully pulled {model_name}")
    return True


def get_model_size_gb(model_name: str) -> float | None:
    """Get the approximate model parameter size from ollama show.

    Returns the first numeric value from lines containing 'size' or
    'parameters' in the output of ``ollama show``. The value is
    typically the parameter count in billions (e.g. 8.0 for an 8B
    model), not an on-disk byte count.
    """
    try:
        result = run_command(["ollama", "show", model_name], timeout=30)
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            lower = line.lower()
            if "size" in lower or "parameters" in lower:
                for part in line.split():
                    # Strip trailing unit suffixes (e.g. "8.0B", "32.8B")
                    cleaned = part.rstrip("BbMmKk")
                    try:
                        val = float(cleaned)
                        # Sanity: parameter counts are typically 0.5–200
                        if 0.1 <= val <= 500:
                            return val
                    except ValueError:
                        continue
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def start_ollama() -> subprocess.Popen[str]:
    """Start the Ollama server and wait until it's responsive."""
    print("  Starting ollama serve...")
    proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait up to 30s for ollama to become responsive
    for _ in range(30):
        time.sleep(1)
        if check_ollama_running():
            print("  Ollama is ready.")
            return proc
    proc.kill()
    proc.wait()
    raise RuntimeError("Ollama failed to start within 30 seconds")


def stop_ollama(proc: subprocess.Popen[str]) -> None:
    """Stop the Ollama server gracefully, then force-kill if needed."""
    print("  Stopping ollama...")
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    # Give the OS a moment to free resources
    time.sleep(2)
    print("  Ollama stopped.")


def run_inference(model_name: str, prompt: str, run_number: int = 0) -> RunResult:
    """Run a single inference and measure performance."""
    start = time.perf_counter()

    try:
        result = subprocess.run(
            ["ollama", "run", model_name, prompt],
            capture_output=True,
            text=True,
            timeout=300,
        )
        total_duration = time.perf_counter() - start
    except subprocess.TimeoutExpired:
        return RunResult(
            run_number=run_number,
            time_to_first_token_s=None,
            total_duration_s=300.0,
            tokens_per_second=None,
            json_valid=False,
            has_valid_state=False,
            has_valid_rules=False,
            raw_output="TIMEOUT after 300s",
            parsed_output=None,
        )

    # Check for process errors
    if result.returncode != 0:
        error_msg = result.stderr.strip() or f"exit code {result.returncode}"
        return RunResult(
            run_number=run_number,
            time_to_first_token_s=None,
            total_duration_s=total_duration,
            tokens_per_second=None,
            json_valid=False,
            has_valid_state=False,
            has_valid_rules=False,
            raw_output=f"ERROR: {error_msg}",
            parsed_output=None,
        )

    raw_output = result.stdout.strip()
    tps = _estimate_tokens_per_second(raw_output, total_duration)

    # Validate JSON — json_extracted indicates prose-wrapped output
    parsed, json_valid, _json_extracted = _try_parse_json(raw_output)
    has_valid_state = False
    has_valid_rules = False

    if parsed and isinstance(parsed, dict):
        has_valid_state = parsed.get("next_state") in EXPECTED_STATES
        rules = parsed.get("applied_rules", [])
        if isinstance(rules, list) and rules:
            has_valid_rules = all(
                isinstance(r, str) and any(r.startswith(p + "-") for p in RULE_ID_PREFIXES)
                for r in rules
            )

    return RunResult(
        run_number=run_number,
        time_to_first_token_s=None,
        total_duration_s=total_duration,
        tokens_per_second=tps,
        json_valid=json_valid,
        has_valid_state=has_valid_state,
        has_valid_rules=has_valid_rules,
        raw_output=raw_output,
        parsed_output=parsed,
    )


def _estimate_tokens_per_second(output: str, duration: float) -> float | None:
    """Rough estimate: ~0.75 tokens per word."""
    if duration <= 0:
        return None
    word_count = len(output.split())
    estimated_tokens = int(word_count * 0.75)
    return estimated_tokens / duration if estimated_tokens > 0 else None


def _try_parse_json(text: str) -> tuple[dict[str, object] | None, bool, bool]:
    """Attempt to parse JSON from model output, handling markdown fences.

    Returns (parsed_dict, json_valid, json_extracted) where json_extracted
    is True when JSON was found embedded in prose rather than returned cleanly.
    """
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:]  # Remove opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed, True, False
        return None, False, False
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed, True, True
            except json.JSONDecodeError:
                pass
        return None, False, False


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def generate_decision_table(results: list[ModelResult]) -> str:
    """Generate a markdown decision table from results."""
    lines = [
        "# Local Model Feasibility Results",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d')}",
        "**Hardware:** Apple M4 MacBook Air, 32GB RAM",
        f"**Runs per model:** {RUNS_PER_MODEL}",
        "",
        "## Decision Table",
        "",
        "| Model | Size | Avg Duration (s) | Avg Tokens/s "
        "| JSON Valid | Valid State | Valid Rules | Feasible? |",
        "|-------|------|-------------------|------------- "
        "|------------|------------|-------------|-----------|",
    ]

    for r in results:
        if not r.pull_success:
            lines.append(f"| {r.model_name} | - | - | - | - | - | - | - | PULL FAILED |")
            continue

        size = f"{r.model_size_gb:.1f}GB" if r.model_size_gb else "?"
        avg_dur = f"{r.avg_total_duration_s:.1f}" if r.avg_total_duration_s else "?"
        avg_tps = f"{r.avg_tokens_per_second:.1f}" if r.avg_tokens_per_second else "?"
        json_rate = f"{r.json_success_rate:.0%}"
        state_rate = f"{r.valid_state_rate:.0%}"
        rules_rate = f"{r.valid_rules_rate:.0%}"

        # Feasibility heuristic
        if r.avg_total_duration_s is not None and r.avg_total_duration_s > 120:
            feasible = "NO (SLOW)"
        elif r.json_success_rate < 0.5:
            feasible = "NO (JSON)"
        elif r.avg_total_duration_s is not None:
            feasible = "YES"
        else:
            feasible = "?"

        lines.append(
            f"| {r.model_name} | {size} | {avg_dur} | {avg_tps} "
            f"| {json_rate} | {state_rate} | {rules_rate} | {feasible} |"
        )

    lines.extend(
        [
            "",
            "## Per-Model Details",
            "",
        ]
    )

    for r in results:
        lines.append(f"### {r.model_name}")
        lines.append("")
        if not r.pull_success:
            lines.append("Model pull failed. Skipped.")
            lines.append("")
            continue

        for run in r.runs:
            lines.append(f"**Run {run.run_number}:**")
            lines.append("")
            lines.append(f"- Duration: {run.total_duration_s:.1f}s")
            tps_str = f"{run.tokens_per_second:.1f}" if run.tokens_per_second else "N/A"
            lines.append(f"- Tokens/s: {tps_str}")
            lines.append(f"- JSON valid: {run.json_valid}")
            lines.append(f"- Valid state: {run.has_valid_state}")
            lines.append(f"- Valid rules: {run.has_valid_rules}")
            if run.parsed_output:
                lines.append("- Parsed output:")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(run.parsed_output, indent=2))
                lines.append("```")
            else:
                lines.append("- Raw output (first 500 chars):")
                lines.append("")
                lines.append("```text")
                lines.append(run.raw_output[:500])
                lines.append("```")
            lines.append("")

    lines.extend(
        [
            "## Recommendations",
            "",
            "<!-- Fill in after reviewing results -->",
            "",
            "- **Proceed with:** (models that passed all checks)",
            "- **Investigate further:** (models with marginal results)",
            "- **Drop:** (models that failed feasibility)",
            "",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _load_existing_results(json_path: Path) -> list[dict[str, object]]:
    """Load previously saved raw results, if any."""
    if not json_path.exists():
        return []
    try:
        data = json.loads(json_path.read_text())
        if isinstance(data, list):
            return data
        print(f"WARNING: {json_path} exists but contains non-list data; starting fresh")
    except json.JSONDecodeError:
        print(f"WARNING: {json_path} is corrupted (invalid JSON); starting fresh")
    except OSError as exc:
        print(f"WARNING: could not read {json_path}: {exc}; starting fresh")
    return []


def _merge_results(
    existing: list[dict[str, object]],
    new_results: list[ModelResult],
) -> list[dict[str, object]]:
    """Merge new benchmark results into existing data.

    New results for a model replace previous results for that model.
    Models not re-benchmarked are preserved from the existing data.
    """
    merged: dict[str, dict[str, object]] = {}

    # Load existing results keyed by model name
    for entry in existing:
        name = entry.get("model_name")
        if isinstance(name, str):
            merged[name] = entry

    # Overwrite with new results
    for result in new_results:
        merged[result.model_name] = asdict(result)

    return list(merged.values())


def _benchmark_prompt(
    prompt_name: str,
    prompt_text: str,
    models: list[str],
    runs: int,
    skip_pull: bool,
    output_dir: Path,
) -> None:
    """Benchmark all models for a single prompt variant."""
    print(f"\nBenchmarking {len(models)} models, {runs} runs each")
    print(f"Prompt: {prompt_name}")
    print("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "raw_results.json"

    # Load existing results so partial re-runs don't lose data
    existing_raw = _load_existing_results(json_path)
    if existing_raw:
        existing_models = [e.get("model_name") for e in existing_raw]
        print(f"Loaded existing results for: {', '.join(str(m) for m in existing_models)}")
        new_models = [m for m in models if m not in existing_models]
        rerun_models = [m for m in models if m in existing_models]
        if rerun_models:
            print(f"Will replace results for: {', '.join(rerun_models)}")
        if new_models:
            print(f"New models to benchmark: {', '.join(new_models)}")

    new_results: list[ModelResult] = []

    for model_name in models:
        print(f"\n--- {model_name} [{prompt_name}] ---")

        model_result = ModelResult(
            model_name=model_name,
            pull_success=True,
            model_size_gb=None,
        )

        # Start ollama for this model
        ollama_proc = start_ollama()
        try:
            # Pull model
            if not skip_pull:
                model_result.pull_success = pull_model(model_name)
                if not model_result.pull_success:
                    new_results.append(model_result)
                    continue

            model_result.model_size_gb = get_model_size_gb(model_name)

            # Run inferences
            for i in range(1, runs + 1):
                print(f"  Run {i}/{runs}...", end=" ", flush=True)
                run_result = run_inference(model_name, prompt_text, run_number=i)
                model_result.runs.append(run_result)

                status = "OK" if run_result.json_valid else "JSON_FAIL"
                print(f"{run_result.total_duration_s:.1f}s [{status}]")

            new_results.append(model_result)
        finally:
            stop_ollama(ollama_proc)

    # Merge new results with existing data
    merged_raw = _merge_results(existing_raw, new_results)

    # Reconstruct ModelResult objects for report generation
    all_results: list[ModelResult] = []
    for entry in merged_raw:
        mr = ModelResult(
            model_name=str(entry.get("model_name", "")),
            pull_success=bool(entry.get("pull_success", False)),
            model_size_gb=(
                float(size_val) if (size_val := entry.get("model_size_gb")) is not None else None
            ),
        )
        raw_runs = entry.get("runs")
        if isinstance(raw_runs, list):
            for run_data in raw_runs:
                if isinstance(run_data, dict):
                    ttft = run_data.get("time_to_first_token_s")
                    tps = run_data.get("tokens_per_second")
                    parsed = run_data.get("parsed_output")
                    mr.runs.append(
                        RunResult(
                            run_number=int(run_data.get("run_number", 0)),
                            time_to_first_token_s=float(ttft) if ttft is not None else None,
                            total_duration_s=float(run_data.get("total_duration_s", 0)),
                            tokens_per_second=float(tps) if tps is not None else None,
                            json_valid=bool(run_data.get("json_valid", False)),
                            has_valid_state=bool(run_data.get("has_valid_state", False)),
                            has_valid_rules=bool(run_data.get("has_valid_rules", False)),
                            raw_output=str(run_data.get("raw_output", "")),
                            parsed_output=parsed if isinstance(parsed, dict) else None,
                        )
                    )
        all_results.append(mr)

    # Write merged results
    report = generate_decision_table(all_results)
    report_path = output_dir / "feasibility_report.md"
    report_path.write_text(report)
    print(f"\nReport written to {report_path}")

    json_path.write_text(json.dumps(merged_raw, indent=2, default=str))
    print(f"Raw data written to {json_path}")
    print(f"Total models in results: {len(all_results)}")


def main() -> None:
    """Run the full benchmark suite."""
    import argparse

    prompt_choices = list(PROMPTS.keys()) + ["all"]

    parser = argparse.ArgumentParser(description="Benchmark local Ollama models")
    parser.add_argument(
        "--models",
        nargs="+",
        default=CANDIDATE_MODELS,
        help="Model names to benchmark (default: all candidates)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS_PER_MODEL,
        help=f"Number of runs per model (default: {RUNS_PER_MODEL})",
    )
    parser.add_argument(
        "--skip-pull",
        action="store_true",
        help="Skip pulling models (assume already available)",
    )
    parser.add_argument(
        "--prompt",
        choices=prompt_choices,
        nargs="+",
        default=["all"],
        help="Prompt variant(s) to use (default: all)",
    )
    args = parser.parse_args()

    # Resolve prompt selection
    selected_prompts: list[str] = []
    for p in args.prompt:
        if p == "all":
            selected_prompts = list(PROMPTS.keys())
            break
        if p not in selected_prompts:
            selected_prompts.append(p)

    timestamp = time.strftime("%Y-%m-%d_%H-%M")

    for prompt_name in selected_prompts:
        prompt_text = PROMPTS[prompt_name]
        output_dir = OUTPUT_DIR / timestamp / prompt_name
        _benchmark_prompt(
            prompt_name=prompt_name,
            prompt_text=prompt_text,
            models=args.models,
            runs=args.runs,
            skip_pull=args.skip_pull,
            output_dir=output_dir,
        )


if __name__ == "__main__":
    main()
