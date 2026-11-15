"""World-object indices and tags of everything the server places, from one table.

The 2.9.2 client keeps world objects in a 1000-entry table (AllocNewObject
0x4A5960 makes tag 0x40CCIIII with index IIII below 1000). The host's kinds
each own a fixed block; target ships fill upward from index 2 and stop below
the lowest block a run reserves. Imports nothing from the server.

aoa/maps/navigation.py keeps its own copy of the buoy block (the maps layer
may not import the host); tests/test_host_data.py checks they agree.
"""
OBJECT_LIMIT = 1000
OBJECT_TAG = 0x40010000     # LoadObject 0x25 world objects: the test object, targets, gates, turrets, buoys
DYNAMIC_TAG = 0x40000000    # SpawnPowerUp 0x43 power-ups; missiles add a counter byte (0x40CC0000)
PLAYER_TAG = 0x80010000

# kind: (first index, count). Ordered by index; no two overlap.
BLOCKS = {
    "test_object": (1, 1),
    "warp_gates": (71, 9),
    "turrets": (80, 5),
    "buoys": (90, 10),
    "powerups": (100, 400),
    "missiles": (500, 500),
}
TARGETS_FIRST = 2
# The fixed block after the target ships when nothing else is reserved.
TARGETS_END = BLOCKS["powerups"][0]


def first(kind):
    return BLOCKS[kind][0]


def last(kind):
    start, count = BLOCKS[kind]
    return start + count - 1


def count(kind):
    return BLOCKS[kind][1]


def target_limit(reserved=()):
    """Most target ships that fit below the lowest reserved block (98 with none)."""
    return min([first(kind) for kind in reserved] + [TARGETS_END]) - TARGETS_FIRST


def object_tag(index):
    """Tag of a LoadObject world object at this index."""
    if not 0 < index < OBJECT_LIMIT:
        raise ValueError(f"object index {index} is not 1..{OBJECT_LIMIT - 1}")
    return OBJECT_TAG | index


def reservation(kind):
    """'slots 71..79' for messages."""
    return f"slots {first(kind)}..{last(kind)}"
