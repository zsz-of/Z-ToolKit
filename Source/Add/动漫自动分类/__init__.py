# -*- coding: utf-8 -*-
"""动漫自动分类模块"""

import os
import re
import shutil
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from common import TabModule, FileSelector


class AnimeClassifierModule(TabModule):
    """动漫自动分类模块"""
    TAB_NAME = "动漫自动分类"
    TAB_ORDER = 2
    PIP_DEPENDENCIES = []

    def __init__(self, host):
        super().__init__(host)
        self.anime_processing = False
        self.anime_last_operation = None

    def build_ui(self, parent):
        """构建标签页 UI"""
        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 统一文件选择器
        input_frame = ttk.LabelFrame(main_frame, text="视频文件", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.anime_file_selector = FileSelector(input_frame, supported_types='video')

        # 按钮（统一 side=RIGHT, padx=5）
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 20))

        self.anime_classify_btn = ttk.Button(btn_frame, text="开始分类", command=self.anime_start)
        self.anime_classify_btn.pack(side=tk.RIGHT, padx=5)

        self.anime_undo_btn = ttk.Button(btn_frame, text="撤销上一次操作", command=self.anime_undo, state="disabled")
        self.anime_undo_btn.pack(side=tk.RIGHT, padx=5)

        # 进度条
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.anime_progress_label = ttk.Label(progress_frame, text="已处理: 0 / 0")
        self.anime_progress_label.pack(anchor=tk.W)
        self.anime_progress = ttk.Progressbar(progress_frame, orient=tk.HORIZONTAL, mode="determinate")
        self.anime_progress.pack(fill=tk.X, pady=(5, 0))

        self._ui_built = True

    def anime_start(self):
        """开始分类"""
        files = self.anime_file_selector.get_files()
        if not files:
            messagebox.showwarning("警告", "请先添加视频文件")
            return
        if self.anime_processing:
            messagebox.showinfo("提示", "正在处理中，请等待完成")
            return

        self.anime_progress["value"] = 0
        self.anime_progress_label.config(text="已处理: 0 / 0")

        self.anime_processing = True
        self.host.set_processing_state(self.tab_widget, True)
        self.anime_classify_btn.config(state="disabled")
        self.anime_undo_btn.config(state="disabled")

        # 清空错误日志并设置标题
        self.host.clear_error_log(self.TAB_NAME)

        threading.Thread(target=self.anime_classify, args=(files,), daemon=True).start()

    def stop_processing(self):
        """停止分类"""
        self.anime_processing = False

    def is_processing(self):
        return self.anime_processing

    def anime_set_progress(self, value, processed=None, total=None):
        """设置进度条与文字提示（线程安全）"""
        def update():
            self.anime_progress.config(value=value)
            if processed is not None and total is not None:
                self.anime_progress_label.config(text=f"已处理: {processed} / {total}")
        self.host.after(0, update)

    def anime_classify(self, video_files):
        """执行分类"""
        try:
            self.log('info', f"开始处理 {len(video_files)} 个文件")

            operation_history = []

            if not video_files:
                self.log('warning', "未找到视频文件")
                self.host.after(0, self.anime_finish)
                return

            total = len(video_files)
            self.log('info', f"找到 {total} 个视频文件")

            processed = 0
            self.anime_set_progress(0, 0, total)  # 立即更新总数

            for i, file_path in enumerate(video_files):
                if not self.anime_processing:
                    break
                file = os.path.basename(file_path)

                self.log('info', f"[{i+1}/{total}] 处理文件: {file}")

                # 跳过电影文件
                if not re.search(r'第\d+话', file) and not re.search(r'\b(OVA|OAD)\b', file):
                    self.log('info', f"跳过电影文件: {file}")
                    processed += 1
                    self.anime_set_progress((processed / total) * 100, processed, total)
                    continue

                # 提取动漫名
                ova_match = re.match(r'(.+?)\s+(OVA|OAD)', file)
                episode_match = re.match(r'(.+?)\s+第\d+话', file)

                if ova_match:
                    anime_name = ova_match.group(1)
                elif episode_match:
                    anime_name = episode_match.group(1)
                else:
                    self.log('warning', f"无法解析文件名: {file}")
                    processed += 1
                    self.anime_set_progress((processed / total) * 100, processed, total)
                    continue

                # 检查季度信息
                season_match = re.search(r'(.*?)\s*第?(\d+)季', anime_name)
                if season_match:
                    base_name = season_match.group(1)
                    season = season_match.group(2)
                    folder_name = f"{base_name} 第{season}季"
                else:
                    folder_name = f"{anime_name}"

                source = os.path.dirname(file_path)
                target_folder = os.path.join(source, folder_name)
                folder_existed = os.path.exists(target_folder)
                if not folder_existed:
                    os.makedirs(target_folder)
                    self.log('info', f"创建文件夹: {folder_name}")

                target_path = os.path.join(target_folder, file)
                if os.path.exists(target_path):
                    self.log('info', f"文件已存在，跳过: {file}")
                else:
                    operation_history.append({
                        'source': file_path,
                        'destination': target_path,
                        'folder_created': not folder_existed
                    })
                    shutil.move(file_path, target_path)
                    self.log('info', f"已移动 [{file}] -> [{folder_name}]")

                processed += 1
                self.anime_set_progress((processed / total) * 100, processed, total)

            self.anime_last_operation = operation_history
            self.host.after(0, lambda: self.anime_undo_btn.config(state="normal"))
            self.log('info', f"全部完成！成功处理 {total} 个文件")

        except Exception as e:
            self.log('error', f"发生错误: {str(e)}")
        finally:
            self.host.after(0, self.anime_finish)

    def anime_undo(self):
        """撤销操作"""
        if not self.anime_last_operation:
            messagebox.showinfo("提示", "没有可撤销的操作")
            return

        try:
            self.log('info', "开始撤销上一次操作...")

            for op in reversed(self.anime_last_operation):
                if os.path.exists(op['destination']):
                    shutil.move(op['destination'], op['source'])
                    self.log('info', f"已恢复: {os.path.basename(op['destination'])}")

            # 删除空文件夹
            folders = set(os.path.dirname(op['destination']) for op in self.anime_last_operation)
            for folder in folders:
                try:
                    if os.path.exists(folder) and not os.listdir(folder):
                        os.rmdir(folder)
                        self.log('info', f"已删除空文件夹: {os.path.basename(folder)}")
                except Exception:
                    pass

            self.anime_last_operation = None
            self.anime_undo_btn.config(state="disabled")
            self.log('info', "撤销完成！")

        except Exception as e:
            self.log('error', f"撤销时发生错误: {str(e)}")

    def anime_finish(self):
        """完成处理"""
        self.anime_processing = False
        self.host.set_processing_state(self.tab_widget, False)
        self.anime_classify_btn.config(state="normal")
        self.anime_undo_btn.config(state="normal")
        self.anime_progress["value"] = 100


# 模块导出
MODULE_CLASS = AnimeClassifierModule
