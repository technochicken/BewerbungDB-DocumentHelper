#!/usr/bin/env python3
"""
Erstellt eine start.bat im Zielordner, die create_application.py startet.

Aufruf:
    python make_starter.py [zielordner]

Wenn kein Zielordner angegeben wird, wird start.bat im aktuellen Verzeichnis erstellt.

Beispiel:
    python "D:\\BewerbungAuto\\create_documents\\make_starter.py" "D:\\Bewerbungen\\Acme_GmbH"
"""

import sys
from pathlib import Path

SCRIPT_PATH = (Path(__file__).parent / "create_application.py").resolve()


def create_starter(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    bat_path = target / "start.bat"
    # %~dp0 expands to the directory of the .bat file (with trailing backslash)
    content = (
        "@echo off\r\n"
        f'python "{SCRIPT_PATH}" "%~dp0"\r\n'
        "pause\r\n"
    )
    bat_path.write_text(content, encoding="utf-8")
    print(f"Erstellt: {bat_path}")
    print()
    print("Legen Sie folgende Dateien in diesen Ordner:")
    print("  blprnt_Deckblatt.docx")
    print("  blprnt_Anschreiben.docx")
    print("  blprnt_Lebenslauf.docx")
    print("  Anhang.pdf")
    print("  <job-id>.txt  (z.B. 42.txt)")
    print()
    print("Starten Sie die Dokumentenerstellung mit:  start.bat")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        create_starter(Path(sys.argv[1]).resolve())
    else:
        create_starter(Path.cwd())
