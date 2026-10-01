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
from sim_006.explanation import ExplanationService
from sim_006.models import EvaluationRequest, EvaluationResponse
from sim_006.rules import RULE_REGISTRY
from sim_006.simulator import SCENARIO_LABELS, SCENARIOS, generate_request

_GATE_COLORS: dict[str, str] = {
    "PASS": "#2e7d32",
    "WARN": "#f9a825",
    "HARD_FAIL": "#c62828",
}


_CSS = """
<style>
    .stApp {
        background:
            radial-gradient(
                circle at top,
                rgba(52, 88, 208, 0.28),
                transparent 28%
            ),
            linear-gradient(
                135deg,
                #050b1d 0%,
                #0b122e 30%,
                #120c2e 100%
            );
        color: #edf4ff;
    }

    .main .block-container {
        max-width: 1500px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    .hero {
        padding: 1.2rem 0 1rem 0;
        border-bottom: 1px solid rgba(104, 152, 255, 0.25);
        margin-bottom: 1.2rem;
    }

    .hero .eyebrow {
        font-size: 0.8rem;
        letter-spacing: 0.28rem;
        text-transform: uppercase;
        color: #6ab6ff;
        margin-bottom: 0.2rem;
    }

    .hero h1 {
        margin: 0;
        font-size: clamp(2.4rem, 5vw, 5.2rem);
        line-height: 0.96;
        font-weight: 900;
        letter-spacing: -0.06em;
        color: #eff6ff;
    }

    .hero .accent {
        background: linear-gradient(
            90deg,
            #7dd3fc 0%,
            #60a5fa 22%,
            #a78bfa 68%,
            #f0abfc 100%
        );
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
    }

    .panel {
        background: rgba(11, 18, 46, 0.72);
        border: 1px solid rgba(109, 166, 255, 0.45);
        border-radius: 18px;
        box-shadow: 0 0 25px rgba(53, 127, 255, 0.15);
        padding: 1rem 1rem 0.6rem 1rem;
        margin-bottom: 1rem;
    }

    .metric-card {
        background: rgba(14, 25, 58, 0.8);
        border: 1px solid rgba(99, 188, 255, 0.45);
        border-radius: 16px;
        padding: 0.7rem 0.9rem;
        min-height: 94px;
    }

    .metric-card .label {
        display: block;
        color: #7fc9ff;
        text-transform: uppercase;
        letter-spacing: 0.15em;
        font-size: 0.62rem;
        margin-bottom: 0.45rem;
    }

    .metric-card .value {
        display: block;
        color: #eff7ff;
        font-size: 1.25rem;
        font-weight: 700;
    }

    .gate-badge {
        display: inline-block;
        padding: 0.7rem 1.3rem;
        border-radius: 14px;
        font-weight: 800;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 0.65rem;
        box-shadow: 0 0 18px rgba(255,255,255,0.08);
    }

    .gate-pass {
        background: linear-gradient(
            90deg,
            rgba(34,197,94,.2),
            rgba(21,128,61,.72)
        );
        border: 1px solid rgba(34,197,94,.8);
    }

    .gate-warn {
        background: linear-gradient(
            90deg,
            rgba(250,204,21,.18),
            rgba(217,119,6,.7)
        );
        border: 1px solid rgba(250,204,21,.8);
    }

    .gate-hard_fail {
        background: linear-gradient(
            90deg,
            rgba(248,113,113,.20),
            rgba(220,38,38,.78)
        );
        border: 1px solid rgba(248,113,113,.8);
    }

    .rule-card {
        background: rgba(15, 22, 48, 0.8);
        border: 1px solid rgba(110, 154, 255, 0.4);
        border-radius: 16px;
        padding: 0.9rem 1rem;
        margin-bottom: 0.7rem;
    }

    .rule-card.pass {
        border-color: rgba(74, 222, 128, 0.8);
    }

    .rule-card.warn {
        border-color: rgba(250, 204, 21, 0.8);
    }

    .rule-card.hard_fail {
        border-color: rgba(248, 113, 113, 0.8);
    }

    .rule-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 1rem;
        margin-bottom: 0.35rem;
    }

    .rule-id {
        font-weight: 700;
        color: #7cd7ff;
    }

    .rule-status {
        font-size: 0.72rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        font-weight: 700;
        color: #edf6ff;
        padding: 0.2rem 0.5rem;
        border-radius: 999px;
        background: rgba(148, 163, 184, 0.18);
    }

    .rule-card.pass .rule-status {
        background: rgba(21,128,61,.32);
    }

    .rule-card.warn .rule-status {
        background: rgba(217,119,6,.32);
    }

    .rule-card.hard_fail .rule-status {
        background: rgba(220,38,38,.32);
    }

    .small-muted {
        color: #9fb6d9;
        font-size: 0.85rem;
    }

    .section-tag {
        color: #6dd3ff;
        font-size: 0.7rem;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        margin-bottom: 0.7rem;
        display: block;
    }

    .stButton>button {
        border-radius: 12px;
        border: 1px solid rgba(123, 197, 255, 0.8);
        background: linear-gradient(
            180deg,
            rgba(17,34,72,0.95),
            rgba(12,20,47,0.95)
        );
        color: #edf4ff;
        font-weight: 700;
    }

    .stButton>button:hover {
        border-color: rgba(132, 238, 255, 0.95);
        box-shadow: 0 0 15px rgba(96, 165, 250, 0.25);
    }

    .stTextArea textarea,
    .stSelectbox div[role="combobox"],
    .stMultiSelect div[role="combobox"] {
        background: rgba(10, 16, 35, 0.7);
        border: 1px solid rgba(108, 158, 255, 0.55);
        border-radius: 12px;
        color: #edf4ff;
    }

    .stDataFrame {
        background: rgba(7, 12, 26, 0.3);
        border-radius: 14px;
    }
</style>
"""


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


def _evaluate(
    raw_text: str,
    scope: str,
    selected_rule_ids: list[str],
) -> EvaluationResponse | None:
    """Parse the input and run the RuleEngine, surfacing errors in the UI.

    Args:
        raw_text: The pasted or uploaded request JSON text.
        scope: "all" or "subset".
        selected_rule_ids: Rule IDs chosen in the multi-select when scope is
            "subset".

    Returns:
        The EvaluationResponse, or None if the input failed validation.
    """
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
        return None

    if not isinstance(payload, dict):
        st.error("JSON payload must be an object: " "{battery_id, event, rule_ids?}")
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
    """Render the gate badge, results table, cards, and export button."""
    gate_class = f"gate-{response.overall_gate.lower()}"
    color = _GATE_COLORS[response.overall_gate]

    st.markdown(
        (
            f'<div class="gate-badge {gate_class}" '
            f'style="background: linear-gradient('
            f'90deg, rgba(255,255,255,0.1), {color});">'
            f"Overall gate: {response.overall_gate}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    st.caption(response.gate_reason)

    # Build a normal Python list of dictionaries so Streamlit exposes
    # the results as a native dataframe. This also keeps the UI testable
    # through Streamlit AppTest.
    rows = [
        {
            "Rule ID": result.rule_id,
            "Name": result.rule_name,
            "Result": result.result,
            "Detail": result.detail,
        }
        for result in response.results
    ]

    # Native Streamlit dataframe.
    #
    # IMPORTANT:
    # The tests intentionally inspect app.dataframe[0].value.
    # Therefore this must remain a real st.dataframe() component rather
    # than an HTML <table>.
    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download evaluation report (JSON)",
        data=response.model_dump_json(indent=2),
        file_name="sim_006_evaluation_report.json",
        mime="application/json",
    )

    if st.button("Explain with AI", key="explain_button"):
        st.session_state["explanation"] = ExplanationService().explain(response)

    explanation = st.session_state.get("explanation")

    if explanation is not None:
        st.markdown(
            "<div class='section-tag'>Explanation</div>",
            unsafe_allow_html=True,
        )
        st.write(explanation.summary)
        st.write(explanation.what_happened)
        st.write(explanation.why_it_matters)

        if explanation.recommended_checks:
            st.write("Recommended checks: " + " ".join(explanation.recommended_checks))

        st.caption(
            "AI explanation unavailable: showing the deterministic "
            "fallback. AI never decides the gate."
        )

    st.markdown(
        "<div class='section-tag'>Rule Results</div>",
        unsafe_allow_html=True,
    )

    for result in response.results:
        card_class = result.result.lower()

        st.markdown(
            f"""
            <div class='rule-card {card_class}'>
                <div class='rule-header'>
                    <span class='rule-id'>{result.rule_id}</span>
                    <span class='rule-status'>{result.result}</span>
                </div>
                <strong>{result.rule_name}</strong><br>
                <span class='small-muted'>{result.detail}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def main() -> None:
    """Render the SIM-006 Streamlit dashboard."""
    st.set_page_config(
        page_title="SIM-006 Detection Rule Simulator",
        layout="wide",
    )

    st.markdown(_CSS, unsafe_allow_html=True)

    st.markdown(
        """
        <div class='hero'>
            <div class='eyebrow'>Battery Cybersecurity Platform</div>
            <h1>
                SIM-006
                <span class='accent'>Detection Rule Simulator</span>
            </h1>
        </div>
        """,
        unsafe_allow_html=True,
    )

    status_api, status_simulator, status_ai = st.columns(3)

    with status_api:
        st.markdown(
            """
            <div class='metric-card'>
                <span class='label'>API status</span>
                <span class='value'>Local engine</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with status_simulator:
        st.markdown(
            """
            <div class='metric-card'>
                <span class='label'>Simulator status</span>
                <span class='value'>Ready</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with status_ai:
        st.markdown(
            """
            <div class='metric-card'>
                <span class='label'>AI status</span>
                <span class='value'>Fallback</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        "<div class='section-tag'>Event Input</div>",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Upload evaluation request JSON",
        type=["json"],
    )

    pasted = st.text_area(
        "Or paste evaluation request JSON",
        value=_load_default_input(),
        height=260,
    )

    scope = st.radio(
        "Rules to evaluate",
        options=["all", "subset"],
        format_func=lambda value: ("All 8 rules" if value == "all" else "Select subset"),
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

        response = _evaluate(
            raw_text,
            scope,
            selected_rule_ids,
        )

        if response is not None:
            st.session_state["evaluation"] = response

    if "evaluation" in st.session_state:
        st.markdown(
            "<div class='section-tag'>Evaluation</div>",
            unsafe_allow_html=True,
        )

        _render_results(st.session_state["evaluation"])

    st.markdown(
        "<div class='section-tag'>Test Event Simulator</div>",
        unsafe_allow_html=True,
    )

    source = st.selectbox(
        "Event source",
        ["telemetry", "identity", "firmware", "cyber"],
    )

    scenario = st.selectbox(
        "Scenario",
        options=list(SCENARIOS),
        format_func=lambda value: SCENARIO_LABELS[value],
    )

    if st.button("Generate Test Event"):
        generated = generate_request(
            scenario,
            source=source,
        )

        generated_json = generated.model_dump_json(indent=2)

        st.session_state["generated_event"] = generated_json
        st.session_state["generated_event_text"] = generated_json

        st.rerun()

    if "generated_event_text" not in st.session_state:
        st.session_state["generated_event_text"] = st.session_state.get(
            "generated_event",
            "",
        )

    generated_text = st.text_area(
        "Generated event JSON",
        height=220,
        key="generated_event_text",
    )

    if st.button("Validate generated event"):
        try:
            EvaluationRequest.model_validate(json.loads(generated_text))
            st.success("Event is valid for SIM-006 evaluation.")
        except (json.JSONDecodeError, ValidationError) as exc:
            st.error(f"Invalid generated event: {exc}")

    if st.button("Evaluate generated event"):
        if not generated_text:
            st.warning("Generate or enter an event before evaluating it.")
        else:
            response = _evaluate(
                generated_text,
                "all",
                [],
            )

            if response is not None:
                st.session_state["evaluation"] = response
                st.session_state["generated_event_status"] = (
                    "Generated event evaluated successfully."
                )
                st.rerun()

    if st.session_state.get("generated_event_status"):
        st.success(st.session_state["generated_event_status"])


if __name__ == "__main__":
    main()
