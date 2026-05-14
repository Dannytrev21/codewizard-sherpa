"""Unit tests for ``codegenie.probes._lockfiles._npm``.

Each test is keyed to an AC in S3-02 and names the mutation it
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
    MalformedJSONError,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.probes._lockfiles import _npm

# --- AC-2 — module surface -----------------------------------------------------


def test_module_all_exports_npmlock_and_parse_only() -> None:
    """AC-2. Mutation caught: a future export leak (e.g., re-exporting
    a private helper or the module constants) would silently widen the
    module's public surface."""
    assert set(_npm.__all__) == {"NpmLock", "parse"}


# --- AC-3 — module constants typed Final at the documented values --------------


def test_module_constants_are_final_with_documented_values() -> None:
    """AC-3. Mutation caught: changing the size or depth cap silently.
    The cap values match arch §"Component design" #9 (50 MB / depth 64)."""
    assert _npm.NPM_LOCKFILE_MAX_BYTES == 50 * 1024 * 1024
    assert _npm.NPM_LOCKFILE_MAX_DEPTH == 64


def test_parse_invokes_safe_json_load_with_module_constants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-3. Mutation caught: hard-coding alternate cap literals at
    the call site (the module constants would drift unnoticed)."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"name":"x","lockfileVersion":3,"packages":{}}')
    captured: dict[str, Any] = {}

    def fake_load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, Any]:
        captured["path"] = path
        captured["max_bytes"] = max_bytes
        captured["max_depth"] = max_depth
        return {"name": "x", "lockfileVersion": 3, "packages": {}}

    monkeypatch.setattr(_npm.safe_json, "load", fake_load)
    _npm.parse(lockfile)
    assert captured["path"] == lockfile
    assert captured["max_bytes"] == _npm.NPM_LOCKFILE_MAX_BYTES
    assert captured["max_depth"] == _npm.NPM_LOCKFILE_MAX_DEPTH


# --- AC-9 — happy paths, both v3 and v1 shapes ---------------------------------


def test_parse_happy_path_v3_returns_typed_dict_shape(tmp_path: Path) -> None:
    """AC-3, AC-9. Mutation caught: dropping ``total=False`` would
    force every NpmLock to carry all six keys — v1 fixtures lacking
    ``packages`` would TypeError. The v3 fixture omits ``dependencies``."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"name":"x","version":"1.0.0","lockfileVersion":3,'
        '"packages":{"":{"name":"x","version":"1.0.0"}}}'
    )
    result = _npm.parse(lockfile)
    assert result["lockfileVersion"] == 3
    assert result["name"] == "x"
    assert result["packages"] == {"": {"name": "x", "version": "1.0.0"}}
    assert "dependencies" not in result  # v3 shape — packages-only.
    # Shape only — value-equality of nested structure is NodeManifestProbe's job.


def test_parse_happy_path_v1_missing_packages_still_parses(tmp_path: Path) -> None:
    """AC-9. Mutation caught: defaulting ``packages`` at the parser
    layer would mask the v1 vs v3 distinction the consumer needs.
    v1 ships ``dependencies`` (nested tree) only — no ``packages``."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text(
        '{"name":"x","version":"1.0.0","lockfileVersion":1,"requires":true,'
        '"dependencies":{"lodash":{"version":"4.17.21"}}}'
    )
    result = _npm.parse(lockfile)
    assert "packages" not in result  # v1 shape — no flat tree.
    assert result["lockfileVersion"] == 1
    assert result["dependencies"] == {"lodash": {"version": "4.17.21"}}


# --- AC-4 — typed exceptions propagate unchanged from safe_json.load -----------
# Re-raise paths exercised via direct safe_json.load monkey-patch (Rule 2 — the
# pass-through contract is the load-bearing assertion; safe_json's own tests
# already prove that load raises each class on the right input). Mirrors S3-01's
# parametrized object-identity approach (see _attempts/S3-01.md Deviation #2).


@pytest.mark.parametrize(
    "raised",
    [
        SizeCapExceeded("synthetic: size>cap"),
        SymlinkRefusedError("synthetic: ELOOP"),
    ],
)
def test_parse_passes_through_typed_safe_json_exceptions_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
) -> None:
    """AC-4. Mutation caught: a blanket ``except Exception`` that
    re-wraps every error into ``MalformedLockfileError`` would absorb
    the typed pass-through classes; an ``except`` clause without a
    bare ``raise`` would swallow them entirely. Object-identity
    assertion (``exc.value is raised``) is strictly stronger than
    ``pytest.raises(type(raised))`` — catches any re-wrap that
    constructs a new instance of the same class."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"name":"x","lockfileVersion":3,"packages":{}}')

    def fake_load(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise raised

    monkeypatch.setattr(_npm.safe_json, "load", fake_load)
    with pytest.raises(type(raised)) as exc:
        _npm.parse(lockfile)
    # Identity check — the very instance flows through, not a re-wrap.
    assert exc.value is raised


def test_parse_passes_through_depth_cap_from_real_safe_json(tmp_path: Path) -> None:
    """AC-4. Real ``safe_json.load`` invocation against bracket-nested
    JSON — proves the integration, not just the pass-through wrapper.
    Mutation caught: catching ``CodegenieError`` broadly would absorb
    ``DepthCapExceeded``.

    JSON has no aliases (unlike YAML), so bracket-nesting is the
    canonical depth-cap vector — ``json.loads`` parses
    ``{"a":{"a":...}}`` 70-deep in C-extension iteration without
    hitting Python recursion (stdlib ``_json.c`` is iterative for
    object/array bodies). The post-parse depth walker
    (``parsers/_depth.assert_max_depth``) then raises
    ``DepthCapExceeded`` at depth 65. 70 levels is well above the 64
    cap.
    """
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("{" + '"a":{' * 70 + "}" * 71)
    with pytest.raises(DepthCapExceeded):
        _npm.parse(lockfile)


def test_parse_symlink_at_final_component_reraises_symlink_refused(
    tmp_path: Path,
) -> None:
    """AC-4. Real ``safe_json.load`` invocation against a symlink.
    Mutation caught: any path that strips ``O_NOFOLLOW`` in a future
    re-impl would suddenly follow the link; the wrapper must let
    ``SymlinkRefusedError`` propagate unchanged."""
    real = tmp_path / "real.json"
    real.write_text('{"name":"x","lockfileVersion":3,"packages":{}}')
    link = tmp_path / "package-lock.json"
    link.symlink_to(real)
    with pytest.raises(SymlinkRefusedError):
        _npm.parse(link)


# --- AC-5, AC-7, AC-8, AC-10, AC-11 — malformed-JSON translation ---------------


def test_parse_malformed_json_raises_malformed_lockfile_with_cause_chain(
    tmp_path: Path,
) -> None:
    """AC-5, AC-7. Mutation caught: dropping ``from cause`` (loses
    ``__cause__``); catching ``Exception`` (would absorb unrelated
    types); translating to a different marker class."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"unterminated')  # JSONDecodeError path.
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
    # AC-7: ``__cause__`` is the original MalformedJSONError.
    assert isinstance(exc.value.__cause__, MalformedJSONError)


def test_parse_malformed_json_message_contains_path(tmp_path: Path) -> None:
    """AC-8. Mutation caught: building the message without the path
    (e.g., ``MalformedLockfileError(str(cause))``) — downstream
    WarningId construction in NodeManifestProbe recovers the path
    from ``args[0]``."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text("not valid json at all")
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
    assert str(lockfile) in exc.value.args[0]


def test_parse_top_level_non_mapping_raises_malformed_lockfile(tmp_path: Path) -> None:
    """AC-10. Mutation caught: returning the non-mapping object (the
    cast would silently widen ``list`` to ``NpmLock``); the
    translation pass re-uses the same MalformedJSONError handler.
    ``safe_json._decode`` raises ``MalformedJSONError("expected JSON
    object at top level")`` for any top-level non-dict — we translate
    it like any other malformed-JSON cause."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('["a","b"]')  # top-level JSON array, not a mapping.
    with pytest.raises(MalformedLockfileError):
        _npm.parse(lockfile)


def test_parse_empty_file_raises_malformed_lockfile(tmp_path: Path) -> None:
    """AC-11. Mutation caught: only translating the JSONDecodeError
    path (e.g., ``except json.JSONDecodeError: ...``) would miss the
    empty-file branch — ``safe_json._decode`` raises
    ``MalformedJSONError("empty file")`` *before* ``json.loads`` runs.
    We catch ``MalformedJSONError`` as the class, so empty files
    surface as ``MalformedLockfileError``."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_bytes(b"")
    with pytest.raises(MalformedLockfileError):
        _npm.parse(lockfile)


# --- AC-6, AC-15 — marker discipline ------------------------------------------


def test_raised_marker_carries_only_positional_message_and_no_attributes(
    tmp_path: Path,
) -> None:
    """AC-6, AC-15. Mutation caught: a future "convenience" override
    of ``MalformedLockfileError.__init__(self, *, path, cause)`` would
    be flagged immediately. The Phase-0 invariant
    ``test_subclasses_are_markers_only`` guards the class-level
    contract; this test guards the construction site in _npm.py."""
    lockfile = tmp_path / "package-lock.json"
    lockfile.write_text('{"unterminated')
    with pytest.raises(MalformedLockfileError) as exc:
        _npm.parse(lockfile)
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


def test_npm_module_does_not_reference_sibling_parsers() -> None:
    """AC-12, CLAUDE.md "Extension by addition". Mutation caught: a
    future edit that imports ``_pnpm`` / ``_yarn`` / ``_bun`` into
    ``_npm`` — sibling parsers must be free to evolve independently.
    The shared kernel is ``parsers/safe_json`` + ``codegenie.errors``,
    not other sibling modules."""
    src = inspect.getsource(_npm)
    for forbidden in ("_pnpm", "_yarn", "_bun"):
        assert forbidden not in src, (
            f"_npm.py must not reference sibling parser {forbidden!r}; "
            f"adding a new lockfile format is a new file, not an edit here."
        )


# --- AC-1 — _lockfiles/__init__.py stays inert (S3-02 doesn't edit it) --------


def test_lockfiles_init_remains_inert() -> None:
    """AC-1, CLAUDE.md "Extension by addition". Mutation caught: an
    implementer adding ``from . import _npm`` or ``NpmLock`` to the
    package ``__init__`` — S3-01 settled this file as inert and S3-02
    must not touch it. The contract: ``__all__: list[str] = []`` and
    sibling parsers export from their own modules."""
    from codegenie.probes import _lockfiles

    assert getattr(_lockfiles, "__all__", None) == [], (
        "_lockfiles/__init__.py is settled as inert by S3-01 — S3-02 must "
        "not re-export NpmLock through it. Consumers import siblings directly."
    )
    # Negative: no NpmLock attribute leaked through the package.
    assert not hasattr(_lockfiles, "NpmLock"), (
        "NpmLock must be imported from codegenie.probes._lockfiles._npm, "
        "not the package __init__. S3-03 may revisit if extracting a shared "
        "_translate helper (rule of three)."
    )
