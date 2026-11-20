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

The setup steps that stood here are in [play/README.md](../play/README.md);
what `setup_game.ps1` does, and the skin-registration symptom, are in
[play/troubleshooting.md](../play/troubleshooting.md#setting-up-by-hand-what-setup_gameps1-does).
`patch_client.py`, `local_station.py` and `physics_timestep.py` are now
libraries only: their
standalone command lines were removed on 13 November 2026, because they
changed the executable without updating `_client_setup.json` and broke a
prepared client. Where this document mentions them, it describes earlier
experiments.

## What was broken

| Symptom | Cause | Fix |
|---|---|---|
| Crash `0xC000041D` creating the first dialog | Login/station dialogs host SoftShape ActiveSkin 3.60 ActiveX controls (`{972DE6C2-…}`, `{53FA8D4x-…}`); unregistered, MFC throws and then frees a bad pointer. | `tools/register_activeskin.ps1`: runs the OCX's own `DllRegisterServer` in a 32-bit process with HKCR → `HKCU\Software\Classes` and HKLM → HKCU (`RegOverridePredefKey`). HKLM is needed because the ScriptPlugins object writes `HKLM\Software\SoftShape\ActiveSkin\ScriptPlugins` directly and fails registration otherwise. Nothing is written to HKLM. |
| Random heap crashes during `InitAppResources` (`0xC0000005` in ntdll heap, or `CMemoryException` on tiny allocations) | Heap overflow: the separately built Dx7Api library (`Z:\src\Dx7Api`) allocates the "DxGfx" logger with a stale `sizeof` of 0x20 (`push 0x20` at VA 0x551775); the logger class is 0x24 bytes and its constructor (0x5266b0) writes +0x20. | `aoa/client/base.py`: `push 0x20` → `push 0x24`. |
| Occasional crash writing 0x10023 in a worker thread | Logger (0x526d00) is not thread-safe: per line it does fopen/fwrite/fclose and stores `(FILE*)0xFFFF`, so a concurrent thread can `fwrite(0xFFFF)`; the formatter it uses (0x527210) `vsprintf`s into one global buffer. | `aoa/client/base.py`: both functions wrapped in a recursive spinlock in the `.text` padding (0x58B200), using only imports the client already has. |

The overflow was located with `aoa/live/crashdbg.py --guard-heap`, which serves
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
file offset `0x1C5C60`; its standalone command line and `--undo` no longer
exist.
The subsequent user-operated run reached Station with Play Online. A separate
Play failure was traced to the stub's
nonexistent backdrop and corrected by advertising bundled assets. A local
run now reaches the in-game briefing; world/spawn state and stability remain
unfinished. See `docs/research/findings.md` sections 9.4–9.5 for evidence and limits.

### Local arena physics: zero-time updates

The original 2.9.2 physics code sometimes calculates acceleration with a
zero elapsed-time divisor, producing NaN values that contaminate remote
movement. A live breakpoint confirmed zero time steps; the original
instructions also reproduce the failure in Unicorn. A bounded patched run
recorded no invalid values in 300 samples, versus 38 of 100 before the fix.

The consolidated preparation above includes this guard. The guard skips
physics only when the elapsed time is zero and leaves positive time steps on
the original path. It was first tried as a standalone command
(`aoa/client/patches/physics_timestep.py EXE`, with `--undo`); that command line was
removed on 13 November 2026 and `prepare_client.py` is now the only way to
apply it. This does not implement missing multiplayer gameplay. See
findings 9.10.

### Other leftovers

* `Error (Load Texture) file not found(NavDisplay1.tga)` — likely a
  server-delivered resource; the HUD still renders.
* Many tightly spaced test crashes can make Windows apply the Fault Tolerant
  Heap to that EXE path (`FTH: ... applied` in a debugger); here it was no
  longer applied two hours later. Run crash-loop experiments on fresh copies of
  the game folder so FTH does not change heap behaviour mid-investigation.
