# -*- coding: utf-8 -*-
"""扫描工作线程 Mixin：ASS 与 MKV 扫描的多线程实现"""

import os
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Set

from .ass_parser import ASSParser


class ScanWorkersMixin:
    """扫描工作线程方法（通过 Mixin 组合到主模块类）"""

    def _scan_ass_worker(self, ass_files: List[str]) -> None:
        try:
            self._init_font_db()

            self.root.after(0, lambda: self.status_label.config(text="正在扫描ASS文件..."))
            self.root.after(0, lambda: self.log('info', f"找到 {len(ass_files)} 个ASS字幕文件 (多线程)"))

            all_required: Set[str] = set()
            matched_count = 0
            total = len(ass_files)
            completed_count = [0]
            progress_lock = threading.Lock()
            temp_mapping_snapshot = self._load_temp_mapping()
            scan_done = [False]

            def process_single_ass(ass_path: str) -> Optional[Dict]:
                if not self.scanning:
                    return None

                folder = self.folder_path.get()
                rel_path = os.path.basename(ass_path)
                if folder and self.input_mode.get() == 'folder' and len(ass_files) > 1:
                    try:
                        rel_path = os.path.relpath(ass_path, folder)
                    except Exception:
                        pass

                try:
                    parser = ASSParser(ass_path)
                    fonts = parser.get_actually_used_fonts()
                    matched, missing = self._analyze_fonts(fonts)

                    # 考虑 temp_mapping 中的替换字体
                    for font in list(missing):
                        if font in temp_mapping_snapshot:
                            missing.remove(font)
                            matched[font] = (temp_mapping_snapshot[font], {'is_replacement': True})

                    if not missing:
                        status = "全部匹配"
                    else:
                        status = f"缺少 {len(missing)} 个"

                    with self._scan_results_lock:
                        self.scan_results[ass_path] = {
                            'fonts': fonts,
                            'matched': matched,
                            'missing': missing,
                            'font_subset_map': parser.font_subset_map,
                            'font_subset_reverse': parser.font_subset_reverse,
                            'rel_path': rel_path
                        }

                    self.root.after(0, lambda rp=rel_path, nf=len(fonts), st=status, ap=ass_path:
                                   self.scan_tree.insert('', tk.END, values=(rp, nf, st), tags=(ap,)))

                    return {'fonts': fonts, 'matched': matched, 'missing': missing,
                            'status': status, 'rel_path': rel_path, 'path': ass_path}

                except Exception as e:
                    self.root.after(0, lambda rp=rel_path, err=str(e):
                                   self.scan_tree.insert('', tk.END, values=(rp, "?", f"错误: {err}")))
                    self.root.after(0, lambda rp=rel_path, err=str(e):
                                   self.log('error', f"扫描ASS失败 {rp}: {err}"))
                    return None

            # 定时器周期性更新进度条，避免多任务同时完成导致进度跳跃
            def _progress_timer():
                if scan_done[0]:
                    return
                with progress_lock:
                    c = completed_count[0]
                if total > 0:
                    progress = c / total * 100
                    self.progress_var.set(min(progress, 100))
                    self.status_label.config(text=f"正在扫描 ({c}/{total})")
                    self.progress_label.config(text=f"{c}/{total}")
                    self.root.update_idletasks()
                if c < total and not scan_done[0]:
                    self.root.after(120, _progress_timer)

            self.root.after(120, _progress_timer)

            max_workers = min((os.cpu_count() or 2), 8)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_single_ass, p): p for p in ass_files}

                for future in as_completed(futures):
                    if not self.scanning:
                        break

                    result = future.result()
                    with progress_lock:
                        completed_count[0] += 1

                    if result:
                        all_required.update(result['fonts'])
                        if not result['missing']:
                            matched_count += 1

            scan_done[0] = True

            font_match_cache = self._update_font_match_display(all_required)

            temp_mapping_for_stats = self._load_temp_mapping()
            found_total = sum(1 for f in all_required
                            if (f in font_match_cache and font_match_cache[f][0] is not None) or f in temp_mapping_for_stats)
            self.root.after(0, lambda af=len(ass_files), ar=len(all_required), ft=found_total, mc=matched_count:
                           self.stats_label.config(
                               text=f"统计: {af} 个ASS文件 | {ar} 种所需字体 | "
                                    f"{ft} 种已匹配 | {mc} 个文件完全匹配"
                           ))

            self.root.after(0, lambda: self.log('info', "扫描完成！"))
            self.root.after(0, self._scan_done)

        except Exception as e:
            scan_done[0] = True
            self.root.after(0, lambda err=str(e): self.log('error', f"扫描异常: {err}"))
            self.root.after(0, self._scan_done)

    def _scan_mkv_worker(self, mkv_files: List[str]) -> None:
        try:
            self._init_font_db()

            self.root.after(0, lambda: self.status_label.config(text="正在分析MKV文件..."))
            self.root.after(0, lambda: self.log('info', f"找到 {len(mkv_files)} 个MKV文件 (多线程)"))

            all_required: Set[str] = set()
            matched_count = 0
            with self._extracted_ass_map_lock:
                self.extracted_ass_map = {}

            total = len(mkv_files)
            completed_count = [0]
            progress_lock = threading.Lock()
            scan_temp_counter = [0]
            scan_temp_lock = threading.Lock()
            temp_mapping_snapshot = self._load_temp_mapping()
            scan_done = [False]

            def process_single_mkv(mkv_path: str) -> Optional[Dict]:
                if not self.scanning:
                    return None

                self.root.after(0, lambda f=os.path.basename(mkv_path):
                               self.log('info', f"分析MKV: {f}"))

                random_mkv_path = self.random_name_mgr.rename_with_random(mkv_path)

                folder = self.folder_path.get()
                rel_path = None
                if folder and self.input_mode.get() == 'folder':
                    try:
                        rel_path = os.path.relpath(mkv_path, folder)
                    except Exception:
                        pass

                track_results = []
                try:
                    with scan_temp_lock:
                        scan_temp_counter[0] += 1
                        mkv_scan_temp = os.path.join(
                            self.subset_generator.temp_dir,
                            f'mkv_scan_{scan_temp_counter[0]:04d}'
                        )
                    os.makedirs(mkv_scan_temp, exist_ok=True)

                    def _register_extract_scan(proc):
                        with self._subprocess_lock:
                            self._current_subprocesses.append(proc)

                    extracted = self.mkv_extractor.extract_subtitles(
                        random_mkv_path,
                        mkv_scan_temp,
                        callback=None,
                        stop_event=self._stop_event,
                        subprocess_register_callback=_register_extract_scan
                    )

                    self.random_name_mgr.restore_original_name(random_mkv_path, mkv_path)

                    if not extracted:
                        self.root.after(0, lambda f=os.path.basename(mkv_path):
                                       self.scan_tree.insert('', tk.END, values=(f, 0, "无字幕轨道")))
                        return {'mkv_path': mkv_path, 'tracks': [], 'has_subtitle': False}

                    with self._extracted_ass_map_lock:
                        self.extracted_ass_map[mkv_path] = extracted

                    for track_id, track_type, lang, ass_path in extracted:
                        parser = ASSParser(ass_path)
                        fonts = parser.get_actually_used_fonts()

                        matched, missing = self._analyze_fonts(fonts)

                        # 考虑 temp_mapping 中的替换字体
                        for font in list(missing):
                            if font in temp_mapping_snapshot:
                                missing.remove(font)
                                matched[font] = (temp_mapping_snapshot[font], {'is_replacement': True})

                        if not missing:
                            status = "全部匹配"
                        else:
                            status = f"缺少 {len(missing)} 个"

                        with self._scan_results_lock:
                            self.scan_results[ass_path] = {
                                'fonts': fonts,
                                'matched': matched,
                                'missing': missing,
                                'font_subset_map': parser.font_subset_map,
                                'font_subset_reverse': parser.font_subset_reverse,
                                'mkv_path': mkv_path,
                                'track_id': track_id,
                                'lang': lang,
                                'rel_path': rel_path
                            }

                        rel_display = f"{os.path.basename(mkv_path)} -> track{track_id}_{lang}.ass"
                        self.root.after(0, lambda rp=rel_display, nf=len(fonts), st=status, ap=ass_path:
                                       self.scan_tree.insert('', tk.END, values=(rp, nf, st), tags=(ap,)))

                        track_results.append({'fonts': fonts, 'matched': matched,
                                              'missing': missing, 'status': status})

                    return {'mkv_path': mkv_path, 'tracks': track_results, 'has_subtitle': True}

                except Exception as e:
                    self.random_name_mgr.restore_original_name(random_mkv_path, mkv_path)
                    self.root.after(0, lambda f=os.path.basename(mkv_path), err=str(e):
                                   self.scan_tree.insert('', tk.END, values=(f, "?", f"错误: {err}")))
                    self.root.after(0, lambda f=os.path.basename(mkv_path), err=str(e):
                                   self.log('error', f"分析MKV失败 {f}: {err}"))
                    return None

            # 定时器周期性更新进度条，避免多任务同时完成导致进度跳跃
            def _progress_timer():
                if scan_done[0]:
                    return
                with progress_lock:
                    c = completed_count[0]
                if total > 0:
                    progress = c / total * 100
                    self.progress_var.set(min(progress, 100))
                    self.status_label.config(text=f"正在分析 ({c}/{total})")
                    self.progress_label.config(text=f"{c}/{total}")
                    self.root.update_idletasks()
                if c < total and not scan_done[0]:
                    self.root.after(120, _progress_timer)

            self.root.after(120, _progress_timer)

            max_workers = min((os.cpu_count() or 2), 4)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_single_mkv, p): p for p in mkv_files}

                for future in as_completed(futures):
                    if not self.scanning:
                        self.root.after(0, self.restore_all_renamed_files)
                        break

                    result = future.result()
                    with progress_lock:
                        completed_count[0] += 1

                    if result and result.get('has_subtitle'):
                        for track in result['tracks']:
                            all_required.update(track['fonts'])
                            if not track['missing']:
                                matched_count += 1

            scan_done[0] = True

            font_match_cache = self._update_font_match_display(all_required)

            temp_mapping_for_stats = self._load_temp_mapping()
            found_total = sum(1 for f in all_required
                            if (f in font_match_cache and font_match_cache[f][0] is not None) or f in temp_mapping_for_stats)
            self.root.after(0, lambda nf=len(mkv_files), ar=len(all_required), ft=found_total, mc=matched_count:
                           self.stats_label.config(
                               text=f"统计: {nf} 个MKV | {ar} 种所需字体 | "
                                    f"{ft} 种已匹配 | {mc} 个字幕完全匹配"
                           ))

            self.root.after(0, lambda: self.log('info', "分析完成！"))
            self.root.after(0, self._scan_done)

        except Exception as e:
            scan_done[0] = True
            self.root.after(0, lambda err=str(e): self.log('error', f"分析异常: {err}"))
            self.root.after(0, self._scan_done)
