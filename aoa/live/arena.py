"""Read-only 2.9.2 player-slot snapshot for local debugging: <PID>.

Offsets recovered from AllocNewPlayer, LoadPlayer and ReceivePositionUpdate
(aoa/live/addresses_292.py). The process must be the 2.9.2 client: its PE
timestamp is checked before anything is read (aoa/live/procmem.py).

    python -I tools/run.py aoa.live.arena <PID> [--objects]
"""
import json
import struct
import sys

from aoa import cli  # noqa: E402
from aoa.live import addresses_292 as at
from aoa.live.procmem import Process


def snapshot(pid, include_objects=False, include_render=False):
    process = Process(pid)
    read = process.read

    try:
        tick_start = struct.unpack("<I", read(at.GAME_CLOCK, 4))[0] if include_render else None
        world = struct.unpack("<I", read(at.WORLD, 4))[0]
        def render_fields(p):
            pointer = struct.unpack_from("<I", p, 0x19C)[0]
            result = {"control_flags": struct.unpack_from("<I", p, 0xF4)[0]}
            if pointer:
                # Render object matrix begins at +0x7C, translation at +0xAC;
                # copied by the original view code at 0x4499DB..0x4499FD.
                result["render_matrix"] = list(struct.unpack("<16f", read(pointer + 0x7C, 64)))
            return result
        players = []
        for slot in range(50):
            p = read(world + at.PLAYERS + slot * at.PLAYER_STRIDE, at.PLAYER_STRIDE)
            if p[0x243]:
                players.append({"slot": slot, "tag": hex(struct.unpack_from("<I", p, 0x178)[0]),
                                "position": list(struct.unpack_from("<3f", p, 0x30)),
                                "target_position": list(struct.unpack_from("<3f", p, 0x70)),
                                "velocity": list(struct.unpack_from("<3f", p, 0x54)),
                                "acceleration": list(struct.unpack_from("<3f", p, 0x60)),
                                "max_velocity": struct.unpack_from("<H", p, 0x10C)[0],
                                "max_acceleration": struct.unpack_from("<H", p, 0x10E)[0],
                                "name": p[0x244:0x258].split(b"\0")[0].decode("ascii", "replace"),
                                **(render_fields(p) if include_render else {})})
        result = {"pid": pid, "active_players": players}
        if include_render:
            result["app_active"] = read(at.APP_ACTIVE, 1)[0]
            result["frame_tick"] = struct.unpack("<I", read(at.GAME_CLOCK, 4))[0]
            result["joystick_axes"] = list(struct.unpack("<4i", read(at.JOYSTICK_AXES, 16)))
            graphics = struct.unpack("<I", read(at.GRAPHICS_POINTER, 4))[0]
            # SetTransform(D3DTRANSFORMSTATE_VIEW), original 0x43B48E.
            result["view_matrix"] = list(struct.unpack("<16f", read(graphics + 0x25E0, 64)))
            # Main camera input copied by 0x553810. The D3D view above can
            # instead describe a HUD/target subview at the instant of sampling.
            result["main_camera_matrix"] = list(struct.unpack("<16f", read(graphics + at.MAIN_CAMERA, 64)))
            result["camera_tick_delta"] = struct.unpack("<I", read(graphics + 0x24EC, 4))[0]
        if include_objects:
            objects = []
            data = read(world + 0x4C, 1000 * 0x360)
            for slot in range(1000):
                p = data[slot * 0x360:(slot + 1) * 0x360]
                if p[0x243]:
                    objects.append({"slot": slot,
                                    "graphics": hex(struct.unpack_from("<I", p, 0x19C)[0]),
                                    "visible": bool(p[0x2F7]),
                                    "collidable": bool(p[0x2FB]),
                                    "tag": hex(struct.unpack_from("<I", p, 0x178)[0]),
                                    "kind": struct.unpack_from("<I", p, 0x1F8)[0],
                                    "turret_activation": struct.unpack_from("<i", p, 0x1DC)[0],
                                    "ai": hex(struct.unpack_from("<I", p, 0x30C)[0]),
                                    "position": list(struct.unpack_from("<3f", p, 0x30)),
                                    "target_position": list(struct.unpack_from("<3f", p, 0x70)),
                                    "name": p[0x244:0x284].split(b"\0")[0].decode("ascii", "replace"),
                                    "velocity": list(struct.unpack_from("<3f", p, 0x54)),
                                    **(render_fields(p) if include_render else {})})
            result["active_objects"] = objects
            # Native terrain uses a separate linked list, not the 1000 dynamic
            # object slots above (0x4981D5..0x4981F2).
            controller = struct.unpack("<I", read(world + 0xDF03C, 4))[0]
            if controller:
                flags = read(controller, 0x1A)
                result["terrain_controller_flags"] = {hex(offset): flags[offset] for offset in (4, 5, 0x18, 0x19)}
            terrain, seen = [], set()
            node = struct.unpack("<I", read(controller, 4))[0] if controller else 0
            while node and node not in seen and len(terrain) < 4096:
                seen.add(node)
                p = read(node, 0x360)
                terrain.append({"address": hex(node),
                                "terrain_kind": struct.unpack_from("<I", p, 0x1F8)[0],
                                "collidable": bool(p[0x2FB]),
                                "position": list(struct.unpack_from("<3f", p, 0x30)),
                                "graphics": hex(struct.unpack_from("<I", p, 0x19C)[0]),
                                "name": p[0x244:0x284].split(b"\0")[0].decode("ascii", "replace")})
                node = struct.unpack_from("<I", p, 0x180)[0]
            result["terrain_objects"] = terrain
            result["terrain_list_complete"] = node == 0
            zone_handler = struct.unpack("<I", read(world + 0xDF06C, 4))[0]
            zone_node = struct.unpack("<I", read(zone_handler, 4))[0] if zone_handler else 0
            zone_seen = set()
            while zone_node and zone_node not in zone_seen and len(zone_seen) < 4096:
                zone_seen.add(zone_node)
                zone_node = struct.unpack("<I", read(zone_node + 8, 4))[0]
            result["safe_zone_count"] = len(zone_seen)
            result["safe_zone_list_complete"] = zone_node == 0
        if include_render:
            result["frame_tick_start"] = tick_start
            result["frame_tick_end"] = struct.unpack("<I", read(at.GAME_CLOCK, 4))[0]
        return result
    finally:
        process.close()


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("pid", type=int, help="process id of a running 2.9.2 client")
    ap.add_argument("--objects", action="store_true", help="also list objects, terrain and safe zones")
    a = ap.parse_args(argv)
    if sys.platform != "win32":
        sys.exit("inspect_arena: needs Windows (it reads the client's process memory)")
    print(json.dumps(snapshot(a.pid, a.objects), indent=2))


if __name__ == "__main__":
    sys.exit(cli.run(main))
