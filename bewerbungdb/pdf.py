"""DOCX → PDF über LibreOffice, PDFs zusammenführen."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional


class PdfError(RuntimeError):
    pass


_WINDOWS_CANDIDATES = [
    "C:/Program Files/LibreOffice/program/soffice.exe",
    "C:/Program Files (x86)/LibreOffice/program/soffice.exe",
]


def find_libreoffice(configured: str = "", bundled_dir: Optional[Path] = None) -> Optional[Path]:
    """Sucht LibreOffice: mitgeliefert → konfiguriert → Standardpfade → PATH."""
    candidates: list[Path] = []
    if bundled_dir:
        candidates.append(bundled_dir / "program" / ("soffice.exe" if sys.platform == "win32" else "soffice"))
    if configured:
        candidates.append(Path(configured))
    candidates += [Path(p) for p in _WINDOWS_CANDIDATES]
    for c in candidates:
        if c.exists():
            return c
    found = shutil.which("soffice") or shutil.which("libreoffice")
    return Path(found) if found else None


def _kill_tree(proc: subprocess.Popen) -> None:
    """soffice.exe startet soffice.bin als Kindprozess – beide beenden."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


# Ein LibreOffice-Profil verträgt nur einen Prozess gleichzeitig.
_lo_lock = threading.Lock()


def warm_up(soffice: Path, profile_dir: Path, sample_docx: Path, timeout: int = 300) -> None:
    """Profil im Hintergrund anlegen, damit die erste PDF-Erstellung nicht über eine Minute wartet.

    Nur eine echte Umwandlung löst die teure Ersteinrichtung von LibreOffice vollständig aus
    (--terminate_after_init beendet sich vorher).
    """
    done = profile_dir / ".warmed_up"
    if done.exists() or not sample_docx.exists():
        return
    with tempfile.TemporaryDirectory(prefix="lo_warm_") as tmp:
        try:
            docx_to_pdfs([sample_docx], Path(tmp), soffice, profile_dir, timeout)
            done.write_text("ok")
        except PdfError:
            pass  # nicht kritisch: die echte Umwandlung legt das Profil dann selbst an


def docx_to_pdfs(docx_paths: list[Path], output_dir: Path, soffice: Path,
                 profile_dir: Path, timeout: int = 300) -> dict[Path, Path]:
    """Alle DOCX in einem einzigen LibreOffice-Start umwandeln.

    Eigenes, dauerhaftes Profil: stört weder die LibreOffice-Einstellungen des Nutzers
    noch scheitert es, wenn der Nutzer LibreOffice gerade offen hat. Das erste
    Anlegen des Profils dauert etwas, danach geht es deutlich schneller.
    Keine Pipes: soffice.bin würde sie sonst nach einem Timeout offen halten.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(soffice), f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--headless", "--norestore", "--convert-to", "pdf",
        "--outdir", str(output_dir), *map(str, docx_paths),
    ]
    with _lo_lock:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            raise PdfError("Die PDF-Umwandlung hat zu lange gedauert. Bitte erneut versuchen.")
    return {d: output_dir / (d.stem + ".pdf") for d in docx_paths if (output_dir / (d.stem + ".pdf")).exists()}


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> Path:
    import pikepdf

    existing = [p for p in pdf_paths if p.exists()]
    if not existing:
        raise PdfError("Keine PDF-Dateien zum Zusammenführen gefunden.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pikepdf.Pdf.new() as out:
        for p in existing:
            with pikepdf.Pdf.open(p) as src:
                out.pages.extend(src.pages)
        out.save(str(output_path))
    return output_path
