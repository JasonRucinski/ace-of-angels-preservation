"""Third-person cameras for the 2.9.2 client: F2 chase, F4 orbit.

The renderer already has a chase camera, switched off. The main render
function 0x43B1D0 tests the byte CHASE_FLAG (0x5E6879) at 0x43B35A. When it
is set, it moves the eye to position - 420 * forward + 100 * up (constants
0x59015C and 0x5900BC) and enables the player's node with 0x542A90(1);
otherwise it calls 0x542A90(0). Nothing in the client ever writes that byte.
The forward vector it uses is its own copy at graphics+0x262C (esi there),
which then becomes the view direction. The view matrix comes from 0x569880
with eye +0x2620, direction +0x262C and the camera object's *right* vector
(edi, from vtable +0xB0), copied to +0x2638 at 0x43B431; up is derived.

Turning it on alone does not show your ship, because culling runs earlier in
the frame against the old eye. In flight the camera *is* the player's render
node: the frame function 0x449900 hands the node's matrix (node+0x7C: right,
up, forward rows, position at +0xAC) to the main-camera setter 0x553810 at
0x44A092, disables the node at 0x44A097 (0x542A90(0) stores node+0x150, the
enabled gate), and culls every object in 0x49BC90 against the camera record
[player+0x19C]+0x2C. Your ship is therefore disabled and at distance 0
(findings 9.36). Drawing (0x542990) needs enabled +0x150 and visible +0x151.

  * cave A (replaces `push eax; call 0x553810` at 0x44A091) reads the
    toggle bits of F2 (chase) and F4 (orbit) with GetKeyState (already
    imported) and stores F2 | F4 to CHASE_FLAG. When set, it copies the
    camera record (node+0x2C, 0xE0 bytes) to FAKE in the zero-filled .data
    tail. With orbit on it turns the copy's right and forward rows about
    the ship's up axis by an angle that grows with the game clock (one lap
    per ORBIT_PERIOD ms, starting behind the ship when F4 is pressed). It
    moves the copy's position to the renderer's chase eye (same constants,
    turned forward), calls 0x553810 unchanged, and enables the node for
    culling with 0x542A90(1) in place of the original 0x542A90(0). Off, it
    clears NODE and the original code runs. It clears ARMED every frame and
    sets it on an orbit frame.
  * cave B (replaces `mov edx,[eax+0x19C]; add edx,0x2C` at 0x49BCB8) hands
    the culling routine FAKE instead of the real camera record when the
    camera object's node is the one cave A just used, in the same game
    tick (0x5E8E5C). Your ship is then ~430 units from the eye and visible.
    The tick check keeps spectate frames (0x449B37 path, cave A not run)
    on the original record.
  * cave R (replaces `mov eax,[esp+0x38]; push ecx; fld [eax+8]` at
    0x43B367, the first instructions of the renderer's chase branch) runs
    only when ARMED is set and clears it, so it serves the render that
    follows cave A in the same frame and no other (spectate frames do not
    run cave A). It copies the turned forward row from FAKE into the
    renderer's forward copy and points edi at the turned right row. The
    renderer's own arithmetic then puts the eye on the orbit and builds a
    view that keeps the ship centred. A game-tick check is not usable here:
    the millisecond clock often advances between cave A and the render.
    Turning the forward alone left the stock right vector in the view and
    skewed it (seen live, findings 9.47).

F2 and F3 are bound in the default key map (Toggle Mentor, Toggle Joystick
Curve window, registered at 0x44F464 and 0x44F47C); plain F4 is not.

Known limit: CHASE_FLAG is only updated in flight frames, so with F2 or F4
on, a spectate view (F7) is also pulled back by the renderer's offset (not
orbited).

A v1 client (chase only, before cave R) is recognized and upgraded in place.

Library use only (prepare_client.py composes it); no file is written here.
"""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm, jmp_patch  # noqa: E402

NAME = "third-person-camera-v2"
VK_TOGGLE = 0x71                 # F2: chase; bound by default only to Toggle Mentor
VK_ORBIT = 0x73                  # F4: orbit; unbound in the default key map
IAT_GETKEYSTATE = 0x58C4A0
GAME_TICK = 0x5E8E5C
CHASE_FLAG = 0x5E6879            # read only at 0x43B35A; never written by the client
CHASE_BACK = 0x59015C            # 420.0, the renderer's own constants
CHASE_UP = 0x5900BC              # 100.0
SET_MAIN_CAMERA = 0x553810       # thiscall(matrix*, tick), ret 8
SET_ENABLED = 0x542A90           # thiscall(bool): node+0x150 = arg
ORBIT_PERIOD = 24000             # ms per lap

SITE_A = 0x44A091                # push eax ; call 0x553810
ORIGINAL_A = bytes.fromhex("50e879971000")
RESUME_A = 0x44A097              # push 0 ; mov ecx,edi ; call 0x542A90 (hide own node)
RESUME_A_SHOWN = 0x44A0A0        # after that call
SITE_B = 0x49BCB8                # mov edx,[eax+19C] ; add edx,2C
ORIGINAL_B = bytes.fromhex("8b909c01000083c22c")
RESUME_B = 0x49BCC1              # push edx ; call 0x546B20
SITE_R = 0x43B367                # mov eax,[esp+38] ; push ecx ; fld [eax+8]
ORIGINAL_R = bytes.fromhex("8b44243851d94008")
RESUME_R = 0x43B36F              # fmul [0x5900BC] (up * 100)

CAVE = 0x58BC00                  # free .text padding after station detail
CAVE_END = 0x58BE00              # own_ship_model.py follows
FAKE = 0x60D300                  # .data tail (patch_client extended it to 0x60E000)
FAKE_SIZE = 0xE0                 # camera fields read: +0x4C..+0x8C, +0xD0..+0xDC
NODE = FAKE + FAKE_SIZE
TICK = NODE + 4
ORBIT = TICK + 0xC               # after own_ship_menu's RESTRICT (TICK + 8)
START = ORBIT + 4                # game tick when F4 last changed
ARMED = START + 4                # set by cave A on an orbit frame, used up by cave R


def d32(value):
    return struct.pack("<I", value)


def code(legacy=False):
    """legacy=True rebuilds the v1 cave (chase only) for recognition and upgrade."""
    a = Asm(CAVE)
    # Cave A. eax = node+0x7C matrix (or 0), edi = player node, ecx = graphics,
    # tick already pushed. Must end by calling 0x553810 with one more push.
    a.label("cave_a")
    a.emit(0x50, 0x51)                                      # push eax; push ecx
    a.emit(b"\xc7\x05", d32(NODE), d32(0))                  # NODE = 0
    if not legacy:
        a.emit(b"\xc6\x05", d32(ARMED), 0)                  # ARMED = 0
        a.emit(0x6A, VK_ORBIT)
        a.emit(b"\xff\x15", d32(IAT_GETKEYSTATE))           # GetKeyState(VK_F4)
        a.emit(b"\x24\x01\x3a\x05", d32(ORBIT))             # and al,1; cmp al,ORBIT
        a.rel8(0x74, "same")
        a.emit(0xA2, d32(ORBIT))                            # ORBIT = al
        a.emit(b"\x8b\x15", d32(GAME_TICK), b"\x89\x15", d32(START))  # START = tick
        a.label("same")
    a.emit(0x6A, VK_TOGGLE)
    a.emit(b"\xff\x15", d32(IAT_GETKEYSTATE))               # GetKeyState(VK_F2)
    a.emit(b"\x24\x01")                                     # and al,1
    if not legacy:
        a.emit(b"\x0a\x05", d32(ORBIT))                     # or al,ORBIT
    a.emit(0xA2, d32(CHASE_FLAG))                           # CHASE_FLAG = al
    a.emit(0x59, 0x58)                                      # pop ecx; pop eax
    a.emit(0x0F); a.rel32(0x84, "plain")                    # jz near
    a.emit(b"\x85\xc0")                                     # test eax,eax
    a.emit(0x0F); a.rel32(0x84, "plain")
    a.emit(0x56, 0x57, 0x51)                                # push esi; push edi; push ecx
    a.emit(b"\x8d\x77\x2c", 0xBF, d32(FAKE))                # esi = node+2C; edi = FAKE
    a.emit(0xB9, d32(FAKE_SIZE // 4), b"\xf3\xa5")          # rep movsd
    a.emit(0x59, 0x5F, 0x5E)                                # pop ecx; pop edi; pop esi
    if not legacy:
        a.emit(b"\x80\x3d", d32(ORBIT), 0)                  # cmp byte ORBIT,0
        a.rel8(0x74, "eye")
        a.emit(0x50, 0x51, 0x56)                            # push eax; push ecx; push esi
        a.emit(0xA1, d32(GAME_TICK), b"\x2b\x05", d32(START))   # eax = tick - START
        a.emit(b"\x31\xd2", 0xB9, d32(ORBIT_PERIOD), b"\xf7\xf1")  # edx = eax % period
        a.emit(0x52, b"\xdb\x04\x24", 0x5A)                 # fild dword [esp] (via push/pop edx)
        a.emit(b"\xd8\x0d"); a.fixups.append(("abs32", len(a.code), "rate")); a.emit(d32(0))
        a.emit(b"\xd9\xfb")                                 # fsincos: st0 = cos, st1 = sin
        a.emit(0xBE, d32(FAKE))                             # esi = FAKE (+0x50 right, +0x70 forward)
        a.label("turn")
        a.emit(b"\xd9\x46\x70\xd8\xc9")                     # f * cos
        a.emit(b"\xd9\x46\x50\xd8\xcb\xde\xc1")             # + r * sin  -> forward'
        a.emit(b"\xd9\x46\x50\xd8\xca")                     # r * cos
        a.emit(b"\xd9\x46\x70\xd8\xcc\xde\xe9")             # - f * sin  -> right'
        a.emit(b"\xd9\x5e\x50\xd9\x5e\x70")                 # store right', forward'
        a.emit(b"\x83\xc6\x04\x81\xfe", d32(FAKE + 0xC))    # add esi,4; cmp esi,FAKE+0xC
        a.rel8(0x72, "turn")                                # jb turn
        a.emit(b"\xdd\xd8\xdd\xd8")                         # drop cos, sin
        a.emit(0x5E, 0x59, 0x58)                            # pop esi; pop ecx; pop eax
        a.emit(b"\xc6\x05", d32(ARMED), 1)                  # ARMED = 1 (this frame's render)
        a.label("eye")
    for i in range(3):
        if legacy:
            a.emit(b"\xd9\x87", d32(0x9C + 4 * i))          # fld forward[i]
        else:
            a.emit(b"\xd9\x05", d32(FAKE + 0x70 + 4 * i))   # fld (turned) forward[i]
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
    if not legacy:
        # Cave R. esi = graphics+0x262C (the renderer's forward copy); edi = the
        # camera object's right vector, copied to graphics+0x2638 at 0x43B431.
        a.label("cave_r")
        a.emit(b"\x80\x3d", d32(ARMED), 0)                  # cmp byte ARMED,0
        a.rel8(0x74, "chase")
        a.emit(b"\xc6\x05", d32(ARMED), 0)                  # used up: one render per cave A
        for i in range(3):
            a.emit(0xA1, d32(FAKE + 0x70 + 4 * i), b"\x89\x46", 4 * i)   # forward[i] = turned
        a.emit(0xBF, d32(FAKE + 0x50))                      # edi = turned right
        a.label("chase")
        a.emit(ORIGINAL_R)
        a.rel32(0xE9, RESUME_R)
        a.label("rate")
        a.emit(struct.pack("<f", 2 * math.pi / ORBIT_PERIOD))
    abs32 = [f for f in a.fixups if f[0] == "abs32"]
    a.fixups = [f for f in a.fixups if f[0] != "abs32"]
    body = bytearray(a.resolve())
    for _, pos, label in abs32:
        struct.pack_into("<I", body, pos, a.labels[label])
    return bytes(body), a.labels


def regions(legacy=False):
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    body, labels = code(legacy)
    assert CAVE + len(body) <= CAVE_END
    out = [(CAVE - 0x400000, bytes(len(body)), body),
           (SITE_A - 0x400000, ORIGINAL_A, jmp_patch(SITE_A, labels["cave_a"], len(ORIGINAL_A))),
           (SITE_B - 0x400000, ORIGINAL_B, jmp_patch(SITE_B, labels["cave_b"], len(ORIGINAL_B)))]
    if not legacy:
        out.append((SITE_R - 0x400000, ORIGINAL_R, jmp_patch(SITE_R, labels["cave_r"], len(ORIGINAL_R))))
    return out


def matches(data, legacy):
    """True/False if every region is patched/original for this variant, else None."""
    found = set()
    for offset, old, new in regions(legacy):
        actual = data[offset:offset + len(old)]
        if actual == old:
            found.add(False)
        elif actual == new:
            found.add(True)
        else:
            return None
    return found.pop() if len(found) == 1 else None


def state(data):
    """True if applied (v2 or the v1 chase-only cave), False if absent; raises otherwise."""
    for legacy in (False, True):
        found = matches(data, legacy)
        if found is not None:
            return found
    raise ValueError("unexpected or partial third-person camera patch")


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    if matches(data, True):                    # remove the v1 cave before applying
        for offset, old, new in regions(True):
            out[offset:offset + len(old)] = old
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
