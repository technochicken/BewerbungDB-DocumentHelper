"""Zugriff auf die BewerbungDB-REST-API (nur Standardbibliothek – schnell zu laden, nichts zu installieren)."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse


class ApiError(RuntimeError):
    """Fehler mit einer für Endnutzer verständlichen Meldung."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def fetch_job(api_base: str, job_id: str, api_key: str = "") -> dict:
    job_id = str(job_id).strip()
    # Buchstaben, Ziffern, - und _ (alte Server: Zahlen, neue: z. B. "c876474e3c"); nichts, was die URL verändern könnte.
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
        raise ApiError("Die Job-ID ist ungültig. Erlaubt sind Buchstaben, Ziffern, - und _.")
    if urlparse(api_base).scheme not in ("http", "https"):
        raise ApiError("Die Adresse der BewerbungDB muss mit https:// beginnen.")

    headers = {"Accept": "application/json", "User-Agent": "BewerbungDB-App"}
    if api_key:
        headers["X-Api-Key"] = api_key
    req = urllib.request.Request(f"{api_base.rstrip('/')}/api/v1/jobs/{job_id}", headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ApiError("Der API-Schlüssel ist ungültig oder fehlt.", 401)
        if e.code == 404:
            raise ApiError(f"Stelle #{job_id} wurde nicht gefunden.", 404)
        raise ApiError(f"Die BewerbungDB meldet einen Fehler (HTTP {e.code}).", e.code)
    except (socket.timeout, TimeoutError):
        raise ApiError("Die BewerbungDB antwortet nicht (Zeitüberschreitung).")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ApiError("Die BewerbungDB antwortet nicht (Zeitüberschreitung).")
        raise ApiError("Keine Verbindung zur BewerbungDB. Bitte Internetverbindung und Adresse prüfen.")
    except (OSError, ValueError):
        raise ApiError("Keine Verbindung zur BewerbungDB. Bitte Internetverbindung und Adresse prüfen.")

    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiError("Ungültige Antwort der BewerbungDB.")
    if not isinstance(data, dict):
        raise ApiError("Ungültige Antwort der BewerbungDB.")
    return data
