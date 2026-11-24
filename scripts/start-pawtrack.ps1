# PawTrack - auto-start helper (runs at Windows logon via the "PawTrack App" scheduled task)
# Waits for MariaDB to answer on 3306, then starts the app with no console window.
# Logs app output to pawtrack.log.

Set-Location "C:\Users\Juan Miguel\Documents\pawtrack backup\PawTrack"

for ($i = 0; $i -lt 90; $i++) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $tcp.Connect('127.0.0.1', 3306)
        if ($tcp.Connected) { break }
    } catch {
        Start-Sleep -Seconds 2
    } finally {
        $tcp.Close()
    }
}

if (-not $tcp.Connected) {
    Add-Content "C:\Users\Juan Miguel\Documents\pawtrack backup\PawTrack\pawtrack.log" `
        "$(Get-Date -Format s) MariaDB did not answer on 127.0.0.1:3306; starting anyway"
}

& .\venv\Scripts\pythonw.exe app.py *>> "C:\Users\Juan Miguel\Documents\pawtrack backup\PawTrack\pawtrack.log"
