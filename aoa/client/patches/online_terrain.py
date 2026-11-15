"""Online terrain hook: the server picks a map with the flight-entry marker.

The original 0x2C handler ignores its four-byte body. After SetupFlightMode,
the hook reuses the offline CreateTerrainFromGfxInfo call sequence
(0x4564DB..0x4564FB) for an original layout, or calls the native terrain-file
reader ReadInTerrain (0x4967E0) for a converted .TRN map.

Markers: `AR1A` (version 1, kept so v1-prepared clients still get Arena1a)
selects index 0; `MAP` + one index byte selects any entry of MAPS (the map
registry, aoa/maps/registry.py, which this cave embeds as its table). Unknown
markers, indexes and missing state leave the client unchanged. No collision,
service-zone, turret or warp acceptance is implied.

Version 3 also registers safe-zone visuals. SetupFlightMode (0x44B5C0, called
just before SITE) hands each box on the zone handler's safe list
(world+0xDF06C, node: box, next at +8) to 0x43E030 on the flight view
([0x5E6E58]+0x138), which builds the blue CDxWaveCube drawn by 0x43E190. The
hook creates the zones after that walk, so without a second walk the list was
empty when it ran and no cube was ever made. 0x43E030 skips a box it already
holds, so repeating the walk is harmless.
"""
import struct

from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches.base import Patch, Region
from aoa.maps.registry import MAP_PREFIX, MAPS, MARKER

NAME = "online-terrain-v3"
V2_NAME = "online-terrain-v2"
LEGACY_NAME = "online-arena1a-v1"
SITE = 0x4306AF
CAVE = layout.cave(NAME).start
REGION = layout.cave(NAME).size
TABLE = CAVE + 0xC0  # v2 kept it at +0xA0
V2_TABLE = CAVE + 0xA0
SLOT = 16  # name (NUL-padded, at most 14 characters) + kind byte at +15
DISPLACED = bytes.fromhex("a128775e00")  # mov eax,[world]
LOOKUP, LOAD, READ_TRN = 0x4CDD30, 0x495DF0, 0x4967E0
ADD_SAFE_ZONE_VISUAL = 0x43E030  # thiscall(box), ret 4
FLIGHT_MODE = 0x5E6E58  # ecx of SetupFlightMode


def table():
    out = bytearray()
    for _, kind, target, _ in MAPS:
        raw = target.encode("ascii")
        assert len(raw) < SLOT - 1
        out += raw.ljust(SLOT - 1, b"\0") + bytes([kind])
    return bytes(out)


def cave_code():
    return _cave(TABLE, True)


def v2_code():
    """Version 2 bytes (no safe-zone walk), recognized so prepare can upgrade them."""
    return _cave(V2_TABLE, False)


def _cave(table_at, safe_zones):
    a = Asm(CAVE)
    a.emit(0x9C, 0x60)  # preserve flags and all registers
    a.emit(bytes.fromhex("8b8664030000"))  # eax = marker at receive buffer esi+364
    a.emit(0x31, 0xC9)  # index 0
    a.emit(0x3D, MARKER)
    a.rel8(0x74, "have")
    a.emit(0x89, 0xC1, bytes.fromhex("c1e918"))  # ecx = marker >> 24
    a.emit(0x25, struct.pack("<I", 0xFFFFFF))
    a.emit(0x3D, MAP_PREFIX + b"\0")
    a.rel8(0x75, "done")
    a.emit(0x83, 0xF9, len(MAPS))
    a.rel8(0x73, "done")
    a.label("have")
    a.emit(DISPLACED, bytes.fromhex("85c0"))
    a.rel8(0x74, "done")
    a.emit(bytes.fromhex("8b983cf00d00"))  # ebx = world terrain controller
    a.emit(bytes.fromhex("85db"))
    a.rel8(0x74, "done")
    a.emit(bytes.fromhex("833b00"))  # existing terrain list: avoid duplicate creation
    a.rel8(0x75, "done")
    a.emit(bytes.fromhex("c1e104"))  # ecx *= SLOT
    a.emit(bytes.fromhex("8db9"), struct.pack("<I", table_at))  # edi = table entry
    a.emit(bytes.fromhex("807f0f01"))  # cmp byte [edi+15], TRN
    a.rel8(0x74, "trn")
    a.emit(0x57, 0xB9, struct.pack("<I", 0x5E7C18))
    a.rel32(0xE8, LOOKUP)
    a.emit(bytes.fromhex("85c0"))
    a.rel8(0x74, "done")
    a.emit(0x6A, 0, 0x50, 0x89, 0xD9)  # null parent, gfx info; ecx=controller
    a.rel32(0xE8, LOAD)
    a.rel8(0xEB, "zones" if safe_zones else "done")
    a.label("trn")
    a.emit(0x57, 0x89, 0xD9)  # file name; ecx=controller (ReadInTerrain, ret 4)
    a.rel32(0xE8, READ_TRN)
    if safe_zones:
        a.rel8(0xEB, "zones")
    a.label("done")
    a.emit(0x61, 0x9D, DISPLACED)
    a.rel32(0xE9, SITE + len(DISPLACED))
    if safe_zones:
        # Repeat SetupFlightMode's walk (0x44B7AB..0x44B7CF) now that zones
        # exist; placed after the exit so the early branches stay short.
        a.label("zones")
        a.emit(DISPLACED, bytes.fromhex("8b806cf00d00"))  # eax = zone handler
        a.emit(bytes.fromhex("85c0"))
        a.rel8(0x74, "done")
        a.emit(bytes.fromhex("8b38"))  # edi = first safe-zone node
        a.emit(bytes.fromhex("8b0d"), struct.pack("<I", FLIGHT_MODE))
        a.emit(bytes.fromhex("85c9"))
        a.rel8(0x74, "done")
        a.emit(bytes.fromhex("8bb138010000"))  # esi = flight view
        a.emit(bytes.fromhex("85f6"))
        a.rel8(0x74, "done")
        a.label("zone")
        a.emit(bytes.fromhex("85ff"))
        a.rel8(0x74, "done")
        a.emit(bytes.fromhex("ff37"), 0x89, 0xF1)  # push box; ecx = view
        a.rel32(0xE8, ADD_SAFE_ZONE_VISUAL)
        a.emit(bytes.fromhex("8b7f08"))  # next node
        a.rel8(0xEB, "zone")
    code = a.resolve()
    assert len(code) <= table_at - CAVE
    return (code.ljust(table_at - CAVE, b"\0") + table()).ljust(REGION, b"\0")


def legacy_code():
    """Version 1 bytes (Arena1a only), recognized so prepare can upgrade them."""
    a = Asm(CAVE)
    a.emit(0x9C, 0x60)
    a.emit(bytes.fromhex("81be64030000"), MARKER)
    a.rel8(0x75, "done")
    a.emit(DISPLACED, bytes.fromhex("85c0"))
    a.rel8(0x74, "done")
    a.emit(bytes.fromhex("8b983cf00d00"))
    a.emit(bytes.fromhex("85db"))
    a.rel8(0x74, "done")
    a.emit(bytes.fromhex("833b00"))
    a.rel8(0x75, "done")
    a.emit(0x68, struct.pack("<I", CAVE + 0x100))
    a.emit(0xB9, struct.pack("<I", 0x5E7C18))
    a.rel32(0xE8, LOOKUP)
    a.emit(bytes.fromhex("85c0"))
    a.rel8(0x74, "done")
    a.emit(0x6A, 0, 0x50, 0x89, 0xD9)
    a.rel32(0xE8, LOAD)
    a.label("done")
    a.emit(0x61, 0x9D, DISPLACED)
    a.rel32(0xE9, SITE + len(DISPLACED))
    return (a.resolve().ljust(0x100, b"\0") + b"Arena1a\0").ljust(REGION, b"\0")


def _regions(cave):
    return (Region(SITE, DISPLACED, jmp_patch(SITE, CAVE, len(DISPLACED))),
            Region(CAVE, bytes(REGION), cave, "cave"))


# Version 1 (online-arena1a-v1) arrived in patch version 6, v2 in 11, v3 in 18.
PATCH = Patch(
    id=NAME, since=18, policy="always", regions=_regions(cave_code()),
    legacy=((V2_NAME, _regions(v2_code())), (LEGACY_NAME, _regions(legacy_code()))))
