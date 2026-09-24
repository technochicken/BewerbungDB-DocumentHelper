"""Bestehende Bewerbungen dürfen nie stillschweigend überschrieben werden."""

import json

import pytest

from bewerbungdb import generator, library
from bewerbungdb.config import load_settings
from tests.test_server import Client, running  # noqa: F401  (Fixture + Hilfsklasse wiederverwenden)

JOB = {"title": "Tester", "company": "ACME", "location": "Ulm", "bewerbungstext": "Text"}


@pytest.fixture()
def client(running, monkeypatch):  # noqa: F811
    calls = []
    monkeypatch.setattr("bewerbungdb.server.fetch_job", lambda url, jid, key="": dict(JOB))
    monkeypatch.setattr(generator, "generate",
                        lambda s, jid, job, types=None, pdf_only=False: calls.append((jid, types, pdf_only))
                        or generator.GenerationResult(folder="x"))
    c = Client(running[0]).open()
    c.calls = calls
    return c


def make_existing(job_id="c876474e3c"):
    s = load_settings()
    d = s.arbeitsordner / "ACME_Tester"
    d.mkdir(parents=True)
    (d / generator.JOB_FILE).write_text(json.dumps({"job_id": job_id, "job": JOB}), encoding="utf-8")
    (d / "Deckblatt_Tester_Max.docx").write_bytes(b"x")
    return d


def test_new_job_is_created_without_overwrite_flag(client):
    assert client.call("POST", "/api/applications", {"job_id": "c876474e3c"})[0] == 200
    assert len(client.calls) == 1


def test_existing_job_is_refused_without_overwrite(client):
    make_existing()
    status, body, _ = client.call("POST", "/api/applications", {"job_id": "c876474e3c"})
    assert status == 409 and "bereits" in body["detail"]
    assert client.calls == []          # es wurde nichts erzeugt


def test_overwrite_flag_allows_regeneration(client):
    make_existing()
    assert client.call("POST", "/api/applications", {"job_id": "c876474e3c", "overwrite": True})[0] == 200
    assert client.calls == [("c876474e3c", None, False)]


def test_single_document_regeneration_passes_type(client):
    make_existing()
    client.call("POST", "/api/applications", {"job_id": "c876474e3c", "types": ["Anschreiben"], "overwrite": True})
    assert client.calls == [("c876474e3c", ["Anschreiben"], False)]


def test_pdf_only_never_needs_confirmation(client):
    make_existing()
    assert client.call("POST", "/api/applications", {"job_id": "c876474e3c", "pdf_only": True})[0] == 200


def test_job_info_reports_existing_application(client):
    assert client.call("GET", "/api/jobs/c876474e3c")[1]["existing"] is None
    make_existing()
    existing = client.call("GET", "/api/jobs/c876474e3c")[1]["existing"]
    assert existing["folder"] == "ACME_Tester" and existing["modified"]
    assert client.call("GET", "/api/jobs/other")[1]["existing"] is None


def test_library_lists_files_in_sensible_order(client):
    d = make_existing()
    for name in ("Email_T.eml", "Lebenslauf_T.pdf", "Lebenslauf_T.docx", "Bewerbung_T.pdf", "Anschreiben_T.pdf",
                 "Anschreiben_T.docx", "Deckblatt_Anschreiben_T.pdf"):
        (d / name).write_bytes(b"x")
    names = [f["name"] for f in library.list_applications(load_settings())[0]["files"]]
    assert names == ["Bewerbung_T.pdf", "Deckblatt_Anschreiben_T.pdf", "Deckblatt_Tester_Max.docx",
                     "Anschreiben_T.docx", "Anschreiben_T.pdf", "Lebenslauf_T.docx", "Lebenslauf_T.pdf", "Email_T.eml"]


def test_library_marks_single_word_documents(client):
    d = make_existing()
    for name in ("Anschreiben_T_M.docx", "Deckblatt_Anschreiben_T_M.pdf", "Bewerbung_T_M.pdf", "Email_T_M.eml"):
        (d / name).write_bytes(b"x")
    files = {f["name"]: f["type"] for f in library.list_applications(load_settings())[0]["files"]}
    assert files["Anschreiben_T_M.docx"] == "Anschreiben"
    assert files["Deckblatt_T_M.docx" if "Deckblatt_T_M.docx" in files else "Deckblatt_Tester_Max.docx"] == "Deckblatt"
    assert files["Deckblatt_Anschreiben_T_M.pdf"] is None and files["Bewerbung_T_M.pdf"] is None
    assert files["Email_T_M.eml"] is None
