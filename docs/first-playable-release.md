# First playable release specification

## Current priority: private LAN dogfight

The user narrowed the immediate goal to a private LAN relay on 21 October 2026.
Follow [LAN dogfight setup and acceptance](lan-dogfight.md) for that milestone:
original-client movement/damage, temporary guest pilots, original immediate
respawns, 20-kill/10-minute score rounds, and host/client restarts for reconnects.
Start with two players and test four/eight later. No authoritative protocol gate,
complete map reconstruction, custom protection or production release work is a
prerequisite for this narrower version. Real separate-PC gameplay remains pending.

The specification below is retained as the **deferred authoritative release**;
its additional requirements do not apply to the quick LAN milestone.

Implementation target selected 21 October 2026 while executing the internet
roadmap. This is a design decision, not a claim that the match is playable.

## Scope

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

## Match loop and proposed new rules

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

## Supported client and compatibility decision

Support the hash-pinned 2.9.2 executable with the versioned preparation in
[client-setup.md](client-setup.md). The server rejects a well-sized handshake
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

## Acceptance scene and release gates

Use eight pilots in the same encounter, simultaneous joins/respawns, sustained
fire from every ship, one disconnect/reconnect, and a match restart. The scene
is specified but cannot yet be reproduced because combat/world loading are
missing. Keep the roadmap's 30/80/150 ms, 0/1/3% loss, churn and soak matrix.

Target 1080p/60 FPS and initially evaluate a 20 Hz server simulation. Minimum
and recommended hardware remain unmeasured; the earlier Windows 11 local run
is one observation, not a supported hardware baseline. No two-hour full-match
soak, outside-connection match, clean-machine install or eight-player capacity
result exists yet. These remain release blockers, not optional documentation.

## Continuation checkpoint: ordered combat delivery

The relay now has an opt-in ordered reliable combat experiment. It covers
missile launches, impacts and observer death notices, shares the client's
30-event duplicate-history budget with removals, and retires endpoints on
budget exhaustion or delivery timeout. See [local server](local-server.md).
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
