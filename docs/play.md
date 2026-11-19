# Playing Ace of Angels on Windows 10/11

This guide goes from nothing to flying, then to playing with friends. It uses
the 2.9.2 client (2004), the most complete build recovered. Nothing here runs
the original installer: the game files are unpacked from it directly.

The player window was rebuilt on 16 November 2026 and has been opened only on
Linux under a virtual screen, never on Windows; its Windows-only steps have
not been run ([status](STATUS.md#implemented-but-not-tested)). The older
command-line route is kept below as a fallback.

## 1. What you need

- Windows 10 or 11 (Windows 11 is the tested platform)
- [Python](https://www.python.org/downloads/) 3.10 or later. In its installer,
  tick **Add python.exe to PATH**. No packages are needed.
- About 400 MB of disk space

## 2. Get the project

On the project's GitHub page choose **Code → Download ZIP**, and extract the
ZIP anywhere (for example `Documents\ace-of-angels`). Git users can clone it
instead.

## 3. Double-click `Play.cmd` and follow the checklist

The player window opens on a checklist. Each row says what it will do, and
has one button:

1. **Game files.** **Find my game folder…** if you already have a 2.9.2 game
   folder, or **Download (35 MB)**. The download comes from archive.org (the
   Internet Archive), which keeps a 2004 games disc the installer was on. The
   window says so and asks before it starts. The file is checked against its
   known fingerprint, saved in its own folder under `builds\`, and never run.
2. **Game folder.** **Unpack the game** extracts the installer into
   `game\2.9.2\` and checks every file against `config/client-2.9.2.json`.
3. **Compatibility fixes.** **Apply the fixes** makes the 2004 game run on
   Windows 10 and 11 and shows the patch level (22 today). Every change has
   an exact undo.
4. **Login screen.** **Register** registers the login screen's skin control
   for your Windows user only (no administrator rights needed). Without it the
   login screen never appears.
5. **Graphics wrapper (recommended).** **Open the download page**, download
   `dgVoodoo2_87_5.zip` from it, then choose **I've downloaded it**: the
   window finds the ZIP in your Downloads folder, checks it and installs it.
   With the wrapper the game runs in a borderless window and survives
   Alt+Tab. **Skip** keeps the original full-screen mode.

When every row is green, **Done: go to Play**. The **Setup** button brings the
checklist back later.

## 4. Fly

On the **Play** tab, click **Play**. At the login screen type any name and
password (there are no accounts), choose **Play Offline**, then **Play** for
the training mission (waves of six enemies, with three AI wingmen you
command), or **Tutorial Mode**. The key map is `game\2.9.2\KEYMAP.PDF`.

Keys added or fixed by this project: **F2** a chase camera, **F4** an orbit
camera that circles your ship (**F5** saves a screenshot to
`Capture Images\`), **T / G / J** cycle and pick targets, **Alt+Q** leaves
the arena.

The **Options** tab groups the client options: **Fixes (recommended)**,
**Visual extras**, **Experimental**, and **Graphics quality** (with the
wrapper). Hover over an option to see what it does. Options that change the
same code explain why only one can be on. **Recommended** and **Original
visuals** set them all at once; **Apply** saves and checks them. **Restore the
original game** undoes every fix, and **Install JRMAP terrain** makes the file
JRMAP needs. Details: [client-setup.md](client-setup.md#client-launcher-and-visual-options).

Optional: [texture-pack.md](texture-pack.md) makes sharper, 32-bit ship and
station skins from your own copy.

## 5. Multiplayer on one PC

1. Double-click `Host.cmd`. Leave **This PC only** chosen and click **Start**.
2. In the player window choose **Play on: This PC** and **Play**. Log in with
   any name, choose **Play Online**, pick the temporary pilot and the arena,
   and fly.

The host window shows players, kills and deaths, and can message, kick, end
matches and change maps. See [host-control.md](host-control.md).

## Play with friends

Everyone sets up their own copy with steps 1 to 3. The host chooses **My
home network** or **Friends over a VPN** in the host window, clicks
**Start**, and sends everyone the line in **Tell your players** (there is a
**Copy** button). Each player then:

1. Opens the **Join a friend** tab and pastes the line.
2. Clicks **Check**. Three results appear: whether the game can use the
   address, whether the name the game uses leads to it, and whether the host
   answers.
3. Clicks **Join**. Only the server address changes; every other option
   keeps its setting.

A home-network address of up to 11 characters (such as `192.168.1.5`) works
directly. Longer addresses, which includes every VPN address, go through a
short name such as `aoavpn` that the Windows hosts file points at the
address. The window shows the exact line, with **Copy** and **Open Notepad
as administrator**: add the line at the end of the file, save, and choose
**Check** again. The window never edits the hosts file itself.

Never forward the game ports through your router: the old protocol has no
real authentication. The VPN route keeps the host reachable only by people
you invite. The full runbooks: [lan-dogfight.md](lan-dogfight.md) and
[vpn-dogfight.md](vpn-dogfight.md).

Matches are free-for-all: 20 kills or 10 minutes, then scores reset and play
continues. Separate PCs have played over a LAN only through the
[Linux host](linux-host.md) so far. A Windows-hosted LAN game and VPN play
between separate connections have not been recorded
([status](STATUS.md#implemented-but-not-tested)). If you try one, please open
an issue with what worked and what didn't.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Play.cmd` says Python was not found | Install Python 3.10 or later with **Add python.exe to PATH** ticked, then double-click `Play.cmd` again. |
| A window shows an error | It names what happened and what to do; **Show details** has the rest, also saved in `work\logs\launcher.log` (player) or `work\logs\host.log` (host). |
| A taskbar button appears but no login screen | Open **Setup** and do step 4 (**Register**). After moving the game folder, register again. |
| Hangs or crashes at start | Remove any compatibility mode from `AOACLIENT.EXE` (Properties → Compatibility). The game breaks under them. |
| **Play Online** is greyed out | The game cannot find its server. Use **Join a friend** and **Check**, or choose **Play on: This PC**. |
| Server list fails, or the login works but flight doesn't | The host's firewall: the host window's **Firewall** box has the two commands to copy. |
| Step 2 says a file is changed | The folder is not a clean 2.9.2 copy. Choose another folder, or rename `game\2.9.2` and unpack again. |

More detail: [running-on-windows-11.md](running-on-windows-11.md) (what was
broken and why) and [client-setup.md](client-setup.md) (every patch, the undo
and the checks).

## Without the window (fallback)

The command-line route still works, from PowerShell at the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -I tools\fetch_known_builds.py builds\
powershell -ExecutionPolicy Bypass -File tools\setup_game.ps1
.venv\Scripts\python.exe -I tools\prepare_client.py launch game\2.9.2\AOACLIENT.EXE
```

`setup_game.ps1` expects the wrapper ZIP (if any) at
`originals\wrappers\dgvoodoo2-2.87.5\dgVoodoo2_87_5.zip`. To point the client
at a friend's server without the window (every other option keeps its
state):

```powershell
.venv\Scripts\python.exe -I tools\prepare_client.py prepare game\2.9.2\AOACLIENT.EXE --station aoalan --no-experimental-protection
```

To undo the client changes, or remove the skin registration:

```powershell
.venv\Scripts\python.exe -I tools\prepare_client.py undo game\2.9.2\AOACLIENT.EXE
powershell -ExecutionPolicy Bypass -File tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX -Unregister
```
