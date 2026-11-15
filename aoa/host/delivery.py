"""Sustained ordered 0x1B delivery within the 2.9.2 client's 30-ID history.

The client keeps the last 30 distinct reliable IDs per sender in a circular
buffer (findings 9.13). An old copy executes again only if 30 newer distinct
IDs reach the client first. The lifetime budget of the diagnostic
ReliableRemovals (aoa/host/diagnostics.py) prevents that by never sending
more than 30 IDs. WindowedReliable, the engine for play, prevents it with a time window instead, so delivery can continue for a
whole session.

Assumption (stated, like TCP's maximum segment lifetime): a datagram is
either delivered or lost within `margin` seconds after a later datagram on
the same path. Under it, a copy of ID k sent last at t_last cannot arrive
after anything sent later than t_last + margin. So k is "live" while it is
unacknowledged, and for `margin` seconds after its final transmission. A new
ID is first sent only if fewer than 30 IDs have been sent since the oldest
live ID, inclusive; then no live ID can be evicted by newer ones.

Delivery is stop-and-wait per peer, which preserves order (an impact never
overtakes its launch). Essential messages (despawns) retire the peer when
undelivered by their deadline. Droppable messages (combat events) are
abandoned after their deadline and later messages continue.
"""
import math
import struct
from collections import OrderedDict, deque


class Delivery:
    """What the server needs from an outbound reliable (0x1B) engine.

    queue_message(peer, kind, body, now, essential=True)
        the packet to send now, () when it waits behind earlier traffic, or
        None when the peer's budget or queue is exhausted (the server then
        retires the peer). Droppable (essential=False) events may be
        abandoned after their deadline; essential ones retire the peer.
    queue(peer, slot, now)      the despawn (0x2D) of a player slot, as above
    acknowledge(peer, payload, now=None)  a 0x0F ACK; True if it matched
    due(now)        (packets to resend now, peers whose essential event failed)
    next_due()      the next time due() has work, or None
    discard(peer)   forget a departed peer
    pending         the unacknowledged events, keyed (peer, sequence)
    expired         droppable events abandoned so far
    """
    expired = 0

    def queue_message(self, peer, kind, body, now, essential=True):
        raise NotImplementedError

    def queue(self, peer, slot, now):
        raise NotImplementedError

    def acknowledge(self, peer, payload, now=None):
        raise NotImplementedError

    def due(self, now):
        raise NotImplementedError

    def next_due(self):
        return None

    def discard(self, peer):
        raise NotImplementedError


def engine(args, deadline):
    """The delivery engine for these server settings.

    Sustained delivery uses WindowedReliable, the engine for play. Without
    it the bounded 30-event engine of aoa/host/diagnostics.py carries the
    despawns (and, with --experimental-reliable-combat or the protection
    probe, ordered combat): it is what a host without sustained delivery
    has always sent, kept so that a lan-dogfight host without map objects
    behaves as before.
    """
    if args.sustained_delivery:
        return WindowedReliable(deadline=deadline, margin=args.reorder_margin)
    from aoa.host.diagnostics import ReliableRemovals
    return ReliableRemovals(deadline=deadline,
                            ordered=args.experimental_reliable_combat or args.experimental_protection_probe)


class WindowedReliable(Delivery):
    HISTORY = 30
    INTERVAL = 0.3
    MAX_INTERVAL = 2.0
    DROPPABLE_DEADLINE = 5.0
    MAX_QUEUE = 256

    def __init__(self, deadline=30.0, margin=3.0):
        if not (math.isfinite(deadline) and deadline > 0 and math.isfinite(margin) and margin > 0):
            raise ValueError("deadline and margin must be finite and positive")
        self.deadline, self.margin = deadline, margin
        self.queues = {}    # peer -> deque of entries; the head may be in flight
        self.history = {}   # peer -> deque of [seq, last_sent, in_flight] in send order
        self.sent = {}
        self.sequence = 1
        self.expired = 0
        self.window_waits = 0

    @property
    def pending(self):
        return {(peer, entry["seq"]): entry for peer, entries in self.queues.items() for entry in entries}

    def queue_message(self, peer, kind, body, now, essential=True):
        """Packet to send now, () when queued behind earlier traffic, None on overflow."""
        if not 0 <= kind <= 255 or kind == 0x1B or len(body) > 503:
            raise ValueError("invalid reliable inner message")
        entries = self.queues.setdefault(peer, deque())
        if len(entries) >= self.MAX_QUEUE or self.sequence > 0xFFFFFFFF:
            return None
        seq = self.sequence
        self.sequence += 1
        entries.append({"seq": seq, "packet": (0x1B, body + struct.pack("<I", seq) + bytes([kind])),
                        "essential": essential, "first": None, "due": now, "interval": self.INTERVAL,
                        "give_up": None})
        if len(entries) == 1 and self._transmit(peer, entries[0], now):
            return entries[0]["packet"]
        return ()

    def queue(self, peer, slot, now):
        if not 1 <= slot < 50:
            raise ValueError("player slot must be 1..49")
        return self.queue_message(peer, 0x2D, bytes([slot]), now)

    def _window_open(self, peer, now):
        records = self.history.setdefault(peer, deque())
        while records and not records[0][2] and records[0][1] + self.margin <= now:
            records.popleft()
        return len(records) < self.HISTORY

    def _window_reopens(self, peer):
        records = self.history.get(peer)
        if not records or records[0][2]:
            return math.inf
        return records[0][1] + self.margin

    def _transmit(self, peer, entry, now):
        """Send (or resend) the head entry if the history window allows it."""
        if entry["first"] is None:
            if not self._window_open(peer, now):
                self.window_waits += 1
                entry["due"] = self._window_reopens(peer)
                return False
            entry["first"] = now
            entry["give_up"] = now + (self.deadline if entry["essential"] else
                                      min(self.deadline, self.DROPPABLE_DEADLINE))
            self.history[peer].append([entry["seq"], now, True])
            self.sent[peer] = self.sent.get(peer, 0) + 1
        else:
            for record in self.history[peer]:
                if record[0] == entry["seq"]:
                    record[1] = now
            entry["interval"] = min(entry["interval"] * 2, self.MAX_INTERVAL)
        entry["due"] = now + entry["interval"]
        return True

    def _finish_head(self, peer):
        entries = self.queues[peer]
        head = entries.popleft()
        for record in self.history.get(peer, ()):
            if record[0] == head["seq"]:
                record[2] = False
        if not entries:
            del self.queues[peer]
        else:
            entries[0]["due"] = -math.inf
        return head

    def acknowledge(self, peer, payload, now=None):
        if len(payload) != 4:
            return False
        entries = self.queues.get(peer)
        if not entries or entries[0]["first"] is None:
            return False
        if struct.unpack("<I", payload)[0] != entries[0]["seq"]:
            return False
        self._finish_head(peer)
        return True

    def due(self, now):
        """(packets to send, peers whose essential message failed)."""
        packets, failed = [], set()
        for peer in list(self.queues):
            while peer in self.queues:
                head = self.queues[peer][0]
                if head["give_up"] is not None and now >= head["give_up"]:
                    if head["essential"]:
                        failed.add(peer)
                        break
                    self.expired += 1
                    self._finish_head(peer)
                    continue
                if now >= head["due"] and self._transmit(peer, head, now):
                    packets.append((peer, head["packet"]))
                break
        return packets, failed

    def next_due(self):
        times = [entries[0]["due"] for entries in self.queues.values()]
        times += [entries[0]["give_up"] for entries in self.queues.values() if entries[0]["give_up"] is not None]
        return min(times) if times else None

    def discard(self, peer):
        self.queues.pop(peer, None)
        self.history.pop(peer, None)
        self.sent.pop(peer, None)


class InboundReliable:
    """Per-channel/endpoint duplicate suppression for inbound 0x1B envelopes.

    Mirrors the client's own receive history (a fixed count of recent IDs),
    with a larger window. Callers ACK every copy, since an earlier ACK may
    have been lost; only the first copy may cause side effects. Sequence zero
    is not pre-filled: the client's send counter origin is unverified.
    History outlives departure (endpoints are never reused); the table is
    bounded instead. A replay older than WINDOW newer distinct IDs, or from
    an endpoint evicted from the table, is treated as new, so handlers must
    remain idempotent.
    """
    WINDOW = 64
    MAX_ENDPOINTS = 512
    # Repeated handshakes must be re-answered: the reply may have been lost.
    REPLAYABLE = frozenset({0x0A})

    def __init__(self):
        self.history = OrderedDict()
        self.duplicates = 0

    def first(self, endpoint, sequence):
        recent = self.history.pop(endpoint, None) or deque(maxlen=self.WINDOW)
        self.history[endpoint] = recent
        if len(self.history) > self.MAX_ENDPOINTS:
            self.history.popitem(last=False)
        if sequence in recent:
            self.duplicates += 1
            return False
        recent.append(sequence)
        return True
