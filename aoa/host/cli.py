"""The stand-in Station and arena server's command line (tools/station_stub.py).

    python -I tools/station_stub.py <SCRTY.BIN> <log.jsonl> [--profile P] [options]

Every flag, its default and its group: docs/host/server-reference.md (generated from
this parser by aoa/host/flagdoc.py), or --help. --print-config validates and
prints the settings without opening sockets or reading the key.

Profiles: diagnostic (default) only listens and logs, on 127.0.0.1;
local-relay and local-guests serve clients on this PC; lan-dogfight binds one
private LAN IPv4 address and vpn-dogfight also a VPN (100.64.0.0/10) address.
Point a local client at 127.0.0.1 in the login dialog's "Station IP" box.
Datagrams are decoded with aoa/protocol/codec.py (cipher keyed by SCRTY.BIN,
CCompress, CRC16); bounded, rotating metadata logs are the default and
--raw-capture explicitly includes packet data. Synthetic-peer motion,
combat and admission are tested; full gameplay is not implemented, and
TCP lists use diagnostic correlation, not authentication or ownership.
Hosts with players normally start through tools/aoa_host.py or the host
window, which build these flags from one settings file (aoa/host/config.py).
"""
import json
import sys
from contextlib import ExitStack
from pathlib import Path

from aoa.host.objects import load_objects
from aoa.host.runtime import EventLog, parse_args
from aoa.host.server import run


def main(argv=None):
    args = parse_args(argv)
    try:
        objects = load_objects(args)
    except (OSError, ValueError, KeyError) as error:
        # An asset problem, reported as one line like the other setting errors.
        print(f"{Path(sys.argv[0]).name}: error: map objects: {error}", file=sys.stderr, flush=True)
        raise SystemExit(2) from None
    if args.print_config:
        print(json.dumps(vars(args), default=str, indent=2))
        return
    key = args.key.read_bytes()
    if len(key) != 256:
        raise ValueError("SCRTY.BIN must contain exactly 256 bytes")
    try:
        with EventLog(args.log, args.raw_capture, args.log_max_bytes, args.log_backups) as log, ExitStack() as resources:
            return run(args, key, log, resources, objects)
    except KeyboardInterrupt:
        # systemd uses SIGINT, like a foreground Ctrl+C, so the context
        # managers close sockets and drain logs before a successful exit.
        print("Host stopped", flush=True)
    except OSError as error:
        raise SystemExit(f"Host I/O failed: {error}. Check that {args.bind_address} belongs to this PC and the ports are free.") from error


if __name__ == "__main__":
    raise SystemExit(main())
