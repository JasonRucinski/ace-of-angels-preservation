"""Extract a MSVC two-level switch (byte index table + dword jump table).

Usage: python -I tools/dispatch_table.py <client.exe> <cache.pkl> <switch_insn_va> <out.json>

<switch_insn_va> is the `jmp dword ptr [ecx*4 + JT]` instruction. The code
before it must be the usual MSVC pattern:
    add eax, -BASE ; cmp eax, MAX ; ja DEFAULT ; mov cl, [eax + IDX] ; jmp [ecx*4 + JT]
For each case value the first few calls in the case body are listed with
thunks resolved, plus strings referenced in the body.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402


def main():
    path, cache, sw_s, out = sys.argv[1:5]
    pe = PE(path)
    d = Disasm(pe, cache)
    sw = int(sw_s, 16)
    w = d.window(sw, 6, 0)
    base = mx = idx_tab = default = None
    for va, size, mn, ops in w:
        m = re.match(r"(\w+), (-?0x[0-9a-f]+|-?\d+)$", ops)
        if mn == "add" and m:
            base = -int(m.group(2), 0)
        elif mn == "sub" and m:
            base = int(m.group(2), 0)
        elif mn == "cmp" and m:
            mx = int(m.group(2), 0)
        elif mn == "ja":
            default = int(ops, 16)
        elif mn == "mov" and "byte ptr [eax + " in ops:
            idx_tab = int(re.search(r"0x[0-9a-f]+", ops).group(), 16)
    jt = int(re.search(r"0x[0-9a-f]+", d.at(sw)[3]).group(), 16)
    n_targets = max(pe.read_va(idx_tab, mx + 1)) + 1
    targets = [pe.u32(jt + 4 * i) for i in range(n_targets)]
    cases = []
    for k in range(mx + 1):
        value = k + (base or 0)
        t = targets[pe.read_va(idx_tab + k, 1)[0]]
        body = d.window(t, 0, 24)
        calls, strs = [], []
        for va, size, mn, ops in body:
            if mn == "call":
                if ops.startswith("0x"):
                    tgt = int(ops, 16)
                    calls.append(hex(d.resolve(tgt)))
                else:
                    calls.append(ops)
            for h in re.findall(r"0x[0-9a-f]+", ops):
                s = pe.cstr(int(h, 16), 120) if pe.section_of_va(int(h, 16)) else None
                if s and len(s) > 3 and s.isprintable():
                    strs.append(s)
            if mn == "jmp" or mn.startswith("ret"):
                break
        cases.append({"type": value, "type_hex": f"0x{value:02x}", "target": hex(t),
                      "is_default": t == default, "calls": calls[:4], "strings": strs[:3]})
    res = {"file": Path(path).as_posix(), "switch_insn": hex(sw), "base": base, "max_index": mx,
           "index_table": hex(idx_tab), "jump_table": hex(jt), "default": hex(default) if default else None,
           "distinct_targets": n_targets, "cases": cases}
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    handled = [c for c in cases if not c["is_default"]]
    print(f"switch at {hex(sw)}: types {base}..{base + mx}, {len(handled)} handled, default {hex(default)}")
    for c in handled:
        print(f"  {c['type_hex']} ({c['type']:3d}) -> {c['target']} calls {c['calls'][:3]} {c['strings'][:2]}")


if __name__ == "__main__":
    main()
