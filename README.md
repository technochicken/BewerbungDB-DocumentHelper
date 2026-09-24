# BewerbungDB Dokumenten-App

Erstellt Bewerbungsunterlagen (Deckblatt, Anschreiben, Lebenslauf, PDFs, E-Mail-Entwurf) aus den Daten
deiner BewerbungDB. Bedienung im Browser-Fenster, keine Programmierkenntnisse nötig.

## Für Nutzer

`BewerbungDB-Setup-<version>.exe` ausführen. Der Installer

- braucht **keine Administratorrechte** und installiert nach `%LOCALAPPDATA%\Programs\BewerbungDB`,
- bringt alles Nötige selbst mit (kein Python erforderlich),
- bietet an, **LibreOffice** herunterzuladen und zu installieren, falls es fehlt (für PDFs; nur dieser Schritt fragt nach Administratorrechten),
- legt Startmenü- (und optional Desktop-)Verknüpfung an und bringt einen Deinstaller mit.

Beim ersten Start fragt ein kurzer Assistent nach Name, Adresse und API-Schlüssel.

| Was | Wo |
|---|---|
| Programm | `%LOCALAPPDATA%\Programs\BewerbungDB` |
| Einstellungen, Profil, Logdatei | `%APPDATA%\BewerbungDB` |
| Vorlagen und fertige Bewerbungen | `Dokumente\BewerbungDB` |

### Links aus dem Browser

Der Installer registriert das Link-Format `bewerbungdb://create-application/<job-id>` (nur für den
aktuellen Benutzer). Ein Klick darauf öffnet BewerbungDB und lädt die Stelle – erstellt wird erst nach
Klick auf „Bewerbung erstellen“. Läuft die App schon, öffnet sich nur ein neues Fenster.
In der BewerbungDB-Weboberfläche genügt dafür ein normaler Link:

```html
<a href="bewerbungdb://create-application/c876474e3c">Bewerbung erstellen</a>
```

Beim ersten Klick fragt der Browser einmalig, ob er „BewerbungDB“ öffnen darf.

Beim Deinstallieren bleiben Vorlagen und Bewerbungen immer erhalten; die Einstellungen (inkl. API-Schlüssel)
werden nur auf Nachfrage gelöscht.

## Für Entwickler

```
pip install -r requirements.txt pytest
python dev_server.py            # http://127.0.0.1:8765
python -m pytest tests
```

Nur die Standardbibliothek wird für Server und API-Zugriff genutzt (schneller Start, wenig Fehlerquellen).
Eigene Daten für Entwicklung: `config.json` und `profil.json` neben `run_app.py` (siehe `*.example.json`);
sie sind per `.gitignore` von Git ausgeschlossen. Alternativ `BEWERBUNGDB_HOME` auf einen Ordner setzen.

### Installer bauen

Voraussetzungen: Internet, [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

Ergebnis: `dist\BewerbungDB-Setup-<version>.exe`. Das Skript lädt eine Embeddable-Python-Runtime,
installiert die Pakete hinein, prüft, dass die App damit startet, und ruft Inno Setup auf.

Die gepinnte LibreOffice-Version steht in `installer/BewerbungDB.iss` (mit SHA-256-Prüfsumme).
Beim Aktualisieren beide Werte gemeinsam ändern; die Prüfsumme steht neben dem Download als `.msi.sha256`.

Die Standard-Vorlagen in `bewerbungdb/default_templates` erzeugt `python tools/make_default_templates.py`.
