#!/usr/bin/env python3
"""Read the compiled-in version of an Ace of Angels client (AOACLIENT.EXE).

The client keeps major/minor/patch in three initialised .data globals and only
ever reads them, e.g. for "Entering Ace of Angels runtime client ver(%d.%d.%d)".
The bundled AOANOTES.TXT is not trustworthy -- the 2004 build's notes say
v2.3.0 while the binary is v2.9.2.

Method: find a version format string, find the `push imm32` of its address,
take the absolute-address loads (mov reg, [abs]) just before it, and read
those dwords from the file. No disassembler needed.

    python3 -I tools/aoa_version.py AOACLIENT.EXE
    python3 -I tools/aoa_version.py AOACLIENT.EXE --detail [--out probe.json]

--detail (needs capstone and pefile, imported only then) also disassembles
the client and examines every code reference to every ASCII string holding
"%d.%d.%d": the three dword arguments pushed just before the format string
are resolved (either `push dword ptr [G]` or `mov reg, dword ptr [G]` ...
`push reg`). Values are read through the section table; addresses inside a
section's virtual size but past its raw data are reported as virtual
zero-fill (0). It also counts every instruction referencing each global and
whether it writes, prints the call sites, and with --out writes them as JSON
(the evidence/<version>/version_probe.json layout).

The older `aoa.research.version_probe CLIENT CACHE OUT` form (tools/run.py)
still works: it means --detail --out OUT. The disassembly cache is kept in
work/cache/ by the client's SHA-256, so CACHE is ignored.
"""
import json
import re
import struct
import sys
from pathlib import Path

from aoa import cli  # noqa: E402
from aoa.formats.pe import Image
from aoa.analysis.cache_args import drop_cache_args

FORMATS = [
    b"Entering Ace of Angels runtime client ver(%d.%d.%d)",
    b"Ace of Angels (v%d.%d.%d Beta)",
    b"Ace of Angels v%d.%d.%d",
]
# mov eax,[moffs32] is A1; mov r32,[disp32] is 8B with modrm 00 reg 101.
LOADS = {b"\xa1": 1, b"\x8b\x0d": 2, b"\x8b\x15": 2, b"\x8b\x1d": 2,
         b"\x8b\x35": 2, b"\x8b\x3d": 2}

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


def detail(path):
    """The --detail report: every "%d.%d.%d" call site, its globals and their references."""
    from aoa.analysis.pe_util import PE, Disasm
    pe = PE(path)
    d = Disasm(pe)
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
    return summary


def show_detail(summary):
    for r in summary["call_sites"]:
        gs = r.get("globals")
        print(r["xref_va"], r["format"][:45].ljust(45),
              " / ".join(f"{g['va']}(off {g['file_off']})={g['value']}" for g in gs) if gs else "unresolved")
    print("global refs:", json.dumps(summary["global_ref_stats"]))
    print("distinct versions:", summary["distinct_versions"])


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("client", help="the AOACLIENT.EXE to read")
    ap.add_argument("legacy_out", nargs="?", metavar="OUT",
                    help="the old version_probe form: the same as --detail --out OUT")
    ap.add_argument("--detail", action="store_true",
                    help="also resolve every %%d.%%d.%%d call site with a disassembler (needs capstone)")
    ap.add_argument("--out", help="with --detail: write the call sites as JSON to this file")
    a = ap.parse_args(drop_cache_args(argv))
    if a.legacy_out:
        if a.out:
            ap.error("give OUT or --out, not both")
        a.detail, a.out = True, a.legacy_out
    if a.out and not a.detail:
        ap.error("--out needs --detail")
    d = open(a.client, "rb").read()
    image = Image(d)
    results = set()
    for fmt in FORMATS:
        soff = d.find(fmt)
        if soff < 0:
            continue
        sva = image.off_to_va(soff)
        push = b"\x68" + struct.pack("<I", sva)
        p = 0
        while (p := d.find(push, p)) >= 0:
            window = d[max(0, p - 64):p]
            addrs = []
            for k in range(len(window)):
                for op, n in LOADS.items():
                    if window[k:k + n] == op and k + n + 4 <= len(window):
                        addrs.append(struct.unpack_from("<I", window, k + n)[0])
            # The last three loads before the push are the arguments.
            cand = sorted(set(addrs[-3:]))
            if len(cand) == 3 and cand[1] - cand[0] == 4 and cand[2] - cand[1] == 4:
                o = image.va_to_off(cand[0])
                if o is not None:
                    v = struct.unpack_from("<III", d, o)
                    results.add(v)
                    print(f"{fmt.decode()!r} @ {sva:#x}: globals {cand[0]:#x}.. -> "
                          f"v{v[0]}.{v[1]}.{v[2]}")
            p += 1
    if not results:
        message = "no version found (format strings or load pattern differ in this build)"
        if not a.detail:
            sys.exit(message)
        print(message)
    if len(results) > 1:
        print("warning: references disagree:", sorted(results))
    if a.detail:
        summary = detail(a.client)
        if a.out:
            Path(a.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        show_detail(summary)


if __name__ == "__main__":
    sys.exit(cli.run(main))
