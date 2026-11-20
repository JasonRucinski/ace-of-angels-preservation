# Authoritative server (deferred)

The deferred plan for a server that owns movement, weapons and damage, in two
parts written on 21 October 2026, each kept as it was: the specification of
the first playable release, and the gate of client changes such a server
would need. Neither blocks the private LAN and VPN relay that is hosted today
([host/README.md](../host/README.md)). The wider roadmap:
[internet-server.md](internet-server.md).

## First playable release specification

### Current priority: private LAN dogfight

The user narrowed the immediate goal to a private LAN relay on 21 October 2026.
Follow [LAN dogfight setup and acceptance](../host/lan.md) for that milestone:
original-client movement/damage, temporary guest pilots, original immediate
respawns, 20-kill/10-minute score rounds, and host/client restarts for reconnects.
Start with two players and test four/eight later. No authoritative protocol gate,
complete map reconstruction, custom protection or production release work is a
prerequisite for this narrower version. Real separate-PC gameplay remains pending.

The specification below is retained as the **deferred authoritative release**;
its additional requirements do not apply to the quick LAN milestone.

Implementation target selected 21 October 2026 while executing the internet
roadmap. This is a design decision, not a claim that the match is playable.

### Scope

The first release is an eight-player free-for-all dogfight with one ship,
`Ym Khtat`, on one layout. `CTF_arena` is the selected validation candidate
with `spacebkgd3`; it becomes the release map only after geometry, collision,
spawn safety and loading are verified. No flag mechanics are required for
this first match. CTF, Curt3/AI, other layouts and ship selection remain
subsequent roadmap work; they have not been removed from the todo.

The server now defaults to eight simultaneous arena admissions, configurable
from 1 to 49 for local tests. This is a capacity guard, not a measured player
capacity. The existing lifetime admission limits remain until safe reuse is
implemented.

### Match loop and proposed new rules

1. Connect to Station using a limited guest session, choose its owned pilot,
   and select the compatible arena/ship. The opt-in local guest profile now
   implements ownership; authenticated outside access and ship selection remain.
2. Download/check required content before joining, complete world loading,
   then spawn at a verified free location. Loading must have a deadline.
3. Fly and fight using server-owned movement, weapons and damage. The current
   relay does not satisfy this step.
4. On death, stop combat input, publish one kill/death result, and respawn
   after five seconds at a safe spawn with two seconds of protection.
5. End at 20 kills or ten minutes; if time expires, show ties as ties.
   No invented historical sudden-death rule is attributed to AoA.
6. Show kills/deaths and winner/tie, clear every match entity and pending
   event, then return to Station. Reconnect must not inherit a prior identity
   or consume permanent slots.

The respawn, protection, scoring and duration values above are **proposed new
design**, not recovered original rules. Weapon numbers, damage, thrust,
turn rates and physical units remain unresolved and must be recorded before
combat implementation; using plausible numbers would not recover the game.

### Supported client and compatibility decision

Support the hash-pinned 2.9.2 executable with the versioned preparation in
[client-setup.md](../reference/client-patches.md). The server rejects a well-sized handshake
with a different advertised version using legacy result 8. The network version
is self-reported and cannot establish that a client applied the patches.
Older layouts, arbitrary modified binaries and direct public ingress are
unsupported.

A maintained client/protocol change is the selected next step when the legacy
format cannot carry required integrity or ordering. Do not advertise a full
game on the basis of the existing relay. Before enabling slot reuse or an
authoritative match, require a reviewed, versioned change that supplies:

- Session generations across reconnect, entity reuse and stale datagrams.
- Ordered/deduplicated essential events beyond the original 30-ID history.
- Input sequence numbers and complete baselines, or an explicitly documented
  state-validation compromise if control inputs cannot be recovered.
- Authenticated transport/session integrity for outside testing.

A replacement client is a separate deliberate scope decision if those changes
cannot be maintained. The new preparation tool records known changes; it does
not silently implement any of the protocol extensions above.

### Acceptance scene and release gates

Use eight pilots in the same encounter, simultaneous joins/respawns, sustained
fire from every ship, one disconnect/reconnect, and a match restart. The scene
is specified but cannot yet be reproduced because combat/world loading are
missing. Keep the roadmap's 30/80/150 ms, 0/1/3% loss, churn and soak matrix.

Target 1080p/60 FPS and initially evaluate a 20 Hz server simulation. Minimum
and recommended hardware remain unmeasured; the earlier Windows 11 local run
is one observation, not a supported hardware baseline. No two-hour full-match
soak, outside-connection match, clean-machine install or eight-player capacity
result exists yet. These remain release blockers, not optional documentation.

### Continuation checkpoint: ordered combat delivery

The relay now has an opt-in ordered reliable combat experiment. It covers
missile launches, impacts and observer death notices, shares the client's
30-event duplicate-history budget with removals, and retires endpoints on
budget exhaustion or delivery timeout. See [local server](../host/server-reference.md).
This is a diagnostic milestone, not the maintained protocol change specified
above. Spawn protection, five-second respawn delay, rearming, safe reconnect,
slot reuse and authoritative simulation are still unimplemented.

The current gate passes 60 tests and six original-code emulators. The queue
tests cover 90 deterministic RTT/loss cases with jitter and duplicates; the
socket test checks launch/impact ordering, duplicate death scoring, respawn
position and exhaustion. It sends a synthetic victim death report, so it does
not prove a missile killed a real player. No full-match impairment or outside
connection claim follows from these tests.

The static CTF_arena export has valid finite geometry but omits six unresolved
nodes, including both bases. It cannot serve as complete authoritative
collision geometry without further reconstruction and original-client checks.

## Authoritative-client extension gate

Implementation checkpoint, 21 October 2026. This gate is **not passed**.
It applies to the deferred authoritative-server project. The subsequently
approved [private LAN relay milestone](../host/lan.md) does not depend on these
extensions and does not install the protection or ordered-event experiments.
All work here is localhost-only and keeps the original 2.9.2 client.
No active game executable is modified by the automated probes.

### Evidence and remaining work

Run `.venv/Scripts/python.exe -I tools/run.py aoa.emulation.check_client_extensions game/2.9.2/AOACLIENT.EXE.orig work/client-extension-gate.json`.
The source hash is checked before emulation. Prepared images exist only in
temporary directories. The tool explicitly reports the overall gate as false.

| Capability | Established evidence | Still required |
|---|---|---|
| Explicit protection | Opt-in `explicit-protection-v1` replaces the `0x81` toggle receive case at `0x4867C3`. 529 isolated cases cover idempotency, invalid length/value, null world, preserved stack/registers and adjacent memory. | Real-client messages, actual damage immunity, firing suppression, session/ordering protection and spawn policy. |
| Position correction | Original `0x4BE970` writes both actual and target coordinates; 103 isolated finite-value cases. | Velocity/orientation reconciliation, rendering, prediction and live corrections. |
| Control input | Original command handler `0x442140` maps 13 command IDs to control bits and signed scalar fields. The command record supplies a u16 ID at `+0x40`; the tested branch has nonzero `+0x44`. | Map names/units, analog input, sampling/release behavior, capture patch and sequence transport. This proves internal controls exist, not that the legacy network transmits them. |
| Ammunition | Original `0x4DD280`, called by the death-reset path, writes a rack count at `+0x50`, readiness at `+0x54`, and dirty flag at `+0x24`; eight isolated cases. Negative counts clamp to zero. | Network setter, correct rack identity/generation, loadout capacity, firing synchronization and live rearming. The original setter has no capacity check. |
| Health/reset | Death path `0x4A5440` immediately calls `0x49BB60`. Two isolated reset cases restore configured shield, ship and system values in a synthetic nonlocal player; system lookup/kind queries are mocked and the inventory-profile loop is excluded. | Local death callback, arbitrary health correction and explicit authoritative health setters. |
| Delayed respawn | Death reporting and local reset are coupled in the original path. | Verified hold-dead state, suppressed controls/fire, and server-triggered release without duplicate death reports. |
| World readiness | Ship load case `0x4306C1` calls `0x4A7F90`; entering flight subsequently resets position. | Readiness after actual dependencies finish, not an ACK for packet receipt. |
| Session/entity generations | Emulator-only guard rejects mismatched fixture epochs, entities and generations before the protection handler. | Authenticated context binding and rejection across the real receive path, including stale local gateway packets and reconnect. |
| Ordered application events | Emulator-only protection guard completes 1,000 events with retry/replay checks. Live diagnostic server remains limited to 30 lifetime events. | Actual application ACK delivery and maintained semantics across all required handlers; real-client verification. |

### Manual protection probe

Additional original-code branch evidence: the protection flag bypasses the
damage branch at `0x49BD4C`. It also bypasses missile-ammunition decrement at
`0x4B1446` when world field `+0xDEF20` is zero. Six branch cases verify both
effects. This legacy flag is therefore not a complete spawn-protection
policy: firing suppression and authoritative ammunition must be implemented
before using it in matches. No meaning is assigned to the unresolved override
field beyond the tested branch behavior.

This checks repeated explicit state commands, not combat or release readiness.
Use one client and dummy login values. Close the game before preparing it.

```powershell
.venv\Scripts\python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station localhost --experimental-protection
.venv\Scripts\python.exe -I tools/prepare_client.py check game/2.9.2/AOACLIENT.EXE
```

Check that the reported patches include `explicit-protection-v1`. Preparation
version 4 records the exact input/output hashes and preserves the original
setup backup. The optional patch persists across subsequent preparations
unless explicitly disabled. It rejects a non-loopback Station setting.

Start the probe server in a terminal, with no other local server running:

```powershell
.venv\Scripts\python.exe -I tools/station_stub.py game/2.9.2/SCRTY.BIN work/protection-probe.jsonl --ack --arena --tcp 5034 --experimental-flight --max-players 1 --experimental-protection-probe --seconds 180
```

In another terminal, launch the prepared client yourself:

```powershell
.venv\Scripts\python.exe -I tools/prepare_client.py launch game/2.9.2/AOACLIENT.EXE
```

Log in, select the pilot, and enter flight. Three seconds after the server's
bootstrap, it begins sending `1, 1, 0, 0`, three seconds apart, waiting for
the prior event's transport ACK. Each is a distinct reliable event; loss
retries reuse its sequence. The server prints each step. The client should
show **one** "you are invulnerable" message, no second enable message, then
**one** "you are no longer invulnerable" message, with no second disable
message. Record the observed messages and whether flight remains responsive.
Transport ACKs alone do not count as this observation. If loading takes
longer than the probe window, repeat after investigating load timing.

The original unpatched client would toggle four times. Do not use this
probe with an unpatched client. The diagnostic handshake cannot attest the
patch; the operator must check the prepared executable before launching it.

After the check, close the game and stop the probe server. Remove only this
optional patch, retaining the established stability patches:

```powershell
.venv\Scripts\python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --no-experimental-protection
```

The setter is idempotent but not order-independent: an old disable arriving
after a new enable would still disable protection. Therefore it must not
be promoted to gameplay until the session/ordered-event gate passes. A
server interruption can leave an incomplete probe; close the client rather
than assuming it has returned to the disabled state.

### Dependency rule

#### Ordered receive prototype (emulation only)

`aoa/emulation/check_ordered_events.py` injects an x86 guard into emulator memory
before the original protection handler. Its 25-byte fixture body carries a
magic marker, 64-bit session epoch, entity ID, generation, sequence and explicit
protection value. The trusted context is supplied by the harness, not by a
proved authentication or reconnect handshake. This is not an installable patch
or the final protocol contract.

The probe exercises 1,000 ordered events and 5,273 total cases, including lost
completion retries, future events, replay beyond 30 events, conflicting retry
payloads, stale epochs/generations, malformed values/lengths, a null world,
unbound context and sequence wrap. It rejects invalid events before the original handler,
commits the sequence only after the handler returns, and classifies exact
retries without reapplying them. A forced stop at handler entry leaves the
completion state untouched. Stack, callee-saved registers and context boundary
guards are checked. The original status-text output is mocked.

Completion here is an emulator-observed return value, **not a network ACK**.
The legacy reliable receive path sends its transport ACK at `0x486439`, before
duplicate filtering at `0x486450` and game dispatch. That existing ACK cannot
prove application completion. The prototype bypasses that receive loop; it
does not protect other handlers or establish crash recovery after partial side
effects. Authenticated binding, integration across incoming events, actual
completion delivery and manual client interaction remain blockers. Keep the
live 30-event limit and slot retirement unchanged.

Evidence: [ordered event probe](../../evidence/2.9.2/ordered_events_20261021.json).

#### Remaining gate

Keep transport/account/session integration and authoritative gameplay gated
on the remaining client proofs. Do not remove the 30-event cap, enable slot
reuse, add public ingress, or mark the server checklist complete based on
these isolated probes. A failed emulation or manual check must be diagnosed
before layering additional patches on that behavior.
