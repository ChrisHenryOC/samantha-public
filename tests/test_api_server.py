"""Tests for the FastAPI server and REST endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.models.base import ModelResponse
from src.prediction.engine import PredictionEngine, PredictionResult
from src.server.app import create_test_app
from src.server.config import ServerConfig
from src.server.routing_service import RoutingService
from src.workflow.database import Database
from src.workflow.models import Event, Order, Slide
from src.workflow.state_machine import StateMachine

# --- Helpers ---


def _make_order(
    order_id: str,
    state: str = "ACCESSIONING",
    priority: str = "routine",
    flags: list[str] | None = None,
) -> Order:
    return Order(
        order_id=order_id,
        scenario_id="live",
        patient_name="Jane Doe",
        patient_age=55,
        patient_sex="F",
        specimen_type="Core Needle Biopsy",
        anatomic_site="Left Breast",
        fixative="10% NBF",
        fixation_time_hours=12.0,
        ordered_tests=["ER", "PR", "HER2", "Ki-67"],
        priority=priority,
        billing_info_present=True,
        current_state=state,
        flags=flags or [],
    )


def _make_slide(slide_id: str, order_id: str, test: str = "H&E") -> Slide:
    return Slide(
        slide_id=slide_id,
        order_id=order_id,
        test_assignment=test,
        status="sectioned",
    )


def _make_event(
    order_id: str,
    event_type: str = "order_received",
    step_number: int = 1,
) -> Event:
    return Event(
        event_id=str(uuid.uuid4()),
        order_id=order_id,
        step_number=step_number,
        event_type=event_type,
        event_data={},
    )


def _make_prediction_result(
    next_state: str = "ACCEPTED",
    applied_rules: list[str] | None = None,
    flags: list[str] | None = None,
) -> PredictionResult:
    response = ModelResponse(
        raw_text="{}",
        parsed_output={
            "next_state": next_state,
            "applied_rules": applied_rules or ["ACC-008"],
            "flags": flags or [],
            "reasoning": "Test",
        },
        latency_ms=100.0,
        input_tokens=50,
        output_tokens=25,
        cost_estimate_usd=None,
        model_id="test-model",
    )
    return PredictionResult(
        next_state=next_state,
        applied_rules=tuple(applied_rules or ["ACC-008"]),
        flags=tuple(flags or []),
        reasoning="Test",
        raw_response=response,
    )


# --- Fixtures ---


@pytest.fixture
def server_config() -> ServerConfig:
    return ServerConfig(
        model_id="test-model",
        provider="llamacpp",
        llamacpp_url="http://localhost:8080",
        db_path="data/test.sqlite",
        host="127.0.0.1",
        port=8000,
    )


@pytest.fixture
def db(tmp_path: Path) -> Generator[Database, None, None]:
    """Create a temporary database with test data."""
    database = Database(tmp_path / "test.sqlite", check_same_thread=False)
    with database:
        database.init_db()

        # Seed test data
        database.insert_order(_make_order("ORD-001", state="ACCESSIONING"), _commit=False)
        database.insert_order(
            _make_order("ORD-002", state="ACCEPTED", priority="rush"), _commit=False
        )
        database.insert_order(
            _make_order(
                "ORD-003",
                state="PATHOLOGIST_HE_REVIEW",
                flags=["FIXATION_WARNING"],
            ),
            _commit=False,
        )
        database.insert_order(_make_order("ORD-004", state="ORDER_COMPLETE"), _commit=False)
        database.insert_slide(_make_slide("SLD-001", "ORD-001", "H&E"), _commit=False)
        database.insert_slide(_make_slide("SLD-002", "ORD-001", "ER"), _commit=False)

        # Seed an event for ORD-001
        database.insert_event(
            _make_event("ORD-001", "order_received", step_number=1), _commit=False
        )

        database.commit()
        yield database


@pytest.fixture
def mock_engine() -> MagicMock:
    engine = MagicMock(spec=PredictionEngine)
    engine.model_id = "test-model"
    engine.provider = "mock"
    return engine


@pytest.fixture
def service(db: Database, mock_engine: MagicMock) -> RoutingService:
    state_machine = StateMachine.get_instance()
    return RoutingService(db, mock_engine, state_machine)


@pytest.fixture
def client(db: Database, service: RoutingService, server_config: ServerConfig) -> TestClient:
    app = create_test_app(db, service, server_config)
    return TestClient(app)


# --- Health endpoint ---


class TestHealthEndpoint:
    def test_health_returns_config(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model"] == "test-model"
        assert data["provider"] == "llamacpp"
        assert data["provider_status"] in ("connected", "unreachable")


# --- Orders endpoints ---


class TestListOrders:
    def test_all_orders(self, client: TestClient) -> None:
        resp = client.get("/api/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4

    def test_filter_by_state(self, client: TestClient) -> None:
        resp = client.get("/api/orders?state=ACCESSIONING")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["order_id"] == "ORD-001"

    def test_filter_by_role_accessioner(self, client: TestClient) -> None:
        resp = client.get("/api/orders?role=accessioner")
        assert resp.status_code == 200
        data = resp.json()
        # Only ORD-001 is in ACCESSIONING
        assert len(data) == 1
        assert data[0]["current_state"] == "ACCESSIONING"

    def test_filter_by_role_pathologist(self, client: TestClient) -> None:
        resp = client.get("/api/orders?role=pathologist")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["order_id"] == "ORD-003"

    def test_filter_by_role_lab_manager_sees_all(self, client: TestClient) -> None:
        resp = client.get("/api/orders?role=lab_manager")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4

    def test_invalid_role_returns_400(self, client: TestClient) -> None:
        resp = client.get("/api/orders?role=invalid")
        assert resp.status_code == 400

    def test_filter_by_priority(self, client: TestClient) -> None:
        resp = client.get("/api/orders?priority=rush")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["order_id"] == "ORD-002"


class TestGetOrder:
    def test_existing_order(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["order_id"] == "ORD-001"
        assert data["current_state"] == "ACCESSIONING"

    def test_missing_order_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-MISSING")
        assert resp.status_code == 404


class TestGetOrderEvents:
    def test_order_events(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-001/events")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "order_received"
        assert "created_at" in data[0]

    def test_missing_order_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-MISSING/events")
        assert resp.status_code == 404


class TestGetOrderSlides:
    def test_order_slides(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-001/slides")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        slide_ids = {s["slide_id"] for s in data}
        assert slide_ids == {"SLD-001", "SLD-002"}

    def test_order_with_no_slides(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-002/slides")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_missing_order_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/orders/ORD-MISSING/slides")
        assert resp.status_code == 404


# --- Events endpoint ---


class TestRoutingServicePromptExtras:
    def test_prompt_extras_passed_to_engine(self, db: Database, mock_engine: MagicMock) -> None:
        mock_engine.predict_routing.return_value = _make_prediction_result(next_state="ACCEPTED")
        state_machine = StateMachine.get_instance()
        extras = frozenset({"skills", "retry_clarification"})
        service = RoutingService(db, mock_engine, state_machine, prompt_extras=extras)

        event = _make_event("ORD-001", "order_received", step_number=2)
        service.process_event("ORD-001", event)

        call_kwargs = mock_engine.predict_routing.call_args
        assert call_kwargs.kwargs["prompt_extras"] == extras

    def test_prompt_extras_default_empty(self, db: Database, mock_engine: MagicMock) -> None:
        mock_engine.predict_routing.return_value = _make_prediction_result(next_state="ACCEPTED")
        state_machine = StateMachine.get_instance()
        service = RoutingService(db, mock_engine, state_machine)

        event = _make_event("ORD-001", "order_received", step_number=2)
        service.process_event("ORD-001", event)

        call_kwargs = mock_engine.predict_routing.call_args
        assert call_kwargs.kwargs["prompt_extras"] == frozenset()


class TestSubmitEvent:
    def test_submit_event_routes_order(self, client: TestClient, mock_engine: MagicMock) -> None:
        mock_engine.predict_routing.return_value = _make_prediction_result(next_state="ACCEPTED")

        resp = client.post(
            "/api/events",
            json={
                "order_id": "ORD-001",
                "event_type": "order_received",
                "event_data": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied"] is True
        assert data["to_state"] == "ACCEPTED"
        assert data["from_state"] == "ACCESSIONING"

    def test_submit_event_missing_order_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/events",
            json={
                "order_id": "ORD-MISSING",
                "event_type": "order_received",
                "event_data": {},
            },
        )
        assert resp.status_code == 404

    def test_submit_event_terminal_order_returns_409(self, client: TestClient) -> None:
        resp = client.post(
            "/api/events",
            json={
                "order_id": "ORD-004",
                "event_type": "order_received",
                "event_data": {},
            },
        )
        assert resp.status_code == 409
        assert "terminal state" in resp.json()["detail"]

    def test_submit_event_increments_step_number(
        self, client: TestClient, mock_engine: MagicMock, db: Database
    ) -> None:
        mock_engine.predict_routing.return_value = _make_prediction_result()

        # ORD-001 already has 1 event (step_number=1)
        client.post(
            "/api/events",
            json={
                "order_id": "ORD-001",
                "event_type": "order_received",
                "event_data": {},
            },
        )

        events = db.get_events_for_order("ORD-001")
        # Original event (step 1) + new event (step 2)
        assert len(events) == 2
        assert events[-1].step_number == 2

    def test_submit_event_missing_fields_returns_422(self, client: TestClient) -> None:
        resp = client.post("/api/events", json={"order_id": "ORD-001"})
        assert resp.status_code == 422


# --- Config tests ---


class TestServerConfig:
    def test_load_valid_config(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text(
            "model_id: qwen3:8b\n"
            "llamacpp_url: http://localhost:8080\n"
            "db_path: data/live.sqlite\n"
            "host: 127.0.0.1\n"
            "port: 8000\n"
        )
        config = load_server_config(config_file)
        assert config.model_id == "qwen3:8b"
        assert config.port == 8000
        assert config.prompt_extras == frozenset()

    def test_load_config_with_prompt_extras_string(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text(
            "model_id: qwen3:8b\n"
            "llamacpp_url: http://localhost:8080\n"
            "db_path: data/live.sqlite\n"
            'prompt_extras: "skills,retry_clarification"\n'
        )
        config = load_server_config(config_file)
        assert config.prompt_extras == frozenset({"skills", "retry_clarification"})

    def test_load_config_with_prompt_extras_list(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text(
            "model_id: qwen3:8b\n"
            "llamacpp_url: http://localhost:8080\n"
            "db_path: data/live.sqlite\n"
            "prompt_extras:\n"
            "  - skills\n"
            "  - few_shot\n"
        )
        config = load_server_config(config_file)
        assert config.prompt_extras == frozenset({"skills", "few_shot"})

    def test_load_config_with_invalid_prompt_extras_raises(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text(
            "model_id: qwen3:8b\n"
            "llamacpp_url: http://localhost:8080\n"
            "db_path: data/live.sqlite\n"
            'prompt_extras: "skills,bogus"\n'
        )
        with pytest.raises(ValueError, match="Invalid prompt_extras"):
            load_server_config(config_file)

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text("model_id: qwen3:8b\n")
        with pytest.raises(KeyError):
            load_server_config(config_file)

    def test_non_dict_yaml_raises(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text("- item1\n- item2\n")
        with pytest.raises(ValueError, match="YAML mapping"):
            load_server_config(config_file)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        with pytest.raises(FileNotFoundError):
            load_server_config(tmp_path / "nonexistent.yaml")

    def test_defaults_for_host_and_port(self, tmp_path: Path) -> None:
        from src.server.config import load_server_config

        config_file = tmp_path / "server.yaml"
        config_file.write_text(
            "model_id: qwen3:8b\nllamacpp_url: http://localhost:8080\ndb_path: data/live.sqlite\n"
        )
        config = load_server_config(config_file)
        assert config.host == "0.0.0.0"
        assert config.port == 8000
