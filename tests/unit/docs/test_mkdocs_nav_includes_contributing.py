"""S8-04 AC-6b — `contributing.md` is reachable via the mkdocs nav tree.

No subprocess: parses ``mkdocs.yml`` as YAML and walks the nav tree
recursively (nav entries can be strings, dicts mapping to strings, or dicts
mapping to nested lists). Asserts ``contributing.md`` appears as a leaf
somewhere in the tree.

The actual ``mkdocs build --strict`` invocation stays in the existing
``make docs`` CI job (per CLAUDE.md `make check` chain); duplicating it from
a unit test would be slow + side-effectful.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class _IgnoreUnknownTagsLoader(yaml.SafeLoader):
    """SafeLoader that returns ``None`` for any unknown tag.

    ``mkdocs.yml`` uses ``!!python/name:material.extensions.emoji.twemoji`` and
    similar tags that SafeLoader rejects. We only need the ``nav`` subtree;
    ignoring the rest is sufficient.
    """


def _construct_undefined(loader: yaml.Loader, node: yaml.Node) -> None:
    return None


_IgnoreUnknownTagsLoader.add_constructor(None, _construct_undefined)


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MKDOCS_YML = _REPO_ROOT / "mkdocs.yml"


def _walk(node: Any) -> bool:
    """Return True if ``contributing.md`` appears anywhere as a string leaf."""
    if isinstance(node, str):
        return node == "contributing.md"
    if isinstance(node, list):
        return any(_walk(child) for child in node)
    if isinstance(node, dict):
        return any(_walk(child) for child in node.values())
    return False


def test_contributing_in_nav_tree() -> None:
    config = yaml.load(  # noqa: S506 — custom safe-derived loader that ignores unknown tags.
        _MKDOCS_YML.read_text(encoding="utf-8"),
        Loader=_IgnoreUnknownTagsLoader,
    )
    assert isinstance(config, dict), f"mkdocs.yml: expected dict, got {type(config).__name__}"
    nav = config.get("nav")
    assert nav is not None, "mkdocs.yml: missing top-level `nav` key"
    assert _walk(nav), (
        "mkdocs.yml `nav` tree does not include `contributing.md`. "
        "Add a row like `- Contributing: contributing.md` somewhere under `nav:`."
    )
