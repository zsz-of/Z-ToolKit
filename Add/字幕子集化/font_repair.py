# -*- coding: utf-8 -*-
"""字体修复 Mixin：重命名、可变字体实例化、表修复、hb-subset 回退"""

import os
import re
import shutil
import struct
import subprocess
from typing import Optional, Callable

from .font_utils import FONTTOOLS_AVAILABLE, LogLevel

try:
    import fontTools.ttLib as ttLib
except ImportError:
    ttLib = None


class FontRepairMixin:
    """字体修复方法（通过 Mixin 组合到 FontSubsetGenerator）"""

    def _rename_font(self, font, new_name: str) -> None:
        name_table = font.get('name')
        if not name_table:
            return

        safe_ps_name = re.sub(r'[^A-Za-z0-9_\-]', '', new_name) or 'Font'

        for record in name_table.names:
            if record.nameID not in (1, 4, 6, 16, 17):
                continue

            if record.nameID == 1 or record.nameID == 16:
                new_str = new_name
            elif record.nameID == 4:
                new_str = new_name
            elif record.nameID == 6:
                new_str = safe_ps_name
            else:
                continue

            try:
                if record.platformID == 3:
                    record.string = new_str.encode('utf-16-be')
                elif record.platformID == 0:
                    record.string = new_str.encode('utf-16-be')
                elif record.platformID == 1:
                    record.string = new_str.encode('mac_roman', errors='replace')
                else:
                    record.string = new_str.encode('utf-8', errors='replace')
            except Exception:
                pass

    def rename_font_file(self, font_path: str, output_path: str, new_name: str,
                         font_index: int = 0) -> bool:
        if not FONTTOOLS_AVAILABLE:
            try:
                shutil.copy2(font_path, output_path)
                return True
            except Exception:
                return False

        try:
            font = ttLib.TTFont(font_path, fontNumber=font_index)
            try:
                self._rename_font(font, new_name)
                font.save(output_path)
                return True
            finally:
                font.close()
        except Exception:
            pass

        try:
            shutil.copy2(font_path, output_path)
            return True
        except Exception:
            return False

    @staticmethod
    def _is_variable_font(font) -> bool:
        """检查字体是否为可变字体"""
        return 'fvar' in font

    def _instantiate_variable_font(self, font, log_callback=None):
        """将可变字体实例化为静态字体（移除所有可变数据）"""
        try:
            from fontTools.instancer import instantiateVariableFont
            axis_values = {}
            for axis in font['fvar'].axes:
                axis_values[axis.axisTag] = axis.defaultValue
            instantiateVariableFont(font, axis_values)
            if log_callback:
                log_callback(f"可变字体实例化成功", LogLevel.NOTICE)
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"可变字体实例化失败: {e}", LogLevel.NOTICE)
            return False

    def _repair_font_tables(self, font, log_callback=None):
        """修复字体中损坏的表，使其可以被子集化"""
        repaired = []

        # 修复 cmap 表：移除损坏的子表
        if 'cmap' in font:
            cmap = font['cmap']
            healthy_tables = []
            for table in cmap.tables:
                try:
                    _ = list(table.cmap.items())
                    healthy_tables.append(table)
                except (IndexError, ValueError, struct.error) as e:
                    if log_callback:
                        log_callback(f"跳过损坏的cmap子表: format={table.format}, platformID={table.platformID}: {e}", LogLevel.NOTICE)
                    repaired.append('cmap')
            if len(healthy_tables) < len(cmap.tables):
                cmap.tables = healthy_tables

        # 修复 GPOS/GSUB 表：移除损坏的 Lookup
        for table_name in ['GPOS', 'GSUB']:
            if table_name not in font:
                continue
            try:
                table = font[table_name]
                if hasattr(table, 'table') and hasattr(table.table, 'LookupList'):
                    lookup_list = table.table.LookupList
                    if hasattr(lookup_list, 'Lookup'):
                        healthy_lookups = []
                        for i, lookup in enumerate(lookup_list.Lookup):
                            try:
                                for subtable in lookup.SubTable:
                                    if hasattr(subtable, 'Coverage'):
                                        _ = subtable.Coverage
                                healthy_lookups.append(lookup)
                            except Exception as e:
                                if log_callback:
                                    log_callback(f"跳过损坏的{table_name} Lookup[{i}]: {e}", LogLevel.NOTICE)
                                repaired.append(table_name)
                        if len(healthy_lookups) < len(lookup_list.Lookup):
                            lookup_list.Lookup = healthy_lookups
                            lookup_list.LookupCount = len(healthy_lookups)
            except Exception:
                del font[table_name]
                repaired.append(table_name)
                if log_callback:
                    log_callback(f"移除损坏的{table_name}表", LogLevel.NOTICE)

        # 修复 glyf 表：确保 indexToLocFormat 为长格式
        if 'glyf' in font and 'head' in font:
            font['head'].indexToLocFormat = 1

        if repaired and log_callback:
            log_callback(f"字体表修复完成: {', '.join(set(repaired))}", LogLevel.NOTICE)

        return bool(repaired)

    def _hb_subset_font(self, font_path, text, output_path, font_index=0, log_callback=None):
        """使用 hb-subset 命令行工具子集化字体"""
        # 优先使用主程序外部工具管理配置的路径，回退到内置 tools 目录
        exe = self.hb_subset_path
        if not exe:
            exe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'harfbuzz-win64', 'hb-subset.exe')
        if not os.path.exists(exe):
            return False

        # 文本写入临时文件（避免命令行传参编码问题）
        text_file = None
        hb_output = None
        try:
            import tempfile
            # hb-subset 临时输出文件：放在系统临时目录，使用正确的扩展名
            # 避免路径中的中文字符和 .hb_tmp 扩展名导致 hb-subset 无法创建输出文件
            ext = os.path.splitext(output_path)[1].lower()
            if not ext:
                ext = '.ttf'
            fd, hb_output = tempfile.mkstemp(suffix=ext, prefix='hbsubset_out_')
            os.close(fd)
            # 删除已存在的文件，让 hb-subset 创建新文件
            if os.path.exists(hb_output):
                os.unlink(hb_output)

            fd, text_file = tempfile.mkstemp(suffix='.txt', prefix='hbsubset_')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(text)

            cmd = [
                exe,
                '--text-file=' + text_file,
                '--output-file=' + hb_output,
                '--drop-tables=VARC,STAT,fvar,avar,HVAR,VVAR,MVAR',
                '--retain-gids',
                '--desubroutinize',
                '--no-hinting',
            ]
            if font_index > 0:
                cmd.append(f'--face-index={font_index}')
            cmd.append(font_path)

            result = subprocess.run(
                cmd, capture_output=True,
                encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=120
            )

            if result.returncode == 0 and os.path.exists(hb_output) and os.path.getsize(hb_output) > 0:
                # 将 hb-subset 输出复制到目标路径
                shutil.copy2(hb_output, output_path)
                return True
            else:
                if log_callback:
                    err_info = f"ret={result.returncode}"
                    if not os.path.exists(hb_output):
                        err_info += ", output file not created"
                    elif os.path.getsize(hb_output) == 0:
                        err_info += ", output file is empty"
                    if result.stderr:
                        err_info += f", stderr: {result.stderr[:200]}"
                    log_callback(f"hb-subset 失败详情: {err_info}", LogLevel.WARNING)
                return False
        except subprocess.TimeoutExpired:
            if log_callback:
                log_callback("hb-subset 超时(120s)", LogLevel.WARNING)
            return False
        except Exception as e:
            if log_callback:
                log_callback(f"hb-subset 异常: {e}", LogLevel.WARNING)
            return False
        finally:
            if text_file:
                try:
                    os.unlink(text_file)
                except OSError:
                    pass
            if hb_output:
                try:
                    os.unlink(hb_output)
                except OSError:
                    pass
