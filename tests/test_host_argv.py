"""Golden snapshot of every server command line the launchers and docs build; game-free.

Builds the station_stub.py arguments that each front end produces today:
host_control.server_args over a settings matrix, dedicated_host's child
arguments for the deploy/linux/*.example files, map_viewer serve, the
start_lan_dogfight.ps1 examples (mirrored here, since PowerShell cannot run
in this test) and every server command line in the docs. Each must parse with
station_runtime.parse_args; the arguments and the resulting effective config
are compared with tests/snapshots/host_configs.json.

  python -I tools/test.py test_host_argv               compare with the snapshot
  python -I tools/test.py test_host_argv -- --update   rewrite the snapshot

Paths are written relative to a scratch repository root (deploy paths keep
their /etc and /var/lib form). Nothing is started and no socket is opened.
"""
import contextlib
import io
import itertools
import json
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aoa.host import dedicated  # noqa: E402
from aoa.host import headless  # noqa: E402
from aoa.host.config import HostConfig  # noqa: E402
from aoa.launchers import host_control  # noqa: E402
from aoa.host import ops  # noqa: E402
from aoa.maps import map_viewer  # noqa: E402
from aoa.maps import registry  # noqa: E402
from aoa.host import runtime  # noqa: E402
from aoa.host.runtime import parse_args  # noqa: E402

from aoa.paths import ROOT
SNAPSHOT = Path(__file__).resolve().parent / "snapshots/host_configs.json"
DEPLOY = ROOT / "deploy/linux"
ADDRESSES = {"local-guests": "127.0.0.1", "lan-dogfight": "192.168.1.5", "vpn-dogfight": "100.101.102.103"}
NODES_ON = dict.fromkeys(host_control.NODE_LABELS, True)
NODES_OFF = dict.fromkeys(host_control.NODE_LABELS, False)
# One row per mode: name, assets exported, settings changes.
HOST_CONTROL_CASES = (
    ("defaults", True, {}),
    ("defaults, no exported assets", False, {}),
    ("terrain off", True, {"terrain": False}),
    ("Arena1a, all nodes", True, NODES_ON),
    ("CTF_arena, all nodes", True, {"map": "CTF_arena", **NODES_ON}),
    ("JRMAP, no nodes", True, {"map": "JRMAP", **NODES_OFF}),
    ("limits and backdrop", True, {"max_players": 2, "kill_limit": 10, "time_limit_min": 15, "target_ships": 0,
                                   "backdrop": "spacebkgd", "map": "ast_fld_a"}),
)
MAP_VIEWER_CASES = (["serve", "Arena1a"], ["serve", "CTF_arena", "--backdrop", "spacebkgd5"],
                    ["serve", "JRMAP", "--spawn-at", "1", "2", "3", "--seconds", "5"])
# start_lan_dogfight.ps1 parameters: its two .EXAMPLE lines and the -Terrain and test-impairment switches.
PS1_CASES = ({"HostAddress": "192.168.1.55"},
             {"Vpn": True, "HostAddress": "100.101.102.103", "MaxPlayers": 4},
             {"HostAddress": "192.168.1.55", "Map": "Arena1a", "Terrain": True},
             {"HostAddress": "192.168.1.55", "TestRttMs": 80, "TestLossPercent": 1})
DOC_COMMAND = re.compile(r"python(?:\.exe)?\s+-I\s+tools[/\\]station_stub\.py\s+([^`]*)")


def make_root(base, assets=True):
    """Scratch repository root with the files the server checks for."""
    game = base / "game/2.9.2"
    game.mkdir(parents=True)
    (game / "SCRTY.BIN").write_bytes(bytes(256))
    (game / "jrmap292.trn").write_bytes(b"")
    (game / "JRMAP.TRN").write_bytes(b"")  # navigation buoys on JRMAP
    if assets:
        export = base / "work/2.9.2/export/AOAOBJECTS"
        export.mkdir(parents=True)
        (export / "Arena1a.Gob").write_bytes(b"")
        (export.parent / "_export.json").write_text("{}")
    return base


def normalize(value, prefixes):
    """JSON-ready value; absolute paths under a scratch prefix are given their published form."""
    if isinstance(value, (list, tuple)):
        return [normalize(v, prefixes) for v in value]
    if isinstance(value, (str, Path)) and Path(value).is_absolute():
        for prefix, published in prefixes:
            with contextlib.suppress(ValueError):
                relative = Path(value).relative_to(prefix).as_posix()
                return f"{published}/{relative}" if published else relative
    return Path(value).as_posix() if isinstance(value, Path) else value


def effective(argv):
    """station_runtime.parse_args(argv) as a dict; a parse error raises ValueError with its message."""
    error = io.StringIO()
    try:
        with contextlib.redirect_stderr(error):
            return vars(parse_args(argv))
    except SystemExit:
        lines = error.getvalue().strip().splitlines()
        raise ValueError(lines[-1] if lines else "parse error") from None


def case(argv, prefixes, **extra):
    return {**extra, "argv": normalize(argv, prefixes),
            "config": {k: normalize(v, prefixes) for k, v in sorted(effective(argv).items())}}


def host_control_cases():
    out = {}
    for mode, (label, assets, changes) in itertools.product(host_control.MODES, HOST_CONTROL_CASES):
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(Path(temp).resolve(), assets)
            settings = {**host_control.DEFAULTS, "mode": mode, "address": ADDRESSES[mode], **changes}
            with mock.patch.object(host_control, "ROOT", root), mock.patch.object(host_control, "WORK", root / "work/host"):
                argv = host_control.server_args(settings)
            out[f"{host_control.MODES[mode]}: {label}"] = case(
                argv[1:], [(root, "")], assets_exported=assets, settings=settings,
                script=normalize(argv[0], [(root, "")]))
    return out


def deploy_cases():
    """aoa_host.py as aoa-host.service starts it, with host.json.example as its host.json."""
    line = next(l for l in (DEPLOY / "aoa-host.service").read_text().splitlines() if l.startswith("ExecStart="))
    argv = shlex.split(line[len("ExecStart="):])
    action, config = argv[[Path(a).name for a in argv].index("aoa_host.py") + 1:]
    if (action, config) != ("run", "/etc/ace-of-angels/host.json"):
        raise ValueError(f"unexpected aoa-host.service command: {action} {config}")
    config = headless.load(DEPLOY / "host.json.example")
    return {f"aoa-host.service: {name}": case(config.to_argv(name), []) for name in config.maps}


def legacy_deploy_cases():
    """dedicated_host with the older host.env.example and rotation.json.example, as the unit started it before."""
    env = dict(line.split("=", 1) for line in (DEPLOY / "host.env.example").read_text().splitlines()
               if line.strip() and not line.startswith("#"))
    command = ("/usr/bin/python3 -I -u /opt/ace-of-angels/tools/dedicated_host.py /etc/ace-of-angels/SCRTY.BIN "
               "/var/lib/ace-of-angels/host.jsonl --config /etc/ace-of-angels/rotation.json --state-file "
               "/var/lib/ace-of-angels/rotation-state.json --profile vpn-dogfight --bind-address ${AOA_BIND_ADDRESS} "
               "--max-players ${AOA_MAX_PLAYERS} --status-file /var/lib/ace-of-angels/status.json")
    command = re.sub(r"\$\{(\w+)\}", lambda m: env[m.group(1)], command)
    argv = shlex.split(command)
    argv = argv[[Path(a).name for a in argv].index("dedicated_host.py") + 1:]
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp).resolve()
        prefixes = [(root / "etc", "/etc/ace-of-angels"), (root / "var", "/var/lib/ace-of-angels")]
        for folder, _ in prefixes:
            folder.mkdir()
        (root / "etc/SCRTY.BIN").write_bytes(bytes(256))
        shutil.copyfile(DEPLOY / "rotation.json.example", root / "etc/rotation.json")
        local = []
        for a in argv:
            for prefix, published in prefixes:
                if a.startswith(published + "/"):
                    a = str(prefix / a[len(published) + 1:])
            local.append(a)
        seen = []
        with mock.patch.object(dedicated, "run", side_effect=lambda args, settings: seen.append((args, settings))):
            if dedicated.main(local) is not None or len(seen) != 1:
                raise ValueError("dedicated_host did not reach its run loop")
        args, settings = seen[0]
        return {f"aoa-host.service: {name}": case(dedicated.child_args(args, settings, name), prefixes)
                for name in settings["maps"]}


class DeployTests(unittest.TestCase):
    def test_old_two_file_form_reads_as_host_json(self):
        # A host still on rotation.json + host.env runs the same server as host.json.example.
        self.assertEqual(legacy_deploy_cases(), deploy_cases())
        with tempfile.TemporaryDirectory() as temp:
            shutil.copyfile(DEPLOY / "rotation.json.example", Path(temp) / "rotation.json")
            shutil.copyfile(DEPLOY / "host.env.example", Path(temp) / "host.env")
            legacy = headless.load(Path(temp) / "rotation.json", environ={})
        self.assertEqual(legacy, headless.load(DEPLOY / "host.json.example"))


def map_viewer_cases():
    out = {}
    for extra in MAP_VIEWER_CASES:
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(Path(temp).resolve())
            calls = []
            with mock.patch.object(map_viewer, "ROOT", root), \
                    mock.patch.object(sys, "argv", ["map_viewer.py", *extra]), \
                    mock.patch.object(map_viewer.subprocess, "call", side_effect=lambda c: calls.append(c) or 0), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(SystemExit):
                map_viewer.main()
            command = calls[0]
            out[" ".join(extra)] = case(command[3:], [(root, "")], script=normalize(command[2], [(root, "")]))
    return out


def ps1_args(root, HostAddress, Vpn=False, MaxPlayers=2, Map="CTF_arena", Backdrop="spacebkgd3", Terrain=False,
             TestRttMs=0, TestJitterMs=0, TestLossPercent=0):
    """The server arguments of start_lan_dogfight.ps1: its aoa_host.py command (mirrored by hand: keep
    the two in step), resolved by aoa_host.py's own option handling."""
    words = ["run", "--profile", "vpn-dogfight" if Vpn else "lan-dogfight", "--bind-address", HostAddress,
             "--max-players", str(MaxPlayers), "--map", Map, "--backdrop", Backdrop, "--console"]
    if Terrain:
        words.append("--terrain")
    if TestRttMs or TestJitterMs or TestLossPercent:
        words += ["--", "--impair-rtt-ms", f"{TestRttMs:g}", "--impair-jitter-ms", f"{TestJitterMs:g}",
                  "--impair-loss", f"{TestLossPercent:g}"]
    seen = []
    with mock.patch.object(headless, "run", side_effect=seen.append), \
            mock.patch.object(headless, "HostConfig", lambda: HostConfig(root=root)), \
            mock.patch.object(HostConfig, "validate", lambda self, **_: {}), \
            contextlib.redirect_stdout(io.StringIO()):
        if headless.main(words) != 0 or len(seen) != 1:
            raise ValueError("aoa_host.py did not reach its run loop")
    return seen[0].to_argv()


def doc_commands():
    """{argument text: [doc files]} for every station_stub.py command line in the Markdown docs."""
    found = {}
    paths = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "tools").rglob("*.md"),
             *(ROOT / "deploy").rglob("*.md")]
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("docs/restructure/"):
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = DOC_COMMAND.search(line)
            if match:
                found.setdefault(match.group(1).strip(), []).append(relative)
    return found


def text_cases():
    """Docs and PS1 commands use repository-relative paths, so they parse inside a scratch root."""
    docs, ps1 = {}, {}
    with tempfile.TemporaryDirectory() as temp:
        root = make_root(Path(temp).resolve())
        with contextlib.chdir(root):
            for text, sources in sorted(doc_commands().items()):
                docs[text] = case(shlex.split(text), [(root, "")], sources=sorted(set(sources)))
            for params in PS1_CASES:
                label = " ".join(f"-{k}" if v is True else f"-{k} {v}" for k, v in params.items())
                ps1[label] = case(ps1_args(root, **params), [(root, "")])
    return docs, ps1


def snapshot():
    docs, ps1 = text_cases()
    return {"about": "Server command lines and their effective config; regenerate with "
                     "python -I tools/test.py test_host_argv -- --update only for an intended change.",
            "host_control": host_control_cases(), "dedicated_host": deploy_cases(),
            "map_viewer": map_viewer_cases(), "start_lan_dogfight": ps1, "docs": docs}


def render(data):
    return json.dumps(data, indent=1, sort_keys=True) + "\n"


class HostArgvTests(unittest.TestCase):
    def test_snapshot_unchanged(self):
        self.assertTrue(SNAPSHOT.is_file(), "missing snapshot; run with --update")
        expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        current = json.loads(render(snapshot()))
        for group in sorted(set(expected) | set(current)):
            if not isinstance(current.get(group), dict):
                continue
            for name in sorted(set(expected.get(group, {})) | set(current[group])):
                with self.subTest(group=group, case=name):
                    self.assertEqual(current[group].get(name), expected.get(group, {}).get(name))
        self.assertEqual(current, expected)

    def test_docs_have_server_commands(self):
        # Guards the extraction pattern: the docs show a dozen direct server launches today.
        self.assertGreaterEqual(len(doc_commands()), 10)

    def test_every_host_control_combination_parses(self):
        # Every mode, map, terrain, node and target-ship choice the window offers.
        with tempfile.TemporaryDirectory() as temp:
            root = make_root(Path(temp).resolve())
            with mock.patch.object(host_control, "ROOT", root), mock.patch.object(host_control, "WORK", root / "work/host"):
                for mode, terrain, name, buoys, turret, warp, ships in itertools.product(
                        host_control.MODES, (True, False), registry.MAP_NAMES,
                        (True, False), (True, False), (True, False), (0, 4, 20)):
                    settings = {**host_control.DEFAULTS, "mode": mode, "address": ADDRESSES[mode],
                                "terrain": terrain, "map": name, "navigation_buoys": buoys,
                                "turret_trial": turret, "warp_trial": warp, "target_ships": ships, "max_players": 8}
                    try:
                        effective(host_control.server_args(settings)[1:])
                    except ValueError as error:
                        self.fail(f"{settings}: {error}")


class LauncherDefaultsTests(unittest.TestCase):
    def test_one_defaults_table(self):
        server = vars(parse_args(["key", "log"]))
        table = runtime.HOST_DEFAULTS
        self.assertEqual((server["kill_limit"], server["time_limit"], server["max_players"]),
                         (table["kill_limit"], table["time_limit_seconds"], table["max_players"]))
        self.assertEqual((host_control.DEFAULTS["kill_limit"], host_control.DEFAULTS["time_limit_min"] * 60,
                          host_control.DEFAULTS["max_players"]),
                         (table["kill_limit"], table["time_limit_seconds"], table["max_players"]))
        self.assertEqual((dedicated.DEFAULTS["kill_limit"], dedicated.DEFAULTS["time_limit_seconds"]),
                         (table["kill_limit"], table["time_limit_seconds"]))
        # The Linux example keeps its own explicit limits.
        example = json.loads((DEPLOY / "rotation.json.example").read_text())
        self.assertEqual((example["kill_limit"], example["time_limit_seconds"]), (10, 900))
        self.assertIn("override", example["comment"])

    def test_start_lan_dogfight_script(self):
        text = (ROOT / "tools/start_lan_dogfight.ps1").read_text(encoding="utf-8")
        description = text[text.index(".DESCRIPTION"):text.index(".EXAMPLE")]
        for command in re.findall(r"(?:^ |\| )(\w+)", ops.HELP.split(":", 1)[1]):
            self.assertIn(command, description)
        self.assertNotIn("ValidateSet('CTF_arena'", text)  # every map the server accepts (H5)
        self.assertNotIn("Arena1a terrain", text)  # the map it was given (H4)
        self.assertNotIn("20 kills / 10 minutes", text)  # limits from --print-config


def main():
    if "--update" in sys.argv[1:]:
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(render(snapshot()), encoding="utf-8", newline="\n")
        print(f"wrote {SNAPSHOT.relative_to(ROOT).as_posix()}")
        return
    unittest.main()


if __name__ == "__main__":
    main()
