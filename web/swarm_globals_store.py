"""Swarm 全局变量持久化模块。

提供将 GlobalVariablesConfig 序列化为 TOML 片段、读取现有配置以及
安全地替换/追加到 manifest.toml 的能力。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import re

from core.swarm_spec import GlobalVariablesConfig, SwarmLoaderError
from web.utils import to_jsonable


def serialize_global_variables(config: GlobalVariablesConfig) -> Dict[str, Any]:
    """将全局变量配置转换为 JSON 安全的字典。

    Args:
        config: 全局变量配置对象。

    Returns:
        包含 values 与 visibility 的字典。
    """
    return {
        "values": to_jsonable(dict(config.values)),
        "visibility": {key: list(value) for key, value in config.visibility.items()},
    }


def load_global_variables(manifest_path: Path) -> GlobalVariablesConfig:
    """从指定 manifest 文件中加载全局变量配置。

    Args:
        manifest_path: manifest.toml 的路径。

    Returns:
        解析后的 GlobalVariablesConfig。
    """
    from core.swarm_spec import load_swarm_manifest

    _, manifest = load_swarm_manifest(manifest_path.parent)
    return manifest.global_variables


def save_global_variables(manifest_path: Path, globals_config: GlobalVariablesConfig) -> None:
    """将全局变量配置写回 manifest.toml。

    采用替换/追加策略：若文件已存在 [globals] 段，则整段替换；
    否则追加到文件末尾。

    Args:
        manifest_path: manifest.toml 的路径。
        globals_config: 待保存的全局变量配置。

    Raises:
        SwarmLoaderError: manifest 文件不存在时抛出。
    """
    path = Path(manifest_path)
    if not path.exists():
        raise SwarmLoaderError(f"Manifest file not found: {path}")
    text = path.read_text(encoding="utf-8")
    section = _render_globals_section(globals_config)
    updated = _replace_or_append_section(text, section)
    path.write_text(updated, encoding="utf-8")


def _render_globals_section(config: GlobalVariablesConfig) -> str:
    """将全局变量渲染为 TOML [globals] 段落。

    Args:
        config: 全局变量配置。

    Returns:
        TOML 文本片段（包含尾部换行）。
    """
    lines = ["[globals]"]
    for key in sorted(config.values.keys()):
        lines.append(f"{key} = {_render_toml_value(config.values[key])}")

    if config.visibility:
        lines.append("")
        lines.append("[globals.visibility]")
        for key in sorted(config.visibility.keys()):
            agents = [str(item) for item in config.visibility.get(key, [])]
            lines.append(f"{key} = {_render_toml_array(agents)}")
    lines.append("")
    return "\n".join(lines)


def _replace_or_append_section(text: str, section: str) -> str:
    """在 TOML 文本中替换现有 [globals] 段，或在末尾追加新段。

    Args:
        text: 原始 manifest.toml 全文。
        section: 新的 [globals] 段文本。

    Returns:
        更新后的 TOML 全文。
    """
    lines = text.splitlines()
    start_idx = None
    end_idx = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[globals]":
            start_idx = index
            end_idx = index + 1
            # 向后扫描直到遇到下一个非 [globals.* 的顶级段落
            while end_idx < len(lines):
                next_line = lines[end_idx].strip()
                if re.match(r"^\[", next_line) and not next_line.startswith("[globals."):
                    break
                end_idx += 1
            break

    section_lines = section.rstrip("\n").splitlines()
    if start_idx is None:
        # 原文件无 [globals] 段，追加到末尾并确保空行分隔
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(section_lines)
        return "\n".join(lines) + ("\n" if not text.endswith("\n") else "")

    return "\n".join(lines[:start_idx] + section_lines + lines[end_idx:]) + ("\n" if not text.endswith("\n") else "")


def _render_toml_value(value: Any) -> str:
    """将单个 Python 值渲染为 TOML 字面量。

    支持 None、bool、数字、字符串、dict、list/tuple/set。

    Args:
        value: 待渲染的 Python 值。

    Returns:
        TOML 字面量字符串。
    """
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return _render_toml_string(value)
    if isinstance(value, dict):
        return _render_toml_inline_table(value)
    if isinstance(value, (list, tuple, set)):
        return _render_toml_array(list(value))
    return _render_toml_string(str(value))


def _render_toml_array(values: list[Any]) -> str:
    """将列表渲染为 TOML 数组字面量。"""
    return "[" + ", ".join(_render_toml_value(item) for item in values) + "]"


def _render_toml_inline_table(value: Dict[str, Any]) -> str:
    """将字典渲染为 TOML 内联表。"""
    items = [f"{key} = {_render_toml_value(item)}" for key, item in value.items()]
    return "{ " + ", ".join(items) + " }"


def _render_toml_string(value: str) -> str:
    """为 TOML 字符串添加双引号并转义内部字符。"""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
