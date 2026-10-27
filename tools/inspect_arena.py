"""Read-only 2.9.2 player-slot snapshot for local debugging: <PID>.

Offsets recovered from AllocNewPlayer, LoadPlayer and ReceivePositionUpdate.
Only use with the 2.9.2 executable (image base 0x400000).
"""
import ctypes
import json
import struct
import sys
from ctypes import wintypes


def snapshot(pid, include_objects=False, include_render=False):
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k.OpenProcess(0x10, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    def read(addr, size):
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        if not k.ReadProcessMemory(handle, addr, buf, size, ctypes.byref(got)) or got.value != size:
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw

    try:
        tick_start = struct.unpack("<I", read(0x5E8E5C, 4))[0] if include_render else None
        world = struct.unpack("<I", read(0x5E7728, 4))[0]
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
            p = read(world + 0xD32AC + slot * 0x3B0, 0x3B0)
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
            result["app_active"] = read(0x5E6E28, 1)[0]
            result["frame_tick"] = struct.unpack("<I", read(0x5E8E5C, 4))[0]
            result["joystick_axes"] = list(struct.unpack("<4i", read(0x60CC14, 16)))
            graphics = struct.unpack("<I", read(0x60C828, 4))[0]
            # SetTransform(D3DTRANSFORMSTATE_VIEW), original 0x43B48E.
            result["view_matrix"] = list(struct.unpack("<16f", read(graphics + 0x25E0, 64)))
            # Main camera input copied by 0x553810. The D3D view above can
            # instead describe a HUD/target subview at the instant of sampling.
            result["main_camera_matrix"] = list(struct.unpack("<16f", read(graphics + 0x2510, 64)))
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
            result["frame_tick_end"] = struct.unpack("<I", read(0x5E8E5C, 4))[0]
        return result
    finally:
        k.CloseHandle(handle)


if __name__ == "__main__":
    print(json.dumps(snapshot(int(sys.argv[1]), "--objects" in sys.argv), indent=2))
