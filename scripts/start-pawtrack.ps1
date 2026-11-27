# PawTrack - auto-start helper
# Runs at Windows logon via the "PawTrack AutoStart" scheduled task.
# Starts XAMPP MySQL (if needed), waits for it, starts the Flask app hidden,
# and makes sure the Tailscale Funnel still points at the app.
# Safe to run manually more than once - it never starts duplicates.
# Output is appended to pawtrack.log.

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$log = Join-Path $root 'pawtrack.log'

function Write-Log([string]$Msg) {
    Add-Content -Path $log -Value "$(Get-Date -Format s) $Msg"
}

function Test-Port([string]$HostName, [int]$Port) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $ok = $tcp.ConnectAsync($HostName, $Port).Wait(1000)
        return ($ok -and $tcp.Connected)
    } catch {
        return $false
    } finally {
        $tcp.Close()
    }
}

# ---------- 1. MySQL / MariaDB ----------
$mysqld = 'C:\xampp\mysql\bin\mysqld.exe'
$myIni  = 'C:\xampp\mysql\bin\my.ini'

if (-not (Test-Port '127.0.0.1' 3306)) {
    Write-Log 'MySQL not listening - starting XAMPP MySQL'
    if (Test-Path $mysqld) {
        Start-Process -FilePath $mysqld `
            -ArgumentList "--defaults-file=`"$myIni`" --standalone" `
            -WorkingDirectory 'C:\xampp\mysql' -WindowStyle Hidden
    } else {
        Write-Log "ERROR: mysqld not found at $mysqld"
    }
} else {
    Write-Log 'MySQL already listening on 3306'
}

$mysqlOk = $false
for ($i = 0; $i -lt 60; $i++) {
    if (Test-Port '127.0.0.1' 3306) { $mysqlOk = $true; break }
    Start-Sleep -Seconds 2
}
if ($mysqlOk) {
    Write-Log 'MySQL is ready'
} else {
    Write-Log 'WARNING: MySQL did not answer on 3306 - starting the app anyway'
}

# ---------- 2. PawTrack Flask app ----------
if (-not (Test-Port '127.0.0.1' 5000)) {
    $py = Join-Path $root 'venv\Scripts\python.exe'
    if (Test-Path $py) {
        Write-Log 'Starting PawTrack app'
        Start-Process -FilePath $py -ArgumentList 'app.py' `
            -WorkingDirectory $root -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $root 'pawtrack.out.log') `
            -RedirectStandardError (Join-Path $root 'pawtrack.err.log')
    } else {
        Write-Log "ERROR: python not found at $py"
    }
} else {
    Write-Log 'PawTrack app already listening on 5000'
}

$appOk = $false
for ($i = 0; $i -lt 30; $i++) {
    if (Test-Port '127.0.0.1' 5000) { $appOk = $true; break }
    Start-Sleep -Seconds 2
}
Write-Log $(if ($appOk) { 'PawTrack app is ready' } else { 'ERROR: PawTrack app did not start' })

# ---------- 3. Tailscale Funnel ----------
$ts = 'C:\Program Files\Tailscale\tailscale.exe'
if (-not (Test-Path $ts)) {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) { $ts = $cmd.Source }
}

if (Test-Path $ts) {
    $target = 'http://127.0.0.1:5000'
    $envFile = Join-Path $root '.env'
    if ((Test-Path $envFile) -and
        (Select-String -Path $envFile -Pattern '^\s*PAWTRACK_HTTPS\s*=\s*(True|1|yes|on)\s*$' -Quiet)) {
        $target = 'https+insecure://127.0.0.1:5000'
    }

    for ($i = 0; $i -lt 15; $i++) {
        $status = & $ts serve status 2>&1
        if ($LASTEXITCODE -eq 0) {
            $text = $status | Out-String
            if (($text -match 'Funnel on') -and ($text -match [regex]::Escape($target))) {
                Write-Log 'Tailscale Funnel already active'
                break
            }
            & $ts funnel --bg --https=443 $target *> $null
            if ($LASTEXITCODE -eq 0) {
                Write-Log "Tailscale Funnel configured for $target"
                break
            }
        }
        Start-Sleep -Seconds 4
    }
} else {
    Write-Log 'Tailscale not installed - skipping Funnel setup'
}

Write-Log 'Auto-start finished'
