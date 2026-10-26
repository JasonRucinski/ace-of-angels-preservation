"""Original 2.9.2 terrain category dispatch and parent-transform probes.

No rendering, object allocation, online loading or gameplay is exercised.
"""
import hashlib
import json
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_arena1a import EXPECTED_DISPATCH
from emulate_codec import Emu, HEAP, STACK, STOP
from patch_client import PRISTINE_292
from pe_util import PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP


def main():
    source, output = map(Path, sys.argv[1:])
    if hashlib.sha256(source.read_bytes()).hexdigest() != PRISTINE_292:
        raise ValueError("requires original 2.9.2")
    emu = Emu(PE(source))
    stops = set(EXPECTED_DISPATCH)

    def hook(uc, address, size, _):
        if address in stops:
            uc.emu_stop()

    emu.uc.hook_add(UC_HOOK_CODE, hook)
    categories = {}
    for category in range(12):
        emu.uc.reg_write(UC_X86_REG_EAX, category)
        emu.uc.emu_start(0x496130, STOP, count=20)
        destination = emu.uc.reg_read(UC_X86_REG_EIP)
        expected = EXPECTED_DISPATCH[category - 1] if 1 <= category <= 10 else 0x496423
        assert destination == expected
        categories[category] = hex(destination)
    stops.clear()
    stops.add(0x4960CF)
    sp = STACK + 0xE0000
    for index in range(32):
        angle = index * 0.2
        co, si = math.cos(angle), math.sin(angle)
        parent = [co, si, 0, 0, -si, co, 0, 0, 0, 0, 1, 0, 13 * index, -17 * index, 19 * index, 1]
        parent = struct.unpack("<16f", struct.pack("<16f", *parent))
        position = [index * 7.0, index * -11.0, index * 3.0]
        emu.write(HEAP, struct.pack("<16f", *parent))
        emu.write(sp, bytes(0x240))
        emu.write(sp + 0x200, struct.pack("<I", HEAP))
        emu.write(sp + 0x20, struct.pack("<3f", *position))
        # The original preceding instructions hold Y's float bits in EDX;
        # 0x495F5C writes them into the local position before transforming it.
        emu.uc.reg_write(UC_X86_REG_EDX, struct.unpack("<I", struct.pack("<f", position[1]))[0])
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.emu_start(0x495F53, STOP, count=200)
        assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x4960CF
        observed = struct.unpack("<3f", emu.read(sp + 0xEC, 12))
        expected = [sum(position[k] * parent[k * 4 + c] for k in range(3)) + parent[12 + c]
                    for c in range(3)]
        assert all(math.isclose(a, b, abs_tol=0.001) for a, b in zip(observed, expected)), (observed, expected)
    report = {"source_sha256": PRISTINE_292, "category_cases": len(categories), "category_destinations": categories,
              "parent_position_cases": 32, "parent_transform_matches_row_vector_math": True,
              "scope": "isolated original category switch and nested position arithmetic; no allocation, rendering, online loading, collision or gameplay",
              "all_arena1a_nodes_working": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
