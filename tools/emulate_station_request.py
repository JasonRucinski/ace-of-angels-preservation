"""Verify original 2.9.2 player-record copy and TCP request field packing.

Usage: python -I tools/emulate_station_request.py CLIENT.EXE OUT.json
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, SCRATCH, STACK, STOP
from pe_util import PE
from station_stub import ack_connect
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EBX, UC_X86_REG_EDX


def probe(pe, identity):
    emu = Emu(pe)
    world, comm, source = SCRATCH, SCRATCH + 0xF0000, SCRATCH + 0xF4000
    player = world + 0xD32AC
    emu.write(0x5E7728, struct.pack("<I", world))

    def hook(uc, address, size, _):
        if address == 0x4A60D0:  # Name/UI propagation after the actual record copy.
            sp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, int.from_bytes(emu.read(sp, 4), "little"))
            uc.reg_write(UC_X86_REG_ESP, sp + 12)

    emu.uc.hook_add(UC_HOOK_CODE, hook)
    request = bytearray(381)
    request[31:40] = b"testpilot"
    request[31 + 0x8B] = 0xA7
    _, ack = ack_connect(request, station_id=identity)
    emu.write(source, ack[13:])
    emu.thiscall(0x49DB20, player, source)
    assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
    record = int.from_bytes(emu.read(world + 0xD3620, 4), "little")
    assert emu.read(record, 350) == ack[13:]

    # Execute original initialization, string copies and scalar packing.
    # Start after logging; stop before TCP socket creation/connection.
    sp = STACK + 0xE0000
    emu.uc.reg_write(UC_X86_REG_ESP, sp)
    emu.uc.reg_write(UC_X86_REG_EBP, comm)
    emu.write(source + 400, b"first\0second\0")
    emu.write(sp + 12 + 0x48, struct.pack("<6I", source + 400, source + 406, 5, 0, 0, 0))
    emu.uc.emu_start(0x4302A6, 0x43044B, count=10000)
    assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x43044B
    header = emu.read(comm + 0x12E8, 142)
    assert header[:6] == b"first\0" and header[64:71] == b"second\0"
    assert int.from_bytes(header[60:64], "little") == identity
    assert header[128:130] == b"\x05\xa7"
    # RequestGameserverConnect passes the saved ACK block to SendConnectRequest.
    # Run its original block-copy and version-field construction before Winsock.
    arena_packet = SCRATCH + 0xF6000
    emu.uc.reg_write(UC_X86_REG_ESP, sp)
    emu.uc.reg_write(UC_X86_REG_EBX, comm)
    emu.uc.reg_write(UC_X86_REG_EDX, arena_packet)
    emu.write(sp + 0x14, struct.pack("<I", source))
    emu.write(sp + 0x1C, bytes(4))
    emu.uc.emu_start(0x486ED4, 0x486F1F, count=10000)
    assert emu.uc.reg_read(UC_X86_REG_EIP) == 0x486F1F
    arena = emu.read(arena_packet, 381)
    assert arena[31:] == ack[13:]
    assert struct.unpack_from("<III", arena, 1) == (9, 2, 2)
    assert struct.unpack_from("<I", arena, 31 + 0x7B)[0] == identity
    return {"station_id": identity, "request_id": int.from_bytes(header[60:64], "little"),
            "job": header[128], "flag": header[129], "header_length": len(header),
            "arena_connect_id": struct.unpack_from("<I", arena, 31 + 0x7B)[0],
            "arena_player_block_preserved": True}


def main():
    source, output = sys.argv[1:]
    pe = PE(source)
    digest = hashlib.sha256(pe.data).hexdigest()
    if digest != "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e":
        raise ValueError("requires original 2.9.2 client")
    result = {"source_sha256": digest, "record_copy": "0x49DB20",
              "request_packing": "0x4302A6..0x43044B",
              "cases": [probe(pe, identity) for identity in (0x01020304, 0xF0E0D0C0)],
              "mocked": ["allocation/free", "name/UI propagation after record copy"],
              "scope": "isolated original record copy, TCP header packing and arena request construction; no full ACK dispatch, OS socket, UI or complete arena transition"}
    Path(output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
