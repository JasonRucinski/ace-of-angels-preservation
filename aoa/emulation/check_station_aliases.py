"""Verify the synthetic pilot list with the 2.9.2 client's actual handler.

Usage: python -I tools/run.py aoa.emulation.check_station_aliases <client.exe> <out.json>

Only 0x45DBE0 runs in Unicorn. Logging and UI imports are intercepted;
no Windows loader, real UI, network, or other game code runs.
"""
import hashlib
import sys
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP

from aoa import cli
from aoa.builds import require_build
from aoa.emulation.emu import Emu, check_main, HEAP, SCRATCH, STUBS, STOP
from aoa.analysis.pe_util import PE
from aoa.host.server import pilot_list


def check(pe, name, current):
    emu = Emu(pe)
    uc = emu.uc
    world, player = HEAP, HEAP + 0x100000
    emu.write(0x5E7728, world.to_bytes(4, "little"))
    emu.write(world + 0xD3620, player.to_bytes(4, "little"))
    emu.write(player, current.encode("ascii") + b"\0")
    emu.write(SCRATCH + 0x1000, pilot_list(name))
    get_item, send = STUBS + 0x200, STUBS + 0x210
    emu.write(0x58C4FC, get_item.to_bytes(4, "little"))
    emu.write(0x58C580, send.to_bytes(4, "little"))
    observed = {"pilot": name, "current": current, "items": [], "selected": None}

    def cstr(address):
        return emu.read(address, 32).split(b"\0", 1)[0].decode("ascii")

    def intercept(uc, address, size, data):
        if address not in (0x526D00, get_item, send):
            return
        sp = uc.reg_read(UC_X86_REG_ESP)
        ret = int.from_bytes(emu.read(sp, 4), "little")
        cleanup = 0
        if address == get_item:
            cleanup = 8
        elif address == send:
            cleanup = 16
            msg = int.from_bytes(emu.read(sp + 8, 4), "little")
            param = int.from_bytes(emu.read(sp + 16, 4), "little")
            if msg == 0x14A:
                observed["items"].append(cstr(param))
            elif msg == 0x14D:
                observed["selected"] = cstr(param)
        uc.reg_write(UC_X86_REG_EAX, 1)
        uc.reg_write(UC_X86_REG_ESP, sp + 4 + cleanup)
        uc.reg_write(UC_X86_REG_EIP, ret)

    uc.hook_add(UC_HOOK_CODE, intercept)
    emu.thiscall(0x45DBE0, SCRATCH, SCRATCH + 0x1000)
    assert uc.reg_read(UC_X86_REG_EIP) == STOP, "handler did not return"
    assert observed["items"] == [name], observed
    assert observed["selected"] == name, observed
    return observed


def run(source):
    """The report for the client at `source` (the original 2.9.2 executable)."""
    source = Path(source)
    pe = PE(source)
    digest = hashlib.sha256(require_build(pe.data, "2.9.2")).hexdigest()
    cases = [check(pe, "testpilot", current) for current in ("", "Offline", "testpilot")]
    cases.append(check(pe, "abcdefghijklmnopqrs", ""))
    result = {"client_sha256": digest, "handler": "0x45dbe0", "cases": cases,
              "passed": len(cases), "scope": "isolated client handler; UI imports mocked; not live gameplay"}
    return result


def main(argv=None):
    return check_main(__doc__, run, argv)


if __name__ == "__main__":
    sys.exit(cli.run(main))
