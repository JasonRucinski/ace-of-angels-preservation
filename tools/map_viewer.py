"""Command shim for aoa.maps.map_viewer; `serve` runs through aoa.launchers.serve (HostConfig)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aoa.launchers import serve  # noqa: E402
from aoa.maps.map_viewer import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(serve=serve.map_viewer))
