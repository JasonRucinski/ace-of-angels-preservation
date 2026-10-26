"""Cross-check accumulated movement fields/absolute refresh against 2.9.2."""
import hashlib
import json
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, HEAP, SCRATCH, STOP
from pe_util import PE
import relay_motion as motion
from unicorn.x86_const import UC_X86_REG_EIP


def decoder(pe):
    emu = Emu(pe)
    for offset, pointer in ((0, HEAP), (0x10, HEAP + 0x1000), (0x14, HEAP + 0x2000)):
        emu.write(SCRATCH + offset, struct.pack("<I", pointer))
    return emu


def receive(emu, packet):
    mask = struct.unpack_from("<I", packet, 4)[0]
    emu.write(SCRATCH + 0x1000, packet[8:] + bytes(512))
    consumed = emu.thiscall(0x495330, HEAP + 0x3000, SCRATCH + 0x1000, SCRATCH, mask)
    assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
    assert consumed == len(packet) - 8


def compare(emu, state, control=True):
    for flag, offset, fmt, _ in motion.FIELDS:
        if flag in state and (control or flag != 0x400):
            assert emu.read(HEAP + offset, struct.calcsize("<" + fmt)) == struct.pack("<" + fmt, *state[flag]), hex(flag)


def main():
    source, output = sys.argv[1:]
    pe = PE(source)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e":
        raise ValueError("requires original 2.9.2 client")
    assert struct.unpack("<f", pe.read_va(0x59820C, 4))[0] == motion.SMALL_DELTA_SCALE
    sender, observer = decoder(pe), decoder(pe)
    state = {flag: ((123,) if fmt == "i" else tuple(float(i + 1) for i in range(3 if fmt == "3f" else 1)))
             for flag, _, fmt, _ in motion.FIELDS}
    receive(sender, motion.snapshot(1, state, include_control=True))
    receive(observer, motion.snapshot(1, state))
    compare(sender, state)
    rng = random.Random(20261021)
    refreshes = 0
    for index in range(300):
        mask, body = 0, bytearray()
        for flag, _, fmt, scale in motion.FIELDS:
            mode = rng.randrange(4)
            if mode == 0:
                continue
            if scale is not None:
                mask |= flag << (mode - 1)
                wire_fmt = ("3f", "3h", "3b")[mode - 1]
                values = tuple(rng.randrange(-100, 101) for _ in range(3))
            elif flag == 0x400:
                mask |= flag if mode == 1 else 0x800
                wire_fmt = "i" if mode == 1 else "h"
                values = (rng.randrange(-100, 101),)
            else:
                mask |= flag
                wire_fmt = fmt
                values = tuple(rng.uniform(-1000, 1000) for _ in range(3 if fmt == "3f" else 1))
            body.extend(struct.pack("<" + wire_fmt, *values))
        packet = struct.pack("<HHI", 0x8000, 1, mask) + body
        state, _, missing = motion.update(packet, state)
        assert not missing
        receive(sender, packet)
        compare(sender, state)
        # Lose every third downstream update; the next absolute packet restores
        # every observed safe float field, independent of the lost deltas.
        if index % 3:
            refresh = motion.snapshot(1, state)
            receive(observer, refresh)
            compare(observer, state, control=False)
            receive(observer, refresh)  # Duplicate absolute is also harmless.
            compare(observer, state, control=False)
            refreshes += 1
    result = {"source_sha256": digest, "decoder": "0x495330", "state_cases": 300,
              "field_groups": len(motion.FIELDS), "absolute_refresh_cases": refreshes,
              "scaled_delta_constant": motion.SMALL_DELTA_SCALE,
              "control_scalar_excluded_from_refresh": True,
              "scope": "original isolated decoder; destination bytes and scale verified, not physical semantics, upstream ordering, renderer or authoritative simulation"}
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
