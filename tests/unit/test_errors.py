"""Pins the :mod:`codegenie.errors` public surface (S2-01 / AC-1, AC-4).

Sources:
- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Agentic
  best practices — enumerates the nine ``CodegenieError`` subclasses.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md``
  — names ``SecretLikelyFieldNameError`` and ``SymlinkRefusedError``.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
  — names ``DisallowedSubprocessError`` and ``ToolMissingError``.
"""

from __future__ import annotations

import codegenie.errors as e

EXPECTED_SUBCLASSES = {
    "ConfigError",
    "ToolMissingError",
    "ProbeError",
    "ProbeTimeoutError",
    "CacheError",
    "SchemaValidationError",
    "SecretLikelyFieldNameError",
    "DisallowedSubprocessError",
    "SymlinkRefusedError",
}
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
