"""Transaction tests against an in-memory device and the real project geometry."""

from copy import deepcopy
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from keyboard_lab import model, validation, workflow
from keyboard_lab.model import read_json


PROJECT = Path(workflow.__file__).resolve().parents[1]
SHIFTED_ALIASES = dict(zip(
    "EXLM AT HASH DLR PERC CIRC AMPR ASTR LPRN RPRN UNDS PLUS LCBR RCBR PIPE TILD".split(),
    "1 2 3 4 5 6 7 8 9 0 MINUS EQUAL LEFT_BRACKET RIGHT_BRACKET BACKSLASH GRAVE".split(),
    strict=True,
))


def fixture_layout():
    """Expand the pinned factory keymap and reproduce the user's live Space change."""
    positions = read_json(PROJECT / "firmware/positions.json")
    ordered_positions = sorted(
        positions.values(), key=lambda pos: (pos["matrix"][0] % 4, pos["x"])
    )
    source = (PROJECT / "firmware/keymaps/adam_vial_trial/keymap.c").read_text()
    layers = re.findall(r"LAYOUT_split_3x6_3_ex2\(([^)]+)\)", source)
    layout = [[[0] * 7 for _ in range(8)] for _ in range(8)]
    assert len(layers) == len(layout)
    for grid, keys in zip(layout, layers, strict=True):
        for position, key in zip(ordered_positions, keys.split(","), strict=True):
            row, col = position["matrix"]
            key = key.strip()
            if key == "XXXXXXX":
                code = 0
            elif key == "_______":
                code = 1
            elif key.startswith("KC_") and key[3:] in SHIFTED_ALIASES:
                code = 0x0200 | model.parse_code("KC_" + SHIFTED_ALIASES[key[3:]])
            else:
                code = model.parse_code(key)
            grid[row][col] = code
    row, col = positions["left.thumb.inner"]["matrix"]
    layout[0][row][col] = 0x292C
    return layout


class SimulatedBoard:
    def __init__(self, layout):
        self.layout = deepcopy(layout)
        self.writes = []
        self.connections = 0
        self.on_write = None
        self.disconnected = False

    def connect(self, expected):
        if self.disconnected:
            raise OSError("USB disconnected")
        self.connections += 1
        return FakeDevice(self, expected)


class FakeDevice:
    def __init__(self, board, expected):
        self.board = board
        self.expected = expected
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.closed = True

    def identity(self):
        return self.expected | {"vial_protocol": 6}

    def read_layout(self):
        if self.closed or self.board.disconnected:
            raise OSError("USB disconnected")
        return deepcopy(self.board.layout)

    def set_key(self, layer, row, col, code):
        if self.closed or self.board.disconnected:
            raise OSError("USB disconnected")
        self.board.layout[layer][row][col] = code
        self.board.writes.append((layer, row, col, code))
        if self.board.on_write:
            self.board.on_write(self.board, len(self.board.writes))


class TransactionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        shutil.copytree(PROJECT / "firmware", self.root / "firmware")
        shutil.copy(PROJECT / "requirements.yaml", self.root)
        self.layout = fixture_layout()
        for module in (model, validation, workflow):
            root_patch = patch.object(module, "ROOT", self.root)
            root_patch.start()
            self.addCleanup(root_patch.stop)

        self.board = SimulatedBoard(self.layout)
        with self.board.connect(workflow.identity()) as device:
            self.baseline = workflow.snapshot(device)
        self.board.connections = 0
        self.edits = [(1, "left.row1.col1", "KC_LEFT"), (1, "left.row1.col2", "KC_DOWN")]

    def candidate(self, edits=None):
        return workflow.make_candidate(
            self.baseline, self.edits if edits is None else edits,
            "Exercise editing without changing the typing layer", ["NAV-01"],
        )

    def apply(self, candidate):
        return workflow.apply_candidate(candidate, device_factory=self.board.connect)

    def completed_transaction(self):
        transaction, = (self.root / "state").glob("transaction-*")
        return transaction, read_json(transaction / "journal.json")

    def test_recovery_after_reconnection(self):
        def disconnect(board, number):
            board.disconnected=True
            raise OSError('disconnected')
        self.board.on_write=disconnect
        with self.assertRaisesRegex(RuntimeError,'rollback-required'):
            self.apply(self.candidate())
        transaction,_=self.completed_transaction()
        self.board.disconnected=False
        self.board.on_write=None
        result=workflow.recover(transaction,device_factory=self.board.connect)
        self.assertEqual(result['status'],'rolled-back')
        self.assertEqual(self.board.layout,self.layout)

    def test_recovery_refuses_unexpected_changes(self):
        def disconnect(board, number):
            board.disconnected=True
            raise OSError('disconnected')
        self.board.on_write=disconnect
        with self.assertRaises(RuntimeError): self.apply(self.candidate())
        transaction,_=self.completed_transaction()
        self.board.disconnected=False
        self.board.on_write=None
        self.board.layout[2][0][0]=0
        writes=len(self.board.writes)
        with self.assertRaisesRegex(RuntimeError,'concurrent'):
            workflow.recover(transaction,device_factory=self.board.connect)
        self.assertEqual(len(self.board.writes),writes)

    def test_persistent_and_special_keycodes_are_rejected(self):
        for code in (0x52e0,0x5700,0x7c00):
            with self.subTest(code=code),self.assertRaises(ValueError):
                self.candidate([(1,'left.row1.col1',str(code))])

    def test_stale_baseline_refuses_all_writes(self):
        candidate = self.candidate()
        self.board.layout[2][0][0] = 0
        with self.assertRaisesRegex(RuntimeError, "baseline"):
            self.apply(candidate)
        self.assertEqual(self.board.writes, [])
        self.assertEqual(list((self.root / "state").glob("transaction-*")), [])

    def test_no_op_checks_live_baseline_without_journaling_or_writing(self):
        result = self.apply(self.candidate(edits=[]))
        self.assertEqual(result["status"], "no-op")
        self.assertEqual(result["snapshot"]["layout"], self.layout)
        self.assertEqual(self.board.connections, 1)
        self.assertEqual(self.board.writes, [])
        self.assertEqual(list((self.root / "state").glob("transaction-*")), [])

    def test_verified_edit_persists_before_and_after(self):
        candidate = self.candidate()
        result = self.apply(candidate)
        transaction, journal = self.completed_transaction()
        self.assertEqual(result["status"], "applied-unaccepted")
        self.assertEqual(read_json(transaction / "before.json")["layout"], self.layout)
        self.assertEqual(read_json(transaction / "after.json")["layout"], self.board.layout)
        self.assertEqual(journal["attempted"], candidate["changes"])
        self.assertEqual(journal["verified"], candidate["changes"])
        self.assertEqual(self.board.layout, candidate["proposed"]["layout"])

    def test_lost_second_ack_rolls_back_verified_and_unverified_writes(self):
        def drop_second_ack(board, write_number):
            if write_number == 2:
                _, journal = self.completed_transaction()
                self.assertEqual(len(journal["attempted"]), 2)
                self.assertEqual(len(journal["verified"]), 1)
                raise OSError("Lost acknowledgement after write")

        self.board.on_write = drop_second_ack
        with self.assertRaisesRegex(RuntimeError, "rolled-back"):
            self.apply(self.candidate())
        _, journal = self.completed_transaction()
        self.assertEqual(journal["status"], "rolled-back")
        self.assertEqual(self.board.connections, 2)
        self.assertEqual(self.board.layout, self.layout)
        self.assertEqual(self.board.writes[2:], [(1, 1, 2, 0), (1, 1, 1, 0)])

    def test_disconnect_preserves_recovery_record(self):
        def disconnect(board, write_number):
            board.disconnected = True
            raise OSError("USB disconnected after write")

        self.board.on_write = disconnect
        with self.assertRaisesRegex(RuntimeError, "rollback-required"):
            self.apply(self.candidate())
        transaction, journal = self.completed_transaction()
        self.assertEqual(journal["status"], "rollback-required")
        self.assertIn("USB disconnected", journal["rollback_error"])
        self.assertEqual(len(journal["attempted"]), 1)
        self.assertEqual(journal["verified"], [])
        self.assertEqual(read_json(transaction / "before.json")["layout"], self.layout)
        self.assertEqual(len(self.board.writes), 1)

    def test_concurrent_edit_refuses_automatic_rollback(self):
        def concurrent_edit(board, write_number):
            if write_number == 1:
                board.layout[2][0][0] = 0
                raise OSError("Lost acknowledgement after concurrent edit")

        self.board.on_write = concurrent_edit
        with self.assertRaisesRegex(RuntimeError, "rollback-required"):
            self.apply(self.candidate())
        _, journal = self.completed_transaction()
        self.assertIn("concurrent edit", journal["rollback_error"])
        self.assertEqual(len(self.board.writes), 1)
        self.assertEqual(self.board.layout[2][0][0], 0)

    def test_unresolved_transaction_blocks_subsequent_write(self):
        transaction = self.root / "state/transaction-interrupted"
        model.save_json(transaction / "journal.json", {"status": "applying"})
        with self.assertRaisesRegex(RuntimeError, "Unresolved transaction"):
            self.apply(self.candidate())
        self.assertEqual(self.board.writes, [])

    def test_failure_to_update_journal_still_attempts_rollback(self):
        def drop_write_ack(board, write_number):
            if write_number == 1:
                raise OSError("Lost acknowledgement after write")

        def fail_first_recovery_record(path, data):
            if data.get("status") == "rollback-required":
                raise OSError("Filesystem write failed")
            model.save_json(path, data)

        self.board.on_write = drop_write_ack
        with patch.object(workflow, "save_json", side_effect=fail_first_recovery_record):
            with self.assertRaisesRegex(RuntimeError, "rolled-back"):
                self.apply(self.candidate())
        _, journal = self.completed_transaction()
        self.assertEqual(self.board.layout, self.layout)
        self.assertEqual(journal["status"], "rolled-back")
        self.assertIn("Filesystem write failed", journal["journal_error"])

    def test_whole_keymap_mismatch_attempts_recovery(self):
        def revert_first_edit(board, write_number):
            if write_number == 2:
                board.layout[1][1][1] = self.layout[1][1][1]

        self.board.on_write = revert_first_edit
        with self.assertRaisesRegex(RuntimeError, "rolled-back"):
            self.apply(self.candidate())
        transaction, journal = self.completed_transaction()
        self.assertIn("Whole-keymap readback differs", journal["failure"])
        self.assertEqual(len(journal["verified"]), 2)
        self.assertFalse((transaction / "after.json").exists())
        self.assertEqual(self.board.layout, self.layout)


if __name__ == "__main__":
    unittest.main()
