# -*- coding: utf-8 -*-
"""视频分辨率检查模块"""

import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from common import TabModule, FileSelector


class ResolutionCheckerModule(TabModule):
    """视频分辨率检查模块"""
    TAB_NAME = "视频分辨率检查"
    TAB_ORDER = 4
    PIP_DEPENDENCIES = []
    CONFIG_KEY = "resolution_checker"
    EXE_REQUIREMENTS = ['ffprobe']

    def __init__(self, host):
        super().__init__(host)
        self.res_processing = False
        self.res_stop_flag = False

    def build_ui(self, parent):
        """构建标签页 UI"""
        self.res_target_width = tk.IntVar(value=1920)
        self.res_target_height = tk.IntVar(value=1080)
        self.res_thread_count = tk.IntVar(value=8)

        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 统一文件选择器
        input_frame = ttk.LabelFrame(main_frame, text="视频文件", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.res_file_selector = FileSelector(input_frame, supported_types='video')

        # 分辨率输入
        res_frame = ttk.LabelFrame(main_frame, text="目标分辨率", padding="5")
        res_frame.pack(fill=tk.X, pady=5)

        ttk.Label(res_frame, text="宽度:").pack(side=tk.LEFT, padx=5)
        self.res_width_entry = ttk.Spinbox(res_frame, from_=1, to=7680, width=6, textvariable=self.res_target_width)
        self.res_width_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(res_frame, text="高度:").pack(side=tk.LEFT, padx=5)
        self.res_height_entry = ttk.Spinbox(res_frame, from_=1, to=4320, width=6, textvariable=self.res_target_height)
        self.res_height_entry.pack(side=tk.LEFT, padx=5)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        self.res_start_btn = ttk.Button(btn_frame, text="开始检测", command=self.res_start)
        self.res_start_btn.pack(side=tk.RIGHT, padx=5)

        self.res_cancel_btn = ttk.Button(btn_frame, text="取消", command=self.res_cancel, state=tk.DISABLED)
        self.res_cancel_btn.pack(side=tk.RIGHT, padx=5)

        # 线程数量
        thread_frame = ttk.Frame(main_frame)
        thread_frame.pack(fill=tk.X, pady=5)

        ttk.Label(thread_frame, text="线程数量:").pack(side=tk.LEFT, padx=5)
        ttk.Spinbox(thread_frame, from_=1, to=64, width=5, textvariable=self.res_thread_count).pack(side=tk.LEFT, padx=5)
        ttk.Label(thread_frame, text="(1-64)").pack(side=tk.LEFT, padx=5)

        # 进度条
        self.res_progress = ttk.Progressbar(main_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.res_progress.pack(fill=tk.X, pady=5)

        self.res_progress_label = ttk.Label(main_frame, text="准备就绪")
        self.res_progress_label.pack(fill=tk.X, pady=2)

        # 结果表格
        result_frame = ttk.LabelFrame(main_frame, text="检测结果", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("文件路径", "实际分辨率")
        self.res_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=1)

        for col in columns:
            self.res_tree.heading(col, text=col)
            self.res_tree.column(col, width=300)

        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.res_tree.yview)
        self.res_tree.configure(yscrollcommand=scrollbar.set)

        self.res_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._ui_built = True

    def res_start(self):
        """开始检测"""
        if self.res_processing:
            return
        video_files = self.res_file_selector.get_files()
        if not video_files:
            messagebox.showwarning("警告", "请先添加视频文件")
            return

        try:
            target_width = self.res_target_width.get()
            target_height = self.res_target_height.get()
        except (tk.TclError, ValueError):
            messagebox.showwarning("警告", "请输入有效的宽度和高度")
            return

        if target_width <= 0 or target_height <= 0:
            messagebox.showwarning("警告", "宽度和高度必须大于 0")
            return

        # 清空表格
        for item in self.res_tree.get_children():
            self.res_tree.delete(item)

        self.res_processing = True
        self.res_stop_flag = False
        self.host.set_processing_state(self.tab_widget, True)

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        self.res_start_btn.config(state=tk.DISABLED)
        self.res_cancel_btn.config(state=tk.NORMAL)
        self.res_width_entry.config(state=tk.DISABLED)
        self.res_height_entry.config(state=tk.DISABLED)
        self.res_progress["value"] = 0
        self.res_progress_label.config(text="正在扫描文件夹...")

        threading.Thread(target=self.res_process, args=(video_files, target_width, target_height), daemon=True).start()

    def res_cancel(self):
        """取消检测"""
        self.res_stop_flag = True
        self.res_progress_label.config(text="正在取消...")

    def stop_processing(self):
        """外部调用停止"""
        self.res_cancel()

    def is_processing(self):
        return self.res_processing

    def res_process(self, video_files, target_width, target_height):
        """处理视频"""
        total = len(video_files)
        if total == 0:
            self.log('warning', "未找到视频文件")
            self.host.after(0, lambda: self.res_progress_label.config(text="未找到视频文件"))
            self.host.after(0, self.res_finish)
            return

        self.log('info', f"开始检测，共 {total} 个文件，目标分辨率: {target_width}*{target_height}")

        mismatched = []
        processed = 0

        for i, video_file in enumerate(video_files):
            if self.res_stop_flag:
                self.log('warning', "用户取消操作")
                break

            filename = os.path.basename(video_file)
            self.log('info', f"[{i+1}/{total}] 检测: {filename}")

            try:
                width, height = self.res_get_resolution(video_file)
                if width == 0 and height == 0:
                    mismatched.append((video_file, "无法检测"))
                    self.log('warning', f"无法检测分辨率 [{filename}]")
                elif width != target_width or height != target_height:
                    mismatched.append((video_file, f"{width}*{height}"))
                    self.log('info', f"分辨率不符 [{filename}]: {width}*{height}")
                else:
                    self.log('info', f"检测成功 [{filename}]: {width}*{height} (符合)")
            except Exception as e:
                self.host.after(0, lambda m=str(e): self.res_progress_label.config(text=f"错误: {m}"))
                mismatched.append((video_file, f"检测错误: {e}"))
                self.log('error', f"检测失败 [{filename}]: {e}")

            processed += 1
            progress = (processed / total) * 100
            self.host.after(0, lambda p=progress: self.res_progress.config(value=p))
            self.host.after(0, lambda p=progress, pr=processed, t=total: self.res_progress_label.config(text=f"正在处理: {pr}/{t}"))

        # 记录完成日志
        if mismatched:
            self.log('warning', f"检测完成，{len(mismatched)}/{total} 个文件不符合目标分辨率")
        else:
            self.log('info', f"全部完成！{total} 个文件都符合目标分辨率 {target_width}*{target_height}")

        self.host.after(0, lambda: self.res_display_results(mismatched))
        self.host.after(0, self.res_finish)

    def res_get_resolution(self, video_file):
        """获取视频分辨率"""
        try:
            ffprobe_path = self.get_exe_path('ffprobe')
            cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", video_file]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW,
                                    timeout=120)
            if result.returncode == 0:
                resolution = result.stdout.strip()
                if "x" in resolution:
                    width, height = map(int, resolution.split("x"))
                    return width, height
        except Exception:
            pass
        return 0, 0

    def res_display_results(self, mismatched):
        """显示结果"""
        for item in self.res_tree.get_children():
            self.res_tree.delete(item)

        sorted_videos = sorted(mismatched, key=lambda x: os.path.basename(x[0]).lower())

        for video_path, resolution in sorted_videos:
            self.res_tree.insert("", tk.END, values=(video_path, resolution))

        if not sorted_videos:
            self.res_progress_label.config(text="所有视频都符合目标分辨率")
        else:
            self.res_progress_label.config(text=f"找到 {len(sorted_videos)} 个不符合分辨率的视频")

    def res_finish(self):
        """完成处理"""
        self.res_processing = False
        self.host.set_processing_state(self.tab_widget, False)
        self.res_start_btn.config(state=tk.NORMAL)
        self.res_cancel_btn.config(state=tk.DISABLED)
        self.res_width_entry.config(state=tk.NORMAL)
        self.res_height_entry.config(state=tk.NORMAL)
        self.res_progress["value"] = 100

    def save_config(self, config):
        """保存配置到嵌套字典"""
        data = {}
        if hasattr(self, 'res_target_width'):
            data["target_width"] = self.res_target_width.get()
        if hasattr(self, 'res_target_height'):
            data["target_height"] = self.res_target_height.get()
        if hasattr(self, 'res_thread_count'):
            data["thread_count"] = self.res_thread_count.get()
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        """从子字典加载配置"""
        if hasattr(self, 'res_target_width'):
            val = config.get("target_width")
            if val is not None:
                self.res_target_width.set(val)
        if hasattr(self, 'res_target_height'):
            val = config.get("target_height")
            if val is not None:
                self.res_target_height.set(val)
        if hasattr(self, 'res_thread_count'):
            val = config.get("thread_count")
            if val is not None:
                self.res_thread_count.set(val)

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        if hasattr(self, 'res_target_width'):
            self.res_target_width.set(1920)
        if hasattr(self, 'res_target_height'):
            self.res_target_height.set(1080)
        if hasattr(self, 'res_thread_count'):
            self.res_thread_count.set(8)


# 模块导出
MODULE_CLASS = ResolutionCheckerModule
