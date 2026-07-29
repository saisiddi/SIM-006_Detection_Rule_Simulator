"""CLI tests for SIM-006 (PRD Sections 10.1, 11 and 12)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

import sim_006.rules as rules
from sim_006.cli import main
from tests.conftest import FIXTURES_DIR

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
FIXED_NOW = datetime(2026, 7, 29, 14, 30, 5, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the evaluation clock so R-01/R-03 checks are deterministic."""
    monkeypatch.setattr(rules, "_utcnow", lambda: FIXED_NOW)


def _fixture_path(name: str) -> str:
    """Return the absolute path to a fixture file.

    Args:
        name: Fixture file name.

    Returns:
        The absolute path as a string.
    """
    return str(FIXTURES_DIR / name)


class TestEvaluate:
    """The evaluate subcommand."""

    def test_section_11_sample_matches_exactly(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            [
                "evaluate",
                "--event",
                str(SAMPLES_DIR / "evaluate_input.json"),
                "--rules",
                "R-02,R-05,R-06",
            ]
        )
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        expected = json.loads((SAMPLES_DIR / "evaluate_output.json").read_text())
        assert output == expected

    def test_rules_all_on_full_fixture(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            ["evaluate", "--event", _fixture_path("event_all_pass.json"), "--rules", "all"]
        )
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["rules_evaluated"] == 8
        assert output["overall_gate"] == "PASS"
        assert output["simulated"] is True

    def test_rule_ids_from_file_used_without_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["evaluate", "--event", _fixture_path("event_impossible_soc.json")])
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["rules_evaluated"] == 1
        assert output["results"][0]["rule_id"] == "R-08"
        assert output["overall_gate"] == "HARD_FAIL"

    def test_rules_flag_overrides_file(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            [
                "evaluate",
                "--event",
                _fixture_path("event_missing_timestamp.json"),
                "--rules",
                "R-05",
            ]
        )
        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["overall_gate"] == "PASS"
        assert output["rules_evaluated"] == 1

    def test_bypass_logged_not_silent(self, caplog: pytest.LogCaptureFixture) -> None:
        exit_code = main(
            [
                "evaluate",
                "--event",
                _fixture_path("event_missing_timestamp.json"),
                "--rules",
                "R-05",
            ]
        )
        assert exit_code == 0
        assert "bypassed" in caplog.text
        assert "R-02" in caplog.text
        assert "did not count toward the gate decision" in caplog.text

    def test_unknown_rule_id_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            ["evaluate", "--event", _fixture_path("event_all_pass.json"), "--rules", "R-99"]
        )
        captured = capsys.readouterr()
        assert exit_code == 1
        payload = json.loads(captured.err)
        assert payload["error"] == "unknown_rule_id"
        assert "R-99" in payload["detail"]
        assert payload["simulated"] is True
        assert "Traceback" not in captured.err

    def test_empty_rules_flag_rejected(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(
            ["evaluate", "--event", _fixture_path("event_all_pass.json"), "--rules", ""]
        )
        captured = capsys.readouterr()
        assert exit_code == 1
        payload = json.loads(captured.err)
        assert payload["error"] == "empty_rule_selection"
        assert "Traceback" not in captured.err

    def test_missing_event_file_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["evaluate", "--event", "no_such_file.json", "--rules", "R-02"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "cannot read event file" in captured.err
        assert "Traceback" not in captured.err

    def test_invalid_json_error(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not json", encoding="utf-8")
        exit_code = main(["evaluate", "--event", str(bad_file), "--rules", "R-02"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "not valid JSON" in captured.err
        assert "Traceback" not in captured.err

    def test_malformed_event_rejected(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        bad_file = tmp_path / "malformed.json"
        bad_file.write_text(
            json.dumps(
                {"battery_id": "BID-001", "event": {"voltage_v": 48.2}, "rule_ids": ["R-02"]}
            ),
            encoding="utf-8",
        )
        exit_code = main(["evaluate", "--event", str(bad_file)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "invalid evaluation request" in captured.err
        assert "Traceback" not in captured.err

    def test_missing_rules_and_file_rule_ids_error(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        bare_file = tmp_path / "bare.json"
        bare_file.write_text(
            json.dumps({"battery_id": "BID-001", "event": {"event_type": "telemetry"}}),
            encoding="utf-8",
        )
        exit_code = main(["evaluate", "--event", str(bare_file)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "no rules specified" in captured.err

    def test_non_object_json_error(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        bad_file = tmp_path / "list.json"
        bad_file.write_text("[1, 2, 3]", encoding="utf-8")
        exit_code = main(["evaluate", "--event", str(bad_file), "--rules", "R-02"])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "must contain a JSON object" in captured.err

    def test_no_command_prints_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main([])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "evaluate" in captured.out
        assert "list-rules" in captured.out


class TestListRules:
    """The list-rules subcommand (PRD Section 12: all 8 rules present)."""

    def test_all_eight_rules_listed(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["list-rules"])
        assert exit_code == 0
        output = capsys.readouterr().out
        for i in range(1, 9):
            rule_id = f"R-{i:02d}"
            assert rule_id in output
        assert "Replay attack detected" in output
        assert "Physically impossible telemetry" in output

    def test_thresholds_included(self, capsys: pytest.CaptureFixture[str]) -> None:
        main(["list-rules"])
        output = capsys.readouterr().out
        assert "40-56V" in output
        assert "-20-55C" in output
        assert "30s" in output
        assert "5 points" in output
