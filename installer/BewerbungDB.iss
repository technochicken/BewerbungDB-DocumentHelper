; Inno Setup 6.1+ – wird von build.ps1 aufgerufen (Ordner "stage" wird dort erzeugt).

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

; LibreOffice wird nur heruntergeladen, wenn es fehlt und der Nutzer zustimmt.
; Die Version ist bewusst gepinnt (ausgereifter Stand) und per SHA-256 abgesichert.
#define LoVersion "26.2.6"
#define LoFile    "LibreOffice_26.2.6_Win_x86-64.msi"
#define LoUrl     "https://download.documentfoundation.org/libreoffice/stable/26.2.6/win/x86_64/" + LoFile
#define LoSha256  "f9877032fd908beb9c0ddf06df4af5c2e85f419c42e14876c4cce5aae5fb2660"

[Setup]
AppId={{B7D2A6C4-5E1F-4B8A-9C3D-2F6E8A1D4C57}
AppName=BewerbungDB
AppVersion={#AppVersion}
AppPublisher=BewerbungDB
; Pro Benutzer, ohne Administratorrechte: {autopf} = %LOCALAPPDATA%\Programs
PrivilegesRequired=lowest
DefaultDirName={autopf}\BewerbungDB
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=BewerbungDB-Setup-{#AppVersion}
SetupIconFile=BewerbungDB.ico
UninstallDisplayIcon={app}\BewerbungDB.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop erstellen"; GroupDescription: "Zusätzliche Symbole:"
Name: "installlo"; Description: "LibreOffice installieren (für die PDF-Erstellung nötig, ca. 360 MB Download)"; GroupDescription: "Benötigte Programme:"; Check: not LibreOfficeInstalled

[Files]
Source: "stage\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "stage\app\*";    DestDir: "{app}\app";    Flags: recursesubdirs createallsubdirs ignoreversion
Source: "BewerbungDB.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\BewerbungDB"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\run_app.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\BewerbungDB.ico"
Name: "{autodesktop}\BewerbungDB";  Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\run_app.py"""; WorkingDir: "{app}\app"; IconFilename: "{app}\BewerbungDB.ico"; Tasks: desktopicon

[Registry]
; bewerbungdb://create-application/<job-id> im Browser anklicken → App öffnet den Dialog für diese Stelle.
; HKCU: gilt nur für diesen Benutzer, keine Administratorrechte nötig; wird beim Deinstallieren entfernt.
Root: HKCU; Subkey: "Software\Classes\bewerbungdb"; ValueType: string; ValueName: ""; ValueData: "URL:BewerbungDB"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\bewerbungdb"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\bewerbungdb\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\BewerbungDB.ico"
Root: HKCU; Subkey: "Software\Classes\bewerbungdb\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\python\pythonw.exe"" ""{app}\app\run_app.py"" ""%1"""

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\run_app.py"""; WorkingDir: "{app}\app"; Description: "BewerbungDB jetzt starten"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Zur Laufzeit erzeugte Dateien (z. B. __pycache__) mit entfernen. Nutzerdaten liegen woanders.
Type: filesandordirs; Name: "{app}"

[Code]
function LibreOfficeInstalled: Boolean;
begin
  Result :=
    FileExists(ExpandConstant('{commonpf64}\LibreOffice\program\soffice.exe')) or
    FileExists(ExpandConstant('{commonpf32}\LibreOffice\program\soffice.exe'));
end;

function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if ProgressMax > 0 then
    WizardForm.StatusLabel.Caption :=
      Format('LibreOffice wird heruntergeladen … %d %%', [Progress * 100 div ProgressMax]);
  Result := True;
end;

procedure InstallLibreOffice;
var
  Msi: String;
  ResultCode: Integer;
begin
  Msi := ExpandConstant('{tmp}\{#LoFile}');
  try
    DownloadTemporaryFile('{#LoUrl}', '{#LoFile}', '{#LoSha256}', @OnDownloadProgress);
  except
    MsgBox('LibreOffice konnte nicht heruntergeladen werden:' + #13#10 + GetExceptionMessage + #13#10#13#10 +
           'BewerbungDB wird trotzdem installiert. Für PDFs installiere LibreOffice später von libreoffice.org.',
           mbInformation, MB_OK);
    Exit;
  end;

  WizardForm.StatusLabel.Caption := 'LibreOffice wird installiert … (bitte Windows-Rückfrage bestätigen)';
  { LibreOffice braucht Administratorrechte – nur dieser eine Schritt wird erhöht ausgeführt. }
  if not ShellExec('runas', 'msiexec.exe', '/i "' + Msi + '" /qb-! REBOOT=ReallySuppress', '',
                   SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode) or ((ResultCode <> 0) and (ResultCode <> 3010)) then
    MsgBox('LibreOffice wurde nicht installiert (Code ' + IntToStr(ResultCode) + ').' + #13#10 +
           'BewerbungDB funktioniert, PDFs erfordern aber LibreOffice. Du kannst es später von libreoffice.org installieren.',
           mbInformation, MB_OK);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('installlo') then
    InstallLibreOffice;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\BewerbungDB');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Sollen auch deine gespeicherten Einstellungen gelöscht werden (Profil, API-Schlüssel)?' + #13#10#13#10 +
                'Deine Bewerbungen und Vorlagen im Ordner "Dokumente\BewerbungDB" bleiben in jedem Fall erhalten. ' +
                'LibreOffice wird nicht entfernt.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
