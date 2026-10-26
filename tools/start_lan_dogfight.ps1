<#
.SYNOPSIS
Start the private LAN or VPN dogfight relay. Does not change firewall or client files.
.DESCRIPTION
-Vpn selects the vpn-dogfight profile for players who reach this PC through a
private VPN such as Tailscale, ZeroTier or WireGuard (see docs/vpn-dogfight.md).
The host reads console commands (status, kick, ban, end, help) and rewrites
work/<profile>-status.json every two seconds. -TestRttMs/-TestJitterMs/
-TestLossPercent add artificial delay and loss for testing only.
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -HostAddress 192.168.1.55
.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lan_dogfight.ps1 -Vpn -HostAddress 100.101.102.103 -MaxPlayers 4
#>
param(
    [Parameter(Mandatory = $true)][string]$HostAddress,
    [switch]$Vpn,
    [ValidateRange(1, 8)][int]$MaxPlayers = 2,
    [ValidateSet('CTF_arena', 'Arena1a')][string]$Map = 'CTF_arena',
    [ValidateSet('spacebkgd', 'spacebkgd2', 'spacebkgd3', 'spacebkgd5', 'spacebkgd6')][string]$Backdrop = 'spacebkgd3',
    [switch]$Terrain,
    [ValidateRange(0, 5000)][double]$TestRttMs = 0,
    [ValidateRange(0, 5000)][double]$TestJitterMs = 0,
    [ValidateRange(0, 50)][double]$TestLossPercent = 0,
    [ValidateRange(0, 10)][int]$MaxRestarts = 3,
    [string]$Key = "game/2.9.2/SCRTY.BIN",
    [string]$Log = "",
    [switch]$PrintConfig
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$profileName = if ($Vpn) { "vpn-dogfight" } else { "lan-dogfight" }
if (-not $Log) { $Log = "work/$profileName.jsonl" }
$status = "work/$profileName-status.json"
Push-Location $repoRoot
try {
    $python = Join-Path $repoRoot ".venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Missing project Python environment: $python"
    }
    $serverArgs = @("-I", "tools/station_stub.py", $Key, $Log, "--profile", $profileName,
                    "--bind-address", $HostAddress, "--max-players", "$MaxPlayers", "--map", $Map, "--backdrop", $Backdrop,
                    "--console", "--status-file", $status)
    if ($Terrain) { $serverArgs += "--experimental-terrain" }
    $testing = $TestRttMs -or $TestJitterMs -or $TestLossPercent
    if ($testing) {
        $serverArgs += @("--impair-rtt-ms", "$TestRttMs", "--impair-jitter-ms", "$TestJitterMs", "--impair-loss", "$TestLossPercent")
    }
    # Validation has no socket, log, key-file or client side effects.
    $config = & $python @serverArgs --print-config
    if ($LASTEXITCODE -ne 0) { throw "Invalid $profileName host configuration." }
    if ($PrintConfig) {
        $config
        return
    }
    $address = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
               Where-Object { $_.IPAddress -eq $HostAddress -and $_.AddressState -eq "Preferred" } |
               Select-Object -First 1
    if (-not $address) {
        throw "$HostAddress is not a preferred IPv4 address on this PC. Check ipconfig (or the VPN app)."
    }
    if (-not (Test-Path -LiteralPath $Key -PathType Leaf)) { throw "Missing game key: $Key" }
    $logDirectory = Split-Path ([System.IO.Path]::GetFullPath($Log)) -Parent
    [System.IO.Directory]::CreateDirectory($logDirectory) | Out-Null
    $alias = if ($Vpn) { "aoavpn" } else { "aoalan" }
    Write-Host "$(if ($Vpn) { 'VPN' } else { 'LAN' }) Dogfight: $HostAddress on adapter '$($address.InterfaceAlias)' | up to $MaxPlayers players (capacity requires testing)"
    Write-Host "Map: $Map$(if ($Terrain) { ' with Arena1a terrain' }) | Backdrop: $Backdrop"
    if ($Map -eq 'Arena1a') { Write-Host "Arena1a validation build: see docs/arena1a.md for unresolved nodes and gameplay." }
    Write-Host "UDP 5033 + 5031; TCP 5034. Firewall rules: docs/$(if ($Vpn) { 'vpn' } else { 'lan' })-dogfight.md"
    Write-Host "Each client hosts-file entry: $HostAddress $alias"
    Write-Host "Prepare each client for Station $alias; use dummy login values."
    if ($Vpn) {
        Write-Host "Sustained delivery is on: players can rejoin after a crash or dropout (49 joins per host run)."
    } else {
        Write-Host "Restart host and clients for reconnects."
    }
    Write-Host "20 kills / 10 minutes; score reset only. Status: $status"
    if ($testing) { Write-Host "TEST IMPAIRMENT ON: do not use this host for normal play." -ForegroundColor Yellow }
    Write-Host "Type 'help' for host commands. Ctrl+C stops the host."
    $starts = @()
    while ($true) {
        $starts = @($starts | Where-Object { $_ -gt (Get-Date).AddMinutes(-10) }) + (Get-Date)
        & $python @serverArgs
        $code = $LASTEXITCODE
        if ($code -eq 0) { break }
        if ($starts.Count -gt $MaxRestarts) {
            throw "Host stopped with exit code $code; $MaxRestarts restarts in 10 minutes already used."
        }
        Write-Host "Host stopped with exit code $code. Restarting in 5 seconds; players must rejoin." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
} finally {
    Pop-Location
}
