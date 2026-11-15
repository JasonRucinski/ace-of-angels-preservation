"""Match limits and results of the relay's dogfight."""


class Match:
    """Kill/time limits for the proposed first dogfight (new design, not a
    recovered rule). A match starts when the first player is loaded; when it
    ends the server announces the result and the next match starts at once.
    Returning clients to Station has no recovered server message (9.22)."""

    def __init__(self, kill_limit, time_limit):
        self.kill_limit, self.time_limit = kill_limit, time_limit
        self.started, self.number = None, 1

    def start(self, now):
        if self.started is None:
            self.started = now

    def stop(self):
        self.started = None

    def ended(self, kills, now):
        if self.kill_limit and max(kills.values(), default=0) >= self.kill_limit:
            return "kill limit"
        if self.started is not None and self.time_limit and now - self.started >= self.time_limit:
            return "time limit"
        return None

    def result(self, kills, names):
        """Announcement text; ties are reported as ties."""
        best = max(kills.values(), default=0)
        leaders = sorted(names.get(slot, f"Pilot{slot}") for slot, k in kills.items() if k == best and best)
        if not leaders:
            return f"Match {self.number} over: no kills"
        if len(leaders) > 1:
            return f"Match {self.number} over: tie at {best} kills ({', '.join(leaders)})"
        return f"Match {self.number} over: {leaders[0]} wins with {best} kills"

    def next(self, now):
        self.number += 1
        self.started = now
