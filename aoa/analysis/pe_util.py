"""Shared static-analysis helpers for the AoA clients (pefile + capstone).

Address spaces:
  file offset  <->  RVA  <->  VA (= ImageBase + RVA)
Mapping goes through the section table. Bytes past a section's SizeOfRawData
but inside its VirtualSize are zero-initialised at load time and have no file
backing; `read_va` returns zeros for them and `va_to_off` returns None.
"""
import pickle
import re
from bisect import bisect_right
from pathlib import Path

import capstone
import pefile

HEX = re.compile(r"0x[0-9a-f]+")


class PE:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.pe = pefile.PE(data=self.data, fast_load=False)
        self.base = self.pe.OPTIONAL_HEADER.ImageBase
        self.sections = []
        for s in self.pe.sections:
            self.sections.append({
                "name": s.Name.rstrip(b"\0").decode("latin1"),
                "va": self.base + s.VirtualAddress,
                "vsize": s.Misc_VirtualSize,
                "raw_off": s.PointerToRawData,
                "raw_size": s.SizeOfRawData,
                "chars": s.Characteristics,
            })
        self.imports = {}  # IAT VA -> "dll!name"
        for entry in getattr(self.pe, "DIRECTORY_ENTRY_IMPORT", []):
            dll = entry.dll.decode("latin1")
            for imp in entry.imports:
                name = imp.name.decode("latin1") if imp.name else f"ord{imp.ordinal}"
                self.imports[imp.address] = f"{dll}!{name}"

    # ---- address mapping -------------------------------------------------
    def section_of_va(self, va):
        for s in self.sections:
            if s["va"] <= va < s["va"] + max(s["vsize"], s["raw_size"]):
                return s
        return None

    def va_to_off(self, va):
        s = self.section_of_va(va)
        if s is None:
            return None
        delta = va - s["va"]
        if delta >= s["raw_size"]:
            return None  # virtual zero-fill
        return s["raw_off"] + delta

    def off_to_va(self, off):
        for s in self.sections:
            if s["raw_off"] <= off < s["raw_off"] + s["raw_size"]:
                return s["va"] + (off - s["raw_off"])
        return None

    def read_va(self, va, n):
        out = bytearray()
        for i in range(n):
            o = self.va_to_off(va + i)
            out.append(self.data[o] if o is not None else 0)
        return bytes(out)

    def u32(self, va):
        return int.from_bytes(self.read_va(va, 4), "little")

    def cstr(self, va, limit=512):
        o = self.va_to_off(va)
        if o is None:
            return None
        end = self.data.find(b"\0", o, o + limit)
        if end < 0:
            return None
        raw = self.data[o:end]
        try:
            return raw.decode("ascii")
        except UnicodeDecodeError:
            return None

    def find_all(self, needle: bytes):
        out, i = [], self.data.find(needle)
        while i >= 0:
            out.append(i)
            i = self.data.find(needle, i + 1)
        return out

    def text(self):
        return next(s for s in self.sections if s["chars"] & 0x20000000)  # MEM_EXECUTE


class Disasm:
    """Linear-sweep disassembly of the executable section, cached on disk.

    Each instruction is (va, size, mnemonic, op_str). `refs` maps every
    hex constant >= ImageBase that appears in an operand to the instruction
    addresses using it (push imm, mov imm, [disp], call/jmp target).
    """

    def __init__(self, pe: PE, cache_path):
        self.pe = pe
        cache = Path(cache_path)
        if cache.exists():
            self.insns = pickle.loads(cache.read_bytes())
        else:
            self.insns = self._sweep()
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(pickle.dumps(self.insns))
        self.addrs = [i[0] for i in self.insns]
        self.index = {a: n for n, a in enumerate(self.addrs)}
        self.refs = {}
        lo = pe.base
        hi = pe.base + pe.pe.OPTIONAL_HEADER.SizeOfImage
        for n, (va, size, mn, ops) in enumerate(self.insns):
            for h in HEX.findall(ops):
                v = int(h, 16)
                if lo <= v < hi:
                    self.refs.setdefault(v, []).append(va)
        self._funcs = None
        # Incremental-link thunks: a 5-byte `jmp imm32` that is itself the
        # target of a call or of a code pointer. thunk VA -> real target VA.
        self.thunk_to = {}
        self.thunks_of = {}
        t = pe.text()
        tlo, thi = t["va"], t["va"] + t["vsize"]
        for va, size, mn, ops in self.insns:
            if mn == "jmp" and size == 5 and ops.startswith("0x"):
                tgt = int(ops, 16)
                if tlo <= tgt < thi and any(self.at(r) and self.at(r)[2] in ("call", "push", "mov")
                                            for r in self.refs.get(va, [])):
                    self.thunk_to[va] = tgt
                    self.thunks_of.setdefault(tgt, []).append(va)

    def resolve(self, va):
        """Follow incremental-link thunks to the real function."""
        seen = 0
        while seen < 4:
            if va in self.thunk_to:
                va = self.thunk_to[va]
            else:
                ins = self.at(va)
                if not (ins and ins[2] == "jmp" and ins[1] == 5 and ins[3].startswith("0x")):
                    break
                va = int(ins[3], 16)
            seen += 1
        return va

    def refs_to_func(self, target):
        """References to a function directly or through its thunks."""
        out = list(self.refs.get(target, []))
        for th in self.thunks_of.get(target, []):
            out += [r for r in self.refs.get(th, []) if r != th]
        return out

    def _sweep(self):
        t = self.pe.text()
        code = self.pe.data[t["raw_off"]:t["raw_off"] + min(t["raw_size"], t["vsize"] or t["raw_size"])]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        md.skipdata = True
        out = []
        for va, size, mn, ops in md.disasm_lite(code, t["va"]):
            out.append((va, size, mn, ops))
        return out

    def at(self, va):
        n = self.index.get(va)
        return self.insns[n] if n is not None else None

    def window(self, va, before=0, after=20):
        n = self.index.get(va)
        if n is None:
            n = bisect_right(self.addrs, va) - 1
        return self.insns[max(0, n - before): n + after + 1]

    # ---- functions ---------------------------------------------------------
    def functions(self):
        """Function starts: direct call targets plus `push ebp; mov ebp, esp`
        prologues and post-padding starts. Heuristic; good enough for MSVC6."""
        if self._funcs is not None:
            return self._funcs
        starts = set()
        t = self.pe.text()
        lo, hi = t["va"], t["va"] + t["vsize"]
        pad = ("int3", "nop")
        for n, (va, size, mn, ops) in enumerate(self.insns):
            if mn == "call" and ops.startswith("0x"):
                v = int(ops, 16)
                if lo <= v < hi:
                    starts.add(v)
            elif mn == "push" and ops == "ebp" and n + 1 < len(self.insns):
                nx = self.insns[n + 1]
                if nx[2] == "mov" and nx[3] == "ebp, esp":
                    starts.add(va)
            elif mn in ("ret", "jmp") and n + 1 < len(self.insns):
                # padding after an unconditional exit, then code => new function
                k = n + 1
                while k < len(self.insns) and self.insns[k][2] in pad:
                    k += 1
                if k > n + 1 and k < len(self.insns):
                    starts.add(self.insns[k][0])
        # Code pointers stored in data (vtables, message maps, callbacks).
        for s in self.pe.sections:
            if s["chars"] & 0x20000000 or s["raw_size"] == 0:
                continue
            blob = self.pe.data[s["raw_off"]:s["raw_off"] + s["raw_size"]]
            for i in range(0, len(blob) - 3, 4):
                v = int.from_bytes(blob[i:i + 4], "little")
                if lo <= v < hi and v in self.index:
                    starts.add(v)
        starts.update(self.thunk_to.values())
        # Code pointers pushed / moved as immediates (thread procs, WndProcs).
        for n, (va, size, mn, ops) in enumerate(self.insns):
            if mn in ("push", "mov") and "ptr" not in ops:
                for h in HEX.findall(ops):
                    v = int(h, 16)
                    if lo <= v < hi and v in self.index:
                        starts.add(v)
        self._funcs = sorted(starts)
        return self._funcs

    def func_containing(self, va):
        f = self.functions()
        i = bisect_right(f, va) - 1
        return f[i] if i >= 0 else None

    def func_body(self, start, max_insns=4000):
        """Instructions from `start` up to the next known function start."""
        f = self.functions()
        i = bisect_right(f, start)
        end = f[i] if i < len(f) else start + 0x10000
        n = self.index.get(start)
        if n is None:
            return []
        out = []
        while n < len(self.insns) and self.insns[n][0] < end and len(out) < max_insns:
            out.append(self.insns[n])
            n += 1
        return out

    def callers(self, target):
        """Direct call sites of target, including calls through its thunks."""
        return [va for va in self.refs_to_func(target) if self.at(va)[2] == "call"]

    def iat_calls(self, iat_va):
        """Instructions doing `call dword ptr [iat]` or `jmp dword ptr [iat]`,
        plus `mov reg, dword ptr [iat]` (MSVC often caches the import in a reg)."""
        return [va for va in self.refs.get(iat_va, [])]

    def thunks_for(self, iat_va):
        """Addresses of `jmp dword ptr [iat]` stubs (import thunks)."""
        return [va for va in self.refs.get(iat_va, []) if self.at(va)[2] == "jmp"]


def fmt(insn):
    va, size, mn, ops = insn
    return f"{va:08x}  {mn:<7} {ops}"
