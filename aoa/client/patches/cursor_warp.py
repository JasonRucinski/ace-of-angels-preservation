"""2.9.2 in-game cursor warp fix; library only, reversible known site.

The mouse object's warp (0x4EACE0) calls SetCursorPos(x + origin) with a
client origin cached from WM_MOVE (0x4451D0) as *unsigned* 16-bit words.
A negative or stale origin (seen live: 65535,65535 for a window at 0,0)
sends every warp to the lower-right screen corner. Window dragging warps the
cursor to window + grab offset each frame (0x51E072), so the panel then
chases the cursor into that corner. The cave asks Windows for the current
origin with ScreenToClient (already imported) on the main window handle
(0x5E6DE8). If that fails, the original cached-origin arithmetic is kept.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch

NAME = "cursor-warp-origin-v1"
CAVE = 0x58B300  # free .text padding between logger lock and physics guard
SITE = 0x4EAD16
RESUME = 0x4EAD28  # pop esi; ret 8
# mov esi,[ecx+2c]; mov ecx,[ecx+28]; add esi,edx; add ecx,eax;
# push esi; push ecx; call [SetCursorPos]
DISPLACED = bytes.fromhex("8b712c8b492803f203c85651ff1514c55800")
MAIN_HWND = 0x5E6DE8
IAT_SCREENTOCLIENT = 0x58C480
IAT_SETCURSORPOS = 0x58C514


def code():
    # Entry: ECX = mouse object; [esp] saved ESI, [esp+8] x, [esp+0xc] y.
    a = Asm(CAVE)
    a.emit(0x51)                                   # push ecx (this)
    a.emit(bytes.fromhex("6a006a0054"))            # POINT {0,0}; push &POINT
    a.emit(bytes.fromhex("ff35"), MAIN_HWND.to_bytes(4, "little"))
    a.emit(bytes.fromhex("ff15"), IAT_SCREENTOCLIENT.to_bytes(4, "little"))
    a.emit(bytes.fromhex("595a85c058"))            # ecx=-ox; edx=-oy; test eax; eax=this
    a.rel8(0x75, "live")
    # Fallback: the original cached origin, negated to match.
    a.emit(bytes.fromhex("8b4828f7d98b502cf7da"))
    a.label("live")
    a.emit(bytes.fromhex("8b4424082bc18b74240c2bf25650"))  # push y - (-oy); push x - (-ox)
    a.emit(bytes.fromhex("ff15"), IAT_SETCURSORPOS.to_bytes(4, "little"))
    a.rel32(0xE9, RESUME)
    return a.resolve()


def regions():
    cave = code()
    assert CAVE + len(cave) <= 0x58B400
    return [(CAVE - 0x400000, bytes(len(cave)), cave),
            (SITE - 0x400000, DISPLACED, jmp_patch(SITE, CAVE, len(DISPLACED)))]


def state(data):
    states = []
    for off, old, new in regions():
        actual = data[off:off + len(old)]
        if actual not in (old, new):
            raise ValueError("unexpected cursor-warp code or cave")
        states.append(actual == new)
    if len(set(states)) != 1:
        raise ValueError("partial cursor-warp patch")
    return states[0]


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    for off, old, new in regions():
        out[off:off + len(old)] = new if enabled else old
    return bytes(out)
