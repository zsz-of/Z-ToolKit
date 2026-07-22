# -*- coding: utf-8 -*-
"""视频缩放模块

包含缩放滤镜构建、ffmpeg 命令构建、进度解析、视频缩放处理等纯业务逻辑，
以及 UI 与事件调度层。

FFmpeg 路径由主程序外部工具管理统一提供。
"""

import os
import re
import time
import threading
import subprocess
import tkinter as tk
from collections import deque
from tkinter import ttk, filedialog, messagebox

from common import TabModule, FileSelector, EncodingOptionsPanel, safe_remove, get_video_total_frames


# ========== 业务逻辑层 ==========

# 常量定义

# 缩放算法选项：(value, display)
SCALE_ALGO_OPTIONS = [
    ("fast_bilinear", "快速双线性（最快/质量较低）"),
    ("bilinear", "双线性（较快/质量一般）"),
    ("bicubic", "双三次（中等/质量较好）"),
    ("lanczos", "Lanczos（较慢/质量最好）"),
]

# 显示名 → 内部值 的映射
ALGO_DISPLAY_TO_VALUE = {display: value for value, display in SCALE_ALGO_OPTIONS}

# 预设分辨率：显示名 → (宽, 高)
RESOLUTION_PRESETS = {
    "480p (854x480)": (854, 480),
    "720p (1280x720)": (1280, 720),
    "1080p (1920x1080)": (1920, 1080),
    "1440p (2560x1440)": (2560, 1440),
    "4K (3840x2160)": (3840, 2160),
}


# 维度校验

def validate_even_dimension(value):
    """校验像素值必须为偶数，否则修正为最近的偶数

    Args:
        value: 输入的像素值

    Returns:
        tuple: (corrected_value, was_corrected)
            corrected_value: 修正后的值（无法解析时原样返回）
            was_corrected: 是否进行了修正
    """
    try:
        v = int(value)
    except (ValueError, TypeError):
        return value, False
    if v % 2 != 0:
        corrected = v + 1 if v > 0 else v - 1
        return corrected, True
    return v, False


# 输出路径解析

def resolve_output_path(output_folder, video_file):
    """解析输出路径，若已存在同名文件则添加数字后缀避免冲突

    Args:
        output_folder: 输出文件夹
        video_file: 输入视频文件路径

    Returns:
        str: 最终输出文件路径
    """
    output_name = os.path.basename(video_file)
    output_path = os.path.join(output_folder, output_name)
    if not os.path.exists(output_path):
        return output_path
    base, ext = os.path.splitext(output_name)
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(output_folder, f"{base}_{counter}{ext}")
        counter += 1
    return output_path


# 缩放滤镜与命令构建

def build_scale_filter(target_width, target_height, algo_value, keep_ratio, pixel_format):
    """构建缩放滤镜字符串（含色彩深度格式转换）

    Args:
        target_width: 目标宽度（必须为偶数）
        target_height: 目标高度（必须为偶数）
        algo_value: 缩放算法内部值（如 'lanczos'）
        keep_ratio: 是否保持原始宽高比
        pixel_format: 像素格式（如 'yuv420p'）

    Returns:
        str: ffmpeg -vf 滤镜字符串
    """
    if keep_ratio:
        return (f"scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease:force_divisible_by=2:"
                f"flags={algo_value},setsar=1:1,format={pixel_format}")
    return (f"scale={target_width}:{target_height}:"
            f"force_divisible_by=2:flags={algo_value},format={pixel_format}")


def build_scale_command(ffmpeg_path, video_file, output_path, encode_args, vf_filter):
    """构建 ffmpeg 缩放命令

    Args:
        ffmpeg_path: ffmpeg 可执行文件路径
        video_file: 输入视频文件
        output_path: 输出文件路径
        encode_args: 编码参数列表（由 EncodingOptionsPanel.build_ffmpeg_args() 提供）
        vf_filter: 缩放滤镜字符串

    Returns:
        list[str]: ffmpeg 命令参数列表
    """
    cmd = [ffmpeg_path, '-y', '-i', video_file, '-map', '0', '-c', 'copy']
    cmd.extend(encode_args)
    cmd.extend(['-vf', vf_filter, output_path])
    return cmd


# 进度解析

def parse_frame_from_line(line):
    """从 ffmpeg 输出行解析当前已处理帧数

    Args:
        line: ffmpeg stdout 的一行文本

    Returns:
        int | None: 帧数，无法解析时返回 None
    """
    match = re.search(r'frame=\s*(\d+)', line)
    return int(match.group(1)) if match else None


def compute_file_progress(current_frame, total_frames):
    """计算文件处理进度百分比

    Args:
        current_frame: 当前已处理帧数
        total_frames: 总帧数

    Returns:
        float | None: 进度百分比（0-100），无总帧数时返回 None
    """
    if total_frames and total_frames > 0:
        return min(100, (current_frame / total_frames) * 100)
    return None


# 视频缩放处理

def process_single_video(video_file, params, callbacks):
    """处理单个视频文件的缩放

    Args:
        video_file: 输入视频文件路径
        params: dict，包含：
            - target_width (int): 目标宽度
            - target_height (int): 目标高度
            - algo_display (str): 缩放算法显示名
            - keep_ratio (bool): 是否保持宽高比
            - output_folder (str): 输出文件夹
            - ffmpeg_path (str): ffmpeg 路径
            - ffprobe_path (str): ffprobe 路径
            - encode_args (list): 编码参数
            - pixel_format (str): 像素格式
            - host: HostInterface 实例（用于 safe_remove 日志）
            - tab_name (str): 日志来源标签
        callbacks: dict，包含：
            - is_stopped () -> bool: 是否请求停止
            - log (level, msg) -> None: 日志记录
            - on_file_progress (pct) -> None: UI 更新文件进度
            - on_frame_label (text) -> None: UI 更新帧标签
            - on_status (text) -> None: UI 更新状态
            - on_failed (file, err) -> None: 记录失败文件
            - register_process (proc|None) -> None: 注册/注销当前进程

    Returns:
        bool: 处理是否成功
    """
    filename = os.path.basename(video_file)
    target_width = params['target_width']
    target_height = params['target_height']
    # 兜底修正：确保宽高为偶数
    if target_width % 2 != 0:
        target_width += 1
    if target_height % 2 != 0:
        target_height += 1
    algo_value = ALGO_DISPLAY_TO_VALUE.get(params['algo_display'], params['algo_display'])
    pixel_format = params['pixel_format']
    ffmpeg_path = params['ffmpeg_path']
    ffprobe_path = params['ffprobe_path']

    output_path = resolve_output_path(params['output_folder'], video_file)
    vf_filter = build_scale_filter(target_width, target_height, algo_value,
                                   params['keep_ratio'], pixel_format)
    cmd = build_scale_command(ffmpeg_path, video_file, output_path,
                              params['encode_args'], vf_filter)

    total_frames = get_video_total_frames(video_file,
                                          ffprobe_path=ffprobe_path,
                                          ffmpeg_path=ffmpeg_path)
    callbacks['on_frame_label'](f"已处理: 0 / {total_frames if total_frames else '--'} 帧")

    stderr_lines = deque(maxlen=20)
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, encoding='utf-8', errors='ignore',
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        callbacks['register_process'](proc)

        file_progress_value = 0
        while True:
            if callbacks['is_stopped']():
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
                break

            if proc.poll() is not None:
                break

            line = proc.stdout.readline()
            if line:
                stderr_lines.append(line)
            current_frame = parse_frame_from_line(line)
            if current_frame is not None:
                pct = compute_file_progress(current_frame, total_frames)
                if pct is not None:
                    callbacks['on_file_progress'](pct)
                    callbacks['on_frame_label'](f"已处理: {current_frame} / {total_frames} 帧")
                else:
                    file_progress_value = min(99, file_progress_value + 0.5)
                    callbacks['on_file_progress'](file_progress_value)
                    callbacks['on_frame_label'](f"已处理: {current_frame} / -- 帧")
            time.sleep(0.05)

        proc.wait()
        for line in proc.stdout:
            if line:
                stderr_lines.append(line)

        if proc.returncode != 0:
            if callbacks['is_stopped']():
                safe_remove(output_path, params['host'], params['tab_name'])
            else:
                stderr_text = ''.join(stderr_lines)
                err_msg = f"FFmpeg 返回码 {proc.returncode}\n{stderr_text}"
                callbacks['on_failed'](video_file, err_msg)
                callbacks['log']('error', f"处理失败 [{filename}]: FFmpeg 返回码 {proc.returncode}")
                callbacks['on_status'](f"状态: {err_msg[:200]}")
                safe_remove(output_path, params['host'], params['tab_name'])
        else:
            callbacks['log']('info', f"处理成功 [{filename}]，已缩放到 {target_width}x{target_height}")

        callbacks['register_process'](None)
        return proc.returncode == 0

    except Exception as e:
        err_msg = str(e)
        callbacks['on_failed'](video_file, err_msg)
        callbacks['log']('error', f"处理失败 [{filename}]: {err_msg}")
        callbacks['on_status'](f"状态: 错误 - {err_msg}")
        safe_remove(output_path, params['host'], params['tab_name'])
        callbacks['register_process'](None)
        return False


def process_files(files, params, callbacks):
    """处理多个视频文件的缩放

    Args:
        files: 输入视频文件路径列表
        params: dict，同 process_single_video 的 params
        callbacks: dict，同 process_single_video 的 callbacks，额外包含：
            - on_current_file (name) -> None: UI 更新当前文件名
            - on_total_progress (pct) -> None: UI 更新总进度
            - on_processed_count (count) -> None: 记录已处理数量
            - on_complete () -> None: 处理完成回调
    """
    total = len(files)
    processed = 0
    target_width = params['target_width']
    target_height = params['target_height']
    callbacks['log']('info', f"开始处理，共 {total} 个文件，目标分辨率: {target_width}x{target_height}")

    for i, video in enumerate(files):
        if callbacks['is_stopped']():
            callbacks['log']('warning', "用户取消操作")
            break

        filename = os.path.basename(video)
        callbacks['on_current_file'](filename)
        callbacks['on_file_progress'](0)
        callbacks['on_total_progress']((i / total) * 100)
        callbacks['on_status']("状态: 处理中...")
        callbacks['log']('info', f"[{i + 1}/{total}] 开始处理: {filename}")

        process_single_video(video, params, callbacks)
        processed += 1

    callbacks['on_processed_count'](processed)
    callbacks['on_complete']()


# ========== UI 层 ==========

class VideoScaleModule(TabModule):
    """视频缩放模块"""
    TAB_NAME = "视频缩放"
    TAB_ORDER = 10
    CONFIG_KEY = "video_scale"
    PIP_DEPENDENCIES = []
    EXE_REQUIREMENTS = ['ffmpeg', 'ffprobe']

    def __init__(self, host):
        super().__init__(host)
        self.scale_processing = False
        self.scale_stop_flag = False
        self.scale_output_folder = ""
        self.scale_current_process = None
        self.scale_process_lock = threading.Lock()

    def build_ui(self, parent):
        """构建标签页 UI"""
        paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        # 统一文件选择器
        input_frame = ttk.LabelFrame(left_frame, text="文件选择", padding=5)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.scale_file_selector = FileSelector(input_frame, supported_types='video')
        # 输出设置
        output_frame = ttk.LabelFrame(left_frame, text="输出设置", padding=5)
        output_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(output_frame, text="输出文件夹:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.scale_output_var = tk.StringVar(value="未选择")
        ttk.Label(output_frame, textvariable=self.scale_output_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        self.scale_select_output_btn = ttk.Button(output_frame, text="选择", command=self.scale_select_output)
        self.scale_select_output_btn.grid(row=0, column=2, padx=5, pady=5)
        # 缩放设置
        scale_frame = ttk.LabelFrame(right_frame, text="缩放设置", padding=5)
        scale_frame.pack(fill=tk.X, padx=5, pady=5)
        # 宽度设置
        width_frame = ttk.Frame(scale_frame)
        width_frame.pack(fill=tk.X, pady=5)
        ttk.Label(width_frame, text="目标宽度:").pack(side=tk.LEFT, padx=5)
        self.scale_width_var = tk.IntVar(value=1920)
        self.scale_width_spinbox = ttk.Spinbox(width_frame, from_=320, to=7680, width=10, textvariable=self.scale_width_var)
        self.scale_width_spinbox.pack(side=tk.LEFT, padx=5)
        self.scale_width_spinbox.bind("<FocusOut>", lambda e: self.scale_validate_dimension(self.scale_width_var, self.scale_width_spinbox, "宽度"))
        ttk.Label(width_frame, text="像素 (必须为偶数)").pack(side=tk.LEFT)
        # 高度设置
        height_frame = ttk.Frame(scale_frame)
        height_frame.pack(fill=tk.X, pady=5)
        ttk.Label(height_frame, text="目标高度:").pack(side=tk.LEFT, padx=5)
        self.scale_height_var = tk.IntVar(value=1080)
        self.scale_height_spinbox = ttk.Spinbox(height_frame, from_=240, to=4320, width=10, textvariable=self.scale_height_var)
        self.scale_height_spinbox.pack(side=tk.LEFT, padx=5)
        self.scale_height_spinbox.bind("<FocusOut>", lambda e: self.scale_validate_dimension(self.scale_height_var, self.scale_height_spinbox, "高度"))
        ttk.Label(height_frame, text="像素 (必须为偶数)").pack(side=tk.LEFT)
        # 预设分辨率
        preset_res_frame = ttk.Frame(scale_frame)
        preset_res_frame.pack(fill=tk.X, pady=5)
        ttk.Label(preset_res_frame, text="预设:").pack(side=tk.LEFT, padx=5)
        self.scale_preset_var = tk.StringVar(value="custom")
        preset_values = ["自定义"] + list(RESOLUTION_PRESETS.keys())
        self.scale_preset_combo = ttk.Combobox(preset_res_frame, textvariable=self.scale_preset_var,
                                    values=preset_values, state="readonly", width=15)
        self.scale_preset_combo.pack(side=tk.LEFT, padx=5)
        self.scale_preset_combo.bind("<<ComboboxSelected>>", self.scale_apply_preset)
        # 缩放算法
        algo_frame = ttk.Frame(scale_frame)
        algo_frame.pack(fill=tk.X, pady=5)
        ttk.Label(algo_frame, text="缩放算法:").pack(side=tk.LEFT, padx=5)
        self.scale_algo_var = tk.StringVar(value=SCALE_ALGO_OPTIONS[3][1])
        self.scale_algo_combo = ttk.Combobox(algo_frame, textvariable=self.scale_algo_var,
                                  values=[p[1] for p in SCALE_ALGO_OPTIONS], state="readonly", width=25)
        self.scale_algo_combo.pack(side=tk.LEFT, padx=5)
        # 保持宽高比
        self.scale_keep_ratio_var = tk.BooleanVar(value=True)
        self.scale_keep_ratio_chk = ttk.Checkbutton(scale_frame, text="保持原始宽高比", variable=self.scale_keep_ratio_var)
        self.scale_keep_ratio_chk.pack(anchor=tk.W, padx=5, pady=5)
        # 编码选项（使用公共组件）
        self.scale_encode_panel = EncodingOptionsPanel(right_frame)
        # 进度区域
        progress_frame = ttk.LabelFrame(right_frame, text="处理进度", padding=5)
        progress_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(progress_frame, text="当前文件:").pack(anchor=tk.W, padx=5)
        self.scale_current_file_label = ttk.Label(progress_frame, text="无")
        self.scale_current_file_label.pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(progress_frame, text="单个文件进度:").pack(anchor=tk.W, padx=5)
        self.scale_file_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.scale_file_progress.pack(fill=tk.X, padx=5, pady=2)
        self.scale_frame_label = ttk.Label(progress_frame, text="已处理: 0 / -- 帧")
        self.scale_frame_label.pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(progress_frame, text="总进度:").pack(anchor=tk.W, padx=5)
        self.scale_total_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.scale_total_progress.pack(fill=tk.X, padx=5, pady=2)
        self.scale_status_label = ttk.Label(progress_frame, text="状态: 等待开始")
        self.scale_status_label.pack(anchor=tk.W, padx=5, pady=2)
        # 控制按钮
        control_frame = ttk.Frame(right_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=10)
        self.scale_start_btn = ttk.Button(control_frame, text="开始处理", command=self.scale_start)
        self.scale_start_btn.pack(side=tk.RIGHT, padx=5)
        self.scale_stop_btn = ttk.Button(control_frame, text="停止处理", command=self.scale_stop, state=tk.DISABLED)
        self.scale_stop_btn.pack(side=tk.RIGHT, padx=5)
        self.scale_open_output_btn = ttk.Button(control_frame, text="打开输出文件夹",
                                               command=self.scale_open_output, state=tk.DISABLED)
        self.scale_open_output_btn.pack(side=tk.RIGHT, padx=5)
        self._ui_built = True

    def scale_apply_preset(self, event=None):
        """应用预设分辨率"""
        preset = self.scale_preset_var.get()
        if preset in RESOLUTION_PRESETS:
            width, height = RESOLUTION_PRESETS[preset]
            self.scale_width_var.set(width)
            self.scale_height_var.set(height)

    def scale_validate_dimension(self, var, widget, name):
        """验证像素值必须为偶数"""
        corrected, was_corrected = validate_even_dimension(var.get())
        if was_corrected:
            var.set(corrected)
            widget.selection_clear()
            self.host.after(0, lambda: messagebox.showwarning("输入修正", f"{name}必须输入偶数，已自动修正为 {corrected}"))

    def scale_select_output(self):
        """选择输出文件夹"""
        folder = filedialog.askdirectory(title="选择输出文件夹")
        if folder:
            self.scale_output_folder = folder
            self.scale_output_var.set(folder)

    def scale_start(self):
        """开始处理"""
        if self.scale_processing:
            return
        files = self.scale_file_selector.get_files()
        if not files:
            messagebox.showwarning("警告", "请先添加视频文件")
            return
        if not self.scale_output_folder:
            messagebox.showwarning("警告", "请先选择输出文件夹")
            return
        self.scale_processing = True
        self.scale_stop_flag = False
        self.scale_failed_files = []
        self.scale_total_count = len(files)
        self.host.set_processing_state(self.tab_widget, True)
        self.host.clear_error_log(self.TAB_NAME)
        self.scale_start_btn.config(state=tk.DISABLED)
        self.scale_select_output_btn.config(state=tk.DISABLED)
        self.scale_stop_btn.config(state=tk.NORMAL)
        self.scale_open_output_btn.config(state=tk.DISABLED)
        self.scale_width_spinbox.config(state=tk.DISABLED)
        self.scale_height_spinbox.config(state=tk.DISABLED)
        self.scale_preset_combo.config(state=tk.DISABLED)
        self.scale_algo_combo.config(state=tk.DISABLED)
        self.scale_keep_ratio_chk.config(state=tk.DISABLED)
        self.scale_encode_panel.set_state(tk.DISABLED)
        threading.Thread(target=self.scale_process_files, args=(files,), daemon=True).start()

    def scale_stop(self):
        """停止处理"""
        self.scale_stop_flag = True
        self.scale_stop_btn.config(state=tk.DISABLED)
        with self.scale_process_lock:
            proc = self.scale_current_process
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
        self.scale_stop()

    def is_processing(self):
        return self.scale_processing

    def _register_process(self, proc):
        with self.scale_process_lock:
            self.scale_current_process = proc

    def scale_process_files(self, files):
        """处理文件（线程入口）"""
        after = self.host.after
        params = {
            'target_width': self.scale_width_var.get(), 'target_height': self.scale_height_var.get(),
            'algo_display': self.scale_algo_var.get(), 'keep_ratio': self.scale_keep_ratio_var.get(),
            'output_folder': self.scale_output_folder, 'ffmpeg_path': self.get_exe_path('ffmpeg'),
            'ffprobe_path': self.get_exe_path('ffprobe'),
            'encode_args': self.scale_encode_panel.build_ffmpeg_args(),
            'pixel_format': self.scale_encode_panel.get_pixel_format(),
            'host': self.host, 'tab_name': self.TAB_NAME,
        }
        callbacks = {
            'is_stopped': lambda: self.scale_stop_flag, 'log': self.log,
            'on_current_file': lambda v: after(0, lambda: self.scale_current_file_label.config(text=v)),
            'on_file_progress': lambda p: after(0, lambda: self.scale_file_progress.config(value=p)),
            'on_total_progress': lambda p: after(0, lambda: self.scale_total_progress.config(value=p)),
            'on_status': lambda t: after(0, lambda: self.scale_status_label.config(text=t)),
            'on_frame_label': lambda t: after(0, lambda: self.scale_frame_label.config(text=t)),
            'on_failed': lambda f, e: self.scale_failed_files.append((f, e)),
            'register_process': self._register_process,
            'on_processed_count': lambda c: setattr(self, 'scale_processed_count', c),
            'on_complete': lambda: after(0, self.scale_processing_complete),
        }
        process_files(files, params, callbacks)

    def scale_processing_complete(self):
        """处理完成"""
        self.scale_processing = False
        self.host.set_processing_state(self.tab_widget, False)

        self.scale_start_btn.config(state=tk.NORMAL)
        self.scale_select_output_btn.config(state=tk.NORMAL)
        self.scale_stop_btn.config(state=tk.DISABLED)
        self.scale_open_output_btn.config(state=tk.NORMAL)
        self.scale_width_spinbox.config(state=tk.NORMAL)
        self.scale_height_spinbox.config(state=tk.NORMAL)
        self.scale_preset_combo.config(state="readonly")
        self.scale_algo_combo.config(state="readonly")
        self.scale_keep_ratio_chk.config(state=tk.NORMAL)
        self.scale_encode_panel.set_state(tk.NORMAL)

        self.scale_current_file_label.config(text="无")
        self.scale_file_progress.config(value=0)
        self.scale_total_progress.config(value=100)

        total = getattr(self, 'scale_total_count', 0)
        processed = getattr(self, 'scale_processed_count', total)
        failed = len(self.scale_failed_files)
        success = processed - failed

        if failed > 0:
            self.log('warning', f"处理完成，{failed}/{total} 个文件失败")
            self.scale_status_label.config(text=f"状态: 处理完成（{success} 成功，{failed} 失败）")
            failed_list = "\n".join([f"  {os.path.basename(f)}: {e}" for f, e in self.scale_failed_files[:5]])
            if failed > 5:
                failed_list += f"\n  ... 还有 {failed - 5} 个文件失败"
            messagebox.showwarning("完成", f"视频缩放处理完成，但部分文件失败：\n\n成功: {success} 个\n失败: {failed} 个\n\n失败详情:\n{failed_list}")
        else:
            self.log('info', f"全部完成！成功处理 {success} 个文件")
            self.scale_status_label.config(text="状态: 处理完成")
            messagebox.showinfo("完成", "视频缩放处理已完成！")

    def scale_open_output(self):
        """打开输出文件夹"""
        if self.scale_output_folder and os.path.exists(self.scale_output_folder):
            os.startfile(self.scale_output_folder)

    def save_config(self, config):
        """保存配置到嵌套字典"""
        data = {}
        if hasattr(self, 'scale_encode_panel'):
            data.update(self.scale_encode_panel.save_config())
        if hasattr(self, 'scale_preset_var'):
            data["preset"] = self.scale_preset_var.get()
        if hasattr(self, 'scale_width_var'):
            data["width"] = self.scale_width_var.get()
        if hasattr(self, 'scale_height_var'):
            data["height"] = self.scale_height_var.get()
        if hasattr(self, 'scale_algo_var'):
            data["algo"] = self.scale_algo_var.get()
        if hasattr(self, 'scale_keep_ratio_var'):
            data["keep_ratio"] = self.scale_keep_ratio_var.get()
        if hasattr(self, 'scale_output_folder'):
            data["output_folder"] = self.scale_output_folder
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        """从子字典加载配置"""
        if hasattr(self, 'scale_encode_panel'):
            self.scale_encode_panel.load_config(config)
        if hasattr(self, 'scale_preset_var'):
            pre = config.get("preset", "")
            if pre:
                self.scale_preset_var.set(pre)
        if hasattr(self, 'scale_width_var'):
            w = config.get("width")
            if w is not None:
                self.scale_width_var.set(w)
        if hasattr(self, 'scale_height_var'):
            h = config.get("height")
            if h is not None:
                self.scale_height_var.set(h)
        if hasattr(self, 'scale_algo_var'):
            algo = config.get("algo", "")
            if algo:
                self.scale_algo_var.set(algo)
        if hasattr(self, 'scale_keep_ratio_var'):
            kr = config.get("keep_ratio")
            if kr is not None:
                self.scale_keep_ratio_var.set(kr)
        if hasattr(self, 'scale_output_folder'):
            folder = config.get("output_folder", "")
            if folder:
                self.scale_output_folder = folder
                if hasattr(self, 'scale_output_var'):
                    self.scale_output_var.set(folder)

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        if hasattr(self, 'scale_encode_panel'):
            self.scale_encode_panel.reset()
        if hasattr(self, 'scale_preset_var'):
            self.scale_preset_var.set("custom")
        if hasattr(self, 'scale_width_var'):
            self.scale_width_var.set(1920)
        if hasattr(self, 'scale_height_var'):
            self.scale_height_var.set(1080)
        if hasattr(self, 'scale_algo_var'):
            self.scale_algo_var.set(SCALE_ALGO_OPTIONS[3][1])
        if hasattr(self, 'scale_keep_ratio_var'):
            self.scale_keep_ratio_var.set(True)
        if hasattr(self, 'scale_output_folder'):
            self.scale_output_folder = ""
            if hasattr(self, 'scale_output_var'):
                self.scale_output_var.set("未选择")


# 模块导出
MODULE_CLASS = VideoScaleModule
