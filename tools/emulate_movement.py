"""Check filtered movement lengths with the original 2.9.2 decoder.

Usage: python -I tools/emulate_movement.py CLIENT.EXE OUT.json
Runs isolated x86 code in Unicorn; no client process or network.
"""
import hashlib
import json
import math
import random
import struct
import sys
from pathlib import Path

from unicorn import UcError
from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_EAX

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, HEAP, SCRATCH, STACK, STOP
from pe_util import PE
from station_stub import movement_update, reported_motion, motion_snapshot
import relay_motion
from physics_timestep import SITE, CAVE, DISPLACED, guard_code
from patch_client import jmp_patch


GUN_COUNTERS = SCRATCH + 0x4000  # Outside the zeroed context and body.


def main():
    source, output = sys.argv[1:]
    pe = PE(source)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e":
        raise ValueError("requires original 2.9.2 client")
    emu = Emu(pe)

    def decode(mask, body):
        emu.write(HEAP, bytes(0x4000))
        emu.write(SCRATCH, bytes(0x100))
        # Receiver supplies kinematics, stats and object destinations. Leave
        # the unsupported optional destination at +4 null deliberately.
        for off, pointer in ((0, HEAP), (0x10, HEAP + 0x1000), (0x14, HEAP + 0x2000)):
            emu.write(SCRATCH + off, struct.pack("<I", pointer))
        # Decoder object: per-system counter array {ptr, count}. The live
        # client has 5000 entries; the relay's index bound is 128.
        emu.write(GUN_COUNTERS, bytes(4 * relay_motion.MAX_SYSTEM_INDEX))
        emu.write(HEAP + 0x3000, struct.pack("<II", GUN_COUNTERS, relay_motion.MAX_SYSTEM_INDEX))
        # Remote player with an empty system container (+0xAC list null):
        # 0x4D4820 then finds no system, as for an unknown index.
        emu.write(HEAP + 0x2000 + 0x194, struct.pack("<I", HEAP + 0x2800))
        emu.write(SCRATCH + 0x1000, body + bytes(512))
        consumed = emu.thiscall(0x495330, HEAP + 0x3000, SCRATCH + 0x1000, SCRATCH, mask)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        return consumed

    # Confirm the dangerous path is exercised by the regression setup.
    try:
        decode(0x80000000, struct.pack("<I", 1) + bytes(32))
    except UcError:
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x49598C
    else:
        raise AssertionError("expected unsupported destination write")

    rng = random.Random(20261021)
    masks = [1 << bit for bit in range(27)] + [0xD1207381, 0xFFFFFFFF]
    masks += [rng.getrandbits(32) for _ in range(200)]
    for mask in masks:
        packet = movement_update(struct.pack("<HHI", 0x8000, 1, mask) + bytes(256), 1)
        assert packet is not None
        filtered = struct.unpack_from("<I", packet, 4)[0]
        assert decode(filtered, packet[8:]) == len(packet) - 8, hex(mask)

    # A relayed per-gun fire-state block (live capture: guns 2..7 at 15)
    # plus the highest permitted index is consumed exactly and stays in
    # bounds; the guard word after the array must remain untouched.
    records = [(index, 15) for index in range(2, 8)] + [(relay_motion.MAX_SYSTEM_INDEX - 1, 1)]
    block = bytes([0x80 | len(records)]) + b"".join(struct.pack("<HB", i, v) for i, v in records)
    packet = movement_update(struct.pack("<HHI", 0x8000, 1, 0x10000040) + bytes(12) + block, 1)
    assert struct.unpack_from("<I", packet, 4)[0] == 0x10000040
    emu.write(GUN_COUNTERS + 4 * relay_motion.MAX_SYSTEM_INDEX, b"\xEE" * 16)
    assert decode(0x10000040, packet[8:]) == len(packet) - 8
    counters = struct.unpack(f"<{relay_motion.MAX_SYSTEM_INDEX}I",
                             emu.read(GUN_COUNTERS, 4 * relay_motion.MAX_SYSTEM_INDEX))
    assert {i for i, c in enumerate(counters) if c} == {i for i, _ in records}
    assert emu.read(GUN_COUNTERS + 4 * relay_motion.MAX_SYSTEM_INDEX, 16) == b"\xEE" * 16
    assert emu.read(HEAP + 0x2000 + 0x1A4, 1) == b"\x01"
    gun_cases = 1

    # A server-built stats-only 0x80000000 block (submask 0x100) after the
    # prefix and gun state: consumed exactly; the stats struct (ctx+0x10)
    # gets kills/deaths/score and the valid flag, the rating lands at
    # ctx+0x2E, and no other submask part (unset pointers) is touched.
    snap = relay_motion.snapshot(1, {0x40: (1.0, 2.0, 3.0), relay_motion.GUN_STATE: (0x81, ((2, 15),))},
                                 stats=(3, 2, 7, 1234))
    mask = struct.unpack_from("<I", snap, 4)[0]
    assert mask == 0x90000040
    assert decode(mask, snap[8:]) == len(snap) - 8
    stats = emu.read(HEAP + 0x1000, 0x24)
    assert struct.unpack_from("<hhi", stats, 0) == (3, 2, 1234) and stats[0x20] == 1
    assert struct.unpack_from("<h", emu.read(SCRATCH + 0x2E, 2))[0] == 7
    stats_cases = 1

    # Check that nonzero absolute movement reaches its actual destination.
    coords = struct.pack("<3f", 123.0, -456.0, 789.0)
    assert decode(0x40, coords) == 12
    assert emu.read(HEAP + 0x6C, 12) == coords
    initial = ((123.0, -456.0, 789.0), (1.5, -2.5, 3.5))
    for mask, fmt, delta in ((2, "3h", (300, -400, 500)), (4, "3b", (1, -2, 3))):
        _, packet = motion_snapshot(1, initial)
        decode(0x41, packet[8:])
        body = struct.pack("<" + fmt, *delta)
        emu.write(SCRATCH + 0x1000, body)
        consumed = emu.thiscall(0x495330, HEAP + 0x3000, SCRATCH + 0x1000, SCRATCH, mask)
        assert consumed == len(body)
        expected = reported_motion(struct.pack("<HHI", 0x8000, 1, mask) + body, initial)
        assert struct.unpack("<3f", emu.read(HEAP + 0x50, 12)) == expected[1]
        _, seed = motion_snapshot(1, expected)
        decode(0x41, seed[8:])
        assert struct.unpack("<3f", emu.read(HEAP + 0x6C, 12)) == expected[0]
        assert struct.unpack("<3f", emu.read(HEAP + 0x50, 12)) == expected[1]
    # Position setter called by type 0x24 updates both actual and target.
    emu.thiscall(0x4BE970, HEAP, *struct.unpack("<3I", coords))
    assert emu.read(HEAP + 0x2C, 12) == coords
    assert emu.read(HEAP + 0x6C, 12) == coords
    # Isolate the original physics acceleration calculation. This proves
    # the zero-time hazard, not that the live caller supplied zero time.
    acceleration_cases = []
    for dt in (0.016, 0.0):
        sp = STACK + 0xF0000
        emu.write(sp, bytes(0x100))
        for offset in (0x0C, 0xA8):
            emu.write(sp + offset, struct.pack("<3f", 10.0, 0.0, 0.0))
        emu.write(sp + 0x3C, struct.pack("<f", dt))
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.reg_write(UC_X86_REG_EBP, HEAP)
        emu.uc.emu_start(0x48C1BF, 0x48C236, count=100)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x48C236
        acceleration = struct.unpack("<3f", emu.read(HEAP + 0x5C, 12))
        if dt:
            assert acceleration == (0.0, 0.0, 0.0)
        else:
            assert all(math.isnan(v) for v in acceleration)
        acceleration_cases.append({"dt": dt, "all_nan": all(math.isnan(v) for v in acceleration)})
    assert pe.read_va(SITE, 6) == DISPLACED
    emu.write(CAVE, guard_code())
    emu.write(SITE, jmp_patch(SITE, CAVE, 6))
    for dt in (0.0, 0.001, 0.016, 1.0):
        sp = STACK + 0xF0000
        emu.write(sp, bytes(0x100))
        emu.write(sp + 0x38, struct.pack("<f", dt))
        emu.write(sp + 0xB0, struct.pack("<I", STOP))
        emu.write(HEAP + 0xF0, struct.pack("<I", 123))
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.reg_write(UC_X86_REG_EBP, HEAP)
        end = SITE + 6 if dt else STOP
        emu.uc.emu_start(SITE, end, count=100)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == end
        if dt:
            assert emu.uc.reg_read(UC_X86_REG_EAX) == 123
            assert emu.uc.reg_read(UC_X86_REG_ESP) == sp
        else:
            assert emu.uc.reg_read(UC_X86_REG_ESP) == sp + 0xC4
    result = {"client_sha256": digest, "decoder": "0x495330", "mask_cases_passed": len(masks),
              "unsafe_mask_fault": "0x49598c", "absolute_target_position_verified": True,
              "late_join_delta_seed_cases_passed": 2,
              "gun_state_block_cases_passed": gun_cases, "stats_block_cases_passed": stats_cases, "local_position_setter_verified": True,
              "physics_acceleration_cases": acceleration_cases,
              "zero_time_guard_cases_passed": 4,
              "scope": "isolated decoder and physics snippets; not live multiplayer verification"}
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
