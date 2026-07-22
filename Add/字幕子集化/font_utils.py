# -*- coding: utf-8 -*-
"""字体工具模块：常量、日志、插件系统、系统字体缓存、随机命名管理"""

import os
import re
import json
import shutil
import stat
import random
import string
import threading
from enum import IntEnum
from typing import Optional, Dict, List, Callable

# ========== Constants ==========

FONT_EXTENSIONS = frozenset({'.ttf', '.ttc', '.otf', '.otc'})

FONTS_PER_SUBFOLDER = 2000

MKVEXTRACT_TIMEOUT = 300
MKVMERGE_TIMEOUT = 600

RANDOM_NAME_LENGTH = 64
SUBSET_IDENTIFIER_LENGTH = 8

# 数据库结构版本号，修改表结构/索引/列时必须同步递增此版本号，旧版数据库将自动重建
DB_SCHEMA_VERSION = '1.4.0'

# ========== Optional Dependencies ==========

try:
    import fontTools.ttLib as ttLib
    from fontTools.subset import Subsetter, Options as SubsetOptions
    FONTTOOLS_AVAILABLE = True
except ImportError:
    FONTTOOLS_AVAILABLE = False

try:
    from send2trash import send2trash
    SEND2TRASH_AVAILABLE = True
except ImportError:
    SEND2TRASH_AVAILABLE = False


# ========== Log System ==========

class LogLevel(IntEnum):
    INFO = 0
    NOTICE = 1
    WARNING = 2
    ERROR = 3


# LogLevel 到主程序日志级别的映射（供 FontSubsetGenerator 的 log_callback 使用）
LOG_LEVEL_TO_HOST = {
    LogLevel.INFO: 'info',
    LogLevel.NOTICE: 'info',
    LogLevel.WARNING: 'warning',
    LogLevel.ERROR: 'error',
}


# ========== Plugin System ==========

class PluginBase:
    name: str = ""
    description: str = ""

    def on_font_matched(self, font_name: str, matched_path: Optional[str], info: Optional[dict]) -> None:
        pass

    def on_file_processed(self, ass_path: str, output_path: Optional[str], success: bool) -> None:
        pass

    def on_batch_complete(self, total: int, success: int, failed: int) -> None:
        pass


class PluginRegistry:
    _plugins: List[PluginBase] = []

    @classmethod
    def register(cls, plugin: PluginBase) -> None:
        cls._plugins.append(plugin)

    @classmethod
    def unregister(cls, plugin: PluginBase) -> None:
        cls._plugins.remove(plugin)

    @classmethod
    def notify(cls, event: str, **kwargs) -> None:
        for plugin in cls._plugins:
            handler = getattr(plugin, f'on_{event}', None)
            if handler:
                try:
                    handler(**kwargs)
                except Exception:
                    pass


# ========== System Font Cache ==========

class SystemFontCache:
    _instance: Optional['SystemFontCache'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._font_names: set = set()
        self._loaded = False
        self._data_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'SystemFontCache':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_system_font(self, font_name: str) -> bool:
        with self._data_lock:
            if not self._loaded:
                self._load_locked()
                self._loaded = True
            return font_name.lower() in self._font_names

    def _load_locked(self):
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            ]
            for hkey, subkey in reg_paths:
                try:
                    key = winreg.OpenKey(hkey, subkey)
                    i = 0
                    while True:
                        try:
                            value_name, _, _ = winreg.EnumValue(key, i)
                            display_name = value_name.split('(')[0].strip()
                            self._font_names.add(display_name.lower())
                            i += 1
                        except OSError:
                            break
                    winreg.CloseKey(key)
                except OSError:
                    pass
        except Exception:
            pass


# ========== Random Name Manager ==========

class RandomNameManager:
    def __init__(self):
        self._name_map: Dict[str, str] = {}
        self._lock = threading.Lock()
        self._mapping_file: Optional[str] = None

    @property
    def name_map(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._name_map)

    def get_random_name(self, original_path: str) -> Optional[str]:
        with self._lock:
            return self._name_map.get(original_path)

    @property
    def mapping_file(self) -> Optional[str]:
        return self._mapping_file

    def generate_mapping(self, file_paths: List[str], output_dir: str) -> None:
        with self._lock:
            self._name_map = {}
            used_names: set = set()
            for path in file_paths:
                random_name = self._generate_unique_random_name(used_names, path)
                self._name_map[path] = random_name
                used_names.add(random_name)
            self._mapping_file = self._get_mapping_file_path(output_dir)
            if self._mapping_file:
                mapping_data = {}
                for orig_path, rand_name in self._name_map.items():
                    mapping_data[orig_path] = {
                        'random_name': rand_name,
                        'extension': os.path.splitext(orig_path)[1]
                    }
                os.makedirs(os.path.dirname(self._mapping_file), exist_ok=True)
                with open(self._mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(mapping_data, f, ensure_ascii=False, indent=2)

    def get_random_path(self, original_path: str) -> str:
        with self._lock:
            random_name = self._name_map.get(original_path)
        if not random_name:
            return original_path
        dir_name = os.path.dirname(original_path)
        return os.path.join(dir_name, random_name)

    def rename_with_random(self, original_path: str) -> str:
        random_path = self.get_random_path(original_path)
        if random_path == original_path:
            return original_path
        if os.path.exists(original_path) and not os.path.exists(random_path):
            try:
                os.rename(original_path, random_path)
            except OSError:
                shutil.move(original_path, random_path)
        return random_path

    def restore_original_name(self, random_path: str, original_path: str) -> bool:
        if random_path == original_path:
            return True
        if os.path.exists(random_path) and not os.path.exists(original_path):
            try:
                os.rename(random_path, original_path)
            except OSError:
                shutil.move(random_path, original_path)
            return True
        return False

    def restore_all(self, progress_callback=None) -> int:
        with self._lock:
            items = list(self._name_map.items())
        total = len(items)
        restored = 0
        for i, (original_path, random_name) in enumerate(items):
            dir_name = os.path.dirname(original_path)
            random_path = os.path.join(dir_name, random_name)
            if self.restore_original_name(random_path, original_path):
                restored += 1
            if progress_callback:
                progress_callback(i + 1, total)
        return restored

    def delete_mapping_file(self) -> None:
        if self._mapping_file and os.path.exists(self._mapping_file):
            try:
                os.remove(self._mapping_file)
            except Exception:
                pass
        self._mapping_file = None

    def clear(self) -> None:
        with self._lock:
            self._name_map.clear()
            self._mapping_file = None

    def _generate_unique_random_name(self, used_names: set, original_path: str) -> str:
        ext = os.path.splitext(original_path)[1]
        chars = string.ascii_letters + string.digits
        for _ in range(100):
            name = ''.join(random.choice(chars) for _ in range(RANDOM_NAME_LENGTH))
            if name not in used_names:
                return name + ext
        raise RuntimeError(f"无法为 {original_path} 生成唯一随机名")

    def _get_mapping_file_path(self, output_dir: str) -> Optional[str]:
        if not output_dir:
            return None
        temp_dir = os.path.join(output_dir, 'Temp')
        return os.path.join(temp_dir, '.random_name_mapping.json')


# ========== Utility Functions ==========

def rmtree_onerror(func, path, exc_info):
    """shutil.rmtree 的错误处理回调，尝试修改权限后重试"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass
