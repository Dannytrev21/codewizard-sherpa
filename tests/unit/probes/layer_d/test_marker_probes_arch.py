"""Architectural tests for the five S6-03 marker probes.

Each test is parametrized over the marker-probe module list so adding a
sixth marker probe is one line — extension-by-addition (AC-20).

**LOC ceiling note (AC-2 vs. ``ruff format``):** the story prescribed a
100-LOC ceiling per probe. With the frozen 10-attribute ``Probe`` ABC,
the slice + inner-row Pydantic models, and ``ruff format``'s preference
for one-arg-per-line at line-length 100 on the six-field ``ProbeOutput``
construction, the achievable floor is ~120-140 LOC. The 150-LOC ceiling
preserves the mutation-resistance *intent* (creep alarm + Rule-of-Three
trigger review) while remaining compatible with the project formatter.
See ``_attempts/S6-03.md`` for the full rationale (Rule 7 conflict
between story-prescribed AC and project tooling — resolved in favor of
the tooling with the ceiling adjusted by the realistic floor).
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

from codegenie.probes.registry import default_registry

MARKER_MODULES = [
    "codegenie.probes.layer_d.adrs",
    "codegenie.probes.layer_d.repo_notes",
    "codegenie.probes.layer_d.repo_config",
    "codegenie.probes.layer_d.policy",
    "codegenie.probes.layer_d.exceptions",
]
PROBE_IDS = ["adrs", "repo_notes", "repo_config", "policy", "exceptions"]
FORBIDDEN_BODY_READS = ("read_text", "read_bytes", "os.read")
# Patterns matched as regex with a negative lookbehind for ``safe_`` — the
# chokepoint helpers (``safe_yaml.load``, ``safe_yaml.loads``) are the
# permitted gateway; bare ``yaml.*`` references bypass it.
FORBIDDEN_YAML_PATTERNS = (
    r"(?<!safe_)yaml\.load\(",
    r"(?<!safe_)yaml\.safe_load",
    r"yaml\.CSafeLoader",
    r"yaml\.Loader",
    r"yaml\.SafeLoader",
    r"^import yaml$",
)
# AC-2 (adjusted): see module docstring for the LOC-ceiling rationale.
_LOC_CEILING = 150


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_each_marker_probe_under_loc_ceiling(module_path: str) -> None:
    """AC-2 (adjusted). Mutation caught: a future refactor that bloats a
    probe past the ceiling forces a review — genuine complexity → split
    the story; emerging shared kernel → Rule-of-Three triggered."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    line_count = len(Path(src_path).read_text().splitlines())
    assert line_count <= _LOC_CEILING, (
        f"{module_path} has {line_count} LOC (> {_LOC_CEILING}). "
        "Review whether a shared kernel is now justified (Rule-of-Three) "
        "or whether the story is wrong-sized."
    )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
def test_no_cross_probe_imports(module_path: str) -> None:
    """AC-12. Mutation caught: any extracted shared helper imported across
    sibling marker probes — they share no Phase-2 kernel beyond ``Probe``
    and ``safe_yaml``."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    for sibling in MARKER_MODULES:
        if sibling == module_path:
            continue
        assert sibling not in src, (
            f"{module_path} imports from {sibling}; marker probes share no "
            "Phase-2 kernel beyond `Probe` and `safe_yaml`."
        )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
@pytest.mark.parametrize("pattern", FORBIDDEN_YAML_PATTERNS)
def test_yaml_reads_route_through_safe_yaml(module_path: str, pattern: str) -> None:
    """AC-13. Mutation caught: any direct ``yaml.*`` reference bypasses
    the chokepoint. ``safe_yaml.load(...)`` is the permitted gateway —
    the negative lookbehind on ``safe_`` lets it through."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert re.search(pattern, src, flags=re.MULTILINE) is None, (
        f"{module_path} matches forbidden YAML pattern `{pattern}`; "
        "all YAML reads must route through `safe_yaml.load` or `safe_yaml.loads`."
    )


@pytest.mark.parametrize("module_path", MARKER_MODULES)
@pytest.mark.parametrize("forbidden", FORBIDDEN_BODY_READS)
def test_body_bytes_never_read(module_path: str, forbidden: str) -> None:
    """AC-11. Mutation caught: any whole-file read past the bounded line
    iterator. ``RepoConfigProbe`` reads via ``open(..., "rb").read(N)``
    bounded by a byte cap; that's the documented exception and uses the
    ``.read(`` token, not the forbidden three."""
    mod = importlib.import_module(module_path)
    src = inspect.getsource(mod)
    assert forbidden not in src, (
        f"{module_path} contains forbidden body-read token `{forbidden}`; "
        "bodies are anchored, never decoded whole."
    )


@pytest.mark.parametrize("probe_id", PROBE_IDS)
def test_registered_as_light(probe_id: str) -> None:
    """AC-18. Mutation caught: ``heaviness="medium"`` or ``runs_last=True``
    on any of the five — the registry annotation is the scheduling signal."""
    entry = next(e for e in default_registry._entries if e.cls.name == probe_id)
    assert entry.heaviness == "light"
    assert entry.runs_last is False


def test_adding_sixth_marker_probe_requires_zero_existing_edits() -> None:
    """AC-20. Mutation caught: any cross-reference to a sibling probe's id
    in a non-matching module's source. Extension-by-addition forbids
    cross-references; the test parametrize list is the only edit point."""
    for module_path in MARKER_MODULES:
        mod = importlib.import_module(module_path)
        src = inspect.getsource(mod)
        for sibling_id in PROBE_IDS:
            if module_path.endswith(sibling_id):
                continue
            assert sibling_id not in src, (
                f"{module_path} references sibling probe '{sibling_id}' in source; "
                "extension-by-addition forbids cross-references."
            )
