"""Run test suites, each in its own `python -I` process, and summarize.

  python -I tools/test.py --tier ci          the game-free suites CI runs
  python -I tools/test.py --tier local       the local gate's suites (need the game)
  python -I tools/test.py --tier all         every suite under tests/, and the archived ones
  python -I tools/test.py test_station_stub test_reel
  python -I tools/test.py test_cli_help -- -k fetch_known_builds

Prints one line per suite and a summary; exits non-zero if any suite fails.
Arguments after `--` are passed to every suite (unittest's -k, -v, or a
suite's own --update). Suites are listed in tests/tiers.py.
"""
import argparse
import re
import subprocess
import sys
import time

from aoa.paths import ROOT
from tests import tiers

# The child puts the repository on sys.path (-I leaves it off) and runs the
# suite module as __main__, as `python -I tools/<suite>.py` did before.
BOOT = ("import runpy, sys; root, name = sys.argv[1:3]; sys.path[:0] = [root]; "
        "sys.argv = [sys.argv[0], *sys.argv[3:]]; "
        "runpy.run_module(name, run_name='__main__', alter_sys=True)")
TIMEOUT = 900


def module(name):
    """tests.<name> for a bare suite name, else the dotted name as given."""
    return name if "." in name else f"tests.{name}"


def command(name, *args):
    """The child process that runs one suite."""
    return [sys.executable, "-I", "-c", BOOT, str(ROOT), module(name), *args]


def every_suite():
    return sorted(p.stem for p in (ROOT / "tests").glob("test_*.py"))


def tier(name):
    if name == "ci":
        return list(tiers.CI) + (list(tiers.CI_WINDOWS) if sys.platform == "win32" else [])
    if name == "local":
        return list(tiers.LOCAL)
    return every_suite() + list(tiers.ARCHIVED)


def summary(output):
    """(tests run or None, skipped) from unittest's closing lines."""
    ran = re.search(r"^Ran (\d+) tests? in", output, re.M)
    skipped = re.search(r"skipped=(\d+)", output)
    return (int(ran[1]) if ran else None), (int(skipped[1]) if skipped else 0)


def run(name, args=(), stream=False):
    """Run one suite; return (exit code, output, seconds)."""
    start = time.monotonic()
    try:
        result = subprocess.run(command(name, *args), cwd=ROOT, text=True, timeout=TIMEOUT,
                                stdin=subprocess.DEVNULL,
                                **({} if stream else {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT}))
        code, output = result.returncode, result.stdout or ""
    except subprocess.TimeoutExpired as error:
        code, output = 1, f"{error.output or ''}\ntimed out after {TIMEOUT} s"
    return code, output, time.monotonic() - start


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("suites", nargs="*", help="suite names (default: --tier ci)")
    ap.add_argument("--tier", choices=("ci", "local", "all"), help="run the suites of a tier")
    ap.add_argument("-v", "--verbose", action="store_true", help="show each suite's own output as it runs")
    argv = sys.argv[1:] if argv is None else list(argv)
    extra = []
    if "--" in argv:
        at = argv.index("--")
        argv, extra = argv[:at], argv[at + 1:]
    args = ap.parse_args(argv)
    if args.suites and args.tier:
        ap.error("give suite names or --tier, not both")
    names = args.suites or tier(args.tier or "ci")
    known = set(every_suite()) | set(tiers.ARCHIVED)
    unknown = [n for n in names if n not in known]
    if unknown:
        ap.error(f"no such suite: {', '.join(unknown)}")
    failed = []
    for name in names:
        if args.verbose:
            print(f"== {name}", flush=True)
        code, output, seconds = run(name, extra, stream=args.verbose)
        ran, skipped = summary(output)
        counts = "" if args.verbose else (f"ran {ran}, skipped {skipped}" if ran is not None else "did not run")
        print(f"{'PASS' if code == 0 else 'FAIL'}  {name:<55} {counts:<22} {seconds:6.1f}s", flush=True)
        if code != 0:
            failed.append((name, output))
    for name, output in failed:
        if output:
            print(f"\n== {name} (exit non-zero), last lines:\n" + "\n".join(output.rstrip().splitlines()[-40:]))
    print(f"\n{len(names) - len(failed)} of {len(names)} suites passed"
          + (f"; failed: {', '.join(n for n, _ in failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
