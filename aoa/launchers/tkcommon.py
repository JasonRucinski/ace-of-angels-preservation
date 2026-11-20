"""What both windows share: a worker thread for slow work, the error dialog and
its log file, hover help, the look, and a start-up guard.

tkinter is imported inside the functions that need it, so Worker and
log_error can be used and tested on a Python without tkinter.
"""
import datetime
import queue
import sys
import threading
import traceback
from pathlib import Path

from aoa.paths import WORK

LOGS = WORK / "logs"
GLYPH = {"done": "✓", "skipped": "–", "unavailable": "–", "optional": "○", "todo": "●", "waiting": "○",
         "error": "!", "working": "…", True: "✓", False: "✗", None: "–"}
COLOR = {"done": "#1b7a3a", "skipped": "#6b6b6b", "unavailable": "#6b6b6b", "optional": "#9a6b00",
         "todo": "#b45309", "waiting": "#8a8a8a", "error": "#b91c1c", "working": "#1d4ed8",
         True: "#1b7a3a", False: "#b91c1c", None: "#6b6b6b"}
MUTED = "#555555"
ACCENT = "#1d4ed8"


class Worker:
    """Runs slow work off the window thread and hands results back on it.

    submit(job, done, failed, progress): job(progress) runs in a thread;
    progress(text) and the result or exception come back through pump(),
    which the window calls from its timer (`schedule` is root.after).
    One job at a time: busy is True while one runs.
    """

    def __init__(self, schedule, interval=100):
        self.schedule, self.interval = schedule, interval
        self.events = queue.Queue()
        self.busy = False
        self.on_busy = None

    def submit(self, job, done=None, failed=None, progress=None):
        if self.busy:
            return False
        self.busy = True
        if self.on_busy:
            self.on_busy(True)

        def report(text):
            self.events.put(("progress", progress, text))

        def body():
            try:
                result = job(report)
            except BaseException as error:  # noqa: BLE001 - handed to `failed` on the window thread
                self.events.put(("failed", failed, error))
            else:
                self.events.put(("done", done, result))

        threading.Thread(target=body, daemon=True).start()
        self.schedule(self.interval, self.pump)
        return True

    def pump(self):
        """Deliver what the thread reported; keep polling while a job runs."""
        while True:
            try:
                kind, callback, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind != "progress":
                self.busy = False
                if self.on_busy:
                    self.on_busy(False)
            if callback is not None:
                callback(value)
            elif kind == "failed":
                raise value
        if self.busy:
            self.schedule(self.interval, self.pump)


def log_error(path, context, error=None):
    """Append the time, `context` and a traceback (of `error`, or the current one) to `path`."""
    if error is not None:
        text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    else:
        text = traceback.format_exc()
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {context}\n{text}\n")
    except OSError:
        print(text, file=sys.stderr)
    return text


def details_of(error):
    """The text for an error dialog's Details: tool output when there is some, else the traceback."""
    extra = getattr(error, "details", "")
    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    return (extra.strip() + "\n\n" + trace) if extra else trace


# --- widgets (need tkinter) ------------------------------------------------------
def font_family():
    return "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


def style(root):
    """Fonts and ttk styles used by both windows."""
    import tkinter.font as tkfont
    from tkinter import ttk
    family = font_family()
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        tkfont.nametofont(name).configure(family=family, size=10)
    s = ttk.Style(root)
    if "vista" not in s.theme_names() and "clam" in s.theme_names():
        s.theme_use("clam")
    background = s.lookup("TFrame", "background") or "#f0f0f0"
    root.configure(background=background)
    s.configure("Title.TLabel", font=(family, 18, "bold"))
    s.configure("Heading.TLabel", font=(family, 11, "bold"))
    s.configure("Muted.TLabel", foreground=MUTED)
    s.configure("Small.TLabel", foreground=MUTED, font=(family, 9))
    s.configure("Big.TButton", font=(family, 16, "bold"), padding=(36, 14))
    s.configure("Accent.TButton", font=(family, 10, "bold"))
    s.configure("Glyph.TLabel", font=(family, 14, "bold"))
    s.configure("TNotebook.Tab", padding=(16, 6))
    s.configure("Treeview", rowheight=24)
    return family


class Tooltip:
    """Hover text: shown after a short pause, beside the pointer."""

    def __init__(self, widget, text, wrap=360):
        self.widget, self.text, self.wrap, self.tip, self.job = widget, text, wrap, None, None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def schedule(self, _event=None):
        self.job = self.widget.after(450, self.show)

    def show(self, x=None, y=None):
        import tkinter as tk
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 24 if x is None else x
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4 if y is None else y
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", wraplength=self.wrap, background="#fffbe6",
                 relief="solid", borderwidth=1, padx=8, pady=5, font=(font_family(), 9)).pack()

    def hide(self, _event=None):
        if self.job:
            self.widget.after_cancel(self.job)
            self.job = None
        if self.tip:
            self.tip.destroy()
            self.tip = None


def copy_text(widget, text):
    widget.clipboard_clear()
    widget.clipboard_append(text)


def show_error(parent, title, sentence, details="", log_path=None):
    """One sentence, a Details section (closed at first), Copy details and Close."""
    import tkinter as tk
    from tkinter import ttk
    dialog = tk.Toplevel(parent, highlightthickness=1, highlightbackground="#8a8a8a")
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(True, False)
    frame = ttk.Frame(dialog, padding=18)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    tk.Label(frame, text="!", font=(font_family(), 20, "bold"), fg="white", bg=COLOR["error"], width=2).grid(
        row=0, column=0, rowspan=2, sticky="n", padx=(0, 14))
    ttk.Label(frame, text=sentence, wraplength=440, justify="left", style="Heading.TLabel").grid(
        row=0, column=1, sticky="w")
    if log_path:
        ttk.Label(frame, text=f"Also saved in {log_path}", style="Small.TLabel", wraplength=440).grid(
            row=1, column=1, sticky="w", pady=(6, 0))
    text = tk.Text(frame, height=10, width=70, wrap="word", font=("Consolas" if sys.platform == "win32"
                                                                  else "DejaVu Sans Mono", 9))
    text.insert("1.0", details or "No further details.")
    text.configure(state="disabled")
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(14, 0))
    shown = tk.BooleanVar(value=False)

    def toggle():
        shown.set(not shown.get())
        if shown.get():
            text.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
            toggle_button.configure(text="Hide details")
        else:
            text.grid_remove()
            toggle_button.configure(text="Show details")

    toggle_button = ttk.Button(buttons, text="Show details", command=toggle)
    toggle_button.pack(side="left")
    ttk.Button(buttons, text="Copy details", command=lambda: copy_text(dialog, f"{sentence}\n\n{details}")).pack(
        side="left", padx=8)
    close = ttk.Button(buttons, text="Close", command=dialog.destroy, style="Accent.TButton")
    close.pack(side="right")
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    close.focus_set()
    dialog.update_idletasks()
    if parent.winfo_viewable():
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_reqwidth()) // 2)
        y = parent.winfo_rooty() + 120
        dialog.geometry(f"+{x}+{y}")
    dialog.toggle_details = toggle
    return dialog


def ask(parent, title, sentence, yes, no="Cancel"):
    """A yes/no question with button words of our own; True when `yes` is chosen."""
    import tkinter as tk
    from tkinter import ttk
    dialog = tk.Toplevel(parent, highlightthickness=1, highlightbackground="#8a8a8a")
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    answer = tk.BooleanVar(value=False)
    frame = ttk.Frame(dialog, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=sentence, wraplength=420, justify="left").pack(anchor="w")
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(16, 0))

    def choose(value):
        answer.set(value)
        dialog.destroy()

    ttk.Button(buttons, text=no, command=lambda: choose(False)).pack(side="right")
    ok = ttk.Button(buttons, text=yes, style="Accent.TButton", command=lambda: choose(True))
    ok.pack(side="right", padx=8)
    dialog.bind("<Escape>", lambda _e: choose(False))
    ok.focus_set()
    dialog.update_idletasks()
    if parent.winfo_viewable():
        dialog.geometry(f"+{parent.winfo_rootx() + 120}+{parent.winfo_rooty() + 140}")
    dialog.grab_set()
    parent.wait_window(dialog)
    return answer.get()


def guard(main, log_path, title):
    """Run a window's main(); an error that stops it is logged and shown (pythonw has no console)."""
    try:
        return main()
    except Exception as error:  # noqa: BLE001 - nothing else would report it
        log_error(log_path, f"{title} stopped")
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(title, f"The window stopped because of an error: {error}\n\n"
                                        f"Details are in {log_path}", parent=root)
            root.destroy()
        except Exception:  # noqa: BLE001
            print(f"{title}: {error}. Details: {log_path}", file=sys.stderr)
        return 1
