"""Demo frontend: static mount, untouched API behaviour, and scenario expectations."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sim_006.api import app
from sim_006.engine import RuleEngine
from sim_006.models import EvaluationRequest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
client = TestClient(app)


def test_root_redirects_to_demo_ui() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


def test_demo_ui_is_served_with_local_assets() -> None:
    page = client.get("/app/")
    assert page.status_code == 200
    assert "Detection Rule Simulator" in page.text
    assert "fonts.googleapis" not in page.text
    assert client.get("/app/app.js").status_code == 200
    assert client.get("/app/fonts/barlow-latin-400-normal.woff2").status_code == 200


def test_existing_api_behaviour_is_unchanged_by_the_mount() -> None:
    assert client.get("/health").json() == {"status": "ok", "simulated": True}
    assert client.get("/evaluate").status_code == 405  # not swallowed by the static mount
    assert client.post("/evaluate", json={}).status_code == 422
    assert len(client.get("/rules").json()["rules"]) == 8


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_every_demo_scenario_produces_its_expected_gate() -> None:
    """Run the real scenarios.js, send each request through the real engine."""
    script = (
        "import { SCENARIOS } from './scenarios.js';"
        "console.log(JSON.stringify(SCENARIOS.map(s => ({id: s.id, expect: s.expect, triggers: s.triggers, req: s.build()}))));"  # noqa: E501 (inline JS)
    )
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    scenarios = json.loads(out)
    assert [s["id"] for s in scenarios] == [
        "clean",
        "voltage-warning",
        "replay",
        "missing-timestamp",
        "firmware",
        "impossible-soc",
    ]
    for scenario in scenarios:
        response = RuleEngine().evaluate(EvaluationRequest.model_validate(scenario["req"]))
        assert response.overall_gate == scenario["expect"], scenario["id"]
        assert response.rules_evaluated == 8


def test_demo_ui_offers_json_file_upload_next_to_the_paste_box() -> None:
    page = client.get("/app/").text
    assert 'id="req"' in page  # paste still works
    assert 'id="load-file"' in page and 'type="file"' in page and "application/json" in page


def test_demo_assets_are_cache_busted_and_upload_runs_the_evaluation() -> None:
    page = client.get("/app/").text
    assert "app.js?v=" in page and "app.css?v=" in page
    js = client.get("/app/app.js").text
    assert "and evaluated." in js and "R-01 (replay detection)" in js


def test_use_current_time_is_a_click_only_button() -> None:
    page = client.get("/app/").text
    assert 'id="use-now"' in page and "Use current time" in page
    js = client.get("/app/app.js").text
    # wired only to a click; nothing calls it on load or after a file loads
    assert js.count("useCurrentTime") == 2
    assert '$("use-now").addEventListener("click", useCurrentTime)' in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_expected_gate_on_a_rule_subset_matches_the_backend() -> None:
    """expectedGate() from the real scenarios.js must agree with the engine for every subset."""
    rule_ids = [r["rule_id"] for r in client.get("/rules").json()["rules"]]
    subsets = [[r for r in rule_ids if r != skip] for skip in rule_ids] + [
        rule_ids[:3],
        rule_ids[3:5],
    ]
    script = (
        "import { SCENARIOS, expectedGate } from './scenarios.js';"
        f"const subsets = {json.dumps(subsets)};"
        "console.log(JSON.stringify(SCENARIOS.map(s => ({id: s.id, req: s.build(),"  # noqa: E501 (inline JS)
        " want: subsets.map(ids => expectedGate(s, ids))}))));"
    )
    out = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for scenario in json.loads(out):
        for ids, want in zip(subsets, scenario["want"], strict=True):
            body = {**scenario["req"], "rule_ids": ids}
            got = client.post("/evaluate", json=body).json()
            assert got["overall_gate"] == want, (scenario["id"], ids)
    replay = next(s for s in json.loads(out) if s["id"] == "replay")
    # replay with R-01 unticked is PASS, and the backend agrees
    assert replay["want"][0] == "PASS"
    assert (
        client.post("/evaluate", json={**replay["req"], "rule_ids": subsets[0]}).json()[
            "overall_gate"
        ]
        == "PASS"
    )


def test_api_rejects_an_empty_rule_list_so_the_ui_never_sends_one() -> None:
    body = {"battery_id": "B", "event": {"event_type": "telemetry"}, "rule_ids": []}
    assert client.post("/evaluate", json=body).status_code == 400
