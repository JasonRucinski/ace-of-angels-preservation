"""Local stand-in for the AoA Station server (UDP), for observing the real client.

Usage:
    python -I tools/station_stub.py <SCRTY.BIN> <log.jsonl> [--port 5033] [--tcp 5034] [--ack] [--arena] [--pilot testpilot] [--seconds N]

Defaults to 127.0.0.1; lan-dogfight opts into one private LAN IPv4 address,
vpn-dogfight into one private or VPN (100.64.0.0/10) address.
Decodes every datagram
with aoa/protocol/codec.py (cipher keyed by SCRTY.BIN, CCompress, CRC16). Bounded,
rotating metadata logs are the default; --raw-capture explicitly includes
packet data. --profile local-relay enables the documented loopback setup.
Use --print-config to inspect settings without opening sockets.
See docs/lan-dogfight.md for LAN setup. Point a local client at 127.0.0.1 in the login dialog's
"Station IP" box. Nothing is ever sent unless --ack is given; replies are
built per message type and are experiments, not a complete server. --arena
adds the initial game-server acknowledgement on UDP 5031. --pilot sets the
one synthetic pilot supplied per session after its first TCP server-list request.
--experimental-flight loads a local vessel and enters flight. The separate
--experimental-relay also assigns player tags and forwards filtered movement
fields. Synthetic-peer motion is verified; full gameplay is not implemented.
--arena-port overrides 5031 for isolated protocol tests.
--experimental-object adds one passive mission ship to the flight bootstrap.
--target-ships N adds N passive hostile ships ahead of the spawn for the target keys.
--peer-timeout sets Station/arena inactivity expiry in seconds (default 30). Retired
relay slots and endpoints are not reused during this run (49 admissions max);
despawn delivery uses bounded reliable retries. Use a fresh client endpoint
to rejoin. Observers retire if removal delivery fails or its 30-ID duplicate
history would be exceeded; safe slot reuse still requires protocol work.
LAN sessions require restarting host and clients for reconnects.
--sustained-delivery (default for vpn-dogfight) replaces that 30-ID lifetime
budget with a time window (aoa/host/delivery.py): despawns and combat
events stay ordered and reliable for a whole session, and a rejoining
client from a silent player's IP replaces the stale ship. Slots are still
not reused (49 arena joins per host run).
Station allows 64 lifetime admissions; expired/quit endpoints stay retired.
TCP lists require the ID echoed in the Station player record and a matching
source IP. This is diagnostic correlation, not authentication or ownership.
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
