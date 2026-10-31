"""Scout maps for filming: object positions plus an F5 screenshot at the spawn.

  python -I tools/reel/scout.py MAP [MAP ...] [--out work/reel/scout]

Enters flight on each map like record.py, then writes MAP.json (native
terrain objects with names and positions, from tools/inspect_arena.py) and
copies the client's F5 capture to MAP.tga. F5 reads the game's own frame,
so this works with the display off.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import inspect_arena  # noqa: E402
import record  # noqa: E402
import window  # noqa: E402

CAPTURES = record.GAME / "Capture Images"


def latest_capture():
    files = sorted(CAPTURES.glob("AoAImg*.tga"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def scout(name, out, spawn_at=None, camera="cockpit"):
    shot = {"name": name, "map": name, "target_ships": 0}
    if spawn_at:
        shot["spawn_at"] = spawn_at
    record.kill_clients()
    host = record.start_host(shot, out / f"{name}.jsonl")
    try:
        client = record.enter_flight()
        time.sleep(7)
        client.camera(camera)
        snap = inspect_arena.snapshot(client.pid, include_objects=True)
        before = latest_capture()
        window.key(window.main_window(), 0x74)  # F5
        deadline = time.monotonic() + 10
        while latest_capture() == before and time.monotonic() < deadline:
            time.sleep(0.2)
        time.sleep(1.5)  # let the 8 MB TGA finish writing
        if latest_capture() != before:
            shutil.copy(latest_capture(), out / f"{name}.tga")
        objects = [{"name": o["name"], "position": [round(v) for v in o["position"]]}
                   for o in snap.get("terrain_objects", [])]
        (out / f"{name}.json").write_text(json.dumps({"player": snap["active_players"][:1], "objects": objects}))
        client.camera("cockpit")
        return len(objects)
    finally:
        record.kill_clients()
        record.stop_host(host)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("maps", nargs="+")
    parser.add_argument("--out", type=Path, default=record.ROOT / "work/reel/scout")
    parser.add_argument("--spawn-at", type=float, nargs=3)
    parser.add_argument("--camera", default="cockpit")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.maps:
        try:
            print(name, scout(name, args.out, args.spawn_at, args.camera), "objects", flush=True)
        except Exception as error:
            print(name, "failed:", repr(error), flush=True)


if __name__ == "__main__":
    main()
