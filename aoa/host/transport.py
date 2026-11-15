"""UDP transport of one host run: the Station and arena sockets, ingress limits,
one reliable envelope per datagram and the client version gate.

`receive()` waits for at most one datagram, logs it, and returns what the
server should handle; replies that need no session state (reliable ACKs and
version rejections) are sent here.
"""
import errno
import select
import socket
import struct
import time
from typing import NamedTuple

from aoa.host.delivery import InboundReliable
from aoa.host.net_impair import MeteredSocket
from aoa.host.runtime import DatagramBudget
from aoa.protocol import codec
from aoa.protocol.messages import TYPE_NAMES
from aoa.protocol.station import ack_connect, ack_reliable


class Datagram(NamedTuple):
    receiver: object        # the socket it arrived on: Transport.station or .arena
    addr: tuple
    type: int               # inner type when it came in a reliable envelope
    payload: bytes
    wrapped: bool           # arrived in a 0x1B envelope


class Transport:
    def __init__(self, args, key, log, resources, meter, impair_in, impair_out):
        self.key, self.log, self.reply = key, log, args.ack
        self.ingress = DatagramBudget()
        self.inbound = InboundReliable()
        resources.callback(lambda: print(f"UDP ingress: rate_limited={self.ingress.dropped} "
                                         f"reliable_duplicates={self.inbound.duplicates}", flush=True))
        station = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        station.bind((args.bind_address, args.port))
        self.station = MeteredSocket(station, meter, impair_in, impair_out)
        self.sockets = [self.station]
        self.arena = None
        if args.arena:
            arena = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            arena.bind((args.bind_address, args.arena_port))
            self.arena = MeteredSocket(arena, meter, impair_in, impair_out)
            self.sockets.append(self.arena)

    def flush(self, now):
        for sock in self.sockets:
            sock.flush(now)

    def receive(self, banned_ips, next_due=None):
        """One Datagram to handle, or None (nothing arrived, dropped, or answered here).

        Waits up to 0.5 s, or until `next_due` (a monotonic time or None).
        """
        ready = [sock for sock in self.sockets if sock.has_due()]
        if not ready:
            wait = 0.5
            for due in [sock.next_due() for sock in self.sockets] + [next_due]:
                if due is not None:
                    wait = min(wait, max(0.0, due - time.monotonic()))
            ready, _, _ = select.select(self.sockets, [], [], wait)
        if not ready:
            return None
        receiver = ready[0]
        self.sockets.remove(receiver)
        self.sockets.append(receiver)  # Fair service when both UDP channels stay ready.
        try:
            wire, addr = receiver.recvfrom(codec.MAX_WIRE + 1)
        except BlockingIOError:
            return None  # Held or dropped by test impairment.
        except ConnectionResetError:
            # Windows reports ICMP port-unreachable here after a client exits.
            # A dead test peer must not take down the other clients' listener.
            return None
        except OSError as error:
            # Windows raises WSAEMSGSIZE for a UDP datagram larger than the
            # buffer. POSIX truncates it to MAX_WIRE+1, rejected by decode.
            if error.errno == errno.EMSGSIZE or getattr(error, "winerror", None) == 10040:
                return None
            raise
        try:
            if not self.ingress.allow((receiver.getsockname()[1], addr), time.monotonic()):
                return None
            m = codec.decode(wire, self.key)
        except Exception as e:  # noqa: BLE001
            m = {"type": None, "payload": b"", "crc_ok": False, "error": repr(e)}
        rec = {"t": round(time.time(), 3), "from": f"{addr[0]}:{addr[1]}", "wire_len": len(wire),
               "udp_port": receiver.getsockname()[1],
               "type": m["type"], "name": TYPE_NAMES.get(m["type"], ""), "crc_ok": m["crc_ok"],
               "len": len(m["payload"]), "payload": m["payload"].hex()}
        self.log({"event": "udp_packet", **rec})
        if not (self.reply and m["crc_ok"]):
            return None
        return self._unwrap(receiver, addr, m, banned_ips)

    def _unwrap(self, receiver, addr, m, banned_ips):
        if addr[0] in banned_ips:
            # Before any reply, including reliable acks and version rejections.
            return None
        message_type, payload = m["type"], m["payload"]
        if message_type == 0x1B:
            if len(payload) < 5:
                return None
            rtype, rpay = ack_reliable(payload)
            receiver.sendto(codec.encode(rtype, rpay, self.key), addr)
            message_type, payload = payload[-1], payload[:-5]
            if message_type == 0x1B:
                # Only one reliable envelope is supported. Do not let a
                # nested envelope fall through to the stateless helper.
                return None
            if (not self.inbound.first((receiver.getsockname()[1], addr), rpay)
                    and message_type not in InboundReliable.REPLAYABLE):
                self.log({"t": round(time.time(), 3), "event": "reliable_duplicate", "type": message_type})
                return None
        if message_type == 0x0A and len(payload) == 381:
            if struct.unpack_from("<III", payload, 1) != (9, 2, 2):
                # Original 2.9.2 login error switch maps result 8 to
                # 'Incorrect version.' Do not allocate on rejection.
                receiver.sendto(codec.encode(*ack_connect(payload, kind=1 if receiver is self.station else 0, result=8),
                                             self.key), addr)
                self.log({"t": round(time.time(), 3), "event": "admission_rejected", "reason": "unsupported client version"})
                return None
        return Datagram(receiver, addr, message_type, payload, m["type"] == 0x1B)
