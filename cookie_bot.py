#!/usr/bin/env python3
"""Cookie Run: OvenBreak auto-farm bot for Android emulators (MuMu, Nox), via ADB.

UI (tkinter): detect emulators, run an independent bot per screen, live log.
Each bot loops: capture screen -> match against known game states -> tap.

See requirement.txt for the original spec (Thai).
"""
import os
os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")  # macOS system Tk 8.5 deprecation notice
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np

# --- config ---------------------------------------------------------------
ADB = os.environ.get("ADB", "adb")  # override with ADB=/path/to/adb if not on PATH
# Emulators expose ADB on these loopback ports, per program.
# LDPlayer: 5555 then +2 per extra instance (5557, 5559, ...).
EMULATOR_PORTS = {
    "MuMu": [16384, 16416, 16448, 16480, 7555],
    "Nox": [62001, 62025, 62026, 62027, 62028, 52001],
    "LDPlayer": [5555, 5557, 5559, 5561, 5563],
}
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")

CANON = (256, 144)      # everything is downscaled to this before matching
MATCH_THRESHOLD = 0.62  # min correlation to accept a state; below => assume mid-run
LOOP_SLEEP = 0.6        # seconds between capture cycles
MENU_SLEEP = 2.0        # extra wait after a menu/boost tap, to let the screen transition

# Each known state: reference image, what to do, and where to tap (as fractions of
# the screen so it scales to any device resolution). Coordinates read off the
# reference screenshots in images/.
#   "tap"   -> menu button, tap and wait for transition
#   "boost" -> optional paid boost prompt; only tapped when "Use boosts" is on
#   "wait"  -> do nothing, just poll again
# The dynamic in-run screens (running/bonus-time/...) are NOT listed: when nothing
# matches above threshold we assume we're mid-run and tap Jump. ponytail: run
# backgrounds vary wildly, so a fallback beats trying to template every frame.
STATES = {
    "loading":           ("loading.webp",           "wait",  None),
    "lobby":             ("lobby.webp",             "tap",   (0.700, 0.895)),  # Play!
    "pre-run":           ("pre-run.webp",           "tap",   (0.665, 0.852)),  # Play! (over upgrades popup)
    "mysterybox":        ("mysterybox.webp",        "tap",   (0.500, 0.891)),  # Open all
    "opened-mysterybox": ("opened-mysterybox.webp", "tap",   (0.500, 0.891)),  # Confirm
    "result":            ("result.webp",            "tap",   (0.385, 0.859)),  # OK
    "start-run":         ("start-run.webp",         "boost", (0.507, 0.479)),  # Fast Start Boost
    "first-cookie-die":  ("first-cookie-die.webp",  "boost", (0.507, 0.479)),  # Cookie Relay Boost
}
JUMP = (0.140, 0.868)  # Jump button, tapped repeatedly during a run

CONFIG = {"use_boosts": False}  # shared, read by worker threads


# --- adb -------------------------------------------------------------------
# On Windows, stop every adb call from flashing a console window (bot calls adb
# several times a second). No-op elsewhere.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args, **kw):
    return subprocess.run([ADB, *args], capture_output=True, timeout=20,
                          creationflags=_NO_WINDOW, **kw)


def detect_devices(program=None):
    """Connect to known emulator ports, then return serials adb reports as online.

    program: an EMULATOR_PORTS key to limit to one program, or None for all."""
    ports = EMULATOR_PORTS[program] if program else [p for v in EMULATOR_PORTS.values() for p in v]
    for port in ports:
        try:
            _run(["connect", f"127.0.0.1:{port}"])
        except Exception:
            pass  # port not listening; fine
    out = _run(["devices"]).stdout.decode(errors="replace")
    serials = []
    for line in out.splitlines()[1:]:  # skip "List of devices attached"
        parts = line.split()
        if len(parts) == 2 and parts[1] == "device":
            serials.append(parts[0])
    return serials


def capture(serial):
    """Grab the screen as a BGR image, or None on failure. exec-out avoids CRLF mangling."""
    r = _run(["-s", serial, "exec-out", "screencap", "-p"])
    if not r.stdout:
        return None
    img = cv2.imdecode(np.frombuffer(r.stdout, np.uint8), cv2.IMREAD_COLOR)
    return img


def tap(serial, frac, shape):
    h, w = shape[:2]
    x, y = int(frac[0] * w), int(frac[1] * h)
    _run(["-s", serial, "shell", "input", "tap", str(x), str(y)])


# --- matching --------------------------------------------------------------
def _canon(img):
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), CANON)


def load_refs():
    refs = {}
    for name, (fn, action, pt) in STATES.items():
        path = os.path.join(IMAGES_DIR, fn)
        img = cv2.imread(path)
        if img is None:
            raise FileNotFoundError(f"reference image missing: {path}")
        refs[name] = (_canon(img), action, pt)
    return refs


def detect(frame, refs):
    """Return (name, action, tap_frac, score) of the best matching state, or None if below threshold."""
    small = _canon(frame)
    best, best_score = None, -1.0
    for name, (ref, action, pt) in refs.items():
        # equal-size templates -> matchTemplate returns a 1x1 normalized correlation
        score = float(cv2.matchTemplate(small, ref, cv2.TM_CCOEFF_NORMED)[0][0])
        if score > best_score:
            best_score, best = score, (name, action, pt)
    if best_score < MATCH_THRESHOLD:
        return None, best_score
    name, action, pt = best
    return (name, action, pt), best_score


# --- worker ----------------------------------------------------------------
class BotWorker(threading.Thread):
    def __init__(self, serial, refs, events):
        super().__init__(daemon=True)
        self.serial = serial
        self.refs = refs
        self.events = events        # queue of (kind, serial, payload)
        self.stop_flag = threading.Event()

    def log(self, msg):
        self.events.put(("log", self.serial, msg))

    def set_state(self, state):
        self.events.put(("state", self.serial, state))

    def run(self):
        self.log("bot started")
        self.set_state("running")
        while not self.stop_flag.is_set():
            frame = capture(self.serial)
            if frame is None:
                self.log("capture failed; retrying")
                time.sleep(1.0)
                continue
            match, score = detect(frame, self.refs)
            if match is None:
                # mid-run: keep the cookie jumping
                tap(self.serial, JUMP, frame.shape)
                time.sleep(LOOP_SLEEP)
                continue

            name, action, pt = match
            if action == "wait":
                self.log(f"{name} ({score:.2f}) -> wait")
            elif action == "tap":
                self.log(f"{name} ({score:.2f}) -> tap")
                tap(self.serial, pt, frame.shape)
                time.sleep(MENU_SLEEP)
            elif action == "boost":
                if CONFIG["use_boosts"]:
                    self.log(f"{name} ({score:.2f}) -> boost")
                    tap(self.serial, pt, frame.shape)
                    time.sleep(MENU_SLEEP)
                else:
                    tap(self.serial, JUMP, frame.shape)  # ignore boost, keep running
            time.sleep(LOOP_SLEEP)
        self.log("bot stopped")
        self.set_state("stopped")

    def stop(self):
        self.stop_flag.set()


# --- ui --------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.refs = load_refs()
        self.workers = {}                  # serial -> BotWorker
        self.events = queue.Queue()
        root.title("Cookie Run Bot")
        root.geometry("720x520")

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        self.program = tk.StringVar(value="All")
        ttk.Combobox(top, textvariable=self.program, state="readonly", width=10,
                     values=["All", *EMULATOR_PORTS]).pack(side="left", padx=(0, 4))
        ttk.Button(top, text="Detect Emulators", command=self.detect).pack(side="left")
        ttk.Button(top, text="Start All", command=self.start_all).pack(side="left", padx=4)
        ttk.Button(top, text="Stop All", command=self.stop_all).pack(side="left")
        self.use_boosts = tk.BooleanVar(value=CONFIG["use_boosts"])
        ttk.Checkbutton(top, text="Use boosts", variable=self.use_boosts,
                        command=self._sync_boosts).pack(side="right")

        self.tree = ttk.Treeview(root, columns=("serial", "state"), show="headings", height=6)
        self.tree.heading("serial", text="Emulator")
        self.tree.heading("state", text="State")
        self.tree.column("state", width=120, anchor="center")
        self.tree.pack(fill="x", padx=8)

        row = ttk.Frame(root, padding=(8, 4))
        row.pack(fill="x")
        ttk.Button(row, text="Start Selected", command=self.start_selected).pack(side="left")
        ttk.Button(row, text="Stop Selected", command=self.stop_selected).pack(side="left", padx=4)
        ttk.Button(row, text="Remove Selected", command=self.remove_selected).pack(side="left")

        self.log = tk.Text(root, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

        self.root.after(200, self._drain)

    def _sync_boosts(self):
        CONFIG["use_boosts"] = self.use_boosts.get()

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_row_state(self, serial, state):
        if self.tree.exists(serial):
            self.tree.set(serial, "state", state)

    def _drain(self):
        try:
            while True:
                kind, serial, payload = self.events.get_nowait()
                if kind == "log":
                    self._log(f"[{serial}] {payload}")
                elif kind == "state":
                    self._set_row_state(serial, payload)
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    def detect(self):
        program = self.program.get()
        program = None if program == "All" else program
        self._log(f"detecting {program or 'all'} emulators...")
        try:
            serials = detect_devices(program)
        except FileNotFoundError:
            self._log(f"ERROR: adb not found. Install it or set ADB=/path/to/adb. Tried '{ADB}'.")
            return
        for s in serials:
            if not self.tree.exists(s):
                self.tree.insert("", "end", iid=s, values=(s, "idle"))
        self._log(f"found {len(serials)} emulator(s)" if serials else "no emulators found")

    def _selected(self):
        return list(self.tree.selection())

    def _start(self, serial):
        w = self.workers.get(serial)
        if w and w.is_alive():
            return
        w = BotWorker(serial, self.refs, self.events)
        self.workers[serial] = w
        w.start()

    def _stop(self, serial):
        w = self.workers.get(serial)
        if w:
            w.stop()

    def start_selected(self):
        for s in self._selected():
            self._start(s)

    def stop_selected(self):
        for s in self._selected():
            self._stop(s)

    def start_all(self):
        for s in self.tree.get_children():
            self._start(s)

    def stop_all(self):
        for s in list(self.workers):
            self._stop(s)

    def remove_selected(self):
        for s in self._selected():
            self._stop(s)
            self.workers.pop(s, None)
            self.tree.delete(s)


def demo():
    """Self-check: every reference must best-match itself. Fails loudly if matching breaks."""
    refs = load_refs()
    for name, (fn, _a, pt) in STATES.items():
        if pt is not None:
            assert 0 <= pt[0] <= 1 and 0 <= pt[1] <= 1, f"tap frac out of range for {name}"
        img = cv2.imread(os.path.join(IMAGES_DIR, fn))
        match, score = detect(img, refs)
        assert match is not None and match[0] == name, f"{name} detected as {match} ({score:.2f})"
    print(f"OK: {len(STATES)} states self-identify above threshold {MATCH_THRESHOLD}")


def main():
    import sys
    if "--self-test" in sys.argv:
        demo()
        return
    root = tk.Tk()
    App(root)
    # macOS system Tk 8.5 renders a blank window until the first resize; nudge it once.
    root.geometry("720x520")
    root.after(60, lambda: root.geometry("721x521"))
    root.mainloop()


if __name__ == "__main__":
    main()
