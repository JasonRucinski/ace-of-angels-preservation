"""Just enough of an x86 assembler for the client patches' code caves."""
import struct


class Asm:
    """Bytes, labels, rel8/rel32 fixups, assembled at a fixed origin."""

    def __init__(self, origin):
        self.origin, self.code, self.labels, self.fixups = origin, bytearray(), {}, []

    def here(self):
        return self.origin + len(self.code)

    def label(self, name):
        self.labels[name] = self.here()

    def emit(self, *parts):
        for p in parts:
            self.code += p if isinstance(p, (bytes, bytearray)) else bytes([p])

    def rel8(self, opcode, target):
        self.emit(opcode)
        self.fixups.append(("rel8", len(self.code), target))
        self.emit(0)

    def rel32(self, opcode, target):
        self.emit(opcode)
        self.fixups.append(("rel32", len(self.code), target))
        self.emit(b"\0\0\0\0")

    def resolve(self):
        for kind, pos, target in self.fixups:
            dest = self.labels[target] if isinstance(target, str) else target
            if kind == "rel8":
                disp = dest - (self.origin + pos + 1)
                assert -128 <= disp <= 127, (target, disp)
                self.code[pos] = disp & 0xFF
            else:
                struct.pack_into("<i", self.code, pos, dest - (self.origin + pos + 4))
        return bytes(self.code)


def d32(v):
    return struct.pack("<I", v)


def jmp_patch(at, target, length):
    """`jmp target` at `at`, padded with NOPs to `length` bytes."""
    code = b"\xE9" + struct.pack("<i", target - (at + 5))
    return code + b"\x90" * (length - len(code))


def call(at, target):
    """`call target` at `at` (5 bytes)."""
    return b"\xE8" + struct.pack("<i", target - (at + 5))
