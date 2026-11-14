"""Dump the client's compiled name/float configuration records.

Usage: python -I tools/config_records.py <client.exe> <cache.pkl> <name_len> <anchor_name> <out.json>

Records are <name_len>-byte NUL-padded ASCII names followed by a 4-byte
IEEE-754 float (2.7.1 and later: 64; 2.0.0 uses 32 per the handoff).
Starting at <anchor_name>, the table is walked backwards and forwards for as
long as entries keep the expected shape. Code references to each record
(name or value) are listed.
"""
import json
import re
import struct
import sys
from pathlib import Path

from aoa import cli  # noqa: E402
from aoa.analysis.pe_util import PE, Disasm  # noqa: E402

NAME = re.compile(rb"^[A-Za-z0-9_]{2,}\0+$")


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("client", help="client executable")
    ap.add_argument("cache", help="disassembly cache (.pkl) for that executable")
    ap.add_argument("name_len", type=int, help="record name length (64 for 2.7.1 and later, 32 for 2.0.0)")
    ap.add_argument("anchor", help="a record name known to be in the table")
    ap.add_argument("out", help="JSON file to write")
    a = ap.parse_args(argv)
    path, cache, nlen, anchor, out = a.client, a.cache, a.name_len, a.anchor, a.out
    stride = nlen + 4
    pe = PE(path)
    d = Disasm(pe, cache)
    a = pe.data.find(anchor.encode() + b"\0")
    assert a >= 0, "anchor not found"

    def ok(off):
        blob = pe.data[off:off + nlen]
        return len(blob) == nlen and NAME.match(blob) is not None

    start = a
    while ok(start - stride):
        start -= stride
    recs = []
    off = start
    while ok(off):
        name = pe.data[off:off + nlen].split(b"\0")[0].decode()
        val = struct.unpack_from("<f", pe.data, off + nlen)[0]
        va = pe.off_to_va(off)
        refs = sorted(set(d.refs.get(va, []) + d.refs.get(va + nlen, [])))
        recs.append({"name": name, "name_off": hex(off), "value_off": hex(off + nlen),
                     "name_va": hex(va), "value": val, "code_refs": [hex(r) for r in refs]})
        off += stride
    table_va = pe.off_to_va(start)
    res = {"file": Path(path).as_posix(), "name_len": nlen, "table_start_off": hex(start),
           "table_start_va": hex(table_va), "count": len(recs),
           "refs_to_table_start": [hex(r) for r in d.refs.get(table_va, [])], "records": recs}
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"{len(recs)} records from off {hex(start)} (va {hex(table_va)}); "
          f"refs to start: {res['refs_to_table_start'][:6]}")
    for r in recs:
        print(f"  {r['name']:<28} name@{r['name_off']} value@{r['value_off']} = {r['value']:g}  refs={r['code_refs'][:3]}")


if __name__ == "__main__":
    sys.exit(cli.run(main))
