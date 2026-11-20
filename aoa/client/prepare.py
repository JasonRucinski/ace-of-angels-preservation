"""Prepare/check/undo/launch the supported 2.9.2 client using the user's files.

No installer, game binary, wrapper or asset is downloaded or redistributed.
All executable changes are built and verified in memory before replacement.

Every patch is a descriptor in the registry (aoa/client/patches/__init__.py);
this module is the one engine over it: inspect() reports and removes them,
configure() resolves the options and applies them, and prepare() and undo()
are the one transaction on the game folder, with one exact-undo backup
(AOACLIENT.EXE.setup-original) and one record (_client_setup.json).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from aoa.client.patches import CONFLICTS, OPTIONS, PATCH_LEVEL, REGISTRY, VARIANT_OF
from aoa.client.patches import base as patching
from aoa.client.patches import logger
from aoa.client.patches.station_host import OFFSET, ORIGINAL
from aoa.paths import ROOT

PATCH_VERSION = PATCH_LEVEL
ASSET_MANIFEST = ROOT / "config/client-2.9.2.json"
WRAPPERS = {
    "DDraw.dll": "612a24408a090a3c6f3886557fa18034ee742e94ad0a40ebdf854d2816176c2e",
    "D3DImm.dll": "93c534f2d17419ea78f15551f7e0aac78b3c503733a840914fa063708a5afe8e",
}
LOOPBACK = ("localhost", "127.0.0.1")
# Needs a loopback Station; prepare refuses it with any other.
LOOPBACK_ONLY = "explicit-protection-v1"
BASE = tuple(p.id for p in REGISTRY if p.policy == "base")
# A client with only these has never been prepared, so it has no options yet:
# the logger fixes, and the physics guard the old standalone tool added.
UNPREPARED = {*BASE, "zero-time-physics-v1"}
# What `check` requires: every patch applied whatever the options.
REQUIRED = {p.id for p in REGISTRY if p.policy in ("base", "always")}
# Older variants inspect() still recognizes; prepare upgrades them in place.
OUTDATED = {variant for p in REGISTRY for variant, _ in p.legacy}
# Exact-undo backups of the standalone patch tools removed in phase 2a.
OLD_BACKUPS = ".before-*"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def host_field(host):
    # Preserve the recovered fixed-width field; no extra executable cave.
    if not isinstance(host, str) or not 1 <= len(host) <= 11:
        raise ValueError("Station host must fit the legacy 11-character field")
    if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
           for label in host.split(".")):
        raise ValueError("Station host must contain valid ASCII hostname labels or IPv4 text")
    if all(part.isdigit() for part in host.split(".")):
        import ipaddress
        ipaddress.IPv4Address(host)
    return host.encode("ascii").ljust(12, b"\0")


def strip(data):
    """({patch ID: installed variant}, the image with every non-base patch removed).

    Raises ValueError on unknown bytes at any patch site. Two patches that
    share a site (a declared conflict) cannot both be installed; the one that
    is not reads as unknown until the other is removed, so it is retried.
    """
    installed, pending = {}, [p for p in reversed(REGISTRY) if p.policy != "base"]
    while pending:
        retry, error = [], None
        for patch in pending:
            try:
                variant = patching.state(patch, data)
            except ValueError as failure:
                if not patch.conflicts:
                    raise
                retry.append(patch)
                error = failure
                continue
            if variant:
                installed[patch.id] = variant
                data = patching.apply(patch, data, False)
        if len(retry) == len(pending):
            raise error
        pending = retry
    return installed, data


def _inspect(data):
    """(inspect()'s result, the image with every non-base patch and the Station removed)."""
    if sha(data) == logger.PRISTINE_292:
        return {"source": "original-2.9.2", "host": "aoahost.com", "patches": []}, data
    patching.check_mapping(data, REGISTRY)
    installed, data = strip(data)
    field = data[OFFSET:OFFSET + 12]
    try:
        host = field.split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("unrecognized Station hostname bytes") from error
    if field != host_field(host):
        raise ValueError("unrecognized Station hostname padding")
    normalized = data[:OFFSET] + ORIGINAL + data[OFFSET + 12:]
    if sha(normalized) != logger.STABLE_SHA256:
        raise ValueError("unsupported client or conflicting patches")
    patches = [*BASE, *(installed[p.id] for p in REGISTRY if p.id in installed)]
    return {"source": "supported-2.9.2", "host": host, "patches": patches}, normalized


def inspect(data):
    """Station and installed patch variants, in registry order; raises on anything unknown."""
    return _inspect(data)[0]


def resolve(state, options):
    """{patch ID: on} for every non-base patch, from the installed state and the options.

    An option set to True or False wins; one not named (or None) keeps its
    installed state, and on a client never prepared takes the patch default.
    Requesting both sides of a conflict is an error; an explicit request
    replaces the installed other side. A patch with no option of its own
    follows the patches it requires.
    """
    unknown = sorted(set(options) - set(OPTIONS))
    if unknown:
        raise ValueError(f"unknown option: {', '.join(unknown)}")
    fresh = set(state["patches"]) <= UNPREPARED
    installed = {VARIANT_OF[v].id for v in state["patches"]}
    requested = {p.id: options.get(p.option) for p in OPTIONS.values()}
    for a, b in CONFLICTS:
        if requested[a.id] and requested[b.id]:
            raise ValueError(f"{a.id} and {b.id} cannot both be on; select one")
    chosen = {}
    for p in REGISTRY:
        if p.policy == "always":
            chosen[p.id] = True
        elif p.option:
            wanted = requested[p.id]
            chosen[p.id] = wanted if wanted is not None else p.default if fresh else p.id in installed
    for a, b in CONFLICTS:
        if chosen[a.id] and chosen[b.id]:
            chosen[b.id if requested[a.id] else a.id] = False
    for p in REGISTRY:
        if p.policy == "option" and not p.option:
            chosen[p.id] = all(chosen[r] for r in p.requires)
        elif chosen.get(p.id) and not all(chosen[r] for r in p.requires):
            raise ValueError(f"{p.id} requires {', '.join(p.requires)}")
    return chosen


def configure(data, station=None, options=None, **named):
    """The prepared image, in memory.

    `options` (and keyword arguments) map option names to True, False or None
    (see resolve()). The Station is kept when not given, and is localhost on
    a client never prepared.
    """
    options = {**(options or {}), **named}
    state, stable = _inspect(data)
    fresh = set(state["patches"]) <= UNPREPARED
    host = station if station is not None else "localhost" if fresh else state["host"]
    field = host_field(host)
    chosen = resolve(state, options)
    if chosen[LOOPBACK_ONLY] and host not in LOOPBACK:
        raise ValueError("experimental protection requires a loopback Station")
    if not state["patches"]:
        stable = logger.stabilize(data)
        if sha(stable) != logger.STABLE_SHA256:
            raise ValueError("unsupported client: the stability patches did not give the known image")
    result = stable[:OFFSET] + field + stable[OFFSET + 12:]
    for p in REGISTRY:
        if chosen.get(p.id):
            result = patching.apply(p, result, True)
    inspect(result)
    return result


def atomic_write(path, data):
    """Same-directory replacement; interrupted writes cannot truncate the EXE."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def wrapper_state(folder):
    present = [name for name in WRAPPERS if (folder / name).exists()]
    if not present:
        return "native-directx7"
    if len(present) != len(WRAPPERS):
        raise ValueError("partial DirectX wrapper installation")
    for name, digest in WRAPPERS.items():
        if sha((folder / name).read_bytes()) != digest:
            raise ValueError(f"unrecognized/conflicting wrapper: {name}")
    return "dgVoodoo2-2.87.5"


def check_assets(folder):
    manifest = json.loads(ASSET_MANIFEST.read_text(encoding="utf-8"))
    for name, expected in manifest["required"].items():
        path = folder / name
        if not path.is_file():
            raise ValueError(f"missing game dependency: {name}")
        if path.stat().st_size != expected["bytes"] or sha(path.read_bytes()) != expected["sha256"]:
            from aoa.client import texture_pack
            record = texture_pack.verified(folder) if name in texture_pack.ARCHIVES else None
            if record is None or name not in record["archives"]:
                raise ValueError(f"modified or incompatible game dependency: {name}")
    for name, policy in manifest["mutable"].items():
        path = folder / name
        if not path.is_file() or not policy["initial_bytes"] <= path.stat().st_size <= policy["max_bytes"]:
            raise ValueError(f"missing or out-of-bounds mutable dependency: {name}")
    return len(manifest["required"]) + len(manifest["mutable"])


def paths(exe):
    exe = Path(exe)
    if exe.is_symlink() or "originals" in (p.lower() for p in exe.resolve().parts):
        raise ValueError("use a regular executable in a working game folder, outside originals/")
    return exe, exe.with_name(exe.name + ".setup-original"), exe.with_name("_client_setup.json")


def load_record(record_path, backup, current):
    if not record_path.exists():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("schema") != 1 or not backup.is_file() or sha(backup.read_bytes()) != record["backup_sha256"]:
        raise ValueError("setup record or exact-undo backup is invalid")
    allowed = [record["output_sha256"]]
    if record["status"] == "pending":
        allowed.append(record["input_sha256"])
    if sha(current) not in allowed:
        raise ValueError("executable changed outside the recorded setup; refusing to overwrite")
    return record


def _transaction(exe, result_of=None):
    """Write the executable and its record: pending, then ready, or restored
    when result_of is None (undo)."""
    undo = result_of is None
    exe, backup, record_path = paths(exe)
    current = exe.read_bytes()
    inspect(current)
    wrapper = "not-checked-on-undo" if undo else wrapper_state(exe.parent)
    old = load_record(record_path, backup, current)
    if undo:
        if old is None:
            raise ValueError("no recorded setup to undo")
        result = backup.read_bytes()
        inspect(result)
    else:
        result = result_of(current)
        if old is None:
            # Exclusive creation: never replace an unrelated backup. A prior
            # interruption before recording is recoverable only if bytes match.
            if backup.exists():
                if backup.read_bytes() != current:
                    raise ValueError("unrecorded backup differs from current executable")
            else:
                with backup.open("xb") as stream:
                    stream.write(current)
                    stream.flush()
                    os.fsync(stream.fileno())
    record = {"schema": 1, "patch_version": PATCH_VERSION, "status": "pending",
              "input_sha256": sha(current), "output_sha256": sha(result),
              "backup_sha256": sha(backup.read_bytes()), "wrapper": wrapper, **inspect(result)}
    atomic_write(record_path, (json.dumps(record, indent=2) + "\n").encode())
    if current != result:
        atomic_write(exe, result)
    if exe.read_bytes() != result:
        raise RuntimeError("executable write verification failed")
    record["status"] = "restored" if undo else "ready"
    atomic_write(record_path, (json.dumps(record, indent=2) + "\n").encode())
    return record


def prepare(exe, options=None, station=None):
    """Prepare the executable in place. An option not named keeps its installed
    state, and so does the Station when not given (see configure())."""
    return _transaction(exe, lambda current: configure(current, station, options))


def undo(exe):
    """Restore the exact executable from before the first prepare."""
    return _transaction(exe)


def check(exe, require_assets=True):
    exe, backup, record_path = paths(exe)
    data = exe.read_bytes()
    state = inspect(data)
    record = load_record(record_path, backup, data)
    old = sorted(OUTDATED & set(state["patches"]))
    if old:
        raise ValueError(f"outdated client patches ({', '.join(old)}); re-run prepare")
    if record is None or record["status"] != "ready" or not REQUIRED <= set(state["patches"]):
        raise ValueError("run prepare before launching; setup must be recorded and complete")
    wrapper = wrapper_state(exe.parent)
    if require_assets:
        check_assets(exe.parent)
    result = {"sha256": sha(data), "status": "ready", "wrapper": wrapper,
              "mutable_assets_not_hash_verified": ["SOUNDS.AOA"] if require_assets else [], **state}
    # Left by the standalone patch tools that phase 2a removed; prepare and
    # undo never use them, and the player may delete them.
    stale = sorted(p.name for p in exe.parent.glob(exe.name + OLD_BACKUPS))
    if stale:
        result["unused_old_backups"] = stale
    return result


# Command-line flags of earlier releases, kept as aliases of the generated ones.
FLAG_ALIASES = {"smooth_frame_clock": "--frame-clock", "bounded_visibility": "--visibility-math",
                "chase_camera": "--third-person", "powerup_pickups": "--powerup-pickup"}


def flag(option):
    return "--" + option.replace("_", "-")


def parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    actions = ap.add_subparsers(dest="action", required=True, metavar="ACTION")
    prep = actions.add_parser("prepare", help="patch the executable; options not named keep their installed state",
                              epilog="An option that is not named keeps its installed state. The defaults apply "
                                     "only to a client never prepared before.")
    prep.add_argument("exe", type=Path)
    prep.add_argument("--station", help="Station hostname/IP, max 11 ASCII characters "
                      "(default: keep the installed one; localhost on a fresh client)")
    for option, patch in OPTIONS.items():
        names = [flag(option), *([FLAG_ALIASES[option]] if option in FLAG_ALIASES else [])]
        ids = [patch.id, *(p.id for p in REGISTRY if patch.id in p.requires and not p.option)]
        prep.add_argument(*names, dest=option, action=argparse.BooleanOptionalAction,
                          help=f"{patch.label or patch.id} ({', '.join(ids)}; "
                               f"default {'on' if patch.default else 'off'})")
    for name, text in (("check", "verify the prepared executable, its record, wrapper and assets"),
                       ("undo", "restore the executable from before the first prepare"),
                       ("launch", "check, then start the client")):
        actions.add_parser(name, help=text).add_argument("exe", type=Path)
    return ap


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    try:
        if args.action == "prepare":
            result = prepare(args.exe, {option: getattr(args, option) for option in OPTIONS}, args.station)
        elif args.action == "undo":
            result = undo(args.exe)
        else:
            result = check(args.exe)
            if args.action == "launch":
                subprocess.Popen([str(args.exe.resolve())], cwd=args.exe.resolve().parent)
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as error:
        ap.exit(1, f"Client setup failed: {error}\n")


if __name__ == "__main__":
    main()
