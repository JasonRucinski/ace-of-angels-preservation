"""Recovered layout parser regression and nested transform checks."""
import collections
import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene2obj

SOURCE = Path(__file__).resolve().parents[1] / "work/2.9.2/export/AOAOBJECTS"


class SceneNodeTests(unittest.TestCase):
    def test_arena1a_records_including_exporter_text(self):
        data = (SOURCE / "Arena1a.Gob").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), "5d652eaca4972d958eb1dc54b8ef277fdb8ea475be4912f01a5fd8d02afa7886")
        nodes = scene2obj.read_nodes(data)
        self.assertEqual(len(nodes), 383)
        self.assertEqual(collections.Counter(n["category"] for n in nodes), {1: 80, 4: 10, 5: 18, 6: 9, 7: 4, 9: 262})
        turrets = [n for n in nodes if n["category"] == 1]
        self.assertTrue(all(n["exporter_text"].startswith("*Type: Dummy") for n in turrets))
        self.assertEqual(len({n["source_offset"] for n in nodes}), len(nodes))
        for node in nodes:
            self.assertEqual(node["matrix"][12:15], node["position"])
        altered = bytearray(data)
        # Category metadata must not silently bleed into the following node.
        offset = nodes[0]["category_offset"]
        altered[offset:offset + 4] = bytes(4)
        with self.assertRaises(ValueError):
            scene2obj.read_nodes(altered)

    def test_ctf_inventory_unchanged(self):
        self.assertEqual(len(scene2obj.read_nodes((SOURCE / "CTF_arena.Gob").read_bytes())), 119)

    def test_nested_layout_transform_and_cycle_guard(self):
        identity = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]
        child = identity.copy()
        child[12:15] = [2., 3., 4.]
        # 90-degree Z rotation followed by translation. Row-vector convention.
        parent = [0., 1., 0., 0., -1., 0., 0., 0., 0., 0., 1., 0., 10., 20., 30., 1.]
        self.assertEqual(scene2obj.compose(child, parent)[12:15], [7., 22., 34.])
        nodes = list(scene2obj.expanded_nodes(SOURCE, "Arena1a", True))
        self.assertEqual(len(nodes), 394)
        nested = [n for n in nodes if n["source_scene"] == "HyBase2Lay"]
        self.assertEqual(len(nested), 11)
        self.assertTrue(all(n["node_path"].startswith("HyBase2Lay/") for n in nested))
        with self.assertRaises(ValueError):
            list(scene2obj.expanded_nodes(SOURCE, "Arena1a", True, ancestors=("arena1a",)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
