# -*- coding: utf-8 -*-
"""公共工具函数

提供文件名清理、安全删除、文件大小格式化、视频帧数探测等工具函数。
所有模块应直接导入使用，禁止在模块内复制实现。
"""

import os
import re
import subprocess


def get_video_total_frames(video_file, ffprobe_path=None, ffmpeg_path=None):
    """获取视频总帧数，支持多种备用方案，失败则返回 None

    参数:
        video_file: 视频文件路径
        ffprobe_path: ffprobe 可执行文件路径（来自主程序外部工具管理）
        ffmpeg_path: ffmpeg 可执行文件路径（来自主程序外部工具管理）

    注意: 调用者必须通过 self.get_exe_path() 传入有效路径，本函数不再回退到裸命令名。
    """
    if not video_file or not os.path.isfile(video_file):
        return None

    # 方案1: 使用 ffprobe 获取 stream 层级的 nb_frames / duration / r_frame_rate
    if ffprobe_path:
        try:
            cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=nb_frames,r_frame_rate,duration",
                   "-of", "default=noprint_wrappers=1", video_file]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            if result.returncode == 0:
                nb_frames = None
                fps = None
                duration = None
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('nb_frames='):
                        val = line.split('=', 1)[1].strip()
                        if val and val.lower() != 'n/a':
                            try:
                                nb_frames = int(val)
                            except Exception:
                                pass
                    elif line.startswith('r_frame_rate='):
                        val = line.split('=', 1)[1].strip()
                        if val and val.lower() != 'n/a':
                            try:
                                num, den = val.split('/')
                                fps = float(num) / float(den)
                            except Exception:
                                pass
                    elif line.startswith('duration='):
                        val = line.split('=', 1)[1].strip()
                        if val and val.lower() != 'n/a':
                            try:
                                duration = float(val)
                            except Exception:
                                pass
                if nb_frames and nb_frames > 0:
                    return nb_frames
                if fps and duration and fps > 0 and duration > 0:
                    return int(fps * duration)
        except Exception:
            pass

    # 方案2: 使用 ffprobe 获取 format 层级的 duration
    if ffprobe_path:
        try:
            cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
                   "-show_entries", "stream=r_frame_rate", "-show_entries", "format=duration",
                   "-of", "default=noprint_wrappers=1", video_file]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            if result.returncode == 0:
                fps = None
                duration = None
                for line in result.stdout.strip().split('\n'):
                    if line.startswith('r_frame_rate='):
                        val = line.split('=', 1)[1].strip()
                        if val and val.lower() != 'n/a':
                            try:
                                num, den = val.split('/')
                                fps = float(num) / float(den)
                            except Exception:
                                pass
                    elif line.startswith('duration='):
                        val = line.split('=', 1)[1].strip()
                        if val and val.lower() != 'n/a':
                            try:
                                duration = float(val)
                            except Exception:
                                pass
                if fps and duration and fps > 0 and duration > 0:
                    return int(fps * duration)
        except Exception:
            pass

    # 方案3: 使用 ffprobe -count_packets 获取 nb_read_packets
    if ffprobe_path:
        try:
            cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0",
                   "-count_packets", "-show_entries", "stream=nb_read_packets",
                   "-of", "default=noprint_wrappers=1:nokey=1", video_file]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
            if result.returncode == 0:
                val = result.stdout.strip()
                if val and val.lower() != 'n/a':
                    try:
                        pkt_count = int(val)
                        if pkt_count > 0:
                            return pkt_count
                    except Exception:
                        pass
        except Exception:
            pass

    # 方案4: 使用 ffmpeg 解码统计实际帧数
    if ffmpeg_path:
        try:
            cmd = [ffmpeg_path, "-v", "warning", "-stats", "-i", video_file,
                   "-map", "0:v:0", "-c", "copy", "-f", "null", "-"]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
                                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=120)
            frame_match = re.search(r'frame=\s*(\d+)', result.stderr)
            if frame_match:
                frame_count = int(frame_match.group(1))
                if frame_count > 0:
                    return frame_count
            frame_match = re.search(r'frame=\s*(\d+)', result.stdout)
            if frame_match:
                frame_count = int(frame_match.group(1))
                if frame_count > 0:
                    return frame_count
        except Exception:
            pass

    return None


def sanitize_filename(name):
    """清理文件名中的非法字符"""
    illegal_chars = r'[\\/:*?"<>|]'
    safe_name = re.sub(illegal_chars, '_', name)
    safe_name = safe_name.strip(' .')
    if not safe_name:
        safe_name = 'Unnamed'
    return safe_name


def safe_remove(filepath, host, source=""):
    """安全删除文件，失败时记录日志

    参数:
        filepath: 要删除的文件路径
        host: HostInterface 实例（用于记录日志）
        source: 日志来源标签（默认为 "系统"）
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        host.log_message('warning', f"删除文件失败 [{filepath}]: {e}", source or "系统")


def format_size(size_bytes):
    """将字节数格式化为人类可读的字符串

    参数:
        size_bytes: 字节数（int 或 float）

    返回:
        格式化后的字符串，如 "1.5 MB"、"300 B"
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
