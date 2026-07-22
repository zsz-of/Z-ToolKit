# -*- coding: utf-8 -*-
"""模块基类

所有功能模块均继承 TabModule，并通过 host 接口与主程序交互。
模块通过类属性声明依赖（pip/exe），通过生命周期方法接入主程序。
"""


class TabModule:
    """功能模块基类

    所有功能模块均继承此类，并通过 host 接口与主程序交互。

    类属性（子类覆盖）:
        TAB_NAME: 标签页显示名称（必填）
        TAB_ORDER: 标签页排序（数字越小越靠前，默认 100）
        PIP_DEPENDENCIES: 必需 pip 依赖列表（缺失阻止模块加载）
            元素可为字符串（pip 名=import 名）或元组 (pip 名, import 名)
        OPTIONAL_PIP_DEPENDENCIES: 可选 pip 依赖列表（缺失仅警告）
            元素形式同 PIP_DEPENDENCIES
        CONFIG_KEY: zAPP 配置子字典键名（默认使用 TAB_NAME）
        EXE_REQUIREMENTS: 必需外部 exe 列表（缺失阻止模块加载）
        OPTIONAL_EXE_REQUIREMENTS: 可选外部 exe 列表（缺失不阻止加载）
            模块必须自行处理缺失情况（如 is_available() 检查 + 功能降级）

    生命周期方法（子类按需实现）:
        build_ui(parent): 构建标签页 UI（必须实现）
        on_tab_activated(): 标签页激活时回调
        on_tab_deactivated(): 标签页失活时回调
        stop_processing(): 停止当前处理
        is_processing(): 是否正在处理中
        cleanup(): 程序关闭时清理资源
        save_config(config): 保存配置到共享字典
        load_config(config): 从模块专属子字典加载配置
        clear_memory(): 清除本模块记忆（重置为默认值）
    """
    TAB_NAME = ""          # 标签页显示名称
    TAB_ORDER = 100        # 标签页排序（数字越小越靠前）
    PIP_DEPENDENCIES = []  # 必需 pip 依赖列表（如 ['requests', 'chardet']），缺失时阻止模块加载
                           # 元素可为字符串（pip 名=import 名）或元组 (pip 名, import 名)
    OPTIONAL_PIP_DEPENDENCIES = []  # 可选 pip 依赖列表，缺失时仅显示警告，不阻止加载
                           # 元素形式同 PIP_DEPENDENCIES
    CONFIG_KEY = ""        # zAPP 配置文件中的键名（默认使用 TAB_NAME）
    EXE_REQUIREMENTS = []  # 必需外部 exe 列表（如 ['ffmpeg', 'ffprobe']），缺失时阻止模块加载
    OPTIONAL_EXE_REQUIREMENTS = []  # 可选外部 exe 列表（如 ['upscayl-bin']），缺失时不阻止加载
                           # 模块必须自行处理缺失情况（功能降级或日志提示）

    def __init__(self, host):
        self.host = host          # 主程序接口（HostInterface）
        self.tab_widget = None    # 标签页 widget
        self._ui_built = False    # UI 是否已构建

    def build_ui(self, parent):
        """构建标签页 UI。首次打开标签页时调用"""
        raise NotImplementedError

    def on_tab_activated(self):
        """标签页被激活时调用"""
        pass

    def on_tab_deactivated(self):
        """标签页被切换离开时调用"""
        pass

    def stop_processing(self):
        """停止当前处理（由主程序在切换标签页时调用）"""
        pass

    def is_processing(self):
        """是否正在处理中"""
        return False

    def cleanup(self):
        """程序关闭时清理资源"""
        pass

    def save_config(self, config):
        """保存模块配置到共享配置字典。

        config 是整个配置字典，模块应将自己的配置保存到 config[self.config_key] 中。
        """
        pass

    def load_config(self, config):
        """从模块专属配置字典加载配置。

        config 是该模块的专属配置子字典（已由主程序提取）。
        """
        pass

    def clear_memory(self):
        """清除本模块的记忆（重置所有配置变量为默认值）。

        由主程序在用户点击"清除记忆"时调用。
        """
        pass

    @property
    def config_key(self):
        """获取配置键名"""
        return self.CONFIG_KEY or self.TAB_NAME

    # ========== 便捷方法（转发到 host）==========

    def log(self, level, message):
        """记录日志

        参数:
            level: 日志级别（'info' / 'warning' / 'error' / 'critical'）
            message: 日志消息
        """
        self.host.log_message(level, message, self.TAB_NAME)

    def after(self, ms, callback, *args):
        """在主线程调度回调（线程安全）

        参数:
            ms: 延迟毫秒数
            callback: 回调函数
            *args: 回调函数参数
        """
        return self.host.after(ms, callback, *args)

    def get_exe_path(self, name):
        """获取外部 exe 路径（由主程序外部工具管理统一提供）

        参数:
            name: exe 名称（如 'ffmpeg'、'ffprobe'、'mkvextract'、'mkvmerge'、'hb-subset'、'7z'）

        返回:
            exe 完整路径字符串，若未配置则返回 None

        注意:
            禁止使用 `or 'ffmpeg'` 等回退处理。标签页访问控制确保模块加载时 exe 路径已配置。
        """
        return self.host.get_exe_path(name)

    def create_admin_request_button(self, parent, return_tab=None,
                                    text="请求管理员权限", **kwargs):
        """创建一个由主程序管理的管理员权限请求按钮

        按钮行为由主程序完全管理，模块只能指定按钮的父容器、外观和重启后
        跳转的选项卡，不能干涉按钮的运行逻辑和可否点击状态：
        - 管理员模式下按钮自动禁用
        - 非管理员模式下按钮可点击
        - 点击后直接触发 Windows UAC（无需程序二次确认）
        - UAC 通过则保存配置并以管理员身份重启程序
        - UAC 未通过则弹出警告提示框说明用户未授权

        参数:
            parent: 按钮的父容器
            return_tab: 重启后跳转的选项卡名称；None 默认使用 self.TAB_NAME
            text: 按钮文本（默认"请求管理员权限"）
            **kwargs: 传递给 ttk.Button 的其他参数（如 width、style 等）

        返回:
            ttk.Button 实例
        """
        if return_tab is None:
            return_tab = self.TAB_NAME
        return self.host.create_admin_request_button(
            parent, return_tab, text, **kwargs)

    @property
    def root(self):
        """获取根窗口"""
        return self.host.root
