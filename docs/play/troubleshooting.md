# Troubleshooting

For the player window and the game on Windows 10/11. The setup itself is in
[README.md](README.md).

## Symptoms

| Symptom | Fix |
|---|---|
| `Play.cmd` says Python was not found | Install Python 3.10 or later with **Add python.exe to PATH** ticked, then double-click `Play.cmd` again. |
| A window shows an error | It names what happened and what to do; **Show details** has the rest, also saved in `work\logs\launcher.log` (player) or `work\logs\host.log` (host). |
| A taskbar button appears but no login screen | Open **Setup** and do step 4 (**Register**). After moving the game folder, register again. |
| Hangs or crashes at start | Remove any compatibility mode from `AOACLIENT.EXE` (Properties → Compatibility). The game breaks under them. |
| **Play Online** is greyed out | The game cannot find its server. Use **Join a friend** and **Check**, or choose **Play on: This PC**. |
| Server list fails, or the login works but flight doesn't | The host's firewall: the host window's **Firewall** box has the two commands to copy. |
| Step 2 says a file is changed | The folder is not a clean 2.9.2 copy. Choose another folder, or rename `game\2.9.2` and unpack again. |

More detail: [running-on-windows-11.md](../research/windows-11.md) (what was
broken and why) and [client-setup.md](../reference/client-patches.md) (every patch, the undo
and the checks).

## Setting up by hand: what `setup_game.ps1` does

Run this yourself in a normal PowerShell window (not from a sandboxed agent
shell — its registry writes are invisible to programs you launch, and the
login dialog then silently never appears):

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_game.ps1
```

If `game\2.9.2` already exists and only the registration is missing:

```powershell
powershell -ExecutionPolicy Bypass -File tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX
```

Symptom of a missing registration: a taskbar button appears, no login dialog,
and the log stops at `(LoginTrace) Restore()..End` without
`initializing login dialog` (MFC's `DoModal` for dialog 127 fails because the
ActiveSkin controls cannot be created).

It needs the project's `.venv` and stops with the commands to create it if
`.venv` is missing. This builds `game\2.9.2\` (gitignored) from
`originals\2.9.2\aoa_2.9.2_installer_2.11.1.exe`, or, if that file is absent,
from `builds\v2.9.2_2004_FamilyGamePack3\aoa-current.exe` where
`fetch_known_builds.py` saves it, without running the installer,
patches the client, registers the skin control for the current user, and
installs the wrapper from `originals\wrappers\dgvoodoo2-2.87.5\dgVoodoo2_87_5.zip`
(official GitHub release v2.87.5, 9,268,078 bytes, SHA-256
`5ffde6927f7355ca3fdd5d785b581256a8e6539fa13e395a891ade6ba1040850`) plus an
`AOACLIENT.EXE.manifest` declaring DPI awareness (without it, at 125% scaling
the game renders at 1536x864 and is upscaled). Pass `-Wrapper ""` for native
DirectX 7. If the default wrapper zip is absent, it continues with native
DirectX 7 and prints how to add the wrapper later; a `-Wrapper` path you name
must exist, or it stops. Then
run `game\2.9.2\AOACLIENT.EXE` and choose **Play Offline** → **Play**, or
**Tutorial Mode**. Undo the registration with
`tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX -Unregister`.
