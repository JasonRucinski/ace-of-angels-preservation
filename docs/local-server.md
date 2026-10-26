# Reproducible local Station and relay

For multiple PCs on a private LAN, use the new
[LAN dogfight profile and launcher](lan-dogfight.md). The profiles documented
below retain loopback-only behavior. LAN combat uses ordinary best-effort relay;
the optional bounded reliable-combat experiment is excluded from that profile.

This is a loopback diagnostic profile, not an internet-ready server or a
complete game. Run commands from the repository root. It requires the existing
Python environment, a locally extracted 256-byte `SCRTY.BIN`, and the prepared
2.9.2 client described in [running on Windows](running-on-windows-11.md).
Use dummy login values. Nothing here adds account authentication.

## Start the local relay

```powershell
.venv\Scripts\python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/local-relay.jsonl --profile local-relay
```

The named profile enables replies, Station UDP 5033, list TCP 5034, arena UDP
5031 and experimental movement relay. All sockets bind `127.0.0.1`; there
is no public bind option. The synthetic Station pilot is `testpilot`, arena
ship is `Ym Khtat`, terrain label is `CTF_arena`, and backdrop is `spacebkgd3`.
Those labels do not establish a loaded, collidable map or CTF rules.
The passive mission object remains off unless `--experimental-object` is added.

For the new, opt-in local guest ownership path:

```powershell
.venv\Scripts\python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/local-guests.jsonl --profile local-guests
```

It enables the same listeners/relay but requires a Station-issued ticket and
pilot name for arena entry. Use this profile for the guest-admission tests;
the older `local-relay` profile retains direct diagnostic arena admission.

Inspect and validate the effective configuration without reading the key,
creating logs or opening sockets:

```powershell
.venv\Scripts\python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/local-relay.jsonl --profile local-relay --print-config
```

Use `--seconds 120` for a bounded run. `0` (the default) runs until stopped.
Ctrl+C unwinds the resource contexts; forced process termination cannot flush
queued logs. Normal exit closes UDP sockets, stops the TCP worker and flushes
the logger with a five-second maximum join. This is process cleanup, not a
verified client-facing shutdown/return-to-Station protocol.

## Diagnostic mode and overrides

The default `diagnostic` profile listens on Station UDP without sending
replies. Existing explicit flags remain available:

```powershell
.venv\Scripts\python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/observe.jsonl --seconds 60
.venv\Scripts\python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/flight.jsonl --ack --arena --tcp 5034 --experimental-flight --seconds 120
```

| Option | Behavior |
|---|---|
| `--port`, `--arena-port`, `--tcp` | Override individual ports; 0 requests an ephemeral port for tests. Station and arena cannot share a nonzero UDP port. TCP and UDP may use the same numeric port. |
| `--pilot NAME` | Synthetic Station pilot, 1–19 non-NUL ASCII characters. Does not create an account or own an arena identity. |
| `--peer-timeout SECONDS` | Positive finite Station/arena inactivity timeout; default 30, with three extra seconds for initial arena flight bootstrap. |
| `--max-players N` | Simultaneous arena admissions, default 8, range 1–49. Full arenas are omitted from the list; rejected joins consume no slot. Separate lifetime limits still apply. |
| `--ack`, `--arena`, experimental flags | Boolean flags also support `--no-…` overrides. Flight/relay requires both arena and replies; the passive object requires flight or relay. |
| `--spawn-axis x\|z`, `--spawn-spacing N` | Diagnostic relay spawn line, default x and 1000. Ships initially face +z, so `z` with a short spacing (e.g. 300) puts later players directly ahead of the first, for firing tests. Missiles need the target at least 5000 units away (Type II), so missile tests use `--spawn-axis z --spawn-spacing 6000` with the shooter joining first ([findings 9.32](findings.md#932-missiles-work-hostile-relations-launch-echo-and-impact-relay-21-october-2026)). |
| `--experimental-teams` | Relay only, off by default. Free-for-all teams: each player its own team in player loads and `0x50` (with itself as leader). Verified on only two joins ([findings 9.31](findings.md#931-teams-fixed-opt-in-missiles-need-a-loadout-21-october-2026)). Not needed for missiles: every player load already marks other players Hostile ([9.32](findings.md#932-missiles-work-hostile-relations-launch-echo-and-impact-relay-21-october-2026)). |
| `--experimental-reliable-combat` | Relay only, off by default. Death notices and missile launches/impacts share ordered reliable delivery with removals. One outstanding event per peer; subsequent events wait for its ACK. **30 total essential events per peer per admission**, including acknowledged events; exceeding the budget retires that peer. Queued events also expire after `--peer-timeout`. This is a bounded experiment, not sustained-match support. |
| `--experimental-protection-probe` | Single-client flight diagnostic; requires `--experimental-flight --max-players 1`, forbids relay. Sends explicit states `1,1,0,0` three seconds apart after bootstrap, waiting for ACKs. Requires the opt-in patched client; see [client-extension-gate.md](client-extension-gate.md). This is not timed spawn protection. |
| `--kill-limit N`, `--time-limit SECONDS` | Relay match limits, default 20 kills and 600 s; 0 disables either. At a limit every player gets the result as arena text, kills/deaths reset and the next match starts. Proposed rules, not recovered ones ([findings 9.30](findings.md#930-scoreboard-match-limits-and-why-missiles-need-teams-21-october-2026)). |
| `--raw-capture` | Explicitly include payloads/addresses in diagnostic files. These may contain dummy credentials and must remain private. |
| `--log-max-bytes N`, `--log-backups N` | Default 1 MiB per file and three backups; minimum file budget 16 KiB, backups 1–10. |

Unknown flags, invalid ports/timeouts and inconsistent combinations fail before
network startup. A missing key or a key other than 256 bytes also fails.
`--print-config` intentionally skips key-file inspection. Profile values can
be overridden; for a no-TCP test, use the diagnostic profile and explicit
arena/reply/relay flags rather than the local-relay preset.

## Logs and bounded TCP work

Normal JSONL logs contain event/type/size/CRC/job/status data and fixed
departure reasons. They omit payloads, login handles, peer addresses and TCP
request names. Console output is limited to startup addresses and a shutdown
summary of event counts, dropped log records and writer failure status.

One worker drains a 1,024-record queue. A full queue increments a drop counter
without waiting on disk. Each encoded record is limited to 16,000 bytes;
oversized raw records retain metadata with an omission marker. Rotation uses
`log.jsonl`, `.1`, `.2`, `.3` by default, totaling at most 4 MiB for files
created by this configuration. Existing oversized logs are preserved during
rotation, so start a new log path when enforcing a fresh disk budget. Older
backups outside a newly reduced backup count are not automatically deleted.
Do not run multiple servers against the same log path.

TCP list jobs run in an independent nonblocking event loop, with at most 64
open connections and a three-second deadline for each request/reply, counted
from its first byte. A connection whose request resolved a Station session
stays open for further jobs while that session lives, and closes when the
session ends. The real 2.9.2 client reuses its data connection, and a server
close leaves its TCP queue mutex stuck, which later hangs its UI thread
([findings 9.23](findings.md#923-real-client-check-21-october-2026)).
Connections that resolve no session close after one reply or the deadline.
Only 142 request bytes are retained. A stalled request does not block another
client or the UDP loop. Truncated requests get no partial-job reply; unknown
complete jobs retain the legacy zero-length response. Socket resets are
isolated to their connection. The alias-notification queue is capped at 1,024.
The channel serves only the existing small list/file-state responses, not
content downloads. Actual content transfers still need a separate design.

## Station sessions

Each accepted Station endpoint receives a distinct nonzero correlation ID
in its ACK player record. Original-client emulation verifies that the client
copies this value into TCP request bytes 60–63. The job occupies byte 128;
byte 129 is a separate flag. TCP list/file-state requests require a current
ID and matching source IP. An unknown/expired ID gets a zero-length reply;
there is no fallback to the last UDP peer or an IP-only match.

Each session receives the configured synthetic pilot once, after its first
successful server-list reply. Two clients sharing an IP route independently.
Queued notifications recheck the session before delivery. Identical direct
or wrapped handshakes preserve the ID and alias state; conflicting handshakes
cannot replace an occupied endpoint. Alias delivery itself remains best effort.

Station sends a heartbeat every second. Only a correctly sized reply from the
same endpoint with an outstanding timestamp extends expiry; each timestamp can
be consumed once. The echoed tag is not checked: the real client uses one UDP
socket for Station and arena, and after arena entry it echoes its arena slot. Handshake retries and TCP jobs do not extend
the lease. Quit and expiry clear the session, timers and pending alias target.
The server keeps only a handshake fingerprint in Station session state.

There are 64 lifetime Station admissions per process. IDs and retired UDP
endpoints are never reused within that process, preventing delayed quit or
TCP activity from targeting a replacement session. Restart with fresh clients
after exhaustion. Full/retired admissions receive no success ACK; a useful
client-facing rejection and supported reconnect flow remain future work.
The 49-admission arena limit is separate.

In diagnostic/local-relay mode, these IDs are predictable correlation values,
not secrets or authentication. Pilot names remain synthetic and have no ownership
protection. Joining an arena does not establish Station authorization. However,
the real client uses one UDP socket for both. When an arena endpoint equals a
live Station endpoint, the two are bound: Station stops pinging that socket,
the Station lease follows arena activity, and either side's quit or expiry
ends both ([findings 9.28](findings.md#928-station-pings-during-arena-entry-21-october-2026)).
Other arena endpoints remain independent. The guest profile adds the limited
ownership described next.

### Opt-in local guest ownership

`local-guests` replaces sequential IDs with random nonzero 32-bit tickets and
assigns a name such as `testpilot-01`. Names use at most 16 prefix characters
plus a two-digit admission suffix, stay within 19 ASCII characters, and are
unique within the run. The Station ACK, alias list and arena player announcement
use that assigned name. User-supplied login values do not create real accounts.

An arena join must carry the current ticket at request+`0x9A`, the exact assigned
20-byte name field, and the Station session's source IP. The original client's
request-building instructions preserve these fields from its saved Station ACK.
Once bound, a ticket cannot authorize a different arena UDP endpoint. Invalid,
expired, revoked or mismatched tickets receive legacy result 5; the original
client's generic “Invalid login” wording does not specifically explain a guest
ticket failure.

While bound, the Station lease follows validated arena activity, and redundant
Station pings stop. This avoids expiring an active flyer solely because its
Station socket is idle. Station quit/expiry also departs its arena peer. Arena
departure releases the guest binding and starts a fresh Station inactivity
period; retired arena endpoints still cannot be reused. Complete return-to-
Station/reconnect UI behavior remains unverified.

The ticket is only 32 bits and travels through the legacy channel. It is **not
modern authentication**, and a captured unused ticket can be impersonated.
The same-IP socket tests establish local ownership/state-machine behavior,
not resistance to a network attacker. Public exposure remains unsupported.

## What the server list reports

The arena row uses `Local Relay`, `Local Flight` or `Handshake Test` as its
name and retains the recovered terrain/backdrop fields. Population counts
admitted arena connections, including loading clients, and changes on quit
and expiry. Duplicate handshakes do not increase it. Its port is the actual
bound arena port, including ephemeral test ports.

No arena row is advertised without an arena listener/replies, or after the
49 lifetime admissions are exhausted. Slots and departed endpoints remain
reserved until restart; this is not slot reuse or sustained churn support.
The separate Station login count reports active Station sessions and decreases
on quit or expiry. Duplicate handshakes do not increase either population.

## Movement recovery and ingress limits

The relay tracks all 16 recovered safe movement groups, validates every float
component, and forwards absolute observations. A one-second snapshot restores
an observer after a downstream update is lost. Late joins receive all observed
safe float state. Unknown delta bases are omitted until an absolute sample
arrives. The control scalar that refreshes a client timer is not repeated in
periodic snapshots. The byte layouts and evidence are in
[local-protocol.md](local-protocol.md).

Client-to-server loss, duplication and reordering remain unresolved: the legacy
prefix has no proven sequence field. The server still relays client-reported
state; it does not enforce authoritative movement or implement combat.

UDP decoding caps wire size and every decompression pass at 512 bytes. Global
ingress is limited to 400 packets/sec with burst 200; a peer/channel gets 60/sec
with burst 120, tracked in at most 256 entries. Rate-limited packets are dropped
before decoding; their count is printed at shutdown. These are diagnostic
bounds, not validated internet flood protection. A well-sized handshake with
an incompatible version receives result 8 and allocates no session or slot.

## Verification

```powershell
.venv\Scripts\python.exe -I tools/verify_local.py
```

This runs all eight regression suites and six original-code emulators and
writes `work/local-verification.json`. Missing prerequisites, skipped tests,
failures and emulator errors fail the gate. It does not run the real game or
replace the roadmap's full-match, outside-network, clean-machine and performance
acceptance gates. Individual earlier checks remain available:

```powershell
.venv\Scripts\python.exe -I tools/test_station_runtime.py
.venv\Scripts\python.exe -I tools/test_station_stub.py
.venv\Scripts\python.exe -I tools/test_station_sessions.py
.venv\Scripts\python.exe -I tools/emulate_reliable_history.py game/2.9.2/AOACLIENT.EXE.orig evidence/2.9.2/reliable_history_emulation.json
.venv\Scripts\python.exe -I tools/emulate_station_request.py game/2.9.2/AOACLIENT.EXE.orig evidence/2.9.2/station_request_emulation.json
```

The runtime suite covers configuration rejection, profile startup, redaction,
raw opt-in, rotation, queue overflow, slow/fragmented/truncated/reset TCP
clients, deadlines, capacity, shutdown, live population and admission
exhaustion while TCP work is pending. Protocol tests retain the existing
handshake, relay, expiry and reliable-removal checks. Session tests cover two
clients on one IP, separate alias delivery, retries, stale partial TCP requests,
quit/expiry, heartbeat validation, source-IP mismatch and admission limits.
The new emulator executes the original player-record copy and TCP-header
packing, including a nonzero flag; it excludes full ACK dispatch and UI. These are synthetic
localhost tests; they do not establish real-client UI behavior, public
security, content installation, map collision, combat or performance budgets.
