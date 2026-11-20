"""Select closest authored mesh/texture variants for solid world model groups."""
from aoa.client.patches import station_detail
from aoa.client.patches.base import Patch, Region

NAME = "world-full-detail-v1"
SITE = station_detail.SITE
ORIGINAL = station_detail.ORIGINAL
PATCHED = bytes.fromhex("b900007a4590")  # mov ecx, float-bits(4000); nop
RANGE_SITE = 0x546B46
RANGE_ORIGINAL = bytes.fromhex("7455")
RANGE_PATCHED = bytes.fromhex("eb55")  # use original 5..4096 group visibility range


# Shares its site with station-full-detail-v1, so the two conflict.
PATCH = Patch(
    id=NAME, since=None, policy="option", option="experimental_world_detail",
    label="Full world mesh and texture detail", group="experimental", conflicts=(station_detail.NAME,),
    regions=(Region(SITE, ORIGINAL, PATCHED), Region(RANGE_SITE, RANGE_ORIGINAL, RANGE_PATCHED)))
