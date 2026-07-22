# -*- coding: utf-8 -*-
"""可滚动容器组件

使用 Canvas + 双向 Scrollbar 实现横纵向滚动。
- 滚动条仅在对应方向内容超出可见区域时显示
- 当内容小于可见区域时，自动扩展 inner_frame 以铺满 Canvas
- 鼠标进入时绑定滚轮，离开时解绑，避免事件冒泡
"""

import tkinter as tk
from tkinter import ttk


class ScrollableContainer(ttk.Frame):
    """可滚动容器：使用 Canvas + 双向 Scrollbar 实现

    使用方式:
        container = ScrollableContainer(parent)
        container.pack(fill=tk.BOTH, expand=True)
        inner = container.get_inner_frame()
        # 在 inner 中构建 UI
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0, bg='#F0F0F0')
        self.vscrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.hscrollbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.inner_frame = ttk.Frame(self.canvas)

        self.inner_window = self.canvas.create_window((0, 0), window=self.inner_frame, anchor=tk.NW)

        self.canvas.configure(yscrollcommand=self.vscrollbar.set,
                              xscrollcommand=self.hscrollbar.set)

        # 使用 grid 布局：Canvas 占主区域，滚动条在右侧和底部
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vscrollbar.grid(row=0, column=1, sticky='ns')
        self.hscrollbar.grid(row=1, column=0, sticky='ew')
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 初始隐藏滚动条（使用 grid_remove 保留位置信息）
        self.vscrollbar.grid_remove()
        self.hscrollbar.grid_remove()

        # 事件绑定
        self.inner_frame.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # 鼠标滚轮：仅在鼠标进入 canvas 时绑定，离开时解绑
        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)

        self._vscrollbar_visible = False
        self._hscrollbar_visible = False
        self._mouse_inside = False
        self._updating = False  # 防止递归更新

    def _on_inner_configure(self, event):
        """内部内容大小变化时更新滚动区域"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_layout()

    def _on_canvas_configure(self, event):
        """Canvas 大小变化时重新布局"""
        self._update_layout()

    def _update_layout(self):
        """统一更新布局：调整 inner_frame 大小并更新滚动条可见性"""
        if self._updating:
            return
        self._updating = True
        try:
            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:
                self.after(50, self._update_layout)
                return

            # 获取内容请求大小（由子组件决定，与 inner_frame 实际大小无关）
            req_width = self.inner_frame.winfo_reqwidth()
            req_height = self.inner_frame.winfo_reqheight()

            # 滚动条预留尺寸（避免显示/隐藏滚动条时反复闪烁）
            sb_v_width = self.vscrollbar.winfo_reqwidth() or 17
            sb_h_height = self.hscrollbar.winfo_reqheight() or 17

            # 第一轮判断：基于 Canvas 大小
            needs_vscroll = req_height > canvas_height
            needs_hscroll = req_width > canvas_width

            # 第二轮判断：考虑滚动条占据空间后的相互影响
            if needs_vscroll and not needs_hscroll:
                # 竖直滚动条占据宽度后，可能需要水平滚动条
                if req_width > (canvas_width - sb_v_width):
                    needs_hscroll = True
            if needs_hscroll and not needs_vscroll:
                # 水平滚动条占据高度后，可能需要竖直滚动条
                if req_height > (canvas_height - sb_h_height):
                    needs_vscroll = True

            # 计算可用大小（减去滚动条）
            avail_width = canvas_width - (sb_v_width if needs_vscroll else 0)
            avail_height = canvas_height - (sb_h_height if needs_hscroll else 0)

            # 设置 inner_frame 大小为 max(请求大小, 可用大小)
            # - 当请求大小 < 可用大小时，扩展到可用大小（控件自动调宽/调高间隙铺满）
            # - 当请求大小 > 可用大小时，使用请求大小（显示滚动条）
            target_width = max(req_width, avail_width)
            target_height = max(req_height, avail_height)

            self.canvas.itemconfig(self.inner_window,
                                   width=target_width, height=target_height)

            # 更新滚动区域
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

            # 显示/隐藏竖直滚动条
            if needs_vscroll != self._vscrollbar_visible:
                if needs_vscroll:
                    self.vscrollbar.grid()
                else:
                    self.vscrollbar.grid_remove()
                    self.canvas.yview_moveto(0)
                self._vscrollbar_visible = needs_vscroll

            # 显示/隐藏水平滚动条
            if needs_hscroll != self._hscrollbar_visible:
                if needs_hscroll:
                    self.hscrollbar.grid()
                else:
                    self.hscrollbar.grid_remove()
                    self.canvas.xview_moveto(0)
                self._hscrollbar_visible = needs_hscroll
        except Exception:
            pass
        finally:
            self._updating = False

    def _on_enter(self, event):
        """鼠标进入时启用滚轮"""
        self._mouse_inside = True
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Shift-MouseWheel>", self._on_shift_mousewheel)
        # Linux 上还需绑定 Button-4/5
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _on_leave(self, event):
        """鼠标离开时禁用滚轮"""
        self._mouse_inside = False
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Shift-MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        """鼠标滚轮（竖直滚动）"""
        if not self._mouse_inside or not self._vscrollbar_visible:
            return
        try:
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                delta = -1 * (event.delta // 120)
                self.canvas.yview_scroll(delta, "units")
        except Exception:
            pass

    def _on_shift_mousewheel(self, event):
        """Shift+鼠标滚轮（水平滚动）"""
        if not self._mouse_inside or not self._hscrollbar_visible:
            return
        try:
            delta = -1 * (event.delta // 120)
            self.canvas.xview_scroll(delta, "units")
        except Exception:
            pass

    def get_inner_frame(self):
        """获取内部 frame，模块在此构建 UI"""
        return self.inner_frame

    def check_scroll_needed(self):
        """外部调用：检查是否需要滚动条"""
        self._update_layout()
