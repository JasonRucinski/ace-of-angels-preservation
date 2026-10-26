"""Decode a CTerrainObjectHandler terrain map (*.TRN), e.g. JRMAP.TRN.

Format from the 2.0.0 client's ReadInTerrain (0x46F600; 2.9.2 keeps the
reader at 0x4967E0):

  u32 count
  count x 512-byte records; the reader checks u32 0xFADE1234 at +0x1FC
    +0x000 char database[64]   ("AoAObjects.odb")
    +0x040 char object[64]     ODB object name ("" for some marker kinds)
    +0x080 char name[24]       instance name ("---" = unnamed)
    +0x098 f32  rotation[9]
    +0x0BC f32  ?              (0)
    +0x0C0 f32  position[3]
    +0x1E4 u32  kind           (observed: 0 static model, 1 turret,
                                2 safe zone, 6 power-up zone (both 2.9.2
                                AddTerrainObject), 3 cube/buoy, 7 warp gate,
                                8 flag station; other labels are not from code)
    +0x1E8 u32  ?              (4 on static models and kind 2)
    +0x1EC u32  ?              (3/4/5 on turrets only)
  then 48-byte (char turret[24], char flag[24]) links until EOF

The records are raw struct dumps: pointers and MSVC debug fill (0xCDCDCDCD)
survive in unused fields. No field beyond these is interpreted.

2.9.2's reader (0x4967E0) takes 540-byte records (sentinel at +0x218). It
unpacks +0x00/+0x40/+0x80 names, +0x98..+0xAC rotation rows, position at
+0xC4, +0x104, +0x194 and kind at +0x200: the 2.0.0 fields shifted by 4 after
+0xC0 and by 28 after +0x194. convert_292 inserts zeros at those two points;
the links are unchanged. The object-creation call reads nothing else.

Usage: python -I tools/decode_trn.py <file.trn> [out.json]
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

SENTINEL = 0xFADE1234
REC = 512
REC_292 = 540
DATABASE, SAFE_ZONE_OBJECT = b"AoAObjects.odb", b"Cube"
LINK = 48


def cstr(b):
    return b.split(b"\0")[0].decode("latin1")


def decode(data):
    count = struct.unpack_from("<I", data, 0)[0]
    end = 4 + count * REC
    if end > len(data):
        raise ValueError(f"{count} records need {end} bytes, file has {len(data)}")
    records = []
    for i in range(count):
        r = 4 + i * REC
        if struct.unpack_from("<I", data, r + 0x1FC)[0] != SENTINEL:
            raise ValueError(f"record {i}: missing 0xFADE1234 sentinel")
        records.append({
            "index": i,
            "database": cstr(data[r:r + 0x40]),
            "object": cstr(data[r + 0x40:r + 0x80]),
            "name": cstr(data[r + 0x80:r + 0x98]),
            "kind": struct.unpack_from("<I", data, r + 0x1E4)[0],
            "u32_1e8": struct.unpack_from("<I", data, r + 0x1E8)[0],
            "u32_1ec": struct.unpack_from("<I", data, r + 0x1EC)[0],
            "rotation": [round(v, 6) for v in struct.unpack_from("<9f", data, r + 0x98)],
            "position": [round(v, 3) for v in struct.unpack_from("<3f", data, r + 0xC0)],
        })
    tail = data[end:]
    if len(tail) % LINK:
        raise ValueError(f"{len(tail)} trailing bytes are not whole {LINK}-byte links")
    links = [{"turret": cstr(tail[k:k + 24]), "flag": cstr(tail[k + 24:k + 48])}
             for k in range(0, len(tail), LINK)]
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "record_count": count, "link_count": len(links),
            "consumed_exactly": True, "records": records, "links": links}


def convert_292(data):
    """Rewrite a 2.0.0 terrain map for the 2.9.2 reader (see module notes).

    Kind-2 records (safe zones; half-size f32 at 2.9.2 +0x104) are saved with
    empty database and object names. 2.9.2's AddTerrainObject (0x4971F0)
    looks the object up (0x4CDA80) before its kind switch and drops them, so
    give them the names the layout path passes for a safe zone
    (CreateTerrainFromGfxInfo, category 7). The zone path builds no model.
    """
    count = decode(data)["record_count"]
    out = bytearray(data[:4])
    for i in range(count):
        r = data[4 + i * REC:4 + (i + 1) * REC]
        if struct.unpack_from("<I", r, 0x1E4)[0] == 2 and not r[0] and not r[0x40]:
            r = DATABASE.ljust(0x40, b"\0") + SAFE_ZONE_OBJECT.ljust(0x40, b"\0") + r[0x80:]
        out += r[:0xC0] + bytes(4) + r[0xC0:0x194] + bytes(24) + r[0x194:]
    out += data[4 + count * REC:]
    for i in range(count):
        base = 4 + i * REC_292
        assert struct.unpack_from("<I", out, base + REC_292 - 4)[0] == SENTINEL
    return bytes(out)


KIND_POWERUP_ZONE = 6


def powerup_zones_292(data):
    """Power-up zones of a 2.9.2 terrain map (540-byte records), in file order.

    ReadInTerrain (0x4967E0) passes record +0xC4 position, +0x104 half-size,
    +0x194 power-up type and +0x200 kind to AddTerrainObject (0x4971F0); its
    kind-6 case calls CAOAZoneHandler::AddPowerupZone (0x492C10) with the box
    centre +- half-size and the type (findings 9.44). Types are 0..4.
    """
    count = struct.unpack_from("<I", data, 0)[0]
    if 4 + count * REC_292 > len(data):
        raise ValueError(f"{count} records need {4 + count * REC_292} bytes, file has {len(data)}")
    zones = []
    for i in range(count):
        r = 4 + i * REC_292
        if struct.unpack_from("<I", data, r + REC_292 - 4)[0] != SENTINEL:
            raise ValueError(f"record {i}: missing 0xFADE1234 sentinel")
        if struct.unpack_from("<I", data, r + 0x200)[0] == KIND_POWERUP_ZONE:
            zones.append({"position": struct.unpack_from("<3f", data, r + 0xC4),
                          "half": struct.unpack_from("<f", data, r + 0x104)[0],
                          "type": struct.unpack_from("<I", data, r + 0x194)[0]})
    return zones


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    out = decode(Path(sys.argv[1]).read_bytes())
    text = json.dumps(out, indent=1)
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
        print(json.dumps({k: v for k, v in out.items() if k not in ("records", "links")}))
    else:
        print(text)


if __name__ == "__main__":
    main()
