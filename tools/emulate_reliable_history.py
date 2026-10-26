"""Probe the original 2.9.2 reliable receive path in Unicorn (no game process).

Usage: python -I tools/emulate_reliable_history.py CLIENT.EXE OUT.json
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, SCRATCH, STACK, STOP
from pe_util import PE
from station_stub import ReliableRemovals
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EIP, UC_X86_REG_EAX, UC_X86_REG_ECX,
                               UC_X86_REG_ESI, UC_X86_REG_ESP)


def receive_probe(pe, combat=False):
    """Run the admitted-peer wrapper path; mock OS calls and packet sending.

    Stop at the dispatch decision. For accepted removals, execute the real
    0x2D case up to RemovePlayer entry, without running world destruction.
    """
    emu = Emu(pe)
    comm, peer, history = SCRATCH, SCRATCH + 0x2000, SCRATCH + 0x3000
    emu.thiscall(0x4C26D0, history, 30)
    emu.write(comm + 0x8BC, struct.pack("<I", peer))
    emu.write(peer + 0x384, struct.pack("<I", history))
    emu.write(0x5E7728, struct.pack("<I", SCRATCH + 0x4000))
    acknowledgments, dispatched_slots = [], []
    stop_reason = []

    def u32(address):
        return struct.unpack("<I", emu.read(address, 4))[0]

    def hook(uc, address, size, _):
        if address in (0x486464, 0x486925):
            stop_reason.append("dispatch" if address == 0x486464 else "duplicate")
            uc.emu_stop()
            return
        sp = uc.reg_read(UC_X86_REG_ESP)
        if address == 0x4A6FB0:
            dispatched_slots.append(u32(sp + 4) & 0xFF)
            uc.emu_stop()
            return
        # Isolated external dependencies. Original wrapper/filter/case bytes
        # remain untouched. Return from each intercepted call with its ABI.
        pop_bytes = {0x529710: 0, 0x529960: 8, 0x57D806: 4,
                     0x57D800: 4, 0x57D7FA: 4, 0x486A60: 16}
        if address not in pop_bytes:
            return
        if address == 0x529710:
            emu.write(uc.reg_read(UC_X86_REG_ECX), bytes(0x49C))
        if address == 0x486A60:
            packet, length, kind, reliable = struct.unpack("<4I", emu.read(sp + 4, 16))
            assert (length, kind, reliable) == (4, 0x0F, 0)
            acknowledgments.append(emu.read(packet + 0x14, 4))
        uc.reg_write(UC_X86_REG_EAX, 0)
        uc.reg_write(UC_X86_REG_EIP, u32(sp))
        uc.reg_write(UC_X86_REG_ESP, sp + 4 + pop_bytes[address])

    emu.uc.hook_add(UC_HOOK_CODE, hook)

    def receive(packet):
        kind, body = packet
        assert kind == 0x1B and len(body) >= 5
        emu.write(comm + 0x364, body)
        emu.write(comm + 0x7E4, struct.pack("<I", len(body)))
        emu.write(comm + 0x7E8, bytes([kind]))
        emu.uc.reg_write(UC_X86_REG_ESI, comm)
        emu.uc.reg_write(UC_X86_REG_ESP, STACK + 0xE0000)
        stop_reason.clear()
        emu.uc.emu_start(0x4863C8, STOP, count=10000)
        assert len(stop_reason) == 1
        assert u32(comm + 0x7E4) == len(body) - 5
        assert emu.read(comm + 0x7E8, 1) == body[-1:]
        assert acknowledgments[-1] == body[-5:-1]
        if stop_reason[0] == "dispatch" and body[-1] == 0x2D:
            before = len(dispatched_slots)
            emu.uc.emu_start(0x430710, STOP, count=100)
            assert len(dispatched_slots) == before + 1
            assert dispatched_slots[-1] == body[0]
        return stop_reason[0]

    if combat:
        delivery = ReliableRemovals(ordered=True)
        first = None
        for index in range(30):
            kind = (0x2A, 0x30, 0x38)[index % 3]
            packet = delivery.queue_message("observer", kind, bytes([index]), index)
            first = first or packet
            assert receive(packet) == "dispatch"
            assert receive(packet) == "duplicate"
            assert delivery.acknowledge("observer", acknowledgments[-1], now=index)
        assert receive(first) == "duplicate"
        assert delivery.queue("observer", 2, 31) is None
        return {"events_dispatched": 30, "duplicates_rejected": 31,
                "acknowledgments": len(acknowledgments), "budget_shared_with_removal": True,
                "scope": "original admitted-peer wrapper filter only; combat handler bodies not executed"}

    delivery = ReliableRemovals()
    first = delivery.queue("observer", 2, 0)
    assert receive(first) == "dispatch"
    retries, failed = delivery.due(0.5)
    assert not failed and retries == [("observer", first)]
    assert receive(retries[0][1]) == "duplicate"
    assert delivery.acknowledge("observer", acknowledgments[-1])
    assert not delivery.pending
    second = delivery.queue("observer", 3, 1)
    assert receive(second) == "dispatch"
    assert receive(first) == "duplicate"  # Delayed, reordered old removal.
    assert receive(second) == "duplicate"
    assert dispatched_slots == [2, 3]
    assert len(acknowledgments) == 5
    return {"packets_received": 5, "acknowledgments": 5,
            "remove_player_calls": dispatched_slots, "duplicate_dispatches": 0,
            "server_retry_cleared_by_client_ack": True,
            "entry": "0x4863C8", "removal_case": "0x430710",
            "mocked": ["packet initialization/address setup", "Winsock address conversion",
                       "ACK transmission", "RemovePlayer body"],
            "scope": "admitted-peer wrapper path and removal case; no wire decode, sender lookup, world destruction or rendering"}


def main():
    source, output = sys.argv[1:]
    pe = PE(source)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e":
        raise ValueError("requires original 2.9.2 client")
    emu = Emu(pe)
    emu.thiscall(0x4C26D0, SCRATCH, 30)

    def accept(sequence):
        result = emu.thiscall(0x4C2730, SCRATCH, sequence) & 0xFF
        assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        return result == 1

    assert not accept(0), "zero is pre-filled, not a usable initial sequence"
    for sequence in range(1, 31):
        assert accept(sequence)
        assert not accept(sequence)
    assert not accept(1)
    assert accept(31)
    assert accept(1), "old duplicate is accepted after cache eviction"
    result = {"source_sha256": digest, "capacity": 30,
              "constructor": "0x4C26D0", "filter": "0x4C2730",
              "zero_rejected": True, "recent_duplicates_rejected": True,
              "evicted_duplicate_accepted": True,
              "receive_probe": receive_probe(pe),
              "combat_wrapper_probe": receive_probe(pe, combat=True),
              "scope": "isolated original duplicate filter and admitted-peer reliable receive path; not full network dispatch or renderer"}
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
