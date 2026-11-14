"""Command shim for aoa.research.ia_disc_find; the code lives there."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aoa import cli  # noqa: E402
from aoa.research.ia_disc_find import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.run(main))
