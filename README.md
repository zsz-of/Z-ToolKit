# Z-ToolKit

视频/字幕/文件处理工具集，提供符号链接创建、动漫自动分类、重复文件检查、视频编码转换、字幕处理等 13 个功能模块。

**开发者**: zsz & Kimi-K3  
**当前版本**: v1.0.0

---

## 系统要求

- **操作系统**: Windows 10 64-Bit 及以上
- **运行时**: 无需额外安装（安装包已内置完整运行环境）

---

## 下载安装

前往 [Releases 页面](https://github.com/zsz-of/Z-ToolKit/releases) 下载最新版本。

| 安装包 | 格式 | 大小 |
|--------|------|------|
| Z-ToolKit_Installer.exe | Inno Setup | 136 MB |
| Z-ToolKit_Installer.msi | Windows Installer | 101 MB |

**安装步骤**：

1. 下载 `Z-ToolKit_Installer.exe` 或 `Z-ToolKit_Installer.msi`
2. 双击运行安装程序
3. 选择需要安装的组件（主程序为必选，6 个外部工具为可选，默认全部安装）
4. 完成安装后，从开始菜单或桌面快捷方式启动

> 两种安装包功能完全一致，任选其一即可。MSI 格式适合企业部署，EXE 格式适合个人使用。

---

## 从源码恢复开发环境

### 前提条件

- **Python**: 3.13+
- **pip**: 最新版本

### 步骤

```bat
:: 1. 克隆仓库
git clone https://github.com/zsz-of/Z-ToolKit.git
cd Z-ToolKit

:: 2. 创建虚拟环境
python -m venv Build\venv
Build\venv\Scripts\activate

:: 3. 安装 Python 依赖
pip install requests chardet tkinterdnd2 fontTools send2trash pyinstaller

:: 4. 准备外部工具（下载地址见下方"开源引用"章节）
::    将工具放入 Source\Tools\ 目录，结构如下：
::    Source\Tools\7z\7z.exe
::    Source\Tools\ffmpeg\ffmpeg.exe
::    Source\Tools\ffprobe\ffprobe.exe
::    Source\Tools\mkvextract\mkvextract.exe
::    Source\Tools\mkvmerge\mkvmerge.exe
::    Source\Tools\hb-subset\hb-subset.exe

:: 5. 脚本模式运行（开发调试）
cd Source
python Z-ToolKit.py
```

### 国内镜像加速

```bat
:: 使用清华镜像安装 pip 依赖
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple requests chardet tkinterdnd2 fontTools send2trash pyinstaller
```

### 构建 EXE

```bat
:: 使用 PyInstaller 打包（--onedir --windowed 模式）
pyinstaller --onedir --windowed --name Z-ToolKit ^
  --collect-all tkinterdnd2 --collect-all fontTools --collect-all send2trash ^
  --collect-all requests --collect-all chardet --collect-all sqlite3 ^
  --hidden-import tkinter.colorchooser ^
  --hidden-import tkinter.scrolledtext --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox --hidden-import tkinter.font ^
  --hidden-import uuid --hidden-import hashlib --hidden-import difflib ^
  --hidden-import unicodedata --hidden-import struct ^
  --hidden-import concurrent.futures --hidden-import logging ^
  --hidden-import string --hidden-import pathlib ^
  --hidden-import enum --hidden-import shutil --hidden-import stat ^
  --hidden-import random ^
  Source\Z-ToolKit.py
```

构建后将 `dist\Z-ToolKit\` 内容复制到 `Application\`，并将 `Add\` 和 `Tools\` 放在 EXE 同级目录。

### 开发模式热更新

脚本模式下修改 `Source\Add\` 中的模块代码后，重启程序即可生效，无需重新构建 EXE。

---

## 目录结构

```
Z-ToolKit/
├── Source/                        # 源代码
│   ├── Z-ToolKit.py               # 主程序入口
│   ├── Readme.md                  # 项目说明
│   ├── Add/                       # 业务模块目录
│   │   ├── README.md              # 模块开发规范（二次开发必读）
│   │   ├── common/                # 公共组件包（TabModule 基类、文件选择器等）
│   │   ├── module_base.py         # 兼容层
│   │   └── [模块名]/              # 各业务模块（文件夹形式，中文命名）
│   └── Tools/                     # 外部工具目录（不入库，见 .gitignore）
├── Build/                         # 构建相关
│   └── Z-ToolKit.spec             # PyInstaller 规格文件
├── Installer/                     # 安装包构建脚本
│   ├── MSI/
│   │   └── generate_wxs.py        # WiX 源文件生成脚本
│   └── Inno_Setup/
│       └── Z-ToolKit.iss          # Inno Setup 脚本
├── .gitignore
└── README.md                      # 本文件
```

### 模块开发

Z-ToolKit 采用插件式架构，所有业务模块位于 `Source/Add/` 目录下。每个模块是一个 Python 包（文件夹 + `__init__.py`），继承 `TabModule` 基类，由主程序在启动时自动加载。详细的模块开发规范请参阅 [Source/Add/README.md](Source/Add/README.md)。

---

## 功能特性

| 模块 | 功能说明 | 外部工具依赖 |
|------|----------|-------------|
| 符号链接创建 | 批量创建符号链接，支持拖放操作 | - |
| 动漫自动分类 | 按番剧名规则自动分类视频文件 | - |
| 重复文件检查 | 基于 SHA256 哈希检测重复文件 | 7z |
| 视频编码转换 | H.264/H.265/AV1/VP9/H.266 编码转换 | ffmpeg, ffprobe |
| 视频缩放 | 多种缩放算法，保持宽高比 | ffmpeg, ffprobe |
| 视频分辨率检查 | 批量检测视频分辨率和帧率 | ffprobe |
| 字幕转换 | ASS/SRT 字幕格式互转 | - |
| 字幕导出 | 从 MKV 视频提取内嵌字幕轨 | mkvextract |
| 字幕内封MKV | 将外挂字幕和字体内封到 MKV | mkvmerge |
| 字幕删除 | 移除 MKV 视频中的字幕轨 | mkvmerge |
| 字幕子集化 | ASS 字体子集化，减小字体体积 | mkvextract, mkvmerge, hb-subset |
| SRT转ASS | SRT 字幕转 ASS 格式 | - |
| M3U8合并 | 合并 M3U8 流媒体片段为完整视频 | ffmpeg |

---

## 开源引用

本程序使用以下开源项目，在此致谢：

| 项目 | 用途 | 仓库地址 |
|------|------|----------|
| FFmpeg | 视频编码转换/缩放/处理 | https://github.com/FFmpeg/FFmpeg |
| MKVToolNix | MKV 字幕提取/合并 | https://gitlab.com/mbunkus/mkvtoolnix |
| HarfBuzz | 字体子集化 (hb-subset) | https://github.com/harfbuzz/harfbuzz |
| 7-Zip | 压缩/哈希计算 | https://github.com/ip7z/7zip |
| requests | HTTP 请求（字幕转换） | https://github.com/psf/requests |
| chardet | 编码检测（SRT转ASS） | https://github.com/chardet/chardet |
| tkinterdnd2 | Tkinter 拖放支持 | https://github.com/pmgagnon/tkinterdnd2 |
| fonttools | 字体处理（子集化） | https://github.com/fonttools/fonttools |
| Send2Trash | 回收站删除（子集化） | https://github.com/arsenetar/send2trash |
| PyInstaller | Python 打包工具 | https://github.com/pyinstaller/pyinstaller |
| WiX Toolset | MSI 安装包制作 | https://github.com/wixtoolset/wix |
| Inno Setup | EXE 安装包制作 | https://github.com/jrsoftware/issrc |

---

**开发者**: zsz & Kimi-K3
