"""Unit tests for ``codegenie.probes._lockfiles._pnpm``.

Each test is keyed to an AC in S3-01 and names the mutation it
catches in its docstring (mutation-resistance per Rule 9 — tests
verify intent, not just behavior).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from codegenie.errors import (
    DepthCapExceeded,
    MalformedLockfileError,
    MalformedYAMLError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _pnpm

# --- AC-2 — module surface -----------------------------------------------------


def test_module_all_exports_pnpmlock_and_parse_only() -> None:
    """AC-2. Mutation caught: a future export leak (e.g., re-exporting
    a private helper) would silently widen the module's public surface."""
    assert set(_pnpm.__all__) == {"PnpmLock", "parse"}


# --- AC-3 — module constants typed Final at the documented values --------------


def test_module_constants_are_final_with_documented_values() -> None:
    """AC-3. Mutation caught: changing the size or depth cap silently.
    The cap values match arch §"Component design" #9 (50 MB / depth 64)."""
    assert _pnpm.PNPM_LOCKFILE_MAX_BYTES == 50 * 1024 * 1024
    assert _pnpm.PNPM_LOCKFILE_MAX_DEPTH == 64


def test_parse_invokes_safe_yaml_load_with_module_constants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3. Mutation caught: hard-coding alternate cap literals at
    the call site (the module constants would drift unnoticed)."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '9.0'\npackages: {}\n")
    captured: dict[str, Any] = {}

    def fake_load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, Any]:
        captured["path"] = path
        captured["max_bytes"] = max_bytes
        captured["max_depth"] = max_depth
        return {"lockfileVersion": "9.0", "packages": {}}

    monkeypatch.setattr(_pnpm.safe_yaml, "load", fake_load)
    _pnpm.parse(lockfile)
    assert captured["path"] == lockfile
    assert captured["max_bytes"] == _pnpm.PNPM_LOCKFILE_MAX_BYTES
    assert captured["max_depth"] == _pnpm.PNPM_LOCKFILE_MAX_DEPTH


# --- AC-9 — happy paths, both pnpm v6 and v9 shapes ----------------------------


def test_parse_happy_path_v9_returns_typed_dict_shape(tmp_path: Path) -> None:
    """AC-3, AC-9. Mutation caught: dropping ``total=False`` would
    force every PnpmLock to carry all four keys — v6 callers would
    TypeError. The v9 fixture includes ``snapshots``."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text(
        "lockfileVersion: '9.0'\n"
        "importers:\n"
        "  .:\n"
        "    dependencies: {}\n"
        "packages: {}\n"
        "snapshots: {}\n"
    )
    result = _pnpm.parse(lockfile)
    assert result["lockfileVersion"] == "9.0"
    assert result["packages"] == {}
    assert result["snapshots"] == {}
    # Shape only — value-equality of nested structure is NodeManifestProbe's job.


def test_parse_happy_path_v6_missing_snapshots_still_parses(tmp_path: Path) -> None:
    """AC-9. Mutation caught: defaulting ``snapshots`` at the parser
    layer would mask the v6 vs v9 distinction the consumer needs."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("lockfileVersion: '6.0'\npackages: {}\nimporters: {}\n")
    result = _pnpm.parse(lockfile)
    assert "snapshots" not in result  # v6 shape — packages-only.
    assert result["lockfileVersion"] == "6.0"


# --- AC-4 — typed exceptions propagate unchanged from safe_yaml.load -----------
# Re-raise paths exercised via direct safe_yaml.load monkey-patch (Rule 2 — the
# pass-through contract is the load-bearing assertion; safe_yaml's own tests
# already prove that load raises each class on the right input).


@pytest.mark.parametrize(
    "raised",
    [
        SizeCapExceeded("synthetic: size>cap"),
        SymlinkRefusedError("synthetic: ELOOP"),
    ],
)
def test_parse_passes_through_typed_safe_yaml_exceptions_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
) -> None:
    """AC-4. Mutation caught: a blanket ``except Exception`` that
    re-wraps every error into ``MalformedLockfileError`` would absorb
    the typed pass-through classes; an ``except`` clause without a
    bare ``raise`` would swallow them entirely."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("k: v\n")

    def fake_load(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise raised

    monkeypatch.setattr(_pnpm.safe_yaml, "load", fake_load)
    with pytest.raises(type(raised)) as exc:
        _pnpm.parse(lockfile)
    # Identity check — the very instance flows through, not a re-wrap.
    assert exc.value is raised


def test_parse_passes_through_depth_cap_from_real_safe_yaml(tmp_path: Path) -> None:
    """AC-4. Real ``safe_yaml.load`` invocation against plain
    flow-style deep nesting — proves the integration, not just the
    pass-through wrapper. Mutation caught: catching ``CodegenieError``
    broadly would absorb ``DepthCapExceeded``.

    NOTE on test design (deviation from story TDD plan): the story
    prescribes a YAML-anchor-amplification fixture for this AC. The
    ``id()``-memoized walker in ``parsers/_depth.py`` defeats alias
    amplification by skipping shared subtrees — empirically the
    prescribed alias chain parses successfully (max walked depth = 1).
    Plain flow-style deep nesting (``{k: {k: ...}}`` × 70) is the
    proven trigger for ``DepthCapExceeded`` in
    ``tests/unit/parsers/test_safe_yaml.py::_nest_dict``; we reuse
    that shape here.
    """
    out = "v"
    for _ in range(70):
        out = "{k: " + out + "}"
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("k: " + out + "\n")
    with pytest.raises(DepthCapExceeded):
        _pnpm.parse(lockfile)


def test_parse_symlink_at_final_component_reraises_symlink_refused(tmp_path: Path) -> None:
    """AC-4. Real ``safe_yaml.load`` invocation against a symlink.
    Mutation caught: any path that strips ``O_NOFOLLOW`` in a future
    re-impl would suddenly follow the link; the wrapper must let
    ``SymlinkRefusedError`` propagate unchanged."""
    real = tmp_path / "real.yaml"
    real.write_text("lockfileVersion: '9.0'\npackages: {}\n")
    link = tmp_path / "pnpm-lock.yaml"
    link.symlink_to(real)
    with pytest.raises(SymlinkRefusedError):
        _pnpm.parse(link)


# --- AC-5, AC-7, AC-8, AC-10 — malformed-YAML translation ----------------------


def test_parse_malformed_yaml_raises_malformed_lockfile_with_cause_chain(
    tmp_path: Path,
) -> None:
    """AC-5, AC-7. Mutation caught: dropping ``from cause`` would
    strip ``__cause__`` (the catch site loses provenance);
    translating to a different marker class would break the
    one-class-per-warning-ID contract in ADR-0007."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("packages: {unclosed\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    # AC-7: ``__cause__`` is the original MalformedYAMLError.
    assert isinstance(exc.value.__cause__, MalformedYAMLError)


def test_parse_malformed_yaml_message_contains_path(tmp_path: Path) -> None:
    """AC-8. Mutation caught: building the message without the path
    (e.g., ``MalformedLockfileError(str(cause))``) — downstream
    WarningId construction in NodeManifestProbe recovers the path
    from ``args[0]``."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text(": :\n")  # CSafeLoader rejects (ParserError).
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    assert str(lockfile) in exc.value.args[0]


def test_parse_top_level_non_mapping_raises_malformed_lockfile(tmp_path: Path) -> None:
    """AC-10. Mutation caught: returning the non-mapping object would
    silently widen ``list`` to ``PnpmLock`` via the cast; the
    translation pass re-uses the same MalformedYAMLError handler."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("- a\n- b\n")  # top-level YAML list, not a mapping.
    with pytest.raises(MalformedLockfileError):
        _pnpm.parse(lockfile)


# --- AC-11 — single-document only ---------------------------------------------


def test_parse_multi_document_yaml_translates_to_malformed_lockfile(tmp_path: Path) -> None:
    """AC-11. Mutation caught: swapping ``safe_yaml.load`` for
    ``safe_yaml.load_all`` and returning the first document — would
    silently accept multi-doc lockfiles. Real pnpm-lock.yaml is
    single-document by spec; multi-doc is a malformed artifact."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text(
        "lockfileVersion: '9.0'\npackages: {}\n---\nlockfileVersion: '6.0'\npackages: {}\n"
    )
    with pytest.raises(MalformedLockfileError):
        _pnpm.parse(lockfile)


# --- AC-6, AC-15 — marker discipline ------------------------------------------


def test_raised_marker_carries_only_positional_message_and_no_attributes(
    tmp_path: Path,
) -> None:
    """AC-6, AC-15. Mutation caught: a future "convenience" override
    of ``MalformedLockfileError.__init__(self, *, path, cause)`` would
    be flagged immediately. The Phase-0 invariant
    ``test_subclasses_are_markers_only`` guards the class-level
    contract; this test guards the construction site in _pnpm.py."""
    lockfile = tmp_path / "pnpm-lock.yaml"
    lockfile.write_text("packages: {unclosed\n")
    with pytest.raises(MalformedLockfileError) as exc:
        _pnpm.parse(lockfile)
    # Marker invariant: args is a single positional message string.
    assert len(exc.value.args) == 1
    assert isinstance(exc.value.args[0], str)
    # Negatives — no instance attributes smuggled in.
    for forbidden in ("path", "cap", "detail", "cause", "warning_id"):
        assert not hasattr(exc.value, forbidden), (
            f"MalformedLockfileError must remain a marker; instance must "
            f"not carry {forbidden!r}. Path lives in args[0]; cause lives "
            f"on __cause__."
        )


# --- AC-12 — extension-by-addition (architectural test) -----------------------


def test_pnpm_module_does_not_reference_sibling_parsers() -> None:
    """AC-12, CLAUDE.md "Extension by addition". Mutation caught: a
    future edit that imports ``_npm`` / ``_yarn`` / ``_bun`` into
    ``_pnpm`` — sibling parsers must be free to evolve independently.
    The shared kernel is ``parsers/safe_yaml`` + ``codegenie.errors``,
    not other sibling modules."""
    src = inspect.getsource(_pnpm)
    for forbidden in ("_npm", "_yarn", "_bun"):
        assert forbidden not in src, (
            f"_pnpm.py must not reference sibling parser {forbidden!r}; "
            f"adding a new lockfile format is a new file, not an edit here."
        )


# --- AC-1 — sibling package __init__ stays inert ------------------------------


def test_lockfiles_package_init_has_empty_all() -> None:
    """AC-1. Mutation caught: re-exporting ``parse`` from the package
    ``__init__`` would force import order to surface (and S3-02/S3-03
    additions become edits to this file rather than new modules)."""
    from codegenie.probes import _lockfiles

    assert _lockfiles.__all__ == []
