<#
.SYNOPSIS
  Build a playable Ace of Angels 2.9.2 folder for Windows 10/11 from the original installer.

.DESCRIPTION
  Needs the project Python environment .venv (see docs\play\README.md).

  1. tools\make_install.py      - extract the game payload (installer is never run);
                                  the untouched client is kept as AOACLIENT.EXE.orig
  2. tools\prepare_client.py prepare - stability and compatibility fixes, the Station
                                  and the default options, with an exact-undo backup
  3. tools\register_activeskin.ps1 - register the dialog skin OCX for this user (no admin)
  4. tools\install_wrapper.py   - dgVoodoo2 DirectX 7 wrapper + DPI-aware manifest
                                  (skipped if the default -Wrapper zip is absent;
                                  a -Wrapper path you name must exist)
  5. tools\prepare_client.py prepare and check - record the wrapper and verify

  Then double-click tools\client_launcher.cmd to choose visual options and play.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\setup_game.ps1
#>
param(
    [string]$Installer = "originals\2.9.2\aoa_2.9.2_installer_2.11.1.exe",
    [string]$Dest = "game\2.9.2",
    # dgVoodoo2 release zip; omit or pass "" for native DirectX 7.
    [string]$Wrapper = "originals\wrappers\dgvoodoo2-2.87.5\dgVoodoo2_87_5.zip",
    [string]$Station = "localhost"
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot)
$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing project Python environment: $python. Create it first: py -3.12 -m venv .venv; then $python -m pip install -r requirements.txt (see docs\play\README.md)"
}
if ($Wrapper -and $PSBoundParameters.ContainsKey("Wrapper") -and -not (Test-Path $Wrapper)) {
    throw "Wrapper zip not found: $Wrapper. Fix the path, or pass -Wrapper `"`" for native DirectX 7."
}
# Fall back to where tools\fetch_known_builds.py saves the same installer.
$fetched = "builds\v2.9.2_2004_FamilyGamePack3\aoa-current.exe"
if (-not (Test-Path $Installer) -and -not $PSBoundParameters.ContainsKey("Installer") -and (Test-Path $fetched)) {
    $Installer = $fetched
}
if (-not (Test-Path $Installer)) {
    throw "Installer not found: $Installer. Run: $python -I tools\fetch_known_builds.py builds\  (see docs\play\README.md)"
}

function Invoke-Step([string]$What, [scriptblock]$Cmd) {
    "== $What"
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit $LASTEXITCODE)" }
}

Invoke-Step "extract game files" { & $python -I tools\make_install.py $Installer $Dest }
# Keep the untouched client: the patch tests and tools\verify_local.py read it from here.
Copy-Item (Join-Path $Dest "AOACLIENT.EXE") (Join-Path $Dest "AOACLIENT.EXE.orig")
Invoke-Step "prepare supported client" { & $python -I tools\prepare_client.py prepare (Join-Path $Dest "AOACLIENT.EXE") --station $Station }
Invoke-Step "register ActiveSkin (current user)" {
    & powershell -NoProfile -ExecutionPolicy Bypass -File tools\register_activeskin.ps1 (Join-Path $Dest "ACTIVESKIN.OCX")
}
if ($Wrapper -and (Test-Path $Wrapper)) {
    Invoke-Step "install DirectX 7 wrapper" { & $python -I tools\install_wrapper.py $Wrapper $Dest }
} else {
    "== no wrapper zip found; using native DirectX 7 (exclusive fullscreen)"
    "   For a borderless window, save https://github.com/dege-diosg/dgVoodoo2/releases/download/v2.87.5/dgVoodoo2_87_5.zip"
    "   as $Wrapper, then run: $python -I tools\install_wrapper.py $Wrapper $Dest"
    "   and: $python -I tools\prepare_client.py prepare $(Join-Path $Dest "AOACLIENT.EXE")"
}
foreach ($hive in "HKCU", "HKLM") {
    $layer = Get-ItemProperty "${hive}:\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers" -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty ((Resolve-Path $Dest).Path + "\AOACLIENT.EXE") -ErrorAction SilentlyContinue
    if ($layer) { "WARNING: a compatibility mode ('$layer', $hive) is set on this EXE; it breaks the client. Untick it in Properties > Compatibility." }
}
Invoke-Step "record final configuration" { & $python -I tools\prepare_client.py prepare (Join-Path $Dest "AOACLIENT.EXE") --station $Station }
Invoke-Step "verify prepared client" { & $python -I tools\prepare_client.py check (Join-Path $Dest "AOACLIENT.EXE") }
"Done. Double-click tools\client_launcher.cmd to choose visual options and play."
