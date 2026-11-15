<#
.SYNOPSIS
Start the private LAN or VPN dogfight relay. Does not change firewall or client files.
.DESCRIPTION
A wrapper around tools/aoa_host.py run (the headless host; see docs/lan-dogfight.md).
-Vpn selects the vpn-dogfight profile for players who reach this PC through a
private VPN such as Tailscale, ZeroTier or WireGuard (see docs/vpn-dogfight.md).
The host reads console commands (status, kick <slot>, ban <slot>, end,
say <text>, quit, help) and rewrites work/host/<profile>-status.json every
two seconds, the file the host window uses. A crashed host restarts up to 3
times in 10 minutes. -TestRttMs/-TestJitterMs/-TestLossPercent add artificial
delay and loss for testing only. -PrintConfig validates and prints the settings.
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.1.55
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -Vpn -HostAddress 100.101.102.103 -MaxPlayers 4
#>
param(
    [Parameter(Mandatory = $true)][string]$HostAddress,
    [switch]$Vpn,
    [ValidateRange(1, 8)][int]$MaxPlayers = 2,
    # Any map the server accepts; aoa_host.py rejects unknown names.
    [string]$Map = 'CTF_arena',
    [string]$Backdrop = 'spacebkgd3',
    [switch]$Terrain,
    [ValidateRange(0, 5000)][double]$TestRttMs = 0,
    [ValidateRange(0, 5000)][double]$TestJitterMs = 0,
    [ValidateRange(0, 50)][double]$TestLossPercent = 0,
    [switch]$PrintConfig
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $repoRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Missing project Python environment: $python" }
$hostArgs = @(if ($PrintConfig) { "check" } else { "run" })
$hostArgs += @("--profile", $(if ($Vpn) { "vpn-dogfight" } else { "lan-dogfight" }), "--bind-address", $HostAddress,
               "--max-players", "$MaxPlayers", "--map", $Map, "--backdrop", $Backdrop, "--console")
if ($Terrain) { $hostArgs += "--terrain" }
if ($TestRttMs -or $TestJitterMs -or $TestLossPercent) {
    $hostArgs += @("--", "--impair-rtt-ms", "$TestRttMs", "--impair-jitter-ms", "$TestJitterMs", "--impair-loss", "$TestLossPercent")
}
Push-Location $repoRoot
try {
    & $python -I tools/aoa_host.py @hostArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
