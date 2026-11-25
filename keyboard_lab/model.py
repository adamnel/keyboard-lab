"""Pure data model: explicit numeric keymap snapshots, never firmware defaults."""
import os
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read_json(path):
    return json.loads(Path(path).read_text())

def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def save_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w") as f:
        f.write(json.dumps(data, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(p)
    fd = os.open(p.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def parse_code(text):
    codes = read_json(ROOT / "firmware/keycodes.json")
    aliases = {"KC_SPC": "KC_SPACE", "KC_TRNS": "KC_TRANSPARENT", "KC_LCTL": "KC_LEFT_CTRL", "KC_LGUI": "KC_LEFT_GUI", "TL_LOWR": "QK_TRI_LAYER_LOWER", "TL_UPPR": "QK_TRI_LAYER_UPPER"}
    text = text.strip()
    if text in codes:
        return codes[text]
    if text in aliases:
        return codes[aliases[text]]
    if re.fullmatch(r"0x[0-9a-fA-F]{1,4}|[0-9]{1,5}", text):
        n = int(text, 16 if text.startswith("0x") else 10)
        if 0 <= n <= 65535:
            return n
    mt = re.fullmatch(r"MT\(([^,]+),\s*(\w+)\)", text)
    if mt:
        flags = {"MOD_LCTL": 1, "MOD_LSFT": 2, "MOD_LALT": 4, "MOD_LGUI": 8}
        parts = [s.strip() for s in mt[1].split("|")]
        if not parts or any(s not in flags for s in parts):
            raise ValueError("Only explicit left-hand mod-tap flags supported")
        mods = 0
        for p in parts:
            mods |= flags[p]
        tap = parse_code(mt[2])
        if tap > 255:
            raise ValueError("Mod-tap tap key must be basic")
        return 0x2000 | (mods << 8) | tap
    raise ValueError(f"Unsupported keycode expression: {text}. Use a verified name or 16-bit numeric value.")

def changes(before, after):
    return [{"layer": l, "row": r, "col": c, "before": x, "after": after[l][r][c]}
            for l, layer in enumerate(before) for r, row in enumerate(layer)
            for c, x in enumerate(row) if x != after[l][r][c]]

def shape(layout):
    return (isinstance(layout, list) and len(layout) == 8 and
            all(isinstance(layer, list) and len(layer) == 8 and
                all(isinstance(row, list) and len(row) == 7 and
                    all(type(k) is int and 0 <= k <= 65535 for k in row)
                    for row in layer) for layer in layout))
