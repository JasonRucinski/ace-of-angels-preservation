"""Read and write a running client's memory on Windows (ReadProcessMemory / WriteProcessMemory).

The one OpenProcess wrapper of aoa/live and aoa/reel. Every read gets a
buffer of exactly the size asked for. Opening checks the build: the PE
header's TimeDateStamp in the process must be the one recorded for that
version (aoa/live/addresses_292.py), so 2.9.2 addresses are never read from
another build. Windows only; importing it elsewhere is harmless, opening a
process fails.
"""
import ctypes
import struct
import sys
from ctypes import wintypes

from aoa.live import addresses_292

VM_OPERATION, VM_READ, VM_WRITE, QUERY_INFORMATION = 0x0008, 0x0010, 0x0020, 0x0400
PE_TIMESTAMPS = {"2.9.2": addresses_292.PE_TIMESTAMP}
IMAGE_BASE = addresses_292.IMAGE_BASE


def _error():
    if sys.platform == "win32":
        return ctypes.WinError(ctypes.get_last_error())
    return OSError("process memory access failed")


def _kernel32():
    if sys.platform != "win32":
        raise OSError("reading another process's memory needs Windows")
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k.OpenProcess.restype = wintypes.HANDLE
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    for name in ("ReadProcessMemory", "WriteProcessMemory"):
        getattr(k, name).argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                     ctypes.POINTER(ctypes.c_size_t)]
    k.VirtualProtectEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD,
                                   ctypes.POINTER(wintypes.DWORD)]
    k.FlushInstructionCache.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
    return k


class Process:
    """A client process opened with `access` (default read-only), checked to be `build`."""

    def __init__(self, pid, access=VM_READ, build="2.9.2"):
        self.pid = pid
        self.handle = self._open(pid, access)
        try:
            if build is not None:
                self.check_build(build)
        except BaseException:
            self.close()
            raise

    # The three calls into kernel32; tests replace them.
    def _open(self, pid, access):
        self.k = _kernel32()
        handle = self.k.OpenProcess(access, False, pid)
        if not handle:
            raise _error()
        return handle

    def _transfer(self, call, address, buffer, size):
        """Bytes ReadProcessMemory / WriteProcessMemory moved, or -1 when the call failed."""
        got = ctypes.c_size_t()
        ok = getattr(self.k, call)(self.handle, address, buffer, size, ctypes.byref(got))
        return got.value if ok else -1

    def _close(self):
        self.k.CloseHandle(self.handle)

    def read(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        if self._transfer("ReadProcessMemory", address, buffer, size) != size:
            raise _error()
        return buffer.raw

    def u32(self, address):
        return struct.unpack("<I", self.read(address, 4))[0]

    def write(self, address, data, code=False):
        """Write data; code=True lifts page protection around it and flushes the instruction cache."""
        old = wintypes.DWORD()
        if code and not self.k.VirtualProtectEx(self.handle, address, len(data), 0x40, ctypes.byref(old)):
            raise _error()
        moved = self._transfer("WriteProcessMemory", address, data, len(data))
        if code:
            self.k.VirtualProtectEx(self.handle, address, len(data), old.value, ctypes.byref(old))
            self.k.FlushInstructionCache(self.handle, address, len(data))
        if moved != len(data):
            raise _error()

    def check_build(self, build):
        """ValueError unless the process's PE TimeDateStamp is the one recorded for build."""
        if build not in PE_TIMESTAMPS:
            raise ValueError(f"no PE timestamp recorded for client {build}")
        stamp = self.u32(IMAGE_BASE + self.u32(IMAGE_BASE + 0x3C) + 8)
        if stamp != PE_TIMESTAMPS[build]:
            raise ValueError(f"process {self.pid} is not the {build} client "
                             f"(PE timestamp {stamp:#x}, expected {PE_TIMESTAMPS[build]:#x})")

    def close(self):
        if self.handle:
            self._close()
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
