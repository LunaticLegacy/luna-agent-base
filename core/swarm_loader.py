"""Public API for loading Angelus swarm packages.

This module re-exports the key loading functions and types from the
internal ``swarm_loader_parts`` sub-package so that external code can
discover and initialise swarm packages without reaching into private
implementation details.

Exports:
    - :class:`LoadedSwarm`
    - :class:`SwarmLoaderError`
    - :func:`build_core_from_package`
    - :func:`load_all_swarms`
    - :func:`load_swarm_graph`
    - :func:`load_swarm_tools`
    - :func:`load_swarm_apis`
    - Requirement helpers for pre-installation
"""

from __future__ import annotations

from .swarm_loader_parts import LoadedSwarm, build_core_from_package, load_all_swarms, load_swarm_graph
from .swarm_loader_parts import (
    collect_api_requirement_files,
    collect_tool_requirement_files,
    install_api_requirements,
    install_tool_requirements,
    load_swarm_apis,
    load_swarm_tools,
)
from .swarm_spec import SwarmLoaderError

__all__ = [
    "LoadedSwarm",
    "SwarmLoaderError",
    "collect_api_requirement_files",
    "build_core_from_package",
    "collect_tool_requirement_files",
    "install_api_requirements",
    "install_tool_requirements",
    "load_all_swarms",
    "load_swarm_apis",
    "load_swarm_graph",
    "load_swarm_tools",
]
