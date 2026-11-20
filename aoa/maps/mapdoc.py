"""The map table of docs/reference/maps.md, generated from the map registry.

  python -I tools/run.py aoa.maps.mapdoc            print the table
  python -I tools/run.py aoa.maps.mapdoc --check    exit 1 if the docs table is out of date
  python -I tools/run.py aoa.maps.mapdoc --write    rewrite the table in docs/reference/maps.md

One row per entry of MAPS in aoa/maps/registry.py, in index order: the
name, how the client loads it, its content class, the objects a real client
built (23 Oct 2026) and the registry's note. The table sits between two
marker comments; the text around it is written by hand.
"""
import re
import sys

from aoa import cli
from aoa.maps import registry

LOADERS = {registry.LAYOUT: "layout", registry.TRN: "2.0.0 `.TRN`"}
OBJECTS = re.compile(r"^(\d+) objects?(?:;\s*|\s+|$)")


def objects_and_note(name):
    """('239', 'main arena') from the registry note '239 objects; main arena'."""
    note = registry.NOTES[name]
    m = OBJECTS.match(note)
    if m:
        return m[1], note[m.end():]
    return ("0" if registry.CONTENT[name] == registry.EMPTY else ""), note


def spawn_text(name):
    spawn = registry.spawn(name)
    return "origin" if spawn is None else "(" + ", ".join(f"{v:g}" for v in spawn) + ")"


def table():
    rows = ["| # | Map | Loader | Content | Viewing spawn | Loaded | Note |",
            "|---:|---|---|---|---|---:|---|"]
    for index, (name, kind, _source, _spawn) in enumerate(registry.MAPS):
        count, note = objects_and_note(name)
        rows.append(f"| {index} | {name} | {LOADERS[kind]} | {registry.CONTENT[name]} | {spawn_text(name)} "
                    f"| {count} | {note} |")
    return "\n".join(rows) + "\n"


BLOCK = cli.DocBlock("docs/reference/maps.md", "map table", "aoa.maps.mapdoc", table)


def main(argv=None):
    return BLOCK.main(argv, __doc__)


if __name__ == "__main__":
    sys.exit(cli.run(main))
