"""Minimal Win32 debugger for running the 32-bit AoA client and catching crashes.

Usage (from 64-bit Python on Windows):
    python -I tools/crashdbg.py [options] <game_dir> [exe] [args...]

Options:
    --trace-physics     log 2.9.2 acceleration time steps (changes timing)
    --trace-exit        log the caller and stack of msvcrt exit/_exit before
                        deliberate shutdowns (which are not exceptions)
    --timeout SECONDS   terminate the game after this long
    --trace VA[,VA...]  log the registers each time one of these instruction
                        addresses (image VAs, base 0x400000) executes; each
                        must be the first byte of an instruction
    --debug-heap        leave the NT debug heap on (normally _NO_DEBUG_HEAP=1
                        is set so behaviour matches a normal launch)
    --guard-heap        serve every msvcrt malloc/calloc/realloc/free/_msize/
                        _expand from the debugger: each block ends flush
                        against an uncommitted page and freed blocks are
                        decommitted and never reused, so the instruction that
                        overruns a heap block or touches freed memory faults
                        immediately (a debugger-driven page heap that needs no
                        admin rights or registry changes)
    --guard-continue    after reporting a guard-page fault, commit the page and
                        resume, to collect every bad access in one run
    --guard-fill BYTE   fill new guard-heap blocks with BYTE (default: leave
                        the zero-filled pages, which hides uninitialised reads)
    --guard-reuse       reuse freed page runs after 4096 subsequent frees;
                        limits exhaustion but cannot detect UAF after reuse

Launches <game_dir>/<exe> (default AOACLIENT.EXE) with <game_dir> as the
working directory under DEBUG_ONLY_THIS_PROCESS and logs, to stdout:
  * module loads (base address + path),
  * OutputDebugString text,
  * every first-chance exception other than the two loader breakpoints, with
    module+offset, the i386 register set (via Wow64GetThreadContext), and a
    heuristic call stack: stack dwords that point into a loaded module's
    image, plus the EBP frame chain.
Second-chance (unhandled) exceptions end the session.
"""
import ctypes
import ctypes.wintypes as wt
import os
import struct
import subprocess
import sys
import time
from collections import Counter

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

DEBUG_ONLY_THIS_PROCESS = 0x2
CREATE_UNICODE_ENVIRONMENT = 0x400
DBG_CONTINUE = 0x00010002
DBG_EXCEPTION_NOT_HANDLED = 0x80010001
EXCEPTION_DEBUG_EVENT, CREATE_THREAD_DEBUG_EVENT, CREATE_PROCESS_DEBUG_EVENT = 1, 2, 3
EXIT_THREAD_DEBUG_EVENT, EXIT_PROCESS_DEBUG_EVENT, LOAD_DLL_DEBUG_EVENT = 4, 5, 6
UNLOAD_DLL_DEBUG_EVENT, OUTPUT_DEBUG_STRING_EVENT, RIP_EVENT = 7, 8, 9
BREAKPOINT_CODES = {0x80000003, 0x4000001F}  # int3, STATUS_WX86_BREAKPOINT
SINGLE_STEP_CODES = {0x80000004, 0x4000001E}  # STATUS_SINGLE_STEP, STATUS_WX86_SINGLE_STEP
ACCESS_VIOLATION = 0xC0000005
QUIET_CODES = {0x406D1388}  # MS_VC_EXCEPTION thread naming
WOW64_CONTEXT_FULL = 0x10000 | 0x1 | 0x2 | 0x4
THREAD_ALL_ACCESS = 0x1FFFFF
PAGE = 0x1000
MEM_COMMIT, MEM_RESERVE, MEM_DECOMMIT = 0x1000, 0x2000, 0x4000
PAGE_NOACCESS, PAGE_READWRITE = 0x01, 0x04
TRAP_FLAG = 0x100
GUARDED_EXPORTS = ("malloc", "calloc", "realloc", "free", "_msize", "_expand")


class EXCEPTION_RECORD(ctypes.Structure):
    _fields_ = [("ExceptionCode", wt.DWORD), ("ExceptionFlags", wt.DWORD),
                ("ExceptionRecord", ctypes.c_void_p), ("ExceptionAddress", ctypes.c_void_p),
                ("NumberParameters", wt.DWORD), ("ExceptionInformation", ctypes.c_size_t * 15)]


class EXCEPTION_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", wt.DWORD)]


class CREATE_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("hFile", wt.HANDLE), ("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("lpBaseOfImage", ctypes.c_void_p), ("dwDebugInfoFileOffset", wt.DWORD),
                ("nDebugInfoSize", wt.DWORD), ("lpThreadLocalBase", ctypes.c_void_p),
                ("lpStartAddress", ctypes.c_void_p), ("lpImageName", ctypes.c_void_p),
                ("fUnicode", wt.WORD)]


class CREATE_THREAD_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("hThread", wt.HANDLE), ("lpThreadLocalBase", ctypes.c_void_p),
                ("lpStartAddress", ctypes.c_void_p)]


class LOAD_DLL_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("hFile", wt.HANDLE), ("lpBaseOfDll", ctypes.c_void_p),
                ("dwDebugInfoFileOffset", wt.DWORD), ("nDebugInfoSize", wt.DWORD),
                ("lpImageName", ctypes.c_void_p), ("fUnicode", wt.WORD)]


class OUTPUT_DEBUG_STRING_INFO(ctypes.Structure):
    _fields_ = [("lpDebugStringData", ctypes.c_void_p), ("fUnicode", wt.WORD),
                ("nDebugStringLength", wt.WORD)]


class EXIT_PROCESS_DEBUG_INFO(ctypes.Structure):
    _fields_ = [("dwExitCode", wt.DWORD)]


class _U(ctypes.Union):
    _fields_ = [("Exception", EXCEPTION_DEBUG_INFO), ("CreateThread", CREATE_THREAD_DEBUG_INFO),
                ("CreateProcessInfo", CREATE_PROCESS_DEBUG_INFO), ("ExitProcess", EXIT_PROCESS_DEBUG_INFO),
                ("LoadDll", LOAD_DLL_DEBUG_INFO), ("DebugString", OUTPUT_DEBUG_STRING_INFO),
                ("_pad", ctypes.c_byte * 160)]


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [("dwDebugEventCode", wt.DWORD), ("dwProcessId", wt.DWORD),
                ("dwThreadId", wt.DWORD), ("u", _U)]


class WOW64_CONTEXT(ctypes.Structure):
    _fields_ = [("ContextFlags", wt.DWORD), ("Dr", wt.DWORD * 6), ("FloatSave", ctypes.c_byte * 112),
                ("SegGs", wt.DWORD), ("SegFs", wt.DWORD), ("SegEs", wt.DWORD), ("SegDs", wt.DWORD),
                ("Edi", wt.DWORD), ("Esi", wt.DWORD), ("Ebx", wt.DWORD), ("Edx", wt.DWORD),
                ("Ecx", wt.DWORD), ("Eax", wt.DWORD), ("Ebp", wt.DWORD), ("Eip", wt.DWORD),
                ("SegCs", wt.DWORD), ("EFlags", wt.DWORD), ("Esp", wt.DWORD), ("SegSs", wt.DWORD),
                ("ExtendedRegisters", ctypes.c_byte * 512)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("lpReserved", wt.LPWSTR), ("lpDesktop", wt.LPWSTR),
                ("lpTitle", wt.LPWSTR), ("dwX", wt.DWORD), ("dwY", wt.DWORD), ("dwXSize", wt.DWORD),
                ("dwYSize", wt.DWORD), ("dwXCountChars", wt.DWORD), ("dwYCountChars", wt.DWORD),
                ("dwFillAttribute", wt.DWORD), ("dwFlags", wt.DWORD), ("wShowWindow", wt.WORD),
                ("cbReserved2", wt.WORD), ("lpReserved2", ctypes.c_void_p), ("hStdInput", wt.HANDLE),
                ("hStdOutput", wt.HANDLE), ("hStdError", wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wt.HANDLE), ("hThread", wt.HANDLE),
                ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD)]


k32.WaitForDebugEvent.argtypes = [ctypes.POINTER(DEBUG_EVENT), wt.DWORD]
k32.ContinueDebugEvent.argtypes = [wt.DWORD, wt.DWORD, wt.DWORD]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                   ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD, wt.DWORD]
k32.VirtualFreeEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD]
k32.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
k32.Wow64GetThreadContext.argtypes = [wt.HANDLE, ctypes.POINTER(WOW64_CONTEXT)]
k32.Wow64SetThreadContext.argtypes = [wt.HANDLE, ctypes.POINTER(WOW64_CONTEXT)]
k32.OpenThread.restype = wt.HANDLE
k32.OpenThread.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.GetFinalPathNameByHandleW.argtypes = [wt.HANDLE, wt.LPWSTR, wt.DWORD, wt.DWORD]
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]


def path_of(h):
    if not h:
        return "?"
    buf = ctypes.create_unicode_buffer(1024)
    n = k32.GetFinalPathNameByHandleW(h, buf, 1024, 0)
    return buf.value.removeprefix("\\\\?\\") if n else "?"


def pe_exports(path):
    """name -> RVA for a DLL on disk (no third-party deps)."""
    data = open(path, "rb").read()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    opt = e + 24
    exp_rva = struct.unpack_from("<I", data, opt + 96)[0]
    secs = [struct.unpack_from("<IIII", data, opt + struct.unpack_from("<H", data, e + 20)[0] + 40 * i + 8)
            for i in range(nsec)]  # VirtualSize, VirtualAddress, SizeOfRawData, PointerToRawData

    def off(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs):
                return rva - va + ro
        raise ValueError(hex(rva))
    d = off(exp_rva)
    nnames, funcs, names, ords = struct.unpack_from("<IIII", data, d + 24)
    out = {}
    for i in range(nnames):
        nm_off = off(struct.unpack_from("<I", data, off(names) + 4 * i)[0])
        name = data[nm_off:data.index(b"\0", nm_off)].decode()
        ordinal = struct.unpack_from("<H", data, off(ords) + 2 * i)[0]
        out[name] = struct.unpack_from("<I", data, off(funcs) + 4 * ordinal)[0]
    return out


class GuardHeap:
    """Debugger-side allocator: one block per page run, guard page after each."""

    def __init__(self, sess, fill, reuse=False):
        self.s = sess
        self.fill = fill
        self.base = self.size = self.next = 0
        self.blocks = {}   # ptr -> (size, region, npages, alloc_site)
        self.freed = {}    # ptr -> (size, region, npages, alloc_site, free_site)
        self.stats = Counter()
        self.reuse = reuse
        self.quarantine = []
        self.available = {}

    def reserve(self):
        for mb in (768, 512, 384, 256):
            b = k32.VirtualAllocEx(self.s.hproc, None, mb << 20, MEM_RESERVE, PAGE_NOACCESS)
            if b:
                self.base, self.size = b, mb << 20
                self.s.log(f"guard heap: reserved {mb} MB at {b:#x}")
                return
        raise ctypes.WinError(ctypes.get_last_error())

    def in_arena(self, a):
        return self.base <= a < self.base + self.size

    def alloc(self, n, site):
        if n >= 0x40000000:
            self.stats["huge_request"] += 1
            self.s.log(f"guard heap: refusing {n:#x}-byte request from {site}")
            return 0
        pages = max(1, (n + PAGE - 1) // PAGE)
        reusable = self.available.get(pages)
        if reusable:
            old_ptr, region = reusable.pop()
            self.freed.pop(old_ptr, None)
            self.stats["reuse"] += 1
        elif self.next + (pages + 1) * PAGE > self.size:
            self.stats["arena_exhausted"] += 1
            return 0
        else:
            region = self.base + self.next
            self.next += (pages + 1) * PAGE
        if not k32.VirtualAllocEx(self.s.hproc, region, pages * PAGE, MEM_COMMIT, PAGE_READWRITE):
            raise ctypes.WinError(ctypes.get_last_error())
        ptr = region + pages * PAGE - n
        if self.fill is not None and n:
            self.s.write(ptr, bytes([self.fill]) * n)
        self.blocks[ptr] = (n, region, pages, site)
        self.stats["alloc"] += 1
        return ptr

    def release(self, ptr, site):
        n, region, pages, asite = self.blocks.pop(ptr)
        # Also remove a guard page committed by --guard-continue.
        k32.VirtualFreeEx(self.s.hproc, region, (pages + 1) * PAGE, MEM_DECOMMIT)
        self.freed[ptr] = (n, region, pages, asite, site)
        self.stats["free"] += 1
        if self.reuse:
            self.quarantine.append((ptr, region, pages))
            if len(self.quarantine) > 4096:
                old_ptr, old_region, old_pages = self.quarantine.pop(0)
                self.available.setdefault(old_pages, []).append((old_ptr, old_region))

    def describe(self, a):
        """Which block an arena address belongs to (or just past)."""
        for tbl, kind in ((self.blocks, "live"), (self.freed, "freed")):
            for ptr, rec in tbl.items():
                n, region, pages = rec[:3]
                if region <= a < region + (pages + 1) * PAGE:
                    extra = f" freed by {rec[4]}" if kind == "freed" else ""
                    return (f"{kind} block {ptr:#x} size {n:#x} (offset {a - ptr:+#x}) "
                            f"allocated by {rec[3]}{extra}")
        return "unknown arena address"

    def bad_pointer(self, what, ptr, site):
        self.stats["bad_" + what] += 1
        kind = "DOUBLE FREE / FREED POINTER" if ptr in self.freed else "INTERIOR/INVALID POINTER"
        self.s.log(f"GUARD HEAP: {what}({ptr:#x}) {kind} from {site}: {self.describe(ptr)}")

    def call(self, name, args, site):
        """Emulate one allocator call. Returns the result, or None to run the real one."""
        a1, a2 = args
        if name == "malloc":
            return self.alloc(a1, site)
        if name == "calloc":
            n = a1 * a2
            p = self.alloc(n, site) if n < 0x40000000 else 0
            if p and self.fill is not None:
                self.s.write(p, b"\0" * n)
            return p
        if name == "free":
            if a1 == 0:
                return 0
            if a1 in self.blocks:
                self.release(a1, site)
                return 0
            if self.in_arena(a1):
                self.bad_pointer("free", a1, site)
                return 0
            self.stats["passthrough_free"] += 1
            return None
        if name == "realloc":
            if a1 == 0:
                return self.alloc(a2, site)
            if a1 in self.blocks:
                if a2 == 0:
                    self.release(a1, site)
                    return 0
                new = self.alloc(a2, site)
                if new:
                    keep = min(a2, self.blocks[a1][0])
                    self.s.write(new, self.s.read(a1, keep))
                    self.release(a1, site)
                return new
            if self.in_arena(a1):
                self.bad_pointer("realloc", a1, site)
                return 0
            self.stats["passthrough_realloc"] += 1
            return None
        if name == "_msize":
            if a1 in self.blocks:
                return self.blocks[a1][0]
            if self.in_arena(a1):
                self.bad_pointer("_msize", a1, site)
                return 0xFFFFFFFF
            return None
        if name == "_expand":
            if a1 in self.blocks:
                return a1 if a2 <= self.blocks[a1][0] else 0
            return None if not self.in_arena(a1) else 0
        raise KeyError(name)


class Session:
    def __init__(self, guard=False, guard_continue=False, guard_fill=None, guard_reuse=False):
        self.modules = {}  # base -> (end, name)
        self.threads = {}
        self.hproc = None
        self.seen_loader_bp = set()
        self.exe_base = 0
        self.hooks = {}    # va -> (name, original byte)
        self.rearm = {}    # tid -> va to re-insert int3 at after a single step
        self.guard = GuardHeap(self, guard_fill, guard_reuse) if guard else None
        self.guard_continue = guard_continue
        self.trace_vas = []  # image VAs (default base 0x400000) logged on every hit
        self.t0 = time.monotonic()

    def log(self, msg):
        print(f"[{time.monotonic() - self.t0:7.3f}] {msg}", flush=True)

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.hproc, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return b""
        return buf.raw[:got.value]

    def read_upto(self, addr, n):
        """Read up to n bytes, stopping at the first unreadable page (stack tops)."""
        out = b""
        while len(out) < n:
            chunk = min(n - len(out), PAGE - ((addr + len(out)) & (PAGE - 1)))
            got = self.read(addr + len(out), chunk)
            out += got
            if len(got) < chunk:
                break
        return out

    def write(self, addr, data):
        got = ctypes.c_size_t()
        if not k32.WriteProcessMemory(self.hproc, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got)):
            raise ctypes.WinError(ctypes.get_last_error())
        k32.FlushInstructionCache(self.hproc, ctypes.c_void_p(addr), len(data))

    def image_size(self, base):
        hdr = self.read(base, 0x400)
        if not hdr or hdr[:2] != b"MZ":
            return 0x1000
        e = struct.unpack_from("<I", hdr, 0x3C)[0]
        if e + 0x58 > len(hdr) or hdr[e:e + 4] != b"PE\0\0":
            return 0x1000
        return struct.unpack_from("<I", hdr, e + 24 + 56)[0]  # OptionalHeader.SizeOfImage

    def sym(self, addr):
        for base, (end, name) in self.modules.items():
            if base <= addr < end:
                return f"{os.path.basename(name)}+{addr - base:#x}"
        return f"{addr:#010x}"

    def in_module(self, addr):
        return any(b <= addr < e for b, (e, _) in self.modules.items())

    def thread(self, tid):
        h = self.threads.get(tid)
        if not h:
            h = self.threads[tid] = k32.OpenThread(THREAD_ALL_ACCESS, False, tid)
        return h

    def context(self, tid):
        ctx = WOW64_CONTEXT()
        ctx.ContextFlags = WOW64_CONTEXT_FULL
        if not k32.Wow64GetThreadContext(self.thread(tid), ctypes.byref(ctx)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctx

    def set_context(self, tid, ctx):
        if not k32.Wow64SetThreadContext(self.thread(tid), ctypes.byref(ctx)):
            raise ctypes.WinError(ctypes.get_last_error())

    def call_site(self, esp):
        """Return address plus the first return address into the main EXE."""
        stack = self.read_upto(esp, 0x100)
        ret = struct.unpack_from("<I", stack, 0)[0]
        site = self.sym(ret)
        exe_base = self.exe_base
        exe_end = self.modules.get(exe_base, (0,))[0]
        if not (exe_base <= ret < exe_end):
            for off in range(4, len(stack) - 3, 4):
                v = struct.unpack_from("<I", stack, off)[0]
                if exe_base <= v < exe_end:
                    site += f" <~ {self.sym(v)}"
                    break
        return site

    def dump_exception(self, ev):
        er = ev.u.Exception.ExceptionRecord
        code, addr = er.ExceptionCode, er.ExceptionAddress or 0
        info = [er.ExceptionInformation[i] for i in range(er.NumberParameters)]
        first = bool(ev.u.Exception.dwFirstChance)
        self.log(f"EXCEPTION {code:#010x} {'first' if first else 'SECOND'}-chance tid={ev.dwThreadId} "
                 f"at {self.sym(addr)} params={[hex(x) for x in info]}")
        try:
            ctx = self.context(ev.dwThreadId)
        except OSError as e:
            self.log(f"  (no context: {e})")
            return
        regs = " ".join(f"{r.lower()}={getattr(ctx, r):08x}" for r in
                        ("Eax", "Ebx", "Ecx", "Edx", "Esi", "Edi", "Ebp", "Esp", "Eip"))
        self.log(f"  {regs}")
        chain, ebp = [], ctx.Ebp
        for _ in range(24):
            fr = self.read(ebp, 8)
            if len(fr) < 8:
                break
            nxt, ret = struct.unpack("<II", fr)
            chain.append(self.sym(ret))
            if nxt <= ebp:
                break
            ebp = nxt
        self.log(f"  ebp-chain: {' <- '.join(chain)}")
        stack = self.read_upto(ctx.Esp, 0x400)
        hits = []
        for off in range(0, len(stack) - 3, 4):
            v = struct.unpack_from("<I", stack, off)[0]
            if self.in_module(v):
                hits.append(f"esp+{off:03x}:{self.sym(v)}")
        self.log("  stack-scan: " + "  ".join(hits[:40]))

    def install_guard_hooks(self, base, path):
        if self.guard.base == 0:
            self.guard.reserve()
        exports = pe_exports(path)
        for name in GUARDED_EXPORTS:
            va = base + exports[name]
            orig = self.read(va, 1)
            self.write(va, b"\xCC")
            self.hooks[va] = (name, orig)
        self.log(f"guard heap: hooked {', '.join(GUARDED_EXPORTS)} in {path}")

    def on_hook(self, ev, va):
        name, orig = self.hooks[va]
        tid = ev.dwThreadId
        ctx = self.context(tid)
        ret, a1, a2 = struct.unpack("<III", self.read_upto(ctx.Esp, 12).ljust(12, b"\0"))
        if name == "physics:acceleration":
            dt = struct.unpack("<f", self.read(ctx.Esp + 0x3C, 4))[0]
            tag = struct.unpack("<I", self.read(ctx.Ebp + 0x174, 4))[0]
            self.log(f"TRACE physics acceleration tag={tag:#x} dt={dt!r}")
            result = None
        elif name.startswith("arena:"):
            self.log(f"TRACE {name} at {self.sym(va)}")
            result = None
        elif name.startswith("trace:"):
            regs = " ".join(f"{r.lower()}={getattr(ctx, r):08x}" for r in
                            ("Eax", "Ebx", "Ecx", "Edx", "Esi", "Edi", "Ebp", "Esp"))
            self.log(f"TRACE {va - self.exe_base + 0x400000:#x} {regs}")
            result = None
        elif name in ("exit", "_exit"):
            self.log(f"EXIT REQUEST {name}({a1}) caller={self.call_site(ctx.Esp)}")
            self.dump_exception(ev)
            result = None
        else:
            result = self.guard.call(name, (a1, a2), self.call_site(ctx.Esp))
        if result is None:  # run the real function: unpatch, single-step, re-arm
            self.write(va, orig)
            ctx.Eip = va
            ctx.EFlags |= TRAP_FLAG
            self.rearm[tid] = va
        else:               # emulate a cdecl return
            ctx.Eax = result & 0xFFFFFFFF
            ctx.Eip = ret
            ctx.Esp += 4
        self.set_context(tid, ctx)

    def on_guard_fault(self, ev):
        """Report an AV inside the guard arena; optionally make it survivable."""
        er = ev.u.Exception.ExceptionRecord
        rw = {0: "READ", 1: "WRITE", 8: "EXECUTE"}.get(er.ExceptionInformation[0], "?")
        a = er.ExceptionInformation[1]
        self.log(f"GUARD HEAP: {rw} of {a:#x} by {self.sym(er.ExceptionAddress or 0)}: "
                 f"{self.guard.describe(a)}")
        self.dump_exception(ev)
        if self.guard_continue:
            k32.VirtualAllocEx(self.hproc, a & ~(PAGE - 1), PAGE, MEM_COMMIT, PAGE_READWRITE)
            return DBG_CONTINUE
        return DBG_EXCEPTION_NOT_HANDLED

    def run(self, game_dir, exe, args, debug_heap, timeout, trace_exit=False, trace_arena=False, trace_physics=False):
        app = os.path.join(game_dir, exe)
        cmd = subprocess.list2cmdline([app] + args)
        env = dict(os.environ)
        if not debug_heap:
            env["_NO_DEBUG_HEAP"] = "1"
        env_block = "".join(f"{k}={v}\0" for k, v in env.items()) + "\0"
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(si)
        pi = PROCESS_INFORMATION()
        if not k32.CreateProcessW(app, ctypes.create_unicode_buffer(cmd), None, None, False,
                                  DEBUG_ONLY_THIS_PROCESS | CREATE_UNICODE_ENVIRONMENT,
                                  ctypes.create_unicode_buffer(env_block), game_dir,
                                  ctypes.byref(si), ctypes.byref(pi)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.hproc = pi.hProcess
        self.log(f"started pid={pi.dwProcessId} {cmd}")
        ev = DEBUG_EVENT()
        deadline = time.monotonic() + timeout if timeout else None
        killed = False
        while True:
            if deadline and not killed and time.monotonic() > deadline:
                self.log("timeout: terminating process")
                k32.TerminateProcess(self.hproc, 0xDEAD)
                killed = True
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 500):
                continue
            status = DBG_CONTINUE
            c = ev.dwDebugEventCode
            if c == CREATE_PROCESS_DEBUG_EVENT:
                cp = ev.u.CreateProcessInfo
                base = self.exe_base = cp.lpBaseOfImage
                self.modules[base] = (base + self.image_size(base), path_of(cp.hFile))
                self.threads[ev.dwThreadId] = cp.hThread
                if cp.hFile:
                    k32.CloseHandle(cp.hFile)
                self.log(f"process image {self.modules[base][1]} @ {base:#x}")
                if trace_physics:
                    va = base + 0x8C200
                    self.hooks[va] = ("physics:acceleration", self.read(va, 1))
                    self.write(va, b"\xCC")
                for image_va in self.trace_vas:
                    va = base + image_va - 0x400000
                    self.hooks[va] = (f"trace:{image_va:#x}", self.read(va, 1))
                    self.write(va, b"\xCC")
                if trace_arena:
                    for rva, label in ((0x306c1, "load-ship"), (0x30684, "enter-flight"),
                                       (0x30608, "load-player"), (0x30881, "set-position"),
                                       (0x33ac9, "watchdog-flight")):
                        va = base + rva
                        self.hooks[va] = ("arena:" + label, self.read(va, 1))
                        self.write(va, b"\xCC")
            elif c == CREATE_THREAD_DEBUG_EVENT:
                self.threads[ev.dwThreadId] = ev.u.CreateThread.hThread
            elif c == EXIT_THREAD_DEBUG_EVENT:
                self.threads.pop(ev.dwThreadId, None)
            elif c == LOAD_DLL_DEBUG_EVENT:
                ld = ev.u.LoadDll
                base = ld.lpBaseOfDll
                name = path_of(ld.hFile)
                if ld.hFile:
                    k32.CloseHandle(ld.hFile)
                self.modules[base] = (base + self.image_size(base), name)
                self.log(f"load {base:#010x} {name}")
                if self.guard and name.lower().endswith("syswow64\\msvcrt.dll"):
                    self.install_guard_hooks(base, name)
                if trace_exit and name.lower().endswith("syswow64\\msvcrt.dll"):
                    exports = pe_exports(name)
                    for symbol in ("exit", "_exit"):
                        va = base + exports[symbol]
                        self.hooks[va] = (symbol, self.read(va, 1))
                        self.write(va, b"\xCC")
            elif c == OUTPUT_DEBUG_STRING_EVENT:
                ds = ev.u.DebugString
                raw = self.read(ds.lpDebugStringData,
                                ds.nDebugStringLength * (2 if ds.fUnicode else 1))
                txt = raw.decode("utf-16le" if ds.fUnicode else "latin1", "replace").rstrip("\0\r\n")
                self.log(f"ODS: {txt}")
            elif c == EXCEPTION_DEBUG_EVENT:
                er = ev.u.Exception.ExceptionRecord
                code, addr = er.ExceptionCode, er.ExceptionAddress or 0
                first = bool(ev.u.Exception.dwFirstChance)
                if code in BREAKPOINT_CODES and addr in self.hooks:
                    self.on_hook(ev, addr)
                elif code in SINGLE_STEP_CODES and ev.dwThreadId in self.rearm:
                    self.write(self.rearm.pop(ev.dwThreadId), b"\xCC")
                elif code in BREAKPOINT_CODES and first and code not in self.seen_loader_bp:
                    # One native + one WOW64 loader breakpoint; later ones
                    # (e.g. debug-heap validation failures) are logged.
                    self.seen_loader_bp.add(code)
                elif code in BREAKPOINT_CODES and first:
                    self.dump_exception(ev)
                elif code in QUIET_CODES:
                    status = DBG_EXCEPTION_NOT_HANDLED
                elif (code == ACCESS_VIOLATION and first and self.guard
                      and er.NumberParameters >= 2 and self.guard.in_arena(er.ExceptionInformation[1])):
                    status = self.on_guard_fault(ev)
                else:
                    self.dump_exception(ev)
                    status = DBG_EXCEPTION_NOT_HANDLED
            elif c == EXIT_PROCESS_DEBUG_EVENT:
                self.log(f"process exited code={ev.u.ExitProcess.dwExitCode:#x}")
                if self.guard:
                    self.log(f"guard heap stats: {dict(self.guard.stats)} live={len(self.guard.blocks)} "
                             f"arena used={self.guard.next >> 20} MB")
                k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, DBG_CONTINUE)
                return ev.u.ExitProcess.dwExitCode
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)


def main():
    argv = sys.argv[1:]
    opts = {"--debug-heap": False, "--guard-heap": False, "--guard-continue": False,
            "--trace-exit": False, "--trace-arena": False, "--guard-reuse": False,
            "--trace-physics": False}
    for flag in opts:
        if flag in argv:
            opts[flag] = True
            argv.remove(flag)
    timeout, fill = 0.0, None
    if "--timeout" in argv:
        i = argv.index("--timeout")
        timeout = float(argv[i + 1])
        del argv[i:i + 2]
    if "--guard-fill" in argv:
        i = argv.index("--guard-fill")
        fill = int(argv[i + 1], 0)
        del argv[i:i + 2]
    trace = []
    if "--trace" in argv:
        i = argv.index("--trace")
        trace = [int(v, 16) for v in argv[i + 1].split(",")]
        del argv[i:i + 2]
    game_dir = os.path.abspath(argv[0])
    exe = argv[1] if len(argv) > 1 else "AOACLIENT.EXE"
    session = Session(opts["--guard-heap"], opts["--guard-continue"], fill, opts["--guard-reuse"])
    session.trace_vas = trace
    session.run(
        game_dir, exe, argv[2:], opts["--debug-heap"], timeout, opts["--trace-exit"], opts["--trace-arena"], opts["--trace-physics"])


if __name__ == "__main__":
    main()
