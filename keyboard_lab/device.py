"""Read and edit the dynamic keymap over the keyboard's Vial Raw HID interface."""

import hashlib
import json
import lzma
import struct


_REPORT_SIZE = 32
_TIMEOUT_MS = 750
_MAX_DEFINITION_BYTES = 32 * 1024
_MAX_DECOMPRESSED_BYTES = 256 * 1024

_GET_KEY = 0x04
_SET_KEY = 0x05
_GET_LAYER_COUNT = 0x11
_GET_BUFFER = 0x12

_VIAL = 0xFE
_GET_ID = 0x00
_GET_DEFINITION_SIZE = 0x01
_GET_DEFINITION_PAGE = 0x02
_GET_UNLOCK_STATUS = 0x05
_VIAL_PROTOCOL = 6
MAINTENANCE_KEYCODES = range(0x7C00, 0x7C05)


class DeviceError(RuntimeError):
    """A HID transport, protocol, or identity check failed."""


def descriptor_sha256(definition):
    """Hash the complete Vial JSON definition independently of formatting."""
    canonical = json.dumps(definition, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VialDevice:
    def __init__(self, identity):
        self._expected = dict(identity)
        self._handle = None
        self._observed = None

    def __enter__(self):
        if self._handle is not None:
            raise DeviceError("The Vial device is already open.")
        try:
            import hid

            vid, pid = self._expected["vid"], self._expected["pid"]
            interfaces = hid.enumerate(vid, pid)
            matching = [
                interface for interface in interfaces
                if interface["usage_page"] == self._expected["usage_page"]
                and interface["usage"] == self._expected["usage"]
            ]
            if len(matching) != 1:
                raise DeviceError(
                    f"Expected one matching Vial Raw HID interface, found {len(matching)}."
                )
            interface = matching[0]
            self._handle = hid.Device(path=interface["path"])
            self._observed = self._verify_identity(interface)
        except BaseException as error:
            self.close()
            if isinstance(error, (DeviceError, KeyboardInterrupt, SystemExit)):
                raise
            raise DeviceError(f"Unable to open or verify the Vial device: {error}") from error
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        handle, self._handle = self._handle, None
        self._observed = None
        if handle is not None:
            handle.close()

    def _exchange(self, command, echo=None):
        if self._handle is None:
            raise DeviceError("The Vial device is closed.")
        request = bytes(command).ljust(_REPORT_SIZE, b"\0")
        try:
            # HIDAPI takes a leading report ID even for unnumbered reports.
            written = self._handle.write(b"\0" + request)
            if written != _REPORT_SIZE + 1:
                raise DeviceError(f"Vial HID write sent {written} bytes, expected 33.")
            response = self._handle.read(_REPORT_SIZE + 1, timeout=_TIMEOUT_MS)
            if len(response) != _REPORT_SIZE:
                raise DeviceError(
                    f"Vial HID response contained {len(response)} bytes, expected 32."
                )
            if echo is not None and response[:echo] != request[:echo]:
                raise DeviceError("Vial HID response did not echo the request.")
        except Exception as error:
            self.close()
            if isinstance(error, DeviceError):
                raise
            raise DeviceError(f"Vial HID exchange failed: {error}") from error
        return response

    def _definition(self):
        reply = self._exchange((_VIAL, _GET_DEFINITION_SIZE))
        size = int.from_bytes(reply[:4], "little")
        if not 0 < size <= _MAX_DEFINITION_BYTES:
            raise DeviceError(f"Unexpected Vial definition size {size}.")
        pages = bytearray()
        for page in range((size + _REPORT_SIZE - 1) // _REPORT_SIZE):
            pages.extend(self._exchange((_VIAL, _GET_DEFINITION_PAGE, page & 0xFF, page >> 8)))
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=32 * 1024 * 1024)
        definition = decoder.decompress(pages[:size], max_length=_MAX_DECOMPRESSED_BYTES + 1)
        if not decoder.eof or decoder.unused_data or len(definition) > _MAX_DECOMPRESSED_BYTES:
            raise DeviceError("Invalid or oversized Vial definition.")
        return json.loads(definition)

    def _verify_identity(self, interface):
        reply = self._exchange((_VIAL, _GET_ID))
        protocol = int.from_bytes(reply[:4], "little")
        if protocol != _VIAL_PROTOCOL:
            raise DeviceError(f"Unsupported Vial protocol {protocol}, expected {_VIAL_PROTOCOL}.")
        uid = reply[4:12].hex()
        if uid != self._expected["vial_uid"]:
            raise DeviceError(f"Vial UID mismatch: observed {uid}.")
        definition = self._definition()
        digest = descriptor_sha256(definition)
        if digest != self._expected["descriptor_sha256"]:
            raise DeviceError(f"Vial definition SHA-256 mismatch: observed {digest}.")

        vid, pid = interface["vendor_id"], interface["product_id"]
        if (vid, pid) != (int(definition["vendorId"], 0), int(definition["productId"], 0)):
            raise DeviceError("The Vial definition and USB interface disagree on VID/PID.")
        self._check_unlock_status()
        observed = {
            "vid": vid,
            "pid": pid,
            "usage_page": interface["usage_page"],
            "usage": interface["usage"],
            "vial_uid": uid,
            "descriptor_sha256": digest,
            "layers": self._exchange((_GET_LAYER_COUNT,), echo=1)[1],
            "rows": definition["matrix"]["rows"],
            "cols": definition["matrix"]["cols"],
            "vial_protocol": protocol,
        }
        for name in ("vid", "pid", "layers", "rows", "cols"):
            if observed[name] != self._expected[name]:
                raise DeviceError(f"Vial {name} mismatch: observed {observed[name]}.")
        layers, rows, cols = (observed[name] for name in ("layers", "rows", "cols"))
        if any(type(value) is not int or not 1 <= value <= 255 for value in (layers, rows, cols)):
            raise DeviceError("Invalid Vial keymap dimensions.")
        if layers * rows * cols * 2 > 65536:
            raise DeviceError("The keymap exceeds the Vial buffer address range.")
        return observed

    def _check_unlock_status(self):
        status = self._exchange((_VIAL, _GET_UNLOCK_STATUS))
        if status[0] not in (0, 1) or status[1] != 0:
            raise DeviceError("Vial unlock state prevents verifying the keymap operation.")

    def identity(self):
        if self._observed is None:
            raise DeviceError("The Vial device must be open and verified.")
        return dict(self._observed)

    def read_layout(self):
        observed = self.identity()
        layers, rows, cols = (observed[name] for name in ("layers", "rows", "cols"))
        self._check_unlock_status()
        data = bytearray()
        size = 2 * layers * rows * cols
        for offset in range(0, size, 28):
            length = min(28, size - offset)
            command = (_GET_BUFFER, offset >> 8, offset & 0xFF, length)
            reply = self._exchange(command, echo=4)
            data.extend(reply[4:4 + length])
        self._check_unlock_status()
        codes = iter(code for (code,) in struct.iter_unpack(">H", data))
        return [[[next(codes) for _ in range(cols)] for _ in range(rows)] for _ in range(layers)]

    def set_key(self, layer, row, col, code):
        observed = self.identity()
        for name, value, stop in (
            ("layer", layer, observed["layers"]),
            ("row", row, observed["rows"]),
            ("column", col, observed["cols"]),
            ("keycode", code, 65536),
        ):
            if type(value) is not int or not 0 <= value < stop:
                raise ValueError(f"{name} must be an integer in [0, {stop}).")
        if code in MAINTENANCE_KEYCODES:
            raise ValueError("Bootloader, reboot, debug, EEPROM-clear, and make keycodes are disabled.")

        self._check_unlock_status()
        try:
            self._exchange((_SET_KEY, layer, row, col, code >> 8, code & 0xFF), echo=_REPORT_SIZE)
            reply = self._exchange((_GET_KEY, layer, row, col), echo=4)
            self._check_unlock_status()
            actual = int.from_bytes(reply[4:6], "big")
            if actual != code:
                raise DeviceError(f"Expected 0x{code:04x}, observed 0x{actual:04x}.")
        except DeviceError as error:
            raise DeviceError(f"Vial did not verify the key change: {error}") from error
