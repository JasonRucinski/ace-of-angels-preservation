"""Diagnostic delivery: the bounded 30-event reliable engine.

ReliableRemovals sends at most 30 reliable IDs to each peer for the whole
session, the 2.9.2 client's duplicate history (findings 9.13), and then
retires the peer. It carries the despawns of a host without sustained
delivery, and ordered combat for the two diagnostic flags
--experimental-reliable-combat and --experimental-protection-probe.
Play with sustained delivery uses aoa/host/delivery.py's WindowedReliable.
"""
import math
import struct
import time

from aoa.host.delivery import Delivery
from aoa.protocol.arena import remove_player


class ReliableRemovals(Delivery):
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

    def queue_message(self, peer, kind, body, now, essential=True):
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
