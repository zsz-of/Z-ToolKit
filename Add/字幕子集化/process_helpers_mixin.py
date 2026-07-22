# -*- coding: utf-8 -*-
"""处理辅助 Mixin：单文件处理、停止流程、文件名还原"""

import os
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Tuple

from .ass_parser import ASSParser
from .font_utils import FONTTOOLS_AVAILABLE, LOG_LEVEL_TO_HOST, PluginRegistry


class ProcessHelpersMixin:
    """处理辅助方法（通过 Mixin 组合到主模块类）"""

    def _process_single_ass(self, ass_path: str, output_dir: str, data: Optional[Dict],
                             create_subsets_val: bool, original_name: Optional[str] = None) -> Optional[Tuple[str, bool]]:
        try:
            ass_parser = ASSParser(ass_path)

            # 按字体提取各自实际渲染的文本
            text_per_font = self.subset_generator.extract_text_per_font(ass_parser)
            # 全文本用于未匹配到字体的回退
            all_text = self.subset_generator.extract_text_from_ass(ass_parser)

            # 只处理实际在 Dialogue 中被使用的字体
            if text_per_font:
                original_refs = sorted(text_per_font.keys())
            else:
                original_refs = ass_parser.get_font_references()
                self.root.after(0, lambda p=ass_path:
                                   self.log('info', f"未检测到实际使用字体，回退全量解析: {os.path.basename(p)}"))

            font_resolution: Dict[str, Tuple[str, str]] = {}
            used_fonts = []
            missing_fonts = []

            temp_mapping = self._load_temp_mapping()

            for ref in original_refs:
                # 通过 font_subset_map 将子集标识符解析为真实字体名
                check = ref.lstrip('@')
                identifier_upper = check.upper()
                if identifier_upper in ass_parser.font_subset_map:
                    mapped = ass_parser.font_subset_map[identifier_upper]
                    real_name = mapped if mapped else ref
                else:
                    real_name = ref

                # temp_mapping 优先于数据库匹配
                if real_name in temp_mapping:
                    found_path = temp_mapping[real_name]
                    font_idx = 0
                    found_info = {'is_collection': found_path.lower().endswith(('.ttc', '.otc'))}
                else:
                    found_path, font_idx, found_info = self.font_db.find_font(real_name)

                if not found_path:
                    missing_fonts.append(real_name)
                    continue

                # 生成随机标识符，传入已有标识符集合避免碰撞
                existing_ids = set(font_resolution[ref2][1] for ref2 in font_resolution)
                identifier = self.subset_generator.generate_subset_identifier(existing=existing_ids)

                font_resolution[ref] = (real_name, identifier)
                used_fonts.append({
                    'original': ref,
                    'real_name': real_name,
                    'identifier': identifier,
                    'path': found_path,
                    'font_index': font_idx,
                    'info': found_info
                })

            if original_name:
                ass_name = os.path.splitext(os.path.basename(original_name))[0]
            else:
                ass_name = os.path.splitext(os.path.basename(ass_path))[0]
            ass_output_dir = os.path.join(output_dir, ass_name)
            if os.path.exists(ass_output_dir):
                suffix = 2
                while os.path.exists(os.path.join(output_dir, f"{ass_name}_{suffix}")):
                    suffix += 1
                ass_output_dir = os.path.join(output_dir, f"{ass_name}_{suffix}")
            os.makedirs(ass_output_dir, exist_ok=True)
            fonts_dir = os.path.join(ass_output_dir, 'Attachments')
            os.makedirs(fonts_dir, exist_ok=True)

            copied_fonts = []
            identifier_to_path: Dict[str, str] = {}
            identifier_to_src: Dict[str, str] = {}
            has_font_failure = False

            for font_info in used_fonts:
                src_path = font_info['path']
                identifier = font_info['identifier']
                ext = os.path.splitext(src_path)[1]

                if font_info.get('info') and font_info['info'].get('is_collection') and ext in ('.ttc', '.otc'):
                    ext = '.ttf' if ext == '.ttc' else '.otf'

                # 同一源文件产生相同 identifier → 复用，跳过子集化
                if identifier in identifier_to_src and identifier_to_src[identifier] == src_path:
                    copied_fonts.append(os.path.basename(identifier_to_path[identifier]))
                    continue

                # 真正的碰撞（不同源文件产生相同 identifier）→ 加后缀
                if identifier in identifier_to_path:
                    base_identifier = identifier
                    suffix = 2
                    while identifier in identifier_to_path:
                        identifier = f"{base_identifier}_{suffix}"
                        suffix += 1
                    # 同步更新 font_resolution，确保 ASS 引用与实际字体文件名一致
                    font_resolution[font_info['original']] = (font_info['real_name'], identifier)

                dst_name = identifier + ext
                dst_path = os.path.join(fonts_dir, dst_name)

                if create_subsets_val and FONTTOOLS_AVAILABLE:
                    # 优先使用该字体实际渲染的文本，回退到全文本
                    real_name = font_info['real_name']
                    font_text = text_per_font.get(real_name, text_per_font.get(ref, all_text))
                    if not font_text:
                        font_text = all_text
                    result = self.subset_generator.create_subset_with_rename(
                        src_path, font_text, dst_path, identifier,
                        font_index=font_info.get('font_index', 0),
                        log_callback=lambda msg, level: self.root.after(0, lambda m=msg, l=level: self.log(LOG_LEVEL_TO_HOST.get(l, 'info'), m))
                    )
                else:
                    result = 'ok' if self.subset_generator.rename_font_file(
                        src_path, dst_path, identifier,
                        font_index=font_info.get('font_index', 0)
                    ) else 'failed'

                if result == 'ok' or result == 'rename_only':
                    copied_fonts.append(dst_name)
                    identifier_to_path[identifier] = dst_path
                    identifier_to_src[identifier] = src_path
                elif result == 'copy_only':
                    # 回退3：仅复制了原文件，字体内部名称未改为标识符
                    # 需要回滚 font_resolution 中的标识符为原始字体名
                    self.root.after(0, lambda rn=font_info['real_name']: self.log('warning',
                        f"字体无法重命名，回滚为原始字体名引用: {rn}"))
                    font_resolution[font_info['original']] = (font_info['real_name'], font_info['real_name'])
                    # 删除已复制的文件（内部名称不匹配，留着无意义）
                    try:
                        if os.path.exists(dst_path):
                            os.remove(dst_path)
                    except OSError:
                        pass
                else:
                    has_font_failure = True
                    self.root.after(0, lambda rn=font_info['real_name'], an=ass_name: self.log('error',
                        f"[严重] 字体处理完全失败，所有回退策略均无效: {rn}（字幕: {an}）"))
                    font_resolution[font_info['original']] = (font_info['real_name'], font_info['real_name'])

            replace_map = {}
            for ref, (real_name, identifier) in font_resolution.items():
                if ref != identifier:
                    replace_map[ref] = identifier

            if replace_map:
                ass_parser.replace_fonts(replace_map)

            ass_parser.update_font_subset_comments(font_resolution)

            if original_name:
                output_filename = os.path.basename(original_name)
            else:
                output_filename = os.path.basename(ass_path)
            output_ass = os.path.join(ass_output_dir, output_filename)
            ass_parser.save(output_ass)

            PluginRegistry.notify('file_processed', font_name='', ass_path=ass_path,
                                 output_path=output_ass, success=True)

            return (output_ass, has_font_failure)

        except Exception as e:
            self.root.after(0, lambda p=ass_path, err=str(e):
                           self.log('error', f"处理失败 {os.path.basename(p)}: {err}"))
            import traceback
            self.root.after(0, lambda err=traceback.format_exc():
                           self.log('error', f"详细错误:\n{err}"))

            PluginRegistry.notify('file_processed', font_name='', ass_path=ass_path,
                                 output_path=None, success=False)
            return None

    def _processing_done(self) -> None:
        self.processing = False
        self.scan_btn.config(state='normal')
        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='disabled')
        self.dissolve_btn.config(state='normal')
        self._set_config_locked(False)
        self._set_options_state('normal')
        self._clear_temp_mapping()
        self.progress_var.set(100)
        self.status_label.config(text="处理完成")

        # 通知主程序处理结束
        self.host.set_processing_state(self.tab_widget, False)

        if self.delete_source.get():
            mode = self.mode.get()
            if mode == 'ass':
                self.ass_files.clear()
            else:
                self.mkv_files.clear()
            self.file_listbox.delete(0, tk.END)

        self.random_name_mgr.delete_mapping_file()
        self.random_name_mgr.clear()

        with self._completed_lock:
            completed = self._completed_tasks

        PluginRegistry.notify('batch_complete', total=self.total_tasks,
                             success=completed, failed=self.total_tasks - completed)

        msg = f"字幕处理已完成！\n成功处理 {completed}/{self.total_tasks} 个任务"
        if getattr(self, '_skip_incomplete', False) and self._skipped_count > 0:
            msg += f"\n（其中 {self._skipped_count} 个因缺少字体被跳过）"
        messagebox.showinfo("完成", msg)

    def _stop_processing(self) -> None:
        self.processing = False
        self.scanning = False
        self._stop_event.set()
        self.status_label.config(text="正在停止...")

        with self._subprocess_lock:
            procs = list(self._current_subprocesses)
            self._current_subprocesses.clear()
        for proc in procs:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

        if self.current_thread and self.current_thread.is_alive():
            self.root.after(100, self._poll_thread_stop)
        else:
            self._finish_stop()

    def _poll_thread_stop(self) -> None:
        if self.current_thread and self.current_thread.is_alive():
            self.root.after(100, self._poll_thread_stop)
        else:
            self._finish_stop()

    def _finish_stop(self) -> None:
        self._stop_event.clear()

        self.restore_all_renamed_files()

        self.status_label.config(text="已停止")
        self.scan_btn.config(state='normal')
        self.process_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.dissolve_btn.config(state='normal')
        self._set_config_locked(False)
        self._set_options_state('normal')
        self.progress_var.set(0)

        # 通知主程序处理结束
        self.host.set_processing_state(self.tab_widget, False)

        with self._completed_lock:
            completed = self._completed_tasks

        messagebox.showwarning("处理已停止", f"已处理 {completed}/{self.total_tasks} 个文件\n处理过程已停止")

    def restore_all_renamed_files(self) -> None:
        if not self.random_name_mgr.name_map:
            return

        dialog = self._show_restore_dialog(len(self.random_name_mgr.name_map))

        try:
            def on_progress(current, total):
                self._restore_progress_var.set(current)
                self._restore_status_var.set(f"{current} / {total}")
                dialog.update()

            self.random_name_mgr.restore_all(progress_callback=on_progress)
        finally:
            dialog.destroy()

    def _show_restore_dialog(self, total_count: int) -> tk.Toplevel:
        dialog = tk.Toplevel(self.root)
        dialog.title("正在还原文件...")
        dialog.geometry("400x120")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.focus_force()
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        tk.Label(dialog, text="正在还原文件名称，请勿关闭窗口...", pady=15).pack()
        progress_var = tk.DoubleVar()
        ttk.Progressbar(dialog, variable=progress_var, maximum=total_count, length=350).pack(padx=15)
        self._restore_progress_var = progress_var

        status_var = tk.StringVar(value=f"0 / {total_count}")
        tk.Label(dialog, textvariable=status_var).pack(pady=10)
        self._restore_status_var = status_var

        dialog.update()
        return dialog
