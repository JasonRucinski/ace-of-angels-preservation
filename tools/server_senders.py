"""Server-side senders left in the 2.7.1 client (findings 9.43).

Usage: python -I tools/server_senders.py <2.7.1 client> <2.7.1 cache.pkl>
           <2.7.1 send_sites.json> <2.9.2 client> <out.json>

Lists every `Send<Name>` routine name found in the 2.7.1 executable's
strings but not in 2.9.2's, then ties each name to the function whose code
references a string containing it, and to that function's packet type and
length from send_sites.json. It also records code references to each such
function, directly or through its incremental-link thunk. A name with no
referencing code, or a function with no send site, is reported as such.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402

NAME_RE = re.compile(rb"(?:CAOAComm::|::)?(Send[A-Z][A-Za-z]+)")
HEX_RE = re.compile(r"0x[0-9a-f]{6,8}")


def send_names(path):
    return {m.group(1).decode() for m in NAME_RE.finditer(Path(path).read_bytes())}


def callers(d, target):
    """Functions referencing `target`, looking through `jmp target` thunks."""
    found = set()
    for ref in d.refs.get(target, []):
        insn = d.at(ref)
        if insn is not None and insn[2] == "jmp" and insn[3] == hex(target):
            found |= {d.func_containing(r) or r for r in d.refs.get(ref, [])}
        else:
            found.add(d.func_containing(ref) or ref)
    return sorted(found)


def main():
    old_path, cache, sites_path, new_path, out = sys.argv[1:6]
    pe = PE(old_path)
    d = Disasm(pe, cache)
    data = Path(old_path).read_bytes()
    sites = json.loads(Path(sites_path).read_text(encoding="utf-8"))["sites"]
    by_function = {}
    for s in sites:
        by_function.setdefault(int(s["function"], 16), []).append((s["type_hex"], s["length"]))
    refs = {}
    for va, _, _, ops in d.insns:
        for h in HEX_RE.findall(ops):
            refs.setdefault(int(h, 16), []).append(va)
    rows = []
    for name in sorted(send_names(old_path) - send_names(new_path)):
        functions = {}
        for m in re.finditer(re.escape(name.encode()) + rb"(?![A-Za-z])", data):
            start = m.start()
            while start and 32 <= data[start - 1] < 127:
                start -= 1
            va = pe.off_to_va(start)
            for ref in refs.get(va, []):
                f = d.func_containing(ref)
                if f is not None:
                    functions.setdefault(f, pe.cstr(va, 120))
        for f, text in sorted(functions.items()):
            rows.append({"name": name, "function": hex(f), "string": text,
                         "sends": [{"type": t, "length": n} for t, n in by_function.get(f, [])],
                         "callers": [hex(c) for c in callers(d, f)]})
        if not functions:
            rows.append({"name": name, "function": None, "string": None, "sends": [], "callers": []})
    # Packet types with a send site in 2.7.1 but none in 2.9.2, named or not.
    new_sites = Path(sites_path.replace("2.7.1", "2.9.2"))
    new_types = {s["type"] for s in json.loads(new_sites.read_text(encoding="utf-8"))["sites"]}
    old_only = [{"type": s["type_hex"], "length": s["length"], "function": s["function"],
                 "size_matches": s["size_matches"],
                 "callers": [hex(c) for c in callers(d, int(s["function"], 16))]}
                for s in sites if s["type"] not in new_types]
    result = {"old_client": Path(old_path).name, "new_client": Path(new_path).name,
              "names_only_in_old": len({r["name"] for r in rows}), "rows": rows,
              "types_sent_only_in_old": old_only}
    Path(out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        sends = ", ".join(f"{s['type']}/{s['length']}" for s in r["sends"]) or "-"
        print(f"{r['name']:28} {r['function'] or '-':10} sends {sends:16} callers {r['callers'] or '-'}")


if __name__ == "__main__":
    main()
