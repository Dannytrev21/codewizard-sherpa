"""Typed failure markers for every codegenie chokepoint.

The hierarchy is intentionally flat: a single :class:`CodegenieError` root and
nine direct-child subclasses, each a behavior-free marker that names the module
where it is raised. Sources:

- ``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md`` §Agentic
  best practices — enumerates the nine subclasses.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md``
  — names :class:`SecretLikelyFieldNameError` and :class:`SymlinkRefusedError`.
- ``docs/phases/00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md``
  — names :class:`DisallowedSubprocessError` and :class:`ToolMissingError`.

Subclasses carry no ``__init__``, no ``__str__``, no class attributes — they
are markers only. Adding behavior is a separate decision (Rule 2, Rule 3).
"""

from __future__ import annotations

__all__ = [
    "CodegenieError",
    "ConfigError",
    "ToolMissingError",
    "ProbeError",
    "ProbeTimeoutError",
    "CacheError",
    "SchemaValidationError",
    "SecretLikelyFieldNameError",
    "DisallowedSubprocessError",
    "SymlinkRefusedError",
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


class CacheError(CodegenieError):
    """Raised by the cache store when a blob is unreadable, corrupt, or fails its checksum."""


class SchemaValidationError(CodegenieError):
    """Raised by the schema validator when a ProbeOutput or repo-context fails its JSON Schema."""


class SecretLikelyFieldNameError(CodegenieError):
    """Raised by the output sanitizer when a value's field name looks like a secret slot."""


class DisallowedSubprocessError(CodegenieError):
    """Raised by the exec wrapper when the requested binary is not on the allowlist."""


class SymlinkRefusedError(CodegenieError):
    """Raised by the writer / sanitizer walker when a symlink would escape the analyzed repo."""
