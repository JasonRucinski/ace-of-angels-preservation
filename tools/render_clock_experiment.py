"""Offline-only QPC clock experiment. Not part of supported client preparation.

Changes the two game-clock sources together, retaining unsigned millisecond
timestamps. QPC has its own epoch: apply before launch, never to a live process.
Logger timestamps and random seeding retain GetTickCount. No physics changes.
"""
import struct
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm
import prepare_client

CAVE = 0x58B600


def code():
    a = Asm(CAVE)
    a.emit(bytes.fromhex("515283ec188d44240850ff1560c0580085c0"))
    a.rel8(0x74, "fallback")
    a.emit(bytes.fromhex("8d042450ff155cc0580085c0"))
    a.rel8(0x74, "fallback")
    # round(QPC * 1000 / frequency) to a 64-bit integer; return low DWORD.
    # Direct3D sets single precision: save/restore CW and use extended precision
    # locally, otherwise an uptime-sized counter loses many milliseconds.
    a.emit(bytes.fromhex("d97c241466c74424167f03d96c2416"))
    a.emit(bytes.fromhex("c7442410e8030000df2c24da4c2410df6c2408def9df3c24d96c24148b042483c4185a59c3"))
    a.label("fallback")
    a.emit(bytes.fromhex("83c4185a59ff25a4c05800"))
    return a.resolve()


def regions():
    body = code()
    return [(CAVE - 0x400000, bytes(len(body)), body),
            (0x1296C4, bytes.fromhex("8b3da4c05800"), b"\xbf" + struct.pack("<I", CAVE) + b"\x90"),
            (0x129700, bytes.fromhex("ff15a4c05800"), b"\xe8" + struct.pack("<i", CAVE - 0x529705) + b"\x90")]


def configure(data, enabled=True):
    states = []
    original = bytearray(data)
    for off, old, new in regions():
        actual = data[off:off + len(old)]
        if actual not in (old, new):
            raise ValueError("unexpected clock code or cave")
        states.append(actual == new)
        original[off:off + len(old)] = old
    if len(set(states)) != 1:
        raise ValueError("partial clock experiment")
    prepare_client.inspect(bytes(original))
    out = bytearray(original)
    if enabled:
        for off, old, new in regions():
            out[off:off + len(old)] = new
    return bytes(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--undo', action='store_true')
    args = parser.parse_args()
    # Intentionally no arbitrary executable argument: this remains an offline
    # rendering experiment, not an unvalidated upgrade to networked clients.
    exe = Path(__file__).resolve().parents[1] / 'game/offline-baseline-2.9.2/AOACLIENT.EXE'
    source = exe.read_bytes()
    original = configure(source, False)
    backup = exe.with_suffix('.EXE.before-clock')
    if backup.exists() and backup.read_bytes() != original:
        raise ValueError('clock undo backup does not match normalized executable')
    if not backup.exists():
        prepare_client.atomic_write(backup, original)
    result = configure(source, not args.undo)
    if result != source:
        prepare_client.atomic_write(exe, result)
    if exe.read_bytes() != result:
        raise ValueError('clock patch verification failed')
    record = {'clock': 'GetTickCount' if args.undo else 'QPC milliseconds, extended precision conversion',
              'sha256': prepare_client.sha(result), 'undo_sha256': prepare_client.sha(original),
              'scope': 'isolated offline baseline; multiplayer unverified'}
    prepare_client.atomic_write(exe.parent / '_render_clock.json', (json.dumps(record, indent=2)+'\n').encode())
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
