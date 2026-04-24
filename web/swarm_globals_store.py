from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
import re

from core.swarm_spec import GlobalVariablesConfig, SwarmLoaderError
from web.utils import to_jsonable


def serialize_global_variables(config: GlobalVariablesConfig) -> Dict[str, Any]:
    return {
        "values": to_jsonable(dict(config.values)),
        "visibility": {key: list(value) for key, value in config.visibility.items()},
    }


def load_global_variables(manifest_path: Path) -> GlobalVariablesConfig:
    from core.swarm_spec import load_swarm_manifest

    _, manifest = load_swarm_manifest(manifest_path.parent)
    return manifest.global_variables


def save_global_variables(manifest_path: Path, globals_config: GlobalVariablesConfig) -> None:
    path = Path(manifest_path)
    if not path.exists():
        raise SwarmLoaderError(f"Manifest file not found: {path}")
    text = path.read_text(encoding="utf-8")
    section = _render_globals_section(globals_config)
    updated = _replace_or_append_section(text, section)
    path.write_text(updated, encoding="utf-8")


def _render_globals_section(config: GlobalVariablesConfig) -> str:
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
    lines = text.splitlines()
    start_idx = None
    end_idx = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "[globals]":
            start_idx = index
            end_idx = index + 1
            while end_idx < len(lines):
                next_line = lines[end_idx].strip()
                if re.match(r"^\[", next_line) and not next_line.startswith("[globals."):
                    break
                end_idx += 1
            break

    section_lines = section.rstrip("\n").splitlines()
    if start_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(section_lines)
        return "\n".join(lines) + ("\n" if not text.endswith("\n") else "")

    return "\n".join(lines[:start_idx] + section_lines + lines[end_idx:]) + ("\n" if not text.endswith("\n") else "")


def _render_toml_value(value: Any) -> str:
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
    return "[" + ", ".join(_render_toml_value(item) for item in values) + "]"


def _render_toml_inline_table(value: Dict[str, Any]) -> str:
    items = [f"{key} = {_render_toml_value(item)}" for key, item in value.items()]
    return "{ " + ", ".join(items) + " }"


def _render_toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
