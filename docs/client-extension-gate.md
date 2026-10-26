# Authoritative-client extension gate

Implementation checkpoint, 21 October 2026. This gate is **not passed**.
It applies to the deferred authoritative-server project. The subsequently
approved [private LAN relay milestone](lan-dogfight.md) does not depend on these
extensions and does not install the protection or ordered-event experiments.
All work here is localhost-only and keeps the original 2.9.2 client.
No active game executable is modified by the automated probes.

## Evidence and remaining work

Run `.venv/Scripts/python.exe -I tools/emulate_client_extensions.py game/2.9.2/AOACLIENT.EXE.orig work/client-extension-gate.json`.
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

## Manual protection probe

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

## Dependency rule

### Ordered receive prototype (emulation only)

`tools/emulate_ordered_events.py` injects an x86 guard into emulator memory
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

Evidence: [ordered event probe](../evidence/2.9.2/ordered_events_20261021.json).

### Remaining gate

Keep transport/account/session integration and authoritative gameplay gated
on the remaining client proofs. Do not remove the 30-event cap, enable slot
reuse, add public ingress, or mark the server checklist complete based on
these isolated probes. A failed emulation or manual check must be diagnosed
before layering additional patches on that behavior.
