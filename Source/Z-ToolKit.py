#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Z-ToolKit
主程序：负责 GUI 框架、日志标签页、模块加载与滚动支持
各功能模块位于 Add 文件夹，启动时自动加载
"""

import os
import sys
import re
import json
import ctypes
import threading
import importlib
import datetime
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ========== Windows 高 DPI 适配（必须在创建窗口前执行）==========
if os.name == 'nt':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

# ========== 隐藏命令提示符窗口 ==========
if os.name == 'nt' and '--console' not in sys.argv:
    try:
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass

# ========== zAPP 配置系统 ==========

def _get_zapp_dir():
    zapp_dir = os.path.join(os.path.expanduser("~"), ".zAPP")
    os.makedirs(zapp_dir, exist_ok=True)
    return zapp_dir

def _load_config(filename, defaults=None):
    path = os.path.join(_get_zapp_dir(), filename)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return defaults if defaults is not None else {}

def _save_config(filename, data):
    try:
        zapp_dir = _get_zapp_dir()
        path = os.path.join(zapp_dir, filename)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except OSError:
        pass

def _delete_config(filename):
    """删除指定配置文件"""
    path = os.path.join(_get_zapp_dir(), filename)
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False

def _register_config(filename, program_name):
    """在 _registry.json 中注册配置文件"""
    registry_path = os.path.join(_get_zapp_dir(), "_registry.json")
    registry = {}
    if os.path.exists(registry_path):
        try:
            with open(registry_path, 'r', encoding='utf-8') as f:
                registry = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    registry[filename] = program_name
    try:
        tmp_path = registry_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, registry_path)
    except OSError:
        pass

CONFIG_FILE = "video_tool_config.json"
_register_config(CONFIG_FILE, "Z-ToolKit")

# ========== 路径常量 ==========
# 项目根目录
# - Python 脚本运行：Z-ToolKit.py 所在目录
# - PyInstaller 打包后：EXE 所在目录（Add/ 和 Tools/ 放在此处）
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
# 外部 exe 工具目录（每种工具一个子文件夹，命名为 exe 名）
TOOLS_DIR = os.path.join(PROJECT_ROOT, "Tools")
# 模块加载目录
ADD_DIR = os.path.join(PROJECT_ROOT, "Add")

# 确保 Add 目录在 sys.path 中（用于导入 common 包和模块）
if ADD_DIR not in sys.path:
    sys.path.insert(0, ADD_DIR)

# 尝试导入 tkinterdnd2（可选，主程序不依赖）
try:
    from tkinterdnd2 import TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    TKDND_AVAILABLE = False
    TkinterDnD = tk

# 导入可翻页标签页组件
try:
    from common.pageable_notebook import PageableNotebook
    PAGEABLE_NOTEBOOK_AVAILABLE = True
except ImportError:
    PAGEABLE_NOTEBOOK_AVAILABLE = False
    PageableNotebook = None

# 导入公共组件（ScrollableContainer 从 common 包加载）
try:
    from common.scrollable_container import ScrollableContainer
    SCROLLABLE_CONTAINER_AVAILABLE = True
except ImportError:
    SCROLLABLE_CONTAINER_AVAILABLE = False
    ScrollableContainer = None


# ========== 主程序接口（提供给模块使用）==========

class HostInterface:
    """
    主程序接口：为功能模块提供服务
    模块通过此接口与主程序交互，避免直接访问主程序内部状态
    """
    def __init__(self, app):
        self._app = app

    @property
    def root(self):
        """获取根窗口"""
        return self._app.root

    def after(self, ms, callback, *args):
        """在主线程调度回调"""
        return self._app.root.after(ms, callback, *args)

    def log_message(self, level, message, source_tab="系统"):
        """记录日志到日志标签页"""
        self._app.log_message(level, message, source_tab)

    def clear_error_log(self, tab_name=None):
        """清空错误日志"""
        self._app.clear_error_log(tab_name)

    def set_processing_state(self, tab_widget, is_processing, has_error=False):
        """设置选项卡的处理状态"""
        self._app.set_tab_processing(tab_widget, is_processing, has_error)

    def switch_to_error_log(self):
        """切换到错误日志选项卡"""
        self._app.switch_to_error_log()

    def show_error(self, title, message):
        """显示错误对话框"""
        messagebox.showerror(title, message)

    def show_warning(self, title, message):
        """显示警告对话框"""
        messagebox.showwarning(title, message)

    def show_info(self, title, message):
        """显示信息对话框"""
        messagebox.showinfo(title, message)

    def get_exe_path(self, name):
        """获取外部 exe 路径（由主程序外部工具管理统一提供）

        参数:
            name: exe 名称（如 'ffmpeg'、'ffprobe'、'mkvextract'、'mkvmerge'、'hb-subset'）
        返回:
            exe 完整路径字符串，若未配置则返回 None
        """
        return self._app.get_exe_path(name)

    def refresh_exe_status(self):
        """刷新外部工具管理标签页的状态显示"""
        self._app.refresh_exe_status()

    def save_config_now(self):
        """请求主程序立即保存所有模块的配置到 zAPP

        适用于用户修改了重要配置（如目录路径）后需要立即持久化的场景，
        避免程序异常退出导致配置丢失。
        """
        self._app._save_last_config()

    def create_admin_request_button(self, parent, return_tab=None,
                                    text="请求管理员权限", **kwargs):
        """创建一个由主程序管理的管理员权限请求按钮

        按钮行为由主程序完全管理，模块不能干涉按钮的运行逻辑和可否点击状态：
        - 管理员模式下按钮自动禁用
        - 非管理员模式下按钮可点击
        - 点击后直接触发 Windows UAC（无需程序二次确认）
        - UAC 通过则保存配置并以管理员身份重启程序
        - UAC 未通过则弹出警告提示框说明用户未授权

        参数:
            parent: 按钮的父容器
            return_tab: 重启后跳转的选项卡名称；None 则不跳转
            text: 按钮文本（默认"请求管理员权限"）
            **kwargs: 传递给 ttk.Button 的其他参数（如 width、style 等）

        返回:
            ttk.Button 实例
        """
        return self._app._create_admin_request_button(
            parent, return_tab, text, **kwargs)



# ========== 模块加载器 ==========

class ModuleLoader:
    """
    模块加载器：从 Add 文件夹加载功能模块
    每个模块文件需定义 MODULE_CLASS 变量指向 TabModule 子类
    """
    def __init__(self, host, add_folder):
        self.host = host
        self.add_folder = add_folder
        self.modules = []  # [(module_instance, module_class)]

    def load_all(self):
        """加载 Add 文件夹中的所有模块

        支持两种模块形式：
        1. 文件夹形式（package）：Add/<module_name>/__init__.py（优先）
        2. 单文件形式：Add/<module_name>.py

        跳过以下内容：
        - 以下划线或点开头的项
        - module_base.py / common（公共模块包，非业务模块）
        - 已存在文件夹形式的同名 .py 文件（避免重复加载）
        """
        if not os.path.isdir(self.add_folder):
            return []

        results = []
        # 确保 Add 文件夹在 sys.path 中
        if self.add_folder not in sys.path:
            sys.path.insert(0, self.add_folder)

        # 收集所有模块名（去重：文件夹优先于 .py 文件）
        folder_modules = set()
        file_modules = set()
        for entry in sorted(os.listdir(self.add_folder)):
            if entry.startswith('_') or entry.startswith('.'):
                continue
            full_path = os.path.join(self.add_folder, entry)
            if os.path.isdir(full_path):
                # 文件夹形式：必须有 __init__.py
                if os.path.isfile(os.path.join(full_path, '__init__.py')):
                    if entry in ('common', 'Trae-Backup', 'harfbuzz-win64'):
                        continue  # 公共模块包和资源目录不作为业务模块加载
                    folder_modules.add(entry)
            elif entry.endswith('.py'):
                module_name = entry[:-3]
                if module_name in ('module_base', '__init__'):
                    continue
                file_modules.add(module_name)

        # 文件夹形式优先，同名的 .py 文件被跳过
        all_module_names = sorted(folder_modules | (file_modules - folder_modules))

        for module_name in all_module_names:
            try:
                module = self._load_module(module_name)
                if module is None:
                    continue
                module_class = getattr(module, 'MODULE_CLASS', None)
                if module_class is None:
                    continue
                results.append((module_name, module_class))
            except Exception as e:
                # 模块加载失败记录到日志（但日志系统可能尚未初始化）
                import traceback
                err_msg = f"加载模块 {module_name} 失败: {e}\n{traceback.format_exc()}"
                print(err_msg, file=sys.stderr)
                try:
                    log_path = os.path.join(tempfile.gettempdir(), "Z-ToolKit-module-load-errors.log")
                    with open(log_path, "a", encoding="utf-8") as f:
                        import datetime
                        f.write(f"\n[{datetime.datetime.now()}] {err_msg}\n")
                except Exception:
                    pass

        return results

    def _load_module(self, module_name):
        """加载单个模块（common 包和 module_base 保持共享，不重新加载）"""
        try:
            # 仅移除目标模块（便于热重载），保留公共模块共享实例
            if module_name in sys.modules:
                del sys.modules[module_name]
            return importlib.import_module(module_name)
        except Exception as e:
            import traceback
            err_msg = f"导入模块 {module_name} 失败: {e}\n{traceback.format_exc()}"
            print(err_msg, file=sys.stderr)
            # --windowed 模式下 stderr 丢失，额外写入日志文件便于诊断
            try:
                log_path = os.path.join(tempfile.gettempdir(), "Z-ToolKit-module-load-errors.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    import datetime
                    f.write(f"\n[{datetime.datetime.now()}] {err_msg}\n")
            except Exception:
                pass
            return None


# ========== 主程序 ==========

class VideoProcessingTool:
    """Z-ToolKit 主类"""

    def __init__(self):
        self.root = tk.Tk() if not TKDND_AVAILABLE else TkinterDnD.Tk()
        title = "Z-ToolKit"
        if self._is_admin():
            title += "（管理员）"
        self.root.title(title)
        self.root.geometry("1200x800")

        # 主程序接口
        self.host = HostInterface(self)

        # 处理状态管理
        self.processing_tabs = {}  # 记录各选项卡的处理状态
        self.module_instances = {} # 选项卡 widget 到模块实例的映射
        self.tab_scroll_containers = {}  # 选项卡 widget 到滚动容器的映射
        self.current_tab = None

        # 外部 exe 路径管理（name -> path）
        self.exe_paths = {}
        # exe 需求列表（按模块收集，去重后保存）
        self.exe_requirements = []  # [(exe_name, [module_name, ...], is_optional), ...]
        # pip 依赖需求列表（按模块收集，去重后保存）
        self.pip_requirements = []  # [((install_name, import_name), [module_name, ...], is_optional), ...]

        # 修复高 DPI 下 Treeview 行高不缩放导致文字被裁切
        try:
            import tkinter.font as tkfont
            _style = ttk.Style()
            _default_font = tkfont.nametofont('TkDefaultFont')
            _linespace = _default_font.metrics()['linespace']
            _style.configure('Treeview', rowheight=_linespace + 4)
        except Exception:
            pass

        # 创建主界面
        self.create_main_ui()

        # 窗口关闭处理
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 窗口大小变化时检查滚动条
        self.root.bind("<Configure>", self._on_window_configure)

        # 加载上一次配置
        self._load_last_config()

    def _load_last_config(self):
        """从 zAPP 加载上次保存的配置并应用到模块"""
        try:
            cfg = _load_config(CONFIG_FILE)
            if not cfg:
                return
        except Exception:
            return

        # 配置会在模块构建 UI 后通过 load_config 应用
        self._pending_config = cfg

        # 加载 exe 路径配置并验证（每次启动都验证）
        exe_paths_cfg = cfg.get('_exe_paths', {})
        self._validate_exe_paths(exe_paths_cfg)
        # 验证后重新自动查找未配置的 exe（验证可能因 subprocess 超时等原因失败，
        # 需要重新查找以恢复自动查找匹配到的项目）
        self._auto_find_all_exes()
        # 刷新外部工具表格显示
        self.refresh_exe_status()

        # 应用日志级别过滤配置
        log_levels = cfg.get('_log_levels', {})
        if log_levels and hasattr(self, 'log_level_vars'):
            for level, var in self.log_level_vars.items():
                if level in log_levels:
                    var.set(log_levels[level])

    def _validate_exe_paths(self, exe_paths_cfg):
        """验证 exe 路径配置：检查文件是否存在，环境变量是否仍可用

        参数:
            exe_paths_cfg: dict[name, path] 上次保存的 exe 路径配置

        短名称形式（如 "ffmpeg"）验证通过后，用 _find_exe_in_path 的返回值替换，
        优先保存完整路径（Tools 目录或 PATH 中的实际文件路径），
        避免下游消费者用 Path(path).is_file() 检查短名称时误判为不存在。
        """
        self.exe_paths = {}
        for name, path in exe_paths_cfg.items():
            if not path:
                continue
            if path == name or path == name + '.exe':
                # 短名称形式（依赖 PATH），验证并升级为完整路径
                found = self._find_exe_in_path(name)
                if found:
                    self.exe_paths[name] = found
            else:
                # 完整路径形式，验证文件是否存在
                if os.path.isfile(path):
                    self.exe_paths[name] = path

    def _find_exe_in_path(self, name):
        """查找 exe 工具路径，查找优先级：
        1. Tools/<name>/<name>.exe（项目内置工具目录）
        2. PATH 环境变量中的短名称调用（ffmpeg/ffprobe）
        3. PATH 环境变量各目录中查找 exe 文件

        返回完整路径字符串，未找到则返回 None。
        """
        # 优先级 1: Tools 目录查找（Tools/<name>/<name>.exe）
        if TOOLS_DIR:
            for exe_name in (name + '.exe', name):
                tools_exe_path = os.path.join(TOOLS_DIR, name, exe_name)
                if os.path.isfile(tools_exe_path):
                    return tools_exe_path

        # 优先级 2: 短名称直接调用（适用于 PATH 中已存在的情况）
        try:
            import subprocess
            test_cmd = [name, '-version'] if name in ('ffmpeg', 'ffprobe') else None
            if test_cmd is not None:
                result = subprocess.run(test_cmd, capture_output=True, timeout=5,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    return name
        except Exception:
            pass

        # 优先级 3: 在 PATH 各目录中查找
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not path_dir:
                continue
            for exe_name in (name + '.exe', name):
                exe_path = os.path.join(path_dir, exe_name)
                if os.path.isfile(exe_path):
                    return exe_path
        return None

    def _collect_exe_requirements(self):
        """从所有模块收集 exe 需求，去重合并

        必需 exe 和可选 exe 分别收集。可选 exe 缺失时不阻止模块加载，
        仅在外部工具表格中显示提示。
        """
        req_map = {}       # exe_name -> set(module_name)（必需）
        optional_map = {}  # exe_name -> set(module_name)（可选）
        for module in self.module_instances.values():
            module_name = module.TAB_NAME
            for exe_name in getattr(module, 'EXE_REQUIREMENTS', []):
                req_map.setdefault(exe_name, set()).add(module_name)
            for exe_name in getattr(module, 'OPTIONAL_EXE_REQUIREMENTS', []):
                optional_map.setdefault(exe_name, set()).add(module_name)
        # 合并为有序列表，按 exe_name 排序，标注是否可选
        # [(exe_name, [module_names...], is_optional), ...]
        self.exe_requirements = (
            [(name, sorted(mods), False) for name, mods in sorted(req_map.items())]
            + [(name, sorted(mods), True) for name, mods in sorted(optional_map.items())]
        )

    def _collect_pip_requirements(self):
        """从所有模块收集 pip 依赖需求，去重合并（仅收集非内置库）

        必需依赖和可选依赖分别收集，可选依赖在外部工具标签页中标注"可选"。

        依赖声明支持两种形式：
        - 字符串 'numpy'（pip 名 = import 名）
        - 元组 ('opencv-python', 'cv2')（pip 名, import 名）

        内部统一转为元组 (install_name, import_name) 表示。
        """
        # Python 内置模块（不需要 pip 安装，用 import 名判断）
        STDLIB_MODULES = {
            'os', 'sys', 're', 'json', 'threading', 'subprocess', 'tempfile',
            'hashlib', 'time', 'sqlite3', 'random', 'string', 'difflib',
            'unicodedata', 'enum', 'typing', 'collections', 'pathlib',
            'shutil', 'stat', 'struct', 'concurrent', 'ctypes', 'importlib',
            'datetime', 'tkinter', 'winreg', 'glob', 'io', 'abc', 'copy',
            'functools', 'itertools', 'logging', 'math', 'queue', 'socket',
            'traceback', 'warnings', 'weakref', 'argparse', 'configparser',
        }

        def _normalize_dep(dep):
            """将依赖声明统一转为 (install_name, import_name) 元组"""
            if isinstance(dep, tuple):
                return (dep[0], dep[1])
            return (dep, dep)

        def _is_stdlib(dep):
            """判断依赖是否为标准库（用 import 名判断）"""
            return _normalize_dep(dep)[1] in STDLIB_MODULES

        # 必需依赖: (install_name, import_name) -> set(module_name)
        req_map = {}
        # 可选依赖: (install_name, import_name) -> set(module_name)
        optional_map = {}
        for module in self.module_instances.values():
            module_name = module.TAB_NAME
            for dep in getattr(module, 'PIP_DEPENDENCIES', []):
                if _is_stdlib(dep):
                    continue
                spec = _normalize_dep(dep)
                req_map.setdefault(spec, set()).add(module_name)
            for dep in getattr(module, 'OPTIONAL_PIP_DEPENDENCIES', []):
                if _is_stdlib(dep):
                    continue
                spec = _normalize_dep(dep)
                optional_map.setdefault(spec, set()).add(module_name)
        # 合并为有序列表，按 install_name 排序，标注是否可选
        # [((install_name, import_name), [module_names...], is_optional), ...]
        self.pip_requirements = (
            [(spec, sorted(mods), False) for spec, mods in sorted(req_map.items(), key=lambda x: x[0][0])]
            + [(spec, sorted(mods), True) for spec, mods in sorted(optional_map.items(), key=lambda x: x[0][0])]
        )

    def _check_pip_installed(self, dep):
        """检查 pip 依赖是否已安装

        参数:
            dep: 字符串（pip 名 = import 名）或元组 (install_name, import_name)
        返回:
            True 若 import 名可成功导入
        """
        import_name = dep[1] if isinstance(dep, tuple) else dep
        try:
            importlib.import_module(import_name)
            return True
        except ImportError:
            return False

    def get_exe_path(self, name):
        """获取外部 exe 路径。若未配置则返回 None"""
        return self.exe_paths.get(name)

    def refresh_exe_status(self):
        """刷新外部工具管理标签页的状态显示"""
        if hasattr(self, 'exe_tree') and self.exe_tree.winfo_exists():
            self._refresh_exe_tree()
        if hasattr(self, 'pip_tree') and self.pip_tree.winfo_exists():
            self._refresh_pip_tree()

    def _refresh_exe_tree(self):
        """刷新外部工具表格"""
        for item in self.exe_tree.get_children():
            self.exe_tree.delete(item)
        for exe_name, modules, is_optional in self.exe_requirements:
            path = self.exe_paths.get(exe_name)
            display_name = f"{exe_name} (可选)" if is_optional else exe_name
            if path:
                status = "已找到"
                tags = ('found',)
            elif is_optional:
                status = "未找到"
                tags = ('optional_missing',)
            else:
                status = "未找到"
                tags = ('not_found',)
            modules_str = ', '.join(modules)
            self.exe_tree.insert('', tk.END,
                                 values=(display_name, path or '-', status, modules_str),
                                 tags=tags)

    def _save_last_config(self):
        """保存当前配置到 zAPP（嵌套结构：每个模块独立键）

        以磁盘上的现有配置为基础合并：仅更新本次会话中已构建 UI 的模块
        （这些模块的配置已通过 load_config 恢复到内存）。
        未打开的模块跳过保存，保留磁盘原值，避免内存中的默认初始值
        覆盖掉之前保存的路径等记忆内容。
        """
        cfg = _load_config(CONFIG_FILE) or {}
        for module in self.module_instances.values():
            if not getattr(module, '_ui_built', False):
                continue  # 未打开过的模块：保留磁盘上的原有配置
            try:
                module.save_config(cfg)
            except Exception:
                pass
        # 保存日志级别过滤
        if hasattr(self, 'log_level_vars'):
            cfg['_log_levels'] = {level: var.get() for level, var in self.log_level_vars.items()}
        # 保存 exe 路径配置
        cfg['_exe_paths'] = dict(self.exe_paths)
        try:
            _save_config(CONFIG_FILE, cfg)
        except Exception:
            pass

    def clear_selected_memory(self, selected_modules):
        """清除指定模块的记忆

        参数:
            selected_modules: list[TabModule] 需要清除记忆的模块实例列表
        """
        if not selected_modules:
            return

        # 重新加载当前配置
        cfg = _load_config(CONFIG_FILE) or {}

        # 清除选中模块的配置
        for module in selected_modules:
            config_key = getattr(module, 'CONFIG_KEY', module.TAB_NAME)
            if config_key in cfg:
                del cfg[config_key]
            try:
                module.clear_memory()
            except Exception:
                pass

        # 保存更新后的配置
        try:
            _save_config(CONFIG_FILE, cfg)
        except Exception:
            pass

    def _auto_find_all_exes(self):
        """自动查找所有需要的 exe（在 PATH 中查找）"""
        for exe_name, _modules, _is_optional in self.exe_requirements:
            if exe_name in self.exe_paths and self.exe_paths[exe_name]:
                continue  # 已配置则跳过
            found = self._find_exe_in_path(exe_name)
            if found:
                self.exe_paths[exe_name] = found

    def clear_exe_paths_memory(self):
        """清除外部工具路径配置记忆（单独清除 _exe_paths，不影响模块配置）"""
        # 重新加载当前配置
        cfg = _load_config(CONFIG_FILE) or {}
        # 删除 _exe_paths 键
        if '_exe_paths' in cfg:
            del cfg['_exe_paths']
            try:
                _save_config(CONFIG_FILE, cfg)
            except Exception:
                pass
        # 清空内存中的 exe 路径并重新自动查找
        self.exe_paths = {}
        self._auto_find_all_exes()
        self.refresh_exe_status()

    def create_main_ui(self):
        """创建主界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题栏
        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 5))

        title_label = ttk.Label(title_frame, text="Z-ToolKit", font=("Microsoft YaHei UI", 16, "bold"))
        title_label.pack(side=tk.LEFT)

        # 创建选项卡控件（可翻页标签页，宽度不足时自动分页）
        if PAGEABLE_NOTEBOOK_AVAILABLE:
            self.notebook = PageableNotebook(main_frame)
        else:
            self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # 绑定选项卡切换事件
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # 初始化错误日志系统
        self.error_log_entries = []
        self.error_log_lock = threading.Lock()

        # 加载功能模块
        loader = ModuleLoader(self.host, ADD_DIR)
        modules = loader.load_all()

        # 按 TAB_ORDER 排序
        modules.sort(key=lambda x: getattr(x[1], 'TAB_ORDER', 100))

        for module_name, module_class in modules:
            self._create_module_tab(module_name, module_class)

        # 收集所有模块的 exe 需求（去重合并）
        self._collect_exe_requirements()
        # 收集所有模块的 pip 依赖需求（去重合并）
        self._collect_pip_requirements()

        # 创建外部工具管理选项卡（放在错误日志前）
        self.create_external_tools_tab()

        # 创建记忆选项卡（放在外部工具和错误日志之间）
        self.create_memory_clear_tab()

        # 创建错误日志选项卡（放在最后）
        self.create_error_log_tab()

    def _create_module_tab(self, module_name, module_class):
        """为模块创建标签页（UI 延迟构建）"""
        tab_name = getattr(module_class, 'TAB_NAME', module_name)
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=tab_name)

        # 创建模块实例
        module_instance = module_class(self.host)
        module_instance.tab_widget = tab
        self.module_instances[tab] = module_instance

        # 创建占位提示（首次打开时才构建 UI）
        placeholder = ttk.Frame(tab)
        placeholder.pack(fill=tk.BOTH, expand=True)
        ttk.Label(placeholder, text=f"点击此标签页加载 [{tab_name}]...",
                 font=("Microsoft YaHei UI", 11)).pack(expand=True)
        module_instance._placeholder = placeholder

    def _build_module_ui(self, tab):
        """构建模块 UI（首次打开标签页时调用）

        标签页访问控制：检查模块所需的 exe 工具和 pip 依赖，
        缺失时显示居中提示页和"转到外部工具选项卡"按钮，不加载模块；
        工具检测通过才加载模块。每次切换到该标签页都会重新检查。
        """
        module_instance = self.module_instances.get(tab)
        if module_instance is None or module_instance._ui_built:
            return

        # 销毁占位提示
        if hasattr(module_instance, '_placeholder') and module_instance._placeholder is not None:
            module_instance._placeholder.destroy()
            module_instance._placeholder = None

        # 销毁之前的提示页（如果存在，每次切换都会重新检查）
        if hasattr(module_instance, '_missing_tools_frame') and module_instance._missing_tools_frame is not None:
            module_instance._missing_tools_frame.destroy()
            module_instance._missing_tools_frame = None

        # 检查 exe 工具是否已配置
        missing_exes = []
        for exe_name in getattr(module_instance, 'EXE_REQUIREMENTS', []):
            if not self.get_exe_path(exe_name):
                missing_exes.append(exe_name)

        # 检查 pip 依赖是否已安装
        missing_deps = self._check_pip_dependencies(module_instance)

        if missing_exes or missing_deps:
            # 显示居中提示页
            prompt_frame = ttk.Frame(tab)
            prompt_frame.pack(fill=tk.BOTH, expand=True)
            module_instance._missing_tools_frame = prompt_frame

            # 构建提示文本
            lines = [f"模块 [{module_instance.TAB_NAME}] 缺少必要依赖，无法加载：\n"]
            if missing_exes:
                lines.append("\n缺失的外部工具：")
                for exe in missing_exes:
                    lines.append(f"  - {exe}")
            if missing_deps:
                lines.append("\n缺失的 pip 依赖库：")
                for dep in missing_deps:
                    lines.append(f"  - {dep}")
            lines.append("\n\n请先到「外部工具」选项卡补全上述依赖，")
            lines.append("补全后再次点击本标签页即可加载模块。")

            ttk.Label(prompt_frame, text="".join(lines),
                     font=("Microsoft YaHei UI", 11), foreground="red", justify=tk.CENTER).pack(expand=True, padx=20, pady=20)

            # "转到外部工具选项卡"按钮
            ttk.Button(prompt_frame, text="转到外部工具选项卡",
                      command=self._switch_to_external_tools_tab).pack(pady=(0, 20))

            # 记录到日志
            missing_all = missing_exes + missing_deps
            self.log_message('warning',
                f"模块 [{module_instance.TAB_NAME}] 缺少依赖: {', '.join(missing_all)}",
                "系统")
            # 不标记 _ui_built = True，下次切换会重新检查
            return

        # 创建可滚动容器
        scroll_container = ScrollableContainer(tab)
        scroll_container.pack(fill=tk.BOTH, expand=True)
        self.tab_scroll_containers[tab] = scroll_container

        # 在滚动容器内构建模块 UI
        inner_frame = scroll_container.get_inner_frame()
        try:
            module_instance.build_ui(inner_frame)
            module_instance._ui_built = True
            # 应用待加载的配置（只传递该模块的子字典）
            if hasattr(self, '_pending_config'):
                try:
                    config_key = getattr(module_instance, 'CONFIG_KEY', module_instance.TAB_NAME)
                    module_cfg = self._pending_config.get(config_key, {})
                    if module_cfg:
                        module_instance.load_config(module_cfg)
                except Exception:
                    pass
            # 延迟检查滚动条
            self.root.after(100, lambda: scroll_container.check_scroll_needed())
        except Exception as e:
            self.log_message('error',
                f"构建模块 [{module_instance.TAB_NAME}] UI 失败: {e}",
                "系统")
            messagebox.showerror("错误", f"加载模块 [{module_instance.TAB_NAME}] 失败:\n{e}")
            module_instance._ui_built = True  # 避免重复尝试

    def _switch_to_external_tools_tab(self):
        """切换到外部工具选项卡（跨页查找）"""
        try:
            self.notebook.select_by_text('外部工具')
        except Exception:
            pass

    def _check_pip_dependencies(self, module_instance):
        """检查模块的 pip 依赖是否已安装

        返回缺失依赖的安装名列表（用于提示用户）。
        """
        missing = []
        for dep in getattr(module_instance, 'PIP_DEPENDENCIES', []):
            if not self._check_pip_installed(dep):
                install_name = dep[0] if isinstance(dep, tuple) else dep
                missing.append(install_name)
        return missing

    def on_tab_changed(self, event):
        """处理选项卡切换事件"""
        new_tab = self.notebook.select()
        if not new_tab:
            return
        tab_text = self.notebook.tab(new_tab, "text")

        # 将 new_tab（字符串）转换为 widget 对象以便与 processing_tabs 的键比较
        try:
            new_tab_widget = self.notebook.nametowidget(new_tab)
        except Exception:
            new_tab_widget = None

        # 检查是否有正在处理的选项卡（非当前目标）
        processing_tab_id = None
        for tab_id, is_processing in self.processing_tabs.items():
            if is_processing and tab_id != new_tab_widget:
                processing_tab_id = tab_id
                break

        # 错误日志选项卡可自由切换（不受处理中限制），便于查看处理错误
        if tab_text == "错误日志":
            self._notify_deactivated()
            self.current_tab = new_tab
            return

        if processing_tab_id is not None:
            # 有正在处理的选项卡，弹出错误提示并切回
            # 去除标题中的状态图标（▶️/❗）以显示原始名称
            raw_title = self.notebook.tab(processing_tab_id, "text")
            clean_title = re.sub(r'^[\u25B6\uFE0F\u2757\s]+', '', raw_title)
            messagebox.showerror(
                "操作受限",
                f"选项卡「{clean_title}」正在处理中。\n\n"
                "请等待当前任务处理完成后再切换。",
                parent=self.root
            )
            # 切回正在处理的选项卡（会再次触发 on_tab_changed，但 new_tab 即处理中选项卡，不再阻止）
            self.notebook.select(processing_tab_id)
            return

        # 通知旧标签页失活
        self._notify_deactivated()
        self.current_tab = new_tab

        # 构建 UI（如果尚未构建）并触发激活回调
        try:
            tab_widget = self.notebook.nametowidget(new_tab)
            module_instance = self.module_instances.get(tab_widget)
            if module_instance is not None:
                if not module_instance._ui_built:
                    self._build_module_ui(tab_widget)
                if module_instance._ui_built:
                    try:
                        module_instance.on_tab_activated()
                    except Exception:
                        pass
                # 检查滚动条
                if tab_widget in self.tab_scroll_containers:
                    self.root.after(50, lambda: self.tab_scroll_containers[tab_widget].check_scroll_needed())
            else:
                # 外部工具/记忆等非模块选项卡切换时刷新滚动条
                if tab_widget in self.tab_scroll_containers:
                    self.root.after(50, lambda: self.tab_scroll_containers[tab_widget].check_scroll_needed())
        except Exception:
            pass

    def _notify_deactivated(self):
        """通知当前标签页失活"""
        if self.current_tab is None:
            return
        try:
            old_tab_widget = self.notebook.nametowidget(self.current_tab)
        except Exception:
            return
        old_module = self.module_instances.get(old_tab_widget)
        if old_module is not None:
            try:
                old_module.on_tab_deactivated()
            except Exception:
                pass

    def _on_window_configure(self, event):
        """窗口大小变化时检查当前标签页的滚动条"""
        if event.widget != self.root:
            return
        # 只检查当前显示的标签页
        try:
            current = self.notebook.select()
            if not current:
                return
            tab_widget = self.notebook.nametowidget(current)
            if tab_widget in self.tab_scroll_containers:
                self.root.after(50, lambda: self.tab_scroll_containers[tab_widget].check_scroll_needed())
        except Exception:
            pass

    def _on_closing(self):
        """窗口关闭处理"""
        active_tabs = [tab_id for tab_id, is_processing in self.processing_tabs.items()
                       if is_processing]
        if active_tabs:
            result = messagebox.askyesno("确认退出",
                f"有 {len(active_tabs)} 个任务正在运行中。\n退出将终止所有任务，是否继续？",
                icon='warning')
            if not result:
                return

        # 停止所有模块的处理
        for module_instance in self.module_instances.values():
            try:
                module_instance.stop_processing()
                module_instance.cleanup()
            except Exception:
                pass

        self._save_last_config()
        # 退出时隐藏 __pycache__ 文件夹，保持目录整洁
        self._hide_pycache_folders()
        self.root.destroy()

    def _hide_pycache_folders(self):
        """退出时将 __pycache__ 文件夹属性设置为隐藏

        涉及范围：主程序目录（PROJECT_ROOT）下的所有 __pycache__ 文件夹，
        包括 Add 目录及其子目录中的编译缓存。避免在文件管理器中显示
        编译缓存文件夹，保持项目目录整洁。
        """
        if os.name != 'nt':
            return
        try:
            FILE_ATTRIBUTE_HIDDEN = 0x2
            # 遍历主程序目录下的所有 __pycache__ 文件夹
            for root, dirs, files in os.walk(PROJECT_ROOT):
                for dir_name in dirs:
                    if dir_name == '__pycache__':
                        pycache_path = os.path.join(root, dir_name)
                        try:
                            ctypes.windll.kernel32.SetFileAttributesW(
                                pycache_path, FILE_ATTRIBUTE_HIDDEN
                            )
                        except Exception:
                            pass
        except Exception:
            pass

    # ========== 外部工具管理选项卡 ==========

    def create_external_tools_tab(self):
        """创建外部工具管理选项卡（在错误日志前）"""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="外部工具")

        # 使用可滚动容器
        scroll_container = ScrollableContainer(tab)
        scroll_container.pack(fill=tk.BOTH, expand=True)
        self.tab_scroll_containers[tab] = scroll_container
        inner = scroll_container.get_inner_frame()

        # 说明
        if getattr(sys, 'frozen', False):
            pip_hint = "pip 依赖库已全部内置到 EXE，无需安装。\n"
        else:
            pip_hint = "pip 依赖库未安装时可双击自动安装（安装完成后程序将自动重启）。\n"
        desc_label = ttk.Label(inner,
            text="此标签页统一管理各模块所需的外部 exe 工具和 pip 依赖库。\n"
                 "程序启动时自动从 PATH 环境变量查找 exe，未找到的可手动指定（双击列表项）。\n"
                 + pip_hint +
                 "绿色表示已配置/已安装，红色表示未配置/未安装。",
            font=("Microsoft YaHei UI", 10), foreground="gray", justify=tk.LEFT)
        desc_label.pack(fill=tk.X, padx=10, pady=(10, 5))

        # 操作按钮
        btn_frame = ttk.Frame(inner)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="自动查找", command=self._auto_find_exes_btn).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="手动选择", command=self._manual_select_exe).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清除选中", command=self._clear_selected_exe).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="刷新", command=self.refresh_exe_status).pack(side=tk.LEFT, padx=5)

        # exe 列表表格
        list_frame = ttk.LabelFrame(inner, text="外部工具列表（双击选择 exe 文件）", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('name', 'path', 'status', 'modules')
        self.exe_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=1)
        self.exe_tree.heading('name', text='工具名称')
        self.exe_tree.heading('path', text='路径')
        self.exe_tree.heading('status', text='状态')
        self.exe_tree.heading('modules', text='使用模块')
        self.exe_tree.column('name', width=120, anchor=tk.W)
        self.exe_tree.column('path', width=400, anchor=tk.W)
        self.exe_tree.column('status', width=80, anchor=tk.CENTER)
        self.exe_tree.column('modules', width=200, anchor=tk.W)

        # 颜色标签：绿色表示已找到，红色表示未找到
        self.exe_tree.tag_configure('found', foreground='#228B22')
        self.exe_tree.tag_configure('not_found', foreground='#CC0000')
        self.exe_tree.tag_configure('optional_missing', foreground='#FF8C00')

        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.exe_tree.yview)
        scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.exe_tree.xview)
        self.exe_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.exe_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar_y.grid(row=0, column=1, sticky='ns')
        scrollbar_x.grid(row=1, column=0, sticky='ew')
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        # 双击选择 exe 文件
        self.exe_tree.bind('<Double-Button-1>', lambda e: self._manual_select_exe())

        # pip 依赖库列表表格
        pip_frame = ttk.LabelFrame(inner, text="pip 依赖库列表（双击未安装项自动安装）", padding="5")
        pip_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        pip_columns = ('name', 'status', 'type', 'modules')
        self.pip_tree = ttk.Treeview(pip_frame, columns=pip_columns, show='headings', height=1)
        self.pip_tree.heading('name', text='库名称')
        self.pip_tree.heading('status', text='状态')
        self.pip_tree.heading('type', text='类型')
        self.pip_tree.heading('modules', text='使用模块')
        self.pip_tree.column('name', width=180, anchor=tk.W)
        self.pip_tree.column('status', width=80, anchor=tk.CENTER)
        self.pip_tree.column('type', width=80, anchor=tk.CENTER)
        self.pip_tree.column('modules', width=240, anchor=tk.W)

        # 颜色标签：绿色表示已安装，红色表示未安装
        self.pip_tree.tag_configure('installed', foreground='#228B22')
        self.pip_tree.tag_configure('not_installed', foreground='#CC0000')

        pip_scrollbar_y = ttk.Scrollbar(pip_frame, orient=tk.VERTICAL, command=self.pip_tree.yview)
        pip_scrollbar_x = ttk.Scrollbar(pip_frame, orient=tk.HORIZONTAL, command=self.pip_tree.xview)
        self.pip_tree.configure(yscrollcommand=pip_scrollbar_y.set, xscrollcommand=pip_scrollbar_x.set)

        self.pip_tree.grid(row=0, column=0, sticky='nsew')
        pip_scrollbar_y.grid(row=0, column=1, sticky='ns')
        pip_scrollbar_x.grid(row=1, column=0, sticky='ew')
        pip_frame.grid_rowconfigure(0, weight=1)
        pip_frame.grid_columnconfigure(0, weight=1)

        # 双击安装 pip 依赖
        self.pip_tree.bind('<Double-Button-1>', lambda e: self._install_pip_dependency())

        # 启动时自动查找未配置的 exe
        self._auto_find_all_exes()
        self._refresh_exe_tree()
        self._refresh_pip_tree()

    def _auto_find_exes_btn(self):
        """自动查找按钮回调"""
        self._auto_find_all_exes()
        self._refresh_exe_tree()
        found_count = sum(1 for exe_name, _mods, _is_opt in self.exe_requirements if self.exe_paths.get(exe_name))
        total = len(self.exe_requirements)
        messagebox.showinfo("自动查找完成",
            f"已查找 {total} 个外部工具，成功配置 {found_count} 个。",
            parent=self.root)

    def _exe_name_from_tree(self, display_name):
        """从外部工具表格的显示名反查真实 exe 名称

        _refresh_exe_tree 在可选 exe 名称后追加 " (可选)" 后缀用于显示，
        本方法去除该后缀，返回真实的 exe_name（用于 exe_paths 字典键）。
        """
        suffix = " (可选)"
        if display_name.endswith(suffix):
            return display_name[:-len(suffix)]
        return display_name

    def _manual_select_exe(self):
        """手动选择 exe 文件"""
        selection = self.exe_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先在列表中选择一个外部工具",
                                   parent=self.root)
            return
        item = selection[0]
        values = self.exe_tree.item(item, 'values')
        exe_name = self._exe_name_from_tree(values[0])

        path = filedialog.askopenfilename(
            title=f"选择 {exe_name} 可执行文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
            parent=self.root)
        if not path:
            return

        # 验证文件是否存在
        if not os.path.isfile(path):
            messagebox.showerror("错误", f"文件不存在: {path}", parent=self.root)
            return

        self.exe_paths[exe_name] = path
        self._refresh_exe_tree()
        self.log_message('info', f"手动配置 {exe_name}: {path}", "外部工具")

    def _clear_selected_exe(self):
        """清除选中的 exe 配置"""
        selection = self.exe_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先在列表中选择一个外部工具",
                                   parent=self.root)
            return
        item = selection[0]
        values = self.exe_tree.item(item, 'values')
        exe_name = self._exe_name_from_tree(values[0])
        if exe_name in self.exe_paths:
            del self.exe_paths[exe_name]
            self._refresh_exe_tree()
            self.log_message('info', f"已清除 {exe_name} 的路径配置", "外部工具")

    def _refresh_pip_tree(self):
        """刷新 pip 依赖库表格"""
        for item in self.pip_tree.get_children():
            self.pip_tree.delete(item)
        # PyInstaller 打包后所有依赖已内置，统一显示"已内置"，不再调用 _check_pip_installed
        is_frozen = getattr(sys, 'frozen', False)
        for dep_spec, modules, is_optional in self.pip_requirements:
            install_name = dep_spec[0]
            if is_frozen:
                status = "已内置"
                dep_type = "内置"
                tags = ('installed',)
            else:
                installed = self._check_pip_installed(dep_spec)
                status = "已安装" if installed else "未安装"
                dep_type = "可选" if is_optional else "必需"
                tags = ('installed',) if installed else ('not_installed',)
            modules_str = ', '.join(modules)
            self.pip_tree.insert('', tk.END,
                                 values=(install_name, status, dep_type, modules_str),
                                 tags=tags)

    def _install_pip_dependency(self):
        """双击安装 pip 依赖（弹出嵌入式命令行窗口实时显示回显）"""
        # PyInstaller 打包后无法运行 pip install（sys.executable 是 EXE 自身，非 Python）
        if getattr(sys, 'frozen', False):
            messagebox.showinfo("无需安装",
                "EXE 模式下所需 pip 依赖已全部内置，无需也无法在此安装新库。\n"
                "如需添加新依赖，请修改源代码后重新封装。",
                parent=self.root)
            return
        selection = self.pip_tree.selection()
        if not selection:
            messagebox.showwarning("提示", "请先在列表中选择一个 pip 依赖库",
                                   parent=self.root)
            return
        item = selection[0]
        values = self.pip_tree.item(item, 'values')
        install_name = values[0]  # 表格显示的是 install_name

        # 通过 install_name 查找对应的 dep_spec
        dep_spec = None
        for spec, modules, is_optional in self.pip_requirements:
            if spec[0] == install_name:
                dep_spec = spec
                break
        if dep_spec is None:
            messagebox.showerror("错误", f"未找到依赖 {install_name}", parent=self.root)
            return

        # 已安装则提示并返回
        if self._check_pip_installed(dep_spec):
            messagebox.showinfo("提示", f"{install_name} 已安装", parent=self.root)
            return

        # 确认安装
        if not messagebox.askyesno("确认安装",
                f"即将执行：pip install {install_name}\n\n"
                f"安装完成后程序将自动重启以加载新库。\n\n是否继续？",
                parent=self.root):
            return

        # 弹出嵌入式命令行窗口（用 install_name 执行 pip install）
        self._show_pip_install_dialog(install_name)

    def _show_pip_install_dialog(self, dep_name):
        """显示 pip 安装对话框（嵌入式命令行窗口，实时显示回显）"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"安装 pip 依赖 - {dep_name}")
        dialog.transient(self.root)
        dialog.geometry("700x400")
        dialog.resizable(True, True)

        # 信息标签
        info_frame = ttk.Frame(dialog, padding="5")
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text=f"正在执行：pip install {dep_name}",
                 font=("Consolas", 10)).pack(anchor=tk.W)

        # 命令行回显区域
        output_frame = ttk.Frame(dialog, padding="5")
        output_frame.pack(fill=tk.BOTH, expand=True)

        from tkinter import scrolledtext
        output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD,
                                                font=("Consolas", 9), state=tk.DISABLED)
        output_text.pack(fill=tk.BOTH, expand=True)

        # 标签颜色配置
        output_text.tag_configure('stdout', foreground='#000000')
        output_text.tag_configure('stderr', foreground='#CC0000')
        output_text.tag_configure('info', foreground='#0000FF')

        def append_output(text, tag='stdout'):
            output_text.config(state=tk.NORMAL)
            output_text.insert(tk.END, text, tag)
            output_text.see(tk.END)
            output_text.config(state=tk.DISABLED)

        # 状态标签
        status_var = tk.StringVar(value="安装中...")
        status_label = ttk.Label(dialog, textvariable=status_var,
                                font=("Microsoft YaHei UI", 10), foreground="blue")
        status_label.pack(fill=tk.X, padx=5, pady=(0, 5))

        append_output(f"$ pip install {dep_name}\n\n", 'info')

        # 启动 pip 安装进程
        import subprocess
        cmd = [sys.executable, '-m', 'pip', 'install', dep_name]

        def run_install():
            try:
                process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True, encoding='utf-8', errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW)

                for line in process.stdout:
                    dialog.after(0, lambda l=line: append_output(l))

                process.wait()
                returncode = process.returncode

                if returncode == 0:
                    dialog.after(0, lambda: append_output("\n安装成功！\n", 'info'))
                    dialog.after(0, lambda: status_var.set("安装成功，准备重启程序..."))
                    # 安装成功后延迟重启
                    dialog.after(1500, lambda: self._restart_application(dialog))
                else:
                    dialog.after(0, lambda: append_output(f"\n安装失败（返回码 {returncode}）。\n", 'stderr'))
                    dialog.after(0, lambda: status_var.set(f"安装失败（返回码 {returncode}）"))
                    dialog.after(0, lambda: dialog.transient(None))
            except Exception as e:
                err_msg = str(e)
                dialog.after(0, lambda: append_output(f"\n执行异常: {err_msg}\n", 'stderr'))
                dialog.after(0, lambda: status_var.set(f"执行异常: {err_msg}"))

        threading.Thread(target=run_install, daemon=True).start()

        # 阻止用户关闭对话框直到安装完成（通过 protocol）
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    def _create_admin_request_button(self, parent, return_tab, text, **kwargs):
        """创建管理员权限请求按钮（内部实现）

        按钮行为完全由主程序管理：
        - 管理员模式下按钮禁用（state=disabled）
        - 非管理员模式下按钮可点击
        - 点击后直接调用 _restart_application(as_admin=True) 触发 UAC
        - UAC 通过则程序退出重启，UAC 未通过则弹出警告提示框

        参数:
            parent: 按钮父容器
            return_tab: 重启后跳转的选项卡名称
            text: 按钮文本
            **kwargs: 传递给 ttk.Button 的其他参数

        返回:
            ttk.Button 实例
        """
        def _on_click():
            # 直接触发 UAC 重启，无需二次确认
            success = self._restart_application(
                target_tab=return_tab, as_admin=True)
            if not success:
                # UAC 未通过（用户拒绝或出错），弹出警告提示框
                messagebox.showwarning(
                    "UAC 未授权",
                    "无法以管理员身份重启程序。",
                    parent=self.root
                )

        btn = ttk.Button(parent, text=text, command=_on_click, **kwargs)
        # 管理员模式下禁用按钮
        if self._is_admin():
            btn.state(['disabled'])
        return btn

    def _restart_application(self, close_dialog=None, target_tab=None, as_admin=False):
        """保存配置并退出主程序，然后以指定权限重新启动

        兼容 PyInstaller EXE 和 Python 脚本两种运行模式：
        - EXE 模式：直接重启 Z-ToolKit.exe
        - Python 脚本模式：通过 python.exe 运行 Z-ToolKit.py

        管理员模式通过 ShellExecuteW "runas" 触发 UAC 提权；
        普通模式通过临时 bat 文件等待进程退出后启动新进程。

        参数:
            close_dialog: 待关闭的对话框（兼容旧调用）
            target_tab: 重启后跳转的选项卡名称（None 则不跳转）
            as_admin: True=以管理员身份重启（触发 UAC），False=普通重启

        返回:
            True=重启已触发（程序即将退出）；False=UAC 未通过或失败（程序继续运行）
        """
        try:
            import subprocess
            import random
            import string

            # 构建 --tab 参数
            tab_arg = f" --tab={target_tab}" if target_tab else ""

            # 保存配置
            self._save_last_config()

            # 关闭对话框
            if close_dialog is not None:
                try:
                    close_dialog.destroy()
                except Exception:
                    pass

            if as_admin:
                # 管理员模式：使用 ShellExecuteW "runas" 触发 UAC
                # 返回值 > 32 表示成功，<= 32 表示失败（用户取消或出错）
                if getattr(sys, 'frozen', False):
                    # PyInstaller EXE 模式
                    result = ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", sys.executable,
                        tab_arg.strip(), None, 1
                    )
                else:
                    # Python 脚本模式
                    script_path = os.path.abspath(__file__)
                    params = f'"{script_path}"{tab_arg}'
                    result = ctypes.windll.shell32.ShellExecuteW(
                        None, "runas", sys.executable,
                        params, None, 1
                    )

                if result <= 32:
                    # UAC 未通过（用户拒绝或出错），不退出，返回 False
                    return False
                # UAC 通过，退出当前程序
                self.root.destroy()
                return True
            else:
                # 普通模式：生成临时 bat 文件，等待进程退出后启动新进程
                random_name = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
                bat_path = os.path.join(tempfile.gettempdir(), f"{random_name}.bat")

                if getattr(sys, 'frozen', False):
                    launch_cmd = f'"{sys.executable}"{tab_arg}'
                else:
                    script_path = os.path.abspath(__file__)
                    launch_cmd = f'"{sys.executable}" "{script_path}"{tab_arg}'

                bat_content = (
                    f'@echo off\n'
                    f'chcp 65001 >nul\n'
                    f':wait\n'
                    f'tasklist /FI "PID eq {os.getpid()}" 2>NUL | find "{os.getpid()}" >NUL\n'
                    f'if not errorlevel 1 (\n'
                    f'    timeout /t 1 /nobreak >nul\n'
                    f'    goto wait\n'
                    f')\n'
                    f'{launch_cmd}\n'
                    f'del "%~f0"\n'
                )

                with open(bat_path, 'w', encoding='utf-8') as f:
                    f.write(bat_content)

                subprocess.Popen(
                    ['cmd', '/c', bat_path],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    close_fds=True
                )

                # 退出当前程序
                self.root.destroy()
                return True
        except Exception as e:
            messagebox.showerror("重启失败", f"创建重启脚本失败: {e}", parent=self.root)
            return False

    @staticmethod
    def _is_admin():
        """检测当前进程是否以管理员权限运行"""
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    # ========== 记忆选项卡 ==========

    def create_memory_clear_tab(self):
        """创建记忆选项卡（放在外部工具和错误日志之间）

        直接在标签页内处理模块选择和清除操作，不弹出对话框。
        使用 ScrollableContainer 处理横纵向组件超出窗口的滚动。
        """
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="记忆")
        self.memory_clear_tab = tab

        # 使用可滚动容器处理横纵向滚动
        scroll_container = ScrollableContainer(tab)
        scroll_container.pack(fill=tk.BOTH, expand=True)
        self.tab_scroll_containers[tab] = scroll_container
        inner = scroll_container.get_inner_frame()

        # 说明区域
        desc_label = ttk.Label(inner,
            text="勾选需要清除记忆的模块，点击下方按钮清除选中模块的配置。\n"
                 "（包括编码器设置、路径、样式等。清除后不可恢复，请谨慎操作。）\n"
                 "有任务正在处理中时清除功能将被禁用。",
            font=("Microsoft YaHei UI", 10), foreground="gray", justify=tk.LEFT)
        desc_label.pack(fill=tk.X, padx=10, pady=(10, 5))

        # 全选/全不选按钮
        select_frame = ttk.Frame(inner)
        select_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(select_frame, text="全选",
                  command=lambda: self._toggle_all_memory_modules(True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_frame, text="全不选",
                  command=lambda: self._toggle_all_memory_modules(False)).pack(side=tk.LEFT, padx=5)

        # 模块列表区域
        list_frame = ttk.LabelFrame(inner, text="模块列表", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 存储模块复选框变量
        self.memory_module_vars = []

        # 收集所有模块（按 TAB_ORDER 排序）
        modules_sorted = sorted(
            self.module_instances.values(),
            key=lambda m: getattr(m, 'TAB_ORDER', 100)
        )

        for module in modules_sorted:
            var = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(list_frame, text=module.TAB_NAME, variable=var)
            cb.pack(anchor=tk.W, padx=5, pady=2, fill=tk.X)
            self.memory_module_vars.append((var, module))

        # 清除选中记忆按钮（位于复选框下方）
        self.memory_clear_btn = ttk.Button(list_frame, text="清除选中记忆",
                                           command=self._clear_selected_memory_in_tab)
        self.memory_clear_btn.pack(anchor=tk.W, padx=5, pady=(10, 2))

        # 外部工具记忆区域（单独选项）
        exe_frame = ttk.LabelFrame(inner, text="外部工具记忆", padding="5")
        exe_frame.pack(fill=tk.X, padx=10, pady=5)

        exe_desc = ttk.Label(exe_frame,
            text="清除外部 exe 工具的路径配置（包括手动指定和自动查找的路径）。\n"
                 "清除后将重新从 PATH 环境变量自动查找。",
            font=("Microsoft YaHei UI", 10), foreground="gray", justify=tk.LEFT)
        exe_desc.pack(anchor=tk.W, padx=5, pady=(0, 5))

        self.exe_clear_btn = ttk.Button(exe_frame, text="清除外部工具记忆",
                                        command=self._clear_exe_paths_memory_in_tab)
        self.exe_clear_btn.pack(anchor=tk.W, padx=5, pady=2)

    def _toggle_all_memory_modules(self, state):
        """全选/全不选模块复选框"""
        for var, _ in self.memory_module_vars:
            var.set(state)

    def _clear_selected_memory_in_tab(self):
        """在标签页内清除选中模块的记忆（不弹出对话框）"""
        # 检查是否有正在处理的模块
        active_tabs = [tab_id for tab_id, is_processing in self.processing_tabs.items()
                       if is_processing]
        if active_tabs:
            messagebox.showerror("操作受限",
                "有任务正在处理中，无法清除记忆。\n\n请等待所有任务处理完成后再操作。",
                parent=self.root)
            return

        selected = [m for var, m in self.memory_module_vars if var.get()]
        if not selected:
            messagebox.showwarning("提示", "请先勾选需要清除记忆的模块",
                                   parent=self.root)
            return

        names = "、".join(m.TAB_NAME for m in selected)
        self.clear_selected_memory(selected)
        self.log_message('info',
            f"用户清除了以下模块的配置记忆: {names}", "系统")
        messagebox.showinfo("完成", f"已清除 {len(selected)} 个模块的记忆。",
                           parent=self.root)
        # 清除后取消勾选
        for var, _ in self.memory_module_vars:
            var.set(False)

    def _clear_exe_paths_memory_in_tab(self):
        """在标签页内清除外部工具路径配置记忆（不弹出对话框）"""
        # 检查是否有正在处理的模块
        active_tabs = [tab_id for tab_id, is_processing in self.processing_tabs.items()
                       if is_processing]
        if active_tabs:
            messagebox.showerror("操作受限",
                "有任务正在处理中，无法清除记忆。\n\n请等待所有任务处理完成后再操作。",
                parent=self.root)
            return

        self.clear_exe_paths_memory()
        self.log_message('info', "用户清除了外部工具路径配置记忆", "系统")
        messagebox.showinfo("完成", "已清除外部工具记忆，已重新从 PATH 自动查找。",
                           parent=self.root)

    # ========== 错误日志选项卡 ==========

    def create_error_log_tab(self):
        """创建错误日志选项卡"""
        tab = ttk.Frame(self.notebook)
        # 错误日志标签页常驻最右端（pinned=True），不参与分页，
        # 任务进行时用户仍可点击查看日志
        self.notebook.add(tab, text="错误日志", pinned=True)

        main_frame = ttk.Frame(tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 控制面板
        control_frame = ttk.LabelFrame(main_frame, text="日志级别过滤", padding="5")
        control_frame.pack(fill=tk.X, pady=(0, 10))

        self.log_level_vars = {
            'info': tk.BooleanVar(value=True),
            'warning': tk.BooleanVar(value=True),
            'error': tk.BooleanVar(value=True),
            'critical': tk.BooleanVar(value=True)
        }

        ttk.Checkbutton(control_frame, text="信息", variable=self.log_level_vars['info'],
                       command=self.refresh_error_log).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(control_frame, text="警告", variable=self.log_level_vars['warning'],
                       command=self.refresh_error_log).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(control_frame, text="错误", variable=self.log_level_vars['error'],
                       command=self.refresh_error_log).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(control_frame, text="严重错误", variable=self.log_level_vars['critical'],
                       command=self.refresh_error_log).pack(side=tk.LEFT, padx=5)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(btn_frame, text="清空日志", command=self.clear_error_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="刷新", command=self.refresh_error_log).pack(side=tk.LEFT, padx=5)

        # 日志显示区域
        self.error_log_frame = ttk.LabelFrame(main_frame, text="日志内容", padding="5")
        self.error_log_frame.pack(fill=tk.BOTH, expand=True)

        # 日志显示区域容器
        log_container = ttk.Frame(self.error_log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)

        self.error_log_text = tk.Text(log_container, wrap=tk.WORD, state=tk.DISABLED,
                                      font=("Consolas", 10), bg='#FFFFFF', fg='#333333',
                                      borderwidth=1, relief=tk.SOLID)
        self.error_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.error_log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.error_log_text.config(yscrollcommand=scrollbar.set)

        # 配置文本标签（颜色）
        self.error_log_text.tag_configure('info', foreground='#569cd6')
        self.error_log_text.tag_configure('warning', foreground='#dcdcaa')
        self.error_log_text.tag_configure('error', foreground='#ce9178')
        self.error_log_text.tag_configure('critical', foreground='#f44747')

        # 状态栏
        self.error_log_status_var = tk.StringVar(value="就绪")
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        ttk.Label(status_frame, textvariable=self.error_log_status_var, relief=tk.FLAT,
                 anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)

    def log_message(self, level, message, source_tab="系统"):
        """记录日志"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = {
            'timestamp': timestamp,
            'level': level,
            'message': message,
            'source': source_tab
        }

        with self.error_log_lock:
            self.error_log_entries.append(entry)
            if len(self.error_log_entries) > 5000:
                self.error_log_entries = self.error_log_entries[-4000:]

        # 将过滤判断移到主线程执行
        self.root.after(0, self._append_log_entry, entry)

        if level in ['error', 'critical']:
            self.root.after(0, lambda: self.switch_to_error_log())

    def _append_log_entry(self, entry):
        """在主线程中追加日志条目（含级别过滤）"""
        if not self.log_level_vars.get(entry['level'], tk.BooleanVar(value=True)).get():
            return

        level_display = {
            'info': '[INFO]',
            'warning': '[WARN]',
            'error': '[ERROR]',
            'critical': '[FATAL]'
        }.get(entry['level'], f"[{entry['level'].upper()}]")

        log_line = f"{level_display} [{entry['timestamp']}] [{entry['source']}] {entry['message']}\n"
        self.error_log_text.config(state=tk.NORMAL)
        self.error_log_text.insert(tk.END, log_line, entry['level'])
        self.error_log_text.config(state=tk.DISABLED)
        self.error_log_text.see(tk.END)

    def refresh_error_log(self):
        """全量刷新错误日志显示（仅在切换级别过滤时调用）"""
        self.error_log_text.config(state=tk.NORMAL)
        self.error_log_text.delete('1.0', tk.END)

        with self.error_log_lock:
            filtered_entries = [
                entry for entry in self.error_log_entries
                if self.log_level_vars.get(entry['level'], tk.BooleanVar(value=True)).get()
            ]

        for entry in filtered_entries:
            level_display = {
                'info': '[INFO]',
                'warning': '[WARN]',
                'error': '[ERROR]',
                'critical': '[FATAL]'
            }.get(entry['level'], f"[{entry['level'].upper()}]")

            log_line = f"{level_display} [{entry['timestamp']}] [{entry['source']}] {entry['message']}\n"
            self.error_log_text.insert(tk.END, log_line, entry['level'])

        self.error_log_text.config(state=tk.DISABLED)
        self.error_log_text.see(tk.END)

    def clear_error_log(self, tab_name=None):
        """清空错误日志"""
        with self.error_log_lock:
            self.error_log_entries.clear()

        if tab_name:
            self.error_log_frame.configure(text=f"日志内容 - [{tab_name}]")
        else:
            self.error_log_frame.configure(text="日志内容")

        self.refresh_error_log()
        if tab_name:
            self.error_log_status_var.set(f"[{tab_name}] 日志已清空，开始新的处理")
        else:
            self.error_log_status_var.set("日志已清空")

    def switch_to_error_log(self):
        """切换到错误日志选项卡（跨页查找）"""
        try:
            self.notebook.select_by_text('错误日志')
        except Exception:
            pass

    def set_tab_processing(self, tab_widget, is_processing, has_error=False):
        """设置选项卡的处理状态并更新标题"""
        # 去除前缀的状态图标（含 emoji 变体选择符 U+FE0F）
        original_text = self.notebook.tab(tab_widget, "text")
        original_text = re.sub(r'^[\u25B6\uFE0F\u2757\s]+', '', original_text)

        if is_processing and not has_error:
            new_text = f"\u25B6\uFE0F {original_text}"
        elif has_error:
            new_text = f"\u2757 {original_text}"
        else:
            new_text = original_text

        self.notebook.tab(tab_widget, text=new_text)
        self.processing_tabs[tab_widget] = is_processing

        # 更新清除记忆按钮状态：有任意模块处理中时禁用
        self._update_clear_memory_btn_state()

    def _update_clear_memory_btn_state(self):
        """根据当前处理状态更新清除记忆按钮和翻页按钮的可用性

        任务进行时：
        - 禁用清除记忆按钮（防止处理中清除配置）
        - 禁用标签页翻页按钮（防止切换到其他页的标签页）
        但错误日志标签页常驻最右端，仍可点击查看日志。
        """
        any_processing = any(self.processing_tabs.values())
        new_state = tk.DISABLED if any_processing else tk.NORMAL
        if hasattr(self, 'memory_clear_btn'):
            self.memory_clear_btn.config(state=new_state)
        if hasattr(self, 'exe_clear_btn'):
            self.exe_clear_btn.config(state=new_state)
        # 同步禁用/启用 PageableNotebook 的翻页按钮
        if hasattr(self, 'notebook') and hasattr(self.notebook, 'set_buttons_enabled'):
            self.notebook.set_buttons_enabled(not any_processing)


# 主程序入口
def main():
    """主函数

    支持命令行参数：
        --tab=<选项卡名称>：程序启动后延迟跳转到指定选项卡（用于管理员重启后回跳）
    """
    # 解析 --tab 参数（管理员重启后传递）
    target_tab = None
    for arg in sys.argv[1:]:
        if arg.startswith('--tab='):
            target_tab = arg[len('--tab='):]
            break

    app = VideoProcessingTool()

    # 延迟跳转到目标选项卡（等待 notebook 完成初始化和模块加载）
    if target_tab:
        def _jump_to_tab():
            try:
                if hasattr(app, 'notebook') and hasattr(app.notebook, 'select_by_text'):
                    app.notebook.select_by_text(target_tab)
            except Exception:
                pass
        app.root.after(200, _jump_to_tab)

    app.root.mainloop()


if __name__ == "__main__":
    main()
