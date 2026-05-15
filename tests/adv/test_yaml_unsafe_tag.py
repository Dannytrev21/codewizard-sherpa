"""Adversarial: ``!!python/object`` tags cannot construct anything via ``safe_yaml``.

The chokepoint in :mod:`codegenie.parsers.safe_yaml` uses
``yaml.CSafeLoader`` exclusively (ADR-0008 + ADR-0009). The structural
defense is: a hostile YAML document carrying ``!!python/object/apply:os.system``
must raise :class:`~codegenie.errors.MalformedYAMLError` and fire **no**
side-effect — no ``touch`` of any path, no ``os.system`` call.

Two distinct invariants are pinned here:

1. **Hermetic refusal** (AC-10) — the ``ConstructorError`` translates to
   ``MalformedYAMLError`` *before* any constructor body would have run.
   The negative test interpolates ``tmp_path`` into a ``touch`` argument
   and asserts the resulting file does not exist post-call.
2. **Translation contract** (AC-11) — ``exc.__cause__`` is a
   ``yaml.YAMLError`` subclass. Rules out a regression where the size
   cap (or another upstream layer) raises ``MalformedYAMLError`` first
   and the test silently passes for the wrong reason.

A positive-control test in the same module (AC-12) loads a minimal
valid ``pnpm-lock.yaml`` to guard against a degenerate
``safe_yaml.load`` replacement that unconditionally raises
``MalformedYAMLError``.

Traces to:
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Adversarial tests" item #4.
- Phase-1 ADR-0008 (in-process parse caps, not per-probe sandbox).
- Phase-1 ADR-0009 (no new C-extension parser dependencies — pins ``CSafeLoader``).
- ``safe_yaml.py:140-145`` — the ``YAMLError`` translation path.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from codegenie.errors import MalformedYAMLError
from codegenie.parsers import safe_yaml


@pytest.mark.adv
def test_unsafe_python_object_tag_refused(tmp_path: Path) -> None:
    """Pins AC-10 + AC-11.

    Catches:
      - a regression that swapped ``yaml.CSafeLoader`` for ``yaml.Loader``
        or ``yaml.SafeLoader`` (the C-only constraint, ADR-0009) — the
        canary file would appear under ``yaml.Loader``.
      - a regression where ``MalformedYAMLError`` is raised by an earlier
        layer (e.g. the size cap), bypassing the ``CSafeLoader`` parse
        — the ``__cause__`` assertion would fail.
    """
    canary = tmp_path / "adv-canary.txt"
    body = (
        "lockfileVersion: '6.0'\n"
        f'adversarial: !!python/object/apply:os.system ["touch {canary}"]\n'
    )
    target = tmp_path / "pnpm-lock.yaml"
    target.write_text(body)

    with pytest.raises(MalformedYAMLError) as exc_info:
        safe_yaml.load(target, max_bytes=1_000_000)

    assert isinstance(exc_info.value.__cause__, yaml.YAMLError), (
        f"translation contract broken: __cause__={type(exc_info.value.__cause__).__name__!s}"
    )
    assert not canary.exists(), (
        f"os.system fired — CSafeLoader chokepoint failed; canary={canary} exists"
    )


@pytest.mark.adv
def test_safe_yaml_positive_control_loads_minimal_lockfile(tmp_path: Path) -> None:
    """Positive control — AC-12.

    Catches a degenerate mutation where ``safe_yaml.load`` is replaced
    with ``raise MalformedYAMLError(...)`` unconditionally, which would
    trivially-pass the negative test above.
    """
    target = tmp_path / "pnpm-lock-valid.yaml"
    target.write_text("lockfileVersion: '6.0'\n")
    result = safe_yaml.load(target, max_bytes=1_000_000)
    assert isinstance(result, dict)
    assert result.get("lockfileVersion") == "6.0"
