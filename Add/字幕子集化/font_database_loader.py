# -*- coding: utf-8 -*-
"""字体数据库加载器 Mixin：多线程数据库加载、内存查找表构建、规范化"""

import os
import re
import sqlite3
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, Tuple, List

from .font_utils import FONTS_PER_SUBFOLDER


class FontDatabaseLoaderMixin:
    """FontDatabase 的数据库加载与内存查找表构建方法"""

    def _load_all_databases(self) -> None:
        for conn in self._sub_dbs:
            try:
                conn.close()
            except Exception:
                pass
        self._sub_dbs = []
        self._sub_folders = []
        self.font_count = 0
        self.face_count = 0

        sub_folders = self._get_sub_folders()

        rebuild_folders = []
        skip_folders = []
        for folder in sub_folders:
            if self._check_rebuild_needed(folder):
                rebuild_folders.append(folder)
            else:
                skip_folders.append(folder)

        # 先处理可跳过的文件夹（加载已有缓存）
        for folder in skip_folders:
            conn = None
            try:
                conn = sqlite3.connect(os.path.join(folder, '.font_cache.db'), check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM meta WHERE key = 'font_count'")
                row = cursor.fetchone()
                fc = int(row[0]) if row else 0
                cursor.execute("SELECT value FROM meta WHERE key = 'face_count'")
                row = cursor.fetchone()
                fac = int(row[0]) if row else 0

                self._sub_dbs.append(conn)
                self._sub_folders.append(folder)
                self.font_count += fc
                self.face_count += fac
                conn = None  # 成功添加，不再需要关闭
            except Exception as e:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                if self._progress_callback:
                    self._progress_callback(0, 0, 0, f"加载缓存失败，将重建: {os.path.basename(folder)}")
                rebuild_folders.append(folder)

        # 多线程并行扫描需要重建的子文件夹（最多4线程）
        if rebuild_folders:
            global_total_fonts = sum(self._collect_font_files(f)[1] for f in rebuild_folders)

            if self._progress_callback and global_total_fonts > 0:
                self._progress_callback(0, 0, global_total_fonts,
                                        f"正在并行扫描 {len(rebuild_folders)} 个字体子库...")

            shared_processed = [0]
            progress_lock = threading.Lock()

            def _process_folder_thread(folder: str) -> Tuple[str, sqlite3.Connection, int, int, int]:
                """单个子文件夹的扫描线程"""
                conn = self._init_database(folder)
                fc, fac, ec = self._scan_fonts_to_db(
                    conn, folder,
                    shared_processed=shared_processed,
                    global_total=global_total_fonts,
                    progress_lock=progress_lock
                )
                return folder, conn, fc, fac, ec

            results: Dict[str, Tuple[str, sqlite3.Connection, int, int, int]] = {}
            with ThreadPoolExecutor(max_workers=min(8, len(rebuild_folders))) as executor:
                futures = {executor.submit(_process_folder_thread, f): f for f in rebuild_folders}
                for future in as_completed(futures):
                    folder = futures[future]
                    try:
                        result = future.result()
                        results[result[0]] = result
                    except Exception as e:
                        if self._progress_callback:
                            self._progress_callback(0, 0, 0,
                                                    f"扫描子库失败: {os.path.basename(folder)} ({e})")

            # 按原始文件夹顺序添加结果，保持 _sub_dbs 顺序一致
            for folder in rebuild_folders:
                if folder in results:
                    _, conn, fc, fac, ec = results[folder]
                    self._sub_dbs.append(conn)
                    self._sub_folders.append(folder)
                    self.font_count += fc
                    self.face_count += fac
                    self._error_count += ec

            if self._progress_callback and global_total_fonts > 0:
                self._progress_callback(100, global_total_fonts, global_total_fonts, "字体库扫描完成")

        # 构建内存查找表，替代逐次 SQL 查询
        self._build_lookup_cache()

    def _build_lookup_cache(self) -> None:
        """从所有子数据库加载 font_names 记录，构建内存查找表"""
        # 先构建新的查找表，成功后原子替换，避免异常时查找表为空
        new_name_lower: Dict[str, Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]] = {}
        new_name_no_space: Dict[str, Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]] = {}
        new_normalized: Dict[str, Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]] = {}

        for conn in self._sub_dbs:
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT f.file_path, f.font_index, f.format, f.weight, f.slant,
                           f.is_collection, fn.name, fn.name_type, fn.normalized_name
                    FROM fonts f
                    JOIN font_names fn ON f.id = fn.font_id
                    ORDER BY f.font_index
                ''')

                for row in cursor.fetchall():
                    file_path, font_index, fmt, weight, slant, is_collection, name, name_type, normalized_name = row

                    resolved = self._resolve_path(file_path)
                    info = {
                        'format': fmt,
                        'weight': weight,
                        'slant': slant,
                        'is_collection': bool(is_collection),
                        'matched_name': name,
                        'matched_type': name_type
                    }
                    result = (resolved, font_index, info)

                    name_lower = name.lower()
                    if name_lower not in new_name_lower:
                        new_name_lower[name_lower] = result

                    name_no_space = re.sub(r'[\s\-_]+', '', name_lower)
                    if name_no_space not in new_name_no_space:
                        new_name_no_space[name_no_space] = result

                    if normalized_name and normalized_name not in new_normalized:
                        new_normalized[normalized_name] = result
            except Exception as e:
                if self._progress_callback:
                    self._progress_callback(0, 0, 0, f"加载查找缓存失败: {e}")

        self._lookup_name_lower = new_name_lower
        self._lookup_name_no_space = new_name_no_space
        self._lookup_normalized = new_normalized

        # 查找表非空校验
        total_entries = len(new_name_lower)
        if total_entries == 0 and self._sub_dbs:
            if self._progress_callback:
                self._progress_callback(0, 0, 0, "警告: 字体查找表为空，font_id 映射可能存在错误")
        elif self._progress_callback:
            self._progress_callback(0, 0, 0, f"字体查找表已构建: {total_entries} 条记录")

    def _normalize_for_match(self, s: str) -> str:
        s = unicodedata.normalize('NFKC', s)
        result = []
        for ch in s:
            if '\uff01' <= ch <= '\uff5e':
                result.append(chr(ord(ch) - 0xfee0))
            elif ch == '\u3000':
                result.append(' ')
            else:
                cat = unicodedata.category(ch)
                if cat.startswith('Mn') or cat.startswith('Cf'):
                    continue
                result.append(ch)
        normalized = ''.join(result).lower()
        normalized = re.sub(r'[\s\-_]+', '', normalized)
        return normalized.strip()
