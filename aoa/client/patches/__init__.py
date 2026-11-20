"""The registry: every client patch, in the order prepare applies and reports them.

REGISTRY is the only list of patches. aoa/client/prepare.py derives from it
what inspect() reports, what configure() removes and applies (and in which
order), the requires/conflicts rules, the `prepare` command-line flags and
what `check` requires; aoa/launchers/client_launcher.py derives its
checkboxes. Adding a patch means one module exporting PATCH, one entry here
and one reservation in aoa/client/layout.py.

PATCH_LEVEL is the patch version recorded in _client_setup.json (the highest
`since`); levels() is the version table.
"""
from aoa.client.patches import archive_terminator
from aoa.client.patches import asteroid_render
from aoa.client.patches import background_network
from aoa.client.patches import cursor_warp
from aoa.client.patches import explicit_protection
from aoa.client.patches import frame_clock
from aoa.client.patches import logger
from aoa.client.patches import menu_aspect
from aoa.client.patches import object_persistence
from aoa.client.patches import online_terrain
from aoa.client.patches import own_ship_menu
from aoa.client.patches import own_ship_model
from aoa.client.patches import physics_timestep
from aoa.client.patches import powerup_pickup
from aoa.client.patches import solid_world_render
from aoa.client.patches import station_detail
from aoa.client.patches import texture32
from aoa.client.patches import third_person
from aoa.client.patches import visibility_fix
from aoa.client.patches import world_detail

REGISTRY = (
    *logger.PATCHES,
    physics_timestep.PATCH,
    background_network.PATCH,
    archive_terminator.PATCH,
    menu_aspect.PATCH,
    cursor_warp.PATCH,
    online_terrain.PATCH,
    asteroid_render.PATCH,
    solid_world_render.PATCH,
    station_detail.PATCH,
    world_detail.PATCH,
    object_persistence.PATCH,
    texture32.PATCH,
    frame_clock.PATCH,
    visibility_fix.PATCH,
    third_person.PATCH,
    own_ship_model.PATCH,
    own_ship_menu.PATCH,
    powerup_pickup.PATCH,
    explicit_protection.PATCH,
)
BY_ID = {p.id: p for p in REGISTRY}
# Every recognized variant ID (current and legacy) -> its patch.
VARIANT_OF = {variant: p for p in REGISTRY for variant, _ in p.variants}
# The patches a player chooses, by option name.
OPTIONS = {p.option: p for p in REGISTRY if p.option}
# Pairs that share code, each once, in registry order.
CONFLICTS = tuple((p, BY_ID[other]) for i, p in enumerate(REGISTRY) for other in p.conflicts
                  if REGISTRY.index(BY_ID[other]) > i)
PATCH_LEVEL = max(p.since for p in REGISTRY if p.since is not None)


def levels():
    """{patch version: [patch IDs that arrived in it]}; None: arrived in 4 to 10, not recorded."""
    table = {}
    for p in REGISTRY:
        table.setdefault(p.since, []).append(p.id)
    return table


def _check():
    assert len(BY_ID) == len(REGISTRY) and len(VARIANT_OF) == sum(len(p.variants) for p in REGISTRY)
    for p in REGISTRY:
        for other in (*p.requires, *p.conflicts):
            assert other in BY_ID and other != p.id, (p.id, other)
        for other in p.conflicts:
            assert p.id in BY_ID[other].conflicts, f"{p.id} conflicts with {other} but not the reverse"
        if p.policy == "option" and not p.option:
            assert p.requires and all(BY_ID[r].option for r in p.requires), f"{p.id}: no option to follow"


_check()
