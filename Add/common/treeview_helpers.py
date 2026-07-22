# -*- coding: utf-8 -*-
"""Treeview 容器工具

提供可滚动的 Treeview 容器创建工具，消除重复的 grid 布局模板。
"""

import tkinter as tk
from tkinter import ttk


def create_scrollable_tree(parent, columns, headings, heights=None, anchors=None):
    """创建带双向滚动条的 Treeview 容器

    参数:
        parent: 父容器
        columns: 列标识列表，如 ('filename', 'size')
        headings: 列标题字典，如 {'filename': '文件名', 'size': '大小'}
        heights: 可选，列宽字典，如 {'filename': 300, 'size': 80}
        anchors: 可选，列对齐字典，如 {'filename': tk.W, 'size': 'e'}

    返回:
        tuple: (tree, list_frame) - Treeview 实例和包含它的 LabelFrame
    """
    list_frame = ttk.Frame(parent)
    list_frame.pack(fill=tk.BOTH, expand=True)

    tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=1)

    for col in columns:
        tree.heading(col, text=headings.get(col, col))
        if heights and col in heights:
            tree.column(col, width=heights[col], anchor=(anchors or {}).get(col, tk.W))
        else:
            tree.column(col, anchor=(anchors or {}).get(col, tk.W))

    scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
    scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=tree.xview)
    tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

    tree.grid(row=0, column=0, sticky='nsew')
    scrollbar_y.grid(row=0, column=1, sticky='ns')
    scrollbar_x.grid(row=1, column=0, sticky='ew')

    list_frame.grid_rowconfigure(0, weight=1)
    list_frame.grid_columnconfigure(0, weight=1)

    return tree, list_frame
