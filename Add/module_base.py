# -*- coding: utf-8 -*-
"""兼容层：重导出 common 包中的公共组件

此文件为兼容旧模块的导入语句而保留：
    from module_base import TabModule, UnifiedFileSelector, ...

新模块应直接从 common 包导入：
    from common import TabModule, FileSelector, ...

此文件将在所有模块迁移到 common 包后删除。
"""

from common import (
    TabModule,
    ScrollableContainer,
    FileSelector,
    UnifiedFileSelector,
    MKVEmbedFileSelector,
    EncodingOptionsPanel,
    format_size,
    sanitize_filename,
    safe_remove,
    get_video_total_frames,
)

__all__ = [
    'TabModule',
    'ScrollableContainer',
    'FileSelector',
    'UnifiedFileSelector',
    'MKVEmbedFileSelector',
    'EncodingOptionsPanel',
    'format_size',
    'sanitize_filename',
    'safe_remove',
    'get_video_total_frames',
]
