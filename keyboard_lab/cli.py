"""Sync keymap.txt with the keyboard over USB. Cannot flash, reset, unlock, or write macros."""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .device import MAINTENANCE_KEYCODES, VialDevice
from .keymap import KEYS, LAYERS, ORDER, ROOT, codes, decode, format_layer, from_matrix
from .keymap import parse, pin_violations, position, update
from .render import svg

KEYMAP, PINNED = ROOT / "keymap.txt", ROOT / "pinned.txt"
PICTURE, UNDO = ROOT / "build/keymap.svg", ROOT / "state/before-apply.txt"


def connect():
    return VialDevice(json.loads((ROOT / "firmware/device.json").read_text()))


def changes(want, have):
    """[(layer, index, device code, file code)] for every key that differs."""
    return [(n, i, have[n][i], want[n][i]) for n in range(LAYERS) for i in range(KEYS) if want[n][i] != have[n][i]]


def describe(delta, arrow="->"):
    return [f"{position(n, i)}: {decode(old)} {arrow} {decode(new)}" for n, i, old, new in delta]


def checked(text):
    """Parse a keymap and refuse it if it breaks a pinned decision."""
    want = codes(text)
    broken = pin_violations(want, PINNED.read_text())
    if broken:
        raise ValueError("Breaks pinned.txt:\n  " + "\n  ".join(broken))
    return want


def apply(device, want, undo=UNDO):
    """Write only the keys that differ, then confirm the whole keymap reads back as intended."""
    have = from_matrix(device.read_layout())
    delta = changes(want, have)
    if any(new in MAINTENANCE_KEYCODES for _, _, _, new in delta):
        raise ValueError("Bootloader, reboot, debug and EEPROM-clear keys cannot be written here.")
    if delta:
        undo.parent.mkdir(parents=True, exist_ok=True)
        undo.write_text("\n".join(format_layer(n, layer) for n, layer in enumerate(have)))
        for n, index, _, new in delta:
            device.set_key(n, *ORDER[index], new)
        if from_matrix(device.read_layout()) != want:
            raise RuntimeError("Keyboard does not match the file after writing; run `lab diff`.")
    return delta


def draw(text, note):
    PICTURE.parent.mkdir(parents=True, exist_ok=True)
    PICTURE.write_text(svg(codes(text), parse(text)[1], note))


def overlay():
    source, binary = ROOT / "scripts/overlay.swift", ROOT / "build/overlay"
    if not PICTURE.exists():
        draw(KEYMAP.read_text(), "From keymap.txt; not compared with the keyboard.")
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        subprocess.run(["swiftc", "-O", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(PICTURE)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (
        ("check", "parse the file and test it against pinned.txt; no keyboard needed"),
        ("diff", "list keys where the keyboard differs from the file; writes nothing"),
        ("apply", "write the file's differing keys to the keyboard, verify, redraw"),
        ("pull", "rewrite the file's bindings from the keyboard, keeping comments"),
        ("show", "draw build/keymap.svg from the file and open it"),
    ):
        commands.add_parser(name, help=text).add_argument("file", nargs="?", type=Path, default=KEYMAP)
    commands.add_parser("overlay", help="float build/keymap.svg above all windows; Ctrl+Opt+Cmd+K hides it")
    commands.add_parser("inspect", help="print the connected keyboard's identity")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if args.command == "overlay":
            overlay()
        elif args.command == "inspect":
            with connect() as device:
                print(json.dumps(device.identity(), indent=2))
        elif args.command == "pull":
            with connect() as device:
                have = from_matrix(device.read_layout())
            text = update(args.file.read_text() if args.file.exists() else "", have)
            args.file.write_text(text)
            draw(text, f"Read from the keyboard {stamp}.")
            print(f"{args.file} now matches the keyboard.")
        else:
            text = args.file.read_text()
            want = checked(text)
            if args.command == "check":
                print("OK")
            elif args.command == "show":
                draw(text, f"From {args.file.name}; not compared with the keyboard.")
                subprocess.run(["open", str(PICTURE)])
            elif args.command == "diff":
                with connect() as device:
                    delta = changes(want, from_matrix(device.read_layout()))
                print("\n".join(describe(delta, "on keyboard, file has")) or "Keyboard matches the file.")
            elif args.command == "apply":
                with connect() as device:
                    delta = apply(device, want)
                draw(text, f"Written to and read back from the keyboard {stamp}.")
                print("\n".join(describe(delta)) or "Keyboard already matches the file.")
                if delta:
                    print(f"{len(delta)} keys written and verified. Undo: scripts/lab apply {UNDO.relative_to(ROOT)}")
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
