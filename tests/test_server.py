"""Tests für Server-Schutz, API und Fensterüberwachung gegen einen echten Server. Ausführen: python -m pytest tests"""

import http.client
import json
import threading

import pytest

from bewerbungdb.server import Heartbeat, create_server


class Client:
    def __init__(self, port, host=None, cookie=None):
        self.port, self.host, self.cookie = port, host or f"127.0.0.1:{port}", cookie

    def call(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": self.host}
        if self.cookie:
            headers["Cookie"] = self.cookie
        data = None
        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, data, headers)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw
        return resp.status, payload, resp

    def open(self):
        """Startseite laden, damit das Sitzungs-Cookie gesetzt wird (wie der Browser)."""
        status, _, resp = self.call("GET", "/")
        assert status == 200
        self.cookie = resp.getheader("Set-Cookie").split(";")[0]
        return self


@pytest.fixture()
def running(tmp_path, monkeypatch):
    monkeypatch.setenv("BEWERBUNGDB_HOME", str(tmp_path))
    hb = Heartbeat()
    server, app = create_server(port=0, token="t", heartbeat=hb)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], hb
    server.shutdown()
    server.server_close()


@pytest.fixture()
def client(running):
    return Client(running[0]).open()


def test_api_requires_cookie(running):
    assert Client(running[0]).call("GET", "/api/status")[0] == 401


def test_wrong_cookie_rejected(running):
    assert Client(running[0], cookie="bdb_session=falsch").call("GET", "/api/status")[0] == 401


def test_foreign_host_rejected(running):
    assert Client(running[0], host="evil.example").call("GET", "/")[0] == 403


def test_only_known_static_files(client):
    assert client.call("GET", "/app.js")[0] == 200
    assert client.call("GET", "/../config.json")[0] == 404
    assert client.call("GET", "/bewerbungdb/server.py")[0] == 404


def test_status_on_fresh_install(client):
    status, body, _ = client.call("GET", "/api/status")
    assert status == 200
    assert body["api_key_set"] is False and body["profil_complete"] is False and body["first_run"] is True


def test_api_key_never_returned(client):
    client.call("PUT", "/api/config", {"api_key": "geheim123"})
    status, body, resp = client.call("GET", "/api/config")
    assert body["api_key_set"] is True
    assert "geheim123" not in json.dumps(body)


def test_blank_key_keeps_existing(client):
    client.call("PUT", "/api/config", {"api_key": "geheim123"})
    client.call("PUT", "/api/config", {"api_key": ""})
    assert client.call("GET", "/api/config")[1]["api_key_set"] is True


def test_profil_roundtrip_and_first_run(client):
    client.call("PUT", "/api/profil", {"values": {"vorname": " Anna ", "nachname": "Muster", "email": "a@b.de"}})
    assert client.call("GET", "/api/profil")[1]["vorname"] == "Anna"
    client.call("PUT", "/api/config", {"api_key": "k"})
    assert client.call("GET", "/api/status")[1]["first_run"] is False


def test_bad_json_and_unknown_route(client):
    assert client.call("GET", "/api/gibtsnicht")[0] == 404
    assert client.call("GET", "/api/ping")[0] == 405


def test_test_connection_rejects_bad_url(client):
    status, body, _ = client.call("POST", "/api/test-connection", {"api_base_url": "file:///etc/passwd"})
    assert status == 200 and body["ok"] is False


def test_path_traversal_blocked(tmp_path, monkeypatch):
    from bewerbungdb import library
    from bewerbungdb.config import load_settings

    monkeypatch.setenv("BEWERBUNGDB_HOME", str(tmp_path))
    s = load_settings()
    (s.arbeitsordner / "ok").mkdir(parents=True)
    (s.arbeitsordner / "ok" / "a.pdf").write_bytes(b"x")
    (tmp_path / "config.json").write_text("{}")  # liegt ausserhalb des Arbeitsordners

    assert library.resolve_file(s, "ok", "a.pdf").name == "a.pdf"
    for folder, name in [("..", "config.json"), ("ok", "../../config.json"), ("../..", None)]:
        with pytest.raises((ValueError, FileNotFoundError)):
            library.resolve_file(s, folder, name)


def test_file_download_and_traversal_via_http(client, tmp_path):
    from bewerbungdb.config import load_settings

    s = load_settings()
    (s.arbeitsordner / "ok").mkdir(parents=True)
    (s.arbeitsordner / "ok" / "Ä b.pdf").write_bytes(b"%PDF-1.4 test")
    status, body, resp = client.call("GET", "/api/applications/ok/files/%C3%84%20b.pdf")
    assert status == 200 and body == b"%PDF-1.4 test" and resp.getheader("Content-Type") == "application/pdf"
    assert client.call("GET", "/api/applications/..%2f/files/config.json")[0] == 404
    assert client.call("GET", "/api/applications/ok/files/..%2f..%2fconfig.json")[0] == 404


def test_heartbeat_lifecycle():
    hb = Heartbeat()
    assert not hb.window_gone()          # noch nie ein Fenster: nicht "gone"
    hb.ping()
    assert not hb.window_gone()
    hb.bye()
    assert not hb.window_gone(grace=10)  # Neuladen-Toleranz
    assert hb.window_gone(grace=0)
    hb.ping()                            # Neuladen pingt sofort wieder
    assert not hb.window_gone(grace=0)
    assert hb.window_gone(silence=-1)    # lange still
