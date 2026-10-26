"""Seed one synthetic coast test in the isolated offline baseline only.

Usage: python -I tools/seed_offline_velocity.py PID
Writes only player-slot-zero velocity (0, 0, 500), once. Does not emulate keys,
alter positions, change camera transforms, or maintain velocity afterward.
Run immediately after entering a fresh offline scene. Restart to reset fixture.
"""
import ctypes
from ctypes import wintypes
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_clock_experiment


def main():
    pid = int(sys.argv[1])
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    for name in ('ReadProcessMemory', 'WriteProcessMemory'):
        getattr(k, name).argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    h = k.OpenProcess(0x1000 | 0x10 | 0x20 | 0x08, False, pid)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        path = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(path))
        if not k.QueryFullProcessImageNameW(h, 0, path, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        expected = Path(__file__).resolve().parents[1] / 'game/offline-baseline-2.9.2/AOACLIENT.EXE'
        if Path(path.value).resolve() != expected.resolve():
            raise ValueError('fixture is restricted to the isolated offline baseline')
        render_clock_experiment.configure(expected.read_bytes(), False)  # whole-image gate
        def read(addr, size):
            b = ctypes.create_string_buffer(size)
            got = ctypes.c_size_t()
            if not k.ReadProcessMemory(h, addr, b, size, ctypes.byref(got)) or got.value != size:
                raise ctypes.WinError(ctypes.get_last_error())
            return b.raw
        world = struct.unpack('<I', read(0x5E7728, 4))[0]
        player = world + 0xD32AC
        p = read(player, 0x3B0)
        if p[0x243] != 1 or struct.unpack_from('<I', p, 0x178)[0] != 0x80000000 or p[0x244]:
            raise ValueError('requires fresh anonymous offline player slot zero')
        before = struct.unpack_from('<3f', p, 0x54)
        payload = ctypes.create_string_buffer(struct.pack('<3f', 0, 0, 500))
        wrote = ctypes.c_size_t()
        if not k.WriteProcessMemory(h, player + 0x54, payload, 12, ctypes.byref(wrote)) or wrote.value != 12:
            raise ctypes.WinError(ctypes.get_last_error())
        print(f'Synthetic offline coast: previous velocity={before}, seeded velocity=(0, 0, 500)')
    finally:
        k.CloseHandle(h)


if __name__ == '__main__':
    main()
