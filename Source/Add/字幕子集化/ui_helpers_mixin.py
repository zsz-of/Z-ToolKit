# -*- coding: utf-8 -*-
"""UI 辅助 Mixin：文件浏览/添加/删除与控件状态管理"""

import os
import tkinter as tk
from tkinter import filedialog

from .font_utils import SEND2TRASH_AVAILABLE


class UiHelpersMixin:
    """UI 辅助方法（通过 Mixin 组合到主模块类）"""

    def _browse_input_folder(self) -> None:
        dir_path = filedialog.askdirectory(title="选择输入文件夹")
        if dir_path:
            self.folder_path.set(dir_path)
            parent = os.path.dirname(dir_path)
            possible_font = os.path.join(parent, '字体')
            if os.path.exists(possible_font) and not self.font_dir.get():
                self.font_dir.set(possible_font)
            if not self.output_dir.get():
                self.output_dir.set(os.path.join(dir_path, '输出'))

    def _add_files(self) -> None:
        mode = self.mode.get()
        if mode == 'ass':
            files = filedialog.askopenfilenames(
                title="选择ASS字幕文件",
                filetypes=[("ASS字幕", "*.ass"), ("所有文件", "*.*")]
            )
            target_list = self.ass_files
        else:
            files = filedialog.askopenfilenames(
                title="选择MKV视频文件",
                filetypes=[("MKV文件", "*.mkv"), ("所有文件", "*.*")]
            )
            target_list = self.mkv_files

        if files:
            for f in files:
                if f not in target_list:
                    target_list.append(f)
                    self.file_listbox.insert(tk.END, os.path.basename(f))
            if not self.font_dir.get():
                parent = os.path.dirname(files[0])
                possible_font = os.path.join(parent, '字体')
                if os.path.exists(possible_font):
                    self.font_dir.set(possible_font)
            if not self.output_dir.get():
                parent = os.path.dirname(files[0])
                self.output_dir.set(os.path.join(parent, '输出'))

    def _delete_selected_files(self) -> None:
        selected = list(self.file_listbox.curselection())
        mode = self.mode.get()
        target_list = self.ass_files if mode == 'ass' else self.mkv_files

        for idx in sorted(selected, reverse=True):
            if 0 <= idx < len(target_list):
                del target_list[idx]
                self.file_listbox.delete(idx)

    def _clear_files(self) -> None:
        mode = self.mode.get()
        if mode == 'ass':
            self.ass_files.clear()
        else:
            self.mkv_files.clear()
        self.file_listbox.delete(0, tk.END)

    def _browse_font_dir(self) -> None:
        dir_path = filedialog.askdirectory(title="选择字体库根目录")
        if dir_path:
            self.font_dir.set(dir_path)

    def _browse_output_dir(self) -> None:
        dir_path = filedialog.askdirectory(title="选择输出目录")
        if dir_path:
            self.output_dir.set(dir_path)

    def _set_mode_state(self, state: str) -> None:
        self.mode_ass_rb.config(state=state)
        self.mode_mkv_rb.config(state=state)

    def _set_file_selection_state(self, state: str) -> None:
        self.input_mode_folder_rb.config(state=state)
        self.input_mode_filelist_rb.config(state=state)
        self.folder_entry.config(state=state)
        self.folder_btn.config(state=state)
        self.file_listbox.config(state=state)
        self.add_file_btn.config(state=state)
        self.del_file_btn.config(state=state)
        self.clear_file_btn.config(state=state)

    def _set_dir_settings_state(self, state: str) -> None:
        self.font_dir_entry.config(state=state)
        self.font_dir_btn.config(state=state)
        self.output_dir_entry.config(state=state)
        self.output_dir_btn.config(state=state)

    def _set_options_state(self, state: str) -> None:
        self.create_subsets_cb.config(state=state)
        if self.embed_back_cb.cget('state') != 'disabled':
            self.embed_back_cb.config(state=state)
        self.delete_source_cb.config(state=state)
        self.skip_incomplete_cb.config(state=state)
        delete_enabled = self.delete_source.get() and state == 'normal'
        if delete_enabled:
            opt_state = 'normal' if SEND2TRASH_AVAILABLE else 'disabled'
        else:
            opt_state = 'disabled'
        if self.recycle_rb.cget('state') != 'disabled':
            self.recycle_rb.config(state=opt_state)
        self.permanent_rb.config(state=opt_state)

    def _set_config_locked(self, locked: bool) -> None:
        state = 'disabled' if locked else 'normal'
        self._set_mode_state(state)
        self._set_file_selection_state(state)
        self._set_dir_settings_state(state)
