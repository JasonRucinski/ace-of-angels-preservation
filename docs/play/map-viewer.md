# Viewing every recovered map in the client

Added 23 October 2026. This loads any original 2.9.2 layout, or the converted
2.0.0 editor map `JRMAP`, as native terrain in a prepared 2.9.2 client
connected to the loopback relay. It is a way to look at maps. It does not
make them playable: no collision, turret, warp-gate, flag or mission
behaviour is claimed.

## Setup (once)

Close the client, then prepare it and convert the shipped `JRMAP.TRN`. Loading
a map needs the online terrain hook, patch level 11 or later; safe zones draw
from patch level 18. Current preparation gives level 22:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station localhost
.venv/Scripts/python.exe -I tools/map_viewer.py install game/2.9.2
```

`install` checks that `JRMAP.TRN` is the shipped file (SHA-256 `e3da8fbb…c5c4`)
and writes `jrmap292.trn` beside the client. Nothing is downloaded.

## Viewing a map

The [host control window](../host/host-window.md) does all of this from one window
(pick a map, Start, Load map to switch). From the command line:

```powershell
.venv/Scripts/python.exe -I tools/map_viewer.py list
.venv/Scripts/python.exe -I tools/map_viewer.py serve CTF_arena
```

Launch the prepared client from its folder, log in to `127.0.0.1` with any
test handle, and press Play. The map is built when you enter flight.

**To switch maps, quit the client completely.** The hook loads terrain only
when the terrain list is empty, so a second map in the same session is
skipped. Press Alt+Q, close the copy the client relaunches (`autologin`),
stop the server with Ctrl+C, then `serve` the next map.

`--spawn-at X Y Z` overrides the starting point. Ships face +z at spawn.

## Maps

Which maps exist, how many objects each builds, their viewing spawns
and which have been seen on screen: [reference/maps.md](../reference/maps.md)
and [STATUS.md](../STATUS.md#maps). How the client loads a map is in the same
reference; the 26 October 2026 investigation of the layouts' unfilled nodes
is in the [research log](../research/log.md#unfilled-node-investigation-from-playmap-viewermd).
