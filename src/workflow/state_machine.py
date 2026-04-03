"""Workflow state machine loaded from the YAML source of truth.

Provides typed dataclasses for states, transitions, rules, and flags,
plus a StateMachine class that builds indexes for efficient lookup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import yaml

# Default path to the YAML source of truth.
_DEFAULT_YAML_PATH = (
    Path(__file__).resolve().parent.parent.parent / "knowledge_base" / "workflow_states.yaml"
)

# Severity hierarchy for accessioning rules (highest severity first).
_SEVERITY_ORDER: dict[str, int] = {
    "REJECT": 0,
    "HOLD": 1,
    "PROCEED": 2,
    "ACCEPT": 3,
}

# Fallback sort key for unknown severities (sorts last).
_SEVERITY_FALLBACK = 99

# Mapping from non-IHC states to their rule-catalog step.
# ACCEPTED and MISSING_INFO_PROCEED are mapped to SAMPLE_PREP so that
# grossing_complete events at those states can fire SP-001.
_STATE_TO_STEP: dict[str, str] = {
    "ACCESSIONING": "ACCESSIONING",
    "ACCEPTED": "SAMPLE_PREP",
    "MISSING_INFO_PROCEED": "SAMPLE_PREP",
    "SAMPLE_PREP_PROCESSING": "SAMPLE_PREP",
    "SAMPLE_PREP_EMBEDDING": "SAMPLE_PREP",
    "SAMPLE_PREP_SECTIONING": "SAMPLE_PREP",
    "SAMPLE_PREP_QC": "SAMPLE_PREP",
    "HE_QC": "HE_QC",
    "PATHOLOGIST_HE_REVIEW": "PATHOLOGIST_HE_REVIEW",
    "RESULTING": "RESULTING",
    "RESULTING_HOLD": "RESULTING",
    "PATHOLOGIST_SIGNOUT": "RESULTING",
    "REPORT_GENERATION": "RESULTING",
}

# Required top-level keys in the workflow YAML.
_REQUIRED_YAML_KEYS = {"states", "transitions", "rules", "flags", "terminal_states"}

# Required keys within each entry type.
_REQUIRED_STATE_KEYS = {"id", "phase", "description", "terminal"}
_REQUIRED_TRANSITION_KEYS = {"from", "to", "condition"}
_REQUIRED_RULE_KEYS = {"rule_id", "step", "trigger", "action", "source"}
_REQUIRED_FLAG_KEYS = {"flag_id", "set_at", "effect", "cleared_by"}


@dataclass(frozen=True)
class State:
    """A workflow state."""

    id: str
    phase: str
    description: str
    terminal: bool


@dataclass(frozen=True)
class Transition:
    """A valid transition between two states."""

    from_state: str
    to_state: str
    condition: str


@dataclass(frozen=True)
class Rule:
    """A workflow rule from the rule catalog."""

    rule_id: str
    step: str
    trigger: str
    action: str
    source: str
    severity: str | None = None
    priority: int | None = None
    applies_at: str | None = None


@dataclass(frozen=True)
class Flag:
    """A workflow flag that modifies order routing."""

    flag_id: str
    set_at: tuple[str, ...]
    effect: str
    cleared_by: str


# Module-level cache for the default StateMachine instance.
_cached_instance: StateMachine | None = None


class StateMachine:
    """Workflow state machine loaded from YAML.

    Parses the YAML source of truth into typed dataclasses and builds
    indexes for efficient state/transition/rule lookup.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If the YAML is invalid, missing required top-level keys,
            or contains entries with missing required fields or wrong types.

    Use ``get_instance()`` to reuse a cached singleton for the default YAML
    path — avoids re-parsing the file on every call.

    The ``yaml_path`` parameter must not be derived from user input; it is
    intended for tests that supply alternate YAML files from controlled paths.
    Paths are resolved to absolute form and must have a ``.yaml`` or ``.yml``
    extension (CWE-22 mitigation).
    """

    _YAML_SUFFIXES: ClassVar[frozenset[str]] = frozenset({".yaml", ".yml"})

    def __init__(self, yaml_path: Path | None = None) -> None:
        path = yaml_path or _DEFAULT_YAML_PATH
        resolved = Path(path).resolve()

        if resolved.suffix.lower() not in self._YAML_SUFFIXES:
            raise ValueError(
                f"yaml_path must have a .yaml or .yml extension, "
                f"got {resolved.suffix!r}: {resolved}"
            )

        try:
            with open(resolved) as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Workflow YAML not found: {resolved}") from None
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in workflow file {resolved}: {exc}") from None

        if not isinstance(data, dict):
            raise ValueError(f"Workflow YAML must have a mapping root, got {type(data).__name__}")

        missing = _REQUIRED_YAML_KEYS - data.keys()
        if missing:
            raise ValueError(f"Workflow YAML missing required keys: {sorted(missing)}")

        for key in ("states", "transitions", "rules", "flags", "terminal_states"):
            if not isinstance(data[key], list):
                raise ValueError(
                    f"Workflow YAML key '{key}' must be a list, got {type(data[key]).__name__}"
                )

        # Parse states.
        self._states: dict[str, State] = {}
        for i, s in enumerate(data["states"]):
            if not isinstance(s, dict):
                raise ValueError(
                    f"State entry {i} must be a dict, got {type(s).__name__}: {repr(s)[:100]}"
                )
            missing_keys = _REQUIRED_STATE_KEYS - s.keys()
            if missing_keys:
                raise ValueError(f"State entry {i} missing required keys: {sorted(missing_keys)}")
            state = State(
                id=s["id"],
                phase=s["phase"],
                description=s["description"],
                terminal=s["terminal"],
            )
            if state.id in self._states:
                raise ValueError(f"Duplicate state id: {state.id!r} (entry {i})")
            self._states[state.id] = state

        # Parse transitions and build index.
        self._transitions: list[Transition] = []
        self._transition_index: dict[str, list[Transition]] = {}
        for i, t in enumerate(data["transitions"]):
            if not isinstance(t, dict):
                raise ValueError(
                    f"Transition entry {i} must be a dict, got {type(t).__name__}: {repr(t)[:100]}"
                )
            missing_keys = _REQUIRED_TRANSITION_KEYS - t.keys()
            if missing_keys:
                raise ValueError(
                    f"Transition entry {i} missing required keys: {sorted(missing_keys)}"
                )
            transition = Transition(
                from_state=t["from"],
                to_state=t["to"],
                condition=t["condition"],
            )
            self._transitions.append(transition)
            self._transition_index.setdefault(transition.from_state, []).append(transition)

        # Parse rules and build indexes.
        self._rules: list[Rule] = []
        self._rules_by_step: dict[str, list[Rule]] = {}
        _seen_rule_ids: set[str] = set()
        for i, r in enumerate(data["rules"]):
            if not isinstance(r, dict):
                raise ValueError(
                    f"Rule entry {i} must be a dict, got {type(r).__name__}: {repr(r)[:100]}"
                )
            missing_keys = _REQUIRED_RULE_KEYS - r.keys()
            if missing_keys:
                raise ValueError(f"Rule entry {i} missing required keys: {sorted(missing_keys)}")
            rule = Rule(
                rule_id=r["rule_id"],
                step=r["step"],
                trigger=r["trigger"],
                action=r["action"],
                source=r["source"],
                severity=r.get("severity"),
                priority=r.get("priority"),
                applies_at=r.get("applies_at"),
            )
            if rule.rule_id in _seen_rule_ids:
                raise ValueError(f"Duplicate rule_id: {rule.rule_id!r} (entry {i})")
            _seen_rule_ids.add(rule.rule_id)
            self._rules.append(rule)
            self._rules_by_step.setdefault(rule.step, []).append(rule)

        # Sort accessioning rules by severity hierarchy, others by priority.
        for step, rules in self._rules_by_step.items():
            if step == "ACCESSIONING":
                rules.sort(key=lambda r: _SEVERITY_ORDER.get(r.severity or "", _SEVERITY_FALLBACK))
            else:
                rules.sort(key=lambda r: r.priority or 0)

        # Validate applies_at references valid states.
        for rule in self._rules:
            if rule.applies_at and rule.applies_at not in self._states:
                raise ValueError(
                    f"Rule {rule.rule_id} applies_at references unknown state: {rule.applies_at}"
                )

        # Build applies_at index for O(1) IHC rule lookup by state.
        self._rules_by_applies_at: dict[str, list[Rule]] = {}
        for rule in self._rules_by_step.get("IHC", []):
            if rule.applies_at:
                self._rules_by_applies_at.setdefault(rule.applies_at, []).append(rule)

        # Parse flags (normalize set_at to always be a tuple).
        self._flags: dict[str, Flag] = {}
        for i, f_data in enumerate(data["flags"]):
            if not isinstance(f_data, dict):
                snippet = repr(f_data)[:100]
                raise ValueError(
                    f"Flag entry {i} must be a dict, got {type(f_data).__name__}: {snippet}"
                )
            missing_keys = _REQUIRED_FLAG_KEYS - f_data.keys()
            if missing_keys:
                raise ValueError(f"Flag entry {i} missing required keys: {sorted(missing_keys)}")
            set_at_raw = f_data["set_at"]
            set_at = tuple(set_at_raw) if isinstance(set_at_raw, list) else (set_at_raw,)
            flag = Flag(
                flag_id=f_data["flag_id"],
                set_at=set_at,
                effect=f_data["effect"],
                cleared_by=f_data["cleared_by"],
            )
            self._flags[flag.flag_id] = flag

        # Terminal states from explicit list.
        self._terminal_states: frozenset[str] = frozenset(data["terminal_states"])

        # Pre-computed immutable collections for callers.
        self._all_states: frozenset[str] = frozenset(self._states.keys())
        self._all_rule_ids: frozenset[str] = frozenset(r.rule_id for r in self._rules)
        self._all_flag_ids: frozenset[str] = frozenset(self._flags.keys())

        # Cached flag vocabulary (immutable data, built once).
        self._flag_vocabulary: dict[str, dict[str, Any]] = {
            flag_id: {
                "set_at": list(flag.set_at),
                "effect": flag.effect,
                "cleared_by": flag.cleared_by,
            }
            for flag_id, flag in self._flags.items()
        }

    @classmethod
    def get_instance(cls, yaml_path: Path | None = None) -> StateMachine:
        """Return a cached StateMachine for the default YAML path.

        Parses the YAML once and reuses the instance on subsequent calls.
        Pass a custom ``yaml_path`` to bypass the cache (always creates new).
        """
        global _cached_instance  # noqa: PLW0603
        if yaml_path is not None:
            return cls(yaml_path)
        if _cached_instance is None:
            _cached_instance = cls()
        return _cached_instance

    def is_valid_transition(self, from_state: str, to_state: str) -> bool:
        """Check if a transition from one state to another is structurally valid."""
        return any(t.to_state == to_state for t in self._transition_index.get(from_state, []))

    def get_valid_transitions(self, from_state: str) -> list[Transition]:
        """Return all valid transitions from a given state."""
        return list(self._transition_index.get(from_state, []))

    def is_terminal_state(self, state: str) -> bool:
        """Check if a state is terminal."""
        return state in self._terminal_states

    def get_rules_for_step(self, step: str) -> list[Rule]:
        """Return rules for a given workflow step, sorted by severity/priority."""
        return list(self._rules_by_step.get(step, []))

    def get_rules_for_state(self, state: str) -> list[Rule]:
        """Return rules applicable to a given state.

        For IHC states, matches on the rule's ``applies_at`` field using a
        pre-built index.  For non-IHC states, uses the ``_STATE_TO_STEP``
        mapping to find the corresponding rule-catalog step.

        States that intentionally return an empty list (no rule evaluation
        needed at that state):

        - Pass-through states: ``MISSING_INFO_HOLD``,
          ``DO_NOT_PROCESS``, ``HE_STAINING``
        - Terminal states: ``ORDER_COMPLETE``, ``ORDER_TERMINATED``,
          ``ORDER_TERMINATED_QNS``

        Raises ``ValueError`` if the state is not a known workflow state.
        """
        if state not in self._all_states:
            raise ValueError(f"Unknown state: {state}")

        # Try IHC applies_at index first (O(1) lookup).
        ihc_rules = self._rules_by_applies_at.get(state)
        if ihc_rules:
            return list(ihc_rules)

        # Fall back to state-to-step mapping.
        step = _STATE_TO_STEP.get(state)
        if step is None:
            return []
        return self.get_rules_for_step(step)

    def get_all_rules(self) -> list[Rule]:
        """Return all rules, sorted by severity/priority within each step."""
        result: list[Rule] = []
        for rules in self._rules_by_step.values():
            result.extend(rules)
        return result

    def get_state(self, state_id: str) -> State:
        """Return the State object for a given state_id.

        Raises:
            KeyError: If the state_id is not a known workflow state.
        """
        return self._states[state_id]

    def get_all_states(self) -> frozenset[str]:
        """Return all state IDs as an immutable set."""
        return self._all_states

    def get_all_rule_ids(self) -> frozenset[str]:
        """Return all rule IDs as an immutable set."""
        return self._all_rule_ids

    def get_all_flag_ids(self) -> frozenset[str]:
        """Return all flag IDs as an immutable set."""
        return self._all_flag_ids

    def get_flag_vocabulary(self) -> dict[str, dict[str, Any]]:
        """Return flag metadata keyed by flag_id."""
        return self._flag_vocabulary
