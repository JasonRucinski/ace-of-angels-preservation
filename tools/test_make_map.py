"""Custom map builder: record layout, rotations, zones and the Crucible spec.

Game-free; the object-database check runs only when game/2.9.2 is present.
"""
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decode_trn
import make_map

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "config/maps/crucible.json"
GAME = ROOT / "game/2.9.2"
try:
    import capstone  # noqa: F401  (pe_util, for the archive key)
    HAVE_ANALYSIS = True
except ImportError:
    HAVE_ANALYSIS = False


def one(entry):
    data = make_map.build({"name": "t", "spawn": [0, 0, 0], "objects": [entry]})
    return data[4:]


class RecordTests(unittest.TestCase):
    def test_model_record_matches_editor_layout(self):
        r = one({"object": "Wall", "name": "Gate", "pos": [100.0, -200.0, 300.0]})
        self.assertEqual(len(r), decode_trn.REC_292)
        self.assertEqual(decode_trn.cstr(r[0:0x40]), "AoAObjects.odb")
        self.assertEqual(decode_trn.cstr(r[0x40:0x80]), "Wall")
        self.assertEqual(decode_trn.cstr(r[0x80:0x98]), "Gate")
        # JRMAP's editor identity: x axis (1,0,0), z axis (0,0,1).
        self.assertEqual(struct.unpack_from("<6f", r, 0x98), (1, 0, 0, 0, 0, 1))
        self.assertEqual(struct.unpack_from("<3f", r, 0xC4), (100, -200, 300))
        self.assertEqual(struct.unpack_from("<f", r, 0x100)[0], 1.0)
        self.assertEqual(struct.unpack_from("<3f", r, 0x104), (100, -200, 300))
        self.assertEqual(struct.unpack_from("<3I", r, 0x200), (0, 4, 0))
        self.assertEqual(struct.unpack_from("<I", r, 0x218)[0], decode_trn.SENTINEL)

    def test_yaw_matches_editor_flag_record(self):
        # JRMAP flag3 (record 47) stores (c,0,s),(-s,0,c) with c=-0.5384, s=0.8427.
        yaw = -math.degrees(math.atan2(0.8427, -0.5384))
        rows = struct.unpack_from("<6f", one({"object": "Wall", "pos": [0, 0, 0], "rot": [yaw, 0, 0]}), 0x98)
        for got, want in zip(rows, (-0.5384, 0, 0.8427, -0.8427, 0, -0.5384)):
            self.assertAlmostEqual(got, want, places=3)

    def test_rotations_are_proper(self):
        for rot in ((30, 0, 0), (0, 45, 0), (0, 0, 60), (123, -71, 199)):
            x, y, z = make_map.rotation(*rot)
            for a in (x, y, z):
                self.assertAlmostEqual(sum(v * v for v in a), 1, places=9)
            cross = [z[(k + 1) % 3] * x[(k + 2) % 3] - z[(k + 2) % 3] * x[(k + 1) % 3] for k in range(3)]
            for got, want in zip(cross, y):
                self.assertAlmostEqual(got, want, places=9)
        # Positive yaw turns the nose (+z) toward +x.
        self.assertGreater(make_map.rotation(30, 0, 0)[2][0], 0)

    def test_zones(self):
        safe = one({"zone": "safe", "pos": [1, 2, 3], "half": 2500})
        self.assertEqual(decode_trn.cstr(safe[0x40:0x80]), "Cube")
        self.assertEqual(struct.unpack_from("<3f", safe, 0x104), (2500, 2, 3))
        self.assertEqual(struct.unpack_from("<2I", safe, 0x200), (2, 4))
        pu = one({"zone": "powerup", "pos": [10, 20, 30], "half": 500, "type": 4})
        self.assertEqual(pu[0:0x80], bytes(0x80))
        self.assertEqual(struct.unpack_from("<2I", pu, 0x200), (6, 0))
        zones = decode_trn.powerup_zones_292(struct.pack("<I", 1) + pu)
        self.assertEqual(zones, [{"position": (10, 20, 30), "half": 500, "type": 4}])

    def test_waypoint_reaches_the_relay(self):
        import navigation_buoys
        r = one({"nav": "Far Yards", "object": "NavMarkerBlue", "pos": [5.0, 6.0, 7.0]})
        self.assertEqual(decode_trn.cstr(r[0x40:0x80]), "NavMarkerBlue")
        self.assertEqual(decode_trn.cstr(r[0x80:0x98]), "Far Yards")
        self.assertEqual(struct.unpack_from("<2I", r, 0x200), (3, 0))
        data = make_map.build({"name": "t", "spawn": [0, 0, 0], "objects": [
            {"object": "Wall", "pos": [0, 0, 0]}, {"nav": "Home", "pos": [1, 2, 3]}]})
        nodes = navigation_buoys.trn_placements(data)
        self.assertEqual(nodes, [{"name": "Home", "model_object": "Buoy", "position": [1, 2, 3]}])
        (kind, packet), = navigation_buoys.loads(nodes)
        self.assertEqual(kind, 0x25)
        self.assertEqual(packet[:4], b"Buoy")
        self.assertEqual(struct.unpack_from("<II", packet, 0x60), (0x40010000 | 90, 3))
        many = make_map.build({"name": "t", "spawn": [0, 0, 0],
                               "objects": [{"nav": f"N{i}", "pos": [i, 0, 0]} for i in range(11)]})
        with self.assertRaises(ValueError):
            navigation_buoys.trn_placements(many)

    def test_waypoint_options(self):
        from station_runtime import parse_args
        with tempfile.TemporaryDirectory() as tmp:
            trn = Path(tmp) / "m.trn"
            trn.write_bytes(make_map.build({"name": "t", "spawn": [0, 0, 0],
                                            "objects": [{"nav": "Home", "pos": [0, 0, 0]}]}))
            base = ["key", "log", "--profile", "local-relay", "--map", "JRMAP", "--experimental-terrain",
                    "--map-waypoints", str(trn)]
            self.assertEqual(parse_args(base + ["--sustained-delivery"]).map_waypoints, trn)
            for extra in ([], ["--sustained-delivery", "--target-ships", "89"]):
                with self.assertRaises(SystemExit):
                    with open(Path(tmp) / "err", "w") as err:
                        old, sys.stderr = sys.stderr, err
                        try:
                            parse_args(base + extra)
                        finally:
                            sys.stderr = old

    def test_rejections(self):
        bad = [{"object": "Wall", "name": "x" * 24, "pos": [0, 0, 0]},
               {"object": "Wall", "pos": [0, 0]},
               {"object": "Wall", "pos": [0, float("nan"), 0]},
               {"pos": [0, 0, 0]},
               {"zone": "safe", "pos": [0, 0, 0], "half": 0},
               {"zone": "powerup", "pos": [0, 0, 0], "half": 9, "type": 5},
               {"zone": "turret", "pos": [0, 0, 0], "half": 9}]
        for entry in bad:
            with self.assertRaises(ValueError, msg=entry):
                one(entry)
        with self.assertRaises(ValueError):
            make_map.check_objects({"objects": [{"object": "ss1", "pos": [0, 0, 0]}]}, {"wall"})

    def test_install_refuses_main_client(self):
        with self.assertRaises(SystemExit):
            make_map.install({"objects": []}, GAME)


class CrucibleTests(unittest.TestCase):
    def setUp(self):
        self.spec = make_map.load_spec(SPEC)
        self.data = make_map.build(self.spec)

    def test_spec_round_trips(self):
        records = make_map.parse(self.data)
        self.assertEqual(len(records), len(self.spec["objects"]))
        kinds = [r["kind"] for r in records]
        self.assertEqual((kinds.count(0), kinds.count(2), kinds.count(3), kinds.count(6)), (100, 3, 2, 8))
        for entry, rec in zip(self.spec["objects"], records):
            for got, want in zip(rec["position"], entry["pos"]):
                self.assertAlmostEqual(got, want, delta=0.01)
        zones = decode_trn.powerup_zones_292(self.data)
        self.assertEqual(sorted(z["type"] for z in zones), [0, 0, 2, 3, 3, 4, 4, 4])
        names = [e["name"] for e in self.spec["objects"] if "nav" not in e]
        navs = [e["nav"] for e in self.spec["objects"] if "nav" in e]
        self.assertEqual((len(set(names)), len(set(navs))), (len(names), len(navs)))

    def test_spawn_inside_safe_zone_and_clear(self):
        spawn = self.spec["spawn"]
        safe = [e for e in self.spec["objects"] if e.get("zone") == "safe"]
        self.assertTrue(any(all(abs(s - p) <= e["half"] for s, p in zip(spawn, e["pos"])) for e in safe))
        # Nearest model centre is kilometres away (bounding radii checked by `obj`).
        nearest = min(math.dist(spawn, e["pos"]) for e in self.spec["objects"] if "zone" not in e)
        self.assertGreater(nearest, 3000)

    @unittest.skipUnless((GAME / "AOAOBJECTS.ODB").exists() and HAVE_ANALYSIS,
                         "requires the user's 2.9.2 client and requirements.txt")
    def test_objects_exist_in_client(self):
        # New objects (tools/make_object.py) are added to the play copy only.
        added = {json.loads(p.read_text(encoding="utf-8"))["object"].lower()
                 for p in (ROOT / "config/objects").glob("*.json")}
        make_map.check_objects(self.spec, make_map.odb_objects(GAME) | added)

    def test_build_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "c.trn"
            sys.argv = ["make_map.py", "build", str(SPEC), str(out)]
            make_map.main()
            self.assertEqual(out.read_bytes(), self.data)
        self.assertEqual(json.loads(SPEC.read_text(encoding="utf-8"))["name"], "crucible")


if __name__ == "__main__":
    unittest.main()
