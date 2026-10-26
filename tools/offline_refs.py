"""Find code paths that read the client's 'offline' flag.

Usage: python -I tools/offline_refs.py <client.exe> <cache.pkl> <flags_va> <out.json>

LoginToStation (2.7.1: 0x473650) stores (offline & 1) << 8 into the global
flag word at <flags_va> (2.7.1: 0x6A39B4). A read is counted when
`mov REG, dword ptr [flags]` is followed within 6 instructions by
`shr REG, 8` and a bit-0 test/and/sete on the same register.
Containing functions are attributed to source files via the debug-path
strings they reference (an approximation).
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402

REG8 = {"eax": "al", "ebx": "bl", "ecx": "cl", "edx": "dl"}


def main():
    path, cache, flags_s, out = sys.argv[1:5]
    flags = int(flags_s, 16)
    pe = PE(path)
    d = Disasm(pe, cache)
    hits = []
    for x in d.refs.get(flags, []):
        n = d.index[x]
        va, size, mn, ops = d.insns[n]
        m = re.match(rf"(\w+), dword ptr \[{hex(flags)}\]$", ops)
        if mn != "mov" or not m:
            continue
        reg = m.group(1)
        seq = d.insns[n + 1:n + 7]
        shr = next((i for i, s in enumerate(seq) if s[2] == "shr" and s[3] == f"{reg}, 8"), None)
        if shr is None:
            continue
        r8 = REG8.get(reg, "")
        tail = seq[shr + 1:shr + 4]
        if any((s[2] in ("test", "and") and s[3] in (f"{reg}, 1", f"{r8}, 1")) for s in tail):
            hits.append(va)
    funcs = collections.Counter(d.func_containing(h) for h in hits)
    rows = []
    for f, n in sorted(funcs.items()):
        files = collections.Counter()
        strs = []
        for ins in d.func_body(f, 4000):
            for h in re.findall(r"0x[0-9a-f]+", ins[3]):
                v = int(h, 16)
                s = pe.cstr(v, 120) if pe.section_of_va(v) and v >= pe.base + 0x1000 else None
                if s and len(s) > 4 and s.isprintable():
                    if ".cpp" in s:
                        files[s.split("\\")[-1]] += 1
                    elif len(strs) < 4:
                        strs.append(s[:70])
        rows.append({"function": hex(f), "reads": n, "source_files": dict(files), "strings": strs})
    res = {"file": Path(path).as_posix(), "flags_va": hex(flags), "reads": len(hits),
           "functions": len(funcs), "rows": rows}
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{len(hits)} offline-flag reads in {len(funcs)} functions")
    for r in rows:
        print(f"  {r['function']} x{r['reads']} {list(r['source_files'])[:2]} {r['strings'][:3]}")


if __name__ == "__main__":
    main()
