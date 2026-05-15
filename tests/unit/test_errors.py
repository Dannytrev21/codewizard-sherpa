"""Pins the :mod:`codegenie.errors` public surface (S2-01 / AC-1, AC-4).

Sources:
- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Agentic
  best practices — enumerates the eleven Phase 0 ``CodegenieError`` subclasses.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md``
  — names ``SecretLikelyFieldNameError`` and ``SymlinkRefusedError``.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
  — names ``DisallowedSubprocessError`` and ``ToolMissingError``.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md`` §Error
  escalation — adds six Phase 1 marker subclasses for ``parsers/`` and
  ``catalogs/`` raise sites (S1-01).
- ``docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md``
  — the structured ``WarningId`` is constructed at the catch site (the
  calling probe), not embedded on the exception class.
"""

from __future__ import annotations

import pytest

import codegenie.errors as e

# Phase 1 — six new marker subclasses (this story: S1-01).
PHASE1_NEW = {
    "SizeCapExceeded",
    "DepthCapExceeded",
    "MalformedJSONError",
    "MalformedYAMLError",
    "MalformedLockfileError",
    "CatalogLoadError",
}

PHASE2_NEW = {
    # Phase 2 (Layers B–G) — S1-02 adds the indices.registry duplicate-name
    # marker. Additional Phase-2 markers (SkillsLoadError, ConventionsError,
    # …) land in their own stories.
    "FreshnessRegistryError",
    # S1-04 adds the TCCM-loader marker. Reason prefix carried in args[0].
    "TCCMLoadError",
}

EXPECTED_SUBCLASSES = (
    {
        # Phase 0 — eleven (corrected count; the prior draft of S1-01 listed 9).
        "ConfigError",
        "ToolMissingError",
        "ProbeError",
        "ProbeTimeoutError",
        "ProbeBudgetExceeded",
        "CacheError",
        "SchemaValidationError",
        "SecretLikelyFieldNameError",
        "DisallowedSubprocessError",
        "SymlinkRefusedError",
        "AllProbesFailedError",
    }
    | PHASE1_NEW
    | PHASE2_NEW
)

DOCUMENTED_MODULE_SLUGS = {
    "exec",
    "cache",
    "sanitizer",
    "validator",
    "writer",
    "coordinator",
    "config",
    "tool_check",
    "schema",
    # Phase 1 additions (S1-01) — additive only; no Phase 0 slug removed.
    "parsers",
    "catalogs",
    # Phase 2 additions (S1-02) — additive only.
    "indices",
    # Phase 2 additions (S1-04) — TCCM loader slug.
    "tccm",
}
MARKER_ALLOWED_DICT_KEYS = {
    "__module__",
    "__qualname__",
    "__doc__",
    # Python 3.13+ compiler-injected (PEP-issued; not user behavior).
    "__firstlineno__",
    "__static_attributes__",
}


def test_codegenie_error_root_is_distinct_subclass_of_exception() -> None:
    # Guards the aliasing-collapse mutation `CodegenieError = Exception`,
    # which would make every Exception trivially a "CodegenieError".
    assert issubclass(e.CodegenieError, Exception)
    assert e.CodegenieError is not Exception
    assert e.CodegenieError.__mro__[1] is Exception  # direct child


def test_all_closure_pins_public_surface() -> None:
    # Adding a typo'd `ProbErrror` or forgetting an __all__ entry must fail.
    assert set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieError"}


def test_every_subclass_directly_inherits_codegenie_error() -> None:
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__mro__[1] is e.CodegenieError, (
            f"{name} must inherit directly from CodegenieError, not transitively"
        )
        assert name in e.__all__


def test_every_subclass_has_raise_site_docstring() -> None:
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__doc__ and len(cls.__doc__.strip()) >= 10, (
            f"{name} must declare a >=10-char raise-site docstring"
        )
        lowered = cls.__doc__.lower()
        assert any(slug in lowered for slug in DOCUMENTED_MODULE_SLUGS), (
            f"{name} docstring must name one of the documented module slugs "
            f"{sorted(DOCUMENTED_MODULE_SLUGS)}"
        )


def test_subclasses_are_markers_only() -> None:
    # No custom __init__, no class attributes — adding behavior is a separate
    # decision and must not be smuggled into the marker hierarchy.
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__init__ is e.CodegenieError.__init__, (
            f"{name} must inherit __init__ from CodegenieError"
        )
        assert set(cls.__dict__.keys()) <= MARKER_ALLOWED_DICT_KEYS, (
            f"{name} declares extra class attributes {cls.__dict__.keys()}; "
            f"subclasses must remain markers"
        )


# --- Phase 1 / S1-01 ----------------------------------------------------------


# AC-6 — every Phase-1 marker accepts a single positional message string,
# round-trips it via .args[0], and exposes NO instance attributes (markers only).
@pytest.mark.parametrize("name", sorted(PHASE1_NEW))
def test_phase1_subclasses_accept_message_arg_and_expose_args0(name: str) -> None:
    cls = getattr(e, name)
    msg = f"/repo/file.ext: cap=64 detail=for {name}"
    exc = cls(msg)
    # Message round-trips via Exception.args (Phase 0 inherited shape).
    assert exc.args == (msg,)
    assert exc.args[0] == msg
    assert str(exc) == msg  # Exception.__str__ delegates to args[0] when len==1.
    # Markers expose NO instance state — these are deliberate negatives.
    for forbidden_attr in ("path", "cap", "detail", "warning_id"):
        assert not hasattr(exc, forbidden_attr), (
            f"{name} must remain a marker; instance must not carry "
            f"{forbidden_attr!r}. Path/cap/detail live in the message."
        )


# AC-6 — caught instance still exposes args[0]; semantics live in catch context.
def test_caught_phase1_exception_recovers_via_args0() -> None:
    with pytest.raises(e.CodegenieError) as exc_info:
        raise e.SizeCapExceeded("/r/package.json: cap=5242880")
    assert exc_info.value.args[0] == "/r/package.json: cap=5242880"
    assert isinstance(exc_info.value, e.SizeCapExceeded)
    assert isinstance(exc_info.value, e.CodegenieError)


# AC-7 — root unchanged.
def test_codegenie_error_root_init_unchanged() -> None:
    assert e.CodegenieError.__init__ is Exception.__init__


# AC-8 — class identity preserved (no shadow, no rename).
def test_symlink_refused_class_identity_preserved() -> None:
    assert e.SymlinkRefusedError.__module__ == "codegenie.errors"
    assert e.SymlinkRefusedError is e.__dict__["SymlinkRefusedError"]
    assert issubclass(e.SymlinkRefusedError, e.CodegenieError)


# AC-5 — CatalogLoadError docstring records the hard-fail semantics
# (arch §Edge cases row 9).
def test_catalog_load_error_doc_marks_hard_fail() -> None:
    doc = (e.CatalogLoadError.__doc__ or "").lower()
    assert "hard fail" in doc, (
        "CatalogLoadError docstring must mark the hard-fail-at-CLI-startup invariant "
        "per arch §Edge cases row 9; downstream catches must not soft-degrade it."
    )


# AC-1, AC-2 — new subclasses inherit DIRECTLY from CodegenieError
# (not transitively) and are exported via __all__.
@pytest.mark.parametrize("name", sorted(PHASE1_NEW))
def test_phase1_subclasses_inherit_codegenie_error_directly(name: str) -> None:
    cls = getattr(e, name)
    assert cls.__mro__[1] is e.CodegenieError
    assert issubclass(cls, e.CodegenieError)
    assert name in e.__all__
