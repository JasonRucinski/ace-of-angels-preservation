"""The player window, "Ace of Angels" (Play.cmd): setup checklist, Play, Join a friend, Options.

View only: every decision is in install.py, join.py, game_folder.py,
catalog.py, settings.py and client_launcher.py (options, apply with
rollback). Slow work (hashing, prepare, downloads, checks) runs on the
tkcommon.Worker thread. Errors show a dialog and go to work/logs/launcher.log.

  python -I tools/client_launcher.py [GAME_FOLDER] [--demo STATE]

--demo opens the window in a named state with made-up data and changes
nothing (for screenshots and smoke tests): checklist, play, join, options,
error.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from aoa.client import prepare
from aoa.launchers import catalog, client_launcher, game_folder, install, join, settings as settings_module
from aoa.launchers import tkcommon
from aoa.launchers.install import Status
from aoa.paths import ROOT

TITLE = "Ace of Angels"
LOG = tkcommon.LOGS / "launcher.log"
DEMOS = ("checklist", "play", "join", "options", "error")
THIS_PC = "This PC"
SHOWN_OPTIONS = [o for o in catalog.OPTIONS if o.key != "experimental_protection"]


class PlayWindow:
    def __init__(self, root, s, notices=(), demo=None):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.root, self.settings, self.demo = root, s, demo
        self.worker = tkcommon.Worker(root.after)
        self.worker.on_busy = self.set_busy
        self.context = install.Context(s)
        self.state, self.rows, self.options, self.available = None, [], {}, {}
        self.loaded_options = {}
        self.forced_setup = False
        root.title(TITLE)
        root.minsize(800, 640)
        root.geometry("820x720")
        tkcommon.style(root)
        root.report_callback_exception = lambda *exc: self.fail("Something went wrong in the window.", exc[1])

        header = ttk.Frame(root, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.summary = tk.StringVar(value="Looking at your game…")
        ttk.Label(header, textvariable=self.summary, style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.setup_button = ttk.Button(header, text="Setup", command=self.show_setup)
        self.setup_button.grid(row=0, column=1, rowspan=2, sticky="e")
        self.body = ttk.Frame(root, padding=(20, 4, 20, 8))
        self.body.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="")
        footer = ttk.Frame(root, padding=(20, 0, 20, 12))
        footer.pack(fill="x", side="bottom")
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", wraplength=740).pack(anchor="w")

        self.build_checklist()
        self.build_tabs()
        for notice in notices:
            tkcommon.log_error(LOG, f"settings: {notice}", RuntimeError(notice))
        if notices:
            self.status.set("Some saved settings could not be used and were reset: " + " ".join(notices))

    # --- shared ------------------------------------------------------------------
    def set_busy(self, busy):
        self.root.configure(cursor="watch" if busy else "")
        for button in self.action_buttons():
            try:
                button.state(["disabled"] if busy else ["!disabled"])
            except self.tk.TclError:
                pass
        if not busy:
            self.update_buttons()

    def action_buttons(self):
        return [self.play_button, self.apply_button, self.check_button, *self.step_buttons]

    def fail(self, sentence, error):
        if isinstance(error, install.StepError):
            sentence = str(error)
        tkcommon.log_error(LOG, sentence, error)
        tkcommon.show_error(self.root, TITLE, sentence, tkcommon.details_of(error), LOG)
        self.status.set(sentence)

    def run(self, job, done=None, sentence="That did not work.", refresh=True):
        if self.demo:
            self.status.set("Demo: nothing was changed.")
            return

        def finished(result):
            if done:
                done(result)
            if refresh:
                self.refresh()

        def failed(error):
            self.fail(sentence, error)
            if refresh:
                self.refresh()

        self.worker.submit(job, finished, failed, self.status.set)

    def save_settings(self):
        if self.demo:
            return
        try:
            settings_module.save(self.settings)
        except OSError as error:
            self.fail("Your settings could not be saved.", error)

    # --- loading ---------------------------------------------------------------------
    def refresh(self):
        def job(progress):
            progress("Looking at your game…")
            state = self.context.refresh()
            rows = install.checklist(self.context)
            options, available = {}, {}
            if state.ready:
                options, available = client_launcher.read_settings(state.folder)
            return state, rows, options, available

        def done(result):
            self.show(*result)
            if self.status.get() == "Looking at your game…":
                self.status.set("")

        self.worker.submit(job, done, lambda error: self.fail("Your game folder could not be read.", error),
                           self.status.set)

    def show(self, state, rows, options, available):
        self.state, self.rows, self.options, self.available = state, rows, options, available
        self.loaded_options = dict(options)
        self.fill_checklist()
        self.fill_play()
        self.fill_options()
        if self.forced_setup or not install.complete(rows):
            self.tabs.pack_forget()
            self.setup_button.grid_remove()
            self.checklist.pack(fill="both", expand=True)
        else:
            self.checklist.pack_forget()
            self.setup_button.grid()
            self.tabs.pack(fill="both", expand=True)
        self.summary.set(self.summary_text())
        self.update_buttons()

    def summary_text(self):
        state = self.state
        if state is None or not state.ready:
            return "Not ready yet: follow the setup steps."
        parts = [f"Game ready · patch level {state.patch_level}",
                 "wrapper on" if state.wrapper == "installed" else "no wrapper"]
        if self.options.get("texture_pack"):
            parts.append("texture pack on")
        return " · ".join(parts)

    # --- setup checklist ----------------------------------------------------------------
    def build_checklist(self):
        ttk, tk = self.ttk, self.tk
        self.checklist = ttk.Frame(self.body)
        ttk.Label(self.checklist, text="Get the game ready", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(self.checklist, text="Do the steps in order. Each one shows what it will do before it does it.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 10))
        self.rows_frame = ttk.Frame(self.checklist)
        self.rows_frame.pack(fill="x")
        self.rows_frame.columnconfigure(1, weight=1)
        self.step_buttons = []
        bottom = ttk.Frame(self.checklist)
        bottom.pack(fill="x", side="bottom", pady=(10, 0))
        self.done_button = ttk.Button(bottom, text="Done: go to Play", style="Accent.TButton",
                                      command=self.leave_setup)
        self.done_button.pack(side="right")
        self.folder_label = tk.StringVar()
        ttk.Label(bottom, textvariable=self.folder_label, style="Small.TLabel").pack(side="left")

    def step_actions(self, step, status):
        """[(button text, command)] for one checklist row."""
        key = step.key
        if key == "files":
            actions = [("Find my game folder…", self.choose_folder)]
            if status.state != "done":
                size = install.size_text(install.installer_entry()["bytes"])
                actions.append((f"Download ({size})", self.download))
            return actions
        if key == "folder" and status.state == "todo":
            if self.state is not None and self.state.exists:
                return [("Choose another folder…", self.choose_folder)]
            return [("Unpack the game", lambda: self.run_step(step, "The game could not be unpacked."))]
        if key == "fixes" and status.state == "todo":
            return [("Apply the fixes", lambda: self.run_step(step, "The fixes could not be applied."))]
        if key == "skin" and status.state == "todo":
            return [("Register", lambda: self.run_step(step, "The login screen skin could not be registered."))]
        if key == "wrapper" and status.state in ("optional", "todo", "skipped"):
            actions = [("Open the download page", lambda: install.open_page(step.page())),
                       ("I've downloaded it", lambda: self.run_step(step, "The wrapper could not be installed."))]
            if status.state == "optional":
                actions.append(("Skip", self.skip_wrapper))
            return actions
        return []

    def fill_checklist(self):
        ttk, tk = self.ttk, self.tk
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self.step_buttons = []
        for i, (step, status) in enumerate(self.rows):
            tk.Label(self.rows_frame, text=tkcommon.GLYPH[status.state], fg=tkcommon.COLOR[status.state],
                     font=(tkcommon.font_family(), 15, "bold"), width=2,
                     bg=self.root.cget("background")).grid(row=i, column=0, sticky="nw", pady=(8, 0))
            words = ttk.Frame(self.rows_frame)
            words.grid(row=i, column=1, sticky="nw", pady=(10, 6))
            ttk.Label(words, text=f"{i + 1}. {step.title}", style="Heading.TLabel").pack(anchor="w")
            ttk.Label(words, text=status.text, wraplength=480, justify="left").pack(anchor="w", pady=(2, 0))
            buttons = ttk.Frame(self.rows_frame)
            buttons.grid(row=i, column=2, sticky="ne", pady=(10, 6), padx=(12, 0))
            for text, command in self.step_actions(step, status):
                button = ttk.Button(buttons, text=text, command=command)
                button.pack(fill="x", pady=2)
                self.step_buttons.append(button)
        self.folder_label.set(f"Game folder: {self.settings.game_path()}")

    def run_step(self, step, sentence):
        self.run(lambda progress: step.run(progress), sentence=sentence)

    def choose_folder(self):
        from tkinter import filedialog
        chosen = filedialog.askdirectory(parent=self.root, initialdir=str(self.settings.game_path().parent),
                                         title="Choose the folder that holds AOACLIENT.EXE")
        if not chosen:
            return
        if not (Path(chosen) / game_folder.EXE).is_file():
            tkcommon.show_error(self.root, TITLE, f"{chosen} has no AOACLIENT.EXE. Choose the folder the game "
                                                  "is in, or use Download.")
            return
        self.settings.game_folder = str(Path(chosen))
        self.save_settings()
        self.refresh()

    def download(self):
        entry = install.installer_entry()
        sentence = (f"Download the Ace of Angels 2.9.2 installer? It is {install.size_text(entry['bytes'])} and "
                    "comes from archive.org (the Internet Archive), which keeps a 2004 games disc it was on. "
                    "The file is checked against its known fingerprint before use, and the installer itself "
                    "is never run.")
        if self.demo or tkcommon.ask(self.root, "Download the game", sentence, "Download"):
            self.run_step(install.GameFiles(self.context), "The download did not finish.")

    def skip_wrapper(self):
        if tkcommon.ask(self.root, "Skip the wrapper", catalog.WRAPPER_LOSS + " You can install it later from Setup.",
                        "Skip it"):
            self.settings.skip_wrapper = True
            self.save_settings()
            self.refresh()

    def show_setup(self):
        self.forced_setup = True
        if self.state is not None:
            self.show(self.state, self.rows, self.options, self.available)

    def leave_setup(self):
        self.forced_setup = False
        if self.state is not None:
            self.show(self.state, self.rows, self.options, self.available)

    # --- tabs -----------------------------------------------------------------------------
    def build_tabs(self):
        ttk = self.ttk
        self.tabs = ttk.Notebook(self.body)
        self.play_tab = ttk.Frame(self.tabs, padding=20)
        self.join_tab = ttk.Frame(self.tabs, padding=20)
        self.options_tab = ttk.Frame(self.tabs, padding=(16, 12))
        self.tabs.add(self.play_tab, text="Play")
        self.tabs.add(self.join_tab, text="Join a friend")
        self.tabs.add(self.options_tab, text="Options")
        self.build_play()
        self.build_join()
        self.build_options()

    # Play
    def build_play(self):
        ttk, tk = self.ttk, self.tk
        tab = self.play_tab
        tab.columnconfigure(0, weight=1)
        self.play_button = ttk.Button(tab, text="Play", style="Big.TButton", command=self.play)
        self.play_button.grid(row=0, column=0, pady=(24, 18))
        line = ttk.Frame(tab)
        line.grid(row=1, column=0)
        ttk.Label(line, text="Play on:").pack(side="left")
        self.server_choice = tk.StringVar(value=THIS_PC)
        self.server_box = ttk.Combobox(line, textvariable=self.server_choice, state="readonly", width=28)
        self.server_box.pack(side="left", padx=8)
        self.server_box.bind("<<ComboboxSelected>>", lambda _e: self.describe_server())
        self.play_status = tk.StringVar()
        ttk.Label(tab, textvariable=self.play_status, style="Muted.TLabel", wraplength=600, justify="center").grid(
            row=2, column=0, pady=(10, 0))
        ttk.Separator(tab).grid(row=3, column=0, sticky="ew", pady=(28, 16))
        ttk.Label(tab, text="At the login screen, type any name and password: there are no accounts.\n"
                            "Play Offline flies the training mission. Play Online joins the server above.",
                  justify="center").grid(row=4, column=0)
        ttk.Label(tab, text="Keys: F2 chase camera, F4 orbit camera, T and G to pick targets, Alt+Q leaves the arena.",
                  style="Muted.TLabel").grid(row=5, column=0, pady=(10, 0))

    def server_names(self):
        """{label in the Play on box: server address the game uses}."""
        names = {THIS_PC: settings_module.DEFAULT_SERVER}
        for friend in self.settings.friends:
            names[friend["name"]] = join.plan(join.parse(friend["address"])).server \
                if not friend.get("alias") else friend["alias"]
        installed = self.state.server if self.state else None
        if installed and installed not in names.values() and installed != "aoahost.com":
            names[f"{installed} (set earlier)"] = installed
        return names

    def fill_play(self):
        names = self.server_names()
        self.server_box.configure(values=list(names))
        current = self.state.server if self.state else None
        label = next((k for k, v in names.items() if v == current), THIS_PC)
        self.server_choice.set(label)
        self.describe_server()

    def describe_server(self):
        label = self.server_choice.get()
        server = self.server_names().get(label, settings_module.DEFAULT_SERVER)
        if label == THIS_PC:
            text = "Play Online connects to a host on this PC: start one with Host.cmd first."
        else:
            text = f"Play Online connects to {label} ({server})."
        self.play_status.set(text)

    def play(self):
        server = self.server_names().get(self.server_choice.get(), settings_module.DEFAULT_SERVER)
        folder = self.settings.game_path()
        exe = folder / game_folder.EXE

        def job(progress):
            client_launcher.require_closed()
            if self.state is None or self.state.server != server:
                progress(f"Setting the server to {server}…")
                join.apply(exe, server)
            progress("Checking the game…")
            prepare.check(exe)
            progress("Starting the game…")
            subprocess.Popen([str(exe)], cwd=folder)
            return server

        self.settings.server = server
        self.save_settings()
        self.run(job, lambda s: self.status.set("The game is starting. Close it before changing options."),
                 "The game could not be started.")

    # Join a friend
    def build_join(self):
        ttk, tk = self.ttk, self.tk
        tab = self.join_tab
        tab.columnconfigure(0, weight=1)
        ttk.Label(tab, text="Paste what your host sent you", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(tab, text="The line from their host window, or just their address (like 192.168.1.5).",
                  style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 6))
        entry_row = ttk.Frame(tab)
        entry_row.grid(row=2, column=0, sticky="ew")
        entry_row.columnconfigure(0, weight=1)
        self.join_text = tk.StringVar()
        entry = ttk.Entry(entry_row, textvariable=self.join_text, width=50)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _e: self.check_join())
        self.check_button = ttk.Button(entry_row, text="Check", style="Accent.TButton", command=self.check_join)
        self.check_button.grid(row=0, column=1, padx=(8, 0))
        self.results = ttk.Frame(tab)
        self.results.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        self.results.columnconfigure(2, weight=1)
        self.hosts_box = ttk.Frame(self.results)
        self.hosts_box.columnconfigure(0, weight=1)
        self.hosts_line = tk.StringVar()
        line = ttk.Entry(self.hosts_box, textvariable=self.hosts_line, state="readonly", width=28)
        line.grid(row=0, column=0, sticky="ew")
        ttk.Button(self.hosts_box, text="Copy", command=lambda: self.copy(self.hosts_line.get())).grid(
            row=0, column=1, padx=(8, 0))
        ttk.Button(self.hosts_box, text="Open Notepad as administrator", command=self.open_hosts).grid(
            row=0, column=2, padx=(8, 0))
        ttk.Label(self.hosts_box, text=f"In Notepad, add the line at the end of {join.HOSTS_FILE}, save, then "
                                       "choose Check again. Windows asks for permission first.",
                  style="Small.TLabel", wraplength=540).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        save_row = ttk.Frame(tab)
        save_row.grid(row=5, column=0, sticky="ew", pady=(18, 0))
        ttk.Label(save_row, text="Friend's name:").pack(side="left")
        self.friend_name = tk.StringVar()
        ttk.Entry(save_row, textvariable=self.friend_name, width=20).pack(side="left", padx=8)
        self.join_button = ttk.Button(save_row, text="Join", style="Accent.TButton", command=lambda: self.join(True))
        self.join_button.pack(side="right")
        self.save_friend_button = ttk.Button(save_row, text="Save as friend", command=lambda: self.join(False))
        self.save_friend_button.pack(side="right", padx=8)
        self.plan = None

    def show_checks(self, plan, checks):
        ttk, tk = self.ttk, self.tk
        for child in self.results.winfo_children():
            if child is not self.hosts_box:
                child.destroy()
        for i, check in enumerate(checks):
            i = i + 1 if i == 2 else i
            tk.Label(self.results, text=tkcommon.GLYPH[check.ok], fg=tkcommon.COLOR[check.ok], width=2,
                     font=(tkcommon.font_family(), 13, "bold"), bg=self.root.cget("background")).grid(
                row=i, column=0, sticky="nw")
            ttk.Label(self.results, text=check.title, style="Heading.TLabel", width=8).grid(
                row=i, column=1, sticky="nw", pady=(2, 6))
            ttk.Label(self.results, text=check.text, wraplength=540, justify="left").grid(
                row=i, column=2, sticky="nw", pady=(2, 6))
        if plan is not None and plan.needs_hosts and not checks[1].ok:
            self.hosts_line.set(plan.hosts_line)
            self.hosts_box.grid(row=2, column=2, sticky="ew", pady=(0, 10))
        else:
            self.hosts_box.grid_remove()
        self.plan = plan
        self.update_buttons()

    def check_join(self):
        try:
            plan = join.plan(join.parse(self.join_text.get()))
        except ValueError as error:
            self.show_checks(None, [join.Check("Address", False, str(error))])
            return
        if not self.friend_name.get().strip():
            self.friend_name.set(plan.target.alias and f"Host at {plan.target.address}" or plan.target.address)
        self.show_checks(plan, [join.check_fits(plan), join.Check("Name", None, "Checking…"),
                                join.Check("Host", None, "Checking…")])
        if self.demo:
            return
        self.worker.submit(lambda progress: join.checks(plan), lambda checks: self.show_checks(plan, checks),
                           lambda error: self.fail("The checks could not run.", error))

    def open_hosts(self):
        if sys.platform != "win32":
            self.status.set("The hosts file is a Windows file; on this system, edit /etc/hosts instead.")
            return
        try:
            subprocess.Popen(join.open_hosts_command(), creationflags=install.NO_WINDOW)
        except OSError as error:
            self.fail("Notepad could not be opened.", error)

    def join(self, play):
        if self.plan is None:
            return
        name = self.friend_name.get().strip() or self.plan.target.address
        try:
            self.settings.add_friend(name, self.plan.target.address, self.plan.target.alias)
        except ValueError as error:
            tkcommon.show_error(self.root, TITLE, f"That friend could not be saved: {error}.")
            return
        self.save_settings()
        self.fill_play()
        if not play:
            self.status.set(f"Saved. Choose {name} under Play on, in the Play tab.")
            return
        self.server_choice.set(name)
        self.tabs.select(self.play_tab)
        self.play()

    def copy(self, text):
        tkcommon.copy_text(self.root, text)
        self.status.set("Copied.")

    # Options
    def build_options(self):
        ttk, tk = self.ttk, self.tk
        tab = self.options_tab
        tab.columnconfigure(0, weight=1, uniform="col")
        tab.columnconfigure(1, weight=1, uniform="col")
        self.option_vars = {o.key: tk.BooleanVar() for o in SHOWN_OPTIONS}
        self.option_vars.update({q[0]: tk.BooleanVar() for q in catalog.QUALITY})
        self.option_vars["texture_pack"] = tk.BooleanVar()
        self.option_checks = {}
        groups = dict(catalog.grouped_options())
        places = {"Fixes (recommended)": (0, 0), "Visual extras": (1, 0), "Experimental": (0, 1)}
        for title, options in groups.items():
            column, row = places[title]
            box = ttk.LabelFrame(tab, text=title, padding=(10, 6))
            box.grid(row=row, column=column, sticky="nsew", padx=4, pady=4)
            for option in options:
                if option.key == "experimental_protection":
                    continue
                self.add_check(box, option.key, option.label, option.help)
        quality = ttk.LabelFrame(tab, text="Graphics quality (needs the wrapper)", padding=(10, 6))
        quality.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        for key, label, help_text, *_ in catalog.QUALITY:
            self.add_check(quality, key, label, help_text)
        self.add_check(quality, "texture_pack", "Replacement texture pack",
                       "Sharper ship and station skins you built from your own copy (docs/play/texture-pack.md).")
        self.option_note = tk.StringVar()
        ttk.Label(tab, textvariable=self.option_note, foreground=tkcommon.COLOR["todo"], wraplength=700).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        buttons = ttk.Frame(tab)
        buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="Recommended", command=lambda: self.preset(catalog.recommended())).pack(side="left")
        ttk.Button(buttons, text="Original visuals", command=lambda: self.preset(catalog.original_visuals())).pack(
            side="left", padx=6)
        self.apply_button = ttk.Button(buttons, text="Apply", style="Accent.TButton", command=self.apply_options)
        self.apply_button.pack(side="right")
        ttk.Separator(tab).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        more = ttk.Frame(tab)
        more.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.extras = tk.StringVar()
        ttk.Label(more, textvariable=self.extras, style="Small.TLabel", wraplength=700, justify="left").pack(
            anchor="w")
        more_buttons = ttk.Frame(more)
        more_buttons.pack(fill="x", pady=(6, 0))
        self.jrmap_button = ttk.Button(more_buttons, text="Install JRMAP terrain", command=self.install_jrmap)
        self.jrmap_button.pack(side="left")
        ttk.Button(more_buttons, text="Restore the original game", command=self.restore).pack(side="right")

    def add_check(self, parent, key, label, help_text):
        check = self.ttk.Checkbutton(parent, text=label, variable=self.option_vars[key],
                                     command=lambda: self.option_changed(key))
        check.pack(anchor="w", pady=2)
        tkcommon.Tooltip(check, help_text)
        self.option_checks[key] = check

    def option_changed(self, key):
        notes = []
        if key in catalog.OPTION and self.option_vars[key].get():
            for other in catalog.OPTION[key].conflicts:
                if other in self.option_vars and self.option_vars[other].get():
                    self.option_vars[other].set(False)
                    notes.append(catalog.conflict_sentence(key, other) +
                                 f" \"{catalog.OPTION[other].label}\" was turned off.")
        changed = any(self.option_vars[k].get() != self.loaded_options.get(k, False) for k in self.option_vars)
        notes.append("Choose Apply to save your changes." if changed else "")
        self.option_note.set(" ".join(n for n in notes if n))

    def preset(self, values):
        for key, value in values.items():
            if key in self.option_vars:
                self.option_vars[key].set(value)
        self.option_changed("")

    def fill_options(self):
        for key, var in self.option_vars.items():
            var.set(bool(self.options.get(key, False)))
        wrapper = bool(self.available.get("wrapper"))
        for key, *_ in catalog.QUALITY:
            self.option_checks[key].state(["!disabled"] if wrapper else ["disabled"])
        pack = bool(self.available.get("texture_pack"))
        self.option_checks["texture_pack"].state(["!disabled"] if pack else ["disabled"])
        extras = []
        if self.state is not None:
            extras.append("JRMAP terrain: " + ("installed" if self.state.jrmap_terrain else "not installed"))
        extras.append("Texture pack: " + ("on" if self.options.get("texture_pack") else
                                          "built, off" if pack else "not built (see docs/play/texture-pack.md)"))
        if not wrapper:
            extras.append("Graphics quality needs the wrapper (Setup, step 5).")
        self.extras.set(" · ".join(extras))
        self.option_note.set("")

    def apply_options(self):
        folder = self.settings.game_path()
        options = {key: var.get() for key, var in self.option_vars.items()}
        options["station"] = self.state.server if self.state and self.state.server != "aoahost.com" \
            else settings_module.DEFAULT_SERVER
        self.run(lambda progress: client_launcher.apply_settings(folder, options),
                 lambda result: self.status.set("Options saved and checked."), "Your options could not be saved.")

    def restore(self):
        if not tkcommon.ask(self.root, "Restore the original game",
                            "Put back the game exactly as it was before the first fix? Play needs the fixes "
                            "again afterwards (Setup, step 3).", "Restore"):
            return
        exe = self.settings.game_path() / game_folder.EXE
        self.run(lambda progress: prepare.undo(exe), lambda result: self.status.set("The original game is back."),
                 "The original game could not be restored.")

    def install_jrmap(self):
        from aoa.maps import map_viewer
        folder = self.settings.game_path()

        def job(progress):
            if not (folder / game_folder.JRMAP_SOURCE).is_file():
                raise install.StepError(f"{game_folder.JRMAP_SOURCE} is not in {folder}.")
            try:
                map_viewer.install(folder)
            except SystemExit as stop:
                raise install.StepError(str(stop.code)) from None

        self.run(job, lambda result: self.status.set("JRMAP terrain installed."),
                 "The JRMAP terrain could not be installed.")

    def update_buttons(self):
        ready = self.state is not None and self.state.ready
        busy = self.worker.busy
        for button in (self.play_button, self.apply_button):
            button.state(["!disabled"] if ready and not busy else ["disabled"])
        for button in (self.join_button, self.save_friend_button):
            button.state(["!disabled"] if self.plan is not None and not busy else ["disabled"])
        self.done_button.state(["!disabled"] if install.complete(self.rows) else ["disabled"])
        self.jrmap_button.state(["!disabled"] if self.state is not None and self.state.jrmap_source
                                and not self.state.jrmap_terrain else ["disabled"])


# --- demo states (made-up data; nothing is read or changed) ------------------------------
def demo_data(state_name, context):
    folder = ROOT / "game/2.9.2"
    ready = game_folder.FolderState(folder, exe="prepared", assets_ok=True, patch_level=catalog.PATCH_LEVEL,
                                    server="localhost", wrapper="installed", skin=True, jrmap_source=True)
    rows_done = [(cls(context), Status("done", text)) for cls, text in (
        (install.GameFiles, f"Found the game in {folder}."),
        (install.BuildFolder, "Every game file is present and matches the 2.9.2 release."),
        (install.Fixes, f"Applied: patch level {catalog.PATCH_LEVEL}."),
        (install.Skin, "The login screen's skin is registered for you."),
        (install.Wrapper, "Installed: the game runs in a window and survives Alt+Tab."))]
    options = {**catalog.recommended(), "distant_objects": True, "antialiasing": True, "filtering": True,
               "texture_pack": False}
    available = {"wrapper": True, "texture_pack": False}
    if state_name == "checklist":
        state = game_folder.FolderState(folder, exe="original", assets_ok=True, skin=False)
        rows = [rows_done[0], rows_done[1],
                (install.Fixes(context), Status("todo", f"Make the 2004 game run on Windows 10 and 11 (patch level "
                                                        f"{catalog.PATCH_LEVEL}). Each change can be undone.")),
                (install.Skin(context), Status("todo", "Register the login screen's skin for your Windows user (no "
                                                       "administrator needed). Without it the login screen never "
                                                       "opens.")),
                (install.Wrapper(context), Status("optional", "Download dgVoodoo2_87_5.zip from the dgVoodoo2 page, "
                                                              "then choose \"I've downloaded it\". Leave the file as "
                                                              "it is, unopened."))]
        return state, rows, {}, {}
    return ready, rows_done, options, available


def demo(window, name):
    state, rows, options, available = demo_data(name, window.context)
    window.settings.friends = [{"name": "Sam's LAN party", "address": "192.168.1.5"},
                               {"name": "Kim (VPN)", "address": "100.101.102.103", "alias": "aoavpn"}]
    window.show(state, rows, options, available)
    if name == "join":
        window.tabs.select(window.join_tab)
        window.join_text.set(join.share_line("100.101.102.103", "aoavpn"))
        plan = join.plan(join.parse(window.join_text.get()))
        window.friend_name.set("Kim (VPN)")
        window.show_checks(plan, [join.check_fits(plan),
                                  join.check_name(plan, lambda name: (_ for _ in ()).throw(OSError())),
                                  join.Check("Host", True, "The host at 100.101.102.103 answers.")])
    elif name == "options":
        window.tabs.select(window.options_tab)
        window.option_vars["experimental_asteroids"].set(True)
        window.option_vars["experimental_solids"].set(True)
        window.option_changed("experimental_solids")
    elif name == "error":
        error = install.StepError("The download did not finish. Check your internet connection and try again.",
                                  "fetch: HTTP Error 503: Service Unavailable\n(made-up details for the demo)")
        dialog = tkcommon.show_error(window.root, TITLE, str(error), tkcommon.details_of(error), LOG)
        dialog.toggle_details()


def build(demo_state=None, game=None):
    """(root, PlayWindow): loaded from the saved settings, or in a demo state with made-up data."""
    import tkinter as tk
    if demo_state:
        s, notices = settings_module.Settings(), []
    else:
        s, notices = settings_module.load()
    if game is not None:
        s.game_folder = str(Path(game).resolve())
    root = tk.Tk()
    window = PlayWindow(root, s, notices, demo=demo_state)
    if demo_state:
        demo(window, demo_state)
    else:
        window.refresh()
    return root, window


def main(argv=None):
    parser = argparse.ArgumentParser(prog="client_launcher.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game", type=Path, nargs="?", help="game folder (default: the saved one, else game/2.9.2)")
    parser.add_argument("--demo", choices=DEMOS, help="open in a made-up state; nothing is read or changed")
    args = parser.parse_args(argv)

    def start():
        root, window = build(args.demo, args.game)
        root.mainloop()
        return 0

    return tkcommon.guard(start, LOG, TITLE)


if __name__ == "__main__":
    sys.exit(main())
