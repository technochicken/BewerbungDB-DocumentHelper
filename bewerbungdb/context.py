"""Aus Job-Daten und Profil den Platzhalter-Kontext für die Vorlagen bauen."""

from __future__ import annotations

import datetime
import re
from typing import Optional


def format_datum(raw: Optional[str]) -> str:
    if not raw:
        return datetime.date.today().strftime("%d.%m.%Y")
    try:
        return datetime.date.fromisoformat(str(raw)[:10]).strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        return str(raw)


def safe_name(s: str, max_len: int = 40) -> str:
    for src, dst in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"),
                     ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")]:
        s = s.replace(src, dst)
    s = re.sub(r'[\\/:*?"<>|&%$§#~+\-–(),;.!\']', "", s)
    s = s.replace(" ", "_")
    s = re.sub(r"_+", "_", s)
    return s.strip("_")[:max_len].strip("_")


def build_context(job: dict, profil: dict) -> dict:
    title      = job.get("title") or ""
    company    = job.get("company") or ""
    salutation = job.get("contact_salutation") or ""
    c_title    = job.get("contact_title") or ""
    first_name = job.get("contact_first_name") or ""
    last_name  = job.get("contact_last_name") or ""
    street     = job.get("contact_street") or ""
    street_nr  = job.get("contact_street_nr") or ""
    plz        = job.get("contact_plz") or ""
    city       = job.get("contact_city") or ""

    stelle_adresse = f"{street} {street_nr}".strip()
    stelle_adresse_komplett = (
        f"{stelle_adresse}\n{plz} {city}".strip() if (plz or city) else stelle_adresse
    )

    ansprechpartner_full = " ".join(p for p in [salutation, c_title, last_name] if p)
    adressierungsfloskel = "Sehr geehrter" if salutation == "Herr" else "Sehr geehrte"

    if last_name:
        anrede_titel = f"{c_title} {last_name}".strip() if c_title else last_name
        if salutation:
            anrede = f"{adressierungsfloskel} {salutation} {anrede_titel},"
        else:
            anrede = f"{adressierungsfloskel} {anrede_titel},"
    else:
        anrede = "Sehr geehrte Damen und Herren,"

    vorname  = profil.get("vorname") or ""
    nachname = profil.get("nachname") or ""
    p_titel  = profil.get("titel") or ""
    name = " ".join(p for p in [p_titel, vorname, nachname] if p)

    p_strasse    = profil.get("strasse") or ""
    p_hausnummer = profil.get("hausnummer") or ""
    p_plz        = profil.get("plz") or ""
    p_ort        = profil.get("ort") or ""
    profil_adresse = f"{p_strasse} {p_hausnummer}, {p_plz} {p_ort}".strip(", ")

    skills_raw          = profil.get("skills") or []
    sprachen_raw        = profil.get("sprachen") or []
    hobbys_raw          = profil.get("hobbys") or []

    skills_text = ", ".join(s.get("name", "") for s in skills_raw if s.get("name"))
    sprachen_text = ", ".join(
        f"{s.get('sprache', '')} ({s.get('niveau', '')})"
        for s in sprachen_raw if s.get("sprache")
    )
    hobbys_text = ", ".join(h if isinstance(h, str) else h.get("name", "") for h in hobbys_raw)

    return {
        # Stelle
        "jobtitel":                title,
        "arbeitgeber":             company,
        "bereinigter_jobtitel":    job.get("job_name_personalized") or title,
        "firma":                   company,
        "firmen_floskel":          job.get("company_floskel") or f"bei {company}",
        "stelle_strasse":          street,
        "stelle_hausnummer":       street_nr,
        "stelle_plz":              plz,
        "stelle_ort":              city,
        "stelle_adresse":          stelle_adresse,
        "stelle_adresse_komplett": stelle_adresse_komplett,
        # Ansprechpartner
        "ansprechpartner":            ansprechpartner_full,
        "ansprechpartner_formatiert": last_name,
        "ansprechpartner_vorname":    first_name,
        "ansprechpartner_nachname":   last_name,
        "ansprechpartner_anrede":     salutation,
        "ansprechpartner_email":      job.get("contact_email") or "",
        "ap_anrede":                  salutation,
        "adressierungsfloskel":       adressierungsfloskel,
        "begruessung_floskel":        adressierungsfloskel,
        "anrede":                     anrede,
        # Bewerbung
        "anschreiben": job.get("bewerbungstext") or "",
        "datum":       format_datum(job.get("application_date")),
        # Profil
        "name":                  name,
        "vorname":               vorname,
        "nachname":              nachname,
        "titel":                 p_titel,
        "geburtsdatum":          profil.get("geburtsdatum") or "",
        "nationalitaet":         profil.get("nationalitaet") or "",
        "berufsbezeichnung":     profil.get("berufsbezeichnung") or "",
        "berufserfahrung_jahre": str(profil.get("berufserfahrung_jahre") or ""),
        "zusammenfassung":       profil.get("zusammenfassung") or "",
        "email":    profil.get("email") or "",
        "telefon":  profil.get("telefon") or "",
        "mobil":    profil.get("mobil") or "",
        "linkedin": profil.get("linkedin") or "",
        "xing":     profil.get("xing") or "",
        "website":  profil.get("website") or "",
        "github":   profil.get("github") or "",
        "profil_strasse":    p_strasse,
        "profil_hausnummer": p_hausnummer,
        "profil_plz":        p_plz,
        "profil_ort":        p_ort,
        "profil_adresse":    profil_adresse,
        # Listen für Schleifen in Vorlagen
        "skills":          skills_raw,
        "skills_text":     skills_text,
        "sprachen":        sprachen_raw,
        "sprachen_text":   sprachen_text,
        "ausbildung":      profil.get("ausbildung") or [],
        "berufserfahrung": profil.get("berufserfahrung") or [],
        "zertifikate":     profil.get("zertifikate") or [],
        "hobbys":          hobbys_raw,
        "hobbys_text":     hobbys_text,
    }
