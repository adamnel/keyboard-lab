import tempfile
import unittest
from pathlib import Path

from keyboard_lab import cli
from keyboard_lab.keymap import KEYS, LAYERS, ORDER, ROOT, TRANSPARENT
from keyboard_lab.keymap import codes, decode, encode, format_layer, from_matrix, parse, pin_violations, update
from keyboard_lab.render import GEOMETRY, legend, svg

KEYMAP = (ROOT / "keymap.txt").read_text()
PINNED = (ROOT / "pinned.txt").read_text()


class Keyboard:
    """Stands in for VialDevice: a matrix that records writes."""

    def __init__(self, layout, ignore_writes=False):
        self.matrix = [[[0] * 7 for _ in range(8)] for _ in range(LAYERS)]
        for n, layer in enumerate(layout):
            for (row, col), code in zip(ORDER, layer):
                self.matrix[n][row][col] = code
        self.writes, self.ignore_writes = [], ignore_writes

    def read_layout(self):
        return [[list(row) for row in layer] for layer in self.matrix]

    def set_key(self, layer, row, col, code):
        self.writes.append((layer, row, col, code))
        if not self.ignore_writes:
            self.matrix[layer][row][col] = code


class Keycodes(unittest.TestCase):
    def test_every_keycode_survives_a_round_trip_through_its_name(self):
        self.assertEqual([c for c in range(0x10000) if encode(decode(c)) != c], [])

    def test_expressions(self):
        for text, code in {
            "MT(MOD_LCTL | MOD_LGUI, KC_SPC)": 0x292C, "LT(1,KC_ESC)": 0x4129, "MO(2)": 0x5222,
            "LGUI(LSFT(KC_4))": 0x0A21, "KC_EXLM": 0x021E, "RALT(KC_E)": 0x1408,
            "MT(MOD_HYPR,KC_ESC)": 0x2F29, "OSM(MOD_LSFT)": 0x52A2, "0x7c77": 0x7C77,
        }.items():
            self.assertEqual(encode(text), code, text)

    def test_rejects_what_the_firmware_cannot_express(self):
        for text in ("KC_NOPE", "MO(8)", "LT(1,MO(2))", "MT(MOD_LCTL|MOD_RSFT,KC_A)", "LCTL(RSFT(KC_A))", "44"):
            with self.assertRaises(ValueError, msg=text):
                encode(text)


class KeymapFile(unittest.TestCase):
    def test_tracked_keymap_parses_and_keeps_pinned_decisions(self):
        layout = codes(KEYMAP)
        self.assertEqual((len(layout), {len(layer) for layer in layout}), (LAYERS, {KEYS}))
        self.assertEqual(pin_violations(layout, PINNED), [])

    def test_matrix_order_covers_46_distinct_switches(self):
        self.assertEqual((len(ORDER), len(set(ORDER)), len(GEOMETRY)), (KEYS, KEYS, KEYS))

    def test_omitted_layer_is_transparent_and_errors_name_the_line(self):
        self.assertEqual(codes(KEYMAP)[7], [TRANSPARENT] * KEYS)
        with self.assertRaisesRegex(ValueError, "line 2: Unknown keycode: KC_NOPE"):
            codes("layer 0\nKC_NOPE")
        with self.assertRaisesRegex(ValueError, "has 1 keys"):
            codes("layer 0\nKC_A")

    def test_pin_violation_names_the_place_in_the_file(self):
        layout = codes(KEYMAP)
        layout[0][1] = encode("KC_X")
        self.assertEqual(pin_violations(layout, PINNED), ["layer 0 row 1 key 2: pinned to KC_Q, keymap has KC_X"])

    def test_update_rewrites_only_changed_words_and_appends_new_layers(self):
        device = codes(KEYMAP)
        device[0][0] = encode("LT(1,KC_ESC)")
        device[5] = [encode("KC_F1")] * KEYS
        text = update(KEYMAP, device)
        self.assertEqual(codes(text), device)
        self.assertIn("# Corne 4.1 bindings", text)
        self.assertIn("layer 1  # numbers and arrows", text)
        self.assertEqual(update("", device).count("layer "), 5)

    def test_formatted_layer_parses_back(self):
        layout = codes(KEYMAP)
        self.assertEqual(parse(format_layer(0, layout[0]))[0][0][5][0], layout[0][5])


class Apply(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.undo = Path(folder.name) / "state/before-apply.txt"
        self.have = codes(KEYMAP)
        self.want = codes(KEYMAP)
        self.want[1][15] = encode("KC_HOME")

    def test_writes_only_the_difference_and_leaves_an_undo_file(self):
        keyboard = Keyboard(self.have)
        delta = cli.apply(keyboard, self.want, self.undo)
        self.assertEqual(keyboard.writes, [(1, 1, 1, encode("KC_HOME"))])
        self.assertEqual(cli.describe(delta), ["layer 1 row 2 key 2: XXXXXXX -> KC_HOME"])
        self.assertEqual(from_matrix(keyboard.read_layout()), self.want)
        self.assertEqual(codes(self.undo.read_text()), self.have)

    def test_matching_keyboard_is_left_alone(self):
        keyboard = Keyboard(self.have)
        self.assertEqual(cli.apply(keyboard, self.have, self.undo), [])
        self.assertEqual((keyboard.writes, self.undo.exists()), ([], False))

    def test_refuses_bootloader_key_before_writing_anything(self):
        self.want[0][0] = encode("QK_BOOT")
        keyboard = Keyboard(self.have)
        with self.assertRaisesRegex(ValueError, "Bootloader"):
            cli.apply(keyboard, self.want, self.undo)
        self.assertEqual(keyboard.writes, [])

    def test_reports_a_keyboard_that_did_not_take_the_write(self):
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            cli.apply(Keyboard(self.have, ignore_writes=True), self.want, self.undo)

    def test_checked_refuses_a_keymap_that_breaks_a_pin(self):
        with self.assertRaisesRegex(ValueError, "pinned to KC_Q"):
            cli.checked(KEYMAP.replace("KC_Q ", "KC_F1", 1))


class Picture(unittest.TestCase):
    def test_legends(self):
        for text, expected in {
            "MT(MOD_LCTL|MOD_LGUI,KC_SPC)": ("Space", "⌃⌘"), "KC_EXLM": ("!", ""), "LT(1,KC_ESC)": ("Esc", "L1"),
            "MO(2)": ("L2", "hold"), "LGUI(KC_C)": ("⌘C", ""), "TL_LOWR": ("L1", "hold"), "_______": ("", ""),
        }.items():
            self.assertEqual(legend(encode(text)), expected, text)

    def test_draws_one_board_per_layer_with_bindings(self):
        picture = svg(codes(KEYMAP), parse(KEYMAP)[1], "note")
        self.assertEqual(picture.count('class="title"'), 4)
        self.assertIn("Layer 2 · symbols", picture)
