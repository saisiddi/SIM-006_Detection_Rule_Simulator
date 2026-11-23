"""WCAG 2.2 contrast check for the demo UI tokens (frontend/app.css).

Reads the real colours from the stylesheet's :root block, so it cannot drift from the CSS.
Text pairs must reach 4.5:1; large text and UI components 3:1. Exits 1 on any failure.
"""

import re
import sys
from pathlib import Path

CSS = (Path(__file__).resolve().parent.parent / "frontend" / "app.css").read_text()
T = dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", CSS))


def lum(hex_: str) -> float:
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (label, foreground token/hex, background token/hex, minimum)
PAIRS = [
    ("body text on page", "ink", "ground", 4.5),
    ("body text on panel", "ink", "panel", 4.5),
    ("secondary text on panel", "ink-2", "panel", 4.5),
    ("secondary text on inset", "ink-2", "panel-2", 4.5),
    ("PASS lamp: chip text", "on-pass", "pass", 4.5),
    ("PASS lamp: detail text on dim fill", "#C9D9CF", "pass-dim", 4.5),
    ("PASS lamp: ink on dim fill", "ink", "pass-dim", 4.5),
    ("PASS pill text", "pass-ink", "panel", 4.5),
    ("WARN lamp: text on amber", "on-warn", "warn", 4.5),
    ("FAIL lamp: text on red", "on-fail", "fail", 4.5),
    ("FAIL pill text", "#FF9A92", "panel", 4.5),
    ("error text on error box", "#FFB3AC", "#2A1210", 4.5),
    ("standby master text", "ink-2", "panel-2", 4.5),
    ("primary button text", "ground", "ink", 4.5),
    ("pressed scenario text", "ground", "ink", 4.5),
    ("control border vs panel (UI part)", "edge", "panel", 3.0),
    ("control border vs ground (UI part)", "edge", "ground", 3.0),
    ("focus ring vs ground (UI part)", "ink", "ground", 3.0),
    ("focus ring vs panel (UI part)", "ink", "panel", 3.0),
]
LIGHTNESS = [("pass", "warn", "fail")]


def get(x: str) -> str:
    return x if x.startswith("#") else T[x]


bad = 0
for label, fg, bg, need in PAIRS:
    r = ratio(get(fg), get(bg))
    ok = r >= need
    bad += 0 if ok else 1
    print(f"{'OK ' if ok else 'BAD'} {r:5.2f}:1 (need {need}) {label}")
for names in LIGHTNESS:
    ls = {n: round(lum(T[n]), 3) for n in names}
    spread = max(ls.values()) / max(min(ls.values()), 0.001)
    print(f"lightness (relative luminance) {ls}")
    distinct = all(abs(ls[a] - ls[b]) >= 0.08 for a in names for b in names if a < b)
    bad += 0 if distinct else 1
    print(f"{'OK ' if distinct else 'BAD'} status fills differ in lightness by >= 0.08 pairwise")
print("RESULT:", "ALL OK" if bad == 0 else f"{bad} FAILURE(S)")
sys.exit(1 if bad else 0)
