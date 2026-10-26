"""List the nodes of a 2.0.0-format layout Gob (e.g. TestScene.Gob).

Partial decoder. Nodes are found by their tagged name string
(u32 0x05765768, u32 length, bytes, NUL); position is the f32 triple
0x4D bytes past the NUL terminator, followed by a scale triple. A node is accepted only
when that scale is (1, 1, 1) and the position is finite, so animation and
mesh blocks are skipped rather than misread. Parent/child structure is NOT
decoded: child positions (e.g. turrets under a flag) are local to their
parent and must not be read as world coordinates.

Usage: python -I tools/decode_legacy_layout.py <layout.Gob> [out.json]
"""
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

TAG = struct.pack("<I", 0x05765768)
POS = 0x4D


def decode(data):
    nodes, skipped = [], []
    for m in re.finditer(re.escape(TAG), data):
        k = m.start()
        n = struct.unpack_from("<I", data, k + 4)[0]
        name = data[k + 8:k + 8 + n]
        end = k + 8 + n
        if not 1 <= n <= 64 or data[end:end + 1] != b"\0" or not all(32 <= c < 127 for c in name):
            continue
        if end + POS + 24 > len(data):
            skipped.append({"offset": k, "name": name.decode()})
            continue
        pos = struct.unpack_from("<3f", data, end + POS)
        scale = struct.unpack_from("<3f", data, end + POS + 12)
        if all(abs(s - 1) < 1e-4 for s in scale) and all(math.isfinite(p) for p in pos):
            nodes.append({"offset": k, "name": name.decode(), "local_position": [round(p, 3) for p in pos]})
        else:
            skipped.append({"offset": k, "name": name.decode()})
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "node_count": len(nodes), "skipped_names": skipped, "nodes": nodes}


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    out = decode(Path(sys.argv[1]).read_bytes())
    text = json.dumps(out, indent=1)
    if len(sys.argv) == 3:
        Path(sys.argv[2]).write_text(text, encoding="utf-8")
        print(json.dumps({k: v for k, v in out.items() if k != "nodes"}))
    else:
        print(text)


if __name__ == "__main__":
    main()
