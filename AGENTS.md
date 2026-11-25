# Working in keyboard-lab

Read README.md and requirements.yaml first. Inspect current Git status. Follow user instructions and ask when a requested mapping is ambiguous.

Explain concrete impact before live changes. User-requested binding changes authorize the direct pipeline; setup alone does not authorize a layout change. No computer use, emails, firmware flashing, reset, unlock, or macro/settings writes through this project.

Capture the connected device before planning. Never infer its current layout from firmware defaults or earlier conversation. Use scripts/lab plan, diff, validate, apply and render; do not bypass transaction checks. Keep Vial closed during direct access. Resolve interrupted journals with recover before further edits.

Tie each candidate to requirement IDs. Requirements are executable decisions: machine checks must pass, manual goals must remain honestly unverified until observed. Do not silently relax an invariant to get a candidate through. Add focused tests for new validation or transport behavior; run the suite before applying changed tooling.

Keep firmware upstream pinned and untouched outside .cache. Build changes before proposing a flash. Do not modify the user's separate QMK repository. Never commit state, caches, environments, or generated build output.

Use the vault for human experiment notes and the existing work ledger for tasks. Keep this repository's documentation short; no duplicate plans, chat transcripts, progress diaries, or speculative architecture. Record a meaningful accepted decision once and link it where needed. Preserve rejected alternatives only when their reason prevents repeating a mistake.

For each completed request report: changed keys, validation, hardware verification, and any remaining usability uncertainty. Never claim a live write was tested when only a simulator ran.
