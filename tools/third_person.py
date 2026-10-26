"""Third-person chase camera for the 2.9.2 client, toggled in flight with F2.

The renderer already has one, switched off. The main render function
0x43B1D0 tests the byte CHASE_FLAG (0x5E6879) at 0x43B35A. When it is set,
it moves the eye to position - 420 * forward + 100 * up (constants 0x59015C
and 0x5900BC; rows of the main camera matrix at graphics+0x2510) and enables
the player's node with 0x542A90(1); otherwise it calls 0x542A90(0). Nothing
in the client ever writes that byte.

Turning it on alone does not show your ship, because culling runs earlier in
the frame against the old eye. In flight the camera *is* the player's render
node: the frame function 0x449900 hands the node's matrix (node+0x7C: right,
up, forward rows, position at +0xAC) to the main-camera setter 0x553810 at
0x44A092, disables the node at 0x44A097 (0x542A90(0) stores node+0x150, the
enabled gate), and culls every object in 0x49BC90 against the camera record
[player+0x19C]+0x2C. Your ship is therefore disabled and at distance 0
(findings 9.36). Drawing (0x542990) needs enabled +0x150 and visible +0x151.

  * cave A (replaces `push eax; call 0x553810` at 0x44A091) reads F2's
    toggle bit with GetKeyState (already imported) and stores it to
    CHASE_FLAG. When set, it copies the camera record (node+0x2C, 0xE0
    bytes) to FAKE in the zero-filled .data tail, moves the copy's position
    to the renderer's chase eye (same constants), calls 0x553810 unchanged,
    and enables the node for culling with 0x542A90(1) in place of the
    original 0x542A90(0). Off, it clears NODE and the original code runs.
  * cave B (replaces `mov edx,[eax+0x19C]; add edx,0x2C` at 0x49BCB8) hands
    the culling routine FAKE instead of the real camera record when the
    camera object's node is the one cave A just used, in the same game
    tick (0x5E8E5C). Your ship is then ~430 units from the eye and visible.
    The tick check keeps spectate frames (0x449B37 path, cave A not run)
    on the original record.

Known limit: CHASE_FLAG is only updated in flight frames, so with F2 on, a
spectate view (F7) is also pulled back by the renderer's offset.

Library use only (prepare_client.py composes it); no file is written here.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402

NAME = "third-person-camera-v1"
VK_TOGGLE = 0x71                 # F2: unbound in the default key map
IAT_GETKEYSTATE = 0x58C4A0
GAME_TICK = 0x5E8E5C
CHASE_FLAG = 0x5E6879            # read only at 0x43B35A; never written by the client
CHASE_BACK = 0x59015C            # 420.0, the renderer's own constants
CHASE_UP = 0x5900BC              # 100.0
SET_MAIN_CAMERA = 0x553810       # thiscall(matrix*, tick), ret 8
SET_ENABLED = 0x542A90           # thiscall(bool): node+0x150 = arg

SITE_A = 0x44A091                # push eax ; call 0x553810
ORIGINAL_A = bytes.fromhex("50e879971000")
RESUME_A = 0x44A097              # push 0 ; mov ecx,edi ; call 0x542A90 (hide own node)
RESUME_A_SHOWN = 0x44A0A0        # after that call
SITE_B = 0x49BCB8                # mov edx,[eax+19C] ; add edx,2C
ORIGINAL_B = bytes.fromhex("8b909c01000083c22c")
RESUME_B = 0x49BCC1              # push edx ; call 0x546B20

CAVE = 0x58BC00                  # free .text padding after station detail
CAVE_END = 0x58BE00              # own_ship_model.py follows
FAKE = 0x60D300                  # .data tail (patch_client extended it to 0x60E000)
FAKE_SIZE = 0xE0                 # camera fields read: +0x4C..+0x8C, +0xD0..+0xDC
NODE = FAKE + FAKE_SIZE
TICK = NODE + 4


def d32(value):
    return struct.pack("<I", value)


def code():
    a = Asm(CAVE)
    # Cave A. eax = node+0x7C matrix (or 0), edi = player node, ecx = graphics,
    # tick already pushed. Must end by calling 0x553810 with one more push.
    a.label("cave_a")
    a.emit(0x50, 0x51)                                      # push eax; push ecx
    a.emit(b"\xc7\x05", d32(NODE), d32(0))                  # NODE = 0
    a.emit(0x6A, VK_TOGGLE)
    a.emit(b"\xff\x15", d32(IAT_GETKEYSTATE))               # GetKeyState(VK_F2)
    a.emit(b"\x24\x01\xa2", d32(CHASE_FLAG))                # and al,1; CHASE_FLAG = al
    a.emit(0x59, 0x58)                                      # pop ecx; pop eax
    a.emit(0x0F); a.rel32(0x84, "plain")                    # jz near
    a.emit(b"\x85\xc0")                                     # test eax,eax
    a.emit(0x0F); a.rel32(0x84, "plain")
    a.emit(0x56, 0x57, 0x51)                                # push esi; push edi; push ecx
    a.emit(b"\x8d\x77\x2c", 0xBF, d32(FAKE))                # esi = node+2C; edi = FAKE
    a.emit(0xB9, d32(FAKE_SIZE // 4), b"\xf3\xa5")          # rep movsd
    a.emit(0x59, 0x5F, 0x5E)                                # pop ecx; pop edi; pop esi
    for i in range(3):
        a.emit(b"\xd9\x87", d32(0x9C + 4 * i))              # fld forward[i]
        a.emit(b"\xd8\x0d", d32(CHASE_BACK))                # * 420
        a.emit(b"\xd8\xaf", d32(0xAC + 4 * i))              # fsubr position[i]
        a.emit(b"\xd9\x87", d32(0x8C + 4 * i))              # fld up[i]
        a.emit(b"\xd8\x0d", d32(CHASE_UP))                  # * 100
        a.emit(b"\xde\xc1")                                 # faddp
        a.emit(b"\xd9\x1d", d32(FAKE + 0x80 + 4 * i))       # fstp eye[i]
    a.emit(b"\x89\x3d", d32(NODE))                          # NODE = node
    a.emit(b"\x8b\x15", d32(GAME_TICK), b"\x89\x15", d32(TICK))
    a.emit(0x50)
    a.rel32(0xE8, SET_MAIN_CAMERA)
    a.emit(b"\x6a\x01\x8b\xcf")                             # push 1; mov ecx, edi
    a.rel32(0xE8, SET_ENABLED)                              # enabled for culling (original: 0)
    a.rel32(0xE9, RESUME_A_SHOWN)
    a.label("plain")
    a.emit(0x50)
    a.rel32(0xE8, SET_MAIN_CAMERA)
    a.rel32(0xE9, RESUME_A)
    # Cave B. eax = camera object; edx becomes the culling camera record.
    a.label("cave_b")
    a.emit(b"\x8b\x90\x9c\x01\x00\x00")                     # mov edx,[eax+19C]
    a.emit(b"\x85\xd2")
    a.rel8(0x74, "original")
    a.emit(b"\x3b\x15", d32(NODE))
    a.rel8(0x75, "original")
    a.emit(0xA1, d32(GAME_TICK), b"\x3b\x05", d32(TICK))
    a.rel8(0x75, "original")
    a.emit(0xBA, d32(FAKE))
    a.rel32(0xE9, RESUME_B)
    a.label("original")
    a.emit(b"\x83\xc2\x2c")
    a.rel32(0xE9, RESUME_B)
    return a.resolve(), a.labels


def regions():
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    body, labels = code()
    assert CAVE + len(body) <= CAVE_END
    return [(CAVE - 0x400000, bytes(len(body)), body),
            (SITE_A - 0x400000, ORIGINAL_A, jmp_patch(SITE_A, labels["cave_a"], len(ORIGINAL_A))),
            (SITE_B - 0x400000, ORIGINAL_B, jmp_patch(SITE_B, labels["cave_b"], len(ORIGINAL_B)))]


def state(data):
    """True if applied, False if absent; raises on anything else."""
    found = set()
    for offset, old, new in regions():
        actual = data[offset:offset + len(old)]
        if actual == old:
            found.add(False)
        elif actual == new:
            found.add(True)
        else:
            raise ValueError("unexpected third-person camera code or cave")
    if len(found) != 1:
        raise ValueError("partial third-person camera patch")
    return found.pop()


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
