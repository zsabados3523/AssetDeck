; Inno Setup 6 script do instalador do AssetDeck para Windows.
; Uso: iscc /DMyAppVersion=0.1.0 packaging\assetdeck.iss
; Entrada: dist\assetdeck (saida do PyInstaller). Saida: installer-out\AssetDeck-windows-setup.exe

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{B6F0C0E2-7D4A-4F6B-9A55-1D2C3E4F5A60}
AppName=AssetDeck
AppVersion={#MyAppVersion}
AppPublisher=AssetDeck
DefaultDirName={autopf}\AssetDeck
DefaultGroupName=AssetDeck
UninstallDisplayIcon={app}\assetdeck.exe
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer-out
OutputBaseFilename=AssetDeck-windows-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; Flags: unchecked

[Files]
Source: "..\dist\assetdeck\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AssetDeck"; Filename: "{app}\assetdeck.exe"
Name: "{group}\Desinstalar AssetDeck"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AssetDeck"; Filename: "{app}\assetdeck.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\assetdeck.exe"; Description: "Abrir AssetDeck"; Flags: nowait postinstall skipifsilent
