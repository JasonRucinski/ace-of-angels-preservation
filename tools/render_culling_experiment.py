"""Reversible culling correction restricted to the isolated offline baseline."""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm
import prepare_client
import render_clock_experiment as clock

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


def configure(data, enabled=True):
    original = bytearray(data)
    states = []
    for offset, old, new in regions():
        actual = data[offset:offset+len(old)]
        if actual not in (old,new):
            raise ValueError('unexpected culling code or cave')
        states.append(actual == new)
        original[offset:offset+len(old)] = old
    if len(set(states)) != 1:
        raise ValueError('partial culling patch')
    # Clock normalization verifies the complete known image, while preserving
    # whether the caller currently has the clock experiment enabled.
    clock.configure(bytes(original),False)
    result = bytearray(original)
    if enabled:
        for offset, old, new in regions():
            result[offset:offset+len(old)] = new
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--undo',action='store_true')
    args = parser.parse_args()
    exe = Path(__file__).resolve().parents[1]/'game/offline-baseline-2.9.2/AOACLIENT.EXE'
    source = exe.read_bytes()
    original = configure(source,False)
    backup = exe.with_suffix('.EXE.before-culling')
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError('culling backup does not match normalized image')
    if not backup.exists():
        prepare_client.atomic_write(backup,original)
    result = configure(source,not args.undo)
    if result != source:
        prepare_client.atomic_write(exe,result)
    if exe.read_bytes() != result:
        raise ValueError('culling patch verification failed')
    record = {'enabled':not args.undo,'sha256':prepare_client.sha(result),
              'undo_sha256':prepare_client.sha(original),'scope':'isolated offline baseline; full-frame validation pending'}
    prepare_client.atomic_write(exe.parent/'_render_culling.json',(json.dumps(record,indent=2)+'\n').encode())
    print(json.dumps(record,indent=2))


if __name__ == '__main__':
    main()
