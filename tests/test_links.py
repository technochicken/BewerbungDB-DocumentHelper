import http.client
import json
import threading

import pytest

from bewerbungdb import links
from bewerbungdb.server import create_server


@pytest.mark.parametrize("arg,expected", [
    ("bewerbungdb://create-application/c876474e3c", "c876474e3c"),
    ("bewerbungdb://create-application/c876474e3c/", "c876474e3c"),
    ('"bewerbungdb://create-application/42"', "42"),
    ("BewerbungDB://Create-Application/AB-12_cd", "AB-12_cd"),
    ("bewerbungdb:create-application/42", "42"),
    ("bewerbungdb:///create-application/42?x=1#y", "42"),
])
def test_valid_links(arg, expected):
    assert links.parse_link(arg) == expected


@pytest.mark.parametrize("arg", [
    "", "http://create-application/42", "bewerbungdb://create-application/", "bewerbungdb://create-application",
    "bewerbungdb://other/42", "bewerbungdb://create-application/../etc", "bewerbungdb://create-application/a b",
    "bewerbungdb://create-application/42/extra", "bewerbungdb://create-application/" + "x" * 65,
    "bewerbungdb://create-application/<script>", "bewerbungdb://create-application/4%2f2",
])
def test_invalid_links(arg):
    assert links.parse_link(arg) is None


@pytest.fixture()
def instance(tmp_path, monkeypatch):
    monkeypatch.setenv("BEWERBUNGDB_HOME", str(tmp_path))
    server, app = create_server(port=0)
    opened = []
    app.on_open = opened.append
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    links.write_instance(port, app.ipc_secret)
    yield port, app, opened
    server.shutdown()
    server.server_close()


def test_running_instance_receives_link(instance):
    _, _, opened = instance
    assert links.send_to_running_instance("c876474e3c") is True
    assert links.send_to_running_instance(None) is True
    assert opened == ["c876474e3c", None]


def test_no_instance_file_means_not_running(tmp_path, monkeypatch):
    monkeypatch.setenv("BEWERBUNGDB_HOME", str(tmp_path))
    assert links.send_to_running_instance("42") is False


def test_stale_instance_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("BEWERBUNGDB_HOME", str(tmp_path))
    links.write_instance(1, "x")  # nichts hört auf Port 1
    assert links.send_to_running_instance("42") is False


def _post(port, headers, body):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("POST", "/ipc/open", json.dumps(body), {"Content-Type": "application/json", **headers})
    r = c.getresponse(); r.read(); c.close()
    return r.status


def test_ipc_rejects_wrong_secret_and_bad_ids(instance):
    port, app, opened = instance
    assert _post(port, {}, {"job": "42"}) == 403
    assert _post(port, {"X-Ipc-Secret": "falsch"}, {"job": "42"}) == 403
    assert _post(port, {"X-Ipc-Secret": app.ipc_secret}, {"job": "../x"}) == 400
    assert opened == []
    assert _post(port, {"X-Ipc-Secret": app.ipc_secret}, {"job": "42"}) == 200
    assert opened == ["42"]


def test_clear_instance_only_removes_own_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("BEWERBUNGDB_HOME", str(tmp_path))
    links.write_instance(5, "s")
    links.clear_instance(6)
    assert links.instance_file().exists()
    links.clear_instance(5)
    assert not links.instance_file().exists()
