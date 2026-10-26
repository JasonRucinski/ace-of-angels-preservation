# Implemented local protocol contract

Scope: the 2.9.2 loopback Station/relay, not all messages needed for combat.
All integers are little-endian. Evidence is the original executable with
SHA-256 `4b6c35e2b3ab473bd98c0afa6538079ee78678d85c28406c07bc27a08cc78c7e`,
the references below, and executable tests. Unknown units/semantics stay
unknown. Definitions for inventory, damage, teams and match end remain open.

## Transport and dispatch

Station UDP defaults to 5033; list/file-state TCP to 5034; arena UDP to 5031.
They are separate configuration fields. Every listener still binds loopback.
UDP is `Encrypt(Compress(payload || type:u8 || CRC16-XMODEM(payload):u16))`.
The receiver accepts at most 512 wire and decompressed bytes. This leaves
509 payload bytes; incompressible payloads may need 508 to leave room for the
compression trailer. Both CRCs are checked when a compression CRC is present.
Original 2.9.2 receive bounds are at `0x529E8B` and `0x529ECA`.

Decompression checks every intermediate pass against the cap. Empty/truncated
trailers, bad sizes and overflow are rejected before message dispatch. Archive
extraction keeps its separate unbounded-default API; do not use that API for
network data without an explicit bound.

The local ingress budget permits 400 datagrams/sec globally (burst 200), and
60/sec per endpoint/channel (burst 120), before decoding. Tracking holds at
most 256 endpoint entries. UDP channels rotate service order. These are
diagnostic limits, not DDoS protection or measured production budgets.

| Type/job | Direction and size | Fields, valid state, ordering and evidence |
|---|---|---|
| `0x0A` connect | Client → Station/arena; 381 bytes | Minor/major/patch u32 at 1/5/9 must be 9/2/2. Login block starts 31, 350 bytes. Guest profile requires ticket u32 at `0x9A`, assigned name at 31 and current source-IP/lease binding. Identical endpoint retry preserves admission; conflicting replacement ignored. [Findings 3, 9.12, 9.16, 9.20](findings.md). |
| `0x0B` ACK | Server → requesting endpoint; 363 bytes | Kind u8 at 1 (Station 1/arena 0), player tag u32 at 2, result u32 at 6, player block at 13. Result 0 success, 8 version mismatch, 4 capacity rejection, 5 invalid guest admission. Failure blocks are zeroed. Station ID at block+`0x7B`. `0x431630`, login error switch `0x444B8D`. |
| `0x1B` reliable envelope | Either direction; inner size +5 | Inner payload, u32 sequence, u8 type. Nested envelopes rejected. Inbound wrappers ACK once per reception. A repeated sequence from the same channel/endpoint (last 64 IDs, 512 endpoints, history kept after departure) is dispatched only for handshakes, which are idempotent and must re-answer a lost ACK; other repeats are dropped. Wrapped movement is ignored. [Findings 9.21](findings.md#921-inbound-reliable-duplicate-suppression-21-october-2026). Outbound support is removal only. [Findings 9.13–9.14](findings.md). |
| `0x0F` reliable ACK | Client → arena; exactly 4 bytes | Sequence u32, matched against that endpoint's pending removal. Other peers/lengths cannot clear it. No application-level readiness guarantee. |
| `0x08` / `0x09` heartbeat | Server → client / client → server; 12 bytes | Tick u32 milliseconds modulo 2^32, trip u16, player u8, reserved u8, two u16 counters. Reply must match one of four outstanding ticks; tick consumed once. Arena also requires the assigned slot byte. Station does not check it, because the client's shared UDP socket echoes its arena slot there after arena entry. Station stops pinging a socket the arena has admitted ([9.28](findings.md#928-station-pings-during-arena-entry-21-october-2026)). `0x486C20`. |
| `0x42` own record | Arena → that player only; 4 + 350 bytes | u32 tag, then the player's own 350-byte record (its login block) with server kills `+0x7F`, deaths `+0x83`, reported score `+0x4E`. Replaces the local record (`0x49DB20`). Sent to killer and victim after a death and to everyone at a match reset. [9.30](findings.md#930-scoreboard-match-limits-and-why-missiles-need-teams-21-october-2026) |
| `0x21` arena text | Arena → players; 294 bytes | u16 kind 3 at +3, NUL-terminated text at `+0x25`. Match result and start. `0x4348E0`. |
| `0x1F` stats | Arena → observers, mask `0x80000000` | Submask `0x100` only: i16 kills, i16 deaths, i16 rating, u16 0, i32 score (SetStats `0x493670`). Client blocks are never forwarded; clients report rating/score in submask `0x200`. |
| `0x2A` fire missile | Shooter → arena (reliable) → every loaded player, shooter included; 146 bytes | f32 lock, target tag, shooter tag, count, 16 missile tags (zero from the client; the server assigns `0x40CCIIII`, index 500–999), missile and rack names (32 bytes each; stack bytes after the NUL scrubbed), u16 targeted system. Echo is best effort. `MissileLedger.launch`; client `0x4B0E00`/`0x4B16B0`. [9.32](findings.md#932-missiles-work-hostile-relations-launch-echo-and-impact-relay-21-october-2026) |
| `0x30` missile impact | Missile's shooter or target → arena → every loaded player; 21 bytes | Missile tag, hit tag (0 = none), float3 position, direct-hit byte. First report per server-issued missile only; hit must be a loaded player. Receivers damage themselves (`0x433FC0` → `0x49B9F0`). Best effort. |
| `0x37` died | Client → arena; 4 bytes, unreliable | Killer's tag u32. Sent by the victim, whose own client computed the damage from relayed fire state; it then resets its systems. The relay sends observers a `0x38` death notice, counts kills/deaths and respawns the victim at its spawn ([9.27](findings.md)). `0x486AD0`. |
| `0x4E` quit | Client → its listener; 1 byte | Reason byte, not a target slot. Removes only that admitted endpoint; repeat quit harmless. The real client sends three copies to each of Station and arena on Alt+Q (key command 91), then relaunches as `AoAClient.exe autologin`. Closing the window sends none. `0x4871C0`. |
| `0x9A` aliases | Station → requesting session; 320 bytes | Ten 32-byte NUL-terminated names; synthetic name limited to 19 ASCII bytes. Sent once after that session's successful TCP job 5. Best effort. `0x430F5D`, `0x45DBE0`. |
| `0x26` load player | Arena → loaded/new observer; 438 bytes | Ship/database 20-byte strings at 0/20, tag at 40, receiver's relation (value − 1) at 68/69 for same/other team (both 3, Hostile), synthetic name at 70, position float3 at 420. Slot 1..49; never sends private login block. Unreliable and readiness-unverified. `0x4A6320`. [9.32](findings.md#932-missiles-work-hostile-relations-launch-echo-and-impact-relay-21-october-2026) |
| `0x27` load ship | Arena → joining client; 129 bytes | Vessel[64], database[64], local slot 0. Precedes flight entry after diagnostic three-second delay. `0x4306C1`. |
| `0x2C` enter flight | Arena → joining client; 4 bytes | Body unused. Followed by explicit position because this path resets coordinates. Unreliable; no readiness ACK. `0x44B68E`. |
| `0x24` position | Arena → joining client; float3 (12 bytes) | Writes actual and target coordinates. Units/axes still unverified. After `0x2C`. `0x430881` → `0x4BE970`. |
| `0x25` passive object | Arena → joining client; 191 bytes | Optional diagnostic mission ship; ship/database/name at 0/32/64, tag/kind at 96/100, position at 146. Fixed object identity; no AI. `0x48A460`. |
| `0x2D` remove | Arena → observers; 1 byte | Slot 1..49. Reliable wrapper; retries back off from 0.5 s to 4 s until the peer timeout (2.5 s in the bare class default). Observers retire on failure or before 31 distinct removals. A real observer ACKed and dropped the slot ([9.23](findings.md#923-real-client-check-21-october-2026)). No generation check; slots/endpoints not reused. `0x430710`. |
| `0x1F` movement | Loaded client → arena → observers; safe prefix 8..120 bytes | Leading u16 with high bit set, assigned slot u16, mask u32, fields below. Validated gun-state block (`0x10000000`) kept; other optional blocks discarded. Re-encoded absolute observations plus one-second refresh; no upstream sequence guarantee. `0x495330`. |
| TCP request | Client → Station; 142 bytes | Correlation ID u32 at 60, job u8 at 128, separate flag u8 at 129. Current session + source IP required. Two string destinations at 0/64; their semantics remain unresolved. `0x4302A6..0x43044B`. |
| TCP jobs 5/14 | Station → client; u32 size + compressed body | Job 5: 128-byte rows, Station count then available arena; job 14: 128 zero bytes, still the diagnostic “files current” placeholder. Unknown/stale job: zero length. Worker max16 clients, 3-second absolute deadline. `0x432760`, `0x432ED0`, `0x435930`. |

**Reliable combat experiment (21 October 2026):** with
`--experimental-reliable-combat`, the `0x2A`, `0x30` and observer-only `0x38`
messages above use `0x1B` envelopes instead of best-effort sends. They share
the removal queue, sequence namespace and **30-event lifetime limit**; ACKs
do not restore that budget. Per peer, only one event is in flight. An ACK
releases the next event, so an impact cannot overtake its launch. ACKs for
unsent queued events are ignored. Queue deadlines start at enqueue time;
expiry or history exhaustion retires the endpoint without reuse. This mode
does not make world loading, score records or respawn positioning reliable,
and is off by default. It is not a maintained protocol extension.

**Protection prototype:** only with `explicit-protection-v1`, arena `0x81`
has exactly one payload byte (`0` disabled, `1` enabled). The patched receive
case rejects other lengths/values and changes the existing invulnerability
flag only when needed. It remains subject to stale-event ordering, has no
session generation, and the flag also affects ammunition consumption.
Unpatched clients interpret this message as a toggle. Do not mix these wire
semantics in a gameplay profile; the single-client diagnostic requires the
operator's prepared-client check. See [client-extension-gate.md](client-extension-gate.md).

## Movement observations and complete-prefix parsing

The server tracks all 16 safe field groups, validates all float components,
and rounds delta accumulation to float32 like the original decoder. This
table follows wire order. Offsets refer to the decoder's kinematic destination.
Unproven labels remain offsets; physical units and handedness are not inferred.

| Absolute mask | Destination | Encoding and delta alternatives |
|---|---|---|
| `0x40` | `+0x6C` position | float3, no delta alternative |
| `0x1` | `+0x50` velocity | float3; `0x2` signed16×3 / `0x4` signed8×3, added directly |
| `0x8` | `+0xE4` | float3; `0x10` signed16×3 / `0x20` signed8×3, added directly |
| `0x40000` | `+0x5C` acceleration | float3; `0x80000` signed16×3 / `0x100000` signed8×3, added directly |
| `0x80`, `0x100`, `0x200` | `+0xE0`, `+0xDC`, `+0xD8` | float scalars |
| `0x400` | `+0xF0` (player `+0xF4` status flags) | signed32 replacement; `0x800` signed16 replacement; bit `0x40` while guns fire; also refreshes a client timer through `0x4BE950` |
| `0x10000000` | per-gun fire state, after the prefix | u8 header (count in low 7 bits), count × (u16 system index, u8 value). Receiver stores value × 0.1 at the gun's `+0xFC`. Relayed only with every index below 128 (the client's counter array is not bounds-checked). [Findings 9.26](findings.md#926-victim-side-damage-gun-state-relay-and-death-report-21-october-2026) |
| `0x1000`, `0x2000`, `0x4000` | `+0x40`, `+0x3C`, `+0x38` | float scalars |
| `0x8000`, `0x10000`, `0x20000` | `+0x4C`, `+0x48`, `+0x44` | float scalars |
| `0x200000` | `+0x84` | float3; `0x400000` signed16×3 / `0x800000` signed8×3, scaled by float32 bytes `BD 37 06 35` before addition |
| `0x1000000` | `+0x78` | float3; `0x2000000` signed16×3 / `0x4000000` signed8×3, same scale |

The scale is approximately `4.999999987376214e-7`, read at `0x59820C`.
Absolute takes precedence over signed16, which takes precedence over signed8.
No value is committed when any field is non-finite/truncated. An unobserved
delta base is omitted until an absolute sample arrives; it is never invented.
Position and zero velocity start from the server's diagnostic spawn state.

Snapshots include every observed safe float group. The `+0xF0` control scalar
is forwarded only when present in the incoming record; it is omitted from
periodic/late-join refresh to avoid repeatedly extending its timer. Its gameplay
meaning remains unresolved. Periodic snapshots fix observer-side loss once
another snapshot arrives; they cannot reconstruct upstream loss or distinguish
reordered/duplicated client deltas. This is not authoritative motion.

Evidence: `motion_state_emulation.json` checks 300 original-decoder state cases
and 200 loss/duplicate refresh cases. `test_relay_recovery.py` exercises actual
UDP capacity, periodic recovery and non-finite rejection. All evidence lives
under `evidence/2.9.2/`. Full field semantics, client input sequencing, reliable
world load, combat messages and real-renderer loss tests remain required.
