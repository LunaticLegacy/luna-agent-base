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
    require_auth: bool = False
    api_token: str | None = None
    api_token_env: str = "ANGELUS_API_TOKEN"
    cors_allowed_origins: list[str] | None = None

    @classmethod
    def from_config(cls, config: ApiConfig) -> "ApiSettings":
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
        f"require_auth = {_toml_bool(config.api.require_auth)}",
        f"api_token_env = {_toml_string(config.api.api_token_env)}",
        f"cors_allowed_origins = {_toml_string_array(config.api.cors_allowed_origins)}",
        "",
    ]
    if config.api.api_token:
        lines.insert(-1, f"api_token = {_toml_string(config.api.api_token)}")
    return "\n".join(lines)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_string_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _coerce_string(raw: Any, *, fallback: str) -> str:
    if raw is None:
        return fallback
    value = str(raw).strip()
    return value or fallback


def _coerce_optional_string(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _coerce_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


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
    payload = asdict(config)
    payload["api_token"] = None
    payload["api_token_set"] = bool(config.api_token)
    payload["cors_allowed_origins"] = list(config.cors_allowed_origins or [])
    return payload
