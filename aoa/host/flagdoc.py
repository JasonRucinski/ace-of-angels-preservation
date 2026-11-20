"""The server flag table of docs/host/server-reference.md, generated from the server's argparse.

  python -I tools/run.py aoa.host.flagdoc            print the table
  python -I tools/run.py aoa.host.flagdoc --check    exit 1 if the docs table is out of date
  python -I tools/run.py aoa.host.flagdoc --write    rewrite the table in docs/host/server-reference.md

The table sits between the two marker comments in that file; the text
around it is written by hand. Hidden aliases (the old --experimental-relay
and --experimental-terrain) are left out, as in --help.
"""
import argparse
import sys

from aoa import cli
from aoa.host.runtime import build_parser


def cell(text):
    return " ".join(str(text).split()).replace("|", "\\|")


def flag_text(action):
    names = [n for n in action.option_strings if n.startswith("--")] or [action.dest]
    if isinstance(action, argparse.BooleanOptionalAction):
        names = [n for n in names if not n.startswith("--no-")]
        return " ".join(f"`{n}`" for n in names) + " (`--no-…` to turn off)"
    metavar = action.metavar
    if isinstance(metavar, tuple):
        metavar = " ".join(metavar)
    if action.option_strings and action.nargs != 0:
        metavar = metavar or ("{" + ",".join(map(str, action.choices)) + "}" if action.choices and
                              len(action.choices) <= 6 else action.dest.upper())
        return " ".join(f"`{n} {metavar}`" for n in names)
    return " ".join(f"`{n}`" for n in names)


def default_text(action):
    default = action.default
    if default is None or default is False or default is argparse.SUPPRESS:
        return ""
    if isinstance(default, float) and default.is_integer():
        default = int(default)
    return f"`{default}`"


def table(parser=None):
    """The Markdown table: one row per flag, grouped as in --help."""
    parser = parser or build_parser()
    rows = ["| Group | Flag | Default | Meaning |", "|---|---|---|---|"]
    for group in parser._action_groups:
        title = {"positional arguments": "arguments", "options": "general"}.get(group.title, group.title)
        for action in group._group_actions:
            if action.help == argparse.SUPPRESS or isinstance(action, argparse._HelpAction):
                continue
            rows.append(f"| {cell(title)} | {flag_text(action)} | {default_text(action)} | {cell(action.help or '')} |")
    return "\n".join(rows) + "\n"


BLOCK = cli.DocBlock("docs/host/server-reference.md", "server flags", "aoa.host.flagdoc", table)
DOC, BEGIN, END = BLOCK.path, BLOCK.begin, BLOCK.end
splice = BLOCK.splice  # splice(text, table) -> text with the generated block replaced


def main(argv=None):
    return BLOCK.main(argv, __doc__)


if __name__ == "__main__":
    raise SystemExit(main())
