"""Execute world visibility and child selection together in the original x86."""
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import asteroid_render
import object_persistence as patch
import prepare_client
import solid_world_render
import station_detail
import visibility_fix
import world_detail
from audit_object_lod import audit
from emulate_codec import Emu, SCRATCH, STACK, STUBS
from pe_util import Disasm, PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_FPCW,
                               UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_EFLAGS,
                               UC_X86_REG_EDI)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"


class GroupProbe:
    def __init__(self, distant=False, extras=()):
        self.emu = e = Emu(PE(SOURCE))
        for module in (visibility_fix, *extras, *((patch,) if distant else ())):
            for offset, _, new in module.regions():
                e.write(offset + 0x400000, new)
        # Only the C runtime's x87 asin/acos calls are replaced. All group,
        # distance, projected-size and mesh-selection instructions are original.
        self.input, self.output = SCRATCH + 0x9000, SCRATCH + 0x9010
        functions = {}
        for i, (iat, fn) in enumerate(((0x58C368, math.asin), (0x58C364, math.acos))):
            stub = STUBS + 0x400 + i * 0x20
            e.write(iat, struct.pack("<I", stub))
            e.write(stub, b"\xdd\x1d" + struct.pack("<I", self.input)
                    + b"\xdd\x05" + struct.pack("<I", self.output) + b"\xc3")
            functions[stub + 6] = fn

        def trig(uc, address, size, _):
            if address in functions:
                value = struct.unpack("<d", e.read(self.input, 8))[0]
                e.write(self.output, struct.pack("<d", functions[address](value)))
        e.uc.hook_add(UC_HOOK_CODE, trig, begin=STUBS + 0x400, end=STUBS + 0x440)

    def run(self, meshes, distance=100_000., radius=100., control=0x7F, enabled=True, behind=False):
        e = self.emu
        node, camera, context = SCRATCH, SCRATCH + 0xA000, SCRATCH + 0xB000
        e.write(node, bytes(0x400))
        e.write(node + 0xAC, struct.pack("<3f", 0, 0, -distance if behind else distance))
        e.write(node + 0x164, struct.pack("<f", radius))
        e.write(node + 0x150, bytes([enabled, 0, 1]))
        e.write(node + 0x234, struct.pack("<I", SCRATCH + 0x8000))
        e.write(node + 0x33A, b"\1")
        for i, mesh in enumerate(meshes):
            child, link = SCRATCH + 0x1000 + i * 0x400, SCRATCH + 0x8000 + i * 0x20
            e.write(child, bytes(0x400))
            e.write(child + 0x180, struct.pack("<2f", *mesh["screen_size_range"]))
            e.write(link, bytes(0x20))
            e.write(link + 8, struct.pack("<I", link + 0x20 if i + 1 < len(meshes) else 0))
            e.write(link + 0x10, struct.pack("<I", child))
        e.write(camera, bytes(0x100))
        e.write(camera + 0x70, struct.pack("<3f", 0, 0, 1))
        e.write(context, bytes(0x100))
        e.write(context + 8, struct.pack("<f", 960))
        sp = STACK + 0x8000
        e.write(sp, struct.pack("<3I", 0, camera, context))
        e.uc.reg_write(UC_X86_REG_ECX, node)
        e.uc.reg_write(UC_X86_REG_ESP, sp)
        e.uc.reg_write(UC_X86_REG_FPCW, control)
        e.uc.emu_start(0x546B20, 0x546C10, count=10_000)
        assert e.uc.reg_read(UC_X86_REG_ESP) == sp - 0x2C
        assert e.uc.reg_read(UC_X86_REG_FPCW) == control
        return {
            "visible": bool(e.read(node + 0x151, 1)[0]),
            "size": struct.unpack("<f", e.read(node + 0x17C, 4))[0],
            "range": struct.unpack("<2f", e.read(node + 0x180, 8)),
            "selected": [i for i in range(len(meshes))
                         if e.read(SCRATCH + 0x1000 + i * 0x400 + 0x152, 1) == b"\1"],
        }


class ObjectPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models = audit(ROOT / "work/2.9.2/export/AOAOBJECTS")["models"]
        assert len(cls.models) == 154
        cls.simple = [{"screen_size_range": [5., 4096.]}]

    def test_complete_group_remains_visible_beyond_both_old_limits(self):
        original, distant = GroupProbe(), GroupProbe(True)
        for control in (0x7F, 0x27F, 0x37F):
            for distance in (60_000., 61_100., 500_000., 900_000., 2_000_000., 4_499_999.):
                # Size stays above 0.5 even at the new surface-distance horizon.
                old = original.run(self.simple, distance, radius=1500, control=control)
                new = distant.run(self.simple, distance, radius=1500, control=control)
                self.assertEqual(old["visible"], distance - 1500 < 61_000)
                self.assertTrue(new["visible"], (distance, control, new))
                self.assertEqual(new["selected"], [0])
                self.assertEqual(old["size"], new["size"])
            for surface in (patch.HORIZON - 1, patch.HORIZON, patch.HORIZON + 1):
                result = distant.run(self.simple, surface + 1500, radius=1500, control=control)
                self.assertEqual(result["visible"], surface < patch.HORIZON)

    def test_small_objects_persist_ten_times_farther_with_normal_guards(self):
        original, distant = GroupProbe(), GroupProbe(True)
        # radius 100 -> size 5 at distance 38,400, size 0.5 at 384,000.
        for distance in (38_399., 38_400., 38_401., 100_000., 383_999., 384_000., 384_001.):
            old, new = original.run(self.simple, distance), distant.run(self.simple, distance)
            self.assertEqual(old["visible"], distance < 38_400)
            self.assertEqual(new["visible"], distance < 384_000)
            self.assertEqual(new["size"], old["size"])
        self.assertFalse(distant.run(self.simple, enabled=False)["visible"])
        self.assertFalse(distant.run(self.simple, behind=True)["visible"])
        self.assertFalse(distant.run(self.simple, distance=0)["visible"])

    def test_all_models_keep_valid_distant_lod_and_unchanged_near_selection(self):
        original, distant = GroupProbe(), GroupProbe(True)
        for model in self.models:
            meshes = model["meshes"]
            minimum = min(m["screen_size_range"][0] for m in meshes)
            expected_far = [i for i, m in enumerate(meshes)
                            if m["screen_size_range"][0] <= max(minimum, 1.) < m["screen_size_range"][1]]
            with self.subTest(model=model["model"]):
                far = distant.run(meshes, distance=192_000, radius=100)
                self.assertTrue(far["visible"])
                self.assertTrue(far["selected"])
                self.assertEqual(far["selected"], expected_far)
                self.assertEqual(far["size"], 1.)
                boundaries = {v for m in meshes for v in m["screen_size_range"]}
                for size in sorted({4000.} | {v + d for v in boundaries for d in (-.01, 0, .01)
                                               if max(5., minimum) < v + d <= 4000}):
                    old = original.run(meshes, distance=10_000, radius=size * 10_000 / 1920)
                    new = distant.run(meshes, distance=10_000, radius=size * 10_000 / 1920)
                    self.assertEqual(old["selected"], new["selected"])
                    self.assertEqual(old["size"], new["size"])

    def test_existing_optional_render_modes_compose(self):
        raw = SOURCE.read_bytes()
        for options in ({}, {"experimental_asteroids": True}, {"experimental_solids": True},
                        {"experimental_station_detail": True},
                        {"experimental_solids": True, "experimental_world_detail": True}):
            before = prepare_client.configure(raw, **options)
            after = prepare_client.configure(before, distant_objects=True)
            self.assertEqual(prepare_client.configure(after), after)
            self.assertEqual(prepare_client.configure(after, distant_objects=False), before)
            self.assertIn(patch.NAME, prepare_client.inspect(after)["patches"])
        dock = next(m["meshes"] for m in self.models if m["model"] == "newdock")
        for extra in (asteroid_render, solid_world_render, station_detail, world_detail):
            result = GroupProbe(True, (extra,)).run(dock, distance=192_000)
            self.assertTrue(result["visible"])
            self.assertTrue(result["selected"])

    def test_constant_reference_scope_and_cave_abi(self):
        pe = PE(SOURCE)
        with tempfile.TemporaryDirectory() as folder:
            dis = Disasm(pe, Path(folder) / "code.pkl")
            self.assertEqual(dis.refs[0x5B0C30], [0x543222])
            self.assertEqual(dis.refs[0x59D9C0], [0x4ED36A])
            self.assertEqual(dis.refs_to_func(0x543000), [0x546BCE])
        self.assertLessEqual(station_detail.CAVE + len(station_detail.code()), patch.CAVE)
        e = GroupProbe(True).emu
        sp = STACK + 0x8000
        e.write(sp + 4, struct.pack("<f", 200))
        e.uc.reg_write(UC_X86_REG_ESP, sp)
        e.uc.reg_write(UC_X86_REG_EAX, 0x12345678)
        e.uc.reg_write(UC_X86_REG_ECX, 0x87654321)
        e.uc.reg_write(UC_X86_REG_EFLAGS, 0x247)
        e.uc.emu_start(patch.GROUP_SITE, patch.GROUP_SITE + len(patch.GROUP_ORIGINAL), count=100)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), sp - 4)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EAX), 0x12345678)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_ECX), 0x87654321)
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EFLAGS), 0x247)
        self.assertEqual(e.read(sp + 0xC, 4), struct.pack("<f", 200))
        self.assertEqual(e.uc.reg_read(UC_X86_REG_EDX), 0x3F000000)
        # The child hook must restore the original test-edi flags: the very
        # next instruction uses ZF to skip an empty child list.
        for size in (1., 200., 300.):
            for children in (0, 123):
                e = GroupProbe(True).emu
                e.uc.reg_write(UC_X86_REG_ESP, sp)
                e.uc.reg_write(UC_X86_REG_ECX, struct.unpack("<I", struct.pack("<f", size))[0])
                e.uc.reg_write(UC_X86_REG_EDI, children)
                e.uc.reg_write(UC_X86_REG_EAX, 0x12345678)
                e.uc.reg_write(UC_X86_REG_EDX, 0x87654321)
                e.write(sp + 0x14, struct.pack("<f", 200))
                e.uc.emu_start(patch.CHILD_SITE, patch.CHILD_SITE + len(patch.CHILD_ORIGINAL), count=100)
                self.assertEqual(e.read(sp + 0x34, 4), struct.pack("<f", max(size, 200)))
                self.assertEqual(bool(e.uc.reg_read(UC_X86_REG_EFLAGS) & 0x40), children == 0)
                self.assertEqual(e.uc.reg_read(UC_X86_REG_ESP), sp)
                self.assertEqual(e.uc.reg_read(UC_X86_REG_EAX), 0x12345678)
                self.assertEqual(e.uc.reg_read(UC_X86_REG_EDX), 0x87654321)

    def test_transaction_exact_undo_and_nondefault_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "AOACLIENT.EXE"
            exe.write_bytes(SOURCE.read_bytes())
            prepare_client.prepare(exe, host="127.0.0.1", smooth_frame_clock=False,
                                   chase_camera=False, powerup_pickups=False)
            before = exe.read_bytes()
            patch.install(exe)
            after = exe.read_bytes()
            self.assertEqual(patch.configure(after, False), before)
            self.assertIn(patch.NAME, prepare_client.check(exe, require_assets=False)["patches"])
            patch.install(exe)
            self.assertEqual(exe.read_bytes(), after)
            patch.install(exe, undo=True)
            self.assertEqual(exe.read_bytes(), before)
            patch.install(exe, undo=True)
            self.assertEqual(exe.read_bytes(), before)
            exe.with_suffix(".EXE.before-object-persistence").write_bytes(b"wrong")
            with self.assertRaises(ValueError):
                patch.install(exe)
            self.assertEqual(exe.read_bytes(), before)

    def test_byte_scope_partial_corruption_and_backup_rejection(self):
        before = prepare_client.configure(SOURCE.read_bytes())
        after = prepare_client.configure(before, distant_objects=True)
        allowed = {i for off, old, _ in patch.regions() for i in range(off, off + len(old))}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(before, after))))
        for offset, old, new in patch.regions():
            partial = bytearray(before)
            partial[offset:offset + len(new)] = new
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(partial))
            corrupt = bytearray(after)
            corrupt[offset] ^= 1
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(corrupt))
        unrelated = bytearray(after)
        unrelated[0x12345] ^= 1
        with self.assertRaises(ValueError):
            prepare_client.inspect(bytes(unrelated))


if __name__ == "__main__":
    unittest.main()
