"""Single source of truth for the package version.

Read at build time by ``hatchling`` via ``[tool.hatch.version]`` in
``pyproject.toml``; ``hatchling`` parses this file with the ``ast`` module
(no execution), so ``__version__`` MUST be a top-level string assignment.
"""

from __future__ import annotations

__version__: str = "0.0.1"
