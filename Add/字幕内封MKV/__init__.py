# -*- coding: utf-8 -*-
"""字幕内封(MKV)模块"""

import os
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from common import (TabModule, MKVEmbedFileSelector, safe_remove)


class SubtitleMkvEmbedModule(TabModule):
    """字幕内封(MKV)模块"""
    TAB_NAME = "字幕内封(MKV)"
    TAB_ORDER = 9
    PIP_DEPENDENCIES = []
    CONFIG_KEY = "subtitle_mkv_embed"
    EXE_REQUIREMENTS = ['mkvmerge']

    def __init__(self, host):
        super().__init__(host)
        self.mkv_embed_processing = False
        self.mkv_embed_cancel_flag = False
        self.mkv_embed_failed_videos = []

    def build_ui(self, parent):
        """构建标签页 UI"""
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 统一文件选择器
        input_frame = ttk.LabelFrame(main_frame, text="视频文件(MKV)", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.mkv_embed_file_selector = MKVEmbedFileSelector(input_frame, supported_types='video')

        # 导入模式选择（单选框）
        mode_frame = ttk.LabelFrame(main_frame, text="导入模式", padding=5)
        mode_frame.pack(fill=tk.X, pady=5)

        self.mkv_embed_mode_var = tk.StringVar(value="all")
        modes = [
            ("全部导入 (字幕+附件)", "all"),
            ("仅导入字幕", "subtitle_only"),
            ("仅导入附件(字体)", "attachment_only")
        ]

        for text, value in modes:
            ttk.Radiobutton(mode_frame, text=text, variable=self.mkv_embed_mode_var,
                           value=value).pack(side=tk.LEFT, padx=10)

        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        self.mkv_embed_start_btn = ttk.Button(btn_frame, text="开始操作", command=self.mkv_embed_start)
        self.mkv_embed_start_btn.pack(side=tk.RIGHT, padx=5)

        self.mkv_embed_cancel_btn = ttk.Button(btn_frame, text="取消操作", command=self.mkv_embed_cancel, state=tk.DISABLED)
        self.mkv_embed_cancel_btn.pack(side=tk.RIGHT, padx=5)

        # 进度条
        self.mkv_embed_progress_var = tk.DoubleVar()
        self.mkv_embed_progress = ttk.Progressbar(main_frame, variable=self.mkv_embed_progress_var, maximum=100)
        self.mkv_embed_progress.pack(fill=tk.X, pady=5)

        self.mkv_embed_progress_label = ttk.Label(main_frame, text="处理进度")
        self.mkv_embed_progress_label.pack(fill=tk.X, pady=5)

        self._ui_built = True

    def mkv_embed_start(self):
        """开始处理"""
        if self.mkv_embed_processing:
            return
        files = self.mkv_embed_file_selector.get_valid_files()
        if not files:
            all_files = self.mkv_embed_file_selector.get_files()
            if all_files:
                messagebox.showinfo("提示", f"所有 {len(all_files)} 个文件都缺少同名文件夹，无法处理\n请确保每个MKV文件都有对应的同名文件夹（包含字幕和Attachments）")
            else:
                messagebox.showinfo("提示", "请先添加视频文件")
            return

        non_mkv = [f for f in files if not f.lower().endswith('.mkv')]
        if non_mkv:
            self.log('warning',
                f"发现 {len(non_mkv)} 个非MKV文件，字幕内封仅支持MKV格式，这些文件将被跳过")
            files = [f for f in files if f.lower().endswith('.mkv')]
        if not files:
            messagebox.showinfo("提示", "没有可处理的MKV文件")
            return

        mkvmerge_path = self.get_exe_path('mkvmerge')
        if not mkvmerge_path:
            messagebox.showerror("错误",
                "未配置 mkvmerge 路径。\n\n请到「外部工具」标签页配置 MKVToolNix 后再使用本功能。")
            return

        self.mkv_embed_failed_videos = []
        self.mkv_embed_processing = True
        self.mkv_embed_cancel_flag = False
        self.mkv_embed_mode = self.mkv_embed_mode_var.get()
        self.mkv_embed_total_count = len(files)
        self.host.set_processing_state(self.tab_widget, True)

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        # 记录开始日志
        self.log('info', f"开始处理，共 {len(files)} 个文件")
        self.log('info', f"使用 mkvmerge: {mkvmerge_path}")

        self.mkv_embed_start_btn.config(state=tk.DISABLED)
        self.mkv_embed_cancel_btn.config(state=tk.NORMAL)

        threading.Thread(target=self.mkv_embed_process, args=(files,), daemon=True).start()

    def mkv_embed_cancel(self):
        """取消处理"""
        self.mkv_embed_cancel_flag = True
        self.mkv_embed_progress_label.config(text="正在取消...")

    def stop_processing(self):
        """外部调用停止"""
        self.mkv_embed_cancel()

    def is_processing(self):
        return self.mkv_embed_processing

    def mkv_embed_process(self, video_files):
        """处理视频"""
        total = len(video_files)
        skipped_count = 0

        for i, video_file in enumerate(video_files):
            if self.mkv_embed_cancel_flag:
                self.log('warning', "用户取消操作")
                break

            filename = os.path.basename(video_file)
            video_dir = os.path.dirname(video_file)
            video_name = os.path.splitext(filename)[0]
            subtitle_folder = os.path.join(video_dir, video_name)

            # 检查是否存在同名文件夹
            if not os.path.isdir(subtitle_folder):
                self.log('warning',
                    f"[{i+1}/{total}] 跳过 [{filename}] - 未找到同名文件夹: {video_name}\\")
                skipped_count += 1
                continue

            self.host.after(0, lambda l=f"正在处理: {os.path.basename(video_file)}":
                           self.mkv_embed_progress_label.config(text=l))
            self.host.after(0, lambda p=(i/total)*100: self.mkv_embed_progress_var.set(p))

            self.log('info', f"[{i+1}/{total}] 开始处理文件: {filename}")

            success, error = self.mkv_embed_process_video(video_file)
            if not success:
                self.log('error', f"处理失败 [{filename}]: {error}")
                self.mkv_embed_failed_videos.append((video_file, error))
                self.host.after(0, lambda: self.host.set_processing_state(self.tab_widget, True, has_error=True))
            else:
                mode = self.mkv_embed_mode

                # 在清理前记录日志信息
                if os.path.isdir(subtitle_folder):
                    sub_count = len([f for f in os.listdir(subtitle_folder)
                                   if os.path.isfile(os.path.join(subtitle_folder, f))
                                   and f.lower().endswith(('.ass', '.srt', '.ssa', '.sub'))])
                    att_folder = os.path.join(subtitle_folder, "Attachments")
                    att_count = len(os.listdir(att_folder)) if os.path.isdir(att_folder) else 0
                    self.log('info',
                        f"处理成功 [{filename}] - 从文件夹导入 {sub_count} 个字幕，{att_count} 个附件")
                else:
                    self.log('info', f"处理成功 [{filename}]")

                # 内封成功后清理源文件
                self._cleanup_after_embed(video_file, mode)

        # 记录跳过的文件数量
        if skipped_count > 0:
            self.log('info', f"共跳过 {skipped_count} 个无同名文件夹的文件")

        self.host.after(0, self.mkv_embed_complete)

    def mkv_embed_process_video(self, video_file):
        """处理单个视频"""
        try:
            mkvmerge_path = self.get_exe_path('mkvmerge')
            if not mkvmerge_path:
                return False, "未配置 mkvmerge 路径"

            temp_output = video_file + ".temp.mkv"
            video_dir = os.path.dirname(video_file)
            video_name = os.path.splitext(os.path.basename(video_file))[0]
            subtitle_folder = os.path.join(video_dir, video_name)

            subtitle_files = []
            attachment_files = []

            # 获取当前选择的导入模式
            mode = self.mkv_embed_mode

            # 始终查找字幕和附件（用于日志记录）
            all_subtitle_files = []
            all_attachment_files = []

            if os.path.isdir(subtitle_folder):
                for file in os.listdir(subtitle_folder):
                    file_path = os.path.join(subtitle_folder, file)
                    if os.path.isfile(file_path) and file.lower().endswith(('.ass', '.srt', '.ssa', '.sub')):
                        all_subtitle_files.append(file_path)

                attachments_folder = os.path.join(subtitle_folder, "Attachments")
                if os.path.isdir(attachments_folder):
                    for file in os.listdir(attachments_folder):
                        file_path = os.path.join(attachments_folder, file)
                        if os.path.isfile(file_path):
                            all_attachment_files.append(file_path)
            else:
                for file in os.listdir(video_dir):
                    if file.lower().endswith(('.ass', '.srt')) and os.path.splitext(file)[0].lower() == video_name.lower():
                        all_subtitle_files.append(os.path.join(video_dir, file))

                for file in os.listdir(video_dir):
                    if file.lower().endswith(('.ttc', '.ttf', '.otf')):
                        all_attachment_files.append(os.path.join(video_dir, file))

            # 根据模式决定实际使用的文件列表
            if mode == "all":
                subtitle_files = all_subtitle_files
                attachment_files = all_attachment_files
            elif mode == "subtitle_only":
                subtitle_files = all_subtitle_files
                attachment_files = []
            elif mode == "attachment_only":
                subtitle_files = []
                attachment_files = all_attachment_files

            cmd = [mkvmerge_path, "-o", temp_output, video_file]

            for subtitle_file in subtitle_files:
                # 基于文件名推断语言
                sub_basename = os.path.basename(subtitle_file).lower()
                if any(kw in sub_basename for kw in ['chs', 'gb', '简体', '简中', 'sc', 'chi']):
                    lang = 'chi'
                    track_name = 'CHS'
                elif any(kw in sub_basename for kw in ['cht', 'big5', '繁体', '繁中', 'tc']):
                    lang = 'chi'
                    track_name = 'CHT'
                elif any(kw in sub_basename for kw in ['eng', 'en.', 'english']):
                    lang = 'eng'
                    track_name = 'ENG'
                elif any(kw in sub_basename for kw in ['jpn', 'jp.', 'japanese']):
                    lang = 'jpn'
                    track_name = 'JPN'
                else:
                    lang = 'chi'
                    track_name = 'CHS'
                cmd.extend(["--language", f"0:{lang}", "--track-name", f"0:{track_name}", "--default-track", "0:1", subtitle_file])

            for att_file in attachment_files:
                if att_file.lower().endswith('.ttf'):
                    mime = "application/x-truetype-font"
                elif att_file.lower().endswith(('.ttc', '.otf')):
                    mime = "application/vnd.ms-opentype"
                else:
                    mime = "application/octet-stream"
                att_name = os.path.basename(att_file)
                cmd.extend(["--attachment-mime-type", mime, "--attachment-name", att_name, "--attach-file", att_file])

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   encoding='utf-8', errors='ignore',
                                   creationflags=subprocess.CREATE_NO_WINDOW,
                                   timeout=600)
        except subprocess.TimeoutExpired:
            safe_remove(temp_output, self.host, self.TAB_NAME)
            return False, "mkvmerge执行超时"
        except Exception as e:
            safe_remove(temp_output, self.host, self.TAB_NAME)
            return False, f"mkvmerge执行异常: {e}"

        if result.returncode not in [0, 1]:
            safe_remove(temp_output, self.host, self.TAB_NAME)
            return False, f"mkvmerge执行失败: {result.stderr.strip()}"

        if not os.path.exists(temp_output):
            return False, "临时文件未生成"

        backup_file = video_file + ".backup.mkv"
        try:
            shutil.move(video_file, backup_file)
            shutil.move(temp_output, video_file)
            if os.path.exists(backup_file):
                safe_remove(backup_file, self.host, self.TAB_NAME)
        except Exception as e:
            if os.path.exists(backup_file) and not os.path.exists(video_file):
                try:
                    shutil.move(backup_file, video_file)
                except Exception:
                    pass
            if os.path.exists(temp_output) and not os.path.exists(video_file):
                try:
                    shutil.move(temp_output, video_file)
                except Exception:
                    pass
            return False, f"替换文件失败: {e}"

        return True, None

    def _cleanup_after_embed(self, video_file, mode):
        """内封成功后清理源文件"""
        video_dir = os.path.dirname(video_file)
        video_name = os.path.splitext(os.path.basename(video_file))[0]
        subtitle_folder = os.path.join(video_dir, video_name)

        if not os.path.isdir(subtitle_folder):
            return

        try:
            if mode == "all":
                # 全部导入模式：删除整个同名文件夹
                shutil.rmtree(subtitle_folder)
                self.log('info',
                    f"已清理 [{video_name}\\] 文件夹（字幕和附件已全部内封）")

            elif mode == "subtitle_only":
                # 仅字幕模式：只删除字幕文件
                removed_subs = []
                for file in os.listdir(subtitle_folder):
                    file_path = os.path.join(subtitle_folder, file)
                    if os.path.isfile(file_path) and file.lower().endswith(('.ass', '.srt', '.ssa', '.sub')):
                        os.remove(file_path)
                        removed_subs.append(file)

                # 检查文件夹是否为空，如果为空则删除
                remaining = os.listdir(subtitle_folder)
                if not remaining:
                    os.rmdir(subtitle_folder)
                    self.log('info',
                        f"已清理 [{video_name}\\] 文件夹（{len(removed_subs)} 个字幕已内封）")
                else:
                    self.log('info',
                        f"已删除 {len(removed_subs)} 个字幕文件（附件保留在 [{video_name}\\] 中）")

            elif mode == "attachment_only":
                att_folder = os.path.join(subtitle_folder, "Attachments")
                if os.path.isdir(att_folder):
                    removed_atts = []
                    for file in os.listdir(att_folder):
                        file_path = os.path.join(att_folder, file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            removed_atts.append(file)

                    # 如果Attachments文件夹为空则删除
                    remaining_att = os.listdir(att_folder)
                    if not remaining_att:
                        os.rmdir(att_folder)

                    # 检查父文件夹是否为空
                    remaining = os.listdir(subtitle_folder)
                    if not remaining:
                        os.rmdir(subtitle_folder)
                        self.log('info',
                            f"已清理 [{video_name}\\] 文件夹（{len(removed_atts)} 个附件已内封）")
                    else:
                        self.log('info',
                            f"已删除 {len(removed_atts)} 个附件（字幕保留）")

        except Exception as e:
            self.log('warning',
                f"清理源文件失败 [{video_name}]: {e}")

    def mkv_embed_complete(self):
        """完成处理"""
        self.mkv_embed_processing = False
        self.host.set_processing_state(self.tab_widget, False)

        self.mkv_embed_start_btn.config(state=tk.NORMAL)
        self.mkv_embed_cancel_btn.config(state=tk.DISABLED)
        self.mkv_embed_progress_var.set(100)
        self.mkv_embed_progress_label.config(text="处理完成")

        valid_count = self.mkv_embed_total_count

        if not self.mkv_embed_failed_videos:
            self.log('info', f"全部完成！成功处理 {valid_count} 个文件")
            messagebox.showinfo("处理完成", "所有视频都处理成功了！")
        else:
            self.log('warning',
                f"处理完成，{len(self.mkv_embed_failed_videos)}/{valid_count} 个文件失败")
            messagebox.showwarning("处理完成", f"{len(self.mkv_embed_failed_videos)} 个视频处理失败")

    def save_config(self, config):
        """保存配置到嵌套字典"""
        data = {}
        if hasattr(self, 'mkv_embed_mode_var'):
            data["embed_mode"] = self.mkv_embed_mode_var.get()
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        """从子字典加载配置"""
        if hasattr(self, 'mkv_embed_mode_var'):
            val = config.get("embed_mode")
            if val is not None:
                self.mkv_embed_mode_var.set(val)

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        if hasattr(self, 'mkv_embed_mode_var'):
            self.mkv_embed_mode_var.set("all")


# 模块导出
MODULE_CLASS = SubtitleMkvEmbedModule
