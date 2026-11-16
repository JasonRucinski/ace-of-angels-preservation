"""Serve one map on this PC for viewing: `map_viewer.py serve` and `make_map.py serve`.

Both build their server command line from a HostConfig (aoa/host/config.py),
the one builder, and run the server in this terminal until Ctrl+C. aoa/maps
may not import aoa/host, so the two tools' shims hand their `serve` action
here.
"""
import subprocess
import sys

from aoa import paths
from aoa.host.config import HostConfig
from aoa.host.defaults import DEFAULT_BACKDROP
from aoa.maps import make_map
from aoa.paths import ROOT


def run(config, call=subprocess.call):
    """Run the server in the foreground; its exit code."""
    return call([sys.executable, "-I", str(paths.entry("station_stub", ROOT)), *config.to_argv()])


def viewer_config(name, game, backdrop=DEFAULT_BACKDROP, spawn_at=None, seconds=0):
    """One recovered map with terrain, for one client on this PC (local-relay)."""
    work = ROOT / "work/map-viewer"
    extra = []
    if spawn_at:
        extra += ["--spawn-at", *(f"{v:g}" for v in spawn_at)]
    if seconds:
        extra += ["--seconds", f"{seconds:g}"]
    return HostConfig(profile="local-relay", maps=[name], backdrop=backdrop, terrain=True,
                      paths={"game": str(game), "log": str(work / f"{name}.jsonl"),
                             "status": str(work / f"{name}-status.json")}, extra_args=extra)


def custom_config(spec, client, seconds=0):
    """A custom map installed in `client` (make_map.py install), in the JRMAP slot."""
    work = ROOT / "work/custom-map"
    trn = client / make_map.SLOT_FILE
    extra = ["--spawn-at", *(f"{v:g}" for v in spec["spawn"])]
    navigation = any("nav" in e for e in spec["objects"])
    if navigation:
        extra += ["--map-waypoints", str(trn)]
    if seconds:
        extra += ["--seconds", f"{seconds:g}"]
    return HostConfig(profile="local-relay", maps=[make_map.SLOT_MAP], backdrop=spec.get("backdrop", DEFAULT_BACKDROP),
                      terrain=True, objects={"powerups": any(e.get("zone") == "powerup" for e in spec["objects"])},
                      sustained_delivery=True if navigation else None,
                      paths={"game": str(client), "log": str(work / f"{spec['name']}.jsonl"),
                             "status": str(work / f"{spec['name']}-status.json")}, extra_args=extra)


def map_viewer(args, call=subprocess.call):
    """`map_viewer.py serve MAP [--game] [--backdrop] [--spawn-at X Y Z] [--seconds]`."""
    config = viewer_config(args.map, args.game, args.backdrop, args.spawn_at, args.seconds)
    config.path("log").parent.mkdir(parents=True, exist_ok=True)
    print(f"Serving {args.map} on 127.0.0.1; launch the prepared client and Play. Ctrl+C stops.")
    sys.exit(run(config, call))


def custom_map(spec, client, seconds=0, call=subprocess.call):
    """`make_map.py serve SPEC CLIENT [--seconds]`, after make_map checked the installed file."""
    config = custom_config(spec, client, seconds)
    config.path("log").parent.mkdir(parents=True, exist_ok=True)
    print(f"Serving {spec['name']} on 127.0.0.1; launch the client in {client} and Play. Ctrl+C stops.")
    sys.exit(run(config, call))
