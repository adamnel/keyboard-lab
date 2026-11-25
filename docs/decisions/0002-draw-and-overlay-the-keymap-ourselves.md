---
status: accepted
date: 2026-11-25
paths:
  - keyboard_lab/render.py
  - scripts/overlay.swift
---
# Draw and overlay the keymap with our own code

## Context and Problem Statement

The current map has to be visible on screen while acclimating.

## Considered Options

* keymap-drawer for the picture.
* Lenny's ZMK Keyboard Overlay (lenny.zone/overlay) for a live layer display.
* A small SVG renderer plus a floating Swift window.

## Decision Outcome

Chosen option: our own renderer and window, because keymap-drawer adds a dependency and a network fetch for about a hundred lines of drawing, and Lenny's overlay needs ZMK firmware and supports only the 42-key Corne. This board runs Vial on QMK with 46 keys.

The overlay shows every layer at once. Showing only the active layer needs firmware that reports layer changes over HID, which shares a channel with Vial and `scripts/lab`. Deferred by the user on 2026-11-25.
