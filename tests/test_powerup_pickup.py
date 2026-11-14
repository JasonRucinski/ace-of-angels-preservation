"""Run the client's own power-up code in x86, with and without powerup-pickup-v1.

ReceiveSpawnPowerup (0x431D30) runs with object allocation, model loading,
naming, positioning and logging stubbed; SetTerrainType and the countdown
(0x49ABD0) with its show/hide (0x49CD70 -> 0x542A90) run unmodified.
"""
import struct
import sys
import unittest
from pathlib import Path

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI,
                               UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EIP)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import powerup_pickup
import prepare_client

ORIGINAL = Path(__file__).resolve().parents[1] / "game/2.9.2/AOACLIENT.EXE.orig"
SPAWN, COUNTDOWN, SHOW = 0x431D30, 0x49ABD0, 0x49CD70
WORLD_PTR, FLIGHT_VIEW_PTR = 0x5E7728, 0x5E6E58
PACKET, OBJ, GFX, WORLD, VIEW = 0x800000, 0x810000, 0x820000, 0x900000, 0x830000
RETURN, STACK = 0x7F0F00, 0x7F8000
# Stubbed callees of ReceiveSpawnPowerup: address -> (name, bytes of arguments popped).
STUBS = {0x4A5960: ("AllocNewObject", 12), 0x4E0660: ("script detach", 4), 0x4A7F90: ("LoadModel", 12),
         0x49C750: ("SetName", 8), 0x4BE970: ("SetPosition", 12), 0x526D00: ("log", 0)}
SAVED = {UC_X86_REG_EBX: 0x1111, UC_X86_REG_EBP: 0x4444, UC_X86_REG_EDI: 0x3333}


def machine(image):
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    pe = pefile.PE(data=image, fast_load=True)
    mapped = pe.get_memory_mapped_image()
    u.mem_map(0x400000, (len(mapped) + 0xFFFF) & ~0xFFFF)
    u.mem_write(0x400000, mapped)
    for base, size in ((PACKET, 0x10000), (OBJ, 0x10000), (GFX, 0x10000), (VIEW, 0x10000),
                       (WORLD, 0x100000), (0x7F0000, 0x10000)):
        u.mem_map(base, size)
    u.mem_write(WORLD_PTR, struct.pack("<I", WORLD))
    u.mem_write(FLIGHT_VIEW_PTR, struct.pack("<I", VIEW))
    u.mem_write(VIEW + 0x1C0, b"\x01")           # In flight: skip the watchdog branch
    u.mem_write(OBJ + 0x19C, struct.pack("<I", GFX))
    return u


def call(u, entry, this, args, esi=0x2222):
    sp = STACK - 0x100
    u.mem_write(sp, struct.pack("<I", RETURN) + b"".join(struct.pack("<I", a) for a in args))
    for reg, value in {**SAVED, UC_X86_REG_ESI: esi, UC_X86_REG_ESP: sp, UC_X86_REG_ECX: this}.items():
        u.reg_write(reg, value)
    u.emu_start(entry, RETURN, count=2000)
    assert u.reg_read(UC_X86_REG_ESP) == sp + 4 + 4 * len(args), "stack balance"
    assert all(u.reg_read(reg) == value for reg, value in SAVED.items()), "callee-saved registers"
    assert u.reg_read(UC_X86_REG_ESI) == esi, "esi preserved"


def spawn(image, position, kind, tag):
    """Object fields after ReceiveSpawnPowerup, plus the stubbed calls."""
    u = machine(image)
    u.mem_write(OBJ + 0x2FB, b"\x01")            # As AllocNewObject's init (0x49A040) leaves it
    u.mem_write(PACKET + 0x364, struct.pack("<3iBI", *position, kind, tag))
    calls = []

    def stub(uc, address, size, _):
        name, popped = STUBS[address]
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret = struct.unpack("<I", uc.mem_read(esp, 4))[0]
        args = struct.unpack(f"<{popped // 4}I", uc.mem_read(esp + 4, popped)) if popped else ()
        calls.append((name, uc.reg_read(UC_X86_REG_ECX), args))
        uc.reg_write(UC_X86_REG_EAX, OBJ if name == "AllocNewObject" else 1)
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + popped)
        uc.reg_write(UC_X86_REG_EIP, ret)

    for address in STUBS:
        u.hook_add(UC_HOOK_CODE, stub, begin=address, end=address)
    call(u, SPAWN, PACKET, [], esi=0x2222)
    obj = bytes(u.mem_read(OBJ, 0x360))
    return obj, calls


def tick(image, countdown, elapsed, hidden=True):
    """(+0x2F7 shown, model +0x150 enabled, +0x338) after one object update."""
    u = machine(image)
    if hidden:
        call(u, SHOW, OBJ, [0])                  # What CollideWithPowerup / MovePowerupTo do
    else:
        u.mem_write(OBJ + 0x2F7, b"\x01")
        u.mem_write(GFX + 0x150, b"\x01")
    u.mem_write(OBJ + 0x338, struct.pack("<i", countdown))
    call(u, COUNTDOWN, OBJ, [elapsed])
    obj, gfx = u.mem_read(OBJ, 0x360), u.mem_read(GFX, 0x200)
    return obj[0x2F7], gfx[0x150], struct.unpack_from("<i", obj, 0x338)[0]


class PowerupPickupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = prepare_client.configure(ORIGINAL.read_bytes())
        cls.unpatched = powerup_pickup.configure(cls.prepared, False)

    def test_spawn_is_collidable_only_with_the_patch(self):
        for image, collidable in ((self.unpatched, 0), (self.prepared, 1)):
            with self.subTest(patched=bool(collidable)):
                obj, calls = spawn(image, (-4330, 13438, 150), 3, 0x40000065)
                self.assertEqual(obj[0x2FB], collidable)
                self.assertEqual(struct.unpack_from("<II", obj, 0x1F4), (6, 6))       # type, kind
                self.assertEqual(struct.unpack_from("<I", obj, 0x200)[0], 4)        # displaced store kept
                self.assertEqual((obj[0x210], obj[0x211]), (1, 3))
                self.assertEqual(struct.unpack_from("<I", obj, 0x1D0)[0], 10)
                self.assertEqual(calls[0], ("AllocNewObject", WORLD, (1, 0xFFFFFFFF, 0x40000065)))
                position = next(args for name, _, args in calls if name == "SetPosition")
                self.assertEqual(struct.unpack("<3f", struct.pack("<3I", *position)), (-4330.0, 13438.0, 150.0))

    def test_bad_type_creates_nothing_collidable(self):
        obj, calls = spawn(self.prepared, (0, 0, 0), 5, 0x40000064)
        self.assertEqual(obj[0x210], 0)
        self.assertNotIn("LoadModel", [name for name, _, _ in calls])

    def test_expiry_reenables_the_model_only_with_the_patch(self):
        self.assertEqual(tick(self.unpatched, 100, 200), (1, 0, 0))    # Shown flag only: never drawn
        self.assertEqual(tick(self.prepared, 100, 200), (1, 1, 0))
        self.assertEqual(tick(self.prepared, 16, 16), (1, 1, 0))       # Exactly zero also expires

    def test_running_and_idle_countdowns_are_unchanged(self):
        for image in (self.unpatched, self.prepared):
            self.assertEqual(tick(image, 5000, 16), (0, 0, 4984))
            self.assertEqual(tick(image, 0, 16), (0, 0, 0))            # Hidden by a pickup, no move yet
            self.assertEqual(tick(image, 0, 16, hidden=False), (1, 1, 0))

    def test_prepared_by_default_reversible_and_rejects_corruption(self):
        self.assertIn(powerup_pickup.NAME, prepare_client.inspect(self.prepared)["patches"])
        self.assertNotIn(powerup_pickup.NAME, prepare_client.inspect(self.unpatched)["patches"])
        self.assertEqual(prepare_client.configure(ORIGINAL.read_bytes(), powerup_pickups=False), self.unpatched)
        self.assertEqual(prepare_client.configure(self.unpatched), self.prepared)
        self.assertEqual(powerup_pickup.configure(self.prepared), self.prepared)
        for va in (powerup_pickup.SPAWN_SITE, powerup_pickup.CAVE, powerup_pickup.EXPIRY_SITE + 6):
            bad = bytearray(self.prepared)
            bad[va - 0x400000] ^= 0xFF
            with self.assertRaises(ValueError):
                powerup_pickup.configure(bytes(bad))
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(bad))


if __name__ == "__main__":
    unittest.main()
