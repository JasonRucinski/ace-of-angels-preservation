"""Read the members of a Flying Rock installer without running it; standard library only.

The installers are Wise self-installing executables whose payload is an
ordinary ZIP: each file sits behind a PK\\x03\\x04 local header followed by a
raw-deflate stream, and the central directory at the end lets zipfile open
the whole .exe.

- `members(path)` walks the ZIP through zipfile (which checks each member's
  CRC-32 as it reads it): aoa.research.compare_version_assets and
  archive/analysis/inventory.py use it.
- `scan(data)` finds the local headers by searching the bytes, so it also
  lists a damaged or truncated installer; aoa.formats.wise uses it.
- `basename(name)` is the one sanitiser for a member path: whatever a member
  is called, only its last component is ever used for a file name.
"""
import re
import struct
import zipfile

_SEPARATORS = re.compile(r"[\\/]")


def basename(name):
    """The last component of a member path ('/' or '\\' separated); '' for '.', '..' or nothing."""
    base = _SEPARATORS.split(name)[-1]
    return "" if base in (".", "..") else base


def members(path):
    """(index, ZipInfo, basename, bytes) for every member, in archive order."""
    with zipfile.ZipFile(path) as zf:
        for i, info in enumerate(zf.infolist()):
            yield i, info, basename(info.filename), zf.read(info)


def scan(data):
    """(offset, name, method, packed size, size, crc, data start) of every local header in data."""
    i = 0
    while (i := data.find(b"PK\x03\x04", i)) >= 0:
        try:
            _ver, _flag, meth, _t, _d, crc, csz, usz, fnl, exl = struct.unpack(
                "<HHHHHIIIHH", data[i + 4:i + 30])
            name = data[i + 30:i + 30 + fnl].decode("latin1")
            start = i + 30 + fnl + exl
        except struct.error:
            break
        if name and 0 < csz <= len(data) - start:
            yield i, name, meth, csz, usz, crc, start
        i += 4
