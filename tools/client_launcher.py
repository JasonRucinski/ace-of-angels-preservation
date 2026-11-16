"""Command shim for the player window, aoa.launchers.play_app (Play.cmd opens it)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aoa.launchers.play_app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
