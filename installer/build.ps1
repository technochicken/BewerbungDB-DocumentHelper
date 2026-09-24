# Baut den Installer: dist\BewerbungDB-Setup-<version>.exe
#
# Voraussetzungen (nur zum Bauen, nicht für Endnutzer):
#   - Internetverbindung (Python-Runtime + Pakete werden geladen)
#   - Inno Setup 6   ->   winget install JRSoftware.InnoSetup
#
# Aufruf:  powershell -ExecutionPolicy Bypass -File installer\build.ps1

param(
    [string]$PythonVersion = "3.12.10",   # Embeddable-Python; 3.12 hat für alle Pakete fertige Windows-Wheels
    [string]$AppVersion    = "0.1.0"
)

$ErrorActionPreference = "Stop"
$root  = Split-Path -Parent $PSScriptRoot
$inst  = $PSScriptRoot
$cache = Join-Path $inst "cache"
$stage = Join-Path $inst "stage"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# ── Inno Setup finden ────────────────────────────────────────────────────────
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 nicht gefunden. Installieren mit: winget install JRSoftware.InnoSetup" }

# ── Aufräumen ────────────────────────────────────────────────────────────────
Step "Bereite Build-Ordner vor"
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force $cache, $stage | Out-Null

# ── Python-Runtime ───────────────────────────────────────────────────────────
Step "Python $PythonVersion (embeddable)"
$zip = Join-Path $cache "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $zip
}
$py = Join-Path $stage "python"
Expand-Archive $zip -DestinationPath $py

# ._pth: site-packages aktivieren und den App-Ordner in den Suchpfad aufnehmen
$pth = Get-ChildItem $py -Filter "python*._pth" | Select-Object -First 1
$zipName = (Get-ChildItem $py -Filter "python*.zip" | Select-Object -First 1).Name
Set-Content $pth.FullName -Encoding ascii -Value @($zipName, ".", "..\app", "Lib\site-packages", "import site")

# ── pip + Pakete ─────────────────────────────────────────────────────────────
Step "Installiere Python-Pakete"
$getpip = Join-Path $cache "get-pip.py"
if (-not (Test-Path $getpip)) { Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip }
& "$py\python.exe" $getpip --no-warn-script-location --disable-pip-version-check
if ($LASTEXITCODE) { throw "get-pip fehlgeschlagen" }
& "$py\python.exe" -m pip install -r (Join-Path $root "requirements.txt") --no-warn-script-location --disable-pip-version-check --only-binary=:all:
if ($LASTEXITCODE) { throw "pip install fehlgeschlagen" }
# pip selbst wird zur Laufzeit nicht gebraucht
$ErrorActionPreference = "Continue"   # pip schreibt Hinweise auf stderr, das ist kein Fehler
& "$py\python.exe" -m pip uninstall -y pip 2>&1 | Out-Null
$ErrorActionPreference = "Stop"

# ── App-Dateien ──────────────────────────────────────────────────────────────
Step "Kopiere App-Dateien"
$app = Join-Path $stage "app"
New-Item -ItemType Directory -Force $app | Out-Null
Copy-Item (Join-Path $root "bewerbungdb") $app -Recurse
Copy-Item (Join-Path $root "run_app.py") $app
Get-ChildItem $app -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# ── Smoke-Test: startet die gebündelte Runtime und importiert die App? ───────
Step "Prüfe gebündelte Runtime"
& "$py\python.exe" -c "import sys; sys.path.insert(0, r'$app'); import bewerbungdb.server, bewerbungdb.generator, pikepdf, docxtpl, docx, lxml; print('Runtime OK')"
if ($LASTEXITCODE) { throw "Die gebündelte Runtime kann die App nicht laden" }
Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# ── Installer bauen ──────────────────────────────────────────────────────────
Step "Baue Installer"
& $iscc "/DAppVersion=$AppVersion" (Join-Path $inst "BewerbungDB.iss")
if ($LASTEXITCODE) { throw "Inno Setup fehlgeschlagen" }

$out = Join-Path $root "dist\BewerbungDB-Setup-$AppVersion.exe"
Write-Host "`nFertig: $out  ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)" -ForegroundColor Green
