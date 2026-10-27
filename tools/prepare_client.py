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
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive_terminator
import cursor_warp
import explicit_protection
import frame_clock
import visibility_fix
import patch_client
import physics_timestep
import menu_aspect
import online_terrain
import asteroid_render
import solid_world_render
import station_detail
import texture32
import third_person
import own_ship_model
import own_ship_menu
import powerup_pickup
import world_detail
import object_persistence
from local_station import OFFSET, ORIGINAL, STABLE_SHA256

PATCH_VERSION = 22
# Wakeup-timer callback 0x446E70: `jne` at 0x446EAF skips the frame while the
# window is inactive if the graphics layer reports exclusive mode (+0x24C5).
# The client always requests exclusive mode, so an inactive flying client
# stopped reading UDP. NOPs let the 66 ms timer run the frame. Verified only
# with the dgVoodoo windowed wrapper (findings 9.24).
BACKGROUND_OFFSET, BACKGROUND_JNE, BACKGROUND_NOP = 0x46EAF, b"\x75\x34", b"\x90\x90"
ASSET_MANIFEST = Path(__file__).resolve().parents[1] / "config/client-2.9.2.json"
WRAPPERS = {
    "DDraw.dll": "612a24408a090a3c6f3886557fa18034ee742e94ad0a40ebdf854d2816176c2e",
    "D3DImm.dll": "93c534f2d17419ea78f15551f7e0aac78b3c503733a840914fa063708a5afe8e",
}


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
    if sha(data) == patch_client.PRISTINE_292:
        return {"source": "original-2.9.2", "host": "aoahost.com", "patches": []}
    distant = object_persistence.state(data)
    data = object_persistence.configure(data, False)
    pickup = powerup_pickup.state(data)
    data = powerup_pickup.configure(data, False)
    chase = third_person.state(data)
    data = third_person.configure(data, False)
    model = own_ship_model.state(data)
    data = own_ship_model.configure(data, False)
    menu_model = own_ship_menu.state(data)
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
    cursor = cursor_warp.state(data)
    data = cursor_warp.configure(data, False)
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
            + ([third_person.NAME] if chase else [])
            + ([own_ship_model.NAME] if model else [])
            + ([own_ship_menu.NAME] if menu_model else [])
            + ([powerup_pickup.NAME] if pickup else [])
            + ([explicit_protection.NAME] if protection else [])}


def configure(data, host="localhost", experimental_protection=None, experimental_asteroids=None, experimental_solids=None, experimental_station_detail=None, experimental_world_detail=None, experimental_texture32=None, smooth_frame_clock=True, bounded_visibility=True, chase_camera=True, powerup_pickups=True, distant_objects=None):
    field = host_field(host)
    state = inspect(data)
    distant = object_persistence.NAME in state["patches"] if distant_objects is None else distant_objects
    data = object_persistence.configure(data, False)
    data = own_ship_menu.configure(own_ship_model.configure(third_person.configure(data, False), False), False)
    data = powerup_pickup.configure(data, False)
    data = visibility_fix.configure(frame_clock.configure(data, False), False)
    tex32 = (texture32.NAME in state["patches"] if experimental_texture32 is None else experimental_texture32)
    data = texture32.configure(data, False)
    world_lod = (world_detail.NAME in state["patches"] if experimental_world_detail is None else experimental_world_detail)
    if world_lod and experimental_station_detail:
        raise ValueError("select world detail or station-only detail, not both")
    data = world_detail.configure(data, False)
    data = station_detail.configure(data, False)
    solids = (solid_world_render.NAME in state["patches"] if experimental_solids is None else experimental_solids)
    if solids and experimental_asteroids:
        raise ValueError("select either solid-world or asteroid-only rendering, not both")
    data = solid_world_render.configure(data, False)
    data = asteroid_render.configure(data, False)
    data = online_terrain.configure(data, False)
    data = menu_aspect.configure(data, False)
    data = cursor_warp.configure(data, False)
    protection = (explicit_protection.NAME in state["patches"] if experimental_protection is None
                  else experimental_protection)
    if protection and host not in ("localhost", "127.0.0.1"):
        raise ValueError("experimental protection requires a loopback Station")
    data = explicit_protection.configure(data, False)
    stable = (patch_client.configure(data)[0] if not state["patches"]
              else archive_terminator.configure(background_site(data, False), False))
    normalized = stable[:OFFSET] + ORIGINAL + stable[OFFSET + 12:]
    guarded = physics_timestep.configure(normalized)
    result = archive_terminator.configure(background_site(guarded[:OFFSET] + field + guarded[OFFSET + 12:], True))
    result = explicit_protection.configure(result, protection)
    result = menu_aspect.configure(result)
    result = cursor_warp.configure(result)
    result = online_terrain.configure(result)
    result = asteroid_render.configure(result, not solids and (asteroid_render.NAME in state["patches"]
                                       if experimental_asteroids is None else experimental_asteroids))
    result = solid_world_render.configure(result, solids)
    result = station_detail.configure(result, not world_lod and (station_detail.NAME in state["patches"]
                                      if experimental_station_detail is None else experimental_station_detail))
    result = world_detail.configure(result, world_lod)
    result = texture32.configure(result, tex32)
    result = frame_clock.configure(result, smooth_frame_clock)
    result = visibility_fix.configure(result, bounded_visibility)
    result = third_person.configure(result, chase_camera)
    result = own_ship_model.configure(result, chase_camera)
    result = own_ship_menu.configure(result, chase_camera)
    result = powerup_pickup.configure(result, powerup_pickups)
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
            import texture_pack
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


def prepare(exe, host="localhost", undo=False, experimental_protection=None, experimental_asteroids=None, experimental_solids=None, experimental_station_detail=None, experimental_world_detail=None, experimental_texture32=None, smooth_frame_clock=True, bounded_visibility=True, chase_camera=True, powerup_pickups=True, distant_objects=None):
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
        result = configure(current, host, experimental_protection, experimental_asteroids, experimental_solids, experimental_station_detail, experimental_world_detail, experimental_texture32, smooth_frame_clock, bounded_visibility, chase_camera, powerup_pickups, distant_objects)
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
    if (record is None or record["status"] != "ready"
            or not {"zero-time-physics-v1", "background-network-v1",
                    "archive-terminator-v1", menu_aspect.NAME, cursor_warp.NAME, online_terrain.NAME} <= set(state["patches"])):
        raise ValueError("run prepare before launching; setup must be recorded and complete")
    wrapper = wrapper_state(exe.parent)
    if require_assets:
        check_assets(exe.parent)
    return {"sha256": sha(data), "status": "ready", "wrapper": wrapper,
            "mutable_assets_not_hash_verified": ["SOUNDS.AOA"] if require_assets else [], **state}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "undo", "launch"))
    parser.add_argument("exe", type=Path)
    parser.add_argument("--station", default="localhost", help="Station hostname/IP, max 11 ASCII characters")
    parser.add_argument("--experimental-protection", action=argparse.BooleanOptionalAction, default=None,
                        help="opt-in localhost explicit protection setter; prepare only")
    parser.add_argument("--frame-clock", action=argparse.BooleanOptionalAction, default=True,
                        help="millisecond QPC game clock and timer-frame gate (frame-clock-v1); prepare only")
    parser.add_argument("--visibility-math", action=argparse.BooleanOptionalAction, default=True,
                        help="bounded acos/asin inputs in object visibility (visibility-math-v1); prepare only")
    parser.add_argument("--third-person", action=argparse.BooleanOptionalAction, default=True,
                        help="F2 toggles a chase camera behind your ship, F4 one that orbits it (third-person-camera-v3, own-ship-model-v1, own-ship-menu-model-v1); prepare only")
    parser.add_argument("--powerup-pickup", action=argparse.BooleanOptionalAction, default=True,
                        help="server-placed power-ups can be picked up and reappear (powerup-pickup-v1); prepare only")
    parser.add_argument("--distant-objects", action=argparse.BooleanOptionalAction, default=None,
                        help="extend world-object visibility to 4,500,000 units and 0.5 projected size; preserve installed choice by default; prepare only")
    args = parser.parse_args()
    if args.experimental_protection is not None and args.action != "prepare":
        parser.error("--experimental-protection applies only to prepare")
    if args.distant_objects is not None and args.action != "prepare":
        parser.error("--distant-objects applies only to prepare")
    try:
        if args.action in ("prepare", "undo"):
            result = prepare(args.exe, args.station, undo=args.action == "undo",
                             experimental_protection=args.experimental_protection,
                             smooth_frame_clock=args.frame_clock,
                             bounded_visibility=args.visibility_math,
                             chase_camera=args.third_person,
                             powerup_pickups=args.powerup_pickup,
                             distant_objects=args.distant_objects)
        else:
            result = check(args.exe)
            if args.action == "launch":
                subprocess.Popen([str(args.exe.resolve())], cwd=args.exe.resolve().parent)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.exit(1, f"Client setup failed: {error}\n")


if __name__ == "__main__":
    main()
