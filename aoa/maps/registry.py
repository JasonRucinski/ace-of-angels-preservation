"""The maps the online terrain hook can load, with their markers, spawns and notes.

Pure data, standard library only. The server, the launchers and the map
tools read it; the client patch aoa.client.patches.online_terrain builds its
cave's map table from MAPS, so changing MAPS changes the patch bytes (the
golden snapshot in tests/snapshots/patch_regions.json catches that).

The server picks a map with the flight-entry marker: `AR1A` (version 1, kept
so v1-prepared clients still get Arena1a) selects index 0; `MAP` + one index
byte selects any entry of MAPS.
"""
MARKER = b"AR1A"
MAP_PREFIX = b"MAP"
LAYOUT, TRN = 0, 1  # loader kind: an original graphics layout, or a converted .TRN file

# name, loader kind, file or layout name, viewing spawn (None = relay default
# near the origin). Index 0 must stay Arena1a for the AR1A marker. Spawns sit
# in front of geometry (ships face +z); they are viewing aids, not original
# spawn points. The JRMAP file is written by `tools/map_viewer.py install`.
MAPS = (
    ("Arena1a", LAYOUT, "Arena1a", None),
    ("CTF_arena", LAYOUT, "CTF_arena", None),
    ("CTF_arena_b", LAYOUT, "CTF_arena_b", (45396.0, 4633.0, 80000.0)),
    ("newterrain", LAYOUT, "newterrain", None),
    ("outerchange", LAYOUT, "outerchange", None),
    ("ast_fld_a", LAYOUT, "ast_fld_a", None),
    ("ast_fld_b", LAYOUT, "ast_fld_b", None),
    ("ast_fld_c", LAYOUT, "ast_fld_c", None),
    ("ast_fld_d", LAYOUT, "ast_fld_d", None),
    ("CTF_base", LAYOUT, "CTF_base", (0.0, 0.0, -12000.0)),
    ("hu_base_a", LAYOUT, "hu_base_a", None),
    ("hu_base_b", LAYOUT, "hu_base_b", None),
    ("hy_base_test", LAYOUT, "hy_base_test", None),
    ("hy_winga", LAYOUT, "hy_winga", (0.0, 0.0, -6000.0)),
    ("HyBase2Lay", LAYOUT, "HyBase2Lay", None),
    ("irrosa01", LAYOUT, "irrosa01", None),
    ("ze_winga", LAYOUT, "ze_winga", (0.0, 0.0, -3000.0)),
    ("ze_wingb", LAYOUT, "ze_wingb", (0.0, 0.0, -3000.0)),
    ("Hittest", LAYOUT, "Hittest", (0.0, 0.0, -4000.0)),
    ("JRMAP", TRN, "jrmap292.trn", (-6000.0, -6000.0, -112000.0)),
)
MAP_NAMES = tuple(m[0] for m in MAPS)

# What a real client built on flight entry (23 Oct 2026, docs/STATUS.md#maps):
# "playable" has real content, "component" is a small part of a larger layout
# shown alone (1 to 10 objects), "empty" builds nothing alone. Loading is not
# verified play: no map has verified collision.
PLAYABLE, COMPONENT, EMPTY = "playable", "component", "empty"
CONTENT = {
    "Arena1a": PLAYABLE, "CTF_arena": PLAYABLE, "CTF_arena_b": PLAYABLE, "newterrain": PLAYABLE,
    "outerchange": PLAYABLE, "ast_fld_a": PLAYABLE, "ast_fld_b": PLAYABLE, "ast_fld_c": PLAYABLE,
    "ast_fld_d": PLAYABLE, "CTF_base": COMPONENT, "hu_base_a": COMPONENT, "hu_base_b": COMPONENT,
    "hy_base_test": COMPONENT, "hy_winga": EMPTY, "HyBase2Lay": COMPONENT, "irrosa01": PLAYABLE,
    "ze_winga": EMPTY, "ze_wingb": EMPTY, "Hittest": EMPTY, "JRMAP": PLAYABLE,
}
# Native terrain objects a real client built on flight entry (23 Oct 2026).
NOTES = {
    "Arena1a": "239 objects; main arena", "CTF_arena": "55 objects",
    "CTF_arena_b": "60 objects", "newterrain": "234 objects", "outerchange": "616 objects; very large",
    "ast_fld_a": "27 objects", "ast_fld_b": "49 objects", "ast_fld_c": "15 objects", "ast_fld_d": "10 objects",
    "CTF_base": "1 object; component", "hu_base_a": "4 objects; component", "hu_base_b": "2 objects; component",
    "hy_base_test": "2 objects; component", "hy_winga": "loads nothing alone", "HyBase2Lay": "10 objects; component",
    "irrosa01": "457 objects", "ze_winga": "loads nothing alone", "ze_wingb": "loads nothing alone",
    "Hittest": "loads nothing alone",
    "JRMAP": "23 objects incl. 5 safe zones; 2.0.0 editor map (run install first)",
}


def marker(name):
    index = MAP_NAMES.index(name)
    return MARKER if index == 0 else MAP_PREFIX + bytes([index])


def spawn(name):
    return MAPS[MAP_NAMES.index(name)][3]

