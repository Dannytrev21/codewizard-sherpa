"""``codegenie`` CLI entry point — vertical-slice command surface (S4-02).

This module is the **lazy-import boundary**: ``import codegenie.cli`` and the
``--help`` / ``--version`` paths must not transitively load the heavy modules
listed in the import-linter contract (``yaml``, ``jsonschema``, ``pydantic``,
``blake3``, ``structlog``). Every heavy dependency is dispatched through
``importlib.import_module`` inside a function body — dynamic imports are
invisible to AST analysis (per S3-06's lesson) so the import-linter contract
on ``codegenie.cli`` stays kept while real work happens inside subcommands.

The CLI ships three subcommands in Phase 0:

- ``gather <path>`` — the vertical slice. Walks the repo, dispatches the
  registered probes through the coordinator, writes ``repo-context.yaml``
  + a per-run audit record. Exit codes ``0/2/3/5/6`` documented in
  ``--help``; exit ``1`` is the click fallback for unhandled exceptions.
- ``audit verify`` — S3-06's pure-read verifier. Preserved verbatim
  (``--runs-dir`` / ``--cache-dir`` / ``--yaml-path`` flag surface; exit
  ``0`` clean, exit ``4`` mismatch).
- ``cache gc`` — Phase-1+ stub. Logs ``cache.gc.stub`` and exits 0.

Each major step in :func:`gather`'s body is delegated to a module-scope
``_seam_*`` function. Tests patch these seams to assert call ordering and
the exit-code dispatch table without exercising the full pipeline.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import click

from codegenie.errors import (
    AllProbesFailedError,
    CodegenieError,
    SchemaValidationError,
    SecretLikelyFieldNameError,
    SymlinkRefusedError,
    VulnFeedFetchError,
    VulnIndexMigrationNotApplied,
    VulnRefreshPartialError,
)
from codegenie.version import __version__

if TYPE_CHECKING:
    # ``RedactedSlice`` lives in ``codegenie.output.redacted_slice``, a
    # Pydantic-backed module. The cold-start contract (ADR phase-0006,
    # ``codegenie.cli must not top-level import heavy modules``) is honored
    # because this branch is unreachable at runtime — Python evaluates
    # ``TYPE_CHECKING`` as ``False``. The import-linter ``ignore_imports``
    # whitelist names this edge explicitly so the static contract stays
    # green; the runtime ``isinstance`` checks below import the class
    # lazily via ``importlib.import_module``.
    from codegenie.output.redacted_slice import RedactedSlice

__all__ = ["cli"]


# --------------------------------------------------------------------------
# Exit-code dispatch table — module-scope single source of truth (AC-9).
# Adding a code requires a story amendment + ``test_dispatch_table_snapshot``
# update. The order in --help text inherits from this dict at format time.
# --------------------------------------------------------------------------

_EXIT_CODE_DISPATCH: dict[type[CodegenieError], int] = {
    AllProbesFailedError: 2,
    SchemaValidationError: 3,
    VulnRefreshPartialError: 4,
    SymlinkRefusedError: 5,
    SecretLikelyFieldNameError: 6,
    VulnFeedFetchError: 5,
    VulnIndexMigrationNotApplied: 7,
}


# Map from gather exit code to the structured ``cli.end`` outcome label.
_OUTCOME_BY_EXIT: dict[int, str] = {
    0: "ok",
    2: "probes_failed",
    3: "schema_invalid",
    5: "symlink_refused",
    6: "secret_field",
}


class ProbeNameCollisionError(RuntimeError):
    """Two probes registered the same ``name`` — programming error (AC-24).

    Maps to exit 1 via the click default unhandled-exception path; intentionally
    NOT a :class:`CodegenieError` subclass so it never enters the documented
    user-facing exit-code namespace (``0/2/3/5/6``).
    """


# --------------------------------------------------------------------------
# Seam helpers — each is a module-scope callable so tests can monkeypatch
# them on ``codegenie.cli.<name>`` to assert orchestration order (AC-20)
# and exit-code dispatch (AC-9) without driving the whole pipeline.
# --------------------------------------------------------------------------


def _seam_configure_logging(verbose: bool) -> None:
    """Step 1 — configure structlog. Lazy-imported via importlib so the
    import-linter graph for :mod:`codegenie.cli` stays clean."""
    logging_mod = importlib.import_module("codegenie.logging")
    logging_mod.configure_logging(verbose=verbose)


def _seam_check_tools(refresh: bool) -> dict[str, str]:
    """Step 2 — tool-readiness cache (``~/.codegenie/.tool-cache.json``).

    Read-or-detect-then-write. Mode ``0700`` on the parent dir; mode ``0600``
    on the JSON file. Atomic write via ``<tmp> → fsync → os.replace``. A
    corrupt cache JSON is treated as a miss and re-written (AC-22). Phase 0
    checks ``git`` only.
    """
    import json
    import os
    import tempfile

    structlog = importlib.import_module("structlog")
    log = structlog.get_logger(__name__)

    home = Path.home()
    cache_dir = home / ".codegenie"
    cache_path = cache_dir / ".tool-cache.json"

    # First-run dir creation (AC-7).
    if not cache_dir.exists():
        cache_dir.mkdir(mode=0o700)
    os.chmod(cache_dir, 0o700)

    cached: dict[str, str] | None = None
    if not refresh and cache_path.exists():
        try:
            raw = cache_path.read_text()
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "git" in parsed:
                cached = {str(k): str(v) for k, v in parsed.items()}
        except (OSError, ValueError, json.JSONDecodeError):
            # AC-22: corrupt JSON → miss + warn + re-detect.
            log.warning("tool_cache.invalid", path=str(cache_path))
            cached = None

    if cached is not None:
        return cached

    # Detect.
    versions = {"git": _detect_git_version()}

    # Atomic write: tempfile in same dir → fsync → os.replace → chmod.
    body = json.dumps(versions, sort_keys=True).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=".tool-cache.", suffix=".tmp", dir=cache_dir)
    try:
        try:
            os.write(fd, body)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp_name, cache_path)
    except OSError:
        # Clean up tmp on failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    os.chmod(cache_path, 0o600)
    os.chmod(cache_dir, 0o700)
    return versions


def _detect_git_version() -> str:
    """Run ``git --version`` through the allowlist wrapper; return stdout
    stripped. Failure (missing tool, timeout) returns the empty string so
    a partial environment still produces a writable cache."""
    import asyncio

    exec_mod = importlib.import_module("codegenie.exec")
    errors_mod = importlib.import_module("codegenie.errors")

    async def _run() -> str:
        try:
            result = await exec_mod.run_allowlisted(
                ["git", "--version"], cwd=Path.cwd(), timeout_s=10
            )
        except (
            errors_mod.ToolMissingError,
            errors_mod.DisallowedSubprocessError,
            errors_mod.ProbeTimeoutError,
        ):
            return ""
        if result.returncode != 0:
            return ""
        decoded: str = result.stdout.decode("utf-8", errors="replace").strip()
        return decoded

    return asyncio.run(_run())


def _seam_maybe_append_gitignore(repo_root: Path, *, auto: bool, skip: bool) -> None:
    """Step 3 — `.gitignore` mutation (S4-03).

    Thin seam over :func:`codegenie.output.gitignore.maybe_append_gitignore`.
    The helper is the source of truth for branch precedence, byte-exact
    append contract, atomic-write, and the ``gitignore.append.*`` event
    family. ``importlib.import_module`` is mandatory here — the helper
    transitively imports ``structlog``, which the cli.py import-linter
    contract forbids as an AST-visible top-level import.
    """
    gitignore_mod = importlib.import_module("codegenie.output.gitignore")
    gitignore_mod.maybe_append_gitignore(repo_root, auto=auto, skip=skip)


def _seam_load_config(repo_root: Path, cli_overrides: dict[str, Any]) -> Any:
    """Step 4 — read + merge config (defaults < global < repo < CLI)."""
    loader_mod = importlib.import_module("codegenie.config.loader")
    return loader_mod.load_config(repo_root, cli_overrides)


def _seam_git_rev_parse(repo_root: Path) -> str | None:
    """Step 5 — `git rev-parse HEAD` via the allowlist wrapper.

    Any allowlist / tool-missing / timeout / non-zero exit → ``None``
    (AC-18). The async surface is wrapped in :func:`asyncio.run` so the
    caller stays synchronous.
    """
    import asyncio

    exec_mod = importlib.import_module("codegenie.exec")
    errors_mod = importlib.import_module("codegenie.errors")

    async def _run() -> str | None:
        try:
            result = await exec_mod.run_allowlisted(
                ["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_s=10
            )
        except (
            errors_mod.ToolMissingError,
            errors_mod.DisallowedSubprocessError,
            errors_mod.ProbeTimeoutError,
            FileNotFoundError,
            NotADirectoryError,
        ):
            return None
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8", errors="replace").strip() or None

    return asyncio.run(_run())


def _seam_registry_for_task() -> list[Any]:
    """Step 6 — resolve the probes the gather dispatches.

    Returns every probe registered at import time, **instantiated in
    coordinator-dispatch order** (``heavy → medium → light``, then
    ``runs_last=True`` at the tail — 02-ADR-0003 + S1-08 AC-6a). The
    registry's ``for_task`` filter is bypassed at the seam because
    pre-gather we only know ``detected_languages = {"unknown"}``; the
    :func:`codegenie.coordinator.coordinator.gather` prelude pass enriches
    the snapshot with real language counts after Wave 1 runs, and the
    coordinator dispatches every passed-in probe regardless. Per-probe
    "is this applicable" lives in each probe's :meth:`Probe.applies` / its
    no-op-on-missing-inputs branch (e.g.,
    :class:`NodeBuildSystemProbe` emits a minimal slice with
    ``package_manager: null`` when ``package.json`` is absent).
    """
    # Importing the probes package triggers every concrete probe module's
    # ``@register_probe`` decorator (see ``codegenie/probes/__init__.py``).
    importlib.import_module("codegenie.probes")
    registry_mod = importlib.import_module("codegenie.probes.registry")
    entries = registry_mod.default_registry.sorted_for_dispatch()
    return [e.cls() for e in entries]


def _seam_runs_last_names() -> frozenset[str]:
    """Step 6b — surface the set of probe names whose registry entry has
    ``runs_last=True``.

    The coordinator's partition reads this set to hoist a ``tier="base"`` +
    ``runs_last=True`` probe out of the prelude (S1-08 AC-13). The
    coordinator does NOT learn ``runs_last`` from the probe instance itself
    — that would re-introduce the ``Probe`` ABC contract change 02-ADR-0003
    explicitly rejected. The set is a frozen, hashable view of the
    registry-side annotations and is read once per gather.
    """
    importlib.import_module("codegenie.probes")
    registry_mod = importlib.import_module("codegenie.probes.registry")
    return frozenset(
        e.cls.name for e in registry_mod.default_registry.sorted_for_dispatch() if e.runs_last
    )


def _seam_coordinator_gather(
    snapshot: Any, task: Any, probes: list[Any], config: Any, cache: Any, sanitizer: Any
) -> Any:
    """Step 7 — dispatch ``coordinator.gather`` synchronously.

    Threads the ``runs_last_names`` frozenset from :func:`_seam_runs_last_names`
    onto the gather kwargs so the coordinator's partition can hoist
    ``runs_last=True`` probes out of the prelude regardless of declared
    ``tier`` (02-ADR-0003 + S1-08 AC-13).
    """
    import asyncio

    coord_mod = importlib.import_module("codegenie.coordinator.coordinator")
    runs_last_names = _seam_runs_last_names()
    return asyncio.run(
        coord_mod.gather(
            snapshot,
            task,
            probes,
            config,
            cache,
            sanitizer,
            runs_last_names=runs_last_names,
        )
    )


def _seam_shallow_merge(envelope: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    """Step 8 — shallow-merge each output's ``schema_slice`` into ``envelope["probes"][<name>]``.

    Each output's full ``schema_slice`` dict becomes the value under
    ``probes.<name>``. If two probes share a name (registry bug, hot-reload)
    a :class:`ProbeNameCollisionError` is raised (AC-24); the registry
    already enforces uniqueness at registration time (S2-05) so in practice
    this is defense in depth.

    A failure-isolated probe carries ``schema_slice = {}`` (see
    :func:`codegenie.coordinator.coordinator._build_failure_output`).
    Per ADR-0010 "Layer A slices optional at envelope", the empty slice
    is **omitted** from ``probes_block`` rather than written as an empty
    dict — emitting ``{}`` would violate the per-probe sub-schema's
    ``required: [...]`` contract and surface as a misleading
    ``exit_code=3 schema_invalid`` outcome that masks the real failure.
    The probe's failure remains visible via the audit run-record's
    ``exit_status = "error"`` row (Phase-1 failure-isolation contract;
    S5-05 AC-ERR-1).
    """
    probes_block = envelope["probes"]
    for name, output in outputs.items():
        if not output.schema_slice:
            continue
        if name in probes_block and probes_block[name] != {}:
            raise ProbeNameCollisionError(name)
        probes_block[name] = dict(output.schema_slice)
    return envelope


def _seam_redact_envelope(envelope: dict[str, Any]) -> RedactedSlice:
    """Step 8.5 — envelope-level secret redaction chokepoint (02-ADR-0010).

    Sits between :func:`_seam_shallow_merge` (Step 8) and
    :func:`_seam_validate_envelope` (Step 9). Drives the three-pass
    composition in :mod:`codegenie.output.envelope_redactor` and returns
    a :class:`~codegenie.output.redacted_slice.RedactedSlice` that the
    downstream validate + write seams consume.
    """
    redactor_mod = importlib.import_module("codegenie.output.envelope_redactor")
    result: RedactedSlice = redactor_mod._redact_envelope(envelope)
    return result


def _seam_validate_envelope(envelope: RedactedSlice) -> None:
    """Step 9 — JSON Schema validation. Raises :class:`SchemaValidationError`.

    Validates the inner :attr:`RedactedSlice.slice` payload (the only
    surface that gets persisted). Tightens in lock-step with the writer
    (02-ADR-0010 — type-uniformity at the seam layer).
    """
    validator_mod = importlib.import_module("codegenie.schema.validator")
    validator_mod.validate(envelope.slice)


def _seam_write_envelope(
    envelope: RedactedSlice,
    raw_artifacts: list[tuple[str, bytes]],
    output_dir: Path,
) -> bytes:
    """Step 10 — atomic envelope + raw-artifact write. Returns the YAML
    bytes so the audit writer can hash them (the writer itself does not
    expose its serialized payload).

    Defense in depth: the writer's own ``isinstance(envelope,
    RedactedSlice)`` guard also rejects a non-``RedactedSlice`` caller,
    but the seam guards first so the failure-mode message points at the
    seam (the public consumer surface) per 02-ADR-0010.
    """
    redacted_slice_mod = importlib.import_module("codegenie.output.redacted_slice")
    if not isinstance(envelope, redacted_slice_mod.RedactedSlice):
        raise TypeError(
            f"_seam_write_envelope requires RedactedSlice (02-ADR-0010); "
            f"got {type(envelope).__name__}"
        )
    writer_mod = importlib.import_module("codegenie.output.writer")
    yaml_mod = importlib.import_module("yaml")
    writer = writer_mod.Writer()
    writer.write(envelope, raw_artifacts, output_dir)
    yaml_path = output_dir / "repo-context.yaml"
    return (
        yaml_path.read_bytes()
        if yaml_path.exists()
        else yaml_mod.dump(envelope.slice).encode("utf-8")
    )


def _emit_phase2_summary(
    findings_count: int,
    fingerprints: list[str],
    skills_slice: dict[str, Any] | None,
) -> None:
    """Step 11.5 — print the Phase 2 three-line stdout summary block (S8-02).

    The block reports:

    - ``secrets_redacted_count`` — the value the caller already read off
      :attr:`RedactedSlice.findings_count`; the same value the writer
      emitted on ``envelope.written``.
    - ``fingerprints`` — ASCII-lex-sorted dedup of the
      :attr:`RedactedSlice.fingerprints` list (upstream dedup is
      insertion-order; this step gives the determinism property AC-9
      requires).
    - ``skill_shadowed`` — ``<skill_id>:<shadowed_tier>`` for each row in
      ``skills_slice["shadowed_skills"]``. ``skills_slice`` is ``None`` when
      ``SkillsIndexProbe`` did not run for this gather (the registry can
      filter it out by task type); we still print ``skill_shadowed=[]`` so
      the line stays grep-able.

    The function takes primitives (not :class:`RedactedSlice`) so test
    callers can exercise the data path without constructing a
    :class:`RedactedSlice` — the smart-constructor invariant in
    02-ADR-0010 keeps that construction restricted to the redaction
    pipeline. The caller in :func:`_run_gather_pipeline` reads the
    primitives off the in-scope :class:`RedactedSlice` directly.

    Per 02-ADR-0008: this function emits zero structlog events. The
    operator surface is stdout only; the structured-log surface for
    ``secrets_redacted_count`` is the existing ``envelope.written`` event.
    """
    cli_summary_mod = importlib.import_module("codegenie.cli_summary")
    skills_model_mod = importlib.import_module("codegenie.skills.model")
    raw_shadowed: list[Any] = []
    if skills_slice is not None:
        raw_shadowed = list(skills_slice.get("shadowed_skills", []))
    shadowed = [skills_model_mod.ShadowedSkill.model_validate(r) for r in raw_shadowed]
    block = cli_summary_mod.summary_block(
        count=findings_count,
        fingerprints=fingerprints,
        shadowed=shadowed,
    )
    # The repo's ruff T201 + forbidden-patterns hook reserve stdlib's
    # builtin emit-and-newline helper for tests and scripts; structured
    # logs go through structlog and operator-facing stdout flows through
    # ``sys.stdout.write``. Three writes, one newline each.
    for line in block.as_lines():
        sys.stdout.write(line + "\n")


def _seam_audit_record(
    output_dir: Path,
    gather_result: Any,
    *,
    cli_version: str,
    sherpa_commit: str | None,
    tool_versions: dict[str, str],
    yaml_sha256: str,
) -> Path:
    """Step 11 — write the per-run audit record. The ``RunRecord`` is built
    inside ``AuditWriter.record`` — the CLI passes the fingerprints only."""
    audit_mod = importlib.import_module("codegenie.audit")
    writer = audit_mod.AuditWriter(output_dir)
    path: Path = writer.record(
        gather_result,
        cli_version=cli_version,
        sherpa_commit=sherpa_commit,
        tool_versions=tool_versions,
        yaml_sha256=yaml_sha256,
    )
    return path


# --------------------------------------------------------------------------
# The pipeline itself
# --------------------------------------------------------------------------


def _run_gather_pipeline(
    path: Path,
    *,
    verbose: bool,
    refresh_tools: bool,
    no_gitignore: bool,
    auto_gitignore: bool,
) -> None:
    """Drive the 11-step gather pipeline against ``path``.

    Raises a :class:`CodegenieError` subclass on documented failure modes;
    other exceptions escape to the click handler.
    """
    import dataclasses

    # Step 1 — configure structlog up-front so all subsequent events flow.
    _seam_configure_logging(verbose)

    # Step 2 — tool-readiness cache.
    tool_versions = _seam_check_tools(refresh_tools)

    # Step 3 — .gitignore mutation (S4-03).
    _seam_maybe_append_gitignore(path, auto=auto_gitignore, skip=no_gitignore)

    # Step 4 — config loader.
    config = _seam_load_config(path, {})

    # Step 5 — git HEAD via allowlist wrapper.
    git_commit = _seam_git_rev_parse(path)

    # Build the RepoSnapshot + Task in line — they're tiny dataclass holders.
    probes_base = importlib.import_module("codegenie.probes.base")
    snapshot = probes_base.RepoSnapshot(
        root=path.resolve(),
        git_commit=git_commit,
        detected_languages={},
        config={
            "max_concurrent_probes": config.max_concurrent_probes,
            "cache_ttl_hours": config.cache_ttl_hours,
            "enable_audit": config.enable_audit,
        },
    )
    task = probes_base.Task(type="__bullet_tracer__", options={})

    # Step 6 — registry filter → probe instances.
    probes = _seam_registry_for_task()

    # Cache + sanitizer wiring.
    cache_mod = importlib.import_module("codegenie.cache.store")
    sanitizer_mod = importlib.import_module("codegenie.output.sanitizer")
    cache_dir = path / ".codegenie" / "cache"
    cache = cache_mod.CacheStore(cache_dir=cache_dir, ttl_hours=config.cache_ttl_hours)
    sanitizer = sanitizer_mod.OutputSanitizer()

    # Step 7 — coordinator dispatch.
    gather_result = _seam_coordinator_gather(snapshot, task, probes, config, cache, sanitizer)

    # ADR-0009 gate: empty outputs → AllProbesFailedError → exit 2 (AC-6).
    if len(gather_result.outputs) == 0:
        # Still write the audit record so Scenario 3 surfaces the failure
        # (AC-11). The empty envelope is NOT written.
        output_dir = path / ".codegenie" / "context"
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.chmod(output_dir, 0o700)
        except OSError:
            pass
        try:
            _seam_audit_record(
                output_dir,
                gather_result,
                cli_version=__version__,
                sherpa_commit=git_commit,
                tool_versions=tool_versions,
                yaml_sha256="",  # no YAML written
            )
        except Exception:  # noqa: BLE001 — audit failure on probes-failed path is best-effort
            pass
        raise AllProbesFailedError("every probe was Skipped or returned errors")

    # Step 8 — build envelope + shallow-merge probe outputs.
    from datetime import UTC, datetime

    envelope: dict[str, Any] = {
        "schema_version": "0.1.0",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": {
            # ``repo.root`` is the analyzed repo's basename only, not its
            # absolute filesystem path. ADR-0008 §Sanitizer requires the
            # rendered ``RepoContext`` carry no user-identifying path
            # prefixes (``/Users/<u>/...``, ``/home/<u>/...``, tmp dirs);
            # the envelope is the load-bearing emission surface for that
            # commitment. The schema (``repo_context.schema.json``) accepts
            # any string under ``repo.root``; downstream consumers that
            # need the absolute path read it from their own invocation
            # context, never from the rendered YAML.
            "root": snapshot.root.name,
            "git_commit": snapshot.git_commit,
        },
        "probes": {},
    }
    _seam_shallow_merge(envelope, gather_result.outputs)

    # Raw-artifact collection (Phase 0: LanguageDetectionProbe produces none).
    # S1-09 (Gap 2) — apply the soft per-probe raw-artifact truncation policy
    # at this writer-marshalling boundary. The Writer chokepoint (ADR-0011)
    # stays unchanged; the pure helper lives in
    # ``codegenie.output.raw_truncation``. Phase-0 probes have zero raw
    # artifacts so the policy is inert until Phase-1 lockfile parsers ship.
    budget_mod = importlib.import_module("codegenie.coordinator.budget")
    truncation_mod = importlib.import_module("codegenie.output.raw_truncation")
    default_resource_budget = budget_mod.DEFAULT_RESOURCE_BUDGET
    apply_truncation = truncation_mod.apply_raw_artifact_truncation
    truncated_marker = truncation_mod.Truncated
    budgets_by_probe: dict[str, Any] = {
        p.name: getattr(p, "declared_resource_budget", default_resource_budget) for p in probes
    }
    structlog_mod = importlib.import_module("structlog")
    raw_log = structlog_mod.get_logger("codegenie.cli")
    run_id = structlog_mod.contextvars.get_contextvars().get("run_id")

    import os as _os

    # 02-ADR-0012 — raw-artifact byte redaction at the writer-marshalling
    # boundary. The slice-side ``redact_secrets`` does not walk
    # ``ProbeOutput.raw_artifacts``; without this step a secret embedded in
    # an opaque binary blob (e.g. ``scip-index.scip``'s embedded source
    # text — F-03) rides verbatim through ``Writer.write`` onto disk. The
    # function is the single chokepoint so every probe's raw bytes inherit
    # the invariant — see 02-ADR-0012 §Decision.
    raw_redactor_mod = importlib.import_module("codegenie.output.sanitizer")
    redact_raw_artifact_bytes = raw_redactor_mod.redact_raw_artifact_bytes
    probe_id_mod = importlib.import_module("codegenie.types.identifiers")
    raw_artifact_findings: list[Any] = []

    raw_artifacts: list[tuple[str, bytes]] = []
    for probe_name, output in gather_result.outputs.items():
        budget = budgets_by_probe.get(probe_name, default_resource_budget)
        for raw_path in getattr(output, "raw_artifacts", []) or []:
            if isinstance(raw_path, Path) and not raw_path.is_file():
                # Capability-shakedown 2026-05-24 — fail loud (Rule 12) when a
                # cached probe output points at a raw_path that no longer
                # exists on disk. The common cause is a cache hit whose
                # probe-staged source file (under .codegenie/_probe_raw/ or
                # .codegenie/context/<name>.json) was deleted between runs.
                # Without this event the operator sees a silently incomplete
                # .codegenie/context/raw/ on warm runs.
                raw_log.warning(
                    "probe.raw_artifact.missing_on_cache_hit",
                    probe=probe_name,
                    path=str(raw_path),
                    run_id=run_id,
                )
                continue
            if isinstance(raw_path, Path) and raw_path.is_file():
                # Size-check via ``os.fstat`` before reading so a 200 MB
                # artifact never lands in RAM just to be truncated. The
                # ``os.fstat`` codepath is the documented test seam for
                # synthesizing oversized inputs without writing them to disk
                # (S3-06 AC-8 — pattern of record from S3-01/02/03/05's
                # parser-cap tests; B-2 unblocker).
                budget_bytes = budget.raw_artifact_truncate_mb * 1_048_576
                fd = _os.open(str(raw_path), _os.O_RDONLY)
                try:
                    original_bytes = _os.fstat(fd).st_size
                    # Read at most ``budget_bytes`` so we always have enough
                    # to build the truncation wrapper's ``data`` prefix
                    # without slurping the full original payload. Loop to
                    # accumulate against POSIX short-read semantics on
                    # regular files.
                    chunks: list[bytes] = []
                    remaining = budget_bytes
                    while remaining > 0:
                        chunk = _os.read(fd, remaining)
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    payload_bytes = b"".join(chunks)
                finally:
                    _os.close(fd)
                out_bytes, outcome = apply_truncation(
                    payload_bytes,
                    budget.raw_artifact_truncate_mb,
                    original_bytes=original_bytes,
                )
                if isinstance(outcome, truncated_marker):
                    raw_log.info(
                        "probe.raw_artifact.truncated",
                        probe=probe_name,
                        original_bytes=outcome.original_bytes,
                        budget_bytes=outcome.budget_bytes,
                        path=str(raw_path),
                        run_id=run_id,
                    )
                # 02-ADR-0012 — apply named-pattern byte redaction AFTER
                # truncation (so the bound is ``min(file_size, budget)``)
                # and BEFORE bytes flow into the writer. Findings accumulate
                # for the audit summary alongside slice-side findings.
                redacted_bytes, probe_raw_findings = redact_raw_artifact_bytes(
                    out_bytes, probe_id_mod.ProbeId(probe_name)
                )
                raw_artifact_findings.extend(probe_raw_findings)
                raw_artifacts.append((raw_path.name, redacted_bytes))

    output_dir = path / ".codegenie" / "context"

    # Step 8.5 — envelope-level secret-redaction chokepoint (02-ADR-0010).
    # The merged envelope flows through the three-pass composition in
    # ``codegenie.output.envelope_redactor`` and is wrapped in a
    # ``RedactedSlice``; from this line forward the validate + write
    # seams consume only the typed wrapper. Per-probe ``OutputSanitizer
    # .scrub`` (Phase 0, 02-ADR-0005) is upstream of this seam.
    redacted_envelope = _seam_redact_envelope(envelope)

    # Step 9 — schema validation. On failure write the .yaml.invalid sibling
    # and re-raise (CLI exit 3 per ADR-0013).
    try:
        _seam_validate_envelope(redacted_envelope)
    except SchemaValidationError:
        _write_invalid_sibling(redacted_envelope.slice, output_dir)
        raise

    # Step 10 — atomic envelope + raw write. Returns YAML bytes for the
    # audit anchor.
    yaml_bytes = _seam_write_envelope(redacted_envelope, raw_artifacts, output_dir)

    # Step 11 — audit record. Reads the just-written YAML for the SHA-256.
    hashing_mod = importlib.import_module("codegenie.hashing")
    yaml_sha = hashing_mod.identity_hash_bytes(yaml_bytes)
    _seam_audit_record(
        output_dir,
        gather_result,
        cli_version=__version__,
        sherpa_commit=git_commit,
        tool_versions=tool_versions,
        yaml_sha256=yaml_sha,
    )

    # Step 11.5 — Phase 2 stdout summary block (S8-02). Runs AFTER the
    # audit record write so the on-disk anchor is visible before the
    # operator sees the summary on stdout. 02-ADR-0008: no new events;
    # 02-ADR-0005: fingerprints only, no plaintext, 8-hex.
    skills_output = gather_result.outputs.get("skills_index")
    skills_slice = skills_output.schema_slice if skills_output is not None else None
    # 02-ADR-0012 — raw-artifact-origin findings are NOT merged into the
    # stdout summary or the ``envelope.written`` event. Both surfaces report
    # only envelope-redactor (slice-side) findings, which preserves the
    # ``stdout_count == event.secrets_redacted_count`` invariant
    # (``tests/integration/cli/test_summary_count_matches_event.py``) and
    # mirrors the ``gitleaks`` precedent (probe-side redaction is invisible
    # to the envelope count). The redaction itself still fires — see the
    # marshalling block above. Surfacing raw-origin findings on a dedicated
    # field/line is an ADR amendment per 02-ADR-0012 §Reversibility.
    if raw_artifact_findings:
        raw_log.info(
            "raw_artifacts.redacted",
            count=len(raw_artifact_findings),
            fingerprints=sorted({f.fingerprint for f in raw_artifact_findings}),
            run_id=run_id,
        )
    _emit_phase2_summary(
        redacted_envelope.findings_count,
        list(redacted_envelope.fingerprints),
        skills_slice,
    )
    del dataclasses  # silence unused-import on the success path


def _write_invalid_sibling(envelope: dict[str, Any], output_dir: Path) -> None:
    """Write ``repo-context.yaml.invalid`` sibling on schema failure.

    Mirrors :class:`codegenie.output.writer.Writer`'s atomic-replace pattern
    (without raw artifacts) so the rejected envelope is preserved for the
    user to inspect. The success-path ``.yaml`` is NEVER written when this
    sibling exists for the same run.
    """
    import os

    yaml_mod = importlib.import_module("yaml")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    target = output_dir / "repo-context.yaml.invalid"
    body = yaml_mod.dump(envelope, sort_keys=False).encode("utf-8")
    tmp = target.with_suffix(target.suffix + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, body)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(target))
    os.chmod(target, 0o600)


# --------------------------------------------------------------------------
# click group + subcommands
# --------------------------------------------------------------------------


@click.group(name="codegenie")
@click.version_option(__version__, prog_name="codegenie")
@click.option("--verbose", is_flag=True, default=False, help="Raise the log level to DEBUG.")
@click.option(
    "--refresh-tools",
    is_flag=True,
    default=False,
    help="Force re-detection of external tools instead of reading the cache.",
)
@click.option(
    "--no-gitignore",
    is_flag=True,
    default=False,
    help="Skip the .gitignore mutation prompt entirely.",
)
@click.option(
    "--auto-gitignore",
    is_flag=True,
    default=False,
    help="Append `.codegenie/` to .gitignore without prompting.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    verbose: bool,
    refresh_tools: bool,
    no_gitignore: bool,
    auto_gitignore: bool,
) -> None:
    """codewizard-sherpa local POC CLI."""
    # S4-03 AC-15 — the two flag override the prompt in opposite directions;
    # combining them is operator confusion, not a partial override. Reject at
    # the group callback so the subcommand body never sees the impossible
    # state and the user gets a clear click usage error (exit 2).
    if auto_gitignore and no_gitignore:
        raise click.UsageError("--auto-gitignore and --no-gitignore are mutually exclusive")
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["refresh_tools"] = refresh_tools
    ctx.obj["no_gitignore"] = no_gitignore
    ctx.obj["auto_gitignore"] = auto_gitignore


@cli.command(name="gather")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.pass_context
def gather(ctx: click.Context, path: Path) -> None:
    """Walk PATH and produce ``.codegenie/context/repo-context.yaml``.

    Documented exit codes:

    \b
    - exit 0 — at least one probe produced a valid output.
    - exit 2 — every probe was Skipped or errored (per ADR-0009).
    - exit 3 — envelope failed schema validation; ``.yaml.invalid`` written.
    - exit 5 — output destination is a symlink; refused per ADR-0008.
    - exit 6 — probe emitted a secret-shaped field name (per ADR-0010).
    """
    verbose = bool(ctx.obj.get("verbose", False))
    refresh_tools = bool(ctx.obj.get("refresh_tools", False))
    no_gitignore = bool(ctx.obj.get("no_gitignore", False))
    auto_gitignore = bool(ctx.obj.get("auto_gitignore", False))

    # Bind a CLI-level run_id BEFORE emitting cli.start so the same id rides
    # into the cli.end event. The coordinator's inner ``run_id`` rebind
    # (coordinator.py:429) lives inside its own asyncio Task context — it
    # affects probe.* events emitted from within the coordinator but does
    # NOT clobber the CLI's outer binding (AC-13).
    import secrets

    structlog = importlib.import_module("structlog")
    log = structlog.get_logger(__name__)
    run_id = secrets.token_hex(8)
    structlog.contextvars.bind_contextvars(run_id=run_id)

    outcome = "ok"
    exit_code = 0
    try:
        # Bind contextvars so child events inherit ``run_id``; ALSO pass it
        # explicitly so test-only processor chains (e.g.,
        # ``structlog.testing.capture_logs``) that skip ``merge_contextvars``
        # still see it on ``cli.start`` / ``cli.end``. The explicit kwarg
        # is the contract; the bind is the convenience.
        log.info("cli.start", run_id=run_id)
        try:
            _run_gather_pipeline(
                path,
                verbose=verbose,
                refresh_tools=refresh_tools,
                no_gitignore=no_gitignore,
                auto_gitignore=auto_gitignore,
            )
        except CodegenieError as exc:
            exit_code = _EXIT_CODE_DISPATCH.get(type(exc), 1)
            outcome = _OUTCOME_BY_EXIT.get(exit_code, "crash")
            if exit_code == 1:
                # An undocumented CodegenieError subclass leaked through —
                # surface it as an unhandled event so Phase 11 picks it up.
                log.info(
                    "cli.unhandled",
                    error_repr=repr(exc),
                    error_class=type(exc).__name__,
                )
                outcome = "crash"
    except ProbeNameCollisionError as exc:
        # Programming error (AC-24). Hits the click fallback path → exit 1.
        log.info("cli.unhandled", error_repr=repr(exc), error_class=type(exc).__name__)
        outcome = "crash"
        exit_code = 1
    except Exception as exc:  # noqa: BLE001 — fall-through catch for AC-15
        log.info("cli.unhandled", error_repr=repr(exc), error_class=type(exc).__name__)
        outcome = "crash"
        exit_code = 1
    finally:
        log.info("cli.end", outcome=outcome, exit_code=exit_code, run_id=run_id)
        structlog.contextvars.clear_contextvars()

    sys.exit(exit_code)


@cli.group(name="self-check")
def self_check() -> None:
    """Operator self-check subcommands (Phase-4 S3-03).

    Reports posture without escalating any privilege; never opens a socket
    and never invokes ``iptables`` / ``nftables`` as a subprocess.
    """


@self_check.command(name="egress")
def self_check_egress() -> None:
    """Report the active egress allowlist and OS-level posture.

    Always exits ``0`` (reporting command, not a gate). Reads
    :data:`codegenie.fallback.leaf.egress_guard._installed` directly; does
    NOT call :meth:`EgressGuard.install` (production tooling has no
    escape that mutates global state).
    """
    egress_mod = importlib.import_module("codegenie.fallback.leaf.egress_guard")
    shutil_mod = importlib.import_module("shutil")
    platform_mod = importlib.import_module("platform")

    click.echo("codegenie self-check egress")
    click.echo("  allowlist: api.anthropic.com:443")
    click.echo(f"  installed={egress_mod._installed!r}")
    system = platform_mod.system()
    if system == "Linux":
        iptables = shutil_mod.which("iptables") is not None
        nftables = shutil_mod.which("nft") is not None
        click.echo(f"  os_posture (linux): iptables_on_path={iptables} nftables_on_path={nftables}")
        click.echo("    (presence only — reporting rule status would require root)")
    elif system == "Darwin":
        click.echo("  os_posture (darwin): macOS dev — OS filter not configured by default")
    else:
        click.echo(f"  os_posture ({system.lower()}): not reported")


@cli.group(name="audit")
def audit() -> None:
    """Audit-record write/verify subcommands."""


@audit.command(name="verify")
@click.option(
    "--runs-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Directory containing audit run-records (``.codegenie/context/runs/``).",
)
@click.option(
    "--cache-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Cache directory containing ``index.jsonl`` + sharded blobs.",
)
@click.option(
    "--yaml-path",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to ``repo-context.yaml`` (whole-output anchor).",
)
def audit_verify(runs_dir: Path, cache_dir: Path, yaml_path: Path) -> None:
    """Recompute every audit anchor and report mismatches.

    Exit codes (``phase-arch-design.md §Component design / CLI``):

    \b
    - exit 0 — no mismatches; audit anchors verified.
    - exit 4 — one or more mismatches detected (tamper or drift).
    """
    audit_mod = importlib.import_module("codegenie.audit")
    mismatches = audit_mod.verify_runs(runs_dir, cache_dir, yaml_path)
    sys.exit(0 if mismatches == 0 else 4)


@cli.group(name="cache")
def cache() -> None:
    """Cache management subcommands."""


@cache.command(name="gc")
def cache_gc() -> None:
    """Phase-1+ cache GC stub.

    Logs ``cache.gc.stub`` exactly once and exits 0. The event name is part
    of the Phase-1+ migration contract — renames require an ADR amendment.
    """
    structlog = importlib.import_module("structlog")
    structlog.get_logger(__name__).info("cache.gc.stub")
    sys.exit(0)


@cache.command(name="prune")
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Bundle cache directory (defaults to ``<cwd>/.codegenie/cache``).",
)
def cache_prune(cache_dir: Path | None) -> None:
    """S3-05 — evict stale Bundle cache entries (Gap 4 fix).

    Calls :meth:`codegenie.plugins.cache_gc.BundleCacheGc.run` unconditionally
    and emits **exactly one** ``cache_gc_completed`` spanning event with
    ``trigger="operator_cli"`` through :class:`codegenie.plugins.events.EventLog`
    onto the BLAKE3-chained, zstd-compressed spanning stream at
    ``<cache_dir>/../events/spanning/append.jsonl.zst``. S6-01 absorbed the
    interim uncompressed ``append.jsonl`` wire format — that artifact is no
    longer produced. Exits 0 on success.
    """
    cache_gc_mod = importlib.import_module("codegenie.plugins.cache_gc")
    events_mod = importlib.import_module("codegenie.plugins.events")
    identifiers_mod = importlib.import_module("codegenie.types.identifiers")
    resolved_cache_dir = cache_dir if cache_dir is not None else Path.cwd() / ".codegenie" / "cache"
    resolved_cache_dir.mkdir(parents=True, exist_ok=True)

    sandbox_path_mod = importlib.import_module("codegenie.plugins.sandbox_path")
    sandboxed_cache_dir = sandbox_path_mod.SandboxedPath(absolute=resolved_cache_dir)
    gc = cache_gc_mod.BundleCacheGc(sandboxed_cache_dir)
    result = gc.run()
    event = cache_gc_mod.CacheGcCompletedEvent.from_result(result, trigger="operator_cli")

    event_log = events_mod.EventLog(
        root=resolved_cache_dir.parent,
        workflow_id=identifiers_mod.WorkflowId("operator_cli"),
    )
    event_log.emit_spanning(event)
    event_log.flush()
    sys.exit(0)


# ---------------------------------------------------------------------------
# cassette — Phase 4 S3-05 cassettes.lock manifest CLI surface (ADR-0014).
#
# Exit codes:
#   - 0 — rebuild succeeded (write mode) OR lock is consistent (--check mode).
#   - 8 — drift detected in --check mode (lock vs. on-disk cassettes).
#   - 9 — at least one cassette failed sanitizer verification; the CLI refuses
#         to lock a dirty cassette. The operator must redact + re-record first.
# ---------------------------------------------------------------------------


_DEFAULT_CASSETTES_DIR: Final[str] = "tests/cassettes/anthropic"


def _resolve_cassettes_dir(explicit: Path | None) -> Path:
    """Resolve the cassette directory (default: repo-relative anthropic/)."""
    if explicit is not None:
        return explicit
    return Path.cwd() / _DEFAULT_CASSETTES_DIR


def _resolve_lock_path(cassettes_dir: Path) -> Path:
    return cassettes_dir / "cassettes.lock"


def _collect_sanitizer_violations(cassettes_dir: Path) -> list[str]:
    """Return one diagnostic string per sanitizer violation across all cassettes.

    Pure (no I/O writes); reads cassette bytes via S3-04's
    :func:`verify_cassette`. Empty list = every cassette is clean.
    """
    sanitizer_mod = importlib.import_module("codegenie.fallback.cassette.sanitizer")
    findings: list[str] = []
    if not cassettes_dir.exists():
        return findings
    for cassette in sorted(cassettes_dir.rglob("*.yaml")):
        if not cassette.is_file():
            continue
        result = sanitizer_mod.verify_cassette(cassette)
        if result.passed:
            continue
        relpath = cassette.relative_to(cassettes_dir).as_posix()
        for v in result.violations:
            header = f" header={v.header_name!r}" if v.header_name else ""
            pattern = f" pattern={v.pattern!r}" if v.pattern else ""
            findings.append(
                f"sanitizer violation: {relpath} interaction={v.interaction_index} "
                f"kind={v.kind}{header}{pattern} snippet={v.snippet!r}"
            )
    return findings


@cli.group(name="cassette")
def cassette_group() -> None:
    """Cassette-discipline subcommands (Phase 4 S3-05 / ADR-0014)."""


@cassette_group.command(name="rebuild-lockfile")
@click.option(
    "--cassettes-dir",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Directory containing cassette ``*.yaml`` files (default: "
        "``tests/cassettes/anthropic`` relative to cwd)."
    ),
)
@click.option(
    "--check",
    "check_mode",
    is_flag=True,
    default=False,
    help=(
        "Compare-only mode: do not write. Exits 8 on drift, 9 on sanitizer "
        "violation, 0 if the on-disk lock matches the rebuilt lock byte-for-byte."
    ),
)
def cassette_rebuild_lockfile(cassettes_dir: Path | None, check_mode: bool) -> None:
    """Rebuild ``cassettes.lock`` from the cassette directory (ADR-0014).

    \b
    Exit codes:
    - 0 — rebuild succeeded (write) OR lock is byte-identical to disk (--check).
    - 8 — drift (--check only): rebuilt content differs from on-disk lock.
    - 9 — at least one cassette has a sanitizer violation; refuse to lock dirty.
    """
    manifest_mod = importlib.import_module("codegenie.fallback.cassette.manifest")
    resolved_dir = _resolve_cassettes_dir(cassettes_dir)
    lock_path = _resolve_lock_path(resolved_dir)

    # Refuse to ever lock-in a dirty cassette (AC-4).
    sanitizer_findings = _collect_sanitizer_violations(resolved_dir)
    if sanitizer_findings:
        for line in sanitizer_findings:
            click.echo(line, err=True)
        click.echo(
            "refusing to rebuild cassettes.lock while sanitizer violations exist; "
            "redact + re-record the affected cassettes first.",
            err=True,
        )
        sys.exit(9)

    rebuilt = manifest_mod.rebuild_lockfile(resolved_dir)

    if check_mode:
        on_disk = lock_path.read_text(encoding="utf-8") if lock_path.exists() else ""
        if rebuilt != on_disk:
            click.echo(
                "cassette body changed without lock update — run "
                "`python -m codegenie cassette rebuild-lockfile` and commit the "
                "result, then resubmit with cassette-steward CODEOWNERS approval",
                err=True,
            )
            sys.exit(8)
        sys.exit(0)

    # Write mode: idempotent on already-consistent state.
    if lock_path.exists() and lock_path.read_text(encoding="utf-8") == rebuilt:
        sys.exit(0)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(rebuilt, encoding="utf-8")
    sys.exit(0)


# ---------------------------------------------------------------------------
# vuln-index — Phase 3 S3-03 NVD/GHSA/OSV refresh CLI surface.
#
# Exit codes (threaded through ``_EXIT_CODE_DISPATCH``):
#   - 0 — refresh completed (including the empty-feed clean-run case).
#   - 4 — partial refresh (at least one parse error AND at least one success).
#   - 5 — every registered feed's ``fetch()`` failed.
#   - 7 — schema not migrated on an existing ``--index-path`` file.
# ---------------------------------------------------------------------------


_VULN_INDEX_PATH_ENV: Final[str] = "CODEGENIE_VULN_INDEX_PATH"


def _vuln_index_default_path() -> Path:
    """Default ``--index-path``: env override, else ``<cwd>/.codegenie/cache/...``."""
    env_value = os.environ.get(_VULN_INDEX_PATH_ENV)
    if env_value:
        return Path(env_value)
    return Path.cwd() / ".codegenie" / "cache" / "vuln-index.sqlite"


def _refresh_source_choices() -> list[str]:
    """Read CLI ``--source`` choices from the live feed registry (AC-X1)."""
    registry = importlib.import_module("codegenie.vuln_index.registry")
    return ["all", *registry.default_feed_registry.feed_sources()]


def _apply_migrations(db_path: Path) -> None:
    """Lazy-imported Alembic upgrade — cold-start fence (AC-N4)."""
    from alembic import command  # noqa: PLC0415 — cold-start budget
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).parent / "vuln_index" / "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def _has_alembic_version(db_path: Path) -> bool:
    """True iff ``db_path`` exists, opens, and has an ``alembic_version`` row."""
    import sqlite3  # noqa: PLC0415 — already loaded by ``VulnIndex``; minor

    try:
        conn = sqlite3.connect(str(db_path), isolation_level=None)
    except sqlite3.DatabaseError:
        return False
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone()
        if row is None:
            return False
        rev = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return rev is not None
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


@cli.group(name="vuln-index")
def vuln_index() -> None:
    """Vulnerability-index management subcommands (Phase 3 S3-03)."""


@vuln_index.command(name="refresh")
@click.option(
    "--source",
    "source",
    default="all",
    show_default=True,
    help="Feed source to refresh; one of the registered sources or ``all``.",
)
@click.option(
    "--index-path",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Path to the sqlite vuln-index file (default: $CODEGENIE_VULN_INDEX_PATH "
        "or <cwd>/.codegenie/cache/vuln-index.sqlite)."
    ),
)
def vuln_index_refresh(source: str, index_path: Path | None) -> None:
    """Fetch + parse + idempotent UPSERT for one (or all) CVE feed source(s).

    \b
    Exit codes (per ``_EXIT_CODE_DISPATCH``):
    - 0 — refresh succeeded (including the empty-delta case).
    - 4 — at least one parse error AND at least one success (partial).
    - 5 — every registered feed's ``fetch()`` raised.
    - 7 — schema is not migrated (existing path without ``alembic_version``).
    """
    try:
        _vuln_index_refresh_body(source=source, index_path=index_path)
    except CodegenieError as exc:
        exit_code = _EXIT_CODE_DISPATCH.get(type(exc), 1)
        sys.exit(exit_code)
    sys.exit(0)


def _vuln_index_refresh_body(*, source: str, index_path: Path | None) -> None:
    """Body of :func:`vuln_index_refresh`; raises typed exceptions instead of
    invoking :func:`sys.exit`. Click adapter catches + maps via
    :data:`_EXIT_CODE_DISPATCH`."""
    structlog_mod = importlib.import_module("structlog")
    registry_mod = importlib.import_module("codegenie.vuln_index.registry")
    ingest_mod = importlib.import_module("codegenie.vuln_index.ingest")
    index_mod = importlib.import_module("codegenie.vuln_index.index")
    result_mod = importlib.import_module("codegenie.result")

    log = structlog_mod.get_logger(__name__)
    resolved_path = index_path if index_path is not None else _vuln_index_default_path()
    registry = registry_mod.default_feed_registry

    valid_choices = _refresh_source_choices()
    if source not in valid_choices:
        raise click.BadParameter(
            f"--source must be one of {valid_choices}; got {source!r}",
            param_hint="--source",
        )

    # AC-X7 / AC-X9 — migration gate.
    if resolved_path.exists():
        if not _has_alembic_version(resolved_path):
            log.info("vuln_index.refresh.migration_missing", path=str(resolved_path))
            raise VulnIndexMigrationNotApplied(str(resolved_path))
    else:
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        _apply_migrations(resolved_path)

    sources_to_run = list(registry.feed_sources()) if source == "all" else [source]

    total_inserted = 0
    total_skipped = 0
    total_errors = 0
    fetch_attempts = 0
    fetch_failures = 0

    idx = index_mod.VulnIndex(resolved_path)
    try:
        digest_before = idx.digest()
        for src in sources_to_run:
            feed = registry.get_feed(src)
            fetch_attempts += 1
            successes: list[Any] = []
            errors: list[Any] = []
            try:
                chunks = list(feed.fetch())
            except VulnFeedFetchError:
                log.info("vuln_index.fetch_failed", source=src)
                fetch_failures += 1
                continue
            for chunk in chunks:
                result = feed.parse_one(chunk)
                if isinstance(result, result_mod.Ok):
                    successes.append(result.value)
                else:
                    errors.append(result.error)
            stats = ingest_mod.ingest_records(idx, [*successes, *errors])
            total_inserted += stats.inserted
            total_skipped += stats.skipped
            total_errors += len(stats.errors) + stats.errors_truncated
            ingest_mod._update_feed_digest(idx, src, successes)  # noqa: SLF001
        digest_after = idx.digest()
        digest_changed = digest_after != digest_before
    finally:
        idx.close()

    if sources_to_run and fetch_failures == fetch_attempts:
        log.info(
            "vuln_index.refresh.completed",
            source=sources_to_run,
            inserted=0,
            skipped=0,
            errors=0,
            exit_code=5,
            digest_changed=False,
        )
        raise VulnFeedFetchError("all feeds failed HTTP")

    exit_code = 4 if (total_errors > 0 and total_inserted > 0) else 0
    log.info(
        "vuln_index.refresh.completed",
        source=sources_to_run,
        inserted=total_inserted,
        skipped=total_skipped,
        errors=total_errors,
        exit_code=exit_code,
        digest_changed=digest_changed,
    )
    if exit_code == 4:
        raise VulnRefreshPartialError(
            f"partial refresh: inserted={total_inserted} errors={total_errors}"
        )


# ---------------------------------------------------------------------------
# embeddings — Phase 4 S4-01 FastembedEmbedder weight-bootstrap CLI surface.
#
# The subcommand's *body* lives in ``codegenie.rag.cli`` — the only module
# authorized to trigger a fastembed weights download (ADR-0007 §Decision).
# This module wires the Click registration and defer-imports the body so
# ``cli.py`` stays free of any ``fastembed`` symbol (preserves both the
# Phase-4 path-scoped fence at ``tests/fence/test_pyproject_fence_phase4.py``
# AND ``cli.py``'s own cold-start import-linter contract).
#
# Exit codes:
#   - 0 — first write / no-op same-digest / explicit model upgrade.
#   - 1 — same-model digest drift (corruption / tampering) — lock NOT
#         rewritten.
# ---------------------------------------------------------------------------


@cli.group(name="embeddings")
def embeddings_group() -> None:
    """Embeddings substrate management subcommands (Phase 4 S4-01)."""


@embeddings_group.command(name="bootstrap")
@click.option(
    "--model-name",
    "model_name",
    default="BAAI/bge-small-en-v1.5",
    show_default=True,
    help="fastembed model identifier (ADR-0007 default: BGE-small-en-v1.5).",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help=(
        "Model-weights cache root. Defaults to $FASTEMBED_CACHE_DIR or "
        "<cwd>/.codegenie/rag/fastembed-cache."
    ),
)
@click.option(
    "--lock-path",
    type=click.Path(path_type=Path),
    default=None,
    help=("Lock file path. Defaults to .codegenie/rag/embeddings_model.lock."),
)
def embeddings_bootstrap(model_name: str, cache_dir: Path | None, lock_path: Path | None) -> None:
    """Download pinned BGE-small weights and write the embeddings model lock.

    \b
    Exit codes:
    - 0 — lock written (first run), lock_current (idempotent re-run),
          or explicit model upgrade.
    - 1 — same-model digest drift (corruption / tampering). The lock is
          NOT rewritten.
    """
    rag_cli = importlib.import_module("codegenie.rag.cli")
    rag_cli._cli_entrypoint(
        model_name=model_name,
        cache_dir=str(cache_dir) if cache_dir else None,
        lock_path=str(lock_path) if lock_path else None,
    )


# ---------------------------------------------------------------------------
# rag — Phase-4 S4-07 operational-recovery CLI surface.
#
# Reconstructs the chromadb derived index from the canonical YAML records +
# manifest.yaml (ADR-0016). Routes through ``codegenie.rag.cli.rebuild`` so
# every fastembed / chromadb dependency stays under the path-scoped fence.
#
# Exit codes:
#   - 0 — rebuild completed; ``store.digest() == manifest.chain_head``.
#   - 1 — YAML parse error, chromadb write failure, or rmtree refused.
#   - 2 — manifest.yaml missing under --root; nothing to rebuild from.
# ---------------------------------------------------------------------------


@cli.group(name="rag")
def rag_group() -> None:
    """RAG substrate management subcommands (Phase 4 S4-07)."""


@rag_group.command(name="rebuild")
@click.option(
    "--root",
    "root",
    type=click.Path(path_type=Path),
    default=Path(".codegenie/rag/"),
    show_default=True,
    help="RAG root directory containing manifest.yaml and records/.",
)
@click.option(
    "--reembed",
    "reembed",
    is_flag=True,
    default=False,
    help=(
        "Re-embed each record's projected query text via the current "
        "FastembedEmbedder. Use after `embeddings bootstrap` model upgrade."
    ),
)
def rag_rebuild(root: Path, reembed: bool) -> None:
    """Reconstruct the chromadb derived index from canonical YAML records.

    \b
    Exit codes:
    - 0 — rebuild completed; ``store.digest() == manifest.chain_head``.
    - 1 — YAML parse error, chromadb write failure, or rmtree refused.
    - 2 — manifest.yaml missing under --root; nothing to rebuild from.
    """
    rag_cli = importlib.import_module("codegenie.rag.cli")
    rag_cli._rebuild_cli_entrypoint(root=str(root), reembed=reembed)
