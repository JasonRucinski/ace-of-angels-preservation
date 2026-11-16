"""The emulation helpers and the gate checks' shape; game-free.

Every check named in tests/tiers.py EMULATION must have `run(client_path)`
and the shared command line; Emu.for_build and stop_at are exercised on a
synthetic executable (skipped without unicorn and pefile).

    python -I tools/test.py test_emulation
"""
import ast
import contextlib
import importlib.util
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aoa.paths import ROOT
from tests import tiers


def needs(*packages):
    missing = [p for p in packages if importlib.util.find_spec(p) is None]
    return unittest.skipIf(missing, f"needs {', '.join(missing)}")


def synthetic_client(code):
    """A one-section PE whose .text at 0x401000 holds code."""
    base, e = 0x400000, 0x80
    header = bytearray(0x400)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, e)
    header[e:e + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", header, e + 4, 0x14C, 1, 0, 0, 0, 0xE0, 0x10F)
    struct.pack_into("<H", header, e + 24, 0x10B)
    struct.pack_into("<I", header, e + 24 + 16, 0x1000)       # entry point
    struct.pack_into("<I", header, e + 24 + 28, base)
    struct.pack_into("<II", header, e + 24 + 32, 0x1000, 0x200)  # alignments
    struct.pack_into("<I", header, e + 24 + 56, 0x2000)       # SizeOfImage
    struct.pack_into("<I", header, e + 24 + 60, 0x400)        # SizeOfHeaders
    struct.pack_into("<I", header, e + 24 + 92, 16)
    o = e + 24 + 0xE0
    header[o:o + 8] = b".text\0\0\0"
    struct.pack_into("<IIII", header, o + 8, 0x200, 0x1000, 0x200, 0x400)
    struct.pack_into("<I", header, o + 36, 0x60000020)
    return bytes(header) + code.ljust(0x200, b"\xcc")


class Checks(unittest.TestCase):
    def test_every_gate_check_has_run_and_the_shared_main(self):
        self.assertEqual(len(tiers.EMULATION), 9)
        for name in tiers.EMULATION:
            path = ROOT.joinpath(*name.split(".")).with_suffix(".py")
            tree = ast.parse(path.read_text(encoding="utf-8"))
            functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            self.assertIn("run", functions, name)
            self.assertEqual([a.arg for a in functions["run"].args.args], [functions["run"].args.args[0].arg], name)
            self.assertIn("check_main(__doc__, run, argv)", ast.unparse(functions["main"]), name)

    def test_verify_local_calls_run_in_process(self):
        sys.path.insert(0, str(ROOT / "tools"))
        self.addCleanup(sys.path.remove, str(ROOT / "tools"))
        if importlib.util.find_spec("unicorn") is None:
            self.skipTest("needs unicorn (write_report lives beside the emulator)")
        import verify_local
        importlib.import_module("aoa.emulation.emu")  # before import_module is replaced
        fake = mock.Mock()
        fake.run.return_value = {"passed": 3}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(verify_local.importlib, "import_module", return_value=fake):
            verify_local.emulate("aoa.emulation.check_movement", Path("client.exe"), Path(tmp))
            report = json.loads((Path(tmp) / "check_movement.json").read_text(encoding="utf-8"))
        fake.run.assert_called_once_with(Path("client.exe"))
        self.assertEqual(report, {"passed": 3})


@needs("unicorn", "pefile", "capstone")
class Emulator(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="aoa-emu-")
        self.addCleanup(tmp.cleanup)
        # mov eax, 1; mov eax, 2; mov eax, 3; ret
        self.data = synthetic_client(b"\xb8\x01\0\0\0\xb8\x02\0\0\0\xb8\x03\0\0\0\xc3")
        self.path = Path(tmp.name) / "client.exe"
        self.path.write_bytes(self.data)

    def test_for_build_refuses_other_bytes(self):
        from aoa.emulation.emu import Emu
        with self.assertRaises(ValueError):
            Emu.for_build(self.path, "2.9.2")

    def test_for_build_and_stop_at(self):
        import hashlib
        from aoa import builds
        from aoa.emulation.emu import Emu, STOP
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP
        with mock.patch.dict(builds.CLIENT_SHA256, {"2.9.2": hashlib.sha256(self.data).hexdigest()}):
            emu = Emu.for_build(self.path, "2.9.2")
        stops = emu.stop_at({0x40100A})
        emu.uc.emu_start(0x401000, STOP, count=10)
        self.assertEqual(emu.uc.reg_read(UC_X86_REG_EIP), 0x40100A)
        self.assertEqual(emu.uc.reg_read(UC_X86_REG_EAX), 2)
        stops.clear()
        stops.add(0x40100F)
        emu.uc.emu_start(0x40100A, STOP, count=10)
        self.assertEqual(emu.uc.reg_read(UC_X86_REG_EAX), 3)

    def test_check_main_writes_the_report(self):
        from aoa.emulation.emu import check_main
        out = self.path.with_name("sub") / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            check_main("doc", lambda source: {"source": source.name}, [str(self.path), str(out)])
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"source": "client.exe"})


if __name__ == "__main__":
    unittest.main()
