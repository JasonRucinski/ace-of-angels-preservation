"""Decode a SCENARIOS.AOA mission file (the only known one is Curt3).

The file is a stream of u32/u16 fields and tagged strings
(u32 0x05765768, u32 length, bytes, NUL). This decoder applies one fixed
grammar and must consume the file to the exact last byte; any mismatch
raises. Field *names* are inferred from contents (team, role, waypoint
verbs), not from the client's loader, which is not yet traced.

  header   u32 magic 0x8155108D, u16, u16, str name, u32, u16, u16, str
  teams    u32 n; each: str name, u32 n_rel; each rel: str team, u32 x4
  groups   u32 n; each:
             str name, str team, u32, str s1, str role, u32 kind,
             u32 n_members; each: str, str, str ship_type, str callsign
             str objective, str briefing, str, str
             u32 n_orders; each: str target_group, str verb, u32 x5
             u32 n_waypoints; each: str action, str target,
                                    i32 x, i32 y, i32 z, u32, u32 radius, u32 flag

Usage: python -I tools/decode_scenario.py <scenario> [out.json]
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

STR_TAG = 0x05765768
MAGIC = 0x8155108D


class Reader:
    def __init__(self, data):
        self.d, self.p = data, 0

    def u16(self):
        v = struct.unpack_from("<H", self.d, self.p)[0]
        self.p += 2
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.d, self.p)[0]
        self.p += 4
        return v

    def s(self):
        at = self.p
        if self.u32() != STR_TAG:
            raise ValueError(f"expected string tag at 0x{at:x}")
        n = self.u32()
        raw = self.d[self.p:self.p + n]
        if len(raw) != n or self.d[self.p + n:self.p + n + 1] != b"\0":
            raise ValueError(f"bad string at 0x{at:x}")
        self.p += n + 1
        return raw.decode("latin1")

    def count(self, limit=64):
        n = self.u32()
        if n > limit:
            raise ValueError(f"implausible count {n} at 0x{self.p - 4:x}")
        return n


def decode(data):
    r = Reader(data)
    if r.u32() != MAGIC:
        raise ValueError("not a scenario file (magic)")
    header = {"u16a": r.u16(), "u16b": r.u16(), "name": r.s(),
              "u32": r.u32(), "u16c": r.u16(), "u16d": r.u16(), "text": r.s()}
    teams = []
    for _ in range(r.count()):
        name = r.s()
        rel = [{"team": r.s(), "values": [r.u32() for _ in range(4)]} for _ in range(r.count())]
        teams.append({"name": name, "relations": rel})
    groups = []
    for _ in range(r.count()):
        g = {"name": r.s(), "team": r.s(), "u32": r.u32(), "s1": r.s(), "role": r.s(),
             "kind": r.u32()}
        g["members"] = [{"s0": r.s(), "s1": r.s(), "ship_type": r.s(), "callsign": r.s()}
                        for _ in range(r.count())]
        g.update(objective=r.s(), briefing=r.s(), s2=r.s(), s3=r.s())
        g["orders"] = [{"target_group": r.s(), "verb": r.s(), "values": [r.u32() for _ in range(5)]}
                       for _ in range(r.count())]
        g["waypoints"] = [{"action": r.s(), "target": r.s(),
                           "position": [r.i32(), r.i32(), r.i32()],
                           "u32": r.u32(), "radius": r.u32(), "flag": r.u32()}
                          for _ in range(r.count())]
        groups.append(g)
    if r.p != len(data):
        raise ValueError(f"grammar stopped at 0x{r.p:x} of 0x{len(data):x}")
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "consumed_exactly": True, "header": header, "teams": teams, "groups": groups}


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    out = decode(Path(sys.argv[1]).read_bytes())
    text = json.dumps(out, indent=1)
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
