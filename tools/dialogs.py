"""List dialog templates (RT_DIALOG) and their controls from a PE's resources.

Usage: python -I tools/dialogs.py <client.exe> <out.json> [control_id_hex ...]

Parses classic DLGTEMPLATE and DLGTEMPLATEEX. Prints dialogs containing any
of the requested control IDs (all dialogs if none are given).
"""
import json
import struct
import sys
from pathlib import Path

import pefile

ATOMS = {0x80: "Button", 0x81: "Edit", 0x82: "Static", 0x83: "ListBox", 0x84: "ScrollBar", 0x85: "ComboBox"}


def sz_or_ord(b, o):
    w = struct.unpack_from("<H", b, o)[0]
    if w == 0:
        return "", o + 2
    if w == 0xFFFF:
        return struct.unpack_from("<H", b, o + 2)[0], o + 4
    end = o
    while struct.unpack_from("<H", b, end)[0]:
        end += 2
    return b[o:end].decode("utf-16le", "replace"), end + 2


def align4(o):
    return (o + 3) & ~3


def parse(b):
    ex = struct.unpack_from("<HH", b, 0) == (1, 0xFFFF)
    if ex:
        _, _, _helpid, _exstyle, style, n, x, y, cx, cy = struct.unpack_from("<HHIIIHhhhh", b, 0)
        o = 26
    else:
        style, _exstyle, n, x, y, cx, cy = struct.unpack_from("<IIHhhhh", b, 0)
        o = 18
    menu, o = sz_or_ord(b, o)
    cls, o = sz_or_ord(b, o)
    title, o = sz_or_ord(b, o)
    if style & 0x40:  # DS_SETFONT
        o += 6 if ex else 2
        _face, o = sz_or_ord(b, o)
    ctrls = []
    for _ in range(n):
        o = align4(o)
        if ex:
            _help, _exs, cstyle, x, y, cx, cy, cid = struct.unpack_from("<IIIhhhhI", b, o)
            o += 24
        else:
            cstyle, _exs, x, y, cx, cy, cid = struct.unpack_from("<IIhhhhH", b, o)
            o += 18
        ccls, o = sz_or_ord(b, o)
        text, o = sz_or_ord(b, o)
        extra = struct.unpack_from("<H", b, o)[0]
        o += 2 + extra
        ctrls.append({"id": cid, "id_hex": hex(cid), "class": ATOMS.get(ccls, ccls), "text": text,
                      "rect": [x, y, cx, cy], "style": hex(cstyle)})
    return {"title": title, "class": cls, "controls": ctrls}


def main():
    path, out, *want = sys.argv[1:]
    want = {int(w, 16) for w in want}
    pe = pefile.PE(path)
    res = []
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id != 5:
            continue
        for e in t.directory.entries:
            for lang in e.directory.entries:
                d = lang.data.struct
                blob = pe.get_data(d.OffsetToData, d.Size)
                try:
                    dlg = parse(blob)
                except struct.error:
                    continue
                dlg["resource_id"] = e.id if e.id is not None else str(e.name)
                res.append(dlg)
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    for dlg in res:
        ids = {c["id"] for c in dlg["controls"]}
        if want and not ids & want:
            continue
        print(f"dialog {dlg['resource_id']} '{dlg['title']}' ({len(dlg['controls'])} controls)")
        for c in dlg["controls"]:
            mark = "  <==" if c["id"] in want else ""
            print(f"   {c['id_hex']:>7} {str(c['class']):<10} {c['text']!r}{mark}")


if __name__ == "__main__":
    main()
