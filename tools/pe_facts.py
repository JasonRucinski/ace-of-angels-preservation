"""Dump PE identity facts: timestamp, linker, sections, imports, Rich header.

Usage: python -I tools/pe_facts.py <client.exe> <out.json>
"""
import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE  # noqa: E402


def main():
    path, out = sys.argv[1:3]
    p = PE(path)
    fh, oh = p.pe.FILE_HEADER, p.pe.OPTIONAL_HEADER
    rich = p.pe.parse_rich_header() or {}
    rich_vals = rich.get("values", [])
    rich_entries = [{"comp_id": f"{rich_vals[i]:08x}", "prod_id": rich_vals[i] >> 16,
                     "build": rich_vals[i] & 0xFFFF, "count": rich_vals[i + 1]}
                    for i in range(0, len(rich_vals), 2)]
    by_dll = {}
    for iat, full in sorted(p.imports.items()):
        dll, name = full.split("!", 1)
        by_dll.setdefault(dll, []).append({"iat_va": f"0x{iat:08x}", "name": name})
    facts = {
        "file": Path(path).as_posix(),
        "bytes": len(p.data),
        "sha256": hashlib.sha256(p.data).hexdigest(),
        "machine": hex(fh.Machine),
        "timedatestamp": fh.TimeDateStamp,
        "timedatestamp_utc": datetime.datetime.fromtimestamp(fh.TimeDateStamp, datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "linker": f"{oh.MajorLinkerVersion}.{oh.MinorLinkerVersion}",
        "image_base": hex(p.base),
        "entry_va": hex(p.base + oh.AddressOfEntryPoint),
        "size_of_image": hex(oh.SizeOfImage),
        "subsystem": oh.Subsystem,
        "sections": [{**s, "va": hex(s["va"]), "vsize": hex(s["vsize"]), "raw_off": hex(s["raw_off"]),
                      "raw_size": hex(s["raw_size"]), "chars": hex(s["chars"])} for s in p.sections],
        "rich_header": rich_entries,
        "imports": by_dll,
        "import_count": len(p.imports),
    }
    Path(out).write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print(json.dumps({k: facts[k] for k in ("file", "bytes", "sha256", "timedatestamp_utc", "linker",
                                            "image_base", "entry_va", "import_count")}, indent=1))
    for s in facts["sections"]:
        print("  ", s)
    for dll, names in by_dll.items():
        print(f"  {dll}: {len(names)}")


if __name__ == "__main__":
    main()
