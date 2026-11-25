---
status: accepted
date: 2026-11-25
paths:
  - keymap.txt
  - keyboard_lab/cli.py
  - keyboard_lab/keymap.py
---
# Sync one readable keymap file declaratively

## Context and Problem Statement

Trying a key change took seven commands, and the stored keymap was a numeric matrix nobody could read or diff.

## Considered Options

* Journaled transactions: capture, plan, apply, accept, with rollback and recovery.
* One text file in key names; `apply` writes whatever differs and reads the keymap back.

## Decision Outcome

Chosen option: the text file, because a binding write cannot lock the keyboard out and an interrupted apply is fixed by running it again. The journal, recovery and candidate files guarded a risk that re-applying already covers. Undo is the saved pre-apply state or the previous commit.

Kept from the old design: device identity check, per-key read-back, and the block on bootloader, reboot and EEPROM-clear keys.
