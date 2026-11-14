"""make_vessel_combat: argparse, --check, and the generated table against its vessel list; game-free."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_vessel_combat  # noqa: E402
import vessel_combat  # noqa: E402
from station_runtime import SELECTABLE_VESSELS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCO = ROOT / "work/2.9.2/sco.json"
GUN_TABLE = ROOT / "evidence/2.9.2/gun_table.json"


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = make_vessel_combat.main(argv)
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue()


class VesselCombatTests(unittest.TestCase):
    def test_table_covers_the_selectable_vessels(self):
        self.assertEqual(set(vessel_combat.VESSELS), SELECTABLE_VESSELS)

    def test_help_and_check_write_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            self.assertEqual(run(["--help"])[0], 0)
            vessels = [{"name": name, "systems": [{"type": make_vessel_combat.SHIELD, "hp": 50.0},
                                                  {"type": make_vessel_combat.GUN, "weapon": "G-310"}]}
                       for name in SELECTABLE_VESSELS]
            (folder / "sco.json").write_text(json.dumps(vessels))
            (folder / "guns.json").write_text(json.dumps({"guns": [{"id": 310, "fields": {"damage (obj+0x11A)": 14}}]}))
            inputs = [str(folder / "sco.json"), str(folder / "guns.json"), str(folder / "out.py")]
            self.assertEqual(run(inputs[:2] + [str(folder / "missing.py"), "--check"])[0], 2)
            self.assertEqual(run(inputs)[0], 0)
            generated = (folder / "out.py").read_text()
            self.assertIn("'Ym Khtat': (50.0, {2: 14}),", generated)
            self.assertEqual(run(inputs + ["--check"]), (0, f"{folder / 'out.py'} matches its generator (32 vessels)\n"))
            (folder / "out.py").write_text(generated.replace("50.0", "51.0", 1))
            code, diff = run(inputs + ["--check"])
            self.assertEqual(code, 1)
            self.assertIn("-    'AlphaFighter': (51.0", diff)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["guns.json", "out.py", "sco.json"])
            self.assertEqual(run(inputs[:1])[0], 2)  # missing argument: usage error, no traceback

    @unittest.skipUnless(SCO.is_file(), "needs work/2.9.2/sco.json (tools/sco_dump.py on the game's AoAObjects.odb)")
    def test_committed_table_matches_generator(self):
        code, output = run([str(SCO), str(GUN_TABLE), "--check"])
        self.assertEqual(code, 0, output)


if __name__ == "__main__":
    unittest.main()
