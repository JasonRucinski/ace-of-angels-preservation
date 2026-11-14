"""Repository paths: ROOT, the ignored WORK folder, and the tools/ command scripts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"


def entry(name, root=ROOT):
    """tools/<name>.py, the command script that runs a tool as its own process."""
    return Path(root) / "tools" / f"{name}.py"
