"""Einstellungen und Profil laden/speichern.

Wo liegen die Daten?
  1. Umgebungsvariable BEWERBUNGDB_HOME, falls gesetzt
  2. Der Programmordner, falls dort eine config.json liegt (portabler Modus / Entwicklung)
  3. Sonst %APPDATA%/BewerbungDB (bzw. ~/.bewerbungdb ausserhalb von Windows)
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROGRAM_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CONFIG: dict = {
    "api_base_url": "https://bwdb-01.dach-it-01.de",
    "api_key": "",
    "libreoffice_path": "C:/Program Files/LibreOffice/program/soffice.exe",
    # Sichtbarer Ordner unter "Dokumente": Nutzer finden ihre Vorlagen und Bewerbungen selbst.
    "vorlagen_pfad": "~/Documents/BewerbungDB/Vorlagen",
    "arbeitsordner": "~/Documents/BewerbungDB/Bewerbungen",
}

DEFAULT_PROFIL: dict = {
    "vorname": "",
    "nachname": "",
    "email": "",
    "telefon": "",
    "strasse": "",
    "hausnummer": "",
    "plz": "",
    "ort": "",
}


class ConfigError(RuntimeError):
    """Eine Konfigurationsdatei ist unlesbar."""


def find_home() -> Path:
    env = os.environ.get("BEWERBUNGDB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    if (PROGRAM_DIR / "config.json").exists():
        return PROGRAM_DIR
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "BewerbungDB"
    return Path.home() / ".bewerbungdb"


def _read_json(path: Path, defaults: dict) -> dict:
    if not path.exists():
        return dict(defaults)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"Die Datei {path.name} ist fehlerhaft (Zeile {e.lineno}): {e.msg}")
    if not isinstance(data, dict):
        raise ConfigError(f"Die Datei {path.name} hat ein ungültiges Format.")
    return {**defaults, **data}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomar: keine halb geschriebene Datei bei Absturz


@dataclass
class Settings:
    home: Path
    config: dict
    profil: dict

    # ── Pfade ────────────────────────────────────────────────────────────────
    def _resolve(self, raw: str) -> Path:
        p = Path(raw).expanduser()
        return p if p.is_absolute() else (self.home / p).resolve()

    @property
    def vorlagen_dir(self) -> Path:
        return self._resolve(self.config.get("vorlagen_pfad") or DEFAULT_CONFIG["vorlagen_pfad"])

    @property
    def arbeitsordner(self) -> Path:
        return self._resolve(self.config.get("arbeitsordner") or DEFAULT_CONFIG["arbeitsordner"])

    @property
    def api_url(self) -> str:
        return self.config.get("api_base_url") or DEFAULT_CONFIG["api_base_url"]

    @property
    def api_key(self) -> str:
        return self.config.get("api_key") or ""

    @property
    def libreoffice_path(self) -> str:
        return self.config.get("libreoffice_path") or DEFAULT_CONFIG["libreoffice_path"]

    # ── Speichern ────────────────────────────────────────────────────────────
    def save_profil(self, profil: dict) -> None:
        self.profil = {**self.profil, **profil}
        _write_json(self.home / "profil.json", self.profil)

    def save_config(self, updates: dict) -> None:
        allowed = set(DEFAULT_CONFIG)
        self.config = {**self.config, **{k: v for k, v in updates.items() if k in allowed}}
        _write_json(self.home / "config.json", self.config)


def load_settings(home: Optional[Path] = None) -> Settings:
    home = home or find_home()
    return Settings(
        home=home,
        config=_read_json(home / "config.json", DEFAULT_CONFIG),
        profil=_read_json(home / "profil.json", DEFAULT_PROFIL),
    )
