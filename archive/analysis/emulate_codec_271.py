"""Cross-check aoa/formats/aoapack.py's CCompress codec against the client's code.

Usage: python -I tools/run.py archive.analysis.emulate_codec_271 <client.exe(2.7.1)> <out.json>
       python -I tools/run.py archive.analysis.emulate_codec_271 <client.exe(2.7.1)> <out.json> <key256.bin>

With a cipher key, it instead runs the end-to-end CComm framing check
(SendPacket 0x60DDB0 / RecvPacket 0x60DEF0) described at ccomm_check below.

The client image is mapped into a Unicorn x86-32 emulator (sections copied
from the file, virtual tails zero-filled). Only CCompress routines are run:
  ctor 0x60E820, Compress 0x60EB60, DecompressFixed 0x60EED0.
Their only external calls are MFC42 operator new (ord823) / delete (ord825),
which are replaced by a bump allocator / no-op. No OS, loader, Winsock or
other game code runs.
"""
import json
import random
import sys
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

from aoa import cli
from aoa.analysis.pe_util import PE
from aoa.emulation.emu import Emu, SCRATCH, STUBS
from aoa.formats import aoapack


def samples(rng):
    words = [b"SPacket", b"Ace of Angels ", b"\x00\x00\x00\x00", b"Jolly Roger", b"\x01\x02\x03"]
    for n in [3, 4, 5, 8, 20, 35, 61, 100, 200, 300, 461, 509]:
        yield bytes(rng.randrange(256) for _ in range(n))                       # incompressible
        yield b"".join(rng.choice(words) for _ in range(n))[:n]                 # compressible
        yield bytes(rng.choice((0, 0, 0, 1, 0x41)) for _ in range(n))         # very compressible


def codec_check(path, out):
    pe = PE(path)
    emu = Emu(pe)
    this = SCRATCH
    emu.thiscall(0x60E820, this)            # CCompress ctor
    buf, plen = SCRATCH + 0x1000, SCRATCH + 0x100
    rng = random.Random(20261020)
    results = {"cases": 0, "compress_match": 0, "py_decompress_of_client": 0,
               "client_decompress_of_py": 0, "raw_trailer_0x10_accepted": 0, "failures": []}
    for data in samples(rng):
        results["cases"] += 1
        # client Compress as CComm::SendPacket calls it: (buf, &len, 0, 0, 1)
        emu.write(buf, data + b"\0" * 0x400)
        emu.write(plen, len(data).to_bytes(4, "little"))
        emu.thiscall(0x60EB60, this, buf, plen, 0, 0, 1)
        n = int.from_bytes(emu.read(plen, 4), "little")
        c_client = emu.read(buf, n)
        c_py = aoapack.compress(data, small_table=False, with_crc=False, multipass=True)
        if c_client == c_py:
            results["compress_match"] += 1
        else:
            results["failures"].append({"what": "compress", "len": len(data), "client": c_client.hex(), "py": c_py.hex()})
        if aoapack.decompress(c_client)[0] == data:
            results["py_decompress_of_client"] += 1
        # client DecompressFixed (as CComm::RecvPacket calls it: max 0x200)
        for label, enc in (("py", c_py), ("raw", data + b"\x10")):
            if len(enc) > 0x200 or len(data) > 0x200:
                continue
            emu.write(buf, enc + b"\0" * 0x400)
            emu.write(plen, len(enc).to_bytes(4, "little"))
            emu.thiscall(0x60EED0, this, buf, plen, 0x200)
            n = int.from_bytes(emu.read(plen, 4), "little")
            ok = emu.read(buf, n) == data
            if label == "py":
                results["client_decompress_of_py"] += ok
            else:
                results["raw_trailer_0x10_accepted"] += ok
            if not ok:
                results["failures"].append({"what": f"client_decompress_{label}", "len": len(data)})
    results["failures"] = results["failures"][:5]
    Path(out).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


# ---------------------------------------------------------------------------
# End-to-end CComm framing check: run the client's SendPacket / RecvPacket
# with WSOCK32 sendto / recvfrom replaced by capture / inject stubs.
SENDTO, RECVFROM = STUBS + 0x30, STUBS + 0x40


def ccomm_check(path, key_path, out):
    from aoa.protocol import codec
    pe = PE(path)
    emu = Emu(pe)
    key = Path(key_path).read_bytes()
    captured, inject = [], {}

    def wsock(uc, addr, size, _):
        esp = uc.reg_read(UC_X86_REG_ESP)
        a = [int.from_bytes(uc.mem_read(esp + 4 * i, 4), "little") for i in range(7)]
        ret, s, b, n = a[0], a[1], a[2], a[3]
        if addr == SENDTO:
            captured.append(bytes(uc.mem_read(b, n)))
            uc.reg_write(UC_X86_REG_EAX, n)
        else:
            data = inject["bytes"]
            uc.mem_write(b, data)
            uc.reg_write(UC_X86_REG_EAX, len(data))
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + 24)  # stdcall, 6 args
        uc.reg_write(UC_X86_REG_EIP, ret)

    for iat, name in pe.imports.items():
        if name == "WSOCK32.dll!sendto":
            emu.write(iat, SENDTO.to_bytes(4, "little"))
        elif name == "WSOCK32.dll!recvfrom":
            emu.write(iat, RECVFROM.to_bytes(4, "little"))
    emu.uc.hook_add(UC_HOOK_CODE, wsock, begin=SENDTO, end=RECVFROM)

    comm = SCRATCH + 0x8000          # fake CComm: +0x10 ready, +4 CCompress*, +8 key object
    comp = SCRATCH + 0x9000
    keyobj = SCRATCH + 0x9100
    emu.thiscall(0x60E820, comp)
    emu.write(keyobj, key)
    emu.write(comm, b"\0" * 0x400)
    emu.write(comm + 4, comp.to_bytes(4, "little"))
    emu.write(comm + 8, keyobj.to_bytes(4, "little"))
    emu.write(comm + 0x10, b"\x01")
    pkt = SCRATCH + 0xA000           # packet object: +0 sockaddr, +0x14 payload, +0x494 len, +0x498 type
    rng = random.Random(7)
    res = {"cases": 0, "client_wire_eq_python": 0, "python_decodes_client": 0,
           "client_recv_accepts_python": 0, "client_recv_payload_type_ok": 0, "failures": []}
    for data in samples(rng):
        if len(data) >= 0x1FC:
            continue
        ptype = rng.randrange(256)
        res["cases"] += 1
        emu.write(pkt, b"\0" * 0x600)
        emu.write(pkt + 0x14, data)
        emu.write(pkt + 0x494, len(data).to_bytes(4, "little"))
        emu.write(pkt + 0x498, bytes([ptype]))
        captured.clear()
        emu.thiscall(0x60DDB0, comm, 0x1234, pkt, 0)
        wire = captured[0]
        res["client_wire_eq_python"] += wire == codec.encode(ptype, data, key)
        d = codec.decode(wire, key)
        res["python_decodes_client"] += d["payload"] == data and d["type"] == ptype and d["crc_ok"]
        for compressed in (True, False):
            inject["bytes"] = codec.encode(ptype, data, key, compress=compressed)
            emu.write(pkt, b"\0" * 0x600)
            ok = emu.thiscall(0x60DEF0, comm, 0x1234, pkt) & 0xFF
            n = int.from_bytes(emu.read(pkt + 0x494, 4), "little")
            got, gtype = emu.read(pkt + 0x14, n), emu.read(pkt + 0x498, 1)[0]
            res["client_recv_accepts_python"] += bool(ok)
            res["client_recv_payload_type_ok"] += (got == data and gtype == ptype)
            if not ok or got != data:
                res["failures"].append({"len": len(data), "compressed": compressed, "ok": ok})
    res["failures"] = res["failures"][:5]
    Path(out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


def main(argv=None):
    ap = cli.parser(__doc__)
    ap.add_argument("client", help="the 2.7.1 client executable")
    ap.add_argument("out", help="JSON file to write")
    ap.add_argument("key", nargs="?", help="256-byte cipher table: run the CComm framing check instead")
    a = ap.parse_args(argv)
    if a.key:
        ccomm_check(a.client, a.key, a.out)
    else:
        codec_check(a.client, a.out)


if __name__ == "__main__":
    sys.exit(cli.run(main))
