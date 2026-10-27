"""Build the 2x skin pack from your own 2.9.2 game files.

Reads each skin named in config/texture-pack.json from the pinned original
TEXTURES.AOA / DATA.AOA of a game folder, upscales it with Real-ESRGAN and
writes TGAs plus _entries.json for tools/texture_pack.py. No game art is
stored in the repository; every player generates the pack locally.

Per skin: 16 px of wrap padding (seamless tiling), Real-ESRGAN
realesrgan-x4plus on RGB and separately on alpha (as grayscale), crop, Lanczos
to 2x, then a TGA with the original header fields, row order and footer.

Needs the unopened Real-ESRGAN ncnn-vulkan 20220424 Windows zip at
originals/tools/realesrgan-ncnn-vulkan-20220424/ (hash-checked) and a
Vulkan-capable GPU. Finished skins are kept, so an interrupted run resumes.

  python -I tools/build_texture_pack.py game/2.9.2
  python -I tools/build_texture_pack.py game/2.9.2 --group fighters
"""
import argparse
import hashlib
import io
import json
import re
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoapack
import texture_pack

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config/texture-pack.json"
ESRGAN_ZIP = ROOT / "originals/tools/realesrgan-ncnn-vulkan-20220424/realesrgan-ncnn-vulkan-20220424-windows.zip"
ESRGAN_SHA256 = "abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d"
ESRGAN_DIR = ROOT / "work/realesrgan-ncnn-vulkan-20220424"
ESRGAN_MEMBERS = ("realesrgan-ncnn-vulkan.exe", "vcomp140.dll",
                  "models/realesrgan-x4plus.bin", "models/realesrgan-x4plus.param")
OUT = ROOT / "work/texture-pack/build"
PAD = 16
TIMEOUT = 600


def prepare_esrgan():
    """Extract only the needed members of the hash-checked zip; return the exe."""
    exe = ESRGAN_DIR / ESRGAN_MEMBERS[0]
    if all((ESRGAN_DIR / m).is_file() for m in ESRGAN_MEMBERS):
        return exe
    if not ESRGAN_ZIP.is_file():
        raise SystemExit(f"missing {ESRGAN_ZIP.relative_to(ROOT)}; see docs/texture-pack.md")
    if hashlib.sha256(ESRGAN_ZIP.read_bytes()).hexdigest() != ESRGAN_SHA256:
        raise SystemExit(f"{ESRGAN_ZIP.name} does not match the expected SHA-256; download it again")
    with zipfile.ZipFile(ESRGAN_ZIP) as z:
        for member in ESRGAN_MEMBERS:  # fixed names: no paths taken from the archive
            target = ESRGAN_DIR / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(member))
    return exe


def esrgan_x4(exe):
    """Return f(image) -> 4x image using the Real-ESRGAN executable."""
    from PIL import Image

    def run(image):
        with tempfile.TemporaryDirectory() as folder:
            src, dst = Path(folder) / "in.png", Path(folder) / "out.png"
            image.save(src)
            subprocess.run([str(exe), "-i", str(src), "-o", str(dst), "-n", "realesrgan-x4plus",
                            "-m", str(exe.parent / "models")], check=True, capture_output=True, timeout=TIMEOUT)
            with Image.open(dst) as out:
                out.load()
                return out.convert("RGB")
    return run


def wrap_pad(image, pad):
    from PIL import Image
    w, h = image.size
    padded = Image.new(image.mode, (w + 2 * pad, h + 2 * pad))
    for dx in (-w, 0, w):
        for dy in (-h, 0, h):
            padded.paste(image, (pad + dx, pad + dy))
    return padded


def upscale_tga(data, x4):
    """Return a 2x TGA for an uncompressed 24/32-bit TGA, using x4(RGB image)."""
    from PIL import Image
    texture_pack.check_tga("source", data)
    w, h = struct.unpack_from("<HH", data, 12)
    bpp, descriptor = data[16], data[17]
    footer = data[18 + data[0] + w * h * bpp // 8:]
    with Image.open(io.BytesIO(data)) as source:
        source = source.convert("RGBA" if bpp == 32 else "RGB")
    pad = min(PAD, w // 2, h // 2)
    box = (4 * pad, 4 * pad, 4 * (pad + w), 4 * (pad + h))
    size = (2 * w, 2 * h)
    # Colour and alpha are resized separately: an RGBA resize premultiplies,
    # turning colour under transparent pixels black, which filtering and
    # mipmaps then bleed into cutout edges as dark fringes.
    result = x4(wrap_pad(source.convert("RGB"), pad)).crop(box).resize(size, Image.Resampling.LANCZOS)
    if bpp == 32:
        alpha = x4(wrap_pad(source.getchannel("A").convert("RGB"), pad)).crop(box).getchannel("R")
        result = Image.merge("RGBA", (*result.split(), alpha.resize(size, Image.Resampling.LANCZOS)))
    rows = result if descriptor & 0x20 else result.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    header = bytearray(data[:18 + data[0]])
    struct.pack_into("<HH", header, 12, 2 * w, 2 * h)
    out = bytes(header) + rows.tobytes("raw", "BGRA" if bpp == 32 else "BGR") + footer
    with Image.open(io.BytesIO(out)) as check:  # written rows decode back to the result
        if check.convert(result.mode).tobytes() != result.tobytes():
            raise ValueError("TGA round trip failed")
    return out


def file_name(entry):
    return re.sub(r"[^A-Za-z0-9.\-]", "_", entry.rpartition(":")[2])


def sources(game_dir, entries):
    """Yield (entry, tga bytes) from the folder's pinned original archives."""
    key0 = aoapack.builtin_key(game_dir / "AOACLIENT.EXE")
    for name in texture_pack.ARCHIVES:
        wanted = {e.rpartition(":")[2].lower(): e for e in entries if e.upper().startswith(name + ":")}
        if not wanted:
            continue
        d, key, _, items = aoapack.read_archive_bytes(texture_pack.original(game_dir, name), key0)
        for item in items:
            entry = wanted.pop(item["name"].lower(), None)
            if entry:
                yield entry, aoapack.entry_bytes(d, key, key0, item)[0]
        if wanted:
            raise KeyError(f"not in {name}: {sorted(wanted.values())}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game_dir", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--group", action="append", help="manifest group(s) to build; default all")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    groups = args.group or list(manifest["groups"])
    entries = [e for g in groups for e in manifest["groups"][g]]
    x4 = esrgan_x4(prepare_esrgan())
    args.out.mkdir(parents=True, exist_ok=True)
    done, started = {}, time.monotonic()
    for i, (entry, data) in enumerate(sources(args.game_dir, entries), 1):
        target = args.out / file_name(entry)
        if not target.is_file():
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(upscale_tga(data, x4))
            temporary.replace(target)
        done[entry] = target.name
        print(f"[{i}/{len(entries)}] {entry} ({time.monotonic() - started:.0f}s)", flush=True)
    listing = args.out / "_entries.json"
    previous = json.loads(listing.read_text(encoding="utf-8")) if listing.is_file() else {}
    previous.update(done)
    listing.write_text(json.dumps(previous, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(done)} skins in {args.out}; install with:\n"
          f"  .venv\\Scripts\\python.exe -I tools\\texture_pack.py {args.game_dir} --from-dir {args.out}")


if __name__ == "__main__":
    main()
