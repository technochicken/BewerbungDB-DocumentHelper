#!/usr/bin/env python3
"""
Erstellt einen neuen Bewerbungsarbeitsordner.

Ablauf:
  1. Job-ID eingeben
  2. Stelle wird von der API abgerufen
  3. Übergeordneten Ordner wählen
  4. Arbeitsordner <Firma>_<Jobtitel> wird erstellt mit:
       - <job_id>.txt            (Job-ID Datei für create_application.py)
       - start.bat               (startet den Dokumentengenerator)
       - Vorlagen.lnk            (Verknüpfung zum Vorlagen-Ordner)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

SCRIPT_DIR   = Path(__file__).parent.resolve()
CONFIG_FILE  = SCRIPT_DIR / "config.json"
CREATE_APP   = SCRIPT_DIR / "create_application.py"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {
            "api_base_url": "https://dev.mach-tec.de",
            "api_key": "",
            "vorlagen_pfad": "../Vorlagen",
        }
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def safe_name(s: str) -> str:
    for ch in r'\/:*?"<>|':
        s = s.replace(ch, "")
    return s.replace(" ", "_").strip()[:60]


def fetch_job(api_base: str, job_id: str, api_key: str = "") -> dict:
    try:
        import httpx
    except ImportError:
        raise ImportError("httpx nicht installiert.\nBitte: pip install httpx")
    url = f"{api_base.rstrip('/')}/api/v1/jobs/{job_id}"
    headers = {"X-Api-Key": api_key} if api_key else {}
    with httpx.Client(timeout=30, headers=headers) as client:
        resp = client.get(url)
    if resp.status_code == 401:
        raise RuntimeError("API-Key ungültig oder fehlend (HTTP 401).\nBitte api_key in config.json setzen.")
    if resp.status_code == 404:
        raise RuntimeError(f"Stelle #{job_id} nicht gefunden (HTTP 404).")
    resp.raise_for_status()
    return resp.json()


def _create_lnk(target: Path, shortcut: Path) -> None:
    """Create a Windows .lnk shortcut via PowerShell WScript.Shell COM."""
    ps = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$sc = $ws.CreateShortcut("{shortcut}"); '
        f'$sc.TargetPath = "{target}"; '
        f'$sc.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=True, capture_output=True,
    )


def create_workfolder(
    job: dict,
    parent_dir: Path,
    job_id: str,
    vorlagen_dir: Optional[Path],
) -> Path:
    company = safe_name(job.get("company") or "Unbekannt")
    title   = safe_name(
        job.get("job_name_personalized") or job.get("title") or "Stelle"
    )
    work_dir = parent_dir / f"{company}_{title}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Job-ID marker file — picked up automatically by create_application.py
    (work_dir / f"{job_id}.txt").touch()

    # start.bat — runs the document generator with this folder as working dir
    # cd first so Python sees the work folder as cwd; avoids the %~dp0 trailing-
    # backslash quoting bug where MSVCRT turns \" into a literal " in argv[1].
    bat = (
        "@echo off\r\n"
        'cd /d "%~dp0"\r\n'
        f'python "{CREATE_APP}"\r\n'
    )
    (work_dir / "start.bat").write_text(bat, encoding="utf-8")

    # Shortcut to Vorlagen folder for easy template access
    if vorlagen_dir and vorlagen_dir.exists():
        try:
            _create_lnk(vorlagen_dir, work_dir / "Vorlagen.lnk")
        except Exception:
            pass  # Non-critical; user can navigate manually

    return work_dir


def main() -> None:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, filedialog

    config      = load_config()
    api_url     = config.get("api_base_url") or "http://dev.mach-tec.de"
    api_key     = config.get("api_key") or ""
    vorlagen_raw = config.get("vorlagen_pfad") or "../Vorlagen"
    vorlagen_dir = (SCRIPT_DIR / vorlagen_raw).resolve()
    if not vorlagen_dir.exists():
        vorlagen_dir = None

    root = tk.Tk()
    root.withdraw()

    def fatal(msg: str) -> None:
        messagebox.showerror("Fehler", msg, parent=root)
        root.destroy()
        sys.exit(1)

    # ── 1. Ask for job ID ──────────────────────────────────────────────────────
    job_id = simpledialog.askstring(
        "Neuen Arbeitsordner erstellen",
        "Job-ID eingeben:",
        parent=root,
    )
    if not job_id or not job_id.strip():
        root.destroy()
        sys.exit(0)
    job_id = job_id.strip()

    # ── 2. Fetch job ───────────────────────────────────────────────────────────
    try:
        job = fetch_job(api_url, job_id, api_key)
    except ImportError as e:
        fatal(str(e))
        return
    except Exception as e:
        fatal(f"API-Fehler beim Abrufen von Stelle #{job_id}:\n\n{e}")
        return

    title   = job.get("title")   or "–"
    company = job.get("company") or "–"
    loc     = job.get("location") or "–"

    # ── 3. Confirm + pick parent folder ───────────────────────────────────────
    confirmed = messagebox.askyesno(
        "Stelle gefunden",
        f"Stelle gefunden:\n\n"
        f"  Titel:  {title}\n"
        f"  Firma:  {company}\n"
        f"  Ort:    {loc}\n\n"
        f"Arbeitsordner erstellen?",
        parent=root,
    )
    if not confirmed:
        root.destroy()
        sys.exit(0)

    parent_str = filedialog.askdirectory(
        title="Übergeordneten Ordner wählen",
        parent=root,
    )
    if not parent_str:
        root.destroy()
        sys.exit(0)

    # ── 4. Create folder ───────────────────────────────────────────────────────
    try:
        work_dir = create_workfolder(
            job, Path(parent_str), job_id, vorlagen_dir
        )
    except Exception as e:
        fatal(f"Fehler beim Erstellen des Ordners:\n{e}")
        return

    folder_name = work_dir.name
    messagebox.showinfo(
        "Ordner erstellt",
        f"Arbeitsordner erstellt:\n\n"
        f"  {work_dir}\n\n"
        f"Inhalt:\n"
        f"  {job_id}.txt     — Job-ID\n"
        f"  start.bat        — Dokumentengenerator starten\n"
        + (f"  Vorlagen.lnk    — Vorlagen öffnen\n" if vorlagen_dir else ""),
        parent=root,
    )
    subprocess.Popen(["explorer", str(work_dir)])
    root.destroy()


if __name__ == "__main__":
    main()
