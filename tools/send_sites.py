"""Find outgoing-packet construction sites: immediate stores of a type byte
to [reg + 0x498] and of a length to [reg + 0x494] (CComm packet object
layout, see CComm::SendPacket 0x60DDB0).

Usage: python -I tools/send_sites.py <client.exe> <cache.pkl> <packet_sizes.json|-> <out.json>

For each type store, the nearest length store within +-12 instructions in
the same function is paired with it. Lengths are compared with the compiled
structure-size diagnostics (packet_sizes.json) to suggest candidate names;
a size match is only a hint, because several structures share sizes.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402

TYPE_RE = re.compile(r"^byte ptr \[(\w+) \+ 0x498\], (0x[0-9a-f]+|\d+)$")
LEN_RE = re.compile(r"^dword ptr \[(\w+) \+ 0x494\], (0x[0-9a-f]+|\d+)$")


def main():
    path, cache, sizes_path, out = sys.argv[1:5]
    pe = PE(path)
    d = Disasm(pe, cache)
    by_size = {}
    if sizes_path != "-":
        for r in json.loads(Path(sizes_path).read_text(encoding="utf-8"))["rows"]:
            by_size.setdefault(r["value"], []).append(r["name"])
    sites = []
    for n, (va, size, mn, ops) in enumerate(d.insns):
        if mn != "mov":
            continue
        m = TYPE_RE.match(ops)
        if not m:
            continue
        reg, ptype = m.group(1), int(m.group(2), 0)
        f = d.func_containing(va)
        length = None
        best = 99
        for k in range(max(0, n - 12), min(len(d.insns), n + 13)):
            lm = LEN_RE.match(d.insns[k][3]) if d.insns[k][2] == "mov" else None
            if lm and lm.group(1) == reg and d.func_containing(d.insns[k][0]) == f and abs(k - n) < best:
                best, length = abs(k - n), int(lm.group(2), 0)
        sites.append({"type": ptype, "type_hex": f"0x{ptype:02x}", "length": length, "va": hex(va),
                      "function": hex(f), "size_matches": by_size.get(length, []) if length is not None else []})
    sites.sort(key=lambda s: (s["type"], s["va"]))
    Path(out).write_text(json.dumps({"file": Path(path).as_posix(), "count": len(sites), "sites": sites},
                                    indent=1), encoding="utf-8")
    print(f"{len(sites)} type stores; {len({s['type'] for s in sites})} distinct types")
    for s in sites:
        print(f"  {s['type_hex']} len={s['length']!s:>4} at {s['va']} fn {s['function']}  {s['size_matches'][:4]}")


if __name__ == "__main__":
    main()
