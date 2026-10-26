"""Millisecond game clock from QueryPerformanceCounter, plus a timer-frame gate.

The 2.9.2 game clock (0x5E8E5C) comes from GetTickCount at 0x5296C4 and
0x529700, which advances in ~15.6 ms steps. Frames are issued every 16 ms
(main loop 0x407F50), so each frame's game-time step is 15, 16 or 31 ms and
moving scenery judders (offline-rendering-baseline.md). The clock cave returns
round(QPC * 1000 / frequency) as an unsigned millisecond count, computed with
the x87 control word temporarily at extended precision (Direct3D leaves it at
single precision). It falls back to GetTickCount if QPC fails. Only the game
clock changes: the logger and srand keep GetTickCount (the five call sites
are 0x526D7B/0x526DD6 logger, the two above, and 0x56A229 srand).

Gate: the wakeup timer (callback 0x446E70, ~66 ms, ref-counted by
0x452930/0x4529C0) also runs the frame function 0x44AD60; with
background-network-v1 it does so even in exclusive mode (findings 9.24). The
frame function skips a frame whose clock step (+0x34) is zero. With the coarse
clock that hid timer frames issued just after a main-loop frame; with a
millisecond clock they render and split the 16 ms cadence. The gate lets a
timer frame run only when no frame has run for GATE_MS (last frame clock at
app +0x30), so the timer still drives a background window.

Library use only (prepare_client.py composes it); no file is written here.
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_client import Asm  # noqa: E402

NAME = "frame-clock-v1"
CLOCK = 0x58B600
GATE = 0x58B680
GATE_MS = 50
FRAME = 0x44AD60            # app frame function (ecx = app)
TIMER_CALL = 0x446EB1       # call FRAME inside the wakeup-timer callback
GET_TICK_COUNT, QPC, QPF = 0x58C0A4, 0x58C05C, 0x58C060


def clock_code():
    a = Asm(CLOCK)
    a.emit(bytes.fromhex("515283ec18"))            # push ecx; push edx; sub esp,18
    a.emit(bytes.fromhex("8d442408"), b"\x50", b"\xff\x15", struct.pack("<I", QPF))
    a.emit(bytes.fromhex("85c0"))
    a.rel8(0x74, "fallback")
    a.emit(bytes.fromhex("8d0424"), b"\x50", b"\xff\x15", struct.pack("<I", QPC))
    a.emit(bytes.fromhex("85c0"))
    a.rel8(0x74, "fallback")
    # round(QPC * 1000 / frequency) to a 64-bit integer; return low DWORD.
    a.emit(bytes.fromhex("d97c241466c74424167f03d96c2416"))  # save CW; CW = 0x37F
    a.emit(bytes.fromhex("c7442410e8030000df2c24da4c2410df6c2408def9df3c24d96c24148b042483c4185a59c3"))
    a.label("fallback")
    a.emit(bytes.fromhex("83c4185a59"), b"\xff\x25", struct.pack("<I", GET_TICK_COUNT))
    return a.resolve()


def gate_code():
    a = Asm(GATE)
    a.emit(0x51)                          # push ecx (app; the clock fallback may clobber it)
    a.rel32(0xE8, CLOCK)                  # eax = now (ms)
    a.emit(0x59)                          # pop ecx
    a.emit(bytes.fromhex("2b4130"))       # sub eax, [ecx+30]  ; since last frame's clock
    a.emit(bytes.fromhex("83f8"), GATE_MS)  # cmp eax, GATE_MS
    a.rel8(0x72, "skip")                  # jb skip (unsigned)
    a.rel32(0xE9, FRAME)                  # tail call: frame returns to the timer callback
    a.label("skip")
    a.emit(bytes.fromhex("31c0c3"))       # xor eax, eax; ret
    return a.resolve()


def call(site, target):
    return b"\xe8" + struct.pack("<i", target - site - 5)


def regions():
    """(file offset, original bytes, patched bytes); image base 0x400000."""
    clock, gate = clock_code(), gate_code()
    assert CLOCK + len(clock) <= GATE and GATE + len(gate) <= 0x58B700
    return [(CLOCK - 0x400000, bytes(len(clock)), clock),
            (GATE - 0x400000, bytes(len(gate)), gate),
            (0x1296C4, bytes.fromhex("8b3d") + struct.pack("<I", GET_TICK_COUNT),
             b"\xbf" + struct.pack("<I", CLOCK) + b"\x90"),          # mov edi, CLOCK (then call edi)
            (0x129700, b"\xff\x15" + struct.pack("<I", GET_TICK_COUNT), call(0x529700, CLOCK) + b"\x90"),
            (TIMER_CALL - 0x400000, call(TIMER_CALL, FRAME), call(TIMER_CALL, GATE))]


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
            raise ValueError("unexpected frame-clock code or cave")
    if len(found) != 1:
        raise ValueError("partial frame-clock patch")
    return found.pop()


def configure(data, enabled=True):
    state(data)
    out = bytearray(data)
    for offset, old, new in regions():
        out[offset:offset + len(old)] = new if enabled else old
    return bytes(out)
