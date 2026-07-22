# -*- coding: utf-8 -*-
"""ASS 字幕写入器 Mixin：随机标识符替换、字体替换、子集注释管理、文件输出"""

import re
from typing import Dict, Tuple


class AssWriterMixin:
    """ASSParser 的写入与修改方法（通过 Mixin 组合到 ASSParser）"""

    def replace_random_identifiers(self) -> None:
        replaced = False

        if 'Script Info' in self.sections:
            new_lines = []
            for line in self.sections['Script Info']:
                # ; Font Subset: 注释是元数据，由 update_font_subset_comments 统一管理，不做替换
                if re.match(r';\s*Font\s+Subset\s*:', line, re.IGNORECASE):
                    new_lines.append(line)
                    continue
                new_lines.append(line)
            self.sections['Script Info'] = new_lines

        if 'V4+ Styles' in self.sections:
            new_lines = []
            for line in self.sections['V4+ Styles']:
                if line.startswith('Style:'):
                    parts = line[6:].strip().split(',')
                    if len(parts) >= 2:
                        old_font = parts[1].strip()
                        at_prefix = '@' if old_font.startswith('@') else ''
                        font_core = old_font.lstrip('@')
                        if self.is_random_identifier(font_core):
                            real_name = self.font_subset_map.get(font_core.upper())
                            if real_name:
                                parts[1] = at_prefix + real_name
                                line = 'Style: ' + ','.join(parts)
                                replaced = True
                new_lines.append(line)
            self.sections['V4+ Styles'] = new_lines

        if 'Events' in self.sections and self.font_subset_map:
            identifiers = {k: v for k, v in self.font_subset_map.items()
                          if self.is_random_identifier(k) and v}
            if identifiers:
                pattern = re.compile(
                    r'\\fn(@?)(' + '|'.join(map(re.escape, identifiers.keys())) + r')'
                )
                new_lines = []
                for line in self.sections['Events']:
                    if line.startswith('Dialogue:') or line.startswith('Comment:'):
                        def replacer(m):
                            prefix = m.group(1)
                            ident = m.group(2)
                            real = identifiers.get(ident.upper(), ident)
                            return f'\\fn{prefix}{real}'

                        new_line = pattern.sub(replacer, line)
                        if new_line != line:
                            line = new_line
                            replaced = True
                    new_lines.append(line)
                self.sections['Events'] = new_lines

        new_fonts = set()
        for font in self.fonts_used:
            check = font.lstrip('@')
            if self.is_random_identifier(check):
                real_name = self.font_subset_map.get(check.upper())
                if real_name:
                    new_fonts.add(real_name)
                    replaced = True
                    continue
            new_fonts.add(font)
        self.fonts_used = new_fonts

        if replaced:
            self.font_subset_reverse = {v: k for k, v in self.font_subset_map.items() if v}

    def update_font_subset_comments(self, font_resolution: Dict[str, Tuple[str, str]]) -> bool:
        new_comments = []
        seen_ids = set()

        for ref, (real_name, subset_id) in font_resolution.items():
            if subset_id and subset_id not in seen_ids:
                seen_ids.add(subset_id)
                display_name = real_name if real_name and real_name != subset_id else None
                if display_name:
                    comment = f"; Font Subset: {subset_id} - {display_name}"
                else:
                    comment = f"; Font Subset: {subset_id}"
                new_comments.append(comment)

        if 'Script Info' not in self.sections:
            self.sections['Script Info'] = []

        cleaned = []
        font_subset_pattern = re.compile(r';\s*Font\s+Subset\s*:', re.IGNORECASE)
        for line in self.sections['Script Info']:
            if not font_subset_pattern.match(line.strip()):
                cleaned.append(line)

        insert_pos = 0
        for i, line in enumerate(cleaned):
            if line.strip().startswith('Title:') or line.strip().startswith('Original Script:'):
                insert_pos = i + 1

        for i, comment in enumerate(new_comments):
            cleaned.insert(insert_pos + i, comment)

        self.sections['Script Info'] = cleaned

        # 清理 [Events] 中的 Font Subset 注释行
        if 'Events' in self.sections:
            event_font_subset_pattern = re.compile(
                r'^Comment:.*;\s*Font\s+Subset\s*:', re.IGNORECASE
            )
            self.sections['Events'] = [
                line for line in self.sections['Events']
                if not event_font_subset_pattern.match(line.strip())
            ]

        return len(new_comments) > 0

    def replace_fonts(self, font_mapping: Dict[str, str]) -> bool:
        modified = False

        if 'V4+ Styles' in self.sections:
            new_styles = []
            for line in self.sections['V4+ Styles']:
                if line.startswith('Style:'):
                    parts = line[6:].strip().split(',')
                    if len(parts) >= 2:
                        old_font = parts[1].strip()
                        at_prefix = '@' if old_font.startswith('@') else ''
                        font_core = old_font.lstrip('@')
                        if font_core in font_mapping:
                            parts[1] = at_prefix + font_mapping[font_core]
                            line = 'Style: ' + ','.join(parts)
                            modified = True
                new_styles.append(line)
            self.sections['V4+ Styles'] = new_styles

        if 'Events' in self.sections and font_mapping:
            pattern_parts = sorted([re.escape(old_font) for old_font in font_mapping], key=len, reverse=True)
            pattern = re.compile(r'\\fn(@?)(' + '|'.join(pattern_parts) + r')')

            new_events = []
            for line in self.sections['Events']:
                if line.startswith('Dialogue:') or line.startswith('Comment:'):
                    def make_replacer(mapping):
                        def replacer(m):
                            prefix = m.group(1)
                            old = m.group(2)
                            new = mapping.get(old, old)
                            return f'\\fn{prefix}{new}'
                        return replacer

                    new_line = pattern.sub(make_replacer(font_mapping), line)
                    if new_line != line:
                        line = new_line
                        modified = True
                new_events.append(line)
            self.sections['Events'] = new_events

        if modified:
            if hasattr(self, 'styles') and self.styles is not None:
                for style_key, style_dict in list(self.styles.items()):
                    if 'Fontname' in style_dict:
                        old_font = style_dict['Fontname']
                        at_prefix = '@' if old_font.startswith('@') else ''
                        font_core = old_font.lstrip('@')
                        if font_core in font_mapping:
                            style_dict['Fontname'] = at_prefix + font_mapping[font_core]
            if hasattr(self, 'fonts_used') and self.fonts_used is not None:
                new_fonts = set()
                for font in self.fonts_used:
                    font_core = font.lstrip('@')
                    if font_core in font_mapping:
                        new_fonts.add(font_mapping[font_core])
                    else:
                        new_fonts.add(font)
                self.fonts_used = new_fonts

        return modified

    def to_string(self) -> str:
        lines = []
        for section, section_lines in self.sections.items():
            if section == 'Assfonts Rename Info':
                continue
            lines.append(f'[{section}]')
            lines.extend(section_lines)
            lines.append('')
        return '\n'.join(lines)

    def save(self, filepath: str) -> None:
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(self.to_string())
