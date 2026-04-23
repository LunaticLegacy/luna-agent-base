from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from core.swarm_spec import ApiConfig, SwarmAppConfig, load_root_config


@dataclass
class ApiSettings:
    """API settings exposed through the HTTP settings API."""

    base_url: str = "/api"
    timeout_seconds: int = 30
    sse_reconnect_interval_seconds: int = 5
    auto_reconnect: bool = True

    @classmethod
    def from_config(cls, config: ApiConfig) -> "ApiSettings":
        return cls(
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
            sse_reconnect_interval_seconds=config.sse_reconnect_interval_seconds,
            auto_reconnect=config.auto_reconnect,
        )

    @classmethod
    def from_mapping(cls, raw: Any) -> "ApiSettings":
        if not isinstance(raw, dict):
            raise ValueError("'api' must be a JSON object.")
        return cls(
            base_url=_coerce_string(raw.get("base_url", "/api"), fallback="/api"),
            timeout_seconds=_coerce_positive_int(raw.get("timeout_seconds", 30), fallback=30),
            sse_reconnect_interval_seconds=_coerce_positive_int(
                raw.get("sse_reconnect_interval_seconds", 5),
                fallback=5,
            ),
            auto_reconnect=_coerce_bool(raw.get("auto_reconnect", True), fallback=True),
        )

    def to_config(self) -> ApiConfig:
        return ApiConfig(
            base_url=_coerce_string(self.base_url, fallback="/api"),
            timeout_seconds=_coerce_positive_int(self.timeout_seconds, fallback=30),
            sse_reconnect_interval_seconds=_coerce_positive_int(
                self.sse_reconnect_interval_seconds,
                fallback=5,
            ),
            auto_reconnect=bool(self.auto_reconnect),
        )


def load_api_settings(config_path: Path) -> ApiSettings:
    """Load API settings from the root config file."""
    root_config = load_root_config(config_path)
    return ApiSettings.from_config(root_config.api)


def save_api_settings(config_path: Path, api_settings: ApiSettings) -> SwarmAppConfig:
    """Persist API settings into config.toml and return the updated root config."""
    root_config = load_root_config(config_path) if config_path.exists() else SwarmAppConfig()
    updated = SwarmAppConfig(
        swarm_root=root_config.swarm_root,
        api=api_settings.to_config(),
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(_render_root_config(updated), encoding="utf-8")
    return updated


def _render_root_config(config: SwarmAppConfig) -> str:
    lines = [
        "[app]",
        f"swarm_root = {_toml_string(str(config.swarm_root))}",
        "",
        "[api]",
        f"base_url = {_toml_string(config.api.base_url)}",
        f"timeout_seconds = {int(config.api.timeout_seconds)}",
        f"sse_reconnect_interval_seconds = {int(config.api.sse_reconnect_interval_seconds)}",
        f"auto_reconnect = {_toml_bool(config.api.auto_reconnect)}",
        "",
    ]
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _coerce_string(raw: Any, *, fallback: str) -> str:
    if raw is None:
        return fallback
    value = str(raw).strip()
    return value or fallback


def _coerce_positive_int(raw: Any, *, fallback: int) -> int:
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _coerce_bool(raw: Any, *, fallback: bool) -> bool:
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
    return asdict(config)
