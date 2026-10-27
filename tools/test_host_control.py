"""Host control: real server child process, status file, console commands, clean quit."""
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_control  # noqa: E402
import host_ops  # noqa: E402

GAME = Path(__file__).resolve().parents[1] / "game/2.9.2"
EPHEMERAL = ("--port", "0", "--arena-port", "0", "--tcp", "0")


def settings(**changes):
    return {**host_control.DEFAULTS, "game": str(GAME), **changes}


class ConsoleCommandTests(unittest.TestCase):
    def test_say_and_quit_parsing(self):
        self.assertEqual(host_ops.parse_command("say Map change in 1 minute"), ("say", "Map change in 1 minute"))
        self.assertEqual(host_ops.parse_command(" QUIT "), ("quit", None))
        for bad in ("say " + "x" * (host_ops.SAY_LIMIT + 1), "say café", "quit now"):
            self.assertIsNone(host_ops.parse_command(bad)[0])
        self.assertEqual(host_ops.parse_command("say"), (None, host_ops.HELP))


class NodeControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / 'work/2.9.2/export/AOAOBJECTS'
        source.mkdir(parents=True)
        (source.parent / '_export.json').write_text('{}')
        patch = mock.patch.object(host_control, 'ROOT', self.root)
        patch.start()
        self.addCleanup(patch.stop)

    def test_independent_choices_and_unsupported_combinations(self):
        keys = tuple(host_control.NODE_LABELS)
        for bits in range(8):
            choices = {key: bool(bits & (1 << i)) for i, key in enumerate(keys)}
            args = host_control.server_args(settings(**choices))
            for key, enabled in choices.items():
                self.assertEqual('--' + key.replace('_', '-') in args, enabled)
            self.assertEqual(args.count('--sustained-delivery'), int(bool(bits)))
        all_on = dict.fromkeys(keys, True)
        for changes, allowed in (({'terrain': False}, set()),
                                 ({'map': 'CTF_arena'}, {'navigation_buoys'}),
                                 ({'mode': 'LAN'}, {'navigation_buoys', 'turret_trial'})):
            args = host_control.server_args(settings(**all_on, **changes))
            for key in keys:
                self.assertEqual('--' + key.replace('_', '-') in args, key in allowed)
        (self.root / 'work/2.9.2/export/_export.json').unlink()
        args = host_control.server_args(settings(**all_on))
        for key in keys:
            self.assertNotIn('--' + key.replace('_', '-'), args)

    def test_settings_round_trip_and_legacy_defaults(self):
        with mock.patch.object(host_control, 'WORK', self.root), mock.patch.object(
                host_control, 'SETTINGS_FILE', self.root / 'settings.json'):
            host_control.save_settings({'map': 'Arena1a'})
            loaded = host_control.load_settings()
            self.assertTrue(loaded['navigation_buoys'])
            self.assertFalse(loaded['turret_trial'])
            self.assertFalse(loaded['warp_trial'])
            chosen = settings(navigation_buoys=False, turret_trial=True, warp_trial=True)
            host_control.save_settings(chosen)
            self.assertEqual(host_control.load_settings(), chosen)

    def test_real_checkboxes_follow_map_mode_and_terrain(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest('requires Tk widgets')
        make_root = tk.Tk

        def hidden_root():
            try:
                root = make_root()
            except tk.TclError as error:
                self.skipTest(f'requires a working Tk display: {error}')
            root.withdraw()
            return root

        with mock.patch.object(host_control, 'load_settings', return_value=settings()), mock.patch.object(
                host_control, 'detect_addresses', return_value=[]), mock.patch.object(tk, 'Tk', hidden_root):
            ui = host_control.gui(run=False)
        self.addCleanup(ui['root'].destroy)
        checks, variables = ui['node_checks'], ui['vars']
        for key, widget in checks.items():
            self.assertFalse(widget.instate(['disabled']))
            before = variables[key].get()
            widget.invoke()
            self.assertEqual(variables[key].get(), not before)
        variables['mode'].set('LAN')
        self.assertTrue(checks['warp_trial'].instate(['disabled']))
        self.assertFalse(variables['warp_trial'].get())
        self.assertFalse(checks['turret_trial'].instate(['disabled']))
        variables['map'].set('CTF_arena')
        self.assertTrue(checks['turret_trial'].instate(['disabled']))
        self.assertFalse(variables['turret_trial'].get())
        variables['terrain'].set(False)
        self.assertTrue(all(widget.instate(['disabled']) for widget in checks.values()))
        variables['map'].set('Arena1a')
        variables['mode'].set('This PC only')
        variables['terrain'].set(True)
        self.assertTrue(all(not widget.instate(['disabled']) for widget in checks.values()))


@unittest.skipUnless((GAME / "SCRTY.BIN").is_file(), "needs the local 2.9.2 game folder")
class HostProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_work = host_control.WORK
        host_control.WORK = Path(self.temp.name)
        self.host = host_control.HostProcess()

    def tearDown(self):
        if self.host.running:
            self.host.proc.kill()
            self.host.proc.wait()
        host_control.WORK = self.old_work
        self.temp.cleanup()

    def output(self):
        lines = []
        while not self.host.output.empty():
            lines.append(self.host.output.get())
        return lines

    def wait_status(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            data, age = self.host.status()
            if data is not None:
                return data, age
            time.sleep(0.2)
        self.fail("no status file")

    def test_start_status_say_and_clean_quit(self):
        self.host.start(settings(map="CTF_arena", terrain=True), EPHEMERAL)
        data, age = self.wait_status()
        self.assertEqual((data["profile"], data["map"], data["players"]), ("local-relay", "CTF_arena", []))
        self.assertLess(age, 5)
        self.assertTrue(self.host.command("say hello pilots"))
        self.assertEqual(self.host.stop(timeout=10), 0)
        time.sleep(0.3)
        text = "\n".join(self.output())
        self.assertIn("said to 0 player(s)", text)
        self.assertIn(host_ops.QUIT, text)
        self.assertIn("traffic:", text)  # ExitStack cleanup ran
        self.assertFalse(self.host.running)

    def test_invalid_settings_fail_before_starting(self):
        with self.assertRaises(ValueError):
            self.host.start(settings(mode="LAN", address="8.8.8.8"), EPHEMERAL)
        with self.assertRaises(ValueError):
            self.host.start(settings(game=self.temp.name), EPHEMERAL)
        self.assertIsNone(self.host.proc)

    @unittest.skipUnless((host_control.ROOT / 'work/2.9.2/export/_export.json').is_file(),
                         'needs original exported map assets')
    def test_node_choices_reach_running_host(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.host.start(settings(**dict.fromkeys(host_control.NODE_LABELS, enabled)), EPHEMERAL)
                try:
                    data, _ = self.wait_status()
                    self.assertEqual(data['navigation_buoys'], 10 if enabled else 0)
                    self.assertEqual((data['turret_trial'] or {}).get('objects', 0), 5 if enabled else 0)
                    self.assertEqual((data['warp_trial'] or {}).get('objects', 0), 1 if enabled else 0)
                    if enabled:
                        self.assertFalse(data['turret_trial']['enabled'])
                finally:
                    self.assertEqual(self.host.stop(), 0)

    def test_server_args_cover_every_map_and_mode(self):
        for name in host_control.online_terrain.MAP_NAMES:
            args = host_control.server_args(settings(map=name))
            self.assertEqual(args[args.index("--map") + 1], name)
            self.assertIn("--experimental-terrain", args)
        args = host_control.server_args(settings(mode="VPN (internet)", address="100.64.0.5  (Tailscale)",
                                                 terrain=False, time_limit_min=2.5))
        self.assertEqual(args[args.index("--profile") + 1], "vpn-dogfight")
        self.assertEqual(args[args.index("--time-limit") + 1], "150")
        self.assertNotIn("--experimental-terrain", args)
        self.assertEqual(args[args.index("--target-ships") + 1], "4")
        args = host_control.server_args(settings(target_ships=0))
        self.assertEqual(args[args.index("--target-ships") + 1], "0")


if __name__ == "__main__":
    unittest.main()
