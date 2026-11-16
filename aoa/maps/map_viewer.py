"""Fly around any recovered map in the 2.9.2 client, one map per server run.

  python -I tools/map_viewer.py list
  python -I tools/map_viewer.py install game/2.9.2
  python -I tools/map_viewer.py serve Arena1a [--game game/2.9.2] [--spawn-at X Y Z]

`install` converts the user's own JRMAP.TRN (2.0.0 record layout) into
jrmap292.trn beside the client; nothing is downloaded. `serve` runs the
loopback relay with --terrain, so a client at patch level 11 or later
(aoa/host/defaults.py CLIENT_PATCH_LEVELS) builds that map's native terrain on
flight entry. The
client loads terrain once per flight session: quit the client (Alt+Q, then
close the relaunched copy) before switching maps.

Viewing only: no collision, turrets, warp gates, flags or mission rules are
claimed. Kind 1/3/7/8 records in JRMAP (turrets, buoys, warps, flag stations)
are gated off in the 2.9.2 client and are not expected to appear.
"""
import argparse
import hashlib
from pathlib import Path

from aoa.formats import trn  # noqa: E402
from aoa.maps import registry  # noqa: E402

from aoa.paths import ROOT
JRMAP_SHA256 = "e3da8fbbdfb84ac7c830314e62bd8ceb7dfbdf9d90cd5fef614601133f23c5c4"


def install(game):
    source = Path(game) / "JRMAP.TRN"
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != JRMAP_SHA256:
        raise SystemExit(f"{source}: unexpected contents; expected the shipped JRMAP.TRN")
    target = Path(game) / registry.MAPS[registry.MAP_NAMES.index("JRMAP")][2]
    converted = trn.convert_292(data)
    target.write_bytes(converted)
    print(f"wrote {target} ({len(converted)} bytes, sha256 {hashlib.sha256(converted).hexdigest()})")


def main(argv=None, serve=None):
    """`serve` runs a map (aoa/launchers/serve.py, which tools/map_viewer.py passes in)."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    p = sub.add_parser("install")
    p.add_argument("game", type=Path)
    p = sub.add_parser("serve")
    p.add_argument("map", choices=registry.MAP_NAMES)
    p.add_argument("--game", type=Path, default=ROOT / "game/2.9.2")
    p.add_argument("--backdrop", default="spacebkgd3")
    p.add_argument("--spawn-at", type=float, nargs=3, metavar=("X", "Y", "Z"))
    p.add_argument("--seconds", type=float, default=0)
    args = parser.parse_args(argv)
    if args.action == "list":
        for i, (name, kind, target, spawn) in enumerate(registry.MAPS):
            where = "origin" if spawn is None else "(%g, %g, %g)" % spawn
            print(f"{i:2} {name:13} {'trn' if kind else 'layout':6} spawn {where:28} {registry.NOTES.get(name, '')}")
        return
    if args.action == "install":
        install(args.game)
        return
    if args.map == "JRMAP" and not (args.game / "jrmap292.trn").exists():
        raise SystemExit(f"run: python -I tools/map_viewer.py install {args.game}")
    if serve is None:
        raise SystemExit("serve runs from the command: python -I tools/map_viewer.py serve MAP")
    serve(args)


if __name__ == "__main__":
    main()
