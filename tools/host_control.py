"""Command shim for the host window, aoa.launchers.host_app (Host.cmd opens it)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aoa.launchers.host_app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
