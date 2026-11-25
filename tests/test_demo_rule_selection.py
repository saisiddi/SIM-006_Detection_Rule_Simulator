"""Real-browser tests of the rule-selection group (skipped without Playwright or Chromium)."""

import json
import shutil
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from sim_006.api import app  # noqa: E402

CHROMIUM = shutil.which("chromium")
pytestmark = pytest.mark.skipif(CHROMIUM is None, reason="chromium not installed")
PORT = 8765

MULTI_FAULT = {
    "battery_id": "B-MULTI",
    "event": {
        "event_type": "telemetry",
        "voltage_v": 58.0,
        "temperature_c": 25.0,
        "soc_percent": 80.0,
        "prior_soc_percent": 50.0,
        "charging_source_present": False,
        "sequence_number": 100,
        "last_seen_sequence_number": 100,
    },
    "rule_ids": "all",
}


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM)
        pg = browser.new_page()
        pg.sent = []
        pg.on(
            "request",
            lambda r: pg.sent.append(r.post_data_json) if r.url.endswith("/evaluate") else None,
        )
        pg.goto(f"http://127.0.0.1:{PORT}/app/")
        pg.wait_for_selector("#rule-checks input")
        yield pg
        browser.close()
    server.should_exit = True
    thread.join(timeout=5)


def sent_rule_ids(pg):
    return pg.sent[-1]["rule_ids"]


def test_default_is_all_eight_and_sends_all(page) -> None:
    assert page.locator("#rule-checks input").count() == 8
    assert page.inner_text("#rule-count") == "8 of 8 rules selected"
    page.click("#run")
    page.wait_for_selector("#lamps .lamp.lit")
    assert sent_rule_ids(page) == "all"


def test_subset_sends_ticked_ids_and_persists_across_scenario_upload_and_edit(
    page, tmp_path
) -> None:
    page.click("#sel-none")
    for rid in ("R-03", "R-01", "R-05"):  # ticked out of order on purpose
        page.check(f'#rule-checks input[value="{rid}"]')
    assert page.inner_text("#rule-count") == "3 of 8 rules selected"
    page.click("#run")
    page.wait_for_function("document.querySelectorAll('#lamps .lamp.skipped').length === 5")
    assert sent_rule_ids(page) == ["R-01", "R-03", "R-05"]  # rule order
    assert json.loads(page.input_value("#req"))["rule_ids"] == ["R-01", "R-03", "R-05"]
    assert "Not evaluated (bypassed): R-02, R-04, R-06, R-07, R-08" in page.inner_text(
        "#bypass-note"
    )

    # scenario: replay with R-01 ticked fails; expected gate is computed on the subset
    page.click('#scenarios [data-id="replay"]')
    page.wait_for_function("document.getElementById('p-expect').textContent.includes('match')")
    assert sent_rule_ids(page) == ["R-01", "R-03", "R-05"]
    assert "expected HARD_FAIL" in page.inner_text("#p-expect")

    # untick R-01: the same scenario now expects PASS and the backend agrees
    page.uncheck('#rule-checks input[value="R-01"]')
    page.click('#scenarios [data-id="replay"]')
    page.wait_for_function(
        "document.getElementById('p-expect').textContent.includes('expected PASS')"
    )
    assert "expected PASS, backend returned PASS: match (2 of 8 rules)" in page.inner_text(
        "#p-expect"
    )
    assert page.locator("#lamps .lamp.skipped").count() == 6

    # upload: selection unchanged
    f = tmp_path / "multi.json"
    f.write_text(json.dumps(MULTI_FAULT))
    page.set_input_files("#file-input", str(f))
    page.wait_for_function("document.getElementById('file-note').textContent.includes('evaluated')")
    assert sent_rule_ids(page) == ["R-03", "R-05"]
    assert page.inner_text("#rule-count") == "2 of 8 rules selected"


def test_multi_fault_event_on_three_rules_shows_five_not_evaluated(page) -> None:
    page.click("#sel-none")
    for rid in ("R-01", "R-05", "R-08"):
        page.check(f'#rule-checks input[value="{rid}"]')
    page.fill("#req", json.dumps(MULTI_FAULT))
    page.click("#run")
    page.wait_for_function("document.querySelectorAll('#lamps .lamp.skipped').length === 5")
    assert page.locator("#lamps .lamp.lit").count() == 3
    assert page.locator("#lamps .lamp.skipped .chip", has_text="Not evaluated").count() == 5
    assert page.locator("#lamps .lamp.PASS").count() == 0


def test_empty_selection_disables_run_and_never_sends(page) -> None:
    page.click("#sel-none")
    assert page.is_disabled("#run")
    assert (
        page.is_visible("#rule-error")
        and page.inner_text("#rule-error") == "Select at least one rule"
    )
    before = len(page.sent)
    page.click('#scenarios [data-id="clean"]')  # fills the box, must not send
    page.wait_for_timeout(300)
    assert len(page.sent) == before
    page.click("#sel-all")
    assert page.inner_text("#rule-count") == "8 of 8 rules selected"
    assert not page.is_disabled("#run")
