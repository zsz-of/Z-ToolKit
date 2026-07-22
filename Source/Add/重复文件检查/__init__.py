# -*- coding: utf-8 -*-
"""重复文件检查模块

通过 SHA256 哈希扫描文件夹中的重复文件，支持 Python/7-Zip/混合三种哈希计算方式。
"""

import hashlib
import os
import re
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from common import TabModule, format_size


class DuplicateFileCheckerModule(TabModule):
    """重复文件检查模块"""
    TAB_NAME = "重复文件检查"
    TAB_ORDER = 20
    PIP_DEPENDENCIES = []
    CONFIG_KEY = "duplicate_file_checker"
    EXE_REQUIREMENTS = ['7z']

    SIZE_THRESHOLD = 200 * 1024 * 1024  # 200MB，混合模式下使用 7z 的分界

    def __init__(self, host):
        super().__init__(host)
        self.scanning = False
        self.stop_flag = False
        self._lock = threading.Lock()
        self.duplicate_files = {}       # {(size, hash): [file_path, ...]}
        self.processed_files = 0
        self.file_count = 0
        self.selected_folder = ""
        self.hash_method_var = None

    # ────────── UI 构建 ──────────

    def build_ui(self, parent):
        """构建标签页 UI"""
        self.hash_method_var = tk.StringVar(value="python")

        main_frame = ttk.Frame(parent, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 文件夹选择
        folder_frame = ttk.LabelFrame(main_frame, text="扫描目录", padding="5")
        folder_frame.pack(fill=tk.X, pady=(0, 5))

        self.folder_var = tk.StringVar()
        ttk.Entry(folder_frame, textvariable=self.folder_var, state='readonly').pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(folder_frame, text="浏览...", command=self._browse_folder).pack(side=tk.LEFT)

        # 哈希方法
        hash_frame = ttk.LabelFrame(main_frame, text="哈希计算方法", padding="5")
        hash_frame.pack(fill=tk.X, pady=5)

        ttk.Radiobutton(hash_frame, text="Python SHA256", variable=self.hash_method_var,
                        value="python").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(hash_frame, text="7-Zip SHA256", variable=self.hash_method_var,
                        value="7z").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(hash_frame, text="混合(200MB分界)", variable=self.hash_method_var,
                        value="hybrid").pack(side=tk.LEFT, padx=5)

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=5)

        self.start_btn = ttk.Button(btn_frame, text="开始扫描", command=self._start_scan)
        self.start_btn.pack(side=tk.RIGHT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_scan, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.RIGHT, padx=5)
        self.delete_btn = ttk.Button(btn_frame, text="删除重复文件", command=self._delete_duplicates, state=tk.DISABLED)
        self.delete_btn.pack(side=tk.RIGHT, padx=5)
        self.report_btn = ttk.Button(btn_frame, text="生成报告", command=self._generate_report, state=tk.DISABLED)
        self.report_btn.pack(side=tk.RIGHT, padx=5)

        # 进度条
        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100).pack(fill=tk.X, pady=5)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var, anchor=tk.W).pack(fill=tk.X, pady=2)
        self.detail_var = tk.StringVar(value="准备就绪")
        ttk.Label(main_frame, textvariable=self.detail_var, anchor=tk.W).pack(fill=tk.X, pady=2)

        # 结果表格
        result_frame = ttk.LabelFrame(main_frame, text="重复文件列表", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("文件路径", "文件大小", "哈希值")
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=1)
        self.result_tree.heading("文件路径", text="文件路径")
        self.result_tree.heading("文件大小", text="文件大小")
        self.result_tree.heading("哈希值", text="哈希值")
        self.result_tree.column("文件路径", width=350)
        self.result_tree.column("文件大小", width=100, anchor='e')
        self.result_tree.column("哈希值", width=200)

        scroll_y = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        scroll_x = ttk.Scrollbar(result_frame, orient=tk.HORIZONTAL, command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self.result_tree.grid(row=0, column=0, sticky='nsew')
        scroll_y.grid(row=0, column=1, sticky='ns')
        scroll_x.grid(row=1, column=0, sticky='ew')
        result_frame.grid_rowconfigure(0, weight=1)
        result_frame.grid_columnconfigure(0, weight=1)

        self._ui_built = True

    # ────────── 文件夹选择 ──────────

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="选择要扫描的文件夹")
        if folder:
            self.selected_folder = folder
            self.folder_var.set(folder)
            self.log('info', f"已选择扫描目录: {folder}")

    # ────────── 扫描流程 ──────────

    def _start_scan(self):
        if self.scanning:
            return
        if not self.selected_folder or not os.path.isdir(self.selected_folder):
            messagebox.showwarning("警告", "请先选择一个有效的文件夹")
            return

        self.scanning = True
        self.stop_flag = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.delete_btn.config(state=tk.DISABLED)
        self.report_btn.config(state=tk.DISABLED)
        self.duplicate_files = {}
        self.processed_files = 0
        self.progress_var.set(0)

        # 清空结果表格
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        self.host.clear_error_log(self.TAB_NAME)
        self.host.set_processing_state(self.tab_widget, True)

        method = self.hash_method_var.get()
        self.log('info', f"开始扫描: {self.selected_folder} | 哈希方法: {method}")
        self.status_var.set("扫描中...")
        self.detail_var.set("正在收集文件列表...")

        threading.Thread(target=self._scan_folder, daemon=True).start()

    def _stop_scan(self):
        self.stop_flag = True
        self.log('warning', "用户请求停止扫描")
        self.status_var.set("正在停止...")

    def stop_processing(self):
        """外部调用停止"""
        if self.scanning:
            self._stop_scan()

    def is_processing(self):
        return self.scanning

    def _scan_folder(self):
        try:
            # 收集所有文件
            file_list = []
            for root_dir, _, files in os.walk(self.selected_folder):
                if self.stop_flag:
                    break
                for filename in files:
                    file_list.append(os.path.join(root_dir, filename))
                    if self.stop_flag:
                        break

            with self._lock:
                self.file_count = len(file_list)

            self.after(0, lambda: self.detail_var.set(f"共找到 {len(file_list)} 个文件，开始计算哈希值..."))
            self.log('info', f"共找到 {len(file_list)} 个文件，开始计算哈希值")

            for file_path in file_list:
                if self.stop_flag:
                    break
                try:
                    file_size = os.path.getsize(file_path)
                    file_hash = self._calc_hash(file_path, file_size)
                    if not file_hash:
                        self.log('warning', f"无法计算哈希值: {file_path}")
                        continue

                    with self._lock:
                        self.processed_files += 1
                        current = self.processed_files
                        total = self.file_count

                    pct = (current / total) * 100 if total > 0 else 0
                    size_mb = file_size / 1048576
                    self.after(0, lambda p=pct, c=current, t=total, fn=os.path.basename(file_path), sm=size_mb:
                               self._update_progress(p, c, t, fn, sm))

                    key = (file_size, file_hash)
                    with self._lock:
                        if key in self.duplicate_files:
                            first = self.duplicate_files[key][0]
                            self.duplicate_files[key].append(file_path)
                            self.log('info', f"发现重复: {file_path} 与 {first}")
                        else:
                            self.duplicate_files[key] = [file_path]
                except Exception as e:
                    self.log('error', f"处理文件失败 [{file_path}]: {e}")

            if self.stop_flag:
                self.log('warning', "扫描已停止，结果已清除")
                with self._lock:
                    self.duplicate_files = {}
                self.after(0, lambda: self._scan_done(False, 0))
            else:
                dup_count = sum(1 for v in self.duplicate_files.values() if len(v) > 1)
                self.after(0, lambda: self._scan_done(True, dup_count))
        except Exception as e:
            self.log('error', f"扫描过程发生错误: {e}")
            self.after(0, lambda: self._scan_done(False, 0))

    def _update_progress(self, pct, current, total, filename, size_mb):
        self.progress_var.set(pct)
        self.status_var.set(f"处理中: {current}/{total}")
        self.detail_var.set(f"正在处理: {filename} ({size_mb:.1f}MB)")

    def _scan_done(self, success, dup_count):
        self.scanning = False
        self.host.set_processing_state(self.tab_widget, False)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        if success:
            self.progress_var.set(100)
            if dup_count > 0:
                self.delete_btn.config(state=tk.NORMAL)
                self.report_btn.config(state=tk.NORMAL)
                self._display_results()
                self.status_var.set(f"扫描完成: 找到 {dup_count} 组重复文件")
                self.detail_var.set(f"共 {dup_count} 组重复文件")
                self.log('info', f"扫描完成: 找到 {dup_count} 组重复文件")
            else:
                self.status_var.set("扫描完成: 没有重复文件")
                self.detail_var.set("没有重复文件")
                self.log('info', "扫描完成: 没有找到重复文件")
        else:
            self.status_var.set("已停止")
            self.detail_var.set("扫描已停止")

    def _display_results(self):
        """将重复文件显示到结果表格"""
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        for (size, h), paths in self.duplicate_files.items():
            if len(paths) <= 1:
                continue
            size_str = format_size(size)
            for p in paths:
                self.result_tree.insert("", tk.END, values=(p, size_str, h))

    # ────────── 哈希计算 ──────────

    def _calc_hash(self, file_path, file_size=None):
        method = self.hash_method_var.get()
        seven_z_path = self.get_exe_path('7z')
        if method == "7z" and seven_z_path:
            return self._hash_7z(file_path, seven_z_path)
        elif method == "hybrid" and seven_z_path:
            if file_size is None:
                file_size = os.path.getsize(file_path)
            return self._hash_7z(file_path, seven_z_path) if file_size >= self.SIZE_THRESHOLD else self._hash_python(file_path)
        return self._hash_python(file_path)

    @staticmethod
    def _hash_python(file_path, chunk_size=8192):
        h = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    @staticmethod
    def _hash_7z(file_path, seven_z_path):
        try:
            result = subprocess.run(
                [seven_z_path, 'h', '-scrcSHA256', file_path],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in result.stdout.split('\n'):
                parts = line.strip().split()
                if parts and len(parts[0]) == 64 and all(c in '0123456789abcdefABCDEF' for c in parts[0]):
                    return parts[0].lower()
            match = re.search(r'([0-9a-fA-F]{64})', result.stdout)
            return match.group(1).lower() if match else None
        except Exception:
            return None

    # ────────── 报告与删除 ──────────

    def _generate_report(self):
        if not self.duplicate_files:
            messagebox.showinfo("提示", "没有重复文件可生成报告")
            return

        output_file = os.path.join(self.selected_folder, "list.txt")
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("重复文件列表:\n" + "=" * 50 + "\n\n")
                for (size, h), paths in self.duplicate_files.items():
                    if len(paths) > 1:
                        f.write(f"文件大小: {size} 字节\n哈希值: {h}\n文件数量: {len(paths)}\n文件路径:\n")
                        for p in paths:
                            f.write(f"  - {p}\n")
                        f.write("\n" + "-" * 50 + "\n\n")
            self.log('info', f"报告已保存到: {output_file}")
            messagebox.showinfo("成功", f"报告已保存到:\n{output_file}")
        except OSError as e:
            self.log('error', f"生成报告失败: {e}")
            messagebox.showerror("错误", f"生成报告失败: {e}")

    def _delete_duplicates(self):
        if not self.duplicate_files:
            messagebox.showinfo("提示", "没有重复文件可删除")
            return

        if not messagebox.askyesno("确认", "确定要删除重复文件吗？\n每组保留文件名最短的一份，其余删除！"):
            return

        self.log('info', "开始删除重复文件")
        self.delete_btn.config(state=tk.DISABLED)
        deleted = 0
        errors = 0

        for paths in self.duplicate_files.values():
            if len(paths) <= 1:
                continue
            shortest = min(paths, key=lambda x: len(os.path.basename(x)))
            for p in paths:
                if p == shortest:
                    continue
                try:
                    os.remove(p)
                    deleted += 1
                    self.log('info', f"已删除: {p}")
                except Exception as e:
                    errors += 1
                    self.log('error', f"删除失败 [{p}]: {e}")

        self.log('info', f"删除完成: 成功 {deleted}, 失败 {errors}")
        messagebox.showinfo("完成", f"删除完成!\n成功: {deleted}\n失败: {errors}")

        # 刷新结果表格
        self._display_results()

    # ────────── 配置持久化 ──────────

    def save_config(self, config):
        data = {}
        if hasattr(self, 'hash_method_var'):
            data["hash_method"] = self.hash_method_var.get()
        if hasattr(self, 'folder_var'):
            data["last_folder"] = self.folder_var.get()
        if data:
            config[self.config_key] = data

    def load_config(self, config):
        if hasattr(self, 'hash_method_var'):
            method = config.get("hash_method")
            if method in ("python", "7z", "hybrid"):
                self.hash_method_var.set(method)
        if hasattr(self, 'folder_var'):
            folder = config.get("last_folder", "")
            if folder and os.path.isdir(folder):
                self.selected_folder = folder
                self.folder_var.set(folder)

    def clear_memory(self):
        if hasattr(self, 'hash_method_var'):
            self.hash_method_var.set("python")
        if hasattr(self, 'folder_var'):
            self.selected_folder = ""
            self.folder_var.set("")


# 模块导出
MODULE_CLASS = DuplicateFileCheckerModule
