# -*- coding: utf-8 -*-
"""符号链接创建模块：双面板文件管理器，拖拽文件夹到对面面板自动创建符号链接"""

import os
import ctypes
import tkinter as tk
from tkinter import ttk

from common import TabModule


# ===== 常量 =====

FOLDER_TAG = "folder"
FILE_TAG = "file"
PARENT_TAG = "parent"
HIDDEN_TAG = "hidden"

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


# ===== 目录列表工具 =====

def _is_hidden_or_system(path: str) -> bool:
    """检测文件是否具有隐藏或系统属性。"""
    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            return False
        return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
    except Exception:
        return False


def _list_directory(path: str) -> list:
    """列出目录内容，返回 [(name, is_dir, size_str, full_path, is_hidden), ...]。

    显示所有文件（包括隐藏和系统文件），文件夹排在前面，按名称排序。
    """
    items = []
    try:
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                is_dir = os.path.isdir(full)
            except OSError:
                continue
            is_hidden = _is_hidden_or_system(full)
            size_str = ""
            if not is_dir:
                try:
                    s = os.path.getsize(full)
                    if s < 1024:
                        size_str = f"{s} B"
                    elif s < 1024 * 1024:
                        size_str = f"{s / 1024:.1f} KB"
                    elif s < 1024 * 1024 * 1024:
                        size_str = f"{s / (1024 * 1024):.1f} MB"
                    else:
                        size_str = f"{s / (1024 * 1024 * 1024):.2f} GB"
                except OSError:
                    size_str = ""
            items.append((name, is_dir, size_str, full, is_hidden))
    except (PermissionError, FileNotFoundError, OSError):
        pass
    items.sort(key=lambda x: (not x[1], x[0].lower()))
    return items


def _get_drives() -> list:
    """获取可用驱动器的路径列表。"""
    drives = []
    try:
        import string
        for letter in string.ascii_uppercase:
            p = f"{letter}:\\"
            if os.path.exists(p):
                drives.append(p)
    except Exception:
        pass
    return drives or ["C:\\"]


# ===== 符号链接创建 =====

def _create_one_symlink(src: str, dst_dir: str) -> tuple:
    """在目标目录中创建源文件夹的符号链接。

    开发者模式下普通用户即可创建符号链接。

    Returns:
        (ok: bool, message: str)
    """
    src = os.path.normpath(src)
    dst_dir = os.path.normpath(dst_dir)

    if not os.path.isdir(src):
        return False, f"不是文件夹: {os.path.basename(src)}"

    link_name = os.path.basename(src)
    dst_path = os.path.join(dst_dir, link_name)

    if os.path.exists(dst_path):
        return False, f"目标已存在同名项: {link_name}"

    # 直接调用 os.symlink（开发者模式下普通用户可用）
    try:
        os.symlink(src, dst_path, target_is_directory=True)
        return True, f"已创建符号链接: {link_name}"
    except OSError as e:
        return False, f"创建失败: {link_name} ({e})"


# ===== 单个文件面板 =====

class _Panel:
    """单个文件面板：路径栏 + 盘符切换 + 文件列表树 + 导航按钮"""

    def __init__(self, module, parent, side: str, initial_path: str):
        self.module = module
        self.side = side
        self._path = tk.StringVar(value=initial_path)
        self._drive_var = tk.StringVar()

        # 主框架
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # ---- 标题 + 导航栏 ----
        nav = ttk.Frame(self.frame)
        nav.pack(fill=tk.X, pady=(0, 3))

        ttk.Label(nav, text=f"面板 {1 if side == 'left' else 2}").pack(side=tk.LEFT)

        self._up_btn = ttk.Button(nav, text="↑", width=3,
                                   command=self._go_up)
        self._up_btn.pack(side=tk.LEFT, padx=(5, 0))

        self._refresh_btn = ttk.Button(nav, text="↻", width=3,
                                        command=self._refresh)
        self._refresh_btn.pack(side=tk.LEFT, padx=(2, 2))

        # 盘符下拉框
        drives = _get_drives()
        self._drive_combo = ttk.Combobox(
            nav, textvariable=self._drive_var, values=drives,
            width=4, state="readonly")
        self._drive_combo.pack(side=tk.LEFT, padx=(2, 5))
        self._drive_combo.bind('<<ComboboxSelected>>', self._on_drive_selected)

        self._path_entry = ttk.Entry(nav, textvariable=self._path)
        self._path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._path_entry.bind('<Return>', lambda e: self._navigate_to(
            self._path.get()))

        # ---- 文件列表（用 tk.Frame 包裹以便实现拖拽高亮边框）----
        list_container = tk.Frame(
            self.frame, highlightthickness=2,
            highlightbackground="#cccccc", highlightcolor="#4A90D9")
        list_container.pack(fill=tk.BOTH, expand=True)
        self._list_container = list_container

        self.tree = ttk.Treeview(list_container,
                                  columns=("size",),
                                  show="tree headings",
                                  selectmode="browse")
        self.tree.heading("#0", text="名称")
        self.tree.heading("size", text="大小")
        self.tree.column("#0", width=250, minwidth=100)
        self.tree.column("size", width=80, minwidth=60, anchor="e")

        # 隐藏/系统文件用灰色显示
        self.tree.tag_configure(HIDDEN_TAG, foreground="#999999")

        y_scroll = ttk.Scrollbar(list_container, orient="vertical",
                                  command=self.tree.yview)
        x_scroll = ttk.Scrollbar(list_container, orient="horizontal",
                                  command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set,
                            xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        # 双击进入文件夹
        self.tree.bind('<Double-1>', self._on_double_click)
        # 右键菜单
        self.tree.bind('<Button-3>', self._on_right_click)

        # ---- 拖拽支持 ----
        self._drag_item = None
        self._drag_src_path = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_start_root_x = 0
        self._drag_start_root_y = 0
        self._drag_threshold = 5
        self._is_dragging = False
        self._drag_image = None       # 拖拽时跟随光标的半透明 Toplevel

        self.tree.bind('<ButtonPress-1>', self._on_drag_start, add='+')
        self.tree.bind('<B1-Motion>', self._on_drag_motion, add='+')
        self.tree.bind('<ButtonRelease-1>', self._on_drag_release, add='+')

        # 初始加载
        self._load_path(initial_path)

    # ===== 路径加载 =====

    def _load_path(self, path: str):
        """加载指定路径到文件树。"""
        self.tree.delete(*self.tree.get_children())
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            path = os.path.dirname(path) if os.path.exists(path) else "C:\\"

        self._path.set(path)

        # 更新盘符下拉框
        drive = os.path.splitdrive(path)[0]
        if drive:
            self._drive_var.set(drive + "\\")

        # ".." 返回上级
        parent_dir = os.path.dirname(path)
        if parent_dir and parent_dir != path and os.path.exists(parent_dir):
            self.tree.insert("", "end", iid="__parent__",
                             text="..", values=("",),
                             tags=(PARENT_TAG,), open=False)

        # 列出内容（含隐藏/系统文件）
        for name, is_dir, size_str, full, is_hidden in _list_directory(path):
            display = f"📁 {name}" if is_dir else f"📄 {name}"
            tags = [FOLDER_TAG if is_dir else FILE_TAG]
            if is_hidden:
                tags.append(HIDDEN_TAG)
            self.tree.insert("", "end", iid=full,
                             text=display, values=(size_str,),
                             tags=tuple(tags), open=False)

    def _refresh(self):
        self._load_path(self._path.get())
        self.module.log('info', f"[面板 {1 if self.side == 'left' else 2}] 已刷新")

    def _go_up(self):
        parent = os.path.dirname(self._path.get())
        if parent and parent != self._path.get():
            self._navigate_to(parent)

    def _navigate_to(self, path: str):
        path = os.path.normpath(path)
        if os.path.isdir(path):
            self._load_path(path)
        else:
            self.module.log('warning', f"路径不存在: {path}")

    def _on_drive_selected(self, event=None):
        """盘符下拉框切换。"""
        drive = self._drive_var.get()
        if drive:
            self._navigate_to(drive)

    def get_current_path(self) -> str:
        return self._path.get()

    # ===== 拖拽高亮 =====

    def _set_drop_highlight(self, on: bool):
        """设置拖拽放下高亮边框。"""
        try:
            if on:
                self._list_container.config(highlightbackground="#4A90D9")
            else:
                self._list_container.config(highlightbackground="#cccccc")
        except Exception:
            pass

    # ===== 拖拽跟随图标 =====

    def _create_drag_image(self, root_x: int, root_y: int):
        """创建半透明 Toplevel 跟随鼠标，显示被拖拽的文件夹名。"""
        if not self._drag_src_path:
            return
        base = os.path.basename(self._drag_src_path)
        # 截断过长文字
        display = base if len(base) <= 30 else base[:27] + "..."

        top = tk.Toplevel(self.frame)
        top.overrideredirect(True)
        top.attributes('-topmost', True)
        top.attributes('-alpha', 0.75)

        # 内边距与图标文字
        inner = tk.Frame(top, bg="#e8f0fe", bd=1, relief="solid")
        inner.pack(padx=1, pady=1)

        # 文件夹图标 + 名称
        row = tk.Frame(inner, bg="#e8f0fe")
        row.pack(padx=8, pady=4)
        tk.Label(row, text="📁", bg="#e8f0fe", font=("", 16)).pack(
            side=tk.LEFT, padx=(0, 4))
        tk.Label(row, text=display, bg="#e8f0fe").pack(side=tk.LEFT)

        # 位置：鼠标右下偏移
        top.update_idletasks()
        top.geometry(f"+{root_x + 10}+{root_y + 10}")

        self._drag_image = top

    def _move_drag_image(self, root_x: int, root_y: int):
        """移动拖拽图标到光标位置。"""
        if self._drag_image is None:
            return
        try:
            self._drag_image.geometry(f"+{root_x + 10}+{root_y + 10}")
        except Exception:
            pass

    def _destroy_drag_image(self):
        """销毁拖拽图标。"""
        if self._drag_image is not None:
            try:
                self._drag_image.destroy()
            except Exception:
                pass
            self._drag_image = None

    # ===== 事件处理 =====

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        tags = self.tree.item(item, 'tags')
        if FOLDER_TAG in tags:
            self._navigate_to(item)
        elif PARENT_TAG in tags:
            self._go_up()

    def _on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        tags = self.tree.item(item, 'tags')
        menu = tk.Menu(self.frame, tearoff=0)
        if FOLDER_TAG in tags:
            menu.add_command(label="进入文件夹",
                             command=lambda: self._navigate_to(item))
            menu.add_command(label="复制路径",
                             command=lambda: self._copy_path(item))
            menu.add_separator()
            menu.add_command(label="拖拽到对面面板以创建符号链接",
                             state="disabled")
        elif FILE_TAG in tags:
            menu.add_command(label="复制路径",
                             command=lambda: self._copy_path(item))
        elif PARENT_TAG in tags:
            menu.add_command(label="返回上级", command=self._go_up)
        try:
            if menu.index("end") >= 0:
                menu.post(event.x_root, event.y_root)
        except Exception:
            pass

    def _copy_path(self, path: str):
        self.frame.clipboard_clear()
        self.frame.clipboard_append(path)

    # ===== 拖拽逻辑 =====

    def _on_drag_start(self, event):
        # 清理可能残留的旧拖拽状态
        old = getattr(self.module, '_drag_source', None)
        if old is not None and old is not self:
            old._reset_drag_state()
        item = self.tree.identify_row(event.y)
        if not item:
            return
        tags = self.tree.item(item, 'tags')
        if FOLDER_TAG not in tags:
            return
        self._drag_item = item
        self._drag_src_path = item
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._drag_start_root_x = event.x_root
        self._drag_start_root_y = event.y_root
        self._is_dragging = False
        self.module._drag_source = self

    def _on_drag_motion(self, event):
        source = getattr(self.module, '_drag_source', None)
        if source is None or source._drag_item is None:
            return
        dx = abs(event.x_root - source._drag_start_root_x)
        dy = abs(event.y_root - source._drag_start_root_y)
        if dx < source._drag_threshold and dy < source._drag_threshold:
            return

        # 首次进入拖拽状态 → 创建跟随光标
        if not source._is_dragging:
            source._is_dragging = True
            source.tree.config(cursor="hand2")
            source._create_drag_image(event.x_root, event.y_root)

        # 移动拖拽图标跟随光标
        source._move_drag_image(event.x_root, event.y_root)

        # 检测鼠标是否在对面面板上方 → 高亮目标面板
        other = self.module._left_panel if source.side == "right" \
                else self.module._right_panel
        try:
            widget_under = self.frame.winfo_containing(
                event.x_root, event.y_root)
        except Exception:
            widget_under = None

        is_on_other = False
        if widget_under is not None:
            w = widget_under
            while w is not None:
                if w is other.tree:
                    is_on_other = True
                    break
                if w is source.tree:
                    break
                try:
                    w = w.master
                except Exception:
                    break

        # 高亮/取消高亮
        other._set_drop_highlight(is_on_other)

    def _on_drag_release(self, event):
        source = getattr(self.module, '_drag_source', None)
        self.module._drag_source = None

        # 清除所有面板的高亮
        self.module._left_panel._set_drop_highlight(False)
        self.module._right_panel._set_drop_highlight(False)

        if source is None:
            return

        # 恢复光标
        try:
            source.tree.config(cursor="")
            self.tree.config(cursor="")
        except Exception:
            pass

        if not source._is_dragging or not source._drag_src_path:
            source._reset_drag_state()
            return

        src_path = source._drag_src_path
        source._reset_drag_state()

        if not src_path or not os.path.isdir(src_path):
            return

        # 判断鼠标释放位置是否在对面面板上方
        other = self.module._left_panel if source.side == "right" \
                else self.module._right_panel
        try:
            widget_under = self.frame.winfo_containing(
                event.x_root, event.y_root)
        except Exception:
            return

        if widget_under is None:
            return

        is_on_other = False
        w = widget_under
        while w is not None:
            if w is other.tree:
                is_on_other = True
                break
            if w is source.tree:
                break
            try:
                w = w.master
            except Exception:
                break

        if not is_on_other:
            return

        self.module._do_drop_symlink(src_path, other)

    def _reset_drag_state(self):
        """重置本面板的拖拽状态。"""
        self._drag_item = None
        self._drag_src_path = None
        self._is_dragging = False
        self._destroy_drag_image()
        try:
            self.tree.config(cursor="")
        except Exception:
            pass


# ===== 主模块 =====

class SymlinkCreatorModule(TabModule):
    """符号链接创建模块 — 双面板文件管理器

    开发者模式下普通用户即可创建符号链接，无需管理员权限。
    仅在创建失败（权限不足）时才请求管理员权限，非强制模式。
    """

    TAB_NAME = "符号链接创建"
    TAB_ORDER = 14
    CONFIG_KEY = "symlink_creator"
    PIP_DEPENDENCIES = []
    EXE_REQUIREMENTS = []

    def __init__(self, host):
        super().__init__(host)
        self._left_panel = None
        self._right_panel = None
        self._drag_source = None

    # ===== UI 构建 =====

    def build_ui(self, parent):
        # 开发者模式下普通用户即可创建符号链接，无需管理员权限
        # 仅在创建失败时才请求管理员权限（见 _do_drop_symlink）
        main = ttk.Frame(parent, padding="5")
        main.pack(fill=tk.BOTH, expand=True)

        # ---- 提示栏 ----
        hint = ("拖拽文件夹到对面面板 = 创建符号链接  |  "
                "双击文件夹进入  |  右键复制路径")
        ttk.Label(main, text=hint, foreground="gray").pack(
            anchor=tk.W, pady=(0, 3))

        # ---- 双面板 ----
        self._paned = ttk.PanedWindow(main, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        home = os.path.expanduser("~")
        drives = _get_drives()
        left_start = home
        right_start = drives[0] if drives else "C:\\"

        self._left_panel = _Panel(self, self._paned, "left", left_start)
        self._paned.add(self._left_panel.frame, weight=1)

        self._right_panel = _Panel(self, self._paned, "right", right_start)
        self._paned.add(self._right_panel.frame, weight=1)

        # ---- 操作按钮 ----
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        # 管理员权限请求按钮（由主程序管理状态和点击逻辑）
        self.create_admin_request_button(
            btn_frame, return_tab=self.TAB_NAME
        ).pack(side=tk.LEFT)

        self._ui_built = True

    # ===== 拖拽落点 → 创建符号链接 =====

    def _do_drop_symlink(self, src_path: str, target_panel: _Panel):
        dst_dir = target_panel.get_current_path()
        self.log('info', f"[拖拽] {os.path.basename(src_path)} → {dst_dir}")

        ok, msg_text = _create_one_symlink(src_path, dst_dir)
        if ok:
            self.log('info', f"[OK] {msg_text}")
            target_panel._refresh()
        else:
            self.log('error', f"[FAIL] {msg_text}")

    # ===== 生命周期 =====

    def stop_processing(self):
        pass

    def is_processing(self):
        return False

    def cleanup(self):
        pass

    def save_config(self, config):
        data = {}
        if self._left_panel:
            data["left_path"] = self._left_panel.get_current_path()
        if self._right_panel:
            data["right_path"] = self._right_panel.get_current_path()
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        if not isinstance(config, dict):
            return
        if self._left_panel and config.get("left_path"):
            self._left_panel._navigate_to(config["left_path"])
        if self._right_panel and config.get("right_path"):
            self._right_panel._navigate_to(config["right_path"])

    def clear_memory(self):
        drives = _get_drives()
        home = os.path.expanduser("~")
        if self._left_panel:
            self._left_panel._navigate_to(home)
        if self._right_panel:
            self._right_panel._navigate_to(drives[0] if drives else "C:\\")


MODULE_CLASS = SymlinkCreatorModule
