"""AoA UDP datagram codec (CComm layer), as implemented by the 2.7.1 client.

  CComm::SendPacket  0x60DDB0   CComm::RecvPacket  0x60DEF0

Send (client side, per datagram):
    inner = payload || type(u8) || crc16_xmodem(payload) (u16 LE)
    wire  = encrypt(CCompress::Compress(inner, small=0, crc=0, multipass=1), K)
Receive is the inverse; RecvPacket returns true only if the CRC matches.
K is the CComm key object's 256 bytes, loaded from SCRTY.BIN at startup.
The original sender checks payload < 0x200, but recvfrom and decompression
both cap at 0x200. This tool therefore also enforces payload <= 509 (room
for type/CRC) and encoded wire <= 512; an incompressible 509-byte payload
may still be too large once the compression trailer is included.

This module does not open sockets.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoacrypt  # noqa: E402
import aoapack  # noqa: E402

MAX_WIRE = 0x200
MAX_INNER = 0x200
MAX_PAYLOAD = MAX_INNER - 3  # Receiver's bound includes type and CRC.


def encode(ptype: int, payload: bytes, key: bytes, compress: bool = True) -> bytes:
    if len(key) != 256:
        raise ValueError("cipher key must contain 256 bytes")
    if not 0 <= ptype <= 255 or len(payload) > MAX_PAYLOAD:
        raise ValueError("invalid message type or payload exceeds receiver limit")
    inner = payload + bytes([ptype]) + aoapack.crc16_xmodem(payload).to_bytes(2, "little")
    packed = aoapack.compress(inner) if compress else inner + b"\x10"
    if len(packed) > MAX_WIRE:
        raise ValueError("encoded datagram exceeds receiver limit")
    return aoacrypt.encrypt(packed, key)


def decode(wire: bytes, key: bytes):
    """Returns dict(type, payload, crc_ok, codec). Mirrors RecvPacket."""
    if len(key) != 256:
        raise ValueError("cipher key must contain 256 bytes")
    if not 3 <= len(wire) <= MAX_WIRE:
        raise ValueError("invalid datagram length")
    plain = aoacrypt.decrypt(wire, key)
    inner, info = aoapack.decompress(plain, max_output=MAX_INNER)
    if len(inner) < 3:
        raise ValueError("missing message trailer")
    if info.get("has_crc") and not info["crc_ok"]:
        raise ValueError("compression CRC mismatch")
    payload, ptype = inner[:-3], inner[-3]
    crc = int.from_bytes(inner[-2:], "little")
    return {"type": ptype, "payload": payload, "crc_ok": aoapack.crc16_xmodem(payload) == crc,
            "codec": info}


if __name__ == "__main__":
    key = Path(sys.argv[1]).read_bytes()
    w = encode(0x94, b"example", key)
    print(w.hex(), decode(w, key))
