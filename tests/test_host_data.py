"""The host's data modules (defaults, vessels, object slots) and their readers agree; game-free.

    python -I tools/test.py test_host_data
"""
import ast
import contextlib
import io
import tempfile
import unittest

from aoa.host import defaults, object_slots, turret_trial, vessel_combat, vessels, warp_trial
from aoa.host.combat import MissileLedger
from aoa.host.objects.powerups import PowerUps
from aoa.host.objects.targets import TargetShips
from aoa.host.runtime import ConfigError, parse_args
from aoa.maps import navigation
from aoa.paths import ROOT

DATA = ("defaults", "vessels", "object_slots")


class HostDataTests(unittest.TestCase):
    def test_data_modules_import_nothing_from_the_server(self):
        allowed = {"aoa.host.spawn", "aoa.protocol", "aoa.protocol.arena"}
        for name in DATA:
            tree = ast.parse((ROOT / f"aoa/host/{name}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("aoa"):
                    with self.subTest(module=name, imports=node.module):
                        self.assertIn(node.module, allowed)

    def test_object_blocks_are_disjoint_and_in_range(self):
        taken = set()
        for kind, (first, count) in object_slots.BLOCKS.items():
            block = set(range(first, first + count))
            with self.subTest(kind=kind):
                self.assertFalse(block & taken)
                self.assertLess(max(block), object_slots.OBJECT_LIMIT)
            taken |= block
        targets = set(range(object_slots.TARGETS_FIRST, object_slots.TARGETS_END))
        self.assertEqual(targets & taken, set(range(71, 80)) | set(range(80, 85)) | set(range(90, 100)))

    def test_target_limits(self):
        # The limits parse_args has always enforced.
        self.assertEqual(object_slots.target_limit(), 98)
        self.assertEqual(object_slots.target_limit(["warp_gates"]), 69)
        self.assertEqual(object_slots.target_limit(["turrets"]), 78)
        self.assertEqual(object_slots.target_limit(["buoys"]), 88)
        self.assertEqual(object_slots.target_limit(["buoys", "warp_gates"]), 69)

    def test_every_placer_uses_its_block(self):
        slots = object_slots
        self.assertEqual((navigation.FIRST_INDEX, navigation.COUNT), slots.BLOCKS["buoys"])
        self.assertEqual((warp_trial.FIRST_INDEX, warp_trial.COUNT), slots.BLOCKS["warp_gates"])
        self.assertEqual((turret_trial.FIRST_INDEX, turret_trial.COUNT), slots.BLOCKS["turrets"])
        self.assertEqual((PowerUps.FIRST_INDEX, PowerUps.LAST_INDEX), (slots.first("powerups"), slots.last("powerups")))
        self.assertEqual((MissileLedger.FIRST_INDEX, MissileLedger.LAST_INDEX),
                         (slots.first("missiles"), slots.last("missiles")))
        self.assertEqual(TargetShips.LAST_INDEX - TargetShips.FIRST_INDEX + 1, slots.target_limit())
        self.assertEqual(TargetShips.tag(2), 0x40010002)
        self.assertEqual(PowerUps.tag(100), 0x40000064)

    def test_vessels(self):
        self.assertEqual(vessels.SELECTABLE_VESSELS, frozenset(vessel_combat.VESSELS))
        self.assertIn(vessels.DEFAULT_VESSEL, vessels.SELECTABLE_VESSELS)
        self.assertTrue(set(TargetShips.VESSELS) <= vessels.SELECTABLE_VESSELS)

    def test_server_defaults_come_from_the_table(self):
        args = parse_args(["key", "log", "--profile", "local-relay"])
        self.assertEqual((args.port, args.arena_port, args.tcp), tuple(defaults.PORTS[k] for k in ("station", "arena", "tcp")))
        self.assertEqual((args.kill_limit, args.time_limit, args.max_players),
                         (defaults.LIMITS["kill_limit"], defaults.LIMITS["time_limit_seconds"], defaults.LIMITS["max_players"]))
        self.assertEqual(args.backdrop, defaults.DEFAULT_BACKDROP)
        self.assertEqual((args.restart_warning, args.idle_recycle, args.recycle_arena_joins,
                          args.recycle_station_admissions),
                         tuple(defaults.MANAGED[k] for k in ("restart_warning_seconds", "idle_recycle_seconds",
                                                            "recycle_arena_joins", "recycle_station_admissions")))
        self.assertEqual(set(defaults.PROFILES), set(defaults.LOOPBACK_PROFILES + defaults.DOGFIGHT_PROFILES)
                         | {defaults.DIAGNOSTIC})


class FlagRoleTests(unittest.TestCase):
    def parse(self, *extra, profile="local-relay"):
        return parse_args(["key", "log", "--profile", profile, *extra], raise_errors=True)

    def test_role_names_and_hidden_aliases(self):
        self.assertTrue(self.parse("--terrain").terrain)
        self.assertTrue(self.parse("--experimental-terrain").terrain)
        self.assertFalse(self.parse("--no-relay").relay)
        self.assertFalse(self.parse("--no-experimental-relay").relay)
        self.assertTrue(self.parse().relay)
        help_text = io.StringIO()
        with contextlib.redirect_stdout(help_text), self.assertRaises(SystemExit):
            parse_args(["--help"])
        text = help_text.getvalue()
        for name in ("--experimental-terrain", "--experimental-relay", "--advertised-address", "--arena1a-buoys"):
            self.assertNotIn(name, text)
        diagnostics = text[text.index("diagnostics:"):]
        for name in ("--experimental-flight", "--experimental-object", "--experimental-teams",
                     "--experimental-reliable-combat", "--experimental-protection-probe", "--spawn-axis",
                     "--impair-rtt-ms"):
            self.assertIn(name, diagnostics)

    def test_removed_flags(self):
        for extra in (("--advertised-address", "127.0.0.1"), ("--arena1a-buoys", "x.gob")):
            with self.subTest(extra=extra), self.assertRaisesRegex(ConfigError, "unrecognized arguments"):
                self.parse(*extra)

    def test_settings_ignored_in_this_mode_are_refused(self):
        cases = [(("--next-map", "JRMAP"), "--next-map needs --managed-session"),
                 (("--restart-warning", "10"), "--restart-warning needs --managed-session"),
                 (("--idle-recycle", "5"), "--idle-recycle needs --managed-session"),
                 (("--recycle-arena-joins", "5"), "--recycle-arena-joins needs --managed-session"),
                 (("--reorder-margin", "5"), "--reorder-margin needs sustained delivery"),
                 (("--buoy-trn", "JRMAP.TRN"), "--buoy-trn needs --navigation-buoys on JRMAP")]
        for extra, message in cases:
            with self.subTest(extra=extra), self.assertRaisesRegex(ConfigError, message):
                self.parse(*extra)
        for extra in (("--kill-limit", "5"), ("--time-limit", "60"), ("--spawn-axis", "z"),
                      ("--spawn-spacing", "300"), ("--start-vessel", "Vermok")):
            with self.subTest(extra=extra), self.assertRaisesRegex(ConfigError, "requires the relay"):
                self.parse(*extra, profile="diagnostic")
        # The same values are accepted where they act.
        self.assertEqual(self.parse("--kill-limit", "5", "--reorder-margin", "5", "--sustained-delivery").kill_limit, 5)
        # A value equal to the default is not "given".
        self.assertEqual(self.parse("--kill-limit", "20", profile="diagnostic").kill_limit, 20)

    def test_one_rule_for_objects_on_each_profile(self):
        rule = defaults.OBJECT_PROFILES
        self.assertEqual(set(rule["warp_trial"]), set(defaults.LOOPBACK_PROFILES))
        for name in ("navigation_buoys", "map_waypoints", "turret_trial"):
            self.assertEqual(set(rule[name]), set(defaults.LOOPBACK_PROFILES + defaults.DOGFIGHT_PROFILES))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ConfigError, "--warp-trial is not offered on lan-dogfight"):
                parse_args(["key", "log", "--profile", "lan-dogfight", "--bind-address", "192.168.1.5",
                            "--terrain", "--sustained-delivery", "--map", "Arena1a", "--warp-trial", temp],
                           raise_errors=True)
            args = parse_args(["key", "log", "--profile", "lan-dogfight", "--bind-address", "192.168.1.5",
                               "--terrain", "--sustained-delivery", "--map", "Arena1a", "--turret-trial", temp],
                              raise_errors=True)
            self.assertEqual(str(args.turret_trial), temp)


if __name__ == "__main__":
    unittest.main()
