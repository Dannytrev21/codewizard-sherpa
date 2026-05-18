"""S7-02 AC-23 + AC-26 — kernel ``__all__`` + ``_ProbeName`` subset semantics.

Two cross-cutting invariants for ``tests/fixtures/_shape_test_kernel.py``:

- **``__all__`` runtime check (AC-23).** A silent removal of any kernel
  export becomes a build error here; documented contract == runtime
  exports.
- **``_ProbeName`` ⊇ ``default_registry`` (AC-26).** Subset semantics —
  Phase-3+ probes added later do NOT retroactively break this Phase-2
  fixture; but a renamed or newly-added Phase-2 probe whose name fails
  to make it into the Literal IS a build failure.
"""

from __future__ import annotations

from tests.fixtures import _shape_test_kernel as kernel
from tests.fixtures._shape_test_kernel import assert_probe_name_literal_is_superset

_EXPECTED_EXPORTS: frozenset[str] = frozenset(
    {
        "_FIXTURE_NOISE_NAMES",
        "_FORBIDDEN_SUBPATHS",
        "_FileSpec",
        "_ParserKind",
        "_ProbeName",
        "assert_file_content_invariants",
        "assert_file_exists",
        "assert_file_line_endings",
        "assert_file_parses",
        "assert_no_forbidden_subpath",
        "assert_probe_name_literal_is_superset",
        "assert_readme_references_every_spec",
        "assert_tree_is_closed_set",
        "enumerate_rglob_minus_noise",
        "enumerate_tracked",
    }
)


def test_kernel_all_matches_documented_contract() -> None:
    """AC-23 — ``__all__`` is the exact documented export set."""
    actual = frozenset(kernel.__all__)
    extra = actual - _EXPECTED_EXPORTS
    missing = _EXPECTED_EXPORTS - actual
    assert not extra and not missing, (
        f"extras: {sorted(extra)}; missing: {sorted(missing)}. "
        f"Update tests/unit/test_shape_test_kernel.py if the kernel's export "
        f"contract changed deliberately."
    )


def test_kernel_exports_resolve_at_runtime() -> None:
    """Every name in ``__all__`` is a real attribute on the kernel module."""
    for name in kernel.__all__:
        assert hasattr(kernel, name), f"kernel.__all__ lists {name!r} but module has no such attr"


def test_probe_name_literal_is_superset_of_registry() -> None:
    """AC-26 — registered probe names ⊆ ``_ProbeName`` Literal members."""
    assert_probe_name_literal_is_superset()
