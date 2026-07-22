# -*- coding: utf-8 -*-
"""ASS 字幕解析器：解析 ASS 文件结构、提取字体引用与子集映射"""

import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .ass_writer import AssWriterMixin


class ASSParser(AssWriterMixin):
    """ASS 字幕解析器，继承 AssWriterMixin 获得写入与修改方法"""

    STYLE_FIELDS = [
        'Name', 'Fontname', 'Fontsize', 'PrimaryColour', 'SecondaryColour',
        'OutlineColour', 'BackColour', 'Bold', 'Italic', 'Underline',
        'StrikeOut', 'ScaleX', 'ScaleY', 'Spacing', 'Angle', 'BorderStyle',
        'Outline', 'Shadow', 'Alignment', 'MarginL', 'MarginR', 'MarginV',
        'Encoding'
    ]

    EVENT_FIELDS = [
        'Layer', 'Start', 'End', 'Style', 'Name',
        'MarginL', 'MarginR', 'MarginV', 'Effect', 'Text'
    ]

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.sections = defaultdict(list)
        self.styles: Dict[str, Dict[str, str]] = {}
        self.events: List[Dict[str, str]] = []
        self.fonts_used: Set[str] = set()
        self.font_subset_map: Dict[str, Optional[str]] = {}
        self.font_subset_reverse: Dict[str, str] = {}
        self._event_field_order: List[str] = self.EVENT_FIELDS[:]
        self._style_field_order: List[str] = self.STYLE_FIELDS[:]
        self._parse()
        self.replace_random_identifiers()

    def is_random_identifier(self, name: str) -> bool:
        check = name.lstrip('@')
        if len(check) < 6:
            return False
        if not all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in check):
            return False
        if not any(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in check):
            return False
        return check.upper() in self.font_subset_map

    def _parse(self) -> None:
        current_section = None

        with open(self.filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
            content = f.read()

        # 预处理：检测第一个非空行是否以 [Script Info] 开头
        first_non_empty = ''
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                first_non_empty = stripped
                break

        if not first_non_empty.startswith('[Script Info]'):
            content = '[Script Info]\nScriptType: v4.00+\n\n' + content

        for line in content.splitlines():
            line = line.rstrip('\n\r')
            if not line:
                continue

            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1]
                continue

            if current_section:
                self.sections[current_section].append(line)

                if current_section == 'Events' and line.lower().startswith('format:'):
                    self._parse_format_line(line)
                elif current_section in ('V4+ Styles', 'V4 Styles') and line.lower().startswith('format:'):
                    self._parse_style_format_line(line)
                elif current_section in ('V4+ Styles', 'V4 Styles') and line.startswith('Style:'):
                    self._parse_style(line)
                elif current_section == 'Events' and line.startswith('Dialogue:'):
                    self._parse_event(line)

        self._extract_font_subset_mappings()
        self._extract_fonts_from_events()

    def _parse_format_line(self, line: str) -> None:
        content = line[7:].strip()
        fields = [f.strip() for f in content.split(',')]
        if fields:
            if 'Text' in fields:
                self._event_field_order = fields

    def _parse_style_format_line(self, line: str) -> None:
        content = line[7:].strip()
        fields = [f.strip() for f in content.split(',')]
        if fields and 'Fontname' in fields:
            self._style_field_order = fields

    def _parse_style(self, line: str) -> None:
        parts = line[6:].strip().split(',')
        if len(parts) >= 2:
            style = {}
            for i, field in enumerate(self._style_field_order):
                if i < len(parts):
                    style[field] = parts[i].strip()
                else:
                    style[field] = ''
            self.styles[style.get('Name', 'Unknown')] = style
            if 'Fontname' in style and style['Fontname']:
                self.fonts_used.add(style['Fontname'].lstrip('@'))

    def _parse_event(self, line: str) -> None:
        content = line[9:].strip()
        num_fields = len(self._event_field_order)
        if num_fields <= 1:
            parts = content.split(',', 9)
        else:
            parts = content.split(',', num_fields - 1)

        event = {}
        for i, field in enumerate(self._event_field_order):
            if i < len(parts):
                event[field] = parts[i].strip()
            else:
                event[field] = ''
        self.events.append(event)

    def _extract_fonts_from_events(self) -> None:
        font_pattern = re.compile(r'\\fn([^\\}]+?)(?=\\|}|\Z)')
        for event in self.events:
            matches = font_pattern.findall(event.get('Text', ''))
            for match in matches:
                font_name = match.strip()
                if font_name:
                    stripped = font_name.lstrip('@')
                    self.fonts_used.add(stripped)

    def _extract_font_subset_mappings(self) -> None:
        pattern = re.compile(r';\s*Font\s*Subset\s*:\s*([A-Z0-9]{6,})(?:\s*[-\u2013\u2014]\s*(.+))?', re.IGNORECASE)

        for line in self.sections.get('Script Info', []):
            m = pattern.match(line.strip())
            if m:
                identifier = m.group(1).strip().upper()
                real_name = m.group(2).strip() if m.group(2) else None
                # 允许更完整的映射覆盖不完整的映射
                existing = self.font_subset_map.get(identifier)
                if existing is None:
                    self.font_subset_map[identifier] = real_name
                    if real_name:
                        self.font_subset_reverse[real_name] = identifier

        for line in self.sections.get('Events', []):
            if line.strip().startswith('Comment:'):
                m = pattern.search(line.strip())
                if m:
                    identifier = m.group(1).strip().upper()
                    real_name = m.group(2).strip() if m.group(2) else None
                    existing = self.font_subset_map.get(identifier)
                    if existing is None or (existing is not None and real_name is not None):
                        self.font_subset_map[identifier] = real_name
                        if real_name:
                            self.font_subset_reverse[real_name] = identifier

        rename_pattern = re.compile(r'^(.+?)\s*[-]{2,}\s*(.+)$')
        for line in self.sections.get('Assfonts Rename Info', []):
            m = rename_pattern.match(line.strip())
            if m:
                left = m.group(1).strip()
                right = m.group(2).strip()
                left_is_id = (len(left) >= 6
                              and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in left)
                              and any(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in left))
                right_is_id = (len(right) >= 6
                               and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' for c in right)
                               and any(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' for c in right))
                if right_is_id and not left_is_id:
                    real_name, identifier = left, right.upper()
                elif left_is_id and not right_is_id:
                    real_name, identifier = right, left.upper()
                else:
                    continue
                # Assfonts Rename Info 是最权威来源，总是覆盖
                old_real = self.font_subset_map.get(identifier)
                if old_real and old_real in self.font_subset_reverse:
                    del self.font_subset_reverse[old_real]
                self.font_subset_map[identifier] = real_name
                self.font_subset_reverse[real_name] = identifier

        # 提取完毕后清理过期段
        self.sections.pop('Assfonts Rename Info', None)

    def get_required_fonts(self) -> List[str]:
        resolved = set()
        for font in self.fonts_used:
            identifier = font.upper()
            if identifier in self.font_subset_map:
                real_name = self.font_subset_map[identifier]
                if real_name:
                    resolved.add(real_name)
                else:
                    resolved.add(font)
            else:
                resolved.add(font)
        return sorted(resolved)

    def get_font_references(self) -> List[str]:
        return sorted(self.fonts_used)

    def get_actually_used_fonts(self) -> List[str]:
        """返回实际在 Dialogue 中被使用的字体列表（通过 Style 引用或 \\fn 标签）"""
        per_font = self.extract_text_per_font()
        if not per_font:
            return self.get_required_fonts()
        # 将子集标识符解析为真实字体名
        result = set()
        for font in per_font.keys():
            identifier = font.upper()
            if identifier in self.font_subset_map:
                real_name = self.font_subset_map[identifier]
                result.add(real_name if real_name else font)
            else:
                result.add(font)
        return sorted(result)

    def extract_text_per_font(self) -> Dict[str, str]:
        """按字体提取各自实际渲染的文本，返回 {字体名(去@): 字符集字符串}"""
        font_chars: Dict[str, set] = {}

        # 构建 Style名 → Fontname 映射
        style_to_font: Dict[str, str] = {}
        for style_name, style_dict in self.styles.items():
            fontname = style_dict.get('Fontname', '')
            if fontname:
                style_to_font[style_name] = fontname.lstrip('@')

        # \fn 标签匹配（在花括号内）
        fn_pattern = re.compile(r'\\fn(@?)([^\\}]+)')

        for event in self.events:
            text = event.get('Text', '')
            style_name = event.get('Style', '')
            default_font = style_to_font.get(style_name, '')

            if not default_font and not text:
                continue

            # 将文本按花括号分段，提取每段的字体和文本
            current_font = default_font
            pos = 0
            brace_start = text.find('{')
            while pos < len(text):
                if brace_start == -1:
                    segment = text[pos:]
                    clean = segment.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
                    for ch in clean:
                        if ord(ch) > 31:
                            if current_font:
                                font_chars.setdefault(current_font, set()).add(ch)
                    break
                elif brace_start > pos:
                    segment = text[pos:brace_start]
                    clean = segment.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
                    for ch in clean:
                        if ord(ch) > 31:
                            if current_font:
                                font_chars.setdefault(current_font, set()).add(ch)

                brace_end = text.find('}', brace_start)
                if brace_end == -1:
                    break
                override_text = text[brace_start + 1:brace_end]

                fn_match = fn_pattern.search(override_text)
                if fn_match:
                    current_font = fn_match.group(2).strip().lstrip('@')

                # 花括号内非 override 标签的文本也属于当前字体
                clean_override = re.sub(r'\\[^\\}]+', '', override_text)
                if clean_override:
                    clean_override = clean_override.replace('\\N', '\n').replace('\\n', '\n').replace('\\h', ' ')
                    for ch in clean_override:
                        if ord(ch) > 31:
                            if current_font:
                                font_chars.setdefault(current_font, set()).add(ch)

                pos = brace_end + 1
                brace_start = text.find('{', pos)

        # 转为排序字符串
        return {font: ''.join(sorted(chars)) for font, chars in font_chars.items()}
