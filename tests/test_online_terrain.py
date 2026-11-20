"""Execute terrain hook branches in x86 emulation; native rendering is manual."""
import struct
import unittest
import contextlib
import io

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
                               UC_X86_REG_EDX, UC_X86_REG_ESI, UC_X86_REG_EDI,
                               UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP)
from aoa.emulation.emu import Emu, SCRATCH, STACK
from aoa.analysis.pe_util import PE
from aoa.client.asm import jmp_patch
from aoa.client.patches import online_terrain as terrain
from aoa.maps import registry
from aoa.client import prepare
from aoa.host.server import flight_bootstrap
from aoa.host.runtime import parse_args
from aoa.paths import ROOT
from aoa.client.patches import base as patching

SOURCE = ROOT / "game/2.9.2/AOACLIENT.EXE.orig"
from tests.support_patches import needs_game


@needs_game
class TerrainTests(unittest.TestCase):
    def probe(self, marker=registry.MARKER, existing=False, asset=True, world=True, controller=True,
              expect_name=None, code=None, zones=(), handler=True, view=True, boxes=None):
        emu = Emu(PE(SOURCE))
        uc = emu.uc
        emu.write(terrain.SITE, jmp_patch(terrain.SITE, terrain.CAVE, 5))
        emu.write(terrain.CAVE, code or terrain.cave_code())
        w, ctl, gfx = SCRATCH + 0x10000, SCRATCH + 0x8000, SCRATCH + 0x9000
        emu.write(0x5E7728, struct.pack('<I', w if world else 0))
        emu.write(w + 0xDF03C, struct.pack('<I', ctl if controller else 0))
        emu.write(ctl, struct.pack('<I', 1 if existing else 0))
        emu.write(SCRATCH + 0x364, marker)
        # Zone handler safe list: node = {box, ?, next}; flight mode +0x138 = view.
        zone_handler, flight, flight_view = SCRATCH + 0xA000, SCRATCH + 0xC000, SCRATCH + 0xD000
        nodes = [SCRATCH + 0xB000 + i * 0x10 for i in range(len(zones))]
        for node, box, after in zip(nodes, zones, nodes[1:] + [0]):
            emu.write(node, struct.pack('<III', box, 0, after))
        emu.write(zone_handler, struct.pack('<I', nodes[0] if nodes else 0))
        emu.write(w + 0xDF06C, struct.pack('<I', zone_handler if handler else 0))
        emu.write(terrain.FLIGHT_MODE, struct.pack('<I', flight))
        emu.write(flight + 0x138, struct.pack('<I', flight_view if view else 0))
        registers = {UC_X86_REG_EBX: 11, UC_X86_REG_ECX: 12, UC_X86_REG_EDX: 13,
                     UC_X86_REG_ESI: SCRATCH, UC_X86_REG_EDI: 15, UC_X86_REG_EBP: 16,
                     UC_X86_REG_ESP: STACK + 0x80000}
        for reg, value in registers.items():
            uc.reg_write(reg, value)
        calls = []

        def hook(uc, addr, size, _):
            if addr not in (terrain.LOOKUP, terrain.LOAD, terrain.READ_TRN, terrain.ADD_SAFE_ZONE_VISUAL):
                return
            sp = uc.reg_read(UC_X86_REG_ESP)
            ret, arg = struct.unpack('<II', emu.read(sp, 8))
            calls.append(addr)
            if addr == terrain.ADD_SAFE_ZONE_VISUAL:
                self.assertEqual(uc.reg_read(UC_X86_REG_ECX), flight_view)
                if boxes is not None:
                    boxes.append(arg)
                pop = 4
            elif addr == terrain.LOOKUP:
                self.assertEqual(uc.reg_read(UC_X86_REG_ECX), 0x5E7C18)
                expect = (expect_name or 'Arena1a').encode() + b'\0'
                self.assertEqual(emu.read(arg, len(expect)), expect)
                uc.reg_write(UC_X86_REG_EAX, gfx if asset else 0)
                pop = 4
            elif addr == terrain.READ_TRN:
                self.assertEqual(uc.reg_read(UC_X86_REG_ECX), ctl)
                self.assertEqual(emu.read(arg, 13), b'jrmap292.trn\0')
                emu.write(ctl, struct.pack('<I', gfx))
                pop = 4
            else:
                self.assertEqual(uc.reg_read(UC_X86_REG_ECX), ctl)
                self.assertEqual(arg, gfx)
                self.assertEqual(emu.read(sp + 8, 4), bytes(4))
                emu.write(ctl, struct.pack('<I', gfx))
                pop = 8
            uc.reg_write(UC_X86_REG_ECX, 0xDEAD)
            uc.reg_write(UC_X86_REG_EDX, 0xBEEF)
            uc.reg_write(UC_X86_REG_ESP, sp + 4 + pop)
            uc.reg_write(UC_X86_REG_EIP, ret)

        uc.hook_add(UC_HOOK_CODE, hook)
        for _ in range(2):
            uc.emu_start(terrain.SITE, terrain.SITE + 5, count=400)
            self.assertEqual(uc.reg_read(UC_X86_REG_EIP), terrain.SITE + 5)
            self.assertEqual(uc.reg_read(UC_X86_REG_EAX), w if world else 0)
            for reg, value in registers.items():
                self.assertEqual(uc.reg_read(reg), value)
        return calls

    def test_native_call_and_duplicate_guard(self):
        self.assertEqual(self.probe(), [terrain.LOOKUP, terrain.LOAD])

    def test_every_layout_and_file_map(self):
        for name, kind, target, _ in registry.MAPS:
            with self.subTest(name):
                calls = self.probe(marker=registry.marker(name), expect_name=target)
                self.assertEqual(calls, [terrain.READ_TRN] if kind == registry.TRN else [terrain.LOOKUP, terrain.LOAD])

    def test_old_server_and_missing_state(self):
        for args in ({'marker': bytes(4)}, {'existing': True}, {'world': False}, {'controller': False},
                     {'marker': b'MAP' + bytes([len(registry.MAPS)])}, {'marker': b'MAP\xff'},
                     {'marker': b'MAQ\x01'}, {'marker': b'AR1B'}):
            self.assertEqual(self.probe(**args), [])
        self.assertEqual(self.probe(asset=False), [terrain.LOOKUP, terrain.LOOKUP])

    def test_safe_zone_visuals_after_load(self):
        zone = terrain.ADD_SAFE_ZONE_VISUAL
        for name, kind, target, _ in registry.MAPS:
            with self.subTest(name):
                boxes = []
                calls = self.probe(marker=registry.marker(name), expect_name=target,
                                   zones=(0x1111, 0x2222, 0x3333), boxes=boxes)
                self.assertEqual(calls[-3:], [zone] * 3)
                # The second pass finds terrain already loaded and walks nothing.
                self.assertEqual(boxes, [0x1111, 0x2222, 0x3333])
        for args in ({'handler': False}, {'view': False}, {}):
            self.assertEqual(self.probe(zones=(0x1111,) if args else (), **args), [terrain.LOOKUP, terrain.LOAD])
        # No load, no walk: SetupFlightMode already registered whatever existed.
        self.assertEqual(self.probe(existing=True, zones=(0x1111,)), [])
        self.assertEqual(self.probe(asset=False, zones=(0x1111,)), [terrain.LOOKUP, terrain.LOOKUP])

    def test_v2_still_matches_and_upgrades(self):
        self.assertEqual(self.probe(code=terrain.v2_code(), zones=(0x1111,)), [terrain.LOOKUP, terrain.LOAD])
        original = SOURCE.read_bytes()
        v2 = bytearray(patching.apply(terrain.PATCH, original, True))
        v2[(terrain.CAVE - 0x400000):(terrain.CAVE - 0x400000) + terrain.REGION] = terrain.v2_code()
        v2 = bytes(v2)
        self.assertTrue(patching.state(terrain.PATCH, v2))
        self.assertEqual(patching.state(terrain.PATCH, v2), terrain.V2_NAME)
        self.assertEqual(patching.state(terrain.PATCH, patching.apply(terrain.PATCH, original, True)), terrain.NAME)
        self.assertIsNone(patching.state(terrain.PATCH, original))
        self.assertEqual(patching.apply(terrain.PATCH, v2, True), patching.apply(terrain.PATCH, original, True))
        prepared = bytearray(prepare.configure(original))
        prepared[(terrain.CAVE - 0x400000):(terrain.CAVE - 0x400000) + terrain.REGION] = terrain.v2_code()
        self.assertIn(terrain.V2_NAME, prepare.inspect(bytes(prepared))['patches'])
        self.assertEqual(prepare.configure(bytes(prepared)), prepare.configure(original))

    def test_legacy_v1_still_matches_and_upgrades(self):
        self.assertEqual(self.probe(code=terrain.legacy_code()), [terrain.LOOKUP, terrain.LOAD])
        original = SOURCE.read_bytes()
        legacy = bytearray(patching.apply(terrain.PATCH, original, True))
        legacy[(terrain.CAVE - 0x400000):(terrain.CAVE - 0x400000) + terrain.REGION] = terrain.legacy_code()
        legacy = bytes(legacy)
        self.assertTrue(patching.state(terrain.PATCH, legacy))
        self.assertEqual(patching.state(terrain.PATCH, legacy), terrain.LEGACY_NAME)
        self.assertEqual(patching.apply(terrain.PATCH, legacy, True), patching.apply(terrain.PATCH, original, True))

    def test_byte_validation_and_normalization(self):
        original = SOURCE.read_bytes()
        patched = patching.apply(terrain.PATCH, original, True)
        self.assertEqual(patching.apply(terrain.PATCH, patched, False), original)
        self.assertEqual(patching.apply(terrain.PATCH, patched, True), patched)
        for offset in ((terrain.SITE - 0x400000), (terrain.CAVE - 0x400000), (terrain.CAVE - 0x400000) + 0xA0,
                       (terrain.CAVE - 0x400000) + terrain.REGION - 1):
            bad = bytearray(patched)
            bad[offset] ^= 1
            with self.assertRaises(ValueError):
                patching.apply(terrain.PATCH, bad, True)
        prepared = prepare.configure(original)
        self.assertIn(terrain.NAME, prepare.inspect(prepared)['patches'])
        self.assertEqual(prepare.configure(prepared), prepared)

    def test_server_marker_and_scope(self):
        self.assertEqual(flight_bootstrap()[1], (0x2C, bytes(4)))
        self.assertEqual(flight_bootstrap(terrain=registry.marker('Arena1a'))[1], (0x2C, registry.MARKER))
        self.assertEqual(flight_bootstrap(terrain=registry.marker('JRMAP'))[1], (0x2C, b'MAP\x13'))
        with self.assertRaises(ValueError):
            flight_bootstrap(terrain=b'MAP')
        args = ['key', 'log', '--profile', 'local-relay', '--map', 'Arena1a', '--experimental-terrain']
        parsed = parse_args(args)
        self.assertTrue(parsed.terrain)
        self.assertIsNone(parsed.spawn_origin)
        self.assertEqual(parse_args(args + ['--map', 'CTF_base']).spawn_origin, (0.0, 0.0, -12000.0))
        self.assertEqual(parse_args(args + ['--spawn-at', '1', '2', '3']).spawn_origin, (1.0, 2.0, 3.0))
        self.assertIsNone(parse_args(['key', 'log', '--map', 'CTF_base']).spawn_origin)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(args + ['--map', 'NoSuchMap'])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(args + ['--spawn-at', 'nan', '0', '0'])


if __name__ == '__main__':
    unittest.main()
