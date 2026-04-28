"""通用工具函数。

提供将运行时对象递归转换为 JSON 安全结构的能力，供序列化层与
路由响应统一调用。
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def to_jsonable(value: Any) -> Any:
    """将任意运行时对象递归转换为 JSON 可序列化的原生 Python 结构。

    处理顺序：
    1. 标量（None / str / int / float / bool）直接返回。
    2. dict / list / tuple / set 递归转换元素。
    3. dataclass 先转 dict 再递归。
    4. Pydantic model（含 ``model_dump``）优先使用其序列化方法。
    5. 普通对象通过 ``vars()`` 提取公有属性。
    6. 以上均不匹配时回退到 ``str()``。

    Args:
        value: 待转换的任意对象。

    Returns:
        JSON-safe 的 Python 原生值（dict、list、str、int、float、bool、None）。
    """
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        # 强制将键转为字符串，避免非字符串键导致 JSON 编码失败
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if hasattr(value, "model_dump") and callable(value.model_dump):
        # Pydantic v2 风格；v1 的 dict() 已在 __dict__ 分支中兜底
        return to_jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        # 过滤私有属性，减少序列化噪音
        return to_jsonable({key: item for key, item in vars(value).items() if not key.startswith("_")})
    # 最终回退：无法结构化的对象直接转为字符串
    return str(value)
