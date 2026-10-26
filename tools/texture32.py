"""Load 24/32-bit TGA textures as ARGB8888 instead of RGB565/ARGB4444.

The texture loader 0x562A30 fixes its texture-view depth at 16 bits. A 24-bit
TGA becomes RGB565, and a 32-bit TGA becomes ARGB4444 (alpha bits 4). The
allocator 0x563650 already creates ARGB8888 for depth 32 (alpha 0 is promoted
to 8), and the per-surface converters for 32-bit surfaces force 24-bit sources
opaque (0x558B80 ORs 0xFF000000). The 16-bit source path is kept: the 32-bit
surface's 16-bit converter is a bare `ret`.

Rewritten in place (no code cave):
  0x562AB8  je  L16            (target moved to the shared tail)
  0x562ABD  je  L24/32          (24-bit now joins the 32-bit block)
  0x562AE3  L24/32: add ecx,ecx; and eax,ecx; shr eax,2; jmp tail
            L16:    xor eax,eax
            tail:   mov [edi+4],ecx; mov [edi+8],eax; nop
Result: 16 -> (16, 0); 24 -> (32, 0); 32 -> (32, 8). edx stays 0.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

NAME = "texture-argb8888-v1"
BASE = 0x400000
SITES = (
    (0x562AB8, bytes.fromhex("7435"), bytes.fromhex("7432")),
    (0x562ABD, bytes.fromhex("7430"), bytes.fromhex("7424")),
    (0x562AE3, bytes.fromhex("894f04c7470804000000eb06894f04895708"),
     bytes.fromhex("01c921c8c1e802eb0231c0894f0489470890")),
)


def regions():
    return tuple((va - BASE, old, new) for va, old, new in SITES)


def state(data):
    found = [data[off:off + len(old)] == new for off, old, new in regions()]
    if all(found):
        return True
    if any(found) or any(data[off:off + len(old)] not in (old, new) for off, old, new in regions()):
        raise ValueError("unexpected texture-loader bytes or partial texture32 patch")
    return False


def configure(data, enabled=True):
    state(data)
    for off, old, new in regions():
        data = data[:off] + (new if enabled else old) + data[off + len(old):]
    return data


def install(exe, undo=False):
    import prepare_client
    exe = Path(exe).resolve()
    prepare_client.paths(exe)
    source = exe.read_bytes()
    info = prepare_client.inspect(source)
    backup = exe.with_suffix(".EXE.before-texture32")
    if not backup.exists():
        if undo or state(source):
            raise ValueError("missing texture32 exact-undo backup")
        prepare_client.atomic_write(backup, source)
    before = backup.read_bytes()
    before_info = prepare_client.inspect(before)
    if state(before):
        raise ValueError("texture32 backup already contains this patch")
    expected = prepare_client.configure(before, host=before_info["host"], experimental_texture32=True)
    if source not in (before, expected):
        raise ValueError("texture32 backup does not match this client")
    result = before if undo else expected
    prepare_client.prepare(exe, host=info["host"], experimental_texture32=not undo)
    if exe.read_bytes() != result:
        raise ValueError("texture32 verification failed")
    record = {"enabled": not undo, "sha256": prepare_client.sha(result),
              "undo_sha256": prepare_client.sha(before), "visual_acceptance": "pending",
              "scope": "TGA texture views: 24-bit -> 32/0 (ARGB8888 opaque), 32-bit -> 32/8 (ARGB8888); 16-bit unchanged"}
    prepare_client.atomic_write(exe.parent / "_texture32.json",
                               (json.dumps(record, indent=2) + "\n").encode())
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("client", type=Path)
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    print(json.dumps(install(args.client, args.undo), indent=2))
