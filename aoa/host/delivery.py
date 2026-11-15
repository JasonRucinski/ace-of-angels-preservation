"""Sustained ordered 0x1B delivery within the 2.9.2 client's 30-ID history.

The client keeps the last 30 distinct reliable IDs per sender in a circular
buffer (findings 9.13). An old copy executes again only if 30 newer distinct
IDs reach the client first. The lifetime budget in station_stub's
ReliableRemovals prevents that by never sending more than 30 IDs. This
class prevents it with a time window instead, so delivery can continue for a
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
import time
from collections import OrderedDict, deque

from aoa.protocol.arena import remove_player


class WindowedReliable:
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


class ReliableRemovals:
    """Bounded 0x1B delivery; preserve the client's 30-entry duplicate cache.

    All outbound reliable messages must use this shared history budget.
    Sequence zero is pre-filled in the client cache.
    Retries back off from INTERVAL to MAX_INTERVAL and give up after
    `deadline` seconds. A real 2.9.2 client in a background window stops
    servicing UDP for tens of seconds and then drains its queue (findings
    9.23), so the server passes its peer timeout here: an observer is not
    retired for a stall it would otherwise survive.
    """
    INTERVAL = 0.5
    MAX_INTERVAL = 4.0
    HISTORY = 30

    def __init__(self, deadline=2.5, ordered=False):
        self.deadline = deadline
        self.ordered = ordered
        self.pending = {}
        self.sent = {}
        self.sequence = 1

    def queue(self, peer, slot, now):
        kind, body = remove_player(slot)
        return self.queue_message(peer, kind, body, now)

    def queue_message(self, peer, kind, body, now):
        """Share one lifetime history budget across every essential event.

        Ordered mode holds subsequent packets until the preceding ACK. This
        prevents an impact overtaking its launch. None means budget exhausted;
        an empty tuple means accepted but waiting behind another event.
        """
        if not 0 <= kind <= 255 or kind == 0x1B or len(body) > 503:
            raise ValueError("invalid reliable inner message")
        if self.sent.get(peer, 0) >= self.HISTORY or self.sequence > 0xFFFFFFFF:
            return None
        seq = self.sequence
        self.sequence += 1
        packet = (0x1B, body + struct.pack("<I", seq) + bytes([kind]))
        waiting = self.ordered and any(p == peer for p, _ in self.pending)
        self.pending[peer, seq] = (packet, math.inf if waiting else now + self.INTERVAL,
                                  self.INTERVAL, now + self.deadline)
        self.sent[peer] = self.sent.get(peer, 0) + 1
        return () if waiting else packet

    def acknowledge(self, peer, payload, now=None):
        if len(payload) != 4:
            return False
        identity = peer, struct.unpack("<I", payload)[0]
        entry = self.pending.get(identity)
        if entry is None or entry[1] == math.inf:
            return False
        del self.pending[identity]
        if self.ordered:
            for next_id, (packet, due, interval, deadline) in self.pending.items():
                if next_id[0] == peer:
                    self.pending[next_id] = (packet, time.monotonic() if now is None else now,
                                             interval, deadline)
                    break
        return True

    def due(self, now):
        failed = {peer for (peer, _), (_, _, _, give_up) in self.pending.items() if now >= give_up}
        packets = []
        for (peer, seq), (packet, due, interval, give_up) in list(self.pending.items()):
            if peer not in failed and now >= due:
                packets.append((peer, packet))
                interval = min(interval * 2, self.MAX_INTERVAL)
                self.pending[peer, seq] = (packet, now + interval, interval, give_up)
        return packets, failed

    def discard(self, peer):
        for identity in list(self.pending):
            if identity[0] == peer:
                del self.pending[identity]
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
