"""third-person-camera-v2: all three caves run in Unicorn on the prepared client image."""
import math
import struct
import sys
import unittest
from pathlib import Path

import capstone
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                               UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_ESP,
                               UC_X86_REG_EIP)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import own_ship_menu  # noqa: E402
import own_ship_model  # noqa: E402
import prepare_client  # noqa: E402
import third_person as tp  # noqa: E402

ORIGINAL = Path(__file__).resolve().parents[1] / "game/2.9.2/AOACLIENT.EXE.orig"
NODE, RECORD, GRAPHICS, STACK = 0x700000, 0x701000, 0x702000, 0x720000
STUB_GETKEYSTATE = 0x6F0000


def floats(u, address, values):
    u.mem_write(address, struct.pack(f"<{len(values)}f", *values))


def readfloats(u, address, count):
    return list(struct.unpack(f"<{count}f", u.mem_read(address, 4 * count)))


def machine(image, toggled, tick=1000, orbit=False):
    u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x20F000)                 # image through .data tail
    u.mem_map(0x6F0000, 0x40000)
    u.mem_write(0x401000, image[0x1000:0x1C1000])  # .text and .rdata (renderer constants)
    u.mem_write(tp.IAT_GETKEYSTATE, struct.pack("<I", STUB_GETKEYSTATE))
    u.mem_write(tp.GAME_TICK, struct.pack("<I", tick))
    calls = {"getkeystate": [], "main_camera": []}

    def stub(uc, address, size, _):
        esp = uc.reg_read(UC_X86_REG_ESP)
        if address == STUB_GETKEYSTATE:
            ret, vk = struct.unpack("<II", uc.mem_read(esp, 8))
            calls["getkeystate"].append(vk)
            on = {tp.VK_TOGGLE: toggled, tp.VK_ORBIT: orbit}.get(vk, False)
            uc.reg_write(UC_X86_REG_EAX, 0xFFFF0001 if on else 0xFFFF0000)  # toggle bit only
            uc.reg_write(UC_X86_REG_ECX, 0xBAD1)
            uc.reg_write(UC_X86_REG_EDX, 0xBAD2)
            uc.reg_write(UC_X86_REG_ESP, esp + 8)
        else:                                      # 0x553810 thiscall(matrix, tick), ret 8
            ret, matrix, when = struct.unpack("<III", uc.mem_read(esp, 12))
            calls["main_camera"].append({"this": uc.reg_read(UC_X86_REG_ECX), "matrix": matrix,
                                         "values": readfloats(uc, matrix, 16) if matrix else None,
                                         "tick": when})
            uc.reg_write(UC_X86_REG_ESP, esp + 12)
        uc.reg_write(UC_X86_REG_EIP, ret)

    u.hook_add(UC_HOOK_CODE, stub, begin=STUB_GETKEYSTATE, end=STUB_GETKEYSTATE)
    u.hook_add(UC_HOOK_CODE, stub, begin=tp.SET_MAIN_CAMERA, end=tp.SET_MAIN_CAMERA)
    return u, calls


def ship(u, yaw=0.7, pitch=-0.3, position=(1000.0, -250.0, 40000.0), radius=116.0):
    """Orthonormal right/up/forward rows at node+0x7C, position at +0xAC."""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    forward = [sy * cp, -sp, cy * cp]
    up = [sy * sp, cp, cy * sp]
    right = [cy, 0.0, -sy]
    u.mem_write(NODE, bytes(0x400))
    floats(u, NODE + 0x7C, right + [0] + up + [0] + forward + [0] + list(position) + [1])
    floats(u, NODE + 0x164, [radius])
    u.mem_write(NODE + 0xFC, struct.pack("<3f", 5, 6, 7))   # camera+0xD0, read by 0x546B20
    u.mem_write(RECORD + 0x19C, struct.pack("<I", NODE))
    return right, up, forward, list(position)


def run_site_a(u):
    """Enter at 0x44A091 as the frame function does; return where it rejoins.

    0x44A097 (original `push 0; call 0x542A90` still to run) or 0x44A0A0
    (the cave already enabled the node)."""
    sp = STACK - 0x200
    u.mem_write(sp, struct.pack("<I", 1234))       # tick already pushed at 0x44A090
    regs = {UC_X86_REG_ESP: sp, UC_X86_REG_EAX: NODE + 0x7C, UC_X86_REG_ECX: GRAPHICS,
            UC_X86_REG_EDI: NODE, UC_X86_REG_ESI: 0x5151, UC_X86_REG_EBX: 0xB0B0,
            UC_X86_REG_EBP: RECORD}
    for reg, value in regs.items():
        u.reg_write(reg, value)
    stops = []

    def stop(uc, address, size, _):
        stops.append(address)
        uc.emu_stop()
    hooks = [u.hook_add(UC_HOOK_CODE, stop, begin=at, end=at) for at in (tp.RESUME_A, tp.RESUME_A_SHOWN)]
    u.emu_start(tp.SITE_A, 0, count=400)
    for hook in hooks:
        u.hook_del(hook)
    assert len(stops) == 1, "rejoined the frame function"
    assert u.reg_read(UC_X86_REG_ESP) == sp + 4, "stack balance"
    for reg in (UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_EBX, UC_X86_REG_EBP):
        assert u.reg_read(reg) == regs[reg], "preserved registers"
    return stops[0]


def run_site_b(u, camera_object=RECORD):
    """Enter at 0x49BCB8 with eax = camera object; return edx at 0x49BCC1."""
    u.reg_write(UC_X86_REG_ESP, STACK - 0x100)
    u.reg_write(UC_X86_REG_EAX, camera_object)
    u.emu_start(tp.SITE_B, tp.RESUME_B, count=50)
    return u.reg_read(UC_X86_REG_EDX)


def run_renderer_chase(u, right, forward, up, position, player=RECORD):
    """Run the renderer from its chase branch to the built view matrix.

    0x43B367 (cave R) .. 0x43B47C, after 0x569880 built the view, including
    0x43B560, 0x542A90 and 0x5697A0. Stack as 0x43B1D0 leaves it: +0x24
    position, +0x30 the player object (world+0xD32AC), +0x38 the up vector's
    address; esi = graphics+0x262C (the forward copy), edi = the camera
    object's right vector. Returns (eye, forward copy, right copy, view)."""
    sp, up_at, right_at = STACK - 0x400, 0x706000, 0x706100
    floats(u, up_at, up)
    floats(u, right_at, right)
    u.mem_write(sp - 0x40, bytes(0x100))
    floats(u, sp + 0x24, position)
    u.mem_write(sp + 0x30, struct.pack("<I", player))
    u.mem_write(sp + 0x38, struct.pack("<I", up_at))
    floats(u, GRAPHICS + 0x262C, forward)
    u.reg_write(UC_X86_REG_ESP, sp)
    u.reg_write(UC_X86_REG_EBP, GRAPHICS)
    u.reg_write(UC_X86_REG_ESI, GRAPHICS + 0x262C)
    u.reg_write(UC_X86_REG_EDI, right_at)
    u.reg_write(UC_X86_REG_EBX, 0xB0B0)
    u.emu_start(tp.SITE_R, 0x43B47C, count=2000)
    assert u.reg_read(UC_X86_REG_ESP) == sp - 0x14, "five 0x569880 arguments pushed"
    view = readfloats(u, u.reg_read(UC_X86_REG_EAX), 16)
    return (readfloats(u, GRAPHICS + 0x2620, 3), readfloats(u, GRAPHICS + 0x262C, 3),
            readfloats(u, GRAPHICS + 0x2638, 3), view)


def in_view(view, point):
    """D3D row-vector transform: [x y z 1] * view."""
    return [sum(point[i] * view[4 * i + j] for i in range(3)) + view[12 + j] for j in range(3)]


def turned(right, forward, dt):
    angle = 2 * math.pi * (dt % tp.ORBIT_PERIOD) / tp.ORBIT_PERIOD
    c, s = math.cos(angle), math.sin(angle)
    return ([c * r - s * f for r, f in zip(right, forward)],
            [c * f + s * r for r, f in zip(right, forward)])


class ThirdPersonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = ORIGINAL.read_bytes()
        cls.prepared = prepare_client.configure(cls.raw)

    def test_off_is_the_original_camera(self):
        u, calls = machine(self.prepared, toggled=False)
        ship(u)
        u.mem_write(tp.NODE, struct.pack("<I", NODE))       # stale state from a previous frame
        u.mem_write(NODE + 0x150, b"\x07")
        u.mem_write(tp.CHASE_FLAG, b"\x01")                  # F2 was on last frame
        self.assertEqual(run_site_a(u), tp.RESUME_A)        # original hide call still to run
        self.assertEqual(u.mem_read(NODE + 0x150, 1), b"\x07")
        self.assertEqual(u.mem_read(tp.CHASE_FLAG, 1), b"\x00")
        self.assertEqual(calls["getkeystate"], [tp.VK_ORBIT, tp.VK_TOGGLE])
        self.assertEqual(calls["main_camera"][0]["matrix"], NODE + 0x7C)
        self.assertEqual(calls["main_camera"][0]["this"], GRAPHICS)
        self.assertEqual(calls["main_camera"][0]["tick"], 1234)
        self.assertEqual(struct.unpack("<I", u.mem_read(tp.NODE, 4))[0], 0)
        self.assertEqual(run_site_b(u), NODE + 0x2C)

    def test_renderer_chase_constants(self):
        # The dormant branch at 0x43B35A that CHASE_FLAG switches on.
        self.assertEqual(self.raw[0x43B35A - 0x400000:][:5], b"\xa0" + struct.pack("<I", tp.CHASE_FLAG))
        self.assertEqual(struct.unpack_from("<f", self.raw, tp.CHASE_BACK - 0x400000)[0], 420.0)
        self.assertEqual(struct.unpack_from("<f", self.raw, tp.CHASE_UP - 0x400000)[0], 100.0)

    def test_on_sets_the_flag_and_culls_from_the_renderer_eye(self):
        for yaw, pitch in ((0.0, 0.0), (0.7, -0.3), (-2.5, 1.2)):
            with self.subTest(yaw=yaw, pitch=pitch):
                u, calls = machine(self.prepared, toggled=True)
                right, up, forward, position = ship(u, yaw=yaw, pitch=pitch)
                self.assertEqual(run_site_a(u), tp.RESUME_A_SHOWN)
                self.assertEqual(u.mem_read(tp.CHASE_FLAG, 1), b"\x01")
                self.assertEqual(u.mem_read(NODE + 0x150, 1), b"\x01")   # own ship enabled
                call = calls["main_camera"][0]                          # main camera unchanged
                self.assertEqual((call["matrix"], call["this"], call["tick"]), (NODE + 0x7C, GRAPHICS, 1234))
                eye = [p - f * 420 + v * 100 for p, f, v in zip(position, forward, up)]
                for got, want in zip(readfloats(u, tp.FAKE + 0x80, 3), eye):
                    self.assertAlmostEqual(got, want, delta=abs(want) * 1e-6 + 1e-3)
                self.assertEqual(readfloats(u, tp.FAKE + 0x50, 12), readfloats(u, NODE + 0x7C, 12))
                # The ship's own node never moves.
                self.assertEqual(readfloats(u, NODE + 0xAC, 3), list(struct.unpack(
                    "<3f", struct.pack("<3f", *position))))

    def test_chase_renderer_branch_is_unchanged(self):
        u, calls = machine(self.prepared, toggled=True, tick=3000)
        right, up, forward, position = ship(u)
        run_site_a(u)
        eye, direction, side, view = run_renderer_chase(u, right, forward, up, position)
        self.assertEqual(direction, list(struct.unpack("<3f", struct.pack("<3f", *forward))))
        self.assertEqual(side, list(struct.unpack("<3f", struct.pack("<3f", *right))))
        for got, want in zip(eye, readfloats(u, tp.FAKE + 0x80, 3)):
            self.assertAlmostEqual(got, want, delta=abs(want) * 1e-6 + 1e-3)
        self.assert_ship_framed(view, position)

    def assert_ship_framed(self, view, position):
        """A rotation with the ship 420 ahead of the eye and 100 below it, centred."""
        for got, want in zip(in_view(view, position), (0, -100, 420)):
            self.assertAlmostEqual(got, want, delta=0.05)
        rows = [view[0:3], view[4:7], view[8:11]]
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(sum(a * b for a, b in zip(rows[i], rows[j])), float(i == j), delta=1e-4)

    def test_orbit_turns_culling_and_view_together(self):
        for yaw, pitch in ((0.0, 0.0), (0.7, -0.3), (-2.5, 1.2)):
            for dt in (0, 6000, 7777, 12000, 30000):
                with self.subTest(yaw=yaw, pitch=pitch, dt=dt):
                    u, calls = machine(self.prepared, toggled=False, orbit=True, tick=50000)
                    right, up, forward, position = ship(u, yaw=yaw, pitch=pitch)
                    run_site_a(u)                                    # F4 pressed: lap starts
                    self.assertEqual(struct.unpack("<I", u.mem_read(tp.START, 4))[0], 50000)
                    u.mem_write(tp.GAME_TICK, struct.pack("<I", 50000 + dt))
                    self.assertEqual(run_site_a(u), tp.RESUME_A_SHOWN)
                    self.assertEqual(struct.unpack("<I", u.mem_read(tp.START, 4))[0], 50000)
                    self.assertEqual(u.mem_read(tp.CHASE_FLAG, 1), b"\x01")  # F4 alone
                    self.assertEqual(u.mem_read(NODE + 0x150, 1), b"\x01")
                    self.assertEqual(calls["main_camera"][-1]["matrix"], NODE + 0x7C)
                    right2, forward2 = turned(right, forward, dt)
                    for row, want in ((0x50, right2), (0x60, up), (0x70, forward2)):
                        for got, w in zip(readfloats(u, tp.FAKE + row, 3), want):
                            self.assertAlmostEqual(got, w, delta=1e-5)
                    eye = [p - f * 420 + v * 100 for p, f, v in zip(position, forward2, up)]
                    for got, want in zip(readfloats(u, tp.FAKE + 0x80, 3), eye):
                        self.assertAlmostEqual(got, want, delta=abs(want) * 1e-6 + 1e-2)
                    # The ship's own node never turns or moves.
                    for at, row in ((0x7C, right), (0x9C, forward), (0xAC, position)):
                        self.assertEqual(readfloats(u, NODE + at, 3), list(struct.unpack(
                            "<3f", struct.pack("<3f", *row))))
                    self.assertEqual(run_site_b(u), tp.FAKE)
                    # Live, the millisecond clock often ticks between cave A and the render.
                    u.mem_write(tp.GAME_TICK, struct.pack("<I", 50000 + dt + 1))
                    # The renderer looks along the turned forward from the culling eye,
                    # with the turned right, so the ship stays framed all the way round.
                    seen, direction, side, view = run_renderer_chase(u, right, forward, up, position)
                    self.assertEqual(direction, readfloats(u, tp.FAKE + 0x70, 3))
                    self.assertEqual(side, readfloats(u, tp.FAKE + 0x50, 3))
                    for got, want in zip(seen, readfloats(u, tp.FAKE + 0x80, 3)):
                        self.assertAlmostEqual(got, want, delta=abs(want) * 1e-6 + 1e-2)
                    self.assert_ship_framed(view, position)

    def test_orbit_view_is_left_alone_for_other_frames(self):
        u, calls = machine(self.prepared, toggled=False, orbit=True, tick=8000)
        right, up, forward, position = ship(u)
        run_site_a(u)
        u.mem_write(tp.GAME_TICK, struct.pack("<I", 8000 + 6000))
        run_site_a(u)
        stock = [list(struct.unpack("<3f", struct.pack("<3f", *v))) for v in (forward, right)]
        self.assertNotEqual(run_renderer_chase(u, right, forward, up, position)[1], stock[0])
        # A second render without cave A (a spectate frame, F7) keeps the stock view.
        self.assertEqual(list(run_renderer_chase(u, right, forward, up, position)[1:3]), stock)

    def test_releasing_f4_returns_to_f2(self):
        for chase in (False, True):
            with self.subTest(f2=chase):
                u, calls = machine(self.prepared, toggled=chase, orbit=True, tick=1000)
                ship(u)
                run_site_a(u)
                self.assertEqual(u.mem_read(tp.ORBIT, 1), b"\x01")
                u2, calls2 = machine(self.prepared, toggled=chase, orbit=False, tick=4000)
                ship(u2)
                u2.mem_write(tp.ORBIT, b"\x01")
                u2.mem_write(tp.START, struct.pack("<I", 1000))
                self.assertEqual(run_site_a(u2), tp.RESUME_A_SHOWN if chase else tp.RESUME_A)
                self.assertEqual(u2.mem_read(tp.ORBIT, 1), b"\x00")
                self.assertEqual(struct.unpack("<I", u2.mem_read(tp.START, 4))[0], 4000)
                self.assertEqual(u2.mem_read(tp.CHASE_FLAG, 1), bytes([chase]))
                if chase:                                    # back to the plain chase rows
                    self.assertEqual(readfloats(u2, tp.FAKE + 0x50, 12), readfloats(u2, NODE + 0x7C, 12))

    def test_default_key_map_leaves_plain_f4_free(self):
        # 0x4B8500(command, name, vk, modifiers) registers the default key map.
        # Plain F2 and F3 are taken (edi = 0 there); F4 appears only with modifiers.
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        bindings = {}
        for off in range(0x1000, 0x18C000):
            if self.raw[off] == 0xE8 and (off + 0x400005 + struct.unpack_from("<i", self.raw, off + 1)[0]) & 0xFFFFFFFF == 0x4B8500:
                pushes = [i.op_str for i in md.disasm(self.raw[off - 0x30:off], 0) if i.mnemonic == "push"][-4:]
                bindings[off + 0x400000] = pushes[::-1]                  # command, name, vk, modifiers
        self.assertEqual(bindings[0x44F464][2:], [hex(tp.VK_TOGGLE), "edi"])     # Toggle Mentor
        self.assertEqual(bindings[0x44F47C][2:], ["0x72", "edi"])                # Joystick Curve window
        f4 = [b[3] for b in bindings.values() if len(b) == 4 and b[2] == hex(tp.VK_ORBIT)]
        self.assertEqual(sorted(f4), ["0x10", "0x16", "1"])                     # cue grid; keymap save, recall (4)

    def test_culling_uses_the_offset_eye_only_for_this_frame(self):
        u, calls = machine(self.prepared, toggled=True, tick=5000)
        ship(u)
        run_site_a(u)
        self.assertEqual(run_site_b(u), tp.FAKE)
        fake = tp.FAKE
        self.assertEqual(readfloats(u, fake + 0x50, 12), readfloats(u, NODE + 0x7C, 12))
        self.assertEqual(readfloats(u, fake + 0xD0, 3), [5, 6, 7])
        # Another camera object (target windows, other nodes): untouched.
        other = 0x703000
        u.mem_write(other + 0x19C, struct.pack("<I", 0x704000))
        self.assertEqual(run_site_b(u, other), 0x704000 + 0x2C)
        # Null node: original arithmetic.
        u.mem_write(other + 0x19C, struct.pack("<I", 0))
        self.assertEqual(run_site_b(u, other), 0x2C)
        # A later tick without cave A (a spectate frame): original record.
        u.mem_write(tp.GAME_TICK, struct.pack("<I", 5016))
        self.assertEqual(run_site_b(u), NODE + 0x2C)

    def test_preparation_applies_and_undoes_exactly(self):
        on = self.prepared
        off = prepare_client.configure(self.raw, chase_camera=False)
        self.assertIn(tp.NAME, prepare_client.inspect(on)["patches"])
        self.assertNotIn(tp.NAME, prepare_client.inspect(off)["patches"])
        self.assertEqual(own_ship_menu.configure(own_ship_model.configure(tp.configure(on, False), False), False), off)
        self.assertEqual(prepare_client.configure(on), on)
        self.assertEqual(prepare_client.configure(off, chase_camera=True), on)
        allowed = {i for o, old, new in tp.regions() + own_ship_model.regions() + own_ship_menu.regions() for i in range(o, o + len(old))}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(on, off)) if a != b))
        for o, old, new in tp.regions():
            bad = bytearray(on)
            bad[o] ^= 0xFF
            with self.assertRaises(ValueError):
                tp.state(bytes(bad))
            partial = bytearray(on)
            partial[o:o + len(old)] = old
            with self.assertRaises(ValueError):
                tp.state(bytes(partial))
        # A client prepared with the v1 cave (chase only, patch versions 15-19) upgrades in place.
        v1 = bytearray(tp.configure(on, False))
        for o, old, new in tp.regions(legacy=True):
            v1[o:o + len(old)] = new
        v1 = bytes(v1)
        self.assertIs(tp.state(v1), True)
        self.assertIn(tp.NAME, prepare_client.inspect(v1)["patches"])
        self.assertEqual(prepare_client.configure(v1), on)
        self.assertEqual(tp.configure(v1, False), tp.configure(on, False))
        self.assertEqual(on[tp.SITE_R - 0x400000:][:len(tp.ORIGINAL_R)][:1], b"\xe9")
        self.assertEqual(v1[tp.SITE_R - 0x400000:][:len(tp.ORIGINAL_R)], tp.ORIGINAL_R)
        # Coexists with every optional rendering patch.
        for options in ({"experimental_asteroids": True}, {"experimental_solids": True},
                        {"experimental_station_detail": True}, {"experimental_world_detail": True},
                        {"experimental_texture32": True}):
            with self.subTest(options=options):
                self.assertIn(tp.NAME, prepare_client.inspect(prepare_client.configure(self.raw, **options))["patches"])

    def test_state_lives_in_unreferenced_data_tail(self):
        # 0x60D200/0x60D204 are the logger lock words; nothing else is past the original .data.
        self.assertGreater(tp.FAKE, 0x60D208)
        self.assertLessEqual(tp.ARMED + 4, 0x60E000)
        self.assertGreater(tp.ORBIT, own_ship_menu.RESTRICT)
        packed = [struct.pack("<I", v) for v in range(tp.FAKE, tp.ARMED + 4, 4)]
        image = prepare_client.configure(self.raw, chase_camera=False)
        self.assertFalse(any(p in image for p in packed))


class OwnShipModelTests(unittest.TestCase):
    """0x44C0A0(object, is_self) run in Unicorn; 0x43DF70 (attach meshes) stubbed."""
    ATTACH = 0x43DF70

    @classmethod
    def setUpClass(cls):
        cls.raw = ORIGINAL.read_bytes()
        cls.prepared = prepare_client.configure(cls.raw)

    def attaches(self, image, is_self, graphics_active=True):
        u = Uc(UC_ARCH_X86, UC_MODE_32)
        u.mem_map(0x400000, 0x20F000)
        u.mem_map(0x6F0000, 0x40000)
        u.mem_write(0x401000, image[0x1000:0x1C1000])
        app, obj, gfx, ret = 0x700000, 0x701000, 0x702000, 0x6F0F00
        u.mem_write(app + 0x134, struct.pack("<I", gfx))
        u.mem_write(gfx + 0x24C5, bytes([graphics_active]))
        u.mem_write(obj + 0x19C, struct.pack("<I", NODE))
        u.mem_write(obj + 0x194, struct.pack("<I", 0x704000))
        calls = []

        def stub(uc, address, size, _):
            esp = uc.reg_read(UC_X86_REG_ESP)
            back, definition, node = struct.unpack("<III", uc.mem_read(esp, 12))
            calls.append((uc.reg_read(UC_X86_REG_ECX), definition, node))
            uc.reg_write(UC_X86_REG_ESP, esp + 12)
            uc.reg_write(UC_X86_REG_EIP, back)
        u.hook_add(UC_HOOK_CODE, stub, begin=self.ATTACH, end=self.ATTACH)
        sp = STACK - 0x100
        u.mem_write(sp, struct.pack("<III", ret, obj, is_self))
        u.reg_write(UC_X86_REG_ESP, sp)
        u.reg_write(UC_X86_REG_ECX, app)
        u.reg_write(UC_X86_REG_EBX, 0xB0B0)
        u.emu_start(0x44C0A0, ret, count=100)
        self.assertEqual(u.reg_read(UC_X86_REG_ESP), sp + 12)
        self.assertEqual(u.reg_read(UC_X86_REG_EBX), 0xB0B0)
        return calls

    def test_original_skips_own_ship(self):
        off = own_ship_model.configure(self.prepared, False)
        self.assertEqual(self.attaches(off, 0), [(0x702000, 0x704000, NODE)])
        self.assertEqual(self.attaches(off, 1), [])

    def test_patched_attaches_own_ship_too(self):
        self.assertEqual(self.attaches(self.prepared, 1), [(0x702000, 0x704000, NODE)])
        self.assertEqual(self.attaches(self.prepared, 0), [(0x702000, 0x704000, NODE)])
        self.assertEqual(self.attaches(self.prepared, 1, graphics_active=False), [])

    def test_follows_the_third_person_option(self):
        off = prepare_client.configure(self.raw, chase_camera=False)
        self.assertIn(own_ship_model.NAME, prepare_client.inspect(self.prepared)["patches"])
        self.assertNotIn(own_ship_model.NAME, prepare_client.inspect(off)["patches"])
        self.assertEqual(own_ship_menu.configure(own_ship_model.configure(tp.configure(self.prepared, False), False), False), off)
        # A client prepared at patch version 15 (camera, no model) upgrades in place.
        v15 = own_ship_menu.configure(own_ship_model.configure(self.prepared, False), False)
        self.assertEqual(prepare_client.configure(v15), self.prepared)
        for o, old, new in own_ship_model.regions():
            bad = bytearray(self.prepared)
            bad[o] ^= 0xFF
            with self.assertRaises(ValueError):
                prepare_client.inspect(bytes(bad))
            partial = bytearray(self.prepared)
            partial[o:o + len(old)] = old
            with self.assertRaises(ValueError):
                own_ship_model.state(bytes(partial))

    def test_own_children_stay_visible_only_with_chase_on(self):
        # The store at 0x48FAE5 that ends 0x48F730's pass over your ship's children.
        for image, flag, want in ((self.prepared, 0, 0), (self.prepared, 1, 1),
                                  (own_ship_model.configure(self.prepared, False), 1, 0)):
            with self.subTest(patched=image is self.prepared, flag=flag):
                u = Uc(UC_ARCH_X86, UC_MODE_32)
                u.mem_map(0x400000, 0x20F000)
                u.mem_map(0x6F0000, 0x40000)
                u.mem_write(0x401000, image[0x1000:0x1C1000])
                u.mem_write(tp.CHASE_FLAG, bytes([flag]))
                child = 0x700000
                u.mem_write(child + 0x151, b"")
                u.reg_write(UC_X86_REG_ECX, child)
                u.reg_write(UC_X86_REG_EAX, 0x5151)
                u.reg_write(UC_X86_REG_ESP, STACK - 0x100)
                u.emu_start(own_ship_model.CHILD_SITE, own_ship_model.CHILD_RESUME, count=10)
                self.assertEqual(u.mem_read(child + 0x151, 1)[0], want)
                self.assertEqual(u.reg_read(UC_X86_REG_EAX), 0x5151)
                self.assertEqual(u.reg_read(UC_X86_REG_ESP), STACK - 0x100)


class OwnShipMenuTests(unittest.TestCase):
    """The main mesh pass (0x56ECC0) after the fighter menu cleared a part's +0x244."""

    @classmethod
    def setUpClass(cls):
        cls.raw = ORIGINAL.read_bytes()
        cls.prepared = prepare_client.configure(cls.raw)

    def machine(self, image, chase):
        u = Uc(UC_ARCH_X86, UC_MODE_32)
        u.mem_map(0x400000, 0x20F000)
        u.mem_map(0x6F0000, 0x100000)                 # scratch through world + 0xD3448
        u.mem_write(0x401000, image[0x1000:0x1C1000])
        u.mem_write(tp.CHASE_FLAG, bytes([chase]))
        world, top = 0x701000, 0x702000
        u.mem_write(own_ship_menu.WORLD, struct.pack("<I", world))
        u.mem_write(world + own_ship_menu.PLAYER_NODE, struct.pack("<I", top))
        return u, top

    def part_walked(self, image, flag, chase):
        """Run the part check; True if 0x56ECC0 goes on to the part's instances."""
        u, _ = self.machine(image, chase)
        part = 0x703000
        u.mem_write(part + 0x244, bytes([flag]))
        u.reg_write(UC_X86_REG_EDI, part)
        u.reg_write(UC_X86_REG_ESP, STACK - 0x100)
        u.emu_start(own_ship_menu.PART_SITE, own_ship_menu.PART_RESUME, count=20)
        return bool(u.reg_read(UC_X86_REG_EAX) & 0xFF), u

    def instance_drawn(self, image, part_flag, chase, own, drawable=True):
        walked, u = self.part_walked(image, part_flag, chase)
        _, top = 0, 0x702000
        instance = 0x704000
        u.mem_write(instance + 0x150, bytes([1, 1, 1]) if drawable else bytes([1, 0, 1]))
        u.mem_write(instance + 0x144, struct.pack("<I", top if own else 0x705000))
        u.reg_write(UC_X86_REG_ESI, instance)
        u.reg_write(UC_X86_REG_ECX, instance)
        u.reg_write(UC_X86_REG_ESP, STACK - 0x100)
        u.emu_start(own_ship_menu.INSTANCE_SITE, own_ship_menu.INSTANCE_SITE + 5, count=60)
        assert u.reg_read(UC_X86_REG_ESP) == STACK - 0x100
        assert u.reg_read(UC_X86_REG_ESI) == instance
        self.transform_flag = u.mem_read(0x703000 + 0x245, 1)[0]   # the part's +0x245
        return walked and bool(u.reg_read(UC_X86_REG_EAX) & 0xFF)

    def test_original_skips_parts_the_menu_cleared(self):
        off = own_ship_menu.configure(self.prepared, False)
        self.assertFalse(self.part_walked(off, 0, 1)[0])
        self.assertTrue(self.part_walked(off, 1, 0)[0])

    def test_cleared_parts_draw_only_your_ship_with_chase_on(self):
        on = self.prepared
        self.assertTrue(self.instance_drawn(on, 0, chase=1, own=True))
        self.assertEqual(self.transform_flag, 1)                             # sets its own transform
        self.assertFalse(self.instance_drawn(on, 0, chase=1, own=False))     # the menu's preview
        self.assertEqual(self.transform_flag, 0)
        self.assertFalse(self.instance_drawn(on, 0, chase=0, own=True))      # cockpit view: part skipped
        self.assertFalse(self.instance_drawn(on, 0, chase=1, own=True, drawable=False))

    def test_untouched_parts_unchanged(self):
        for chase in (0, 1):
            for own in (True, False):
                with self.subTest(chase=chase, own=own):
                    self.assertTrue(self.instance_drawn(self.prepared, 1, chase, own))
                    self.assertFalse(self.instance_drawn(self.prepared, 1, chase, own, drawable=False))

    def test_prepare_applies_upgrades_and_rejects_partial(self):
        self.assertIn(own_ship_menu.NAME, prepare_client.inspect(self.prepared)["patches"])
        v16 = own_ship_menu.configure(self.prepared, False)
        self.assertEqual(prepare_client.configure(v16), self.prepared)
        # A client prepared with the first cave (no +0x245 restore) upgrades in place.
        first = bytearray(v16)
        for o, old, new in own_ship_menu.regions(legacy=True):
            first[o:o + len(old)] = new
        self.assertIs(own_ship_menu.state(bytes(first)), True)
        self.assertIn(own_ship_menu.NAME, prepare_client.inspect(bytes(first))["patches"])
        self.assertEqual(prepare_client.configure(bytes(first)), self.prepared)
        self.assertEqual(own_ship_menu.configure(bytes(first), False), v16)
        for o, old, new in own_ship_menu.regions():
            partial = bytearray(self.prepared)
            partial[o:o + len(old)] = old
            with self.assertRaises(ValueError):
                own_ship_menu.state(bytes(partial))


if __name__ == "__main__":
    unittest.main()
