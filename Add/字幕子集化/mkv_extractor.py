# -*- coding: utf-8 -*-
"""MKV 字幕提取与合并工具"""

import os
import json
import shutil
import subprocess
import threading
from typing import Optional, Callable, List, Tuple

from .font_utils import MKVEXTRACT_TIMEOUT, MKVMERGE_TIMEOUT


class MKVExtractor:
    def __init__(self, mkvextract_path: Optional[str] = None, mkvmerge_path: Optional[str] = None):
        """初始化 MKV 提取器

        参数:
            mkvextract_path: mkvextract 可执行文件路径。若为 None 则不指定（由模块从主程序获取后传入）
            mkvmerge_path: mkvmerge 可执行文件路径。若为 None 则不指定
        """
        self.mkvextract_path = mkvextract_path
        self.mkvmerge_path = mkvmerge_path

    def update_paths(self, mkvextract_path: Optional[str], mkvmerge_path: Optional[str]):
        """更新工具路径（由模块在调用前从主程序外部工具管理获取后传入）"""
        if mkvextract_path:
            self.mkvextract_path = mkvextract_path
        if mkvmerge_path:
            self.mkvmerge_path = mkvmerge_path

    def extract_subtitles(self, mkv_path: str, output_dir: str,
                          callback: Optional[Callable] = None,
                          stop_event: Optional[threading.Event] = None,
                          subprocess_holder: Optional[list] = None,
                          subprocess_register_callback: Optional[Callable] = None) -> List[Tuple]:
        if not self.mkvextract_path:
            raise FileNotFoundError("未找到mkvextract工具，请安装MKVToolNix")

        try:
            mkvmerge = self.mkvmerge_path
            if not mkvmerge:
                raise FileNotFoundError("未找到mkvmerge工具，请安装MKVToolNix")
            cmd = [mkvmerge, '-J', mkv_path]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace',
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            data = json.loads(result.stdout)

            subtitle_tracks = []
            for track in data.get('tracks', []):
                if track.get('type') == 'subtitles':
                    subtitle_tracks.append({
                        'id': track.get('id'),
                        'codec': track.get('codec'),
                        'language': track.get('properties', {}).get('language'),
                        'name': track.get('properties', {}).get('track_name', '')
                    })

            if not subtitle_tracks:
                return []

            extracted = []
            for track in subtitle_tracks:
                if stop_event and stop_event.is_set():
                    break

                track_id = track['id']
                base_name = os.path.splitext(os.path.basename(mkv_path))[0]

                if track['name']:
                    output_name = f"{base_name}_{track['name']}"
                elif track['language']:
                    output_name = f"{base_name}_{track['language']}"
                else:
                    output_name = f"{base_name}_track{track_id}"

                codec = track['codec'].lower()
                if 'ass' in codec or 'ssa' in codec:
                    ext = '.ass'
                elif 'srt' in codec:
                    ext = '.srt'
                else:
                    ext = '.ass'

                output_file = os.path.join(output_dir, f"{output_name}{ext}")
                if os.path.exists(output_file):
                    counter = 1
                    while os.path.exists(os.path.join(output_dir, f"{output_name}_{counter}{ext}")):
                        counter += 1
                    output_file = os.path.join(output_dir, f"{output_name}_{counter}{ext}")

                if callback:
                    callback(f"提取轨道 {track_id} ({track.get('language', 'und')})...")

                cmd = [self.mkvextract_path, 'tracks', mkv_path, f'{track_id}:{output_file}']

                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        encoding='utf-8', errors='replace',
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if subprocess_holder is not None:
                    subprocess_holder[0] = proc
                if subprocess_register_callback is not None:
                    subprocess_register_callback(proc)

                try:
                    stdout, stderr = proc.communicate(timeout=MKVEXTRACT_TIMEOUT)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    raise RuntimeError(f"提取轨道 {track_id} 超时")

                if stop_event and stop_event.is_set():
                    break

                if proc.returncode == 0 and os.path.exists(output_file):
                    extracted.append((track_id, 'subtitles',
                                     track.get('language', 'und'), output_file))
                    if callback:
                        callback(f"已提取: {output_file}")
                else:
                    if callback:
                        callback(f"提取失败: {stderr}")

            return extracted

        except Exception as e:
            raise RuntimeError(f"提取过程出错: {e}")

    def merge_subtitle_back(self, mkv_path: str, ass_tracks: List[Tuple],
                            font_files: List[str], output_path: str,
                            callback: Optional[Callable] = None,
                            stop_event: Optional[threading.Event] = None,
                            subprocess_holder: Optional[list] = None,
                            subprocess_register_callback: Optional[Callable] = None) -> bool:
        if not self.mkvmerge_path:
            raise FileNotFoundError("未找到mkvmerge工具")

        temp_output = output_path + ".temp.mkv"
        is_replace_mode = os.path.abspath(output_path) == os.path.abspath(mkv_path)

        cmd = [self.mkvmerge_path, "-o", temp_output]

        attached = set()
        for font_file in (font_files or []):
            if not font_file or not os.path.exists(font_file):
                continue
            real_path = os.path.normcase(os.path.abspath(font_file))
            if real_path in attached:
                continue
            attached.add(real_path)
            ext = os.path.splitext(font_file)[1].lower()
            font_mime_types = {
                '.ttf': 'application/x-truetype-font',
                '.ttc': 'application/x-truetype-font',
                '.otf': 'application/vnd.ms-opentype',
                '.otc': 'application/vnd.ms-opentype',
            }
            mime = font_mime_types.get(ext, 'application/x-truetype-font')
            cmd.extend(["--attachment-mime-type", mime, "--attach-file", font_file])

        cmd.extend(["--no-subtitles", mkv_path])

        for i, (ass_path, lang, track_name, is_default) in enumerate(ass_tracks):
            if ass_path and os.path.exists(ass_path):
                lang_code = lang if lang else 'und'
                track_label = track_name if track_name else 'Processed'
                cmd.extend([
                    "--language", f"0:{lang_code}",
                    "--track-name", f"0:{track_label}",
                    "--default-track", f"0:{'1' if is_default else '0'}",
                    ass_path
                ])

        if callback:
            callback("合并字幕回MKV...")

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding='utf-8', errors='replace',
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if subprocess_holder is not None:
            subprocess_holder[0] = proc
        if subprocess_register_callback is not None:
            subprocess_register_callback(proc)

        try:
            stdout, stderr = proc.communicate(timeout=MKVMERGE_TIMEOUT)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise RuntimeError("合并MKV超时")

        if stop_event and stop_event.is_set():
            if os.path.exists(temp_output):
                try:
                    os.remove(temp_output)
                except Exception:
                    pass
            raise RuntimeError("合并被用户取消")

        if proc.returncode not in [0, 1]:
            raise RuntimeError(f"合并失败: {stderr}")

        if not os.path.exists(temp_output):
            raise RuntimeError("临时文件未生成")

        if is_replace_mode:
            backup_file = mkv_path + ".backup.mkv"
            shutil.move(mkv_path, backup_file)
            try:
                shutil.move(temp_output, output_path)
            except Exception:
                if os.path.exists(backup_file):
                    shutil.move(backup_file, mkv_path)
                raise
            try:
                os.remove(backup_file)
            except OSError:
                pass
        else:
            shutil.move(temp_output, output_path)

        if callback:
            callback("合并完成")

        return True
