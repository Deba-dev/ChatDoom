; Inno Setup script (free) - packages the CHATDOOM desktop app
[Setup]
AppId=ChatVoice
AppName=CHATDOOM
AppVersion=1.4.2
AppPublisher=ZUNIMILABS
AppCopyright=Developed and powered by ZUNIMILABS
AppVerName=CHATDOOM 1.4.2
VersionInfoVersion=1.4.2.0
VersionInfoCompany=ZUNIMILABS
VersionInfoDescription=CHATDOOM installer
DefaultDirName={autopf}\ChatVoice
DefaultGroupName=CHATDOOM
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=CHATDOOM-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\CHATDOOM.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Tells Windows to redraw icons after installing, so a new logo shows without a restart
ChangesAssociations=yes
; The [Code] section below closes the app itself; Windows must not reopen it as well as [Run]
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\CHATDOOM\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[InstallDelete]
Type: files; Name: "{app}\ChatVoice.exe"
; Files from the previous version must not mix with the new ones. Settings are safe: they live in %APPDATA%\ChatVoice.
Type: filesandordirs; Name: "{app}\_internal"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "CHATDOOM"; Flags: dontcreatekey uninsdeletevalue

[Icons]
Name: "{autoprograms}\CHATDOOM"; Filename: "{app}\CHATDOOM.exe"
Name: "{autodesktop}\CHATDOOM"; Filename: "{app}\CHATDOOM.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CHATDOOM.exe"; Description: "Start CHATDOOM"; Flags: nowait postinstall skipifsilent
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden nowait skipifdoesntexist
Filename: "{app}\CHATDOOM.exe"; Flags: nowait; Check: WizardSilent

[Code]
// Waits for the running app to close before any file is touched. A file still in use would leave half an update behind.
function AppIsRunning(Args: String): Boolean;
var
  Code: Integer;
begin
  Result := False;
  if Exec(ExpandConstant('{sys}\taskkill.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := Code <> 128;      // 128 = no such program running
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  I: Integer;
begin
  Result := '';
  for I := 1 to 20 do begin
    if not AppIsRunning('/IM CHATDOOM.exe') then begin
      Sleep(500);               // Windows needs a moment to let go of the files
      exit;
    end;
    Sleep(500);
  end;
  AppIsRunning('/F /T /IM CHATDOOM.exe');
  Sleep(1500);
end;
