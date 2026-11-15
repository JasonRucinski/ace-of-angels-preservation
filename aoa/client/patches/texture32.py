"""Load 24/32-bit TGA textures as ARGB8888 instead of RGB565/ARGB4444.

The texture loader 0x562A30 fixes its texture-view depth at 16 bits. A 24-bit
TGA becomes RGB565, and a 32-bit TGA becomes ARGB4444 (alpha bits 4). The
allocator 0x563650 already creates ARGB8888 for depth 32 (alpha 0 is promoted
to 8), and the per-surface converters for 32-bit surfaces force 24-bit sources
opaque (0x558B80 ORs 0xFF000000). The 16-bit source path is kept: the 32-bit
surface's 16-bit converter is a bare `ret`.

Rewritten in place (no code cave):
  0x562AB8  je  L16            (target moved to the shared tail)
  0x562ABD  je  L24/32          (24-bit now joins the 32-bit block)
  0x562AE3  L24/32: add ecx,ecx; and eax,ecx; shr eax,2; jmp tail
            L16:    xor eax,eax
            tail:   mov [edi+4],ecx; mov [edi+8],eax; nop
Result: 16 -> (16, 0); 24 -> (32, 0); 32 -> (32, 8). edx stays 0.
"""
from aoa.client.patches.base import Patch, Region

NAME = "texture-argb8888-v1"
SITES = (
    (0x562AB8, bytes.fromhex("7435"), bytes.fromhex("7432")),
    (0x562ABD, bytes.fromhex("7430"), bytes.fromhex("7424")),
    (0x562AE3, bytes.fromhex("894f04c7470804000000eb06894f04895708"),
     bytes.fromhex("01c921c8c1e802eb0231c0894f0489470890")),
)


PATCH = Patch(
    id=NAME, since=None, policy="option", option="experimental_texture32",
    label="32-bit textures — richer color and alpha", group="experimental",
    regions=tuple(Region(va, old, new) for va, old, new in SITES))
