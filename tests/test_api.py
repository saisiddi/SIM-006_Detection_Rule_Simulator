"""API tests for SIM-006 (PRD Sections 10.2, 11 and 12; Build Spec Section 4)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sim_006.rules as rules
from sim_006.api import app
from tests.conftest import load_fixture

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
FIXED_NOW = datetime(2026, 7, 29, 14, 30, 5, tzinfo=timezone.utc)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """A TestClient with the evaluation clock frozen for determinism.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        The configured TestClient.
    """
    monkeypatch.setattr(rules, "_utcnow", lambda: FIXED_NOW)
    return TestClient(app)


class TestEvaluateEndpoint:
    """POST /evaluate."""

    def test_section_11_sample_matches_exactly(self, client: TestClient) -> None:
        payload = json.loads((SAMPLES_DIR / "evaluate_input.json").read_text())
        response = client.post("/evaluate", json=payload)
        assert response.status_code == 200
        expected = json.loads((SAMPLES_DIR / "evaluate_output.json").read_text())
        assert response.json() == expected

    def test_all_pass_fixture(self, client: TestClient) -> None:
        response = client.post("/evaluate", json=load_fixture("event_all_pass.json"))
        assert response.status_code == 200
        body = response.json()
        assert body["rules_evaluated"] == 8
        assert body["overall_gate"] == "PASS"
        assert body["simulated"] is True

    def test_mixed_result_fixture(self, client: TestClient) -> None:
        response = client.post("/evaluate", json=load_fixture("event_mixed_result.json"))
        assert response.status_code == 200
        body = response.json()
        assert body["overall_gate"] == "HARD_FAIL"
        assert body["gate_reason"] == "Rule R-02 triggered HARD_FAIL"

    def test_unknown_rule_id_returns_400(self, client: TestClient) -> None:
        payload = load_fixture("event_all_pass.json")
        payload["rule_ids"] = ["R-99"]
        response = client.post("/evaluate", json=payload)
        assert response.status_code == 400
        assert response.json() == {
            "error": "unknown_rule_id",
            "detail": "Rule ID 'R-99' not found. Valid rule IDs: "
            "R-01, R-02, R-03, R-04, R-05, R-06, R-07, R-08",
            "simulated": True,
        }

    def test_empty_rule_ids_returns_400(self, client: TestClient) -> None:
        payload = load_fixture("event_all_pass.json")
        payload["rule_ids"] = []
        response = client.post("/evaluate", json=payload)
        assert response.status_code == 400
        assert response.json()["error"] == "empty_rule_selection"
        assert response.json()["simulated"] is True

    def test_malformed_event_returns_422(self, client: TestClient) -> None:
        payload = load_fixture("event_all_pass.json")
        del payload["event"]["event_type"]
        response = client.post("/evaluate", json=payload)
        assert response.status_code == 422

    def test_naive_datetime_returns_422(self, client: TestClient) -> None:
        payload = load_fixture("event_all_pass.json")
        payload["event"]["timestamp"] = "2026-07-29T14:30:00"
        response = client.post("/evaluate", json=payload)
        assert response.status_code == 422

    def test_explain_endpoint_only_explains_supplied_evaluation(self, client: TestClient) -> None:
        evaluation = client.post("/evaluate", json=load_fixture("event_voltage_warn.json")).json()
        response = client.post("/explain", json={"evaluation": evaluation})
        assert response.status_code == 200
        assert response.json()["simulated"] is True
        assert response.json()["overall_decision"] == evaluation["overall_gate"]


class TestRulesEndpoint:
    """GET /rules."""

    def test_all_eight_rules_with_descriptions(self, client: TestClient) -> None:
        response = client.get("/rules")
        assert response.status_code == 200
        body = response.json()
        assert body["simulated"] is True
        rules_by_id = {rule["rule_id"]: rule for rule in body["rules"]}
        assert list(rules_by_id) == [f"R-{i:02d}" for i in range(1, 9)]
        for rule in body["rules"]:
            assert rule["rule_name"]
            assert rule["description"]

    def test_thresholds_present(self, client: TestClient) -> None:
        body = client.get("/rules").json()
        descriptions = " ".join(rule["description"] for rule in body["rules"])
        assert "40-56V" in descriptions
        assert "-20-55C" in descriptions
        assert "30s" in descriptions


class TestHealthEndpoint:
    """GET /health."""

    def test_health_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "simulated": True}


class TestOpenAPIDocs:
    """OpenAPI documentation is auto-generated and accessible."""

    def test_openapi_json_available(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/evaluate" in paths
        assert "/rules" in paths
        assert "/health" in paths

    def test_swagger_ui_available(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200
