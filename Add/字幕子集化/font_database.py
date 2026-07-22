# -*- coding: utf-8 -*-
"""字体数据库核心类：整合组织器、扫描器、加载器 Mixin，提供字体查找接口"""

import os
import re
import threading
from typing import Optional, Dict, Any, Tuple, Callable

from .font_database_organizer import FontDatabaseOrganizerMixin
from .font_database_scanner import FontDatabaseScannerMixin
from .font_database_loader import FontDatabaseLoaderMixin


class FontDatabase(FontDatabaseOrganizerMixin, FontDatabaseScannerMixin, FontDatabaseLoaderMixin):
    """字体数据库：管理字体文件的 SQLite 缓存，提供 O(1) 内存查找"""

    def __init__(self, font_root: str, progress_callback: Optional[Callable] = None):
        self.font_root = font_root
        self._progress_callback = progress_callback
        self._db_lock = threading.RLock()

        self.font_count = 0
        self.face_count = 0
        self._new_font_count = 0
        self._error_count = 0

        self._sub_dbs: list = []
        self._sub_folders: list = []

        # 内存查找表：将 find_font 从 O(N) SQL 查询优化为 O(1) 字典查找
        self._lookup_name_lower: Dict[str, Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]] = {}
        self._lookup_name_no_space: Dict[str, Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]] = {}
        self._lookup_normalized: Dict[str, Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]] = {}

        self._compact_and_organize()

        self._load_all_databases()

    def _resolve_path(self, rel_path: str) -> str:
        if os.path.isabs(rel_path):
            return rel_path
        return os.path.normpath(os.path.join(self.font_root, rel_path))

    def find_font(self, font_name: str) -> Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]:
        if not font_name:
            return None, None, None

        query = font_name.strip()
        query_lower = query.lower()
        query_no_space = re.sub(r'[\s\-_]+', '', query_lower)

        with self._db_lock:
            # 优先级1：精确大小写不敏感匹配
            result = self._lookup_name_lower.get(query_lower)
            if result is not None:
                return result

            # 优先级2：去空格/横线/下划线匹配
            result = self._lookup_name_no_space.get(query_no_space)
            if result is not None:
                return result

            # 优先级3：Unicode 规范化匹配（仅当与去空格结果不同时）
            query_normalized = self._normalize_for_match(query)
            if query_normalized != query_no_space:
                result = self._lookup_normalized.get(query_normalized)
                if result is not None:
                    return result

        return None, None, None

    def get_all_fonts(self) -> Dict[str, Dict[str, Any]]:
        fonts = {}
        with self._db_lock:
            for conn in self._sub_dbs:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT f.file_path, f.font_index, f.format, f.weight, f.slant, f.is_collection,
                           GROUP_CONCAT(CASE WHEN fn.name_type = 'family' THEN fn.name END, '|') as families
                    FROM fonts f
                    LEFT JOIN font_names fn ON f.id = fn.font_id
                    GROUP BY f.id, f.file_path, f.font_index
                ''')

                for row in cursor.fetchall():
                    filepath = self._resolve_path(row[0])
                    font_index = row[1]
                    fonts[(filepath, font_index)] = {
                        'path': filepath,
                        'index': font_index,
                        'format': row[2],
                        'weight': row[3],
                        'slant': row[4],
                        'is_collection': bool(row[5]),
                        'families': row[6].split('|') if row[6] else []
                    }
        return fonts

    def get_all_font_names(self) -> Dict[str, list]:
        """返回字体名称到文件路径列表的映射（仅 family 类型名称）"""
        result: Dict[str, list] = {}
        with self._db_lock:
            for conn in self._sub_dbs:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT fn.name, f.file_path
                    FROM font_names fn
                    JOIN fonts f ON fn.font_id = f.id
                    WHERE fn.name_type = 'family'
                ''')
                for row in cursor.fetchall():
                    name = row[0]
                    path = self._resolve_path(row[1])
                    if name not in result:
                        result[name] = []
                    if path not in result[name]:
                        result[name].append(path)
        return result

    def cleanup(self) -> None:
        with self._db_lock:
            for conn in self._sub_dbs:
                try:
                    conn.close()
                except Exception:
                    pass
            self._sub_dbs = []
            self._lookup_name_lower.clear()
            self._lookup_name_no_space.clear()
            self._lookup_normalized.clear()

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass
