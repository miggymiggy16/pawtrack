<#
PawTrack - publish the local app with Tailscale Funnel (free HTTPS link)
=======================================================================
Run this AFTER `python app.py` is already running in another window.

    powershell -ExecutionPolicy Bypass -File scripts\funnel.ps1

What it does
------------
1. Checks Tailscale is installed and signed in.
2. Points a public https://<machine>.<tailnet>.ts.net address at PawTrack.
3. Prints the public URL.

One-time setup in the Tailscale admin console
---------------------------------------------
https://login.tailscale.com/admin/dns
  - Enable MagicDNS
  - Enable HTTPS Certificates

Turn it off again with:
    & "C:\Program Files\Tailscale\tailscale.exe" funnel reset
#>
param(
    [int]$Port = 5000,
    [string]$Target = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$ts = "C:\Program Files\Tailscale\tailscale.exe"
if (-not (Test-Path $ts)) {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) {
        $ts = $cmd.Source
    } else {
        Write-Host "Tailscale is not installed." -ForegroundColor Yellow
        Write-Host "Install it once, then run this script again:"
        Write-Host "  winget install --id Tailscale.Tailscale -e"
        exit 1
    }
}

& $ts status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tailscale is installed but not connected." -ForegroundColor Yellow
    Write-Host "Open the Tailscale app from the system tray and sign in, then retry."
    exit 1
}

if (-not $Target) {
    $https = $false
    if (Test-Path ".env") {
        $https = [bool](Select-String -Path ".env" -Pattern '^\s*PAWTRACK_HTTPS\s*=\s*(True|1|yes|on)\s*$' -Quiet)
    }
    # With local HTTPS on, Funnel must skip certificate checks on the loopback hop.
    if ($https) { $Target = "https+insecure://127.0.0.1:$Port" } else { $Target = "http://127.0.0.1:$Port" }
}

Write-Host "Publishing $Target ..."
& $ts funnel --bg --https=443 $Target
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Funnel did not start. The usual cause is that HTTPS certificates are off." -ForegroundColor Yellow
    Write-Host "Open https://login.tailscale.com/admin/dns and enable:"
    Write-Host "  - MagicDNS"
    Write-Host "  - HTTPS Certificates"
    Write-Host "then run this script again."
    exit 1
}

Write-Host ""
& $ts funnel status
Write-Host ""
Write-Host "Public link: the https://...ts.net address shown above."
Write-Host "Stop sharing with:  `"$ts`" funnel reset"
