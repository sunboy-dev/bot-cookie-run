# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A desktop auto-farm bot for **Cookie Run: OvenBreak** running in Android emulators (MuMu, Nox).
A tkinter UI detects emulators, runs one independent bot per emulator screen, and shows a live
log. Each bot drives the game by capturing the screen over ADB, matching it against known game
states, and tapping. Original spec (Thai): `requirement.txt`.

## Run / test

```bash
./env/bin/python cookie_bot.py             # launch the UI
./env/bin/python cookie_bot.py --self-test # verify state matching against images/
pip install -r requirements.txt            # opencv-python-headless + numpy; tkinter is stdlib
```

`env/` is a Python 3.9 virtualenv. Requires the `adb` binary on PATH (or set `ADB=/path/to/adb`);
MuMu/Nox bundle one. There is no build step and no test framework — `demo()` in `cookie_bot.py` is the
only check.

## Architecture (all in cookie_bot.py)

- **ADB layer** (`detect_devices`, `capture`, `tap`): control is entirely via ADB, not screen/mouse.
  `detect_devices` first `adb connect`s known emulator loopback ports (`EMULATOR_PORTS`) then parses `adb devices`.
  `capture` uses `exec-out screencap -p` (avoids CRLF mangling) and decodes with OpenCV. This is what
  lets multiple emulators be controlled independently and simultaneously.
- **State matching** (`STATES`, `load_refs`, `detect`): each blocking game screen has a reference in
  `images/`. Frames are downscaled to `CANON` and compared by normalized correlation. The best match
  above `MATCH_THRESHOLD` wins; **below threshold means "mid-run" → tap Jump**. The dynamic in-run
  screens (running / bonus-time / running-after-bonus-time) are deliberately NOT in `STATES` because
  their backgrounds vary too much to template — they're the fallback case.
- **Per-state actions** live in `STATES`: `tap` (menu button), `boost` (paid prompt, only tapped when
  "Use boosts" is on, else ignored), `wait`. Tap points are screen fractions so they scale to any
  device resolution.
- **BotWorker** (thread, one per emulator): capture → detect → act loop, guarded by a stop `Event`.
  Threads never touch tkinter; they push `("log"|"state", serial, payload)` onto a queue.
- **App** (tkinter): the `events` queue is drained on a `root.after` timer to update the log/treeview
  on the UI thread. Buttons act on all or the selected emulator(s).

## Scope

Farm loop only: navigate menus and jump periodically to keep runs going. There is no obstacle-dodging
AI — runs end when the cookie hits something, then the loop restarts. Adding real dodging would mean
per-frame obstacle detection, a separate large effort.

## Editing notes

- Changing tap targets: edit the fractions in `STATES` / `JUMP`, read off the reference screenshots.
- Adding a game screen: add a reference image to `images/` and an entry to `STATES`, then run
  `--self-test` (asserts every reference best-matches itself above threshold).
- If run frames ever start matching a menu state (false positive), raise `MATCH_THRESHOLD` — the
  self-test / discrimination gap is currently ~0.37 (run frames) vs 1.00 (menus).
