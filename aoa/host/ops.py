"""Host operator helpers: atomic status file and a bounded stdin console.

The status file is the health check: a supervisor or the operator can read
it, and a stale `updated_utc` means the host loop has stopped. It holds slot
numbers and temporary pilot names, never addresses or login fields.
"""
import datetime
import json
import os
import queue
import threading
from pathlib import Path
from aoa.paths import ROOT

HELP = ("commands: status | kick <slot> | ban <slot> (kick and refuse its IP until restart) | "
        "end (finish the current match) | say <text> (arena message to all) | quit (stop the host) | help")
QUIT = "host stopping"
SAY_LIMIT = 120
WORK = ROOT / "work/host"


def status_path(profile, folder=WORK):
    """Where a host of this profile writes its status: work/host/<profile>-status.json."""
    return Path(folder) / f"{profile}-status.json"


def read_status(path, pid=None):
    """(status, age in seconds) from a status file, or (None, None).

    None when the file is missing, unreadable or, given `pid`, written by
    another process. The age comes from `updated_utc` and is None without it.
    """
    try:
        status = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(status, dict) or (pid is not None and status.get("pid") != pid):
        return None, None
    try:
        updated = datetime.datetime.fromisoformat(status["updated_utc"])
        age = (datetime.datetime.now(datetime.timezone.utc) - updated).total_seconds()
    except (KeyError, TypeError, ValueError):
        age = None
    return status, age


def write_status(path, status):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    status = dict(status, updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def parse_command(line):
    """(command, slot, text or None) or (None, error text)."""
    words = line.strip().lower().split()
    if not words:
        return None, ""
    command, rest = words[0], words[1:]
    if command == "say" and rest:
        text = line.strip()[3:].strip()
        if text.isascii() and text.isprintable() and len(text) <= SAY_LIMIT:
            return command, text
        return None, f"say: printable ASCII, at most {SAY_LIMIT} characters"
    if command in ("status", "help", "end", "quit") and not rest:
        return command, None
    if command in ("kick", "ban") and len(rest) == 1 and rest[0].isdigit() and 1 <= int(rest[0]) <= 49:
        return command, int(rest[0])
    return None, HELP


class Console:
    """Daemon reader; the host loop drains `lines` without blocking."""

    def __init__(self, stream, size=32):
        self.lines = queue.Queue(maxsize=size)
        self.thread = threading.Thread(target=self._run, args=(stream,), name="host-console", daemon=True)
        self.thread.start()

    def _run(self, stream):
        for line in stream:
            try:
                self.lines.put_nowait(line[:200])
            except queue.Full:
                pass

    def drain(self):
        while True:
            try:
                yield self.lines.get_nowait()
            except queue.Empty:
                return


def player_table(players):
    rows = ["slot pilot               K   D   ping_ms  in_kbps out_kbps idle_s"]
    for player in players:
        rows.append(f"{player['slot']:>4} {player['pilot'][:19]:<19} {player['kills']:>3} {player['deaths']:>3} "
                    f"{player['ping_ms'] if player['ping_ms'] is not None else '-':>8} "
                    f"{player['in_kbps']:>8} {player['out_kbps']:>8} {player['idle_s']:>6}")
    return "\n".join(rows) if players else "no players in the arena"
