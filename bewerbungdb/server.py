"""Lokaler Webserver (nur Standardbibliothek): liefert die Oberfläche und die JSON-API."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import subprocess
import sys
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, quote, unquote, urlsplit

from . import __version__, generator, library, pdf, templates
from .api import ApiError, fetch_job
from .config import ConfigError, Settings, load_settings
from .links import JOB_ID_RE

STATIC_DIR = Path(__file__).parent / "static"
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.css": "app.css", "/app.js": "app.js"}
COOKIE = "bdb_session"
MAX_BODY = 1_000_000

PROFIL_FIELDS = ["titel", "vorname", "nachname", "email", "telefon", "mobil",
                 "strasse", "hausnummer", "plz", "ort"]


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class Heartbeat:
    """Merkt sich, ob noch ein Fenster offen ist, damit sich die App selbst beenden kann."""

    def __init__(self) -> None:
        self.last_ping: Optional[float] = None
        self.bye_at: Optional[float] = None

    def ping(self) -> None:
        self.last_ping, self.bye_at = time.monotonic(), None

    def bye(self) -> None:
        self.bye_at = time.monotonic()

    def window_gone(self, grace: float = 10, silence: float = 180) -> bool:
        """Fenster geschlossen (bye ohne neuen Ping – ein Neuladen pingt sofort wieder) oder lange still."""
        now = time.monotonic()
        if self.bye_at is not None and now - self.bye_at > grace:
            return True
        return self.last_ping is not None and now - self.last_ping > silence


class FileReply:
    def __init__(self, path: Path, download: bool = False):
        self.path, self.download = path, download


def _existing_info(s: Settings, job_id: str) -> Optional[dict]:
    folder = generator.existing_folder(s, job_id)
    if folder is None:
        return None
    return {"folder": folder.name, "modified": time.strftime("%Y-%m-%dT%H:%M", time.localtime(folder.stat().st_mtime))}


class Request:
    def __init__(self, body: dict, query: dict, groups: tuple):
        self.body, self.query, self.groups = body, query, groups

    @property
    def settings(self) -> Settings:
        try:
            return load_settings()
        except ConfigError as e:
            raise HttpError(500, str(e))


Route = tuple[str, "re.Pattern[str]", Callable[[Request, "App"], object]]


class App:
    """Anwendungslogik: Routen, Sitzungstoken, Heartbeat."""

    def __init__(self, token: Optional[str] = None, heartbeat: Optional[Heartbeat] = None):
        self.token = token or secrets.token_urlsafe(32)
        self.ipc_secret = secrets.token_urlsafe(32)  # nur für andere Prozesse des Nutzers (bewerbungdb://-Links)
        self.on_open: Optional[Callable[[Optional[str]], None]] = None
        self.heartbeat = heartbeat or Heartbeat()
        self.routes: list[Route] = []
        self._register()
        try:
            templates.ensure_defaults(load_settings())
        except Exception:
            pass  # nicht kritisch; die Einstellungen zeigen fehlende Vorlagen an

    def route(self, method: str, pattern: str):
        def deco(fn):
            self.routes.append((method, re.compile(f"^{pattern}$"), fn))
            return fn
        return deco

    def dispatch(self, method: str, path: str, query: dict, body: dict):
        matched_path = False
        for m, rx, fn in self.routes:
            hit = rx.match(path)
            if hit:
                matched_path = True
                if m == method:
                    return fn(Request(body, query, tuple(unquote(g) for g in hit.groups())), self)
        raise HttpError(405 if matched_path else 404, "Nicht gefunden")

    # ── Routen ───────────────────────────────────────────────────────────────
    def _register(self) -> None:
        r = self.route

        @r("POST", "/api/ping")
        def ping(req, app):
            app.heartbeat.ping()
            return {"ok": True}

        @r("POST", "/api/bye")
        def bye(req, app):
            app.heartbeat.bye()
            return {"ok": True}

        @r("POST", "/api/test-connection")
        def test_connection(req, app):
            """Adresse und Schlüssel prüfen, ohne zu speichern (leerer Schlüssel = gespeicherten nehmen)."""
            s = req.settings
            url = (req.body.get("api_base_url") or s.api_url).strip()
            key = (req.body.get("api_key") or "").strip() or s.api_key
            try:
                fetch_job(url, "0", key)
            except ApiError as e:
                # Jede Antwort ausser 401 (und Verbindungsfehlern) heisst: Server erreichbar, Schlüssel akzeptiert.
                if e.status is not None and e.status != 401:
                    return {"ok": True, "message": "Verbindung erfolgreich."}
                return {"ok": False, "message": str(e)}
            return {"ok": True, "message": "Verbindung erfolgreich."}

        @r("GET", "/api/status")
        def status(req, app):
            s = req.settings
            soffice = pdf.find_libreoffice(s.libreoffice_path)
            p = s.profil
            return {
                "version": __version__,
                "libreoffice": bool(soffice),
                "api_key_set": bool(s.api_key),
                "api_url": s.api_url,
                "templates": {t: generator.find_blueprint(t, s.vorlagen_dir) is not None for t in generator.TYPES},
                "profil_complete": bool(p.get("vorname") and p.get("nachname") and p.get("email")),
                "first_run": not (s.api_key and p.get("vorname") and p.get("nachname")),
                "arbeitsordner": str(s.arbeitsordner),
                "vorlagen_ordner": str(s.vorlagen_dir),
            }

        @r("GET", "/api/profil")
        def get_profil(req, app):
            return {k: str(req.settings.profil.get(k) or "") for k in PROFIL_FIELDS}

        @r("PUT", "/api/profil")
        def put_profil(req, app):
            values = req.body.get("values")
            if not isinstance(values, dict):
                raise HttpError(400, "Ungültige Eingabe.")
            req.settings.save_profil({k: str(v).strip() for k, v in values.items() if k in PROFIL_FIELDS})
            return {"ok": True}

        @r("GET", "/api/config")  # der API-Schlüssel wird nie zurückgegeben
        def get_config(req, app):
            c = req.settings.config
            return {
                "api_base_url": c.get("api_base_url", ""),
                "api_key_set": bool(c.get("api_key")),
                "libreoffice_path": c.get("libreoffice_path", ""),
                "arbeitsordner": c.get("arbeitsordner", ""),
                "vorlagen_pfad": c.get("vorlagen_pfad", ""),
            }

        @r("PUT", "/api/config")
        def put_config(req, app):
            allowed = ("api_base_url", "api_key", "libreoffice_path", "arbeitsordner", "vorlagen_pfad")
            updates = {k: str(v).strip() for k, v in req.body.items() if k in allowed and v is not None}
            if updates.get("api_key") == "":
                updates.pop("api_key")  # leeres Feld = Schlüssel unverändert lassen
            req.settings.save_config(updates)
            return {"ok": True}

        @r("GET", r"/api/jobs/([^/]+)")
        def get_job(req, app):
            s, job_id = req.settings, req.groups[0]
            try:
                job = fetch_job(s.api_url, job_id, s.api_key)
            except ApiError as e:
                raise HttpError(400, str(e))
            return {
                "job_id": job_id,
                "title": job.get("job_name_personalized") or job.get("title") or "",
                "company": job.get("company") or "",
                "location": job.get("location") or "",
                "contact": " ".join(p for p in [job.get("contact_salutation"), job.get("contact_title"),
                                                job.get("contact_first_name"), job.get("contact_last_name")] if p),
                "has_text": bool(job.get("bewerbungstext")),
                "missing": generator.check_missing(s, job),
                "existing": _existing_info(s, job_id),
            }

        @r("POST", "/api/applications")
        def create_application(req, app):
            s = req.settings
            job_id = str(req.body.get("job_id") or "").strip()
            try:
                job = fetch_job(s.api_url, job_id, s.api_key)
            except ApiError as e:
                raise HttpError(400, str(e))
            pdf_only = bool(req.body.get("pdf_only"))
            # Eine bestehende Bewerbung wird nie stillschweigend überschrieben (Word-Dateien können
            # von Hand bearbeitet sein). Nur "PDFs neu erstellen" fasst die Word-Dateien nicht an.
            if not pdf_only and not req.body.get("overwrite") and _existing_info(s, job_id):
                raise HttpError(409, "Für diese Stelle gibt es bereits eine Bewerbung.")
            res = generator.generate(s, job_id, job, req.body.get("types"), pdf_only)
            return {"folder": res.folder, "files": res.files, "errors": res.errors}

        @r("GET", "/api/applications")
        def list_applications(req, app):
            return library.list_applications(req.settings)

        def resolve(s: Settings, folder: str, name: Optional[str] = None) -> Path:
            try:
                return library.resolve_file(s, folder, name)
            except (ValueError, FileNotFoundError):
                raise HttpError(404, "Nicht gefunden")

        @r("GET", r"/api/applications/([^/]+)/files/([^/]+)")
        def get_file(req, app):
            path = resolve(req.settings, req.groups[0], req.groups[1])
            if not path.is_file():
                raise HttpError(404, "Nicht gefunden")
            return FileReply(path, download=req.query.get("download") == "true")

        @r("POST", r"/api/applications/([^/]+)/open")
        def open_folder(req, app):
            """Ordner oder Datei mit dem Standardprogramm öffnen (z. B. Word-Datei bearbeiten)."""
            _open_in_os(resolve(req.settings, req.groups[0], req.query.get("name")))
            return {"ok": True}

        @r("POST", "/api/open-templates")
        def open_templates(req, app):
            d = req.settings.vorlagen_dir
            d.mkdir(parents=True, exist_ok=True)
            _open_in_os(d)
            return {"ok": True}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BewerbungDB"
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # ruhig bleiben; Fehler landen im Log über unsere eigene Behandlung
            pass

        # ── Sicherheit: nur lokaler Host (DNS-Rebinding) + Sitzungs-Cookie (fremde Webseiten) ──
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            return host in ("127.0.0.1", "localhost")

        def _cookie_ok(self) -> bool:
            jar = SimpleCookie(self.headers.get("Cookie") or "")
            return COOKIE in jar and secrets.compare_digest(jar[COOKIE].value, app.token)

        def _send(self, status: int, body: bytes, ctype: str, extra: Optional[dict] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _handle(self) -> None:
            try:
                if not self._host_ok():
                    return self._json(403, {"detail": "Ungültiger Host"})
                parts = urlsplit(self.path)
                path, query = parts.path, {k: v[0] for k, v in parse_qs(parts.query).items()}

                if path == "/ipc/open":
                    return self._ipc_open()

                if not path.startswith("/api/"):
                    name = STATIC_FILES.get(path)
                    if self.command not in ("GET", "HEAD") or name is None:
                        return self._json(404, {"detail": "Nicht gefunden"})
                    extra = {}
                    if name == "index.html":
                        extra["Set-Cookie"] = f"{COOKIE}={app.token}; HttpOnly; SameSite=Strict; Path=/"
                    ctype = (mimetypes.guess_type(name)[0] or "application/octet-stream") + "; charset=utf-8"
                    return self._send(200, (STATIC_DIR / name).read_bytes(), ctype, extra)

                if not self._cookie_ok():
                    return self._json(401, {"detail": "Nicht autorisiert"})

                body: dict = {}
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._json(413, {"detail": "Anfrage zu groß"})
                if length:
                    try:
                        parsed = json.loads(self.rfile.read(length).decode("utf-8"))
                        body = parsed if isinstance(parsed, dict) else {}
                    except ValueError:
                        return self._json(400, {"detail": "Ungültige Eingabe."})

                result = app.dispatch(self.command, path, query, body)
                if isinstance(result, FileReply):
                    return self._send_file(result)
                self._json(200, result)
            except HttpError as e:
                self._json(e.status, {"detail": e.message})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # unerwartet: Nutzer bekommt eine verständliche Meldung, Details ins Log
                import traceback
                traceback.print_exc()
                try:
                    self._json(500, {"detail": f"Unerwarteter Fehler: {e}"})
                except Exception:
                    pass

        def _ipc_open(self) -> None:
            """Ein zweiter App-Start (Klick auf bewerbungdb://-Link) bittet diese Instanz um ein Fenster."""
            secret = self.headers.get("X-Ipc-Secret") or ""
            if self.command != "POST" or not secrets.compare_digest(secret, app.ipc_secret):
                return self._json(403, {"detail": "Nicht erlaubt"})
            try:
                job = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 4096))
                                 .decode("utf-8") or "{}").get("job")
            except ValueError:
                return self._json(400, {"detail": "Ungültige Eingabe."})
            if job is not None and not (isinstance(job, str) and JOB_ID_RE.fullmatch(job)):
                return self._json(400, {"detail": "Ungültige Job-ID."})
            if app.on_open:
                app.on_open(job)
            self._json(200, {"ok": True})

        def _send_file(self, reply: FileReply) -> None:
            path = reply.path
            ctype = "application/pdf" if path.suffix.lower() == ".pdf" else (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            disposition = "attachment" if reply.download else "inline"
            self._send(200, path.read_bytes(), ctype,
                       {"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(path.name)}"})

        do_GET = do_POST = do_PUT = do_HEAD = _handle

    return Handler


def create_server(port: int = 0, token: Optional[str] = None, heartbeat: Optional[Heartbeat] = None,
                  host: str = "127.0.0.1") -> tuple[ThreadingHTTPServer, App]:
    app = App(token, heartbeat)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    server.daemon_threads = True
    return server, app


def _open_in_os(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606 – Pfad wurde vorher auf den Arbeitsordner geprüft
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
