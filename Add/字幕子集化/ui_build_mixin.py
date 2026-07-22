# -*- coding: utf-8 -*-
"""UI 构建 Mixin：主界面构建与模式切换"""

import tkinter as tk
from tkinter import ttk

from .font_utils import FONTTOOLS_AVAILABLE, SEND2TRASH_AVAILABLE
from .sortable_treeview import SortableTreeview


class UiBuildMixin:
    """UI 构建方法（通过 Mixin 组合到主模块类）"""

    def build_ui(self, parent) -> None:
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)

        # Mode selection
        mode_frame = ttk.LabelFrame(main_frame, text="处理模式", padding="10")
        mode_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        self.mode_ass_rb = ttk.Radiobutton(mode_frame, text="ASS模式（处理ASS字幕文件+子集化字体）",
                       variable=self.mode, value='ass', command=self._on_mode_changed)
        self.mode_ass_rb.grid(row=0, column=0, sticky=tk.W)
        self.mode_mkv_rb = ttk.Radiobutton(mode_frame, text="MKV模式（提取字幕→处理→合并回MKV）",
                       variable=self.mode, value='mkv', command=self._on_mode_changed)
        self.mode_mkv_rb.grid(row=0, column=1, sticky=tk.W, padx=(20, 0))

        # File selection
        file_frame = ttk.LabelFrame(main_frame, text="文件选择", padding="5")
        file_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        file_frame.columnconfigure(1, weight=1)

        self.input_mode = tk.StringVar(value='folder')
        self.input_mode_folder_rb = ttk.Radiobutton(file_frame, text="文件夹输入", variable=self.input_mode,
                       value='folder', command=self._on_input_mode_changed)
        self.input_mode_folder_rb.grid(row=0, column=0, sticky=tk.W)
        self.input_mode_filelist_rb = ttk.Radiobutton(file_frame, text="文件列表", variable=self.input_mode,
                       value='filelist', command=self._on_input_mode_changed)
        self.input_mode_filelist_rb.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        self.folder_path = tk.StringVar()
        self.folder_label = ttk.Label(file_frame, text="输入文件夹:")
        self.folder_label.grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.folder_entry = ttk.Entry(file_frame, textvariable=self.folder_path)
        self.folder_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=(5, 0))
        self.folder_btn = ttk.Button(file_frame, text="浏览...", command=self._browse_input_folder)
        self.folder_btn.grid(row=1, column=2, padx=(5, 0), pady=(5, 0))

        self.file_list_frame = ttk.Frame(file_frame)
        self.file_list_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
        self.file_list_frame.columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(self.file_list_frame, height=1)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        file_list_scroll = ttk.Scrollbar(self.file_list_frame, orient="vertical", command=self.file_listbox.yview)
        file_list_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.file_listbox.config(yscrollcommand=file_list_scroll.set)

        self.file_btn_frame = ttk.Frame(file_frame)
        self.file_btn_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))
        self.add_file_btn = ttk.Button(self.file_btn_frame, text="添加文件...", command=self._add_files)
        self.add_file_btn.pack(side=tk.RIGHT, padx=5)
        self.del_file_btn = ttk.Button(self.file_btn_frame, text="删除选中", command=self._delete_selected_files)
        self.del_file_btn.pack(side=tk.RIGHT, padx=5)
        self.clear_file_btn = ttk.Button(self.file_btn_frame, text="清空列表", command=self._clear_files)
        self.clear_file_btn.pack(side=tk.RIGHT, padx=5)

        # Directory settings
        path_frame = ttk.LabelFrame(main_frame, text="目录设置", padding="5")
        path_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        path_frame.columnconfigure(1, weight=1)

        self.font_dir_label = ttk.Label(path_frame, text="字体库目录:")
        self.font_dir_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.font_dir_entry = ttk.Entry(path_frame, textvariable=self.font_dir)
        self.font_dir_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        self.font_dir_btn = ttk.Button(path_frame, text="浏览...", command=self._browse_font_dir)
        self.font_dir_btn.grid(row=0, column=2, padx=(5, 0))

        self.output_dir_label = ttk.Label(path_frame, text="输出目录:")
        self.output_dir_label.grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.output_dir_entry = ttk.Entry(path_frame, textvariable=self.output_dir)
        self.output_dir_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=(5, 0))
        self.output_dir_btn = ttk.Button(path_frame, text="浏览...", command=self._browse_output_dir)
        self.output_dir_btn.grid(row=1, column=2, padx=(5, 0), pady=(5, 0))

        # Processing options
        options_frame = ttk.LabelFrame(main_frame, text="处理选项", padding="5")
        options_frame.grid(row=3, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        self.create_subsets_cb = ttk.Checkbutton(options_frame, text="生成子集化字体（仅保留必要字形）",
                       variable=self.create_subsets)
        self.create_subsets_cb.grid(row=0, column=0, sticky=tk.W)

        self.embed_back_cb = ttk.Checkbutton(options_frame, text="将处理后的字幕合并回MKV",
                       variable=self.embed_back)
        self.embed_back_cb.grid(row=0, column=1, sticky=tk.W, padx=(20, 0))

        # Delete source file option
        delete_frame = ttk.Frame(options_frame)
        delete_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        self.delete_source_cb = ttk.Checkbutton(delete_frame, text="处理完成后删除源文件",
                       variable=self.delete_source, command=self._on_delete_source_changed)
        self.delete_source_cb.pack(side=tk.LEFT)

        self.delete_method_frame = ttk.Frame(delete_frame)
        self.delete_method_frame.pack(side=tk.LEFT, padx=(10, 0))

        recycle_text = "移动到回收站" if SEND2TRASH_AVAILABLE else "移动到回收站（需安装send2trash）"
        self.recycle_rb = ttk.Radiobutton(self.delete_method_frame, text=recycle_text,
                           variable=self.delete_method, value='recycle')
        self.recycle_rb.pack(side=tk.LEFT)
        if not SEND2TRASH_AVAILABLE:
            self.recycle_rb.config(state='disabled')
            self.delete_method.set('permanent')

        self.permanent_rb = ttk.Radiobutton(self.delete_method_frame, text="永久删除",
                           variable=self.delete_method, value='permanent')
        self.permanent_rb.pack(side=tk.LEFT, padx=(10, 0))

        self.skip_incomplete_cb = ttk.Checkbutton(options_frame, text="仅处理全部字体匹配的文件（跳过缺失字体的文件）",
                       variable=self.skip_incomplete)
        self.skip_incomplete_cb.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        if not FONTTOOLS_AVAILABLE:
            ttk.Label(options_frame, text="未安装fontTools，子集化功能将直接复制完整字体",
                     foreground='orange').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(0, 10))

        self.dissolve_btn = ttk.Button(btn_frame, text="解散数据库", command=self._dissolve_database, width=15)
        self.dissolve_btn.pack(side=tk.RIGHT, padx=5)

        self.process_btn = ttk.Button(btn_frame, text="开始处理", command=self._start_processing,
                                     width=15, state='disabled')
        self.process_btn.pack(side=tk.RIGHT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_processing,
                                  width=15, state='disabled')
        self.stop_btn.pack(side=tk.RIGHT, padx=5)

        self.scan_btn = ttk.Button(btn_frame, text="扫描/分析", command=self._scan_or_analyze, width=15)
        self.scan_btn.pack(side=tk.RIGHT, padx=5)

        # Progress
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, length=400)
        self.progress_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.progress_label = ttk.Label(progress_frame, text="0/0")
        self.progress_label.grid(row=0, column=1, padx=(10, 0))

        self.status_label = ttk.Label(progress_frame, text="就绪")
        self.status_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))

        # Notebook
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # Scan results tab
        self.scan_frame = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(self.scan_frame, text="扫描结果")
        self.scan_frame.columnconfigure(0, weight=1)
        self.scan_frame.rowconfigure(0, weight=1)

        self.scan_tree = SortableTreeview(self.scan_frame, columns=('file', 'fonts', 'status'),
                                      show='headings', height=1)
        self.scan_tree.heading('file', text='文件')
        self.scan_tree.heading('fonts', text='所需字体数')
        self.scan_tree.heading('status', text='状态')
        self.scan_tree.column('file', width=350)
        self.scan_tree.column('fonts', width=80, anchor='center')
        self.scan_tree.column('status', width=120, anchor='center')

        scan_scroll_y = ttk.Scrollbar(self.scan_frame, orient=tk.VERTICAL, command=self.scan_tree.yview)
        scan_scroll_x = ttk.Scrollbar(self.scan_frame, orient=tk.HORIZONTAL, command=self.scan_tree.xview)
        self.scan_tree.configure(yscrollcommand=scan_scroll_y.set, xscrollcommand=scan_scroll_x.set)
        self.scan_tree.grid(row=0, column=0, sticky='nsew')
        scan_scroll_y.grid(row=0, column=1, sticky='ns')
        scan_scroll_x.grid(row=1, column=0, sticky='ew')

        self.scan_tree.bind('<Double-1>', self._on_scan_tree_double_click)

        # Font match tab
        self.font_frame = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(self.font_frame, text="字体匹配")
        self.font_frame.columnconfigure(0, weight=1)
        self.font_frame.rowconfigure(0, weight=1)

        self.font_tree = SortableTreeview(self.font_frame, columns=('requested', 'matched', 'path'),
                                      show='headings', height=1)
        self.font_tree.heading('requested', text='ASS请求字体')
        self.font_tree.heading('matched', text='匹配到的字体')
        self.font_tree.heading('path', text='字体路径')
        self.font_tree.column('requested', width=180)
        self.font_tree.column('matched', width=180)
        self.font_tree.column('path', width=350)

        self.font_tree.tag_configure('missing', foreground='#CC0000')
        self.font_tree.tag_configure('replaced', foreground='blue')
        self.font_tree.set_pinned_tags({'missing', 'replaced'})

        font_scroll_y = ttk.Scrollbar(self.font_frame, orient=tk.VERTICAL, command=self.font_tree.yview)
        font_scroll_x = ttk.Scrollbar(self.font_frame, orient=tk.HORIZONTAL, command=self.font_tree.xview)
        self.font_tree.configure(yscrollcommand=font_scroll_y.set, xscrollcommand=font_scroll_x.set)
        self.font_tree.grid(row=0, column=0, sticky='nsew')
        font_scroll_y.grid(row=0, column=1, sticky='ns')
        font_scroll_x.grid(row=1, column=0, sticky='ew')

        self.font_tree.bind('<Double-1>', self._on_font_tree_double_click)
        self.font_tree.bind('<Button-3>', self._on_font_tree_right_click)
        self._font_tree_menu = None

        # Stats
        self.stats_frame = ttk.Frame(main_frame)
        self.stats_frame.grid(row=7, column=0, columnspan=3, sticky=(tk.W, tk.E))

        self.stats_label = ttk.Label(self.stats_frame, text="统计: 未开始")
        self.stats_label.pack(side=tk.LEFT)

        # 初始化控件状态
        self._update_mode_ui()
        self._on_delete_source_changed()
        self._ui_built = True

    def _on_mode_changed(self) -> None:
        mode = self.mode.get()

        if mode == 'mkv':
            self.embed_back.set(True)
            self.embed_back_cb.config(state='disabled')
        else:
            self.embed_back.set(False)
            self.embed_back_cb.config(state='disabled')

        self._update_mode_ui()
        self._clear_scan_results()
        self._clear_temp_mapping()
        self._clear_files()

    def _on_input_mode_changed(self) -> None:
        self._clear_scan_results()
        self._update_mode_ui()

    def _on_delete_source_changed(self) -> None:
        enabled = self.delete_source.get()
        state = 'normal' if enabled else 'disabled'
        if not SEND2TRASH_AVAILABLE:
            self.recycle_rb.config(state='disabled')
        else:
            self.recycle_rb.config(state=state)
        self.permanent_rb.config(state=state)

    def _update_mode_ui(self) -> None:
        input_mode = self.input_mode.get()

        if input_mode == 'folder':
            self.folder_label.grid()
            self.folder_entry.grid()
            self.folder_btn.grid()
            self.file_list_frame.grid_remove()
            self.file_btn_frame.grid_remove()
        else:
            self.folder_label.grid_remove()
            self.folder_entry.grid_remove()
            self.folder_btn.grid_remove()
            self.file_list_frame.grid()
            self.file_btn_frame.grid()
