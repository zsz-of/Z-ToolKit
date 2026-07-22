# -*- coding: utf-8 -*-
"""扫描编排 Mixin：扫描流程、进度更新、数据库初始化、解散数据库"""

import os
import time
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox
from typing import List, Tuple, Dict, Optional, Any, Set

from .font_utils import FONT_EXTENSIONS
from .font_database import FontDatabase
from .font_subsetter import FontSubsetGenerator


class ScanMixin:
    """扫描编排方法（通过 Mixin 组合到主模块类）"""

    def _dissolve_database(self) -> None:
        # 仅在扫描分析前或处理流程结束后允许解散数据库
        if self.scanning or self.processing:
            messagebox.showwarning("操作受限",
                "扫描分析或处理流程进行中，无法解散数据库。\n\n"
                "请在扫描分析前或处理流程结束后操作。")
            return

        font_dir = self.font_dir.get()
        if not font_dir or not os.path.isdir(font_dir):
            messagebox.showerror("错误", "请先选择有效的字体库目录")
            return

        if not messagebox.askyesno("确认", "解散数据库将：\n1. 删除所有子文件夹中的缓存数据库\n2. 将子文件夹中的字体移动到根目录\n3. 删除空的子文件夹\n\n确定继续？"):
            return

        self.scanning = True
        self.scan_btn.config(state='disabled')
        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.dissolve_btn.config(state='disabled')
        self._set_config_locked(True)
        self._set_options_state('disabled')
        self.progress_var.set(0)
        self.status_label.config(text="正在解散数据库...")

        # 接入主程序统一状态与日志体系
        self.host.clear_error_log(self.TAB_NAME)
        self.host.set_processing_state(self.tab_widget, True)

        def worker():
            moved_count = 0
            deleted_dbs = 0
            deleted_folders = 0
            try:
                if self.font_db is not None:
                    try:
                        self.font_db.cleanup()
                    except Exception:
                        pass
                    self.font_db = None

                subdirs = []
                for name in os.listdir(font_dir):
                    subdir = os.path.join(font_dir, name)
                    if os.path.isdir(subdir) and name.isdigit():
                        subdirs.append(subdir)

                # 也处理 error 目录
                error_dir = os.path.join(font_dir, 'error')
                if os.path.isdir(error_dir):
                    subdirs.append(error_dir)

                total = len(subdirs)

                for i, subdir in enumerate(subdirs, 1):
                    # 先删除数据库文件
                    db_file = os.path.join(subdir, '.font_cache.db')
                    if os.path.exists(db_file):
                        try:
                            os.remove(db_file)
                            deleted_dbs += 1
                        except OSError:
                            pass

                    # 收集并移动子目录中所有字体文件
                    for filename in os.listdir(subdir):
                        filepath = os.path.join(subdir, filename)
                        if os.path.isfile(filepath) and os.path.splitext(filename)[1].lower() in FONT_EXTENSIONS:
                            dst = os.path.join(font_dir, filename)
                            if os.path.exists(dst):
                                base, ext = os.path.splitext(filename)
                                counter = 1
                                while os.path.exists(os.path.join(font_dir, f"{base}_{counter}{ext}")):
                                    counter += 1
                                dst = os.path.join(font_dir, f"{base}_{counter}{ext}")
                            try:
                                shutil.move(filepath, dst)
                                moved_count += 1
                            except Exception:
                                pass

                    # 尝试删除空目录
                    try:
                        remaining = os.listdir(subdir)
                        if not remaining:
                            os.rmdir(subdir)
                            deleted_folders += 1
                    except OSError:
                        pass

                    if total > 0:
                        progress = i / total * 100
                        self.root.after(0, lambda p=progress, d=i, t=total:
                                       (self.progress_var.set(p),
                                        self.status_label.config(text=f"正在解散数据库 ({d}/{t})...")))

                self.root.after(0, lambda: self._dissolve_done(moved_count, deleted_dbs, deleted_folders))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: self._dissolve_done(0, 0, 0, error=err_msg))

        threading.Thread(target=worker, daemon=True).start()

    def _dissolve_done(self, moved_count: int, deleted_dbs: int, deleted_folders: int,
                       error: str = None) -> None:
        self.scanning = False
        self.scan_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.dissolve_btn.config(state='normal')
        self._set_config_locked(False)
        self._set_options_state('normal')
        self.progress_var.set(100)

        # 通知主程序解散数据库结束
        self.host.set_processing_state(self.tab_widget, False)

        if error:
            self.status_label.config(text="解散数据库失败")
            messagebox.showerror("错误", f"解散数据库失败: {error}")
            return

        self.font_db = None
        self.scan_results.clear()
        for item in self.scan_tree.get_children(''):
            self.scan_tree.delete(item)
        for item in self.font_tree.get_children(''):
            self.font_tree.delete(item)
        self.process_btn.config(state='disabled')

        self.status_label.config(text="数据库已解散")
        messagebox.showinfo("完成",
            f"数据库已解散！\n移动字体: {moved_count} 个\n删除数据库: {deleted_dbs} 个\n删除空文件夹: {deleted_folders} 个")

    def _update_progress(self, value: float, text: str, current: int = 0, total: int = 0) -> None:
        now = time.time()
        if hasattr(self, '_last_progress_update') and (now - self._last_progress_update) < 0.1:
            return
        self._last_progress_update = now

        self.progress_var.set(min(value, 100))
        self.status_label.config(text=text)
        if total > 0:
            self.progress_label.config(text=f"{current}/{total}")
        self.root.update_idletasks()

    def _clear_scan_results(self) -> None:
        with self._scan_results_lock:
            self.scan_results = {}
        with self._extracted_ass_map_lock:
            self.extracted_ass_map = {}
        for item in self.scan_tree.get_children():
            self.scan_tree.delete(item)
        for item in self.font_tree.get_children():
            self.font_tree.delete(item)
        self.process_btn.config(state='disabled')

    def _get_input_files(self) -> List[str]:
        mode = self.mode.get()
        input_mode = self.input_mode.get()

        if input_mode == 'folder':
            folder = self.folder_path.get()
            if not folder or not os.path.exists(folder):
                return []

            ext = '.ass' if mode == 'ass' else '.mkv'
            files = []
            for root, dirs, filenames in os.walk(folder):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in filenames:
                    if f.lower().endswith(ext):
                        files.append(os.path.abspath(os.path.join(root, f)))
            return files
        else:
            return [os.path.abspath(f) for f in (self.ass_files[:] if mode == 'ass' else self.mkv_files[:])]

    def _scan_or_analyze(self) -> None:
        if self.scanning or self.processing:
            return

        font_dir = self.font_dir.get()
        if not font_dir or not os.path.exists(font_dir):
            messagebox.showerror("错误", "请选择有效的字体库目录")
            return

        input_files = self._get_input_files()
        if not input_files:
            messagebox.showerror("错误", "没有找到可处理的文件，请检查输入")
            return

        # 扫描前刷新外部工具路径（MKV 模式需要 mkvextract/mkvmerge）
        self._refresh_external_tools()

        self._start_scan_thread(input_files)

    def _start_scan_thread(self, input_files: List[str]) -> None:
        self.scanning = True
        self.scan_btn.config(state='disabled')
        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.dissolve_btn.config(state='disabled')

        self._set_config_locked(True)
        self._set_options_state('disabled')

        self._clear_scan_results()
        self._clear_temp_mapping()

        self.random_name_mgr.generate_mapping(input_files, self.output_dir.get() or tempfile.gettempdir())

        # 接入主程序统一状态与日志体系
        self.host.clear_error_log(self.TAB_NAME)
        self.host.set_processing_state(self.tab_widget, True)

        self.log('info', "=" * 50)
        self.log('info', "开始扫描...")

        mode = self.mode.get()
        if mode == 'ass':
            thread = threading.Thread(target=self._scan_ass_worker, args=(input_files,))
        else:
            thread = threading.Thread(target=self._scan_mkv_worker, args=(input_files,))

        thread.daemon = True
        self.current_thread = thread
        thread.start()

    def _init_font_db(self) -> None:
        font_dir = self.font_dir.get()

        self.root.after(0, lambda: self.status_label.config(text="正在扫描字体库..."))

        def on_font_scan_progress(progress, processed, total, current_file):
            self.root.after(0, lambda:
                self._update_progress(
                    progress,
                    f"扫描字体库 ({processed}/{total}): {current_file}",
                    processed,
                    total
                )
            )

        self.font_db = FontDatabase(font_dir, progress_callback=on_font_scan_progress)
        self.root.after(0, lambda: self.log('info',
            f"字体库中找到 {self.font_db.font_count} 个字体文件, {self.font_db.face_count} 个字体名称"
        ))
        if self.font_db._new_font_count > 0 or self.font_db._error_count > 0:
            parts = []
            if self.font_db._new_font_count > 0:
                parts.append(f"新增 {self.font_db._new_font_count} 个字体")
            if self.font_db._error_count > 0:
                parts.append(f"{self.font_db._error_count} 个字体名称提取失败（已移入error文件夹）")
            self.root.after(0, lambda: self.log('info',
                f"字体库重建完成：{', '.join(parts)}"
            ))

        if self.subset_generator:
            self.subset_generator.cleanup()
        # 创建时传入 hb-subset 路径（来自主程序外部工具管理）
        self.subset_generator = FontSubsetGenerator(
            self.font_db, hb_subset_path=self.get_exe_path('hb-subset'))

    def _analyze_fonts(self, fonts: List[str]) -> Tuple[Dict[str, Tuple], List[str]]:
        matched = {}
        missing = []
        for font in fonts:
            found_path, font_idx, info = self.font_db.find_font(font)
            if found_path:
                matched[font] = (found_path, info)
            else:
                missing.append(font)
        return matched, missing

    def _insert_font_match_row(self, font: str, found_path: Optional[str],
                                info: Optional[Dict], display_name: Optional[str] = None,
                                replacement_font: Optional[str] = None) -> None:
        show_font = display_name if display_name else font

        if replacement_font:
            show_font = f"{show_font} --> {os.path.basename(replacement_font)}"
            matched_name = os.path.basename(replacement_font)
            self.font_tree.insert('', 0, values=(show_font, matched_name, replacement_font), tags=('replaced',))
        elif found_path:
            matched_name = os.path.basename(found_path)
            if info and info.get('matched_name'):
                matched_name = f"{info['matched_name']}"
            self.font_tree.insert('', tk.END, values=(show_font, matched_name, found_path))
        else:
            self.font_tree.insert('', 0, values=(show_font, "未找到", "-"), tags=('missing',))

    def _scan_done(self) -> None:
        self.scanning = False
        self.scan_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        # 扫描分析后不允许解散数据库，仅在扫描前或处理流程结束后允许
        self.dissolve_btn.config(state='disabled')
        if self.scan_results:
            self.process_btn.config(state='normal')
        self._set_options_state('normal')
        self.progress_var.set(100)
        self.status_label.config(text="扫描完成")

        # 通知主程序扫描结束
        self.host.set_processing_state(self.tab_widget, False)
