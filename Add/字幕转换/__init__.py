# -*- coding: utf-8 -*-
"""字幕转换模块"""

import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from common import TabModule, FileSelector


class SubtitleConvertModule(TabModule):
    """字幕转换模块（使用繁化姬 API）"""
    TAB_NAME = "字幕转换"
    TAB_ORDER = 8
    PIP_DEPENDENCIES = ['requests']
    CONFIG_KEY = "subtitle_convert"

    def __init__(self, host):
        super().__init__(host)
        self.conv_ass_processing = False
        self.conv_ass_api_available = False
        self.conv_ass_error_list = []
        self._requests = None

    def build_ui(self, parent):
        """构建标签页 UI"""
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部 - API状态
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.conv_ass_api_label = ttk.Label(top_frame, text="API连接测试中...")
        self.conv_ass_api_label.pack(side=tk.LEFT)

        ttk.Label(top_frame, text="使用繁化姬 /zhconvert.org API处理").pack(side=tk.RIGHT)

        # 左侧 - 文件选择器
        left_frame = ttk.Frame(main_frame, width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        input_frame = ttk.LabelFrame(left_frame, text="ASS字幕文件", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.conv_ass_file_selector = FileSelector(input_frame, supported_types='subtitle')

        # 右侧 - 转换设置
        right_frame = ttk.Frame(main_frame, width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(right_frame, text="转换模式").pack(fill=tk.X, pady=(0, 5))

        converter_frame = ttk.Frame(right_frame)
        converter_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.conv_ass_selected = tk.StringVar(value="China")
        converter_options = [
            ("Simplified", "简体化（纯繁→简）"),
            ("Traditional", "繁体化（纯简→繁）"),
            ("China", "中国大陆化（简＋大陆用词）"),
            ("Hongkong", "香港化（繁＋香港用词）"),
            ("Taiwan", "台湾化（繁＋台湾用词）"),
        ]

        self.conv_ass_radio_buttons = []
        for converter, description in converter_options:
            btn = ttk.Radiobutton(converter_frame, text=description,
                                 variable=self.conv_ass_selected, value=converter)
            btn.pack(anchor=tk.W, pady=2)
            self.conv_ass_radio_buttons.append(btn)

        # 进度条
        progress_frame = ttk.Frame(right_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.conv_ass_progress_var = tk.DoubleVar()
        self.conv_ass_progress = ttk.Progressbar(progress_frame, variable=self.conv_ass_progress_var, maximum=100)
        self.conv_ass_progress.pack(fill=tk.X, pady=(0, 5))

        self.conv_ass_progress_label = ttk.Label(progress_frame, text="准备就绪")
        self.conv_ass_progress_label.pack(fill=tk.X)

        # 控制按钮
        control_frame = ttk.Frame(right_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        self.conv_ass_start_btn = ttk.Button(control_frame, text="开始处理", command=self.conv_ass_start, state=tk.DISABLED)
        self.conv_ass_start_btn.pack(side=tk.RIGHT, padx=5)

        self.conv_ass_cancel_btn = ttk.Button(control_frame, text="取消处理", command=self.conv_ass_cancel, state=tk.DISABLED)
        self.conv_ass_cancel_btn.pack(side=tk.RIGHT, padx=5)

        self._ui_built = True

        # 测试API连接
        if self._requests is not None:
            threading.Thread(target=self.conv_ass_test_api, daemon=True).start()
        else:
            self.conv_ass_api_label.config(text="未安装requests库", foreground="#CC0000")

    def on_tab_activated(self):
        """标签页激活时加载依赖并测试 API"""
        if self._requests is None:
            try:
                import requests
                self._requests = requests
                self.conv_ass_api_label.config(text="API连接测试中...", foreground="black")
                threading.Thread(target=self.conv_ass_test_api, daemon=True).start()
            except ImportError:
                self.conv_ass_api_label.config(text="未安装requests库", foreground="#CC0000")

    def conv_ass_test_api(self):
        """测试API连接"""
        try:
            response = self._requests.post(
                "https://api.zhconvert.org/convert",
                json={"converter": "Traditional", "text": "测试"},
                timeout=10
            )
            if response.status_code == 200 and response.json().get("code") == 0:
                self.conv_ass_api_available = True
                self.host.after(0, lambda: self.conv_ass_api_label.config(text="API连接正常", foreground="#228B22"))
                self.host.after(0, lambda: self.conv_ass_start_btn.config(state=tk.NORMAL))
            else:
                self.host.after(0, lambda: self.conv_ass_api_label.config(text="API连接失败", foreground="#CC0000"))
        except Exception:
            self.host.after(0, lambda: self.conv_ass_api_label.config(text="API连接错误", foreground="#CC0000"))

    def conv_ass_start(self):
        """开始处理"""
        files = self.conv_ass_file_selector.get_files()
        if not files:
            messagebox.showwarning("警告", "请先添加ASS文件")
            return
        if not self.conv_ass_api_available:
            messagebox.showwarning("警告", "API连接失败")
            return

        self.conv_ass_processing = True
        self.conv_ass_converter = self.conv_ass_selected.get()
        self.conv_ass_error_list.clear()
        self.conv_ass_progress_var.set(0)
        self.conv_ass_progress_label.config(text="开始处理...")
        self.host.set_processing_state(self.tab_widget, True)

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        self.conv_ass_disable_controls()

        threading.Thread(target=self.conv_ass_process, args=(files,), daemon=True).start()

    def conv_ass_cancel(self):
        """取消处理"""
        self.conv_ass_processing = False
        self.conv_ass_progress_label.config(text="取消处理中...")
        if hasattr(self, 'conv_ass_cancel_btn'):
            self.conv_ass_cancel_btn.config(state=tk.DISABLED)

    def stop_processing(self):
        """外部调用停止"""
        self.conv_ass_cancel()

    def is_processing(self):
        return self.conv_ass_processing

    def conv_ass_process(self, files):
        """处理文件"""
        total = len(files)
        success_count = 0
        error_count = 0

        converter = self.conv_ass_converter
        self.log('info', f"开始处理，共 {total} 个文件，转换模式: {converter}")

        for i, file_path in enumerate(files):
            if not self.conv_ass_processing:
                self.log('warning', "用户取消操作")
                break

            filename = os.path.basename(file_path)
            try:
                progress = (i + 1) / total * 100
                self.host.after(0, lambda p=progress: self.conv_ass_progress_var.set(p))
                self.host.after(0, lambda f=filename, idx=i+1, t=total: self.conv_ass_progress_label.config(
                    text=f"处理中: {f} ({idx}/{t})"))

                self.log('info', f"[{i+1}/{total}] 开始转换: {filename}")

                with open(file_path, encoding="utf-8") as f:
                    text = f.read()

                converter = self.conv_ass_converter
                converted_text = self.conv_ass_convert_text(text, converter)
                self.conv_ass_save_file(file_path, converter, converted_text)
                success_count += 1
                self.log('info', f"转换成功 [{filename}]")

            except Exception as e:
                error_count += 1
                error_info = {"file": filename, "path": file_path, "error": str(e)}
                self.conv_ass_error_list.append(error_info)
                self.log('error', f"转换失败 [{filename}]: {e}")

        self.host.after(0, lambda: self.conv_ass_complete(success_count, error_count, total))

    def conv_ass_convert_text(self, text, converter):
        """调用API转换文本"""
        max_retries = 3
        retries = 0

        while retries < max_retries:
            try:
                response = self._requests.post(
                    "https://api.zhconvert.org/convert",
                    json={"converter": converter, "text": text},
                    timeout=30
                )

                if response.status_code == 429:
                    time.sleep(10)
                    retries += 1
                    continue

                response.raise_for_status()
                result = response.json()

                if result.get("code") == 0:
                    return result["data"]["text"]
                else:
                    raise Exception(f"API错误: {result.get('message', '未知错误')}")

            except self._requests.exceptions.RequestException as e:
                if retries == max_retries - 1:
                    raise Exception(f"网络错误: {str(e)}")
                retries += 1
                time.sleep(2)

        raise Exception("达到最大重试次数")

    def conv_ass_save_file(self, original_path, converter, converted_text):
        """保存转换后的文件"""
        output_dir = os.path.join(os.path.dirname(original_path), "converted")
        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.basename(original_path)
        name, ext = os.path.splitext(base_name)
        new_name = f"{name}_{converter}{ext}"
        new_path = os.path.join(output_dir, new_name)

        # SRT 文件：去除繁化姬插入的 Comment 行
        if ext.lower() == '.srt':
            lines = converted_text.splitlines()
            cleaned = []
            skip = False
            for line in lines:
                if line.strip() == '0' and not skip:
                    skip = True
                    continue
                if skip:
                    if line.strip().startswith('00:00:00,000'):
                        continue
                    elif line.strip().startswith('Processed by 繁化姬'):
                        continue
                    else:
                        skip = False
                        cleaned.append(line)
                    continue
                cleaned.append(line)
            converted_text = '\n'.join(cleaned) + '\n'

        with open(new_path, "w", encoding="utf-8") as f:
            f.write(converted_text)

    def conv_ass_complete(self, success_count, error_count, total):
        """完成处理"""
        self.conv_ass_processing = False
        self.host.set_processing_state(self.tab_widget, False)
        self.conv_ass_enable_controls()

        if success_count == total:
            self.log('info', f"全部完成！成功处理 {total} 个文件")
            messagebox.showinfo("完成", f"所有 {total} 个文件处理完成！")
            self.conv_ass_progress_label.config(text="处理完成")
        else:
            self.log('warning', f"处理完成，{error_count}/{total} 个文件失败")
            messagebox.showwarning("完成", f"处理完成：{success_count} 个成功，{error_count} 个失败")
            self.conv_ass_progress_label.config(text=f"处理完成：{success_count} 个成功，{error_count} 个失败")

    def conv_ass_disable_controls(self):
        """禁用控件"""
        self.conv_ass_start_btn.config(state=tk.DISABLED)
        self.conv_ass_cancel_btn.config(state=tk.NORMAL)
        for btn in self.conv_ass_radio_buttons:
            btn.config(state=tk.DISABLED)

    def conv_ass_enable_controls(self):
        """启用控件"""
        self.conv_ass_start_btn.config(state=tk.NORMAL if self.conv_ass_api_available else tk.DISABLED)
        self.conv_ass_cancel_btn.config(state=tk.DISABLED)
        for btn in self.conv_ass_radio_buttons:
            btn.config(state=tk.NORMAL)

    def save_config(self, config):
        """保存配置到嵌套字典"""
        data = {}
        if hasattr(self, 'conv_ass_selected'):
            data["ass_selected"] = self.conv_ass_selected.get()
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        """从子字典加载配置"""
        if hasattr(self, 'conv_ass_selected'):
            val = config.get("ass_selected")
            if val is not None:
                self.conv_ass_selected.set(val)

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        if hasattr(self, 'conv_ass_selected'):
            self.conv_ass_selected.set("China")


# 模块导出
MODULE_CLASS = SubtitleConvertModule
