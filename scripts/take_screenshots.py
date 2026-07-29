"""Capture Streamlit UI screenshots for the SIM-006 evidence package.

Starts a headless streamlit server, drives the UI with Playwright, and saves
a PASS-run and a HARD_FAIL-run screenshot to evidence/. Scenarios use fresh
synthetic timestamps so R-01 staleness does not fire on the PASS run.

Usage:
    python scripts/take_screenshots.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = REPO_ROOT / "evidence"
BASE_URL = "http://localhost:8517"

PASS_REQUEST = {
    "battery_id": "BID-UI-001",
    "event": {
        "event_type": "telemetry",
        "voltage_v": 48.0,
        "temperature_c": 25.0,
        "soc_percent": 60.0,
        "sequence_number": 3001,
        "certificate_expiry": "2027-01-01T00:00:00Z",
        "firmware_hash": "abc123",
        "expected_firmware_hash": "abc123",
        "open_incident": False,
        "prior_soc_percent": 58.0,
        "charging_source_present": True,
        "last_seen_sequence_number": 3000,
    },
    "rule_ids": "all",
}

HARD_FAIL_REQUEST = {
    "battery_id": "BID-UI-002",
    "event": {
        "event_type": "telemetry",
        "timestamp": None,
        "voltage_v": 48.2,
        "temperature_c": 28.1,
        "soc_percent": 78.3,
        "sequence_number": 1001,
    },
    "rule_ids": "all",
}


def _fresh_pass_request() -> dict:
    """Build the PASS request with timestamps relative to right now.

    Returns:
        The request payload with current timestamps.
    """
    now = datetime.now(timezone.utc)
    payload = dict(PASS_REQUEST)
    payload["event"] = {
        **PASS_REQUEST["event"],
        "timestamp": now.isoformat(),
        "last_seen_timestamp": (now - timedelta(seconds=5)).isoformat(),
    }
    return payload


def _run_scenario(page: "object", payload: dict, screenshot_path: Path, badge: str) -> None:
    """Paste a request, run the evaluation, and screenshot the result.

    Args:
        page: The Playwright page.
        payload: The request JSON to paste.
        screenshot_path: Destination PNG path.
        badge: Expected badge text, e.g. "Overall gate: PASS".
    """
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator("textarea").first.fill(json.dumps(payload, indent=2))
    page.get_by_role("button", name="Run Evaluation").click()
    page.get_by_text(badge).wait_for(timeout=15000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(screenshot_path), full_page=True)


def main() -> int:
    """Start the server, capture both screenshots, and stop the server.

    Returns:
        Process exit code (0 on success).
    """
    EVIDENCE_DIR.mkdir(exist_ok=True)
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(REPO_ROOT / "sim_006" / "streamlit_app.py"),
            "--server.port",
            "8517",
            "--server.headless",
            "true",
        ],
        cwd=str(REPO_ROOT),
    )
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            for _ in range(30):
                try:
                    page.goto(BASE_URL, timeout=2000)
                    break
                except PlaywrightError:
                    time.sleep(1)
            _run_scenario(
                page, _fresh_pass_request(), EVIDENCE_DIR / "ui_pass.png", "Overall gate: PASS"
            )
            _run_scenario(
                page,
                HARD_FAIL_REQUEST,
                EVIDENCE_DIR / "ui_hard_fail.png",
                "Overall gate: HARD_FAIL",
            )
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)
    print("Screenshots saved to", EVIDENCE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
