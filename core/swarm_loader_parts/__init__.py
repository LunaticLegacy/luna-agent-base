"""Internal swarm loader sub-package.

Exposes the building blocks used by :mod:`core.swarm_loader` to discover,
parse, and instantiate swarm packages.  Most callers should import from
:mod:`core.swarm_loader` rather than using this module directly.

Exports:
    - :class:`LoadedSwarm`
    - :func:`build_core_from_package`
    - :func:`load_all_swarms`
    - :func:`load_swarm_graph`
    - Requirement installation helpers
    - API / tool loading helpers
"""

from .build import LoadedSwarm, build_core_from_package, load_all_swarms, load_swarm_graph
from .utils import (
    collect_api_requirement_files,
    collect_tool_requirement_files,
    install_api_requirements,
    install_tool_requirements,
    load_swarm_apis,
    load_swarm_tools,
)

__all__ = [
    "LoadedSwarm",
    "build_core_from_package",
    "collect_api_requirement_files",
    "collect_tool_requirement_files",
    "install_api_requirements",
    "install_tool_requirements",
    "load_all_swarms",
    "load_swarm_apis",
    "load_swarm_graph",
    "load_swarm_tools",
]
