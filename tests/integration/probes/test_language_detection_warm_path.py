"""S2-04 — warm-path memo integration test + ADR-0004 rejection test.

Two test functions:

- :func:`test_warm_path_memo_hits_once_across_two_probes` — runs
  ``codegenie gather`` against the ``node_typescript_helm/`` fixture
  (S2-03) via :class:`click.testing.CliRunner` and asserts (a) the
  produced envelope's ``probes.language_detection`` slice carries
  ``framework_hints == ["express"]`` and ``monorepo is None``, (b) the
  ``probes.node_build_system`` slice carries ``package_manager ==
  "pnpm"``, (c) neither probe logged a ``probe.failure`` event, (d) the
  ``probe.success`` event each probe emitted reports
  ``confidence == "high"``, and (e) the structlog stream contains
  **exactly one** ``probe.memo.miss`` and **exactly one**
  ``probe.memo.hit`` for ``package.json`` — proving the memo eliminated
  the redundant second parse across the two probes.

  The miss-then-hit assertion is the load-bearing one: ``0/0`` means
  both probes bypassed the memo and called ``safe_json.load`` directly;
  ``2/0`` means the memo was consulted but never returned a hit; either
  is a regression of the S1-07 memo contract.

- :func:`test_extra_field_under_node_build_system_rejected` — ADR-0004
  cross-cutting "additionalProperties: false at each sub-schema" gate.
  Adds a rogue ``unknown_field`` under
  ``probes.node_build_system`` in a minimal valid envelope and asserts
  :class:`codegenie.errors.SchemaValidationError` is raised, with the
  failing path's three components (``probes``,
  ``node_build_system``, ``unknown_field``) embedded in the exception
  message string. The looser per-component ``in`` check (rather than
  asserting the literal RFC-6901 Pointer) is robust against either the
  current JSONPath shape (``$.probes.node_build_system.unknown_field``)
  or a future RFC-6901 normalisation
  (``/probes/node_build_system/unknown_field``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from structlog.testing import capture_logs

from codegenie.cli import cli
from codegenie.errors import SchemaValidationError
from codegenie.schema.validator import validate
from tests.integration.probes.conftest import (
    _copy_tree,
    _count_memo_events,
    _load_envelope,
    _minimal_valid_envelope,
    _stub_node_version_check,
)

FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "node_typescript_helm"


def test_warm_path_memo_hits_once_across_two_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Across :class:`LanguageDetectionProbe` (S2-01) +
    :class:`NodeBuildSystemProbe` (S2-02), ``package.json`` is parsed
    exactly once — second consumer hits the memo.
    """
    # The ``node --version`` cross-check is environment-dependent; stub it
    # so the dev/CI installed Node version never disagrees with the
    # fixture's ``.nvmrc`` and the ``node.version_declared_resolved_disagree``
    # warning does not fire.
    _stub_node_version_check(monkeypatch)

    # arrange: clone fixture into tmp_path so the .codegenie write is hermetic
    repo = _copy_tree(FIXTURE, tmp_path / "repo")

    # act: invoke the real CLI in-process; capture the structlog event stream
    with capture_logs() as events:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])

    # assert: exit clean
    assert result.exit_code == 0, result.output

    # assert: envelope slice content (load-bearing equality, not membership)
    envelope = _load_envelope(repo)
    probes_block = envelope["probes"]
    assert "language_detection" in probes_block, probes_block
    assert "node_build_system" in probes_block, probes_block

    lang_stack = probes_block["language_detection"]["language_stack"]
    assert lang_stack["framework_hints"] == ["express"], lang_stack
    assert lang_stack["monorepo"] is None, lang_stack

    build_system = probes_block["node_build_system"]["build_system"]
    assert build_system["package_manager"] == "pnpm", build_system
    # Stubbed node --version means no warning fires from the disagree
    # cross-check; assert the warnings array is empty so a future
    # regression (silently appending a warning) surfaces here.
    assert build_system["warnings"] == [], build_system

    # assert: no probe.failure events emitted by either probe.
    failures = [
        e
        for e in events
        if e.get("event") == "probe.failure"
        and e.get("probe") in ("language_detection", "node_build_system")
    ]
    assert failures == [], f"unexpected probe.failure events: {failures}"

    # assert: each probe's own probe.success event reports confidence='high'.
    # The probe-emitted event (not the coordinator-emitted one) carries
    # the ``confidence`` field — see ``language_detection.py:480`` and
    # ``node_build_system.py:618``. ``cache_key`` is the coordinator's
    # marker; filter it out to isolate the probe-emitted event.
    for probe_name in ("language_detection", "node_build_system"):
        probe_success = [
            e
            for e in events
            if e.get("event") == "probe.success"
            and e.get("probe") == probe_name
            and "cache_key" not in e
        ]
        assert len(probe_success) == 1, (
            f"expected exactly 1 probe-emitted probe.success for "
            f"{probe_name!r}; got {len(probe_success)}: {probe_success}"
        )
        assert probe_success[0].get("confidence") == "high", probe_success

    # assert: memo event-count invariant (load-bearing). Filter on the
    # structured ``allowlist_match`` key the memo emits, not a substring
    # on ``path``.
    miss, hit = _count_memo_events(events, allowlist_match="package.json")
    assert miss == 1, (
        f"expected exactly 1 probe.memo.miss for package.json; got {miss}. events={events}"
    )
    assert hit == 1, (
        f"expected exactly 1 probe.memo.hit for package.json; got {hit}. events={events}"
    )


def test_extra_field_under_node_build_system_rejected() -> None:
    """ADR-0004 — a rogue field under ``probes.node_build_system``
    fails schema validation with the path surfaced in the error message.
    """
    envelope: dict[str, Any] = _minimal_valid_envelope()
    envelope["probes"]["node_build_system"] = {"unknown_field": 1}

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(envelope)

    message = str(exc_info.value)
    # The validator emits the failing path inside the message string via
    # ``err.json_path`` (jsonschema's JSONPath form). Assert each
    # component appears — robust against either JSONPath or RFC-6901
    # future shape.
    assert "probes" in message, message
    assert "node_build_system" in message, message
    assert "unknown_field" in message, message
