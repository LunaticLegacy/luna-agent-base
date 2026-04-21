from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert runtime objects into JSON-safe structures."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return to_jsonable(value.model_dump())
    if hasattr(value, "__dict__"):
        return to_jsonable({key: item for key, item in vars(value).items() if not key.startswith("_")})
    return str(value)
