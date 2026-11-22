; Windows installer of Coralis (Inno Setup 6).
;   iscc /DAppVersion=0.11.0 packaging\coralis.iss   ->   Coralis-0.11.0-Windows.exe
; Packs dist\Coralis (made by PyInstaller). Audiveris and homr are not inside: Coralis downloads
; them on its first run. Installs for the current user only: no administrator rights needed.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{7C1F8E2A-4B6D-4C1E-9A57-C0BA11500001}
AppName=Coralis
AppVersion={#AppVersion}
AppVerName=Coralis {#AppVersion}
AppPublisher=Orlando Flores
AppPublisherURL=https://github.com/OrlandoFloresC/Coralis
AppSupportURL=https://github.com/OrlandoFloresC/Coralis/issues
DefaultDirName={localappdata}\Programs\Coralis
DefaultGroupName=Coralis
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=..\LICENSE
SetupIconFile=..\assets\coralis.ico
UninstallDisplayIcon={app}\Coralis.exe
OutputDir=..\dist
OutputBaseFilename=Coralis-{#AppVersion}-Windows
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\Coralis\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Coralis"; Filename: "{app}\Coralis.exe"
Name: "{group}\Desinstalar Coralis"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Coralis"; Filename: "{app}\Coralis.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Coralis.exe"; Description: "Abrir Coralis ahora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the readers downloaded on the first run (~1 GB); the converted scores in Documents\Coralis stay
Type: filesandordirs; Name: "{localappdata}\omr-coral\tools"
