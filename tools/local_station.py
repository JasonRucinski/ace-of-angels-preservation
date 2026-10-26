"""Enable localhost Station discovery in the stability-patched 2.9.2 client.

Usage: python -I tools/local_station.py game/2.9.2/AOACLIENT.EXE [--undo]

Changes only the startup hostname string. Does not execute the client.
The login dialog disables Play Online until its asynchronous lookup succeeds;
the original aoahost.com lookup fails and never re-enables the button.
"""
import argparse
import hashlib
from pathlib import Path

STABLE_SHA256 = "87249b8a8ce37684085ad8e62457b6e8f1f9d4a6f5653bcf8dfe11495c1b7f00"
OFFSET = 0x1C5C60
ORIGINAL = b"aoahost.com\0"
LOCAL = b"localhost\0\0\0"


def configure(data, undo=False):
    current = data[OFFSET:OFFSET + len(ORIGINAL)]
    if current not in (ORIGINAL, LOCAL):
        raise ValueError("unexpected startup hostname; not patching")
    normalized = data[:OFFSET] + ORIGINAL + data[OFFSET + len(ORIGINAL):]
    if hashlib.sha256(normalized).hexdigest() != STABLE_SHA256:
        raise ValueError("requires the known stability-patched 2.9.2 client")
    return data[:OFFSET] + (ORIGINAL if undo else LOCAL) + data[OFFSET + len(ORIGINAL):]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--undo", action="store_true")
    args = parser.parse_args()
    if "originals" in (part.lower() for part in args.exe.resolve().parts):
        parser.error("refusing to modify originals/")
    before = args.exe.read_bytes()
    after = configure(before, args.undo)
    if before != after:
        args.exe.write_bytes(after)
    if args.exe.read_bytes() != after:
        raise RuntimeError("written executable did not match expected bytes")
    print("Startup Station lookup: " + ("aoahost.com (restored)" if args.undo else "localhost"))
    print("SHA-256: " + hashlib.sha256(after).hexdigest())


if __name__ == "__main__":
    main()
