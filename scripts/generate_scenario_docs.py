#!/usr/bin/env python3
"""Generate markdown review files from scenario JSON files.

Produces one markdown file per scenario category in docs/scenarios/review/.
Run: python scripts/generate_scenario_docs.py
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "scenarios"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "scenarios" / "review"

ROUTING_CATEGORIES = ["rule_coverage", "multi_rule", "accumulated_state", "unknown_input"]
QUERY_CATEGORY = "query"


def load_scenarios(category: str) -> list[dict]:
    """Load and sort all scenario JSON files for a category."""
    category_dir = SCENARIOS_DIR / category
    if not category_dir.exists():
        return []

    scenarios = []
    for f in category_dir.glob("*.json"):
        with open(f) as fh:
            scenarios.append(json.load(fh))

    def sort_key(s: dict) -> tuple[str, int]:
        sid = s.get("scenario_id", "")
        match = re.search(r"(\d+)$", sid)
        num = int(match.group(1)) if match else 0
        prefix = sid.rstrip("0123456789-")
        return (prefix, num)

    scenarios.sort(key=sort_key)
    return scenarios


def summarize_event_data(event_type: str, event_data: dict) -> str:
    """Produce a compact summary of event_data based on event type."""
    if event_type == "order_received":
        parts = []
        specimen = event_data.get("specimen_type")
        parts.append(str(specimen) if specimen else "null")
        site = event_data.get("anatomic_site")
        if site:
            parts.append(site)
        fixative = event_data.get("fixative")
        if fixative:
            parts.append(fixative)
        fix_time = event_data.get("fixation_time_hours")
        if fix_time is not None:
            parts.append(f"{fix_time}h")
        else:
            parts.append("fix_time=null")
        priority = event_data.get("priority", "routine")
        if priority != "routine":
            parts.append(f"priority={priority}")
        tests = event_data.get("ordered_tests", [])
        if tests and tests != ["Breast IHC Panel"]:
            parts.append(f"tests={tests}")
        billing = event_data.get("billing_info_present")
        if billing is False:
            parts.append("no billing")
        name = event_data.get("patient_name")
        if name is None:
            parts.append("name=null")
        sex = event_data.get("sex")
        if sex is None:
            parts.append("sex=null")
        return ", ".join(parts)

    if event_type == "pathologist_he_review":
        return event_data.get("diagnosis", "?")

    if event_type == "he_staining_complete":
        fix_issue = event_data.get("fixation_issue", False)
        return f"fixation_issue={fix_issue}" if fix_issue else "ok"

    if event_type == "ihc_qc":
        slides = event_data.get("slides", [])
        pass_count = sum(1 for s in slides if s.get("qc_result") == "pass")
        fail_count = len(slides) - pass_count
        complete = event_data.get("all_slides_complete", "?")
        parts = [f"{len(slides)} slides ({pass_count}P/{fail_count}F)"]
        if complete is not True:
            parts.append(f"all_complete={complete}")
        return ", ".join(parts)

    if event_type == "ihc_scoring":
        scores = event_data.get("scores", [])
        parts = []
        for s in scores:
            eq = " (equivocal)" if s.get("equivocal") else ""
            parts.append(f"{s.get('test', '?')}={s.get('value', '?')}{eq}")
        complete = event_data.get("all_scores_complete", "?")
        any_eq = event_data.get("any_equivocal", False)
        suffix = ""
        if complete is not True:
            suffix += f", all_complete={complete}"
        if any_eq:
            suffix += ", any_equivocal"
        return "; ".join(parts) + suffix

    if event_type == "fish_result":
        result = event_data.get("result", "?")
        status = event_data.get("status", "?")
        ratio = event_data.get("ratio")
        s = f"{result} ({status})"
        if ratio is not None:
            s += f", ratio={ratio}"
        return s

    if event_type == "fish_decision":
        return f"approved={event_data.get('approved', '?')}"

    if event_type == "missing_info_received":
        info_type = event_data.get("info_type", "?")
        value = event_data.get("value", "?")
        return f"{info_type}={value}"

    if event_type == "pathologist_signout":
        tests = event_data.get("reportable_tests", [])
        return ", ".join(tests) if tests else "—"

    if event_type == "resulting_review":
        return event_data.get("outcome", "?")

    if event_type == "report_generated":
        return event_data.get("outcome", "?")

    # Outcome-based events (grossing, processing, embedding, sectioning, sample_prep_qc, etc.)
    outcome = event_data.get("outcome")
    if outcome:
        extras = []
        if "tissue_remaining" in event_data:
            extras.append(f"tissue_remaining={event_data['tissue_remaining']}")
        if "tissue_available" in event_data:
            extras.append(f"tissue_available={event_data['tissue_available']}")
        if "backup_slides_available" in event_data:
            extras.append(f"backup_slides={event_data['backup_slides_available']}")
        if extras:
            return f"{outcome}, {', '.join(extras)}"
        return outcome

    # Fallback: compact JSON
    return json.dumps(event_data, separators=(",", ":"))


def escape_pipes(text: str) -> str:
    """Escape pipe characters for markdown tables."""
    return text.replace("|", "\\|")


def generate_routing_markdown(category: str, scenarios: list[dict]) -> str:
    """Generate markdown for a routing scenario category."""
    title = category.replace("_", " ").title()
    lines = [
        f"# {title} Scenarios",
        "",
        f"**{len(scenarios)} scenarios**",
        "",
        "## Summary",
        "",
        "| ID | Description | Rules | Final State | Steps |",
        "|---|---|---|---|---|",
    ]

    for s in scenarios:
        sid = s["scenario_id"]
        desc = escape_pipes(s.get("description", ""))
        events = s.get("events", [])
        all_rules: list[str] = []
        for e in events:
            all_rules.extend(e.get("expected_output", {}).get("applied_rules", []))
        unique_rules = sorted(set(all_rules))
        final_state = (
            events[-1].get("expected_output", {}).get("next_state", "?") if events else "?"
        )
        lines.append(
            f"| {sid} | {desc} | {', '.join(unique_rules) or '—'} | {final_state} | {len(events)} |"
        )

    lines.append("")

    # Detailed sections
    lines.append("## Details")
    lines.append("")

    for s in scenarios:
        sid = s["scenario_id"]
        desc = escape_pipes(s.get("description", ""))
        events = s.get("events", [])

        lines.append(f"### {sid}: {desc}")
        lines.append("")
        lines.append("| Step | Event | Key Data | State | Rules | Flags |")
        lines.append("|---|---|---|---|---|---|")

        for e in events:
            step = e.get("step", "?")
            event_type = e.get("event_type", "?")
            event_data = e.get("event_data", {})
            expected = e.get("expected_output", {})
            state = expected.get("next_state", "?")
            rules = ", ".join(expected.get("applied_rules", [])) or "—"
            flags = ", ".join(expected.get("flags", [])) or "—"
            summary = escape_pipes(summarize_event_data(event_type, event_data))
            lines.append(f"| {step} | {event_type} | {summary} | {state} | {rules} | {flags} |")

        lines.append("")

    return "\n".join(lines)


def generate_query_markdown(scenarios: list[dict]) -> str:
    """Generate markdown for query scenarios."""
    lines = [
        "# Query Scenarios",
        "",
        f"**{len(scenarios)} scenarios**",
        "",
        "## Summary",
        "",
        "| ID | Tier | Description | Answer Type | Expected Orders |",
        "|---|---|---|---|---|",
    ]

    for s in scenarios:
        sid = s["scenario_id"]
        tier = s.get("tier", "?")
        desc = escape_pipes(s.get("description", ""))
        expected = s.get("expected_output", {})
        answer_type = expected.get("answer_type", "?")
        order_ids = ", ".join(expected.get("order_ids", []))
        lines.append(f"| {sid} | {tier} | {desc} | {answer_type} | {order_ids} |")

    lines.append("")

    # Detailed sections
    lines.append("## Details")
    lines.append("")

    for s in scenarios:
        sid = s["scenario_id"]
        tier = s.get("tier", "?")
        desc = escape_pipes(s.get("description", ""))

        lines.append(f"### {sid} (Tier {tier}): {desc}")
        lines.append("")
        lines.append(f"**Query:** {s.get('query', '?')}")
        lines.append("")

        # Database state
        db_state = s.get("database_state", {})
        orders = db_state.get("orders", [])
        if orders:
            lines.append("**Database State:**")
            lines.append("")
            lines.append("| Order ID | State | Specimen | Priority | Flags | Created |")
            lines.append("|---|---|---|---|---|---|")
            for o in orders:
                oid = o.get("order_id", "?")
                state = o.get("current_state", "?")
                specimen = o.get("specimen_type", "?")
                priority = o.get("priority", "?")
                flags = ", ".join(o.get("flags", [])) or "—"
                created = o.get("created_at", "?")
                # Shorten the timestamp
                if isinstance(created, str) and "T" in created:
                    created = created.replace("T", " ").rstrip("Z")
                lines.append(f"| {oid} | {state} | {specimen} | {priority} | {flags} | {created} |")
            lines.append("")

        # Expected output
        expected = s.get("expected_output", {})
        lines.append("**Expected Output:**")
        lines.append("")
        lines.append(f"- **Answer type:** {expected.get('answer_type', '?')}")
        lines.append(f"- **Order IDs:** {', '.join(expected.get('order_ids', []))}")
        lines.append(f"- **Reasoning:** {expected.get('reasoning', '?')}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for category in ROUTING_CATEGORIES:
        scenarios = load_scenarios(category)
        if not scenarios:
            print(f"  Skipping {category} (no scenarios found)")
            continue
        md = generate_routing_markdown(category, scenarios)
        out_path = OUTPUT_DIR / f"{category}.md"
        out_path.write_text(md)
        print(f"  {out_path.relative_to(PROJECT_ROOT)}: {len(scenarios)} scenarios")

    query_scenarios = load_scenarios(QUERY_CATEGORY)
    if query_scenarios:
        md = generate_query_markdown(query_scenarios)
        out_path = OUTPUT_DIR / f"{QUERY_CATEGORY}.md"
        out_path.write_text(md)
        print(f"  {out_path.relative_to(PROJECT_ROOT)}: {len(query_scenarios)} scenarios")

    print(f"\nDone. Files written to {OUTPUT_DIR.relative_to(PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()
