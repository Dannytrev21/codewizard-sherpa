"""Typed failure markers for every codegenie chokepoint.

The hierarchy is intentionally flat: a single :class:`CodegenieError` root and
direct-child subclasses, each a behavior-free marker that names the module
where it is raised. Sources:

- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Agentic
  best practices — enumerates the eleven Phase 0 subclasses.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md``
  — names :class:`SecretLikelyFieldNameError` and :class:`SymlinkRefusedError`.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
  — names :class:`DisallowedSubprocessError` and :class:`ToolMissingError`.
- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md`` §Error
  escalation — adds the six Phase 1 marker subclasses
  (:class:`SizeCapExceeded`, :class:`DepthCapExceeded`,
  :class:`MalformedJSONError`, :class:`MalformedYAMLError`,
  :class:`MalformedLockfileError`, :class:`CatalogLoadError`) raised by
  ``parsers/`` and ``catalogs/``.

Subclasses carry no ``__init__``, no ``__str__``, no class attributes — they
are markers only. Adding behavior is a separate decision (Rule 2, Rule 3).

Phase 1 (Layer A) adds six marker subclasses for ``parsers/`` and
``catalogs/`` raise sites. The structured ``WarningId`` per ADR-0007 is
constructed by the **catch site** (the calling probe), not embedded on the
exception class.
"""

from __future__ import annotations

__all__ = [
    "CodegenieError",
    "ConfigError",
    "ToolMissingError",
    "ProbeError",
    "ProbeTimeoutError",
    "ProbeBudgetExceeded",
    "CacheError",
    "SchemaValidationError",
    "SecretLikelyFieldNameError",
    "DisallowedSubprocessError",
    "SymlinkRefusedError",
    "AllProbesFailedError",
    # Phase 1 (Layer A) — S1-01.
    "SizeCapExceeded",
    "DepthCapExceeded",
    "MalformedJSONError",
    "MalformedYAMLError",
    "MalformedLockfileError",
    "CatalogLoadError",
    # Phase 2 (Layers B–G) — S1-02.
    "FreshnessRegistryError",
    # Phase 2 (Layers B–G) — S1-04.
    "TCCMLoadError",
]


class CodegenieError(Exception):
    """Root of the codegenie error hierarchy (every chokepoint subclass)."""


class ConfigError(CodegenieError):
    """Raised by the config loader when on-disk config fails to parse or validate."""


class ToolMissingError(CodegenieError):
    """Raised by the tool_check / exec wrapper when a required CLI is absent on PATH."""


class ProbeError(CodegenieError):
    """Raised by a probe when its declared work fails (caught by the coordinator)."""


class ProbeTimeoutError(CodegenieError):
    """Raised by the coordinator when a probe exceeds its per-probe wall-clock budget."""


class ProbeBudgetExceeded(CodegenieError):
    """Raised by the coordinator's ``BudgetingContext.report_bytes`` when a
    probe's cumulative raw-artifact write exceeds its declared
    ``raw_artifact_mb`` budget (S3-05 / Gap 3)."""


class CacheError(CodegenieError):
    """Raised by the cache store when a blob is unreadable, corrupt, or fails its checksum."""


class SchemaValidationError(CodegenieError):
    """Raised by the schema validator when a ProbeOutput or repo-context fails its JSON Schema."""


class SecretLikelyFieldNameError(CodegenieError):
    """Raised by the output sanitizer when a value's field name looks like a secret slot."""


class DisallowedSubprocessError(CodegenieError):
    """Raised by the exec wrapper when the requested binary is not on the allowlist."""


class SymlinkRefusedError(CodegenieError):
    """Raised by the writer / sanitizer walker when a symlink would escape the
    analyzed repo, and by parsers/safe_json, parsers/safe_yaml, and
    parsers/jsonc (O_NOFOLLOW open) when a path's final component is
    itself a symlink."""


class AllProbesFailedError(CodegenieError):
    """Raised by the coordinator-result drainer in the CLI when every probe was
    Skipped or returned an errored Ran — i.e. ``len(GatherResult.outputs) == 0``.
    Maps to gather exit code 2 per ADR-0009 §Consequences."""


# --- Phase 1 (Layer A) markers — S1-01 ----------------------------------------


class SizeCapExceeded(CodegenieError):
    """Raised by parsers (safe_json.load / safe_yaml.load) when the file's
    pre-parse size exceeds the configured cap (e.g., package.json > 5 MB,
    lockfile > 50 MB)."""


class DepthCapExceeded(CodegenieError):
    """Raised by parsers (safe_json / safe_yaml) when the post-parse depth
    walker observes a structure exceeding the configured max_depth (e.g.,
    billion-laughs)."""


class MalformedJSONError(CodegenieError):
    """Raised by parsers (safe_json.load) when the file fails JSON decode
    (delegates to stdlib json.JSONDecodeError detail)."""


class MalformedYAMLError(CodegenieError):
    """Raised by parsers (safe_yaml.load) when CSafeLoader refuses the bytes
    (e.g., !!python/object tag) or the load itself raises."""


class MalformedLockfileError(CodegenieError):
    """Raised by parsers (lockfile parsers: pnpm, npm, yarn) when the file
    fails structural validation."""


class CatalogLoadError(CodegenieError):
    """Raised by catalogs at module import time when the catalog YAML fails
    self-schema validation or contains a duplicate name. This is a
    load-bearing-invariant violation — hard fail at CLI startup; operator
    must fix the catalog before any gather runs."""


# --- Phase 2 (Layers B–G) markers — S1-02 -------------------------------------


class FreshnessRegistryError(CodegenieError):
    """Raised by ``codegenie.indices.registry`` on duplicate
    ``@register_index_freshness_check`` decoration. Hard fail at import time
    (load-bearing fail-loud surface — a registry that silently shadows is
    worse than no registry; mirrors the Phase-0 ``ProbeError`` precedent)."""


class TCCMLoadError(CodegenieError):
    """Raised by ``codegenie.tccm.loader.TCCMLoader.load`` when a Task-Class
    Context Manifest YAML fails to load. Reason carried as positional
    ``args[0]`` prefix — one of ``"parse: …"``, ``"schema: …"``,
    ``"unknown_query_primitive: …"``. Marker only: no ``__init__``, no
    class state. Consumers parse the prefix; the structured reason lives at
    the catch site (mirrors ``MalformedYAMLError`` / ``CatalogLoadError``)."""
