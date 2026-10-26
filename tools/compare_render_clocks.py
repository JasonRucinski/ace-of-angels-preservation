"""Replay measured Windows clocks through the original 2.9.2 camera builder.

No client launch, UI automation or networking. This isolates clock quantization
and camera math; it does not exercise scene traversal, LOD or GPU presentation.
Usage: python -I tools/compare_render_clocks.py OUTPUT.json
"""
import ctypes
import hashlib
import json
import math
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emulate_codec import Emu, SCRATCH, STOP, STUBS
from pe_util import PE
import render_clock_experiment as clock
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_FPCW, UC_X86_REG_EIP, UC_X86_REG_ESP, UC_X86_REG_EAX


def view(emu, eye, yaw):
    forward = (math.sin(yaw), 0, math.cos(yaw))
    right = (math.cos(yaw), 0, -math.sin(yaw))
    for address, value in ((SCRATCH + 0x100, eye), (SCRATCH + 0x110, forward), (SCRATCH + 0x120, right)):
        emu.write(address, struct.pack('<3f', *value))
    # Original cdecl BuildView(out, eye, forward, right, roll).
    emu.thiscall(0x569880, 0, SCRATCH, SCRATCH + 0x100, SCRATCH + 0x110, SCRATCH + 0x120, 0)
    assert emu.uc.reg_read(UC_X86_REG_EIP) == STOP
    return struct.unpack('<16f', emu.read(SCRATCH, 64))


def project(matrix, point):
    xyz = [sum(point[i] * matrix[4*i+j] for i in range(3)) + matrix[12+j] for j in range(3)]
    assert xyz[2] > 0
    return 960 * xyz[0] / xyz[2], 960 * xyz[1] / xyz[2]


def main():
    root = Path(__file__).resolve().parents[1]
    pe = PE(root / 'game/2.9.2/AOACLIENT.EXE.orig')
    assert hashlib.sha256(pe.data).hexdigest() == '4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e'
    emu = Emu(pe)
    emu.uc.reg_write(UC_X86_REG_FPCW, 0x7F)  # Direct3D single precision
    k = ctypes.WinDLL('kernel32')
    k.GetTickCount.restype = ctypes.c_uint32
    k.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_int64)]
    k.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_int64)]
    frequency, counter = ctypes.c_int64(), ctypes.c_int64()
    assert k.QueryPerformanceFrequency(ctypes.byref(frequency))
    # Execute the actual patch conversion, including its precision save/restore,
    # against measured counter values; no Python substitute for patched time.
    counter_input = [0]
    emu.write(clock.CAVE, clock.code())
    for iat, stub in ((0x58C060, STUBS + 0x200), (0x58C05C, STUBS + 0x210)):
        emu.write(iat, struct.pack('<I', stub))
        emu.write(stub, bytes.fromhex('c20400'))
    def counter_api(uc, address, size, data):
        if address in (STUBS + 0x200, STUBS + 0x210):
            sp = uc.reg_read(UC_X86_REG_ESP)
            pointer = struct.unpack('<I', emu.read(sp + 4, 4))[0]
            emu.write(pointer, struct.pack('<q', frequency.value if address == STUBS + 0x200 else counter_input[0]))
            uc.reg_write(UC_X86_REG_EAX, 1)
    emu.uc.hook_add(UC_HOOK_CODE, counter_api, begin=STUBS + 0x200, end=STUBS + 0x210)
    cases = []
    for fps in (60, 144):
        samples = []
        start = time.perf_counter()
        for frame in range(fps * 2):
            time.sleep(max(0, start + frame / fps - time.perf_counter()))
            assert k.QueryPerformanceCounter(ctypes.byref(counter))
            original_tick = k.GetTickCount()
            counter_input[0] = counter.value
            patched_tick = emu.thiscall(clock.CAVE, 0)
            assert patched_tick == round(counter.value * 1000 / frequency.value) & 0xFFFFFFFF
            samples.append((counter.value / frequency.value, original_tick, patched_tick))
        for path in ('translation', 'turn', 'combined'):
            traces = {}
            for mode, column in (('original', 1), ('qpc_ms', 2), ('ideal', 0)):
                coords = []
                for sample in samples:
                    elapsed = (sample[column] - samples[0][column]) / (1 if column == 0 else 1000)
                    eye = (500*elapsed if path != 'turn' else 0, 0, 0)
                    yaw = 0.2*elapsed if path != 'translation' else 0
                    coords.append(project(view(emu, eye, yaw), (0, 0, 5000)))
                traces[mode] = coords
            result = {'fps': fps, 'path': path}
            for mode in ('original', 'qpc_ms'):
                errors = [math.dist(a, b) for a, b in zip(traces[mode], traces['ideal'])]
                step_errors = [abs((b[0]-a[0])-(d[0]-c[0])) for a,b,c,d in zip(traces[mode],traces[mode][1:],traces['ideal'],traces['ideal'][1:])]
                result[mode] = {'max_pixel_error': max(errors), 'rms_step_error_pixels': math.sqrt(sum(e*e for e in step_errors)/len(step_errors)),
                                'repeated_clock_samples': sum(b[i] == a[i] for a,b in zip(samples,samples[1:]) for i in [1 if mode == 'original' else 2])}
            cases.append(result)
    # Test camera cancellation while moving and turning at representative world coordinates.
    precision = []
    for distance in (0, 10000, 100000, 1000000):
        errors = []
        for frame in range(120):
            yaw = frame / 120
            eye = (distance + frame*3, distance/2, distance)
            m = view(emu, eye, yaw)
            errors.append(math.sqrt(sum((sum(eye[i]*m[4*i+j] for i in range(3))+m[12+j])**2 for j in range(3))))
        precision.append({'world_offset': distance, 'max_camera_origin_error_units': max(errors)})
    result = {'scope': __doc__.split('Usage:')[0].strip(), 'clock_replays': cases, 'camera_precision': precision}
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
