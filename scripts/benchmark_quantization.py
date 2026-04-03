"""Benchmark full-precision cloud models vs local quantized models.

Calls cloud API providers (Together AI, Groq, OpenRouter) with the same
prompts used in the feasibility benchmark, then compares results with
existing local quantized data.

Usage:
    uv run python scripts/benchmark_quantization.py \
        --provider openrouter --api-key "$OPENROUTER_API_KEY"
    uv run python scripts/benchmark_quantization.py \
        --provider openrouter --api-key "$OPENROUTER_API_KEY" --runs 5
    uv run python scripts/benchmark_quantization.py \
        --provider openrouter --api-key "$OPENROUTER_API_KEY" \
        --models "qwen/qwen-2.5-72b-instruct"
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Reuse prompt definitions from the feasibility benchmark
# ---------------------------------------------------------------------------
from benchmark_models import (
    BASELINE_PROMPT,
    ENRICHED_PROMPT,
    EXPECTED_STATES,
    RULE_ID_PREFIXES,
)

PROMPTS: dict[str, str] = {
    "baseline": BASELINE_PROMPT,
    "enriched": ENRICHED_PROMPT,
}

# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

# Default cloud model IDs for quantized local models.
# Keys are descriptive names; values are per-provider model IDs.
CLOUD_MODELS: dict[str, dict[str, str]] = {
    "Qwen2.5-72B-Instruct": {
        "together": "Qwen/Qwen2.5-72B-Instruct",
        "groq": "qwen-2.5-72b",
        "openrouter": "qwen/qwen-2.5-72b-instruct",
        # No exact cloud match for the 32B — the 72B is the same family
        # at full precision and larger size, providing an upper bound.
        "local_counterpart": "Qwen2.5:32b-instruct-q4_K_M",
    },
    "Llama-3.3-70B-Instruct": {
        "together": "meta-llama/Llama-3.3-70B-Instruct",
        "groq": "llama-3.3-70b-versatile",
        "openrouter": "meta-llama/llama-3.3-70b-instruct",
        "local_counterpart": "llama3.3:70b-instruct-q4_K_M",
    },
}

PROVIDER_ENDPOINTS: dict[str, str] = {
    "together": "https://api.together.xyz/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

RUNS_PER_MODEL = 3
OUTPUT_DIR = Path("results/quantization_impact")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CloudRunResult:
    """Result of a single cloud API inference run."""

    run_number: int
    total_duration_s: float
    json_valid: bool
    has_valid_state: bool
    has_valid_rules: bool
    correct_state: bool
    correct_rules: bool
    raw_output: str
    parsed_output: dict[str, object] | None
    error: str | None = None


@dataclass
class CloudModelResult:
    """Aggregated results for a single cloud model."""

    model_name: str
    provider: str
    cloud_model_id: str
    local_counterpart: str
    runs: list[CloudRunResult] = field(default_factory=list)

    @property
    def avg_total_duration_s(self) -> float | None:
        durations = [r.total_duration_s for r in self.runs if r.error is None]
        return sum(durations) / len(durations) if durations else None

    @property
    def json_success_rate(self) -> float:
        valid_runs = [r for r in self.runs if r.error is None]
        if not valid_runs:
            return 0.0
        return sum(1 for r in valid_runs if r.json_valid) / len(valid_runs)

    @property
    def correct_state_rate(self) -> float:
        valid_runs = [r for r in self.runs if r.error is None]
        if not valid_runs:
            return 0.0
        return sum(1 for r in valid_runs if r.correct_state) / len(valid_runs)

    @property
    def correct_rules_rate(self) -> float:
        valid_runs = [r for r in self.runs if r.error is None]
        if not valid_runs:
            return 0.0
        return sum(1 for r in valid_runs if r.correct_rules) / len(valid_runs)


# ---------------------------------------------------------------------------
# Cloud API inference
# ---------------------------------------------------------------------------


def call_cloud_api(
    provider: str,
    model_id: str,
    prompt: str,
    api_key: str,
) -> tuple[str, float]:
    """Call a cloud API and return (response_text, duration_seconds).

    Uses the OpenAI-compatible chat completions endpoint supported by
    Together AI, Groq, and OpenRouter.

    Raises ``RuntimeError`` on API errors.
    """
    endpoint = PROVIDER_ENDPOINTS[provider]

    payload = json.dumps(
        {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 512,
        }
    ).encode()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(endpoint, data=payload, headers=headers)

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode() if exc.fp else str(exc)
        raise RuntimeError(f"API error {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc

    duration = time.perf_counter() - start

    content = body["choices"][0]["message"]["content"]
    return content, duration


# ---------------------------------------------------------------------------
# JSON parsing and validation (reused logic from benchmark_models)
# ---------------------------------------------------------------------------


def _try_parse_json(text: str) -> tuple[dict[str, object] | None, bool]:
    """Attempt to parse JSON from model output, handling markdown fences.

    Returns (parsed_dict, json_valid).
    """
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
            return parsed, True
        return None, False
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, dict):
                    return parsed, True
            except json.JSONDecodeError:
                pass
        return None, False


def _validate_output(
    parsed: dict[str, object] | None,
) -> tuple[bool, bool, bool, bool]:
    """Validate parsed JSON output.

    Returns (has_valid_state, has_valid_rules, correct_state, correct_rules).
    The enriched prompt scenario expects ACCEPTED + ACC-008.
    """
    if not parsed or not isinstance(parsed, dict):
        return False, False, False, False

    state = parsed.get("next_state")
    has_valid_state = state in EXPECTED_STATES
    correct_state = state == "ACCEPTED"

    rules = parsed.get("applied_rules", [])
    has_valid_rules = False
    correct_rules = False

    if isinstance(rules, list) and rules:
        has_valid_rules = all(
            isinstance(r, str) and any(r.startswith(p + "-") for p in RULE_ID_PREFIXES)
            for r in rules
        )
        correct_rules = rules == ["ACC-008"]

    return has_valid_state, has_valid_rules, correct_state, correct_rules


def run_cloud_inference(
    provider: str,
    model_id: str,
    prompt: str,
    api_key: str,
    run_number: int,
) -> CloudRunResult:
    """Run a single cloud inference and validate the result."""
    try:
        raw_output, duration = call_cloud_api(provider, model_id, prompt, api_key)
    except RuntimeError as exc:
        return CloudRunResult(
            run_number=run_number,
            total_duration_s=0.0,
            json_valid=False,
            has_valid_state=False,
            has_valid_rules=False,
            correct_state=False,
            correct_rules=False,
            raw_output="",
            parsed_output=None,
            error=str(exc),
        )

    parsed, json_valid = _try_parse_json(raw_output)
    has_valid_state, has_valid_rules, correct_state, correct_rules = _validate_output(parsed)

    return CloudRunResult(
        run_number=run_number,
        total_duration_s=duration,
        json_valid=json_valid,
        has_valid_state=has_valid_state,
        has_valid_rules=has_valid_rules,
        correct_state=correct_state,
        correct_rules=correct_rules,
        raw_output=raw_output,
        parsed_output=parsed,
    )


# ---------------------------------------------------------------------------
# Load local results for comparison
# ---------------------------------------------------------------------------


def find_latest_local_results(prompt_name: str) -> Path | None:
    """Find the most recent local feasibility results for a prompt variant.

    Looks for timestamped directories:
    ``results/model_feasibility/<timestamp>/<prompt>/raw_results.json``

    Returns the most recent match (latest timestamp).
    """
    base = Path("results/model_feasibility")
    if not base.exists():
        return None

    candidates: list[Path] = []
    for timestamp_dir in base.iterdir():
        if not timestamp_dir.is_dir():
            continue
        # Skip non-timestamped directories (e.g. flat "baseline", "enriched")
        if not timestamp_dir.name[:4].isdigit():
            continue
        json_path = timestamp_dir / prompt_name / "raw_results.json"
        if json_path.exists():
            candidates.append(json_path)

    if not candidates:
        return None

    # Sort by directory name (timestamp format sorts lexicographically)
    return sorted(candidates)[-1]


def load_local_results(
    json_path: Path,
    model_name: str,
) -> dict[str, object] | None:
    """Load local results for a specific model from raw_results.json."""
    try:
        data = json.loads(json_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, list):
        return None

    for entry in data:
        if isinstance(entry, dict) and entry.get("model_name") == model_name:
            return entry

    return None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _format_local_runs(local_data: dict[str, object] | None) -> list[str]:
    """Format local run data for the comparison report."""
    lines: list[str] = []
    if not local_data:
        lines.append("No local results found for comparison.")
        return lines

    runs = local_data.get("runs")
    if not isinstance(runs, list) or not runs:
        lines.append("No run data in local results.")
        return lines

    for run_data in runs:
        if not isinstance(run_data, dict):
            continue
        run_num = run_data.get("run_number", "?")
        json_valid = run_data.get("json_valid", False)
        duration = run_data.get("total_duration_s", 0)
        parsed = run_data.get("parsed_output")

        correct_state = False
        correct_rules = False
        if isinstance(parsed, dict):
            correct_state = parsed.get("next_state") == "ACCEPTED"
            rules = parsed.get("applied_rules", [])
            correct_rules = rules == ["ACC-008"]

        lines.append(
            f"**Run {run_num}:** {duration:.1f}s | "
            f"JSON: {'Yes' if json_valid else 'No'} | "
            f"State: {'ACCEPTED' if correct_state else 'Wrong'} | "
            f"Rules: {'ACC-008' if correct_rules else 'Wrong'}"
        )

        if isinstance(parsed, dict):
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(parsed, indent=2))
            lines.append("```")
        lines.append("")

    return lines


def generate_comparison_report(
    cloud_results: dict[str, dict[str, CloudModelResult]],
    local_results_by_prompt: dict[str, dict[str, dict[str, object] | None]],
) -> str:
    """Generate a markdown comparison report.

    Args:
        cloud_results: {prompt_name: {model_name: CloudModelResult}}
        local_results_by_prompt: {prompt_name: {model_name: local_data}}
    """
    lines = [
        "# Quantization Impact Comparison",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d')}",
        "**Purpose:** Compare full-precision cloud inference vs local Q4 quantized inference",
        "",
    ]

    for prompt_name in cloud_results:
        lines.append(f"## Prompt: {prompt_name}")
        lines.append("")

        # Summary table
        lines.append("### Summary")
        lines.append("")
        lines.append(
            "| Model | Source | JSON Valid | Correct State | Correct Rules | Avg Duration |"
        )
        lines.append("|-------|--------|-----------|---------------|---------------|-------------|")

        prompt_cloud = cloud_results[prompt_name]
        prompt_local = local_results_by_prompt.get(prompt_name, {})

        for model_name, cloud_mr in prompt_cloud.items():
            # Cloud row
            avg_dur = (
                f"{cloud_mr.avg_total_duration_s:.1f}s" if cloud_mr.avg_total_duration_s else "N/A"
            )
            lines.append(
                f"| {model_name} | Cloud FP16 "
                f"| {cloud_mr.json_success_rate:.0%} "
                f"| {cloud_mr.correct_state_rate:.0%} "
                f"| {cloud_mr.correct_rules_rate:.0%} "
                f"| {avg_dur} |"
            )

            # Local row
            local_data = prompt_local.get(model_name)
            if local_data:
                local_runs = local_data.get("runs")
                if isinstance(local_runs, list) and local_runs:
                    n = len(local_runs)
                    json_rate = (
                        sum(1 for r in local_runs if isinstance(r, dict) and r.get("json_valid"))
                        / n
                    )
                    state_count = 0
                    rules_count = 0
                    dur_sum = 0.0
                    for r in local_runs:
                        if not isinstance(r, dict):
                            continue
                        p = r.get("parsed_output")
                        if isinstance(p, dict):
                            if p.get("next_state") == "ACCEPTED":
                                state_count += 1
                            if p.get("applied_rules") == ["ACC-008"]:
                                rules_count += 1
                        dur_sum += float(r.get("total_duration_s", 0))

                    lines.append(
                        f"| {model_name} | Local Q4 "
                        f"| {json_rate:.0%} "
                        f"| {state_count}/{n} "
                        f"| {rules_count}/{n} "
                        f"| {dur_sum / n:.1f}s |"
                    )
            else:
                lines.append(f"| {model_name} | Local Q4 | — | — | — | No data |")

        lines.append("")

        # Per-model details
        lines.append("### Per-Model Details")
        lines.append("")

        for model_name, cloud_mr in prompt_cloud.items():
            lines.append(f"#### {model_name}")
            lines.append("")

            lines.append(f"**Cloud ({cloud_mr.provider}, FP16):**")
            lines.append("")
            for run in cloud_mr.runs:
                if run.error:
                    lines.append(f"**Run {run.run_number}:** ERROR — {run.error}")
                    lines.append("")
                    continue

                lines.append(
                    f"**Run {run.run_number}:** {run.total_duration_s:.1f}s | "
                    f"JSON: {'Yes' if run.json_valid else 'No'} | "
                    f"State: {'ACCEPTED' if run.correct_state else 'Wrong'} | "
                    f"Rules: {'ACC-008' if run.correct_rules else 'Wrong'}"
                )

                if run.parsed_output:
                    lines.append("")
                    lines.append("```json")
                    lines.append(json.dumps(run.parsed_output, indent=2))
                    lines.append("```")
                elif run.raw_output:
                    lines.append("")
                    lines.append("```text")
                    lines.append(run.raw_output[:500])
                    lines.append("```")
                lines.append("")

            lines.append(f"**Local (Q4, {cloud_mr.local_counterpart}):**")
            lines.append("")
            local_data = prompt_local.get(model_name)
            lines.extend(_format_local_runs(local_data))
            lines.append("")

    lines.extend(
        [
            "## Conclusion",
            "",
            "<!-- Fill in after reviewing results -->",
            "",
            "### Quantization Impact Assessment",
            "",
            "- **Qwen2.5-32B:** (Does FP16 fix the ACC-08 formatting issue? "
            "Is accuracy meaningfully different?)",
            "- **Llama-3.3-70B:** (How does it perform at full precision? "
            "Worth pursuing if hardware constraints change?)",
            "",
            "### Recommendation",
            "",
            "- **Keep / Drop / Change quantization level** for each model",
            "",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _benchmark_prompt(
    prompt_name: str,
    prompt_text: str,
    models: dict[str, dict[str, str]],
    provider: str,
    api_key: str,
    runs: int,
) -> tuple[dict[str, CloudModelResult], dict[str, dict[str, object] | None]]:
    """Benchmark all models for a single prompt variant.

    Returns (cloud_results, local_results) keyed by model display name.
    """
    cloud_results: dict[str, CloudModelResult] = {}
    local_results: dict[str, dict[str, object] | None] = {}

    for display_name, model_config in models.items():
        model_id = model_config.get(provider)
        if not model_id:
            print(f"  SKIP {display_name}: no model ID for provider '{provider}'")
            continue

        local_tag = model_config.get("local_counterpart", "")
        print(f"\n--- {display_name} [{prompt_name}] ---")
        print(f"  Cloud model: {model_id}")
        print(f"  Local counterpart: {local_tag}")

        cloud_mr = CloudModelResult(
            model_name=display_name,
            provider=provider,
            cloud_model_id=model_id,
            local_counterpart=local_tag,
        )

        for i in range(1, runs + 1):
            print(f"  Run {i}/{runs}...", end=" ", flush=True)
            run_result = run_cloud_inference(
                provider,
                model_id,
                prompt_text,
                api_key,
                run_number=i,
            )
            cloud_mr.runs.append(run_result)

            if run_result.error:
                print(f"ERROR: {run_result.error[:80]}")
            else:
                status = "OK" if run_result.json_valid else "JSON_FAIL"
                state = "correct" if run_result.correct_state else "wrong"
                rules = "correct" if run_result.correct_rules else "wrong"
                print(f"{run_result.total_duration_s:.1f}s [{status}] state={state} rules={rules}")

        cloud_results[display_name] = cloud_mr

        # Load local results for comparison
        local_path = find_latest_local_results(prompt_name)
        if local_path:
            local_data = load_local_results(local_path, local_tag)
            local_results[display_name] = local_data
            if local_data:
                print(f"  Loaded local results from {local_path}")
            else:
                print(f"  No local results for {local_tag} in {local_path}")
        else:
            local_results[display_name] = None
            print(f"  No local results found for prompt '{prompt_name}'")

    return cloud_results, local_results


def main() -> None:
    """Run the quantization impact benchmark."""
    import argparse
    import sys

    prompt_choices = list(PROMPTS.keys()) + ["all"]

    parser = argparse.ArgumentParser(
        description="Compare full-precision cloud vs local quantized models",
    )
    parser.add_argument(
        "--provider",
        choices=list(PROVIDER_ENDPOINTS.keys()),
        required=True,
        help="Cloud API provider to use",
    )
    parser.add_argument(
        "--api-key",
        required=True,
        help="API key for the cloud provider",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Cloud model IDs to test (default: all configured models)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=RUNS_PER_MODEL,
        help=f"Number of runs per model (default: {RUNS_PER_MODEL})",
    )
    parser.add_argument(
        "--prompt",
        choices=prompt_choices,
        nargs="+",
        default=["all"],
        help="Prompt variant(s) to use (default: all)",
    )
    parser.add_argument(
        "--local-results",
        type=Path,
        default=None,
        help="Path to local raw_results.json (default: auto-detect latest)",
    )
    args = parser.parse_args()

    # Resolve model selection
    if args.models:
        # Filter to only models matching the provided IDs
        selected_models: dict[str, dict[str, str]] = {}
        for display_name, config in CLOUD_MODELS.items():
            provider_id = config.get(args.provider, "")
            if provider_id in args.models or display_name in args.models:
                selected_models[display_name] = config
        if not selected_models:
            print(f"ERROR: No matching models found for: {args.models}")
            print(f"Available models for {args.provider}:")
            for name, cfg in CLOUD_MODELS.items():
                pid = cfg.get(args.provider, "N/A")
                print(f"  {name}: {pid}")
            sys.exit(1)
    else:
        selected_models = dict(CLOUD_MODELS)

    # Resolve prompt selection
    selected_prompts: list[str] = []
    for p in args.prompt:
        if p == "all":
            selected_prompts = list(PROMPTS.keys())
            break
        if p not in selected_prompts:
            selected_prompts.append(p)

    print(f"Provider: {args.provider}")
    print(f"Models: {', '.join(selected_models.keys())}")
    print(f"Prompts: {', '.join(selected_prompts)}")
    print(f"Runs per model: {args.runs}")
    print("=" * 60)

    # Run benchmarks for each prompt
    all_cloud: dict[str, dict[str, CloudModelResult]] = {}
    all_local: dict[str, dict[str, dict[str, object] | None]] = {}

    for prompt_name in selected_prompts:
        prompt_text = PROMPTS[prompt_name]
        cloud, local = _benchmark_prompt(
            prompt_name=prompt_name,
            prompt_text=prompt_text,
            models=selected_models,
            provider=args.provider,
            api_key=args.api_key,
            runs=args.runs,
        )
        all_cloud[prompt_name] = cloud
        all_local[prompt_name] = local

    # Generate report
    timestamp = time.strftime("%Y-%m-%d_%H-%M")
    output_dir = OUTPUT_DIR / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    report = generate_comparison_report(all_cloud, all_local)
    report_path = output_dir / "comparison_report.md"
    report_path.write_text(report)
    print(f"\nReport written to {report_path}")

    # Write raw cloud results
    raw_data: list[dict[str, object]] = []
    for prompt_name, prompt_results in all_cloud.items():
        for _model_name, mr in prompt_results.items():
            entry = asdict(mr)
            entry["prompt"] = prompt_name
            raw_data.append(entry)

    json_path = output_dir / "cloud_raw_results.json"
    json_path.write_text(json.dumps(raw_data, indent=2, default=str))
    print(f"Raw data written to {json_path}")


if __name__ == "__main__":
    main()
