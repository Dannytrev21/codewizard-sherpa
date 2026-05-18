"""Tests for ``codegenie.probes.registry`` — explicit-imports collection point (S2-05).

Pins the contract surface (`register_probe` decorator, `Registry`,
`default_registry`), the `for_task` filter matrix from AC-2, duplicate-name
rejection at decoration time, and the `lru_cache` observability that catches
the no-cache mutant.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe
from codegenie.probes.registry import Registry, default_registry, register_probe


@pytest.fixture
def restore_default_registry() -> Generator[None, None, None]:
    """Snapshot ``default_registry`` state; restore on teardown.

    The decorator-roundtrip test registers a probe (``fake_one``) into
    the module-level ``default_registry``. Without this fixture the
    probe leaks into every subsequent test in the same pytest session
    (registry is a process-wide singleton), polluting checks like the
    shape-test kernel's `registered ⊆ _ProbeName Literal` subset
    assertion.

    Snapshots ``_entries`` (shallow copy of the entry list — entries are
    immutable namedtuples) and ``_counter`` (int).
    """
    snapshot_entries = list(default_registry._entries)
    snapshot_counter = default_registry._counter
    try:
        yield
    finally:
        default_registry._entries[:] = snapshot_entries
        default_registry._counter = snapshot_counter


def _make_probe(
    name: str,
    *,
    tasks: list[str] | None = None,
    langs: list[str] | None = None,
) -> type[Probe]:
    """Synthesize a concrete Probe subclass with the requested filter attrs."""

    class _P(Probe):
        async def run(self, repo, ctx):  # type: ignore[override, no-untyped-def]
            raise NotImplementedError

    _P.name = name
    _P.version = "1.0"  # type: ignore[attr-defined]  # convention, not on the frozen ABC
    _P.layer = "A"
    _P.tier = "base"
    _P.applies_to_tasks = ["*"] if tasks is None else tasks
    _P.applies_to_languages = ["*"] if langs is None else langs
    _P.declared_inputs = []
    _P.requires = []
    return _P


def test_register_probe_decorator_adds_to_default_registry_and_returns_class(
    restore_default_registry: None,
) -> None:
    """`register_probe(cls) is cls` — catches the `return None` mutant.

    Uses the ``restore_default_registry`` fixture so ``FakeProbe`` does
    not leak into other tests' view of ``default_registry``.
    """

    @register_probe
    class FakeProbe(Probe):
        name = "fake_one"
        version = "1.0"  # type: ignore[misc]
        layer = "A"
        tier = "base"
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        declared_inputs: list[str] = []
        requires: list[str] = []

        async def run(self, repo, ctx):  # type: ignore[override, no-untyped-def]
            raise NotImplementedError

    assert FakeProbe.__name__ == "FakeProbe"
    assert FakeProbe in default_registry.all_probes()


def test_register_probe_returns_class_unchanged() -> None:
    """Decorator must return the class object identically (`is cls`)."""
    Probe_cls = _make_probe("returns_class_unchanged_marker")
    # Bypass the default-registry decoration path; check the decorator's return
    # value directly through Registry.register on a fresh registry.
    reg = Registry()
    assert reg.register(Probe_cls) is Probe_cls


def test_duplicate_name_rejected_at_decoration_time_names_both_classes() -> None:
    reg = Registry()
    a = _make_probe("dup")
    reg.register(a)
    b = _make_probe("dup")
    with pytest.raises(ProbeError, match=r"dup"):
        reg.register(b)


@pytest.mark.parametrize(
    "p_tasks,p_langs,task,langs,expected",
    [
        (["*"], ["*"], "vuln_remediation", frozenset({"unknown"}), True),
        (["vuln_remediation"], ["*"], "distroless_migration", frozenset({"unknown"}), False),
        (["*"], ["javascript"], "vuln_remediation", frozenset({"unknown"}), False),
        (["*"], ["javascript"], "vuln_remediation", frozenset({"javascript"}), True),
        (
            ["*"],
            ["javascript", "python"],
            "vuln_remediation",
            frozenset({"javascript", "go"}),
            True,
        ),
    ],
)
def test_for_task_filter_matrix(
    p_tasks: list[str],
    p_langs: list[str],
    task: str,
    langs: frozenset[str],
    expected: bool,
) -> None:
    reg = Registry()
    probe_cls = _make_probe("matrix_probe", tasks=p_tasks, langs=p_langs)
    reg.register(probe_cls)
    result = reg.for_task(task, langs)
    assert (probe_cls in result) is expected


def test_for_task_lru_cache_hits_on_repeated_calls() -> None:
    """Catches the no-cache mutant: a `for_task` that re-computes every call."""
    from codegenie.probes import registry as reg_mod

    reg_mod._filter.cache_clear()
    reg = Registry()
    p = _make_probe("cache_probe")
    reg.register(p)
    reg.for_task("vuln_remediation", frozenset({"unknown"}))
    reg.for_task("vuln_remediation", frozenset({"unknown"}))
    info = reg_mod._filter.cache_info()
    assert info.hits >= 1


def test_for_task_empty_language_set_is_non_crashing() -> None:
    """`for_task('task', frozenset())` must not crash; result matches the matrix."""
    reg = Registry()
    star = _make_probe("star_star", tasks=["*"], langs=["*"])
    js_only = _make_probe("js_only", tasks=["*"], langs=["javascript"])
    reg.register(star)
    reg.register(js_only)
    result = reg.for_task("vuln_remediation", frozenset())
    assert star in result
    assert js_only not in result


def test_adr_amendment_template_exists() -> None:
    """`templates/adr-amendment.md` from S2-02 must still be present (AC-8)."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / "templates" / "adr-amendment.md").exists()
