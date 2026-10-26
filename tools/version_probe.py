"""Recover the runtime version from the globals passed to "%d.%d.%d" formats.

Usage: python -I tools/version_probe.py <client.exe> <cache.pkl> <out.json>

For every ASCII string containing "%d.%d.%d", each code reference is examined:
the three dword arguments pushed just before the format string are resolved
(either `push dword ptr [G]` or `mov reg, dword ptr [G]` ... `push reg`).
Values are read through the section table; addresses inside a section's
virtual size but past its raw data are reported as virtual zero-fill (0).
Also counts every instruction referencing each global and whether it writes.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402

MEM = re.compile(r"^dword ptr \[(0x[0-9a-f]+)\]$")


def resolve_pushes(d, xref_va, want=3, window=24):
    """Return the `want` values pushed immediately before the format push,
    ordered as format arguments (first %d first)."""
    insns = d.window(xref_va, window, 0)
    idx = [i for i, ins in enumerate(insns) if ins[0] == xref_va][0]
    # Pushes after the format push are not args; walk backwards from it.
    # Register->global map must be "as of" each push, so do a forward pass.
    regs, pushes = {}, []
    for ins in insns[:idx]:
        va, _, mn, ops = ins
        if mn == "mov":
            dst, _, src = ops.partition(", ")
            m = MEM.match(src)
            if dst in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
                regs[dst] = int(m.group(1), 16) if m else None
        elif mn == "push":
            m = MEM.match(ops)
            if m:
                pushes.append((va, int(m.group(1), 16)))
            else:
                pushes.append((va, regs.get(ops)))
        elif mn == "call":
            pushes.clear()
            regs.clear()
        elif mn in ("lea", "xor", "add", "sub", "and", "or", "movsx", "movzx", "pop", "inc", "dec"):
            dst = ops.split(", ")[0]
            if dst in regs:
                regs[dst] = None
    # The last pushes before `push fmt` are the first format args. Some call
    # sites push the output buffer pointer (lea) after the args; those are
    # register pushes resolved to None and are skipped when they are last.
    while pushes and pushes[-1][1] is None:
        pushes.pop()
    args = [g for _, g in reversed(pushes[-want:])]
    return args if len(args) == want and all(args) else None


def main():
    path, cache, out = sys.argv[1:4]
    pe = PE(path)
    d = Disasm(pe, cache)
    results, globals_seen = [], {}
    for m in re.finditer(rb"[\x20-\x7e]*%d\.%d\.%d[\x20-\x7e]*", pe.data):
        sva = pe.off_to_va(m.start())
        for x in d.refs.get(sva, []):
            g = resolve_pushes(d, x)
            rec = {"format": m.group().decode(), "format_off": hex(m.start()), "format_va": hex(sva),
                   "xref_va": hex(x), "function": hex(d.func_containing(x))}
            if g:
                rec["globals"] = []
                for gv in g:
                    off = pe.va_to_off(gv)
                    rec["globals"].append({"va": hex(gv), "file_off": hex(off) if off is not None else None,
                                           "value": pe.u32(gv),
                                           "backing": "file" if off is not None else "virtual zero-fill"})
                    globals_seen[gv] = True
            results.append(rec)
    gstats = {}
    for gv in globals_seen:
        refs = d.refs.get(gv, [])
        writes = [hex(r) for r in refs
                  if d.at(r)[2] in ("mov", "add", "sub", "inc", "dec", "or", "and")
                  and d.at(r)[3].startswith(f"dword ptr [{hex(gv)}]")]
        gstats[hex(gv)] = {"refs": len(refs), "writes": writes}
    versions = {tuple(r["globals"][i]["value"] for i in range(3)) for r in results if "globals" in r}
    summary = {"file": Path(path).as_posix(), "call_sites": results, "global_ref_stats": gstats,
               "distinct_versions": ["%d.%d.%d" % v for v in sorted(versions)]}
    Path(out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    for r in results:
        gs = r.get("globals")
        print(r["xref_va"], r["format"][:45].ljust(45),
              " / ".join(f"{g['va']}(off {g['file_off']})={g['value']}" for g in gs) if gs else "unresolved")
    print("global refs:", json.dumps(gstats))
    print("distinct versions:", summary["distinct_versions"])


if __name__ == "__main__":
    main()
