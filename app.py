"""
PawTrack - application entry point
=================================
The application itself lives in the ``pawtrack`` package. This file only starts
the server, so it can still be run exactly as before:

    python app.py

Public HTTPS is provided by a tunnel (Tailscale Funnel, ngrok, ...); PawTrack
itself always serves plain HTTP behind it. Configure the tunnel in .env:

    PAWTRACK_HOST=127.0.0.1      # only the tunnel can reach the app
    PAWTRACK_WSGI=waitress       # production-style server, no dev warnings
    PAWTRACK_GATE_USER=...       # optional shared password in front of login
    PAWTRACK_GATE_PASSWORD=...

Then run ``scripts/funnel.ps1`` (Tailscale) and open the https:// URL it prints.
"""
import os

from pawtrack import app


if __name__ == "__main__":
    host = os.getenv("PAWTRACK_HOST", "0.0.0.0")
    port = int(os.getenv("PAWTRACK_PORT", "5000"))
    print(f"[PawTrack] HTTP on http://{host}:{port} (put a tunnel in front for public HTTPS)")

    server = os.getenv("PAWTRACK_WSGI", "").strip().lower()
    if server == "waitress":
        from waitress import serve
        threads = int(os.getenv("PAWTRACK_THREADS", "8"))
        print(f"[PawTrack] waitress: {threads} worker threads")
        serve(app, host=host, port=port, threads=threads)
    else:
        app.run(host=host, port=port, debug=True, threaded=True)
