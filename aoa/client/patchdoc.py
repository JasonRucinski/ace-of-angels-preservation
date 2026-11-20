"""The patch table of docs/reference/client-patches.md, generated from the patch registry.

  python -I tools/run.py aoa.client.patchdoc            print the table
  python -I tools/run.py aoa.client.patchdoc --check    exit 1 if the docs table is out of date
  python -I tools/run.py aoa.client.patchdoc --write    rewrite the table in docs/reference/client-patches.md

One row per patch of REGISTRY (aoa/client/patches/__init__.py), in the
order prepare applies them: its ID, the patch level it arrived in, how it is
applied, the `prepare` flag and launcher checkbox of an option, its group
and default, what it requires and conflicts with, and the older variants
prepare still recognizes and upgrades. The table sits between two marker
comments; the text around it is written by hand.
"""
import sys

from aoa import cli
from aoa.client import prepare
from aoa.client.patches import BY_ID, REGISTRY

APPLIED = {"base": "always (stability base)", "always": "always", "option": "option"}


def code(values):
    return ", ".join(f"`{v}`" for v in values)


def flags(patch):
    """`--flag` (`--older-name`), or what an option patch without a flag follows."""
    if not patch.option:
        leaders = [BY_ID[r].option for r in patch.requires if BY_ID[r].option]
        return ", ".join(f"follows `{prepare.flag(o)}`" for o in leaders)
    text = f"`{prepare.flag(patch.option)}`"
    if patch.option in prepare.FLAG_ALIASES:
        text += f" (`{prepare.FLAG_ALIASES[patch.option]}`)"
    return text


def cell(text):
    return text.replace("|", "\\|")


def table():
    rows = ["| Patch | Level | Applied | Flag (older name) | Launcher checkbox | Group | Default "
            "| Requires | Conflicts with | Older variants |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for p in REGISTRY:
        default = ("on" if p.default else "off") if p.option else ""
        rows.append(" | ".join([
            f"| `{p.id}`", "4 to 10" if p.since is None else str(p.since), APPLIED[p.policy], flags(p),
            cell(p.label or ""), p.group or "", default, code(p.requires), code(p.conflicts),
            code(v for v, _ in p.legacy)]) + " |")
    return "\n".join(rows) + "\n"


BLOCK = cli.DocBlock("docs/reference/client-patches.md", "patch table", "aoa.client.patchdoc", table)


def main(argv=None):
    return BLOCK.main(argv, __doc__)


if __name__ == "__main__":
    sys.exit(cli.run(main))
