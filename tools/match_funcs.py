"""Locate 2.7.1 functions in another build by masked byte signatures.

Usage: python -I tools/match_funcs.py <ref.exe> <ref_cache.pkl> <other.exe> <other_cache.pkl> <out.json> name=va ...

For each reference function, its bytes up to the next known function start
are taken with every 4-byte absolute address operand / rel32 call-jump target
masked out (via capstone operand offsets). The other build's .text is
searched for that masked pattern. A unique full-length match is reported as
`identical_masked`; otherwise the longest uniquely matching prefix (>= 24
bytes) is reported as a weaker `prefix` match.
"""
import json
import re
import sys
from pathlib import Path

import capstone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pe_util import PE, Disasm  # noqa: E402


def masked(pe, d, start, limit=0x600):
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    md.detail = True
    body = d.func_body(start, 2000)
    if not body:
        return b"", []
    end = body[-1][0] + body[-1][1]
    end = min(end, start + limit)
    off = pe.va_to_off(start)
    code = pe.data[off:off + (end - start)]
    mask = [True] * len(code)
    for ins in md.disasm(code, start):
        rel = ins.address - start
        imm_off, disp_off = ins.imm_offset, ins.disp_offset
        if ins.group(capstone.CS_GRP_CALL) or ins.group(capstone.CS_GRP_JUMP):
            if ins.size >= 5 and code[rel] in (0xE8, 0xE9):
                for k in range(rel + 1, rel + 5):
                    mask[k] = False
        if disp_off and ins.disp_size == 4 and abs(ins.disp) >= 0x400000:
            for k in range(rel + disp_off, rel + disp_off + 4):
                mask[k] = False
        if imm_off and ins.imm_size == 4:
            for op in ins.operands:
                if op.type == capstone.x86.X86_OP_IMM and op.imm >= 0x400000:
                    for k in range(rel + imm_off, rel + imm_off + 4):
                        mask[k] = False
    return code, mask


def to_regex(code, mask):
    return b"".join(re.escape(bytes([c])) if m else b"." for c, m in zip(code, mask))


def main():
    ref, refc, oth, othc, out, *pairs = sys.argv[1:]
    pr, po = PE(ref), PE(oth)
    dr = Disasm(pr, refc)
    Disasm(po, othc)
    t = po.text()
    text = po.data[t["raw_off"]:t["raw_off"] + t["raw_size"]]
    res = []
    for p in pairs:
        name, va_s = p.split("=")
        va = int(va_s, 16)
        code, mask = masked(pr, dr, va)
        rx = re.compile(to_regex(code, mask), re.S)
        hits = [m.start() for m in rx.finditer(text)]
        rec = {"name": name, "ref_va": hex(va), "bytes": len(code), "masked": mask.count(False)}
        if len(hits) == 1:
            rec.update(kind="identical_masked", other_va=hex(t["va"] + hits[0]))
        else:
            n = len(code)
            best = None
            while n >= 24:
                rx2 = re.compile(to_regex(code[:n], mask[:n]), re.S)
                h2 = [m.start() for m in rx2.finditer(text)]
                if len(h2) == 1:
                    best = (n, h2[0])
                    break
                n = n * 3 // 4
            if best:
                rec.update(kind="prefix", prefix_bytes=best[0], other_va=hex(t["va"] + best[1]))
            else:
                rec.update(kind="not_found", full_hits=len(hits))
        res.append(rec)
        print(rec)
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
