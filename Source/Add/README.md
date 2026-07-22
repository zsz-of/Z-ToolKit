# Z-ToolKit 模块开发规范

Z-ToolKit 是基于 Python + ttk 构建的视频/字幕处理工具集主程序。主程序负责加载 `Add/` 目录下的业务模块，统一管理外部 exe 工具、pip 依赖、配置持久化、日志显示和标签页布局。模块开发者只需在 `Add/` 下创建文件夹形式的模块包，即可被主程序自动加载。

---

## 一、核心原则

1. **修改或新增模块时，原则上不允许修改主程序（`Z-ToolKit.py`）和其他模块**。新增模块只需在 `Add/` 文件夹下创建子文件夹（Python 包），主程序启动时自动加载。
2. **模块间相互独立**，禁止直接导入其他业务模块。公共能力统一从 `common` 包导入。
3. **必须修改主程序或其他模块时，须得到用户明确同意**才能进行。
4. **公共组件优先**：相似度超过 30% 的逻辑必须提取到 `common/` 中，禁止模块内复制实现。
5. **验证即真理**：任何修改必须通过 `python -m py_compile` 语法检查和相关功能验证。

---

## 二、项目结构

```
d:\Code\Trae\
├── Z-ToolKit.py              # 主程序（入口）
├── Add/                      # 业务模块目录
│   ├── README.md             # 本文档
│   ├── module_base.py        # 兼容层（重导出 common 包，将在迁移完成后删除）
│   ├── common/               # 公共组件包
│   │   ├── __init__.py
│   │   ├── tab_module.py            # TabModule 基类
│   │   ├── scrollable_container.py  # 可滚动容器
│   │   ├── file_selector.py         # 统一文件选择器
│   │   ├── encoding_options_panel.py # 视频编码选项面板
│   │   ├── pageable_notebook.py     # 可翻页标签页组件
│   │   ├── treeview_helpers.py      # 可滚动 Treeview 工具
│   │   └── utils.py                 # format_size / sanitize_filename / ...
│   ├── 动漫自动分类/         # 各业务模块（文件夹形式，文件夹名为中文 TAB_NAME）
│   ├── 重复文件检查/
│   ├── M3U8合并/
│   ├── 视频分辨率检查/
│   ├── SRT转ASS/
│   ├── 字幕转换/
│   ├── 字幕导出/
│   ├── 字幕内封MKV/
│   ├── 字幕删除/
│   ├── 字幕子集化/           # 复杂模块，按职责拆分为 20 个文件
│   ├── Trae CN备份/
│   ├── 视频编码转换/
│   ├── 视频缩放/
│   └── 实况照片互转/         # 实况照片互转 + 从视频制作动态照片（12 个文件：core/jpeg_xmp_utils/vivo_mp4_utils/apple_livephoto_utils/pair_file_selector/__init__/video_player/video_config_dialog/batch_config_dialog/video_processor/best_frame_selector/upscayl_runner）
└── Tools/                    # 外部 exe 工具集中存放
    ├── 7z/                   # 7z.exe + 7z.dll + SFX 模块
    ├── ffmpeg/               # ffmpeg.exe + 依赖 DLL
    ├── ffprobe/              # ffprobe.exe + 依赖 DLL
    ├── hb-subset/            # hb-subset.exe
    ├── mkvextract/           # mkvextract.exe（静态链接）
    ├── mkvmerge/             # mkvmerge.exe（静态链接）
    └── upscayl-bin/          # upscayl-bin.exe + models/（AI 图像超分，实况照片互转模块视频模式可选使用）
```

### 模块文件夹命名规范

- 每个模块**必须**是一个 Python 包（文件夹中包含 `__init__.py`）。
- 文件夹名使用**中文**（取自模块的 `TAB_NAME`，移除括号等不合法字符），便于用户在文件系统中识别。
- 由于 Python 3 PEP 3131 允许非 ASCII 标识符，`importlib.import_module("动漫自动分类")` 合法，主程序可直接加载。
- 模块内部使用相对导入（`from .logic import ...`），重命名父文件夹不影响导入。

---

## 三、模块结构

每个模块的 `__init__.py` 需定义一个继承 `TabModule` 的类，并实现必要的方法。

### 最小示例

```python
# Add/我的模块/__init__.py
from common import TabModule

class MyModule(TabModule):
    TAB_NAME = "我的模块"
    TAB_ORDER = 50
    PIP_DEPENDENCIES = []           # 必需 pip 依赖
    OPTIONAL_PIP_DEPENDENCIES = []  # 可选 pip 依赖
    EXE_REQUIREMENTS = []           # 所需外部 exe
    CONFIG_KEY = "MyModule"         # 配置键名（可选，默认用 TAB_NAME）

    def build_ui(self, parent):
        # 构建标签页 UI（主程序已统一包裹 ScrollableContainer，模块直接在 parent 上构建）
        pass

    def save_config(self, config):
        config[self.config_key] = {"key": "value"}

    def load_config(self, config):
        value = config.get("key", "default")

    def clear_memory(self):
        # 重置所有配置变量为默认值
        pass
```

### 类属性说明

| 属性 | 类型 | 说明 |
|------|------|------|
| `TAB_NAME` | str | 标签页显示名称（必填） |
| `TAB_ORDER` | int | 标签页排序，数字越小越靠前（默认 100） |
| `PIP_DEPENDENCIES` | list[str] | 必需 pip 依赖列表，缺失时**阻止模块加载** |
| `OPTIONAL_PIP_DEPENDENCIES` | list[str] | 可选 pip 依赖列表，缺失时仅显示警告，不阻止加载 |
| `EXE_REQUIREMENTS` | list[str] | 所需外部 exe 列表，由主程序统一管理 |
| `CONFIG_KEY` | str | zAPP 配置文件中的键名（默认使用 TAB_NAME） |

### 复杂模块拆分规范

**本程序不强制执行 350 行文件长度限制**。由于主程序已按模块化设计，每个模块独立维护，文件长度对维护性的影响有限。以下原则取代固定行数限制：

- **优先合并**：模块应尽量保持为单个 `__init__.py` 文件，避免无维护意义的拆分。简单模块（如 `M3U8合并`、`SRT转ASS`）应将辅助逻辑（`logic.py`、`ass_converter.py`）合并到 `__init__.py` 中。
- **按功能拆分**：对于复杂模块，可按功能边界拆分为多个文件，每个文件承担明确的职责。允许的拆分维度包括：
  - **核心功能**：算法、数据结构、业务逻辑（如 `core.py`）
  - **辅助控件**：自定义 UI 组件、文件选择器（如 `pair_file_selector.py`）
  - **工具函数**：格式解析、字节操作等纯函数（如 `jpeg_xmp_utils.py`）
  - **GUI 层**：标签页构建、事件绑定（`__init__.py`）
- **Mixin 模式**：极其复杂的模块（如 `字幕子集化`，20+ 文件）可采用 Mixin 模式，将不同职责的实现拆分到多个 Mixin 文件，主类通过多继承组合。
- **禁止无意义拆分**：不要为了规避行数限制而将紧耦合的代码拆到多个文件中，这会增加跳转成本、破坏可读性。
- 模块内部使用相对导入（`from .logic import ...`、`from .ass_parser import ...`）。

### 生命周期方法

| 方法 | 调用时机 |
|------|----------|
| `build_ui(parent)` | 首次打开标签页时调用（延迟构建） |
| `on_tab_activated()` | 标签页被激活时调用 |
| `on_tab_deactivated()` | 标签页被切换离开时调用 |
| `stop_processing()` | 主程序在切换标签页时调用（用于停止当前处理） |
| `is_processing()` | 返回是否正在处理中 |
| `cleanup()` | 程序关闭时清理资源 |
| `save_config(config)` | 保存模块配置到共享配置字典 |
| `load_config(config)` | 从模块专属配置子字典加载配置 |
| `clear_memory()` | 用户点击"清除记忆"时调用，重置所有配置为默认值 |

---

## 四、主程序接口规范

模块通过 `self.host`（`HostInterface` 实例）与主程序交互。所有接口定义在 `Z-ToolKit.py` 的 `HostInterface` 类中。

### 4.1 日志接口

```python
# 记录日志（level: 'info' / 'warning' / 'error' / 'critical'）
self.log('info', "处理完成")
# 等价于
self.host.log_message('info', "处理完成", self.TAB_NAME)

# 清空当前模块的错误日志
self.host.clear_error_log(self.TAB_NAME)
```

**日志行为**：
- `info` / `warning`：写入日志标签页。
- `error` / `critical`：写入日志标签页，并**自动切换到错误日志选项卡**。
- 日志条目上限 5000 条，超出后保留最近 4000 条。

### 4.2 处理状态管理

```python
# 开始处理（禁用标签页切换、清除按钮等）
self.host.set_processing_state(self.tab_widget, True)

# 结束处理
self.host.set_processing_state(self.tab_widget, False)

# 发生错误时结束处理（标记错误状态）
self.host.set_processing_state(self.tab_widget, False, has_error=True)
```

### 4.3 外部 exe 工具接口

**重要：所有外部 exe 的调用必须使用统一方法 `get_exe_path()`，禁止使用 `or 'ffmpeg'` 等回退处理。**

```python
# 获取 exe 路径（返回完整路径字符串，未配置则返回 None）
ffmpeg_path = self.get_exe_path('ffmpeg')
ffprobe_path = self.get_exe_path('ffprobe')
mkvextract_path = self.get_exe_path('mkvextract')
mkvmerge_path = self.get_exe_path('mkvmerge')
hb_subset_path = self.get_exe_path('hb-subset')
seven_z_path = self.get_exe_path('7z')

# 使用示例
cmd = [ffmpeg_path, '-y', '-i', input_path, output_path]
subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
```

**查找优先级**（由主程序 `_find_exe_in_path` 实现）：
1. `Tools/<name>/<name>.exe`（工作目录下的集中工具目录）
2. 系统 PATH 环境变量
3. 用户手动指定（外部工具选项卡中配置）

**禁止回退处理的原因**：标签页访问控制确保用户配置好外部 exe 后才能打开标签页，因此模块加载时 exe 路径必然已配置。使用 `or 'ffmpeg'` 回退会绕过此机制，导致在未配置时仍尝试调用裸命令名而失败。

支持的外部 exe 名称：

| 名称 | 用途 | 所在目录 |
|------|------|----------|
| `ffmpeg` | 视频处理 | `Tools/ffmpeg/` |
| `ffprobe` | 视频信息探测 | `Tools/ffprobe/` |
| `mkvextract` | MKV 字幕提取 | `Tools/mkvextract/` |
| `mkvmerge` | MKV 合并/混流 | `Tools/mkvmerge/` |
| `hb-subset` | 字体子集化 | `Tools/hb-subset/` |
| `7z` | 7-Zip 压缩/哈希计算 | `Tools/7z/` |

### 4.4 其他接口

```python
# 在主线程调度回调（线程安全，所有 UI 更新必须通过此方法）
self.after(0, lambda: self._update_ui())
self.after(100, self._refresh_progress, current, total)

# 获取根窗口
root = self.root

# 显示对话框
self.host.show_error("错误", "消息")
self.host.show_warning("警告", "消息")
self.host.show_info("信息", "消息")

# 切换到错误日志选项卡（跨页查找，自动翻页）
self.host.switch_to_error_log()

# 立即保存所有模块的配置到 zAPP（用于重要配置修改后即时持久化）
self.host.save_config_now()
```

#### `save_config_now()` 使用规范

默认情况下配置仅在程序退出时保存。当用户修改了重要配置（如目录路径、编码器选择等）后，应调用此接口立即持久化，避免程序异常退出导致配置丢失。

```python
def _select_output_dir(self):
    directory = filedialog.askdirectory()
    if directory:
        self.output_dir = directory
        self.host.save_config_now()  # 立即保存，避免异常退出丢失
```

### 4.5 管理员权限请求

模块可通过 `self.create_admin_request_button()` 创建一个由主程序管理的
管理员权限请求按钮。按钮的状态和点击逻辑完全由主程序控制，模块只能指定
按钮的位置、外观和重启后跳转的选项卡。

#### 接口签名

```python
button = self.create_admin_request_button(
    parent, return_tab=None, text="请求管理员权限", **kwargs
)
```

#### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `parent` | widget | （必填） | 按钮的父容器 |
| `return_tab` | str | `self.TAB_NAME` | 重启后跳转的选项卡名称；`None` 默认使用本模块的 `TAB_NAME` |
| `text` | str | `"请求管理员权限"` | 按钮文本 |
| `**kwargs` | — | — | 传递给 `ttk.Button` 的其他参数（如 `width`、`style` 等） |

#### 返回值

返回 `ttk.Button` 实例。模块可对其进行 `pack` / `grid` 布局，但**不应**修改其
`command` 或 `state`（状态由主程序管理）。

#### 按钮行为（由主程序管理）

| 运行模式 | 按钮状态 | 点击行为 |
|---------|---------|---------|
| 管理员模式 | **禁用**（不可点击） | — |
| 非管理员模式 | **启用**（可点击） | 直接触发 Windows UAC 对话框 |

- **UAC 通过**：主程序保存配置并退出，以管理员身份重启，跳转到 `return_tab` 选项卡
- **UAC 未通过**（用户拒绝或出错）：弹出警告提示框 `"用户未授权 UAC，无法以管理员身份重启程序。"`

模块**不能**干涉按钮的运行逻辑和可否点击状态，主程序也不需要模块提供请求原因
说明——直接使用 Windows 自带的 UAC 对话框即可，无需程序二次确认。

#### 重启机制

1. 用户点击按钮后，主程序调用 `_restart_application(target_tab=return_tab, as_admin=True)`
2. 主程序保存当前配置，然后使用 `ctypes.windll.shell32.ShellExecuteW(..., "runas", ...)`
   触发 UAC，以管理员权限启动新进程
3. `ShellExecuteW` 返回值 > 32 表示 UAC 通过，主程序退出；返回值 ≤ 32 表示未通过，
   弹出警告提示框
4. 新进程启动后，`main()` 解析 `--tab` 参数，延迟 200ms 调用 `notebook.select_by_text(name)` 跳转

**兼容模式**：
- **PyInstaller EXE**：直接重启 `Z-ToolKit.exe`
- **Python 脚本**：通过 `python.exe` 运行 `Z-ToolKit.py`

#### 使用示例

```python
class MyModule(TabModule):
    TAB_NAME = "我的模块"

    def build_ui(self, parent):
        main = ttk.Frame(parent)
        main.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        # 创建管理员权限请求按钮（由主程序管理状态和点击逻辑）
        self.create_admin_request_button(
            btn_frame, return_tab=self.TAB_NAME
        ).pack(side=tk.LEFT)

        # 正常构建 UI ...
```

#### 注意事项

- **重启丢失状态**：主程序重启会丢失所有模块的当前状态（未保存的配置除外）。
  重要配置应在 `save_config()` 中持久化到 zAPP。
- **管理员检测**：主程序使用 `ctypes.windll.shell32.IsUserAnAdmin()` 检测当前进程
  是否以管理员权限运行，模块无需自行检测。
- **开发者模式**：Windows 10 1703+ 开启开发者模式后，普通用户可创建符号链接，
  无需管理员权限。但 WinFsp 虚拟磁盘等仍可能需要管理员权限访问。

---

## 五、公共组件规范

公共组件统一存放在 `Add/common/` 目录，每个组件一个独立的 py 文件。模块应直接从 `common` 包导入，禁止在模块内复制实现。

### 5.1 导入规范

```python
# 推荐：从 common 包导入
from common import TabModule, ScrollableContainer
from common import FileSelector, MKVEmbedFileSelector
from common import EncodingOptionsPanel, format_size

# 兼容：从 module_base 导入（兼容层，将在迁移完成后删除）
from module_base import TabModule, UnifiedFileSelector
```

### 5.2 TabModule 基类

所有模块的基类，位于 `common/tab_module.py`。提供：
- `self.host`：HostInterface 实例
- `self.tab_widget`：标签页 widget
- `self.config_key`：配置键名
- `self.log(level, message)`：日志快捷方法
- `self.get_exe_path(name)`：获取外部 exe 路径
- `self.after(ms, callback, *args)`：主线程调度

### 5.3 ScrollableContainer

可滚动容器，位于 `common/scrollable_container.py`。

**重要**：主程序已统一为所有模块标签页包裹 `ScrollableContainer`，模块**不需要**再自行包裹。模块直接在 `build_ui(parent)` 的 `parent` 参数上构建 UI 即可，`parent` 已经是可滚动容器的内部 frame。

```python
def build_ui(self, parent):
    # parent 已经是 ScrollableContainer 的内部 frame
    main_frame = ttk.Frame(parent, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)
    # ...
```

### 5.4 FileSelector（统一文件选择器）

统一的文件/文件夹选择器，位于 `common/file_selector.py`。支持通过 `filter_func` 接口实现过滤条件。

```python
from common import FileSelector

# 基础用法：视频文件选择器
selector = FileSelector(parent, supported_types='video')

# 自定义过滤条件（用于 MKV 内封等场景）
def mkv_filter(filename):
    return filename.lower().endswith('.mkv')

selector = FileSelector(parent, filter_func=mkv_filter)

# 获取选中的文件列表
files = selector.get_files()
```

**兼容别名**：
- `UnifiedFileSelector`：等同于 `FileSelector`，保留用于旧模块兼容。
- `MKVEmbedFileSelector`：等同于传入 MKV 过滤条件的 `FileSelector`。

### 5.5 EncodingOptionsPanel

视频编码选项面板，位于 `common/encoding_options_panel.py`。封装编码器选择、CRF、压缩模式、色彩深度，被 `视频编码转换` 和 `视频缩放` 共用。

```python
from common import EncodingOptionsPanel

class MyModule(TabModule):
    def build_ui(self, parent):
        self.encode_panel = EncodingOptionsPanel(right_frame)

    def process(self):
        encode_args = self.encode_panel.build_ffmpeg_args()
        pixel_format = self.encode_panel.get_pixel_format()
        cmd = [ffmpeg_path, '-y', '-i', input_path]
        cmd.extend(encode_args)
        cmd.extend(['-vf', f'format={pixel_format}', output_path])

    def save_config(self, config):
        self.encode_panel.save_config()
        config[self.config_key] = self.encode_panel.config_dict

    def load_config(self, config):
        self.encode_panel.load_config(config)

    def clear_memory(self):
        self.encode_panel.reset()
```

### 5.6 PageableNotebook

可翻页标签页组件，位于 `common/pageable_notebook.py`。主程序使用此组件作为顶层标签页容器，当标签页数量超过窗口宽度时自动出现翻页按钮。

**关键特性**：
- **分页显示**：标签页宽度超过容器时自动分页，顶部显示翻页按钮（◀ ▶）。
- **Pinned 标签页**：通过 `add(tab, pinned=True, **kwargs)` 添加常驻标签页，始终显示在最右端，不参与分页。用于"错误日志"等需要随时访问的标签页。
- **翻页按钮禁用**：通过 `set_buttons_enabled(False)` 禁用翻页按钮。任务进行时主程序自动禁用翻页按钮，防止用户切换到其他页的标签页。
- **跨页查找**：通过 `select_by_text(text)` 在所有标签页（包括不可见的）中按文本查找并选中，自动切换页面。

模块开发者通常**不直接使用**此组件。主程序通过 `select_by_text()` 跨页查找并切换标签页：

```python
# 主程序内部使用
self.notebook.select_by_text('错误日志')
self.notebook.select_by_text('外部工具')

# 添加常驻标签页（pinned=True，始终显示在最右端）
self.notebook.add(tab, text="错误日志", pinned=True)

# 任务进行时禁用翻页按钮
self.notebook.set_buttons_enabled(False)
```

### 5.7 公共工具函数

位于 `common/utils.py`，模块应直接导入使用，禁止在模块内复制实现。

| 函数 | 用途 |
|------|------|
| `format_size(size_bytes)` | 将字节数格式化为人类可读字符串（B/KB/MB/GB） |
| `sanitize_filename(name)` | 清理文件名中的非法字符 |
| `safe_remove(path)` | 安全删除文件（捕获异常） |
| `get_video_total_frames(video_path, ffprobe_path)` | 通过 ffprobe 获取视频总帧数 |

### 5.8 Treeview 工具

位于 `common/treeview_helpers.py`，提供 `create_scrollable_tree()` 函数，用于快速创建带滚动条的 Treeview。

---

## 六、配置系统规范

主程序使用 zAPP 配置系统，所有模块配置统一存储在 `%USERPROFILE%\.zAPP\video_tool_config.json` 中。

### 6.1 配置文件结构

```json
{
    "MyModule": {
        "encoder": "AV1",
        "crf": 18,
        "output_dir": "C:/output"
    },
    "另一个模块": {
        "key": "value"
    }
}
```

### 6.2 保存配置

```python
def save_config(self, config):
    config[self.config_key] = {
        "encoder": self.encoder_var.get(),
        "crf": self.crf_var.get(),
        "output_dir": self.output_dir
    }
```

### 6.3 加载配置

```python
def load_config(self, config):
    # 必须使用 .get(key, default) 提供默认值，避免因配置缺失导致崩溃
    self.encoder_var.set(config.get("encoder", "AV1"))
    self.crf_var.set(config.get("crf", 18))
    self.output_dir = config.get("output_dir", "")
```

### 6.4 清除记忆

```python
def clear_memory(self):
    """重置所有配置变量为默认值"""
    self.encoder_var.set("AV1")
    self.crf_var.set(18)
    self.output_dir = ""
```

### 6.5 配置规范要求

- **必须实现** `save_config` / `load_config` / `clear_memory` 三方法，即使为空实现。
- `load_config` 必须使用 `config.get(key, default)` 提供默认值。
- 重要配置修改后应调用 `self.host.save_config_now()` 立即持久化。
- 配置文件读取失败不报错，静默使用默认值。

---

## 七、日志规范

### 7.1 日志级别

| 级别 | 显示标签 | 颜色 | 用途 |
|------|----------|------|------|
| `info` | `[INFO]` | `#569cd6`（蓝） | 正常流程信息 |
| `warning` | `[WARN]` | `#dcdcaa`（黄） | 警告信息，不影响继续执行 |
| `error` | `[ERROR]` | `#ce9178`（橙） | 错误信息，**自动切换到错误日志选项卡** |
| `critical` | `[FATAL]` | `#f44747`（红） | 致命错误，**自动切换到错误日志选项卡** |

### 7.2 日志格式

```
[LEVEL] [YYYY-MM-DD HH:MM:SS] [来源标签页] 消息内容
```

示例：
```
[INFO] [2026-06-27 14:30:15] [视频编码转换] 开始转换: input.mp4
[ERROR] [2026-06-27 14:30:16] [视频编码转换] ffmpeg 退出码非零: 1
```

### 7.3 调用规范

```python
# 推荐：使用 self.log（自动以 TAB_NAME 为来源）
self.log('info', f"开始处理: {file_path}")
self.log('warning', f"跳过不支持的文件: {file_path}")
self.log('error', f"处理失败: {e}")

# 等价写法：显式调用 host
self.host.log_message('info', "消息", self.TAB_NAME)
```

### 7.4 日志条目管理

- 日志保留上限 5000 条，超出后自动裁剪保留最近 4000 条。
- 用户可通过错误日志选项卡的级别过滤复选框筛选显示。
- `self.host.clear_error_log(tab_name)` 可清空指定来源的日志。

---

## 八、UI 规范

### 8.1 框架与显示

- GUI 框架使用 **ttk**（禁止使用 tk 风格组件，除 `tk.Canvas` / `tk.Text` 等无 ttk 替代品的组件）。
- 程序启动时**隐藏命令提示符窗口**。
- 必须**启用 DPI 感知**（Per-Monitor V2，由主程序统一处理）。

### 8.2 字体规范

**统一字体族**：使用 `Microsoft YaHei UI`（即 ttk 默认字体 `TkDefaultFont` 的字体族）。
禁止使用 `Arial`、`Segoe UI`、`SimSun` 等其他字体作为中文显示字体。

> **原因**：`Arial` 不含中文字形，Tkinter 会触发系统字体回退，导致不同汉字
> 回退到不同字形，宽度不一致（部分 23px、部分 24px）。使用 `Microsoft YaHei UI`
> 后所有汉字宽度完全一致，视觉无差异。

| 用途 | 字体 | 大小 | 样式 |
|------|------|------|------|
| 主程序标题 | Microsoft YaHei UI | 16 | bold |
| 占位提示文本 | Microsoft YaHei UI | 11 | normal |
| 普通文本/标签 | Microsoft YaHei UI | 10 | normal |
| 日志/命令行 | Consolas | 10 | normal |
| 日志（紧凑） | Consolas | 9 | normal |

> **ttk 控件默认字体**：不指定 `font` 参数时，ttk 控件使用 `TkDefaultFont`
> （Microsoft YaHei UI 9pt）。仅在需要特殊字号或粗体时显式指定 `font` 参数。

### 8.3 颜色规范

**统一固定调色板**，禁止使用颜色名（如 `'red'`、`'green'`），必须使用十六进制色值。

| 语义 | 色值 | 用途 |
|------|------|------|
| 成功 | `#228B22` | 成功状态、已安装、已找到 |
| 错误 | `#CC0000` | 错误状态、未安装、未找到、无效项 |
| 说明 | `gray` | 提示文本、禁用状态、说明文字 |
| 默认文本 | `black` | 默认前景色 |
| 日志-INFO | `#569cd6` | info 级别日志 |
| 日志-WARN | `#dcdcaa` | warning 级别日志 |
| 日志-ERROR | `#ce9178` | error 级别日志 |
| 日志-CRITICAL | `#f44747` | critical 级别日志 |

**例外**：业务必需的色块（如 SRT转ASS 的字幕颜色预览画布）可使用业务相关的任意色值，不属于 UI 装饰色范畴。

### 8.4 布局规范

#### LabelFrame

- 所有 `ttk.LabelFrame` 统一使用 `padding="5"`（或 `padding=5`）。
- 禁止使用 `padding="10"` 或其他值。

#### 按钮布局

- **操作按钮**（开始/停止/删除/生成报告等）：统一 `side=tk.RIGHT, padx=5`，主操作按钮在最右。
- **表单输入按钮**（浏览.../选择目录等紧邻 Entry 的按钮）：使用 `side=tk.LEFT` 或 `side=tk.RIGHT`，与同行的 Entry 控件紧邻。
- 同一按钮行内的多个操作按钮统一使用 `side=tk.RIGHT`，禁止混用。

#### Treeview

- 统一使用 `show='headings'`（隐藏树形展开图标）。
- 统一使用 `height=1`（让 Treeview 高度由父容器布局决定，避免固定高度导致溢出）。
- 列宽根据内容设置，数值列使用 `anchor='e'`，状态列使用 `anchor='center'`。
- 滚动条使用 `ttk.Scrollbar`，垂直滚动条 `orient=tk.VERTICAL`，水平滚动条 `orient=tk.HORIZONTAL`。

#### 选项卡状态

- 开始处理时禁用相关控件（按钮、输入框等）。
- 结束处理时恢复控件状态。
- 通过 `self.host.set_processing_state(self.tab_widget, True/False)` 通知主程序统一管理标签页切换锁。
- **任务进行时**：主程序自动禁用标签页翻页按钮（◀ ▶），防止用户切换到其他页的标签页。
- **错误日志标签页常驻**：错误日志标签页使用 `pinned=True` 常驻最右端，不参与分页，任务进行时用户仍可点击查看日志。

### 8.5 滚动支持

- **主程序已统一为所有模块标签页包裹 `ScrollableContainer`**，模块**不需要**再自行包裹。
- 模块直接在 `build_ui(parent)` 的 `parent` 参数上构建 UI，`parent` 已是可滚动容器的内部 frame。
- `ScrollableContainer` 自动根据内容尺寸启用横向/纵向滚动条，防止组件超出窗口边缘。
- 日志框独立绑定鼠标滚轮事件，并阻止事件冒泡，避免在日志区域滚动时带动主内容区滚动。

### 8.6 列表自适应规范

- 列表（Treeview/Listbox）应根据窗口大小自由调整横向宽度。
- 纵向最小值为**显示两栏**（即至少能完整显示两行内容）。
- 当窗口尺寸小于最小值时，列表被滚动条包裹。
- 放大窗口时扩大列表，多个列表均分多余空间（指高度）。
- 实现方式：使用 `pack(fill=tk.BOTH, expand=True)` 或 `grid(sticky='nsew')` + `grid_rowconfigure(weight=1)`。

### 8.7 自适应布局

- UI 组件应根据内容自动调整高度（y 轴）和宽度（x 轴）。
- 使用 `pack(fill=tk.BOTH, expand=True)` 或 `grid(sticky='nsew')` 实现自适应。
- 主窗口内容区域应采用 Canvas + Frame 结构，Canvas 宽度在窗口缩放时自动调整，防止出现空白边缘。

---

## 九、外部 exe 工具管理规范

### 9.1 工具集中存放

所有外部 exe 工具集中存放在工作目录下的 `Tools/` 文件夹中，**每种工具一个子文件夹，文件夹名称与 exe 文件名一致**（不含 `.exe` 后缀）。

```
Tools/
├── 7z/            # 7z.exe
├── ffmpeg/        # ffmpeg.exe
├── ffprobe/       # ffprobe.exe
├── hb-subset/     # hb-subset.exe
├── mkvextract/    # mkvextract.exe
└── mkvmerge/      # mkvmerge.exe
```

**命名原因**：主程序通过 `Tools/<name>/<name>.exe` 直接拼接路径查找，避免：
- 搜索子文件夹
- 修改模块中的 exe 请求逻辑
- 主程序维护映射表

### 9.2 工具复制规范

- 从环境变量（PATH）中查找到工具后，复制到 `Tools/<name>/` 目录。
- **7z**：仅保留命令行核心（`7z.exe` + `7z.dll`）和扩展文件（`7z.sfx` / `7zCon.sfx` / `License.txt`），**删除 GUI 文件**（`7zFM.exe` / `7zG.exe` / `Uninstall.exe` / `7-zip.chm` / `7-zip.dll`）和冗余模块（`7za.exe` / `7za.dll` / `7zxa.dll`）。
- **ffmpeg / ffprobe**：复制 exe 及所有依赖 DLL（如 `avcodec-*.dll` / `avformat-*.dll` 等）。
- **mkvmerge / mkvextract**：静态链接 exe，可独立运行，无需额外 DLL。

### 9.3 工具清理规范

- 主程序每次退出时自动将 `Add/` 文件夹和主程序位置下的所有 `__pycache__/` 文件夹属性设置为**隐藏**（使用 Windows API `SetFileAttributesW` + `FILE_ATTRIBUTE_HIDDEN`），保持目录整洁。

---

## 十、pip 依赖管理规范

### 10.1 必需依赖（`PIP_DEPENDENCIES`）

模块运行必需的第三方 pip 库。缺失时：
- 主程序阻止该模块标签页加载
- 在外部工具选项卡中显示为红色
- 用户双击可弹出嵌入式命令行窗口安装

```python
class MyModule(TabModule):
    PIP_DEPENDENCIES = ['requests', 'chardet']  # 缺失则阻止加载
```

### 10.2 可选依赖（`OPTIONAL_PIP_DEPENDENCIES`）

模块有降级处理的第三方 pip 库。缺失时：
- 模块仍可正常加载
- 在外部工具选项卡中显示为红色（提示用户）
- 不阻止标签页访问

```python
class MyModule(TabModule):
    OPTIONAL_PIP_DEPENDENCIES = ['fontTools', 'send2trash']  # 模块内有降级处理
```

### 10.3 安装机制

- 主程序只负责检测和补全 pip 库，**不传递路径给模块**。
- 模块自己使用 `import` 导入 pip 库。
- pip 安装窗口实时显示命令回显。
- 安装完成后通过临时 bat 文件自动重启程序（bat 文件名为随机 64 位字母数字，重启后自动删除）。

### 10.4 pip 名与 import 名不一致

部分 pip 包的安装名与 Python import 模块名不一致（如 `opencv-python` 的 import 名是 `cv2`，`Pillow` 的 import 名是 `PIL`）。此时必须使用元组形式 `(install_name, import_name)` 声明，否则主程序的依赖检查会误判为未安装。

```python
class MyModule(TabModule):
    OPTIONAL_PIP_DEPENDENCIES = [
        ('opencv-python', 'cv2'),   # pip install opencv-python，import cv2
        'numpy',                    # pip 名 = import 名，用字符串即可
        ('Pillow', 'PIL'),          # pip install Pillow，import PIL
        ('pillow-heif', 'pillow_heif'),  # 连字符 vs 下划线
    ]
```

主程序内部统一将依赖转为 `(install_name, import_name)` 元组表示：
- 检查是否已安装：用 `import_name` 调用 `importlib.import_module()`
- 显示在表格中：用 `install_name`
- 执行 `pip install`：用 `install_name`

声明规则：
- pip 名 = import 名：使用字符串（如 `'numpy'`、`'requests'`、`'chardet'`）
- pip 名 ≠ import 名：必须使用元组（如 `('opencv-python', 'cv2')`、`('Pillow', 'PIL')`）

---

## 十一、标签页访问控制

主程序在用户点击标签页时执行以下检查：

1. 检查模块的 `EXE_REQUIREMENTS`（必需 exe）中所有 exe 是否已配置。
2. 检查模块的 `PIP_DEPENDENCIES`（必需 pip 库）中所有 pip 库是否已安装。
3. 若有缺失：
   - 不加载模块
   - 显示居中提示页面，告知用户需要补全工具/pip 库
   - 提供"转到外部工具选项卡"按钮
   - 每次切换到该标签页都重新检查
4. 若全部就绪：加载模块并构建 UI。

因此，模块内**无需**处理必需 exe 路径未配置或必需 pip 库未安装的情况。

### 11.1 可选 exe（`OPTIONAL_EXE_REQUIREMENTS`）

可选 exe 缺失时**不阻止模块加载**，模块必须自行处理缺失情况：

```python
class MyModule(TabModule):
    EXE_REQUIREMENTS = ['ffmpeg', 'ffprobe']      # 必需 exe，缺失阻止加载
    OPTIONAL_EXE_REQUIREMENTS = ['upscayl-bin']   # 可选 exe，缺失不阻止加载
```

模块内必须检查可选 exe 是否可用：

```python
def _do_upscale(self):
    upscayl_path = self.get_exe_path('upscayl-bin')
    if upscayl_path is None:
        self.log('warning', "upscayl-bin 未配置，跳过 AI 超分")
        return None  # 降级处理
    # 正常调用 upscayl_path
```

外部工具表格中可选 exe 的显示：
- 名称后追加 `(可选)` 标记
- 已找到：绿色
- 未找到：橙色（区别于必需 exe 未找到的红色）

---

## 十二、开发注意事项

1. **外部 exe 调用必须使用统一方法**：`self.get_exe_path(name)`，禁止使用 `or 'ffmpeg'` 等回退处理。标签页访问控制确保模块加载时 exe 路径已配置。

2. **pip 库由模块自己使用**：主程序只负责检测和补全，不传递路径。模块直接 `import` 即可。

3. **线程安全**：所有 UI 更新必须通过 `self.after()` 调度到主线程。

4. **错误处理**：使用 `self.log('error', ...)` 记录错误，必要时调用 `self.host.clear_error_log()` 清空旧错误。

5. **资源清理**：在 `cleanup()` 中关闭文件句柄、子进程等资源。

6. **配置兼容性**：`load_config` 时使用 `config.get(key, default)` 提供默认值，避免因配置缺失导致崩溃。

7. **防膨胀原则**：相似度超过 30% 的代码必须提取公共抽象到 `common/`，禁止复制粘贴。

8. **文件长度原则**：本程序不强制执行 350 行限制。模块优先合并为单文件；复杂模块按功能边界拆分（核心功能/辅助控件/工具函数/GUI 层），禁止无意义拆分。详见"复杂模块拆分规范"。

9. **subprocess 调用**：必须使用 `creationflags=subprocess.CREATE_NO_WINDOW` 避免弹出命令行窗口。

10. **新增模块流程**：在 `Add/` 下创建中文命名的文件夹 → 创建 `__init__.py` → 实现 `TabModule` 子类 → 主程序启动时自动加载，无需修改主程序。

---

## 十三、现有模块清单

| 模块文件夹 | TAB_NAME | 用途 | EXE 依赖 |
|------------|----------|------|----------|
| 动漫自动分类 | 动漫自动分类 | 按番剧名分类视频文件 | - |
| 重复文件检查 | 重复文件检查 | SHA256 哈希扫描重复文件 | 7z |
| M3U8合并 | M3U8合并 | 合并 M3U8 流媒体为 MP4 | ffmpeg |
| 视频分辨率检查 | 视频分辨率检查 | 检查视频分辨率是否达标 | ffprobe |
| SRT转ASS | SRT转ASS | 将 SRT 字幕转换为 ASS 字幕 | - |
| 字幕转换 | 字幕转换 | 简繁字幕转换（API + 本地） | - |
| 字幕导出 | 字幕导出 | 从 MKV 提取字幕流 | mkvextract |
| 字幕内封MKV | 字幕内封(MKV) | 将字幕内封到 MKV 视频 | mkvmerge |
| 字幕删除 | 字幕删除 | 删除 MKV 中的字幕流 | mkvmerge |
| 字幕子集化 | 字幕子集化 | ASS 字体子集化 + MKV 合并 | mkvextract, mkvmerge, hb-subset |
| Trae CN备份 | Trae-CN备份 | 备份 Trae 配置文件 | 7z |
| 视频编码转换 | 视频编码转换 | 视频编码格式转换 | ffmpeg, ffprobe |
| 视频缩放 | 视频缩放 | 视频分辨率缩放 | ffmpeg, ffprobe |
| 实况照片互转 | 实况照片互转 | vivo/Google/OPPO/小米/三星/Apple LivePhoto 实况照片互转；从视频制作动态照片（片段裁剪+封面帧+AI超分+自动最佳帧选择） | ffmpeg, ffprobe（视频模式）; upscayl-bin（AI超分，可选）; pillow-heif（HEIC 解码，可选） |
