"""tools/README.md is the current output of aoa.tools_index; game-free.

When this fails, regenerate it: python -I tools/run.py aoa.tools_index --write

    python -I tools/test.py test_tools_index
"""
import unittest

from aoa import tools_index
from aoa.paths import ROOT


class ToolsIndex(unittest.TestCase):
    def test_committed_index_is_current(self):
        committed = (ROOT / "tools/README.md").read_text(encoding="utf-8")
        self.assertEqual(committed, tools_index.render(),
                         "tools/README.md is out of date: python -I tools/run.py aoa.tools_index --write")

    def test_every_command_and_module_is_listed(self):
        text = tools_index.render()
        for path in (ROOT / "tools").glob("*.py"):
            self.assertIn(f"| `{path.name}` |", text)
        for package in ("aoa", "archive"):
            for path in (ROOT / package).rglob("*.py"):
                if path.name != "__init__.py" and "__pycache__" not in path.parts:
                    self.assertIn(f"| `{tools_index.module_name(path)}` |", text)

    def test_shims_are_marked(self):
        rows = dict(tools_index.commands())
        self.assertTrue(rows["prepare_client.py"].startswith("*shim* for `aoa.client.prepare`"))
        self.assertTrue(rows["fetch_known_builds.py"].startswith("*shim* for `aoa.research.fetch.known_builds`"))
        self.assertFalse(rows["verify_local.py"].startswith("*shim*"))


if __name__ == "__main__":
    unittest.main()
