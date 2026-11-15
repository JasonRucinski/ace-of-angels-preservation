"""HostConfig: command line, in-process validation and the JSON form; game-free.

    python -I tools/test.py test_host_config
"""
import json
import tempfile
import unittest
from pathlib import Path

from aoa.host.config import ConfigError, HostConfig
from aoa.host.runtime import parse_args
from aoa.paths import ROOT


def scratch_root(base, assets=False):
    game = base / "game/2.9.2"
    game.mkdir(parents=True)
    (game / "SCRTY.BIN").write_bytes(bytes(256))
    if assets:
        (base / "work/2.9.2/export/AOAOBJECTS").mkdir(parents=True)
    return base


class HostConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = scratch_root(Path(self.temp.name).resolve())

    def tearDown(self):
        self.temp.cleanup()

    def config(self, **changes):
        return HostConfig(root=self.root, **changes)

    def test_defaults_validate_and_parse(self):
        config = self.config()
        args = config.validate()["CTF_arena"]
        self.assertEqual(args.profile, "local-guests")
        self.assertEqual((args.kill_limit, args.time_limit, args.max_players), (20, 600.0, 8))
        self.assertEqual(args.key, self.root / "game/2.9.2/SCRTY.BIN")
        self.assertEqual(args.status_file, self.root / "work/host/local-guests-status.json")
        self.assertEqual(args.tcp, 5034)

    def test_argv_is_what_the_server_parses(self):
        config = self.config(profile="lan-dogfight", bind_address="192.168.1.5", maps=["Arena1a"], terrain=True,
                             target_ships=4, kill_limit=10, time_limit_seconds=900, ports={"station": 6033,
                                                                                          "arena": 6031, "tcp": 6034},
                             console=True)
        args = parse_args(config.to_argv())
        self.assertEqual((args.port, args.arena_port, args.tcp), (6033, 6031, 6034))
        self.assertEqual((args.target_ships, args.kill_limit, args.time_limit), (4, 10, 900.0))
        self.assertTrue(args.console)
        self.assertEqual(args.map, "Arena1a")
        self.assertEqual(config.to_argv()[config.to_argv().index("--time-limit") + 1], "900")

    def test_rotation_names_the_next_map(self):
        config = self.config(profile="local-guests", maps=["CTF_arena", "CTF_arena_b", "ast_fld_a"], terrain=True,
                             sustained_delivery=True, managed={"restart_warning_seconds": 10})
        parsed = config.validate()
        self.assertEqual([parsed[m].next_map for m in config.maps], ["CTF_arena_b", "ast_fld_a", "CTF_arena"])
        self.assertTrue(all(a.managed_session and a.restart_warning == 10 for a in parsed.values()))

    def test_errors_are_one_line(self):
        cases = [
            (dict(profile="lan-dogfight"), "lan-dogfight requires a specific IPv4 address"),
            (dict(maps=["Nowhere"]), "maps must be"),
            (dict(maps=["CTF_arena", "ast_fld_a"]), "managed sessions"),
            (dict(max_players=50), "--max-players must be 1..49"),
            (dict(profile="diagnostic", target_ships=5), "--target-ships requires the relay"),
            (dict(managed={}, sustained_delivery=True, kill_limit=0, time_limit_seconds=0), "needs kill_limit"),
            (dict(managed={"intermission_seconds": 900}), "intermission_seconds"),
            (dict(objects={"navigation_buoys": True}, terrain=True, sustained_delivery=True),
             "--navigation-buoys requires an exported AOAOBJECTS directory"),
        ]
        for changes, text in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ConfigError) as caught:
                    self.config(**changes).validate()
                self.assertIn(text, str(caught.exception))
                self.assertNotIn("\n", str(caught.exception))

    def test_target_ships_on_a_relay(self):
        args = self.config(target_ships=5).validate()["CTF_arena"]
        self.assertEqual(args.target_ships, 5)

    def test_asset_problems_are_caught_before_start(self):
        # An export folder that exists but holds no Arena1a.Gob: argparse accepts
        # it, the object loader does not, and validate() reports it.
        (self.root / "work/2.9.2/export/AOAOBJECTS").mkdir(parents=True)
        config = self.config(maps=["Arena1a"], terrain=True, sustained_delivery=True,
                             objects={"navigation_buoys": True, "turret_trial": False, "warp_trial": False,
                                      "powerups": False})
        with self.assertRaises(ConfigError) as caught:
            config.validate()
        self.assertTrue(str(caught.exception).startswith("map objects: "))

    def test_powerup_zones_need_the_terrain_file(self):
        config = self.config(maps=["JRMAP"], terrain=True, objects={"powerups": True})
        self.assertIn("--powerup-zones", config.to_argv())
        with self.assertRaises(ConfigError) as caught:
            config.validate()
        self.assertIn("--powerup-zones: no file", str(caught.exception))
        # Layout maps have no zones: the option adds nothing.
        self.assertNotIn("--powerup-zones", self.config(maps=["CTF_arena"], terrain=True,
                                                         objects={"powerups": True}).to_argv())

    def test_key_file(self):
        (self.root / "game/2.9.2/SCRTY.BIN").write_bytes(b"short")
        with self.assertRaisesRegex(ConfigError, "exactly 256 bytes"):
            self.config().validate()
        self.config().validate(key=False)

    def test_json_round_trip(self):
        config = self.config(profile="vpn-dogfight", bind_address="100.101.102.103", maps=["CTF_arena", "JRMAP"],
                             terrain=True, managed={"intermission_seconds": 7},
                             paths={"status": "/var/lib/ace-of-angels/status.json"})
        data = json.loads(json.dumps(config.to_json()))
        self.assertEqual(data["schema"], 1)
        again = HostConfig.from_json(data, root=self.root)
        self.assertEqual(again, config)
        self.assertEqual(again.to_argv("JRMAP"), config.to_argv("JRMAP"))
        path = self.root / "host.json"
        config.save(path)
        self.assertEqual(HostConfig.from_json(path, root=self.root), config)

    def test_json_names_unknown_keys(self):
        for data, text in (({"schema": 1, "map": "CTF_arena"}, "unknown settings: map"),
                           ({"schema": 1, "objects": {"buoys": True}}, "objects has unknown settings: buoys"),
                           ({"schema": 2}, "schema must be 1"),
                           ({"profile": "local-guests"}, "schema must be 1"),
                           ({"schema": 1, "managed": {"recycle": 3}}, "managed has unknown settings: recycle"),
                           ({"schema": 1, "terrain": "yes"}, "terrain must be true or false")):
            with self.subTest(data=data), self.assertRaises(ConfigError) as caught:
                HostConfig.from_json(data, root=self.root)
            self.assertIn(text, str(caught.exception))

    def test_deploy_example(self):
        example = ROOT / "deploy/linux/host.json.example"
        if not example.is_file():
            self.skipTest("no host.json.example yet")
        config = HostConfig.from_json(example)
        for name in config.maps:
            parse_args(config.to_argv(name), raise_errors=True)


if __name__ == "__main__":
    unittest.main()
