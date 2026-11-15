"""Read-only bounded sampling of a known 2.9.2 client, without breakpoints.

Usage: python -I tools/run.py aoa.live.sample_rendering PID OUTPUT.json --seconds 10
Snapshots are non-atomic: a frame can advance between individual reads.
They diagnose state/renderer differences, not GPU frame times or smoothness.
"""
import argparse
import json
import time
from pathlib import Path

from aoa.live.arena import snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args(argv)
    if not 0 < args.seconds <= 60:
        parser.error("duration must be greater than zero and at most 60 seconds")
    samples = []
    end = time.perf_counter() + args.seconds
    while time.perf_counter() < end:
        started = time.perf_counter()
        item = snapshot(args.pid, True, True)
        samples.append({"start": started, "end": time.perf_counter(), **item})
        time.sleep(max(0, 0.02 - (time.perf_counter() - started)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(samples))
    print(json.dumps({"samples": len(samples), "active_samples": sum(bool(s["app_active"]) for s in samples),
                      "frame_ticks": len({s["frame_tick"] for s in samples}),
                      "joystick_axes": samples[-1]["joystick_axes"]}))


if __name__ == "__main__":
    main()
