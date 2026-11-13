"""Startup Station hostname of the stability-patched 2.9.2 client.

The login dialog disables Play Online until its asynchronous lookup succeeds;
the original aoahost.com lookup fails and never re-enables the button.
prepare_client.py writes the Station through these constants. Library use
only: the standalone command line was removed because it wrote the
executable with no setup record, which a prepared client then rejects.
"""
import hashlib

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

