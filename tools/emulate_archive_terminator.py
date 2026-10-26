"""Run 2.9.2 CCompress::Decompress (0x52A630) before and after the
archive-terminator patch, in Unicorn (no game process).

Usage: python -I tools/emulate_archive_terminator.py CLIENT.EXE.orig OUT.json

The heap beyond each allocation is pre-filled with 0xAA, as a reused native
heap block can be. Original code must leave the byte after the data
non-zero (the missing terminator behind the arena-join crash); the patched
image must return identical data followed by a NUL.
"""
import hashlib
import json
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoapack  # noqa: E402
import prepare_client  # noqa: E402
from emulate_codec import Emu, HEAP, SCRATCH  # noqa: E402
from pe_util import PE  # noqa: E402

CTOR, DECOMPRESS = 0x52A0B0, 0x52A630


def run(image_path, packed):
    emu = Emu(PE(image_path))
    this = SCRATCH + 0x8000
    emu.thiscall(CTOR, this)
    emu.write(emu.brk, b"\xAA" * 0x40000)  # stale heap contents after every block
    source, length = SCRATCH + 0x1000, SCRATCH + 0x800
    emu.write(source, packed)
    emu.write(length, struct.pack("<I", len(packed)))
    out = emu.thiscall(DECOMPRESS, this, source, length)
    size = struct.unpack("<I", emu.read(length, 4))[0]
    return emu.read(out, size), emu.read(out + size, 1)[0]


def main():
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    original = source.read_bytes()
    body = b"".join(b"DxTgtWin_%d 20 %d 300 400 tgtwin2 icon\r\n" % (i, i * 7) for i in range(17))[:681]
    packed = aoapack.compress(body)
    result = {"client_sha256": hashlib.sha256(original).hexdigest(), "decompressor": hex(DECOMPRESS),
              "body_bytes": len(body), "packed_bytes": len(packed)}
    with tempfile.TemporaryDirectory() as tmp:
        for name, image in (("original", original), ("patched", prepare_client.configure(original))):
            path = Path(tmp) / f"{name}.exe"
            path.write_bytes(image)
            data, after = run(path, packed)
            result[name] = {"data_matches": data == body, "byte_after_data": hex(after),
                            "image_sha256": hashlib.sha256(image).hexdigest()}
    assert result["original"]["data_matches"] and result["patched"]["data_matches"]
    assert result["original"]["byte_after_data"] != "0x0", "original unexpectedly terminated"
    assert result["patched"]["byte_after_data"] == "0x0"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
