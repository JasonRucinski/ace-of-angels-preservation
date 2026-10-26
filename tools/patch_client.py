"""Apply stability fixes to the 2.9.2 AoA client so it runs on modern Windows.

Usage:
    python -I tools/patch_client.py <AOACLIENT.EXE in a game folder>

The file is patched in place after its SHA-256 is checked against the
pristine 2.9.2 client; the untouched copy is kept beside it as
AOACLIENT.EXE.orig. Never point this at originals/.

Both bugs were present in 2003 but only became fatal under the modern NT
heap (found with tools/crashdbg.py --guard-heap):

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
import json
import shutil
import struct
import sys
from pathlib import Path

PRISTINE_292 = "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e"
IMAGE_BASE = 0x400000

IAT_SLEEP = 0x58C068
IAT_GETCURRENTTHREADID = 0x58C08C
LOCK_OWNER = 0x60D200   # .data tail, beyond the original VirtualSize (zero-filled)
LOCK_DEPTH = 0x60D204
CAVE = 0x58B200         # .text zero padding, beyond the original VirtualSize
TEXT_VSIZE = 0x18B000   # was 0x18A1E0; now covers the cave (== SizeOfRawData)
DATA_VSIZE = 0x4D000    # was 0x4C10C; now covers the lock words (ends at .rsrc)


class Asm:
    """Just enough of an x86 assembler for the cave: bytes, labels, rel8/rel32."""

    def __init__(self, origin):
        self.origin, self.code, self.labels, self.fixups = origin, bytearray(), {}, []

    def here(self):
        return self.origin + len(self.code)

    def label(self, name):
        self.labels[name] = self.here()

    def emit(self, *parts):
        for p in parts:
            self.code += p if isinstance(p, (bytes, bytearray)) else bytes([p])

    def rel8(self, opcode, target):
        self.emit(opcode)
        self.fixups.append(("rel8", len(self.code), target))
        self.emit(0)

    def rel32(self, opcode, target):
        self.emit(opcode)
        self.fixups.append(("rel32", len(self.code), target))
        self.emit(b"\0\0\0\0")

    def resolve(self):
        for kind, pos, target in self.fixups:
            dest = self.labels[target] if isinstance(target, str) else target
            if kind == "rel8":
                disp = dest - (self.origin + pos + 1)
                assert -128 <= disp <= 127, (target, disp)
                self.code[pos] = disp & 0xFF
            else:
                struct.pack_into("<i", self.code, pos, dest - (self.origin + pos + 4))
        return bytes(self.code)


def d32(v):
    return struct.pack("<I", v)


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


def jmp_patch(at, target, length):
    code = b"\xE9" + struct.pack("<i", target - (at + 5))
    return code + b"\x90" * (length - len(code))


def configure(source):
    """Build the known stability image in memory; never mutate source files."""
    data = bytearray(source)
    sha = hashlib.sha256(data).hexdigest()
    if sha != PRISTINE_292:
        raise ValueError(f"SHA-256 {sha} is not the pristine 2.9.2 client")

    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    sec_tab = e + 24 + struct.unpack_from("<H", data, e + 20)[0]
    sections = {}
    for i in range(nsec):
        off = sec_tab + 40 * i
        name = data[off:off + 8].rstrip(b"\0").decode()
        vsize, va, rsize, roff = struct.unpack_from("<IIII", data, off + 8)
        sections[name] = (off, vsize, va, rsize, roff)

    def file_off(va):
        rva = va - IMAGE_BASE
        for _, vs, sva, rs, ro in sections.values():
            if sva <= rva < sva + max(vs, rs):
                return rva - sva + ro
        raise ValueError(hex(va))

    cave, labels = build_cave()
    patches = [
        ("dxgfx-logger-size", 0x551775, b"\x6A\x20", b"\x6A\x24"),
        ("logger-lock entry", 0x526D00, bytes.fromhex("64a1000000006aff"),
         jmp_patch(0x526D00, labels["log_entry"], 8)),
        ("logger-lock exit", 0x526F8C, bytes.fromhex("64890d0000000083c424c3"),
         jmp_patch(0x526F8C, labels["log_exit"], 11)),
        ("format-lock entry", 0x527210, bytes.fromhex("8b4c24088d44240c"),
         jmp_patch(0x527210, labels["fmt_entry"], 8)),
        ("format-lock exit", 0x527233, bytes.fromhex("e868fdffff8b065ec3"),
         jmp_patch(0x527233, labels["fmt_exit"], 9)),
        ("logger-lock cave", CAVE, b"\0" * len(cave), cave),
    ]
    record = []
    for name, va, old, new in patches:
        off = file_off(va)
        assert len(old) == len(new), name
        if bytes(data[off:off + len(old)]) != old:
            raise ValueError(f"{name}: unexpected bytes at {va:#x}")
        data[off:off + len(new)] = new
        record.append({"patch": name, "va": hex(va), "file_offset": hex(off),
                       "old": old.hex(), "new": new.hex()})
    for name, new_vsize in ((".text", TEXT_VSIZE), (".data", DATA_VSIZE)):
        off, vsize, va, rsize, roff = sections[name]
        struct.pack_into("<I", data, off + 8, new_vsize)
        record.append({"patch": f"{name} VirtualSize", "old": hex(vsize), "new": hex(new_vsize)})

    result = {"input_sha256": sha, "output_sha256": hashlib.sha256(data).hexdigest(),
              "patches": record}
    return bytes(data), result


def main():
    exe = Path(sys.argv[1])
    if "originals" in (part.lower() for part in exe.resolve().parts):
        sys.exit("refusing to patch a file under originals/")
    data, result = configure(exe.read_bytes())
    backup = exe.with_name(exe.name + ".orig")
    if not backup.exists():
        shutil.copy2(exe, backup)
    exe.write_bytes(data)
    exe.with_name("_patches.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
