"""keymap.txt <-> 16-bit keycodes. The text file is the source of truth for bindings."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS, KEYS = 8, 46
NO, TRANSPARENT = 0, 1

# File order (LAYOUT_split_3x6_3_ex2) -> matrix (row, col). Right-half columns count from the outside.
ROWS = [
    [(0, c) for c in range(7)] + [(4, c) for c in range(6, -1, -1)],
    [(1, c) for c in range(7)] + [(5, c) for c in range(6, -1, -1)],
    [(2, c) for c in range(6)] + [(6, c) for c in range(5, -1, -1)],
    [(3, 3), (3, 4), (3, 5), (7, 5), (7, 4), (7, 3)],
]
ORDER = [cell for row in ROWS for cell in row]

MODS = {"CTL": 0x01, "SFT": 0x02, "ALT": 0x04, "GUI": 0x08}
RIGHT = 0x10
LAYER_KEYS = {"TO": 0x5200, "MO": 0x5220, "DF": 0x5240, "TG": 0x5260, "OSL": 0x5280, "TT": 0x52C0}
PREFERRED = ("XXXXXXX", "_______", "KC_LGUI", "KC_RGUI", "KC_LALT", "KC_RALT")
SHIFTED = {
    "KC_EXLM": "KC_1", "KC_AT": "KC_2", "KC_HASH": "KC_3", "KC_DLR": "KC_4", "KC_PERC": "KC_5",
    "KC_CIRC": "KC_6", "KC_AMPR": "KC_7", "KC_ASTR": "KC_8", "KC_LPRN": "KC_9", "KC_RPRN": "KC_0",
    "KC_UNDS": "KC_MINS", "KC_PLUS": "KC_EQL", "KC_LCBR": "KC_LBRC", "KC_RCBR": "KC_RBRC",
    "KC_PIPE": "KC_BSLS", "KC_COLN": "KC_SCLN", "KC_DQUO": "KC_QUOT", "KC_TILD": "KC_GRV",
    "KC_LT": "KC_COMM", "KC_GT": "KC_DOT", "KC_QUES": "KC_SLSH",
}


def _tables():
    codes = json.loads((ROOT / "firmware/keycodes.json").read_text())
    codes.update({name: 0x0200 | codes[base] for name, base in SHIFTED.items()})
    names = {}
    for name, code in codes.items():
        # Composite ranges are written structurally; range markers are not keys.
        structural = 0x0100 <= code <= 0x52FF and name not in SHIFTED
        if structural or name.endswith("_MAX"):
            continue
        if code not in names or (len(name), name) < (len(names[code]), names[code]):
            names[code] = name
    names.update({codes[name]: name for name in PREFERRED})
    return codes, names


CODES, NAMES = _tables()


def _mods(text):
    """MOD_LCTL|MOD_LGUI -> five-bit modifier mask."""
    mask = 0
    for part in text.split("|"):
        found = re.fullmatch(r"MOD_(?:([LR])(CTL|SFT|ALT|GUI)|(HYPR|MEH))", part)
        if not found:
            raise ValueError(f"Unknown modifier: {part}")
        if found[3]:
            bits = 0x0F if found[3] == "HYPR" else 0x07
        else:
            bits = MODS[found[2]] | (RIGHT if found[1] == "R" else 0)
        if mask and (mask ^ bits) & RIGHT:
            raise ValueError("Left and right modifiers cannot be mixed in one key")
        mask |= bits
    return mask


def _mod_names(mask):
    side = "R" if mask & RIGHT else "L"
    return "|".join(f"MOD_{side}{name}" for name, bit in MODS.items() if mask & bit)


def _split(args):
    parts, depth, start = [], 0, 0
    for index, char in enumerate(args):
        depth += (char == "(") - (char == ")")
        if char == "," and depth == 0:
            parts.append(args[start:index])
            start = index + 1
    return parts + [args[start:]]


def _layer(text, limit=LAYERS):
    if not text.isdigit() or int(text) >= limit:
        raise ValueError(f"Layer must be 0-{limit - 1}: {text}")
    return int(text)


def _basic(text):
    code = encode(text)
    if code > 0xFF:
        raise ValueError(f"Tap key must be a basic keycode: {text}")
    return code


def encode(text):
    """Key name or expression -> keycode."""
    text = re.sub(r"\s+", "", text)
    if text in CODES:
        return CODES[text]
    if re.fullmatch(r"0x[0-9a-fA-F]{1,4}", text):
        return int(text, 16)
    call = re.fullmatch(r"(\w+)\((.*)\)", text)
    if not call:
        raise ValueError(f"Unknown keycode: {text}")
    name, args = call[1], _split(call[2])
    wrapper = re.fullmatch(r"([LR])(CTL|SFT|ALT|GUI)", name)
    if wrapper and len(args) == 1:
        inner = encode(args[0])
        mask = MODS[wrapper[2]] | (RIGHT if wrapper[1] == "R" else 0)
        if inner > 0x1FFF or (inner >> 8 and (inner >> 8 ^ mask) & RIGHT):
            raise ValueError(f"Cannot apply {name} to {args[0]}")
        return inner | mask << 8
    if name in LAYER_KEYS and len(args) == 1:
        return LAYER_KEYS[name] | _layer(args[0])
    if name == "MT" and len(args) == 2:
        return 0x2000 | _mods(args[0]) << 8 | _basic(args[1])
    if name == "LT" and len(args) == 2:
        return 0x4000 | _layer(args[0]) << 8 | _basic(args[1])
    if name == "LM" and len(args) == 2:
        return 0x5000 | _layer(args[0]) << 5 | _mods(args[1])
    if name == "OSM" and len(args) == 1:
        return 0x52A0 | _mods(args[0])
    raise ValueError(f"Unknown keycode: {text}")


def decode(code):
    """Keycode -> the shortest name encode() accepts; hex when nothing fits."""
    if code in NAMES:
        return NAMES[code]
    low, high = code & 0xFF, code >> 8
    if 0x0100 <= code <= 0x1FFF and high & 0x0F:
        side, text = "R" if high & RIGHT else "L", decode(low)
        for name, bit in reversed(MODS.items()):
            if high & bit:
                text = f"{side}{name}({text})"
        return text
    if 0x2000 <= code <= 0x3FFF and high & 0x0F:
        return f"MT({_mod_names(high & 0x1F)},{decode(low)})"
    if 0x4000 <= code <= 0x4FFF and (high & 0x0F) < LAYERS:
        return f"LT({high & 0x0F},{decode(low)})"
    if 0x5000 <= code <= 0x51FF and (code >> 5 & 0x0F) < LAYERS and code & 0x0F:
        return f"LM({code >> 5 & 0x0F},{_mod_names(code & 0x1F)})"
    if 0x52A0 <= code <= 0x52BF and code & 0x0F:
        return f"OSM({_mod_names(code & 0x1F)})"
    for name, base in LAYER_KEYS.items():
        if base <= code < base + LAYERS:
            return f"{name}({code - base})"
    return f"0x{code:04x}"


def parse(text, wildcard=False):
    """Text -> ({layer: [(code, start, end), ...]}, {layer: title}).

    Offsets locate each key in the text. With wildcard, `*` parses to None.
    """
    layers, titles, current, offset = {}, {}, None, 0
    for number, raw in enumerate(text.splitlines(keepends=True), 1):
        line, _, comment = raw.partition("#")
        header = re.fullmatch(r"\s*layer\s+(\d+)\s*", line)
        try:
            if header:
                current = _layer(header[1])
                if current in layers:
                    raise ValueError(f"Layer {current} appears twice")
                layers[current], titles[current] = [], comment.strip()
            else:
                depth, start = 0, None
                for index, char in enumerate(line + " "):
                    depth += (char == "(") - (char == ")")
                    if not char.isspace() or depth > 0:
                        start = index if start is None else start
                    elif start is not None:
                        if current is None:
                            raise ValueError("Key before the first `layer N` line")
                        word = line[start:index]
                        code = None if wildcard and word == "*" else encode(word)
                        layers[current].append((code, offset + start, offset + index))
                        start = None
        except ValueError as error:
            raise ValueError(f"line {number}: {error}") from None
        offset += len(raw)
    for layer, keys in layers.items():
        if len(keys) != KEYS:
            raise ValueError(f"Layer {layer} has {len(keys)} keys, expected {KEYS}")
    return layers, titles


def codes(text):
    """Text -> eight lists of 46 keycodes. A layer left out of the file is fully transparent."""
    layers, _ = parse(text)
    return [[code for code, _, _ in layers[n]] if n in layers else [TRANSPARENT] * KEYS for n in range(LAYERS)]


def from_matrix(layout):
    """Device [layer][row][col] -> eight lists in file order."""
    return [[layer[row][col] for row, col in ORDER] for layer in layout]


def format_layer(number, layer, title=""):
    words = iter(decode(code).ljust(7) for code in layer)
    blank = " " * 7

    def take(count):
        return [next(words) for _ in range(count)]

    lines = [
        take(7) + [""] + take(7),
        take(7) + [""] + take(7),
        take(6) + [blank, "", blank] + take(6),
        [blank] * 4 + take(3) + [""] + take(3),
    ]
    head = f"layer {number}" + (f"  # {title}" if title else "")
    return head + "\n" + "".join(" ".join(line).rstrip() + "\n" for line in lines)


def update(text, device):
    """Rewrite the bindings in text to match device codes, leaving comments and spacing alone."""
    layers, _ = parse(text)
    edits = [
        (start, end, decode(device[n][index]))
        for n, keys in layers.items()
        for index, (code, start, end) in enumerate(keys)
        if code != device[n][index]
    ]
    for start, end, word in sorted(edits, reverse=True):
        text = text[:start] + word + text[end:]
    for n in range(LAYERS):
        if n not in layers and set(device[n]) != {TRANSPARENT}:
            text = text.rstrip("\n") + "\n\n" + format_layer(n, device[n])
    return text


def position(layer, index):
    """Where a key sits in keymap.txt: its layer, then line and word within the block."""
    for row, cells in enumerate(ROWS, 1):
        if index < len(cells):
            return f"layer {layer} row {row} key {index + 1}"
        index -= len(cells)


def pin_violations(layout, pinned_text):
    pinned, _ = parse(pinned_text, wildcard=True)
    return [
        f"{position(n, index)}: pinned to {decode(code)}, keymap has {decode(layout[n][index])}"
        for n, keys in pinned.items()
        for index, (code, _, _) in enumerate(keys)
        if code is not None and code != layout[n][index]
    ]
