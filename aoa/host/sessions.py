"""Station sessions: admission, guest pilots, aliases and the arena lease."""
import hashlib
import secrets

from aoa.protocol.station import arena_ping


class StationSessions:
    """Local session/guest ownership, not authenticated internet identity.

    UDP owns mutable state. TCP reads a replaced, immutable route snapshot.
    No endpoint/ID reuse during a process: delayed quits cannot hit a rejoin.
    """
    CAPACITY = 64

    def __init__(self, timeout, pilot="testpilot", guests=False):
        self.timeout = timeout
        self.pilot, self.guests = pilot, guests
        self.peers = {}
        self.retired = set()
        self.next_id = 1
        self.routes = {}
        self.used_ids = set()

    def _publish(self):
        self.routes = {state["id"]: (peer, state["expiry"])
                       for peer, state in self.peers.items()}

    def admit(self, peer, payload, now):
        fingerprint = hashlib.sha256(payload).digest()
        if peer in self.peers:
            state = self.peers[peer]
            return state["id"] if state["request"] == fingerprint and now < state["expiry"] else None
        if peer in self.retired or self.next_id > self.CAPACITY:
            return None
        identity = self.next_id
        if self.guests:
            # This legacy field is only 32 bits. Randomness prevents trivial
            # sequential selection, but is not a modern authentication scheme.
            for _ in range(128):
                identity = secrets.randbits(32)
                if identity and identity not in self.used_ids:
                    break
            else:
                return None
        pilot = f"{self.pilot[:16]}-{self.next_id:02d}" if self.guests else self.pilot
        self.next_id += 1
        self.used_ids.add(identity)
        self.peers[peer] = {"id": identity, "request": fingerprint, "aliases": False,
                            "pilot": pilot, "arena": None,
                            "expiry": now + self.timeout, "ping_due": now + 1, "ticks": []}
        self._publish()
        return identity

    def resolve(self, request, address, now):
        """Called by TCP; a source IP alone never selects a session."""
        identity = int.from_bytes(request[60:64], "little")
        route = self.routes.get(identity)
        if route is not None and route[0][0] == address[0] and now < route[1]:
            return identity
        return None

    def alias_target(self, identity, now):
        route = self.routes.get(identity)
        if route is None or now >= route[1]:
            return None
        peer = route[0]
        state = self.peers[peer]
        if state["aliases"]:
            return None
        state["aliases"] = True
        return peer

    def depart(self, peer):
        if self.peers.pop(peer, None) is None:
            return False
        self.retired.add(peer)
        self._publish()
        return True

    def heartbeat(self, peer, payload, now):
        # No tag check: the 2.9.2 client uses one UDP socket for Station and
        # arena, and after arena entry it echoes its arena slot here (live
        # capture, findings 9.23). The single-use issued tick is the check.
        state = self.peers.get(peer)
        if (state is None or now >= state["expiry"] or len(payload) != 12
                or payload[:4] not in state["ticks"]):
            return False
        state["ticks"].remove(payload[:4])
        state["expiry"] = now + self.timeout
        self._publish()
        return True

    def pings(self, now):
        packets = []
        for peer, state in self.peers.items():
            if state["arena"] is None and now < state["expiry"] and now >= state["ping_due"]:
                packet = arena_ping(int(now * 1000))
                state["ticks"].append(packet[1][:4])
                del state["ticks"][:-4]
                state["ping_due"] = now + 1
                packets.append((peer, packet))
        return packets

    def arena_owner(self, payload, peer, now):
        if len(payload) != 381:
            return None
        identity = int.from_bytes(payload[31 + 0x7B:35 + 0x7B], "little")
        route = self.routes.get(identity)
        if route is None or route[0][0] != peer[0] or now >= route[1]:
            return None
        state = self.peers[route[0]]
        if payload[31:51] != state["pilot"].encode("ascii").ljust(20, b"\0"):
            return None
        if state["arena"] is not None and state["arena"] != peer:
            return None
        return identity

    def bind_arena(self, identity, peer, expiry):
        state = self.peers[self.routes[identity][0]]
        state["arena"], state["expiry"] = peer, expiry
        self._publish()

    def renew_arena(self, peer, expiry):
        for state in self.peers.values():
            if state["arena"] == peer:
                state["expiry"] = expiry
                self._publish()
                return

    def release_arena(self, peer, now):
        for state in self.peers.values():
            if state["arena"] == peer:
                state["arena"] = None
                state["expiry"] = now + self.timeout
                self._publish()
                return
