# -*- coding: utf-8 -*-
"""字体数据库组织器 Mixin：文件夹整理、数据库文件管理、重建检测"""

import os
import shutil
import sqlite3
from typing import List, Tuple

from .font_utils import FONT_EXTENSIONS, FONTS_PER_SUBFOLDER, DB_SCHEMA_VERSION


class FontDatabaseOrganizerMixin:
    """FontDatabase 的文件夹组织与数据库文件管理方法"""

    def _compact_and_organize(self) -> None:
        if not os.path.exists(self.font_root):
            return

        root_new_fonts = []
        for filename in os.listdir(self.font_root):
            filepath = os.path.join(self.font_root, filename)
            if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in FONT_EXTENSIONS:
                root_new_fonts.append(filepath)

        numbered_folders = []
        for name in os.listdir(self.font_root):
            subdir = os.path.join(self.font_root, name)
            if os.path.isdir(subdir) and name.isdigit():
                numbered_folders.append(int(name))

        numbered_folders.sort()

        folder_font_files: dict = {}
        for num in numbered_folders:
            folder_path = os.path.join(self.font_root, str(num))
            files = []
            for filename in os.listdir(folder_path):
                filepath = os.path.join(folder_path, filename)
                if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in FONT_EXTENSIONS:
                    files.append(filepath)
            folder_font_files[num] = files

        changed_folders: set = set()
        self._new_font_count = len(root_new_fonts)

        new_fonts_list = list(root_new_fonts)
        new_fonts_idx = 0

        for folder_num in numbered_folders:
            current_count = len(folder_font_files.get(folder_num, []))
            if current_count >= FONTS_PER_SUBFOLDER:
                continue

            needed = FONTS_PER_SUBFOLDER - current_count

            while needed > 0 and new_fonts_idx < len(new_fonts_list):
                new_font = new_fonts_list[new_fonts_idx]
                new_fonts_idx += 1

                target_path = os.path.join(self.font_root, str(folder_num))
                dst_path = os.path.join(target_path, os.path.basename(new_font))
                if os.path.exists(dst_path):
                    base, ext = os.path.splitext(os.path.basename(new_font))
                    counter = 1
                    while os.path.exists(os.path.join(target_path, f"{base}_{counter}{ext}")):
                        counter += 1
                    dst_path = os.path.join(target_path, f"{base}_{counter}{ext}")
                try:
                    shutil.move(new_font, dst_path)
                    changed_folders.add(folder_num)
                    needed -= 1
                except Exception:
                    pass

            if needed > 0:
                donor_folders = sorted(
                    [n for n in numbered_folders if n > folder_num],
                    reverse=True
                )

                for donor_num in donor_folders:
                    if needed <= 0:
                        break

                    donor_files = folder_font_files.get(donor_num, [])
                    if not donor_files:
                        continue

                    to_take = donor_files[:needed]
                    remaining_donor = donor_files[needed:]
                    folder_font_files[donor_num] = remaining_donor

                    target_path = os.path.join(self.font_root, str(folder_num))
                    for src_path in to_take:
                        dst_path = os.path.join(target_path, os.path.basename(src_path))
                        if os.path.exists(dst_path):
                            base, ext = os.path.splitext(os.path.basename(src_path))
                            counter = 1
                            while os.path.exists(os.path.join(target_path, f"{base}_{counter}{ext}")):
                                counter += 1
                            dst_path = os.path.join(target_path, f"{base}_{counter}{ext}")
                        try:
                            shutil.move(src_path, dst_path)
                        except Exception:
                            pass

                    changed_folders.add(folder_num)
                    changed_folders.add(donor_num)
                    needed -= len(to_take)

        remaining_new = new_fonts_list[new_fonts_idx:]
        last_folder_has_fonts = bool(numbered_folders) and len(folder_font_files.get(max(numbered_folders), [])) > 0
        if remaining_new or last_folder_has_fonts:
            last_folder_num = max(numbered_folders) if numbered_folders else 0
            last_folder_path = os.path.join(self.font_root, str(last_folder_num)) if last_folder_num else None
            current_count = sum(
                1 for f in os.listdir(last_folder_path)
                if os.path.isfile(os.path.join(last_folder_path, f))
                and os.path.splitext(f)[1].lower() in FONT_EXTENSIONS
            ) if last_folder_path else 0

            if last_folder_path and current_count < FONTS_PER_SUBFOLDER:
                space = FONTS_PER_SUBFOLDER - current_count
                to_move = remaining_new[:space]
                remaining_new = remaining_new[space:]

                for src_path in to_move:
                    dst_path = os.path.join(last_folder_path, os.path.basename(src_path))
                    if os.path.exists(dst_path):
                        base, ext = os.path.splitext(os.path.basename(src_path))
                        counter = 1
                        while os.path.exists(os.path.join(last_folder_path, f"{base}_{counter}{ext}")):
                            counter += 1
                        dst_path = os.path.join(last_folder_path, f"{base}_{counter}{ext}")
                    try:
                        shutil.move(src_path, dst_path)
                    except Exception:
                        pass
                if to_move:
                    changed_folders.add(last_folder_num)

            while remaining_new:
                last_folder_num += 1
                new_folder = os.path.join(self.font_root, str(last_folder_num))
                os.makedirs(new_folder, exist_ok=True)

                to_move = remaining_new[:FONTS_PER_SUBFOLDER]
                remaining_new = remaining_new[FONTS_PER_SUBFOLDER:]

                for src_path in to_move:
                    dst_path = os.path.join(new_folder, os.path.basename(src_path))
                    if os.path.exists(dst_path):
                        base, ext = os.path.splitext(os.path.basename(src_path))
                        counter = 1
                        while os.path.exists(os.path.join(new_folder, f"{base}_{counter}{ext}")):
                            counter += 1
                        dst_path = os.path.join(new_folder, f"{base}_{counter}{ext}")
                    try:
                        shutil.move(src_path, dst_path)
                    except Exception:
                        pass
                changed_folders.add(last_folder_num)

        for folder_num in numbered_folders:
            if not folder_font_files.get(folder_num):
                folder_path = os.path.join(self.font_root, str(folder_num))
                db_file = os.path.join(folder_path, '.font_cache.db')
                if os.path.exists(db_file):
                    try:
                        os.remove(db_file)
                    except OSError:
                        pass
                try:
                    remaining_files = os.listdir(folder_path)
                    if not remaining_files:
                        os.rmdir(folder_path)
                except OSError:
                    pass
                changed_folders.discard(folder_num)

        for folder_num in changed_folders:
            self._invalidate_db(folder_num)

    def _invalidate_db(self, folder_num: int) -> None:
        db_path = os.path.join(self.font_root, str(folder_num), '.font_cache.db')
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except OSError:
                pass

    def _get_sub_folders(self) -> List[str]:
        folders = []
        if not os.path.exists(self.font_root):
            return folders
        for name in os.listdir(self.font_root):
            subdir = os.path.join(self.font_root, name)
            if os.path.isdir(subdir) and name.isdigit():
                folders.append(subdir)
        folders.sort(key=lambda p: int(os.path.basename(p)))
        return folders

    def _collect_font_files(self, font_dir: str) -> Tuple[List[str], int]:
        font_files = []
        if not os.path.exists(font_dir):
            return font_files, 0
        for filename in os.listdir(font_dir):
            filepath = os.path.join(font_dir, filename)
            if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in FONT_EXTENSIONS:
                font_files.append(filepath)
        return font_files, len(font_files)

    def _compute_signature_hash(self, font_files: List[str]) -> str:
        import hashlib
        signatures = []
        for filepath in font_files:
            try:
                stat_info = os.stat(filepath)
                sig = f"{os.path.basename(filepath)}|{stat_info.st_size}|{int(stat_info.st_mtime)}"
                signatures.append(sig)
            except Exception:
                pass
        signatures.sort()
        return hashlib.sha256('\n'.join(signatures).encode('utf-8')).hexdigest()

    def _check_rebuild_needed(self, font_dir: str) -> bool:
        db_file = os.path.join(font_dir, '.font_cache.db')
        if not os.path.exists(db_file):
            return True

        conn = None
        try:
            conn = sqlite3.connect(db_file, check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM meta WHERE key = 'schema_version'")
            ver_row = cursor.fetchone()
            if not ver_row or ver_row[0] != DB_SCHEMA_VERSION:
                return True

            # 验证表结构完整性：确保 font_names 表包含所有必要列
            cursor.execute("PRAGMA table_info(font_names)")
            existing_columns = {row[1] for row in cursor.fetchall()}
            required_columns = {'font_id', 'name_type', 'name', 'lang_id', 'normalized_name'}
            if not required_columns.issubset(existing_columns):
                return True

            cursor.execute("SELECT value FROM meta WHERE key = 'source_font_count'")
            row_count = cursor.fetchone()
            cursor.execute("SELECT value FROM meta WHERE key = 'source_signature_hash'")
            row_hash = cursor.fetchone()

            if not row_count or not row_hash:
                return True

            font_files, current_count = self._collect_font_files(font_dir)

            if int(row_count[0]) != current_count:
                return True

            current_hash = self._compute_signature_hash(font_files)
            return row_hash[0] != current_hash
        except Exception:
            return True
        finally:
            if conn is not None:
                conn.close()

    def _init_database(self, font_dir: str) -> sqlite3.Connection:
        db_file = os.path.join(font_dir, '.font_cache.db')

        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError as e:
                try:
                    old_conn = sqlite3.connect(db_file, check_same_thread=False)
                    old_cursor = old_conn.cursor()
                    old_cursor.execute("DROP TABLE IF EXISTS font_names")
                    old_cursor.execute("DROP TABLE IF EXISTS fonts")
                    old_cursor.execute("DROP TABLE IF EXISTS meta")
                    old_conn.commit()
                    old_conn.close()
                except Exception:
                    raise RuntimeError(f"无法删除旧数据库文件且无法清除旧数据: {e}")

        conn = sqlite3.connect(db_file, check_same_thread=False)

        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode = WAL')
        cursor.execute('PRAGMA synchronous = OFF')
        cursor.execute('PRAGMA cache_size = -64000')
        cursor.execute('PRAGMA temp_store = MEMORY')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fonts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                format TEXT NOT NULL,
                font_index INTEGER DEFAULT 0,
                weight INTEGER DEFAULT 400,
                slant INTEGER DEFAULT 0,
                is_collection INTEGER DEFAULT 0,
                version TEXT DEFAULT ''
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS font_names (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                font_id INTEGER NOT NULL,
                name_type TEXT NOT NULL,
                name TEXT NOT NULL,
                lang_id INTEGER DEFAULT 0,
                normalized_name TEXT,
                FOREIGN KEY (font_id) REFERENCES fonts(id)
            )
        ''')
        cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                       (DB_SCHEMA_VERSION,))
        conn.commit()

        return conn
