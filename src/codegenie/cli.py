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
import sys
from pathlib import Path
from typing import Any

import click

from codegenie.errors import (
    AllProbesFailedError,
    CodegenieError,
    SchemaValidationError,
    SecretLikelyFieldNameError,
    SymlinkRefusedError,
)
from codegenie.version import __version__

__all__ = ["cli"]


# --------------------------------------------------------------------------
# Exit-code dispatch table — module-scope single source of truth (AC-9).
# Adding a code requires a story amendment + ``test_dispatch_table_snapshot``
# update. The order in --help text inherits from this dict at format time.
# --------------------------------------------------------------------------

_EXIT_CODE_DISPATCH: dict[type[CodegenieError], int] = {
    AllProbesFailedError: 2,
    SchemaValidationError: 3,
    SymlinkRefusedError: 5,
    SecretLikelyFieldNameError: 6,
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
    """Step 6 — resolve the probes the bullet tracer dispatches."""
    # Importing the probe module triggers its ``@register_probe`` decorator.
    importlib.import_module("codegenie.probes.language_detection")
    registry_mod = importlib.import_module("codegenie.probes.registry")
    probe_classes = registry_mod.default_registry.for_task(
        "__bullet_tracer__", frozenset({"unknown"})
    )
    return [cls() for cls in probe_classes]


def _seam_coordinator_gather(
    snapshot: Any, task: Any, probes: list[Any], config: Any, cache: Any, sanitizer: Any
) -> Any:
    """Step 7 — dispatch ``coordinator.gather`` synchronously."""
    import asyncio

    coord_mod = importlib.import_module("codegenie.coordinator.coordinator")
    return asyncio.run(coord_mod.gather(snapshot, task, probes, config, cache, sanitizer))


def _seam_shallow_merge(envelope: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    """Step 8 — shallow-merge each output's ``schema_slice`` into ``envelope["probes"][<name>]``.

    Each output's full ``schema_slice`` dict becomes the value under
    ``probes.<name>``. If two probes share a name (registry bug, hot-reload)
    a :class:`ProbeNameCollisionError` is raised (AC-24); the registry
    already enforces uniqueness at registration time (S2-05) so in practice
    this is defense in depth.
    """
    probes_block = envelope["probes"]
    for name, output in outputs.items():
        if name in probes_block and probes_block[name] != {}:
            raise ProbeNameCollisionError(name)
        probes_block[name] = dict(output.schema_slice)
    return envelope


def _seam_validate_envelope(envelope: dict[str, Any]) -> None:
    """Step 9 — JSON Schema validation. Raises :class:`SchemaValidationError`."""
    validator_mod = importlib.import_module("codegenie.schema.validator")
    validator_mod.validate(envelope)


def _seam_write_envelope(
    envelope: dict[str, Any],
    raw_artifacts: list[tuple[str, bytes]],
    output_dir: Path,
) -> bytes:
    """Step 10 — atomic envelope + raw-artifact write. Returns the YAML
    bytes so the audit writer can hash them (the writer itself does not
    expose its serialized payload)."""
    writer_mod = importlib.import_module("codegenie.output.writer")
    yaml_mod = importlib.import_module("yaml")
    writer = writer_mod.Writer()
    writer.write(envelope, raw_artifacts, output_dir)
    yaml_path = output_dir / "repo-context.yaml"
    return yaml_path.read_bytes() if yaml_path.exists() else yaml_mod.dump(envelope).encode("utf-8")


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
            "root": str(snapshot.root),
            "git_commit": snapshot.git_commit,
        },
        "probes": {},
    }
    _seam_shallow_merge(envelope, gather_result.outputs)

    # Raw-artifact collection (Phase 0: LanguageDetectionProbe produces none).
    raw_artifacts: list[tuple[str, bytes]] = []
    for output in gather_result.outputs.values():
        for raw_path in getattr(output, "raw_artifacts", []) or []:
            if isinstance(raw_path, Path) and raw_path.is_file():
                raw_artifacts.append((raw_path.name, raw_path.read_bytes()))

    output_dir = path / ".codegenie" / "context"

    # Step 9 — schema validation. On failure write the .yaml.invalid sibling
    # and re-raise (CLI exit 3 per ADR-0013).
    try:
        _seam_validate_envelope(envelope)
    except SchemaValidationError:
        _write_invalid_sibling(envelope, output_dir)
        raise

    # Step 10 — atomic envelope + raw write. Returns YAML bytes for the
    # audit anchor.
    yaml_bytes = _seam_write_envelope(envelope, raw_artifacts, output_dir)

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
