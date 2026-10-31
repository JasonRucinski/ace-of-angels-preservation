# Recording the highlight reel

A short highlight video made from scripted recordings of the real 2.9.2
client: different fighters on different maps, filmed in the cockpit, chase
(F2) and orbit (F4) views, with title cards and the game's own music. Nothing
in it is rendered outside the game; every shot is the client running on this
PC. First made on 27 Oct 2026 (48.9 s).

The recordings and the finished video contain Flying Rock's game footage and
music. They live in git-ignored `work/reel/` and are **never committed**.

## What you need

- `game\2.9.2` set up as in [play.md](play.md), at patch version 21 (the
  orbit camera with whole-frame culling; version 20 makes objects blink in
  the orbit view, [findings 9.48](findings.md)).
- ffmpeg 8.0 or later on `PATH`, for its `gfxcapture` (Windows Graphics
  Capture) source. 8.1.1 was used.
- The PC unlocked, awake and left alone for about 12 minutes. The game takes
  the foreground on the main display. Plug a laptop in: on battery it drops
  into Modern Standby after a few idle minutes, and from then on every
  capture is black. The recorder keeps the display awake once it is running,
  but it cannot wake a sleeping one.
- No other host running: stop the host control window (or any
  `station_stub.py`) first. The recorder needs the game ports for its own
  host on each shot's map, and refuses to film if they are taken.
- A shell that is not sandboxed. A restricted process captures black frames
  (window capture) or hangs (`ddagrab`).

## Steps

```powershell
py -3.12 -I tools\reel\record.py tools\reel\shots.json
py -3.12 -I tools\reel\edit.py tools\reel\edit.json
```

`record.py` writes `work\reel\raw\NN_<shot>.mp4` and a log of what each shot
got (`work\reel\logs\record.json`). `--only NAME ...` re-films single shots.
`edit.py` writes `work\reel\reel.mp4` (1920×1080, 60 fps, −14 LUFS) and
`reel-720p.mp4`. `--no-music` or `--music FILE` swaps the soundtrack, since
platforms may flag the original MUSIC.MP3.

## How a shot is filmed

For each entry in [`shots.json`](../tools/reel/shots.json), `record.py`:

1. Starts the loopback host on the shot's map with `--start-vessel` (the
   fighter the pilot starts in), optional `--spawn-at` and `--target-ships`.
2. Launches the client and logs in with window messages only
   (`client_login.ps1`, then Station Play). After a killed session the first
   launch sometimes shows a login dialog with five edit boxes; the recorder
   relaunches.
3. Logs in the shot's scripted pilots (`tools/reel/bot.py`): synthetic
   clients that ask for a hull with the fighter menu's `0xA0` request and send
   absolute position and velocity 30 times a second along a straight line or
   circle. They fly nose-first along +z; nothing sends orientation, so the
   shots keep their paths along +z.
4. Brings the game to the foreground and hides cluttering HUD panels with
   real Shift+key presses (the game's own "visible toggle" commands:
   Shift+U user list, Shift+C comms, Shift+A arena messages, Shift+W weapon
   list). Posted key messages do not reach these.
5. Forces the camera in the running process only (`client_mem.py`): the
   `and al,1` after the F2/F4 key reads in the third-person camera's cave
   (`0x58BC3E`, `0x58BC1B`) becomes `mov al,1`. Both views were checked on
   screen. The file on disk is not changed.
6. Holds the ship's velocity by rewriting player slot 0 `+0x54` every 10 ms,
   and optionally holds the fire key, while ffmpeg records the window.

`scout.py MAP ...` enters flight on maps and saves each one's terrain object
positions plus an F5 screenshot. F5 reads the game's own frame, so it works
with the display off. Safe zones are 5,137-unit half-size cubes, mostly at
the origin; the shot spawns sit outside them.

## Known limits

- The laptop GPU renders irrosa01's base at about 12 fps, so that shot is
  kept short. Other shots run at 20–45 fps; the reel is encoded at 60.
- Flying into a structure flashes the view red. Spawns need a clear path.
- Remote ships' orientation is whatever the client gives them, and the
  bots' paths are straight lines.
- Tholfus and Saksatar use the untextured AlphaFighter model and draw flat
  orange; the shot list avoids them.
