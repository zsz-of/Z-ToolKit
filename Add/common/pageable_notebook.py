# -*- coding: utf-8 -*-
"""可翻页标签页组件

当标签页数量或宽度超过容器宽度时，自动分页显示，并提供翻页按钮。
兼容 ttk.Notebook 常用 API：add / select / tab / index / nametowidget / bind。
"""

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont


class PageableNotebook(ttk.Frame):
    """可翻页的标签页组件

    包装 ttk.Notebook，当标签页宽度超过容器宽度时自动分页。
    顶部右侧显示翻页按钮（仅在需要分页时显示）。

    兼容 ttk.Notebook 的常用 API：
        - add(tab, **kwargs)
        - select(tab_id=None)
        - tab(tab_id, option=None, **kwargs)
        - index(index=None)
        - nametowidget(name)
        - bind(sequence, func, add)
        - tabs()
    """

    # 每个标签的水平内边距估算（ttk 默认 padding）
    TAB_PADDING = 24
    # 重新布局的防抖延迟（毫秒）
    RELAYOUT_DELAY = 80

    def __init__(self, parent, **kwargs):
        super().__init__(parent)

        # 顶部翻页按钮栏（默认不 pack，需要分页时才显示）
        self._nav_bar = ttk.Frame(self)
        # 按钮右对齐布局（翻页控件位于右上角，符合常规交互习惯）
        self._next_btn = ttk.Button(self._nav_bar, text='▶', width=3,
                                     command=self._next_page)
        self._page_label = ttk.Label(self._nav_bar, text='')
        self._prev_btn = ttk.Button(self._nav_bar, text='◀', width=3,
                                     command=self._prev_page)
        self._next_btn.pack(side=tk.RIGHT, padx=2)
        self._page_label.pack(side=tk.RIGHT, padx=8)
        self._prev_btn.pack(side=tk.RIGHT, padx=2)

        # 内部 Notebook
        self._notebook = ttk.Notebook(self, **kwargs)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        # 所有标签页信息
        self._all_tabs = []          # list of tab_widget（按 add 顺序）
        self._tab_texts = {}         # tab_widget -> 当前文本
        self._tab_widths = {}        # tab_widget -> 估算宽度
        self._pinned_tabs = []       # 常驻标签页（不参与分页，始终显示在最右端）
        self._current_page = 0       # 当前页码（0-based）
        self._tabs_per_page = 0      # 每页标签数（0 表示全部显示，不分页）
        self._total_pages = 1

        # 字体测量（用于估算标签宽度）
        self._measure_font = tkfont.Font(self, family='TkDefaultFont')

        # 防递归标志
        self._updating = False
        self._relayout_scheduled = False

        # 监听 Notebook 大小变化
        self._notebook.bind('<Configure>', self._on_configure)

    # ========== 内部布局逻辑 ==========

    def _on_configure(self, event):
        """Notebook 大小变化时触发重新布局"""
        if event.widget != self._notebook:
            return
        self._schedule_relayout()

    def _schedule_relayout(self):
        """防抖调度重新布局"""
        if self._relayout_scheduled:
            return
        self._relayout_scheduled = True
        self.after(self.RELAYOUT_DELAY, self._do_relayout)

    def _do_relayout(self):
        """执行重新布局：计算分页并更新可见性"""
        self._relayout_scheduled = False
        if self._updating or not self._all_tabs:
            return
        self._updating = True
        try:
            available_width = self._notebook.winfo_width()
            if available_width <= 1:
                # 宽度尚未确定，延迟重试
                self.after(100, self._do_relayout)
                return

            # 计算或更新每个标签的估算宽度
            for tab in self._all_tabs:
                text = self._tab_texts.get(tab, '')
                self._tab_widths[tab] = (
                    self._measure_font.measure(text) + self.TAB_PADDING
                )

            # 分离 normal 标签和 pinned 标签（pinned 不参与分页）
            normal_tabs = [t for t in self._all_tabs if t not in self._pinned_tabs]
            pinned_tabs = self._pinned_tabs

            # pinned 标签占据的宽度（始终显示在最右端）
            pinned_width = sum(self._tab_widths[t] for t in pinned_tabs)
            # 留给 normal 标签的可用宽度
            usable_width = max(available_width - pinned_width, 80)

            total_normal_width = sum(self._tab_widths[t] for t in normal_tabs)

            if total_normal_width <= usable_width:
                # 无需分页：所有 normal 标签都能完整显示
                need_pagination = False
                self._tabs_per_page = 0
                self._total_pages = 1
                self._current_page = 0
            else:
                # 需要分页：计算每页可容纳的 normal 标签数
                # nav bar 位于 notebook 上方（不占用横向空间）
                accumulated = 0
                count = 0
                for tab in normal_tabs:
                    w = self._tab_widths[tab]
                    if count > 0 and accumulated + w > usable_width:
                        break
                    accumulated += w
                    count += 1
                if count == 0:
                    count = 1
                self._tabs_per_page = count
                self._total_pages = (
                    (len(normal_tabs) + count - 1) // count
                ) if normal_tabs else 1
                need_pagination = self._total_pages > 1

            # 修正当前页码
            if self._current_page >= self._total_pages:
                self._current_page = self._total_pages - 1
            if self._current_page < 0:
                self._current_page = 0

            # 更新标签可见性
            self._update_tab_visibility()

            # 更新翻页按钮栏
            if need_pagination:
                self._show_nav_bar()
                self._update_page_label()
            else:
                self._hide_nav_bar()
        finally:
            self._updating = False

    def _update_tab_visibility(self, preserve_selection=True):
        """根据当前页码显示/隐藏标签页

        使用 forget() + insert() 而非 hide() + add()。
        原因：ttk.Notebook.hide() 将标签保留在 tabs() 列表中但不可见，
        后续判断 "if str(tab) not in current_tabs" 永远为 False，
        导致隐藏后的标签无法被重新显示（用户看到空白区域）。
        forget() 彻底移除标签，insert() 按顺序重新添加，避免此问题。

        pinned 标签页始终显示在最后，不参与分页。

        参数:
            preserve_selection: 是否保持当前选中标签页的显示状态。
                True（默认，用于翻页/窗口缩放）：当前选中标签页的内容保持显示，
                    即使该标签页不在当前页上（其头部仍可见，避免切换内容）。
                False（用于显式 select）：允许切换到目标标签页所在的页。
        """
        # 分离 normal 标签和 pinned 标签
        normal_tabs = [t for t in self._all_tabs if t not in self._pinned_tabs]
        pinned_tabs = self._pinned_tabs

        if self._tabs_per_page == 0:
            # 不分页：显示所有 normal 标签
            visible_normal = normal_tabs
        else:
            start = self._current_page * self._tabs_per_page
            end = min(start + self._tabs_per_page, len(normal_tabs))
            visible_normal = normal_tabs[start:end]

        # visible_tabs = 当前页 normal 标签 + 全部 pinned 标签（pinned 在最右端）
        visible_tabs = visible_normal + pinned_tabs

        # 记住当前选中的标签（用于后续恢复选中状态）
        try:
            selected_id = self._notebook.select()
            current_selected = (
                self._notebook.nametowidget(selected_id)
                if selected_id else None
            )
        except (tk.TclError, KeyError):
            current_selected = None

        # 翻页/缩放时保持当前选中标签页的显示（不切换内容）
        # 即使该标签页不在当前页上，也将其保留在 notebook 中
        # 保留位置：当前页的第一个位置（visible_normal 之前）
        if preserve_selection and current_selected is not None:
            if current_selected not in visible_tabs and current_selected in self._all_tabs:
                visible_tabs = [current_selected] + visible_normal + pinned_tabs

        visible_set = set(visible_tabs)

        # 获取当前 notebook 中的标签 widget 列表
        try:
            current_tab_names = list(self._notebook.tabs())
            current_tabs = [
                self._notebook.nametowidget(n) for n in current_tab_names
            ]
        except (tk.TclError, KeyError):
            current_tabs = []

        # 第一步：forget 所有不在当前页的标签
        for tab in current_tabs:
            if tab not in visible_set:
                try:
                    self._notebook.forget(tab)
                except tk.TclError:
                    pass

        # 第二步：按顺序 insert/add 当前页的标签，确保顺序正确
        try:
            current_tab_names = list(self._notebook.tabs())
        except tk.TclError:
            current_tab_names = []

        for i, tab in enumerate(visible_tabs):
            # 若该标签已在正确位置，无需操作
            if i < len(current_tab_names):
                try:
                    existing = self._notebook.nametowidget(current_tab_names[i])
                    if existing == tab:
                        continue
                except (tk.TclError, KeyError):
                    pass
            # 否则插入到位置 i
            try:
                # 若标签在其他位置存在，先 forget
                if str(tab) in current_tab_names:
                    self._notebook.forget(tab)
                self._notebook.insert(i, tab, text=self._tab_texts.get(tab, ''))
                current_tab_names = list(self._notebook.tabs())
            except tk.TclError:
                try:
                    self._notebook.add(tab, text=self._tab_texts.get(tab, ''))
                    current_tab_names = list(self._notebook.tabs())
                except tk.TclError:
                    pass

        # 恢复选中状态：保持当前选中标签页（不切换内容）
        if current_selected is not None:
            try:
                # 确保当前选中标签页仍被选中
                if str(current_selected) != self._notebook.select():
                    self._notebook.select(current_selected)
            except tk.TclError:
                pass
        elif visible_tabs:
            try:
                self._notebook.select(visible_tabs[0])
            except tk.TclError:
                pass

    def _show_nav_bar(self):
        """显示翻页按钮栏"""
        if not self._nav_bar.winfo_ismapped():
            self._nav_bar.pack(fill=tk.X, side=tk.TOP,
                              before=self._notebook, pady=(0, 2))

    def _hide_nav_bar(self):
        """隐藏翻页按钮栏"""
        if self._nav_bar.winfo_ismapped():
            self._nav_bar.pack_forget()

    def _update_page_label(self):
        """更新页码显示"""
        self._page_label.config(
            text=f'{self._current_page + 1} / {self._total_pages}'
        )

    def _prev_page(self):
        """切换到上一页"""
        if self._current_page > 0:
            self._current_page -= 1
            self._update_tab_visibility()
            self._update_page_label()

    def _next_page(self):
        """切换到下一页"""
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._update_tab_visibility()
            self._update_page_label()

    def _ensure_tab_visible(self, tab):
        """确保指定标签页在当前可见页中，必要时切换页码

        pinned 标签页始终可见，无需切换页码。
        此方法用于显式 select()，允许切换内容（preserve_selection=False）。
        """
        if self._tabs_per_page == 0 or tab not in self._all_tabs:
            return
        # pinned 标签始终可见，无需切换页码
        if tab in self._pinned_tabs:
            return
        # 在 normal 标签中查找索引
        normal_tabs = [t for t in self._all_tabs if t not in self._pinned_tabs]
        if tab not in normal_tabs:
            return
        idx = normal_tabs.index(tab)
        target_page = idx // self._tabs_per_page
        if target_page != self._current_page:
            self._current_page = target_page
            self._update_tab_visibility(preserve_selection=False)
            self._update_page_label()

    # ========== ttk.Notebook 兼容 API ==========

    def add(self, tab, pinned=False, **kwargs):
        """添加标签页

        参数:
            tab: 标签页 widget（ttk.Frame）
            pinned: 是否常驻最右端（不参与分页，始终可见）
            **kwargs: ttk.Notebook.add 的参数（text、image 等仅支持 text）
        """
        text = kwargs.get('text', '')
        self._notebook.add(tab, **kwargs)
        if tab not in self._all_tabs:
            self._all_tabs.append(tab)
        self._tab_texts[tab] = text
        self._tab_widths.pop(tab, None)
        if pinned and tab not in self._pinned_tabs:
            self._pinned_tabs.append(tab)
        self._schedule_relayout()

    def set_buttons_enabled(self, enabled):
        """启用或禁用翻页按钮

        任务进行时调用 set_buttons_enabled(False) 禁用翻页按钮，
        防止用户切换到其他页的标签页。
        """
        state = tk.NORMAL if enabled else tk.DISABLED
        try:
            self._prev_btn.config(state=state)
            self._next_btn.config(state=state)
        except tk.TclError:
            pass

    def select(self, tab_id=None):
        """选择标签页

        参数:
            tab_id: 可选，标签页 widget 或索引或名称字符串。
                    不传则返回当前选中的 tab_id。

        如果 tab_id 不在当前可见页，会自动切换到对应页。
        """
        if tab_id is None:
            return self._notebook.select()

        # 解析 tab_id 为 tab_widget
        tab_widget = self._resolve_tab_id(tab_id)
        if tab_widget is not None:
            self._ensure_tab_visible(tab_widget)
        return self._notebook.select(tab_id)

    def tab(self, tab_id, option=None, **kwargs):
        """获取或设置标签页属性

        当设置 text 属性时，会更新缓存并触发重新布局。
        当 tab_id 指向被 forget 的标签页（在其他页上）时，从缓存查找。
        """
        if 'text' in kwargs:
            tab_widget = self._resolve_tab_id(tab_id)
            if tab_widget is not None:
                self._tab_texts[tab_widget] = kwargs['text']
                self._tab_widths.pop(tab_widget, None)
                self._schedule_relayout()
        try:
            return self._notebook.tab(tab_id, option, **kwargs)
        except tk.TclError:
            # tab_id 可能指向被 forget 的标签页（在其他页上）
            # 从缓存中查找
            tab_widget = self._resolve_tab_id(tab_id)
            if tab_widget is not None:
                if kwargs:
                    # 设置操作：已更新缓存，重新插入时会使用新值，忽略错误
                    return None
                if option is None:
                    # 返回所有属性的字典
                    return {'text': self._tab_texts.get(tab_widget, '')}
                elif option == 'text':
                    return self._tab_texts.get(tab_widget, '')
            raise

    def index(self, index=None):
        """获取标签页索引"""
        return self._notebook.index(index)

    def nametowidget(self, name):
        """通过名称字符串获取 widget"""
        return self._notebook.nametowidget(name)

    def bind(self, sequence=None, func=None, add=None):
        """绑定事件到内部 Notebook"""
        return self._notebook.bind(sequence, func, add)

    def tabs(self):
        """返回当前可见的标签页列表"""
        return self._notebook.tabs()

    def select_by_text(self, text):
        """通过标签文本查找并选中标签页（跨页查找）

        在所有标签页（包括当前不可见的）中查找文本匹配的标签，
        自动切换到对应页并选中。用于主程序按名称切换到特定标签页
        （如"外部工具"、"错误日志"），避免分页时找不到目标标签。

        参数:
            text: 标签页文本

        返回:
            True 如果找到并选中；False 如果未找到。
        """
        for tab in self._all_tabs:
            if self._tab_texts.get(tab, '') == text:
                self._ensure_tab_visible(tab)
                try:
                    self._notebook.select(tab)
                except tk.TclError:
                    pass
                return True
        return False

    def forget(self, tab_id):
        """移除标签页"""
        tab_widget = self._resolve_tab_id(tab_id)
        self._notebook.forget(tab_id)
        if tab_widget in self._all_tabs:
            self._all_tabs.remove(tab_widget)
        self._tab_texts.pop(tab_widget, None)
        self._tab_widths.pop(tab_widget, None)
        self._schedule_relayout()

    def winfo_children(self):
        """返回子 widget 列表"""
        return self._notebook.winfo_children()

    def _resolve_tab_id(self, tab_id):
        """将 tab_id（widget/索引/名称）解析为 tab_widget"""
        try:
            if isinstance(tab_id, int):
                # 索引形式（仅在当前可见标签中有效）
                visible = list(self._notebook.tabs())
                if 0 <= tab_id < len(visible):
                    return self._notebook.nametowidget(visible[tab_id])
                return None
            elif isinstance(tab_id, str):
                return self._notebook.nametowidget(tab_id)
            else:
                # widget 对象
                return tab_id
        except (tk.TclError, KeyError):
            return None
