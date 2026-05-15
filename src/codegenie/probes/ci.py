"""``CIProbe`` — Layer A, base-tier (S4-01).

Reads the well-known CI marker paths in catalog precedence order
(``github_actions > gitlab_ci > circleci > jenkins > azure_pipelines``)
and produces the ``ci`` slice. First match wins for ``provider``;
remaining matches accumulate on ``additional_providers`` (Phase 1
additive — resolves the singleton-vs-list disagreement between
``localv2.md §5.1 A4`` and real-world multi-provider repos).

**Open/Closed at the file boundary** — three module-level seams:

- ``_PROVIDER_PRECEDENCE``: precedence-ordered tuple, anchored to
  ``CI_PROVIDERS`` catalog YAML order at import time. A reshuffled
  catalog without a corresponding edit here trips the import-time
  assertion (Rule 12 — fail loud).
- ``_CI_PARSERS``: dispatch registry keyed on the ``Literal`` arms of
  ``CIProviderEntry.parser``. Adding a sixth provider is one new
  function + one dict entry; zero edits to the iterate-catalog loop in
  :meth:`CIProbe.run`.
- ``_IMAGE_BUILD_MARKERS``: tagged tuple ``(substring, "run" | "uses")``
  pinning each marker to the workflow-step shape that carries it. Fixes
  the original outline's run-vs-uses confusion (``docker/build-push-action``
  is a ``uses:`` reference, not a ``run:`` shell substring).

**Compile-time discipline (Rule 12).** ``_WARNING_IDS`` is a frozenset
asserted against the ADR-0007 pattern at import time; a typo'd ID
refuses to load the module rather than slipping into a slice.

**Failure routing (Phase 1 simplification).** Per-file workflow parse
errors emit the bare ``ci.workflow_parse_error`` warning; the offending
path is recorded under ``raw/ci.json`` (CN-1 resolution — colon-suffixed
WarningIds violate ADR-0007). All parser exceptions in Phase 1 land in
``slice["warnings"]``; ``ProbeOutput.errors`` stays empty for ``CIProbe``.

Sources:

- ``docs/phases/01-context-gather-layer-a-node/stories/S4-01-ci-probe.md``
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #5; §"Data model" CISlice
- ``docs/phases/01-context-gather-layer-a-node/ADRs/`` —
  ``0004-per-probe-subschema-additional-properties-false.md`` (slice strict),
  ``0006-native-module-catalog-versioning.md`` (catalog in declared_inputs),
  ``0007-warnings-id-pattern.md`` (ID pattern),
  ``0009-no-new-c-extension-parser-dependencies.md`` (CSafeLoader closure),
  ``0010-probe-output-trust-boundary.md`` (slice optional at envelope).
- ``docs/production/adrs/0005-no-llm-in-gather-pipeline.md`` —
  ``references_secrets`` records literal names; values never resolved.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias, cast, get_args

import structlog

from codegenie.catalogs import CI_PROVIDERS
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

__all__ = ["CIProbe"]


_log = structlog.get_logger(__name__)


# --- module-level Open/Closed seams -----------------------------------------


_PARSER_LITERAL: TypeAlias = Literal[
    "github_actions",
    "gitlab_ci",
    "jenkins",
    "circleci",
    "azure_pipelines",
]


# Catalog precedence pinned at file boundary. A reshuffled
# ``ci_providers.yaml`` without a corresponding edit here fails at
# import time (assertion below). Mirrors the ``_LOCKFILE_PRECEDENCE``
# anchor in ``node_build_system.py``.
_PROVIDER_PRECEDENCE: Final[tuple[str, ...]] = (
    "github_actions",
    "gitlab_ci",
    "circleci",
    "jenkins",
    "azure_pipelines",
)


# Image-build marker table — tagged with the workflow-step shape that
# carries it (``"run"`` for ``run:`` shell substrings, ``"uses"`` for
# ``uses:`` action references). First hit wins.
_IMAGE_BUILD_MARKERS: Final[tuple[tuple[str, Literal["run", "uses"]], ...]] = (
    ("docker build", "run"),
    ("docker buildx", "run"),
    ("docker/build-push-action", "uses"),
)


# Test-command markers (substring match against workflow run/script lines).
# Module-level for stability; if this grows past five entries a Phase-2
# ADR migrates it to a YAML catalog (matches ``native_modules.yaml``
# precedent).
_UNIT_TEST_MARKERS: Final[tuple[str, ...]] = (
    "npm test",
    "npm run test",
    "vitest",
    "jest",
    "pytest",
    "go test",
)


_SMOKE_TEST_MARKERS: Final[tuple[str, ...]] = (
    "npm run smoke",
    "scripts/smoke",
    "smoke.sh",
    "smoke.js",
    "smoke.ts",
)


# Bounded secrets regex — anchored upper bound (130 chars total) on the
# captured identifier. Single capture group, no backtracking nesting.
# This is the one regex in this probe that runs on attacker-controllable
# bytes; the ReDoS guard (T-12) enforces a one-second wall-clock ceiling
# on a 5000-rep adversarial input.
_SECRETS_RE: Final[re.Pattern[str]] = re.compile(
    r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]{0,128})\s*\}\}"
)


# Bounded Jenkinsfile ``sh '...'`` / ``sh "..."`` extractor. Single
# capture group, no nested groups, line-bounded. The regex IS the
# Jenkinsfile contract — Phase 1 has no Groovy parser (ADR-0009 forbids
# new C-extension parser deps).
_JENKINS_SH_RE: Final[re.Pattern[str]] = re.compile(
    r"""sh\s+(?:'([^'\n]{1,500})'|"([^"\n]{1,500})")"""
)


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "ci.jenkinsfile_regex_only",
        "ci.multi_provider",
        "ci.workflow_parse_error",
        "ci.gitlab_ci_parse_error",
        "ci.local_action_unparsed",
        "ci.empty_workflows_dir",
        "ci.circleci_presence_only",
        "ci.azure_pipelines_presence_only",
    }
)


_CONFIDENCE_RANK: Final[Mapping[str, int]] = {"low": 0, "medium": 1, "high": 2}


_PARSE_MAX_BYTES: Final[int] = 10 * 1024 * 1024
_PARSE_MAX_DEPTH: Final[int] = 64


# --- compile-time discipline (Rule 12) --------------------------------------


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

for _id in _WARNING_IDS:
    assert _ID_PATTERN.match(_id), f"ADR-0007 violation: {_id!r}"

assert _PROVIDER_PRECEDENCE == tuple(CI_PROVIDERS.keys()), (
    "S4-01 _PROVIDER_PRECEDENCE drift: ci_providers.yaml order "
    f"{tuple(CI_PROVIDERS.keys())!r} differs from the precedence pinned "
    f"in ci.py {_PROVIDER_PRECEDENCE!r}. Fix one of them and re-run."
)


# --- pure helpers (functional core, AC-26) ---------------------------------


def _demote(current: str, target: str) -> str:
    if _CONFIDENCE_RANK[target] < _CONFIDENCE_RANK[current]:
        return target
    return current


def _select_provider(
    present: Sequence[str], precedence: Sequence[str]
) -> tuple[str | None, list[str]]:
    """First-match-wins selector preserving precedence order in the rest.

    ``present`` is expected to be pre-sorted by ``precedence`` (the
    caller in :meth:`CIProbe.run` builds ``present`` by iterating
    ``precedence``); the helper does not sort defensively to keep its
    contract minimal and observable in tests.
    """
    if not present:
        return None, []
    by_precedence = {name: i for i, name in enumerate(precedence)}
    ordered = sorted(present, key=lambda n: by_precedence.get(n, len(precedence)))
    return ordered[0], list(ordered[1:])


def _extract_run_strings(workflow: Mapping[str, Any]) -> list[str]:
    """Walk ``jobs.*.steps[].run`` returning string entries in source order."""
    out: list[str] = []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return out
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            run = step.get("run")
            if isinstance(run, str):
                out.append(run)
    return out


def _extract_uses_strings(workflow: Mapping[str, Any]) -> list[str]:
    """Walk ``jobs.*.steps[].uses`` returning string entries in source order."""
    out: list[str] = []
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return out
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if isinstance(uses, str):
                out.append(uses)
    return out


def _extract_secret_names(text: str) -> list[str]:
    """Sorted+deduped literal identifier names captured by ``_SECRETS_RE``."""
    return sorted({m.group(1) for m in _SECRETS_RE.finditer(text)})


def _collect_string_values(node: Any) -> list[str]:
    """Depth-first walk yielding every string leaf in ``node``.

    Used for secrets-regex coverage that must not depend on the
    workflow's ``jobs.*.steps[].run`` shape — secrets references can
    appear under any key (``env:``, ``with:``, top-level commands).
    """
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            out.extend(_collect_string_values(v))
    elif isinstance(node, list):
        for v in node:
            out.extend(_collect_string_values(v))
    return out


def _detect_image_build(runs: Sequence[str], uses: Sequence[str]) -> tuple[bool, str | None]:
    """Iterate ``_IMAGE_BUILD_MARKERS`` in order; first hit wins.

    The marker tuple is the precedence — first marker that finds a
    substring match in the appropriate stream (``run:`` or ``uses:``)
    wins. Returns ``(builds_image, image_build_command)``.
    """
    for substring, kind in _IMAGE_BUILD_MARKERS:
        stream = runs if kind == "run" else uses
        for entry in stream:
            if substring in entry:
                return True, entry
    return False, None


def _first_marker_match(entries: Sequence[str], markers: Sequence[str]) -> str | None:
    for entry in entries:
        for marker in markers:
            if marker in entry:
                return entry
    return None


def _extract_gitlab_run_strings(workflow: Mapping[str, Any]) -> list[str]:
    """Walk top-level GitLab CI job entries returning ``script:`` strings.

    GitLab CI jobs are top-level dict entries (excluding well-known
    config keys like ``stages:`` / ``image:``). Each job carries
    ``script:`` and/or ``before_script:`` as a list of shell strings or
    a single shell string.
    """
    out: list[str] = []
    reserved = {"stages", "image", "variables", "include", "default", "workflow"}
    for key, job in workflow.items():
        if key in reserved or not isinstance(job, dict):
            continue
        for field in ("script", "before_script"):
            value = job.get(field)
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, list):
                out.extend(s for s in value if isinstance(s, str))
    return out


# --- parser dispatch shape --------------------------------------------------


class _ParseOutcome:
    """Per-parser scratchpad accumulated as the catalog is iterated."""

    __slots__ = (
        "workflow_files",
        "runs",
        "uses",
        "secrets_text",
        "warnings",
        "parse_errors",
        "confidence",
    )

    def __init__(self) -> None:
        self.workflow_files: list[str] = []
        self.runs: list[str] = []
        self.uses: list[str] = []
        self.secrets_text: list[str] = []
        self.warnings: list[str] = []
        self.parse_errors: list[dict[str, str]] = []
        self.confidence: str = "high"


_ParserKind: TypeAlias = _PARSER_LITERAL


def _parse_github_actions(root: Path) -> _ParseOutcome:
    out = _ParseOutcome()
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return out
    candidates = sorted(
        list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")),
        key=lambda p: p.name,
    )
    if not candidates:
        out.warnings.append("ci.empty_workflows_dir")
        out.confidence = _demote(out.confidence, "low")
        return out
    for path in candidates:
        try:
            data = safe_yaml.load(path, max_bytes=_PARSE_MAX_BYTES, max_depth=_PARSE_MAX_DEPTH)
        except (
            SizeCapExceeded,
            DepthCapExceeded,
            MalformedYAMLError,
            SymlinkRefusedError,
        ) as exc:
            out.parse_errors.append({"path": path.name, "kind": type(exc).__name__})
            if "ci.workflow_parse_error" not in out.warnings:
                out.warnings.append("ci.workflow_parse_error")
            continue
        out.workflow_files.append(path.name)
        runs = _extract_run_strings(data)
        uses = _extract_uses_strings(data)
        out.runs.extend(runs)
        out.uses.extend(uses)
        # Secrets references can appear in any string leaf (run:, with:,
        # env:, even top-level on the malformed-but-parseable fixtures
        # the test corpus carries). Walk the parsed dict end-to-end.
        out.secrets_text.extend(_collect_string_values(data))
        if any(u.startswith("./") for u in uses):
            if "ci.local_action_unparsed" not in out.warnings:
                out.warnings.append("ci.local_action_unparsed")
    return out


def _parse_gitlab_ci(root: Path) -> _ParseOutcome:
    out = _ParseOutcome()
    path = root / ".gitlab-ci.yml"
    if not path.is_file():
        return out
    try:
        data = safe_yaml.load(path, max_bytes=_PARSE_MAX_BYTES, max_depth=_PARSE_MAX_DEPTH)
    except (
        SizeCapExceeded,
        DepthCapExceeded,
        MalformedYAMLError,
        SymlinkRefusedError,
    ) as exc:
        out.parse_errors.append({"path": path.name, "kind": type(exc).__name__})
        out.warnings.append("ci.gitlab_ci_parse_error")
        out.confidence = _demote(out.confidence, "low")
        return out
    out.workflow_files.append(path.name)
    runs = _extract_gitlab_run_strings(data)
    out.runs.extend(runs)
    out.secrets_text.extend(_collect_string_values(data))
    return out


def _parse_jenkinsfile(root: Path) -> _ParseOutcome:
    out = _ParseOutcome()
    path = root / "Jenkinsfile"
    if not path.is_file():
        return out
    out.workflow_files.append(path.name)
    out.warnings.append("ci.jenkinsfile_regex_only")
    out.confidence = _demote(out.confidence, "low")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        m = _JENKINS_SH_RE.search(line)
        if m is not None:
            captured = m.group(1) or m.group(2) or ""
            out.runs.append(captured)
    return out


def _parse_circleci_stub(root: Path) -> _ParseOutcome:
    out = _ParseOutcome()
    path = root / ".circleci" / "config.yml"
    if not path.is_file():
        return out
    out.warnings.append("ci.circleci_presence_only")
    out.confidence = _demote(out.confidence, "low")
    return out


def _parse_azure_stub(root: Path) -> _ParseOutcome:
    out = _ParseOutcome()
    path = root / "azure-pipelines.yml"
    if not path.is_file():
        return out
    out.warnings.append("ci.azure_pipelines_presence_only")
    out.confidence = _demote(out.confidence, "low")
    return out


_CI_PARSERS: Final[Mapping[_ParserKind, Callable[[Path], _ParseOutcome]]] = {
    "github_actions": _parse_github_actions,
    "gitlab_ci": _parse_gitlab_ci,
    "jenkins": _parse_jenkinsfile,
    "circleci": _parse_circleci_stub,
    "azure_pipelines": _parse_azure_stub,
}


# Catch a new catalog ``Literal`` arm without a corresponding parser
# entry at import time (Rule 12 — fail loud).
assert set(_CI_PARSERS.keys()) == set(get_args(_PARSER_LITERAL)), (
    f"S4-01 _CI_PARSERS keys {set(_CI_PARSERS.keys())!r} differ from "
    f"_PARSER_LITERAL arms {set(get_args(_PARSER_LITERAL))!r}. "
    "Add a parser function before widening the catalog."
)


# --- presence detection -----------------------------------------------------


def _provider_present(root: Path, name: str) -> bool:
    """Provider-specific presence check (handles directories vs files)."""
    if name == "github_actions":
        return (root / ".github" / "workflows").is_dir()
    if name == "gitlab_ci":
        return (root / ".gitlab-ci.yml").is_file()
    if name == "circleci":
        return (root / ".circleci" / "config.yml").is_file()
    if name == "jenkins":
        return (root / "Jenkinsfile").is_file()
    if name == "azure_pipelines":
        return (root / "azure-pipelines.yml").is_file()
    return False


# --- the probe --------------------------------------------------------------


@register_probe
class CIProbe(Probe):
    """Layer A — CI provider, workflows, image-build, secrets (literal names)."""

    name: str = "ci"
    version: str = "1.0.0"
    layer = "A"
    tier = "base"
    applies_to_tasks: list[str] = ["*"]
    applies_to_languages: list[str] = ["*"]
    requires: list[str] = []
    timeout_seconds: int = 10
    declared_inputs: list[str] = [
        ".github/workflows/*.yml",
        ".github/workflows/*.yaml",
        ".gitlab-ci.yml",
        ".circleci/config.yml",
        "Jenkinsfile",
        "azure-pipelines.yml",
        "src/codegenie/catalogs/ci_providers.yaml",
    ]

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()
        warnings: list[str] = []
        confidence: str = "high"

        # --- (1) provider presence + selection --------------------------
        present = [name for name in _PROVIDER_PRECEDENCE if _provider_present(repo.root, name)]
        provider, additional_providers = _select_provider(present, _PROVIDER_PRECEDENCE)
        if len(present) > 1:
            warnings.append("ci.multi_provider")
            confidence = _demote(confidence, "low")

        # --- (2) dispatch to per-provider parsers -----------------------
        # Iterate every present provider's parser so multi-provider repos
        # accumulate warnings + parse_errors from every contributor.
        all_parse_errors: list[dict[str, str]] = []
        workflow_files: list[str] = []
        runs: list[str] = []
        uses: list[str] = []
        secrets_text: list[str] = []
        for name in present:
            # ``present`` is built from ``_PROVIDER_PRECEDENCE`` whose
            # entries are exactly the ``_PARSER_LITERAL`` arms (asserted
            # at import time), so the cast is sound.
            parser = _CI_PARSERS[cast(_ParserKind, name)]
            outcome = parser(repo.root)
            workflow_files.extend(outcome.workflow_files)
            runs.extend(outcome.runs)
            uses.extend(outcome.uses)
            secrets_text.extend(outcome.secrets_text)
            for w in outcome.warnings:
                if w not in warnings:
                    warnings.append(w)
            confidence = _demote(confidence, outcome.confidence)
            all_parse_errors.extend(outcome.parse_errors)

        workflow_files = sorted(workflow_files)

        # --- (3) image build + test commands ----------------------------
        builds_image, image_build_command = _detect_image_build(runs, uses)
        unit_test_command = _first_marker_match(runs, _UNIT_TEST_MARKERS)
        # Jenkinsfile is presence + bounded regex only — the captured sh
        # commands ARE the test commands in Phase-1 low-confidence mode.
        # Fall back to the first captured shell string when no specific
        # unit-test marker matched.
        if unit_test_command is None and provider == "jenkins" and runs:
            unit_test_command = runs[0]
        smoke_test_command = _first_marker_match(runs, _SMOKE_TEST_MARKERS)

        # --- (4) secrets ----------------------------------------------
        references_secrets = _extract_secret_names("\n".join(secrets_text))

        # --- (5) raw artifact (CN-1: parse-error path provenance) -----
        # The runtime ``BudgetingContext`` only exposes ``workspace``; the
        # ``ProbeContext.output_dir`` field is a Phase-0 spec absent from
        # the per-dispatch context. Write under the established
        # ``.codegenie/`` namespace (CLAUDE.md ; S3-06 L-39 confirms it is
        # already excluded from input-fingerprint walks). The CLI's raw-
        # artifact reader then copies this to ``.codegenie/context/raw/``.
        raw_artifacts: list[Path] = []
        if all_parse_errors or provider is not None:
            raw_path = ctx.workspace / ".codegenie" / "_probe_raw" / "ci.json"
            try:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_text(
                    json.dumps(
                        {
                            "provider": provider,
                            "additional_providers": additional_providers,
                            "workflow_files": workflow_files,
                            "parse_errors": all_parse_errors,
                        },
                        sort_keys=True,
                    )
                )
                raw_artifacts.append(raw_path)
            except OSError:
                # Raw artifact write is best-effort; the slice carries
                # the load-bearing facts.
                pass

        slice_payload: dict[str, Any] = {
            "provider": provider,
            "additional_providers": additional_providers,
            "workflow_files": workflow_files,
            "builds_image": builds_image,
            "image_build_command": image_build_command,
            "unit_test_command": unit_test_command,
            "smoke_test_command": smoke_test_command,
            "references_secrets": references_secrets,
            "warnings": warnings,
        }

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        if confidence == "high":
            _log.info(
                EVENT_PROBE_SUCCESS,
                probe=self.name,
                confidence=confidence,
                provider=provider,
            )
        else:
            _log.info(
                EVENT_PROBE_FAILURE,
                probe=self.name,
                confidence=confidence,
                warnings=warnings,
            )

        return ProbeOutput(
            schema_slice={"ci": slice_payload},
            raw_artifacts=raw_artifacts,
            confidence=confidence,  # type: ignore[arg-type]
            duration_ms=duration_ms,
            warnings=[],
            errors=[],
        )
