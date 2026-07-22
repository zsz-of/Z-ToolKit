# -*- coding: utf-8 -*-
"""视频编码选项公共组件

封装编码器选择、CRF、压缩模式、色彩深度的 UI 和逻辑。
被 video_converter 和 video_scale 共用，消除重复代码。

使用方式:
    panel = EncodingOptionsPanel(parent_frame)
    panel.pack()                          # 布局
    args = panel.build_ffmpeg_args()      # 获取 ffmpeg 编码参数
    panel.set_state(tk.DISABLED)          # 处理时禁用
    panel.save_config() / load_config()   # 配置持久化
"""

import tkinter as tk
from tkinter import ttk


class EncodingOptionsPanel:
    """编码选项公共组件

    封装编码器选择、CRF、压缩模式、色彩深度，被视频处理类模块共用。
    """

    ENCODING_OPTIONS = {
        "VP9": "libvpx-vp9", "H.264": "libx264", "H.265": "libx265",
        "H.266": "libvvenc", "AV1": "libsvtav1"
    }

    def __init__(self, parent):
        """
        参数:
            parent: 父容器（编码选项 UI 将 pack 到该容器）
        """
        self.parent = parent
        self.selected_encoder = "libsvtav1"
        self._build_ui()
        self.update_encoder()
        self.update_crf_label(18)
        self.update_preset_label(6)

    def _build_ui(self):
        """构建编码选项 UI"""
        # 编码器选择
        options_frame = ttk.LabelFrame(self.parent, text="编码选项", padding=5)
        options_frame.pack(fill=tk.X, padx=5, pady=5)
        self.options_frame = options_frame

        ttk.Label(options_frame, text="编码器:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.encoder_var = tk.StringVar(value="AV1")
        self.encoder_radios = []
        for i, (name, value) in enumerate(self.ENCODING_OPTIONS.items()):
            rb = ttk.Radiobutton(options_frame, text=name, variable=self.encoder_var,
                                value=name, command=self.update_encoder)
            rb.grid(row=0, column=i+1, padx=5, pady=5)
            self.encoder_radios.append(rb)

        # CRF 设置
        crf_frame = ttk.LabelFrame(self.parent, text="CRF值 (质量设置)", padding=5)
        crf_frame.pack(fill=tk.X, padx=5, pady=5)
        self.crf_frame = crf_frame

        ttk.Label(crf_frame, text="数值越小质量越高，文件越大").pack(anchor=tk.W, padx=5)

        self.crf_var = tk.IntVar(value=18)
        self.crf_slider = ttk.Scale(crf_frame, from_=0, to=51, orient=tk.HORIZONTAL,
                                    variable=self.crf_var, command=self.update_crf_label)
        self.crf_slider.pack(fill=tk.X, padx=5, pady=5)

        crf_label_frame = ttk.Frame(crf_frame)
        crf_label_frame.pack(fill=tk.X, padx=5)

        ttk.Label(crf_label_frame, text="CRF: ").pack(side=tk.LEFT)
        self.crf_value_label = ttk.Label(crf_label_frame, text="18")
        self.crf_value_label.pack(side=tk.LEFT)
        ttk.Label(crf_label_frame, text="  (").pack(side=tk.LEFT)
        self.crf_desc_label = ttk.Label(crf_label_frame, text="高质量")
        self.crf_desc_label.pack(side=tk.LEFT)
        ttk.Label(crf_label_frame, text=")").pack(side=tk.LEFT)

        # 压缩模式
        preset_frame = ttk.LabelFrame(self.parent, text="压缩模式", padding=5)
        preset_frame.pack(fill=tk.X, padx=5, pady=5)
        self.preset_frame = preset_frame

        ttk.Label(preset_frame, text="左边速度快/质量低，右边速度慢/质量高").pack(anchor=tk.W, padx=5)

        self.preset_mode_var = tk.StringVar(value="6")
        self.preset_slider = ttk.Scale(preset_frame, from_=0, to=10, orient=tk.HORIZONTAL,
                                       variable=self.preset_mode_var, command=self.update_preset_label)
        self.preset_slider.pack(fill=tk.X, padx=5, pady=5)

        preset_label_frame = ttk.Frame(preset_frame)
        preset_label_frame.pack(fill=tk.X, padx=5)

        ttk.Label(preset_label_frame, text="预设: ").pack(side=tk.LEFT)
        self.preset_value_label = ttk.Label(preset_label_frame, text="6")
        self.preset_value_label.pack(side=tk.LEFT)
        ttk.Label(preset_label_frame, text="  (").pack(side=tk.LEFT)
        self.preset_desc_label = ttk.Label(preset_label_frame, text="中等")
        self.preset_desc_label.pack(side=tk.LEFT)
        ttk.Label(preset_label_frame, text=")").pack(side=tk.LEFT)

        # 色彩深度
        depth_frame = ttk.LabelFrame(self.parent, text="色彩深度选项", padding=5)
        depth_frame.pack(fill=tk.X, padx=5, pady=5)
        self.depth_frame = depth_frame

        self.depth_var = tk.StringVar(value="auto")
        self.depth_radios = []
        for i, (text, value) in enumerate([("输出8-bit", "8bit"), ("输出10-bit", "10bit"), ("自动判断", "auto")]):
            rb = ttk.Radiobutton(depth_frame, text=text, variable=self.depth_var, value=value)
            rb.grid(row=0, column=i, padx=5, pady=5)
            self.depth_radios.append(rb)

    def update_encoder(self):
        """更新编码器，并根据编码器类型调整压缩模式滑块范围"""
        encoder_name = self.encoder_var.get()
        self.selected_encoder = self.ENCODING_OPTIONS[encoder_name]

        if self.selected_encoder in ['libx264', 'libx265']:
            self.preset_slider.config(from_=0, to=9)
            self.preset_mode_var.set("6")
        elif self.selected_encoder == 'libsvtav1':
            self.preset_slider.config(from_=0, to=13)
            self.preset_mode_var.set("6")
        elif self.selected_encoder == 'libvpx-vp9':
            self.preset_slider.config(from_=0, to=2)
            self.preset_mode_var.set("1")
        elif self.selected_encoder == 'libvvenc':
            self.preset_slider.config(from_=0, to=4)
            self.preset_mode_var.set("2")
        self.update_preset_label(self.preset_mode_var.get())

    def update_crf_label(self, value):
        """更新 CRF 标签"""
        crf = int(float(value))
        self.crf_value_label.config(text=str(crf))
        if crf <= 15:
            desc = "极高画质"
        elif crf <= 18:
            desc = "高质量"
        elif crf <= 23:
            desc = "中等质量"
        elif crf <= 28:
            desc = "较低质量"
        else:
            desc = "低质量"
        self.crf_desc_label.config(text=desc)

    def update_preset_label(self, value):
        """更新压缩模式预设标签"""
        preset = int(float(value))
        self.preset_value_label.config(text=str(preset))

        if self.selected_encoder in ['libx264', 'libx265']:
            presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast',
                      'medium', 'slow', 'slower', 'veryslow', 'placebo']
            desc = presets[preset] if preset < len(presets) else 'placebo'
        elif self.selected_encoder == 'libsvtav1':
            if preset <= 4:
                desc = "极慢/极高画质"
            elif preset <= 8:
                desc = "中等/高质量"
            elif preset <= 11:
                desc = "快速/中等质量"
            else:
                desc = "极快/较低质量"
        elif self.selected_encoder == 'libvpx-vp9':
            deadlines = ['realtime', 'good', 'best']
            desc = deadlines[preset] if preset < len(deadlines) else 'best'
        else:
            presets = ['fast', 'faster', 'medium', 'slow', 'slower']
            desc = presets[preset] if preset < len(presets) else 'veryslow'
        self.preset_desc_label.config(text=desc)

    def get_preset_value(self):
        """获取压缩模式预设值（用于 ffmpeg 命令）"""
        preset = int(float(self.preset_mode_var.get()))
        if self.selected_encoder in ['libx264', 'libx265']:
            presets = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast',
                      'medium', 'slow', 'slower', 'veryslow', 'placebo']
            return presets[preset] if preset < len(presets) else 'placebo'
        elif self.selected_encoder == 'libsvtav1':
            return str(preset)
        elif self.selected_encoder == 'libvpx-vp9':
            deadlines = ['realtime', 'good', 'best']
            return deadlines[preset] if preset < len(deadlines) else 'best'
        else:
            presets = ['fast', 'faster', 'medium', 'slow', 'slower']
            return presets[preset] if preset < len(presets) else 'veryslow'

    def get_encoder(self):
        """返回当前选中的编码器内部名称（如 'libsvtav1'）"""
        return self.selected_encoder

    def get_crf(self):
        """返回当前 CRF 值"""
        return int(self.crf_var.get())

    def get_depth(self):
        """返回色彩深度选项"""
        return self.depth_var.get()

    def get_pixel_format(self):
        """根据色彩深度返回像素格式"""
        depth = self.depth_var.get()
        if depth == "8bit":
            return "yuv420p"
        elif depth == "10bit":
            return "yuv420p10le"
        else:
            return "yuv420p"

    def build_ffmpeg_args(self):
        """构建 ffmpeg 编码参数列表（不含 -vf 和 -i 等通用参数）

        返回:
            list[str]: 如 ['-c:v', 'libsvtav1', '-preset', '6', '-crf', '18']
        """
        encoder = self.selected_encoder
        crf = self.get_crf()
        preset = self.get_preset_value()
        if encoder == 'libvpx-vp9':
            return ['-c:v', encoder, '-deadline', preset, '-cpu-used', '1',
                    '-crf', str(crf), '-b:v', '0']
        else:
            return ['-c:v', encoder, '-preset', preset, '-crf', str(crf)]

    def set_state(self, state):
        """设置所有控件的启用/禁用状态（tk.NORMAL 或 tk.DISABLED）"""
        self.crf_slider.config(state=state)
        self.preset_slider.config(state=state)
        for rb in self.encoder_radios:
            rb.config(state=state)
        for rb in self.depth_radios:
            rb.config(state=state)

    def save_config(self):
        """返回配置字典"""
        return {
            "encoder": self.encoder_var.get(),
            "crf": self.crf_var.get(),
            "preset_mode": self.preset_mode_var.get(),
            "depth": self.depth_var.get()
        }

    def load_config(self, config):
        """从配置字典加载"""
        enc = config.get("encoder", "")
        if enc:
            self.encoder_var.set(enc)
            self.update_encoder()
        crf = config.get("crf")
        if crf is not None:
            self.crf_var.set(crf)
            self.update_crf_label(crf)
        pre = config.get("preset_mode", "")
        if pre:
            self.preset_mode_var.set(pre)
            self.update_preset_label(pre)
        depth = config.get("depth", "")
        if depth:
            self.depth_var.set(depth)

    def reset(self):
        """重置为默认值"""
        self.encoder_var.set("AV1")
        self.crf_var.set(18)
        self.preset_mode_var.set("6")
        self.depth_var.set("auto")
        self.update_encoder()
        self.update_crf_label(18)
        self.update_preset_label(6)
