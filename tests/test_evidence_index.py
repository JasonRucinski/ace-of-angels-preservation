"""evidence/INDEX.tsv lists every committed evidence file with a generator that exists; game-free.

    python -I tools/test.py test_evidence_index
"""
import hashlib
import re
import unittest

from aoa.paths import ROOT

EVIDENCE = ROOT / "evidence"
INDEX = EVIDENCE / "INDEX.tsv"
NONE = "no generator in the repository"
COMMAND = re.compile(r"^python -I (tools/\w+\.py)(?: ([\w.]+))?")


def rows():
    lines = [line for line in INDEX.read_text(encoding="utf-8").splitlines() if not line.startswith("#")]
    header = lines[0].split("\t")
    return header, [dict(zip(header, line.split("\t"))) for line in lines[1:]]


class EvidenceIndex(unittest.TestCase):
    def test_every_file_is_listed_once(self):
        header, listed = rows()
        self.assertEqual(header, ["file", "generator", "date", "cited_by", "notes"])
        names = [r["file"] for r in listed]
        self.assertEqual(len(names), len(set(names)), "a file is listed twice")
        on_disk = sorted(p.relative_to(EVIDENCE).as_posix() for p in EVIDENCE.rglob("*")
                         if p.is_file() and p != INDEX)
        self.assertEqual(sorted(names), on_disk)

    def test_every_generator_exists(self):
        for row in rows()[1]:
            generator = row["generator"]
            if generator.startswith(NONE):
                continue
            m = COMMAND.match(generator)
            self.assertTrue(m, f"{row['file']}: generator is not a tools/ command: {generator}")
            self.assertTrue((ROOT / m[1]).is_file(), f"{row['file']}: {m[1]} does not exist")
            if m[1] == "tools/run.py":
                module = ROOT.joinpath(*m[2].split(".")).with_suffix(".py")
                self.assertTrue(module.is_file(), f"{row['file']}: module {m[2]} does not exist")

    def test_rows_are_complete(self):
        for row in rows()[1]:
            self.assertRegex(row["date"], r"^20\d\d-\d\d-\d\d", row["file"])
            for path in row["cited_by"].split():
                if path != "-":
                    self.assertTrue((ROOT / path).is_file(), f"{row['file']}: cited_by {path} does not exist")

    def test_byte_identical_files_are_recorded(self):
        seen = {}
        for path in sorted(EVIDENCE.rglob("*")):
            if path.is_file() and path != INDEX:
                seen.setdefault(hashlib.sha256(path.read_bytes()).hexdigest(), []).append(
                    path.relative_to(EVIDENCE).as_posix())
        notes = {r["file"]: r["notes"] for r in rows()[1]}
        for group in seen.values():
            for name in group[1:] if len(group) > 1 else []:
                self.assertIn("byte-identical", notes[name], f"{name} duplicates {group[0]}")


if __name__ == "__main__":
    unittest.main()
