"""NUL-terminate archive data decompressed by the 2.9.2 client (findings 9.29).

CCompress::Decompress (0x52A630) returns its result in a buffer allocated at
0x52A6E8 with exactly the decompressed size and no terminator. The target
window loader (0x502B80) parses tgtwin2.cfg from hud.aoa as a C string
(copy at 0x526FA0), so it reads whatever follows in the heap. When that byte
is not zero, the tokenizer sizes its array from garbage, operator new throws,
and unwinding frees config text as a pointer: the intermittent arena-join
crash in ntdll. This patch allocates one extra byte and stores a NUL after
the data; binary callers ignore it.

Library use only (prepare_client.py composes it); no file is written here.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402

SITE, SITE_OFFSET = 0x52A6E3, 0x12A6E3
CAVE, CAVE_OFFSET = 0x58B440, 0x18B440
DISPLACED = bytes.fromhex("8b4c241051e851290500")  # mov ecx,[esp+10]; push ecx; call new
NEW = 0x57D03E      # MFC42 ord823 (operator new) thunk
RESUME = 0x52A6ED   # mov ecx,[esp+14] after the original call


def cave_code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex("8b4c2410"))   # mov ecx, [esp+10]   ; size
    a.emit(0x41, 0x51)                  # inc ecx; push ecx   ; size + 1
    a.rel32(0xE8, NEW)                  # call operator new
    a.emit(bytes.fromhex("8b4c2414"))   # mov ecx, [esp+14]   ; size (one push deeper)
    a.emit(bytes.fromhex("c6040800"))   # mov byte [eax+ecx], 0
    a.rel32(0xE9, RESUME)
    return a.resolve()


def state(data):
    """True if applied, False if original; raises on anything else."""
    code, jump = cave_code(), jmp_patch(SITE, CAVE, len(DISPLACED))
    current = (data[SITE_OFFSET:SITE_OFFSET + len(DISPLACED)], data[CAVE_OFFSET:CAVE_OFFSET + len(code)])
    if current == (DISPLACED, bytes(len(code))):
        return False
    if current == (jump, code):
        return True
    raise ValueError("unexpected archive-terminator code or cave")


def configure(data, enabled=True):
    state(data)
    code, jump = cave_code(), jmp_patch(SITE, CAVE, len(DISPLACED))
    out = bytearray(data)
    out[SITE_OFFSET:SITE_OFFSET + len(jump)] = jump if enabled else DISPLACED
    out[CAVE_OFFSET:CAVE_OFFSET + len(code)] = code if enabled else bytes(len(code))
    return bytes(out)
