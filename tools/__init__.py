"""Angelus 内置工具聚合模块。

本模块统一导入并导出项目预置的核心工具单例，
方便上层注册器一次性加载全部可用工具。

导出内容：
    - ``AGENT_MANAGER_TOOL``: Agent 生命周期管理工具。
    - ``ECHO_TOOL``: 调试回显工具。
    - ``FILE_WRITER_TOOL``: 文件写入工具。
    - ``GRAPH_EDITOR_TOOL``: 执行图编辑工具。
    - ``WEB_SEARCH_TOOL``: 网络搜索工具。
"""

from .agent_manager_tool import TOOL as AGENT_MANAGER_TOOL
from .echo_tool import TOOL as ECHO_TOOL
from .file_writer_tool import TOOL as FILE_WRITER_TOOL
from .graph_editor_tool import TOOL as GRAPH_EDITOR_TOOL
from .web_search_tool import TOOL as WEB_SEARCH_TOOL

__all__ = [
    "AGENT_MANAGER_TOOL",
    "ECHO_TOOL",
    "FILE_WRITER_TOOL",
    "GRAPH_EDITOR_TOOL",
    "WEB_SEARCH_TOOL",
]
