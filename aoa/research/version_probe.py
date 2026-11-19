"""The old name of `tools/aoa_version.py CLIENT --detail`; docs/research/findings.md still names it.

Usage: python -I tools/run.py aoa.research.version_probe <client.exe> [<cache.pkl>] <out.json>

Runs aoa.research.version with these arguments (an old CACHE argument is ignored: the
disassembly cache is kept by the client's SHA-256).
"""
import sys

from aoa import cli
from aoa.research.version import main

if __name__ == "__main__":
    sys.exit(cli.run(main))
