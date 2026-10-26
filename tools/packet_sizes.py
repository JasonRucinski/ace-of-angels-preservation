"""Extract the compiled structure-size diagnostics ("SFoo (%d)" log calls).

Usage: python -I tools/packet_sizes.py <client.exe> <cache.pkl> <out.json>

Locates the routine that logs "SPacketServerRegister (%d)" and parses every
    push <imm>        ; the logged value
    push <fmt VA>     ; "<Name> (%d)"
    push <log obj>
    call <log fn>
quadruple in it, in program order. The logged values look like sizeof()
results (see docs/protocol-notes.md); they are NOT treated as opcode IDs.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402

NAME_FMT = re.compile(r"^(S[A-Za-z0-9_]+) \(%d\)$")


def imm(ops):
    try:
        return int(ops, 16) if ops.startswith("0x") else int(ops)
    except ValueError:
        return None


def main():
    path, cache, out = sys.argv[1:4]
    pe = PE(path)
    d = Disasm(pe, cache)
    anchor_off = pe.data.find(b"SPacketServerRegister (%d)\0")
    if anchor_off < 0:
        res = {"file": Path(path).as_posix(), "count": 0, "rows": [],
               "absent": "no 'SPacketServerRegister (%d)' string; "
                         f"'SPacket' occurs {pe.data.count(b'SPacket')} times in the file"}
        Path(out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(res["absent"])
        return
    anchor_va = pe.off_to_va(anchor_off)
    xref = d.refs[anchor_va][0]
    # Walk back/forward from the anchor across the contiguous run of log calls.
    n0 = d.index[xref]
    lo = n0
    while lo > 0 and n0 - lo < 3000:
        lo -= 1
        if d.insns[lo][2] == "ret":
            break
    hi = n0
    while hi < len(d.insns) - 1 and hi - n0 < 3000:
        hi += 1
        if d.insns[hi][2] == "ret":
            break
    body = d.insns[lo + 1: hi + 1]
    rows, log_fns, log_objs = [], set(), set()
    for i in range(len(body) - 3):
        a, b, c, e = body[i:i + 4]
        if a[2] == b[2] == c[2] == "push" and e[2] == "call":
            fmt_va = imm(b[3])
            s = pe.cstr(fmt_va) if fmt_va else None
            m = NAME_FMT.match(s) if s else None
            val = imm(a[3])
            if m and val is not None:
                rows.append({"name": m.group(1), "value": val, "value_hex": hex(val),
                             "push_va": hex(a[0]), "format_va": hex(fmt_va),
                             "format_off": hex(pe.va_to_off(fmt_va)),
                             "log_obj": c[3], "log_fn": e[3]})
                log_fns.add(e[3])
                log_objs.add(c[3])
    result = {"file": Path(path).as_posix(), "routine_first_insn": hex(body[0][0]),
              "routine_last_insn": hex(body[-1][0]), "log_functions": sorted(log_fns),
              "log_objects": sorted(log_objs), "count": len(rows), "rows": rows}
    Path(out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{result['count']} size diagnostics; log fn {sorted(log_fns)} obj {sorted(log_objs)};"
          f" range {result['routine_first_insn']}..{result['routine_last_insn']}")
    for r in rows:
        print(f"  {r['push_va']}  {r['value']:>6}  {r['value_hex']:>7}  {r['name']}  fmt@{r['format_va']}")


if __name__ == "__main__":
    main()
