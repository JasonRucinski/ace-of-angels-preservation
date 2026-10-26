"""Prove bounded 2.9.2 extension hooks in isolation, without launching the game.

Usage: python -I tools/emulate_client_extensions.py CLIENT.EXE.orig OUT.json
Passing these probes does not complete the authoritative-client gate.
"""
import hashlib
import json
import random
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explicit_protection as protection
import prepare_client
from emulate_codec import Emu, HEAP, SCRATCH, STACK, STOP
from patch_client import PRISTINE_292
from pe_util import PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_ESI,
                               UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_EDI, UC_X86_REG_EAX,
                               UC_X86_REG_ECX)


def protection_probe(path, patched):
    emu = Emu(PE(path))
    comm, world = HEAP, SCRATCH
    messages = []
    registers = (UC_X86_REG_ESI, UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_EDI)

    def hook(uc, address, size, _):
        if address == protection.RESUME:
            uc.emu_stop()
        elif address == 0x446E50:  # cdecl status text sink, not gameplay
            sp = uc.reg_read(UC_X86_REG_ESP)
            messages.append(struct.unpack("<I", emu.read(sp + 4, 4))[0])
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", emu.read(sp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, sp + 4)

    emu.uc.hook_add(UC_HOOK_CODE, hook)
    emu.write(protection.WORLD_POINTER, struct.pack("<I", world))
    emu.write(world + protection.FLAG - 4, b"\xA5" * 9)

    def receive(body, initial, length=None, null_world=False):
        emu.write(protection.WORLD_POINTER, struct.pack("<I", 0 if null_world else world))
        emu.write(world + protection.FLAG, bytes([initial]))
        emu.write(comm + 0x364, body.ljust(16, b"\xCC"))
        emu.write(comm + 0x7E4, struct.pack("<I", len(body) if length is None else length))
        sp = STACK + 0xE0000
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        for register, value in zip(registers, (comm, 0x11111111, 0x22222222, 0x33333333)):
            emu.uc.reg_write(register, value)
        before = len(messages)
        emu.uc.emu_start(protection.SITE, STOP, count=1000)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == protection.RESUME
        assert emu.uc.reg_read(UC_X86_REG_ESP) == sp
        assert [emu.uc.reg_read(r) for r in registers] == [comm, 0x11111111, 0x22222222, 0x33333333]
        assert emu.read(world + protection.FLAG - 4, 4) == b"\xA5" * 4
        assert emu.read(world + protection.FLAG + 1, 4) == b"\xA5" * 4
        return emu.read(world + protection.FLAG, 1)[0], len(messages) - before

    if not patched:
        assert receive(b"\x01", 0) == (1, 1)
        assert receive(b"\x01", 1) == (0, 1)
        return {"duplicate_enable_inverts_state": True}
    cases = 0
    for initial in (0, 1):
        for desired in range(256):
            expected = desired if desired <= 1 else initial
            assert receive(bytes([desired]), initial) == (expected, int(expected != initial))
            cases += 1
        for length in (0, 2, 509, 0xFFFFFFFF):
            assert receive(b"\x01", initial, length=length) == (initial, 0)
            cases += 1
        assert receive(b"\x01", initial, null_world=True) == (initial, 0)
        cases += 1
    current = 0
    for desired in (1, 1, 1, 0, 0, 1, 0):
        current, notifications = receive(bytes([desired]), current)
        assert current == desired
        cases += 1
    return {"cases": cases, "idempotent": True, "malformed_values_ignored": True,
            "stack_callee_saved_and_adjacent_memory_preserved": True,
            "scope": "receive case and original ToggleNodam; status text sink mocked; no damage/rendering"}


def position_probe(path):
    emu = Emu(PE(path))
    rng = random.Random(20261021)
    cases = [(0, 0, 0), (1000, 0, 6000), (-1000, 20, -6000)]
    cases += [tuple(rng.uniform(-1e6, 1e6) for _ in range(3)) for _ in range(100)]
    for xyz in cases:
        emu.write(HEAP, b"\xA5" * 0x100)
        packed = struct.pack("<3f", *xyz)
        emu.thiscall(0x4BE970, HEAP, *struct.unpack("<3I", packed))
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        expected = bytearray(b"\xA5" * 0x100)
        expected[0x2C:0x38] = packed
        expected[0x6C:0x78] = packed
        assert emu.read(HEAP, 0x100) == bytes(expected)
    return {"cases": len(cases), "entry": "0x4BE970", "actual_and_target_updated": True,
            "scope": "original position setter only; excludes orientation, velocity, prediction and rendering"}


def input_probe(path):
    """Run the original command dispatcher, with its UI-mode query mocked."""
    emu = Emu(PE(path))
    world, handler, command = SCRATCH, HEAP, HEAP + 0x1000
    motion = world + 0xD32B0
    emu.write(protection.WORLD_POINTER, struct.pack("<I", world))

    def hook(uc, address, size, _):
        if address == 0x453130:
            sp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EAX, 0)
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", emu.read(sp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, sp + 4)

    emu.uc.hook_add(UC_HOOK_CODE, hook)
    rows = []
    for identifier, mask, offset, value in (
            (4, 8, 0xDC, -110.0), (5, 8, 0xDC, 110.0),
            (6, 4, 0xD8, -114.0), (7, 4, 0xD8, 114.0),
            (8, 16, 0xE0, -108.0), (9, 16, 0xE0, 108.0),
            (11, 1, None, None), (12, 32, None, None), (15, 0x40000, None, None),
            (16, 0x400, None, None), (17, 0x800, None, None),
            (18, 0x100, None, None), (19, 0x200, None, None)):
        emu.write(motion, bytes(0x120))
        for field, scale in ((0x10C, 108), (0x110, 110), (0x114, 114)):
            emu.write(motion + field, struct.pack("<H", scale))
        emu.write(command + 0x40, struct.pack("<HHI", identifier, 0, 1))
        emu.thiscall(0x442140, handler, command)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        assert struct.unpack("<I", emu.read(motion + 0xF0, 4))[0] == mask
        if offset is not None:
            assert struct.unpack("<f", emu.read(motion + offset, 4))[0] == value
        rows.append({"command": identifier, "mask": hex(mask),
                     "field": hex(offset) if offset is not None else None, "fixture_value": value})
    return {"entry": "0x442140", "cases": len(rows), "commands": rows,
            "scope": "decoded command object to kinematic controls; UI-mode query mocked; no keyboard, joystick, transport or physics",
            "unresolved": "command names, physical units, input sampling, release behavior and sequenced transport"}


def ammunition_probe(path):
    emu = Emu(PE(path))
    values = (-10, -1, 0, 1, 2, 16, 100, 0x7FFFFFFF)
    for value in values:
        emu.write(HEAP, b"\xA5" * 0x100)
        emu.thiscall(0x4DD280, HEAP, value & 0xFFFFFFFF)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        expected = bytearray(b"\xA5" * 0x100)
        expected[0x24] = 1
        expected[0x50:0x54] = struct.pack("<I", max(0, value))
        expected[0x54] = int(value > 0)
        assert emu.read(HEAP, 0x100) == bytes(expected)
    return {"entry": "0x4DD280", "cases": len(values), "negative_clamped_to_zero": True,
            "capacity_enforced_by_setter": False,
            "scope": "isolated rack count setter called by original death reset; no inventory selection or network handler"}


def protection_consumers_probe(path):
    """Verify the actual damage/munition branch, not just the toggle name."""
    emu = Emu(PE(path))
    stops = {0x49BD58, 0x49BF8D, 0x4B145E, 0x4B148C}

    def hook(uc, address, size, _):
        if address in stops:
            uc.emu_stop()

    emu.uc.hook_add(UC_HOOK_CODE, hook)
    for enabled in (0, 1):
        emu.write(HEAP + 0x240, bytes([enabled]))
        emu.uc.reg_write(UC_X86_REG_EDI, HEAP)
        emu.uc.reg_write(UC_X86_REG_EBX, 0)
        emu.uc.emu_start(0x49BD4C, STOP, count=20)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == (0x49BF8D if enabled else 0x49BD58)
        for override in (0, 1):
            sp = STACK + 0xE0000
            emu.uc.reg_write(UC_X86_REG_ESP, sp)
            emu.uc.reg_write(UC_X86_REG_ECX, HEAP)
            emu.write(sp + 0x1C, struct.pack("<I", SCRATCH))
            emu.write(SCRATCH + 0xDEF20, struct.pack("<I", override))
            emu.uc.emu_start(0x4B1446, STOP, count=30)
            assert emu.uc.reg_read(UC_X86_REG_EIP) == (0x4B148C if enabled and not override else 0x4B145E)
    return {"cases": 6, "damage_branch_skipped_when_protected": True,
            "missile_ammo_decrement_skipped_when_protected_and_override_zero": True,
            "scope": "isolated original branch execution; not full damage, missile or gun simulation",
            "blocker": "legacy invulnerability also changes ammo consumption; it is not a complete spawn-protection policy"}


def health_reset_probe(path):
    """Execute the original reset with a synthetic ship/system list."""
    emu = Emu(PE(path))
    player, ship, shield, system, node, vtable = (HEAP + i * 0x1000 for i in range(6))
    method = 0x40000200
    gun_system = [False]

    def hook(uc, address, size, _):
        # Isolate name/profile lookup and the system-kind virtual query.
        if address not in (0x4D6D80, 0x4CDA80, method):
            return
        sp = uc.reg_read(UC_X86_REG_ESP)
        value = shield if address == 0x4D6D80 else int(gun_system[0]) if address == method else 0
        uc.reg_write(UC_X86_REG_EAX, value)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", emu.read(sp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, sp + (4 if address == method else 8))

    emu.uc.hook_add(UC_HOOK_CODE, hook)
    emu.write(protection.WORLD_POINTER, struct.pack("<I", SCRATCH))
    emu.write(player + 0x194, struct.pack("<I", ship))
    emu.write(ship + 0xAC, struct.pack("<I", node))
    emu.write(node + 0x10, struct.pack("<I", system))
    emu.write(system, struct.pack("<I", vtable))
    emu.write(vtable + 0x1C, struct.pack("<I", method))
    for is_gun in (False, True):
        gun_system[0] = is_gun
        for base, maximum, current, value in ((shield, 0x6C, 0x88, 12.5),
                                               (ship, 0x84, 0x80, 99.5),
                                               (system, 0x6C, 0x88, 47.25)):
            emu.write(base + maximum, struct.pack("<f", value))
            emu.write(base + current, struct.pack("<f", 1.0))
        emu.write(system + 0x100, struct.pack("<H", 77))
        emu.thiscall(0x49BB60, player)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        for base, current, value in ((shield, 0x88, 12.5), (ship, 0x80, 99.5), (system, 0x88, 47.25)):
            assert struct.unpack("<f", emu.read(base + current, 4))[0] == value
        assert struct.unpack("<H", emu.read(system + 0x100, 2))[0] == (0 if gun_system[0] else 77)
    return {"entry": "0x49BB60", "cases": 2, "configured_health_restored": True,
            "scope": "nonlocal player reset with synthetic ship and one system; lookups and kind query mocked; inventory-profile loop excluded",
            "remaining": "local death callback, arbitrary health correction and server-owned respawn state"}


def main():
    source, output = map(Path, sys.argv[1:])
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != PRISTINE_292:
        raise ValueError("requires hash-pinned original 2.9.2 client")
    prepared = prepare_client.configure(original, experimental_protection=True)
    with tempfile.TemporaryDirectory(prefix="aoa-extension-probe-") as tmp:
        patched = Path(tmp) / "patched.exe"
        patched.write_bytes(prepared)
        result = {"source_sha256": PRISTINE_292,
                  "patched_sha256": hashlib.sha256(prepared).hexdigest(),
                  "patch": protection.NAME,
                  "original_protection": protection_probe(source, False),
                  "patched_protection": protection_probe(patched, True),
                  "position": position_probe(source),
                  "input_commands": input_probe(source),
                  "ammunition": ammunition_probe(source),
                  "protection_consumers": protection_consumers_probe(source),
                  "health_reset": health_reset_probe(source),
                  "authoritative_client_gate_passed": False,
                  "remaining": ["real-client protection and position checks", "control input capture",
                                "orientation and prediction correction", "health and ammunition setters",
                                "hold-dead and respawn release", "world readiness",
                                "session/entity generations before dispatch", "ordered application acknowledgments"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
