"""Keep world model groups on their mesh path to the existing far horizon.

This changes the model visibility comparison, not the sprite/particle renderer.
It shares its site with the asteroid-only patch, so the two conflict; prepare
refuses both together and lets an explicit request replace the other.
"""
from aoa.client.patches import asteroid_render
from aoa.client.patches.base import Patch, Region

NAME = "solid-world-mesh-distance-v1"
SITE = asteroid_render.SITE
ORIGINAL = asteroid_render.ORIGINAL
PATCHED = bytes.fromhex("d81dc0d95900")  # fcomp [existing 900000.0 horizon]


PATCH = Patch(
    id=NAME, since=None, policy="option", option="experimental_solids",
    label="Solid world models — reduce distant shape popping", group="experimental",
    conflicts=(asteroid_render.NAME,), reads=(asteroid_render.BILLBOARD_HORIZON,),
    regions=(Region(SITE, ORIGINAL, PATCHED),))
