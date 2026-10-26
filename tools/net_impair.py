"""Metered UDP sockets with optional server-side delay/loss impairment.

Wraps the host's Station and arena sockets. Every datagram is counted per
endpoint for bandwidth reporting. With impairment enabled, each direction
independently drops, duplicates and delays datagrams (half the configured
round trip plus random jitter, which also reorders them). This is a test
harness for real clients on a LAN or VPN; it must never be left on for play.
"""
import heapq
import itertools
import math
import random
import time


class Impairment:
    """One-direction settings: delay = rtt/2 + uniform(0, jitter)."""

    def __init__(self, rtt_ms=0.0, jitter_ms=0.0, loss=0.0, duplicate=0.0, seed=None):
        for name, value in (("rtt", rtt_ms), ("jitter", jitter_ms)):
            if not math.isfinite(value) or not 0 <= value <= 5000:
                raise ValueError(f"{name} must be 0..5000 ms")
        for name, value in (("loss", loss), ("duplicate", duplicate)):
            if not math.isfinite(value) or not 0 <= value <= 50:
                raise ValueError(f"{name} must be 0..50 percent")
        self.delay = rtt_ms / 2000
        self.jitter = jitter_ms / 1000
        self.loss = loss / 100
        self.duplicate = duplicate / 100
        self.random = random.Random(seed)

    @property
    def active(self):
        return bool(self.delay or self.jitter or self.loss or self.duplicate)

    def describe(self):
        return {"rtt_ms": round(self.delay * 2000, 3), "jitter_ms": round(self.jitter * 1000, 3),
                "loss_percent": round(self.loss * 100, 3), "duplicate_percent": round(self.duplicate * 100, 3)}

    def schedule(self, now):
        """Arrival times for one datagram: empty when dropped."""
        if self.loss and self.random.random() < self.loss:
            return []
        copies = 2 if self.duplicate and self.random.random() < self.duplicate else 1
        return [now + self.delay + (self.random.random() * self.jitter if self.jitter else 0)
                for _ in range(copies)]


class TrafficMeter:
    """Per-endpoint datagram/byte counters; bounded by the caller's endpoints."""
    MAX_ENDPOINTS = 1024

    def __init__(self):
        self.endpoints = {}
        self.dropped_in = self.dropped_out = 0

    def count(self, endpoint, direction, size):
        entry = self.endpoints.get(endpoint)
        if entry is None:
            if len(self.endpoints) >= self.MAX_ENDPOINTS:
                return
            entry = self.endpoints[endpoint] = {"rx_packets": 0, "rx_bytes": 0, "tx_packets": 0, "tx_bytes": 0}
        entry[direction + "_packets"] += 1
        entry[direction + "_bytes"] += size

    def totals(self):
        total = {"rx_packets": 0, "rx_bytes": 0, "tx_packets": 0, "tx_bytes": 0}
        for entry in self.endpoints.values():
            for key in total:
                total[key] += entry[key]
        return total


class MeteredSocket:
    """Socket facade used by the host loop: sendto/recvfrom/fileno/getsockname.

    recvfrom raises BlockingIOError when the only readable datagram is still
    being held by the inbound delay, or was dropped. Call flush() regularly
    and use next_due()/has_due() to wake for held traffic.
    """
    _order = itertools.count()

    def __init__(self, sock, meter, inbound=None, outbound=None, clock=time.monotonic):
        self.sock, self.meter, self.clock = sock, meter, clock
        self.inbound = inbound if inbound is not None and inbound.active else None
        self.outbound = outbound if outbound is not None and outbound.active else None
        self.held_in, self.held_out = [], []

    MAX_HELD = 4096

    def fileno(self):
        return self.sock.fileno()

    def getsockname(self):
        return self.sock.getsockname()

    def sendto(self, data, address):
        self.meter.count(address, "tx", len(data))
        if self.outbound is None:
            return self.sock.sendto(data, address)
        arrivals = self.outbound.schedule(self.clock())
        if not arrivals:
            self.meter.dropped_out += 1
        for due in arrivals:
            if len(self.held_out) < self.MAX_HELD:
                heapq.heappush(self.held_out, (due, next(self._order), bytes(data), address))
        return len(data)

    def recvfrom(self, size):
        if self.inbound is None:
            data, address = self.sock.recvfrom(size)
            self.meter.count(address, "rx", len(data))
            return data, address
        now = self.clock()
        if not self.has_due(now):
            data, address = self.sock.recvfrom(size)
            arrivals = self.inbound.schedule(now)
            if not arrivals:
                self.meter.dropped_in += 1
            for due in arrivals:
                if len(self.held_in) < self.MAX_HELD:
                    heapq.heappush(self.held_in, (due, next(self._order), data, address))
        if not self.has_due(now):
            raise BlockingIOError("datagram held by impairment")
        _, _, data, address = heapq.heappop(self.held_in)
        self.meter.count(address, "rx", len(data))
        return data, address

    def has_due(self, now=None):
        return bool(self.held_in) and self.held_in[0][0] <= (self.clock() if now is None else now)

    def flush(self, now=None):
        now = self.clock() if now is None else now
        while self.held_out and self.held_out[0][0] <= now:
            _, _, data, address = heapq.heappop(self.held_out)
            try:
                self.sock.sendto(data, address)
            except OSError:
                pass  # A vanished peer must not stop delayed traffic to others.

    def next_due(self):
        times = [held[0][0] for held in (self.held_in, self.held_out) if held]
        return min(times) if times else None
