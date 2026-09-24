"""Standard-Vorlagen beim ersten Start in den Vorlagen-Ordner des Nutzers kopieren."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Settings

DEFAULTS_DIR = Path(__file__).parent / "default_templates"


def ensure_defaults(settings: Settings) -> None:
    """Nur wenn der Vorlagen-Ordner noch keine Vorlagen enthält – vorhandene bleiben unangetastet."""
    target = settings.vorlagen_dir
    if not DEFAULTS_DIR.exists() or (target.exists() and any(target.glob("blprnt*"))):
        return
    target.mkdir(parents=True, exist_ok=True)
    for src in DEFAULTS_DIR.glob("blprnt*"):
        shutil.copy2(src, target / src.name)
