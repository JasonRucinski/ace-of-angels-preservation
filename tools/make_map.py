"""Command shim for aoa.maps.make_map; the code lives there."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aoa.maps.make_map import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
