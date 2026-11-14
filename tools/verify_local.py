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
sys.path.insert(0, str(ROOT))
from tests import runner, tiers  # noqa: E402

# The suites and emulation checks are listed in tests/tiers.py (LOCAL, EMULATION).
SUITES = tiers.LOCAL
EMULATORS = tiers.EMULATION


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "work/local-verification.json")
    args = parser.parse_args(argv)
    client = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"
    report = {"schema": 1, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "synthetic loopback and isolated original-code emulation; excludes real-client UI, combat, collision, internet, clean-machine install and performance release gates",
              "python": sys.version.split()[0], "checks": [], "passed": False}
    commands = [(name, runner.command(name), True) for name in SUITES]
    for name in EMULATORS:
        # Reports stay local by default; callers can inspect before committing.
        output = args.report.parent / (name.rpartition(".")[2] + ".json")
        commands.append((name, [sys.executable, "-I", str(ROOT / "tools/run.py"), name, str(client), str(output)],
                         False))
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
