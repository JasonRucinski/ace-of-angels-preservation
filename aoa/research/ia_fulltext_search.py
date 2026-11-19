"""The old name of `aoa.research.ia_fulltext search`; data/magazine-mentions.md still names it.

    python -I tools/run.py aoa.research.ia_fulltext_search data/
"""
import sys

from aoa import cli
from aoa.research import ia_fulltext


def main(argv=None):
    return ia_fulltext.main(["search", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(cli.run(main))
