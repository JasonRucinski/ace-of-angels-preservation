"""Prepare/check/undo/launch the supported 2.9.2 client using the user's files.

No installer, game binary, wrapper or asset is downloaded or redistributed.
All executable changes are built and verified in memory before replacement.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from aoa.client.patches import archive_terminator
from aoa.client.patches import cursor_warp
from aoa.client.patches import explicit_protection
from aoa.client.patches import frame_clock
from aoa.client.patches import visibility_fix
from aoa.client import base
from aoa.client.patches import base as patching
from aoa.client.patches import physics_timestep
from aoa.client.patches import menu_aspect
from aoa.client.patches import online_terrain
from aoa.client.patches import asteroid_render
from aoa.client.patches import solid_world_render
from aoa.client.patches import station_detail
from aoa.client.patches import texture32
from aoa.client.patches import third_person
from aoa.client.patches import own_ship_model
from aoa.client.patches import own_ship_menu
from aoa.client.patches import powerup_pickup
from aoa.client.patches import world_detail
from aoa.client.patches import object_persistence
from aoa.client.patches.station_host import OFFSET, ORIGINAL, STABLE_SHA256
from aoa.paths import ROOT

PATCH_VERSION = 22
# Wakeup-timer callback 0x446E70: `jne` at 0x446EAF skips the frame while the
# window is inactive if the graphics layer reports exclusive mode (+0x24C5).
# The client always requests exclusive mode, so an inactive flying client
# stopped reading UDP. NOPs let the 66 ms timer run the frame. Verified only
# with the dgVoodoo windowed wrapper (findings 9.24).
BACKGROUND_OFFSET, BACKGROUND_JNE, BACKGROUND_NOP = 0x46EAF, b"\x75\x34", b"\x90\x90"
ASSET_MANIFEST = ROOT / "config/client-2.9.2.json"
WRAPPERS = {
    "DDraw.dll": "612a24408a090a3c6f3886557fa18034ee742e94ad0a40ebdf854d2816176c2e",
    "D3DImm.dll": "93c534f2d17419ea78f15551f7e0aac78b3c503733a840914fa063708a5afe8e",
}
LOOPBACK = ("localhost", "127.0.0.1")
# A client with only these has never been prepared, so it has no options yet.
UNPREPARED = {"logger-size-v1", "logger-lock-v1", "zero-time-physics-v1"}
# Older variants inspect() still recognizes; prepare upgrades them in place.
OUTDATED = {*third_person.NAMES[1:], own_ship_menu.LEGACY_NAME, online_terrain.V2_NAME,
            online_terrain.LEGACY_NAME}


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


def background_site(data, enabled):
    site = data[BACKGROUND_OFFSET:BACKGROUND_OFFSET + 2]
    if site not in (BACKGROUND_JNE, BACKGROUND_NOP):
        raise ValueError("unexpected background-network code")
    return data[:BACKGROUND_OFFSET] + (BACKGROUND_NOP if enabled else BACKGROUND_JNE) + data[BACKGROUND_OFFSET + 2:]


def inspect(data):
    if sha(data) == base.PRISTINE_292:
        return {"source": "original-2.9.2", "host": "aoahost.com", "patches": []}
    distant = object_persistence.state(data)
    data = object_persistence.configure(data, False)
    pickup = powerup_pickup.state(data)
    data = powerup_pickup.configure(data, False)
    chase = third_person.installed_name(data)
    data = third_person.configure(data, False)
    model = own_ship_model.state(data)
    data = own_ship_model.configure(data, False)
    menu_model = own_ship_menu.installed_name(data)
    data = own_ship_menu.configure(data, False)
    clock = frame_clock.state(data)
    data = frame_clock.configure(data, False)
    visibility = visibility_fix.state(data)
    data = visibility_fix.configure(data, False)
    tex32 = texture32.state(data)
    data = texture32.configure(data, False)
    world_lod = world_detail.state(data)
    data = world_detail.configure(data, False)
    detail = station_detail.state(data)
    data = station_detail.configure(data, False)
    solids = solid_world_render.state(data)
    data = solid_world_render.configure(data, False)
    asteroids = asteroid_render.state(data)
    data = asteroid_render.configure(data, False)
    terrain = online_terrain.state(data)
    terrain_name = online_terrain.installed_name(data)
    data = online_terrain.configure(data, False)
    menu = menu_aspect.state(data)
    data = menu_aspect.configure(data, False)
    cursor = patching.state(cursor_warp.PATCH, data)
    data = patching.apply(cursor_warp.PATCH, data, False)
    background = data[BACKGROUND_OFFSET:BACKGROUND_OFFSET + 2] == BACKGROUND_NOP
    terminated = archive_terminator.state(data)
    protection = explicit_protection.state(data)
    data = explicit_protection.configure(data, False)
    data = archive_terminator.configure(background_site(data, False), False)
    field = data[OFFSET:OFFSET + 12]
    try:
        host = field.split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("unrecognized Station hostname bytes") from error
    if field != host_field(host):
        raise ValueError("unrecognized Station hostname padding")
    normalized = data[:OFFSET] + ORIGINAL + data[OFFSET + 12:]
    stable = physics_timestep.configure(normalized, undo=True)
    if sha(stable) != STABLE_SHA256:
        raise ValueError("unsupported client or conflicting patches")
    guarded = normalized != stable
    return {"source": "supported-2.9.2", "host": host,
            "patches": ["logger-size-v1", "logger-lock-v1"] + (["zero-time-physics-v1"] if guarded else [])
            + (["background-network-v1"] if background else [])
            + (["archive-terminator-v1"] if terminated else [])
            + ([menu_aspect.NAME] if menu else [])
            + ([cursor_warp.NAME] if cursor else [])
            + ([terrain_name] if terrain else [])
            + ([asteroid_render.NAME] if asteroids else [])
            + ([solid_world_render.NAME] if solids else [])
            + ([station_detail.NAME] if detail else [])
            + ([world_detail.NAME] if world_lod else [])
            + ([object_persistence.NAME] if distant else [])
            + ([texture32.NAME] if tex32 else [])
            + ([frame_clock.NAME] if clock else [])
            + ([visibility_fix.NAME] if visibility else [])
            + ([chase] if chase else [])
            + ([own_ship_model.NAME] if model else [])
            + ([menu_model] if menu_model else [])
            + ([powerup_pickup.NAME] if pickup else [])
            + ([explicit_protection.NAME] if protection else [])}


def choose(state, requested, names, default):
    """An explicit True/False wins; None keeps the installed state.

    names is the patch ID, or a tuple of the IDs of every recognized variant.
    The default applies only to an unprepared client (pristine, or carrying
    only the legacy stability fixes), which has no options installed yet.
    """
    if requested is not None:
        return requested
    if set(state["patches"]) <= UNPREPARED:
        return default
    return bool(({names} if isinstance(names, str) else set(names)) & set(state["patches"]))


def exclusive(state, first, first_name, second, second_name):
    """Resolve a pair that shares one code site: requesting both is an error,
    and an explicit request replaces the installed other one."""
    if first and second:
        raise ValueError(f"{first_name} and {second_name} cannot both be on; select one")
    a, b = choose(state, first, first_name, False), choose(state, second, second_name, False)
    if a and b:
        a, b = (a, False) if first else (False, b)
    return a, b


def configure(data, host=None, experimental_protection=None, experimental_asteroids=None, experimental_solids=None, experimental_station_detail=None, experimental_world_detail=None, experimental_texture32=None, smooth_frame_clock=None, bounded_visibility=None, chase_camera=None, powerup_pickups=None, distant_objects=None, menu_framing=None):
    """Every option left as None keeps its installed state (see choose())."""
    state = inspect(data)
    fresh = set(state["patches"]) <= UNPREPARED
    host = host if host is not None else "localhost" if fresh else state["host"]
    field = host_field(host)
    distant = choose(state, distant_objects, object_persistence.NAME, False)
    chase = choose(state, chase_camera, third_person.NAMES, True)
    pickups = choose(state, powerup_pickups, powerup_pickup.NAME, True)
    clock = choose(state, smooth_frame_clock, frame_clock.NAME, True)
    visibility = choose(state, bounded_visibility, visibility_fix.NAME, True)
    framing = choose(state, menu_framing, menu_aspect.NAME, True)
    tex32 = choose(state, experimental_texture32, texture32.NAME, False)
    station_lod, world_lod = exclusive(state, experimental_station_detail, station_detail.NAME,
                                       experimental_world_detail, world_detail.NAME)
    asteroids, solids = exclusive(state, experimental_asteroids, asteroid_render.NAME,
                                  experimental_solids, solid_world_render.NAME)
    data = object_persistence.configure(data, False)
    data = own_ship_menu.configure(own_ship_model.configure(third_person.configure(data, False), False), False)
    data = powerup_pickup.configure(data, False)
    data = visibility_fix.configure(frame_clock.configure(data, False), False)
    data = texture32.configure(data, False)
    data = world_detail.configure(data, False)
    data = station_detail.configure(data, False)
    data = solid_world_render.configure(data, False)
    data = asteroid_render.configure(data, False)
    data = online_terrain.configure(data, False)
    data = menu_aspect.configure(data, False)
    data = patching.apply(cursor_warp.PATCH, data, False)
    protection = choose(state, experimental_protection, explicit_protection.NAME, False)
    if protection and host not in LOOPBACK:
        raise ValueError("experimental protection requires a loopback Station")
    data = explicit_protection.configure(data, False)
    stable = (base.configure(data)[0] if not state["patches"]
              else archive_terminator.configure(background_site(data, False), False))
    normalized = stable[:OFFSET] + ORIGINAL + stable[OFFSET + 12:]
    guarded = physics_timestep.configure(normalized)
    result = archive_terminator.configure(background_site(guarded[:OFFSET] + field + guarded[OFFSET + 12:], True))
    result = explicit_protection.configure(result, protection)
    result = menu_aspect.configure(result, framing)
    result = patching.apply(cursor_warp.PATCH, result, True)
    result = online_terrain.configure(result)
    result = asteroid_render.configure(result, asteroids)
    result = solid_world_render.configure(result, solids)
    result = station_detail.configure(result, station_lod)
    result = world_detail.configure(result, world_lod)
    result = texture32.configure(result, tex32)
    result = frame_clock.configure(result, clock)
    result = visibility_fix.configure(result, visibility)
    result = third_person.configure(result, chase)
    result = own_ship_model.configure(result, chase)
    result = own_ship_menu.configure(result, chase)
    result = powerup_pickup.configure(result, pickups)
    result = object_persistence.configure(result, distant)
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


def prepare(exe, host=None, undo=False, experimental_protection=None, experimental_asteroids=None, experimental_solids=None, experimental_station_detail=None, experimental_world_detail=None, experimental_texture32=None, smooth_frame_clock=None, bounded_visibility=None, chase_camera=None, powerup_pickups=None, distant_objects=None, menu_framing=None):
    """Options left as None keep their installed state, as in configure()."""
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
        result = configure(current, host=host, experimental_protection=experimental_protection,
                           experimental_asteroids=experimental_asteroids, experimental_solids=experimental_solids,
                           experimental_station_detail=experimental_station_detail,
                           experimental_world_detail=experimental_world_detail,
                           experimental_texture32=experimental_texture32, smooth_frame_clock=smooth_frame_clock,
                           bounded_visibility=bounded_visibility, chase_camera=chase_camera,
                           powerup_pickups=powerup_pickups, distant_objects=distant_objects,
                           menu_framing=menu_framing)
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


def check(exe, require_assets=True):
    exe, backup, record_path = paths(exe)
    data = exe.read_bytes()
    state = inspect(data)
    record = load_record(record_path, backup, data)
    old = sorted(OUTDATED & set(state["patches"]))
    if old:
        raise ValueError(f"outdated client patches ({', '.join(old)}); re-run prepare")
    if (record is None or record["status"] != "ready"
            or not {"zero-time-physics-v1", "background-network-v1",
                    "archive-terminator-v1", cursor_warp.NAME, online_terrain.NAME} <= set(state["patches"])):
        raise ValueError("run prepare before launching; setup must be recorded and complete")
    wrapper = wrapper_state(exe.parent)
    if require_assets:
        check_assets(exe.parent)
    return {"sha256": sha(data), "status": "ready", "wrapper": wrapper,
            "mutable_assets_not_hash_verified": ["SOUNDS.AOA"] if require_assets else [], **state}


PREPARE_ONLY = ("station", "experimental_protection", "frame_clock", "visibility_math", "third_person",
                "powerup_pickup", "distant_objects", "menu_framing")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog="An option that is not named keeps its "
                                     "installed state. The defaults apply only to a client never prepared before.")
    parser.add_argument("action", choices=("prepare", "check", "undo", "launch"))
    parser.add_argument("exe", type=Path)
    parser.add_argument("--station", help="Station hostname/IP, max 11 ASCII characters "
                        "(default: keep the installed one; localhost on a fresh client); prepare only")
    parser.add_argument("--experimental-protection", action=argparse.BooleanOptionalAction,
                        help="opt-in localhost explicit protection setter (default off); prepare only")
    parser.add_argument("--frame-clock", action=argparse.BooleanOptionalAction,
                        help="millisecond QPC game clock and timer-frame gate (frame-clock-v1; default on); prepare only")
    parser.add_argument("--visibility-math", action=argparse.BooleanOptionalAction,
                        help="bounded acos/asin inputs in object visibility (visibility-math-v1; default on); prepare only")
    parser.add_argument("--third-person", action=argparse.BooleanOptionalAction,
                        help="F2 toggles a chase camera behind your ship, F4 one that orbits it (third-person-camera-v3, own-ship-model-v1, own-ship-menu-model-v1; default on); prepare only")
    parser.add_argument("--powerup-pickup", action=argparse.BooleanOptionalAction,
                        help="server-placed power-ups can be picked up and reappear (powerup-pickup-v1; default on); prepare only")
    parser.add_argument("--distant-objects", action=argparse.BooleanOptionalAction,
                        help="extend world-object visibility to 4,500,000 units and 0.5 projected size (default off); prepare only")
    parser.add_argument("--menu-framing", action=argparse.BooleanOptionalAction,
                        help="widescreen ship-selection framing (default on); prepare only")
    args = parser.parse_args(argv)
    if args.action != "prepare":
        named = [f"--{key.replace('_', '-')}" for key in PREPARE_ONLY if getattr(args, key) is not None]
        if named:
            parser.error(f"{', '.join(named)} applies only to prepare")
    try:
        if args.action in ("prepare", "undo"):
            result = prepare(args.exe, host=args.station, undo=args.action == "undo",
                             experimental_protection=args.experimental_protection,
                             smooth_frame_clock=args.frame_clock,
                             bounded_visibility=args.visibility_math,
                             chase_camera=args.third_person,
                             powerup_pickups=args.powerup_pickup,
                             distant_objects=args.distant_objects, menu_framing=args.menu_framing)
        else:
            result = check(args.exe)
            if args.action == "launch":
                subprocess.Popen([str(args.exe.resolve())], cwd=args.exe.resolve().parent)
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Client setup failed: {error}\n")


if __name__ == "__main__":
    main()
