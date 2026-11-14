"""Run a module's command line: python -I tools/run.py aoa.analysis.explore ARGS

  python -I tools/run.py --list                       every runnable module
  python -I tools/run.py aoa.formats.trn --help       that module's own help

A module is runnable when it ends in an `if __name__ == "__main__":` block
(test suites run through tools/test.py instead).
run.py executes it as __main__, as `python -I tools/<old name>.py` did
before the move; commands people use also keep a tools/<name>.py shim.
Archived scripts run the same way (archive.analysis.pe_facts).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import argparse  # noqa: E402
import ast  # noqa: E402
import re  # noqa: E402
import runpy  # noqa: E402

MAIN = re.compile(r"""^if __name__ == ['"]__main__['"]""", re.M)
PACKAGES = ("aoa", "archive")


def runnable():
    """{dotted module name: first line of its docstring} for every module with a __main__ block."""
    found = {}
    for package in PACKAGES:
        for path in sorted((ROOT / package).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            if MAIN.search(source) and not path.name.startswith("test_"):
                name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
                doc = ast.get_docstring(ast.parse(source)) or ""
                found[name] = doc.strip().splitlines()[0] if doc.strip() else ""
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = argparse.ArgumentParser(prog="run.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list every runnable module and exit")
    ap.add_argument("module", nargs="?", help="dotted module name, e.g. aoa.formats.trn")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="arguments for the module")
    # Everything after the module name belongs to the module, --help included.
    first = next((i for i, a in enumerate(argv) if not a.startswith("-")), len(argv))
    args = ap.parse_args(argv[:first + 1])
    if args.list:
        modules = runnable()
        width = max(map(len, modules))
        for name, summary in modules.items():
            print(f"{name:<{width}}  {summary}")
        return 0
    if not args.module:
        ap.error("give a module name, or --list")
    if args.module not in runnable():
        ap.error(f"{args.module} is not a runnable module (see --list)")
    sys.argv = [args.module, *argv[first + 1:]]
    runpy.run_module(args.module, run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
