"""Red-team tests: malformed YAML fed to StateMachine.__init__.

Each test starts from minimal_valid_yaml and corrupts one thing.
Tests surface uncaught KeyErrors for missing required fields and
document silently accepted but semantically wrong inputs.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.workflow.state_machine import StateMachine

# ---------------------------------------------------------------------------
# Top-level structural errors
# ---------------------------------------------------------------------------


class TestMalformedYAMLStructure:
    """Top-level structure is wrong (list, scalar, None, missing keys)."""

    def test_list_root(self, make_yaml: Any) -> None:
        """YAML root is a list → ValueError."""
        path = make_yaml([1, 2, 3])
        with pytest.raises(ValueError, match="mapping root"):
            StateMachine(yaml_path=path)

    def test_scalar_root(self, make_yaml: Any) -> None:
        """YAML root is a scalar → ValueError."""
        path = make_yaml("just a string")
        with pytest.raises(ValueError, match="mapping root"):
            StateMachine(yaml_path=path)

    def test_none_root(self, make_yaml: Any) -> None:
        """YAML root is None (empty file) → ValueError."""
        path = make_yaml(None)
        with pytest.raises(ValueError, match="mapping root"):
            StateMachine(yaml_path=path)

    def test_missing_required_key(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Missing a required top-level key → ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        del data["transitions"]
        path = make_yaml(data)
        with pytest.raises(ValueError, match="missing required keys"):
            StateMachine(yaml_path=path)

    def test_states_as_dict(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """'states' is a dict instead of list → ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = {"ONLY_STATE": {"phase": "test"}}
        path = make_yaml(data)
        with pytest.raises(ValueError, match="must be a list"):
            StateMachine(yaml_path=path)

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Nonexistent file → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            StateMachine(yaml_path=tmp_path / "does_not_exist.yaml")

    def test_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        """Unparseable YAML → ValueError."""
        p = tmp_path / "bad.yaml"
        p.write_text("states:\n  - id: [unterminated\n")
        with pytest.raises(ValueError, match="Invalid YAML"):
            StateMachine(yaml_path=p)


# ---------------------------------------------------------------------------
# Per-state dict corruption
# ---------------------------------------------------------------------------


class TestMalformedStateEntries:
    """Per-state dict is missing required keys or has wrong types."""

    def test_state_missing_id(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """State entry without 'id' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [{"phase": "test", "description": "no id", "terminal": False}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_state_missing_phase(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """State entry without 'phase' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [{"id": "S1", "description": "no phase", "terminal": False}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_state_missing_description(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """State entry without 'description' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [{"id": "S1", "phase": "test", "terminal": False}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_state_missing_terminal(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """State entry without 'terminal' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [{"id": "S1", "phase": "test", "description": "no terminal"}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_state_id_as_integer(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Integer state id is accepted silently (stored as int key)."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [{"id": 42, "phase": "test", "description": "int id", "terminal": False}]
        data["terminal_states"] = []
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        # Documents that integer id is accepted — 42 is stored as-is.
        assert 42 in sm.get_all_states()

    def test_terminal_as_truthy_string(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """String 'yes' for terminal field is truthy but not boolean."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [{"id": "S1", "phase": "test", "description": "truthy", "terminal": "yes"}]
        data["terminal_states"] = []
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        # The State dataclass stores "yes" — it's truthy but not True.
        state = sm._states["S1"]
        assert state.terminal == "yes"
        assert state.terminal is not True

    def test_duplicate_state_ids(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Duplicate state IDs → ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["states"] = [
            {"id": "DUP", "phase": "a", "description": "first", "terminal": False},
            {"id": "DUP", "phase": "b", "description": "second", "terminal": True},
        ]
        data["terminal_states"] = []
        path = make_yaml(data)
        with pytest.raises(ValueError, match="Duplicate state id"):
            StateMachine(yaml_path=path)


# ---------------------------------------------------------------------------
# Per-transition dict corruption
# ---------------------------------------------------------------------------


class TestMalformedTransitionEntries:
    """Transition dict is missing required keys or references bad states."""

    def test_transition_missing_from(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Transition without 'from' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["transitions"] = [{"to": "ONLY_STATE", "condition": "always"}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_transition_missing_to(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Transition without 'to' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["transitions"] = [{"from": "ONLY_STATE", "condition": "always"}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_transition_missing_condition(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Transition without 'condition' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["transitions"] = [{"from": "ONLY_STATE", "to": "ONLY_STATE"}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_transition_references_nonexistent_state(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Transition referencing unknown state is accepted silently."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["transitions"] = [{"from": "ONLY_STATE", "to": "PHANTOM", "condition": "always"}]
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        # Documents that transitions to nonexistent states are allowed.
        assert sm.is_valid_transition("ONLY_STATE", "PHANTOM") is True


# ---------------------------------------------------------------------------
# Per-rule dict corruption
# ---------------------------------------------------------------------------


class TestMalformedRuleEntries:
    """Rule dict is missing required keys or has unusual values."""

    def test_rule_missing_rule_id(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Rule without 'rule_id' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["rules"] = [
            {
                "step": "TEST",
                "trigger": "always",
                "action": "do thing",
                "source": "test",
            }
        ]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_duplicate_rule_ids(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Duplicate rule IDs → ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["rules"] = [
            {
                "rule_id": "R-001",
                "step": "TEST",
                "trigger": "a",
                "action": "x",
                "source": "s",
            },
            {
                "rule_id": "R-001",
                "step": "TEST",
                "trigger": "b",
                "action": "y",
                "source": "s",
            },
        ]
        path = make_yaml(data)
        with pytest.raises(ValueError, match="Duplicate rule_id"):
            StateMachine(yaml_path=path)

    def test_unknown_severity_value(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Unknown severity falls back to position 99 in sort order."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["rules"] = [
            {
                "rule_id": "R-001",
                "step": "ACCESSIONING",
                "trigger": "a",
                "action": "x",
                "source": "s",
                "severity": "UNKNOWN_SEVERITY",
            },
            {
                "rule_id": "R-002",
                "step": "ACCESSIONING",
                "trigger": "b",
                "action": "y",
                "source": "s",
                "severity": "REJECT",
            },
        ]
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        rules = sm.get_rules_for_step("ACCESSIONING")
        # REJECT (0) sorts before UNKNOWN_SEVERITY (99).
        assert rules[0].rule_id == "R-002"
        assert rules[1].rule_id == "R-001"

    def test_applies_at_references_nonexistent_state(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Rule applies_at referencing unknown state → ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["rules"] = [
            {
                "rule_id": "R-001",
                "step": "IHC",
                "trigger": "a",
                "action": "x",
                "source": "s",
                "applies_at": "PHANTOM_STATE",
            }
        ]
        path = make_yaml(data)
        with pytest.raises(ValueError, match="unknown state"):
            StateMachine(yaml_path=path)


# ---------------------------------------------------------------------------
# Per-flag dict corruption
# ---------------------------------------------------------------------------


class TestMalformedFlagEntries:
    """Flag dict is missing required keys or has unusual types."""

    def test_flag_missing_flag_id(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Flag without 'flag_id' → should raise ValueError."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["flags"] = [{"set_at": "ONLY_STATE", "effect": "something", "cleared_by": "never"}]
        path = make_yaml(data)
        with pytest.raises(ValueError):
            StateMachine(yaml_path=path)

    def test_set_at_as_integer(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Integer set_at is wrapped in tuple as (42,) — accepted silently."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["flags"] = [{"flag_id": "F1", "set_at": 42, "effect": "e", "cleared_by": "c"}]
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        assert sm._flags["F1"].set_at == (42,)

    def test_set_at_as_empty_list(self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]) -> None:
        """Empty list set_at is accepted as empty tuple."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["flags"] = [{"flag_id": "F1", "set_at": [], "effect": "e", "cleared_by": "c"}]
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        assert sm._flags["F1"].set_at == ()


# ---------------------------------------------------------------------------
# terminal_states validation
# ---------------------------------------------------------------------------


class TestTerminalStatesValidation:
    """terminal_states list edge cases."""

    def test_terminal_states_references_nonexistent_state(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """terminal_states referencing unknown state → accepted silently."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["terminal_states"] = ["PHANTOM"]
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        # Documents: is_terminal_state("PHANTOM") returns True even though it's not a state.
        assert sm.is_terminal_state("PHANTOM") is True
        assert "PHANTOM" not in sm.get_all_states()

    def test_terminal_states_as_string(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """String terminal_states → ValueError (must be a list)."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["terminal_states"] = "ORDER_COMPLETE"
        path = make_yaml(data)
        with pytest.raises(ValueError, match="must be a list"):
            StateMachine(yaml_path=path)

    def test_terminal_states_as_empty_list(
        self, make_yaml: Any, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Empty terminal_states → all is_terminal_state() returns False."""
        data = copy.deepcopy(minimal_valid_yaml)
        data["terminal_states"] = []
        path = make_yaml(data)
        sm = StateMachine(yaml_path=path)
        assert sm.is_terminal_state("ONLY_STATE") is False


# ---------------------------------------------------------------------------
# Path validation (CWE-22 mitigation)
# ---------------------------------------------------------------------------


class TestYAMLPathValidation:
    """Runtime validation rejects paths without YAML extensions."""

    def test_non_yaml_extension_rejected(self, tmp_path: Path) -> None:
        """A .txt file is rejected even if it contains valid YAML."""
        bad = tmp_path / "workflow.txt"
        bad.write_text("states: []")
        with pytest.raises(ValueError, match=r"\.yaml or \.yml extension"):
            StateMachine(yaml_path=bad)

    def test_no_extension_rejected(self, tmp_path: Path) -> None:
        """A file with no extension is rejected."""
        bad = tmp_path / "workflow"
        bad.write_text("states: []")
        with pytest.raises(ValueError, match=r"\.yaml or \.yml extension"):
            StateMachine(yaml_path=bad)

    def test_yml_extension_accepted(
        self, tmp_path: Path, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """.yml extension is accepted alongside .yaml."""
        yml_path = tmp_path / "workflow.yml"
        yml_path.write_text(yaml.dump(minimal_valid_yaml))
        sm = StateMachine(yaml_path=yml_path)
        assert sm is not None

    def test_uppercase_extensions_accepted(
        self, tmp_path: Path, minimal_valid_yaml: dict[str, Any]
    ) -> None:
        """Mixed-case extensions (.YAML, .YML) are accepted via .lower()."""
        for ext in (".YAML", ".YML", ".Yaml"):
            path = tmp_path / f"workflow{ext}"
            path.write_text(yaml.dump(minimal_valid_yaml))
            sm = StateMachine(yaml_path=path)
            assert sm is not None

    def test_symlink_target_extension_checked(self, tmp_path: Path) -> None:
        """Symlink resolution checks the target's extension, not the link name."""
        target = tmp_path / "data.txt"
        target.write_text("states: []")
        link = tmp_path / "workflow.yaml"
        link.symlink_to(target)
        # resolve() follows the symlink; target has .txt → rejected.
        with pytest.raises(ValueError, match=r"\.yaml or \.yml extension"):
            StateMachine(yaml_path=link)
