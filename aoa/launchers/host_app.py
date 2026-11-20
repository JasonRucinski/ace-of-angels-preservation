"""The host window, "Ace of Angels Host" (Host.cmd): set up, start, share, watch, change map.

View only: the decisions are in hosting.py, catalog.py, netinfo.py and
settings.py; the server runs under the headless host's Supervisor
(restart budget, rotation, recycling). Slow work (address detection,
checks, stopping) runs on tkcommon's worker thread. Errors show a dialog
and go to work/logs/host.log. Nothing here changes the firewall or any
system setting: the firewall lines are shown to copy.

  python -I tools/host_control.py [--autostart] [--demo STATE]

--demo opens a made-up state and starts nothing: setup, advanced, running, error.
"""
import argparse
import collections
import queue
import sys
from pathlib import Path

from aoa.host.config import ConfigError
from aoa.host.supervisor import SupervisorError
from aoa.launchers import catalog, hosting, netinfo, settings as settings_module, tkcommon
from aoa.paths import WORK

TITLE = "Ace of Angels Host"
LOG = tkcommon.LOGS / "host.log"
RUN_FILE = WORK / "host" / "host.json"
DEMOS = ("setup", "advanced", "running", "error")


def map_label(name):
    return catalog.BY_NAME[name].describe()


class HostWindow:
    def __init__(self, root, s, notices=(), demo=None):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.settings, self.demo = root, s, demo
        self.config = s.host
        self.worker = tkcommon.Worker(root.after)
        self.worker.on_busy = self.set_busy
        self.supervisor, self.found, self.events = None, [], queue.Queue()
        self.recent = collections.deque(maxlen=30)
        root.title(TITLE)
        root.minsize(960, 700)
        tkcommon.style(root)
        root.report_callback_exception = lambda *exc: self.fail("Something went wrong in the window.", exc[1])
        root.protocol("WM_DELETE_WINDOW", self.close)

        header = ttk.Frame(root, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.headline = tk.StringVar(value="Stopped")
        ttk.Label(header, textvariable=self.headline, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.body = ttk.Frame(root, padding=(20, 0, 20, 0))
        self.body.pack(fill="both", expand=True)
        self.status = tk.StringVar()
        footer = ttk.Frame(root, padding=(20, 4, 20, 10))
        footer.pack(fill="x", side="bottom")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=920).pack(anchor="w")
        self.build_setup()
        self.build_running()
        self.load_choices()
        self.show_setup()
        for notice in notices:
            tkcommon.log_error(LOG, f"settings: {notice}", RuntimeError(notice))
        if notices:
            self.status.set("Some saved settings could not be used and were reset: " + " ".join(notices))

    # --- shared ----------------------------------------------------------------------
    def set_busy(self, busy):
        self.root.configure(cursor="watch" if busy else "")
        for button in (self.start_button, self.stop_button, self.change_button):
            button.state(["disabled"] if busy else ["!disabled"])

    def fail(self, sentence, error):
        if isinstance(error, ConfigError):
            sentence = str(error)
        tkcommon.log_error(LOG, sentence, error)
        tkcommon.show_error(self.root, TITLE, sentence, tkcommon.details_of(error), LOG)
        self.status.set(sentence)

    def write_log(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 1000:
            self.log.delete("1.0", "200.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def save(self):
        if self.demo:
            return
        try:
            settings_module.save(self.settings)
        except OSError as error:
            self.fail("Your settings could not be saved.", error)

    # --- setup panel -------------------------------------------------------------------
    def build_setup(self):
        ttk, tk = self.ttk, self.tk
        self.setup = ttk.Frame(self.body)
        self.setup.columnconfigure(0, weight=1, uniform="half")
        self.setup.columnconfigure(1, weight=1, uniform="half")
        left = ttk.Frame(self.setup)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = ttk.Frame(self.setup)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        ttk.Label(left, text="Who can join?", style="Heading.TLabel").pack(anchor="w")
        self.audience = tk.StringVar()
        for a in catalog.AUDIENCES:
            ttk.Radiobutton(left, text=a.label, value=a.key, variable=self.audience,
                            command=self.audience_changed).pack(anchor="w", pady=(6, 0))
        self.audience_text = tk.StringVar()
        ttk.Label(left, textvariable=self.audience_text, style="Muted.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(4, 0))

        ttk.Label(left, text="Address", style="Heading.TLabel").pack(anchor="w", pady=(16, 0))
        row = ttk.Frame(left)
        row.pack(fill="x", pady=(4, 0))
        self.address = tk.StringVar()
        self.address_box = ttk.Combobox(row, textvariable=self.address, width=22)
        self.address_box.pack(side="left")
        self.address_box.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.address_box.bind("<FocusOut>", lambda _e: self.changed())
        ttk.Button(row, text="Refresh", command=self.detect).pack(side="left", padx=8)
        self.address_text = tk.StringVar()
        ttk.Label(left, textvariable=self.address_text, style="Muted.TLabel", wraplength=420,
                  justify="left").pack(anchor="w", pady=(4, 0))

        ttk.Label(left, text="Map", style="Heading.TLabel").pack(anchor="w", pady=(16, 0))
        self.map_mode = tk.StringVar(value="one")
        ttk.Radiobutton(left, text="One map", value="one", variable=self.map_mode,
                        command=self.map_mode_changed).pack(anchor="w", pady=(4, 0))
        self.map_one = tk.StringVar()
        self.map_box = ttk.Combobox(left, textvariable=self.map_one, state="readonly", width=48,
                                    values=[map_label(m.name) for m in catalog.PLAYABLE_MAPS])
        self.map_box.pack(anchor="w", padx=(22, 0), pady=(2, 0))
        self.map_box.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        ttk.Radiobutton(left, text="Rotate through several maps (players rejoin between maps)", value="rotate",
                        variable=self.map_mode, command=self.map_mode_changed).pack(anchor="w", pady=(6, 0))
        listed = ttk.Frame(left)
        listed.pack(anchor="w", padx=(22, 0), pady=(2, 0), fill="x")
        self.map_list = tk.Listbox(listed, selectmode="multiple", height=6, exportselection=False, width=48,
                                   activestyle="none")
        for m in catalog.PLAYABLE_MAPS:
            self.map_list.insert("end", map_label(m.name))
        scroll = ttk.Scrollbar(listed, command=self.map_list.yview)
        self.map_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.map_list.pack(side="left", fill="x", expand=True)
        self.map_list.bind("<<ListboxSelect>>", lambda _e: self.changed())

        ttk.Label(right, text="Rules", style="Heading.TLabel").pack(anchor="w")
        rules = ttk.Frame(right)
        rules.pack(anchor="w", pady=(6, 0))
        self.kills, self.minutes, self.players = tk.IntVar(), tk.DoubleVar(), tk.IntVar()
        for column, (text, var, low, high) in enumerate((("Kills to win", self.kills, 0, 1000),
                                                         ("Minutes per match", self.minutes, 0, 1440),
                                                         ("Players", self.players, 1, 8))):
            ttk.Label(rules, text=text).grid(row=0, column=column, sticky="w", padx=(0, 18))
            ttk.Spinbox(rules, from_=low, to=high, textvariable=var, width=7, command=self.changed).grid(
                row=1, column=column, sticky="w", padx=(0, 18), pady=(2, 0))
        ttk.Label(right, text="0 kills or 0 minutes: no limit of that kind.", style="Small.TLabel").pack(
            anchor="w", pady=(4, 0))

        self.advanced_open = tk.BooleanVar(value=False)
        self.advanced_button = ttk.Button(right, text="Advanced ▸", command=self.toggle_advanced)
        self.advanced_button.pack(anchor="w", pady=(16, 0))
        self.advanced = ttk.Frame(right)
        self.build_advanced(self.advanced)

        self.firewall = ttk.LabelFrame(right, text="Firewall", padding=(10, 6))
        self.firewall.pack(fill="x", pady=(16, 0))
        self.firewall_text = tk.StringVar()
        ttk.Label(self.firewall, textvariable=self.firewall_text, wraplength=400, justify="left").pack(anchor="w")
        self.firewall_lines = tk.Text(self.firewall, height=8, wrap="word", font=(
            "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono", 8))
        self.firewall_buttons = ttk.Frame(self.firewall)
        ttk.Button(self.firewall_buttons, text="Copy the commands", style="Accent.TButton",
                   command=lambda: self.copy("\n".join(hosting.firewall_commands(self.config)))).pack(side="right")
        self.show_commands = ttk.Button(self.firewall_buttons, text="Show them", command=self.toggle_commands)
        self.show_commands.pack(side="right", padx=8)

        start_row = ttk.Frame(self.setup)
        start_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.describe = tk.StringVar()
        ttk.Label(start_row, textvariable=self.describe, style="Muted.TLabel").pack(side="left")
        self.start_button = ttk.Button(start_row, text="Start", style="Big.TButton", command=self.start)
        self.start_button.pack(side="right")

    def build_advanced(self, frame):
        ttk, tk = self.ttk, self.tk
        frame.columnconfigure(1, weight=1)
        self.backdrop = tk.StringVar()
        ttk.Label(frame, text="Backdrop").grid(row=0, column=0, sticky="w", pady=2)
        box = ttk.Combobox(frame, textvariable=self.backdrop, state="readonly", width=14,
                           values=[label for _, label in catalog.BACKDROPS])
        box.grid(row=0, column=1, sticky="w", pady=2)
        box.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.targets = tk.IntVar()
        ttk.Label(frame, text="Target ships").grid(row=1, column=0, sticky="w", pady=2)
        spin = ttk.Spinbox(frame, from_=0, to=20, textvariable=self.targets, width=6, command=self.changed)
        spin.grid(row=1, column=1, sticky="w", pady=2)
        tkcommon.Tooltip(spin, "Passive enemy ships ahead of the start point, for target practice. "
                               "They come back 15 s after they are destroyed.")
        self.terrain = tk.BooleanVar()
        check = ttk.Checkbutton(frame, text="Map terrain", variable=self.terrain, command=self.changed)
        check.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)
        tkcommon.Tooltip(check, catalog.feature_sentence("terrain") + " Without it players fly in empty space.")
        self.object_vars, self.object_checks = {}, {}
        for i, (key, label, help_text) in enumerate(catalog.OBJECTS):
            self.object_vars[key] = tk.BooleanVar()
            check = ttk.Checkbutton(frame, text=label, variable=self.object_vars[key], command=self.changed)
            check.grid(row=3 + i, column=0, columnspan=2, sticky="w", pady=1)
            tkcommon.Tooltip(check, help_text)
            self.object_checks[key] = check
        self.object_text = tk.StringVar()
        ttk.Label(frame, textvariable=self.object_text, style="Small.TLabel", wraplength=400, justify="left").grid(
            row=6, column=0, columnspan=2, sticky="w")
        ports = ttk.Frame(frame)
        ports.grid(row=7, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.port_vars = {}
        ttk.Label(ports, text="Ports").grid(row=0, column=0, sticky="w", padx=(0, 8))
        for i, (key, label, help_text) in enumerate((
                ("station", "UDP", "Login (Station) port"), ("arena", "UDP", "Arena (flight) port"),
                ("tcp", "TCP", "Server list port"))):
            self.port_vars[key] = tk.IntVar()
            ttk.Label(ports, text=label).grid(row=0, column=1 + i * 2, sticky="w", padx=(0, 3))
            spin = ttk.Spinbox(ports, from_=1024, to=65535, textvariable=self.port_vars[key], width=6,
                               command=self.changed)
            spin.grid(row=0, column=2 + i * 2, sticky="w", padx=(0, 10))
            tkcommon.Tooltip(spin, help_text)
        folder = ttk.Frame(frame)
        folder.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self.game = tk.StringVar()
        ttk.Label(folder, text="Game folder").pack(side="left")
        ttk.Entry(folder, textvariable=self.game, width=26).pack(side="left", padx=6)
        ttk.Button(folder, text="Browse…", command=self.browse).pack(side="left")

    def toggle_advanced(self):
        self.advanced_open.set(not self.advanced_open.get())
        if self.advanced_open.get():
            self.advanced.pack(fill="x", pady=(6, 0), after=self.advanced_button)
            self.advanced_button.configure(text="Advanced ▾")
        else:
            self.advanced.pack_forget()
            self.advanced_button.configure(text="Advanced ▸")

    def load_choices(self):
        """Settings to widgets."""
        c = self.config
        self.audience.set(hosting.audience(c).key)
        self.address.set("" if hosting.audience(c).kind is None else c.bind_address)
        playable = [m.name for m in catalog.PLAYABLE_MAPS]
        maps = [m for m in c.maps if m in playable] or [playable[0]]
        self.map_mode.set("rotate" if len(maps) > 1 else "one")
        self.map_one.set(map_label(maps[0]))
        self.map_list.selection_clear(0, "end")
        for name in maps:
            self.map_list.selection_set(playable.index(name))
        self.kills.set(c.kill_limit)
        minutes = round(c.time_limit_seconds / 60, 2)
        self.minutes.set(int(minutes) if minutes == int(minutes) else minutes)
        self.players.set(c.max_players)
        self.backdrop.set(dict(catalog.BACKDROPS).get(c.backdrop, c.backdrop))
        self.targets.set(c.target_ships)
        self.terrain.set(c.terrain)
        for key, var in self.object_vars.items():
            var.set(bool(c.objects.get(key)))
        for key, var in self.port_vars.items():
            var.set(c.ports[key])
        self.game.set(self.settings.game_folder)
        self.refresh_setup()

    def read_choices(self):
        """Widgets to settings; ValueError with a sentence when a number is not one."""
        c = self.config
        hosting.set_audience(c, self.audience.get(), self.address.get().split()[0] if self.address.get().strip()
                             else "")
        playable = [m.name for m in catalog.PLAYABLE_MAPS]
        if self.map_mode.get() == "rotate":
            maps = [playable[i] for i in self.map_list.curselection()]
            if len(maps) < 2:
                raise ConfigError("Choose at least two maps to rotate through, or choose One map.")
        else:
            maps = [self.map_one.get().split(":")[0]]
        hosting.set_maps(c, maps)
        try:
            c.kill_limit, c.max_players, c.target_ships = self.kills.get(), self.players.get(), self.targets.get()
            c.time_limit_seconds = int(round(float(self.minutes.get()) * 60))
            for key, var in self.port_vars.items():
                c.ports[key] = var.get()
        except (self.tk.TclError, ValueError):
            raise ConfigError("Kills, minutes, players, target ships and ports must be numbers.") from None
        c.backdrop = {label: name for name, label in catalog.BACKDROPS}.get(self.backdrop.get(), c.backdrop)
        c.terrain = self.terrain.get() or len(maps) > 1
        for key, var in self.object_vars.items():
            c.objects[key] = var.get()
        c.objects["powerups"] = c.terrain
        if self.game.get().strip():
            self.settings.game_folder = self.game.get().strip()
        return c

    def changed(self):
        try:
            self.read_choices()
        except ConfigError as error:
            self.status.set(str(error))
        self.refresh_setup()

    def audience_changed(self):
        chosen = catalog.AUDIENCE[self.audience.get()]
        choices = netinfo.for_kind(self.found, chosen.kind) if chosen.kind else []
        if chosen.kind and self.address.get() not in choices:
            self.address.set(choices[0] if choices else "")
        self.changed()

    def map_mode_changed(self):
        if self.map_mode.get() == "rotate" and len(self.map_list.curselection()) < 2:
            self.map_list.configure(state="normal")
            self.map_list.selection_set(0, 2)
        self.changed()

    def refresh_setup(self):
        c = self.config
        chosen = catalog.AUDIENCE[self.audience.get()]
        self.audience_text.set(chosen.sentence)
        choices = netinfo.for_kind(self.found, chosen.kind) if chosen.kind else []
        self.address_box.configure(values=choices)
        if chosen.kind is None:
            self.address_box.state(["disabled"])
            self.address_text.set("Only this PC: the address is 127.0.0.1.")
        else:
            self.address_box.state(["!disabled"])
            if self.address.get():
                self.address_text.set(f"Players will connect to {self.address.get()}.")
            else:
                self.address_text.set(chosen.no_address)
        one = self.map_mode.get() == "one"
        self.map_box.state(["!disabled"] if one else ["disabled"])
        self.map_list.configure(state="disabled" if one else "normal")
        reasons = catalog.object_availability(c.profile, c.maps, self.terrain.get(),
                                              self.demo is not None or self.export_ready())
        for key, reason in reasons.items():
            self.object_checks[key].state(["disabled"] if reason else ["!disabled"])
        notes = list(dict.fromkeys(r for r in reasons.values() if r))
        self.object_text.set(("Map objects: " + " ".join(notes)) if notes else
                             "Map objects are trials: turret firing stays off.")
        commands = hosting.firewall_commands(c)
        self.firewall_text.set(hosting.firewall_sentence(c))
        self.firewall_lines.configure(state="normal")
        self.firewall_lines.delete("1.0", "end")
        self.firewall_lines.insert("1.0", "\n".join(commands))
        self.firewall_lines.configure(state="disabled")
        if commands:
            self.firewall_buttons.pack(fill="x", pady=(6, 0))
        else:
            self.firewall_buttons.pack_forget()
            self.firewall_lines.pack_forget()
            self.show_commands.configure(text="Show them")
        self.describe.set(hosting.describe(c))

    def toggle_commands(self):
        if self.firewall_lines.winfo_ismapped():
            self.firewall_lines.pack_forget()
            self.show_commands.configure(text="Show them")
        else:
            self.firewall_lines.pack(fill="x", pady=(6, 0), before=self.firewall_buttons)
            self.show_commands.configure(text="Hide them")

    def export_ready(self):
        from aoa.launchers import game_folder
        return game_folder.export_ready(self.config.path("export"))

    def browse(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self.root, title="Choose the folder that holds SCRTY.BIN")
        if chosen:
            self.game.set(chosen)
            self.changed()

    def detect(self):
        def done(found):
            self.found = found
            self.audience_changed()
            self.status.set("")
        self.status.set("Looking for this PC's addresses…")
        if self.demo:
            return
        self.worker.submit(lambda progress: netinfo.addresses(), done,
                           lambda error: self.fail("This PC's addresses could not be read.", error))

    # --- running panel -------------------------------------------------------------------
    def build_running(self):
        ttk, tk = self.ttk, self.tk
        self.running = ttk.Frame(self.body)
        share = ttk.LabelFrame(self.running, text="Tell your players", padding=(10, 8))
        share.pack(fill="x")
        share.columnconfigure(0, weight=1)
        self.share = tk.StringVar()
        ttk.Entry(share, textvariable=self.share, state="readonly", font=(tkcommon.font_family(), 11)).grid(
            row=0, column=0, sticky="ew")
        ttk.Button(share, text="Copy", style="Accent.TButton", command=lambda: self.copy(self.share.get())).grid(
            row=0, column=1, padx=(8, 0))
        self.share_note = tk.StringVar()
        ttk.Label(share, textvariable=self.share_note, style="Small.TLabel", wraplength=880, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.detail = tk.StringVar()
        ttk.Label(self.running, textvariable=self.detail, wraplength=920).pack(anchor="w", pady=(10, 4))
        table_frame = ttk.Frame(self.running)
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=[c[0] for c in hosting.COLUMNS], show="headings", height=6,
                                  selectmode="browse")
        for key, title, width in hosting.COLUMNS:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, anchor="w" if key == "pilot" else "center")
        self.table.pack(fill="both", expand=True)
        actions = ttk.Frame(self.running)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Kick", command=lambda: self.kick(False)).pack(side="left")
        ttk.Button(actions, text="Ban", command=lambda: self.kick(True)).pack(side="left", padx=6)
        ttk.Button(actions, text="End match", command=lambda: self.command("end")).pack(side="left")
        self.say_text = tk.StringVar()
        ttk.Button(actions, text="Send to all", command=self.say).pack(side="right")
        say = ttk.Entry(actions, textvariable=self.say_text, width=36)
        say.pack(side="right", padx=6)
        say.bind("<Return>", lambda _e: self.say())
        ttk.Label(actions, text="Message:").pack(side="right")
        change = ttk.Frame(self.running)
        change.pack(fill="x", pady=(10, 0))
        ttk.Label(change, text="Next map:").pack(side="left")
        self.next_map = tk.StringVar()
        ttk.Combobox(change, textvariable=self.next_map, state="readonly", width=44,
                     values=[map_label(m.name) for m in catalog.PLAYABLE_MAPS]).pack(side="left", padx=6)
        self.change_button = ttk.Button(change, text="Change map", command=self.change_map)
        self.change_button.pack(side="left")
        self.stop_button = ttk.Button(change, text="Stop host", command=self.stop)
        self.stop_button.pack(side="right")
        log_frame = ttk.LabelFrame(self.running, text="Host log", padding=(6, 4))
        log_frame.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(log_frame, height=7, wrap="word", state="disabled",
                           font=("Consolas" if sys.platform == "win32" else "DejaVu Sans Mono", 9))
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)

    def show_setup(self):
        self.running.pack_forget()
        self.setup.pack(fill="both", expand=True)
        self.headline.set("Stopped · choose who can join, then Start")

    def show_running(self, config):
        self.setup.pack_forget()
        self.running.pack(fill="both", expand=True)
        self.share.set(hosting.share_text(config))
        notes = []
        needs = hosting.needs_text(config)
        if needs:
            notes.append(needs)
        if any(catalog.BY_NAME[m].client_file for m in config.maps) and config.terrain:
            notes.append("Every player needs JRMAP's terrain: Play.cmd, Options, Install JRMAP terrain.")
        self.share_note.set(" ".join(notes))
        self.next_map.set(map_label(config.maps[0]))

    def copy(self, text):
        tkcommon.copy_text(self.root, text)
        self.status.set("Copied.")

    # --- actions --------------------------------------------------------------------------------
    def start(self):
        try:
            self.read_choices()
        except ConfigError as error:
            self.fail(str(error), error)
            return
        self.save()
        if self.demo:
            return
        settings = self.settings

        def job(progress):
            progress("Checking the settings…")
            return hosting.check(hosting.run_config(settings))

        self.worker.submit(job, self.launch, lambda error: self.fail("The host cannot start.", error),
                           self.status.set)

    def launch(self, config):
        try:
            config.save(RUN_FILE)  # this run's settings, in the headless host's format
        except OSError:
            pass
        self.supervisor = hosting.supervisor_for(config, report=self.events.put)
        try:
            self.supervisor.load_state()
            self.supervisor.start()
        except (OSError, SupervisorError) as error:
            self.supervisor = None
            self.fail("The host cannot start.", error)
            return
        self.status.set("")
        self.show_running(config)
        self.poll()

    def poll(self):
        if self.supervisor is None:
            return
        if not self.worker.busy:
            process = self.supervisor.process
            try:
                state = self.supervisor.poll()
                failure = None
            except SupervisorError as error:
                state, failure = "stopped", error
            while True:
                try:
                    line = process.output.get_nowait()
                except queue.Empty:
                    break
                self.recent.append(line)
                self.write_log(line)
            if failure is not None:
                self.stopped_with(failure)
            while True:
                try:
                    self.write_log(f"[{self.events.get_nowait()}]")
                except queue.Empty:
                    break
            status, age = process.status()
            self.show_status(status, self.supervisor.config, age)
            if state == "stopped":
                self.supervisor = None
                self.show_setup()
                return
        self.root.after(500, self.poll)

    def stopped_with(self, error):
        """The host gave up: say why in the server's own words when it printed them."""
        sentence = hosting.stop_reason(self.recent) or "The host stopped and was not restarted."
        error.details = "\n".join(self.recent)
        self.fail(sentence, error)

    def show_status(self, status, config, age=None):
        headline, detail = hosting.status_lines(status, config, age)
        self.headline.set(headline)
        self.detail.set(detail)
        chosen = self.table.selection()
        chosen = self.table.item(chosen[0])["values"][0] if chosen else None
        self.table.delete(*self.table.get_children())
        for row in hosting.player_rows(status):
            iid = self.table.insert("", "end", values=row)
            if row[0] == chosen:
                self.table.selection_set(iid)

    def player_count(self):
        status = self.supervisor.process.status()[0] if self.supervisor else None
        return len((status or {}).get("players") or [])

    def command(self, line):
        if self.supervisor is not None and self.supervisor.process.command(line):
            self.write_log(f"[sent: {line}]")

    def kick(self, ban):
        selected = self.table.selection()
        if not selected:
            self.status.set("Choose a player in the table first.")
            return
        slot, pilot = self.table.item(selected[0])["values"][:2]
        word = "Ban" if ban else "Kick"
        extra = " Their address cannot join again until the host restarts." if ban else ""
        if tkcommon.ask(self.root, word, f"{word} {pilot}?{extra}", word):
            self.command(f"{word.lower()} {slot}")

    def say(self):
        text = self.say_text.get().strip()
        if text:
            self.command("say " + text)
            self.say_text.set("")

    def change_map(self):
        if self.supervisor is None:
            return
        name = self.next_map.get().split(":")[0]
        n = self.player_count()
        if n and not tkcommon.ask(self.root, "Change map", f"{n} player(s) will be disconnected. They quit the "
                                                          f"game and rejoin to fly on {name}.", "Change map"):
            return
        self.map_mode.set("one")
        self.map_one.set(map_label(name))
        self.read_choices()
        self.save()
        new = hosting.run_config(self.settings)
        supervisor = self.supervisor

        def job(progress):
            progress(f"Checking {name}, then restarting…")
            hosting.change_map(supervisor, new)
            return new

        self.worker.submit(job, lambda config: (self.show_running(config), self.status.set(f"Now on {name}.")),
                           lambda error: self.fail("The map was not changed.", error), self.status.set)

    def stop(self, then=None):
        if self.supervisor is None:
            return
        n = self.player_count()
        if n and not tkcommon.ask(self.root, "Stop host", f"{n} player(s) will be disconnected.", "Stop host"):
            return
        supervisor = self.supervisor
        self.worker.submit(lambda progress: (progress("Stopping…"), supervisor.stop())[1],
                           lambda code: (self.write_log(f"[host stopped, exit code {code}]"), then and then()),
                           lambda error: self.fail("The host did not stop cleanly.", error), self.status.set)

    def close(self):
        if self.supervisor is not None and not self.demo:
            if tkcommon.ask(self.root, "Close", "Stop the host and close the window?", "Stop and close"):
                self.supervisor.process.stop(5)
            else:
                return
        self.root.destroy()


# --- demo states (made-up data; nothing starts) ------------------------------------------------
DEMO_STATUS = {"map": "CTF_arena", "match": 3, "uptime_s": 1834, "max_players": 8, "arena_joins_used": 7,
               "arena_joins_limit": 49, "banned_ips": 0,
               "players": [{"slot": 2, "pilot": "Raven", "kills": 6, "deaths": 2, "ping_ms": 24, "idle_s": 0,
                            "loaded": True},
                           {"slot": 4, "pilot": "Guest-4", "kills": 3, "deaths": 5, "ping_ms": 61, "idle_s": 2,
                            "loaded": True},
                           {"slot": 5, "pilot": "Kestrel", "kills": 3, "deaths": 1, "ping_ms": None, "idle_s": 40,
                            "loaded": False}]}


def demo(window, name):
    window.found = [("192.168.0.61", "home"), ("100.101.102.103", "vpn")]
    hosting.set_audience(window.config, "home", "192.168.0.61")
    window.load_choices()
    if name == "advanced":
        window.toggle_advanced()
        window.map_mode.set("rotate")
        window.map_mode_changed()
    elif name == "running":
        config = hosting.run_config(window.settings, export_ready=False)
        window.show_running(config)
        window.show_status(DEMO_STATUS, config, 1.0)
        for line in ("Host listening on 192.168.0.61 (UDP 5033, 5031; TCP 5034); map CTF_arena with terrain",
                     "slot 2 Raven joined", "slot 4 Guest-4 joined", "slot 5 Kestrel joined",
                     "match 3 started: 20 kills or 10 minutes"):
            window.write_log(line)
    elif name == "error":
        window.recent.extend([
            "Host I/O failed: [WinError 10049] The requested address is not valid in its context. "
            "Check that 192.168.0.99 belongs to this PC and the ports are free.",
            "[host exited with code 1]"])
        window.stopped_with(SupervisorError("game process exited unexpectedly (1); retaining map CTF_arena"))
        window.root.winfo_children()[-1].toggle_details()


def build(demo_state=None):
    import tkinter as tk
    if demo_state:
        s, notices = settings_module.Settings(), []
    else:
        s, notices = settings_module.load()
    root = tk.Tk()
    window = HostWindow(root, s, notices, demo=demo_state)
    if demo_state:
        demo(window, demo_state)
    else:
        window.detect()
    return root, window


def main(argv=None):
    parser = argparse.ArgumentParser(prog="host_control.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--autostart", action="store_true", help="start the host with the saved settings")
    parser.add_argument("--demo", choices=DEMOS, help="open in a made-up state; nothing starts")
    args = parser.parse_args(argv)

    def start():
        root, window = build(args.demo)
        if args.autostart and not args.demo:
            root.after(300, window.start)
        root.mainloop()
        return 0

    return tkcommon.guard(start, LOG, TITLE)


if __name__ == "__main__":
    sys.exit(main())
