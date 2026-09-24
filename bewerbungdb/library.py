"""Dokumentenverwaltung: Bewerbungsordner und ihre Dateien auflisten."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Optional

from .config import Settings
from .generator import JOB_FILE

KIND_BY_EXT = {".pdf": "pdf", ".docx": "word", ".eml": "mail"}


def _kind(name: str) -> str:
    return KIND_BY_EXT.get(Path(name).suffix.lower(), "other")


def _label(name: str) -> str:
    stem = Path(name).stem
    for prefix, label in [
        ("Bewerbung_", "Vollständige Bewerbung"),
        ("Deckblatt_Anschreiben_", "Deckblatt + Anschreiben"),
        ("Deckblatt_", "Deckblatt"),
        ("Anschreiben_", "Anschreiben"),
        ("Lebenslauf_", "Lebenslauf"),
        ("Email_", "E-Mail-Entwurf"),
    ]:
        if stem.startswith(prefix):
            return label
    return stem


def _doc_type(name: str) -> Optional[str]:
    """Deckblatt / Anschreiben / Lebenslauf, wenn es die einzelne Word-Datei dieses Typs ist."""
    if Path(name).suffix.lower() != ".docx":
        return None
    for typ in ("Deckblatt", "Anschreiben", "Lebenslauf"):
        if name.startswith(typ + "_"):
            return typ
    return None


_ORDER = ["Bewerbung_", "Deckblatt_Anschreiben_", "Deckblatt_", "Anschreiben_", "Lebenslauf_", "Email_"]


def _sort_key(name: str) -> tuple:
    """Fertige Bewerbung zuerst, dann je Dokument Word vor PDF, E-Mail zuletzt."""
    rank = next((i for i, p in enumerate(_ORDER) if name.startswith(p)), len(_ORDER))
    return (rank, Path(name).suffix.lower() != ".docx", name)


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).isoformat(timespec="minutes")


def _read_meta(folder: Path) -> Optional[dict]:
    meta = folder / JOB_FILE
    if meta.is_file():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    # Altbestand aus dem alten Skript: <job-id>.txt als Marker
    for txt in folder.glob("*.txt"):
        if txt.stem.isalnum():
            return {"job_id": txt.stem, "job": {}}
    return None


def list_applications(settings: Settings) -> list[dict]:
    root = settings.arbeitsordner
    if not root.exists():
        return []
    items: list[dict] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        meta = _read_meta(d)
        if meta is None:
            continue
        job = meta.get("job") or {}
        files = [
            {"name": f.name, "label": _label(f.name), "kind": _kind(f.name), "type": _doc_type(f.name),
             "size": f.stat().st_size, "modified": _iso(f.stat().st_mtime)}
            for f in sorted(d.iterdir(), key=lambda p: _sort_key(p.name))
            if f.is_file() and f.suffix.lower() in KIND_BY_EXT
        ]
        items.append({
            "folder": d.name,
            "job_id": str(meta.get("job_id", "")),
            "title": job.get("job_name_personalized") or job.get("title") or d.name,
            "company": job.get("company") or "",
            "location": job.get("location") or "",
            "modified": _iso(d.stat().st_mtime),
            "files": files,
        })
    items.sort(key=lambda i: i["modified"], reverse=True)
    return items


def resolve_file(settings: Settings, folder: str, name: Optional[str] = None) -> Path:
    """Sicher auf einen Ordner bzw. eine Datei unterhalb des Arbeitsordners auflösen."""
    root = settings.arbeitsordner.resolve()
    path = (root / folder / (name or "")).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Ungültiger Pfad.")
    if not path.exists():
        raise FileNotFoundError(name or folder)
    return path
