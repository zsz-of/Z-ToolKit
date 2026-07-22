# -*- coding: utf-8 -*-
"""字幕导出模块"""

import os
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from common import TabModule, FileSelector, sanitize_filename


class SubtitleExportModule(TabModule):
    """字幕导出模块"""
    TAB_NAME = "字幕导出"
    TAB_ORDER = 5
    PIP_DEPENDENCIES = []
    EXE_REQUIREMENTS = ['mkvextract', 'mkvmerge']

    def __init__(self, host):
        super().__init__(host)
        self.export_processing = False
        self.export_failed_files = []
        self.export_current_process = None

    def build_ui(self, parent):
        """构建标签页 UI"""
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 统一文件选择器
        input_frame = ttk.LabelFrame(main_frame, text="视频文件(MKV)", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.export_file_selector = FileSelector(input_frame, supported_types='video')

        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.export_start_btn = ttk.Button(btn_frame, text="开始导出", command=self.export_start)
        self.export_start_btn.pack(side=tk.RIGHT, padx=5)

        self.export_cancel_btn = ttk.Button(btn_frame, text="取消导出", command=self.export_cancel, state=tk.DISABLED)
        self.export_cancel_btn.pack(side=tk.RIGHT, padx=5)

        # 进度
        progress_frame = ttk.LabelFrame(main_frame, text="进度", padding="5")
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.export_progress_label = ttk.Label(progress_frame, text="当前进度: 0/0")
        self.export_progress_label.pack(anchor=tk.W)

        self.export_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.export_progress.pack(fill=tk.X, pady=(5, 10))

        # 状态栏
        self.export_status_var = tk.StringVar(value="就绪")
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Label(status_frame, textvariable=self.export_status_var, relief=tk.FLAT, anchor=tk.W).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=2)

        self._ui_built = True

    def export_start(self):
        """开始导出"""
        if self.export_processing:
            return
        files = self.export_file_selector.get_files()
        if not files:
            messagebox.showwarning("警告", "请先添加MKV文件")
            return

        self.export_processing = True
        self.export_failed_files = []
        self.export_total_count = len(files)
        self.export_current_process = None
        self.host.set_processing_state(self.tab_widget, True)

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        # 记录开始日志
        self.log('info', f"开始处理，共 {len(files)} 个文件")

        self.export_start_btn.config(state=tk.DISABLED)
        self.export_cancel_btn.config(state=tk.NORMAL)

        self.export_progress['maximum'] = len(files)
        self.export_progress['value'] = 0
        self.export_progress_label.config(text=f"当前进度: 0/{len(files)}")
        self.export_status_var.set("正在处理...")

        threading.Thread(target=self.export_process, args=(files,), daemon=True).start()

    def export_cancel(self):
        """取消导出"""
        self.export_processing = False
        self.export_status_var.set("操作已取消")
        self.host.set_processing_state(self.tab_widget, False)
        self.export_cancel_btn.config(state=tk.DISABLED)

    def stop_processing(self):
        """外部调用停止"""
        self.export_cancel()

    def is_processing(self):
        return self.export_processing

    def export_process(self, files):
        """处理导出"""
        mkvextract = self.get_exe_path('mkvextract')
        if not mkvextract:
            self.log('critical', "未配置 mkvextract 路径，请到「外部工具」标签页配置")
            self.host.after(0, lambda: messagebox.showerror("错误",
                "未配置 mkvextract 路径。\n\n请到「外部工具」标签页配置 MKVToolNix 后再使用本功能。"))
            self.host.after(0, self.export_finish)
            return

        self.log('info', f"使用 mkvextract: {mkvextract}")

        for i, mkv_file in enumerate(files):
            if not self.export_processing:
                self.log('warning', "用户取消操作")
                break

            filename = os.path.basename(mkv_file)
            self.host.after(0, lambda v=i+1: self.export_progress.config(value=v))
            self.host.after(0, lambda v=i+1, t=len(files):
                           self.export_progress_label.config(text=f"当前进度: {v}/{t}"))
            self.host.after(0, lambda f=mkv_file: self.export_status_var.set(f"正在处理: {os.path.basename(f)}"))

            self.log('info', f"[{i+1}/{len(files)}] 开始处理文件: {filename}")

            error = self.export_process_file(mkv_file, mkvextract)
            if error:
                self.log('error', f"处理失败 [{filename}]: {error}")
                self.export_failed_files.append((mkv_file, error))
                self.host.after(0, lambda: self.host.set_processing_state(self.tab_widget, True, has_error=True))
            else:
                self.log('info', f"处理成功 [{filename}]，已提取到同名文件夹")

        self.host.after(0, self.export_finish)

    def export_process_file(self, mkv_file, mkvextract):
        """处理单个文件"""
        try:
            mkvmerge = self.get_exe_path('mkvmerge')
            cmd = [mkvmerge, '-J', mkv_file]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            self.export_current_process = proc
            try:
                stdout, stderr = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                self.export_current_process = None
                return "读取MKV信息超时"
            finally:
                self.export_current_process = None

            if proc.returncode != 0:
                return f"读取MKV信息失败: {stderr.strip()}"

            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                return "MKV信息解析失败，文件可能已损坏"

            video_dir = os.path.dirname(mkv_file)
            base_name = os.path.splitext(os.path.basename(mkv_file))[0]

            output_folder = os.path.join(video_dir, base_name)
            os.makedirs(output_folder, exist_ok=True)

            attachments_folder = os.path.join(output_folder, "Attachments")

            subtitle_tracks = []
            attachment_tracks = []

            for track in data.get('tracks', []):
                if track.get('type') == 'subtitles':
                    subtitle_tracks.append({
                        'id': track.get('id'),
                        'codec': track.get('codec'),
                        'language': track.get('properties', {}).get('language'),
                        'name': track.get('properties', {}).get('track_name', '')
                    })

            for att in data.get('attachments', []):
                attachment_tracks.append({
                    'id': att.get('id'),
                    'name': att.get('file_name', f'attachment_{att["id"]}'),
                    'uid': att.get('properties', {}).get('uid')
                })

            if not subtitle_tracks and not attachment_tracks:
                return "未找到字幕轨道或附件"

            used_names = set()
            for track in subtitle_tracks:
                if not self.export_processing:
                    return "用户取消操作"

                track_id = track['id']

                if track['name']:
                    safe_name = sanitize_filename(track['name'])
                    output_name = f"{base_name}_{safe_name}"
                elif track['language']:
                    safe_lang = sanitize_filename(track['language'])
                    output_name = f"{base_name}_{safe_lang}"
                else:
                    output_name = f"{base_name}_Track{track_id}"

                final_name = output_name
                counter = 1
                while final_name in used_names:
                    final_name = f"{output_name}_{counter}"
                    counter += 1
                used_names.add(final_name)

                codec = track['codec'].lower()
                if 'ass' in codec or 'ssa' in codec:
                    ext = '.ass'
                elif 'srt' in codec:
                    ext = '.srt'
                else:
                    ext = '.ass'

                output_file = os.path.join(output_folder, f"{final_name}{ext}")

                cmd = [mkvextract, 'tracks', mkv_file, f'{track_id}:{output_file}']
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding='utf-8', errors='ignore',
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                self.export_current_process = proc
                try:
                    _, stderr = proc.communicate(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    self.export_current_process = None
                    return f"提取轨道 {track_id} 超时"
                finally:
                    self.export_current_process = None

                if proc.returncode not in [0, 1]:
                    return f"提取轨道 {track_id} 失败: {stderr.strip()}"

            if attachment_tracks:
                if not self.export_processing:
                    return "用户取消操作"

                os.makedirs(attachments_folder, exist_ok=True)
                cmd = [mkvextract, 'attachments', mkv_file]
                for att in attachment_tracks:
                    safe_name = os.path.basename(att['name'])
                    att_output = os.path.join(attachments_folder, safe_name)
                    cmd.append(f'{att["id"]}:{att_output}')

                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding='utf-8', errors='ignore',
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                self.export_current_process = proc
                try:
                    _, stderr = proc.communicate(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    self.export_current_process = None
                    return "提取附件超时"
                finally:
                    self.export_current_process = None

                if proc.returncode not in [0, 1]:
                    failed_names = [att['name'] for att in attachment_tracks
                                   if not os.path.exists(os.path.join(attachments_folder, att['name']))]
                    if failed_names:
                        return f"部分附件提取失败: {', '.join(failed_names)}"

            return None
        except Exception as e:
            return str(e)

    def export_finish(self):
        """完成导出"""
        self.export_processing = False
        self.host.set_processing_state(self.tab_widget, False)

        self.export_start_btn.config(state=tk.NORMAL)
        self.export_cancel_btn.config(state=tk.DISABLED)

        total = getattr(self, 'export_total_count', len(self.export_file_selector.get_files()))

        if self.export_failed_files:
            self.log('warning', f"处理完成，{len(self.export_failed_files)}/{total} 个文件失败")
            self.export_status_var.set("处理完成，但有错误")
            messagebox.showwarning("完成", f"处理完成，{len(self.export_failed_files)} 个文件失败")
        else:
            self.log('info', f"全部完成！成功处理 {total} 个文件")
            self.export_status_var.set("处理完成")
            messagebox.showinfo("完成", "所有视频成功处理完成")


# 模块导出
MODULE_CLASS = SubtitleExportModule
