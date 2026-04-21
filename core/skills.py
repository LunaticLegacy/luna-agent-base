from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import tomllib


@dataclass
class SkillContract:
    """Structured contract metadata for a skill asset."""

    version: str = "1.0"
    capability: str = ""
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    requires_tools: List[str] = field(default_factory=list)
    requires_skills: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    failure_policy: str = "retry"
    parallelizable: bool = False


@dataclass
class SkillAsset:
    """A standalone prompt asset loaded from a skill file."""

    name: str
    path: Path
    content: str
    contract: Optional[SkillContract] = None
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
        contract = _load_skill_contract_sidecar(path)
        return SkillAsset(
            name=_normalize_skill_name(path.stem),
            path=path,
            content=content,
            contract=contract,
            metadata=_contract_metadata(contract),
        )

    if suffix == ".toml":
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        skill_section = raw.get("skill")
        if not isinstance(skill_section, dict):
            raise ValueError(f"[skill] table is required in {path}")

        name = str(skill_section.get("name", _normalize_skill_name(path.stem))).strip() or _normalize_skill_name(path.stem)
        content = str(skill_section.get("content", "")).strip()
        content_file = skill_section.get("content_file")
        if content_file:
            content_path = path.parent / str(content_file)
            content = content_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError(f"Skill file is missing content: {path}")
        contract = _parse_contract_section(skill_section)
        metadata = {
            key: value
            for key, value in skill_section.items()
            if key not in {"name", "content", "content_file"}
        }
        metadata.update(_contract_metadata(contract))
        return SkillAsset(
            name=name,
            path=path,
            content=content,
            contract=contract,
            metadata=metadata,
        )

    raise ValueError(f"Unsupported skill file type: {path}")


def _normalize_skill_name(raw_name: str) -> str:
    return raw_name.replace(".", "_").replace("-", "_")


def _load_skill_contract_sidecar(path: Path) -> Optional[SkillContract]:
    sidecar_candidates = [
        path.with_suffix(".toml"),
        path.with_name(f"{path.name}.toml"),
    ]
    for candidate in sidecar_candidates:
        if candidate.exists():
            with candidate.open("rb") as handle:
                raw = tomllib.load(handle)
            skill_section = raw.get("skill")
            if not isinstance(skill_section, dict):
                raise ValueError(f"[skill] table is required in {candidate}")
            return _parse_contract_section(skill_section)
    return None


def _parse_contract_section(skill_section: Dict[str, Any]) -> SkillContract:
    return SkillContract(
        version=str(skill_section.get("version", "1.0")).strip() or "1.0",
        capability=str(skill_section.get("capability", "")).strip(),
        description=str(skill_section.get("description", "")).strip(),
        input_schema=_as_mapping(skill_section.get("input_schema")),
        output_schema=_as_mapping(skill_section.get("output_schema")),
        requires_tools=_as_string_list(skill_section.get("requires_tools")),
        requires_skills=_as_string_list(skill_section.get("requires_skills")),
        preconditions=_as_string_list(skill_section.get("preconditions")),
        postconditions=_as_string_list(skill_section.get("postconditions")),
        failure_policy=str(skill_section.get("failure_policy", "retry")).strip() or "retry",
        parallelizable=bool(skill_section.get("parallelizable", False)),
    )


def _contract_metadata(contract: Optional[SkillContract]) -> Dict[str, Any]:
    if contract is None:
        return {}
    return {
        "contract_version": contract.version,
        "capability": contract.capability,
        "description": contract.description,
        "input_schema": dict(contract.input_schema),
        "output_schema": dict(contract.output_schema),
        "requires_tools": list(contract.requires_tools),
        "requires_skills": list(contract.requires_skills),
        "preconditions": list(contract.preconditions),
        "postconditions": list(contract.postconditions),
        "failure_policy": contract.failure_policy,
        "parallelizable": contract.parallelizable,
    }


def _as_mapping(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Skill contract schema values must be TOML tables.")
    return dict(raw)


def _as_string_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("Skill contract list values must be TOML arrays.")
    return [str(item).strip() for item in raw if str(item).strip()]
