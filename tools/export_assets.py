"""Turn extracted AoA archive entries into a browsable asset tree.

Usage:
    python -I tools/export_assets.py <extracted_dir> <out_dir>

<extracted_dir> holds one sub-folder per archive as written by
`tools/aoapack.py extract` (files named NNNN_<entry name>, plus _index.json).
For each archive this writes <out_dir>/<ARCHIVE>/<entry name>:
  * .tga -> .png (uncompressed true-colour TGA, 24/32 bpp, honouring the
    origin bit; alpha kept), using only the standard library;
  * everything else is copied unchanged (BMP, MP3, WAV, scripts, and the
    still-undecoded model formats .gob/.sco/.shs).
Entry names are used only after stripping path separators. Writes
<out_dir>/_export.json listing every output with its SHA-256.
"""
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path


def tga_to_rgba(data):
    id_len, cmap_type, img_type = data[0], data[1], data[2]
    w, h, bpp, desc = struct.unpack_from("<HHBB", data, 12)
    if cmap_type != 0 or img_type != 2 or bpp not in (24, 32):
        raise ValueError(f"unsupported TGA (type {img_type}, {bpp} bpp, cmap {cmap_type})")
    px = bpp // 8
    start = 18 + id_len
    raw = data[start:start + w * h * px]
    if len(raw) < w * h * px:
        raise ValueError("truncated TGA")
    rows = []
    for y in range(h):
        row = raw[y * w * px:(y + 1) * w * px]
        out = bytearray(w * 4)
        out[0::4] = row[2::px]          # BGR(A) -> RGBA
        out[1::4] = row[1::px]
        out[2::4] = row[0::px]
        out[3::4] = row[3::px] if px == 4 else b"\xff" * w
        rows.append(bytes(out))
    if not desc & 0x20:                 # bottom-left origin
        rows.reverse()
    return w, h, rows


def png(w, h, rows):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    body = zlib.compress(b"".join(b"\0" + r for r in rows), 9)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", body) + chunk(b"IEND", b""))


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    record = []
    for arch in sorted(p for p in src.iterdir() if p.is_dir()):
        for f in sorted(arch.iterdir()):
            if f.name.startswith("_"):
                continue
            name = re.sub(r"^\d{4}_", "", f.name).replace("/", "_").replace("\\", "_")
            data = f.read_bytes()
            out = dst / arch.name / name
            out.parent.mkdir(parents=True, exist_ok=True)
            note = "copied"
            if name.lower().endswith(".tga"):
                try:
                    data = png(*tga_to_rgba(data))
                    out = out.with_suffix(".png")
                    note = "tga->png"
                except ValueError as e:
                    note = f"copied ({e})"
            out.write_bytes(data)
            record.append({"archive": arch.name, "entry": f.name, "out": out.relative_to(dst).as_posix(),
                           "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "note": note})
    (dst / "_export.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    counts = {}
    for r in record:
        counts[r["note"].split(" ")[0]] = counts.get(r["note"].split(" ")[0], 0) + 1
    print(f"exported {len(record)} files to {dst}: {counts}")


if __name__ == "__main__":
    main()
