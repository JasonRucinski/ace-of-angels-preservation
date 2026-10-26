"""Emulator-only ordered protection dispatch experiment; never installs a patch.

Trusted session/entity context is injected by the harness. Completion is a
return value, NOT a transmitted application acknowledgment. The real receive
loop, authenticated binding, reconnect lifecycle and other handlers remain open.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explicit_protection as protection
from emulate_codec import Emu, HEAP, SCRATCH, STACK, STUBS, STOP
from patch_client import Asm, PRISTINE_292, d32, jmp_patch
from pe_util import PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP,
                               UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBX,
                               UC_X86_REG_EBP)

CODE, CONTEXT = STUBS + 0x200, HEAP + 0x2000
MAGIC = b"AOP1"


def prototype():
    """Fixed fixture addresses, not an installable client extension."""
    a = Asm(CODE)

    def branch(opcode, label="reject"):
        a.emit(0x0F)
        a.rel32(opcode, label)

    a.emit(bytes.fromhex("83bee407000019"))  # body length exactly 25
    branch(0x85)
    a.emit(bytes.fromhex("81be64030000"), MAGIC)
    branch(0x85)
    a.emit(0xA1, d32(CONTEXT), b"\x0B\x05", d32(CONTEXT + 4))
    branch(0x84)  # unbound epoch (zero) rejected
    for offset in (0, 4, 8, 12):  # epoch low/high, entity, generation
        a.emit(b"\x8B\x86", d32(0x368 + offset))
        a.emit(b"\x3B\x05", d32(CONTEXT + offset))
        branch(0x85)
    a.emit(bytes.fromhex("0fb6867c03000083f801"))  # desired byte <= 1
    branch(0x87)
    a.emit(b"\x8B\x0D", d32(protection.WORLD_POINTER), b"\x85\xC9")
    branch(0x84)
    a.emit(bytes.fromhex("8b967803000085d2"))  # seq != 0
    branch(0x84)
    a.emit(b"\x3B\x15", d32(CONTEXT + 16))
    branch(0x84, "duplicate")
    a.emit(0xA1, d32(CONTEXT + 16), b"\x83\xF8\xFF")
    branch(0x84)  # sequence wrap requires a fresh binding
    a.emit(b"\x40\x39\xC2")  # seq == last + 1
    branch(0x85)
    a.emit(bytes.fromhex("8a867c030000"), b"\x38\x81", d32(protection.FLAG))
    branch(0x84, "commit")
    a.rel32(0xE8, protection.TOGGLE)
    a.label("commit")  # only reached after original handler returns
    a.emit(bytes.fromhex("8b8678030000"), 0xA3, d32(CONTEXT + 16))
    a.emit(bytes.fromhex("0fb6867c030000"), 0xA3, d32(CONTEXT + 20))
    a.emit(b"\xB8", d32(1))
    a.rel32(0xE9, protection.RESUME)
    a.label("duplicate")
    a.emit(b"\x3B\x05", d32(CONTEXT + 20))
    branch(0x85)  # same sequence with different payload is not a retry
    a.emit(b"\xB8", d32(2))
    a.rel32(0xE9, protection.RESUME)
    a.label("reject")
    a.emit(b"\x31\xC0")
    a.rel32(0xE9, protection.RESUME)
    return a.resolve()


def probe(path):
    emu = Emu(PE(path))
    code = prototype()
    assert len(code) < 0xE00
    assert emu.read(protection.SITE, len(protection.DISPLACED)) == protection.DISPLACED
    emu.write(CODE, code)
    emu.write(protection.SITE, jmp_patch(protection.SITE, CODE, len(protection.DISPLACED)))
    comm, world = HEAP, SCRATCH
    epoch, entity, generation = 0x123456789ABCDEF0, 3, 7
    calls, completions, cases = [], [], 0
    fail_handler = False

    def hook(uc, address, size, _):
        if address == protection.RESUME:
            completions.append(uc.reg_read(UC_X86_REG_EAX))
            uc.emu_stop()
        elif address == protection.TOGGLE:
            calls.append(struct.unpack("<I", emu.read(CONTEXT + 16, 4))[0])
            if fail_handler:
                uc.emu_stop()
        elif address == 0x446E50:  # original status-text sink only
            sp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", emu.read(sp, 4))[0])
            uc.reg_write(UC_X86_REG_ESP, sp + 4)

    emu.uc.hook_add(UC_HOOK_CODE, hook)

    def bind(e=epoch, g=generation, last=0, desired=0):
        emu.write(CONTEXT - 4, b"\xA5" * 32)
        emu.write(CONTEXT, struct.pack("<QIIII", e, entity, g, last, desired))
        emu.write(world + protection.FLAG, bytes([desired]))

    def body(seq, desired, e=epoch, ent=entity, gen=generation):
        return MAGIC + struct.pack("<QIIIB", e, ent, gen, seq, desired)

    def receive(payload, expected, length=None, null_world=False):
        nonlocal cases
        before_context = emu.read(CONTEXT, 24)
        before_flag = emu.read(world + protection.FLAG, 1)
        before_calls, before_completions = len(calls), len(completions)
        emu.write(comm + 0x364, payload.ljust(32, b"\xCC"))
        emu.write(comm + 0x7E4, d32(len(payload) if length is None else length))
        emu.write(protection.WORLD_POINTER, d32(0 if null_world else world))
        regs = (UC_X86_REG_ESI, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_EBP)
        values = (comm, 0x11223344, 0x22334455, 0x33445566)
        for reg, value in zip(regs, values):
            emu.uc.reg_write(reg, value)
        sp = STACK + 0xE0000
        emu.uc.reg_write(UC_X86_REG_ESP, sp)
        emu.uc.emu_start(protection.SITE, STOP, count=2000)
        if expected is None:
            assert emu.uc.reg_read(UC_X86_REG_EIP) == protection.TOGGLE
            assert len(completions) == before_completions
            assert emu.read(CONTEXT, 24) == before_context
        else:
            assert emu.uc.reg_read(UC_X86_REG_EIP) == protection.RESUME
            assert completions[-1] == expected, (payload.hex(), expected, completions[-1])
            assert emu.uc.reg_read(UC_X86_REG_ESP) == sp
            assert [emu.uc.reg_read(r) for r in regs] == list(values)
            if expected in (0, 2):
                assert len(calls) == before_calls
                assert emu.read(CONTEXT, 24) == before_context
                assert emu.read(world + protection.FLAG, 1) == before_flag
            else:
                seq, desired = struct.unpack("<IB", payload[20:])
                assert emu.read(CONTEXT + 16, 8) == struct.pack("<II", seq, desired)
                assert emu.read(world + protection.FLAG, 1) == bytes([desired])
                if len(calls) > before_calls:
                    assert calls[-1] == seq - 1  # no early commit at handler entry
        assert emu.read(CONTEXT - 4, 4) == b"\xA5" * 4
        assert emu.read(CONTEXT + 24, 4) == b"\xA5" * 4
        cases += 1

    bind()
    for seq in range(1, 1001):
        desired = (seq // 2) % 2  # both state changes and no-op state setters
        receive(body(seq + 1, desired), 0)  # reordered future event
        receive(body(seq, desired), 1)
        receive(body(seq, desired), 2)  # lost completion, retry same event
        receive(body(seq, 1 - desired), 0)
        if seq > 1:
            receive(body(1, 0), 0)  # replay remains rejected beyond cache size 30
    for e, ent, gen in ((epoch ^ 1, entity, generation),
                        (epoch ^ (1 << 32), entity, generation),
                        (epoch, entity + 1, generation),
                        (epoch, entity, generation - 1)):
        receive(body(1001, 1, e, ent, gen), 0)
    for length in (0, 1, 24, 26, 509, 0xFFFFFFFF):
        receive(body(1001, 1), 0, length=length)
    receive(b"BAD!" + body(1001, 1)[4:], 0)
    for desired in range(2, 256):
        receive(body(1001, desired), 0)
    receive(body(1001, 1), 0, null_world=True)
    receive(body(0, 1), 0)
    bind(e=0)
    receive(body(1, 1, e=0), 0)
    # Fixture rebind models trusted lifecycle replacement, not a network handshake.
    bind(e=epoch + 1, g=generation + 1)
    receive(body(1, 1), 0)
    receive(body(1, 1, e=epoch + 1, gen=generation + 1), 1)
    bind(last=0xFFFFFFFF)
    receive(body(0, 1), 0)
    receive(body(1, 1), 0)
    bind()
    fail_handler = True
    receive(body(1, 1), None)
    fail_handler = False
    receive(body(1, 1), 1)
    return {"cases": cases, "ordered_events": 1000,
            "prototype_sha256": hashlib.sha256(code).hexdigest(),
            "stale_context_rejected_before_handler": True,
            "completion_after_handler_return": True,
            "interrupted_handler_does_not_commit": True,
            "exact_retry_does_not_reapply": True,
            "sequence_wrap_rejected": True,
            "scope": "emulator-injected x86 guard and original protection handler; trusted context fixture; status-text sink mocked",
            "limitations": ["no authenticated context binding or lifecycle implementation",
                            "no application ACK sent over network", "no real receive-loop integration",
                            "protection only; no other legacy handler protected",
                            "no crash recovery guarantee after partial handler side effects",
                            "no real-client interaction or installable patch"],
            "authoritative_client_gate_passed": False}


def main():
    path, output = map(Path, sys.argv[1:])
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    if source_hash != PRISTINE_292:
        raise ValueError("requires pinned pristine 2.9.2 executable")
    result = {"source_sha256": source_hash, **probe(path)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
