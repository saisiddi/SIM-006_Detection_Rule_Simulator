"""Drive the demo UI against a running API and cross-check every scenario.

For each of the six scenarios: click it in a real browser, read the verdict the page
shows, then send the *exact request the page sent* straight to the API and compare the
gate and every per-rule result. Also saves screenshots to evidence/demo/.

Usage: python scripts/verify_demo.py [base_url]   (API must already be running)
"""

import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
OUT = Path(__file__).resolve().parent.parent / "evidence" / "demo"
SCENARIOS = [
    ("Clean pass", "PASS", "pass_1440"),
    ("Voltage warning", "WARN", "warn_1440"),
    ("Replay attack", "HARD_FAIL", "hard_fail_1440"),
    ("Missing timestamp", "HARD_FAIL", None),
    ("Firmware tampering", "HARD_FAIL", None),
    ("Impossible SOC", "HARD_FAIL", None),
]


LOCAL = BASE.startswith(("http://localhost", "http://127.0.0.1"))
if not LOCAL:  # a public run must never overwrite the committed evidence screenshots
    OUT = Path(tempfile.mkdtemp(prefix="sim006-public-"))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return None


def check_transport() -> int:
    """/health must be 200 and "/" must redirect to /app/ (not followed, so we see the 3xx)."""
    bad = 0
    with urllib.request.urlopen(BASE + "/health", timeout=15) as res:
        body = json.load(res)
        ok = res.status == 200 and body.get("status") == "ok"
        print(f"{'OK ' if ok else 'BAD'} GET /health -> {res.status} {body}")
        bad += 0 if ok else 1
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        opener.open(BASE + "/", timeout=15)
        print("BAD GET / did not redirect")
        bad += 1
    except urllib.error.HTTPError as err:
        loc = err.headers.get("Location", "")
        ok = err.code in (301, 302, 307, 308) and loc.rstrip("/").endswith("/app")
        print(f"{'OK ' if ok else 'BAD'} GET / -> {err.code} Location: {loc}")
        bad += 0 if ok else 1
    return bad


def api_post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.load(res)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    failures = check_transport()
    latencies: list[int] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.goto(BASE + "/app/")
        page.wait_for_selector(".pill[data-state='ok']")
        print("pills:", [t.strip() for t in page.locator(".pill").all_inner_texts()])

        for label, expected, shot in SCENARIOS:
            page.get_by_role("button", name=label, exact=True).click()
            page.wait_for_function(
                "document.getElementById('master-word').textContent.startsWith('Overall gate')"
            )
            page.wait_for_timeout(350)  # let the lamp-on animation finish
            shown = page.locator("#master-word").inner_text()
            latency = page.locator("#p-latency").inner_text()
            status = page.locator("#p-status").inner_text()
            sent = json.loads(page.locator("#p-request").inner_text())
            shown_response = json.loads(page.locator("#p-response").inner_text())
            direct = api_post("/evaluate", sent)
            gate_ok = shown.endswith(direct["overall_gate"].replace("_", " "))
            rules_ok = shown_response["results"] == direct["results"]
            expect_ok = direct["overall_gate"] == expected
            ok = gate_ok and rules_ok and expect_ok and status.startswith("200")
            failures += 0 if ok else 1
            latencies.append(int(latency.split()[0]))
            print(
                f"{'OK ' if ok else 'BAD'} {label:20} page='{shown}' api={direct['overall_gate']:9} "  # noqa: E501 (inline JS)
                f"expected={expected:9} rules_match={rules_ok} http='{status}' latency='{latency}'"
            )
            if shot and LOCAL:  # never overwrite the committed evidence from a public run
                page.screenshot(path=str(OUT / f"{shot}.png"))

        # keyboard focus ring, captured on a fresh load so the ring is in view
        fresh = browser.new_page(viewport={"width": 1440, "height": 1000})
        fresh.goto(BASE + "/app/")
        fresh.wait_for_selector(".pill[data-state='ok']")
        fresh.keyboard.press("Tab")  # skip link
        fresh.keyboard.press("Tab")  # first scenario
        fresh.keyboard.press("Tab")  # second scenario
        fresh.screenshot(path=str(OUT / "focus_ring_1440.png"))

        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(BASE + "/app/")
        mobile.wait_for_selector(".pill[data-state='ok']")
        mobile.get_by_role("button", name="Replay attack", exact=True).click()
        mobile.wait_for_function(
            "document.getElementById('master-word').textContent.startsWith('Overall gate')"
        )
        mobile.wait_for_timeout(350)
        mobile.screenshot(path=str(OUT / "hard_fail_390.png"))
        for width in (320, 390, 768, 1024, 1440):
            mobile.set_viewport_size({"width": width, "height": 900})
            sw = mobile.evaluate("document.documentElement.scrollWidth")
            print(f"width {width}: scrollWidth {sw} {'OK' if sw <= width else 'HORIZONTAL SCROLL'}")
            failures += 0 if sw <= width else 1
        print(
            f"UI-measured round trips (ms): {latencies}, mean {sum(latencies) / len(latencies):.0f}"
        )
        print("console errors:", console_errors or "none")
        failures += len(console_errors)
        browser.close()
    print("RESULT:", "ALL OK" if failures == 0 else f"{failures} FAILURE(S)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
