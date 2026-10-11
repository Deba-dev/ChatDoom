; Inno Setup script (free) - packages the CHATDOOM desktop app
[Setup]
AppId=ChatVoice
AppName=CHATDOOM
AppVersion=1.0.6
AppPublisher=itsmeblitz
AppCopyright=Created by itsmeblitz
AppVerName=CHATDOOM 1.0.6 BETA
VersionInfoVersion=1.0.6.0
VersionInfoCompany=itsmeblitz
VersionInfoDescription=CHATDOOM (BETA) installer
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

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\CHATDOOM\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[InstallDelete]
Type: files; Name: "{app}\ChatVoice.exe"

[Icons]
Name: "{autoprograms}\CHATDOOM"; Filename: "{app}\CHATDOOM.exe"
Name: "{autodesktop}\CHATDOOM"; Filename: "{app}\CHATDOOM.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\CHATDOOM.exe"; Description: "Start CHATDOOM"; Flags: nowait postinstall skipifsilent
Filename: "{app}\CHATDOOM.exe"; Flags: nowait; Check: WizardSilent
