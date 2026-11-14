"""Shared command-line conventions for the tools in this folder.

Every tool has `main(argv=None)` built on `parser()`, does no work at import,
and ends with

    if __name__ == "__main__":
        sys.exit(cli_util.run(main))

so `--help` only prints usage, and a missing or unreadable input ends with one
line on stderr and a non-zero exit instead of a traceback.
"""
import argparse
import sys
from pathlib import Path

from aoa.paths import ROOT
WORK = ROOT / "work"


def parser(doc, **kwargs):
    """An ArgumentParser whose help shows the module docstring as written."""
    kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
    return argparse.ArgumentParser(description=doc, **kwargs)


def output_dir(value):
    """argparse type for an output folder: refuses a name that looks like an option."""
    if not value or value.startswith("-"):
        raise argparse.ArgumentTypeError(f"refusing output folder {value!r}: give a real folder name")
    return value


def add_evidence_option(ap, committed):
    """--evidence PATH for an audit whose committed copy is `committed` (repo-relative).

    Without it the audit writes to work/<committed>, so a re-run never
    overwrites committed evidence by accident.
    """
    ap.add_argument("--evidence", type=Path, metavar="PATH",
                    help=f"write the result to PATH instead of work/{committed} "
                         f"(the committed copy is {committed})")


def evidence_target(chosen, committed):
    """The --evidence PATH if given, else work/<committed>; its parent folder is created."""
    target = Path(chosen) if chosen else WORK / committed
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def shown(path):
    """A path for messages: repo-relative when inside the repository."""
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def run(main, argv=None):
    """Call main(argv); turn a missing or unreadable file into a one-line error."""
    try:
        return main(argv)
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError) as error:
        name = Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "tool"
        detail = error.strerror or str(error)
        where = f": {error.filename}" if error.filename else ""
        sys.exit(f"{name}: error: {detail}{where}")
