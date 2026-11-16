"""The launchers' logic without a window: settings, catalog, game folder, setup steps,
joining a friend and this PC's addresses. Game-free: the client is the synthetic
one of tests/support_patches.py, and the fetcher, resolver, socket and
PowerShell are fakes. Nothing here downloads or opens a window.

    python -I tools/test.py test_launcher_logic
"""
import hashlib
import io
import json
import socket
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from aoa.client import install_wrapper, patches, prepare
from aoa.host import defaults
from aoa.host.config import HostConfig
from aoa.host.config import ConfigError
from aoa.launchers import catalog, game_folder, hosting, install, join, netinfo, settings, tkcommon
from aoa.maps import registry
from tests import support_patches


def temp_dir(case):
    temp = tempfile.TemporaryDirectory()
    case.addCleanup(temp.cleanup)
    return Path(temp.name)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = temp_dir(self)
        self.path = self.dir / "settings.json"
        self.old = self.dir / "host_control.json"

    def load(self):
        return settings.load(self.path, old_host_file=self.old, root=self.dir)

    def test_missing_file_gives_defaults_and_saves_only_differences(self):
        s, notices = self.load()
        self.assertEqual(notices, [])
        self.assertEqual(s.server, "localhost")
        self.assertEqual(s.host.to_json(), settings.default_host().to_json())
        settings.save(s, self.path)
        self.assertEqual(json.loads(self.path.read_text()),
                         {"schema": 1, "host": {"schema": 1, "terrain": True, "objects": {
                             "navigation_buoys": False, "turret_trial": False, "warp_trial": False, "powerups": True}}})
        self.assertEqual(self.load()[0], s)

    def test_round_trip_stores_only_differences(self):
        s, _ = self.load()
        s.server, s.game_folder, s.skip_wrapper = "aoalan", "D:/Games/aoa", True
        s.add_friend("Sam", "192.168.0.61")
        s.add_friend("Kim", "100.101.102.103", "aoavpn")
        s.host.profile, s.host.bind_address, s.host.maps = "lan-dogfight", "192.168.0.61", ["Arena1a"]
        settings.save(s, self.path)
        data = json.loads(self.path.read_text())
        self.assertEqual(set(data["host"]), {"schema", "profile", "bind_address", "maps", "terrain", "objects"})
        self.assertEqual([f["name"] for f in data["client"]["friends"]], ["Kim", "Sam"])
        again, notices = self.load()
        self.assertEqual(notices, [])
        self.assertEqual(again, s)
        # The host object is a HostConfig file as it stands (the Linux host's format).
        self.assertEqual(HostConfig.from_json(data["host"], root=self.dir).bind_address, "192.168.0.61")

    def test_bad_values_are_named_and_the_rest_kept(self):
        self.path.write_text(json.dumps({
            "schema": 1, "colour": "red", "game_folder": 5,
            "client": {"server": "a-name-that-is-too-long", "friends": [{"name": "Sam", "address": "1.2.3.4"},
                                                                         {"name": "", "address": "x"}],
                       "volume": 3, "skip_wrapper": "yes"},
            "host": {"schema": 1, "profile": "lan-dogfight", "max_players": "eight", "maps": ["Nowhere"],
                     "kill_limit": 5, "bogus": 1}}))
        s, notices = self.load()
        text = "\n".join(notices)
        for word in ("'colour'", "game folder", "a-name-that-is-too-long", "'volume'", "skip_wrapper",
                     "'max_players'", "'maps'", "'bogus'", "friend"):
            self.assertIn(word, text)
        self.assertEqual((s.host.profile, s.host.kill_limit, s.host.max_players),
                         ("lan-dogfight", 5, defaults.LIMITS["max_players"]))
        self.assertEqual([f["name"] for f in s.friends], ["Sam"])
        self.assertEqual(s.server, "localhost")

    def test_unreadable_files_open_with_defaults(self):
        for text in ("{not json", "[1, 2]", json.dumps({"schema": 7})):
            self.path.write_text(text)
            s, notices = self.load()
            self.assertEqual(len(notices), 1, text)
            self.assertEqual(s, settings.Settings())

    def test_old_host_window_file_is_migrated_once_and_left_in_place(self):
        self.old.write_text(json.dumps({"mode": "LAN", "address": "192.168.1.5  (Ethernet)", "map": "CTF_arena",
                                        "terrain": True, "time_limit_min": 15, "max_players": 4,
                                        "navigation_buoys": False, "game": "elsewhere", "backdrop": "space"}))
        s, notices = self.load()
        self.assertEqual((s.host.profile, s.host.bind_address, s.host.maps, s.host.time_limit_seconds,
                          s.host.max_players, s.game_folder),
                         ("lan-dogfight", "192.168.1.5", ["CTF_arena"], 900, 4, "elsewhere"))
        self.assertTrue(any("host_control.json" in n for n in notices))
        settings.save(s, self.path)
        self.assertTrue(self.old.exists())
        self.old.write_text(json.dumps({"mode": "VPN (internet)"}))
        self.assertEqual(self.load()[0].host.profile, "lan-dogfight")  # read once only

    def test_headless_host_reads_the_settings_file(self):
        from aoa.host import headless
        s, _ = self.load()
        s.host.profile, s.host.bind_address = "lan-dogfight", "192.168.0.61"
        s.game_folder = "D:/Games/aoa"
        settings.save(s, self.path)
        config = headless.load(self.path)
        self.assertEqual((config.profile, config.bind_address), ("lan-dogfight", "192.168.0.61"))
        self.assertEqual(config.paths["game"], "D:/Games/aoa")

    def test_host_config_for_a_run_uses_the_shared_game_folder(self):
        s = settings.Settings(game_folder="D:/Games/aoa")
        self.assertEqual(settings.host_config(s).paths["game"], "D:/Games/aoa")
        s.host.paths["game"] = "C:/other"
        self.assertEqual(settings.host_config(s).paths["game"], "C:/other")


class CatalogTests(unittest.TestCase):
    def test_maps_playable_first_with_notes(self):
        self.assertEqual({m.name for m in catalog.MAPS}, set(registry.MAP_NAMES))
        flags = [m.playable for m in catalog.MAPS]
        self.assertEqual(flags, sorted(flags, reverse=True))
        self.assertEqual({m.name for m in catalog.PLAYABLE_MAPS},
                         {n for n, c in registry.CONTENT.items() if c == registry.PLAYABLE})
        self.assertTrue(all(m.note for m in catalog.MAPS))
        self.assertEqual(catalog.BY_NAME["JRMAP"].client_file, "jrmap292.trn")

    def test_every_option_has_words_and_a_group(self):
        self.assertEqual({o.key for o in catalog.OPTIONS}, set(patches.OPTIONS))
        for option in catalog.OPTIONS:
            self.assertIn(option.group, dict(catalog.GROUPS))
            self.assertTrue(option.label and option.help.endswith("."))
            self.assertLessEqual(len(option.label), 40)
        self.assertEqual(sum(len(o) for _, o in catalog.grouped_options()), len(catalog.OPTIONS))
        pairs = {frozenset((o.key, c)) for o in catalog.OPTIONS for c in o.conflicts}
        self.assertEqual(pairs, {frozenset((a.option, b.option)) for a, b in patches.CONFLICTS})
        self.assertIn("only one", catalog.conflict_sentence("experimental_solids", "experimental_asteroids"))

    def test_presets(self):
        self.assertEqual(catalog.recommended(), {k: p.default for k, p in patches.OPTIONS.items()})
        original = catalog.original_visuals()
        self.assertTrue(original["smooth_frame_clock"] and original["bounded_visibility"])  # fixes stay
        self.assertFalse(original["chase_camera"] or original["distant_objects"])

    def test_audiences_and_features(self):
        self.assertEqual([a.profile for a in catalog.AUDIENCES], ["local-guests", "lan-dogfight", "vpn-dogfight"])
        self.assertTrue(all(a.profile in defaults.PROFILES for a in catalog.AUDIENCES))
        self.assertEqual([n for n, _ in catalog.BACKDROPS], list(defaults.BACKDROPS))
        self.assertIn("11", catalog.feature_sentence("terrain"))
        config = HostConfig(maps=["JRMAP"], terrain=True, objects={"powerups": True})
        self.assertEqual(catalog.host_needs(config), ["terrain", "power-ups"])
        self.assertEqual(catalog.host_needs(HostConfig()), [])

    def test_object_availability(self):
        ok = catalog.object_availability("local-guests", ["Arena1a"], True, True)
        self.assertEqual(ok, dict.fromkeys(ok, ""))
        lan = catalog.object_availability("lan-dogfight", ["Arena1a"], True, True)
        self.assertTrue(lan["warp_trial"] and not lan["turret_trial"])
        other = catalog.object_availability("local-guests", ["CTF_arena"], True, True)
        self.assertTrue(other["turret_trial"] and not other["navigation_buoys"])
        self.assertTrue(all(catalog.object_availability("local-guests", ["Arena1a"], False, True).values()))
        self.assertIn("exported", catalog.object_availability("local-guests", ["Arena1a"], True, False)[
            "navigation_buoys"])


class SyntheticGame:
    """A game folder holding the synthetic client, with the asset check stubbed."""

    def setUp(self):
        self.pristine = support_patches.synthetic_pristine()
        self.enterContext(support_patches.synthetic_client(self.pristine))
        self.enterContext(mock.patch.object(prepare, "check_assets", return_value=0))
        self.root = temp_dir(self)
        self.folder = self.root / "game"
        self.folder.mkdir()
        (self.folder / "AOACLIENT.EXE").write_bytes(self.pristine)
        self.exe = self.folder / "AOACLIENT.EXE"


class GameFolderTests(SyntheticGame, unittest.TestCase):
    def test_states(self):
        state = game_folder.examine(self.root / "nowhere", lambda f: None)
        self.assertEqual((state.exe, state.exists, state.ready), ("missing", False, False))
        state = game_folder.examine(self.folder, lambda f: None)
        self.assertEqual((state.exe, state.assets_ok, state.wrapper), ("original", True, "none"))
        prepare.prepare(self.exe)
        state = game_folder.examine(self.folder, lambda f: True)
        self.assertEqual((state.exe, state.patch_level, state.ready, state.skin, state.server),
                         ("prepared", prepare.PATCH_VERSION, True, True, "localhost"))
        record = json.loads((self.folder / "_client_setup.json").read_text())
        record["patch_version"] = 20
        (self.folder / "_client_setup.json").write_text(json.dumps(record))
        self.assertEqual(game_folder.examine(self.folder, lambda f: None).exe, "update")
        self.exe.write_bytes(b"MZ not the game")
        state = game_folder.examine(self.folder, lambda f: None)
        self.assertEqual(state.exe, "unknown")
        self.assertTrue(state.exe_problem)

    def test_assets_and_wrapper_problems_are_reported(self):
        with mock.patch.object(prepare, "check_assets", side_effect=ValueError("missing game dependency: DATA.AOA")):
            state = game_folder.examine(self.folder, lambda f: None)
        self.assertFalse(state.assets_ok)
        self.assertIn("DATA.AOA", state.assets_problem)
        (self.folder / "DDraw.dll").write_bytes(b"x")
        self.assertEqual(game_folder.examine(self.folder, lambda f: None).wrapper, "damaged")

    def test_skin_registration(self):
        self.assertIsNone(game_folder.skin_registered(self.folder, "linux"))
        ocx = str((self.folder / game_folder.OCX).resolve())
        self.assertFalse(game_folder.skin_registered(self.folder, "win32", lambda: None))
        game_folder.record_skin(self.folder)
        self.assertTrue(game_folder.skin_registered(self.folder, "win32", lambda: None))
        self.assertTrue(game_folder.skin_registered(self.folder, "win32", lambda: {ocx}))
        # The registry wins when it can be read: a moved folder is not registered.
        self.assertFalse(game_folder.skin_registered(self.folder, "win32", lambda: {"C:/old/ACTIVESKIN.OCX"}))

    def test_wrapper_zip_search(self):
        downloads = self.root / "Downloads"
        downloads.mkdir()
        self.assertEqual(game_folder.find_wrapper_zip([downloads]), (None, []))
        (downloads / "dgVoodoo2_87_5.zip").write_bytes(b"not it")
        self.assertEqual(game_folder.find_wrapper_zip([downloads]), (None, [downloads / "dgVoodoo2_87_5.zip"]))
        with mock.patch.object(install_wrapper, "ZIP_SHA256", hashlib.sha256(b"not it").hexdigest()):
            self.assertEqual(game_folder.find_wrapper_zip([downloads])[0], downloads / "dgVoodoo2_87_5.zip")


def wrapper_zip():
    conf = "Version = 0x287\n[General]\nFullScreenMode = true\nCenterAppWindow = false\n[DirectX]\n" \
           "dgVoodooWatermark = true\nDisableAltEnterToToggleScreenMode = true\nAntialiasing = appdriven\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("MS/x86/DDraw.dll", b"ddraw")
        z.writestr("MS/x86/D3DImm.dll", b"d3dimm")
        z.writestr("dgVoodoo.conf", conf)
    return buffer.getvalue()


class InstallStepTests(SyntheticGame, unittest.TestCase):
    ENTRY = {"runtime_version": "2.9.2", "bytes": 3, "suggested_local_filename": "aoa_installer.exe"}

    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(install, "installer_entry", return_value=self.ENTRY))
        self.downloads = self.root / "builds"
        self.settings = settings.Settings(game_folder=str(self.root / "new-game"))
        self.calls = []

    def context(self, platform="linux", **changes):
        context = install.Context(self.settings, runner=self.fake_run, platform=platform,
                                  downloads_root=self.downloads, wrapper_folders=[self.root / "Downloads"],
                                  python="python")
        for key, value in changes.items():
            setattr(context, key, value)
        context.refresh()
        return context

    def fake_run(self, argv, **kwargs):
        self.calls.append(argv)
        if Path(argv[2]).name == "fetch.py":
            (Path(argv[5]) / self.ENTRY["suggested_local_filename"]).write_bytes(b"abc")
        return mock.Mock(returncode=0, stdout="ok", stderr="")

    def statuses(self, context):
        context.refresh()
        return {step.key: status.state for step, status in install.checklist(context)}

    def test_fresh_pc_to_ready(self):
        context = self.context()
        self.assertEqual(self.statuses(context), {"files": "todo", "folder": "waiting", "fixes": "waiting",
                                                  "skin": "unavailable", "wrapper": "waiting"})
        rows = install.checklist(context)
        self.assertIn("35 MB" if self.ENTRY["bytes"] > 1e6 else "archive.org", rows[0][1].text)
        install.GameFiles(context).run(lambda text: None)
        fetch = self.calls[0]
        self.assertEqual(fetch[:2], ["python", "-I"])
        self.assertEqual([Path(fetch[2]).name, Path(fetch[3]).name, fetch[4]], ["fetch.py", "downloads.json", "2.9.2"])
        self.assertEqual(Path(fetch[5]).parent, self.downloads)
        self.assertEqual(self.statuses(context)["folder"], "todo")
        # Build the folder from a stand-in installer (a ZIP, as the Wise installer is).
        installer = install.find_installer(self.downloads, self.ENTRY)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("Games/AOACLIENT.EXE", self.pristine)
            z.writestr("WISE0001.DLL", b"installer only")
        installer.chmod(0o644)
        installer.write_bytes(buffer.getvalue())
        self.ENTRY = {**self.ENTRY, "bytes": len(buffer.getvalue())}
        with mock.patch.object(install, "installer_entry", return_value=self.ENTRY), \
                mock.patch.dict(install.builds.INSTALLER_SHA256, {"2.9.2": game_folder.sha_file(installer)}), \
                mock.patch("sys.stdout", io.StringIO()):
            install.BuildFolder(context).run(lambda text: None)
            self.assertEqual(self.statuses(context), {"files": "done", "folder": "done", "fixes": "todo",
                                                      "skin": "unavailable", "wrapper": "optional"})
        folder = context.folder
        self.assertFalse((folder / "WISE0001.DLL").exists())
        self.assertEqual((folder / "AOACLIENT.EXE.orig").read_bytes(), self.pristine)
        self.assertFalse(install.complete(install.checklist(context)))
        install.Fixes(context).run(lambda text: None)
        context.refresh()
        rows = install.checklist(context)
        self.assertIn(f"patch level {prepare.PATCH_VERSION}", rows[2][1].text)
        self.assertTrue(install.complete(rows))

    def test_build_refuses_a_wrong_installer_and_an_existing_folder(self):
        context = self.context()
        with self.assertRaisesRegex(install.StepError, "step 1"):
            install.BuildFolder(context).run(lambda text: None)
        (self.downloads / "v").mkdir(parents=True)
        (self.downloads / "v" / self.ENTRY["suggested_local_filename"]).write_bytes(b"abc")
        with self.assertRaisesRegex(install.StepError, "not the expected"):
            install.BuildFolder(context).run(lambda text: None)
        self.settings.game_folder = str(self.folder)
        with self.assertRaisesRegex(install.StepError, "already exists"):
            install.BuildFolder(context).run(lambda text: None)

    def test_failed_download_says_what_to_do(self):
        def fail(argv, **kwargs):
            return mock.Mock(returncode=1, stdout="", stderr="HTTP Error 503\n")
        context = self.context(runner=fail)
        with self.assertRaises(install.StepError) as caught:
            install.GameFiles(context).run(lambda text: None)
        self.assertIn("try again", str(caught.exception))
        self.assertIn("503", caught.exception.details)

    def test_existing_folder_skin_and_wrapper(self):
        self.settings.game_folder = str(self.folder)
        prepare.prepare(self.exe)
        context = self.context(platform="win32")
        with mock.patch.object(game_folder, "user_com_servers", return_value=None):
            self.assertEqual(self.statuses(context), {"files": "done", "folder": "done", "fixes": "done",
                                                      "skin": "todo", "wrapper": "optional"})
            self.assertFalse(install.complete(install.checklist(context)))
            install.Skin(context).run(lambda text: None)
            self.assertEqual(self.calls[-1][:2], ["powershell", "-NoProfile"])
            self.assertEqual(Path(self.calls[-1][5]).name, "register_activeskin.ps1")
            self.assertEqual(self.statuses(context)["skin"], "done")
            self.assertTrue(install.complete(install.checklist(context)))
        wrapper = install.Wrapper(context)
        with self.assertRaisesRegex(install.StepError, "not in"):
            wrapper.run(lambda text: None)
        downloads = self.root / "Downloads"
        downloads.mkdir()
        data = wrapper_zip()
        (downloads / "dgVoodoo2_87_5.zip").write_bytes(data)
        with self.assertRaisesRegex(install.StepError, "not version 2.87.5"):
            wrapper.run(lambda text: None)
        digests = {"DDraw.dll": hashlib.sha256(b"ddraw").hexdigest(), "D3DImm.dll": hashlib.sha256(b"d3dimm").hexdigest()}
        with mock.patch.object(install_wrapper, "ZIP_SHA256", hashlib.sha256(data).hexdigest()), \
                mock.patch.dict(prepare.WRAPPERS, digests), mock.patch("sys.stdout", io.StringIO()):
            wrapper.run(lambda text: None)
            context.refresh()
            self.assertEqual(context.state.wrapper, "installed")
            self.assertEqual(json.loads((self.folder / "_client_setup.json").read_text())["wrapper"],
                             "dgVoodoo2-2.87.5")
        self.settings.skip_wrapper = True
        for name in ("DDraw.dll", "D3DImm.dll"):
            (self.folder / name).unlink()
        self.assertEqual(self.statuses(context)["wrapper"], "skipped")

    def test_options_survive_the_fixes_step_and_join(self):
        self.settings.game_folder = str(self.folder)
        prepare.prepare(self.exe, {"chase_camera": False, "distant_objects": True})
        record = json.loads((self.folder / "_client_setup.json").read_text())
        record["patch_version"] = 20
        (self.folder / "_client_setup.json").write_text(json.dumps(record))
        context = self.context()
        install.Fixes(context).run(lambda text: None)
        join.apply(self.exe, "aoalan")
        state = prepare.check(self.exe, require_assets=False)
        self.assertEqual(state["host"], "aoalan")
        self.assertIn("distant-world-objects-v1", state["patches"])
        self.assertNotIn("third-person-camera-v3", state["patches"])

    def test_join_switches_the_protection_probe_off_only_for_another_pc(self):
        prepare.prepare(self.exe, {"experimental_protection": True})
        join.apply(self.exe, "127.0.0.1")
        self.assertIn(prepare.LOOPBACK_ONLY, prepare.check(self.exe, require_assets=False)["patches"])
        join.apply(self.exe, "192.168.1.5")
        self.assertNotIn(prepare.LOOPBACK_ONLY, prepare.check(self.exe, require_assets=False)["patches"])


class FakeConnection:
    def close(self):
        pass


class JoinTests(unittest.TestCase):
    def test_parse(self):
        line = join.share_line("100.101.102.103", "aoavpn")
        cases = {line: ("100.101.102.103", "aoavpn"), "192.168.1.5": ("192.168.1.5", None),
                 "  aoa://100.101.102.103?name=aoavpn ": ("100.101.102.103", "aoavpn"),
                 "aoalan": ("aoalan", None), "my server is 10.0.0.5 ok": ("10.0.0.5", None),
                 "Ace of Angels server 192.168.10.25 (name aoalan)": ("192.168.10.25", "aoalan")}
        for text, expected in cases.items():
            with self.subTest(text=text):
                target = join.parse(text)
                self.assertEqual((target.address, target.alias), expected)
        for bad in ("", "  ", "hello there friend", "999.1.1.1", "0.0.0.0"):
            with self.subTest(bad=bad), self.assertRaises(ValueError) as caught:
                join.parse(bad)
            self.assertTrue(str(caught.exception).endswith("."))

    def test_plan(self):
        short = join.plan(join.parse("192.168.1.5"))
        self.assertEqual((short.server, short.needs_hosts), ("192.168.1.5", False))
        long = join.plan(join.parse(join.share_line("100.101.102.103", "aoavpn")))
        self.assertEqual((long.server, long.hosts_line), ("aoavpn", "100.101.102.103 aoavpn"))
        self.assertEqual(join.plan(join.parse("192.168.100.200")).hosts_line, "192.168.100.200 aoavpn")
        self.assertEqual(join.plan(join.parse("aoalan")).server, "aoalan")
        with self.assertRaisesRegex(ValueError, "longer than"):
            join.plan(join.parse("my.long.server.name"))

    def test_three_checks_with_fakes(self):
        long = join.plan(join.parse("100.101.102.103 (name aoavpn)"))
        def resolver(table):
            def resolve(name):
                if name not in table:
                    raise socket.gaierror("not found")
                return table[name]
            return resolve
        refused = mock.Mock(side_effect=ConnectionRefusedError())
        results = join.checks(long, resolver({}), refused)
        self.assertEqual([c.ok for c in results], [True, False, False])
        self.assertIn("hosts file", results[1].text)
        self.assertIn("not running", results[2].text)
        connect = mock.Mock(return_value=FakeConnection())
        results = join.checks(long, resolver({"aoavpn": "100.101.102.103"}), connect)
        self.assertEqual([c.ok for c in results], [True, True, True])
        connect.assert_called_once_with(("100.101.102.103", defaults.PORTS["tcp"]), 3.0)
        wrong = join.check_name(long, resolver({"aoavpn": "100.64.0.9"}))
        self.assertFalse(wrong.ok)
        self.assertIn("100.64.0.9", wrong.text)
        timeout = join.check_answers(long, mock.Mock(side_effect=socket.timeout()))
        self.assertIn("No answer", timeout.text)
        short = join.plan(join.parse("192.168.1.5"))
        self.assertTrue(join.check_name(short, resolver({})).ok)
        named = join.plan(join.parse("aoalan"))
        self.assertFalse(join.check_name(named, resolver({})).ok)
        self.assertTrue(join.check_name(named, resolver({"aoalan": "192.168.1.5"})).ok)

    def test_notepad_command_only_opens_the_file(self):
        command = join.open_hosts_command()
        self.assertIn("RunAs", command[-1])
        self.assertIn(join.HOSTS_FILE, command[-1])


class NetinfoTests(unittest.TestCase):
    def test_kinds(self):
        for address, kind in (("127.0.0.1", "loopback"), ("192.168.1.5", "home"), ("10.1.2.3", "home"),
                              ("172.20.0.1", "home"), ("100.101.102.103", "vpn"), ("169.254.3.4", "link-local"),
                              ("8.8.8.8", "other"), ("100.128.0.1", "other")):
            self.assertEqual(netinfo.kind(address), kind, address)

    def test_addresses_are_unique_and_ordered(self):
        found = netinfo.addresses((lambda: ["127.0.0.1", "100.101.102.103", "192.168.1.5", "bad"],
                                   lambda: ["192.168.1.5", "8.8.4.4"]))
        self.assertEqual(found, [("192.168.1.5", "home"), ("100.101.102.103", "vpn"), ("8.8.4.4", "other"),
                                 ("127.0.0.1", "loopback")])
        self.assertEqual(netinfo.for_kind(found, "vpn"), ["100.101.102.103"])
        self.assertEqual(netinfo.for_kind(found, None), ["127.0.0.1"])

    def test_real_lookup_sends_nothing_and_returns_a_list(self):
        self.assertIsInstance(netinfo.addresses(), list)


class FakeSupervisor:
    def __init__(self):
        self.calls, self.state = [], {"map": "CTF_arena"}
        self.process = mock.Mock(command=lambda line: self.calls.append(("say", line)))

    def stop(self):
        self.calls.append(("stop",))

    def change(self, config):
        self.calls.append(("change", config.maps))

    def start(self, config):
        self.calls.append(("start", config.maps, self.state["map"]))


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir(self)
        game = self.root / "game/2.9.2"
        game.mkdir(parents=True)
        (game / "SCRTY.BIN").write_bytes(bytes(256))
        self.settings = settings.Settings()
        self.settings.host.root = self.root

    def test_audience_maps_and_run_config(self):
        config = self.settings.host
        hosting.set_audience(config, "home", " 192.168.0.61 ")
        self.assertEqual((config.profile, config.bind_address), ("lan-dogfight", "192.168.0.61"))
        hosting.set_audience(config, "this-pc", "192.168.0.61")
        self.assertEqual(config.bind_address, "127.0.0.1")
        found = [("192.168.0.61", "home"), ("100.101.102.103", "vpn")]
        hosting.set_audience(config, "vpn")
        self.assertEqual(hosting.address_choices(config, found), ["100.101.102.103"])
        hosting.set_maps(config, ["Arena1a", "CTF_arena", "Arena1a"])
        self.assertEqual((config.maps, config.managed, config.terrain), (["Arena1a", "CTF_arena"], {}, True))
        hosting.set_maps(config, ["Arena1a"])
        self.assertIsNone(config.managed)
        with self.assertRaises(ConfigError):
            hosting.set_maps(config, [])
        config.objects.update(navigation_buoys=True, turret_trial=True, warp_trial=True)
        run = hosting.run_config(self.settings, export_ready=False)
        self.assertFalse(any(run.objects[k] for k in ("navigation_buoys", "turret_trial", "warp_trial")))
        self.assertTrue(run.console and run.objects["powerups"])
        self.assertTrue(config.objects["navigation_buoys"])  # the saved settings keep the choice
        run = hosting.run_config(self.settings, export_ready=True)
        self.assertEqual([run.objects[k] for k in ("navigation_buoys", "turret_trial", "warp_trial")],
                         [True, True, False])  # warp gates: this PC only
        self.assertTrue(run.sustained_delivery)
        self.assertEqual(run.path("game"), self.root / "game/2.9.2")

    def test_check_before_start(self):
        config = hosting.run_config(self.settings, export_ready=False)
        hosting.check(config)
        hosting.set_audience(config, "home", "")
        with self.assertRaisesRegex(ConfigError, "home-network address"):
            hosting.check(config)
        hosting.set_audience(config, "home", "8.8.8.8")
        with self.assertRaisesRegex(ConfigError, "Choose an address from the list"):
            hosting.check(config)
        hosting.set_audience(config, "this-pc")
        hosting.set_maps(config, ["JRMAP"])
        with self.assertRaisesRegex(ConfigError, "Install JRMAP terrain"):
            hosting.check(config)
        self.settings.game_folder = str(self.root / "nowhere")
        with self.assertRaisesRegex(ConfigError, "No game found"):
            hosting.check(hosting.run_config(self.settings, export_ready=False))

    def test_share_line_reaches_the_join_tab(self):
        config = self.settings.host
        self.assertIn("This PC", hosting.share_text(config))
        self.assertEqual(hosting.firewall_commands(config), [])
        for key, address, server in (("home", "192.168.0.61", "aoalan"), ("vpn", "100.101.102.103", "aoavpn"),
                                     ("home", "10.0.0.5", "10.0.0.5")):
            hosting.set_audience(config, key, address)
            target = join.parse(hosting.share_text(config))
            self.assertEqual((target.address, join.plan(target).server), (address, server))

    def test_firewall_commands_are_the_documented_ones(self):
        config = self.settings.host
        for key, address, doc in (("home", "192.168.0.61", "lan-dogfight.md"),
                                  ("vpn", "100.101.102.103", "vpn-dogfight.md")):
            hosting.set_audience(config, key, address)
            text = (settings.ROOT / "docs" / doc).read_text(encoding="utf-8")
            for line in hosting.firewall_commands(config):
                self.assertIn(line.replace("5031,5033", "5031,5033"), text)

    def test_change_map_checks_first(self):
        supervisor = FakeSupervisor()
        bad = hosting.run_config(self.settings, export_ready=False)
        hosting.set_maps(bad, ["JRMAP"])
        with self.assertRaises(ConfigError):
            hosting.change_map(supervisor, bad, sleep=lambda s: None)
        self.assertEqual(supervisor.calls, [])  # nothing said, nothing stopped
        good = hosting.run_config(self.settings, export_ready=False)
        hosting.set_maps(good, ["Arena1a"])
        hosting.change_map(supervisor, good, sleep=lambda s: None)
        self.assertEqual([c[0] for c in supervisor.calls], ["say", "stop", "change", "start"])
        self.assertIn("Arena1a", supervisor.calls[0][1])
        self.assertEqual(supervisor.calls[-1], ("start", ["Arena1a"], "Arena1a"))

    def test_status_text_and_rows(self):
        config = self.settings.host
        self.assertEqual(hosting.status_lines(None, config), ("Starting…", ""))
        status = {"map": "CTF_arena", "match": 2, "uptime_s": 3725, "max_players": 8, "arena_joins_used": 3,
                  "arena_joins_limit": 49, "banned_ips": 0,
                  "players": [{"slot": 1, "pilot": "a", "kills": 1, "deaths": 0},
                              {"slot": 2, "pilot": "b", "kills": 4, "deaths": 2, "ping_ms": 31, "loaded": True}]}
        headline, detail = hosting.status_lines(status, config, age=20)
        self.assertIn("1:02:05", headline)
        self.assertIn("not responding", headline)
        self.assertIn("2 of 8 players", detail)
        self.assertEqual([r[0] for r in hosting.player_rows(status)], [2, 1])
        self.assertIn("This PC only", hosting.describe(config))

    def test_supervisor_is_the_headless_one(self):
        config = hosting.run_config(self.settings, export_ready=False)
        supervisor = hosting.supervisor_for(config, report=lambda text: None, process=mock.Mock())
        self.assertIsNone(supervisor.state_path)
        hosting.set_maps(config, ["Arena1a", "CTF_arena"])
        supervisor = hosting.supervisor_for(config, report=lambda text: None, process=mock.Mock())
        self.assertEqual(supervisor.state_path, config.path("state"))
        self.assertEqual(supervisor.watchdog_timeout, defaults.MANAGED["health_timeout_seconds"])


class WorkerTests(unittest.TestCase):
    """The worker runner: the job runs off the calling thread; results come back through pump()."""

    def drive(self, worker, scheduled):
        import time
        for _ in range(500):
            if not scheduled:
                return
            scheduled.pop(0)()
            time.sleep(0.005)
        self.fail("the worker never finished")

    def test_result_progress_and_error(self):
        import threading
        scheduled, seen = [], []
        worker = tkcommon.Worker(lambda ms, callback: scheduled.append(callback))
        worker.on_busy = lambda busy: seen.append(("busy", busy))
        caller = threading.get_ident()

        def job(progress):
            progress("half way")
            return threading.get_ident()

        self.assertTrue(worker.submit(job, lambda r: seen.append(("done", r != caller)),
                                      progress=lambda t: seen.append(("progress", t))))
        self.assertFalse(worker.submit(job))  # one job at a time
        self.drive(worker, scheduled)
        self.assertEqual(seen, [("busy", True), ("progress", "half way"), ("busy", False), ("done", True)])
        self.assertFalse(worker.busy)
        failures = []
        worker.submit(lambda progress: 1 / 0, failed=failures.append)
        self.drive(worker, scheduled)
        self.assertIsInstance(failures[0], ZeroDivisionError)

    def test_error_log(self):
        path = temp_dir(self) / "logs/launcher.log"
        try:
            raise install.StepError("The download did not finish.", "HTTP Error 503")
        except install.StepError as error:
            tkcommon.log_error(path, "download", error)
            details = tkcommon.details_of(error)
        text = path.read_text()
        self.assertIn("download", text)
        self.assertIn("StepError: The download did not finish.", text)
        self.assertTrue(details.startswith("HTTP Error 503"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
