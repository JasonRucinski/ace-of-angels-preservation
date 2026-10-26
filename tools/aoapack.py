"""Reader for AoA CDataHandler archives (*.aoa) and the CCompress codec.

Derived from the 2.7.1 client (SHA-256 b179c3c2...); see docs/file-formats.md.

  CDataHandler::ReadHeader   0x60CAB0   archive header / directory
  CDataHandler entry read    0x60CE00   seek, read, decrypt, decompress
  CCompress::Decompress      0x60EDA0   trailer parsing, passes, CRC check
  CCompress::DoDecompress    0x60F1D0   one predictor pass
  CRC16                      0x60FCD0   CRC-16/XMODEM (table at 0x6A024C)
  cipher                     tools/aoacrypt.py (0x60F5B0 / 0x60F6A0)

Archive layout (all little-endian):
  0x000  256 bytes   archive key, encrypted with the client's built-in key
  0x100  4 bytes     encrypted with archive key: u16 count, u16 version (0x0402)
  0x104  count*280   encrypted with archive key: directory entries
         entry: char name[256]; u64 offset; u32 size; u32 compress_sel;
                u32 cipher_mode; u32 unused
  data   each entry's bytes at `offset`, `size` long; cipher_mode 0 = built-in
         key, 1 = archive key, other = plain; then CCompress::Decompress when
         compress_sel <= 1.

Usage:
  python -I tools/aoapack.py list    <client.exe> <archive.aoa>
  python -I tools/aoapack.py extract <client.exe> <archive.aoa> <out_dir>
  python -I tools/aoapack.py replace <client.exe> <archive.aoa> <out.aoa> <entry>=<file> ...

`replace` keeps the key, header and every other entry's stored bytes; each
named entry is compressed with CRC and encrypted with the archive key, as in
the shipped archives (whose entries this codec reproduces byte for byte).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoacrypt  # noqa: E402

BUILTIN_KEY_VA = {  # per client build; located by content search in 2.9.2
    "b179c3c22e6426d55de52d57476aaa53b7e92622009daf754c5153be0b7503a7": 0x6A0128,
}


def builtin_key(client_path):
    """Return the client's 256-byte built-in key. For 2.7.1 it is read at its
    known VA; for other builds the 2.7.1 key bytes are searched for."""
    from pe_util import PE
    pe = PE(client_path)
    sha = hashlib.sha256(pe.data).hexdigest()
    if sha in BUILTIN_KEY_VA:
        return pe.read_va(BUILTIN_KEY_VA[sha], 256)
    raise KeyError("unknown client build; pass the 2.7.1 client to obtain the key")


def crc16_xmodem(data: bytes, crc: int = 0) -> int:
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def predictor_pass(src: bytes, small_table: bool, expand: int, max_output=None) -> bytes:
    """One CCompress::DoDecompress pass (0x60F1D0).
    small_table: 256-entry table, hash = ((h << 2) ^ c) & 0xFF
    otherwise:   65536-entry table, hash = ((h << 4) ^ c) & 0xFFFF (RFC 1978)
    `remaining` mirrors the original length counter, which counts the
    current group's flag byte until the group ends."""
    if not src:
        raise ValueError("empty predictor pass")
    table = bytearray(256 if small_table else 65536)
    limit = (expand + 1) * len(src) + 1
    out = bytearray()
    h = 0
    pos = 0
    remaining = len(src)
    while True:
        if pos >= len(src):
            raise ValueError("truncated predictor flags")
        flags = src[pos]
        pos += 1
        for bit in range(8):
            if flags & (1 << bit):
                c = table[h]
            else:
                remaining -= 1
                if remaining == 0:
                    return bytes(out)
                if pos >= len(src):
                    raise ValueError("truncated predictor literal")
                c = src[pos]
                pos += 1
                table[h] = c
            if max_output is not None and len(out) >= max_output:
                raise ValueError("decompressed output exceeds limit")
            out.append(c)
            h = (((h << 2) ^ c) & 0xFF) if small_table else (((h << 4) ^ c) & 0xFFFF)
            if len(out) >= limit:
                raise ValueError("overflow (original logs 'Trying to overflow!')")
        remaining -= 1
        if remaining == 0:
            return bytes(out)


def predictor_compress_pass(src: bytes, small_table: bool) -> bytes:
    """One CCompress compression pass (0x60F040): a flag byte per 8 input
    bytes; bit k set = byte k was predicted by the hash table (not emitted)."""
    table = bytearray(256 if small_table else 65536)
    out = bytearray()
    h = 0
    i, n = 0, len(src)
    while i < n:
        flag_pos = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if i >= n:
                break
            c = src[i]
            if table[h] == c:
                flags |= 1 << bit
            else:
                table[h] = c
                out.append(c)
            h = (((h << 2) ^ c) & 0xFF) if small_table else (((h << 4) ^ c) & 0xFFFF)
            i += 1
        out[flag_pos] = flags
    return bytes(out)


def compress(data: bytes, small_table=False, with_crc=False, multipass=True) -> bytes:
    """CCompress::Compress (0x60EB60), including its pass/expand bookkeeping.
    CComm::SendPacket calls it with small_table=0, with_crc=0, multipass=1."""
    inlen = len(data)
    small_bit = 4 if small_table else 0
    crc = crc16_xmodem(data) if with_crc else None
    if not data:
        return (bytes(2) if with_crc else b"") + bytes([(0x18 if with_crc else 0x10) | small_bit])
    out = predictor_compress_pass(data, small_table)
    a = len(out)
    if not inlen >= a - 1:  # compression expanded the data: store raw
        if with_crc:
            return data + crc.to_bytes(2, "little") + bytes([0x18 | small_bit])
        return data + bytes([0x10 | small_bit])
    expand = max(1, inlen // a + 1)
    passes = 0
    if not multipass:
        passes = 1
    else:
        while True:
            prev = a
            out2 = predictor_compress_pass(out, small_table)
            a2 = len(out2)
            expand = max(expand, prev // a2 + 1)
            passes += 1
            if prev > a2 and passes < 3:
                out, a = out2, a2
                continue
            a = prev
            break
    trailer = (((expand << 4) & 0xFF) + passes) & 0xFF
    if with_crc:
        return out + crc.to_bytes(2, "little") + bytes([trailer | 8 | small_bit])
    return out + bytes([trailer | small_bit])


def decompress(data: bytes, max_output=None):
    """CCompress::Decompress (0x60EDA0). Returns (payload, info)."""
    if not data:
        raise ValueError("missing compression trailer")
    if max_output is not None and (max_output < 0 or len(data) > max_output + 3):
        raise ValueError("compressed input exceeds limit")
    trailer = data[-1]
    passes = trailer & 3
    small = bool(trailer >> 2 & 1)
    has_crc = bool(trailer >> 3 & 1)
    expand = trailer >> 4
    body = data[:-1]
    stored_crc = None
    if has_crc:
        if len(body) < 2:
            raise ValueError("truncated compression CRC")
        stored_crc = int.from_bytes(body[-2:], "little")
        body = body[:-2]
    for _ in range(passes):
        body = predictor_pass(body, small, expand, max_output)
    if max_output is not None and len(body) > max_output:
        raise ValueError("decompressed output exceeds limit")
    info = {"trailer": f"0x{trailer:02x}", "passes": passes, "small_table": small,
            "expand": expand, "has_crc": has_crc}
    if has_crc:
        calc = crc16_xmodem(body)
        info.update(stored_crc=f"0x{stored_crc:04x}", calc_crc=f"0x{calc:04x}", crc_ok=calc == stored_crc)
    return body, info


def read_archive(path, key0):
    return read_archive_bytes(Path(path).read_bytes(), key0)


def entry_bytes(d, key, key0, e):
    raw = d[e["offset"]:e["offset"] + e["size"]]
    if e["cipher_mode"] == 0:
        raw = aoacrypt.decrypt(raw, key0)
    elif e["cipher_mode"] == 1:
        raw = aoacrypt.decrypt(raw, key)
    info = {}
    if e["compress_sel"] <= 1:
        raw, info = decompress(raw)
    return raw, info


def rebuild(path, key0, replacements):
    """Return archive bytes with entries replaced by name (case-insensitive).
    replacements: {entry name: new uncompressed bytes}."""
    d, key, version, entries = read_archive(path, key0)
    wanted = {name.lower(): data for name, data in replacements.items()}
    names = [e["name"].lower() for e in entries]
    missing = set(wanted) - set(names)
    if missing:
        raise KeyError(f"no such archive entries: {sorted(missing)}")
    if any(names.count(n) > 1 for n in wanted):
        raise KeyError("ambiguous replacement: duplicate entry name")
    count = len(entries)
    directory = bytearray(aoacrypt.decrypt(d[260:260 + count * 280], key))
    body, offset = [], 260 + count * 280
    for e in entries:
        if e["name"].lower() in wanted:
            if (e["compress_sel"], e["cipher_mode"]) != (0, 1):
                raise ValueError(f"unsupported entry mode for {e['name']}")
            # The decode check below applies the client's (expand + 1) output
            # limit, so a wrapped 4-bit expand factor is rejected there.
            packed = compress(wanted[e["name"].lower()], with_crc=True)
            raw = aoacrypt.encrypt(packed, key)
        else:
            raw = d[e["offset"]:e["offset"] + e["size"]]
        record = e["index"] * 280
        directory[record + 256:record + 264] = offset.to_bytes(8, "little")
        directory[record + 264:record + 268] = len(raw).to_bytes(4, "little")
        body.append(raw)
        offset += len(raw)
    out = d[:260] + aoacrypt.encrypt(bytes(directory), key) + b"".join(body)
    _, check_key, _, check_entries = read_archive_bytes(out, key0)
    for e in check_entries:
        if e["name"].lower() in wanted:
            data, info = entry_bytes(out, check_key, key0, e)
            if data != wanted[e["name"].lower()] or not info.get("crc_ok"):
                raise ValueError(f"round-trip verification failed for {e['name']}")
    return out


def read_archive_bytes(d, key0):
    key = aoacrypt.decrypt(d[:256], key0)
    hdr = aoacrypt.decrypt(d[256:260], key)
    count = int.from_bytes(hdr[0:2], "little")
    version = int.from_bytes(hdr[2:4], "little")
    dirb = aoacrypt.decrypt(d[260:260 + count * 280], key)
    entries = []
    for i in range(count):
        e = dirb[i * 280:(i + 1) * 280]
        entries.append({
            "index": i,
            "name": e[:256].split(b"\0")[0].decode("latin1"),
            "offset": int.from_bytes(e[256:264], "little"),
            "size": int.from_bytes(e[264:268], "little"),
            "compress_sel": int.from_bytes(e[268:272], "little"),
            "cipher_mode": int.from_bytes(e[272:276], "little"),
        })
    return d, key, version, entries

def safe_name(i, name):
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", name.replace("\\", "/").split("/")[-1]) or "unnamed"
    return f"{i:04d}_{base}"


def main():
    cmd, client, archive = sys.argv[1:4]
    key0 = builtin_key(client)
    if cmd == "replace":
        out = Path(sys.argv[4])
        if out.exists():
            sys.exit(f"refusing to overwrite {out}")
        pairs = dict(arg.split("=", 1) for arg in sys.argv[5:])
        data = rebuild(archive, key0, {k: Path(v).read_bytes() for k, v in pairs.items()})
        out.write_bytes(data)
        print(json.dumps({"archive": out.as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                          "replaced": sorted(pairs)}))
        return
    d, key, version, entries = read_archive(archive, key0)
    out_dir = Path(sys.argv[4]) if cmd == "extract" else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    report = {"archive": Path(archive).as_posix(), "bytes": len(d), "version": f"0x{version:04x}",
              "count": len(entries), "entries": []}
    for e in entries:
        data, info = entry_bytes(d, key, key0, e)
        rec = {**e, "out_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), **info}
        if out_dir:
            dest = out_dir / safe_name(e["index"], e["name"])
            dest.write_bytes(data)
            rec["extracted_to"] = dest.as_posix()
        report["entries"].append(rec)
    end = max((e["offset"] + e["size"] for e in entries), default=260)
    report["trailing_bytes_after_last_entry"] = len(d) - end
    ok = [r for r in report["entries"] if r.get("has_crc")]
    report["crc_checked"] = len(ok)
    report["crc_ok"] = sum(1 for r in ok if r["crc_ok"])
    print(json.dumps(report, indent=1) if cmd == "list" else
          json.dumps({k: v for k, v in report.items() if k != "entries"}))
    if out_dir:
        (out_dir / "_index.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
