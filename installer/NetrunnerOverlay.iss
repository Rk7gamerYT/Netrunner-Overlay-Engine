#ifndef AppVersion
  #define AppVersion "1.3.2"
#endif
#ifndef ProjectRoot
  #define ProjectRoot ".."
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

[Setup]
AppId={{E3E4E189-C7FB-4FF3-9252-72D99045A7A4}
AppName=Netrunner Overlay Engine
AppVersion={#AppVersion}
AppVerName=Netrunner Overlay Engine {#AppVersion}
UninstallDisplayName=Netrunner Overlay Engine
AppPublisher=Rk7gamerYT
DefaultDirName={localappdata}\Programs\Netrunner Overlay Engine
DefaultGroupName=Netrunner Overlay Engine
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=NetrunnerOverlay-Setup-v{#AppVersion}-windows-x64
SetupIconFile={#ProjectRoot}\assets\netrunner.ico
UninstallDisplayIcon={app}\NetrunnerOverlay.exe
LicenseFile={#ProjectRoot}\LICENSE.md
; O executavel Nuitka isolado passa limpo no VirusTotal (0/70), enquanto o
; instalador LZMA2/solid recebe uma deteccao heuristica da Microsoft. Manter o
; payload sem compressao deixa os PE/DLLs diretamente inspecionaveis pelo AV.
Compression=none
SolidCompression=no
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=NetrunnerOverlay.exe
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoCompany=Rk7gamerYT
VersionInfoDescription=Instalador do Netrunner Overlay Engine
VersionInfoProductName=Netrunner Overlay Engine
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; O build standalone do Nuitka gera NetrunnerOverlay.dist sem stub
; autoextraivel. O executavel continua sendo instalado como NetrunnerOverlay.exe.
Source: "{#ProjectRoot}\dist\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\LICENSE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\OBS.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\images\*"; DestDir: "{app}\docs\images"; Flags: ignoreversion
Source: "{#ProjectRoot}\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Netrunner Overlay Engine"; Filename: "{app}\NetrunnerOverlay.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Netrunner Overlay Engine"; Filename: "{app}\NetrunnerOverlay.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\NetrunnerOverlay.exe"; Description: "{cm:LaunchProgram,Netrunner Overlay Engine}"; Flags: nowait postinstall skipifsilent

[CustomMessages]
english.RemoveSettingsPrompt=Do you also want to remove your saved overlay customizations? Choose No to keep them for a future installation.
brazilianportuguese.RemoveSettingsPrompt=Deseja remover também as personalizações salvas do overlay? Escolha Não para mantê-las para uma instalação futura.
spanish.RemoveSettingsPrompt=¿También deseas eliminar las personalizaciones guardadas del overlay? Elige No para conservarlas para una futura instalación.
french.RemoveSettingsPrompt=Voulez-vous également supprimer les personnalisations enregistrées de l’overlay ? Choisissez Non pour les conserver pour une future installation.

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
    if MsgBox(ExpandConstant('{cm:RemoveSettingsPrompt}'), mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\NetrunnerOverlay'), True, True, True);
end;

