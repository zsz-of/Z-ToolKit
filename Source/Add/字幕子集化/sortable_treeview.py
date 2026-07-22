# -*- coding: utf-8 -*-
"""可排序 Treeview 组件"""

import re
from typing import Set

import tkinter as tk
from tkinter import ttk


class SortableTreeview(ttk.Treeview):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self._sort_column = None
        self._sort_reverse = False
        self._pinned_tags: Set[str] = set()

    def set_pinned_tags(self, tags: Set[str]) -> None:
        self._pinned_tags = tags

    def heading(self, column, **kwargs):
        command = kwargs.get('command')
        if command is None:
            kwargs['command'] = lambda: self._sort_by_column(column)
        super().heading(column, **kwargs)

    @staticmethod
    def _natural_sort_key(s: str):
        parts = re.split(r'(\d+)', s.lower())
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                result.append(int(part))
            else:
                result.append(part)
        return result

    @staticmethod
    def _smart_sort_key(s: str):
        """智能排序键：纯数字按数值排，非数字按自然排序，数字优先于非数字"""
        s = str(s).strip()
        try:
            return (0, int(s), '')
        except ValueError:
            return (1, 0, SortableTreeview._natural_sort_key(s))

    def _sort_by_column(self, column: str):
        items = []
        for k in self.get_children(''):
            val = self.set(k, column)
            item_tags = self.item(k, 'tags') or ()
            is_pinned = any(t in self._pinned_tags for t in item_tags)
            items.append((val, is_pinned, k))

        items.sort(key=lambda t: (not t[1], self._smart_sort_key(t[0])), reverse=self._sort_reverse)

        for index, (val, pinned, k) in enumerate(items):
            self.move(k, '', index)

        self._sort_reverse = not self._sort_reverse
        self._sort_column = column
