#define AppName "AI Drama Desktop"
#define AppPublisher "OneHot"
#ifndef AppVersion
#define AppVersion "dev"
#endif
#ifndef SourceDir
#define SourceDir "..\..\dist\AI Drama Desktop"
#endif
#ifndef OutputDir
#define OutputDir "..\..\dist"
#endif

[Setup]
AppId={{7B24C63A-51E5-4DF0-8E49-4D54B9F3854B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\AI Drama Desktop
DefaultGroupName=AI Drama Desktop
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=AI-Drama-Desktop-Setup-{#AppVersion}-windows-x64
SetupIconFile=..\..\src\aidrama_desktop\assets\app-icon.ico
UninstallDisplayIcon={app}\AI Drama Desktop.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AI Drama Desktop"; Filename: "{app}\AI Drama Desktop.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\AI Drama Desktop"; Filename: "{app}\AI Drama Desktop.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\AI Drama Desktop.exe"; Description: "{cm:LaunchProgram,AI Drama Desktop}"; Flags: nowait postinstall skipifsilent
