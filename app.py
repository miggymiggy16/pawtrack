"""
PawTrack - application entry point
==================================
The application itself lives in the ``pawtrack`` package. This file only starts
the server, so it can still be run exactly as before:

    python app.py

Two ways to expose it, both driven by .env:

1) Local network with HTTPS (camera on phones on the same Wi-Fi):

    PAWTRACK_HTTPS=True
    PAWTRACK_SSL_CERT=certs/pawtrack.crt
    PAWTRACK_SSL_KEY=certs/pawtrack.key

   Create the certificate once with ``python scripts/make_cert.py`` or mkcert.

2) Public link through a tunnel (Tailscale Funnel, ngrok, ...). The tunnel
   terminates HTTPS, so PawTrack itself can stay on plain HTTP behind it:

    PAWTRACK_HTTPS=False
    PAWTRACK_HOST=127.0.0.1      # only the tunnel can reach the app
    PAWTRACK_WSGI=waitress       # production-style server, no dev warnings
    PAWTRACK_GATE_USER=...       # optional shared password in front of login
    PAWTRACK_GATE_PASSWORD=...

   Then run ``scripts/funnel.ps1`` (Tailscale) and open the https:// URL it prints.
"""
import os
from pathlib import Path

from pawtrack import app
from pawtrack.config import BASE_DIR


def _enabled(name):
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _ssl_context():
    """Return (cert, key) when HTTPS is on and both files exist, else None."""
    if not _enabled("PAWTRACK_HTTPS"):
        return None
    cert = Path(os.getenv("PAWTRACK_SSL_CERT", "certs/pawtrack.crt"))
    key = Path(os.getenv("PAWTRACK_SSL_KEY", "certs/pawtrack.key"))
    if not cert.is_absolute():
        cert = BASE_DIR / cert
    if not key.is_absolute():
        key = BASE_DIR / key
    if cert.exists() and key.exists():
        return (str(cert), str(key))
    print("[PawTrack] HTTPS requested but the certificate files are missing.")
    print("[PawTrack] Run: python scripts/make_cert.py")
    return None


if __name__ == "__main__":
    host = os.getenv("PAWTRACK_HOST", "0.0.0.0")
    port = int(os.getenv("PAWTRACK_PORT", "5000"))
    ssl_context = _ssl_context()

    if ssl_context:
        print(f"[PawTrack] HTTPS on https://{host}:{port}")
    else:
        print(f"[PawTrack] HTTP on http://{host}:{port} (put a tunnel in front for public HTTPS)")

    # waitress is a production WSGI server, but it cannot serve TLS itself.
    # Behind a tunnel (Funnel/ngrok) the app is plain HTTP, so waitress fits.
    server = os.getenv("PAWTRACK_WSGI", "").strip().lower()
    if server == "waitress" and not ssl_context:
        from waitress import serve
        threads = int(os.getenv("PAWTRACK_THREADS", "8"))
        print(f"[PawTrack] waitress: {threads} worker threads")
        serve(app, host=host, port=port, threads=threads)
    else:
        if server == "waitress":
            print("[PawTrack] waitress has no TLS support; using the built-in server for HTTPS.")
        # host 0.0.0.0 lets phones on the same Wi-Fi open PawTrack (see README).
        app.run(host=host, port=port, debug=False, threaded=True, ssl_context=ssl_context)
