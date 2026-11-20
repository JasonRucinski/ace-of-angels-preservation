"""The old name of `aoa.research.ia_fulltext context`; the research log's tool table of 20 October 2026 names it.

    python -I tools/run.py aoa.research.ia_fulltext_context data/
"""
import sys

from aoa import cli
from aoa.research import ia_fulltext


def main(argv=None):
    return ia_fulltext.main(["context", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(cli.run(main))
