; Z-ToolKit Inno Setup 安装脚本
; 开发者: zsz、Kimi-K3

[Setup]
AppName=Z-ToolKit
AppVersion=1.0
AppPublisher=zsz
AppPublisherURL=https://github.com/zsz
DefaultDirName={autopf}\Z-ToolKit
DefaultGroupName=Z-ToolKit
UninstallDisplayIcon={app}\Z-ToolKit.exe
OutputDir=..
OutputBaseFilename=Z-ToolKit_Installer
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
DisableProgramGroupPage=yes
PrivilegesRequired=admin
WizardStyle=modern

[Types]
Name: "full"; Description: "完整安装（推荐，包含全部组件）"
Name: "custom"; Description: "自定义安装"; Flags: iscustom

[Components]
Name: "main"; Description: "Z-ToolKit 主程序（必需）"; Types: full custom; Flags: fixed
Name: "tools_7z"; Description: "7z — 压缩/哈希计算工具"; Types: full
Name: "tools_ffmpeg"; Description: "ffmpeg — 视频处理工具"; Types: full
Name: "tools_ffprobe"; Description: "ffprobe — 视频信息探测工具"; Types: full
Name: "tools_hbsubset"; Description: "hb-subset — 字体子集化工具"; Types: full
Name: "tools_mkvextract"; Description: "mkvextract — MKV 字幕提取工具"; Types: full
Name: "tools_mkvmerge"; Description: "mkvmerge — MKV 合并/混流工具"; Types: full

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"

[Files]
; 主程序（必选）
Source: "d:\Code\Program\Z-ToolKit\Application\Z-ToolKit.exe"; DestDir: "{app}"; Components: main; Flags: ignoreversion
Source: "d:\Code\Program\Z-ToolKit\Application\_internal\*"; DestDir: "{app}\_internal"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "d:\Code\Program\Z-ToolKit\Application\Add\*"; DestDir: "{app}\Add"; Components: main; Flags: ignoreversion recursesubdirs createallsubdirs

; 工具（可选，默认全部安装）
Source: "d:\Code\Program\Z-ToolKit\Application\Tools\7z\*"; DestDir: "{app}\Tools\7z"; Components: tools_7z; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "d:\Code\Program\Z-ToolKit\Application\Tools\ffmpeg\*"; DestDir: "{app}\Tools\ffmpeg"; Components: tools_ffmpeg; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "d:\Code\Program\Z-ToolKit\Application\Tools\ffprobe\*"; DestDir: "{app}\Tools\ffprobe"; Components: tools_ffprobe; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "d:\Code\Program\Z-ToolKit\Application\Tools\hb-subset\*"; DestDir: "{app}\Tools\hb-subset"; Components: tools_hbsubset; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "d:\Code\Program\Z-ToolKit\Application\Tools\mkvextract\*"; DestDir: "{app}\Tools\mkvextract"; Components: tools_mkvextract; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "d:\Code\Program\Z-ToolKit\Application\Tools\mkvmerge\*"; DestDir: "{app}\Tools\mkvmerge"; Components: tools_mkvmerge; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Z-ToolKit"; Filename: "{app}\Z-ToolKit.exe"
Name: "{group}\卸载 Z-ToolKit"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Z-ToolKit"; Filename: "{app}\Z-ToolKit.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Z-ToolKit.exe"; Description: "启动 Z-ToolKit"; Flags: nowait postinstall skipifsilent
