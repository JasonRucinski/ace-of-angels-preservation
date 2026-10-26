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
    def test_original_client_prefix_comparison(self):
        from emulate_codec import Emu, SCRATCH
        from pe_util import PE
        from patch_client import PRISTINE_292
        from unicorn import UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP
        client = Path(__file__).resolve().parents[1] / 'game/2.9.2/AOACLIENT.EXE.orig'
        self.assertEqual(hashlib.sha256(client.read_bytes()).hexdigest(), PRISTINE_292)
        emu = Emu(PE(client))

        def crt(uc, address, size, _):
            if address not in (0x57D70E, 0x57D59E):
                return
            sp = uc.reg_read(UC_X86_REG_ESP)
            ret, arg = struct.unpack('<II', emu.read(sp, 8))
            if address == 0x57D59E:
                value = arg - 32 if 97 <= arg <= 122 else arg
            else:
                char = int.from_bytes(emu.read(sp + 8, 4), 'little')
                data = emu.read(arg, 128).split(b'\0')[0]
                at = data.find(bytes([char]))
                value = arg + at if at >= 0 else 0
            uc.reg_write(UC_X86_REG_EAX, value)
            uc.reg_write(UC_X86_REG_ESP, sp + 4)
            uc.reg_write(UC_X86_REG_EIP, ret)

        emu.uc.hook_add(UC_HOOK_CODE, crt)
        for stored, query, expected in [('HyBase2Lay', 'HyBase2La', True),
                                         ('ast_fld_d', 'AST_FLD_', True),
                                         ('ast_fld_a', 'ast_fld_', True),
                                         ('ast_fld_d', 'ast_fld_a', False),
                                         ('HyBase2La', 'HyBase2Lay', False)]:
            emu.write(SCRATCH, struct.pack('<III', SCRATCH + 256, len(stored), 0))
            emu.write(SCRATCH + 256, stored.encode() + bytes(128))
            emu.write(SCRATCH + 512, query.encode() + bytes(128))
            self.assertEqual(bool(emu.thiscall(0x5270C0, SCRATCH, SCRATCH + 512, 0) & 255), expected)

    def test_native_prefix_order_and_ambiguous_unproven_order(self):
        paths = [Path('ast_fld_d.Gob'), Path('ast_fld_a.Gob')]
        self.assertEqual(scene2obj.resolve_layout('AST_FLD_', (paths, True)), paths[0])
        self.assertIsNone(scene2obj.resolve_layout('ast_fld_', (paths, False)))
        self.assertEqual(scene2obj.resolve_layout('ast_fld_a', (paths, False)), paths[1])
        self.assertIsNone(scene2obj.resolve_layout('', (paths, True)))
        self.assertIsNone(scene2obj.resolve_layout('absent', (paths, True)))

    def test_recovered_truncated_layout_references(self):
        outer = list(scene2obj.expanded_nodes(SOURCE, 'outerchange', True))
        self.assertEqual(len(outer), 1035)
        truncated = [n for n in outer if n.get('layout_lookup') == 'ast_fld_']
        self.assertEqual(len(truncated), 5)
        self.assertTrue(all(n['nested_layout'] == 'ast_fld_d' for n in truncated))
        bases = [n for n in outer if n.get('layout_lookup') == 'HyBase2La']
        self.assertEqual(len(bases), 1)
        self.assertEqual(bases[0]['nested_layout'], 'HyBase2Lay')
        self.assertEqual(len(list(scene2obj.expanded_nodes(SOURCE, 'irrosa01', True))), 775)

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
