"""Interactive-style static exploration CLI for one client.

Usage: python -I tools/explore.py <client.exe> <cache.pkl> <command> [args...]

Commands
  str <substring>            ASCII strings containing substring: file off, VA, xrefs
  xref <va>                  instructions referencing a VA constant
  callers <va>               direct `call <va>` sites (with containing function)
  imp <name>                 call sites of an import (via IAT and thunks)
  dis <va> [n]               disassemble n instructions from va
  func <va>                  disassemble the whole function containing va
  ctx <va> [before] [after]  instructions around va
  u32 <va> [count]           dwords at va
  f32 <va> [count]           floats at va
"""
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm, fmt  # noqa: E402


def annotate(pe, d, insn):
    s = fmt(insn)
    notes = []
    for h in re.findall(r"0x[0-9a-f]+", insn[3]):
        v = int(h, 16)
        if v in pe.imports:
            notes.append(pe.imports[v])
        elif pe.section_of_va(v) and v >= pe.base + 0x1000:
            st = pe.cstr(v, 200)
            if st and len(st) >= 3 and all(32 <= ord(c) < 127 or c in "\r\n\t" for c in st):
                notes.append(repr(st[:90]))
    if insn[2] in ("call", "jmp", "push", "mov") and re.search(r"0x[0-9a-f]+$", insn[3]):
        tgt = int(re.search(r"0x[0-9a-f]+$", insn[3]).group(), 16)
        real = d.resolve(tgt)
        if real != tgt:
            notes.append(f"thunk->{real:08x}")
            tgt = real
        t = d.at(tgt)
        if t and t[2] == "jmp" and "dword ptr [" in t[3]:
            m = re.search(r"0x[0-9a-f]+", t[3])
            if m and int(m.group(), 16) in pe.imports:
                notes.append("-> " + pe.imports[int(m.group(), 16)])
    return s + (("    ; " + " | ".join(notes)) if notes else "")


def ascii_strings(data, minlen=4):
    for m in re.finditer(rb"[\x20-\x7e\t\r\n]{%d,}" % minlen, data):
        yield m.start(), m.group().decode("ascii")


def main():
    path, cache, cmd, *args = sys.argv[1:]
    pe = PE(path)
    d = Disasm(pe, cache)
    if cmd == "str":
        needle = args[0].lower()
        for off, s in ascii_strings(pe.data):
            if needle in s.lower():
                va = pe.off_to_va(off)
                xr = d.refs.get(va, []) if va else []
                print(f"off=0x{off:06x} va={va and hex(va)} xrefs={[hex(x) for x in xr[:12]]}{'...' if len(xr) > 12 else ''}  {s[:160]!r}")
    elif cmd == "xref":
        va = int(args[0], 16)
        for x in d.refs.get(va, []):
            print(f"[func {d.func_containing(x):08x}] " + annotate(pe, d, d.at(x)))
    elif cmd == "callers":
        va = int(args[0], 16)
        for x in d.callers(va):
            print(f"[func {d.func_containing(x):08x}] {x:08x}")
    elif cmd == "imp":
        name = args[0]
        iats = [a for a, n in pe.imports.items() if n.split("!")[1] == name]
        for iat in iats:
            print(f"IAT {iat:08x} {pe.imports[iat]}")
            for x in d.refs.get(iat, []):
                ins = d.at(x)
                if ins[2] == "jmp":
                    print(f"  thunk {x:08x}")
                    for c in d.callers(x):
                        print(f"    call {c:08x}  [func {d.func_containing(c):08x}]")
                else:
                    print(f"  {x:08x}  {ins[2]} {ins[3]}  [func {d.func_containing(x):08x}]")
    elif cmd == "dis":
        va = int(args[0], 16)
        n = int(args[1]) if len(args) > 1 else 40
        for ins in d.window(va, 0, n - 1):
            print(annotate(pe, d, ins))
    elif cmd == "func":
        va = int(args[0], 16)
        f = d.func_containing(va)
        print(f"; function {f:08x}  callers={[hex(c) for c in d.callers(f)][:20]}")
        for ins in d.func_body(f):
            print(annotate(pe, d, ins))
    elif cmd == "ctx":
        va = int(args[0], 16)
        b = int(args[1]) if len(args) > 1 else 15
        a = int(args[2]) if len(args) > 2 else 15
        for ins in d.window(va, b, a):
            print(("=> " if ins[0] == va else "   ") + annotate(pe, d, ins))
    elif cmd == "range":
        # every string / import referenced by code in [lo, hi)
        lo, hi = int(args[0], 16), int(args[1], 16)
        from bisect import bisect_left
        for ins in d.insns[bisect_left(d.addrs, lo):]:
            if ins[0] >= hi:
                break
            line = annotate(pe, d, ins)
            if "; " in line:
                print(line)
    elif cmd == "funcs":
        lo, hi = int(args[0], 16), int(args[1], 16)
        for f in d.functions():
            if lo <= f < hi:
                print(f"{f:08x} callers={len(d.callers(f))} xrefs={len(d.refs.get(f, []))}")
    elif cmd in ("u32", "f32"):
        va = int(args[0], 16)
        n = int(args[1]) if len(args) > 1 else 8
        raw = pe.read_va(va, 4 * n)
        fmtc = "<%dI" % n if cmd == "u32" else "<%df" % n
        vals = struct.unpack(fmtc, raw)
        for i, v in enumerate(vals):
            print(f"{va + 4 * i:08x} off={pe.va_to_off(va + 4 * i)} {v if cmd == 'f32' else hex(v)}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
