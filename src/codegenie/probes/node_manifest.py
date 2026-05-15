"""``NodeManifestProbe`` — Layer A, base-tier (S3-05).

Parses ``package.json`` plus the single canonical lockfile (precedence
``pnpm > yarn > npm``; ``bun.lockb`` counts for multi-detect but is never
parsed — ADR-0011), cross-references resolved dependencies against
``catalogs/native_modules.yaml`` (ADR-0006), and produces a ``manifests``
slice with a ``native_modules`` block. The seam this probe creates —
"data-as-code catalog cross-reference, no LLM, no ``npm ls``" — is what
makes Phase 7's distroless migration deterministic six phases later.

This module is the **third concrete consumer** of the lockfile-parser
family (after S3-01 / S3-02 / S3-03). The rule-of-three threshold those
stories deferred is resolved here: ``_FLATTENERS``,
``_PARSER_KIND_BY_FILENAME``, ``_PARSERS``, ``_ERROR_PREFIX_BY_KIND``
are module-scope registries; adding a future ``_bun.py`` is one new
``ParserKind`` Literal arm + one entry per registry — zero edits to
``run()``. ``_lockfiles/__init__.py`` stays inert (S3-02 / S3-03
invariant).

Pure module-level helpers:

- ``_flatten_pnpm`` / ``_flatten_npm`` / ``_flatten_yarn`` — TypedDict →
  ``Mapping[str, str]`` (package_name → version). Names are normalized:
  ``/bcrypt@5.1.1(peer@^1)`` → ``bcrypt``; ``node_modules/@types/bcrypt``
  → ``@types/bcrypt``; ``bcrypt@^5.1.0, bcrypt@^5.0`` → ``bcrypt``.
- ``_cross_reference_native_modules`` — exact-name dict lookup (per
  AC-15: ``@types/bcrypt``, ``bcryptjs``, ``bcrypt-utils`` are not
  hits for ``bcrypt``).
- ``_error_id`` — ``(ParserKind, exception) → "<prefix>.<suffix>"`` per
  ADR-0007's warning-ID pattern; constructed at the catch site from
  the marker's positional message (S3-02 / S3-03 discipline).

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S3-05-node-manifest-probe.md``
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #4
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0004-per-probe-subschema-additional-properties-false.md`` (slice strict),
  ``0006-native-module-catalog-versioning.md`` (cache invalidation via
  ``declared_inputs``),
  ``0007-warnings-id-pattern.md`` (WarningId pattern at catch site),
  ``0011-no-helm-render-no-hcl-no-npm-ls.md`` (no ``npm ls`` /
  ``bun.lockb`` parse).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

import structlog

from codegenie.catalogs import NATIVE_MODULES, NATIVE_MODULES_CATALOG_VERSION, NativeModuleEntry
from codegenie.coordinator.budget import ResourceBudget
from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    MalformedLockfileError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.parsers import safe_json
from codegenie.probes._lockfiles import _npm, _pnpm, _yarn
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe

__all__ = ["NodeManifestProbe"]


_log = structlog.get_logger(__name__)


_PARSE_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_PARSE_MAX_DEPTH: Final[int] = 64


# --- module-level Open/Closed seams (rule-of-three resolution) -------------


ParserKind = Literal["pnpm", "yarn", "npm"]

# Filename → parser-kind. The keys are also the precedence chain when
# combined with ``_PARSEABLE_LOCKFILES``: first present wins.
_PARSER_KIND_BY_FILENAME: Final[Mapping[str, ParserKind]] = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    "package-lock.json": "npm",
}

# Precedence-ordered parseable lockfiles. Matches
# ``node_build_system._LOCKFILE_PRECEDENCE`` minus ``bun.lockb`` (which is
# enumerated for multi-detect only — ADR-0011 forbids parsing it).
_PARSEABLE_LOCKFILES: Final[tuple[str, ...]] = (
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
)

_ALL_LOCKFILES: Final[tuple[str, ...]] = _PARSEABLE_LOCKFILES + ("bun.lockb",)

_PNPM_V6_SLASH_RE: Final[re.Pattern[str]] = re.compile(r"^([^/]+)/([^/]+)$")


# --- shapes ------------------------------------------------------------------


class NativeModuleHit(TypedDict):
    """One native-module catalog cross-reference hit.

    Plain ``TypedDict`` (not ``NamedTuple``) so the schema's
    ``additionalProperties: false`` matching at the JSON layer round-trips
    cleanly; the slice is serialized as JSON for the raw-artifact dump and
    revalidated at envelope merge.
    """

    name: str
    version: str
    requires_node_gyp: bool
    system_deps_required: list[str]
    binary_artifacts_glob: list[str]
    catalog_entry_version: int


# --- pure helpers (functional core) ----------------------------------------


def _flatten_pnpm(parsed: _pnpm.PnpmLock | Mapping[str, Any]) -> Mapping[str, str]:
    """Normalize pnpm v6/v9 ``packages`` keys to ``{name: version}``.

    - v9: ``/bcrypt@5.1.1`` and ``/bcrypt@5.1.1(peer@^1)`` (peer-dep parenthetical).
    - v9 scoped: ``/@types/bcrypt@1.0.0`` (the leading ``@`` is the scope sigil).
    - v6: ``/bcrypt/5.1.1`` (slash separator, no ``@``).
    """
    out: dict[str, str] = {}
    raw_packages = parsed.get("packages") if isinstance(parsed, Mapping) else None
    if not isinstance(raw_packages, Mapping):
        return out
    for raw_key in raw_packages:
        if not isinstance(raw_key, str):
            continue
        key = raw_key.lstrip("/")
        # Strip the v9 peer-dep parenthetical suffix.
        paren = key.find("(")
        if paren != -1:
            key = key[:paren]
        # v6 ``name/version`` form: exactly one slash, no ``@`` on the right.
        m = _PNPM_V6_SLASH_RE.match(key)
        if m is not None and "@" not in m.group(2):
            name, version = m.group(1), m.group(2)
        else:
            # find the last ``@`` that is NOT the scoped-package leading char.
            at_idx = key.rfind("@")
            if at_idx <= 0:
                continue
            name, version = key[:at_idx], key[at_idx + 1 :]
        if name and version:
            out[name] = version
    return out


def _flatten_npm(parsed: _npm.NpmLock | Mapping[str, Any]) -> Mapping[str, str]:
    """Normalize package-lock.json v1/v3 keys to ``{name: version}``.

    - v3: flat ``packages`` keyed by ``node_modules/<name>`` (or
      ``node_modules/<scope>/<name>`` for scoped). The empty-string root
      key is skipped.
    - v1: nested ``dependencies`` tree (recursive walk).
    """
    out: dict[str, str] = {}
    flat = parsed.get("packages") if isinstance(parsed, Mapping) else None
    if isinstance(flat, Mapping):
        for raw_key, entry in flat.items():
            if not isinstance(raw_key, str) or not raw_key:
                continue
            if not isinstance(entry, Mapping):
                continue
            name = raw_key
            if name.startswith("node_modules/"):
                name = name[len("node_modules/") :]
            # Nested dep-of-dep installation: last segment is the name.
            if "node_modules/" in name:
                name = name.rsplit("node_modules/", 1)[-1]
            ver = entry.get("version")
            if name and isinstance(ver, str):
                out[name] = ver
    # v1 fallback — walk nested ``dependencies`` tree.
    if not out and isinstance(parsed, Mapping):
        nested = parsed.get("dependencies")
        if isinstance(nested, Mapping):
            _walk_npm_v1(nested, out)
    return out


def _walk_npm_v1(tree: Mapping[str, Any], out: dict[str, str]) -> None:
    """Depth-first walk over npm v1's nested ``dependencies`` tree."""
    for name, entry in tree.items():
        if not isinstance(name, str) or not isinstance(entry, Mapping):
            continue
        ver = entry.get("version")
        if isinstance(ver, str):
            out[name] = ver
        sub = entry.get("dependencies")
        if isinstance(sub, Mapping):
            _walk_npm_v1(sub, out)


def _flatten_yarn(parsed: _yarn.YarnLock | Mapping[str, Any]) -> Mapping[str, str]:
    """Normalize yarn-classic ``entries`` keys to ``{name: version}``.

    Yarn-classic entry headers may be comma-joined for shared resolutions
    (``bcrypt@^5.1.0, bcrypt@^5.0``); each locator is split on ``, ``
    and the trailing range-spec is stripped from the **last** ``@`` —
    preserving scoped-package leading ``@``.
    """
    out: dict[str, str] = {}
    entries = parsed.get("entries") if isinstance(parsed, Mapping) else None
    if not isinstance(entries, Mapping):
        return out
    for raw_key, entry in entries.items():
        if not isinstance(raw_key, str) or not isinstance(entry, Mapping):
            continue
        ver = entry.get("version")
        if not isinstance(ver, str):
            continue
        for locator in raw_key.split(", "):
            at_idx = locator.rfind("@")
            if at_idx <= 0:
                continue
            name = locator[:at_idx]
            if name:
                out[name] = ver
    return out


# Dispatch registries (rule-of-three resolution — adding ``_bun.py`` is one
# new ``ParserKind`` Literal arm + one entry per registry; zero edits to
# ``run()``).
_FLATTENERS: Final[Mapping[ParserKind, Callable[[Any], Mapping[str, str]]]] = {
    "pnpm": _flatten_pnpm,
    "yarn": _flatten_yarn,
    "npm": _flatten_npm,
}
_PARSERS: Final[Mapping[ParserKind, Callable[[Path], Any]]] = {
    "pnpm": _pnpm.parse,
    "yarn": _yarn.parse,
    "npm": _npm.parse,
}
_ERROR_PREFIX_BY_KIND: Final[Mapping[ParserKind, str]] = {
    "pnpm": "pnpm_lock",
    "yarn": "yarn_lock",
    "npm": "npm_lock",
}
_ERROR_SUFFIX_BY_EXC: Final[Mapping[type[BaseException], str]] = {
    SizeCapExceeded: "size_cap_exceeded",
    DepthCapExceeded: "depth_cap_exceeded",
    MalformedLockfileError: "malformed",
    SymlinkRefusedError: "symlink_refused",
}

# Catchable parser exceptions for the ``run()`` try/except (mirrors
# ``_ERROR_SUFFIX_BY_EXC.keys()``; tuple form is what ``except`` needs).
_PARSER_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = tuple(_ERROR_SUFFIX_BY_EXC)

# package.json read-time failures — separate prefix so the IDs are
# distinguishable from lockfile errors in downstream logs.
_PKG_JSON_FAILURE: Final[Mapping[type[BaseException], str]] = {
    SizeCapExceeded: "package_json.size_cap_exceeded",
    MalformedJSONError: "package_json.malformed",
    SymlinkRefusedError: "package_json.symlink_refused",
    DepthCapExceeded: "package_json.depth_cap_exceeded",
}


# Compile-time ADR-0007 discipline — refuse to load the module if any
# emittable ID drifts from the pattern.
_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
for _prefix in _ERROR_PREFIX_BY_KIND.values():
    for _suffix in _ERROR_SUFFIX_BY_EXC.values():
        _id = f"{_prefix}.{_suffix}"
        assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"
for _id in _PKG_JSON_FAILURE.values():
    assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"


def _error_id(parser_kind: ParserKind, exc: BaseException) -> str:
    """Translate (parser_kind, exception) → ``"<prefix>.<suffix>"`` per ADR-0007."""
    suffix = _ERROR_SUFFIX_BY_EXC.get(type(exc), "unknown_error")
    return f"{_ERROR_PREFIX_BY_KIND[parser_kind]}.{suffix}"


def _cross_reference_native_modules(
    resolved: Mapping[str, str],
    catalog: Mapping[str, NativeModuleEntry],
) -> tuple[NativeModuleHit, ...]:
    """Exact-name dict lookup against the resolved-dep map.

    Iterates the catalog (small, fixed size) and checks ``name in resolved``
    (O(1) per lookup). Substring matching is forbidden by AC-15:
    ``@types/bcrypt`` is not a hit for ``bcrypt``.
    """
    hits: list[NativeModuleHit] = []
    for name, entry in catalog.items():
        if name not in resolved:
            continue
        hits.append(
            {
                "name": name,
                "version": resolved[name],
                "requires_node_gyp": bool(entry.requires_node_gyp),
                "system_deps_required": list(entry.system_deps_required),
                "binary_artifacts_glob": list(entry.binary_artifacts_glob),
                "catalog_entry_version": int(entry.catalog_entry_version),
            }
        )
    return tuple(hits)


def _read_package_json(
    pkg_path: Path, ctx: ProbeContext, errors: list[str]
) -> Mapping[str, Any] | None:
    """Read ``package.json`` via the memo seam (S1-07) with safe-json fallback.

    Returns ``None`` on any typed parser failure; the corresponding error_id
    is appended to ``errors``. A missing file returns an empty mapping so the
    rest of the probe runs with empty deps (slice still emitted; confidence
    stays high).
    """
    if not (pkg_path.exists() or pkg_path.is_symlink()):
        return {}
    try:
        if ctx.parsed_manifest is not None:
            memoed = ctx.parsed_manifest(pkg_path)
            if memoed is not None:
                return memoed
        return safe_json.load(
            pkg_path,
            max_bytes=_PARSE_MAX_BYTES,
            max_depth=_PARSE_MAX_DEPTH,
        )
    except (
        SizeCapExceeded,
        MalformedJSONError,
        SymlinkRefusedError,
        DepthCapExceeded,
    ) as exc:
        errors.append(_PKG_JSON_FAILURE[type(exc)])
        return None


@register_probe
class NodeManifestProbe(Probe):
    """Layer A — Node manifest + native-module catalog cross-reference.

    See module docstring for the full read pipeline and Open/Closed rationale.
    """

    name: str = "node_manifest"
    version: str = "0.1.0"
    layer = "A"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection"]
    timeout_seconds: int = 30
    declared_inputs: list[str] = [
        "package.json",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "src/codegenie/catalogs/native_modules.yaml",
    ]
    # First non-default ResourceBudget in Phase 1: pnpm-lock.yaml on
    # monorepos hits 20 MB; the default 5 MB truncate cap is too tight.
    declared_resource_budget: Final[ResourceBudget] = ResourceBudget(
        raw_artifact_mb=50, raw_artifact_truncate_mb=25
    )

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        warnings: list[str] = []
        errors: list[str] = []
        confidence: Literal["high", "medium", "low"] = "high"

        # (1) package.json
        pkg = _read_package_json(repo.root / "package.json", ctx, errors)
        if pkg is None:
            return self._build_output(
                t0, primary=None, warnings=warnings, errors=errors, confidence="low"
            )
        # Empty file on disk is fine; pkg is a Mapping (possibly empty).

        # (2) lockfile detection — existence-only (no parse-for-selection).
        present = [f for f in _ALL_LOCKFILES if (repo.root / f).exists()]
        if len(present) >= 2:
            warnings.append("lockfile.multi_present")
            confidence = "low"

        # Select the highest-precedence parseable lockfile.
        selected = next((f for f in _PARSEABLE_LOCKFILES if f in present), None)

        # (3) parse + flatten via the registries — no per-format branches.
        resolved: Mapping[str, str] = {}
        if selected is not None:
            parser_kind = _PARSER_KIND_BY_FILENAME[selected]
            try:
                parsed = _PARSERS[parser_kind](repo.root / selected)
                resolved = _FLATTENERS[parser_kind](parsed)
            except _PARSER_EXCEPTIONS as exc:
                errors.append(_error_id(parser_kind, exc))
                confidence = "low"

        # (4) catalog cross-reference (pure function).
        native_hits = _cross_reference_native_modules(resolved, NATIVE_MODULES)

        # (5) assemble slice.
        engines_obj = pkg.get("engines")
        declared_engines: dict[str, str] = (
            {k: v for k, v in engines_obj.items() if isinstance(k, str) and isinstance(v, str)}
            if isinstance(engines_obj, Mapping)
            else {}
        )
        runtime_deps = pkg.get("dependencies")
        dev_deps = pkg.get("devDependencies")
        optional_deps = pkg.get("optionalDependencies")
        bundled_deps = pkg.get("bundledDependencies")
        primary: dict[str, Any] = {
            "path": "package.json",
            "direct_dependencies": {
                "runtime": len(runtime_deps) if isinstance(runtime_deps, Mapping) else 0,
                "dev": len(dev_deps) if isinstance(dev_deps, Mapping) else 0,
            },
            "declared_engines": declared_engines,
            "lockfile": {"name": selected} if selected is not None else None,
            "native_modules": {
                "detected": len(native_hits) > 0,
                "packages": [dict(h) for h in native_hits],
            },
            "optional_dependencies": (
                len(optional_deps) if isinstance(optional_deps, Mapping) else 0
            ),
            "bundled_dependencies": (
                [s for s in bundled_deps if isinstance(s, str)]
                if isinstance(bundled_deps, list)
                else []
            ),
        }

        lockfile_path = repo.root / selected if selected is not None else None
        return self._build_output(
            t0,
            primary=primary,
            warnings=warnings,
            errors=errors,
            confidence=confidence,
            raw_lockfile=lockfile_path,
        )

    def _build_output(
        self,
        t0: float,
        *,
        primary: dict[str, Any] | None,
        warnings: list[str],
        errors: list[str],
        confidence: Literal["high", "medium", "low"],
        raw_lockfile: Path | None = None,
    ) -> ProbeOutput:
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        event = EVENT_PROBE_SUCCESS if confidence == "high" else EVENT_PROBE_FAILURE
        _log.info(event, probe=self.name, confidence=confidence)
        slice_payload: dict[str, Any] = {
            "manifests": {
                "primary": primary,
                "catalog_version": NATIVE_MODULES_CATALOG_VERSION,
                "warnings": list(warnings),
                "errors": list(errors),
            }
        }
        # Surface the selected lockfile as a raw artifact so the S1-09 soft
        # truncation policy has a real input on portfolio-scale repos
        # (S3-06 AC-8/9/10 unblocker).
        raw_artifacts: list[Path] = []
        if raw_lockfile is not None and raw_lockfile.is_file():
            raw_artifacts.append(raw_lockfile)
        return ProbeOutput(
            schema_slice=slice_payload,
            raw_artifacts=raw_artifacts,
            confidence=confidence,
            duration_ms=duration_ms,
            warnings=warnings,
            errors=errors,
        )
