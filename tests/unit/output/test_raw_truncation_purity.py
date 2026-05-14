"""AC-8 — ``codegenie.output.raw_truncation`` is a pure module.

No I/O, no logging, no os/pathlib. The functional core stays a leaf node in
the dependency graph so the imperative shell (``cli.py``) is the sole
side-effect site.
"""

from __future__ import annotations

import importlib
import inspect


def test_raw_truncation_module_imports_no_io_or_logging() -> None:
    """AC-8 — forbidden imports/uses are absent from the module source."""
    mod = importlib.import_module("codegenie.output.raw_truncation")
    src = inspect.getsource(mod)
    for forbidden in (
        "import os",
        "import logging",
        "import structlog",
        "from pathlib",
        "open(",
        "Path(",
    ):
        assert forbidden not in src, (
            f"raw_truncation.py imports/uses {forbidden!r} — should be pure"
        )


def test_raw_truncation_public_surface() -> None:
    """AC-6 — module's __all__ is the four contracted public names."""
    mod = importlib.import_module("codegenie.output.raw_truncation")
    assert set(mod.__all__) == {
        "Untruncated",
        "Truncated",
        "TruncationOutcome",
        "apply_raw_artifact_truncation",
    }
