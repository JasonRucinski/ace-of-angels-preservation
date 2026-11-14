"""Command shim for aoa.launchers.client_launcher; the code lives there."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aoa.launchers.client_launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
