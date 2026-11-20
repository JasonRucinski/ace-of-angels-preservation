"""2.9.2 ship-selection framing fix; library only, reversible known sites.

The menu is authored for a 90-degree horizontal FOV at 4:3. Keep its
effective focal length min(width/2, height*2/3) for layout and rendering.
Flight projection is untouched. Requires the existing mapped .text padding.
"""

from aoa.client import layout
from aoa.client.asm import Asm, jmp_patch
from aoa.client.patches.base import Patch, Region

NAME = "ship-menu-aspect-v1"
CAVE = layout.cave(NAME).start
SITES = ((0x463D06, bytes.fromhex("8b4058d1f8"), "layout"),
         (0x4652A1, bytes.fromhex("68db0fc93f"), "render"))


def code():
    a = Asm(CAVE)
    a.label("half_width")  # EAX = viewport structure; returns effective half width
    a.emit(bytes.fromhex("51528b48588b405cc1e00233d26a03f7342483c4043bc1"))
    a.rel8(0x76, "bounded")
    a.emit(bytes.fromhex("8bc1"))
    a.label("bounded")
    a.emit(bytes.fromhex("d1f85a59c3"))
    a.label("layout")
    a.rel32(0xE8, "half_width")
    a.rel32(0xE9, 0x463D0B)
    a.label("render")
    # Preserve registers; reserve the original push's argument plus two locals.
    a.emit(bytes.fromhex("83ec045083ec088b851c0100008b40048b4058d1f8"))
    # Physical half width -> local 0; effective half width -> local 4.
    a.emit(bytes.fromhex("8904248b851c0100008b4004"))
    a.rel32(0xE8, "half_width")
    a.emit(bytes.fromhex("89442404db0424db442404d9f3d8c0d95c240c83c40858"))
    a.rel32(0xE9, 0x4652A6)
    return a.resolve(), a.labels


def _regions():
    cave, labels = code()
    return (Region(CAVE, bytes(len(cave)), cave, "cave"),
            *(Region(va, old, jmp_patch(va, labels[label], len(old))) for va, old, label in SITES))


PATCH = Patch(
    id=NAME, since=None, policy="option", option="menu_framing", label="Widescreen ship-selection framing",
    group="fixes", default=True, regions=_regions())
