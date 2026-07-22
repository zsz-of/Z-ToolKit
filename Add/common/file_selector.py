# -*- coding: utf-8 -*-
"""统一文件选择器组件

提供 FileSelector 主类，支持文件夹扫描和手动文件列表两种模式，
按扩展名过滤（video / subtitle / all），并通过 filter_func 接口
支持业务侧自定义过滤逻辑。

兼容性：
- UnifiedFileSelector 为 FileSelector 的别名（无过滤逻辑）。
- MKVEmbedFileSelector 预置字幕内封专用过滤逻辑（mkv 文件需有同名文件夹）。

filter_func 接口规范：
    def filter_func(file_path: str) -> Tuple[bool, str]:
        返回 (is_valid, status_text)
        - is_valid=True 表示文件可处理；False 表示跳过（标记为红色）
        - status_text 为状态列显示文本（如 "可处理"/"跳过"）
        - 返回 None 视为有效且无状态文本
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from typing import Callable, Optional, Tuple


class FileSelector:
    """统一文件选择器

    支持两种输入模式：
    - 文件夹模式：递归扫描指定文件夹下匹配扩展名的文件
    - 文件列表模式：手动添加/移除文件

    通过 filter_func 接口支持业务侧过滤：
    - filter_func 为 None 时，所有匹配扩展名的文件均视为有效
    - filter_func 不为 None 时，显示状态列，按业务逻辑标记有效性

    扩展名过滤：
    - supported_types='video'：仅视频文件
    - supported_types='subtitle'：仅字幕文件
    - supported_types='all'：视频 + 字幕
    """

    VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.wmv',
                       '.mpg', '.mpeg', '.m4v', '.3gp', '.ts', '.m2ts', '.mts'}
    SUBTITLE_EXTENSIONS = {'.ass', '.srt', '.ssa'}

    def __init__(self, parent, supported_types='video',
                 filter_func: Optional[Callable[[str], Optional[Tuple[bool, str]]]] = None):
        self.parent = parent
        self.file_list = []                # 文件列表模式下的文件
        self.folder_file_list = []         # 文件夹模式下扫描到的文件
        self.supported_types = supported_types
        self.filter_func = filter_func     # 业务侧过滤函数
        self.invalid_files = set()         # 被 filter_func 标记为无效的文件
        self._build_ui()

    # ========== UI 构建 ==========

    def _build_ui(self):
        mode_frame = ttk.LabelFrame(self.parent, text="输入模式", padding="5")
        mode_frame.pack(fill=tk.X, pady=(0, 5))

        self.mode_var = tk.StringVar(value="folder")

        ttk.Radiobutton(mode_frame, text="文件夹", variable=self.mode_var,
                       value="folder", command=self._switch_mode).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="文件列表", variable=self.mode_var,
                       value="filelist", command=self._switch_mode).pack(side=tk.LEFT, padx=10)

        self.content_frame = ttk.Frame(self.parent)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        self._switch_mode()

    def _switch_mode(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        if self.mode_var.get() == "folder":
            self._create_folder_mode()
        else:
            self._create_filelist_mode()

    def _create_folder_mode(self):
        path_frame = ttk.Frame(self.content_frame)
        path_frame.pack(fill=tk.X, pady=5)

        self.folder_var = tk.StringVar()
        self.folder_entry = ttk.Entry(path_frame, textvariable=self.folder_var, state='readonly')
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(path_frame, text="浏览...", command=self._browse_folder).pack(side=tk.RIGHT)

        # 状态标签文案：有 filter_func 时显示有效数量
        initial_text = "已找到: 0 个文件 (0 个可处理)" if self.filter_func else "已找到: 0 个文件"
        self.folder_count_label = ttk.Label(self.content_frame, text=initial_text)
        self.folder_count_label.pack(anchor=tk.W, pady=(5, 0))

        list_frame = ttk.LabelFrame(self.content_frame, text="扫描结果", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # 列定义：有 filter_func 时显示状态列
        if self.filter_func:
            columns = ('filename', 'size', 'status')
        else:
            columns = ('filename', 'size')

        self.folder_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=1)
        self.folder_tree.heading('filename', text='文件名')
        self.folder_tree.heading('size', text='大小')
        self.folder_tree.column('filename', width=280)
        self.folder_tree.column('size', width=80, anchor='e')

        if self.filter_func:
            self.folder_tree.heading('status', text='状态')
            self.folder_tree.column('status', width=80, anchor='center')
            self.folder_tree.tag_configure(
                'invalid', foreground='#CC0000', font=('Consolas', 9, 'overstrike'))

        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.folder_tree.yview)
        scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.folder_tree.xview)
        self.folder_tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.folder_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar_y.grid(row=0, column=1, sticky='ns')
        scrollbar_x.grid(row=1, column=0, sticky='ew')

        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

    def _create_filelist_mode(self):
        list_frame = ttk.LabelFrame(self.content_frame, text="已选文件", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ('filename',)
        self.filelist_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=1)
        self.filelist_tree.heading('filename', text='文件路径')
        self.filelist_tree.column('filename', width=400)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.filelist_tree.yview)
        self.filelist_tree.configure(yscrollcommand=scrollbar.set)

        self.filelist_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        ttk.Button(btn_frame, text="添加文件", command=self._add_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self._clear_list).pack(side=tk.LEFT, padx=5)

        self.list_count_label = ttk.Label(btn_frame, text="已添加: 0 个文件")
        self.list_count_label.pack(side=tk.LEFT, padx=20)

        self._refresh_filelist_display()

    # ========== 文件夹模式 ==========

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            self.folder_var.set(folder)
            self._scan_folder()

    def _get_extensions_and_desc(self):
        """返回 (扩展名集合, 文件描述)"""
        if self.supported_types == 'video':
            return self.VIDEO_EXTENSIONS, "视频"
        if self.supported_types == 'subtitle':
            return self.SUBTITLE_EXTENSIONS, "字幕"
        return self.VIDEO_EXTENSIONS | self.SUBTITLE_EXTENSIONS, "文件"

    def _scan_folder(self):
        folder = self.folder_var.get()
        if not folder or not Path(folder).is_dir():
            return

        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)
        self.folder_file_list.clear()
        self.invalid_files.clear()

        extensions, file_desc = self._get_extensions_and_desc()
        folder_path = Path(folder)
        count = 0
        valid_count = 0

        for file_path in sorted(folder_path.rglob('*')):
            if not file_path.is_file() or file_path.suffix.lower() not in extensions:
                continue

            abs_path = str(file_path.resolve())
            self.folder_file_list.append(abs_path)

            display_name = file_path.name
            size_kb = file_path.stat().st_size / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"

            # 调用业务过滤逻辑
            if self.filter_func:
                result = self.filter_func(abs_path)
                if result is None:
                    is_valid, status_text = True, ""
                else:
                    is_valid, status_text = result
                if not is_valid:
                    self.invalid_files.add(abs_path)
                    tags = ('invalid',)
                    if not status_text:
                        status_text = "跳过"
                else:
                    tags = ()
                    if not status_text:
                        status_text = "可处理"
                    valid_count += 1
                self.folder_tree.insert(
                    '', tk.END, values=(display_name, size_str, status_text), tags=tags)
            else:
                self.folder_tree.insert('', tk.END, values=(display_name, size_str))
                valid_count += 1
            count += 1

        if self.filter_func:
            self.folder_count_label.config(
                text=f"已找到: {count} 个{file_desc}文件 ({valid_count} 个可处理)")
        else:
            self.folder_count_label.config(text=f"已找到: {count} 个{file_desc}文件")

    # ========== 文件列表模式 ==========

    def _add_files(self):
        if self.supported_types == 'video':
            filetypes = [("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.webm *.wmv *.mpg *.mpeg *.m4v"),
                        ("所有文件", "*.*")]
        elif self.supported_types == 'subtitle':
            filetypes = [("字幕文件", "*.ass *.srt *.ssa"), ("所有文件", "*.*")]
        else:
            filetypes = [("所有支持文件", "*.mp4 *.mkv *.avi *.ass *.srt *.ssa"), ("所有文件", "*.*")]

        files = filedialog.askopenfilenames(title="选择文件", filetypes=filetypes)

        added = 0
        for file in files:
            normalized = str(Path(file).resolve())
            if normalized not in self.file_list:
                self.file_list.append(normalized)
                added += 1

        self._refresh_filelist_display()

    def _remove_selected(self):
        selected = self.filelist_tree.selection()
        indices_to_remove = []
        for item_id in selected:
            index = self.filelist_tree.index(item_id)
            if 0 <= index < len(self.file_list):
                indices_to_remove.append(index)

        for index in sorted(indices_to_remove, reverse=True):
            del self.file_list[index]

        self._refresh_filelist_display()

    def _clear_list(self):
        self.file_list.clear()
        self._refresh_filelist_display()

    def _update_list_buttons(self):
        count = len(self.file_list)
        self.list_count_label.config(text=f"已添加: {count} 个文件")

    def _refresh_filelist_display(self):
        if not hasattr(self, 'filelist_tree') or not self.filelist_tree.winfo_exists():
            return

        for item in self.filelist_tree.get_children():
            self.filelist_tree.delete(item)

        for file_path in self.file_list:
            display_name = Path(file_path).name
            self.filelist_tree.insert('', tk.END, values=(display_name,))

        self._update_list_buttons()

    # ========== 外部查询接口 ==========

    def get_files(self):
        """返回当前模式下所有匹配扩展名的文件列表（不过滤有效性）"""
        if self.mode_var.get() == "folder":
            return self.folder_file_list.copy()
        return self.file_list.copy()

    def get_file_count(self):
        """返回当前模式下的文件总数"""
        if self.mode_var.get() == "folder":
            return len(self.folder_file_list)
        return len(self.file_list)

    def get_valid_files(self):
        """返回有效文件列表（被 filter_func 标记为无效的文件被排除）

        若未设置 filter_func，等同 get_files()。
        """
        if not self.filter_func:
            return self.get_files()

        if self.mode_var.get() == "folder":
            return [f for f in self.folder_file_list if f not in self.invalid_files]

        # 文件列表模式：对每个文件调用 filter_func
        valid = []
        for f in self.file_list:
            result = self.filter_func(f)
            if result is None:
                valid.append(f)
            elif result[0]:
                valid.append(f)
        return valid


# ========== 兼容别名 ==========

# UnifiedFileSelector：无过滤逻辑的统一选择器
UnifiedFileSelector = FileSelector


def _mkv_embed_filter(file_path: str) -> Tuple[bool, str]:
    """字幕内封专用过滤逻辑：mkv 文件必须有同名文件夹（用于存放字幕）

    返回:
        (True, "可处理")：非 mkv 文件或存在同名文件夹
        (False, "跳过")：mkv 文件且不存在同名文件夹
    """
    video_name = os.path.splitext(os.path.basename(file_path))[0]
    video_dir = os.path.dirname(file_path)
    subtitle_folder = os.path.join(video_dir, video_name)
    if file_path.lower().endswith('.mkv') and not os.path.isdir(subtitle_folder):
        return False, "跳过"
    return True, "可处理"


class MKVEmbedFileSelector(FileSelector):
    """字幕内封专用文件选择器（兼容旧 API）

    预置 filter_func：mkv 文件必须有同名文件夹（用于存放字幕），
    否则标记为"跳过"。
    """

    def __init__(self, parent, supported_types='video'):
        super().__init__(parent, supported_types=supported_types, filter_func=_mkv_embed_filter)
