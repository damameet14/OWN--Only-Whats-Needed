; Inno Setup Script for OWN
; Compiles the 'main.dist' folder into a professional Windows Installer

[Setup]
AppName=OWN
AppVersion=1.0
AppPublisher=damameet14
DefaultDirName={autopf}\OWN
DefaultGroupName=OWN
; If you have an icon, uncomment the line below and make sure app_icon.ico exists next to this .iss file
; SetupIconFile=app_icon.ico
OutputBaseFilename=OWN_Setup_v1.0
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DisableDirPage=no

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Copy all files from the Nuitka distribution folder
Source: "main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\OWN"; Filename: "{app}\main.exe"
; Optional Desktop shortcut
Name: "{autodesktop}\OWN"; Filename: "{app}\main.exe"; Tasks: desktopicon

[Run]
; Option to launch the app immediately after installation
Filename: "{app}\main.exe"; Description: "Launch OWN"; Flags: nowait postinstall skipifsilent
