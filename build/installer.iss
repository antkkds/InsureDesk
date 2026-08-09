; InsureDesk — Windows Installer (Inno Setup)
; Build with: iscc build/installer.iss

#define MyAppName "InsureDesk"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "UIP-AI"
#define MyAppURL "https://insuredesk.ai"
#define MyAppExeName "InsureDesk.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=..\dist
OutputBaseFilename=InsureDesk-Setup-{#MyAppVersion}
SetupIconFile=build\insuredesk.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; Main application
Source: "dist\InsureDesk\{#MyAppExeName}"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "dist\InsureDesk\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

; Portal YAML profiles (built-in)
Source: "portals\*"; DestDir: "{app}\profiles"; Flags: ignoreversion recursesubdirs createallsubdirs

; Default configuration
Source: "config\agent.yaml"; DestDir: "{app}\config"; Flags: ignoreversion

; Browser runtime (Playwright Chromium)
Source: "browser\*"; DestDir: "{app}\browser"; Flags: ignoreversion recursesubdirs createallsubdirs

; Readme
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\app\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Clean up user data (optional — kept by default)
; Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{userappdata}\{#MyAppName}"""; Flags: runhidden

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create user data directory
    if not DirExists(ExpandConstant('{userappdata}\{#MyAppName}')) then
      CreateDir(ExpandConstant('{userappdata}\{#MyAppName}'));
    // Create logs directory
    if not DirExists(ExpandConstant('{userappdata}\{#MyAppName}\logs')) then
      CreateDir(ExpandConstant('{userappdata}\{#MyAppName}\logs'));
  end;
end;
