# -*- coding: utf-8 -*-
"""
M3U8 转 MKV 模块
支持文件队列、文件夹扫描模式，显示处理进度条
FFmpeg 路径由主程序外部工具管理统一提供
"""

import os
import re
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from common import TabModule


# ========== 视频元信息探测 ==========

def get_video_rotation(input_file: str, ffmpeg_path: str, ffprobe_path: str | None) -> int | None:
    """获取视频旋转角度

    Args:
        input_file: 输入视频文件
        ffmpeg_path: ffmpeg 可执行文件路径
        ffprobe_path: ffprobe 可执行文件路径（由主程序外部工具管理统一提供）
    """
    if not ffprobe_path:
        return None

    try:
        # 方法1: stream_tags=rotate
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream_tags=rotate",
             "-of", "default=noprint_wrappers=1:nokey=1", input_file],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        val = result.stdout.strip()
        if val and val.lower() not in ("n/a", "", "none"):
            return int(val)

        # 方法2: side_data=rotation
        result2 = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "side_data=rotation",
             "-of", "default=noprint_wrappers=1:nokey=1", input_file],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        for line in result2.stdout.strip().split("\n"):
            line = line.strip()
            if line and line.lower() not in ("n/a", "", "none"):
                try:
                    rot = int(float(line))
                    if rot != 0:
                        return rot
                except ValueError:
                    pass

        # 方法3: ffmpeg -i stderr
        result3 = subprocess.run(
            [ffmpeg_path, "-i", input_file],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
        rot_match = re.search(r"rotate\s*[:=]\s*(-?\d+)", result3.stderr, re.IGNORECASE)
        if rot_match:
            return int(rot_match.group(1))
    except Exception:
        pass
    return None


def get_video_duration(input_file: str, ffmpeg_path: str, ffprobe_path: str | None) -> float | None:
    """获取视频时长（优先 ffprobe，回退 ffmpeg）

    Args:
        input_file: 输入视频文件
        ffmpeg_path: ffmpeg 可执行文件路径
        ffprobe_path: ffprobe 可执行文件路径（由主程序外部工具管理统一提供）
    """
    if ffprobe_path:
        try:
            result = subprocess.run(
                [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", input_file],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            val = result.stdout.strip()
            if val and val.lower() not in ("n/a", "", "none"):
                return float(val)
        except Exception:
            pass

    # 回退方案：使用 ffmpeg 解析 stderr
    try:
        result = subprocess.run(
            [ffmpeg_path, "-i", input_file],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", result.stderr)
        if match:
            return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    except Exception:
        pass
    return None


def fmt_time(seconds: float) -> str:
    """将秒数格式化为可读时长字符串"""
    if seconds <= 0:
        return "00:00"
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


# ========== ffmpeg 命令构建 ==========

def build_convert_command(ffmpeg_path: str, input_path: str, output_path: str,
                          rotation: int | None) -> tuple[list[str], str | None, str]:
    """构建 ffmpeg 转换命令（含旋转修正）

    Args:
        ffmpeg_path: ffmpeg 可执行文件路径
        input_path: 输入文件路径
        output_path: 输出文件路径
        rotation: 视频旋转角度（可为 None）

    Returns:
        (cmd, log_message, log_level):
            cmd: ffmpeg 命令参数列表
            log_message: 旋转处理说明（None 表示无需额外日志）
            log_level: 日志级别 ('info' / 'warning')
    """
    if rotation and rotation % 360 != 0:
        norm_rot = rotation % 360
        if norm_rot < 0:
            norm_rot += 360
        vf_map = {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}
        vf = vf_map.get(norm_rot)
        if vf:
            msg = f"检测到旋转 {norm_rot}°，应用滤镜: {vf}"
            cmd = [ffmpeg_path, "-y", "-i", input_path, "-vf", vf,
                   "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                   "-c:a", "copy", "-metadata:s:v:0", "rotate=0", output_path]
            return cmd, msg, 'info'
        msg = f"检测到非标准旋转角度 {norm_rot}°，仅复制流"
        cmd = [ffmpeg_path, "-y", "-i", input_path, "-c", "copy",
               "-metadata:s:v:0", "rotate=0", output_path]
        return cmd, msg, 'warning'

    cmd = [ffmpeg_path, "-y", "-i", input_path, "-c", "copy", output_path]
    return cmd, None, 'info'


# ========== 进度解析 ==========

def parse_progress_time(line: str) -> float | None:
    """从 ffmpeg 输出行解析已处理时长（秒）

    Args:
        line: ffmpeg stdout 的一行文本

    Returns:
        已处理时长（秒，float），无法解析时返回 None
    """
    match = re.search(r"time=\s*(\d+):(\d+):(\d+\.?\d*)", line)
    if not match:
        return None
    return (int(match.group(1)) * 3600 +
            int(match.group(2)) * 60 +
            float(match.group(3)))


# ========== 文件扫描与冲突检测 ==========

def list_m3u8_files(folder: str, recursive: bool) -> list[tuple[str, str, str]]:
    """列出文件夹中的 M3U8 文件

    Args:
        folder: 文件夹路径
        recursive: 是否递归扫描子文件夹

    Returns:
        [(abs_path, file_name, parent_dir_str), ...] 按文件名排序
    """
    folder_path = Path(folder)
    files = folder_path.rglob("*.m3u8") if recursive else folder_path.glob("*.m3u8")
    result = []
    for file_path in sorted(files):
        if file_path.is_file():
            result.append((str(file_path.resolve()), file_path.name, str(file_path.parent)))
    return result


def get_output_conflicts(file_list: list[str]) -> list[str]:
    """检查输出 MKV 文件是否已存在，返回冲突文件名列表"""
    return [Path(p).with_suffix(".mkv").name for p in file_list
            if Path(p).with_suffix(".mkv").exists()]


def _safe_remove_output(output_path: str) -> None:
    """删除输出文件（忽略错误）"""
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except OSError:
            pass


# ========== 单文件转换执行 ==========

def convert_single_m3u8(input_path: str, output_path: str, display_name: str,
                        ffmpeg_path: str, ffprobe_path: str | None,
                        stop_check, log, on_progress, on_status, on_final) -> bool:
    """转换单个 M3U8 文件为 MKV（含旋转修正与进度上报）

    纯业务逻辑，通过回调与 UI 交互：
        stop_check: () -> bool，返回 True 表示请求停止
        log: (level, msg) -> None
        on_progress: (current_time, duration) -> None，duration 可为 None
        on_status: (text, color) -> None
        on_final: (duration) -> None，成功完成时调用以填充 100% 进度

    Returns:
        True 表示转换成功
    """
    duration = get_video_duration(input_path, ffmpeg_path, ffprobe_path)
    rotation = get_video_rotation(input_path, ffmpeg_path, ffprobe_path)

    if duration is not None:
        log('info', f"视频时长: {fmt_time(duration)} | 旋转: {rotation if rotation else '无'} | 文件: {display_name}")
    else:
        log('warning', f"无法获取视频时长，进度将无法显示百分比 | 文件: {display_name}")

    cmd, filter_msg, filter_level = build_convert_command(
        ffmpeg_path, input_path, output_path, rotation)
    if filter_msg:
        log(filter_level, f"{filter_msg} | 文件: {display_name}")

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, encoding="utf-8", errors="ignore",
            creationflags=subprocess.CREATE_NO_WINDOW)

        while True:
            if stop_check():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                _safe_remove_output(output_path)
                return False

            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break

            new_time = parse_progress_time(line)
            if new_time is not None:
                on_progress(new_time, duration)
            time.sleep(0.03)

        process.wait()
        if process.returncode != 0:
            _safe_remove_output(output_path)
            on_status(f"转换失败: {display_name}", "red")
            log('error', f"FFmpeg 返回码 {process.returncode}，转换失败: {display_name}")
            return False

        on_final(duration)
        return True
    except Exception as e:
        on_status(f"错误: {e}", "red")
        log('error', f"处理异常 [{display_name}]: {e}")
        _safe_remove_output(output_path)
        return False


# ========== 队列调度 ==========

def process_conversion_queue(file_list, ffmpeg_path, ffprobe_path, stop_check, log,
                             on_total, on_progress, on_status, on_final, on_done):
    """处理 M3U8 转换队列（逐文件转换并上报进度）

    逐个调用 convert_single_m3u8 转换，所有 UI 交互通过回调完成：
        stop_check: () -> bool
        log: (level, msg) -> None
        on_total: (idx, total, filename) -> None
        on_progress: (current_time, duration) -> None（透传给单文件转换）
        on_status: (text, color) -> None
        on_final: (duration) -> None（透传给单文件转换，填充 100%）
        on_done: (success, fail, stopped) -> None

    Returns:
        (success, fail, stopped)
    """
    total = len(file_list)
    success = fail = 0
    for i, m3u8_path in enumerate(file_list):
        if stop_check():
            break
        output_path = str(Path(m3u8_path).with_suffix(".mkv"))
        filename = Path(m3u8_path).name
        on_total(i, total, filename)
        log('info', f"[{i+1}/{total}] 开始处理: {filename}")
        if convert_single_m3u8(m3u8_path, output_path, filename,
                               ffmpeg_path, ffprobe_path, stop_check, log,
                               on_progress, on_status, on_final):
            success += 1
            log('info', f"[{i+1}/{total}] 转换成功: {filename} -> {Path(output_path).name}")
        elif not stop_check():
            fail += 1
    stopped = stop_check()
    on_done(success, fail, stopped)
    return success, fail, stopped


# ========== 主模块 ==========

class M3U8MergerModule(TabModule):
    """M3U8 转 MKV 模块"""
    TAB_NAME = "M3U8合并"
    TAB_ORDER = 12
    CONFIG_KEY = "m3u8_merger"
    PIP_DEPENDENCIES = []
    EXE_REQUIREMENTS = ['ffmpeg', 'ffprobe']

    def __init__(self, host):
        super().__init__(host)
        self.file_list: list[str] = []
        self.is_processing_flag = False
        self.stop_flag = False
        self.mode_var = tk.StringVar(value="folder")
        self.recursive_var = tk.BooleanVar(value=True)
        self.output_folder = ""

    @property
    def ffmpeg_path(self) -> str | None:
        """FFmpeg 路径（从主程序外部工具管理获取）"""
        return self.get_exe_path('ffmpeg')

    def build_ui(self, parent):
        """构建标签页 UI"""
        # 文件选择
        file_frame = ttk.LabelFrame(parent, text="文件选择", padding=5)
        file_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        mode_frame = ttk.Frame(file_frame)
        mode_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Radiobutton(mode_frame, text="文件夹扫描", variable=self.mode_var,
                        value="folder", command=self._switch_mode).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="手动选择文件", variable=self.mode_var,
                        value="filelist", command=self._switch_mode).pack(side=tk.LEFT, padx=10)

        self.content_frame = ttk.Frame(file_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)
        self._switch_mode()

        # 进度
        progress_frame = ttk.LabelFrame(parent, text="处理进度", padding=5)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)

        total_frame = ttk.Frame(progress_frame)
        total_frame.pack(fill=tk.X, pady=2)
        ttk.Label(total_frame, text="总体:").pack(side=tk.LEFT)
        self.total_progress = ttk.Progressbar(total_frame, mode="determinate", length=400)
        self.total_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.total_label = ttk.Label(total_frame, text="0 / 0", width=12)
        self.total_label.pack(side=tk.RIGHT)

        current_frame = ttk.Frame(progress_frame)
        current_frame.pack(fill=tk.X, pady=2)
        ttk.Label(current_frame, text="当前:").pack(side=tk.LEFT)
        self.current_progress = ttk.Progressbar(current_frame, mode="determinate", length=400)
        self.current_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.current_label = ttk.Label(current_frame, text="0.0%", width=12)
        self.current_label.pack(side=tk.RIGHT)

        self.status_label = ttk.Label(progress_frame, text="就绪", foreground="gray")  # 说明色：gray
        self.status_label.pack(anchor=tk.W, pady=2)

        # 操作按钮
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        self.start_btn = ttk.Button(btn_frame, text="开始转换", command=self._start_conversion)
        self.start_btn.pack(side=tk.RIGHT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop_conversion, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.RIGHT, padx=5)

        self._ui_built = True

    # ────────── UI 模式切换 ──────────

    def _switch_mode(self):
        self.file_list.clear()
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        if self.mode_var.get() == "folder":
            self._create_folder_mode()
        else:
            self._create_filelist_mode()

    def _create_m3u8_treeview(self, parent):
        """创建 M3U8 文件列表 Treeview（带滚动条）"""
        columns = ("filename", "path")
        tree = ttk.Treeview(parent, columns=columns, show="headings",
                            selectmode="extended", height=1)
        tree.heading("filename", text="文件名")
        tree.heading("path", text="路径")
        tree.column("filename", width=200)
        tree.column("path", width=400)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    def _create_folder_mode(self):
        path_frame = ttk.Frame(self.content_frame)
        path_frame.pack(fill=tk.X, pady=5)
        self.folder_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self.folder_var, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(path_frame, text="浏览...", command=self._browse_folder).pack(side=tk.RIGHT)

        ttk.Checkbutton(self.content_frame, text="扫描子文件夹",
                        variable=self.recursive_var).pack(anchor=tk.W, pady=2)

        results_frame = ttk.LabelFrame(self.content_frame, text="扫描结果", padding=5)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.folder_tree = self._create_m3u8_treeview(results_frame)

        # 计数标签（不再需要"扫描文件夹"按钮）
        self.folder_count_label = ttk.Label(self.content_frame, text="找到: 0 个文件")
        self.folder_count_label.pack(anchor=tk.W, pady=5)

    def _create_filelist_mode(self):
        list_frame = ttk.LabelFrame(self.content_frame, text="已选文件", padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.filelist_tree = self._create_m3u8_treeview(list_frame)

        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加文件", command=self._add_files).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="移除选中", command=self._remove_selected).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self._clear_filelist).pack(side=tk.RIGHT, padx=5)

        self.list_count_label = ttk.Label(self.content_frame, text="已添加: 0 个文件")
        self.list_count_label.pack(anchor=tk.W, pady=2)

    # ────────── 文件夹模式 ──────────

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="选择包含 M3U8 文件的文件夹")
        if folder:
            self.folder_var.set(folder)
            self._scan_folder()

    def _scan_folder(self):
        folder = self.folder_var.get()
        if not folder or not Path(folder).is_dir():
            return
        for item in self.folder_tree.get_children():
            self.folder_tree.delete(item)
        self.file_list.clear()
        count = 0
        for abs_path, name, parent in list_m3u8_files(folder, self.recursive_var.get()):
            self.file_list.append(abs_path)
            self.folder_tree.insert("", tk.END, values=(name, parent))
            count += 1
        self.folder_count_label.config(text=f"找到: {count} 个文件")
        self.log('info', f"扫描文件夹完成: {folder} | 递归: {'是' if self.recursive_var.get() else '否'} | 找到 {count} 个 M3U8 文件")

    # ────────── 文件列表模式 ──────────

    def _add_files(self):
        files = filedialog.askopenfilenames(
            title="选择 M3U8 文件", filetypes=[("M3U8 文件", "*.m3u8"), ("所有文件", "*.*")])
        for f in files:
            normalized = str(Path(f).resolve())
            if normalized not in self.file_list:
                self.file_list.append(normalized)
                p = Path(f)
                self.filelist_tree.insert("", tk.END, values=(p.name, str(p.parent)))
        self.list_count_label.config(text=f"已添加: {len(self.file_list)} 个文件")

    def _remove_selected(self):
        selected = self.filelist_tree.selection()
        for item_id in reversed(selected):
            idx = self.filelist_tree.index(item_id)
            if 0 <= idx < len(self.file_list):
                del self.file_list[idx]
            self.filelist_tree.delete(item_id)
        self.list_count_label.config(text=f"已添加: {len(self.file_list)} 个文件")

    def _clear_filelist(self):
        self.file_list.clear()
        for item in self.filelist_tree.get_children():
            self.filelist_tree.delete(item)
        self.list_count_label.config(text="已添加: 0 个文件")

    # ────────── 转换流程 ──────────

    def _start_conversion(self):
        ffmpeg_path = self.ffmpeg_path
        if not ffmpeg_path:
            messagebox.showerror("错误",
                "未配置 FFmpeg 路径。\n\n请到「外部工具」标签页配置 FFmpeg 后再使用本功能。",
                parent=self.root)
            return
        if not self.file_list:
            messagebox.showwarning("提示", "请先选择要转换的 M3U8 文件", parent=self.root)
            return

        # 检查输出文件冲突
        conflicts = get_output_conflicts(self.file_list)
        if conflicts:
            msg = f"以下输出文件已存在:\n{chr(10).join(conflicts[:10])}"
            if len(conflicts) > 10:
                msg += "\n..."
            if not messagebox.askyesno("文件已存在", msg + "\n\n是否覆盖？", parent=self.root):
                self.log('warning', "用户取消了转换（存在输出文件冲突且选择不覆盖）")
                return
            self.log('warning', f"检测到 {len(conflicts)} 个输出文件已存在，用户选择覆盖")

        self.is_processing_flag = True
        self.stop_flag = False
        # 接入主程序统一状态与日志体系
        self.host.clear_error_log(self.TAB_NAME)
        self.host.set_processing_state(self.tab_widget, True)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log('info', f"开始转换任务，共 {len(self.file_list)} 个 M3U8 文件")
        threading.Thread(target=self._process_queue, daemon=True).start()

    def _stop_conversion(self):
        self.stop_flag = True
        self.status_label.config(text="正在停止...", foreground="orange")
        self.log('warning', "用户请求停止转换")

    def _process_queue(self):
        def on_progress(current_time, duration):
            if duration and duration > 0:
                pct = min(100.0, (current_time / duration) * 100)
                self.after(0, self._update_current_progress, pct, current_time, duration)
            else:
                self.after(0, self._update_current_progress_unknown, current_time)

        process_conversion_queue(
            file_list=self.file_list,
            ffmpeg_path=self.get_exe_path('ffmpeg'),
            ffprobe_path=self.get_exe_path('ffprobe'),
            stop_check=lambda: self.stop_flag,
            log=self.log,
            on_total=lambda i, total, fn: self.after(0, self._update_total_progress, i, total, fn),
            on_progress=on_progress,
            on_status=lambda text, color: self.after(0, self._update_status, text, color),
            on_final=lambda dur: self.after(0, self._update_current_progress, 100.0, dur or 0, dur or 0),
            on_done=lambda s, f, st: self.after(0, self._conversion_done, s, f, st),
        )

    # ────────── 进度更新 ──────────

    def _update_total_progress(self, current_idx, total, filename):
        self.total_progress["value"] = (current_idx / total) * 100 if total > 0 else 0
        self.total_label.config(text=f"{current_idx + 1} / {total}")
        self.status_label.config(text=f"正在处理: {filename}", foreground="blue")

    def _update_current_progress(self, pct, current_time, duration):
        self.current_progress["value"] = pct
        self.current_label.config(text=f"{pct:.1f}%  {fmt_time(current_time)}/{fmt_time(duration)}")

    def _update_current_progress_unknown(self, current_time):
        self.current_progress["value"] = 0
        self.current_label.config(text=f"{fmt_time(current_time)} / 未知时长")

    def _update_status(self, text, color="gray"):
        self.status_label.config(text=text, foreground=color)

    def _conversion_done(self, success, fail, stopped):
        self.is_processing_flag = False
        self.host.set_processing_state(self.tab_widget, False)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.total_progress["value"] = 100 if not stopped else self.total_progress["value"]
        self.current_progress["value"] = 0
        self.current_label.config(text="0.0%")
        if stopped:
            self.status_label.config(text=f"已停止 - 成功: {success}, 失败: {fail}", foreground="orange")
            self.log('warning', f"转换已停止 - 成功: {success}, 失败: {fail}")
        elif fail == 0:
            self.status_label.config(text=f"全部完成 - 成功: {success}", foreground="green")
            self.log('info', f"全部转换完成 - 成功: {success} 个文件")
        else:
            self.status_label.config(text=f"完成 - 成功: {success}, 失败: {fail}", foreground="red")
            self.log('error', f"转换完成但有失败 - 成功: {success}, 失败: {fail}")

    # ────────── 模块接口实现 ──────────

    def stop_processing(self):
        """外部调用停止"""
        if self.is_processing_flag:
            self._stop_conversion()

    def is_processing(self):
        """是否正在处理中"""
        return self.is_processing_flag

    def cleanup(self):
        """程序关闭时清理资源"""
        if self.is_processing_flag:
            self.stop_flag = True

    # ────────── 配置记忆 ──────────

    def save_config(self, config):
        """保存模块配置到共享配置字典（FFmpeg 路径由主程序外部工具管理统一保存）"""
        data = {
            "mode": self.mode_var.get(),
            "recursive": bool(self.recursive_var.get()),
            "output_folder": self.output_folder,
        }
        config[self.config_key] = data

    def load_config(self, config):
        """从模块专属配置字典加载配置"""
        mode = config.get("mode")
        if mode in ("folder", "filelist"):
            self.mode_var.set(mode)

        recursive = config.get("recursive")
        if recursive is not None:
            self.recursive_var.set(bool(recursive))

        output_folder = config.get("output_folder")
        if output_folder:
            self.output_folder = output_folder

    def clear_memory(self):
        """清除本模块的记忆，重置为默认值"""
        self.mode_var.set("folder")
        self.recursive_var.set(True)
        self.output_folder = ""
        if self._ui_built:
            self._switch_mode()


# 模块导出
MODULE_CLASS = M3U8MergerModule
