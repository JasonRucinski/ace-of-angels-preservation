"""The old name of `aoa.research.disc_image iso`; the research log's tool table of 20 October 2026 names it.

    7z e -so dvd.7z image.mdf | python -I tools/run.py aoa.research.iso_stream_extract '(?i)angel|aoa' outdir
"""
import sys

from aoa import cli
from aoa.research import disc_image


def main(argv=None):
    return disc_image.main(["iso", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(cli.run(main))
