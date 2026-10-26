# Running the 2.9.2 client on Windows 10/11

Status (20 Oct 2026, Windows 11 23H2, AMD Radeon iGPU, 125% display scaling):
the client reaches the login dialog, **Play Offline** opens the Station screen,
and **Play** loads the offline mission in full 3D at the desktop resolution
(1920x1080, 60 FPS) with the complete HUD. The historical-host lookup fails
(WSA 11001); the later local Station work uses the preparation below.

Recommended graphics path: dgVoodoo2 (DirectX 7 → Direct3D 11), set to
windowed. The game sizes its window to the desktop, so this behaves like
borderless fullscreen, never changes the display mode, and survives Alt+Tab.
Native DirectX 7 also renders, but switches to exclusive fullscreen and drew
fewer HUD elements in testing.

**Do not set a compatibility mode** (Windows 95/98/XP) on `AOACLIENT.EXE`. A
Windows 95 layer makes the client hang before the login dialog natively and
overflow the stack in the shim engine (AcGenral.dll) with dgVoodoo.

## Setup

For the current supported local workflow, use
[client-setup.md](client-setup.md). `prepare_client.py` now composes the logger,
physics and configurable Station-host fixes with exact undo and a checked
launcher. The setup script below calls it. The separate patch commands later
in this document describe earlier experiments; do not mix them with a recorded
prepared client, because unrecorded executable changes are rejected.

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

This builds `game\2.9.2\` (gitignored) from
`originals\2.9.2\aoa_2.9.2_installer_2.11.1.exe` without running the installer,
patches the client, registers the skin control for the current user, and
installs the wrapper from `originals\wrappers\dgvoodoo2-2.87.5\dgVoodoo2_87_5.zip`
(official GitHub release v2.87.5, 9,268,078 bytes, SHA-256
`5ffde6927f7355ca3fdd5d785b581256a8e6539fa13e395a891ade6ba1040850`) plus an
`AOACLIENT.EXE.manifest` declaring DPI awareness (without it, at 125% scaling
the game renders at 1536x864 and is upscaled). Pass `-Wrapper ""` for native
DirectX 7. Then
run `game\2.9.2\AOACLIENT.EXE` and choose **Play Offline** → **Play**, or
**Tutorial Mode**. Undo the registration with
`tools\register_activeskin.ps1 game\2.9.2\ACTIVESKIN.OCX -Unregister`.

## What was broken

| Symptom | Cause | Fix |
|---|---|---|
| Crash `0xC000041D` creating the first dialog | Login/station dialogs host SoftShape ActiveSkin 3.60 ActiveX controls (`{972DE6C2-…}`, `{53FA8D4x-…}`); unregistered, MFC throws and then frees a bad pointer. | `tools/register_activeskin.ps1`: runs the OCX's own `DllRegisterServer` in a 32-bit process with HKCR → `HKCU\Software\Classes` and HKLM → HKCU (`RegOverridePredefKey`). HKLM is needed because the ScriptPlugins object writes `HKLM\Software\SoftShape\ActiveSkin\ScriptPlugins` directly and fails registration otherwise. Nothing is written to HKLM. |
| Random heap crashes during `InitAppResources` (`0xC0000005` in ntdll heap, or `CMemoryException` on tiny allocations) | Heap overflow: the separately built Dx7Api library (`Z:\src\Dx7Api`) allocates the "DxGfx" logger with a stale `sizeof` of 0x20 (`push 0x20` at VA 0x551775); the logger class is 0x24 bytes and its constructor (0x5266b0) writes +0x20. | `tools/patch_client.py`: `push 0x20` → `push 0x24`. |
| Occasional crash writing 0x10023 in a worker thread | Logger (0x526d00) is not thread-safe: per line it does fopen/fwrite/fclose and stores `(FILE*)0xFFFF`, so a concurrent thread can `fwrite(0xFFFF)`; the formatter it uses (0x527210) `vsprintf`s into one global buffer. | `tools/patch_client.py`: both functions wrapped in a recursive spinlock in the `.text` padding (0x58B200), using only imports the client already has. |

The overflow was located with `tools/crashdbg.py --guard-heap`, which serves
every msvcrt allocation from a guard-paged arena so the overrunning instruction
faults immediately. Before the patch the client crashed in 3/3 fresh-path
launches; after it, 6/6 reached the login dialog. The Windows XP SP3
compatibility layer only masks the overflow (3/4) and is not needed.

## Known leftovers

### Local online testing: Play Online stays disabled

The login dialog disables Play Online (control `0x3F4`) before looking up
`aoahost.com`. If that lookup fails, it logs `PANIC LoginDlgProc error
[11001]` and returns without enabling the button. Typing a Station IP
does not by itself complete this startup lookup. This explains why the
earlier test driver could trigger online login while a manual click did
nothing: the driver posts the command directly.

For the local stand-in, close the game and use the consolidated command:

```powershell
.venv/Scripts/python.exe -I tools/prepare_client.py prepare game/2.9.2/AOACLIENT.EXE --station localhost
```

This selects `localhost`, previously verified to resolve to `127.0.0.1` on
this machine, while composing the stability and physics fixes. The successful
lookup path selects the returned IP and enables Play Online (`0x44428F`
onward). Preparation does not run the game. Use the checked `launch` action
and dummy login values with the loopback server running. Exact undo is the
`prepare_client.py undo` action described in the setup runbook.

Historically, `local_station.py` made the isolated 12-byte hostname edit at
file offset `0x1C5C60`; its standalone `--undo` belongs to that older tool.
The subsequent user-operated run reached Station with Play Online. A separate
Play failure was traced to the stub's
nonexistent backdrop and corrected by advertising bundled assets. A local
run now reaches the in-game briefing; world/spawn state and stability remain
unfinished. See `docs/findings.md` sections 9.4–9.5 for evidence and limits.

### Local arena physics: zero-time updates

The original 2.9.2 physics code sometimes calculates acceleration with a
zero elapsed-time divisor, producing NaN values that contaminate remote
movement. A live breakpoint confirmed zero time steps; the original
instructions also reproduce the failure in Unicorn. A bounded patched run
recorded no invalid values in 300 samples, versus 38 of 100 before the fix.

The consolidated preparation above includes this guard. For reproducing the
earlier standalone experiment on an unrecorded working copy, the command was:

```powershell
.venv/Scripts/python.exe -I tools/physics_timestep.py game/2.9.2/AOACLIENT.EXE
```

This optional, reversible guard skips physics only when the elapsed time
is zero. It accepts only the known stability-patched 2.9.2 image (original
or localhost hostname), checks the entire image hash, and leaves positive
time steps on the original path. Use the same command with `--undo` to
restore the prior bytes. Remove this guard before using `local_station.py`
to change or undo the hostname; that older tool requires the prior hash.
This does not implement missing multiplayer gameplay. See findings 9.10.

### Other leftovers

* `Error (Load Texture) file not found(NavDisplay1.tga)` — likely a
  server-delivered resource; the HUD still renders.
* Many tightly spaced test crashes can make Windows apply the Fault Tolerant
  Heap to that EXE path (`FTH: ... applied` in a debugger); here it was no
  longer applied two hours later. Run crash-loop experiments on fresh copies of
  the game folder so FTH does not change heap behaviour mid-investigation.
