# -*- coding: utf-8 -*-
"""字体详情 Mixin：字体库搜索、在线搜索、文件详情、树排序"""

import os
import re
import difflib
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Optional


class FontDetailMixin:
    """字体详情方法（通过 Mixin 组合到主模块类）"""

    def _search_font_online(self, font_name: str) -> None:
        import webbrowser
        from urllib.parse import quote
        query = quote(f'{font_name} 字体下载')
        url = f'https://www.bing.com/search?q={query}'
        webbrowser.open(url)

    def _search_font_in_library(self, requested_font: str) -> None:
        """打开字体库搜索窗口，以模糊匹配方式查找字体"""
        if not self.font_db or not self.font_db._sub_dbs:
            messagebox.showinfo("提示", "字体库尚未初始化，请先扫描字体库")
            return

        # 创建搜索窗口
        search_win = tk.Toplevel(self.root)
        search_win.title(f"从字体库搜索 - {requested_font}")
        search_win.geometry("500x500")
        search_win.transient(self.root)
        search_win.grab_set()
        search_win.focus_force()

        # 搜索框
        search_frame = ttk.Frame(search_win)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        search_var = tk.StringVar(value=requested_font)
        search_entry = ttk.Entry(search_frame, textvariable=search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        search_entry.select_range(0, tk.END)
        search_entry.icursor(tk.END)

        # 结果列表
        result_frame = ttk.Frame(search_win)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        result_tree = ttk.Treeview(result_frame, columns=('name', 'match'), show='headings', height=1)
        result_tree.heading('name', text='字体名称')
        result_tree.heading('match', text='匹配度')
        result_tree.column('name', width=380)
        result_tree.column('match', width=80, anchor='center')

        result_scroll = ttk.Scrollbar(result_frame, orient="vertical", command=result_tree.yview)
        result_tree.configure(yscrollcommand=result_scroll.set)
        result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 提示标签
        hint_label = ttk.Label(search_win, text="双击字体名称以指定为替换字体", foreground='gray')
        hint_label.pack(padx=10, pady=(0, 5))

        # 预加载字体名称（使用内存查找表，O(1) 查询，无需 SQL）
        name_to_paths = self.font_db.get_all_font_names()
        if not name_to_paths:
            messagebox.showinfo("提示", "字体库中没有字体")
            search_win.destroy()
            return

        all_names = list(name_to_paths.keys())

        _search_after_id = [None]

        def _do_search_impl():
            if not search_win.winfo_exists():
                return
            keyword = search_var.get().strip()
            if not keyword:
                for item in result_tree.get_children():
                    result_tree.delete(item)
                return

            keyword_lower = keyword.lower()
            keyword_norm = re.sub(r'[\s\-_]+', '', keyword_lower)

            # 在后台线程中执行模糊匹配，避免卡死主线程
            def _search_worker():
                contain_matches = []
                fuzzy_matches = []

                for name in all_names:
                    name_lower = name.lower()
                    name_norm = re.sub(r'[\s\-_]+', '', name_lower)

                    # 完全包含判断
                    if keyword_norm in name_norm:
                        contain_matches.append(name)
                        continue

                    # 模糊匹配
                    ratio = difflib.SequenceMatcher(None, keyword_norm, name_norm).ratio()
                    if ratio >= 0.6:
                        fuzzy_matches.append((name, ratio))

                # 模糊匹配按匹配度降序排序
                fuzzy_matches.sort(key=lambda x: x[1], reverse=True)

                if not search_win.winfo_exists():
                    return

                # 回到主线程更新 UI
                def _update_ui():
                    if not search_win.winfo_exists():
                        return
                    for item in result_tree.get_children():
                        result_tree.delete(item)

                    # 先显示完全包含的结果
                    for name in sorted(contain_matches, key=lambda x: x.lower()):
                        result_tree.insert('', tk.END, values=(name, "包含"), tags=('contain',))

                    # 再显示模糊匹配结果
                    for name, ratio in fuzzy_matches:
                        pct = f"{ratio * 100:.0f}%"
                        result_tree.insert('', tk.END, values=(name, pct), tags=('fuzzy',))

                    result_tree.tag_configure('contain', foreground='black')
                    result_tree.tag_configure('fuzzy', foreground='gray')

                search_win.after(0, _update_ui)

            t = threading.Thread(target=_search_worker, daemon=True)
            t.start()

        def do_search(*_args):
            if _search_after_id[0]:
                search_win.after_cancel(_search_after_id[0])
            _search_after_id[0] = search_win.after(200, _do_search_impl)

        def on_double_click(event):
            selection = result_tree.selection()
            if not selection:
                return
            item = selection[0]
            values = result_tree.item(item, 'values')
            if not values:
                return
            selected_name = values[0]
            paths = name_to_paths.get(selected_name, [])
            if not paths:
                messagebox.showwarning("警告", f"未找到字体 {selected_name} 的文件路径")
                return

            # 使用第一个路径作为替换字体
            replacement_path = paths[0]
            search_win.destroy()
            self._apply_replacement_font(requested_font, replacement_path)

        search_var.trace_add('write', do_search)
        result_tree.bind('<Double-1>', on_double_click)
        search_entry.bind('<Return>', lambda e: _do_search_impl())

        # 初始搜索
        _do_search_impl()

    def _reorder_font_tree(self) -> None:
        missing_items = []
        replaced_items = []
        normal_items = []

        for item_id in self.font_tree.get_children(''):
            tags = self.font_tree.item(item_id, 'tags') or ()
            vals = self.font_tree.item(item_id, 'values')
            if not vals:
                normal_items.append(item_id)
                continue
            if 'missing' in tags:
                missing_items.append((vals[0].lower(), item_id))
            elif 'replaced' in tags:
                replaced_items.append((vals[0].lower(), item_id))
            else:
                normal_items.append(item_id)

        missing_items.sort(key=lambda x: x[0])
        replaced_items.sort(key=lambda x: x[0])

        idx = 0
        for _, item_id in missing_items:
            self.font_tree.move(item_id, '', idx)
            idx += 1
        for _, item_id in replaced_items:
            self.font_tree.move(item_id, '', idx)
            idx += 1
        for item_id in normal_items:
            self.font_tree.move(item_id, '', idx)
            idx += 1

    def _on_scan_tree_double_click(self, event) -> None:
        selection = self.scan_tree.selection()
        if not selection:
            return

        item = selection[0]
        item_tags = self.scan_tree.item(item, 'tags')
        values = self.scan_tree.item(item, 'values')
        if not values:
            return

        if item_tags and len(item_tags) > 0:
            file_path = item_tags[0]
        else:
            file_display = values[0]
            with self._scan_results_lock:
                scan_results_copy = dict(self.scan_results)
            file_path = None
            for path in scan_results_copy:
                if os.path.basename(path) == file_display or file_display in path:
                    file_path = path
                    break

        if not file_path:
            return

        with self._scan_results_lock:
            data = self.scan_results.get(file_path)

        if not data:
            return

        self._show_file_detail(file_path, data)

    def _show_file_detail(self, file_path: str, data: Optional[Dict] = None) -> None:
        if data is None:
            with self._scan_results_lock:
                data = self.scan_results.get(file_path)

        if not data:
            return

        # 记录当前查看的文件路径，用于刷新
        self._detail_file_path = file_path

        fonts = data['fonts']
        matched = data['matched']
        missing = data['missing']

        temp_mapping = self._load_temp_mapping()

        display_path = data.get('mkv_path', file_path)
        display_path = display_path.replace('/', '\\')

        original_path = data.get('mkv_path', file_path)

        if self._detail_window and self._detail_window.winfo_exists():
            self._detail_window.destroy()

        detail_window = tk.Toplevel(self.root)
        self._detail_window = detail_window
        detail_window.title(f"文件详情 - {os.path.basename(original_path)}")
        detail_window.geometry("600x400")
        detail_window.focus_force()

        ttk.Label(detail_window, text=f"文件: {display_path}", wraplength=580).pack(padx=10, pady=(10, 5), anchor=tk.W)

        tree_frame = ttk.Frame(detail_window)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree = ttk.Treeview(tree_frame, columns=('font', 'status', 'source'), show='headings', height=1)
        tree.heading('font', text='字体名称')
        tree.heading('status', text='状态')
        tree.heading('source', text='来源')
        tree.column('font', width=200)
        tree.column('status', width=150)
        tree.column('source', width=200)

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        system_fonts = set()
        replaced_count = 0
        for font in fonts:
            if font in matched:
                found_path, info = matched[font]
                is_replacement = isinstance(info, dict) and info.get('is_replacement')
                if is_replacement or font in temp_mapping:
                    repl_path = temp_mapping.get(font, found_path)
                    status = f"替换: {os.path.basename(repl_path)}"
                    source = repl_path
                    tree.insert('', tk.END, values=(font, status, source), tags=('replaced',))
                    replaced_count += 1
                else:
                    status = "字体库匹配"
                    tree.insert('', tk.END, values=(font, status, found_path), tags=('matched',))
            elif font in missing:
                is_system = font in system_fonts or self.system_font_cache.is_system_font(font)
                if is_system:
                    system_fonts.add(font)
                status = "系统字体" if is_system else "未找到"
                source = "Windows系统" if is_system else "-"
                tag = 'system' if is_system else 'missing'
                tree.insert('', tk.END, values=(font, status, source), tags=(tag,))
            else:
                tree.insert('', tk.END, values=(font, "未知", "-"))

        tree.tag_configure('matched', foreground='#228B22')
        tree.tag_configure('replaced', foreground='blue')
        tree.tag_configure('system', foreground='black')
        tree.tag_configure('missing', foreground='#CC0000')

        matched_count = len(fonts) - replaced_count - len(missing)
        system_count = len(system_fonts)
        missing_count = len(missing) - system_count

        stats_text = f"总计: {len(fonts)} | 字体库匹配: {matched_count} | 替换: {replaced_count} | 系统字体: {system_count} | 未找到: {missing_count}"
        ttk.Label(detail_window, text=stats_text).pack(padx=10, pady=5, anchor=tk.W)

        ttk.Button(detail_window, text="关闭", command=detail_window.destroy).pack(pady=(0, 10))
