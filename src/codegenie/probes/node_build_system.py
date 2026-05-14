"""``NodeBuildSystemProbe`` — Layer A, base-tier (S2-02).

The first new probe of Phase 1: it composes the shared primitives Step 1
landed (``safe_json`` / ``jsonc`` parsers, ``ParsedManifestMemo``, ``exec``
allowlist with ``node`` admitted, sub-schema convention) into a working probe
**without editing the frozen Phase 0 chokepoints**.

Reads, in this order:

1. **Lockfile precedence** — single linear scan over
   ``_LOCKFILE_PRECEDENCE`` (``bun > pnpm > yarn > npm``). First present
   filename wins for ``package_manager``; remaining filenames are reported in
   precedence order on ``additional_lockfiles``. Multi-lockfile → ``warnings``
   contains ``"package_manager.multi_lockfile"`` + ``confidence="low"``.
2. **``package.json``** — via ``ctx.parsed_manifest`` (the
   ``ParsedManifestMemo`` seam from S1-07) when present; falls back to
   ``parsers.safe_json.load`` otherwise. Typed parser exceptions
   (``SizeCapExceeded``, ``MalformedJSONError``, ``SymlinkRefusedError``)
   land in ``ProbeOutput.errors`` (NOT ``warnings`` — ADR-0007 line 50).
3. **``tsconfig.json``** — via ``parsers.jsonc.load`` with a depth-4
   ``extends`` walker; cycle and depth-cap diagnostics emit
   ``tsconfig.extends_cycle`` / ``tsconfig.extends_depth_exceeded``
   warnings.
4. **Node version** — four precedence sources:
   ``engines.node`` (constraint string) → ``.nvmrc`` → ``.node-version``
   → ``.tool-versions``. First non-``None`` hit lands in
   ``node_version_pinned``; ``engines.node`` is routed separately to
   ``node_version_constraint`` (AC-17 — routing is by field semantics, not
   by precedence-chain order).
5. **``node --version`` cross-check** — via ``_exec.run_allowlisted`` (the
   ADR-0001 env-strip seam). Optional: absent / timeout / non-zero exit
   are silent (`confidence="high"` preserved). Garbage stdout (hostile
   shim) emits ``node.version_unparseable`` but stays `"high"` — the
   cross-check is informational.
6. **Bundler detection** — alpha-sorted tuple
   ``_BUNDLERS_SORTED = (esbuild, parcel, rollup, turbopack, vite, webpack)``;
   first member present in ``dependencies ∪ devDependencies`` wins.
7. **``packageManager`` declaration** — if the ``pnpm@8.6.0`` prefix
   disagrees with the lockfile-derived ``package_manager``, emit
   ``package_manager.declaration_lockfile_disagree``. The lockfile wins
   (Open Question #3 resolution; Phase-1.5/Phase-2 ADR upgrade TODO).
8. **``scripts``** — verbatim (no eval, no quoting). Non-string values
   silently skipped (we are not a ``package.json`` linter).

**Open/Closed at the file boundary** — three precedence chains
(``_LOCKFILE_PRECEDENCE``, ``_BUNDLERS_SORTED``,
``_NODE_VERSION_PINNED_SOURCES``) are module-level tuples. Adding a new
lockfile / bundler / version-source is one tuple-entry insertion + a
schema-enum bump + a fixture test; **zero** edits to selection logic.

**Compile-time discipline (Rule 12).** All emittable warning + error IDs
are module-level frozensets; a regex assertion at import time refuses to
load the module if any ID drifts from the ADR-0007 pattern.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S2-02-node-build-system-probe.md``
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #2
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0001-add-node-to-allowed-binaries.md`` (env-strip seam),
  ``0002-parsed-manifest-memo-on-probe-context.md`` (memo seam),
  ``0004-per-probe-subschema-additional-properties-false.md`` (slice strict),
  ``0007-warnings-id-pattern.md`` (ID pattern),
  ``0008-in-process-parse-caps-not-per-probe-sandbox.md`` (parse caps),
  ``0010-probe-output-trust-boundary.md`` (slice optional at envelope).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

import structlog

from codegenie import exec as _exec
from codegenie.errors import (
    DepthCapExceeded,
    DisallowedSubprocessError,
    MalformedJSONError,
    ProbeTimeoutError,
    SizeCapExceeded,
    SymlinkRefusedError,
    ToolMissingError,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.parsers import jsonc, safe_json
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe

__all__ = ["NodeBuildSystemProbe"]


_log = structlog.get_logger(__name__)


# --- module-level Open/Closed seams -----------------------------------------


# Precedence-ordered ``(lockfile_filename, package_manager_name)``. First hit
# wins; remaining hits report on ``additional_lockfiles`` in this order.
# Adding a new package manager (e.g., Deno) is a single tuple-entry insertion
# (+ schema enum bump + fixture test). Zero edits to selection logic.
#
# NOTE: index ``[2]`` is the yarn seam — the static ``"yarn"`` literal here is
# OVERRIDDEN at probe runtime by ``_detect_yarn_variant`` (S2-02a / ADR-0013),
# which resolves to either ``"yarn-classic"`` or ``"yarn-berry"``. A reader
# grepping for ``"yarn"`` should not mistake this literal for the emitted value.
_LOCKFILE_PRECEDENCE: Final[tuple[tuple[str, str], ...]] = (
    ("bun.lockb", "bun"),
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("package-lock.json", "npm"),
)


# Bundler detection — alpha-sorted (interpretation of the arch's
# "deterministic-sorted" prescription). Phase-2 intentional-priority
# alternative documented in the story Notes-for-implementer.
_BUNDLERS_SORTED: Final[tuple[str, ...]] = (
    "esbuild",
    "parcel",
    "rollup",
    "turbopack",
    "vite",
    "webpack",
)


# Caps for ``.tool-versions`` / ``.nvmrc`` / ``.node-version`` (file size,
# not parse depth). 1 KiB is generous — typical content is ~10 bytes.
_NODE_VERSION_FILE_CAP_BYTES: Final[int] = 1024
_PARSE_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_PARSE_MAX_DEPTH: Final[int] = 64
_TSCONFIG_EXTENDS_MAX_DEPTH: Final[int] = 4
_NODE_VERSION_CHECK_TIMEOUT_S: Final[float] = 5.0
_NODE_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^v\d+\.\d+\.\d+")
_SEMVER_FOR_COMPARE_RE: Final[re.Pattern[str]] = re.compile(r"^v?\d+\.\d+\.\d+")
# Anchored + tight; captures only the major number. Pre-release suffixes
# (e.g. ``yarn@4.0.0-rc.42``) match cleanly. ``yarn@1`` (no dot) does NOT
# match — major-only declarations fall through to marker detection.
_YARN_PACKAGE_MANAGER_RE: Final[re.Pattern[str]] = re.compile(r"^yarn@(\d+)\.")


def _read_small_text_first_line(path: Path) -> str | None:
    """Read at most ``_NODE_VERSION_FILE_CAP_BYTES`` and return the first stripped non-empty line.

    Returns ``None`` on any I/O error or empty content. No symlink hardening
    here: ``.nvmrc``-style files are short, content is captured verbatim
    (no further processing), and the file is **not** parsed.
    """
    try:
        with path.open("rb") as fh:
            head = fh.read(_NODE_VERSION_FILE_CAP_BYTES)
    except OSError:
        return None
    try:
        text = head.decode("utf-8", errors="replace")
    except UnicodeDecodeError:  # pragma: no cover — errors="replace" prevents this
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def _read_nvmrc(root: Path) -> str | None:
    return _read_small_text_first_line(root / ".nvmrc")


def _read_node_version(root: Path) -> str | None:
    return _read_small_text_first_line(root / ".node-version")


def _read_tool_versions_node(root: Path) -> str | None:
    """Return the version following ``node `` in ``.tool-versions`` if present."""
    path = root / ".tool-versions"
    try:
        with path.open("rb") as fh:
            head = fh.read(_NODE_VERSION_FILE_CAP_BYTES)
    except OSError:
        return None
    text = head.decode("utf-8", errors="replace")
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split(None, 1)
        if len(parts) == 2 and parts[0] == "node":
            return parts[1].strip() or None
    return None


# Precedence-ordered ``(source_name, pure_extractor)``. ``engines.node`` is
# NOT here — it lives in ``node_version_constraint`` per AC-17. Adding Volta
# is a one-line tuple insertion.
_NODE_VERSION_PINNED_SOURCES: Final[tuple[tuple[str, Callable[[Path], str | None]], ...]] = (
    (".nvmrc", _read_nvmrc),
    (".node-version", _read_node_version),
    (".tool-versions", _read_tool_versions_node),
)


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "package_manager.multi_lockfile",
        "package_manager.declaration_lockfile_disagree",
        "tsconfig.extends_cycle",
        "tsconfig.extends_depth_exceeded",
        "node.version_unparseable",
        "node.version_declared_resolved_disagree",
        "node_build_system.yarn_variant_inferred",
        "node_build_system.package_manager_field_unparseable",
    }
)


_ERROR_IDS: Final[frozenset[str]] = frozenset(
    {
        "package_json.size_cap_exceeded",
        "package_json.malformed",
        "package_json.symlink_refused",
        "tsconfig.depth_cap_exceeded",
    }
)


# Map typed parser exception → (error_id, confidence). Mirrors S2-01's
# ``_PKG_JSON_FAILURE``; same demote-only rule applies via ``_demote``.
_PKG_JSON_FAILURE: Final[Mapping[type[Exception], tuple[str, str]]] = {
    SizeCapExceeded: ("package_json.size_cap_exceeded", "low"),
    MalformedJSONError: ("package_json.malformed", "low"),
    SymlinkRefusedError: ("package_json.symlink_refused", "low"),
}


_CONFIDENCE_RANK: Final[Mapping[str, int]] = {"low": 0, "medium": 1, "high": 2}


# --- compile-time discipline (Rule 12) --------------------------------------


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

for _id in (*_WARNING_IDS, *_ERROR_IDS):
    assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"

assert _LOCKFILE_PRECEDENCE[0][1] == "bun", (
    "S2-02 _LOCKFILE_PRECEDENCE: 'bun' must be the highest-precedence entry "
    f"(got {_LOCKFILE_PRECEDENCE[0]!r})"
)
assert list(_BUNDLERS_SORTED) == sorted(_BUNDLERS_SORTED), (
    f"S2-02 _BUNDLERS_SORTED must be alpha-sorted (got {_BUNDLERS_SORTED!r})"
)


# --- shapes ------------------------------------------------------------------


class TypeScriptInfo(TypedDict, total=False):
    compiler_options_path: str | None
    resolved_compiler_options: dict[str, Any]


# --- pure helpers ------------------------------------------------------------


def _demote(current: str, target: str) -> str:
    if _CONFIDENCE_RANK[target] < _CONFIDENCE_RANK[current]:
        return target
    return current


def _select_package_manager(
    present: list[str],
) -> tuple[str | None, list[str]]:
    """Single linear scan over ``_LOCKFILE_PRECEDENCE``.

    ``present`` is a precedence-ordered list of filenames; first entry wins,
    rest are runners-up in precedence order (not alpha).
    """
    if not present:
        return None, []
    by_filename = dict(_LOCKFILE_PRECEDENCE)
    picked = by_filename[present[0]]
    return picked, present[1:]


# Priority-ordered Berry filesystem markers. Each entry is
# ``(name, predicate)``. The first hit wins; deciding whether
# the marker is a file or a directory is the predicate's job.
# Open/Closed: a future Berry marker (e.g. a fork ships ``.yarn-modern.cjs``)
# is a one-line tuple-entry insertion + a fixture test; zero edits to the
# priority-chain control flow in ``_detect_yarn_variant``.
_BERRY_MARKERS: Final[tuple[tuple[str, Callable[[Path], bool]], ...]] = (
    (".yarnrc.yml", lambda p: p.is_file()),
    (".yarn", lambda p: p.is_dir()),
    (".pnp.cjs", lambda p: p.is_file()),
    (".pnp.loader.mjs", lambda p: p.is_file()),
)


# Priority-anchor discipline (Rule 12). A refactor that flattens the
# priority chain or reshuffles the head will fail at import time.
assert _BERRY_MARKERS[0][0] == ".yarnrc.yml", (
    "S2-02a _BERRY_MARKERS: '.yarnrc.yml' must be the highest-priority Berry marker "
    f"(got {_BERRY_MARKERS[0]!r}). ADR-0013 priority chain: yml > .yarn/ > .pnp.*."
)


def _detect_yarn_variant(
    repo_root: Path,
    parsed_manifest: Mapping[str, Any] | None,
) -> tuple[Literal["yarn-classic", "yarn-berry"], list[str]]:
    """Resolve ``yarn`` to ``yarn-classic`` or ``yarn-berry`` per ADR-0013.

    Priority order (first hit wins):

    1. ``package.json#packageManager`` matches ``^yarn@1\\.`` → ``yarn-classic``
    2. ``package.json#packageManager`` matches ``^yarn@(\\d+)\\.`` with major ≥ 2 → ``yarn-berry``
    3. ``.yarnrc.yml`` exists in repo root → ``yarn-berry``
       (Berry-only — Classic uses ``.yarnrc`` without the extension.)
    4. ``.yarn/`` directory exists → ``yarn-berry``
    5. ``.pnp.cjs`` or ``.pnp.loader.mjs`` exists → ``yarn-berry``
    6. Safe default → ``yarn-classic`` + ``node_build_system.yarn_variant_inferred``

    A ``packageManager`` value that starts with ``yarn`` but does not match
    the priority-1/2 regex emits ``node_build_system.package_manager_field_unparseable``
    and falls through to priorities 3-6.

    Returns ``(variant, warnings)``. The function is pure given inputs: no
    side effects, no I/O beyond filesystem existence checks on the listed
    markers.
    """
    warnings: list[str] = []

    pm_field = parsed_manifest.get("packageManager") if parsed_manifest is not None else None
    if isinstance(pm_field, str) and pm_field.startswith("yarn"):
        m = _YARN_PACKAGE_MANAGER_RE.match(pm_field)
        if m is not None:
            major = int(m.group(1))
            if major == 1:
                return "yarn-classic", warnings
            if major >= 2:
                return "yarn-berry", warnings
            # major == 0 is nonsense — fall through.
        else:
            warnings.append("node_build_system.package_manager_field_unparseable")

    for name, predicate in _BERRY_MARKERS:
        if predicate(repo_root / name):
            return "yarn-berry", warnings

    warnings.append("node_build_system.yarn_variant_inferred")
    return "yarn-classic", warnings


def _parse_node_version_output(stdout: str) -> str | None:
    m = _NODE_VERSION_RE.match(stdout.strip())
    if m is None:
        return None
    return m.group(0)


def _walk_extends(
    tsconfig_path: Path,
    repo_root: Path,
    *,
    max_depth: int = _TSCONFIG_EXTENDS_MAX_DEPTH,
) -> tuple[dict[str, Any], list[str]]:
    """Walk ``tsconfig.json#extends`` up to ``max_depth`` levels.

    Returns ``(deepest_compiler_options, warnings_emitted)``.

    - Cycle detection uses a ``set[Path]`` of **resolved-absolute** paths
      (``./a.json`` and ``a.json`` resolve identically).
    - Linear chain at depth > ``max_depth`` (no cycle) →
      ``tsconfig.extends_depth_exceeded``.
    - Cycle at any depth → ``tsconfig.extends_cycle``.
    - Path containment: every referenced file MUST be under ``repo_root``
      (``Path.resolve`` + ``is_relative_to``); otherwise the chain stops
      silently (the absent file branch).
    """
    warnings: list[str] = []
    visited: set[Path] = set()
    current_path: Path | None = tsconfig_path
    deepest: dict[str, Any] = {}
    repo_root_resolved = repo_root.resolve()

    for depth in range(max_depth + 1):
        if current_path is None:
            break
        resolved = current_path.resolve()
        if not resolved.is_relative_to(repo_root_resolved):
            break
        if resolved in visited:
            warnings.append("tsconfig.extends_cycle")
            break
        visited.add(resolved)
        _log.info(
            "probe.tsconfig.parse",
            probe=NodeBuildSystemProbe.name,
            path=str(resolved.relative_to(repo_root_resolved)),
            depth=depth,
            parser_kind="jsonc",
        )
        try:
            data = jsonc.load(
                current_path,
                max_bytes=_PARSE_MAX_BYTES,
                max_depth=_PARSE_MAX_DEPTH,
            )
        except (SizeCapExceeded, SymlinkRefusedError, MalformedJSONError):
            break
        if isinstance(data, dict):
            co = data.get("compilerOptions")
            if isinstance(co, dict):
                deepest = co
        next_extends = data.get("extends") if isinstance(data, dict) else None
        if not isinstance(next_extends, str) or not next_extends:
            current_path = None
            break
        next_path = (resolved.parent / next_extends).resolve()
        if depth + 1 > max_depth:
            warnings.append("tsconfig.extends_depth_exceeded")
            break
        current_path = next_path
    return deepest, warnings


def _framework_or_bundler_from(deps: set[str], candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        if name in deps:
            return name
    return None


def _deps_union(pkg: Mapping[str, Any]) -> set[str]:
    deps_obj = pkg.get("dependencies") or {}
    devdeps_obj = pkg.get("devDependencies") or {}
    deps: set[str] = set()
    if isinstance(deps_obj, dict):
        deps |= set(deps_obj.keys())
    if isinstance(devdeps_obj, dict):
        deps |= set(devdeps_obj.keys())
    return deps


def _strip_v_prefix(s: str) -> str:
    return s[1:] if s.startswith("v") else s


def _semver_parseable(s: str) -> bool:
    return _SEMVER_FOR_COMPARE_RE.match(s) is not None


def _minimal_slice(
    package_manager: str | None,
    additional_lockfiles: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """The minimal ``build_system`` slice emitted when a parser error short-circuits parse work."""
    return {
        "package_manager": package_manager,
        "package_manager_version": None,
        "additional_lockfiles": additional_lockfiles,
        "commands": {},
        "bundler": None,
        "typescript": None,
        "node_version_pinned": None,
        "node_version_constraint": None,
        "node_version_resolved_locally": None,
        "output_artifacts": [],
        "warnings": warnings,
    }


async def _resolve_node_version_via_exec(
    snapshot_root: Path,
) -> tuple[str | None, bool]:
    """Run ``node --version`` via the env-strip seam.

    Returns ``(parsed_version_or_None, hostile_shim_detected)``.

    - Tool absent / timeout / non-zero exit → ``(None, False)`` (silent).
    - Unparseable stdout (hostile shim, ANSI noise, etc.) → ``(None, True)``.
    """
    try:
        result = await _exec.run_allowlisted(
            ["node", "--version"],
            cwd=snapshot_root,
            timeout_s=_NODE_VERSION_CHECK_TIMEOUT_S,
        )
    except (FileNotFoundError, ToolMissingError, ProbeTimeoutError, DisallowedSubprocessError):
        return None, False
    except OSError:
        return None, False
    if getattr(result, "returncode", 0) != 0:
        return None, False
    stdout = result.stdout.decode("utf-8", errors="replace")
    parsed = _parse_node_version_output(stdout)
    if parsed is None:
        return None, True
    return parsed, False


@register_probe
class NodeBuildSystemProbe(Probe):
    """Layer A — Node build-system facts (lockfile, scripts, tsconfig, version).

    See module docstring for the full read pipeline.
    """

    name: str = "node_build_system"
    version: str = "0.1.0"
    layer = "A"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["javascript", "typescript"]
    requires: list[str] = ["language_detection"]
    timeout_seconds: int = 30
    declared_inputs: list[str] = [
        "package.json",
        "pnpm-workspace.yaml",
        "lerna.json",
        "nx.json",
        "turbo.json",
        ".nvmrc",
        ".node-version",
        ".tool-versions",
        "tsconfig.json",
        "tsconfig.*.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        warnings: list[str] = []
        errors: list[str] = []
        confidence: str = "high"

        # --- (1) Lockfile precedence ------------------------------------
        present: list[str] = [
            name for name, _ in _LOCKFILE_PRECEDENCE if (repo.root / name).is_file()
        ]
        package_manager, additional_lockfiles = _select_package_manager(present)
        if len(present) > 1:
            warnings.append("package_manager.multi_lockfile")
            confidence = _demote(confidence, "low")

        # --- (2) package.json --------------------------------------------
        pkg_path = repo.root / "package.json"
        pkg: Mapping[str, Any] | None = None
        if pkg_path.exists() or pkg_path.is_symlink():
            try:
                if ctx.parsed_manifest is not None:
                    pkg = ctx.parsed_manifest(pkg_path)
                else:
                    pkg = safe_json.load(
                        pkg_path,
                        max_bytes=_PARSE_MAX_BYTES,
                        max_depth=_PARSE_MAX_DEPTH,
                    )
            except (SizeCapExceeded, MalformedJSONError, SymlinkRefusedError) as exc:
                error_id, demoted = _PKG_JSON_FAILURE[type(exc)]
                errors.append(error_id)
                confidence = _demote(confidence, demoted)
                duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
                _log.info(
                    EVENT_PROBE_FAILURE,
                    probe=self.name,
                    error=type(exc).__name__,
                    error_id=error_id,
                )
                return ProbeOutput(
                    schema_slice={
                        "build_system": _minimal_slice(
                            package_manager, additional_lockfiles, warnings
                        )
                    },
                    raw_artifacts=[],
                    confidence=confidence,  # type: ignore[arg-type]
                    duration_ms=duration_ms,
                    warnings=[],
                    errors=errors,
                )

        pkg = pkg or {}
        assert isinstance(pkg, Mapping)

        # --- scripts ----------------------------------------------------
        scripts_obj = pkg.get("scripts")
        if isinstance(scripts_obj, dict):
            commands: dict[str, str] = {
                k: v for k, v in scripts_obj.items() if isinstance(k, str) and isinstance(v, str)
            }
        else:
            commands = {}

        # --- output_artifacts (AC-15) -----------------------------------
        files_obj = pkg.get("files")
        if isinstance(files_obj, list) and all(isinstance(f, str) for f in files_obj):
            output_artifacts: list[str] = list(files_obj)
        else:
            output_artifacts = []

        # --- yarn variant detection (S2-02a / ADR-0013) -----------------
        # Runs only when the lockfile-precedence resolution picked plain
        # "yarn". Other managers (bun/pnpm/npm) skip this entirely.
        if package_manager == "yarn":
            variant, variant_warnings = _detect_yarn_variant(repo.root, pkg)
            package_manager = variant
            warnings.extend(variant_warnings)

        # --- packageManager (AC-8) --------------------------------------
        # Compare *families* (yarn/pnpm/npm/bun), not variants, so
        # ``packageManager: yarn@1.22.19`` against a ``yarn.lock`` does not
        # spuriously disagree with the variant ``yarn-classic``.
        pm_field = pkg.get("packageManager")
        if isinstance(pm_field, str) and "@" in pm_field and package_manager is not None:
            declared_prefix = pm_field.split("@", 1)[0]
            resolved_family = package_manager.split("-", 1)[0]
            if declared_prefix != resolved_family:
                warnings.append("package_manager.declaration_lockfile_disagree")

        # --- (3) tsconfig.json ------------------------------------------
        tsconfig_path = repo.root / "tsconfig.json"
        typescript: TypeScriptInfo | None
        if tsconfig_path.is_file():
            try:
                deepest, ts_warnings = _walk_extends(tsconfig_path, repo.root)
                warnings.extend(ts_warnings)
                typescript = {
                    "compiler_options_path": "tsconfig.json",
                    "resolved_compiler_options": deepest,
                }
            except DepthCapExceeded:
                errors.append("tsconfig.depth_cap_exceeded")
                confidence = _demote(confidence, "low")
                typescript = None
        else:
            typescript = None

        # --- (4) Node version sources -----------------------------------
        engines = pkg.get("engines")
        engines_node = engines.get("node") if isinstance(engines, dict) else None
        node_version_constraint: str | None = (
            engines_node if isinstance(engines_node, str) else None
        )

        node_version_pinned: str | None = None
        for _name, extractor in _NODE_VERSION_PINNED_SOURCES:
            hit = extractor(repo.root)
            if hit is not None:
                node_version_pinned = hit
                break

        # --- (5) node --version cross-check -----------------------------
        node_version_resolved_locally, hostile_shim = await _resolve_node_version_via_exec(
            repo.root
        )
        if hostile_shim:
            warnings.append("node.version_unparseable")

        # --- (6) version disagree (AC-7) -------------------------------
        if (
            node_version_pinned is not None
            and node_version_resolved_locally is not None
            and _semver_parseable(node_version_pinned)
            and _semver_parseable(node_version_resolved_locally)
        ):
            if _strip_v_prefix(node_version_pinned) != _strip_v_prefix(
                node_version_resolved_locally
            ):
                warnings.append("node.version_declared_resolved_disagree")

        # --- (7) bundler -----------------------------------------------
        deps = _deps_union(pkg)
        bundler = _framework_or_bundler_from(deps, _BUNDLERS_SORTED)

        slice_payload: dict[str, Any] = {
            "package_manager": package_manager,
            "package_manager_version": None,
            "additional_lockfiles": additional_lockfiles,
            "commands": commands,
            "bundler": bundler,
            "typescript": dict(typescript) if typescript is not None else None,
            "node_version_pinned": node_version_pinned,
            "node_version_constraint": node_version_constraint,
            "node_version_resolved_locally": node_version_resolved_locally,
            "output_artifacts": output_artifacts,
            "warnings": warnings,
        }

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        if confidence == "high":
            _log.info(
                EVENT_PROBE_SUCCESS,
                probe=self.name,
                confidence=confidence,
                package_manager=package_manager,
                bundler=bundler,
            )

        return ProbeOutput(
            schema_slice={"build_system": slice_payload},
            raw_artifacts=[],
            confidence=confidence,  # type: ignore[arg-type]
            duration_ms=duration_ms,
            warnings=[],
            errors=errors,
        )
