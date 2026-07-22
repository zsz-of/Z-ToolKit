# -*- coding: utf-8 -*-
"""字体子集生成器：从 ASS 提取文本、生成子集字体、6 级回退策略"""

import os
import re
import random
import shutil
import tempfile
import logging
from typing import Optional, Callable, Dict, TYPE_CHECKING

from .font_utils import FONTTOOLS_AVAILABLE, SUBSET_IDENTIFIER_LENGTH, LogLevel, rmtree_onerror
from .font_repair import FontRepairMixin

try:
    import fontTools.ttLib as ttLib
    from fontTools.subset import Subsetter, Options as SubsetOptions
except ImportError:
    ttLib = None
    Subsetter = None
    SubsetOptions = None

if TYPE_CHECKING:
    from .font_database import FontDatabase
    from .ass_parser import ASSParser


class FontSubsetGenerator(FontRepairMixin):
    """字体子集生成器，继承 FontRepairMixin 获得字体修复方法"""

    ASCII_FULL = (
        '0123456789'
        'abcdefghijklmnopqrstuvwxyz'
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
        ' \t'
        '\u3002\uff0c\u3001\uff1b\uff1a\uff1f\uff01\u2026\u2014\u00b7\u02c9\u00a8\u2018\u2019\u201c\u201d\u3005\uff5e\u2016\u2236\uff07\u0060\uff5c\u3003\u3014\u3015\u3008\u3009\u300a\u300b\u300c\u300d\u300e\u300f\uff0e\u3016\u3017\u3010\u3011'
        '\uff08\uff09\uff3b\uff3d\uff5b\uff5d'
        '\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19'
        '\uff41\uff42\uff43\uff44\uff45\uff46\uff47\uff48\uff49\uff4a\uff4b\uff4c\uff4d\uff4e\uff4f\uff50\uff51\uff52\uff53\uff54\uff55\uff56\uff57\uff58\uff59\uff5a'
        '\uff21\uff22\uff23\uff24\uff25\uff26\uff27\uff28\uff29\uff2a\uff2b\uff2c\uff2d\uff2e\uff2f\uff30\uff31\uff32\uff33\uff34\uff35\uff36\uff37\uff38\uff39\uff3a'
    )

    SUBSET_LAYOUT_FEATURES = [
        'ccmp', 'liga', 'clig', 'kern', 'mark', 'mkmk',
        'calt', 'rclt', 'rlig', 'locl', 'init', 'medi', 'fina', 'isol',
    ]

    def __init__(self, font_db: 'FontDatabase', hb_subset_path: Optional[str] = None):
        self.font_db = font_db
        self.hb_subset_path = hb_subset_path
        self.temp_dir = tempfile.mkdtemp(prefix='font_subset_')

    def extract_text_from_ass(self, ass_parser: 'ASSParser') -> str:
        chars = set(self.ASCII_FULL)

        for event in ass_parser.events:
            text = event.get('Text') or ''
            clean = re.sub(r'\{[^}]*\}', '', text)
            clean = clean.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')

            for char in clean:
                if ord(char) > 31:
                    chars.add(char)

        return ''.join(sorted(set(chars)))

    def extract_text_per_font(self, ass_parser: 'ASSParser') -> Dict[str, str]:
        """按字体提取各自实际渲染的文本，每个字体加上 ASCII_FULL 基础字符集"""
        raw = ass_parser.extract_text_per_font()
        result = {}
        for font, chars in raw.items():
            all_chars = set(self.ASCII_FULL)
            all_chars.update(chars)
            result[font] = ''.join(sorted(all_chars))
        return result

    def generate_subset_identifier(self, font_path: str = '', text: Optional[str] = None,
                                    existing: Optional[set] = None) -> str:
        """生成随机字体标识符，确保同时包含大写字母和数字，避免与已有标识符碰撞"""
        chars_pool = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        digits = '0123456789'
        while True:
            result = ''.join(random.choices(chars_pool, k=SUBSET_IDENTIFIER_LENGTH))
            # 确保同时包含大写字母和数字
            if not any(c in letters for c in result):
                continue
            if not any(c in digits for c in result):
                continue
            if existing and result in existing:
                continue
            return result

    def create_subset_with_rename(self, font_path: str, text: str, output_path: str,
                                   new_name: str, font_index: int = 0,
                                   log_callback: Optional[Callable] = None) -> str:
        """子集化并重命名字体。返回值: 'ok'=子集化成功, 'rename_only'=仅重命名成功, 'copy_only'=仅复制(需回滚标识符), 'failed'=失败

        回退策略（6级）：
        1. fontTools 正常子集化
        2. fontTools + retain_gids + 可变字体实例化
        3. fontTools + 预修复损坏表 + 子集化
        4. hb-subset 命令行工具
        5. 仅重命名（不子集化）
        6. 直接复制原文件（需回滚标识符）
        """
        if not FONTTOOLS_AVAILABLE:
            try:
                shutil.copy2(font_path, output_path)
                return 'copy_only'
            except Exception:
                return 'failed'

        # 捕获 fontTools 的日志输出
        ft_logger = logging.getLogger('fontTools')
        class _CaptureHandler(logging.Handler):
            def __init__(self):
                super().__init__()
                self.messages = []
            def emit(self, record):
                self.messages.append(self.format(record))

        # === 级别1: fontTools 正常子集化 ===
        capture = _CaptureHandler()
        capture.setLevel(logging.WARNING)
        ft_logger.addHandler(capture)
        old_level = ft_logger.level
        ft_logger.setLevel(logging.WARNING)

        try:
            font = ttLib.TTFont(font_path, fontNumber=font_index)
            try:
                if 'head' in font:
                    font['head'].indexToLocFormat = 1

                options = SubsetOptions()
                options.layout_features = self.SUBSET_LAYOUT_FEATURES
                options.name_IDs = ['*']
                options.Notdef_outline = True
                options.recalc_bounds = True
                options.recalc_timestamp = False
                options.canonical_order = True
                options.desubroutinize = True
                options.hinting = False
                options.ignore_unsupported_tables = True
                options.text = text

                subsetter = Subsetter(options=options)
                subsetter.populate(text=text)
                subsetter.subset(font)

                self._rename_font(font, new_name)
                font.save(output_path)

                return 'ok'
            finally:
                font.close()
        except Exception as e:
            if log_callback:
                log_callback(f"[级别1失败] 子集化失败 {font_path}[{font_index}]: {e}", LogLevel.WARNING)
                for msg in capture.messages:
                    log_callback(f"[fontTools] {os.path.basename(font_path)}: {msg}", LogLevel.NOTICE)
        finally:
            ft_logger.removeHandler(capture)
            ft_logger.setLevel(old_level)

        # === 级别2: fontTools + retain_gids + 可变字体实例化 ===
        capture2 = _CaptureHandler()
        capture2.setLevel(logging.WARNING)
        ft_logger.addHandler(capture2)
        ft_logger.setLevel(logging.WARNING)

        try:
            font = ttLib.TTFont(font_path, fontNumber=font_index)
            try:
                if self._is_variable_font(font):
                    self._instantiate_variable_font(font, log_callback)

                if 'head' in font:
                    font['head'].indexToLocFormat = 1

                options = SubsetOptions()
                options.layout_features = self.SUBSET_LAYOUT_FEATURES
                options.name_IDs = ['*']
                options.Notdef_outline = True
                options.recalc_bounds = True
                options.recalc_timestamp = False
                options.canonical_order = True
                options.desubroutinize = True
                options.hinting = False
                options.ignore_unsupported_tables = True
                options.retain_gids = True
                options.text = text

                subsetter = Subsetter(options=options)
                subsetter.populate(text=text)
                subsetter.subset(font)

                self._rename_font(font, new_name)
                font.save(output_path)

                if log_callback:
                    log_callback(f"[级别2] retain_gids+实例化 子集化成功", LogLevel.NOTICE)

                return 'ok'
            finally:
                font.close()
        except Exception as e:
            if log_callback:
                log_callback(f"[级别2失败] {font_path}[{font_index}]: {e}", LogLevel.WARNING)
        finally:
            ft_logger.removeHandler(capture2)
            ft_logger.setLevel(old_level)

        # === 级别3: fontTools + 预修复损坏表 + 子集化 ===
        capture3 = _CaptureHandler()
        capture3.setLevel(logging.WARNING)
        ft_logger.addHandler(capture3)
        ft_logger.setLevel(logging.WARNING)

        try:
            font = ttLib.TTFont(font_path, fontNumber=font_index)
            try:
                if self._is_variable_font(font):
                    self._instantiate_variable_font(font, log_callback)

                self._repair_font_tables(font, log_callback)

                if 'head' in font:
                    font['head'].indexToLocFormat = 1

                options = SubsetOptions()
                options.layout_features = self.SUBSET_LAYOUT_FEATURES
                options.name_IDs = ['*']
                options.Notdef_outline = True
                options.recalc_bounds = True
                options.recalc_timestamp = False
                options.canonical_order = True
                options.desubroutinize = True
                options.hinting = False
                options.ignore_unsupported_tables = True
                options.retain_gids = True
                options.text = text

                subsetter = Subsetter(options=options)
                subsetter.populate(text=text)
                subsetter.subset(font)

                self._rename_font(font, new_name)
                font.save(output_path)

                if log_callback:
                    log_callback(f"[级别3] 修复表后子集化成功", LogLevel.NOTICE)

                return 'ok'
            finally:
                font.close()
        except Exception as e:
            if log_callback:
                log_callback(f"[级别3失败] {font_path}[{font_index}]: {e}", LogLevel.WARNING)
        finally:
            ft_logger.removeHandler(capture3)
            ft_logger.setLevel(old_level)

        # === 级别4: hb-subset 命令行工具 ===
        try:
            if self._hb_subset_font(font_path, text, output_path, font_index, log_callback):
                try:
                    font = ttLib.TTFont(output_path, fontNumber=0)
                    try:
                        self._rename_font(font, new_name)
                        font.save(output_path)
                    finally:
                        font.close()
                    if log_callback:
                        log_callback(f"[级别4] hb-subset+重命名成功", LogLevel.NOTICE)
                    return 'ok'
                except Exception as e:
                    if log_callback:
                        log_callback(f"[级别4] hb-subset成功但重命名失败: {e}", LogLevel.WARNING)
                    return 'rename_only'
            else:
                if log_callback:
                    log_callback(f"[级别4失败] hb-subset 无法处理 {os.path.basename(font_path)}", LogLevel.WARNING)
        except Exception as e:
            if log_callback:
                log_callback(f"[级别4失败] hb-subset 异常: {e}", LogLevel.WARNING)

        # === 级别5: 仅重命名 ===
        try:
            font = ttLib.TTFont(font_path, fontNumber=font_index)
            try:
                self._rename_font(font, new_name)
                font.save(output_path)
                if log_callback:
                    log_callback(f"[级别5] 回退为仅重命名: {output_path}", LogLevel.NOTICE)
                return 'rename_only'
            finally:
                font.close()
        except Exception as e2:
            if log_callback:
                log_callback(f"[级别5失败] 仅重命名也失败 {font_path}[{font_index}]: {e2}", LogLevel.WARNING)

        # === 级别6: 直接复制原文件 ===
        try:
            shutil.copy2(font_path, output_path)
            if log_callback:
                log_callback(
                    f"[级别6] 警告: 无法重命名字体内部名称，ASS引用与字体名称可能不匹配: {os.path.basename(output_path)}",
                    LogLevel.WARNING
                )
            return 'copy_only'
        except Exception:
            if log_callback:
                log_callback(f"字体文件复制失败: {os.path.basename(output_path)}", LogLevel.ERROR)
            return 'failed'

    def cleanup(self) -> None:
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, onerror=rmtree_onerror)

    @staticmethod
    def cleanup_old_temp_dirs() -> None:
        temp_root = tempfile.gettempdir()
        for name in os.listdir(temp_root):
            if name.startswith('font_subset_'):
                old_dir = os.path.join(temp_root, name)
                try:
                    shutil.rmtree(old_dir, onerror=rmtree_onerror)
                except Exception:
                    pass
