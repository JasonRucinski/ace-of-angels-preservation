"""Stability fixes that let the 2.9.2 AoA client run on modern Windows.

They are the base of every supported client (policy "base"): stabilize()
applies them once to a client whose SHA-256 matches the pristine 2.9.2
client, and the result, with the original Station, is STABLE_SHA256. prepare
removes every other patch and checks that hash, so the whole image is
verified, not only the patch sites. (A standalone command line was removed
in phase 0b because it wrote the executable with no setup record.)

Both bugs were present in 2003 but only became fatal under the modern NT
heap (found with tools/run.py aoa.live.crashdbg --guard-heap):

1. dxgfx-logger-size: the separately built Dx7Api library (Z:\\src\\Dx7Api)
   allocates the "DxGfx" log object with a stale sizeof of 0x20, but the
   logger class is 0x24 bytes (its constructor at 0x5266b0 zeroes +0x20;
   the static logger at 0x5e7e38 is followed by another object at 0x5e7e5c).
   The 4-byte write past the block corrupts the next heap chunk's header,
   so the client dies during start-up with 0xC0000005/0xC000041D.

2. logger-lock: the logger (0x526d00) and the string formatter it uses
   (0x527210, which vsprintf()s into one global buffer) are called from
   several threads with no locking. Each log line does fopen/fwrite/fclose
   and then stores the sentinel 0xFFFF as its FILE*, so a second thread can
   fwrite((FILE*)0xFFFF) and fault at 0x10023. Both functions are wrapped in
   one recursive spinlock placed in the zero padding at the end of .text,
   with its two state words in the zero-filled tail of .data. The only
   imports used are ones the client already has (GetCurrentThreadId, Sleep).
"""
import hashlib
import struct

from aoa.builds import CLIENT_SHA256
from aoa.client import layout
from aoa.client.asm import Asm, d32, jmp_patch
from aoa.client.patches import base
from aoa.client.patches.base import Patch, Region

PRISTINE_292 = CLIENT_SHA256["2.9.2"]
# Both logger patches applied, Station still aoahost.com: what every
# supported client is once its other patches and its Station are removed.
STABLE_SHA256 = "87249b8a8ce37684085ad8e62457b6e8f1f9d4a6f5653bcf8dfe11495c1b7f00"

IAT_SLEEP = 0x58C068
IAT_GETCURRENTTHREADID = 0x58C08C
LOCK_OWNER = layout.data("logger-lock-v1").start   # .data tail, beyond the original VirtualSize
LOCK_DEPTH = LOCK_OWNER + 4
CAVE = layout.cave("logger-lock-v1").start         # .text padding, beyond the original VirtualSize
# Section VirtualSize: (name, original, patched). .text now covers the caves
# (== SizeOfRawData); .data covers the runtime variables (ends at .rsrc).
HEADER = ((".text", 0x18A1E0, 0x18B000), (".data", 0x4C10C, 0x4D000))


def build_cave():
    a = Asm(CAVE)
    # acquire: recursive spinlock keyed by thread id; preserves eax/ecx/edx.
    a.label("acquire")
    a.emit(0x50, 0x51, 0x52)                          # push eax; push ecx; push edx
    a.emit(b"\xFF\x15", d32(IAT_GETCURRENTTHREADID))  # call [GetCurrentThreadId]
    a.emit(b"\x8B\xC8")                               # mov ecx, eax
    a.label("retry")
    a.emit(b"\x33\xC0")                               # xor eax, eax
    a.emit(b"\xF0\x0F\xB1\x0D", d32(LOCK_OWNER))      # lock cmpxchg [owner], ecx
    a.rel8(0x74, "got")                               # jz got (was free)
    a.emit(b"\x3B\xC1")                               # cmp eax, ecx
    a.rel8(0x74, "got")                               # jz got (already ours)
    a.emit(0x51, 0x6A, 0x01)                          # push ecx; push 1
    a.emit(b"\xFF\x15", d32(IAT_SLEEP))               # call [Sleep]  (Sleep(1))
    a.emit(0x59)                                      # pop ecx
    a.rel8(0xEB, "retry")                             # jmp retry
    a.label("got")
    a.emit(b"\xFF\x05", d32(LOCK_DEPTH))              # inc dword [depth]
    a.emit(0x5A, 0x59, 0x58, 0xC3)                    # pop edx; pop ecx; pop eax; ret
    # release: only flags are touched.
    a.label("release")
    a.emit(b"\xFF\x0D", d32(LOCK_DEPTH))              # dec dword [depth]
    a.rel8(0x75, "release_done")                      # jnz done
    a.emit(b"\xC7\x05", d32(LOCK_OWNER), d32(0))      # mov dword [owner], 0
    a.label("release_done")
    a.emit(0xC3)                                      # ret
    # logger entry (from 0x526d00): lock, then the two displaced instructions.
    a.label("log_entry")
    a.rel32(0xE8, "acquire")
    a.emit(b"\x64\xA1\x00\x00\x00\x00")               # mov eax, fs:[0]
    a.emit(b"\x6A\xFF")                               # push -1
    a.rel32(0xE9, 0x526D08)
    # logger exit (from 0x526f8c): displaced epilogue, unlock, ret.
    a.label("log_exit")
    a.emit(b"\x64\x89\x0D\x00\x00\x00\x00")           # mov fs:[0], ecx
    a.emit(b"\x83\xC4\x24")                           # add esp, 0x24
    a.rel32(0xE8, "release")
    a.emit(0xC3)
    # Format entry (from 0x527210).
    a.label("fmt_entry")
    a.rel32(0xE8, "acquire")
    a.emit(b"\x8B\x4C\x24\x08")                       # mov ecx, [esp+8]
    a.emit(b"\x8D\x44\x24\x0C")                       # lea eax, [esp+0xc]
    a.rel32(0xE9, 0x527218)
    # Format exit (from 0x527233): displaced tail, unlock, ret.
    a.label("fmt_exit")
    a.rel32(0xE8, 0x526FA0)                           # call string-assign
    a.emit(b"\x8B\x06", 0x5E)                         # mov eax, [esi]; pop esi
    a.rel32(0xE8, "release")
    a.emit(0xC3)
    return a.resolve(), a.labels


def _regions():
    cave, labels = build_cave()
    return (Region(0x526D00, bytes.fromhex("64a1000000006aff"), jmp_patch(0x526D00, labels["log_entry"], 8)),
            Region(0x526F8C, bytes.fromhex("64890d0000000083c424c3"), jmp_patch(0x526F8C, labels["log_exit"], 11)),
            Region(0x527210, bytes.fromhex("8b4c24088d44240c"), jmp_patch(0x527210, labels["fmt_entry"], 8)),
            Region(0x527233, bytes.fromhex("e868fdffff8b065ec3"), jmp_patch(0x527233, labels["fmt_exit"], 9)),
            Region(CAVE, bytes(len(cave)), cave, "cave"))


# The section sizes in HEADER belong to logger-size-v1: every cave and runtime
# variable of every other patch depends on them.
LOGGER_SIZE = Patch(id="logger-size-v1", since=1, policy="base",
                    regions=(Region(0x551775, b"\x6A\x20", b"\x6A\x24"),))
LOGGER_LOCK = Patch(id="logger-lock-v1", since=1, policy="base",
                    data=((LOCK_OWNER, layout.data("logger-lock-v1").size),), regions=_regions())
PATCHES = (LOGGER_SIZE, LOGGER_LOCK)


def section_headers(data):
    """{section name: file offset of its section-table entry}."""
    e = struct.unpack_from("<I", data, 0x3C)[0]
    table = e + 24 + struct.unpack_from("<H", data, e + 20)[0]
    entries = (table + 40 * i for i in range(struct.unpack_from("<H", data, e + 6)[0]))
    return {data[at:at + 8].rstrip(b"\0").decode("latin1"): at for at in entries}


def stabilize(source):
    """The stability-patched image built from the pristine client, in memory."""
    sha = hashlib.sha256(source).hexdigest()
    if sha != PRISTINE_292:
        raise ValueError(f"SHA-256 {sha} is not the pristine 2.9.2 client")
    data = bytes(source)
    base.check_mapping(data, PATCHES)
    for patch in PATCHES:
        data = base.apply(patch, data, True)
    out, headers = bytearray(data), section_headers(data)
    for name, old, new in HEADER:
        if struct.unpack_from("<I", out, headers[name] + 8)[0] != old:
            raise ValueError(f"unexpected {name} VirtualSize")
        struct.pack_into("<I", out, headers[name] + 8, new)
    return bytes(out)
