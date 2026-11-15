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
from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches.base import Patch, Region

NAME = "archive-terminator-v1"
SITE = 0x52A6E3
CAVE = layout.cave(NAME).start
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


PATCH = Patch(
    id=NAME, since=3, policy="always",
    regions=(Region(SITE, DISPLACED, jmp_patch(SITE, CAVE, len(DISPLACED))),
             Region(CAVE, bytes(len(cave_code())), cave_code(), "cave")))
