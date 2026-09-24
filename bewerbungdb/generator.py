"""Eine Bewerbung erzeugen: Ordner anlegen, DOCX befüllen, PDFs bauen, E-Mail-Entwurf."""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import docx_engine, email_draft, pdf
from .config import Settings
from .context import build_context, safe_name

TYPES = ["Deckblatt", "Anschreiben", "Lebenslauf"]
JOB_FILE = "job.json"


@dataclass
class GenerationResult:
    folder: str
    files: dict[str, str] = field(default_factory=dict)   # Bezeichnung → Dateiname
    errors: list[str] = field(default_factory=list)


def output_suffix(job: dict, profil: dict) -> str:
    parts = [
        safe_name(job.get("job_name_personalized") or job.get("title") or "Bewerbung"),
        safe_name(profil.get("vorname") or ""),
        safe_name(profil.get("nachname") or ""),
    ]
    return "_".join(p for p in parts if p)


def existing_folder(settings: Settings, job_id: str) -> Optional[Path]:
    """Ordner einer bereits erstellten Bewerbung zu dieser Job-ID (oder None)."""
    root = settings.arbeitsordner
    if not root.exists():
        return None
    for d in root.iterdir():
        meta = d / JOB_FILE
        if meta.is_file():
            try:
                if str(json.loads(meta.read_text(encoding="utf-8")).get("job_id")) == str(job_id):
                    return d
            except (OSError, ValueError):
                continue
    return None


def folder_for_job(settings: Settings, job_id: str, job: dict) -> Path:
    """Arbeitsordner der Stelle; existiert bereits einer zur Job-ID, wird er weiterverwendet."""
    found = existing_folder(settings, job_id)
    if found:
        return found
    root = settings.arbeitsordner
    name = "_".join(p for p in [
        safe_name(job.get("company") or "Unbekannt", 30),
        safe_name(job.get("job_name_personalized") or job.get("title") or "Stelle"),
    ] if p)
    candidate = root / name
    if candidate.exists():  # anderer Job mit gleichem Namen
        candidate = root / f"{name}_{job_id}"
    return candidate


def find_blueprint(typ: str, *dirs: Optional[Path]) -> Optional[Path]:
    for d in dirs:
        if not d or not d.exists():
            continue
        for match in sorted(d.glob(f"blprnt*{typ}*.docx")):
            try:
                if docx_engine.get_template_variables(match):  # schon gefüllte Dateien überspringen
                    return match
            except Exception:
                continue
    return None


def check_missing(settings: Settings, job: dict) -> dict[str, list[str]]:
    context = build_context(job, settings.profil)
    missing: dict[str, list[str]] = {}
    for typ in TYPES:
        bp = find_blueprint(typ, settings.vorlagen_dir)
        if bp:
            try:
                m = docx_engine.missing_placeholders(bp, context)
            except Exception:
                continue
            if m:
                missing[typ] = m
    return missing


def generate(
    settings: Settings,
    job_id: str,
    job: dict,
    types: Optional[list[str]] = None,
    pdf_only: bool = False,
) -> GenerationResult:
    """types: Dokumente, die (neu) aus der Vorlage erzeugt werden; None = alle."""
    types = TYPES if types is None else [t for t in types if t in TYPES]
    context = build_context(job, settings.profil)
    suffix = output_suffix(job, settings.profil)
    work_dir = folder_for_job(settings, job_id, job)
    work_dir.mkdir(parents=True, exist_ok=True)
    res = GenerationResult(folder=work_dir.name)

    (work_dir / JOB_FILE).write_text(
        json.dumps({"job_id": str(job_id), "job": job}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    docx_by_type: dict[str, Path] = {}
    for typ in TYPES:
        target = work_dir / f"{typ}_{suffix}.docx"
        if typ in types and not pdf_only:
            bp = find_blueprint(typ, settings.vorlagen_dir)
            if bp is None:
                res.errors.append(f"Vorlage fehlt: blprnt_{typ}.docx im Vorlagen-Ordner")
                continue
            try:
                docx_engine.fill_docx(bp, context, target)
            except Exception as e:
                res.errors.append(f"{typ}: Vorlage konnte nicht befüllt werden ({e})")
                continue
            res.files[f"{typ} (Word)"] = target.name
        if target.exists():
            docx_by_type[typ] = target

    _build_pdfs(settings, work_dir, suffix, docx_by_type, res)
    _write_email(settings, work_dir, suffix, context, res)
    return res


def _build_pdfs(settings: Settings, work_dir: Path, suffix: str,
                docx_by_type: dict[str, Path], res: GenerationResult) -> None:
    if not docx_by_type:
        return
    soffice = pdf.find_libreoffice(settings.libreoffice_path)
    if soffice is None:
        res.errors.append("LibreOffice wurde nicht gefunden – PDFs konnten nicht erstellt werden.")
        return

    tmp = Path(tempfile.mkdtemp(prefix="bewerbung_"))
    try:
        pdf_by_type: dict[str, Path] = {}
        try:
            converted = pdf.docx_to_pdfs(list(docx_by_type.values()), tmp, soffice,
                                         settings.home / "lo_profile")
        except Exception as e:
            res.errors.append(str(e))
            return
        for typ, docx in docx_by_type.items():
            if docx not in converted:
                res.errors.append(f"{typ}: PDF konnte nicht erstellt werden.")
                continue
            out = work_dir / f"{typ}_{suffix}.pdf"
            shutil.copy2(converted[docx], out)
            pdf_by_type[typ] = out
            res.files[f"{typ} (PDF)"] = out.name

        if "Deckblatt" in pdf_by_type and "Anschreiben" in pdf_by_type:
            kombi = work_dir / f"Deckblatt_Anschreiben_{suffix}.pdf"
            try:
                pdf.merge_pdfs([pdf_by_type["Deckblatt"], pdf_by_type["Anschreiben"]], kombi)
                res.files["Deckblatt + Anschreiben"] = kombi.name
            except Exception as e:
                res.errors.append(f"Zusammenführen Deckblatt + Anschreiben: {e}")

        parts = [pdf_by_type[t] for t in TYPES if t in pdf_by_type]
        anhang = next((p for p in (work_dir / "Anhang.pdf", settings.vorlagen_dir / "Anhang.pdf")
                       if p.exists()), None)
        if anhang:
            parts.append(anhang)
        if parts:
            full = work_dir / f"Bewerbung_{suffix}.pdf"
            try:
                pdf.merge_pdfs(parts, full)
                res.files["Vollständige Bewerbung"] = full.name
            except Exception as e:
                res.errors.append(f"Zusammenführen Bewerbung: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_email(settings: Settings, work_dir: Path, suffix: str,
                 context: dict, res: GenerationResult) -> None:
    if not context.get("anschreiben"):
        return
    attach = next((work_dir / res.files[k] for k in ("Vollständige Bewerbung", "Deckblatt + Anschreiben")
                   if k in res.files), None)
    template = email_draft.find_email_template(settings.vorlagen_dir)
    try:
        eml = work_dir / f"Email_{suffix}.eml"
        email_draft.write_eml(eml, context, settings.profil.get("email") or "", attach, template)
        res.files["E-Mail-Entwurf"] = eml.name
    except Exception as e:
        res.errors.append(f"E-Mail-Entwurf: {e}")
