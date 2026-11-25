# Keyboard lab

Keymap experiments for a wired YMDK Corne 4.1 (46 keys, Vial firmware) on macOS.

- `keymap.txt` is the keymap. Edit it; `scripts/lab apply` writes the differing keys over USB in about a second. No flashing.
- `pinned.txt` holds the decisions a keymap may not break.
- `scripts/lab --help` lists every command. `scripts/lab overlay` floats the current map on screen.
- `scripts/bootstrap.sh` sets up Python, the pinned Vial source and the commit hook. `scripts/build.sh` builds firmware into `build/` and never flashes.

Quit Vial before using `scripts/lab`: macOS gives the keyboard to one program at a time.

Only key bindings are synced. Tap-hold timing, combos, macros and RGB are set in Vial and are not recorded here.

Each accepted experiment is one commit of `keymap.txt`; the commit message says what was learned. Research and open questions live in `/Users/adam/Knowledge/01-Projects/Keyboard Experimentation/`, not here. Tooling choices and rejected alternatives are recorded in `docs/decisions/`. `tests/test_repo.py` fails the commit if the repository grows other documents or directories.

`recovery/` is the firmware that was on the board before this project.
