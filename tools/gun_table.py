"""Dump the 2.9.2 client's static gun table (no game process).

Usage: python -I tools/gun_table.py CLIENT.EXE OUT.json

Layout from the reader at 0x4DA990: level i (1..10) has a 36-byte record at
0x5D62CC + 36*i. Field +6 is per-shot damage: server message 0x41
(SetGunDamage) overwrites it and the dword at +8 (0x430A7A). The level-to-id
switch at 0x4DAAC2 gives ids 250..850, matching the `.Sco` gun names
(Gun310, Gun-360). Other fields are copied to the weapon object at the
listed offsets; their meanings are not established and stay unnamed.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE  # noqa: E402

PRISTINE_292 = "4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e"
BASE, STRIDE = 0x5D62CC, 36
LEVEL_IDS = (250, 280, 310, 360, 410, 460, 550, 650, 750, 850)
# (record offset, struct format, weapon-object destination or meaning)
FIELDS = ((0x00, "<H", "obj+0x120"), (0x02, "<H", "obj+0x122"), (0x04, "<H", "obj+0x118"),
          (0x06, "<H", "damage (obj+0x11A)"), (0x08, "<f", "obj+0x11C (set with damage by 0x41)"),
          (0x0C, "<f", "obj+0x74"), (0x10, "<f", "obj+0x70 and obj+0x7C"),
          (0x14, "<H", "obj+0x102"), (0x16, "<H", "obj+0x104"), (0x18, "<H", "obj+0x106"),
          (0x1A, "<H", "obj+0x108"), (0x1C, "<b", "argument to 0x4C3D00"))


def main():
    exe, out = Path(sys.argv[1]), Path(sys.argv[2])
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if digest != PRISTINE_292:
        raise SystemExit("expected the original 2.9.2 executable")
    pe = PE(exe)
    guns = []
    for level, gun_id in enumerate(LEVEL_IDS, 1):
        record = pe.read_va(BASE + STRIDE * level, STRIDE)
        fields = {name: round(struct.unpack_from(fmt, record, offset)[0], 4) for offset, fmt, name in FIELDS}
        guns.append({"level": level, "id": gun_id, "object_kind": 0x0C if level <= 6 else 0x0D,
                     "record_va": hex(BASE + STRIDE * level), "fields": fields})
    out.write_text(json.dumps({"exe_sha256": digest, "reader": "0x4DA990", "guns": guns}, indent=1) + "\n")
    for gun in guns:
        print(gun["level"], gun["id"], gun["fields"]["damage (obj+0x11A)"])


if __name__ == "__main__":
    main()
