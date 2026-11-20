"""Host window: the server's console and status file, start-up errors, and a real server
child process under the window's Supervisor (that part needs the game's SCRTY.BIN)."""
import contextlib
import io
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path

from aoa.host import ops  # noqa: E402
from aoa.launchers import host_app, hosting, settings, tkcommon  # noqa: E402
from aoa.paths import ROOT

GAME = ROOT / "game/2.9.2"
EPHEMERAL = ("--port", "0", "--arena-port", "0", "--tcp", "0")


class ConsoleCommandTests(unittest.TestCase):
    def test_say_and_quit_parsing(self):
        self.assertEqual(ops.parse_command("say Map change in 1 minute"), ("say", "Map change in 1 minute"))
        self.assertEqual(ops.parse_command(" QUIT "), ("quit", None))
        for bad in ("say " + "x" * (ops.SAY_LIMIT + 1), "say café", "quit now"):
            self.assertIsNone(ops.parse_command(bad)[0])
        self.assertEqual(ops.parse_command("say"), (None, ops.HELP))


class StatusFileTests(unittest.TestCase):
    def test_one_status_path_and_reader(self):
        with tempfile.TemporaryDirectory() as temp:
            path = ops.status_path("lan-dogfight", temp)
            self.assertEqual(path, Path(temp) / "lan-dogfight-status.json")
            self.assertEqual(ops.status_path("vpn-dogfight").parent, ops.WORK)
            self.assertEqual(ops.read_status(path), (None, None))
            ops.write_status(path, {"pid": 7, "map": "Arena1a"})
            status, age = ops.read_status(path, 7)
            self.assertEqual(status["map"], "Arena1a")
            self.assertLess(age, 5)
            self.assertEqual(ops.read_status(path, 8), (None, None))  # an older run's file
            path.write_text('{"pid": 7}')
            self.assertEqual(ops.read_status(path, 7), ({"pid": 7}, None))
            path.write_text("[1, 2]")
            self.assertEqual(ops.read_status(path), (None, None))


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / "logs/host.log"
        patch = mock.patch.object(host_app, "LOG", self.log)
        patch.start()
        self.addCleanup(patch.stop)

    def test_help_and_options_do_not_open_a_window(self):
        with mock.patch.object(host_app, "build") as build, contextlib.redirect_stdout(io.StringIO()) as out, \
                self.assertRaises(SystemExit) as stop:
            host_app.main(["--help"])
        self.assertEqual(stop.exception.code, 0)
        self.assertIn("--autostart", out.getvalue())
        build.assert_not_called()
        with mock.patch.object(host_app, "build") as build, contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            host_app.main(["--autostrat"])
        build.assert_not_called()
        root, window = mock.Mock(), mock.Mock()
        with mock.patch.object(host_app, "build", return_value=(root, window)) as build:
            self.assertEqual(host_app.main(["--autostart"]), 0)
        build.assert_called_once_with(None)
        root.after.assert_called_once_with(300, window.start)
        root.mainloop.assert_called_once_with()

    def test_startup_error_is_shown_and_logged(self):
        with mock.patch.object(host_app, "build", side_effect=KeyError("Bogus mode")), \
                mock.patch.dict("sys.modules", {"tkinter": None}), contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(host_app.main([]), 1)
        log = self.log.read_text()
        self.assertIn("KeyError: 'Bogus mode'", log)
        self.assertIn("Traceback", log)
        self.assertIn(str(self.log), err.getvalue())

    def test_shims_open_the_new_windows(self):
        for shim, module in (("host_control", "host_app"), ("client_launcher", "play_app")):
            text = (ROOT / "tools" / f"{shim}.py").read_text(encoding="utf-8")
            self.assertIn(f"from aoa.launchers.{module} import main", text)
        for cmd, shim in (("Play.cmd", "client_launcher"), ("Host.cmd", "host_control")):
            text = (ROOT / cmd).read_text(encoding="utf-8")
            self.assertIn(f"tools\\{shim}.py", text)
            self.assertIn(" -I ", text)
        for forwarder, cmd in (("client_launcher", "Play.cmd"), ("host_control", "Host.cmd")):
            self.assertIn(cmd, (ROOT / "tools" / f"{forwarder}.cmd").read_text(encoding="utf-8"))


@unittest.skipUnless((GAME / "SCRTY.BIN").is_file(), "needs the local 2.9.2 game folder")
class HostProcessTests(unittest.TestCase):
    """The window's run: hosting.run_config and the headless host's Supervisor, on a real server."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = settings.Settings(game_folder=str(GAME))
        self.settings.host.paths.update(log=str(Path(self.temp.name) / "host.jsonl"),
                                        status=str(Path(self.temp.name) / "status.json"))
        self.settings.host.extra_args = list(EPHEMERAL)
        self.supervisor = None

    def tearDown(self):
        if self.supervisor is not None and self.supervisor.process.running:
            self.supervisor.process.proc.kill()
            self.supervisor.process.proc.wait()

    def start(self, maps=("CTF_arena",)):
        hosting.set_maps(self.settings.host, list(maps))
        config = hosting.check(hosting.run_config(self.settings))
        self.supervisor = hosting.supervisor_for(config, report=lambda text: None)
        self.supervisor.start()
        return config

    def output(self):
        lines = []
        while not self.supervisor.process.output.empty():
            lines.append(self.supervisor.process.output.get())
        return lines

    def wait_status(self, timeout=15):
        deadline = time.time() + timeout
        while time.time() < deadline:
            data, age = self.supervisor.process.status()
            if data is not None:
                return data, age
            time.sleep(0.2)
        self.fail("no status file")

    def test_start_status_say_and_clean_quit(self):
        self.start()
        data, age = self.wait_status()
        self.assertEqual((data["profile"], data["map"], data["players"]), ("local-guests", "CTF_arena", []))
        self.assertLess(age, 5)
        self.assertTrue(self.supervisor.process.command("say hello pilots"))
        self.assertEqual(self.supervisor.stop(timeout=10), 0)
        self.assertEqual(self.supervisor.poll(), "stopped")
        time.sleep(0.3)
        text = "\n".join(self.output())
        self.assertIn("said to 0 player(s)", text)
        self.assertIn(ops.QUIT, text)
        self.assertIn("traffic:", text)  # ExitStack cleanup ran

    def test_change_map_restarts_on_the_new_map(self):
        self.start()
        self.wait_status()
        new = hosting.run_config(self.settings)
        hosting.set_maps(new, ["Arena1a"])
        hosting.change_map(self.supervisor, new, notice_seconds=0)
        deadline = time.time() + 15
        while time.time() < deadline:
            data, _ = self.supervisor.process.status()
            if data and data.get("map") == "Arena1a":
                break
            time.sleep(0.2)
        else:
            self.fail("the host did not restart on Arena1a")
        self.assertEqual(self.supervisor.stop(), 0)


if __name__ == "__main__":
    unittest.main()
