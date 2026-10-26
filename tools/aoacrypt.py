"""Python re-implementation of the AoA client's 256-byte-table packet cipher.

Derived by hand from the 2.7.1 client (AOACLIENT.EXE, SHA-256 b179c3c2...):
  encrypt  = 0x60F5B0  (thiscall: this=table object, args buf, len, alt_table)
  decrypt  = 0x60F6A0  (same signature)
  0x60F780 / 0x60F7A0 are static wrappers that pass the built-in table at
  VA 0x6A0128 as alt_table.
T is a 256-byte table (SCRTY.BIN is one; it is a permutation of 0..255).
All index arithmetic is modulo 256 (8-bit adds in the original code).

Both routines return immediately when len < 2. NOTE: for len == 2 the
original encrypt's backward loop counter starts at 0 and is decremented
before its zero test, so it would not terminate; real packets are longer.
This implementation mirrors the loops for len >= 3 and refuses len == 2.

Self-test: python -I tools/aoacrypt.py <scrty.bin>
"""
import os
import sys


def encrypt(buf: bytes, T: bytes) -> bytes:
    b = bytearray(buf)
    n = len(b)
    if n < 2:
        return bytes(b)
    if n == 2:
        raise ValueError("original encrypt() does not terminate for len == 2")
    # forward pass, i = 0 .. n-2
    for i in range(n - 1):
        a = (T[(i + 3) & 255] + b[i]) & 255
        x = ((T[(i + 4) & 255] + b[i + 1]) & 255) ^ T[i & 255]
        b[i + 1] = a ^ x
        b[i] = T[(i + 1) & 255] ^ a ^ b[i + 1]
    # backward pass, j = n-2 .. 1
    for j in range(n - 2, 0, -1):
        c = b[j]
        nv = c ^ T[(j + 2) & 255] ^ b[j + 1]
        b[j + 1] = nv
        b[j] = T[(j + 3) & 255] ^ c ^ nv
    return bytes(b)


def decrypt(buf: bytes, T: bytes) -> bytes:
    b = bytearray(buf)
    n = len(b)
    if n < 2:
        return bytes(b)
    # forward pass, k = 1 .. n-2 (undoes encrypt's backward pass)
    for k in range(1, n - 1):
        x = T[(k + 3) & 255] ^ b[k + 1] ^ b[k]
        b[k] = x
        b[k + 1] = T[(k + 2) & 255] ^ b[k + 1] ^ x
    # backward pass, m = n-2 .. 0 (undoes encrypt's forward pass)
    for m in range(n - 2, -1, -1):
        x, y = b[m], b[m + 1]
        a = y ^ T[(m + 1) & 255] ^ x
        b[m] = (a - T[(m + 3) & 255]) & 255
        b[m + 1] = ((T[m & 255] ^ y ^ a) - T[(m + 4) & 255]) & 255
    return bytes(b)


def _selftest(table_path):
    T = open(table_path, "rb").read()
    assert len(T) == 256
    import random
    rng = random.Random(1)
    for n in [3, 4, 5, 17, 61, 255, 256, 257, 300, 1024]:
        for _ in range(50):
            p = bytes(rng.randrange(256) for _ in range(n))
            c = encrypt(p, T)
            assert decrypt(c, T) == p, n
    print("round-trip OK for lengths 3..1024 (500 random buffers)")


if __name__ == "__main__":
    _selftest(sys.argv[1])
