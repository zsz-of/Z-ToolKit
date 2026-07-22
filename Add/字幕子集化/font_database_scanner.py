# -*- coding: utf-8 -*-
"""字体数据库扫描器 Mixin：字体名称提取、数据库扫描填充"""

import os
import struct
import sqlite3
import threading
from typing import Optional, Dict, Any, Tuple, List

from .font_utils import FONTTOOLS_AVAILABLE

if FONTTOOLS_AVAILABLE:
    from fontTools import ttLib


class FontDatabaseScannerMixin:
    """FontDatabase 的字体名称提取与数据库扫描方法"""

    def _decode_name_record(self, record) -> Optional[str]:
        platform_id = record.platformID
        encoding_id = record.platEncID

        try:
            if platform_id == 0:
                if encoding_id in (0, 1, 2, 3, 4):
                    return record.string.decode('utf-16-be', errors='ignore').strip()
                elif encoding_id == 5:
                    return record.string.decode('utf-8', errors='ignore').strip()
            elif platform_id == 1:
                if encoding_id == 0:
                    return record.string.decode('mac_roman', errors='ignore').strip()
                elif encoding_id in (1, 2, 3, 4, 25):
                    return record.string.decode('utf-8', errors='ignore').strip()
            elif platform_id == 2:
                if encoding_id in (0, 1):
                    return record.string.decode('ascii', errors='ignore').strip()
                elif encoding_id == 2:
                    return record.string.decode('latin-1', errors='ignore').strip()
            elif platform_id == 3:
                if encoding_id in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
                    return record.string.decode('utf-16-be', errors='ignore').strip()
            else:
                return record.string.decode('utf-8', errors='ignore').strip()
        except Exception:
            pass
        return None

    def _extract_font_names(self, filepath: str, font_index: int = 0) -> Dict[str, Any]:
        names = {
            'families': [],
            'fullnames': [],
            'psnames': [],
            'version': '',
            'weight': 400,
            'slant': 0,
            'is_collection': False,
            'num_fonts': 1
        }

        if not FONTTOOLS_AVAILABLE:
            base = os.path.splitext(os.path.basename(filepath))[0]
            names['families'].append((base, 0))
            return names

        try:
            font = ttLib.TTFont(filepath, fontNumber=font_index)
            try:
                name_table = font.get('name', None)

                if name_table:
                    for record in name_table.names:
                        name_id = record.nameID
                        platform_id = record.platformID
                        lang_id = getattr(record, 'langID', 0)

                        string_val = self._decode_name_record(record)
                        if not string_val:
                            continue

                        if name_id == 1:
                            names['families'].append((string_val, lang_id))
                        elif name_id == 4:
                            names['fullnames'].append((string_val, lang_id))
                        elif name_id == 5:
                            if not names['version'] or (platform_id == 3 and lang_id == 0x0409):
                                names['version'] = string_val
                        elif name_id == 6:
                            names['psnames'].append((string_val, lang_id))

                os2_table = font.get('OS/2', None)
                if os2_table:
                    names['weight'] = getattr(os2_table, 'usWeightClass', 400)

                post_table = font.get('post', None)
                if post_table:
                    italic_angle = getattr(post_table, 'italicAngle', 0)
                    names['slant'] = 1 if italic_angle != 0 else 0

                if hasattr(font, 'reader') and font.reader.numFonts > 1:
                    names['is_collection'] = True
                    names['num_fonts'] = font.reader.numFonts
            finally:
                font.close()
        except Exception:
            base = os.path.splitext(os.path.basename(filepath))[0]
            names['families'].append((base, 0))
            try:
                with open(filepath, 'rb') as f:
                    tag = f.read(4)
                    if tag == b'ttcf':
                        f.seek(8)
                        num_fonts_data = f.read(4)
                        if len(num_fonts_data) == 4:
                            names['num_fonts'] = struct.unpack('>I', num_fonts_data)[0]
                            names['is_collection'] = names['num_fonts'] > 1
            except Exception:
                pass

        return names

    def _scan_fonts_to_db(self, conn: sqlite3.Connection, font_dir: str,
                          shared_processed: Optional[List[int]] = None,
                          global_total: int = 0,
                          progress_lock: Optional[threading.Lock] = None) -> Tuple[int, int]:
        font_files, total_files = self._collect_font_files(font_dir)

        local_font_count = 0
        local_face_count = 0
        processed = 0
        error_count = 0

        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode = WAL')
        cursor.execute('PRAGMA synchronous = OFF')
        cursor.execute('PRAGMA cache_size = -64000')
        cursor.execute('PRAGMA temp_store = MEMORY')

        all_font_rows = []
        all_name_rows = []
        error_fps: List[str] = []

        for filepath in font_files:
            filename = os.path.basename(filepath)
            ext = os.path.splitext(filename)[1].lower()
            fmt = ext.lstrip('.')

            try:
                first_names = self._extract_font_names(filepath, font_index=0)
                num_fonts = first_names.get('num_fonts', 1)

                font_has_names = False
                temp_font_rows = []
                temp_name_rows = []

                for font_idx in range(num_fonts):
                    if font_idx == 0:
                        names = first_names
                    else:
                        names = self._extract_font_names(filepath, font_index=font_idx)

                    current_face_has_names = False
                    face_name_rows = []

                    rel_path = os.path.relpath(filepath, self.font_root)
                    version_str = names.get('version', '')

                    temp_font_id = len(temp_font_rows) + 1
                    seen_names = set()
                    for name, lang_id in names['families']:
                        if name and ('family', name) not in seen_names:
                            seen_names.add(('family', name))
                            normalized = self._normalize_for_match(name)
                            face_name_rows.append((temp_font_id, 'family', name, lang_id, normalized))
                            local_face_count += 1
                            current_face_has_names = True

                    for name, lang_id in names['fullnames']:
                        if name and ('fullname', name) not in seen_names:
                            seen_names.add(('fullname', name))
                            normalized = self._normalize_for_match(name)
                            face_name_rows.append((temp_font_id, 'fullname', name, lang_id, normalized))
                            current_face_has_names = True

                    for name, lang_id in names['psnames']:
                        if name and ('psname', name) not in seen_names:
                            seen_names.add(('psname', name))
                            normalized = self._normalize_for_match(name)
                            face_name_rows.append((temp_font_id, 'psname', name, lang_id, normalized))
                            current_face_has_names = True

                    if current_face_has_names:
                        temp_font_rows.append((
                            rel_path, filename, fmt, font_idx,
                            names['weight'], names['slant'],
                            1 if names['is_collection'] else 0,
                            version_str
                        ))
                        temp_name_rows.extend(face_name_rows)
                        font_has_names = True

                    local_font_count += 1

                    if font_idx > 0:
                        first_names = None
                        names = None

                if font_has_names:
                    # 只有有名称的字体才写入DB
                    base_id = len(all_font_rows)
                    all_font_rows.extend(temp_font_rows)
                    for tid, name_type, name, lang_id, normalized in temp_name_rows:
                        all_name_rows.append((base_id + tid, name_type, name, lang_id, normalized))
                else:
                    error_fps.append(filepath)

            except Exception as e:
                error_fps.append(filepath)
                if self._progress_callback:
                    self._progress_callback(0, processed, total_files, f"扫描失败: {filename}")

            processed += 1
            if self._progress_callback:
                if shared_processed is not None and global_total > 0 and progress_lock is not None:
                    with progress_lock:
                        shared_processed[0] += 1
                        global_pos = shared_processed[0]
                    progress = global_pos / global_total * 100
                    self._progress_callback(progress, global_pos, global_total, filename)
                elif total_files > 0:
                    progress = processed / total_files * 100
                    self._progress_callback(progress, processed, total_files, filename)

        # 逐条写入 fonts 表，用 lastrowid 获取真实 ID，建立映射
        if all_font_rows:
            id_mapping: Dict[int, int] = {}
            for i, row in enumerate(all_font_rows):
                cursor.execute('''
                    INSERT INTO fonts (file_path, file_name, format, font_index, weight, slant, is_collection, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', row)
                id_mapping[i + 1] = cursor.lastrowid

            resolved_names = []
            for temp_id, name_type, name, lang_id, normalized in all_name_rows:
                real_id = id_mapping.get(temp_id)
                if real_id is not None:
                    resolved_names.append((real_id, name_type, name, lang_id, normalized))

            if resolved_names:
                cursor.executemany('''
                    INSERT INTO font_names (font_id, name_type, name, lang_id, normalized_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', resolved_names)

        conn.commit()

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_names ON font_names(name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_names_type ON font_names(name_type, name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_font_path ON fonts(file_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_normalized ON font_names(normalized_name)')
        conn.commit()

        cursor.execute('PRAGMA journal_mode = DELETE')
        cursor.execute('PRAGMA synchronous = NORMAL')

        source_hash = self._compute_signature_hash(font_files)

        cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('source_font_count', ?)",
                       (str(total_files),))
        cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('source_signature_hash', ?)",
                       (source_hash,))
        cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('font_count', ?)",
                       (str(local_font_count),))
        cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('face_count', ?)",
                       (str(local_face_count),))
        conn.commit()

        # 处理error字体：移入error文件夹
        if error_fps:
            import shutil
            error_folder = os.path.join(self.font_root, 'error')
            os.makedirs(error_folder, exist_ok=True)
            for fp in error_fps:
                basename = os.path.basename(fp)
                dst = os.path.join(error_folder, basename)
                if os.path.exists(dst):
                    base, ext = os.path.splitext(basename)
                    counter = 1
                    while os.path.exists(os.path.join(error_folder, f"{base}_{counter}{ext}")):
                        counter += 1
                    dst = os.path.join(error_folder, f"{base}_{counter}{ext}")
                try:
                    shutil.move(fp, dst)
                    error_count += 1
                except Exception:
                    pass

        return local_font_count, local_face_count, error_count
