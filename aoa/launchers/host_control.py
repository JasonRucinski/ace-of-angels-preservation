"""One window to run an Ace of Angels host: start, watch, change map, stop.

  .venv/Scripts/python.exe tools/host_control.py [--autostart]

It runs tools/station_stub.py as a child process with --console and
--status-file; the command line comes from aoa/host/config.py (HostConfig)
and the process handling and crash-restart policy from aoa/host/supervisor.py. The window reads the status file every second for the
player/score table and host counters, and sends the server's own console
commands (kick, ban, end, say, quit). "Load map" checks the new settings,
then stops the host cleanly and starts it again on the chosen map; players
must quit and rejoin, because a client builds terrain only once per flight
session.

Modes: this PC only (local-guests on 127.0.0.1, with the guest admission
and sustained delivery LAN and VPN players get), LAN (lan-dogfight) and VPN
(vpn-dogfight). The server validates every setting (--print-config) before
it binds anything. No firewall, hosts-file or client files are changed.
Settings are remembered in work/host/host_control.json, with the mode as its
profile id; a saved value that is not valid falls back to its default with a
notice. Any error that stops the window is shown in a message box and
written to work/logs/host.log.
"""
import argparse
import datetime
import json
import math
import queue
import subprocess
import sys
import time
import traceback
from pathlib import Path

from aoa.host import ops  # noqa: E402
from aoa.maps import registry  # noqa: E402
from aoa.host import supervisor  # noqa: E402
from aoa.host.config import ConfigError, HostConfig  # noqa: E402
from aoa.host.defaults import ALIASES, BACKDROPS, DEFAULT_BACKDROP, LIMITS  # noqa: E402

from aoa.paths import ROOT
from aoa import paths
WORK = ROOT / "work/host"
SETTINGS_FILE = WORK / "host_control.json"
LOG_FILE = ROOT / "work/logs/host.log"
LOCAL = "local-guests"
MODES = {LOCAL: "This PC only", "lan-dogfight": "LAN", "vpn-dogfight": "VPN (internet)"}  # profile -> label
LABELS = {label: profile for profile, label in MODES.items()}  # also reads files saved with labels
DEFAULTS = {"mode": LOCAL, "address": "127.0.0.1", "map": "Arena1a", "terrain": True,
            "backdrop": DEFAULT_BACKDROP, "max_players": LIMITS["max_players"],
            "kill_limit": LIMITS["kill_limit"], "time_limit_min": LIMITS["time_limit_seconds"] // 60,
            "target_ships": 4, "game": "game/2.9.2",
            "navigation_buoys": True, "turret_trial": False, "warp_trial": False}
NODE_LABELS = {"navigation_buoys": "Navigation buoys",
               "turret_trial": "Turret trial (5 turrets, firing disabled; Arena1a)",
               "warp_trial": "Warp gates trial (9 gates; Arena1a, this PC only)"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RESTARTS_PER_10_MIN = supervisor.RESTARTS


def profile_of(mode):
    """The server profile for a saved mode: a profile id, or a display label from older settings."""
    if mode in MODES:
        return mode
    if mode in LABELS:
        return LABELS[mode]
    raise ValueError(f"unknown host mode {mode!r}")


def node_availability(settings):
    """Explain unavailable options consistently in the UI and launch arguments."""
    source = ROOT / 'work/2.9.2/export/AOAOBJECTS'
    common = ("Turn on Build map terrain." if not settings["terrain"] else
              "Original exported map assets are missing." if not (
                  source.is_dir() and (source.parent / '_export.json').is_file()) else "")
    arena = common or ("Select Arena1a." if settings["map"] != "Arena1a" else "")
    return {"navigation_buoys": common, "turret_trial": arena,
            "warp_trial": arena or ("Select This PC only mode." if profile_of(settings["mode"]) != LOCAL else "")}


def host_config(settings, extra=()):
    """The HostConfig of the window's settings; options the window shows as unavailable are left out."""
    profile = profile_of(settings["mode"])
    address = "127.0.0.1" if profile == LOCAL else settings["address"].strip()
    enabled = [key for key, reason in node_availability(settings).items()
               if not reason and settings.get(key, DEFAULTS[key])] if settings["terrain"] else []
    objects = {**dict.fromkeys(NODE_LABELS, False), **dict.fromkeys(enabled, True),
               # The map's own power-up zones (findings 9.44); layouts have none.
               "powerups": bool(settings["terrain"])}
    return HostConfig(profile=profile, bind_address=address, maps=[settings["map"]], backdrop=settings["backdrop"],
                      terrain=bool(settings["terrain"]), max_players=int(settings["max_players"]),
                      kill_limit=int(settings["kill_limit"]),
                      time_limit_seconds=int(float(settings["time_limit_min"]) * 60),
                      target_ships=int(settings["target_ships"]), objects=objects,
                      sustained_delivery=True if enabled or profile == LOCAL else None, console=True,
                      paths={"game": settings["game"], "log": str(WORK / f"{profile}.jsonl"),
                             "status": str(status_path(settings)), "export": str(ROOT / 'work/2.9.2/export/AOAOBJECTS')},
                      extra_args=list(extra), root=ROOT)


def server_args(settings, extra=()):
    """The server script and its arguments for these settings (HostConfig.to_argv)."""
    return [str(paths.entry("station_stub", ROOT)), *host_config(settings, extra).to_argv()]


def status_path(settings):
    return ops.status_path(profile_of(settings["mode"]), WORK)


def detect_addresses():
    """[(ipv4, adapter)] for this PC's preferred addresses (Windows only)."""
    command = ("Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
               "Where-Object { $_.AddressState -eq 'Preferred' -and $_.IPAddress -ne '127.0.0.1' } | "
               "ForEach-Object { $_.IPAddress + '|' + $_.InterfaceAlias }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", command], capture_output=True, text=True,
                             timeout=15, creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [tuple(line.split("|", 1)) for line in out.splitlines() if "|" in line]


class HostProcess(supervisor.HostProcess):
    """The server child process for the window's settings: validated start, commands, clean stop."""

    def __init__(self):
        super().__init__(script=paths.entry("station_stub", ROOT), cwd=ROOT)
        self.settings = None

    def validate(self, settings, extra=()):
        """The server's own checks, in process (HostConfig.validate)."""
        try:
            host_config(settings, extra).validate(key=False)
        except ConfigError as error:
            raise ValueError(str(error)) from None

    def check(self, settings, extra=()):
        """Everything start() checks, without starting: files, then the server's own validation."""
        game = Path(settings["game"])
        game = game if game.is_absolute() else ROOT / game
        if not (game / "SCRTY.BIN").is_file():
            raise ValueError(f"no SCRTY.BIN in {game}")
        if settings["terrain"] and settings["map"] == "JRMAP" and not (game / "jrmap292.trn").is_file():
            raise ValueError(f"JRMAP needs: python -I tools/map_viewer.py install {settings['game']}")
        self.validate(settings, extra)

    def start(self, settings, extra=(), checked=False):
        if self.running:
            raise RuntimeError("host already running")
        if not checked:
            self.check(settings, extra)
        WORK.mkdir(parents=True, exist_ok=True)
        super().start(host_config(settings, extra))
        self.settings = dict(settings)


def valid_setting(key, value):
    """Whether a saved value can be used for this setting (the window's own ranges)."""
    if key in ("terrain", *NODE_LABELS):
        return type(value) is bool
    choices = {"mode": MODES, "map": registry.MAP_NAMES, "backdrop": BACKDROPS}
    if key in choices:
        return isinstance(value, str) and value in choices[key]
    if key in ("address", "game"):
        return isinstance(value, str) and (key == "address" or bool(value.strip()))
    if key == "time_limit_min":
        return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1440
    low, high = {"max_players": (1, 8), "kill_limit": (0, 1000), "target_ships": (0, 20)}[key]
    return type(value) is int and low <= value <= high


def load_map(host, settings, extra=(), notice_seconds=0.5):
    """Restart `host` on new settings. They are checked first: if they are invalid,
    this raises before anything is announced or stopped, and the host keeps running."""
    host.check(settings, extra)
    host.command(f"say Host is switching to {settings['map']}. Quit the game and rejoin in a minute.")
    time.sleep(notice_seconds)
    host.stop()
    host.start(settings, extra, checked=True)


def load_settings(notices=None):
    """Saved settings, each checked; anything unusable becomes its default and adds a line to `notices`."""
    notices = [] if notices is None else notices
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (OSError, ValueError) as error:
        notices.append(f"Could not read {SETTINGS_FILE} ({error}); using the default settings.")
        return dict(DEFAULTS)
    if not isinstance(saved, dict):
        notices.append(f"{SETTINGS_FILE} does not hold settings; using the default settings.")
        return dict(DEFAULTS)
    loaded = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key not in saved:
            continue
        value = saved[key]
        if key == "mode" and isinstance(value, str):
            value = LABELS.get(value, value)  # files saved before profile ids
        if valid_setting(key, value):
            loaded[key] = value
        else:
            notices.append(f"Saved {key.replace('_', ' ')} {saved[key]!r} is not valid; using {default!r}.")
    return loaded


def save_settings(settings):
    WORK.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=1), encoding="utf-8")


def gui(autostart=False, run=True):
    import tkinter as tk
    from tkinter import messagebox, ttk

    host = HostProcess()
    root = tk.Tk()
    root.title("Ace of Angels host")
    root.minsize(860, 640)

    def report(*exc):
        log_error("host window callback failed", exc)
        messagebox.showerror("Ace of Angels host", f"{exc[1]}\n\nDetails: {LOG_FILE}")

    root.report_callback_exception = report
    notices = []
    saved = load_settings(notices)
    addresses = detect_addresses()
    v = {"mode": tk.StringVar(value=MODES[saved["mode"]]), "address": tk.StringVar(value=saved["address"]),
         "map": tk.StringVar(value=saved["map"]), "terrain": tk.BooleanVar(value=saved["terrain"]),
         "backdrop": tk.StringVar(value=saved["backdrop"]), "max_players": tk.IntVar(value=saved["max_players"]),
         "kill_limit": tk.IntVar(value=saved["kill_limit"]), "time_limit_min": tk.DoubleVar(value=saved["time_limit_min"]),
         "target_ships": tk.IntVar(value=saved["target_ships"]),
         "game": tk.StringVar(value=saved["game"])}
    v.update({key: tk.BooleanVar(value=saved[key]) for key in NODE_LABELS})
    budget = supervisor.RestartBudget()

    def settings():
        out = {}
        for key, var in v.items():
            try:
                out[key] = var.get()
            except tk.TclError:
                raise ValueError(f"{key.replace('_', ' ')} must be a number")
        out["address"] = out["address"].split()[0] if out["address"].strip() else ""
        out["mode"] = LABELS[out["mode"]]
        return out

    # Server settings
    box = ttk.LabelFrame(root, text="Server", padding=8)
    box.pack(fill="x", padx=8, pady=(8, 4))
    row = 0
    ttk.Label(box, text="Mode").grid(row=row, column=0, sticky="w")
    mode = ttk.Combobox(box, textvariable=v["mode"], values=list(LABELS), state="readonly", width=16)
    mode.grid(row=row, column=1, sticky="w", padx=4)
    ttk.Label(box, text="Host address").grid(row=row, column=2, sticky="w", padx=(12, 0))
    address = ttk.Combobox(box, textvariable=v["address"], width=34,
                           values=[f"{ip}  ({alias})" for ip, alias in addresses])
    address.grid(row=row, column=3, columnspan=3, sticky="w", padx=4)
    row += 1
    ttk.Label(box, text="Map").grid(row=row, column=0, sticky="w", pady=(6, 0))
    ttk.Combobox(box, textvariable=v["map"], values=list(registry.MAP_NAMES), state="readonly",
                 width=16).grid(row=row, column=1, sticky="w", padx=4, pady=(6, 0))
    ttk.Checkbutton(box, text="Build map terrain (clients need patch v11)", variable=v["terrain"]).grid(
        row=row, column=2, columnspan=2, sticky="w", padx=(12, 0), pady=(6, 0))
    ttk.Label(box, text="Backdrop").grid(row=row, column=4, sticky="e", pady=(6, 0))
    ttk.Combobox(box, textvariable=v["backdrop"], values=BACKDROPS, state="readonly", width=11).grid(
        row=row, column=5, sticky="w", padx=4, pady=(6, 0))
    row += 1
    ttk.Label(box, text="Max players").grid(row=row, column=0, sticky="w", pady=(6, 0))
    ttk.Spinbox(box, from_=1, to=8, textvariable=v["max_players"], width=5).grid(row=row, column=1, sticky="w",
                                                                                  padx=4, pady=(6, 0))
    ttk.Label(box, text="Kill limit (0 = none)").grid(row=row, column=2, sticky="w", padx=(12, 0), pady=(6, 0))
    ttk.Spinbox(box, from_=0, to=1000, textvariable=v["kill_limit"], width=6).grid(row=row, column=3, sticky="w",
                                                                                    padx=4, pady=(6, 0))
    ttk.Label(box, text="Time limit, min").grid(row=row, column=4, sticky="e", pady=(6, 0))
    ttk.Spinbox(box, from_=0, to=1440, textvariable=v["time_limit_min"], width=6).grid(row=row, column=5,
                                                                                        sticky="w", padx=4, pady=(6, 0))
    row += 1
    ttk.Label(box, text="Target ships").grid(row=row, column=0, sticky="w", pady=(6, 0))
    ttk.Spinbox(box, from_=0, to=20, textvariable=v["target_ships"], width=5).grid(row=row, column=1, sticky="w",
                                                                                    padx=4, pady=(6, 0))
    ttk.Label(box, text="passive hostile ships 12 km ahead of the spawn; guns and missiles destroy them and "
                        "they return after 15 s", foreground="#555").grid(row=row, column=2, columnspan=4, sticky="w",
                                                             padx=(12, 0), pady=(6, 0))
    row += 1
    ttk.Label(box, text="Game folder").grid(row=row, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(box, textvariable=v["game"], width=30).grid(row=row, column=1, columnspan=2, sticky="w",
                                                          padx=4, pady=(6, 0))
    buttons = ttk.Frame(box)
    buttons.grid(row=row, column=3, columnspan=3, sticky="e", pady=(6, 0))
    start_b = ttk.Button(buttons, text="Start host")
    load_b = ttk.Button(buttons, text="Load map (restart)")
    stop_b = ttk.Button(buttons, text="Stop host")
    for b in (start_b, load_b, stop_b):
        b.pack(side="left", padx=3)
    hint = ttk.Label(box, foreground="#555", wraplength=820, justify="left")
    hint.grid(row=row + 1, column=0, columnspan=6, sticky="w", pady=(6, 0))

    nodes_box = ttk.LabelFrame(root, text="Map objects", padding=8)
    nodes_box.pack(fill="x", padx=8, pady=4)
    node_checks = {}
    for key, label in NODE_LABELS.items():
        node_checks[key] = ttk.Checkbutton(nodes_box, text=label, variable=v[key])
        node_checks[key].pack(anchor="w")
    ttk.Label(nodes_box, text="Apply with Start host or Load map (restart). Players must rejoin.",
              foreground="#555").pack(anchor="w", pady=(4, 0))
    node_hint = ttk.Label(nodes_box, foreground="#555", wraplength=820, justify="left")
    node_hint.pack(anchor="w")

    # Live status
    info = ttk.LabelFrame(root, text="Status", padding=8)
    info.pack(fill="x", padx=8, pady=4)
    status_text = tk.StringVar(value="Stopped")
    ttk.Label(info, textvariable=status_text, font=("Segoe UI", 10, "bold")).pack(anchor="w")
    detail_text = tk.StringVar(value="")
    ttk.Label(info, textvariable=detail_text, wraplength=820, justify="left").pack(anchor="w")

    # Players and scores
    table_box = ttk.LabelFrame(root, text="Players (sorted by kills)", padding=8)
    table_box.pack(fill="both", expand=True, padx=8, pady=4)
    columns = (("slot", "Slot", 45), ("pilot", "Pilot", 170), ("kills", "Kills", 55), ("deaths", "Deaths", 60),
               ("ping", "Ping ms", 70), ("in", "In kbps", 70), ("out", "Out kbps", 70), ("idle", "Idle s", 60),
               ("flying", "In flight", 70))
    table = ttk.Treeview(table_box, columns=[c[0] for c in columns], show="headings", height=8, selectmode="browse")
    for key, title, width in columns:
        table.heading(key, text=title)
        table.column(key, width=width, anchor="w" if key == "pilot" else "center")
    table.pack(fill="both", expand=True)
    actions = ttk.Frame(table_box)
    actions.pack(fill="x", pady=(6, 0))
    kick_b = ttk.Button(actions, text="Kick selected")
    ban_b = ttk.Button(actions, text="Ban selected")
    end_b = ttk.Button(actions, text="End match")
    for b in (kick_b, ban_b, end_b):
        b.pack(side="left", padx=3)
    say_text = tk.StringVar()
    say_entry = ttk.Entry(actions, textvariable=say_text, width=40)
    say_b = ttk.Button(actions, text="Send message to all")
    say_b.pack(side="right", padx=3)
    say_entry.pack(side="right", padx=3)

    # Server output
    log_box = ttk.LabelFrame(root, text="Host log", padding=8)
    log_box.pack(fill="both", expand=True, padx=8, pady=(4, 8))
    log = tk.Text(log_box, height=10, wrap="word", state="disabled", font=("Consolas", 9))
    scroll = ttk.Scrollbar(log_box, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    log.pack(fill="both", expand=True)

    def write_log(line):
        log.configure(state="normal")
        log.insert("end", line + "\n")
        if int(log.index("end-1c").split(".")[0]) > 1000:
            log.delete("1.0", "200.0")
        log.see("end")
        log.configure(state="disabled")

    def player_count():
        data, _ = host.status()
        return len(data.get("players", [])) if data else 0

    def refresh_controls():
        running = host.running
        start_b.state(["disabled"] if running else ["!disabled"])
        for b in (stop_b, load_b, end_b, say_b, kick_b, ban_b):
            b.state(["!disabled"] if running else ["disabled"])
        profile = LABELS[v["mode"].get()]
        availability = node_availability({"terrain": v["terrain"].get(), "map": v["map"].get(), "mode": profile})
        for key, reason in availability.items():
            node_checks[key].state(["disabled"] if reason else ["!disabled"])
            if reason:
                v[key].set(False)
        reasons = list(dict.fromkeys(reason for reason in availability.values() if reason))
        node_hint.configure(text="Unavailable options: " + " ".join(reasons) if reasons else
                            "Trials are experimental; turret firing stays disabled.")
        address.state(["disabled"] if profile == LOCAL else ["!disabled"])
        if profile == LOCAL:
            hint.configure(text="Only clients on this PC can join: log in to 127.0.0.1. "
                                "Prepare the client with --station localhost.")
        else:
            alias = ALIASES[profile]
            ip = v["address"].get().split()[0] if v["address"].get().strip() else "<host address>"
            hint.configure(text=f"Players: hosts-file line '{ip} {alias}', client prepared with --station {alias}, "
                                f"firewall open for UDP 5033 + 5031 and TCP 5034 "
                                f"(docs/{'vpn' if profile == 'vpn-dogfight' else 'lan'}-dogfight.md).")

    def do_start(quiet=False, crashed=None):
        """Start on the window's settings, or on `crashed`, the settings of a run that crashed."""
        try:
            s = crashed or settings()
            host.start(s)
        except (ValueError, RuntimeError, OSError) as error:
            if not quiet:
                messagebox.showerror("Cannot start host", str(error))
            write_log(f"[not started: {error}]")
            return False
        if crashed is None:
            save_settings(s)
        try:
            host.config.save(WORK / "host.json")  # the run's HostConfig, the headless host's format
        except OSError:
            pass
        write_log(f"[starting {MODES[s['mode']]} host: map {s['map']}{' with terrain' if s['terrain'] else ''}]")
        refresh_controls()
        return True

    def confirm_disconnect(action):
        n = player_count()
        return n == 0 or messagebox.askyesno(
            action, f"{n} player(s) will be disconnected and must quit the game and rejoin. Continue?")

    def do_stop():
        if not confirm_disconnect("Stop host"):
            return
        write_log("[stopping host]")
        root.config(cursor="watch")
        root.update_idletasks()
        code = host.stop()
        root.config(cursor="")
        write_log(f"[host stopped, exit code {code}]")
        refresh_controls()

    def do_load_map():
        new = v["map"].get()
        if not confirm_disconnect(f"Load {new}"):
            return
        try:
            s = settings()
            write_log(f"[switching map to {new}]")
            load_map(host, s)
        except (ValueError, RuntimeError, OSError) as error:
            messagebox.showerror("Cannot load map", str(error))
            write_log(f"[map not changed: {error}]" if host.running else f"[not started: {error}]")
            refresh_controls()
            return
        save_settings(s)
        write_log(f"[starting {MODES[s['mode']]} host: map {s['map']}{' with terrain' if s['terrain'] else ''}]")
        refresh_controls()

    def selected_slot():
        item = table.selection()
        if not item:
            messagebox.showinfo("No player selected", "Select a player in the table first.")
            return None
        return table.item(item[0])["values"][0]

    def do_kick(ban=False):
        slot = selected_slot()
        if slot is None:
            return
        word = "Ban" if ban else "Kick"
        extra = " Their IP is refused until the host restarts." if ban else ""
        if messagebox.askyesno(word, f"{word} the player in slot {slot}?{extra}"):
            host.command(f"{word.lower()} {slot}")

    def do_say(_event=None):
        text = say_text.get().strip()
        if text and host.command("say " + text):
            say_text.set("")

    start_b.configure(command=do_start)
    stop_b.configure(command=do_stop)
    load_b.configure(command=do_load_map)
    kick_b.configure(command=do_kick)
    ban_b.configure(command=lambda: do_kick(True))
    end_b.configure(command=lambda: host.command("end"))
    say_b.configure(command=do_say)
    say_entry.bind("<Return>", do_say)
    mode.bind("<<ComboboxSelected>>", lambda _e: refresh_controls())
    address.bind("<<ComboboxSelected>>", lambda _e: refresh_controls())
    for key in ("mode", "map", "terrain"):
        v[key].trace_add("write", lambda *_args: refresh_controls())

    def poll_output():
        while True:
            try:
                write_log(host.output.get_nowait())
            except queue.Empty:
                break
        if host.proc is not None and not host.running and not host.stopping:
            code = host.proc.returncode
            host.stopping = True
            uptime = time.time() - host.started if host.started else 0
            if code and budget.allow(uptime, time.monotonic()):
                crashed = dict(host.settings)  # restart as it ran, not with later edits in the window
                write_log(f"[host crashed with code {code}; restarting in {budget.delay:g} s, players must rejoin]")
                root.after(int(budget.delay * 1000), lambda: do_start(quiet=True, crashed=crashed))
            elif code:
                write_log(f"[host stopped with code {code}; not restarting]")
            refresh_controls()
        root.after(250, poll_output)

    def poll_status():
        data, age = host.status()
        running = host.running
        if not running:
            status_text.set("Stopped")
            detail_text.set("" if host.proc is None else "Last run's final status is shown below.")
        elif data is None:
            status_text.set("Starting…")
        else:
            uptime = int(data.get("uptime_s", 0))
            stale = " — STATUS NOT UPDATING, host may be stuck" if age is not None and age > 8 else ""
            status_text.set(f"Running: {MODES[host.settings['mode']]} on map {data.get('map')}"
                            f"{' (terrain on)' if host.settings['terrain'] else ''}, "
                            f"match {data.get('match')}, up {uptime // 3600}:{uptime % 3600 // 60:02}:{uptime % 60:02}"
                            + stale)
            traffic = data.get("traffic") or {}
            detail_text.set(
                f"Players {len(data.get('players', []))}/{data.get('max_players')}   "
                f"Arena joins used {data.get('arena_joins_used')}/{data.get('arena_joins_limit')}   "
                f"Station logins {data.get('station_sessions')} "
                f"(admissions {data.get('station_admissions_used')}/{data.get('station_admissions_limit')})   "
                f"Banned IPs {data.get('banned_ips')}   "
                + "   ".join(f"{k} {v}" for k, v in traffic.items() if isinstance(v, (int, float)))
                + ("   TEST IMPAIRMENT ON" if data.get("impairment") else ""))
            detail_text.set(detail_text.get() +
                            f"\nMap objects: {data.get('navigation_buoys', 0)} buoys, "
                            f"{(data.get('turret_trial') or {}).get('objects', 0)} trial turrets (firing disabled), "
                            f"{(data.get('warp_trial') or {}).get('objects', 0)} trial warp gates")
        if data is not None:
            chosen = table.selection()
            chosen = table.item(chosen[0])["values"][0] if chosen else None
            table.delete(*table.get_children())
            for p in sorted(data.get("players", []), key=lambda p: (-p["kills"], p["deaths"], p["slot"])):
                iid = table.insert("", "end", values=(
                    p["slot"], p["pilot"], p["kills"], p["deaths"],
                    "-" if p.get("ping_ms") is None else p["ping_ms"], p.get("in_kbps"), p.get("out_kbps"),
                    p.get("idle_s"), "yes" if p.get("loaded") else "no"))
                if p["slot"] == chosen:
                    table.selection_set(iid)
        refresh_controls()
        root.after(1000, poll_status)

    def on_close():
        if host.running:
            if not messagebox.askyesno("Quit", "Stop the host and close?"):
                return
            host.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    refresh_controls()
    for notice in notices:
        write_log(f"[settings: {notice}]")
    if notices:
        root.after(300, lambda: messagebox.showwarning("Saved settings not used", "\n".join(notices)))
    if autostart:
        root.after(200, do_start)
    poll_output()
    poll_status()
    if not run:  # tests drive the real widgets; the caller pumps root.update()
        return {"root": root, "host": host, "vars": v, "table": table, "log": log, "status": status_text,
                "buttons": {"start": start_b, "load": load_b, "stop": stop_b, "kick": kick_b, "ban": ban_b,
                            "end": end_b, "say": say_b}, "say_text": say_text, "node_checks": node_checks}
    root.mainloop()


def log_error(context, exc=None):
    """Append a traceback (the current exception, or `exc` info) to work/logs/host.log."""
    text = "".join(traceback.format_exception(*exc)) if exc else traceback.format_exc()
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as stream:
            stream.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {context}\n{text}\n")
    except OSError:
        print(text, file=sys.stderr)


def show_error(title, text):
    """A message box; stderr when Tk cannot open one (pythonw has no console)."""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, text, parent=root)
        root.destroy()
    except Exception:  # noqa: BLE001
        print(f"{title}: {text}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--autostart", action="store_true", help="start the host with the saved settings")
    args = parser.parse_args(argv)
    try:
        gui(autostart=args.autostart)
    except Exception as error:  # noqa: BLE001 - under pythonw nothing else would report it
        log_error("host window failed")
        show_error("Ace of Angels host", f"The host window stopped: {error}\n\nDetails: {LOG_FILE}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
