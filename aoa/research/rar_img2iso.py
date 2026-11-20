"""The old name of `aoa.research.disc_image rar`; the research log's tool table of 20 October 2026 names it.

    python -I tools/run.py aoa.research.rar_img2iso disc.rar "Disc.img" disc.iso
"""
import sys

from aoa import cli
from aoa.research import disc_image


def main(argv=None):
    return disc_image.main(["rar", *(sys.argv[1:] if argv is None else argv)])


if __name__ == "__main__":
    sys.exit(cli.run(main))
