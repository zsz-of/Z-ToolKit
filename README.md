# Z-ToolKit

> 视频/字幕/文件处理工具集 — 13 个功能模块的桌面工具箱，涵盖符号链接、动漫分类、视频编码、字幕处理等常见场景。

由 **zsz** 与 **Kimi-K3** 一起创建。

当前版本：**1.0.0**

## 系统要求

- **Windows 10 64-Bit 及以上**
- 无需额外安装运行时（安装包已内置完整运行环境）

## 下载安装

1. 前往 [Releases](../../releases) 页面下载安装包：
   - `Z-ToolKit_Installer.exe`（Inno Setup，136 MB）
   - `Z-ToolKit_Installer.msi`（Windows Installer，101 MB）
   - 两种安装包功能完全相同，选择其一即可
2. 运行安装包，选择需要安装的组件（主程序为必选，6 个外部工具为可选，默认全部安装）
3. 安装后从开始菜单或桌面快捷方式启动 Z-ToolKit

> MSI 格式适合企业部署，EXE 格式适合个人使用。两种安装包均静默安装所需运行时，不重启系统。

---

## 一、项目简介

Z-ToolKit 是基于 Python 3.13 + tkinter/ttk 构建的桌面工具集，采用插件式架构：主程序负责加载 `Add/` 目录下的业务模块，统一管理外部 exe 工具、pip 依赖、配置持久化、日志显示和标签页布局。模块开发者只需在 `Add/` 下创建文件夹形式的模块包，即可被主程序自动加载。

- 主程序入口：`Z-ToolKit.py`
- 业务模块目录：`Add/`（每个模块一个中文命名的文件夹）
- 公共组件包：`Add/common/`（TabModule 基类、文件选择器、编码选项面板等）
- 外部工具目录：`Tools/`（ffmpeg、mkvmerge 等，不入库，见 .gitignore）

## 二、功能特性

| 模块 | 功能说明 | 外部工具依赖 |
|------|----------|-------------|
| 符号链接创建 | 批量创建符号链接，支持拖放操作，自动请求管理员权限 | - |
| 动漫自动分类 | 按番剧名规则自动分类视频文件 | - |
| 重复文件检查 | 基于 SHA256 哈希检测重复文件 | 7z |
| 视频编码转换 | H.264/H.265/AV1/VP9/H.266 编码转换，CRF 质量控制 | ffmpeg, ffprobe |
| 视频缩放 | 多种缩放算法（Lanczos/Bicubic/Bilinear），保持宽高比 | ffmpeg, ffprobe |
| 视频分辨率检查 | 批量检测视频分辨率和帧率 | ffprobe |
| 字幕转换 | ASS/SRT 字幕格式互转，简繁转换 | - |
| 字幕导出 | 从 MKV 视频提取内嵌字幕轨 | mkvextract |
| 字幕内封(MKV) | 将外挂字幕和字体内封到 MKV | mkvmerge |
| 字幕删除 | 移除 MKV 视频中的字幕轨 | mkvmerge |
| 字幕子集化 | ASS 字体子集化，减小字体体积 | mkvextract, mkvmerge, hb-subset |
| SRT转ASS | SRT 字幕转 ASS 格式，支持样式自定义 | - |
| M3U8合并 | 合并 M3U8 流媒体片段为完整视频 | ffmpeg |

## 三、目录结构

```
Z-ToolKit/                         ← 仓库根目录
├── README.md                      ← 本文档
├── Z-ToolKit.py                   ← 主程序入口（加载模块、管理工具、配置持久化）
├── Add/                           ← 业务模块目录
│   ├── common/                    ← 公共组件包
│   │   ├── tab_module.py          ← TabModule 基类
│   │   ├── scrollable_container.py ← 可滚动容器
│   │   ├── file_selector.py       ← 统一文件选择器
│   │   ├── encoding_options_panel.py ← 视频编码选项面板
│   │   ├── pageable_notebook.py   ← 可翻页标签页组件
│   │   ├── treeview_helpers.py    ← 可滚动 Treeview 工具
│   │   └── utils.py               ← format_size / sanitize_filename / ...
│   ├── module_base.py             ← 兼容层（重导出 common 包）
│   └── [模块名]/                  ← 各业务模块（文件夹形式，中文命名）
└── Tools/                         ← 外部工具目录（不入库，见 .gitignore）
    ├── 7z/                        ← 7z.exe + 7z.dll
    ├── ffmpeg/                    ← ffmpeg.exe + 依赖 DLL
    ├── ffprobe/                   ← ffprobe.exe + 依赖 DLL
    ├── mkvextract/                ← mkvextract.exe（静态链接）
    ├── mkvmerge/                  ← mkvmerge.exe（静态链接）
    └── hb-subset/                 ← hb-subset.exe
```

### 从源码恢复开发环境

**前提条件**：Python 3.13+、pip

```bat
:: 1. 克隆仓库
git clone https://github.com/zsz-of/Z-ToolKit.git
cd Z-ToolKit

:: 2. 安装 Python 依赖
pip install requests chardet tkinterdnd2 fontTools send2trash

:: 3. 准备外部工具（下载地址见下方"开源引用"章节）
::    将工具放入 Tools\ 目录，结构如下：
::    Tools\7z\7z.exe
::    Tools\ffmpeg\ffmpeg.exe
::    Tools\ffprobe\ffprobe.exe
::    Tools\mkvextract\mkvextract.exe
::    Tools\mkvmerge\mkvmerge.exe
::    Tools\hb-subset\hb-subset.exe

:: 4. 运行
python Z-ToolKit.py
```

#### 国内镜像加速

```bat
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple requests chardet tkinterdnd2 fontTools send2trash
```

#### 开发模式热更新

脚本模式下修改 `Add/` 中的模块代码后，重启程序即可生效。

## 四、运行方式

```bat
python Z-ToolKit.py
```

- 首次运行：主程序自动加载 `Add/` 下所有模块，按 `TAB_ORDER` 排序显示为标签页。
- 缺少必需 exe 或 pip 依赖的模块：标签页显示居中提示，引导用户前往"外部工具"选项卡补全。
- 配置文件：`%USERPROFILE%\.zAPP\video_tool_config.json`

### 依赖

```bat
pip install requests chardet tkinterdnd2 fontTools send2trash
```

## 五、配置位置

| 内容 | 路径 |
|------|------|
| 用户设置 | `%USERPROFILE%\.zAPP\video_tool_config.json` |
| 外部工具配置 | `%USERPROFILE%\.zAPP\video_tool_config.json`（同一文件） |

> 程序退出时自动保存配置；配置文件读取失败不报错，静默使用默认值。

## 六、开源引用（致谢）

| 项目 | 用途 | 仓库 |
|------|------|------|
| FFmpeg | 视频编码转换/缩放/处理 | <https://github.com/FFmpeg/FFmpeg> |
| MKVToolNix | MKV 字幕提取/合并 | <https://gitlab.com/mbunkus/mkvtoolnix> |
| HarfBuzz | 字体子集化 (hb-subset) | <https://github.com/harfbuzz/harfbuzz> |
| 7-Zip | 压缩/哈希计算 | <https://github.com/ip7z/7zip> |
| requests | HTTP 请求（字幕转换） | <https://github.com/psf/requests> |
| chardet | 编码检测（SRT转ASS） | <https://github.com/chardet/chardet> |
| tkinterdnd2 | Tkinter 拖放支持 | <https://github.com/pmgagnon/tkinterdnd2> |
| fonttools | 字体处理（子集化） | <https://github.com/fonttools/fonttools> |
| Send2Trash | 回收站删除（子集化） | <https://github.com/arsenetar/send2trash> |
