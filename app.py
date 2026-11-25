"""PawTrack server entry point. Run with: python app.py"""
import os

from pawtrack import app

if __name__ == "__main__":
    host = os.getenv("PAWTRACK_HOST", "0.0.0.0")
    port = int(os.getenv("PAWTRACK_PORT", "5000"))
    print(f"[PawTrack] HTTP on http://{host}:{port} (put a tunnel in front for public HTTPS)")

    if os.getenv("PAWTRACK_WSGI", "").strip().lower() == "waitress":
        from waitress import serve
        threads = int(os.getenv("PAWTRACK_THREADS", "8"))
        print(f"[PawTrack] waitress: {threads} worker threads")
        serve(app, host=host, port=port, threads=threads)
    else:
        app.run(host=host, port=port, debug=True, threaded=True)
