from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import tomllib


@dataclass
class SkillAsset:
    """A standalone prompt asset loaded from a skill file."""

    name: str
    path: Path
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def load_skill_asset(path: Path) -> SkillAsset:
    """Load a skill asset from a markdown or TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"Skill file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".prompt"}:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Skill file is empty: {path}")
        return SkillAsset(name=path.stem, path=path, content=content)

    if suffix == ".toml":
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        skill_section = raw.get("skill")
        if not isinstance(skill_section, dict):
            raise ValueError(f"[skill] table is required in {path}")

        name = str(skill_section.get("name", path.stem)).strip() or path.stem
        content = str(skill_section.get("content", "")).strip()
        content_file = skill_section.get("content_file")
        if content_file:
            content_path = path.parent / str(content_file)
            content = content_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Skill file is missing content: {path}")
        metadata = {
            key: value
            for key, value in skill_section.items()
            if key not in {"name", "content", "content_file"}
        }
        return SkillAsset(name=name, path=path, content=content, metadata=metadata)

    raise ValueError(f"Unsupported skill file type: {path}")
