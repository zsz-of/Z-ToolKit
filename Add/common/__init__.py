# -*- coding: utf-8 -*-
"""公共组件包

提供 Z-ToolKit 模块开发所需的公共组件和工具函数。
每个组件独立一个 py 文件，便于维护和扩展。

模块导入规范:
    from common import TabModule, ScrollableContainer
    from common import FileSelector, MKVEmbedFileSelector
    from common.utils import format_size, sanitize_filename, safe_remove
    from common.encoding_options_panel import EncodingOptionsPanel
    from common.pageable_notebook import PageableNotebook

向后兼容 module_base.py 的导入:
    from common import TabModule, ScrollableContainer, UnifiedFileSelector
    from common import EncodingOptionsPanel, format_size
"""

# 公共组件导出
from .tab_module import TabModule
from .scrollable_container import ScrollableContainer
from .file_selector import FileSelector, UnifiedFileSelector, MKVEmbedFileSelector
from .encoding_options_panel import EncodingOptionsPanel
from .pageable_notebook import PageableNotebook
from .utils import (
    get_video_total_frames,
    sanitize_filename,
    safe_remove,
    format_size,
)
from .treeview_helpers import create_scrollable_tree

__all__ = [
    'TabModule',
    'ScrollableContainer',
    'FileSelector',
    'UnifiedFileSelector',
    'MKVEmbedFileSelector',
    'EncodingOptionsPanel',
    'PageableNotebook',
    'format_size',
    'sanitize_filename',
    'safe_remove',
    'get_video_total_frames',
    'create_scrollable_tree',
]
