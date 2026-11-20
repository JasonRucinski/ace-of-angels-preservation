"""The offline culling experiment's bytes, as aoa.emulation.render_pipeline's default patch.

The experiment itself (configure, its command line, its tests) is archived in
archive/offline_baseline/render_culling_experiment.py; visibility-math-v1
superseded it. This module keeps only code() and regions(), because
render_pipeline.run(corrected=True) emulates them when no patch is given.
Nothing else imports it; it can go once render_pipeline takes its patch
explicitly.
"""
import struct

from aoa.client.asm import Asm

CAVE = 0x58B700
ANGLE = 0x58B800


def code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex('d99668010000'))  # displaced fst [esi+168]; ST0=distance
    a.emit(bytes.fromhex('d9e4dfe0f6c440'))  # ftst; fnstsw ax; test ah,40
    a.rel8(0x75, 'center')
    a.rel32(0xE9, 0x54307D)
    a.label('center')
    a.emit(bytes.fromhex('ddd8'))  # discard zero distance before bypassing normalization
    # Direction at the exact origin is undefined; use camera forward, finite
    # and consistent with the coincident-point convention used for the bound.
    for source, target in ((0x70,0x158),(0x74,0x15C),(0x78,0x160)):
        a.emit(b'\x8b\x42', bytes([source]), b'\x89\x86', struct.pack('<I',target))
    a.emit(bytes.fromhex('8b866401000089866c010000'))  # surface distance = radius
    for offset, value in ((0x170,0x3F800000),(0x174,0x3F800000),(0x178,0),(0x17C,0x457A0000)):
        a.emit(b'\xc7\x86',struct.pack('<II',offset,value))
    a.emit(bytes.fromhex('c6865301000001b801000000'))
    a.rel32(0xE9,0x543238)  # set distance-visible and run original LOD/enabled gates
    assert a.here() <= ANGLE
    a.emit(bytes(ANGLE-a.here()))
    a.emit(bytes.fromhex('d98668010000d89e64010000dfe0f6c441')) # distance <= radius?
    a.rel8(0x75,'inside')
    a.emit(bytes.fromhex('d98674010000d9e8d8d9dfe0f6c401')) # +1 vs dot
    a.rel8(0x74,'lower')
    a.emit(bytes.fromhex('ddd8d9e8'))  # replace >1 with +1
    a.label('lower')
    # Compare with -1 held on the stack, avoiding a new global constant.
    a.emit(bytes.fromhex('d9e8d9e0d8d9dfe0f6c401')) # fcomp st1: -1 vs dot
    a.rel8(0x75,'acos')  # -1 < dot, including all ordinary inputs
    a.emit(bytes.fromhex('ddd8d9e8d9e0'))
    a.label('acos')
    a.rel32(0xE9,0x5431A7)  # original _CIacos call consumes bounded ST0
    a.label('inside')
    a.emit(bytes.fromhex('c786700100000000803fc6865301000001b801000000'))
    a.rel32(0xE9,0x543238)
    return a.resolve()


def regions():
    body = code()
    result = [(CAVE-0x400000, bytes(len(body)), body)]
    for address, target, old in ((0x543077,CAVE,'d99668010000'),(0x5431A1,ANGLE,'d98674010000')):
        result.append((address-0x400000,bytes.fromhex(old),b'\xe9'+struct.pack('<i',target-address-5)+b'\x90'))
    return result
