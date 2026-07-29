"""Streamlit UI for SIM-006 (PRD Section 10.3).

Paste or upload an evaluation request JSON ({battery_id, event, rule_ids?}),
multi-select rules or evaluate all, run the shared RuleEngine, view a
color-coded gate badge and results table, and download the JSON report.
"""

import json
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from sim_006.engine import RuleEngine, RuleSelectionError
from sim_006.models import EvaluationRequest, EvaluationResponse
from sim_006.rules import RULE_REGISTRY

_GATE_COLORS: dict[str, str] = {"PASS": "#2e7d32", "WARN": "#f9a825", "HARD_FAIL": "#c62828"}


def _load_default_input() -> str:
    """Load the PRD Section 11 sample as the default input text.

    Returns:
        The sample request JSON, or a minimal inline fallback if the samples
        directory is unavailable.
    """
    sample_path = Path(__file__).resolve().parent.parent / "samples" / "evaluate_input.json"
    try:
        return sample_path.read_text(encoding="utf-8")
    except OSError:
        return json.dumps(
            {
                "battery_id": "BID-001",
                "event": {"event_type": "telemetry"},
                "rule_ids": "all",
            },
            indent=2,
        )


def _evaluate(raw_text: str, scope: str, selected_rule_ids: list[str]) -> EvaluationResponse | None:
    """Parse the input and run the RuleEngine, surfacing errors in the UI.

    Args:
        raw_text: The pasted or uploaded request JSON text.
        scope: "all" or "subset".
        selected_rule_ids: Rule IDs chosen in the multi-select when scope is
            "subset".

    Returns:
        The EvaluationResponse, or None if the input failed validation (the
        error is shown via st.error).
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        st.error("JSON payload must be an object: {battery_id, event, rule_ids?}")
        return None

    payload["rule_ids"] = "all" if scope == "all" else selected_rule_ids
    try:
        request = EvaluationRequest.model_validate(payload)
    except ValidationError as exc:
        st.error(f"Invalid evaluation request: {exc}")
        return None

    try:
        return RuleEngine().evaluate(request)
    except RuleSelectionError as exc:
        st.error(f"{exc.error}: {exc.detail}")
        return None


def _render_results(response: EvaluationResponse) -> None:
    """Render the gate badge, results table, and export button.

    Args:
        response: The EvaluationResponse to display.
    """
    color = _GATE_COLORS[response.overall_gate]
    st.markdown(
        f'<span style="background-color:{color};color:white;padding:6px 16px;'
        f'border-radius:12px;font-weight:bold">'
        f"Overall gate: {response.overall_gate}</span>",
        unsafe_allow_html=True,
    )
    st.caption(response.gate_reason)

    rows = [
        {
            "Rule ID": result.rule_id,
            "Name": result.rule_name,
            "Result": result.result,
            "Detail": result.detail,
        }
        for result in response.results
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.download_button(
        "Download evaluation report (JSON)",
        data=response.model_dump_json(indent=2),
        file_name="sim_006_evaluation_report.json",
        mime="application/json",
    )


def main() -> None:
    """Render the SIM-006 Streamlit dashboard."""
    st.set_page_config(page_title="SIM-006 Detection Rule Simulator", layout="wide")
    st.title("SIM-006 Detection Rule Simulator")
    st.caption("Detection rule evaluation on synthetic events. All output is simulated.")

    uploaded = st.file_uploader("Upload evaluation request JSON", type=["json"])
    pasted = st.text_area(
        "Or paste evaluation request JSON", value=_load_default_input(), height=260
    )

    scope = st.radio(
        "Rules to evaluate",
        options=["all", "subset"],
        format_func=lambda value: "All 8 rules" if value == "all" else "Select subset",
        horizontal=True,
    )
    selected_rule_ids: list[str] = []
    if scope == "subset":
        selected_rule_ids = st.multiselect(
            "Rule IDs",
            options=list(RULE_REGISTRY),
            default=["R-02", "R-05", "R-06"],
        )

    if st.button("Run Evaluation"):
        raw_text = uploaded.getvalue().decode("utf-8") if uploaded is not None else pasted
        response = _evaluate(raw_text, scope, selected_rule_ids)
        if response is not None:
            st.session_state["evaluation"] = response

    if "evaluation" in st.session_state:
        _render_results(st.session_state["evaluation"])


if __name__ == "__main__":
    main()
