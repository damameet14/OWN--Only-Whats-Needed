; Inno Setup Script for OWN — Only What's Needed
; Compiles the 'main.dist' folder into a professional Windows Installer

[Setup]
AppName=OWN
AppVersion=1.0.0
AppPublisher=damameet14
AppSupportURL=https://github.com/damameet14/OWN
DefaultDirName={autopf}\OWN
DefaultGroupName=OWN
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\main.exe
OutputBaseFilename=OWN_Setup_v1.0
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableDirPage=no
WizardStyle=modern
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
; Copy all files from the Nuitka distribution folder
Source: "main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\OWN"; Filename: "{app}\main.exe"; IconFilename: "{app}\logo.ico"
; Optional Desktop shortcut
Name: "{autodesktop}\OWN"; Filename: "{app}\main.exe"; IconFilename: "{app}\logo.ico"; Tasks: desktopicon

[Run]
; Option to launch the app immediately after installation
Filename: "{app}\main.exe"; Description: "Launch OWN"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up runtime-generated data on uninstall
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\models_data"
Type: files; Name: "{app}\own.db"
