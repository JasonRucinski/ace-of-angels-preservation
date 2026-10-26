"""Host control: real server child process, status file, console commands, clean quit."""
import sys
import tempfile
import time
import unittest
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
