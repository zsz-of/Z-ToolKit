# -*- coding: utf-8 -*-
"""字幕子集化生成器模块 - 主模块入口

将原 subtitle_subset_generator.py（4148+ 行）拆分为包结构，
每个文件 ≤350 行，通过 Mixin 模式组合主类，保持类 API 不变。
"""

import os
import threading
import tkinter as tk
from typing import Optional, List, Dict, Any, Set, Tuple, Callable

from common import TabModule

from .font_utils import (
    FONTTOOLS_AVAILABLE, SEND2TRASH_AVAILABLE, FONT_EXTENSIONS,
    LogLevel, LOG_LEVEL_TO_HOST, PluginBase, PluginRegistry,
    SystemFontCache, RandomNameManager, rmtree_onerror,
)
from .font_database import FontDatabase
from .ass_parser import ASSParser
from .font_subsetter import FontSubsetGenerator
from .mkv_extractor import MKVExtractor
from .sortable_treeview import SortableTreeview

from .ui_build_mixin import UiBuildMixin
from .ui_helpers_mixin import UiHelpersMixin
from .scan_mixin import ScanMixin
from .scan_workers_mixin import ScanWorkersMixin
from .font_match_mixin import FontMatchMixin
from .font_detail_mixin import FontDetailMixin
from .process_mixin import ProcessMixin
from .process_helpers_mixin import ProcessHelpersMixin


class SubtitleSubsetGeneratorModule(
    UiBuildMixin,
    UiHelpersMixin,
    ScanMixin,
    ScanWorkersMixin,
    FontMatchMixin,
    FontDetailMixin,
    ProcessMixin,
    ProcessHelpersMixin,
    TabModule,
):
    """字幕子集化生成器模块"""
    TAB_NAME = "字幕子集化"
    TAB_ORDER = 13
    CONFIG_KEY = "subtitle_subset"
    PIP_DEPENDENCIES = []
    OPTIONAL_PIP_DEPENDENCIES = ['fontTools', 'send2trash']  # 可选依赖，模块内有降级处理
    EXE_REQUIREMENTS = ['mkvextract', 'mkvmerge', 'hb-subset']

    def __init__(self, host):
        super().__init__(host)

        self.font_db: Optional[FontDatabase] = None
        self.subset_generator: Optional[FontSubsetGenerator] = None
        # MKVExtractor 不再自己查找工具路径，由主程序外部工具管理统一提供
        self.mkv_extractor = MKVExtractor()
        self.random_name_mgr = RandomNameManager()
        self.system_font_cache = SystemFontCache.get_instance()
        self._detail_window: Optional[tk.Toplevel] = None
        self._detail_file_path: Optional[str] = None

        self.processing = False
        self.scanning = False
        self.current_thread: Optional[threading.Thread] = None
        self.total_tasks = 0
        self._completed_tasks = 0
        self._skip_incomplete = False
        self._skipped_count = 0
        self._completed_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._current_subprocesses: List = []
        self._subprocess_lock = threading.Lock()

        self._scan_results_lock = threading.RLock()
        self._extracted_ass_map_lock = threading.Lock()
        self._temp_mapping_lock = threading.Lock()

        self.mode = tk.StringVar(value='ass')
        self.ass_files: List[str] = []
        self.mkv_files: List[str] = []

        self.font_dir = tk.StringVar()
        self.output_dir = tk.StringVar()

        self.create_subsets = tk.BooleanVar(value=True)
        self.embed_back = tk.BooleanVar(value=True)
        self.delete_source = tk.BooleanVar(value=False)
        self.delete_method = tk.StringVar(value='recycle')
        self.skip_incomplete = tk.BooleanVar(value=False)

        self.scan_results: Dict[str, Dict[str, Any]] = {}
        self.extracted_ass_map: Dict[str, List] = {}

        # 清理上次运行遗留的临时目录
        FontSubsetGenerator.cleanup_old_temp_dirs()

    def load_config(self, config) -> None:
        """从模块专属配置字典加载配置（由主程序在 build_ui 后调用）"""
        cfg = config if config else {}

        try:
            self.font_dir.set(cfg.get('font_dir', ''))
            self.output_dir.set(cfg.get('output_dir', ''))
            self.folder_path.set(cfg.get('folder_path', ''))
            self.mode.set(cfg.get('mode', 'ass'))
            self.input_mode.set(cfg.get('input_mode', 'folder'))
            self.delete_source.set(cfg.get('delete_source', False))
            saved_delete_method = cfg.get('delete_method', 'recycle')
            if not SEND2TRASH_AVAILABLE or saved_delete_method not in ('recycle', 'permanent'):
                self.delete_method.set('permanent')
            else:
                self.delete_method.set(saved_delete_method)
            self.create_subsets.set(cfg.get('create_subsets', True))
            self.skip_incomplete.set(cfg.get('skip_incomplete', False))

            if self.mode.get() == 'mkv':
                self.embed_back.set(True)
                self.embed_back_cb.config(state='disabled')
            else:
                self.embed_back.set(False)
                self.embed_back_cb.config(state='disabled')
        except (OSError, KeyError):
            pass

        # mkvextract_path / mkvmerge_path 由主程序外部工具管理统一提供，不再从模块配置加载
        self._refresh_external_tools()

        self._update_mode_ui()

    def _refresh_external_tools(self) -> None:
        """从主程序外部工具管理获取 mkvextract/mkvmerge/hb-subset 路径并更新到内部对象"""
        try:
            mkvextract_path = self.get_exe_path('mkvextract')
            mkvmerge_path = self.get_exe_path('mkvmerge')
            self.mkv_extractor.update_paths(mkvextract_path, mkvmerge_path)
            hb_subset_path = self.get_exe_path('hb-subset')
            if self.subset_generator is not None:
                self.subset_generator.hb_subset_path = hb_subset_path
        except Exception:
            pass

    def save_config(self, config) -> None:
        """保存模块配置到共享配置字典（mkvextract/mkvmerge/hb-subset 路径由主程序外部工具管理统一保存）"""
        config[self.config_key] = {
            'font_dir': self.font_dir.get(),
            'output_dir': self.output_dir.get(),
            'folder_path': self.folder_path.get() if hasattr(self, 'folder_path') else '',
            'mode': self.mode.get(),
            'input_mode': self.input_mode.get() if hasattr(self, 'input_mode') else 'folder',
            'delete_source': self.delete_source.get(),
            'delete_method': self.delete_method.get(),
            'create_subsets': self.create_subsets.get(),
            'skip_incomplete': self.skip_incomplete.get(),
        }

    def clear_memory(self) -> None:
        """清除记忆，重置为默认值"""
        self.font_dir.set('')
        self.output_dir.set('')
        if hasattr(self, 'folder_path'):
            self.folder_path.set('')
        self.mode.set('ass')
        if hasattr(self, 'input_mode'):
            self.input_mode.set('folder')
        self.delete_source.set(False)
        self.delete_method.set('permanent' if not SEND2TRASH_AVAILABLE else 'recycle')
        self.create_subsets.set(True)
        self.skip_incomplete.set(False)
        self.embed_back.set(False)
        # 重置工具路径对象，路径由主程序外部工具管理统一维护
        self.mkv_extractor = MKVExtractor()
        # 仅在 UI 已构建时刷新控件状态
        if getattr(self, '_ui_built', False):
            self._update_mode_ui()
            self._on_delete_source_changed()

    def stop_processing(self) -> None:
        """停止当前处理（由主程序调用）"""
        if (self.processing or self.scanning) and hasattr(self, '_stop_processing'):
            self._stop_processing()

    def is_processing(self) -> bool:
        """是否正在处理中"""
        return self.processing or self.scanning

    def cleanup(self) -> None:
        """程序关闭时清理资源"""
        # 停止处理
        self.processing = False
        self.scanning = False
        self._stop_event.set()
        with self._subprocess_lock:
            procs = list(self._current_subprocesses)
            self._current_subprocesses.clear()
        for proc in procs:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

        # 还原重命名的文件
        if self.random_name_mgr.name_map:
            try:
                self.random_name_mgr.restore_all()
            except Exception:
                pass

        # 清理随机名称管理器
        try:
            self.random_name_mgr.delete_mapping_file()
            self.random_name_mgr.clear()
        except Exception:
            pass

        # 清理字体数据库
        if self.font_db is not None:
            try:
                self.font_db.cleanup()
            except Exception:
                pass

        # 清理子集生成器临时资源
        if self.subset_generator is not None:
            try:
                self.subset_generator.cleanup()
            except Exception:
                pass


# 模块导出
MODULE_CLASS = SubtitleSubsetGeneratorModule
