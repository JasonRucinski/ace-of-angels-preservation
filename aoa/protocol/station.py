"""Station and handshake messages of the 2.9.2 client: connect acks, reliable acks, pilots, pings."""
import struct


def ack_connect(req_payload, kind=1, player_id=1, station_id=None, result=0, pilot_name=None):
    """SAckConnect (0x0B), layout from 2.9.2 CClientComm::ReceiveAckConnect (0x431630):
    +0 u8 (logged as "me[%d]"), +1 u8 ack kind (switch at 0x4317d6:
    1 = station path, which reads status flags/squad; 0 = game server path),
    +2 u32 player id, +6 u32 result
    (0 or 0x0F = success), +0x0A..0x0C u8 flags, +0x0D the 350-byte player
    block (same size as the request's login block; status flags at +0x3F,
    squad present at +0x45, squad name at +0x11F). The player block is the
    client's own login block echoed back, with status and squad cleared."""
    block = bytearray(req_payload[0x1F:0x1F + 350].ljust(350, b"\0")) if result == 0 else bytearray(350)
    if pilot_name is not None and result == 0:
        pilot_list(pilot_name)
        block[:20] = pilot_name.encode("ascii").ljust(20, b"\0")
    payload = bytearray(0x0D) + block
    payload[1] = kind
    payload[2:6] = player_id.to_bytes(4, "little")
    payload[6:10] = result.to_bytes(4, "little")
    payload[0x3F:0x43] = bytes(4)
    payload[0x45:0x49] = bytes(4)
    if station_id is not None:
        # SendRequestTCPData copies player-record+0x7B to request+0x3C.
        struct.pack_into("<I", payload, 0x0D + 0x7B, station_id)
    return 0x0B, bytes(payload)


def ack_reliable(payload):
    """Reliable messages arrive as 0x1B: inner payload || u32 sequence || u8 inner
    type. The client drops the pending copy when it receives type 0x0F whose
    payload starts with that u32 sequence (CAOAComm receive switch, 0x4864E2,
    walks the retry list at +0xF18 comparing entry+0 with payload+0)."""
    return 0x0F, payload[-5:-1]


def pilot_list(name="testpilot"):
    """Type 0x9A: ten NUL-terminated 32-byte slots, no header.

    2.9.2 dispatch 0x430F5D passes the payload to notify slot +8;
    0x45DBE0 reads ten slots and selects the last nonempty name.
    Keep the test name within the login block's narrower 20-byte field.
    """
    encoded = name.encode("ascii")
    if not encoded or len(encoded) > 19 or b"\0" in encoded:
        raise ValueError("pilot must contain 1..19 non-NUL ASCII characters")
    return encoded.ljust(320, b"\0")


def udp_replies(message_type, payload, arena=False):
    """Replies to validated packets; wrappers acknowledge and dispatch once.

    Only the first arena handshake is implemented, not arena simulation.
    Repeated requests deliberately produce the same stateless replies.
    """
    replies = []
    if message_type == 0x1B:
        if len(payload) < 5:
            return replies
        replies.append(ack_reliable(payload))
        message_type, payload = payload[-1], payload[:-5]
    if message_type == 0x0A and len(payload) == 381:
        replies.append(ack_connect(payload, kind=0 if arena else 1))
    return replies


def arena_ping(tick_ms):
    """Type 8 invokes BouncePing (0x486C20); type 9 is its 12-byte reply.

    Timestamp u32, trip time u16, player u8, reserved u8, two u16 counters.
    Player zero denotes the server peer on the client. The client replaces
    this with its own tag's low byte when bouncing the packet.
    """
    return 0x08, struct.pack("<IHBBHH", tick_ms & 0xFFFFFFFF, 0, 0, 0, 0, 0)
