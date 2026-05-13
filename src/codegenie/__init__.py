"""``codegenie`` — the codewizard-sherpa local POC CLI package.

Re-exports :data:`__version__` from :mod:`codegenie.version` so callers can
read the version without paying for any heavier imports (Phase 0 keeps
``--help`` cold-start clean per ADR-0006 §Consequences).
"""

from __future__ import annotations

from codegenie.version import __version__

__all__ = ["__version__"]
