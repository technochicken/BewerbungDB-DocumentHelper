"""End-to-End-Test der Dokumentenerzeugung mit einer Fake-Stelle (ohne Netzwerk)."""

from pathlib import Path

import pytest

from bewerbungdb import generator, library, pdf
from bewerbungdb.config import Settings

TEMPLATES = Path(__file__).resolve().parent.parent / "Vorlagen"

JOB = {
    "title": "Softwareentwickler (m/w/d)", "company": "Beispiel & Söhne GmbH", "location": "Stuttgart",
    "contact_salutation": "Frau", "contact_last_name": "Müller", "contact_email": "mueller@example.com",
    "bewerbungstext": "Sehr geehrte Frau Müller,\n\nich bewerbe mich <hiermit> & gerne.\n\nMit freundlichen Grüßen",
}
PROFIL = {"vorname": "Max", "nachname": "Mustermann", "email": "max@example.com"}


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        home=tmp_path,
        config={"vorlagen_pfad": str(TEMPLATES), "arbeitsordner": str(tmp_path / "out"),
                "libreoffice_path": "", "api_base_url": "", "api_key": ""},
        profil=PROFIL,
    )


@pytest.mark.skipif(not TEMPLATES.exists(), reason="keine Vorlagen vorhanden")
@pytest.mark.skipif(pdf.find_libreoffice() is None, reason="LibreOffice nicht installiert")
def test_full_generation_and_library(settings):
    res = generator.generate(settings, "42", JOB)
    assert res.errors == []
    assert {"Deckblatt (Word)", "Anschreiben (Word)", "Lebenslauf (Word)", "Vollständige Bewerbung",
            "Deckblatt + Anschreiben", "E-Mail-Entwurf"} <= set(res.files)

    folder = settings.arbeitsordner / res.folder
    for name in res.files.values():
        assert (folder / name).stat().st_size > 0

    apps = library.list_applications(settings)
    assert len(apps) == 1 and apps[0]["job_id"] == "42" and apps[0]["company"].startswith("Beispiel")

    # Zweiter Lauf verwendet denselben Ordner (keine Duplikate)
    generator.generate(settings, "42", JOB, pdf_only=True)
    assert len(library.list_applications(settings)) == 1
