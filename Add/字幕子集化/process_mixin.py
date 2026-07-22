# -*- coding: utf-8 -*-
"""处理工作线程 Mixin：ASS 与 MKV 处理流程、源文件删除"""

import os
import shutil
import threading
from tkinter import messagebox
from typing import Optional, Dict, Any, Tuple, List

from .font_utils import FONTTOOLS_AVAILABLE, SEND2TRASH_AVAILABLE, rmtree_onerror

try:
    from send2trash import send2trash
except ImportError:
    send2trash = None


class ProcessMixin:
    """处理工作线程方法（通过 Mixin 组合到主模块类）"""

    def _start_processing(self) -> None:
        if self.processing or self.scanning:
            return

        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showerror("错误", "请选择输出目录")
            return

        if not self.scan_results:
            messagebox.showerror("错误", "没有扫描到可处理的文件，请先点击【扫描/分析】")
            return

        if not self.font_db:
            messagebox.showerror("错误", "字体数据库未初始化，请先点击【扫描/分析】")
            return

        # 处理前刷新外部工具路径（确保使用最新配置）
        self._refresh_external_tools()

        os.makedirs(output_dir, exist_ok=True)

        self.processing = True
        self.scan_btn.config(state='disabled')
        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.dissolve_btn.config(state='disabled')
        self._set_options_state('disabled')
        with self._completed_lock:
            self._completed_tasks = 0

        # 接入主程序统一状态与日志体系
        self.host.clear_error_log(self.TAB_NAME)
        self.host.set_processing_state(self.tab_widget, True)

        mode = self.mode.get()
        create_subsets_val = self.create_subsets.get()
        embed_back_val = self.embed_back.get()
        delete_source_val = self.delete_source.get()
        delete_method_val = self.delete_method.get()
        skip_incomplete_val = self.skip_incomplete.get()

        if mode == 'ass':
            with self._scan_results_lock:
                self.total_tasks = len(self.scan_results)
            self._skip_incomplete = skip_incomplete_val
            thread = threading.Thread(target=self._ass_process_worker,
                                     args=(output_dir, create_subsets_val,
                                           delete_source_val, delete_method_val,
                                           skip_incomplete_val))
        else:
            with self._extracted_ass_map_lock:
                has_extracted = bool(self.extracted_ass_map)
            if not has_extracted:
                messagebox.showerror("错误", "没有可处理的MKV字幕轨道，请先扫描")
                self.processing = False
                self.scan_btn.config(state='normal')
                self.process_btn.config(state='normal')
                self.stop_btn.config(state='disabled')
                self._set_options_state('normal')
                self.host.set_processing_state(self.tab_widget, False)
                return
            with self._extracted_ass_map_lock:
                self.total_tasks = sum(len(tracks) for tracks in self.extracted_ass_map.values())
            self._skip_incomplete = skip_incomplete_val
            thread = threading.Thread(target=self._mkv_process_worker,
                                     args=(output_dir, create_subsets_val,
                                           embed_back_val, delete_source_val, delete_method_val,
                                           skip_incomplete_val))

        thread.daemon = True
        self.current_thread = thread
        thread.start()

    def _delete_source_file(self, file_path: str, delete_method: str) -> bool:
        if not os.path.exists(file_path):
            return True
        try:
            if delete_method == 'recycle' and SEND2TRASH_AVAILABLE:
                send2trash(file_path)
            else:
                os.remove(file_path)
            return True
        except Exception as e:
            self.root.after(0, lambda p=file_path, err=str(e):
                           self.log('error', f"删除源文件失败 {p}: {err}"))
            return False

    def _ass_process_worker(self, output_dir: str, create_subsets_val: bool,
                             delete_source_val: bool, delete_method_val: str,
                             skip_incomplete_val: bool = False) -> None:
        try:
            with self._scan_results_lock:
                scan_results_copy = list(self.scan_results.items())

            self._skipped_count = 0

            for i, (ass_path, data) in enumerate(scan_results_copy):
                if not self.processing:
                    self.root.after(0, lambda: self.log('warning', "用户取消处理"))
                    break

                rel = os.path.basename(ass_path)
                folder_rel = data.get('rel_path')
                if folder_rel:
                    rel = folder_rel
                total = len(scan_results_copy)

                if skip_incomplete_val:
                    if data:
                        temp_mapping = self._load_temp_mapping()
                        all_found = True
                        for font in data.get('fonts', []):
                            check = font.lstrip('@')
                            found_path, _, _ = self.font_db.find_font(check)
                            if not found_path and check not in temp_mapping and font not in temp_mapping:
                                all_found = False
                                break
                        if not all_found:
                            self._skipped_count += 1
                            self.root.after(0, lambda r=rel: self.log('info', f"跳过（缺少字体）: {r}"))
                            continue

                if total > 0:
                    self.root.after(0, lambda v=i/total*100, c=i+1-self._skipped_count, t=total, r=rel:
                                   self._update_progress(v, f"正在处理 ({c}/{t}): {r}", c, t))

                random_path = self.random_name_mgr.rename_with_random(ass_path)

                try:
                    processed = self._process_single_ass(random_path, output_dir, data,
                                                         create_subsets_val, original_name=rel)
                    if processed:
                        output_ass, font_failure = processed
                        with self._completed_lock:
                            self._completed_tasks += 1

                        if delete_source_val and not font_failure:
                            self.random_name_mgr.restore_original_name(random_path, ass_path)
                            self._delete_source_file(ass_path, delete_method_val)
                            self.root.after(0, lambda p=ass_path:
                                           self.log('info', f"已删除源文件: {os.path.basename(p)}"))
                        elif delete_source_val and font_failure:
                            self.random_name_mgr.restore_original_name(random_path, ass_path)
                            self.root.after(0, lambda r=rel:
                                           self.log('error', f"存在字体处理完全失败，保留源文件: {r}"))
                        else:
                            self.random_name_mgr.restore_original_name(random_path, ass_path)
                    else:
                        self.random_name_mgr.restore_original_name(random_path, ass_path)
                        self.root.after(0, lambda r=rel:
                                       self.log('error', f"处理失败，跳过: {r}"))

                except Exception as inner_e:
                    self.random_name_mgr.restore_original_name(random_path, ass_path)
                    self.root.after(0, lambda p=rel, err=str(inner_e):
                                   self.log('error', f"处理异常 {p}: {err}"))

            self.subset_generator.cleanup()
            if self._skipped_count > 0:
                self.root.after(0, lambda c=self._skipped_count:
                               self.log('info', f"已跳过 {c} 个缺少字体的文件"))
            if self.processing:
                self.root.after(0, self._processing_done)

        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log('error', f"处理异常: {err}"))
            if self.processing:
                self.root.after(0, self._processing_done)

    def _mkv_process_worker(self, output_dir: str, create_subsets_val: bool,
                             embed_back_val: bool, delete_source_val: bool,
                             delete_method_val: str,
                             skip_incomplete_val: bool = False) -> None:
        try:
            with self._extracted_ass_map_lock:
                extracted_map = dict(self.extracted_ass_map)
            if not extracted_map:
                self.root.after(0, lambda: self.log('warning', "没有可处理的字幕轨道"))
                self.root.after(0, self._processing_done)
                return

            self._skipped_count = 0

            for mkv_path, extracted in extracted_map.items():
                if not self.processing:
                    break

                mkv_original_name = os.path.basename(mkv_path)
                mkv_name = os.path.splitext(mkv_original_name)[0]

                if skip_incomplete_val:
                    mkv_has_missing = False
                    for track_id, track_type, lang, ass_path in extracted:
                        with self._scan_results_lock:
                            data = self.scan_results.get(ass_path, {})
                        if data:
                            temp_mapping = self._load_temp_mapping()
                            for font in data.get('fonts', []):
                                check = font.lstrip('@')
                                found_path, _, _ = self.font_db.find_font(check)
                                if not found_path and check not in temp_mapping and font not in temp_mapping:
                                    mkv_has_missing = True
                                    break
                        if mkv_has_missing:
                            break
                    if mkv_has_missing:
                        self._skipped_count += 1
                        self.root.after(0, lambda n=mkv_original_name:
                                       self.log('info', f"跳过（缺少字体）: {n}"))
                        continue

                folder_rel = None
                for track_id, track_type, lang, ass_path in extracted:
                    with self._scan_results_lock:
                        data = self.scan_results.get(ass_path, {})
                    if data.get('rel_path'):
                        folder_rel = data['rel_path']
                        break

                if folder_rel and os.sep in folder_rel:
                    rel_dir = os.path.dirname(folder_rel)
                    output_subdir = os.path.join(output_dir, rel_dir)
                    os.makedirs(output_subdir, exist_ok=True)
                else:
                    output_subdir = output_dir

                random_name = self.random_name_mgr.get_random_name(mkv_path) or mkv_original_name
                random_mkv_path = self.random_name_mgr.rename_with_random(mkv_path)

                mkv_temp_dir = os.path.join(self.subset_generator.temp_dir, random_name)
                os.makedirs(mkv_temp_dir, exist_ok=True)

                ass_tracks = []
                all_font_files = set()
                mkv_success = True
                mkv_has_font_failure = False

                for track_id, track_type, lang, ass_path in extracted:
                    if not self.processing:
                        break

                    with self._scan_results_lock:
                        data = self.scan_results.get(ass_path, {})
                    original_ass_name = os.path.basename(ass_path)

                    try:
                        processed_ass = self._process_single_ass(ass_path, mkv_temp_dir, data,
                                                                  create_subsets_val,
                                                                  original_name=original_ass_name)

                        if processed_ass:
                            output_ass, font_failure = processed_ass
                            if font_failure:
                                mkv_has_font_failure = True
                            track_label = f"Processed_{track_id}"
                            is_default = len(ass_tracks) == 0
                            ass_tracks.append((output_ass, lang, track_label, is_default))

                            fonts_dir = os.path.join(os.path.dirname(output_ass), 'Attachments')
                            if os.path.exists(fonts_dir):
                                for f in os.listdir(fonts_dir):
                                    if f.lower().endswith(('.ttf', '.ttc', '.otf', '.otc')):
                                        all_font_files.add(os.path.join(fonts_dir, f))
                        else:
                            mkv_success = False
                            self.root.after(0, lambda an=original_ass_name:
                                           self.log('error', f"字幕轨道处理失败，跳过: {an}"))
                    except Exception as e:
                        mkv_success = False
                        self.root.after(0, lambda an=original_ass_name, err=str(e):
                                       self.log('error', f"字幕轨道处理异常 {an}: {err}"))
                    else:
                        with self._completed_lock:
                            self._completed_tasks += 1
                            c = self._completed_tasks

                        if self.total_tasks > 0:
                            progress = c / self.total_tasks * 100
                            self.root.after(0, lambda v=progress, cc=c, t=self.total_tasks:
                                           self._update_progress(v, f"处理进度 ({cc}/{t})", cc, t))

                if ass_tracks and os.path.exists(random_mkv_path) and embed_back_val:
                    self.root.after(0, lambda: self.log('info', f"合并 {len(ass_tracks)} 个字幕轨道回MKV..."))
                    output_mkv = os.path.join(output_subdir, f"{mkv_name}_processed.mkv")

                    try:
                        def _register_merge(proc):
                            with self._subprocess_lock:
                                self._current_subprocesses.append(proc)

                        self.mkv_extractor.merge_subtitle_back(
                            random_mkv_path, ass_tracks, list(all_font_files), output_mkv,
                            callback=lambda msg: self.root.after(0, lambda m=msg: self.log('info', m)),
                            stop_event=self._stop_event,
                            subprocess_register_callback=_register_merge
                        )
                        self.root.after(0, lambda o=output_mkv: self.log('info', f"已生成: {o}"))
                    except Exception as e:
                        mkv_success = False
                        self.root.after(0, lambda err=str(e): self.log('error', f"合并失败: {err}"))

                if os.path.exists(mkv_temp_dir):
                    try:
                        shutil.rmtree(mkv_temp_dir, onerror=rmtree_onerror)
                    except Exception:
                        pass

                self.random_name_mgr.restore_original_name(random_mkv_path, mkv_path)

                if delete_source_val and mkv_success and not mkv_has_font_failure:
                    self._delete_source_file(mkv_path, delete_method_val)
                    self.root.after(0, lambda p=mkv_path:
                                   self.log('info', f"已删除源文件: {os.path.basename(p)}"))
                elif mkv_has_font_failure:
                    self.root.after(0, lambda p=mkv_path:
                                   self.log('error', f"存在字体处理完全失败，保留源文件: {os.path.basename(p)}"))
                elif not mkv_success:
                    self.root.after(0, lambda p=mkv_path:
                                   self.log('warning', f"处理未完全成功，保留源文件: {os.path.basename(p)}"))

            self.subset_generator.cleanup()
            if self._skipped_count > 0:
                self.root.after(0, lambda c=self._skipped_count:
                               self.log('info', f"已跳过 {c} 个缺少字体的文件"))
            if self.processing:
                self.root.after(0, self._processing_done)

        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log('error', f"处理失败: {err}"))
            if self.processing:
                self.root.after(0, self._processing_done)
