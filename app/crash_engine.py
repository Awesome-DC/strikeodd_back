"""
crash_engine.py — Server-side global round state for Aviator & Crash Live.

One round runs continuously for ALL users:
  - WAITING  (5 s) — accept bets
  - FLYING   (until crash point) — multiplier climbs
  - CRASHED  (3 s) — show result before next round

Clients GET /api/crash/state  →  { phase, mult, crashAt, roundId, elapsed, startedAt }
They never see crashAt until phase == "crashed".
"""

import time
import math
import random
import threading

WAIT_SECS   = 5      # lobby countdown
CRASHED_SECS = 3     # display crash result before next round
TICK_MS      = 100   # how often the engine updates (ms)

# ── multiplier formula ──────────────────────────────────────
# Same as Aviator: exponential climb with house edge baked in
def _mult_at(elapsed_ms: float) -> float:
    return round(math.pow(1.028, elapsed_ms / 100), 2)

# ── crash point generation ──────────────────────────────────
# ~3% house edge; min 1.00, sometimes very high
def _gen_crash() -> float:
    r = random.random()
    if r < 0.03:
        return 1.00          # instant crash ~3% of time
    # Pareto-like: most rounds 1–5×, occasional 10×+
    return round(max(1.01, 1 / (1 - random.random() * 0.97)), 2)


class CrashEngine:
    def __init__(self):
        self._lock   = threading.Lock()
        self._phase  = "waiting"          # waiting | flying | crashed
        self._round_id = 0
        self._crash_at = 2.00
        self._started_at = 0.0            # epoch ms when flying began
        self._phase_entered = time.time() # epoch s when current phase started
        self._history = []                # last 20 crash points
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ── main loop ───────────────────────────────────────────
    def _loop(self):
        while True:
            now = time.time()
            with self._lock:
                phase = self._phase
                elapsed = now - self._phase_entered

            if phase == "waiting" and elapsed >= WAIT_SECS:
                self._begin_round()
            elif phase == "flying":
                elapsed_ms = (now - self._started_at / 1000) * 1000
                # use real ms since flying started
                elapsed_ms = (now - self._started_at) * 1000
                m = _mult_at(elapsed_ms)
                with self._lock:
                    if m >= self._crash_at:
                        self._phase = "crashed"
                        self._phase_entered = now
                        self._history = [self._crash_at] + self._history[:19]
            elif phase == "crashed" and elapsed >= CRASHED_SECS:
                self._begin_wait()

            time.sleep(TICK_MS / 1000)

    def _begin_wait(self):
        with self._lock:
            self._phase = "waiting"
            self._phase_entered = time.time()
            self._round_id += 1
            self._crash_at = _gen_crash()

    def _begin_round(self):
        with self._lock:
            self._phase = "flying"
            self._started_at = time.time()
            self._phase_entered = self._started_at

    # ── public API ──────────────────────────────────────────
    def state(self) -> dict:
        now = time.time()
        with self._lock:
            phase      = self._phase
            round_id   = self._round_id
            crash_at   = self._crash_at
            started_at = self._started_at
            entered    = self._phase_entered
            history    = list(self._history)

        if phase == "flying":
            elapsed_ms = (now - started_at) * 1000
            mult = min(_mult_at(elapsed_ms), crash_at)
        elif phase == "crashed":
            mult = crash_at
        else:
            mult = 1.00
            elapsed_ms = 0

        countdown = max(0, round(WAIT_SECS - (now - entered), 2)) if phase == "waiting" else 0

        return {
            "phase":     phase,
            "roundId":   round_id,
            "mult":      mult,
            "crashAt":   crash_at if phase == "crashed" else None,  # hidden until crash
            "elapsed":   round((now - started_at) * 1000, 0) if phase == "flying" else 0,
            "countdown": countdown,
            "history":   history,
        }


# Singleton — imported by __init__.py once
engine = CrashEngine()
