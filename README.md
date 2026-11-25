# Keyboard lab

A small, independent Git repository for Adam’s wired YMDK Corne 4.1 (46 keys), macOS, and Vial experiments. Ordinary key changes travel directly over USB; no computer use or firmware flash is needed.

## Sources of truth

- `requirements.yaml`: machine-checked constraints, stated preferences, and explicitly unverified usability goals.
- `layouts/`: observed baseline, proposed change, and latest user-accepted layout. Firmware defaults are **not** the current layout.
- `firmware/`: local firmware source, device identity, physical key positions, and pinned Vial/QMK dependency. The upstream checkout is disposable under `.cache/`.
- `state/`: local transaction backups and journals; ignored by Git. Back these up separately if desired.
- `build/`: generated firmware and HTML key reference; ignored by Git.
- Human research, preferences, and experiment notes remain in `/Users/adam/Knowledge/01-Projects/Keyboard Experimentation/`. Keep the existing work ledger as the only task list.

This repository has its own history. It is not a fork of the large QMK tree. The upstream URL and exact revision live in `firmware/upstream.lock.json`; no Git hosting remote is assumed. The existing `/Users/adam/Projects/qmk` remains independent.

## Setup and checks

Prerequisites on this Mac: Python 3.15, Git, make, ARM GNU toolchain, and HIDAPI (`brew install hidapi`).

```sh
scripts/bootstrap.sh
.venv/bin/python -m pytest -q
scripts/build.sh
```

Bootstrap downloads locked dependencies into this project. Build verifies the pinned upstream revision and required submodules, stages our keymap, and produces a UF2 under `build/`. It never flashes. Toolchain versions are not fully locked, so binary reproducibility is not promised. `recovery/` holds the prior Miryoku firmware/source, not a backup of current Vial settings.

## Iteration

Quit Vial and other device editors first: macOS HID access may be exclusive. Connect the USB master half.

```sh
scripts/lab inspect
scripts/lab capture --out state/live.json
scripts/lab render state/live.json
```

Open `build/keymap.html` for a physical map of all layers. This is a snapshot reference, not a live active-layer overlay. Regenerate after changes.

For each requested experiment, capture fresh, create a small candidate tied to requirement IDs, inspect its diff and validation, then apply. Example syntax only:

```sh
scripts/lab plan --from state/live.json \
  --set 1 left.row1.col1 KC_LEFT \
  --reason 'Trial arrow access' --requirement NAV-01
scripts/lab diff layouts/candidate.json
scripts/lab validate layouts/candidate.json
scripts/lab apply layouts/candidate.json
scripts/lab render layouts/candidate-live.json
```

The agent can perform this pipeline directly for a requested change. It must explain impact first, resolve ambiguity, and preserve unrelated bindings. Applying verifies device identity and unchanged baseline, saves a durable backup, writes only changed keys, and reads back the entire keymap. A failure attempts verified rollback. Disconnection or process termination may leave partial changes; the journal blocks further writes until recovery:

```sh
scripts/lab recover state/transaction-<timestamp>
```

Unexpected concurrent edits make automatic recovery refuse rather than overwrite them. Reconnect first if necessary. Never delete an unresolved journal to bypass this check. To intentionally return to another supported snapshot, use `scripts/lab restore PATH --reason '...'`; normal validation still applies.

After actual use, record one short observation and explicitly accept or revise:

```sh
scripts/lab accept --observation 'User-reported result of the trial'
```

Acceptance verifies the live map matches the last applied snapshot. Commit the accepted layout and relevant requirement changes together. Do not log every keystroke, tool run, or conversation. One experiment should answer one question.

## What is validated

Automated checks enforce geometry, QWERTY placement, the agreed left Space/hold Cmd+Ctrl binding, and the current number/symbol entry keys. Unknown check types fail. Subjective goals remain `unverified`, never silently pass. A changed decision requires updating its requirement and meaningful test before applying the new design.

USB checks verify VID/PID, usage, Vial UID, descriptor hash, protocol, matrix, and layer count. Snapshots cover **key bindings only**: macros, combos, tap-hold timing, RGB, and other EEPROM settings are neither captured nor restored. Supported edits exclude firmware/reset commands and persistent default-layer/tap-dance functions. A complete Vial export is a separate backup.

## Decisions and research

Current decisions: simple modifiers while acclimating; left-thumb Space; one-handed workspace access more frequent than number entry; retain QWERTY; no inherited Miryoku plan. Cmd+Ctrl+D remains a Dictionary conflict. Full Hyper migration, modifier placement, Cmd+number access, arrows versus HJKL, Raycast/1Password shortcuts, and navigation/selection remain experiments, not settled designs.

Primary technical evidence is the pinned source: `quantum/via.c`, `quantum/vial.c`, `quantum/keycodes.h`, and `keyboards/crkbd/rev4_1/`. See [Vial source](https://github.com/vial-kb/vial-qmk) and [Vial documentation](https://get.vial.today/). Research notes should state source, conclusion, and relevance in a few lines; only accepted decisions change requirements. Lenny overlay compatibility and a live macOS layer indicator remain separate research, not delivered features.
