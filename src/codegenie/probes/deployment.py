"""``DeploymentProbe`` — Layer A, base-tier (S4-02).

Detects deployment shape (``helm`` > ``kustomize`` > ``raw`` > ``terraform``;
``none`` is the fall-through), parses Helm charts + values overlays,
follows Kustomize ``resources:`` one level deep with **load-bearing
zip-slip mitigation** (``Path.resolve()`` + repo-root containment), filters
raw Kubernetes manifests by ``kind`` to the Deployment-family, and lists
Terraform ``*.tf`` files by path only (no parsing).

ADRs honored:

- **ADR-0011** — no ``helm template`` invocation, no ``kustomize build``,
  no ``python-hcl2``; ``ALLOWED_BINARIES`` stays at ``{"git", "node"}``.
- **ADR-0012** — emits both ``image_reference: ImageRefBlock | null``
  (singleton, nullable primary) AND ``environments: list`` (additive)
  at the slice root. Singleton-vs-list disagreement resolved additively.
- **ADR-0010** — slice optional at envelope; ``type: "none"`` slice IS
  emitted when no markers match (distinguishes ran-and-found-nothing
  from didn't-run).
- **ADR-0007** — every warning ID is bare (no ``:<path>`` suffix); per-
  values-file parse errors record offending paths under
  ``raw/deployment.json``.
- **ADR-0004** — slice + ``ImageRefBlock`` + ``EnvironmentEntry`` are
  ``additionalProperties: false``; ``security_context`` is the
  documented ``additionalProperties: true`` exception (Kubernetes
  ``SecurityContext`` is a ~30-field evolving open-shape type).

**Open/Closed at the file boundary** — five module-level seams:

- ``_DEPLOYMENT_TYPE`` (``TypeAlias``): the closed set of deployment
  shapes. Schema enum is asserted at import time to match.
- ``_DEPLOYMENT_DETECTORS``: precedence-ordered ``(type, predicate)``
  tuple. Adding ``flux`` is one tuple insertion; zero edits to
  :meth:`DeploymentProbe.run`.
- ``_DEPLOYMENT_PARSERS``: dispatch ``Mapping[type, parser]``. Import-
  time assertion catches a new arm without a parser.
- ``_RAW_KIND_FILTER``: closed set of Deployment-family kinds.
- ``_WARNING_IDS`` / ``_ERROR_IDS``: frozensets pattern-checked against
  ADR-0007 at import time.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S4-02-deployment-probe.md``
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #6 + §"Data model" + §"Edge cases" rows 4 + 15
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0004``, ``0007``, ``0010``, ``0011``, ``0012``
- ``docs/production/adrs/0005-no-llm-in-gather-pipeline.md``
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal, NamedTuple, TypeAlias, TypedDict, get_args

import structlog

from codegenie.errors import (
    DepthCapExceeded,
    MalformedYAMLError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.logging import (
    EVENT_PROBE_FAILURE,
    EVENT_PROBE_START,
    EVENT_PROBE_SUCCESS,
)
from codegenie.parsers import safe_yaml
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.probes.registry import register_probe

__all__ = ["DeploymentProbe"]


_log = structlog.get_logger(__name__)


# --- module-level Open/Closed seams -----------------------------------------


_DEPLOYMENT_TYPE: TypeAlias = Literal["helm", "kustomize", "raw", "terraform", "none"]


class ImageRefBlock(TypedDict):
    """Strict ``additionalProperties: false`` shape per ADR-0012."""

    path: str
    value: str


class EnvironmentEntry(TypedDict):
    """One detected ``values-<env>.{yaml,yml}`` per ADR-0012."""

    name: str
    image_reference: ImageRefBlock | None


# Helm baseline + env-overlay file names. Baselines (``values.yaml`` /
# ``values.yml``) are exact; env overlays use the wider ``values*`` glob
# so non-conforming dot-separator variants (``values.prod.yaml``) are
# also discovered. ``_env_name_from_filename`` distinguishes conformant
# from non-conformant; non-conformant emits ``helm.values_filename_unrecognized``.
_VALUES_BASELINES: Final[frozenset[str]] = frozenset({"values.yaml", "values.yml"})
_VALUES_OVERLAY_GLOBS: Final[tuple[str, ...]] = ("values*.yaml", "values*.yml")


# Deployment-family k8s kinds — every other kind is filtered out.
_RAW_KIND_FILTER: Final[frozenset[str]] = frozenset(
    {"Deployment", "StatefulSet", "DaemonSet", "Pod"}
)


# Kustomize overlay caps (S4-02 AC-26 / arch §"Edge cases").
_OVERLAY_MAX_DEPTH: Final[int] = 5
_OVERLAY_MAX_FILES: Final[int] = 50


# Catalog roots for raw-manifest discovery.
_RAW_DIRS: Final[tuple[str, ...]] = ("deploy", "k8s", "kubernetes")
_RAW_GLOBS: Final[tuple[str, ...]] = ("*.yaml", "*.yml")


_PARSE_MAX_BYTES: Final[int] = 10 * 1024 * 1024
_PARSE_MAX_DEPTH: Final[int] = 64


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "kustomization.resource_outside_repo",
        "kustomization.depth_cap_exceeded",
        "kustomization.file_cap_exceeded",
        "helm.values_file_parse_error",
        "helm.values_filename_unrecognized",
        "helm.no_values_files",
        "deployment.multi_type",
        "deployment.raw_no_workloads",
        "terraform.paths_only",
    }
)


_ERROR_IDS: Final[frozenset[str]] = frozenset(
    {
        "deployment.size_cap_exceeded",
        "deployment.depth_cap_exceeded",
        "deployment.malformed_yaml",
        "deployment.symlink_refused",
    }
)


_CONFIDENCE_RANK: Final[Mapping[str, int]] = {"low": 0, "medium": 1, "high": 2}


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

for _id in (*_WARNING_IDS, *_ERROR_IDS):
    assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"


# --- pure helpers (functional core) -----------------------------------------


def _demote(current: str, target: str) -> str:
    """Monotone confidence downgrader; never upgrades. Verbatim copy from
    ``node_build_system.py:276`` (rule-of-three not yet met cross-file —
    extract to ``probes/_confidence.py`` at S4-03 per S4-02 deferred-patterns)."""
    if _CONFIDENCE_RANK[target] < _CONFIDENCE_RANK[current]:
        return target
    return current


def _is_under(candidate: Path, root_resolved: Path) -> bool:
    """Zip-slip primitive: True iff ``candidate`` resolves under ``root_resolved``.

    Load-bearing per ADR-0011's secure-by-construction clause. Uses
    ``Path.resolve()`` (which collapses ``..`` segments and follows
    symlinks) plus ``is_relative_to`` (Python 3.12+) / parent-walk
    fallback. Never trust ``str(candidate).startswith(str(root))`` —
    ``Path("/tmp/x") / "../outside.yaml"`` stringifies as
    ``/tmp/x/../outside.yaml`` which DOES start with ``/tmp/x``.
    """
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    try:
        return resolved.is_relative_to(root_resolved)
    except AttributeError:  # pragma: no cover — Python < 3.12
        return root_resolved == resolved or root_resolved in resolved.parents


def _env_name_from_filename(filename: str) -> tuple[str, bool]:
    """Pure: ``("prod", True)`` for ``values-prod.yaml`` /
    ``values-prod.yml``; ``("values.prod", False)`` for the
    dot-separator non-conforming variant; ``("values", False)`` for
    the bare ``values.yaml`` baseline (caller distinguishes baselines
    upstream).

    Accepts either a full filename (``values-prod.yaml``) or a bare
    stem (``values-prod``). The boolean is the AC-15 conformance flag;
    ``False`` triggers the ``helm.values_filename_unrecognized``
    warning at the caller.
    """
    stem = filename
    for suffix in (".yaml", ".yml"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if stem.startswith("values-") and len(stem) > len("values-"):
        return stem[len("values-") :], True
    return stem, False


def _extract_image_ref(values: Mapping[str, Any]) -> ImageRefBlock | None:
    """AC-17: handle the four Helm image shapes.

    - ``image: "<repo>:<tag>"`` shorthand → ``{path: "image", value: verbatim}``
    - ``image.repository`` + ``image.tag`` → ``{path: "image.repository",
      value: "<repo>:<tag>"}`` (concatenated)
    - ``image.repository`` alone → ``value: "<repo>"`` (no colon suffix)
    - ``image.tag`` alone, no repository → ``None``
    """
    image = values.get("image")
    if isinstance(image, str):
        return {"path": "image", "value": image}
    if isinstance(image, Mapping):
        repo = image.get("repository")
        tag = image.get("tag")
        if isinstance(repo, str) and isinstance(tag, (str, int)):
            return {"path": "image.repository", "value": f"{repo}:{tag}"}
        if isinstance(repo, str):
            return {"path": "image.repository", "value": repo}
    return None


def _filter_k8s_kinds(docs: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Pure: keep only documents whose ``kind`` is in ``_RAW_KIND_FILTER``."""
    return [d for d in docs if isinstance(d, Mapping) and d.get("kind") in _RAW_KIND_FILTER]


def _extract_container_specs(doc: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Pure: return container dicts. ``Pod`` uses flat ``spec.containers``;
    Deployment/StatefulSet/DaemonSet use ``spec.template.spec.containers``."""
    spec = doc.get("spec")
    if not isinstance(spec, Mapping):
        return []
    if doc.get("kind") == "Pod":
        containers = spec.get("containers")
    else:
        template = spec.get("template")
        inner = template.get("spec") if isinstance(template, Mapping) else None
        containers = inner.get("containers") if isinstance(inner, Mapping) else None
    if not isinstance(containers, list):
        return []
    return [c for c in containers if isinstance(c, Mapping)]


def _aggregate_exposed_ports(containers: Iterable[Mapping[str, Any]]) -> list[int]:
    """Pure deduper + ascending sorter for ``containerPort`` ints."""
    seen: set[int] = set()
    for c in containers:
        ports = c.get("ports")
        if not isinstance(ports, list):
            continue
        for p in ports:
            if not isinstance(p, Mapping):
                continue
            cp = p.get("containerPort")
            if isinstance(cp, int) and not isinstance(cp, bool):
                seen.add(cp)
    return sorted(seen)


def _aggregate_env_var_names(containers: Iterable[Mapping[str, Any]]) -> list[str]:
    """Pure deduper + alpha sorter for ``env[].name`` (NAMES ONLY)."""
    seen: set[str] = set()
    for c in containers:
        env = c.get("env")
        if not isinstance(env, list):
            continue
        for e in env:
            if not isinstance(e, Mapping):
                continue
            name = e.get("name")
            if isinstance(name, str):
                seen.add(name)
    return sorted(seen)


# --- detector predicates + precedence tuple ---------------------------------


def _has_helm(root: Path) -> bool:
    return (root / "Chart.yaml").is_file()


def _has_kustomize(root: Path) -> bool:
    return (root / "kustomization.yaml").is_file() or (root / "kustomization.yml").is_file()


def _has_raw_k8s(root: Path) -> bool:
    """Scan the well-known dirs for any YAML with a ``kind:`` field."""
    for top in _RAW_DIRS:
        d = root / top
        if not d.is_dir():
            continue
        for ext in _RAW_GLOBS:
            for path in d.rglob(ext):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                # Cheap presence check; full parse happens later. The
                # Helm chart `values.yaml` and `Chart.yaml` are not under
                # `_RAW_DIRS`, so this won't false-positive there.
                if re.search(r"^kind\s*:", text, flags=re.MULTILINE):
                    return True
    return False


def _has_terraform(root: Path) -> bool:
    return any(root.rglob("*.tf"))


_DEPLOYMENT_DETECTORS: Final[tuple[tuple[_DEPLOYMENT_TYPE, Callable[[Path], bool]], ...]] = (
    ("helm", _has_helm),
    ("kustomize", _has_kustomize),
    ("raw", _has_raw_k8s),
    ("terraform", _has_terraform),
)


assert tuple(t for t, _ in _DEPLOYMENT_DETECTORS) == ("helm", "kustomize", "raw", "terraform"), (
    "S4-02 _DEPLOYMENT_DETECTORS precedence: 'helm' > 'kustomize' > 'raw' > 'terraform'"
)


def _select_deployment_type(root: Path) -> tuple[_DEPLOYMENT_TYPE, list[_DEPLOYMENT_TYPE]]:
    """Pure: ``(primary, others_in_precedence_order)``."""
    detected: list[_DEPLOYMENT_TYPE] = [
        t for t, predicate in _DEPLOYMENT_DETECTORS if predicate(root)
    ]
    if not detected:
        return "none", []
    return detected[0], detected[1:]


# --- parser dispatch shape --------------------------------------------------


class _ParseResult(NamedTuple):
    """Per-parser dispatch outcome (DP-9). All parsers return this."""

    slice_fragment: dict[str, Any]
    warnings: list[str]
    confidence_demote_to: str | None  # None | "low" | "medium"


_EMPTY_SLICE: Final[Mapping[str, Any]] = {
    "chart_path": None,
    "image_reference": None,
    "environments": [],
    "terraform_files": [],
    "kustomization_resource_path_outside_repo": False,
    "security_context": None,
    "exposed_ports": [],
    "required_env_vars": [],
}


def _empty_fragment() -> dict[str, Any]:
    """Fresh copy of the empty-slice scaffold."""
    return {
        **_EMPTY_SLICE,
        "environments": [],
        "terraform_files": [],
        "exposed_ports": [],
        "required_env_vars": [],
    }


def _parse_helm(root: Path, ctx: ProbeContext) -> _ParseResult:
    """Helm parser — Chart.yaml + values overlays per ADR-0012."""
    fragment = _empty_fragment()
    warnings: list[str] = []
    demote: str | None = None
    parse_errors: list[dict[str, str]] = []

    fragment["chart_path"] = "Chart.yaml"

    # Discover baseline + env files via a wider glob; partition by name.
    discovered: dict[str, Path] = {}
    for pattern in _VALUES_OVERLAY_GLOBS:
        for path in sorted(root.glob(pattern)):
            discovered.setdefault(path.name, path)

    baseline_path: Path | None = None
    env_paths: list[Path] = []
    for name, path in discovered.items():
        if name in _VALUES_BASELINES:
            if baseline_path is None:
                baseline_path = path
        else:
            env_paths.append(path)

    baseline_values: Mapping[str, Any] | None = None
    if baseline_path is not None:
        try:
            baseline_values = safe_yaml.load(
                baseline_path,
                max_bytes=_PARSE_MAX_BYTES,
                max_depth=_PARSE_MAX_DEPTH,
            )
        except (
            SizeCapExceeded,
            DepthCapExceeded,
            MalformedYAMLError,
            SymlinkRefusedError,
        ) as exc:
            parse_errors.append({"path": baseline_path.name, "kind": type(exc).__name__})
            if "helm.values_file_parse_error" not in warnings:
                warnings.append("helm.values_file_parse_error")
            demote = "low"

    if baseline_values is not None:
        fragment["image_reference"] = _extract_image_ref(baseline_values)

    environments: list[EnvironmentEntry] = []
    for env_path in sorted(env_paths, key=lambda p: p.name):
        name, conforming = _env_name_from_filename(env_path.name)
        if not conforming and "helm.values_filename_unrecognized" not in warnings:
            warnings.append("helm.values_filename_unrecognized")
        try:
            data = safe_yaml.load(env_path, max_bytes=_PARSE_MAX_BYTES, max_depth=_PARSE_MAX_DEPTH)
        except (
            SizeCapExceeded,
            DepthCapExceeded,
            MalformedYAMLError,
            SymlinkRefusedError,
        ) as exc:
            parse_errors.append({"path": env_path.name, "kind": type(exc).__name__})
            if "helm.values_file_parse_error" not in warnings:
                warnings.append("helm.values_file_parse_error")
            demote = "low"
            continue
        environments.append({"name": name, "image_reference": _extract_image_ref(data)})

    environments.sort(key=lambda e: e["name"])
    fragment["environments"] = environments

    if baseline_path is None and not env_paths:
        warnings.append("helm.no_values_files")
        demote = "low"

    _write_raw(ctx, parse_errors)
    return _ParseResult(slice_fragment=fragment, warnings=warnings, confidence_demote_to=demote)


def _walk_overlays(
    root_resolved: Path,
    kustomization_path: Path,
    *,
    max_depth: int = _OVERLAY_MAX_DEPTH,
    max_files: int = _OVERLAY_MAX_FILES,
) -> tuple[list[Path], list[str]]:
    """Pure: ``(safe_resource_paths, warnings)``.

    Zip-slip refusal is the load-bearing defense per ADR-0011's
    secure-by-construction clause.
    """
    warnings: list[str] = []
    safe_paths: list[Path] = []
    visited: set[Path] = set()
    accepted_count = 0  # counts every non-zip-slip resource entry against max_files

    pending: list[tuple[Path, int]] = [(kustomization_path, 0)]

    while pending:
        current_kustomize, depth = pending.pop(0)
        if depth >= max_depth:
            if "kustomization.depth_cap_exceeded" not in warnings:
                warnings.append("kustomization.depth_cap_exceeded")
            continue
        try:
            data = safe_yaml.load(
                current_kustomize, max_bytes=_PARSE_MAX_BYTES, max_depth=_PARSE_MAX_DEPTH
            )
        except (
            SizeCapExceeded,
            DepthCapExceeded,
            MalformedYAMLError,
            SymlinkRefusedError,
        ):
            continue
        resources = data.get("resources")
        if not isinstance(resources, list):
            continue
        kustomize_dir = current_kustomize.parent
        for resource in resources:
            if not isinstance(resource, str):
                continue
            candidate = kustomize_dir / resource
            if not _is_under(candidate, root_resolved):
                if "kustomization.resource_outside_repo" not in warnings:
                    warnings.append("kustomization.resource_outside_repo")
                continue
            if accepted_count >= max_files:
                if "kustomization.file_cap_exceeded" not in warnings:
                    warnings.append("kustomization.file_cap_exceeded")
                return safe_paths, warnings
            accepted_count += 1
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in visited:
                continue
            visited.add(resolved)
            if resolved.is_dir():
                nested = resolved / "kustomization.yaml"
                if not nested.is_file():
                    nested = resolved / "kustomization.yml"
                if nested.is_file():
                    pending.append((nested, depth + 1))
                continue
            if resolved.is_file():
                safe_paths.append(resolved)

    return safe_paths, warnings


def _parse_kustomize(root: Path, ctx: ProbeContext) -> _ParseResult:
    """Kustomize parser — load-bearing zip-slip mitigation."""
    fragment = _empty_fragment()
    warnings: list[str] = []
    demote: str | None = None

    root_resolved = root.resolve()
    kustomization_path = root / "kustomization.yaml"
    if not kustomization_path.is_file():
        kustomization_path = root / "kustomization.yml"

    safe_paths, walk_warnings = _walk_overlays(root_resolved, kustomization_path)
    for w in walk_warnings:
        if w not in warnings:
            warnings.append(w)
    if "kustomization.resource_outside_repo" in warnings:
        fragment["kustomization_resource_path_outside_repo"] = True
        demote = "low"

    docs: list[Mapping[str, Any]] = []
    for path in safe_paths:
        try:
            for doc in safe_yaml.load_all(
                path, max_bytes=_PARSE_MAX_BYTES, max_depth=_PARSE_MAX_DEPTH
            ):
                if isinstance(doc, Mapping):
                    docs.append(doc)
        except (
            SizeCapExceeded,
            DepthCapExceeded,
            MalformedYAMLError,
            SymlinkRefusedError,
        ):
            continue

    workloads = _filter_k8s_kinds(docs)
    containers = [c for d in workloads for c in _extract_container_specs(d)]
    fragment["exposed_ports"] = _aggregate_exposed_ports(containers)
    fragment["required_env_vars"] = _aggregate_env_var_names(containers)
    fragment["security_context"] = _first_security_context(workloads)

    return _ParseResult(slice_fragment=fragment, warnings=warnings, confidence_demote_to=demote)


def _first_security_context(workloads: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """First ``containers[0].securityContext`` across workload docs in walk order."""
    for doc in workloads:
        for container in _extract_container_specs(doc):
            sc = container.get("securityContext")
            if isinstance(sc, Mapping):
                return sc
    return None


def _parse_raw(root: Path, ctx: ProbeContext) -> _ParseResult:
    """Raw-manifests parser — kind filter to Deployment family."""
    fragment = _empty_fragment()
    warnings: list[str] = []
    demote: str | None = None

    docs: list[Mapping[str, Any]] = []
    raw_marker_seen = False
    for top in _RAW_DIRS:
        d = root / top
        if not d.is_dir():
            continue
        paths: list[Path] = []
        for pattern in _RAW_GLOBS:
            paths.extend(sorted(d.rglob(pattern)))
        for path in paths:
            try:
                for doc in safe_yaml.load_all(
                    path, max_bytes=_PARSE_MAX_BYTES, max_depth=_PARSE_MAX_DEPTH
                ):
                    if isinstance(doc, Mapping) and "kind" in doc:
                        raw_marker_seen = True
                        docs.append(doc)
            except (
                SizeCapExceeded,
                DepthCapExceeded,
                MalformedYAMLError,
                SymlinkRefusedError,
            ):
                continue

    workloads = _filter_k8s_kinds(docs)
    containers = [c for d in workloads for c in _extract_container_specs(d)]
    fragment["exposed_ports"] = _aggregate_exposed_ports(containers)
    fragment["required_env_vars"] = _aggregate_env_var_names(containers)
    fragment["security_context"] = _first_security_context(workloads)

    if raw_marker_seen and not workloads:
        warnings.append("deployment.raw_no_workloads")
        demote = "low"

    return _ParseResult(slice_fragment=fragment, warnings=warnings, confidence_demote_to=demote)


def _terraform_files(root: Path) -> list[str]:
    """Lex-sorted POSIX-relative paths to ``*.tf`` files."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.tf"))


def _parse_terraform(root: Path, ctx: ProbeContext) -> _ParseResult:
    """Terraform parser — paths only per ADR-0011."""
    fragment = _empty_fragment()
    fragment["terraform_files"] = _terraform_files(root)
    return _ParseResult(
        slice_fragment=fragment,
        warnings=["terraform.paths_only"],
        confidence_demote_to="low",
    )


def _parse_none(root: Path, ctx: ProbeContext) -> _ParseResult:
    """No deployment markers — emit empty-but-present slice (AC-23)."""
    return _ParseResult(slice_fragment=_empty_fragment(), warnings=[], confidence_demote_to=None)


_DEPLOYMENT_PARSERS: Final[
    Mapping[_DEPLOYMENT_TYPE, Callable[[Path, ProbeContext], _ParseResult]]
] = {
    "helm": _parse_helm,
    "kustomize": _parse_kustomize,
    "raw": _parse_raw,
    "terraform": _parse_terraform,
    "none": _parse_none,
}


assert _DEPLOYMENT_PARSERS.keys() == set(get_args(_DEPLOYMENT_TYPE)), (
    f"S4-02 _DEPLOYMENT_PARSERS keys {set(_DEPLOYMENT_PARSERS.keys())!r} differ from "
    f"_DEPLOYMENT_TYPE arms {set(get_args(_DEPLOYMENT_TYPE))!r}. "
    "Add a parser before widening the type."
)


# --- raw artifact writer ----------------------------------------------------


def _write_raw(ctx: ProbeContext, parse_errors: list[dict[str, str]]) -> None:
    """Write per-file parse-error provenance to ``.codegenie/_probe_raw/`` (L-42)."""
    if not parse_errors:
        return
    raw_path = ctx.workspace / ".codegenie" / "_probe_raw" / "deployment.json"
    try:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps({"parse_errors": parse_errors}, sort_keys=True))
    except OSError:
        pass


# --- the probe --------------------------------------------------------------


@register_probe
class DeploymentProbe(Probe):
    """Layer A — Helm/Kustomize/raw/Terraform deployment evidence (no rendering)."""

    name: str = "deployment"
    version: str = "1.0.0"
    layer = "A"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 15
    declared_inputs: list[str] = [
        "deploy/**/*.yaml",
        "deploy/**/*.yml",
        "k8s/**/*.yaml",
        "k8s/**/*.yml",
        "kubernetes/**/*.yaml",
        "Chart.yaml",
        "values.yaml",
        "values-*.yaml",
        "kustomization.yaml",
        "kustomization.yml",
        "helm/**/*",
        "charts/**/*",
        "*.tf",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()

        primary, others = _select_deployment_type(repo.root)
        result = _DEPLOYMENT_PARSERS[primary](repo.root, ctx)
        slice_fragment = dict(result.slice_fragment)
        warnings = list(result.warnings)
        confidence: str = "high"
        if result.confidence_demote_to is not None:
            confidence = _demote(confidence, result.confidence_demote_to)

        if others:
            # Multi-type: gather terraform_files even when type != terraform.
            if "terraform" in others:
                slice_fragment["terraform_files"] = _terraform_files(repo.root)
            warnings.append("deployment.multi_type")
            confidence = _demote(confidence, "low")

        slice_fragment["type"] = primary
        slice_fragment["warnings"] = warnings

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        if confidence == "high":
            _log.info(
                EVENT_PROBE_SUCCESS,
                probe=self.name,
                confidence=confidence,
                deployment_type=primary,
            )
        else:
            _log.info(
                EVENT_PROBE_FAILURE,
                probe=self.name,
                confidence=confidence,
                deployment_type=primary,
                warnings=warnings,
            )

        return ProbeOutput(
            schema_slice={"deployment": slice_fragment},
            raw_artifacts=[],
            confidence=confidence,  # type: ignore[arg-type]
            duration_ms=duration_ms,
            warnings=[],
            errors=[],
        )
