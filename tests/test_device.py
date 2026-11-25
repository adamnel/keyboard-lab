import json
import lzma
import struct
import sys
import unittest
from unittest.mock import patch

from keyboard_lab.device import DeviceError, VialDevice, descriptor_sha256


DEFINITION = {"vendorId": "0x4653", "productId": "0x0004", "matrix": {"rows": 8, "cols": 7}}
UID = bytes.fromhex("4cf5a7243901b58e")
EXPECTED = {
    "vid": 0x4653,
    "pid": 0x0004,
    "usage_page": 0xFF60,
    "usage": 0x61,
    "layers": 8,
    "rows": 8,
    "cols": 7,
    "vial_uid": UID.hex(),
    "descriptor_sha256": descriptor_sha256(DEFINITION),
}


class RawHID:
    def __init__(self):
        self.interface = {
            "vendor_id": EXPECTED["vid"],
            "product_id": EXPECTED["pid"],
            "usage_page": 0xFF60,
            "usage": 0x61,
            "path": b"raw-hid",
        }
        self.interfaces = [dict(self.interface, usage=6), self.interface]
        self.definition = lzma.compress(json.dumps(DEFINITION, indent=2).encode("utf-8"))
        self.codes = [0x100 + index for index in range(8 * 8 * 7)]
        self.uid = UID
        self.protocol = 6
        self.unlocking = False
        self.drop_reads = False
        self.ignore_set = False
        self.bad_echo = False
        self.closed = False
        self.commands = []

    def enumerate(self, vid, pid):
        assert (vid, pid) == (EXPECTED["vid"], EXPECTED["pid"])
        return self.interfaces

    def Device(self, path):
        assert path == self.interface["path"]
        return self

    def close(self):
        self.closed = True

    def write(self, data):
        assert len(data) == 33 and data[0] == 0
        self.commands.append(data[1:])
        return len(data)

    def read(self, size, timeout):
        assert size == 33 and timeout > 0
        if self.drop_reads:
            return b""
        request = self.commands[-1]
        command = request[0]
        if command == 0xFE:
            match request[1]:
                case 0:
                    return (self.protocol.to_bytes(4, "little") + self.uid).ljust(32, b"\0")
                case 1:
                    return len(self.definition).to_bytes(4, "little").ljust(32, b"\0")
                case 2:
                    page = int.from_bytes(request[2:4], "little")
                    data = self.definition[page * 32:(page + 1) * 32]
                    return data + request[len(data):]
                case 5:
                    return bytes((0, self.unlocking)) + b"\xff" * 30
                case _:
                    raise AssertionError(f"Unexpected Vial command {request[1]}")
        if command == 0x11:
            return bytes((command, 8)).ljust(32, b"\0")
        if command == 0x12:
            offset = int.from_bytes(request[1:3], "big")
            data = struct.pack(f">{len(self.codes)}H", *self.codes)
            return (request[:4] + data[offset:offset + request[3]]).ljust(32, b"\0")
        layer, row, col = request[1:4]
        index = (layer * 8 + row) * 7 + col
        if command == 0x04:
            return request[:4] + self.codes[index].to_bytes(2, "big") + request[6:]
        if command == 0x05:
            if not self.ignore_set:
                self.codes[index] = int.from_bytes(request[4:6], "big")
            return request[:-1] + b"\xff" if self.bad_echo else request
        raise AssertionError(f"Unexpected VIA command {command}")


class DeviceTests(unittest.TestCase):
    def setUp(self):
        self.hid = RawHID()
        imports = patch.dict(sys.modules, {"hid": self.hid})
        imports.start()
        self.addCleanup(imports.stop)

    def test_verified_identity_and_all_layers(self):
        with VialDevice(EXPECTED) as device:
            self.assertEqual(device.identity(), EXPECTED | {"vial_protocol": 6})
            layout = device.read_layout()
            self.assertEqual((len(layout), len(layout[0]), len(layout[0][0])), (8, 8, 7))
            self.assertEqual(
                [code for layer in layout for row in layer for code in row], self.hid.codes
            )
        self.assertTrue(self.hid.closed)

    def test_serializes_key_and_requires_readback(self):
        with VialDevice(EXPECTED) as device:
            device.set_key(7, 7, 6, 0x1234)
            self.assertEqual(device.read_layout()[7][7][6], 0x1234)
            self.assertIn(bytes((5, 7, 7, 6, 0x12, 0x34)) + b"\0" * 26, self.hid.commands)
            self.hid.ignore_set = True
            with self.assertRaisesRegex(DeviceError, "observed 0x1234"):
                device.set_key(7, 7, 6, 0xABCD)

    def test_refuses_partial_echo(self):
        with VialDevice(EXPECTED) as device:
            self.hid.bad_echo = True
            with self.assertRaisesRegex(DeviceError, "did not echo"):
                device.set_key(0, 0, 0, 4)
            self.assertTrue(self.hid.closed)

    def test_rejects_ambiguous_interfaces(self):
        self.hid.interfaces.append(dict(self.hid.interface, path=b"other-device"))
        with self.assertRaisesRegex(DeviceError, "found 2"):
            with VialDevice(EXPECTED):
                self.fail("The ambiguous device should not open.")
        self.assertEqual(self.hid.commands, [])

    def test_rejects_identity_mismatches(self):
        for identity, message in (
            (EXPECTED | {"vial_uid": "bad"}, "UID mismatch"),
            (EXPECTED | {"descriptor_sha256": "bad"}, "definition SHA-256 mismatch"),
            (EXPECTED | {"layers": 4}, "layers mismatch"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(DeviceError, message):
                    with VialDevice(identity):
                        self.fail("A device with the wrong identity should not open.")
                self.assertTrue(self.hid.closed)

    def test_rejects_unknown_protocol(self):
        self.hid.protocol = 7
        with self.assertRaisesRegex(DeviceError, "Unsupported Vial protocol 7"):
            with VialDevice(EXPECTED):
                self.fail("An unsupported device should not open.")

    def test_validates_before_sending_a_key_write(self):
        with VialDevice(EXPECTED) as device:
            for coordinates in ((True, 0, 0), (8, 0, 0), (0, 8, 0), (0, 0, 7)):
                with self.assertRaises(ValueError):
                    device.set_key(*coordinates, 4)
            with self.assertRaises(ValueError):
                device.set_key(0, 0, 0, 65536)
            with self.assertRaises(ValueError):
                device.set_key(0, 0, 0, 0x7C00)
            self.hid.unlocking = True
            with self.assertRaisesRegex(DeviceError, "unlock state"):
                device.set_key(0, 0, 0, 4)
        self.assertFalse(any(command[0] == 0x05 for command in self.hid.commands))

    def test_timeout_closes_connection(self):
        with VialDevice(EXPECTED) as device:
            self.hid.drop_reads = True
            with self.assertRaisesRegex(DeviceError, "contained 0 bytes"):
                device.read_layout()
            self.assertTrue(self.hid.closed)


if __name__ == "__main__":
    unittest.main()
