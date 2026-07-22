# -*- coding: utf-8 -*-
"""字体匹配 Mixin：临时映射、字体替换、匹配显示更新"""

import os
import json
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, Optional, Set, Tuple


class FontMatchMixin:
    """字体匹配方法（通过 Mixin 组合到主模块类）"""

    def _update_font_match_display(self, all_required: Set[str]) -> Dict[str, Tuple]:
        font_match_cache = {}
        all_subset_maps = {}
        all_subset_reverse = {}
        with self._scan_results_lock:
            scan_results_copy = dict(self.scan_results)
        for ass_path, data in scan_results_copy.items():
            all_subset_maps.update(data.get('font_subset_map', {}))
            all_subset_reverse.update(data.get('font_subset_reverse', {}))

        temp_mapping = self._load_temp_mapping()

        matched_fonts = []
        missing_fonts = []
        replaced_fonts = []

        for font in sorted(all_required):
            if font not in font_match_cache:
                font_match_cache[font] = self.font_db.find_font(font)
            found_path, font_idx, info = font_match_cache[font]

            display_name = None
            font_upper = font.upper()
            # 正向：font 本身是标识符，映射到真实名
            if font_upper in all_subset_maps:
                mapped = all_subset_maps[font_upper]
                if mapped and mapped != font:
                    display_name = f"{font} -> {mapped}"
            # 反向：font 是真实名，通过反向映射找到标识符
            elif font in all_subset_reverse:
                identifier = all_subset_reverse[font]
                if identifier and identifier != font:
                    display_name = f"{font} <- {identifier}"

            if font in temp_mapping:
                replaced_fonts.append((font, found_path, info, display_name, temp_mapping[font]))
            elif found_path:
                matched_fonts.append((font, found_path, info, display_name))
            else:
                missing_fonts.append((font, None, None, display_name))

        for font, fp, info, dn in sorted(missing_fonts, key=lambda x: x[0].lower()):
            self.root.after(0, lambda f=font, fp2=fp, inf=info, dn2=dn:
                           self._insert_font_match_row(f, fp2, inf, dn2))
        for font, fp, info, dn, repl in sorted(replaced_fonts, key=lambda x: x[0].lower()):
            self.root.after(0, lambda f=font, fp2=fp, inf=info, dn2=dn, r=repl:
                           self._insert_font_match_row(f, fp2, inf, dn2, replacement_font=r))
        for font, fp, info, dn in sorted(matched_fonts, key=lambda x: x[0].lower()):
            self.root.after(0, lambda f=font, fp2=fp, inf=info, dn2=dn:
                           self._insert_font_match_row(f, fp2, inf, dn2))

        return font_match_cache

    def _get_temp_mapping_path(self) -> str:
        return os.path.join(tempfile.gettempdir(), 'subtitle_font_temp_mapping.json')

    def _load_temp_mapping(self) -> Dict[str, str]:
        with self._temp_mapping_lock:
            mapping_path = self._get_temp_mapping_path()
            try:
                with open(mapping_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
            return {}

    def _save_temp_mapping(self, mapping: Dict[str, str]) -> None:
        with self._temp_mapping_lock:
            mapping_path = self._get_temp_mapping_path()
            try:
                with open(mapping_path, 'w', encoding='utf-8') as f:
                    json.dump(mapping, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def _clear_temp_mapping(self) -> None:
        with self._temp_mapping_lock:
            mapping_path = self._get_temp_mapping_path()
            if os.path.exists(mapping_path):
                try:
                    os.remove(mapping_path)
                except Exception:
                    pass

    def _get_requested_font_from_item(self, item) -> Optional[str]:
        """从字体树项目提取请求的真实字体名（用于 temp_mapping 键名）

        字体树显示格式：
        - "FZCuHeiSong"                           → 无映射
        - "ABCDEF12 -> FZCuHeiSong"               → 标识符 → 真实名映射
        - "FZCuHeiSong <- ABCDEF12"               → 真实名 ← 标识符反向映射
        - "... --> replacement.ttf"               → 手动替换后缀

        始终返回真实字体名（与 scan_results['fonts'] 一致），不含箭头和标识符。
        """
        values = self.font_tree.item(item, 'values')
        if not values:
            return None
        display_text = values[0]
        # 去除手动替换后缀 " --> replacement.ttf"
        if ' --> ' in display_text:
            display_text = display_text.split(' --> ')[0]
        # 处理子集映射箭头，提取真实字体名
        # -> "标识符 -> 真实名" → 取右侧真实名
        if ' -> ' in display_text:
            requested_font = display_text.split(' -> ')[1].strip()
        # <- "真实名 <- 标识符" → 取左侧真实名
        elif ' <- ' in display_text:
            requested_font = display_text.split(' <- ')[0].strip()
        else:
            requested_font = display_text
        return requested_font

    def _on_font_tree_double_click(self, event) -> None:
        selection = self.font_tree.selection()
        if not selection:
            return
        item = selection[0]
        requested_font = self._get_requested_font_from_item(item)
        if requested_font:
            self._search_font_online(requested_font)

    def _on_font_tree_right_click(self, event) -> None:
        item = self.font_tree.identify_row(event.y)
        if not item:
            return
        self.font_tree.selection_set(item)
        requested_font = self._get_requested_font_from_item(item)
        if not requested_font:
            return

        if self._font_tree_menu is not None:
            self._font_tree_menu.destroy()
        self._font_tree_menu = tk.Menu(self.root, tearoff=0)
        self._font_tree_menu.add_command(
            label=f"指定替换字体: {requested_font}",
            command=lambda: self._specify_replacement_font(item, requested_font)
        )
        self._font_tree_menu.add_command(
            label=f"从字体库搜索: {requested_font}",
            command=lambda: self._search_font_in_library(requested_font)
        )
        temp_mapping = self._load_temp_mapping()
        if requested_font in temp_mapping:
            self._font_tree_menu.add_separator()
            self._font_tree_menu.add_command(
                label=f"恢复默认匹配: {requested_font}",
                command=lambda: self._restore_default_match(item, requested_font)
            )
        self._font_tree_menu.add_command(
            label=f"在线搜索: {requested_font}",
            command=lambda: self._search_font_online(requested_font)
        )
        self._font_tree_menu.tk_popup(event.x_root, event.y_root)

    def _specify_replacement_font(self, item, requested_font: str) -> None:
        filetypes = [
            ("字体文件", "*.ttf *.ttc *.otf *.otc"),
            ("所有文件", "*.*")
        ]
        selected_path = filedialog.askopenfilename(
            title=f"为【{requested_font}】临时指定字体",
            filetypes=filetypes
        )

        if not selected_path:
            return

        self._apply_replacement_font(requested_font, selected_path)

    def _restore_default_match(self, item, requested_font: str) -> None:
        """恢复字体的默认匹配，移除手动替换"""
        temp_mapping = self._load_temp_mapping()
        if requested_font not in temp_mapping:
            return
        del temp_mapping[requested_font]
        self._save_temp_mapping(temp_mapping)

        # 查找默认匹配
        found_path, font_idx, info = self.font_db.find_font(requested_font)

        # 更新 font_tree 显示
        vals = self.font_tree.item(item, 'values')
        display_text = vals[0] if vals else requested_font
        if ' --> ' in display_text:
            base_display = display_text.split(' --> ')[0]
        else:
            base_display = display_text

        if found_path:
            matched_name = os.path.basename(found_path)
            if info and info.get('matched_name'):
                matched_name = info['matched_name']
            self.font_tree.item(item, values=(
                base_display,
                matched_name,
                found_path
            ), tags=('matched',))
        else:
            self.font_tree.item(item, values=(
                base_display,
                "未找到",
                ""
            ), tags=('missing',))

        self._reorder_font_tree()
        self._refresh_after_replacement()

    def _apply_replacement_font(self, requested_font: str, replacement_path: str) -> None:
        """应用替换字体并同步更新所有UI状态"""
        temp_mapping = self._load_temp_mapping()
        temp_mapping[requested_font] = replacement_path
        self._save_temp_mapping(temp_mapping)

        # 更新 font_tree 显示
        for item_id in self.font_tree.get_children(''):
            extracted = self._get_requested_font_from_item(item_id)
            if extracted == requested_font:
                vals = self.font_tree.item(item_id, 'values')
                display_text = vals[0] if vals else requested_font
                # 保留 --> 之前的显示文本（包含 -> 子集映射）
                if ' --> ' in display_text:
                    base_display = display_text.split(' --> ')[0]
                else:
                    base_display = display_text
                self.font_tree.item(item_id, values=(
                    f"{base_display} --> {os.path.basename(replacement_path)}",
                    os.path.basename(replacement_path),
                    replacement_path
                ), tags=('replaced',))
                break

        self._reorder_font_tree()

        # 同步更新扫描结果数据、scan_tree状态、底部统计栏、详情窗口
        self._refresh_after_replacement()

    def _refresh_after_replacement(self) -> None:
        """指定替换字体后，同步更新所有UI状态"""
        temp_mapping = self._load_temp_mapping()

        with self._scan_results_lock:
            scan_results_copy = dict(self.scan_results)

        all_required: Set[str] = set()
        matched_count = 0
        is_mkv = False

        for ass_path, data in scan_results_copy.items():
            fonts = data['fonts']
            matched = data['matched']
            missing = data['missing']

            if data.get('mkv_path'):
                is_mkv = True

            all_required.update(fonts)

            # 更新 scan_results 中的 matched/missing
            changed = False

            # 处理 missing 中的字体：如果在 temp_mapping 中则移到 matched
            for font in list(missing):
                if font in temp_mapping:
                    missing.remove(font)
                    matched[font] = (temp_mapping[font], {'is_replacement': True})
                    changed = True

            # 处理 matched 中的字体：更新替换或恢复默认
            for font in list(matched.keys()):
                if font in temp_mapping:
                    old_info = matched[font][1] if isinstance(matched[font][1], dict) else {}
                    new_info = dict(old_info)
                    new_info['is_replacement'] = True
                    new_info['is_collection'] = temp_mapping[font].lower().endswith(('.ttc', '.otc'))
                    matched[font] = (temp_mapping[font], new_info)
                    changed = True
                else:
                    old_path, old_info = matched[font]
                    was_replacement = isinstance(old_info, dict) and old_info.get('is_replacement')
                    if was_replacement:
                        found_path, font_idx, info = self.font_db.find_font(font)
                        if found_path:
                            matched[font] = (found_path, info)
                        else:
                            del matched[font]
                            missing.append(font)
                        changed = True

            # 重新计算状态
            if not missing:
                status = "全部匹配"
            else:
                status = f"缺少 {len(missing)} 个"

            if not missing:
                matched_count += 1

            # 更新 scan_tree 中对应行的状态
            if changed:
                for scan_item in self.scan_tree.get_children(''):
                    item_tags = self.scan_tree.item(scan_item, 'tags')
                    if item_tags and ass_path in item_tags:
                        self.scan_tree.item(scan_item, values=(
                            self.scan_tree.item(scan_item, 'values')[0],
                            len(fonts),
                            status
                        ))
                        break

        # 更新底部统计栏
        found_total = sum(1 for f in all_required
                         if self.font_db.find_font(f)[0] is not None or f in temp_mapping)

        if is_mkv:
            mkv_paths = set(d.get('mkv_path') for d in scan_results_copy.values() if d.get('mkv_path'))
            self.stats_label.config(
                text=f"统计: {len(mkv_paths)} 个MKV | {len(all_required)} 种所需字体 | "
                     f"{found_total} 种已匹配 | {matched_count} 个字幕完全匹配"
            )
        else:
            self.stats_label.config(
                text=f"统计: {len(scan_results_copy)} 个ASS文件 | {len(all_required)} 种所需字体 | "
                     f"{found_total} 种已匹配 | {matched_count} 个文件完全匹配"
            )

        # 如果详情窗口打开，刷新它
        if hasattr(self, '_detail_window') and self._detail_window and self._detail_window.winfo_exists():
            if hasattr(self, '_detail_file_path') and self._detail_file_path:
                with self._scan_results_lock:
                    detail_data = self.scan_results.get(self._detail_file_path)
                if detail_data:
                    self._show_file_detail(self._detail_file_path, detail_data)
