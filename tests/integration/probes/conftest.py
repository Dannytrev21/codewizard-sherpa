"""Shared helpers for Phase 1 cross-probe integration tests (S2-04, S2-05, S5-05).

Three concrete consumers > rule-of-three (CLAUDE.md "Extension by addition"),
so the helpers + the autouse seam disablement live here from the start
rather than being copy-pasted into each test file.

Helpers exposed:

- :func:`_copy_tree` — clones a fixture tree under ``tmp_path`` so each
  test's ``.codegenie/`` writes stay hermetic.
- :func:`_load_envelope` — reads
  ``<repo>/.codegenie/context/repo-context.yaml`` via ``yaml.safe_load``.
- :func:`_count_memo_events` — filters captured structlog events by the
  structured ``allowlist_match`` key
  (:mod:`codegenie.coordinator.parsed_manifest_memo` emits this verbatim)
  and returns ``(miss_count, hit_count)``. Adding a new memoizable
  manifest in Phase 2 (``scip-index.json``) requires zero edits to this
  helper.
- :func:`_minimal_valid_envelope` — smallest envelope dict the
  :func:`codegenie.schema.validator.validate` accepts (envelope schema's
  required keys are ``schema_version``, ``generated_at``,
  ``repo.{root, git_commit}``, ``probes``). Used by ADR-0004 rejection
  tests.
- :func:`_stub_node_version_check` — neutralises the
  :func:`codegenie.exec.run_allowlisted` call ``NodeBuildSystemProbe``
  uses for ``node --version`` cross-check so the
  ``node.version_declared_resolved_disagree`` warning does not fire when
  the dev/CI machine's installed Node differs from the fixture's
  ``.nvmrc``. Module-local rebind (a ``SimpleNamespace`` shim around
  ``codegenie.exec``) following the
  :func:`tests.smoke.conftest._install_scandir_counter` precedent — the
  global ``codegenie.exec`` module is never mutated.
- :func:`_install_scandir_counter` — re-exported from
  :mod:`tests.smoke.conftest` (one source of truth, no copy-paste).
  Used by S2-05's two-probe warm-path cache-hit test to count
  ``os.scandir`` invocations inside ``codegenie.probes.language_detection``
  *only* — the global :mod:`os` is untouched.
- :func:`_stat_snapshot` — captures ``{POSIX-resolved-path-str:
  (mtime_ns, size)}`` for every regular file under a root. Used by
  S2-05 as belt-and-suspenders fixture-immutability invariant; not
  the cache-key proof (ADR-0002 derives cache keys from
  ``content_hash``, not live ``os.stat``). Keys are POSIX-form
  resolved strings to dodge the macOS case-insensitive-FS Path-equality
  foot-gun documented in ADR-0002.
- :data:`WARM_PATH_CACHE_HIT_PROBES` — frozenset of probe names whose
  warm-path cache invariant is exercised by ``tests/integration/probes/
  test_cache_hit_on_real_repo.py``. S5-05 extends to all six probes by
  adding entries here — **zero** edits to any test function body.

The ``_disable_cli_configure_logging`` autouse fixture below is the
load-bearing seam disablement: ``click.testing.CliRunner.invoke``
otherwise re-runs :func:`codegenie.logging.configure_logging`, which
replaces structlog's active processor chain and silently drops every
event the :func:`structlog.testing.capture_logs` chain was swapped in to
collect. Without it, every memo-event count in this suite collapses to
``0`` and the test produces a misleading RED. Mirrors
:func:`tests.smoke.conftest._disable_cli_configure_logging` verbatim —
two sources of truth for the same seam are accepted to keep this
directory self-contained; lifting to a root ``tests/conftest.py`` is a
later cleanup.
"""

from __future__ import annotations

import shutil
import types
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

import pytest
import yaml

import codegenie.exec as _exec_mod
import codegenie.probes.node_build_system as _nbs_mod
from tests.smoke.conftest import _install_scandir_counter

if TYPE_CHECKING:
    from click.testing import Result

__all__ = [
    "PHASE_1_PROBE_NAMES",
    "PHASE_1_PROBE_TO_SLICE",
    "WARM_PATH_CACHE_HIT_PROBES",
    "_copy_tree",
    "_count_memo_events",
    "_install_scandir_counter",
    "_invoke_gather",
    "_load_envelope",
    "_minimal_valid_envelope",
    "_stat_snapshot",
    "_stub_node_version_check",
    "assert_monorepo_markers",
    "assert_only_language_stack",
    "assert_phase_1_slices_present",
]


PHASE_1_PROBE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "language_detection",
        "node_build_system",
        "node_manifest",
        "ci",
        "deployment",
        "test_inventory",
    }
)
"""All Phase-1 Layer-A probe names. Adding a 7th probe in Phase 2 = one
frozenset insertion + one :data:`PHASE_1_PROBE_TO_SLICE` entry; zero
edits to any S5-05 test function body. (Open/Closed at the file
boundary; CLAUDE.md 'Extension by addition'.)"""


PHASE_1_PROBE_TO_SLICE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "language_detection": "language_stack",
        "node_build_system": "build_system",
        "node_manifest": "manifests",
        "ci": "ci",
        "deployment": "deployment",
        "test_inventory": "test_inventory",
    }
)
"""Probe-name → declared slice-key. The envelope path is
``probes[<probe>][<slice>]``; this mapping is the source of truth (the
slice name does NOT always match the probe name — note
``language_detection``→``language_stack``,
``node_build_system``→``build_system``,
``node_manifest``→``manifests``). First-draft S5-05 conflated the two."""


WARM_PATH_CACHE_HIT_PROBES: Final[frozenset[str]] = PHASE_1_PROBE_NAMES
"""Probes whose warm-path cache invariant is asserted by
``test_cache_hit_on_real_repo.py``'s metamorphic pair. Aliased to
:data:`PHASE_1_PROBE_NAMES` so a Phase-2 probe addition updates both
frozensets atomically; the module-load invariant below refuses to load
if they diverge.

(Open/Closed at the file boundary; CLAUDE.md "Extension by addition".)
"""


assert WARM_PATH_CACHE_HIT_PROBES == PHASE_1_PROBE_NAMES, (
    "S5-05 invariant: WARM_PATH_CACHE_HIT_PROBES must equal "
    "PHASE_1_PROBE_NAMES. Phase 2's new probes must update both."
)


def _copy_tree(src: Path, dst: Path) -> Path:
    """Clone ``src`` into ``dst`` and return ``dst``.

    Wraps :func:`shutil.copytree`. The Phase 1 fixtures contain no
    symlinks; default ``symlinks=False`` behaviour is intentional.
    """
    shutil.copytree(src, dst)
    return dst


def _load_envelope(repo: Path) -> dict[str, Any]:
    """Load ``<repo>/.codegenie/context/repo-context.yaml`` via ``yaml.safe_load``.

    Fails fast with a clear message if the envelope is missing — a
    coordinator/CLI bug should surface as a useful error here, not a
    downstream ``TypeError`` against ``None``.
    """
    yaml_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    assert yaml_path.exists(), f"envelope missing at {yaml_path}"
    loaded = yaml.safe_load(yaml_path.read_text())
    assert isinstance(loaded, dict), f"envelope is not a mapping: {type(loaded).__name__}"
    return loaded


def _count_memo_events(
    events: Iterable[Mapping[str, Any]], *, allowlist_match: str
) -> tuple[int, int]:
    """Return ``(miss_count, hit_count)`` filtered by structured ``allowlist_match``.

    The memo emits ``allowlist_match=path.name`` on every hit/miss event
    (see :mod:`codegenie.coordinator.parsed_manifest_memo`); filtering on
    this key (rather than a substring on ``path``) is the precise way to
    count manifest reads and is robust to future allowlist widenings.
    """
    miss = 0
    hit = 0
    for event in events:
        if event.get("allowlist_match") != allowlist_match:
            continue
        kind = event.get("event")
        if kind == "probe.memo.miss":
            miss += 1
        elif kind == "probe.memo.hit":
            hit += 1
    return miss, hit


def _minimal_valid_envelope() -> dict[str, Any]:
    """Smallest envelope dict the
    :func:`codegenie.schema.validator.validate` accepts.

    The envelope schema requires ``schema_version``, ``generated_at``,
    ``repo.{root, git_commit}``, and ``probes`` (see
    ``src/codegenie/schema/repo_context.schema.json``). Reused by ADR-0004
    rejection tests across S2-04, S2-05, S5-05 and future probes' RED
    additions.
    """
    return {
        "schema_version": "0.1.0",
        "generated_at": "2026-05-14T00:00:00Z",
        "repo": {"root": "test-repo", "git_commit": None},
        "probes": {},
    }


def _stat_snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Return ``{POSIX-resolved-path-str: (mtime_ns, size)}`` for every
    regular file under ``root``, **excluding** the codegenie output
    namespace ``<root>/.codegenie/`` (which the gather legitimately
    writes to on every run).

    Keys are POSIX-form resolved strings — *not* :class:`pathlib.Path` —
    to dodge the macOS case-insensitive-FS Path-equality foot-gun
    documented in ADR-0002 (two distinct Path instances on a
    case-insensitive volume compare equal even when their bytes differ,
    silently masking drift between cold and warm gathers).

    Used as a belt-and-suspenders fixture-immutability invariant: the
    **fixture inputs** must not drift between two successive gathers.
    The actual cache-key invariance proof lives in the structlog
    ``probe.success``/``probe.cache_hit`` ``cache_key`` byte-equality
    assertion (ADR-0002 routes cache keys through ``content_hash``, not
    live ``os.stat``, so this snapshot is *not* the cache-key proof).
    """
    output_ns = (root / ".codegenie").resolve()
    return {
        str(p.resolve()): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in root.rglob("*")
        if p.is_file() and output_ns not in p.resolve().parents
    }


def _stub_node_version_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Module-locally neutralise the ``node --version`` exec call.

    ``NodeBuildSystemProbe.run`` calls ``await _exec.run_allowlisted([
    "node", "--version"], ...)`` to populate
    ``node_version_resolved_locally``. When the resolved version differs
    from the fixture's ``.nvmrc`` pin, the probe emits the
    ``node.version_declared_resolved_disagree`` warning — a real
    soft-degrade signal, but environment-dependent (the test would pass
    on a machine running Node 20.11.0 and fail elsewhere). Stub it to
    raise :class:`codegenie.errors.ToolMissingError`, which the probe
    handles by returning ``node_version_resolved_locally=None`` and not
    appending the disagree warning.

    Pattern follows :func:`tests.smoke.conftest._install_scandir_counter`:
    rebind the module's ``_exec`` name to a
    :class:`types.SimpleNamespace` shim mirroring every public attribute
    of :mod:`codegenie.exec` plus a stubbed ``run_allowlisted``. The
    global :mod:`codegenie.exec` module is **not** mutated.
    """
    from codegenie.errors import ToolMissingError

    async def _refusing(argv: list[str], *, cwd: Path, timeout_s: float) -> object:
        raise ToolMissingError(f"node disabled for integration test: argv={argv!r}")

    shim = types.SimpleNamespace()
    for attr in dir(_exec_mod):
        if not attr.startswith("_"):
            setattr(shim, attr, getattr(_exec_mod, attr))
    shim.run_allowlisted = _refusing
    monkeypatch.setattr(_nbs_mod, "_exec", shim)


def _invoke_gather(repo: Path) -> Result:
    """Invoke ``codegenie --no-gitignore gather <repo>`` via the click runner.

    Promoted from ``test_cache_hit_on_real_repo.py`` (S5-05 AC-INFRA-3):
    seven+ call sites across Phase-1's integration tests cross the
    rule-of-three threshold. ``--no-gitignore`` is the documented Phase-0
    override that avoids coupling integration tests to TTY-prompt
    behavior; global flags MUST precede the subcommand (click left-to-
    right option binding).
    """
    from click.testing import CliRunner

    from codegenie.cli import cli

    return CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])


def assert_phase_1_slices_present(envelope: Mapping[str, Any]) -> None:
    """Assert every Phase-1 probe has its declared slice non-empty.

    Walks :data:`PHASE_1_PROBE_TO_SLICE` and raises ``AssertionError``
    with a structured message naming which probe/slice failed. Pure
    helper (no I/O); reusable by S6-01's golden-file regen test.
    """
    probes = envelope.get("probes", {})
    for probe_name, slice_key in PHASE_1_PROBE_TO_SLICE.items():
        assert probe_name in probes, f"missing probe entry: {probe_name!r}; got={sorted(probes)!r}"
        slice_obj = probes[probe_name].get(slice_key)
        assert slice_obj, f"empty slice: probes.{probe_name}.{slice_key} = {slice_obj!r}"


def assert_only_language_stack(envelope: Mapping[str, Any]) -> None:
    """Assert the three Node-only probes are ABSENT (ADR-0010 contract).

    ``ci`` and ``deployment`` (``applies_to_languages = ["*"]``) MAY be
    present with empty inner slices — ADR-0010 permits both shapes for
    ``"*"``-applicability probes. Only the three Node-only probes
    (``node_build_system``, ``node_manifest``, ``test_inventory``) MUST
    be absent on a non-Node repo.
    """
    probes = envelope.get("probes", {})
    assert "language_detection" in probes, (
        f"language_detection must be present; got={sorted(probes)!r}"
    )
    assert "language_stack" in probes["language_detection"], probes["language_detection"]
    for forbidden in ("node_build_system", "node_manifest", "test_inventory"):
        assert forbidden not in probes, (
            f"{forbidden!r} must be absent on a non-Node repo "
            f"(ADR-0010 absence-is-the-contract); got={sorted(probes)!r}"
        )


def assert_monorepo_markers(
    envelope: Mapping[str, Any],
    *,
    expected_tool: str,
    expected_markers: Sequence[str],
) -> None:
    """Assert the ``monorepo`` block matches the expected tool + sorted markers.

    ``markers`` is the sorted union of hit marker basenames per the
    ``language_detection`` schema (S2-01).
    """
    monorepo = envelope["probes"]["language_detection"]["language_stack"]["monorepo"]
    assert monorepo is not None, "monorepo block must not be None on a monorepo fixture"
    assert monorepo["tool"] == expected_tool, monorepo
    assert monorepo["markers"] == sorted(expected_markers), monorepo


@pytest.fixture(autouse=True)
def _disable_cli_configure_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op ``codegenie.cli._seam_configure_logging`` for every test in
    this directory — see module docstring for why this is load-bearing.
    """
    import codegenie.cli

    monkeypatch.setattr(codegenie.cli, "_seam_configure_logging", lambda verbose: None)
