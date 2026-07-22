# -*- coding: utf-8 -*-
"""视频编码转换模块"""

import os
import re
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from common import TabModule, FileSelector, EncodingOptionsPanel, get_video_total_frames, safe_remove


class VideoConverterModule(TabModule):
    """视频编码转换模块"""
    TAB_NAME = "视频编码转换"
    TAB_ORDER = 3
    CONFIG_KEY = "video_converter"
    PIP_DEPENDENCIES = []
    EXE_REQUIREMENTS = ['ffmpeg', 'ffprobe']

    def __init__(self, host):
        super().__init__(host)
        self.conv_processing = False
        self.conv_stop_flag = False
        self.conv_output_folder = ""
        self.conv_current_process = None
        self.conv_process_lock = threading.Lock()

    def build_ui(self, parent):
        """构建标签页 UI"""
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        # 统一文件选择器（输入文件）
        input_frame = ttk.LabelFrame(left_frame, text="输入文件", padding=5)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.conv_file_selector = FileSelector(input_frame, supported_types='video')

        # 输出文件夹设置
        output_folder_frame = ttk.LabelFrame(left_frame, text="输出文件夹", padding=5)
        output_folder_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(output_folder_frame, text="输出文件夹:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.conv_output_var = tk.StringVar(value="未选择")
        ttk.Label(output_folder_frame, textvariable=self.conv_output_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        self.conv_select_output_btn = ttk.Button(output_folder_frame, text="选择", command=self.conv_select_output)
        self.conv_select_output_btn.grid(row=0, column=2, padx=5, pady=5)

        # 编码选项（使用公共组件）
        self.conv_encode_panel = EncodingOptionsPanel(right_frame)

        # 进度
        progress_frame = ttk.LabelFrame(right_frame, text="转换进度", padding=5)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(progress_frame, text="当前视频:").pack(anchor=tk.W, padx=5)
        self.conv_current_label = ttk.Label(progress_frame, text="无")
        self.conv_current_label.pack(anchor=tk.W, padx=5, pady=2)

        ttk.Label(progress_frame, text="单个视频进度:").pack(anchor=tk.W, padx=5)
        self.conv_video_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.conv_video_progress.pack(fill=tk.X, padx=5, pady=2)
        self.conv_frame_label = ttk.Label(progress_frame, text="已处理: 0 / -- 帧")
        self.conv_frame_label.pack(anchor=tk.W, padx=5, pady=2)

        ttk.Label(progress_frame, text="总进度:").pack(anchor=tk.W, padx=5)
        self.conv_total_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.conv_total_progress.pack(fill=tk.X, padx=5, pady=2)

        self.conv_status_label = ttk.Label(progress_frame, text="状态: 等待开始")
        self.conv_status_label.pack(anchor=tk.W, padx=5, pady=2)

        # 控制按钮
        control_frame = ttk.Frame(right_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=10)

        self.conv_start_btn = ttk.Button(control_frame, text="开始转换", command=self.conv_start)
        self.conv_start_btn.pack(side=tk.RIGHT, padx=5)

        self.conv_stop_btn = ttk.Button(control_frame, text="停止转换", command=self.conv_stop, state=tk.DISABLED)
        self.conv_stop_btn.pack(side=tk.RIGHT, padx=5)

        self.conv_open_btn = ttk.Button(control_frame, text="打开输出文件夹",
                                       command=self.conv_open_output, state=tk.DISABLED)
        self.conv_open_btn.pack(side=tk.RIGHT, padx=5)

        self._ui_built = True

    def conv_select_output(self):
        """选择输出文件夹"""
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.conv_output_folder = folder
            self.conv_output_var.set(folder)

    def conv_start(self):
        """开始转换"""
        if self.conv_processing:
            return
        files = self.conv_file_selector.get_files()
        if not files:
            messagebox.showwarning("警告", "请先添加视频文件")
            return
        if not self.conv_output_folder:
            messagebox.showwarning("警告", "请先选择输出文件夹")
            return

        self.conv_processing = True
        self.conv_stop_flag = False
        self.conv_failed_files = []
        self.host.set_processing_state(self.tab_widget, True)

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        self.conv_start_btn.config(state=tk.DISABLED)
        self.conv_select_output_btn.config(state=tk.DISABLED)
        self.conv_stop_btn.config(state=tk.NORMAL)
        self.conv_open_btn.config(state=tk.DISABLED)
        self.conv_encode_panel.set_state(tk.DISABLED)

        threading.Thread(target=self.conv_process_files, args=(files,), daemon=True).start()

    def conv_stop(self):
        """停止转换"""
        self.conv_stop_flag = True
        self.conv_stop_btn.config(state=tk.DISABLED)
        with self.conv_process_lock:
            proc = self.conv_current_process
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass

    def stop_processing(self):
        """外部调用停止"""
        self.conv_stop()

    def is_processing(self):
        return self.conv_processing

    def conv_process_files(self, files):
        """处理文件"""
        self.conv_video_files = files

        if not self.conv_video_files:
            self.log('warning', "未找到视频文件")
            self.host.after(0, self.conv_finish)
            return

        total = len(self.conv_video_files)
        self.log('info', f"开始处理，共 {total} 个文件")

        for i, video in enumerate(self.conv_video_files):
            if self.conv_stop_flag:
                self.log('warning', "用户取消操作")
                break

            filename = os.path.basename(video)
            self.host.after(0, lambda v=filename: self.conv_current_label.config(text=v))
            self.host.after(0, lambda: self.conv_video_progress.config(value=0))
            self.host.after(0, lambda v=(i/total)*100: self.conv_total_progress.config(value=v))
            self.host.after(0, lambda: self.conv_status_label.config(text="状态: 处理中..."))

            self.log('info', f"[{i+1}/{total}] 开始处理: {filename}")

            self.conv_convert_video(video)

        self.host.after(0, self.conv_finish)

    def conv_convert_video(self, input_path):
        """转换单个视频"""
        file_ext = os.path.splitext(input_path)[1]
        filename = os.path.basename(input_path)

        encoder = self.conv_encode_panel.get_encoder()
        suffix_map = {
            'libvpx-vp9': '_VP9', 'libx264': '_H264', 'libx265': '_H265',
            'libvvenc': '_H266', 'libsvtav1': '_AV1'
        }
        suffix = suffix_map.get(encoder, '_converted')

        output_name = os.path.splitext(os.path.basename(input_path))[0] + suffix + file_ext
        output_path = os.path.join(self.conv_output_folder, output_name)

        # 避免冲突
        if os.path.exists(output_path):
            base, ext = os.path.splitext(output_name)
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(self.conv_output_folder, f"{base}_{counter}{ext}")
                counter += 1

        pixel_format = self.conv_encode_panel.get_pixel_format()
        ffmpeg_path = self.get_exe_path('ffmpeg')

        # 构建命令：通用参数 + 编码参数 + 像素格式滤镜
        encode_args = self.conv_encode_panel.build_ffmpeg_args()
        cmd = [ffmpeg_path, '-y', '-i', input_path, '-map', '0', '-c', 'copy']
        cmd.extend(encode_args)
        cmd.extend(['-vf', f'format={pixel_format}', output_path])

        total_frames = get_video_total_frames(input_path,
                                              ffprobe_path=self.get_exe_path('ffprobe'),
                                              ffmpeg_path=ffmpeg_path)
        self.host.after(0, lambda tf=total_frames: self.conv_frame_label.config(
            text=f"已处理: 0 / {tf if tf else '--'} 帧"))

        try:
            with self.conv_process_lock:
                self.conv_current_process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=True, encoding='utf-8', errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )

            while True:
                if self.conv_stop_flag:
                    try:
                        self.conv_current_process.terminate()
                        self.conv_current_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.conv_current_process.kill()
                        self.conv_current_process.wait(timeout=3)
                    break

                ret = self.conv_current_process.poll()
                if ret is not None:
                    break

                line = self.conv_current_process.stdout.readline()
                frame_match = re.search(r'frame=\s*(\d+)', line)
                if frame_match:
                    current_frame = int(frame_match.group(1))
                    if total_frames and total_frames > 0:
                        pct = min(100, (current_frame / total_frames) * 100)
                        self.host.after(0, lambda p=pct: self.conv_video_progress.config(value=p))
                        self.host.after(0, lambda cf=current_frame, tf=total_frames: self.conv_frame_label.config(
                            text=f"已处理: {cf} / {tf} 帧"))
                    else:
                        self.conv_video_progress_value = getattr(self, 'conv_video_progress_value', 0) + 0.5
                        if self.conv_video_progress_value > 99:
                            self.conv_video_progress_value = 99
                        self.host.after(0, lambda p=self.conv_video_progress_value:
                                       self.conv_video_progress.config(value=p))
                        self.host.after(0, lambda cf=current_frame: self.conv_frame_label.config(
                            text=f"已处理: {cf} / -- 帧"))
                time.sleep(0.05)

            self.conv_current_process.wait()

            # 检查返回码
            if self.conv_current_process.returncode != 0:
                err_msg = f"FFmpeg 返回码 {self.conv_current_process.returncode}"
                self.conv_failed_files.append((input_path, err_msg))
                self.log('error', f"处理失败 [{filename}]: {err_msg}")
                self.host.after(0, lambda m=err_msg: self.conv_status_label.config(text=f"状态: {m}"))
                safe_remove(output_path, self.host, self.TAB_NAME)
            else:
                self.log('info', f"处理成功 [{filename}]")

            with self.conv_process_lock:
                self.conv_current_process = None

        except Exception as e:
            err_msg = str(e)
            self.conv_failed_files.append((input_path, err_msg))
            self.log('error', f"处理失败 [{filename}]: {err_msg}")
            self.host.after(0, lambda m=err_msg: self.conv_status_label.config(text=f"状态: 错误 - {m}"))
            safe_remove(output_path, self.host, self.TAB_NAME)

    def conv_finish(self):
        """完成处理"""
        self.conv_processing = False
        self.host.set_processing_state(self.tab_widget, False)

        self.conv_start_btn.config(state=tk.NORMAL)
        self.conv_select_output_btn.config(state=tk.NORMAL)
        self.conv_stop_btn.config(state=tk.DISABLED)
        self.conv_open_btn.config(state=tk.NORMAL)
        self.conv_encode_panel.set_state(tk.NORMAL)

        self.conv_current_label.config(text="无")
        self.conv_video_progress.config(value=0)
        self.conv_total_progress.config(value=100)

        total = len(getattr(self, 'conv_video_files', []))
        failed = len(getattr(self, 'conv_failed_files', []))
        success = total - failed

        if failed > 0:
            self.log('warning', f"处理完成，{failed}/{total} 个文件失败")
            self.conv_status_label.config(text=f"状态: 处理完成（{success} 成功，{failed} 失败）")
            failed_list = "\n".join([f"  {os.path.basename(f)}: {e}" for f, e in self.conv_failed_files[:5]])
            if failed > 5:
                failed_list += f"\n  ... 还有 {failed - 5} 个文件失败"
            messagebox.showwarning("完成", f"视频编码转换完成，但部分文件失败：\n\n成功: {success} 个\n失败: {failed} 个\n\n失败详情:\n{failed_list}")
        else:
            self.log('info', f"全部完成！成功处理 {total} 个文件")
            self.conv_status_label.config(text="状态: 处理完成")
            messagebox.showinfo("完成", "视频编码转换已完成！")

    def conv_open_output(self):
        """打开输出文件夹"""
        if self.conv_output_folder and os.path.exists(self.conv_output_folder):
            os.startfile(self.conv_output_folder)

    def save_config(self, config):
        """保存配置到嵌套字典"""
        data = {}
        if hasattr(self, 'conv_encode_panel'):
            data.update(self.conv_encode_panel.save_config())
        if hasattr(self, 'conv_output_folder'):
            data["output_folder"] = self.conv_output_folder
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        """从子字典加载配置"""
        if hasattr(self, 'conv_encode_panel'):
            self.conv_encode_panel.load_config(config)
        if hasattr(self, 'conv_output_folder'):
            folder = config.get("output_folder", "")
            if folder:
                self.conv_output_folder = folder
                if hasattr(self, 'conv_output_var'):
                    self.conv_output_var.set(folder)

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        if hasattr(self, 'conv_encode_panel'):
            self.conv_encode_panel.reset()
        if hasattr(self, 'conv_output_folder'):
            self.conv_output_folder = ""
            if hasattr(self, 'conv_output_var'):
                self.conv_output_var.set("未选择")


# 模块导出
MODULE_CLASS = VideoConverterModule
