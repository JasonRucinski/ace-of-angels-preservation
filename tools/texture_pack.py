"""Install or remove replacement TGA skins in a game folder's archives.

Skins live in TEXTURES.AOA, and a few (e.g. natak-t1.tga, salamtex.tga) in
DATA.AOA. Each entry name is looked up case-insensitively in both; prefix
`DATA.AOA:` to choose when a name exists in both. Every packed archive is
rebuilt from its pinned original, kept as <ARCHIVE>.before-texture-pack;
_texture_pack.json records the installed hashes so prepare_client.check
accepts exactly these archives. Close the client first. Only uncompressed
24/32-bit TGAs are accepted; bigger images also need texture32 (otherwise
they still load as 16-bit).

  python -I tools/texture_pack.py <game_dir> ymkhtat.tga=work/.../ymkhtat.tga ...
  python -I tools/texture_pack.py <game_dir> --from-dir work/texture-pack/fighters/tga --from-dir ...
  python -I tools/texture_pack.py <game_dir> --undo
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoapack
import prepare_client

ARCHIVES = ("TEXTURES.AOA", "DATA.AOA")
SUFFIX = ".before-texture-pack"
RECORD = "_texture_pack.json"
KEY_CLIENT = Path(__file__).resolve().parents[1] / "work/2.7.1/members/15_AOACLIENT.EXE"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(name):
    return json.loads(prepare_client.ASSET_MANIFEST.read_text(encoding="utf-8"))["required"][name]["sha256"]


def check_tga(name, data):
    if len(data) < 18 or data[1] != 0 or data[2] != 2 or data[16] not in (24, 32):
        raise ValueError(f"{name}: expected an uncompressed 24/32-bit TGA")
    width, height = struct.unpack_from("<HH", data, 12)
    if not (width and height and width <= 2048 and height <= 2048):
        raise ValueError(f"{name}: dimensions {width}x{height} outside the client's 1..2048 texture caps")
    if len(data) < 18 + data[0] + width * height * data[16] // 8:
        raise ValueError(f"{name}: truncated pixel data")


def original(folder, name):
    """Pinned original bytes: the backup when packed, else the live archive."""
    backup = folder / (name + SUFFIX)
    data = (backup if backup.exists() else folder / name).read_bytes()
    if sha(data) != pinned(name):
        raise ValueError(f"{backup.name if backup.exists() else name} is not the pinned original")
    return data


def verified(folder):
    """Return the record if the folder holds exactly a recorded pack, else None."""
    folder = Path(folder)
    if not (folder / RECORD).exists():
        return None
    record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
    if record.get("schema") != 2 or not set(record["archives"]) <= set(ARCHIVES):
        raise ValueError("unrecognized texture pack record")
    for name, info in record["archives"].items():
        if sha((folder / (name + SUFFIX)).read_bytes()) != pinned(name) or info["original_sha256"] != pinned(name):
            raise ValueError(f"{name} texture pack backup does not match the pinned original")
        if sha((folder / name).read_bytes()) != info["sha256"]:
            raise ValueError(f"{name} changed outside the recorded texture pack")
    for name in set(ARCHIVES) - set(record["archives"]):
        if sha((folder / name).read_bytes()) != pinned(name):
            raise ValueError(f"{name} changed outside the recorded texture pack")
    return record


def resolve(folder, key0, replacements):
    """Map each requested entry to its archive: {archive: {entry: path}}."""
    index = {}
    for name in ARCHIVES:
        backup = folder / (name + SUFFIX)
        _, _, _, entries = aoapack.read_archive(backup if backup.exists() else folder / name, key0)
        index[name] = {e["name"].lower() for e in entries}
    plan = {}
    for entry, path in replacements.items():
        archive, _, bare = entry.rpartition(":")
        homes = [archive.upper()] if archive else [a for a in ARCHIVES if bare.lower() in index[a]]
        if len(homes) != 1 or homes[0] not in index or bare.lower() not in index[homes[0]]:
            raise KeyError(f"{entry}: found in {homes or 'no archive'}; prefix ARCHIVE: to choose")
        plan.setdefault(homes[0], {})[bare] = path
    return plan


def install(folder, replacements):
    folder = Path(folder)
    if (folder / RECORD).exists():
        verified(folder)
    elif any((folder / (n + SUFFIX)).exists() and sha((folder / n).read_bytes()) != pinned(n) for n in ARCHIVES):
        raise ValueError("an archive differs from its backup with no pack record")
    key0 = aoapack.builtin_key(KEY_CLIENT)
    plan = resolve(folder, key0, replacements)
    outputs, record = {}, {"schema": 2, "visual_acceptance": "pending", "archives": {}}
    for name in ARCHIVES:
        base = original(folder, name)
        if name not in plan:
            outputs[name] = base
            continue
        files = {}
        for entry, path in plan[name].items():
            data = Path(path).read_bytes()
            check_tga(entry, data)
            files[entry] = data
        backup = folder / (name + SUFFIX)
        if not backup.exists():
            prepare_client.atomic_write(backup, base)
        outputs[name] = aoapack.rebuild(backup, key0, files)
        record["archives"][name] = {
            "original_sha256": pinned(name), "sha256": sha(outputs[name]), "bytes": len(outputs[name]),
            "entries": {e: {"sha256": sha(d), "size": list(struct.unpack_from("<HH", d, 12))}
                        for e, d in sorted(files.items())}}
    # Record first: an interrupted write leaves a mismatch that check reports.
    prepare_client.atomic_write(folder / RECORD, (json.dumps(record, indent=2) + "\n").encode())
    for name, data in outputs.items():
        if (folder / name).read_bytes() != data:
            prepare_client.atomic_write(folder / name, data)
    verified(folder)
    return record


def undo(folder):
    folder = Path(folder)
    restored = {}
    for name in ARCHIVES:
        data = original(folder, name)
        if (folder / name).read_bytes() != data:
            prepare_client.atomic_write(folder / name, data)
        restored[name] = sha(data)
    (folder / RECORD).unlink(missing_ok=True)
    return {"restored": restored}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game_dir", type=Path)
    parser.add_argument("replacements", nargs="*", help="[ARCHIVE:]<entry>=<tga file>")
    parser.add_argument("--from-dir", type=Path, action="append", default=[],
                        help="folder whose _entries.json maps entry -> file name; repeatable")
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    pairs = dict(item.split("=", 1) for item in args.replacements)
    for folder in args.from_dir:
        listing = json.loads((folder / "_entries.json").read_text(encoding="utf-8"))
        clash = {e.rpartition(":")[2].lower() for e in listing} & {e.rpartition(":")[2].lower() for e in pairs}
        if clash:
            parser.error(f"entries given twice: {sorted(clash)}")
        pairs.update({entry: folder / file for entry, file in listing.items()})
    if args.undo == bool(pairs):
        parser.error("give replacements, or --undo alone")
    print(json.dumps(undo(args.game_dir) if args.undo else install(args.game_dir, pairs), indent=2))
