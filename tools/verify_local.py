"""Run the supported local regression gate; does not launch a real client.

Requires the user's original 2.9.2 EXE/assets and installed test dependencies.
Any missing source, failed test, skipped test or failed emulator fails the gate.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = ("test_network_bounds.py", "test_relay_motion.py", "test_prepare_client.py",
          "test_station_runtime.py", "test_station_sessions.py", "test_guest_admission.py",
          "test_relay_recovery.py", "test_station_stub.py", "test_combat_delivery.py",
          "test_client_extensions.py", "test_lan_dogfight.py", "test_scene_nodes.py",
          "test_online_terrain.py", "test_host_control.py", "test_asteroid_render.py", "test_solid_world_render.py",
          "test_station_detail.py", "test_world_detail.py", "test_internet_play.py", "test_cursor_warp.py",
          "test_texture32.py", "test_aoapack_write.py", "test_frame_clock.py",
          "test_visibility_fix.py", "test_render_culling.py", "test_third_person.py", "test_powerups.py",
          "test_powerup_pickup.py", "test_target_ships.py")
EMULATORS = ("emulate_station_request.py", "emulate_station_aliases.py", "emulate_reliable_history.py",
             "emulate_movement.py", "emulate_motion_state.py",
             "emulate_archive_terminator.py", "emulate_client_extensions.py",
             "emulate_ordered_events.py", "emulate_terrain_nodes.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "work/local-verification.json")
    args = parser.parse_args()
    client = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"
    report = {"schema": 1, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "synthetic loopback and isolated original-code emulation; excludes real-client UI, combat, collision, internet, clean-machine install and performance release gates",
              "python": sys.version.split()[0], "checks": [], "passed": False}
    commands = [(name, [sys.executable, "-I", str(ROOT / "tools" / name)], True) for name in SUITES]
    for name in EMULATORS:
        # Reports stay local by default; callers can inspect before committing.
        output = args.report.parent / (Path(name).stem + ".json")
        commands.append((name, [sys.executable, "-I", str(ROOT / "tools" / name), str(client), str(output)], False))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if not client.is_file():
        report["error"] = "missing original 2.9.2 executable"
    else:
        for name, command, is_suite in commands:
            start = time.monotonic()
            print(f"Checking {name}", flush=True)
            try:
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
                output = result.stdout + result.stderr
                count = re.search(r"Ran (\d+) tests? in", output) if is_suite else None
                passed = result.returncode == 0 and "skipped=" not in output and (not is_suite or count is not None)
                check = {"name": name, "passed": passed, "seconds": round(time.monotonic() - start, 3)}
                if count:
                    check["tests"] = int(count[1])
                if not passed:
                    check["failure"] = output[-8000:]
                report["checks"].append(check)
                print(f"  {'PASS' if passed else 'FAIL'} ({check['seconds']}s)", flush=True)
                if not passed:
                    break
            except (subprocess.TimeoutExpired, OSError) as error:
                report["checks"].append({"name": name, "passed": False, "failure": str(error)})
                break
        report["passed"] = len(report["checks"]) == len(commands) and all(item["passed"] for item in report["checks"])
    report["tests"] = sum(item.get("tests", 0) for item in report["checks"])
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Local gate {'PASSED' if report['passed'] else 'FAILED'}: {report['tests']} tests; report {args.report}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
