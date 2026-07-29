"""Integration tests: the three interfaces against one engine (PRD 12, Blueprint 4.3)."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import sim_006.rules as rules
from sim_006.api import app
from sim_006.cli import main as cli_main
from sim_006.engine import RuleEngine
from sim_006.models import EvaluationRequest
from tests.conftest import FIXTURES_DIR, load_fixture

FIXED_NOW = datetime(2026, 7, 29, 14, 30, 5, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parent.parent

ALL_FIXTURES = [
    "event_missing_timestamp.json",
    "event_voltage_warn.json",
    "event_all_pass.json",
    "event_mixed_result.json",
    "event_impossible_soc.json",
]


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the evaluation clock so all interfaces agree deterministically."""
    monkeypatch.setattr(rules, "_utcnow", lambda: FIXED_NOW)


def _api_response(payload: dict) -> dict:
    """Run a request through the FastAPI interface.

    Args:
        payload: The evaluation request payload.

    Returns:
        The response JSON.
    """
    response = TestClient(app).post("/evaluate", json=payload)
    assert response.status_code == 200
    return response.json()


def _cli_response(payload: dict, tmp_path: Path, capsys: pytest.CaptureFixture) -> dict:
    """Run a request through the CLI interface.

    Args:
        payload: The evaluation request payload.
        tmp_path: Temporary directory for the request file.
        capsys: Pytest capture fixture.

    Returns:
        The response JSON from stdout.
    """
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(payload), encoding="utf-8")
    exit_code = cli_main(["evaluate", "--event", str(request_file)])
    assert exit_code == 0
    return json.loads(capsys.readouterr().out)


class TestTC00604MultiRuleAggregation:
    """TC-006-04: a failing rule overrides warnings — identical on all interfaces."""

    def test_mixed_result_same_on_all_interfaces(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = load_fixture("event_mixed_result.json")
        engine_response = (
            RuleEngine().evaluate(EvaluationRequest.model_validate(payload)).model_dump()
        )
        api_response = _api_response(payload)
        cli_response = _cli_response(payload, tmp_path, capsys)
        assert engine_response == api_response == cli_response
        assert api_response["overall_gate"] == "HARD_FAIL"


class TestCrossInterfaceConsistency:
    """All three interfaces must return byte-identical responses (PRD Section 7)."""

    @pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
    def test_engine_api_and_cli_agree(
        self, fixture_name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        payload = load_fixture(fixture_name)
        engine_response = (
            RuleEngine().evaluate(EvaluationRequest.model_validate(payload)).model_dump()
        )
        api_response = _api_response(payload)
        cli_response = _cli_response(payload, tmp_path, capsys)
        assert engine_response == api_response
        assert api_response == cli_response
        assert api_response["simulated"] is True


class TestBypassIntegration:
    """Rule bypass scenario across interfaces (PRD Section 12)."""

    def test_bypassed_hard_fail_rule_excluded_from_gate(self, tmp_path: Path) -> None:
        payload = load_fixture("event_missing_timestamp.json")
        payload["rule_ids"] = ["R-05"]
        api_response = _api_response(payload)
        assert api_response["overall_gate"] == "PASS"
        assert api_response["rules_evaluated"] == 1
        assert all(result["rule_id"] != "R-02" for result in api_response["results"])


class TestPackageEntryPoint:
    """python -m sim_006 works as a real subprocess (PRD Section 8)."""

    def test_module_entry_point_list_rules(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "sim_006", "list-rules"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert completed.returncode == 0
        for i in range(1, 9):
            assert f"R-{i:02d}" in completed.stdout

    def test_module_entry_point_evaluate_end_to_end(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "sim_006",
                "evaluate",
                "--event",
                str(FIXTURES_DIR / "event_missing_timestamp.json"),
            ],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
        )
        assert completed.returncode == 0
        output = json.loads(completed.stdout)
        assert output["overall_gate"] == "HARD_FAIL"
        assert output["simulated"] is True
