"""Fly around any recovered map in the 2.9.2 client, one map per server run.

  python -I tools/map_viewer.py list
  python -I tools/map_viewer.py install game/2.9.2
  python -I tools/map_viewer.py serve Arena1a [--game game/2.9.2] [--spawn-at X Y Z]

`install` converts the user's own JRMAP.TRN (2.0.0 record layout) into
jrmap292.trn beside the client; nothing is downloaded. `serve` runs the
loopback relay with --experimental-terrain, so a client prepared with
online-terrain-v2 or later builds that map's native terrain on flight entry. The
client loads terrain once per flight session: quit the client (Alt+Q, then
close the relaunched copy) before switching maps.

Viewing only: no collision, turrets, warp gates, flags or mission rules are
claimed. Kind 1/3/7/8 records in JRMAP (turrets, buoys, warps, flag stations)
are gated off in the 2.9.2 client and are not expected to appear.
"""
import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decode_trn  # noqa: E402
import online_terrain  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JRMAP_SHA256 = "e3da8fbbdfb84ac7c830314e62bd8ceb7dfbdf9d90cd5fef614601133f23c5c4"
# Native terrain objects a real client built on flight entry (23 Oct 2026).
NOTES = {
    "Arena1a": "239 objects; main arena", "CTF_arena": "55 objects",
    "CTF_arena_b": "60 objects", "newterrain": "234 objects", "outerchange": "616 objects; very large",
    "ast_fld_a": "27 objects", "ast_fld_b": "49 objects", "ast_fld_c": "15 objects", "ast_fld_d": "10 objects",
    "CTF_base": "1 object; component", "hu_base_a": "4 objects; component", "hu_base_b": "2 objects; component",
    "hy_base_test": "2 objects; component", "hy_winga": "loads nothing alone", "HyBase2Lay": "10 objects; component",
    "irrosa01": "457 objects", "ze_winga": "loads nothing alone", "ze_wingb": "loads nothing alone",
    "Hittest": "loads nothing alone",
    "JRMAP": "23 objects incl. 5 safe zones; 2.0.0 editor map (run install first)",
}


def install(game):
    source = Path(game) / "JRMAP.TRN"
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != JRMAP_SHA256:
        raise SystemExit(f"{source}: unexpected contents; expected the shipped JRMAP.TRN")
    target = Path(game) / online_terrain.MAPS[online_terrain.MAP_NAMES.index("JRMAP")][2]
    converted = decode_trn.convert_292(data)
    target.write_bytes(converted)
    print(f"wrote {target} ({len(converted)} bytes, sha256 {hashlib.sha256(converted).hexdigest()})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    p = sub.add_parser("install")
    p.add_argument("game", type=Path)
    p = sub.add_parser("serve")
    p.add_argument("map", choices=online_terrain.MAP_NAMES)
    p.add_argument("--game", type=Path, default=ROOT / "game/2.9.2")
    p.add_argument("--backdrop", default="spacebkgd3")
    p.add_argument("--spawn-at", type=float, nargs=3, metavar=("X", "Y", "Z"))
    p.add_argument("--seconds", type=float, default=0)
    args = parser.parse_args()
    if args.action == "list":
        for i, (name, kind, target, spawn) in enumerate(online_terrain.MAPS):
            where = "origin" if spawn is None else "(%g, %g, %g)" % spawn
            print(f"{i:2} {name:13} {'trn' if kind else 'layout':6} spawn {where:28} {NOTES.get(name, '')}")
        return
    if args.action == "install":
        install(args.game)
        return
    if args.map == "JRMAP" and not (args.game / "jrmap292.trn").exists():
        raise SystemExit(f"run: python -I tools/map_viewer.py install {args.game}")
    log = ROOT / "work/map-viewer" / f"{args.map}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-I", str(ROOT / "tools/station_stub.py"), str(args.game / "SCRTY.BIN"), str(log),
               "--profile", "local-relay", "--map", args.map, "--backdrop", args.backdrop,
               "--experimental-terrain"]
    if args.spawn_at:
        command += ["--spawn-at", *map(str, args.spawn_at)]
    if args.seconds:
        command += ["--seconds", str(args.seconds)]
    print(f"Serving {args.map} on 127.0.0.1; launch the prepared client and Play. Ctrl+C stops.")
    sys.exit(subprocess.call(command))


if __name__ == "__main__":
    main()
