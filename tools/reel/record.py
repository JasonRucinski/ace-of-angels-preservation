"""Film scripted shots of the real 2.9.2 client for the highlight reel.

  python -I tools/reel/record.py tools/reel/shots.json [--only NAME ...] [--out work/reel/raw]

For each shot: start the loopback host on the shot's map, launch and log in
the client (window messages only), wait for flight, start the scripted
pilots, force the camera mode in memory, hold the ship's velocity, and
record the game window with ffmpeg's Windows Graphics Capture source.
Afterwards everything is closed again. The PC must stay unlocked with the
game window visible; this process keeps the display awake while it runs.
Capture needs a process outside a restricted sandbox (it records black
otherwise).

Shot fields: name, map, seconds; optional backdrop, spawn_at, start_vessel,
target_ships, pilots (bot.py list, absolute coordinates), velocity (own
ship, world units/s), camera (cockpit|chase|orbit), camera_at (list of
[seconds, mode] switches), fire (list of [start, end] seconds holding guns),
settle (seconds after flight entry before filming), hud ("clean" toggles the
panels in `hide`, default DEFAULT_HIDE, with real Shift+key
presses; "full" leaves them).
"""
import argparse
import ctypes
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tools"))
import bot  # noqa: E402
import client_mem  # noqa: E402
import online_terrain  # noqa: E402
import window  # noqa: E402

GAME = ROOT / "game/2.9.2"
EXE = GAME / "AOACLIENT.EXE"
VK_SPACE = 0x20
# Panels seen over the view in the scouting captures; the rest stay.
DEFAULT_HIDE = ("user_list", "comm", "messages", "weapons")


def keep_awake(on=True):
    # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000003 if on else 0x80000000)


def kill_clients():
    subprocess.run(["taskkill", "/F", "/IM", "AOACLIENT.EXE"], capture_output=True)
    deadline = time.monotonic() + 10
    while window.client_pids() and time.monotonic() < deadline:
        time.sleep(0.2)


def start_host(shot, log):
    command = [sys.executable, "-I", str(ROOT / "tools/station_stub.py"), str(GAME / "SCRTY.BIN"), str(log),
               "--profile", "local-relay", "--bind-address", "127.0.0.1", "--map", shot["map"],
               "--backdrop", shot.get("backdrop", "spacebkgd3"), "--experimental-terrain",
               "--kill-limit", "0", "--time-limit", "0",
               "--target-ships", str(shot.get("target_ships", 0)),
               "--start-vessel", shot.get("start_vessel", "Ym Khtat")]
    if shot.get("spawn_at"):
        command += ["--spawn-at", *map(str, shot["spawn_at"])]
    _, kind, target, _ = online_terrain.MAPS[online_terrain.MAP_NAMES.index(shot["map"])]
    if kind == online_terrain.TRN and shot.get("powerups", True):
        command += ["--powerup-zones", str(GAME / target)]
    host = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ready = time.monotonic() + 15
    seen = []
    for line in host.stdout:
        seen.append(line.strip())
        if "Host console ready" in line or "station stub on" in line:
            break
        if time.monotonic() > ready:
            break
    else:
        # The host exited, e.g. another host (the host window) holds the ports;
        # the client would join that one instead, on its map.
        raise RuntimeError("host did not start: " + " | ".join(seen[-3:]))
    if not seen or not ("Host console ready" in seen[-1] or "station stub on" in seen[-1]):
        stop_host(host)
        raise RuntimeError("host did not start: " + " | ".join(seen[-3:]))
    threading.Thread(target=lambda: [None for _ in host.stdout], daemon=True).start()
    return host


def stop_host(host):
    """End the host and any child (a venv python.exe is a launcher with a child)."""
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(host.pid)], capture_output=True)
    try:
        host.wait(10)
    except subprocess.TimeoutExpired:
        host.kill()


def enter_flight():
    """Launch, log in, press Station Play and wait until slot 0 is flying."""
    subprocess.Popen([str(EXE)], cwd=GAME)
    deadline = time.monotonic() + 60
    while True:
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                 str(ROOT / "tools/client_login.ps1"), "-Station", "127.0.0.1"],
                                capture_output=True, text=True).stdout
        if "pressed Play Online" in result:
            break
        if time.monotonic() > deadline:
            raise RuntimeError(f"login failed: {result.strip()}")
        time.sleep(1)
    station = window.dialog("Ace of Angels (v2.9.2 Beta)", 30)
    if not station:
        raise RuntimeError("Station dialog did not appear")
    time.sleep(1)
    window.press(station, 1012)
    client = client_mem.Client()
    while time.monotonic() < deadline:
        try:
            player = client.player()
            if player and client.read(player + 0x243, 1)[0] and window.main_window():
                return client
        except OSError:
            pass
        time.sleep(0.25)
    raise RuntimeError("flight entry timed out")


class Pilots(threading.Thread):
    """bot.py pilots flown from this process so their paths share the shot's clock."""

    def __init__(self, spec):
        super().__init__(daemon=True)
        key = (GAME / "SCRTY.BIN").read_bytes()
        self.pilots = [bot.Pilot(key, f"Wing{i + 1}", p["hull"], p["path"]) for i, p in enumerate(spec)]
        self.start_at = None
        self.stop = False

    def login(self):
        for pilot in self.pilots:
            pilot.login()
            pilot.send(bot.ARENA, 0xA0, bot.hull_request(pilot.hull))

    def run(self):
        tick, next_send = 1 / bot.RATE, time.monotonic()
        while not self.stop:
            for pilot in self.pilots:
                pilot.pump()
            now = time.monotonic()
            if now >= next_send:
                t = 0.0 if self.start_at is None else max(0.0, now - self.start_at)
                for pilot in self.pilots:
                    pilot.send(bot.ARENA, 0x1F, bot.movement(pilot.slot, *bot.path_state(pilot.path, t)))
                next_send += tick
            time.sleep(0.002)
        for pilot in self.pilots:
            pilot.send(bot.ARENA, 0x4E, b"\0")


def record(path, seconds, encoder):
    video = (["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "16", "-qp_p", "18"]
             if encoder == "amf" else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16"])
    source = ("gfxcapture=window_exe=(?i)aoaclient:window_class=Afx.*:capture_cursor=0:max_framerate=60,"
              "hwdownload,format=bgra")
    return subprocess.Popen(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                             "-f", "lavfi", "-i", source, "-t", str(seconds), "-r", "60", *video,
                             "-pix_fmt", "yuv420p", str(path)])


def film(shot, index, out, encoder):
    name = f"{index:02d}_{shot['name']}"
    logs = out.parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    kill_clients()
    host = start_host(shot, logs / f"{name}.jsonl")
    pilots = None
    client = None
    report = {"shot": name, "ok": False}
    try:
        for attempt in range(3):
            try:
                client = enter_flight()
                break
            except RuntimeError as error:
                # After a killed session the first launch can show another
                # dialog layout; a fresh launch shows the normal login.
                report.setdefault("retries", []).append(repr(error))
                kill_clients()
        else:
            raise RuntimeError("could not enter flight")
        time.sleep(shot.get("settle", 7))  # terrain, config list and the HUD settle
        if shot.get("pilots"):
            pilots = Pilots(shot["pilots"])
            pilots.login()
            pilots.start()
        hwnd = window.main_window()
        report["foreground"] = window.front(hwnd)
        if shot.get("hud", "clean") == "clean" and report["foreground"]:
            window.hide_hud(hwnd, shot.get("hide", DEFAULT_HIDE))
        client.camera(shot.get("camera", "cockpit"))
        switches = sorted(shot.get("camera_at", []))
        fire = shot.get("fire", [])
        velocity = shot.get("velocity")
        time.sleep(1)
        start = time.monotonic()
        if pilots:
            pilots.start_at = start
        ffmpeg = record(out / f"{name}.mp4", shot["seconds"], encoder)
        firing = False
        while ffmpeg.poll() is None:
            t = time.monotonic() - start
            if velocity:
                client.set_velocity(velocity)
            while switches and switches[0][0] <= t:
                client.camera(switches.pop(0)[1])
            want = any(a <= t < b for a, b in fire)
            if want:
                window.user32.PostMessageW(hwnd, window.WM_KEYDOWN, VK_SPACE,
                                           1 | (window.user32.MapVirtualKeyW(VK_SPACE, 0) << 16)
                                           | ((1 << 30) if firing else 0))
            elif firing:
                window.key(hwnd, VK_SPACE, hold=0)
            firing = want
            time.sleep(0.01)
        report["ok"] = ffmpeg.returncode == 0
        report["ffmpeg"] = ffmpeg.returncode
        report["state_end"] = client.state()["position"]
    except Exception as error:  # one failed shot must not stop the rest
        report["error"] = repr(error)
    finally:
        if client:
            try:
                client.camera("cockpit")
                client.close()
            except OSError:
                pass
        if pilots:
            pilots.stop = True
            pilots.join(2)
        kill_clients()
        stop_host(host)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("shots", type=Path)
    parser.add_argument("--only", nargs="*")
    parser.add_argument("--out", type=Path, default=ROOT / "work/reel/raw")
    parser.add_argument("--encoder", choices=("amf", "x264"), default="amf")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    shots = json.loads(args.shots.read_text())
    keep_awake()
    results = []
    try:
        for index, shot in enumerate(shots, 1):
            if args.only and shot["name"] not in args.only:
                continue
            print(f"[{index}] {shot['name']} on {shot['map']} ...", flush=True)
            results.append(film(shot, index, args.out, args.encoder))
            print(json.dumps(results[-1]), flush=True)
    finally:
        keep_awake(False)
        kill_clients()
    (args.out.parent / "logs/record.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
