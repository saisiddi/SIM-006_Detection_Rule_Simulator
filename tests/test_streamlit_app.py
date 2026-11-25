"""Streamlit UI tests via streamlit's AppTest harness (PRD Section 10.3)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import sim_006.rules as rules
import sim_006.simulator as simulator
from tests.conftest import load_fixture

FIXED_NOW = datetime(2026, 7, 29, 14, 30, 5, tzinfo=timezone.utc)
APP_PATH = str(Path(__file__).resolve().parent.parent / "sim_006" / "streamlit_app.py")


@pytest.fixture(autouse=True)
def _freeze_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the evaluation clock so R-01/R-03 checks are deterministic.

    The test-event generator is frozen to the *same* instant: R-01 now flags
    timestamps outside a symmetric +/-30s replay window, so a generated event
    stamped with wall-clock time would be skewed against a frozen evaluation
    clock and legitimately fail as a future timestamp.
    """
    monkeypatch.setattr(rules, "_utcnow", lambda: FIXED_NOW)
    monkeypatch.setattr(simulator, "_now", lambda: FIXED_NOW)


def _run_app(payload: dict) -> AppTest:
    """Run the app with the given request JSON pasted into the text area.

    Args:
        payload: The evaluation request payload to paste.

    Returns:
        The AppTest instance after clicking Run Evaluation.
    """
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    app.text_area[0].set_value(json.dumps(payload)).run(timeout=30)
    app.button[0].click().run(timeout=30)
    return app


def test_all_rules_pass_run_shows_green_badge() -> None:
    """A fully valid event renders a PASS badge and all 8 result rows."""
    app = _run_app(load_fixture("event_all_pass.json"))
    assert not app.error
    assert any("Overall gate: PASS" in md.value for md in app.markdown)
    assert len(app.dataframe[0].value) == 8


def test_hard_fail_run_shows_red_badge() -> None:
    """A null-timestamp telemetry event renders a HARD_FAIL badge."""
    app = _run_app(load_fixture("event_missing_timestamp.json"))
    assert not app.error
    assert any("Overall gate: HARD_FAIL" in md.value for md in app.markdown)
    assert any("Rule R-02 triggered HARD_FAIL" in caption.value for caption in app.caption)


def test_subset_selection_evaluates_only_selected_rules() -> None:
    """Selecting a subset bypasses unselected rules (logged, and gate ignores them)."""
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    app.text_area[0].set_value(json.dumps(load_fixture("event_missing_timestamp.json"))).run(
        timeout=30
    )
    app.radio[0].set_value("subset").run(timeout=30)
    app.multiselect[0].set_value(["R-05"]).run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert not app.error
    assert any("Overall gate: PASS" in md.value for md in app.markdown)
    assert len(app.dataframe[0].value) == 1


def test_generate_test_event_populates_generated_json() -> None:
    """Generating a test event populates the keyed JSON editor."""
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    button_labels = [button.label for button in app.button]
    app.button[button_labels.index("Generate Test Event")].click().run(timeout=30)

    generated_text = next(
        text_area.value for text_area in app.text_area if text_area.label == "Generated event JSON"
    )
    generated_payload = json.loads(generated_text)
    assert generated_payload["battery_id"] == "SIM-BATTERY-001"
    assert generated_payload["event"]["event_type"] == "telemetry"


def test_evaluate_generated_event_renders_results() -> None:
    """A generated event can be sent directly through the shared engine."""
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    button_labels = [button.label for button in app.button]
    app.button[button_labels.index("Generate Test Event")].click().run(timeout=30)
    button_labels = [button.label for button in app.button]
    app.button[button_labels.index("Evaluate generated event")].click().run(timeout=30)

    assert not app.error
    assert any("Overall gate: PASS" in markdown.value for markdown in app.markdown)


def test_default_input_falls_back_when_samples_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default input falls back to inline JSON if samples/ is unreadable."""
    from sim_006.streamlit_app import _load_default_input

    def _raise_oserror(self: Path, *args: object, **kwargs: object) -> str:
        raise OSError("missing")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)
    fallback = json.loads(_load_default_input())
    assert fallback["battery_id"] == "BID-001"
    assert fallback["rule_ids"] == "all"


def test_non_object_json_shows_error() -> None:
    """A non-object JSON payload surfaces a clean error."""
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    app.text_area[0].set_value("[1, 2, 3]").run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert app.error
    assert "must be an object" in app.error[0].value


def test_invalid_json_shows_error() -> None:
    """Malformed JSON surfaces a clean error, not a traceback."""
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    app.text_area[0].set_value("{not json").run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert app.error
    assert "Invalid JSON" in app.error[0].value


def test_empty_rule_subset_shows_error() -> None:
    """Selecting no rules in subset mode surfaces the empty-selection error."""
    app = AppTest.from_file(APP_PATH)
    app.run(timeout=30)
    app.text_area[0].set_value(json.dumps(load_fixture("event_all_pass.json"))).run(timeout=30)
    app.radio[0].set_value("subset").run(timeout=30)
    app.multiselect[0].set_value([]).run(timeout=30)
    app.button[0].click().run(timeout=30)
    assert app.error
    assert "empty_rule_selection" in app.error[0].value


def test_schema_validation_failure_shows_error() -> None:
    """A request missing event_type surfaces a validation error."""
    payload = load_fixture("event_all_pass.json")
    del payload["event"]["event_type"]
    app = _run_app(payload)
    assert app.error
    assert "Invalid evaluation request" in app.error[0].value
