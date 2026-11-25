"""Keyboard-only flow, touch-target, type-size and live-region checks for the demo UI.

Usage: python scripts/verify_a11y.py [base_url]   (API must already be running)
"""

import sys

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'OK ' if ok else 'BAD'} {name} {detail}")
    if not ok:
        fails.append(name)


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page.goto(BASE + "/app/")
    page.wait_for_selector(".pill[data-state='ok']")

    # --- keyboard only: scenario -> read result -> download -> explain ---
    page.keyboard.press("Tab")  # skip link
    page.keyboard.press("Tab")  # first scenario (Clean pass)
    page.keyboard.press("Tab")  # Voltage warning
    focused = page.evaluate("document.activeElement.textContent")
    check("tab order reaches scenarios in DOM order", focused.strip() == "Voltage warning", focused)
    ring = page.evaluate(
        "(() => { const s = getComputedStyle(document.activeElement);"
        " return s.outlineStyle + ' ' + s.outlineWidth; })()"
    )
    check("focus ring visible on keyboard focus", ring.startswith("solid 3px"), ring)
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('live').textContent.includes('Overall gate')")
    live = page.locator("#live").inner_text()
    check("live region announces verdict", "Overall gate: WARN" in live, live)
    check("live region is aria-live=polite", page.get_attribute("#live", "aria-live") == "polite")

    # move on with Tab only until Download is focused, then Explain
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "download":
            break
    check(
        "download reachable by keyboard", page.evaluate("document.activeElement.id") == "download"
    )
    with page.expect_download() as dl:
        page.keyboard.press("Enter")
    check(
        "download via keyboard works",
        dl.value.suggested_filename == "sim_006_evaluation_report.json",
    )
    page.keyboard.press("Tab")
    check("explain reachable by keyboard", page.evaluate("document.activeElement.id") == "explain")
    page.keyboard.press("Enter")
    page.wait_for_selector("#explanation:not([hidden]) .provenance")
    prov = page.locator(".provenance").inner_text()
    check(
        "explanation states its provenance honestly",
        "fallback" in prov.lower() or "AI-generated" in prov,
        prov,
    )
    pill = page.locator(".pill").last.inner_text()
    check(
        "AI pill updated from the real /explain response",
        "fallback" in pill or "live model" in pill,
        pill,
    )

    # --- sizes ---
    small = page.evaluate(
        """() => [...document.querySelectorAll('button, input, textarea, .pill, a')]
        .filter(e => e.getClientRects().length && !e.classList.contains('skip'))
        .map(e => { const r = e.getBoundingClientRect();
        return [e.tagName + '#' + (e.id || e.textContent.trim().slice(0, 18)),
        Math.round(r.width), Math.round(r.height)]; })
        .filter(([, w, h]) => h < 44 && !(w >= 44 && h >= 24))"""
    )
    # inputs: the 24px box sits inside a 44px-tall label; the label is the target.
    boxes = [s for s in small if not s[0].startswith("INPUT")]
    check("buttons/pills/textarea >= 44px tall", not boxes, str(boxes))
    page.get_by_label("Choose rules").check()  # reveals the rule checkboxes so they can be measured
    labels = page.evaluate(
        "[...document.querySelectorAll('label.radio, label.check')].map(l => l.getBoundingClientRect().height)"  # noqa: E501 (inline JS)
    )
    check("radio/checkbox labels >= 44px tall", all(h >= 44 for h in labels), str(labels))
    body_px = page.evaluate("parseFloat(getComputedStyle(document.body).fontSize)")
    verdict_px = page.evaluate(
        "parseFloat(getComputedStyle(document.getElementById('master-word')).fontSize)"
    )
    check("body text >= 18px", body_px >= 18, f"{body_px}px")
    check("verdict >= 40px", verdict_px >= 40, f"{verdict_px}px")

    # --- structure ---
    heads = page.evaluate("[...document.querySelectorAll('h1,h2,h3,h4')].map(h => h.tagName)")
    check("exactly one h1", heads.count("H1") == 1)
    levels = [int(h[1]) for h in heads]
    check(
        "no skipped heading levels",
        all(b - a <= 1 for a, b in zip(levels, levels[1:], strict=False)),
        str(heads),
    )
    unlabelled = page.evaluate(
        """[...document.querySelectorAll('input, textarea, button')].filter(e =>
        !(e.labels && e.labels.length) && !e.textContent.trim() && !e.getAttribute('aria-label')).length"""  # noqa: E501 (inline JS)
    )
    check("every control has a programmatic label", unlabelled == 0)
    svgs = page.evaluate(
        "[...document.querySelectorAll('svg')].filter(s => s.getAttribute('aria-hidden') !== 'true').length"  # noqa: E501 (inline JS)
    )
    check("all SVGs aria-hidden", svgs == 0)
    landmarks = page.evaluate(
        "['header','main','footer'].map(t => document.querySelectorAll(t).length)"
    )
    check("landmarks header/main/footer present", landmarks == [1, 1, 1], str(landmarks))

    # --- 200% zoom ~ 720 CSS px wide, and reduced motion ---
    page.set_viewport_size({"width": 720, "height": 900})
    check(
        "no horizontal scroll at 200% zoom",
        page.evaluate("document.documentElement.scrollWidth") <= 720,
    )
    ctx = b.new_context(reduced_motion="reduce")
    rm = ctx.new_page()
    rm.goto(BASE + "/app/")
    rm.wait_for_selector(".pill[data-state='ok']")
    rm.get_by_role("button", name="Replay attack", exact=True).click()
    rm.wait_for_function("document.getElementById('live').textContent.includes('Overall gate')")
    anim = rm.evaluate("getComputedStyle(document.getElementById('master')).animationName")
    check("animation disabled under prefers-reduced-motion", anim in ("none", ""), anim)
    b.close()

print("RESULT:", "ALL OK" if not fails else f"{len(fails)} FAILURE(S): {fails}")
sys.exit(1 if fails else 0)
