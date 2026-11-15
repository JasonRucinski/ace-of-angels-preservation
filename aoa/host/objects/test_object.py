"""The diagnostic passive mission ship (--experimental-object)."""
import struct


def scenario_test_object():
    """One passive mission ship, not an AI/scenario implementation.

    SendLoadObject 0x48A460 sends type 0x25, 0xBF bytes. The mission-group
    loader uses object kind 0x11. Tag low word is an index below 1000.
    """
    p = bytearray(0xBF)
    for offset, value in ((0, b"Ym Khtat"), (0x20, b"AoAObjects.odb"),
                          (0x40, b"Local mission ship")):
        p[offset:offset + len(value)] = value
    struct.pack_into("<II", p, 0x60, 0x40010001, 0x11)
    struct.pack_into("<3f", p, 0x92, 0.0, 0.0, 1500.0)
    return 0x25, bytes(p)
