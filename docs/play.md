# Playing Ace of Angels on Windows 10/11

This guide goes from nothing to flying, then to playing with friends. It uses
the 2.9.2 client (2004), the most complete build recovered. Nothing here runs
the original installer: the game files are unpacked from it directly.

Everything below is run from a normal PowerShell window at the repository
root. Each player does steps 1–4 on their own PC with their own copy.

## 1. What you need

- Windows 10 or 11 (Windows 11 is the tested platform)
- [Python 3.12](https://www.python.org/downloads/) (tick "Add python.exe to PATH" or use the `py` launcher)
- [Git](https://git-scm.com/download/win)
- About 400 MB of disk space

## 2. Get the project and the game

```powershell
git clone https://github.com/JasonRucinski/ace-of-angels-preservation.git ace-of-angels
cd ace-of-angels
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -I tools\fetch_known_builds.py builds\
```

`fetch_known_builds.py` downloads the 2.8.2 and 2.9.2 installers (about
63 MB) from archive.org and checks their hashes. The 2.9.2 installer lands in
`builds\v2.9.2_2004_FamilyGamePack3\aoa-current.exe`.

Then download the graphics wrapper
[dgVoodoo2 2.87.5](https://github.com/dege-diosg/dgVoodoo2/releases/download/v2.87.5/dgVoodoo2_87_5.zip)
(9.3 MB) and save the zip, unopened, as
`originals\wrappers\dgvoodoo2-2.87.5\dgVoodoo2_87_5.zip`. It translates the
game's DirectX 7 to Direct3D 11, so it runs in a borderless window and
survives Alt+Tab. Only this exact version is accepted.

## 3. Build the game folder

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_game.ps1
```

This creates `game\2.9.2\`. It unpacks the installer, applies the client fixes
(each one recorded with an exact undo), registers the game's dialog skin
control for your Windows user only (no admin needed), and installs the wrapper.

Run it in your own PowerShell window. If an automated or sandboxed shell runs
it, the skin registration may be invisible to the game, and the login dialog
never appears.

## 4. Fly offline

```powershell
.venv\Scripts\python.exe -I tools\prepare_client.py launch game\2.9.2\AOACLIENT.EXE
```

At the login dialog choose **Play Offline**, then **Play** for the training
mission (waves of six enemies, with three AI wingmen you command), or
**Tutorial Mode**. The key map is `game\2.9.2\KEYMAP.PDF`.

Useful keys added or fixed by this project: **F2** toggles a chase camera,
**T / G / J** cycle and pick targets, **Alt+Q** leaves the arena.

Optional: [texture-pack.md](texture-pack.md) makes sharper, 32-bit ship and
station skins from your own copy.

## 5. Multiplayer on one PC

To try online play before involving anyone else:

1. Double-click `tools\host_control.cmd`. Choose **This PC only**, pick a map
   and click **Start host**.
2. Launch the game as in step 4. Log in with any name and password (there are
   no accounts), choose **Play Online**, pick the temporary pilot and the
   arena, and fly.

The host window shows players, kills and deaths, and can message, kick, end
matches and switch maps. See [host-control.md](host-control.md).

## Play with friends

Everyone needs their own copy set up with steps 1–4. Then pick one of:

| Situation | Guide | Players' Station name |
|---|---|---|
| Same home network | [lan-dogfight.md](lan-dogfight.md) | `aoalan` |
| Different internet connections | [vpn-dogfight.md](vpn-dogfight.md) (Tailscale, ZeroTier or WireGuard) | `aoavpn` |

Never forward the game ports through your router: the old protocol has no real
authentication. The VPN route keeps the host reachable only by people you
invite.

In short, the host opens three firewall ports to the LAN or VPN range and
starts the server (`host_control.cmd` in LAN or VPN mode, or
`tools\start_lan_dogfight.ps1`). Each player adds the host's address to their
Windows `hosts` file under the short alias, then re-points their client:

```powershell
.venv\Scripts\python.exe -I tools\prepare_client.py prepare game\2.9.2\AOACLIENT.EXE --station aoalan --no-experimental-protection
```

The guides give the exact firewall and `hosts` commands.

Matches are free-for-all: 20 kills or 10 minutes, then scores reset and play
continues. **Play between separate PCs has not been recorded yet.** If you try
it, please open an issue with what worked and what didn't.

## Troubleshooting

| Symptom | Fix |
|---|---|
| A taskbar button appears but no login dialog | The skin control isn't registered for you. In your own PowerShell window: `powershell -ExecutionPolicy Bypass -File tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX` |
| Hangs or crashes at start | Remove any compatibility mode from `AOACLIENT.EXE` (Properties → Compatibility). The game breaks under them. |
| **Play Online** is greyed out | The client can't resolve its Station name. Check the `hosts` alias, or re-run `prepare` with `--station localhost` for single-PC play. |
| Server list fails, or Station works but flight doesn't | Check the firewall: TCP 5034 for the list, UDP 5033 for Station, UDP 5031 for the arena. |
| `prepare` refuses the executable | It accepts only known builds and recorded patch states. Delete `game\2.9.2` and run step 3 again. |
| `setup_game.ps1` says the folder exists | It never overwrites. Delete or rename `game\2.9.2` first. |

More detail: [running-on-windows-11.md](running-on-windows-11.md) (what was
broken and why) and [client-setup.md](client-setup.md) (every patch, the undo
and the checks).

To undo the client changes:

```powershell
.venv\Scripts\python.exe -I tools\prepare_client.py undo game\2.9.2\AOACLIENT.EXE
```

To remove the skin registration:

```powershell
powershell -ExecutionPolicy Bypass -File tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX -Unregister
```
