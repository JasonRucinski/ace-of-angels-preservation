"""Headless original-client warp checks with explicit service substitutes.

Runs the entire LoadObject receiver and the original overlap/teleport code.
Allocation, scene registration, team services and two CRT calls are fixture
substitutes; no renderer, Windows UI, model loading or live game is simulated.
"""
import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, HEAP, STACK, SCRATCH, STUBS, STOP
from patch_client import PRISTINE_292
from pe_util import PE
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX,
                               UC_X86_REG_EDI, UC_X86_REG_ESI,
                               UC_X86_REG_EIP, UC_X86_REG_ESP)


class NativeWarp:
    WORLD = HEAP + 0x100000
    CONTROL = HEAP + 0x200000
    SHIP = WORLD + 0xd32ac
    SHIP_GFX = HEAP + 0x210000
    GATE_GFX = HEAP + 0x211000
    LOWER, SPRINTF, QUEUE = STUBS + 0x200, STUBS + 0x210, STUBS + 0x220
    SERVICES = {0x4a5960: 'world slot allocation', 0x4e0660: 'AI cleanup',
                0x4bda80: 'scene registration', 0x4c8b10: 'team lookup',
                0x4ad4b0: 'team creation', 0x4a7f90: 'model loading',
                LOWER: 'CRT lowercase', SPRINTF: 'CRT sprintf', QUEUE: 'event queue availability'}

    def __init__(self, client):
        if hashlib.sha256(client.read_bytes()).hexdigest() != PRISTINE_292:
            raise ValueError('requires original 2.9.2 executable')
        self.emu = Emu(PE(client))
        self.emu.uc.mem_map(0, 0x1000)  # SEH chain storage; no OS execution.
        self.emu.write(0x5e7728, struct.pack('<I', self.WORLD))
        self.emu.write(0x58c340, struct.pack('<I', self.LOWER))
        self.emu.write(0x58c3b8, struct.pack('<I', self.SPRINTF))
        self.emu.write(self.WORLD, struct.pack('<I', HEAP + 0x220000))
        self.emu.write(HEAP + 0x220014, struct.pack('<I', self.QUEUE))
        self.emu.write(self.WORLD + 0x3c, struct.pack('<I', 1))
        self.allocations = 0
        self.registrations = 0
        self.model_requests = 0
        self.called = set()
        self.gate = None
        self.stops = set()
        self.emu.uc.hook_add(UC_HOOK_CODE, self._hook)

    def _return(self, popped=0, value=0):
        uc = self.emu.uc
        sp = uc.reg_read(UC_X86_REG_ESP)
        target = struct.unpack('<I', self.emu.read(sp, 4))[0]
        uc.reg_write(UC_X86_REG_EAX, value)
        uc.reg_write(UC_X86_REG_ESP, sp + 4 + popped)
        uc.reg_write(UC_X86_REG_EIP, target)

    def _hook(self, uc, address, size, _):
        if address in self.stops:
            uc.emu_stop()
            return
        if address not in self.SERVICES:
            return
        self.called.add(self.SERVICES[address])
        sp = uc.reg_read(UC_X86_REG_ESP)
        if address == 0x4a5960:
            kind, slot, tag = struct.unpack('<3I', self.emu.read(sp + 4, 12))
            assert kind == 0 and slot == 0xffffffff and tag >> 16 == 0x4001
            index = tag & 0xffff
            assert index < 1000
            self.gate = self.WORLD + 0x4c + index * 0x360
            self.emu.write(self.gate, bytes(0x360))
            self.emu.write(self.gate + 0x178, struct.pack('<I', tag))
            self.emu.write(self.gate + 0x243, b'\1')
            self.emu.write(self.WORLD + 0xdef5a, struct.pack('<H', index + 1))
            self.allocations += 1
            self._return(12, self.gate)
        elif address == 0x4bda80:
            action, obj = struct.unpack('<2I', self.emu.read(sp + 4, 8))
            assert action == 6 and obj == self.gate
            self.registrations += 1
            self._return(8)
        elif address == 0x4a7f90:
            obj, model, database = struct.unpack('<3I', self.emu.read(sp + 4, 12))
            assert obj == self.gate
            assert self.emu.read(model, 32).split(b'\0')[0] == b'WarpGate'
            assert self.emu.read(database, 32).split(b'\0')[0] == b'AoAObjects.odb'
            self.model_requests += 1
            self._return(12, 1)
        elif address == self.LOWER:
            value = struct.unpack('<I', self.emu.read(sp + 4, 4))[0]
            self._return(value=value + 32 if 65 <= value <= 90 else value)
        elif address == self.SPRINTF:
            out, fmt, number = struct.unpack('<3I', self.emu.read(sp + 4, 12))
            assert self.emu.pe.cstr(fmt) == '%d'
            raw = str(number).encode('ascii')
            self.emu.write(out, raw + b'\0')
            self._return(value=len(raw))
        elif address in (0x4e0660, 0x4c8b10):
            self._return(4)
        elif address == 0x4ad4b0:
            self._return(12)
        elif address == self.QUEUE:
            self._return()

    def load(self, packet):
        if len(packet) != 191:
            raise ValueError('expected a LoadObject body')
        self.stops.clear()
        self.emu.write(SCRATCH, packet)
        result = self.emu.thiscall(0x4a66a0, self.WORLD, SCRATCH)
        assert self.emu.uc.reg_read(UC_X86_REG_EIP) == STOP
        assert result == self.gate
        return self.fields()

    def fields(self):
        p = self.emu.read(self.gate, 0x360)
        return {'tag': struct.unpack_from('<I', p, 0x178)[0],
                'name': p[0x244:0x284].split(b'\0')[0].decode('ascii'),
                'position': struct.unpack_from('<3f', p, 0x30),
                'destination': struct.unpack_from('<3f', p, 0x70),
                'kind': struct.unpack_from('<I', p, 0x1f8)[0],
                'collidable': bool(p[0x2fb]), 'active': bool(p[0x243])}

    def overlap(self, ship_position, velocity, *, local=True, busy=False,
                visible=True, collidable=True, ship_radius=10., gate_radius=100.):
        """Run the native sphere-overlap branch, local guards and teleport.

        Render positions/radii are fixture inputs, not recovered model bounds.
        Stop immediately after teleport, before sound/network side effects.
        """
        assert self.gate is not None
        self.emu.write(self.SHIP + 0x30, struct.pack('<3f', *ship_position))
        self.emu.write(self.SHIP + 0x54, struct.pack('<3f', *velocity))
        self.emu.write(self.SHIP_GFX + 0xac, struct.pack('<3f', *ship_position))
        self.emu.write(self.SHIP_GFX + 0x164, struct.pack('<f', ship_radius))
        self.emu.write(self.GATE_GFX + 0xac, self.emu.read(self.gate + 0x30, 12))
        self.emu.write(self.GATE_GFX + 0x164, struct.pack('<f', gate_radius))
        self.emu.write(self.gate + 0x2f7, bytes([visible]))
        self.emu.write(self.gate + 0x2fb, bytes([collidable]))
        self.emu.write(self.CONTROL + 0x20, bytes([busy]))
        sp = STACK + 0xe0000
        self.emu.write(sp, bytes(0x200))
        self.emu.write(sp + 0x13, bytes([local]))
        self.emu.write(sp + 0x18, struct.pack('<I', self.SHIP_GFX))
        for reg, value in ((UC_X86_REG_ESP, sp), (UC_X86_REG_EBX, self.CONTROL),
                           (UC_X86_REG_EBP, self.SHIP), (UC_X86_REG_EDI, self.gate),
                           (UC_X86_REG_ESI, self.GATE_GFX)):
            self.emu.uc.reg_write(reg, value)
        self.stops = {0x4b34d2, 0x4b5110}
        self.emu.uc.emu_start(0x4b3013, STOP, count=2000)
        end = self.emu.uc.reg_read(UC_X86_REG_EIP)
        assert end in self.stops
        position = struct.unpack('<3f', self.emu.read(self.SHIP + 0x30, 12))
        assert self.emu.read(self.SHIP + 0x54, 12) == struct.pack('<3f', *velocity)
        return {'warped': end == 0x4b5110, 'position': position, 'velocity': tuple(velocity)}
