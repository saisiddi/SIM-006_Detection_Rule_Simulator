# SIM-006 demo UI: design tokens

Direction: flight-deck annunciator. A dark instrument panel where **lamps carry meaning**. Mode: Operate (a tool being demonstrated live, projected in a room).

## Rules that never bend
- **Amber means WARN and nothing else.** The accent/chrome colour is a warm neutral.
- Status is always **icon + word + colour**. Colour is never the only signal.
- PASS, WARN and HARD FAIL differ in **lightness**, not just hue (fills: dark green, bright amber, deep red).
- Failures are "lit" (full-fill lamps); passes are "dim" (tinted, calm). The eye finds the problem first.
- Motion: one authored moment, a lamp power-on, at most 300 ms. Disabled under `prefers-reduced-motion`.

## Colour
| Token | Hex | Use |
|---|---|---|
| `--ground` | `#0E0F11` | page |
| `--panel` | `#16181B` | panels |
| `--panel-2` | `#1D2024` | inset surfaces, standby lamps |
| `--hair` | `#2A2D32` | decorative dividers only |
| `--edge` | `#7A7F87` | control borders (3:1+ vs ground) |
| `--ink` | `#E8E4DA` | text, accent, focus ring, primary button |
| `--ink-2` | `#B4B0A6` | secondary text |
| `--pass` | `#22A862` / text `#04140B` | PASS fill |
| `--pass-dim` | `#0F2417` / text `#6EE7A4` | PASS lamp in a list |
| `--warn` | `#FFB000` / text `#1A1200` | WARN fill |
| `--fail` | `#C92A21` / text `#FFFFFF` | HARD FAIL fill |

Contrast for every pair is computed in `scripts/contrast_check.py` (run it; it fails below 4.5:1 for text, 3:1 for UI parts and large text).

## Type
- **Barlow Condensed** 600/700: headings, lamp labels, verdict only.
- **Barlow** 400/500/600: body, minimum **18 px**.
- **JetBrains Mono** 400/500: JSON and rule IDs.
- All files self-hosted in `frontend/fonts/` (SIL OFL 1.1, licences alongside). No external requests.
- Scale: verdict `clamp(40px, 6vw, 72px)`, h2 28 px, lamp name 20 px, body 18 px, mono 16 px.

## Space, shape
- 8 px base: 8 / 16 / 24 / 32 / 48. Panels padded 24. Radius: 4 (controls, lamps), 8 (panels).
- Touch targets ≥ 44 × 44 px. Focus ring: 3 px `--ink`, 2 px offset.

## Motion
- `lamp-on`: opacity 0.6→1 and brightness 1.6→1, 240 ms, `cubic-bezier(.2,.8,.2,1)`. Used on the master lamp and on each rule lamp when a result arrives.
- Nothing loops.
