"""API 设置持久化模块。

负责在内存对象（ApiSettings）与 config.toml 文件之间双向转换，
并提供加载、保存与序列化辅助函数。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.swarm_spec import ApiConfig, SwarmAppConfig, load_root_config


@dataclass
class ApiSettings:
    """HTTP API 相关设置，暴露给前端设置界面读写。

    Attributes:
        base_url: API 根路径。
        timeout_seconds: 请求超时秒数。
        sse_reconnect_interval_seconds: SSE 自动重连间隔。
        auto_reconnect: 是否自动重连 SSE。
        require_auth: 是否强制开启 Token 认证。
        api_token: 显式配置的 API Token（序列化时会被抹除）。
        api_token_env: 存放 Token 的环境变量名。
        cors_allowed_origins: 允许的 CORS 源列表。
    """

    base_url: str = "/api"
    timeout_seconds: int = 30
    sse_reconnect_interval_seconds: int = 5
    auto_reconnect: bool = True
    require_auth: bool = False
    api_token: str | None = None
    api_token_env: str = "ANGELUS_API_TOKEN"
    cors_allowed_origins: list[str] | None = None

    @classmethod
    def from_config(cls, config: ApiConfig) -> "ApiSettings":
        """从内部 ApiConfig 创建前端友好的 ApiSettings。

        Args:
            config: 由配置加载器解析的 ApiConfig 实例。

        Returns:
            对应的 ApiSettings 实例。
        """
        return cls(
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            sse_reconnect_interval_seconds=config.sse_reconnect_interval_seconds,
            auto_reconnect=config.auto_reconnect,
            require_auth=config.require_auth,
            api_token=config.api_token,
            api_token_env=config.api_token_env,
            cors_allowed_origins=list(config.cors_allowed_origins),
        )

    @classmethod
    def from_mapping(cls, raw: Any, *, existing: "ApiSettings | None" = None) -> "ApiSettings":
        """从字典映射增量更新设置，缺失字段回退到现有值或默认值。

        Args:
            raw: 前端提交的字典，通常为 {"api": {...}} 中的内层。
            existing: 当前的 ApiSettings，用于增量合并。

        Returns:
            合并后的 ApiSettings 实例。

        Raises:
            ValueError: raw 不是字典时抛出。
        """
        if not isinstance(raw, dict):
            raise ValueError("'api' must be a JSON object.")
        existing = existing or cls()
        return cls(
            base_url=_coerce_string(raw.get("base_url", existing.base_url), fallback="/api"),
            timeout_seconds=_coerce_positive_int(raw.get("timeout_seconds", existing.timeout_seconds), fallback=30),
            sse_reconnect_interval_seconds=_coerce_positive_int(
                raw.get("sse_reconnect_interval_seconds", existing.sse_reconnect_interval_seconds),
                fallback=5,
            ),
            auto_reconnect=_coerce_bool(raw.get("auto_reconnect", existing.auto_reconnect), fallback=True),
            require_auth=_coerce_bool(raw.get("require_auth", existing.require_auth), fallback=False),
            api_token=_coerce_optional_string(raw.get("api_token", existing.api_token)),
            api_token_env=_coerce_string(raw.get("api_token_env", existing.api_token_env), fallback="ANGELUS_API_TOKEN"),
            cors_allowed_origins=_coerce_string_list(
                raw.get("cors_allowed_origins", existing.cors_allowed_origins or []),
            ),
        )

    def to_config(self) -> ApiConfig:
        """转换回内部 ApiConfig，供安全中间件等系统组件使用。

        Returns:
            ApiConfig 实例。
        """
        return ApiConfig(
            base_url=_coerce_string(self.base_url, fallback="/api"),
            timeout_seconds=_coerce_positive_int(self.timeout_seconds, fallback=30),
            sse_reconnect_interval_seconds=_coerce_positive_int(
                self.sse_reconnect_interval_seconds,
                fallback=5,
            ),
            auto_reconnect=bool(self.auto_reconnect),
            require_auth=bool(self.require_auth),
            api_token=_coerce_optional_string(self.api_token),
            api_token_env=_coerce_string(self.api_token_env, fallback="ANGELUS_API_TOKEN"),
            cors_allowed_origins=_coerce_string_list(self.cors_allowed_origins or []),
        )


def load_api_settings(config_path: Path) -> ApiSettings:
    """从根配置文件中加载 API 设置。

    Args:
        config_path: config.toml 的路径。

    Returns:
        解析后的 ApiSettings。
    """
    root_config = load_root_config(config_path)
    return ApiSettings.from_config(root_config.api)


def save_api_settings(config_path: Path, api_settings: ApiSettings) -> SwarmAppConfig:
    """将 API 设置持久化到 config.toml 并返回更新后的根配置。

    写入前会自动创建父目录，确保新环境也能直接保存。

    Args:
        config_path: config.toml 的路径。
        api_settings: 待保存的 API 设置。

    Returns:
        更新后的 SwarmAppConfig。
    """
    root_config = load_root_config(config_path) if config_path.exists() else SwarmAppConfig()
    updated = SwarmAppConfig(
        swarm_root=root_config.swarm_root,
        api=api_settings.to_config(),
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_render_root_config(updated), encoding="utf-8")
    return updated


def _render_root_config(config: SwarmAppConfig) -> str:
    """将 SwarmAppConfig 渲染为 TOML 格式的字符串。

    目前仅渲染 [app] 与 [api] 两个段落，保持与现有配置模板兼容。

    Args:
        config: 待渲染的根配置。

    Returns:
        TOML 文本。
    """
    lines = [
        "[app]",
        f"swarm_root = {_toml_string(str(config.swarm_root))}",
        "",
        "[api]",
        f"base_url = {_toml_string(config.api.base_url)}",
        f"timeout_seconds = {int(config.api.timeout_seconds)}",
        f"sse_reconnect_interval_seconds = {int(config.api.sse_reconnect_interval_seconds)}",
        f"auto_reconnect = {_toml_bool(config.api.auto_reconnect)}",
        f"require_auth = {_toml_bool(config.api.require_auth)}",
        f"api_token_env = {_toml_string(config.api.api_token_env)}",
        f"cors_allowed_origins = {_toml_string_array(config.api.cors_allowed_origins)}",
        "",
    ]
    if config.api.api_token:
        # api_token 为敏感字段，若存在则插入到 cors_allowed_origins 之后、空行之前
        lines.insert(-1, f"api_token = {_toml_string(config.api.api_token)}")
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    """为 TOML 字符串值添加双引号并转义内部字符。"""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_bool(value: bool) -> str:
    """将布尔值渲染为 TOML 字面量。"""
    return "true" if value else "false"


def _toml_string_array(values: list[str]) -> str:
    """将字符串列表渲染为 TOML 数组字面量。"""
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _coerce_string(raw: Any, *, fallback: str) -> str:
    """将任意值强制转为非空字符串，失败时回退。"""
    if raw is None:
        return fallback
    value = str(raw).strip()
    return value or fallback


def _coerce_optional_string(raw: Any) -> str | None:
    """将任意值强制转为字符串，空值映射为 None。"""
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _coerce_string_list(raw: Any) -> list[str]:
    """将任意值规范化为字符串列表，过滤空项。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _coerce_positive_int(raw: Any, *, fallback: int) -> int:
    """将任意值转为正整数，非正数或解析失败时回退。"""
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _coerce_bool(raw: Any, *, fallback: bool) -> bool:
    """将任意值转为布尔值，支持常见字符串表示。"""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if raw is None:
        return fallback
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def serialize_api_settings(config: ApiSettings) -> dict[str, Any]:
    """将 ApiSettings 序列化为字典，敏感 Token 被抹除。

    序列化结果用于返回给前端，避免直接泄露 api_token 明文。

    Args:
        config: 当前 API 设置。

    Returns:
        包含设置字段的字典；api_token 固定为 None，但保留 api_token_set
        标识以提示前端 Token 是否已配置。
    """
    payload = asdict(config)
    payload["api_token"] = None
    payload["api_token_set"] = bool(config.api_token)
    payload["cors_allowed_origins"] = list(config.cors_allowed_origins or [])
    return payload
