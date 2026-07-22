# -*- coding: utf-8 -*-
"""生成 WiX v4 格式的 .wxs 文件，遍历 Application 目录自动生成所有文件组件。

修复要点：
1. 正确生成嵌套 <Directory> 结构（旧版只生成叶子目录，中间目录缺失）
2. 移除所有 Guid="*"（WiX v4 基于 Component Id 自动生成稳定 GUID，避免同名文件冲突）
3. WiX v4 语法：AllowAbsent="no" 替代 Absent="disallow"
4. WiX v4 UI：使用 xmlns:ui 命名空间 + <ui:WixUI> 替代 <UIRef>
"""

import os

APP_DIR = r"d:\Code\Program\Z-ToolKit\Application"
OUTPUT_FILE = r"d:\Code\Program\Z-ToolKit\Installer\MSI\Z-ToolKit.wxs"

# UpgradeCode（固定 GUID，用于升级检测）
UPGRADE_CODE = "7B3A5F2E-1D4C-4B6E-9F8A-3E5D7C2B1A09"

# Tools 子目录 → (Feature Id, Feature Title)
# 每个 Tools 子目录作为一个可选安装特性
TOOLS_FEATURE_MAP = {
    os.path.join("Tools", "7z"):         ("Tools7z",        "7z 压缩工具"),
    os.path.join("Tools", "ffmpeg"):     ("ToolsFfmpeg",    "ffmpeg 视频处理"),
    os.path.join("Tools", "ffprobe"):    ("ToolsFfprobe",   "ffprobe 视频探测"),
    os.path.join("Tools", "hb-subset"):  ("ToolsHbSubset",  "hb-subset 字体子集化"),
    os.path.join("Tools", "mkvextract"): ("ToolsMkvextract","mkvextract 字幕提取"),
    os.path.join("Tools", "mkvmerge"):   ("ToolsMkvmerge",  "mkvmerge MKV 合并"),
}


def esc(s):
    """XML 属性转义"""
    return (s.replace("&", "&amp;").replace('"', "&quot;")
             .replace("<", "&lt;").replace(">", "&gt;"))


# ========== 目录树构建 ==========

class DirNode:
    """目录树节点"""
    def __init__(self, name, rel_path):
        self.name = name          # 目录名（如 "_internal"）
        self.rel_path = rel_path  # 相对于 APP_DIR 的路径（如 "_internal\certifi"）
        self.children = {}        # name -> DirNode
        self.files = []           # 文件名列表
        self.dir_id = None        # WiX Directory Id（后续分配）


def build_tree():
    """遍历 APP_DIR 构建完整的目录树"""
    root = DirNode("Z-ToolKit", ".")
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        rel = os.path.relpath(dirpath, APP_DIR)
        if rel == ".":
            node = root
        else:
            parts = rel.split(os.sep)
            node = root
            current = ""
            for part in parts:
                current = os.path.join(current, part) if current else part
                if part not in node.children:
                    node.children[part] = DirNode(part, current)
                node = node.children[part]
        node.files = sorted(filenames)
        dirnames.sort()  # 保证遍历顺序一致
    return root


def assign_dir_ids(root):
    """为所有目录节点分配唯一的 WiX Directory Id"""
    root.dir_id = "APPDIR"

    # 顶层已知目录使用语义化 Id
    top_level_ids = {
        "_internal": "InternalDir",
        "Add":       "AddDir",
        "Tools":     "ToolsDir",
    }
    for rel, (feat_id, _) in TOOLS_FEATURE_MAP.items():
        top_level_ids[rel] = f"{feat_id}Dir"

    counter = [0]

    def walk(node):
        for name in sorted(node.children.keys()):
            child = node.children[name]
            if child.rel_path in top_level_ids:
                child.dir_id = top_level_ids[child.rel_path]
            else:
                counter[0] += 1
                child.dir_id = f"dir_{counter[0]:04d}"
            walk(child)

    walk(root)


# ========== XML 生成 ==========

def gen_directory_xml(node, indent=6):
    """递归生成嵌套 <Directory> 元素"""
    lines = []
    pad = " " * indent
    for name in sorted(node.children.keys()):
        child = node.children[name]
        if child.children:
            lines.append(f'{pad}<Directory Id="{child.dir_id}" Name="{esc(child.name)}">')
            lines.extend(gen_directory_xml(child, indent + 2))
            lines.append(f'{pad}</Directory>')
        else:
            lines.append(f'{pad}<Directory Id="{child.dir_id}" Name="{esc(child.name)}" />')
    return lines


def collect_components(node, counter, main_comps, tools_comps):
    """递归收集所有文件组件，按 Feature 分组"""
    for f in node.files:
        counter[0] += 1
        comp_id = f"comp_{counter[0]:05d}"
        file_id = f"file_{counter[0]:05d}"

        if node.rel_path == ".":
            full_rel = f
        else:
            full_rel = os.path.join(node.rel_path, f)
        source = f"$(var.AppDir)\\{full_rel}"

        comp_xml = (
            f'      <Component Id="{comp_id}" Directory="{node.dir_id}">\n'
            f'        <File Id="{file_id}" Source="{esc(source)}" KeyPath="yes" />\n'
            f'      </Component>'
        )

        # 判断属于哪个 Feature
        assigned = False
        if node.rel_path.startswith("Tools"):
            parts = node.rel_path.split(os.sep)
            if len(parts) >= 2:
                tool_key = os.path.join(parts[0], parts[1])
                if tool_key in TOOLS_FEATURE_MAP:
                    feat_id = TOOLS_FEATURE_MAP[tool_key][0]
                    tools_comps.setdefault(feat_id, []).append(comp_xml)
                    assigned = True
        if not assigned:
            main_comps.append(comp_xml)

    for name in sorted(node.children.keys()):
        collect_components(node.children[name], counter, main_comps, tools_comps)


# ========== 主生成逻辑 ==========

root = build_tree()
assign_dir_ids(root)

counter = [0]
main_components = []
tools_components = {}  # feat_id -> [comp_xml, ...]
collect_components(root, counter, main_components, tools_components)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    f.write('<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"\n')
    f.write('     xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui">\n')
    f.write(f'  <Package Name="Z-ToolKit" Manufacturer="zsz" Version="1.0.0" '
            f'UpgradeCode="{{{UPGRADE_CODE}}}" Language="2052" Codepage="936">\n')
    f.write('    <SummaryInformation Description="Z-ToolKit 安装包" />\n')
    f.write('    <MajorUpgrade DowngradeErrorMessage="已安装了更新版本的 Z-ToolKit。" />\n')
    f.write('    <Media Id="1" Cabinet="ZToolKit.cab" EmbedCab="yes" />\n')
    f.write('\n')

    # ---- 目录结构 ----
    f.write('    <!-- 目录结构（完整嵌套） -->\n')
    f.write('    <StandardDirectory Id="ProgramFiles64Folder">\n')
    f.write('      <Directory Id="APPDIR" Name="Z-ToolKit">\n')
    for line in gen_directory_xml(root, 8):
        f.write(line + '\n')
    f.write('      </Directory>\n')
    f.write('    </StandardDirectory>\n')
    f.write('\n')

    # ---- 快捷方式目录 ----
    f.write('    <!-- 开始菜单快捷方式 -->\n')
    f.write('    <StandardDirectory Id="ProgramMenuFolder">\n')
    f.write('      <Directory Id="StartMenuDir" Name="Z-ToolKit" />\n')
    f.write('    </StandardDirectory>\n')
    f.write('\n')
    f.write('    <!-- 桌面快捷方式 -->\n')
    f.write('    <StandardDirectory Id="DesktopFolder" />\n')
    f.write('\n')

    # ---- 主程序文件组件 ----
    f.write('    <!-- 主程序文件组件（必需） -->\n')
    f.write('    <ComponentGroup Id="MainComponents">\n')
    for comp in main_components:
        f.write(comp + '\n')
    f.write('    </ComponentGroup>\n\n')

    # ---- 各 Tools 子目录组件 ----
    for rel, (feat_id, feat_title) in TOOLS_FEATURE_MAP.items():
        comps = tools_components.get(feat_id, [])
        if not comps:
            continue
        f.write(f'    <!-- {feat_title} 组件 -->\n')
        f.write(f'    <ComponentGroup Id="{feat_id}Components">\n')
        for comp in comps:
            f.write(comp + '\n')
        f.write('    </ComponentGroup>\n\n')

    # ---- 快捷方式组件 ----
    f.write('    <!-- 快捷方式组件 -->\n')
    f.write('    <ComponentGroup Id="ShortcutComponents">\n')
    f.write('      <Component Id="StartMenuShortcut" Directory="StartMenuDir">\n')
    f.write('        <Shortcut Id="StartMenuShortcut" Name="Z-ToolKit" '
            'Target="[APPDIR]Z-ToolKit.exe" WorkingDirectory="APPDIR" />\n')
    f.write('        <RemoveFolder Id="RemoveStartMenuDir" Directory="StartMenuDir" On="uninstall" />\n')
    f.write('        <RegistryValue Root="HKCU" Key="Software\\zsz\\Z-ToolKit" Name="installed" '
            'Type="integer" Value="1" KeyPath="yes" />\n')
    f.write('      </Component>\n')
    f.write('      <Component Id="DesktopShortcut" Directory="DesktopFolder">\n')
    f.write('        <Shortcut Id="DesktopShortcut" Name="Z-ToolKit" '
            'Target="[APPDIR]Z-ToolKit.exe" WorkingDirectory="APPDIR" />\n')
    f.write('        <RemoveFolder Id="RemoveDesktopShortcut" Directory="DesktopFolder" On="uninstall" />\n')
    f.write('        <RegistryValue Root="HKCU" Key="Software\\zsz\\Z-ToolKit" Name="desktop" '
            'Type="integer" Value="1" KeyPath="yes" />\n')
    f.write('      </Component>\n')
    f.write('    </ComponentGroup>\n\n')

    # ---- Features ----
    f.write('    <!-- 安装特性 -->\n')
    f.write('    <Feature Id="Main" Title="Z-ToolKit 主程序（必需）" Level="1" '
            'AllowAbsent="no" Description="主程序及运行时依赖">\n')
    f.write('      <ComponentGroupRef Id="MainComponents" />\n')
    f.write('      <ComponentGroupRef Id="ShortcutComponents" />\n')
    f.write('    </Feature>\n')

    for rel, (feat_id, feat_title) in TOOLS_FEATURE_MAP.items():
        if feat_id not in tools_components:
            continue
        f.write(f'    <Feature Id="{feat_id}" Title="{esc(feat_title)}" Level="1" '
                f'Description="{esc(feat_title)}">\n')
        f.write(f'      <ComponentGroupRef Id="{feat_id}Components" />\n')
        f.write(f'    </Feature>\n')
    f.write('\n')

    # ---- 安装后启动（可选） ----
    f.write('    <!-- 安装后启动程序（可选） -->\n')
    f.write('    <Property Id="WIXUI_EXITDIALOGOPTIONALCHECKBOXTEXT" Value="启动 Z-ToolKit" />\n')
    f.write('    <Property Id="WIXUI_EXITDIALOGOPTIONALCHECKBOX" Value="1" />\n')
    f.write('    <CustomAction Id="LaunchApp" Directory="APPDIR" '
            'ExeCommand="[APPDIR]Z-ToolKit.exe" Return="asyncNoWait" />\n')
    f.write('    <InstallExecuteSequence>\n')
    f.write('      <Custom Action="LaunchApp" After="InstallFinalize" '
            'Condition="WIXUI_EXITDIALOGOPTIONALCHECKBOX = 1 and NOT Installed" />\n')
    f.write('    </InstallExecuteSequence>\n')
    f.write('\n')

    # ---- UI ----
    f.write('    <!-- 安装界面 -->\n')
    f.write('    <ui:WixUI Id="WixUI_FeatureTree" />\n')

    f.write('  </Package>\n')
    f.write('</Wix>\n')

print(f"Generated: {OUTPUT_FILE}")
print(f"Total components: {counter[0]}")
print(f"  Main: {len(main_components)}")
for rel, (feat_id, feat_title) in TOOLS_FEATURE_MAP.items():
    print(f"  {feat_title}: {len(tools_components.get(feat_id, []))}")
