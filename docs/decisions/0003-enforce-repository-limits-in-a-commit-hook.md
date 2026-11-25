---
status: accepted
date: 2026-11-25
paths:
  - tests/test_repo.py
  - .githooks/*
---
# Enforce repository limits in a commit hook, not CI

## Context and Problem Statement

Prose asking agents to keep the repository small did not stop it growing.

## Considered Options

* Instructions in `AGENTS.md` only.
* A GitHub Actions workflow.
* A test run by a local pre-commit hook.

## Decision Outcome

Chosen option: the local hook, because the user ruled out anything that requires CI, and a hook fails before the commit exists. The tests use only the standard library so the hook needs no environment.

Decision records are the one place prose may grow. They are limited to tooling choices and rejected alternatives, capped in length, and never deleted. A keymap experiment gets no record: its decision is visible in `pinned.txt` and the commit.
