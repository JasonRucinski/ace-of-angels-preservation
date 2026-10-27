"""Find, foreground and send messages to the running 2.9.2 client's windows.

  python -I tools/reel/window.py list
  python -I tools/reel/window.py press TITLE_PREFIX CONTROL_ID
  python -I tools/reel/window.py front
  python -I tools/reel/window.py key VK [--sys]
"""
import argparse
import ctypes
import json
import subprocess
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumProc, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, EnumProc, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
user32.GetDlgItem.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetForegroundWindow.restype = wintypes.HWND
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.SetProcessDPIAware()

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP, WM_COMMAND = 0x100, 0x101, 0x104, 0x105, 0x111


def client_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AOACLIENT.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"AOACLIENT')]


def _text(hwnd, getter):
    buf = ctypes.create_unicode_buffer(256)
    getter(hwnd, buf, 256)
    return buf.value


def windows(pid=None):
    pids = {pid} if pid else set(client_pids())
    found = []

    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in pids:
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            found.append({"hwnd": hwnd, "pid": owner.value, "class": _text(hwnd, user32.GetClassNameW),
                          "title": _text(hwnd, user32.GetWindowTextW), "visible": bool(user32.IsWindowVisible(hwnd)),
                          "rect": [r.left, r.top, r.right, r.bottom]})
        return True
    user32.EnumWindows(EnumProc(visit), 0)
    return found


def dialog(prefix, timeout=0.0):
    """The first visible #32770 dialog whose title starts with prefix."""
    deadline = time.monotonic() + timeout
    while True:
        for w in windows():
            if w["class"] == "#32770" and w["visible"] and w["title"].startswith(prefix):
                return w["hwnd"]
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.25)


def press(hwnd, control_id):
    child = user32.GetDlgItem(hwnd, control_id)
    return bool(user32.PostMessageW(hwnd, WM_COMMAND, control_id & 0xFFFF, child or 0))


def main_window():
    """The largest visible non-dialog window of the client (the 3D view)."""
    best = None
    for w in windows():
        if w["visible"] and w["class"] != "#32770":
            r = w["rect"]
            area = (r[2] - r[0]) * (r[3] - r[1])
            if best is None or area > best[0]:
                best = (area, w["hwnd"])
    return best[1] if best else None


def front(hwnd):
    """Make hwnd the foreground window (attach to the current foreground thread first)."""
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.ShowWindow(hwnd, 5)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)
    return user32.GetForegroundWindow() == hwnd


def key(hwnd, vk, system=False, hold=0.05):
    scan = user32.MapVirtualKeyW(vk, 0)
    down = 1 | (scan << 16) | ((1 << 29) if system else 0)
    up = down | (1 << 30) | (1 << 31)
    user32.PostMessageW(hwnd, WM_SYSKEYDOWN if system else WM_KEYDOWN, vk, down)
    time.sleep(hold)
    user32.PostMessageW(hwnd, WM_SYSKEYUP if system else WM_KEYUP, vk, up)


VK_SHIFT = 0x10
# Shift+key "visible toggle" commands from the default key map (0x4B8500
# registrations near 0x44F7xx, modifier 1 = Shift).
HUD_PANELS = {"targets": 0x54, "user_list": 0x55, "systems": 0x53, "radar": 0x52, "range": 0x47,
              "damage": 0x44, "comm": 0x43, "messages": 0x41, "weapons": 0x57, "own_ship": 0x48,
              "target_ship": 0x4A, "sight": 0x4C, "connection": 0x49}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def send_keys(*vks, up=False):
    """Real keyboard events (the game must be the foreground window)."""
    events = (INPUT * len(vks))()
    for event, vk in zip(events, vks):
        event.type = 1
        event.ki = KEYBDINPUT(vk, user32.MapVirtualKeyW(vk, 0), 2 if up else 0, 0, 0)
    return user32.SendInput(len(vks), events, ctypes.sizeof(INPUT))


def hide_hud(hwnd, panels=None):
    """Toggle the named HUD panels (all by default) with real Shift+key presses."""
    for name in panels or HUD_PANELS:
        if name in HUD_PANELS:
            send_keys(VK_SHIFT, HUD_PANELS[name])
            time.sleep(0.06)
            send_keys(HUD_PANELS[name], VK_SHIFT, up=True)
            time.sleep(0.12)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    p = sub.add_parser("press")
    p.add_argument("title")
    p.add_argument("control", type=int)
    p.add_argument("--wait", type=float, default=20)
    sub.add_parser("front")
    p = sub.add_parser("key")
    p.add_argument("vk", type=lambda s: int(s, 0))
    p.add_argument("--sys", action="store_true")
    args = parser.parse_args()
    if args.action == "list":
        print(json.dumps(windows(), indent=1))
    elif args.action == "press":
        hwnd = dialog(args.title, args.wait)
        if not hwnd:
            sys.exit(f"no dialog starting {args.title!r}")
        print(press(hwnd, args.control))
    elif args.action == "front":
        print(front(main_window()))
    else:
        key(main_window(), args.vk, args.sys)


if __name__ == "__main__":
    main()
