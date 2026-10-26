# Additional compiled-code findings

Static inspection, 20 October 2026. These are recovered binary code paths,
not recovered C++ source or verified live features. No client was executed
or patched. All detailed addresses below belong to the hash-verified **2.7.1**
client. Cross-version string/reference evidence is in `evidence/code-clues.json`;
annotated instruction excerpts are in ignored `work/code-clues/`.

## Shared server-role scenario code

`CAOAWorld::LoadScenarioGroupObjectMembers` starts at `0x50DB20`.
It tests a world-state byte at `+0xD0068`; the zero branch logs
`non-Server-side, nothing to do` and exits. The other branch iterates group
members, fills an object-load record referencing `AoAObjects.odb`, reads
three coordinate values, and calls the object-loading path (`0x4FF7B0`).

This is stronger evidence than a stray server-related string: the object
iteration and load calls are present. It is a useful starting point for
understanding scenario spawning. Whether the distributed client ever sets
up the complete state required by this branch is unverified. Flipping the
byte is not an established way to make a working server.

## Built-in terrain editing paths

The command handler at `0x503235` toggles an edit-state byte at `+0xD00BA`.
Entry checks another world byte and a player-record field before admitting
the mode; rejection prints `edit mode not allowed -management`.
The exact meaning of those permission fields is not established here.

Adjacent command cases check edit state and call terrain-object loading,
terrain clearing, and a turret-loading path. The latter (`0x5034EA`) loads
`TurretA` from `AoAObjects.odb` and passes further configuration arguments.
Another case reads a terrain map from a supplied filename.

This suggests developer/admin authoring facilities survived compilation.
The actual command-name mapping, activation conditions, and working UI have
not been tested. No access checks were changed.

## Capture-the-flag scoring implementation

The routine identified by `CAOAWorld::CheckCaptureFlagRules` contains winner
selection, an award calculation, iteration over player entries, and a direct
score addition at `0x507DCC`, followed by an update call. It formats
`Team %s wins the Flag Game, %d points awarded` at `0x507D44`.

This provides a concrete lead for reconstructing the original rules instead
of inventing them. The complete win conditions, identities of all fields,
and runtime reachability still need analysis. No claim that CTF currently
works in the replacement server follows from this inspection.

## A small AI scripting language

The parser's action-name pointer table at `0x69476C` contains:
`EMITTEXT`, `GUESSTARGETPOSITION`, `ACQUIREHOSTILE`, `INTERCEPT`, then `~`.
The action parser at `0x54E3E0` compares tokens with this table and dispatches
through four cases, calling parsers at `0x54F3B0`, `0x54F700`, `0x54F8C0`,
and `0x54FA90`. Thus the names are backed by parser implementations.

Bundled scripts provide concrete syntax: the capital-ship script declares
a waypoint and schedules an Intercept action; the missile script uses
`GuessTargetPosition ecm 70`. Robot parameters include a 3,000 ms dodge
interval, 750 ms next-jink interval, and 1,000 ms reacquisition interval.
These are script settings, not measured in-game timing or a proof of how
every parameter affects simulation.

## Developer traces and personality

The executable retains source paths, class/method names, and humorous
diagnostics such as `Fool we's jousting now` and `Chasing sans intercept`.
Both have code references in the AI area. Wingman-order diagnostics also
survive. These help distinguish intended AI states and locate routines;
they do not mean the original source tree is present.

## Verification and scope

Six previously verified clients were scanned for selected diagnostics and
instruction references using the existing `PE`, `Disasm`, and `annotate`
helpers. Detailed control flow was inspected in four 2.7.1 ranges recorded
in the evidence JSON. Cross-version absence of a diagnostic is not proof
that a feature was removed; later builds omit many diagnostic messages.

Best next target for server reconstruction: trace the scenario-object loader
and its callers, then map the CTF score/win fields. Best target for map
research: recover the edit-command table. The terrain read format is now known
and `JRMAP.TRN` decodes with it (`tools/decode_trn.py`, `level-data.md`).

## 2.9.2 follow-up: mission-group loader

The equivalent diagnostic in the verified 2.9.2 executable names
`CAOAWorld::LoadMissionGroupObjectMembers`, starting at `0x4C0030`.
Its server-role test is world byte `+0xDEEEC` at `0x4C0069`; the zero
branch logs `non-Server-side, nothing to do`. The other branch iterates
the group at `+0x78` with count at `+0x6C`, constructing records using
`AoAObjects.odb`. These are static findings, not a tested server mode.
They provide a version-correct starting point for the current client;
the 2.7.1 addresses above must not be used directly in 2.9.2.

Follow-up on 21 Oct: the loader calls `LoadObject` at `0x4A66A0`, then
`SendLoadObject` at `0x48A460` for connected players. The latter sends type
`0x25`, payload length `0xBF` (191), through `0x485B90`. Its payload has
32-byte model/database/display-name fields at `0/0x20/0x40`, tag at `0x60`,
object kind at `0x64`, remaining lifetime at `0x68`, coordinates at `0x92`,
and scene identifier at `0xBB`. The mission loader chooses kind `0x11`.
Receiver `0x43059D` calls the same world object loader. Object indices must
be below 1000; tags with `0x40000000` select the regular object pool.

An opt-in test in `station_stub.py` now creates one `Ym Khtat` with this
message. A real client rendered it as `Local mission ship` and read-only
inspection confirmed its tag, kind and coordinates. This verifies object
spawning, not loading Curt3 or running the mission AI. See findings 9.11.
