"""Cross-check tools/aoacrypt.py against the client's own cipher routines.

Usage: python -I tools/emulate_cipher.py <client.exe> <key256.bin> <enc_va> <dec_va> <out.json>

Only the bytes of the two leaf routines' section are mapped into a Unicorn
x86-32 CPU emulator. No imports, OS, loader, or other game code are run:
the routines are pure arithmetic over (buf, len, table) and end in `ret 0xc`.
A stop address is pushed as the return address; emulation ends there.
"""
import json
import random
import sys
from pathlib import Path

from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoacrypt  # noqa: E402
from pe_util import PE  # noqa: E402

STACK, BUF, TAB, STOP = 0x00100000, 0x00200000, 0x00300000, 0x00400000 - 0x1000


def run(uc, fn_va, buf, table):
    uc.mem_write(BUF, bytes(buf) + b"\0" * 16)
    uc.mem_write(TAB, table)
    sp = STACK + 0x8000
    # thiscall: ecx = table object; stdcall args (buf, len, alt=0); ret 0xc
    frame = STOP.to_bytes(4, "little") + BUF.to_bytes(4, "little") + \
        len(buf).to_bytes(4, "little") + (0).to_bytes(4, "little")
    uc.mem_write(sp, frame)
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.reg_write(UC_X86_REG_ECX, TAB)
    uc.emu_start(fn_va, STOP, count=10_000_000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP
    return bytes(uc.mem_read(BUF, len(buf)))


def main():
    path, key_path, enc_s, dec_s, out = sys.argv[1:6]
    enc_va, dec_va = int(enc_s, 16), int(dec_s, 16)
    pe = PE(path)
    key = Path(key_path).read_bytes()
    t = pe.text()
    uc = Uc(UC_ARCH_X86, UC_MODE_32)
    page = t["va"] & ~0xFFF
    size = ((t["va"] + t["raw_size"] - page) + 0xFFF) & ~0xFFF
    uc.mem_map(page, size)
    uc.mem_write(t["va"], pe.data[t["raw_off"]:t["raw_off"] + t["raw_size"]])
    for base in (STACK, BUF, TAB):
        uc.mem_map(base, 0x10000)
    uc.mem_map(STOP & ~0xFFF, 0x1000)
    rng = random.Random(20261020)
    cases, mismatches = 0, []
    for n in [3, 4, 5, 8, 35, 61, 255, 256, 257, 461, 1024]:
        for _ in range(20):
            p = bytes(rng.randrange(256) for _ in range(n))
            e_orig = run(uc, enc_va, p, key)
            e_py = aoacrypt.encrypt(p, key)
            d_orig = run(uc, dec_va, e_orig, key)
            d_py = aoacrypt.decrypt(e_orig, key)
            cases += 1
            if not (e_orig == e_py and d_orig == d_py == p):
                mismatches.append({"len": n, "plain": p.hex()})
    res = {"client": Path(path).as_posix(), "key": Path(key_path).as_posix(),
           "encrypt_va": hex(enc_va), "decrypt_va": hex(dec_va),
           "cases": cases, "mismatches": len(mismatches), "examples": mismatches[:3]}
    Path(out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
