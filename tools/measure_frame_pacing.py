"""Read-only frame pacing probe for a running 2.9.2 client (no breakpoints).

Usage: python -I tools/measure_frame_pacing.py PID OUTPUT.json [--seconds 10]

Polls, as fast as ReadProcessMemory allows, three values the client writes:
  * the frame counter incremented just before each present (app [0x5E6E58]
    +0x38, `inc` at 0x44AF94, then Flip/blit via 0x5530A0);
  * the game clock (0x5E8E5C, set by 0x529700 / 0x5296C0);
  * the main camera matrix (graphics [0x60C828] +0x2510, copied by 0x553810).
It also records the app-active flag (0x5E6E28): while it is clear (window in
the background) the main loop stops and only the ~66 ms wakeup timer renders.
Each counter change is timestamped with QueryPerformanceCounter. The poll
loop's own interval is recorded so missed frames (counter steps > 1) and
timestamp uncertainty are explicit. The probe never writes to the process.

What this measures: when the client *issues* presents and how much game time
and camera motion each issued frame carries. It does not observe the GPU or
the compositor; the screen can still differ (wrapper queueing, DWM).
"""
import argparse
import ctypes
import json
import math
import statistics
import struct
import time
from ctypes import wintypes
from pathlib import Path

APP_POINTER, FRAME_COUNTER = 0x5E6E58, 0x38
GAME_CLOCK = 0x5E8E5C
GRAPHICS_POINTER, MAIN_CAMERA = 0x60C828, 0x2510
APP_ACTIVE = 0x5E6E28   # main loop renders only while set (0x408061); else the wakeup timer does
HALF = 5                # frames each side for the local camera speed


class Process:
    def __init__(self, pid):
        self.k = k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
        self.handle = k.OpenProcess(0x10, False, pid)  # PROCESS_VM_READ only
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        self.buf = ctypes.create_string_buffer(64)
        self.got = ctypes.c_size_t()

    def read(self, address, size):
        if not self.k.ReadProcessMemory(self.handle, address, self.buf, size, ctypes.byref(self.got)) \
                or self.got.value != size:
            raise ctypes.WinError(ctypes.get_last_error())
        return self.buf.raw[:size]

    def u32(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def close(self):
        self.k.CloseHandle(self.handle)


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))]


def summarize(frames, polls, seconds):
    """Pure statistics over recorded frames (tested without a process)."""
    intervals = [(b["t"] - a["t"]) * 1000 for a, b in zip(frames, frames[1:]) if b["counter"] - a["counter"] == 1]
    world = [(b["clock"] - a["clock"]) & 0xFFFFFFFF for a, b in zip(frames, frames[1:])
             if b["counter"] - a["counter"] == 1]
    steps = [((b["camera"][0] - a["camera"][0]) ** 2 + (b["camera"][1] - a["camera"][1]) ** 2 +
              (b["camera"][2] - a["camera"][2]) ** 2) ** 0.5
             for a, b in zip(frames, frames[1:]) if b["counter"] - a["counter"] == 1]
    missed = sum(b["counter"] - a["counter"] - 1 for a, b in zip(frames, frames[1:]))
    out = {"frames": len(frames), "polls": polls, "seconds": seconds,
           "poll_interval_us": round(seconds / polls * 1e6, 2) if polls else None,
           "missed_counter_steps": missed}
    if intervals:
        out["present_interval_ms"] = {"mean": round(statistics.fmean(intervals), 3),
                                      "stdev": round(statistics.pstdev(intervals), 3),
                                      "p01": round(percentile(intervals, 0.01), 3),
                                      "p50": round(percentile(intervals, 0.5), 3),
                                      "p99": round(percentile(intervals, 0.99), 3),
                                      "max": round(max(intervals), 3)}
        out["fps"] = round(1000 / statistics.fmean(intervals), 2)
        counts = {}
        for w in world:
            counts[w] = counts.get(w, 0) + 1
        out["game_ms_per_frame"] = {str(k): v for k, v in sorted(counts.items())}
        out["frames_without_game_time"] = sum(1 for w in world if w == 0)
        # How far each frame's game-time step is from the real present step.
        out["game_vs_present_rms_ms"] = round(math.sqrt(statistics.fmean(
            [(w - i) ** 2 for w, i in zip(world, intervals)])), 3)
        moving = [s for s in steps if s > 0]
        if len(moving) > len(steps) // 2 and statistics.fmean(intervals) > 0:
            # Speed from the surrounding +-HALF frames, so acceleration (flight
            # control, drag) is not counted as judder; the frame itself is left
            # out of its own estimate.
            errors = []
            for n, (s, i) in enumerate(zip(steps, intervals)):
                window = [k for k in range(max(0, n - HALF), min(len(steps), n + HALF + 1)) if k != n]
                local = sum(steps[k] for k in window) / sum(intervals[k] for k in window)
                if local > 0:
                    errors.append((s - local * i) / (local * statistics.fmean(intervals)))
            out["camera"] = {"units_per_ms": round(sum(steps) / sum(intervals), 4),
                             "frames_without_motion": sum(1 for s in steps if s == 0),
                             "step_error_rms_frames": round(math.sqrt(statistics.fmean([e * e for e in errors])), 4)
                             if errors else None}
    # With frame-clock-v1 the game clock is QPC milliseconds, the same time base
    # as perf_counter: frame start (clock) to the present-time counter step.
    # Measured ~16 ms at 60 Hz: the frame blocks on the previous vsync while
    # rendering, so this is latency, not CPU cost. Meaningless with GetTickCount.
    build = [((f["qpc_ms"] - f["clock"] + 0x80000000) & 0xFFFFFFFF) - 0x80000000 for f in frames if "qpc_ms" in f]
    if build and abs(percentile(build, 0.5)) < 1000:
        out["frame_build_ms"] = {"p50": percentile(build, 0.5), "p90": percentile(build, 0.9),
                                 "p99": percentile(build, 0.99), "max": max(build)}
    active = [f.get("active") for f in frames]
    if active and None not in active:
        out["active_frames"] = sum(1 for a in active if a)
    return out


def record(pid, seconds):
    proc = Process(pid)
    try:
        app = proc.u32(APP_POINTER)
        graphics = proc.u32(GRAPHICS_POINTER)
        if not app or not graphics:
            raise ValueError("client is not in a rendered scene")
        frames, polls = [], 0
        counter_address = app + FRAME_COUNTER
        last = None
        start = time.perf_counter()
        end = start + seconds
        while True:
            now = time.perf_counter()
            if now >= end:
                break
            counter = proc.u32(counter_address)
            polls += 1
            if counter != last:
                clock = proc.u32(GAME_CLOCK)
                camera = struct.unpack("<3f", proc.read(graphics + MAIN_CAMERA + 48, 12))
                active = proc.read(APP_ACTIVE, 1)[0]
                frames.append({"t": now - start, "counter": counter, "clock": clock, "camera": camera,
                               "active": active, "qpc_ms": int(now * 1000) & 0xFFFFFFFF})
                last = counter
        return frames[1:], polls, time.perf_counter() - start  # first sample is mid-frame
    finally:
        proc.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    if not 0 < args.seconds <= 120:
        parser.error("--seconds must be in (0, 120]")
    frames, polls, seconds = record(args.pid, args.seconds)
    summary = {"label": args.label, **summarize(frames, polls, seconds)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "frames": frames}) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
