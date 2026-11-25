"""Draw the keymap as one SVG: a physical board per layer that has bindings."""
import re
from html import escape

from .keymap import KEYS, LAYER_KEYS, NO, RIGHT, TRANSPARENT, CODES, decode

UNIT, GAP, TITLE = 56, 5, 30
BOARD_W, BOARD_H = 15 * UNIT, 4.7 * UNIT
STAGGER = [0.3, 0.3, 0.1, 0, 0.1, 0.2, 0.7]


def _geometry():
    """(x, y, height) in key units, in file order."""
    keys = []
    for row, width in ((0, 7), (1, 7), (2, 6)):
        keys += [(c, row + STAGGER[c], 1) for c in range(width)]
        keys += [(14 - c, row + STAGGER[c], 1) for c in reversed(range(width))]
    return keys + [(4, 3.7, 1), (5, 3.7, 1), (6, 3.2, 1.5), (8, 3.2, 1.5), (9, 3.7, 1), (10, 3.7, 1)]


GEOMETRY = _geometry()
assert len(GEOMETRY) == KEYS

WORDS = {
    "SPC": "Space", "ENT": "Enter", "BSPC": "⌫", "DEL": "⌦", "TAB": "Tab", "ESC": "Esc",
    "LEFT": "←", "DOWN": "↓", "UP": "↑", "RGHT": "→",
    "LCTL": "Ctrl", "RCTL": "Ctrl", "LSFT": "Shift", "RSFT": "Shift",
    "LALT": "Opt", "RALT": "Opt", "LGUI": "Cmd", "RGUI": "Cmd",
    "COMM": ",", "DOT": ".", "SLSH": "/", "SCLN": ";", "QUOT": "'", "MINS": "-", "EQL": "=",
    "LBRC": "[", "RBRC": "]", "BSLS": "\\", "GRV": "`",
}
SHIFT = dict(zip("1234567890-=[]\\;',./`", "!@#$%^&*()_+{}|:\"<>?~"))
LAYER_VERBS = {"TO": "go to", "MO": "hold", "DF": "default", "TG": "toggle", "OSL": "one-shot", "TT": "tap-toggle"}
# Tri-layer keys reach layers 1 and 2 under the firmware's default tri-layer settings.
TRI = {CODES["TL_LOWR"]: 1, CODES["TL_UPPR"]: 2}


def _mods(mask):
    return "".join(sign for bit, sign in ((1, "⌃"), (4, "⌥"), (2, "⇧"), (8, "⌘")) if mask & bit)


def _plain(code):
    name = decode(code)
    name = name[3:] if name.startswith(("KC_", "QK_")) else name
    return WORDS.get(name, name)


def legend(code):
    """Keycode -> (what a tap does, what a hold or mode does)."""
    low, high = code & 0xFF, code >> 8
    if code in (NO, TRANSPARENT):
        return "", ""
    if code in TRI:
        return f"L{TRI[code]}", "hold"
    if 0x0100 <= code <= 0x1FFF:
        key = _plain(low)
        if high & 0x0F == 0x02 and key in SHIFT:
            return SHIFT[key], ""
        return _mods(high) + key, ""
    if 0x2000 <= code <= 0x3FFF:
        return _plain(low), _mods(high)
    if 0x4000 <= code <= 0x4FFF:
        return _plain(low), f"L{high & 0x0F}"
    if 0x5000 <= code <= 0x51FF:
        return f"L{code >> 5 & 0x0F}", _mods(code)
    if 0x52A0 <= code <= 0x52BF:
        return _mods(code), "one-shot"
    for name, base in LAYER_KEYS.items():
        if base <= code < base + 32:
            return f"L{code - base}", LAYER_VERBS[name]
    return _plain(code), ""


def _board(layer, base):
    parts = []
    for index, (x, y, height) in enumerate(GEOMETRY):
        code = layer[index]
        inherited = code == TRANSPARENT
        tap, hold = legend(base[index] if inherited else code)
        if inherited or code == NO:
            kind = "inherit" if inherited else "none"
        else:
            kind = "layer" if re.fullmatch(r"L\d+", tap) or re.fullmatch(r"L\d+", hold) else "key"
        px, py, w, h = x * UNIT, y * UNIT, UNIT - GAP, height * UNIT - GAP
        box = f'x="{px:.0f}" y="{py:.0f}" width="{w}" height="{h:.0f}"'
        parts.append(f'<g class="{kind}"><rect {box} rx="7"/>')
        size = 20 if len(tap) <= 2 else 14 if len(tap) <= 5 else 10
        middle = py + h / 2 + (0 if hold else 6)
        parts.append(f'<text x="{px + w / 2:.0f}" y="{middle:.0f}" font-size="{size}">{escape(tap)}</text>')
        if hold:
            low = f'x="{px + w / 2:.0f}" y="{py + h - 8:.0f}"'
            parts.append(f'<text class="hold" {low} font-size="11">{escape(hold)}</text>')
        parts.append("</g>")
    return "".join(parts)


def svg(layout, titles, note):
    """layout: eight lists of 46 codes. Layers with no bindings of their own are skipped."""
    shown = [n for n, layer in enumerate(layout) if set(layer) - {NO, TRANSPARENT}]
    columns = 2 if len(shown) > 1 else 1
    cell_w, cell_h = BOARD_W + 40, BOARD_H + TITLE + 30
    width, height = columns * cell_w + 20, -(-len(shown) // columns) * cell_h + 50
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height:.0f}" '
        'font-family="-apple-system, Helvetica Neue, sans-serif" text-anchor="middle">',
        "<style>.bg{fill:#12161c}.key rect{fill:#27313d}.layer rect{fill:#1f4a6b}"
        ".inherit rect,.none rect{fill:#1a2029}text{fill:#edf1f5}.inherit text{fill:#566373}"
        ".hold{fill:#7cc4ff}.title{fill:#9fb0c2;font-size:17px;font-weight:600;text-anchor:start}"
        ".note{fill:#6b7a8c;font-size:13px;text-anchor:start}</style>",
        f'<rect class="bg" width="{width}" height="{height:.0f}" rx="18"/>',
    ]
    for slot, n in enumerate(shown):
        x, y = 30 + slot % columns * cell_w, 20 + slot // columns * cell_h
        title = f"Layer {n}" + (f" · {titles[n]}" if titles.get(n) else "")
        out.append(f'<text class="title" x="{x}" y="{y + 18}">{escape(title)}</text>')
        out.append(f'<g transform="translate({x},{y + TITLE})">{_board(layout[n], layout[0])}</g>')
    out.append(f'<text class="note" x="30" y="{height - 16:.0f}">{escape(note)}</text></svg>')
    return "".join(out)
