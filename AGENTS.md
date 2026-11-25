# Working in keyboard-lab

Commands: `scripts/lab --help`. `keymap.txt` is the keymap; `pinned.txt` is what it must keep.

At session start, open accepted decisions whose `paths` cover your edits:

    grep -l '^status: accepted' docs/decisions/*.md | xargs grep -A6 '^paths:'

Rules the code cannot tell you:

- Run `scripts/lab diff` before editing. Never infer the keyboard's state.
- Ask when a mapping is ambiguous. Say which keys will change before `scripts/lab apply`. Only a requested binding change authorizes apply.
- Do not edit `pinned.txt` unless the user changed that decision.
- No flashing, reset, unlock, macro or settings writes, and no computer use. Keep Vial closed while the tool runs.
- Leave `.cache/` and the user's separate QMK repository alone.
- Report changed keys, test result, whether the keyboard was written and read back, and what is untested.

Notes:

- Add a line here only if the repo cannot answer it. If code and a note disagree, delete the note.
- Before the session ends, draft a decision record for a tooling choice or rejection the code does not explain. Keymap experiments get none. Never delete a record; supersede it.
- `tests/test_repo.py` has the limits and record format. Do not raise them.
