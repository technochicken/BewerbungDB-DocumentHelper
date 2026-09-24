#!/usr/bin/env python3
"""Startet BewerbungDB: lokaler Server + App-Fenster (Edge/Chrome), beendet sich beim Schließen."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path
from urllib.parse import quote

from bewerbungdb.config import find_home


def setup_logging() -> None:
    """Ohne Konsole (pythonw) gibt es kein stdout – alles in eine Logdatei umleiten."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    home = find_home()
    home.mkdir(parents=True, exist_ok=True)
    log = open(home / "bewerbungdb.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    print(f"\n--- Start {time.strftime('%Y-%m-%d %H:%M:%S')} ---")


def find_app_browser() -> str | None:
    """Edge (auf Windows 10/11 vorinstalliert) oder Chrome für ein rahmenloses App-Fenster."""
    roots = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
    for r in rel:
        for root in filter(None, roots):
            p = Path(root) / r
            if p.exists():
                return str(p)
    return None


def open_window(url: str) -> None:
    if os.environ.get("BEWERBUNGDB_NO_WINDOW"):  # für automatisierte Tests
        print(url, flush=True)
        return
    browser = find_app_browser()
    if browser:
        subprocess.Popen([browser, f"--app={url}", "--window-size=1200,820"])
    else:
        webbrowser.open(url)


def warm_up_libreoffice() -> None:
    """LibreOffice-Profil vorbereiten, während der Nutzer noch den Startassistenten ausfüllt."""
    try:
        from bewerbungdb import pdf
        from bewerbungdb.config import load_settings
        from bewerbungdb.templates import DEFAULTS_DIR

        s = load_settings()
        soffice = pdf.find_libreoffice(s.libreoffice_path)
        if soffice:
            pdf.warm_up(soffice, s.home / "lo_profile", DEFAULTS_DIR / "blprnt_Deckblatt.docx")
    except Exception:
        traceback.print_exc()  # nicht kritisch


def show_error(msg: str) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "BewerbungDB", 0x10)
    else:
        print(msg, file=sys.stderr)


def window_url(port: int, job_id: str | None) -> str:
    return f"http://127.0.0.1:{port}/" + (f"?job={quote(job_id)}" if job_id else "")


def main() -> None:
    setup_logging()
    from bewerbungdb import links
    from bewerbungdb.server import Heartbeat, create_server

    # Start über einen bewerbungdb://create-application/<id>-Link (oder normal ohne Argument)
    job_id = links.parse_link(sys.argv[1]) if len(sys.argv) > 1 else None
    if len(sys.argv) > 1 and job_id is None:
        print(f"Ignoriere ungültiges Argument: {sys.argv[1]!r}")

    # Läuft die App schon, dieser Instanz ein neues Fenster überlassen statt einen zweiten Server zu starten.
    if links.send_to_running_instance(job_id):
        return

    heartbeat = Heartbeat()
    server, app = create_server(port=0, heartbeat=heartbeat)  # Port 0 = freien Port wählen
    port = server.server_address[1]
    app.on_open = lambda job: open_window(window_url(port, job))
    links.write_instance(port, app.ipc_secret)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    open_window(window_url(port, job_id))
    threading.Thread(target=warm_up_libreoffice, daemon=True).start()

    # Beenden, sobald das Fenster geschlossen wurde. Ohne Ping in den ersten 2 Minuten
    # (Fenster nie geöffnet) ebenfalls beenden, damit kein Prozess zurückbleibt.
    started = time.monotonic()
    while thread.is_alive():
        time.sleep(1)
        if heartbeat.window_gone():
            break
        if heartbeat.last_ping is None and time.monotonic() - started > 120:
            break
    links.clear_instance(port)
    server.shutdown()
    server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        show_error("BewerbungDB konnte nicht gestartet werden.\n\n"
                   "Details stehen in der Datei bewerbungdb.log im Ordner %APPDATA%\\BewerbungDB.")
        sys.exit(1)
