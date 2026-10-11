; Inno Setup script (free) - packages the CHATDOOM desktop app
[Setup]
AppId=ChatVoice
AppName=CHATDOOM
AppVersion=0.5.0
AppPublisher=itsmeblitz
AppCopyright=Created by itsmeblitz
AppVerName=CHATDOOM 0.5.0 BETA
VersionInfoVersion=0.5.0.0
VersionInfoCompany=itsmeblitz
VersionInfoDescription=CHATDOOM (BETA) installer
DefaultDirName={autopf}\ChatVoice
DefaultGroupName=CHATDOOM
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=CHATDOOM-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\ChatVoice.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\ChatVoice\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\CHATDOOM"; Filename: "{app}\ChatVoice.exe"
Name: "{autodesktop}\CHATDOOM"; Filename: "{app}\ChatVoice.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ChatVoice.exe"; Description: "Start CHATDOOM"; Flags: nowait postinstall skipifsilent
Filename: "{app}\ChatVoice.exe"; Flags: nowait; Check: WizardSilent
