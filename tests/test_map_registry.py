"""The map registry (aoa/maps/registry.py) is complete, pure data and agrees with docs/STATUS.md; game-free.

    python -I tools/test.py test_map_registry
"""
import ast
import collections
import unittest

from aoa.maps import registry
from aoa.paths import ROOT


class Registry(unittest.TestCase):
    def test_every_map_has_content_and_notes(self):
        self.assertEqual(set(registry.CONTENT), set(registry.MAP_NAMES))
        self.assertEqual(set(registry.NOTES), set(registry.MAP_NAMES))
        self.assertLessEqual(set(registry.CONTENT.values()),
                             {registry.PLAYABLE, registry.COMPONENT, registry.EMPTY})

    def test_counts_match_status(self):
        # docs/STATUS.md#maps: 20 entries, 11 with real content, 5 small components, 4 empty.
        counts = collections.Counter(registry.CONTENT.values())
        self.assertEqual(len(registry.MAPS), 20)
        self.assertEqual(counts, {registry.PLAYABLE: 11, registry.COMPONENT: 5, registry.EMPTY: 4})
        status = (ROOT / "docs/STATUS.md").read_text(encoding="utf-8")
        self.assertIn("**11 have real content:**", status)
        self.assertIn("**5 are small components**", status)
        self.assertIn("**4 build nothing alone:**", status)

    def test_markers(self):
        self.assertEqual(registry.MAP_NAMES[0], "Arena1a")
        self.assertEqual(registry.marker("Arena1a"), b"AR1A")
        self.assertEqual(registry.marker("JRMAP"), b"MAP\x13")
        self.assertEqual(len({registry.marker(n) for n in registry.MAP_NAMES}), len(registry.MAP_NAMES))
        self.assertEqual(registry.spawn("JRMAP"), (-6000.0, -6000.0, -112000.0))
        self.assertIsNone(registry.spawn("Arena1a"))

    def test_imports_nothing(self):
        tree = ast.parse((ROOT / "aoa/maps/registry.py").read_text(encoding="utf-8"))
        self.assertEqual([n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))], [])


if __name__ == "__main__":
    unittest.main()
