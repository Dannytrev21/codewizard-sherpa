"""Phase-3 S2-04 AC-12 — ``NotImplementedError`` is absent from
``registry.py``.

The S2-01 stub raised ``NotImplementedError`` from
``PluginRegistry.resolve`` as a structural reminder for this story.
After S2-04 ships the delegation to ``resolver.resolve``, the literal
substring ``NotImplementedError`` must not appear anywhere in
``registry.py``. A future regression that re-introduces the stub
(e.g., after a botched merge) trips this scan.
"""

from __future__ import annotations

from pathlib import Path

_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent / "src" / "codegenie" / "plugins" / "registry.py"
)


def test_no_notimplementederror_in_plugin_registry() -> None:
    src = _REGISTRY_PATH.read_text(encoding="utf-8")
    assert "NotImplementedError" not in src, (
        f"{_REGISTRY_PATH}: ``NotImplementedError`` reappeared — "
        "the S2-01 stub is supposed to have been replaced by the "
        "S2-04 delegation to resolver.resolve. Either the merge is "
        "broken or a new stub was added; restore the delegation."
    )
