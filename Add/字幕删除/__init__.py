# -*- coding: utf-8 -*-
"""字幕删除模块"""

import os
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from common import TabModule, FileSelector, safe_remove


class SubtitleRemoveModule(TabModule):
    """字幕删除模块"""
    TAB_NAME = "字幕删除"
    TAB_ORDER = 7
    PIP_DEPENDENCIES = []
    CONFIG_KEY = "subtitle_remove"
    EXE_REQUIREMENTS = ['mkvmerge']

    def __init__(self, host):
        super().__init__(host)
        self.remove_failed_files = []
        self.remove_processing = False
        self.remove_cancel_flag = False

    def build_ui(self, parent):
        """构建标签页 UI"""
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 统一文件选择器
        input_frame = ttk.LabelFrame(main_frame, text="视频文件(MKV)", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.remove_file_selector = FileSelector(input_frame, supported_types='video')

        # 选项框架
        options_frame = ttk.Frame(main_frame)
        options_frame.pack(fill=tk.X, pady=(0, 10))

        self.remove_delete_attachments_var = tk.BooleanVar(value=False)
        self.remove_delete_attachments_cb = ttk.Checkbutton(
            options_frame,
            text="同时删除附件（字体文件等）",
            variable=self.remove_delete_attachments_var
        )
        self.remove_delete_attachments_cb.pack(side=tk.LEFT)

        # 按钮框架
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.remove_start_btn = ttk.Button(btn_frame, text="开始处理", command=self.remove_start)
        self.remove_start_btn.pack(side=tk.RIGHT, padx=5)

        self.remove_cancel_btn = ttk.Button(btn_frame, text="取消处理", command=self.remove_cancel, state=tk.DISABLED)
        self.remove_cancel_btn.pack(side=tk.RIGHT, padx=5)

        # 进度
        progress_frame = ttk.LabelFrame(main_frame, text="处理进度", padding="5")
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.remove_current_label = ttk.Label(progress_frame, text="当前处理文件: 无")
        self.remove_current_label.pack(anchor=tk.W, pady=(0, 5))

        ttk.Label(progress_frame, text="总进度:").pack(anchor=tk.W)
        self.remove_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode='determinate')
        self.remove_progress.pack(fill=tk.X)

        self._ui_built = True

    def remove_start(self):
        """开始处理"""
        if self.remove_processing:
            return
        files = self.remove_file_selector.get_files()
        if not files:
            messagebox.showwarning("警告", "请先添加要处理的MKV文件!")
            return

        mkvmerge_path = self.get_exe_path('mkvmerge')
        if not mkvmerge_path:
            messagebox.showerror("错误",
                "未配置 mkvmerge 路径。\n\n请到「外部工具」标签页配置 MKVToolNix 后再使用本功能。")
            return

        self.remove_processing = True
        self.remove_cancel_flag = False
        self.remove_generation = getattr(self, 'remove_generation', 0) + 1
        self.remove_task_gen = self.remove_generation
        self.remove_failed_files = []
        self.remove_delete_attachments = self.remove_delete_attachments_var.get()
        self.host.set_processing_state(self.tab_widget, True)

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        self.remove_start_btn.config(state=tk.DISABLED)
        self.remove_cancel_btn.config(state=tk.NORMAL)
        self.remove_progress['value'] = 0

        threading.Thread(target=self.remove_process, args=(files,), daemon=True).start()

    def remove_cancel(self):
        """取消处理"""
        self.remove_cancel_flag = True
        self.remove_cancel_btn.config(state=tk.DISABLED)

    def stop_processing(self):
        """外部调用停止"""
        self.remove_cancel()

    def is_processing(self):
        return self.remove_processing

    def remove_process(self, files):
        """处理文件"""
        total = len(files)
        success_count = 0

        self.log('info', f"开始处理，共 {total} 个文件")

        for i, file_path in enumerate(files):
            if self.remove_cancel_flag:
                self.log('warning', "用户取消操作")
                break

            filename = os.path.basename(file_path)
            self.host.after(0, lambda p=filename: self.remove_current_label.config(
                text=f"当前处理文件: {p}"))
            self.host.after(0, lambda p=(i/total)*100: self.remove_progress.config(value=p))

            self.log('info', f"[{i+1}/{total}] 开始处理: {filename}")

            success, error = self.remove_subtitle_tracks(file_path)
            if success:
                success_count += 1
                self.log('info', f"处理成功 [{filename}]，{error}")
            else:
                self.remove_failed_files.append((file_path, error))
                self.log('error', f"处理失败 [{filename}]: {error}")

        self.host.after(0, lambda: self.remove_complete(success_count, total))

    def remove_subtitle_tracks(self, mkv_file):
        """删除字幕轨道和可选的附件"""
        try:
            mkvmerge_path = self.get_exe_path('mkvmerge')
            if not mkvmerge_path:
                return False, "未配置 mkvmerge 路径"

            base_name = os.path.splitext(mkv_file)[0]
            output_file = f"{base_name}_no_subtitles.mkv"

            delete_attachments = self.remove_delete_attachments

            cmd = [mkvmerge_path, "-o", output_file, "--no-subtitles"]
            if delete_attachments:
                cmd.append("--no-attachments")
            cmd.append(mkv_file)

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                _, stderr = proc.communicate(timeout=300)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                safe_remove(output_file, self.host, self.TAB_NAME)
                return False, "处理超时"

            if proc.returncode not in [0, 1]:
                safe_remove(output_file, self.host, self.TAB_NAME)
                return False, f"处理失败: {stderr.strip()}"

            try:
                backup_file = mkv_file + ".backup"
                shutil.move(mkv_file, backup_file)
                shutil.move(output_file, mkv_file)
                safe_remove(backup_file, self.host, self.TAB_NAME)
                action = "已删除字幕轨道"
                if delete_attachments:
                    action += "和附件"
                return True, action
            except Exception as e:
                # 恢复原始文件，每步单独保护
                if os.path.exists(backup_file) and not os.path.exists(mkv_file):
                    try:
                        shutil.move(backup_file, mkv_file)
                    except Exception:
                        self.log('critical', f"恢复备份文件失败: {backup_file} -> {mkv_file}")
                if os.path.exists(output_file) and not os.path.exists(mkv_file):
                    try:
                        shutil.move(output_file, mkv_file)
                    except Exception:
                        self.log('critical', f"恢复输出文件失败: {output_file} -> {mkv_file}")
                return False, f"替换文件失败: {e}"

        except Exception as e:
            return False, str(e)

    def remove_complete(self, success_count, total):
        """完成处理"""
        if getattr(self, 'remove_task_gen', 0) != getattr(self, 'remove_generation', 0):
            return
        self.remove_processing = False
        self.host.set_processing_state(self.tab_widget, False)
        self.remove_start_btn.config(state=tk.NORMAL)
        self.remove_cancel_btn.config(state=tk.DISABLED)
        self.remove_progress['value'] = 100 if not self.remove_cancel_flag else self.remove_progress['value']

        failed = total - success_count

        if self.remove_cancel_flag:
            self.log('warning', f"用户取消操作，已处理 {success_count}/{total} 个文件")
            messagebox.showinfo("处理已取消", f"处理已取消。成功处理 {success_count}/{total} 个文件。")
        elif success_count == total:
            self.log('info', f"全部完成！成功处理 {total} 个文件")
            messagebox.showinfo("处理完成", f"所有文件处理成功！共处理 {success_count} 个文件。")
        else:
            self.log('warning', f"处理完成，{failed}/{total} 个文件失败")
            messagebox.showwarning("处理完成", f"处理完成。成功 {success_count} 个，失败 {failed} 个。")

    def save_config(self, config):
        """保存配置到嵌套字典"""
        data = {}
        if hasattr(self, 'remove_delete_attachments_var'):
            data["delete_attachments"] = self.remove_delete_attachments_var.get()
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        """从子字典加载配置"""
        if hasattr(self, 'remove_delete_attachments_var'):
            val = config.get("delete_attachments")
            if val is not None:
                self.remove_delete_attachments_var.set(val)

    def clear_memory(self):
        """清除记忆，重置为默认值"""
        if hasattr(self, 'remove_delete_attachments_var'):
            self.remove_delete_attachments_var.set(False)


# 模块导出
MODULE_CLASS = SubtitleRemoveModule
