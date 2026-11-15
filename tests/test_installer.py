"""aoa/formats/installer.py on a synthetic installer; game-free.

    python -I tools/test.py test_installer
"""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from aoa.formats import installer


def fake_installer(names):
    """A stub 'executable' followed by a ZIP holding one small member per name."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, f"contents of {name}".encode() * 4)
    return b"MZ" + bytes(510) + buffer.getvalue()


class Installer(unittest.TestCase):
    def test_basename(self):
        cases = {"GAME\\AOACLIENT.EXE": "AOACLIENT.EXE", "a/b/c.txt": "c.txt", "plain": "plain",
                 "..\\..\\evil.dll": "evil.dll", "dir/..": "", "dir\\.": "", "trailing/": "", "": ""}
        for name, want in cases.items():
            self.assertEqual(installer.basename(name), want, name)

    def test_members_and_scan_agree(self):
        names = ["GAME\\AOACLIENT.EXE", "GAME\\AOANOTES.TXT", "WISE0001.DLL"]
        data = fake_installer(names)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "setup.exe"
            path.write_bytes(data)
            found = list(installer.members(path))
        self.assertEqual([i for i, *_ in found], [0, 1, 2])
        self.assertEqual([base for _, _, base, _ in found], ["AOACLIENT.EXE", "AOANOTES.TXT", "WISE0001.DLL"])
        self.assertEqual(found[1][3], b"contents of GAME\\AOANOTES.TXT" * 4)
        scanned = list(installer.scan(data))
        self.assertEqual([name for _, name, *_ in scanned], names)
        self.assertTrue(all(meth == 8 for _, _, meth, *_ in scanned))

    def test_scan_survives_a_truncated_file(self):
        data = fake_installer(["A.TXT", "B.TXT"])
        cut = data[:data.find(b"PK\x01\x02")]  # no central directory
        self.assertEqual([name for _, name, *_ in installer.scan(cut)], ["A.TXT", "B.TXT"])


if __name__ == "__main__":
    unittest.main()
