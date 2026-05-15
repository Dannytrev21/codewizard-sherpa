"""S1-08 AC-6a — ``_seam_registry_for_task`` consumes
``default_registry.sorted_for_dispatch()`` instead of ``all_probes()``.

The seam's job is to (a) trigger ``codegenie.probes`` import side effects so
every concrete ``@register_probe`` decoration runs, then (b) instantiate the
classes in the order ``sorted_for_dispatch`` declares — heavy → medium →
light, then runs_last=True at the tail. The coordinator trusts the order.

Pins the integration point named by AC-6a (`src/codegenie/cli.py`) so a
later regression to ``all_probes()`` (which preserves *registration* order,
not dispatch order) fails loud here.

A sibling seam helper ``_seam_runs_last_names`` returns the frozenset of
probe names whose registry entry has ``runs_last=True``; this is what the
coordinator's partition reads to hoist a ``tier="base"`` + ``runs_last=True``
probe out of the prelude (AC-13).
"""

from __future__ import annotations

from typing import Any

import pytest

from codegenie.probes import registry as registry_mod
from codegenie.probes.registry import Registry


def _make_probe_cls(name_: str) -> type:
    from codegenie.probes.base import Probe

    class _P(Probe):
        async def run(self, repo: Any, ctx: Any) -> Any:  # type: ignore[override]
            raise NotImplementedError

    _P.name = name_
    _P.layer = "B"
    _P.tier = "task_specific"
    _P.applies_to_tasks = ["*"]
    _P.applies_to_languages = ["*"]
    _P.requires = []
    _P.declared_inputs = []
    _P.__name__ = name_
    return _P


def test_seam_returns_probes_in_sorted_for_dispatch_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A registry containing one light, one medium, one heavy, and one
    runs_last=True probe — registered in that registration order — must be
    instantiated by the seam in (heavy, medium, light, runs_last) order.

    Mutation resistance: an implementation that still calls ``all_probes()``
    returns the input in registration order; this assertion fails because
    ``heavy`` is registered second but must appear first.
    """
    from codegenie import cli as cli_mod

    fresh = Registry()
    fresh.register(_make_probe_cls("seam_light"))
    fresh.register(_make_probe_cls("seam_heavy"), heaviness="heavy")
    fresh.register(_make_probe_cls("seam_medium"), heaviness="medium")
    fresh.register(_make_probe_cls("seam_runs_last"), runs_last=True)

    monkeypatch.setattr(registry_mod, "default_registry", fresh)

    instances = cli_mod._seam_registry_for_task()
    names = [p.name for p in instances]
    assert names == ["seam_heavy", "seam_medium", "seam_light", "seam_runs_last"], names

    # Each entry is an instance, not a class (preserves "instantiate each
    # class" step the Phase 0/1 seam established).
    from codegenie.probes.base import Probe

    assert all(isinstance(p, Probe) for p in instances)


def test_seam_runs_last_names_returns_frozenset_of_runs_last_probe_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sibling helper that surfaces the names of ``runs_last=True``
    entries — the coordinator partition reads this to hoist runs_last out
    of the prelude per AC-13."""
    from codegenie import cli as cli_mod

    fresh = Registry()
    fresh.register(_make_probe_cls("rl_light"))
    fresh.register(_make_probe_cls("rl_runs_last_a"), runs_last=True)
    fresh.register(_make_probe_cls("rl_runs_last_b"), heaviness="heavy", runs_last=True)
    monkeypatch.setattr(registry_mod, "default_registry", fresh)

    names = cli_mod._seam_runs_last_names()
    assert isinstance(names, frozenset)
    assert names == frozenset({"rl_runs_last_a", "rl_runs_last_b"})


def test_seam_runs_last_names_is_empty_when_no_runs_last_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codegenie import cli as cli_mod

    fresh = Registry()
    fresh.register(_make_probe_cls("only_light"))
    fresh.register(_make_probe_cls("only_heavy"), heaviness="heavy")
    monkeypatch.setattr(registry_mod, "default_registry", fresh)

    assert cli_mod._seam_runs_last_names() == frozenset()
