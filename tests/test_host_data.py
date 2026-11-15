"""The host's data modules (defaults, vessels, object slots) and their readers agree; game-free.

    python -I tools/test.py test_host_data
"""
import ast
import unittest

from aoa.host import defaults, object_slots, turret_trial, vessel_combat, vessels, warp_trial
from aoa.host.combat import MissileLedger
from aoa.host.objects.powerups import PowerUps
from aoa.host.objects.targets import TargetShips
from aoa.host.runtime import parse_args
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


if __name__ == "__main__":
    unittest.main()
