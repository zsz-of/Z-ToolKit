# -*- coding: utf-8 -*-
"""SRT转ASS字幕模块

包含 SRT 解析、ASS 生成、样式应用、文件读写等纯逻辑函数，
以及 UI 与事件调度层。
"""

import os
import re
import json
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, colorchooser

from common import TabModule, FileSelector


# ========== 业务逻辑层 ==========

# 预设/配置字段的默认值（键名与 UI 变量后缀一致：srt_ass_{key}_var）
PRESET_DEFAULTS = {
    "font_name": "方正兰亭圆GBK",
    "font_size": 80,
    "primary_color": "FFFFFF",
    "outline_color": "000000",
    "outline": 2,
    "shadow": 0,
    "alignment": 2,
    "bold": False,
    "italic": False,
    "scale_x": 100,
    "scale_y": 100,
    "spacing": 0,
    "angle": 0.0,
    "margin_l": 15,
    "margin_r": 15,
    "margin_v": 15,
}

# 字符串字段：加载时使用真值检查（跳过 None 和空字符串）
_STRING_FIELDS = frozenset({"font_name", "primary_color", "outline_color"})


def srt_time_to_ass(time_str):
    """将 SRT 时间戳 (HH:MM:SS,mmm) 转换为 ASS 时间格式 (H:MM:SS.CS)"""
    try:
        time_str = time_str.strip().replace(",", ".")
        parts = time_str.split(":")
        if len(parts) == 3:
            h = int(parts[0])
            mm = parts[1]
            ss_ms = parts[2].split(".")
            ss = ss_ms[0]
            ms = int(ss_ms[1]) if len(ss_ms) > 1 else 0
            cs = ms // 10
            return f"{h}:{mm}:{ss}.{cs:02d}"
        return ":".join(parts)
    except (ValueError, IndexError):
        return "0:00:00.00"


def parse_srt(content):
    """解析 SRT 字幕内容，返回事件列表 [{start, end, text}, ...]"""
    events = []
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        time_line = lines[1]
        time_match = re.match(
            r'(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})',
            time_line,
        )
        if not time_match:
            continue
        start_time = srt_time_to_ass(time_match.group(1))
        end_time = srt_time_to_ass(time_match.group(2))
        text = r'\N'.join(lines[2:])
        text = re.sub(r'<i>(.*?)</i>', r'{\\i1}\1{\\i0}', text)
        text = re.sub(r'<b>(.*?)</b>', r'{\\b1}\1{\\b0}', text)
        text = re.sub(r'<u>(.*?)</u>', r'{\\u1}\1{\\u0}', text)
        text = re.sub(r'<font[^>]*>(.*?)</font>', r'\1', text)
        events.append({'start': start_time, 'end': end_time, 'text': text})
    return events


def color_to_ass(hex_color):
    """将 RGB hex 颜色 (RRGGBB) 转换为 ASS 颜色字符串 (&H00BBGGRR)"""
    hex_color = hex_color.lstrip("#").lstrip("&H")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H00{b}{g}{r}"
    return "&H00FFFFFF"


def build_ass_style(raw):
    """从原始 UI 值字典构建完整的 ASS 样式字典。

    raw 必填键（与 PRESET_DEFAULTS 一致）: font_name, font_size,
        primary_color (hex), outline_color (hex), bold (bool), italic (bool),
        outline, shadow, alignment, scale_x, scale_y, spacing, angle,
        margin_l, margin_r, margin_v
    raw 可选键: back_color (默认 &H14000000), encoding (默认 1)
    """
    return {
        "font_name": raw["font_name"],
        "font_size": raw["font_size"],
        "primary_color": color_to_ass(raw["primary_color"]),
        "outline_color": color_to_ass(raw["outline_color"]),
        "bold": -1 if raw["bold"] else 0,
        "italic": -1 if raw["italic"] else 0,
        "outline": raw["outline"],
        "shadow": raw["shadow"],
        "alignment": raw["alignment"],
        "scale_x": raw["scale_x"],
        "scale_y": raw["scale_y"],
        "spacing": raw["spacing"],
        "angle": raw["angle"],
        "margin_l": raw["margin_l"],
        "margin_r": raw["margin_r"],
        "margin_v": raw["margin_v"],
        "back_color": raw.get("back_color", "&H14000000"),
        "encoding": raw.get("encoding", 1),
    }


def generate_ass(events, style, title="Converted Subtitle"):
    """根据事件列表和样式字典生成完整 ASS 字幕内容"""
    s = style
    ass_content = f"""[Script Info]\nTitle: {title}\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{s['font_name']},{s['font_size']},{s['primary_color']},&H000000FF,{s['outline_color']},{s['back_color']},{s['bold']},{s['italic']},0,0,{s['scale_x']},{s['scale_y']},{s['spacing']},{s['angle']},1,{s['outline']},{s['shadow']},{s['alignment']},{s['margin_l']},{s['margin_r']},{s['margin_v']},{s['encoding']}\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    for event in events:
        ass_content += f"Dialogue: 0,{event['start']},{event['end']},Default,,0,0,0,,{event['text']}\n"
    return ass_content


def read_srt(path, chardet_module=None):
    """读取 SRT 文件内容，自动检测编码（若提供 chardet 模块）"""
    if chardet_module is not None:
        with open(path, 'rb') as f:
            raw = f.read()
        detected = chardet_module.detect(raw)
        encoding = detected.get('encoding', 'utf-8') if detected.get('confidence', 0) > 0.5 else 'utf-8'
        try:
            return raw.decode(encoding, errors='replace')
        except Exception:
            return raw.decode('utf-8', errors='replace')
    else:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()


def convert_single_file(srt_path, style, chardet_module=None):
    """转换单个 SRT 文件为 ASS 内容。

    返回: (events_count, ass_content) 元组；失败抛出异常。
    """
    content = read_srt(srt_path, chardet_module)
    events = parse_srt(content)
    title = os.path.splitext(os.path.basename(srt_path))[0]
    ass_content = generate_ass(events, style, title)
    return len(events), ass_content


def save_preset_to_file(path, preset_dict):
    """将预设字典保存为 JSON 文件"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(preset_dict, f, ensure_ascii=False, indent=2)


def load_preset_from_file(path):
    """从 JSON 文件加载预设字典"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def filter_config_for_apply(config):
    """过滤配置字典，仅返回应被应用的键值对。

    - 跳过 None 值（所有字段）
    - 对字符串字段额外跳过空字符串（与原 load_config 行为一致）
    """
    result = {}
    for key in PRESET_DEFAULTS:
        val = config.get(key)
        if val is None:
            continue
        if key in _STRING_FIELDS and not val:
            continue
        result[key] = val
    return result


# ========== UI 与事件调度层 ==========

class SrtToAssModule(TabModule):
    """SRT转ASS字幕模块"""
    TAB_NAME = "SRT转ASS"
    TAB_ORDER = 11
    CONFIG_KEY = "srt_to_ass"
    PIP_DEPENDENCIES = ['chardet']

    def __init__(self, host):
        super().__init__(host)
        self.srt_ass_processing = False
        # 仅保留 PRESET_DEFAULTS 之外的字段（ASS 格式常量，不参与 UI 变量）
        self.srt_ass_style = {"back_color": "&H14000000", "encoding": 1}
        self._chardet = None

    def _var_name(self, key):
        """根据配置键名生成对应的 UI 变量属性名 (srt_ass_{key}_var)"""
        return f"srt_ass_{key}_var"

    def _spin(self, parent, label, row, col, key, vfrom, vto, vtype=tk.IntVar, pady=None):
        """创建标签+Spinbox行，变量自动绑定到 srt_ass_{key}_var，初值取自 PRESET_DEFAULTS"""
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky=tk.W, padx=5, pady=pady)
        var = vtype(value=PRESET_DEFAULTS[key])
        setattr(self, self._var_name(key), var)
        ttk.Spinbox(parent, from_=vfrom, to=vto, textvariable=var, width=10).grid(row=row, column=col + 1, sticky=tk.W, padx=5)

    def build_ui(self, parent):
        """构建标签页 UI"""
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 左侧：文件选择器
        file_frame = ttk.LabelFrame(left_frame, text="SRT字幕文件", padding="5")
        file_frame.pack(fill=tk.BOTH, expand=True)
        self.srt_ass_file_selector = FileSelector(file_frame, supported_types='subtitle')

        # 左侧：操作按钮
        action_frame = ttk.Frame(left_frame)
        action_frame.pack(fill=tk.X, pady=10)
        self.srt_ass_convert_btn = ttk.Button(action_frame, text="开始批量转换", command=self.srt_ass_convert, width=18)
        self.srt_ass_convert_btn.pack(side=tk.RIGHT, padx=5)
        self.srt_ass_preview_btn = ttk.Button(action_frame, text="预览选中文件", command=self.srt_ass_preview, width=18)
        self.srt_ass_preview_btn.pack(side=tk.RIGHT, padx=5)
        self.srt_ass_cancel_btn = ttk.Button(action_frame, text="取消", command=self.srt_ass_cancel, width=10, state=tk.DISABLED)
        self.srt_ass_cancel_btn.pack(side=tk.RIGHT, padx=5)

        # 右侧：ASS样式设置
        style_frame = ttk.LabelFrame(right_frame, text="ASS样式设置", padding="10")
        style_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(style_frame, text="字体名称:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.srt_ass_font_name_var = tk.StringVar(value=PRESET_DEFAULTS["font_name"])
        ttk.Entry(style_frame, textvariable=self.srt_ass_font_name_var).grid(row=0, column=1, sticky="ew", padx=5)
        self._spin(style_frame, "字体大小:", 0, 2, "font_size", 8, 200)

        ttk.Label(style_frame, text="主颜色:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.srt_ass_primary_color_var = tk.StringVar(value="FFFFFF")
        primary_frame = ttk.Frame(style_frame)
        primary_frame.grid(row=1, column=1, sticky=tk.W, padx=5)
        ttk.Entry(primary_frame, textvariable=self.srt_ass_primary_color_var, width=10).pack(side=tk.LEFT)
        self.srt_ass_primary_preview = tk.Canvas(primary_frame, width=20, height=20, bg="#FFFFFF", highlightthickness=1, highlightbackground="gray")
        self.srt_ass_primary_preview.pack(side=tk.LEFT, padx=5)
        ttk.Button(primary_frame, text="选择", command=lambda: self.srt_ass_pick_color(self.srt_ass_primary_color_var, self.srt_ass_primary_preview, "FFFFFF")).pack(side=tk.RIGHT, padx=5)

        ttk.Label(style_frame, text="描边颜色:").grid(row=1, column=2, sticky=tk.W, padx=5)
        self.srt_ass_outline_color_var = tk.StringVar(value="000000")
        outline_frame = ttk.Frame(style_frame)
        outline_frame.grid(row=1, column=3, sticky=tk.W, padx=5)
        ttk.Entry(outline_frame, textvariable=self.srt_ass_outline_color_var, width=10).pack(side=tk.LEFT)
        self.srt_ass_outline_preview = tk.Canvas(outline_frame, width=20, height=20, bg="#000000", highlightthickness=1, highlightbackground="gray")
        self.srt_ass_outline_preview.pack(side=tk.LEFT, padx=5)
        ttk.Button(outline_frame, text="选择", command=lambda: self.srt_ass_pick_color(self.srt_ass_outline_color_var, self.srt_ass_outline_preview, "000000")).pack(side=tk.RIGHT, padx=5)

        self._spin(style_frame, "描边宽度:", 2, 0, "outline", 0, 10, pady=5)
        self._spin(style_frame, "阴影深度:", 2, 2, "shadow", 0, 10)

        ttk.Label(style_frame, text="对齐方式:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.srt_ass_alignment_var = tk.IntVar(value=2)
        alignment_frame = ttk.Frame(style_frame)
        alignment_frame.grid(row=3, column=1, columnspan=3, sticky=tk.W, padx=5)
        alignments = [
            ("左下", 1), ("中下", 2), ("右下", 3),
            ("左中", 4), ("中中", 5), ("右中", 6),
            ("左上", 7), ("中上", 8), ("右上", 9)
        ]
        for i, (text, val) in enumerate(alignments):
            ttk.Radiobutton(alignment_frame, text=text, variable=self.srt_ass_alignment_var, value=val).grid(row=i // 3, column=i % 3, padx=2)

        options_frame = ttk.Frame(style_frame)
        options_frame.grid(row=4, column=0, columnspan=4, sticky=tk.W, padx=5, pady=5)
        self.srt_ass_bold_var = tk.BooleanVar(value=False)
        self.srt_ass_italic_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="粗体", variable=self.srt_ass_bold_var).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(options_frame, text="斜体", variable=self.srt_ass_italic_var).pack(side=tk.LEFT, padx=5)

        # 高级设置
        adv_frame = ttk.LabelFrame(right_frame, text="高级设置", padding="5")
        adv_frame.pack(fill=tk.X, pady=5)
        self._spin(adv_frame, "缩放 X:", 0, 0, "scale_x", 10, 300)
        self._spin(adv_frame, "缩放 Y:", 0, 2, "scale_y", 10, 300)
        self._spin(adv_frame, "间距:", 1, 0, "spacing", 0, 20)
        self._spin(adv_frame, "旋转角度:", 1, 2, "angle", -360, 360, tk.DoubleVar)
        self._spin(adv_frame, "左边距:", 2, 0, "margin_l", 0, 500)
        self._spin(adv_frame, "右边距:", 2, 2, "margin_r", 0, 500)
        self._spin(adv_frame, "垂直边距:", 3, 0, "margin_v", 0, 500)

        # 预设管理
        preset_frame = ttk.Frame(right_frame)
        preset_frame.pack(fill=tk.X, pady=5)
        ttk.Button(preset_frame, text="保存预设", command=self.srt_ass_save_preset).pack(side=tk.RIGHT, padx=5)
        ttk.Button(preset_frame, text="加载预设", command=self.srt_ass_load_preset).pack(side=tk.RIGHT, padx=5)
        ttk.Button(preset_frame, text="重置默认", command=self.srt_ass_reset_default).pack(side=tk.RIGHT, padx=5)

        self._ui_built = True

    def on_tab_activated(self):
        """标签页激活时加载依赖"""
        if self._chardet is None:
            try:
                import chardet
                self._chardet = chardet
            except ImportError:
                pass  # 编码检测可选，缺失时使用 utf-8

    def srt_ass_pick_color(self, var, preview_canvas, default_color="FFFFFF"):
        hex_val = var.get().strip()
        if not hex_val or len(hex_val) < 6:
            hex_val = default_color
        clean_hex = hex_val.lstrip("#").lstrip("&H").lstrip("0")
        if len(clean_hex) < 6:
            clean_hex = clean_hex.zfill(6)
        try:
            color = colorchooser.askcolor(color="#" + clean_hex)
            if color[1]:
                hex_color = color[1].lstrip("#").upper()
                var.set(hex_color)
                preview_canvas.config(bg=color[1])
        except Exception as e:
            messagebox.showerror("颜色选择错误", f"无法选择颜色: {str(e)}")

    def srt_ass_log(self, message):
        """记录日志"""
        self.log('info', message)

    def _build_style_cache_from_ui(self):
        """从 UI 变量构建 ASS 样式字典（用于转换与预览）"""
        raw = {key: getattr(self, self._var_name(key)).get() for key in PRESET_DEFAULTS}
        raw["back_color"] = self.srt_ass_style.get("back_color", "&H14000000")
        raw["encoding"] = self.srt_ass_style.get("encoding", 1)
        return build_ass_style(raw)

    def srt_ass_convert(self):
        if self.srt_ass_processing:
            return
        files = self.srt_ass_file_selector.get_files()
        if not files:
            messagebox.showerror("错误", "请先添加SRT文件！")
            return
        self.srt_ass_processing = True
        self.host.set_processing_state(self.tab_widget, True)
        self.srt_ass_style_cache = self._build_style_cache_from_ui()
        self.host.clear_error_log(self.TAB_NAME)
        self.srt_ass_convert_btn.config(state=tk.DISABLED)
        self.srt_ass_preview_btn.config(state=tk.DISABLED)
        self.srt_ass_cancel_btn.config(state=tk.NORMAL)
        threading.Thread(target=self.srt_ass_convert_process, args=(files,), daemon=True).start()

    def srt_ass_convert_process(self, files):
        total = len(files)
        if total == 0:
            self.host.after(0, self.srt_ass_convert_complete, 0, 0, 0)
            return
        success_count = 0
        fail_count = 0
        for idx, srt_path in enumerate(files):
            if not self.srt_ass_processing:
                self.log('warning', "用户取消操作")
                break
            filename = os.path.basename(srt_path)
            if not os.path.exists(srt_path):
                self.log('warning', f"[{idx+1}/{total}] 文件不存在: {filename}")
                fail_count += 1
                continue
            self.log('info', f"[{idx+1}/{total}] 开始转换: {filename}")
            try:
                events_count, ass_content = convert_single_file(
                    srt_path, self.srt_ass_style_cache, self._chardet
                )
                ass_path = os.path.splitext(srt_path)[0] + ".ass"
                with open(ass_path, 'w', encoding='utf-8') as f:
                    f.write(ass_content)
                success_count += 1
                self.log('info', f"转换成功 [{filename}]，共 {events_count} 条字幕")
            except Exception as e:
                fail_count += 1
                self.log('error', f"转换失败 [{filename}]: {e}")
        self.host.after(0, self.srt_ass_convert_complete, total, success_count, fail_count)

    def srt_ass_convert_complete(self, total, success_count, fail_count):
        if fail_count > 0:
            self.log('warning', f"转换完成，{fail_count}/{total} 个文件失败")
        else:
            self.log('info', f"全部完成！成功转换 {total} 个文件")
        self.srt_ass_processing = False
        self.host.set_processing_state(self.tab_widget, False)
        self.srt_ass_convert_btn.config(state=tk.NORMAL)
        self.srt_ass_preview_btn.config(state=tk.NORMAL)
        self.srt_ass_cancel_btn.config(state=tk.DISABLED)
        messagebox.showinfo("完成", f"批量转换完成！\n总计: {total} 个\n成功: {success_count} 个\n失败: {fail_count} 个")

    def srt_ass_cancel(self):
        """取消SRT转ASS"""
        self.srt_ass_processing = False
        self.srt_ass_cancel_btn.config(state=tk.DISABLED)

    def stop_processing(self):
        """外部调用停止"""
        self.srt_ass_cancel()

    def is_processing(self):
        return self.srt_ass_processing

    def srt_ass_preview(self):
        files = self.srt_ass_file_selector.get_files()
        if not files:
            messagebox.showerror("错误", "请先添加SRT文件！")
            return
        srt_path = files[0]
        if not os.path.exists(srt_path):
            messagebox.showerror("错误", "选中的SRT文件不存在！")
            return
        try:
            self.srt_ass_style_cache = self._build_style_cache_from_ui()
            _events_count, preview_content = convert_single_file(
                srt_path, self.srt_ass_style_cache, self._chardet
            )
            preview_win = tk.Toplevel(self.root)
            preview_win.title(f"ASS预览 - {os.path.basename(srt_path)}")
            preview_win.geometry("800x600")
            text_widget = scrolledtext.ScrolledText(preview_win, wrap=tk.NONE, font=("Consolas", 10))
            text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            text_widget.insert(tk.END, preview_content)
            text_widget.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("错误", f"预览失败:\n{str(e)}")

    def _build_preset_dict_from_ui(self):
        """从 UI 变量构建预设字典（保存预设与配置共用）"""
        return {key: getattr(self, self._var_name(key)).get() for key in PRESET_DEFAULTS}

    def _apply_preset_dict(self, preset):
        """将预设字典应用到 UI 变量"""
        for key, default in PRESET_DEFAULTS.items():
            getattr(self, self._var_name(key)).set(preset.get(key, default))

    def srt_ass_save_preset(self):
        path = filedialog.asksaveasfilename(title="保存预设", defaultextension=".json", filetypes=[("JSON文件", "*.json")])
        if not path:
            return
        preset = self._build_preset_dict_from_ui()
        try:
            save_preset_to_file(path, preset)
            self.srt_ass_log(f"预设已保存: {path}")
            messagebox.showinfo("成功", "预设保存成功！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{str(e)}")

    def srt_ass_load_preset(self):
        path = filedialog.askopenfilename(title="加载预设", filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            preset = load_preset_from_file(path)
            self._apply_preset_dict(preset)
            self.srt_ass_primary_preview.config(bg="#" + self.srt_ass_primary_color_var.get())
            self.srt_ass_outline_preview.config(bg="#" + self.srt_ass_outline_color_var.get())
            self.srt_ass_log(f"预设已加载: {path}")
            messagebox.showinfo("成功", "预设加载成功！")
        except Exception as e:
            messagebox.showerror("错误", f"加载失败:\n{str(e)}")

    def _apply_default_style(self, log_message=None):
        """重置 UI 变量为默认值（重置默认与清除记忆共用）"""
        if not hasattr(self, 'srt_ass_font_name_var'):
            return
        for key, val in PRESET_DEFAULTS.items():
            getattr(self, self._var_name(key)).set(val)
        if hasattr(self, 'srt_ass_primary_preview'):
            self.srt_ass_primary_preview.config(bg="#FFFFFF")
        if hasattr(self, 'srt_ass_outline_preview'):
            self.srt_ass_outline_preview.config(bg="#000000")
        if log_message:
            self.srt_ass_log(log_message)

    def srt_ass_reset_default(self):
        self._apply_default_style("已重置为默认设置")

    def save_config(self, config):
        """保存配置到嵌套字典"""
        if not hasattr(self, 'srt_ass_font_name_var'):
            return
        config[self.config_key] = self._build_preset_dict_from_ui()

    def load_config(self, config):
        """从子字典加载配置"""
        if not hasattr(self, 'srt_ass_font_name_var'):
            return
        filtered = filter_config_for_apply(config)
        for key, val in filtered.items():
            getattr(self, self._var_name(key)).set(val)
        if "primary_color" in filtered and hasattr(self, 'srt_ass_primary_preview'):
            self.srt_ass_primary_preview.config(bg="#" + filtered["primary_color"])
        if "outline_color" in filtered and hasattr(self, 'srt_ass_outline_preview'):
            self.srt_ass_outline_preview.config(bg="#" + filtered["outline_color"])

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        self._apply_default_style()


# 模块导出
MODULE_CLASS = SrtToAssModule
