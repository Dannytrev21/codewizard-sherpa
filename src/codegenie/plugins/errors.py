"""Typed failure markers for the Phase 3 plugin kernel.

Three exit-code-4 failure classes (Phase-3 ADR-0002 §Consequences):

- :class:`PluginAlreadyRegistered` — duplicate ``manifest.name`` at
  ``PluginRegistry.register`` time. Carries a typed ``.name: PluginId``
  attribute so the S2-03 loader and the exit-code-4 formatter can
  consume a structured field rather than parsing ``args[0]``. Message
  names both colliding ``module.qualname`` strings — mirrors
  ``codegenie.probes.registry``'s
  ``ProbeError`` collision message (``probes/registry.py:154-158``).
- :class:`PluginNotRegistered` — :meth:`PluginRegistry.get` miss. Carries
  the missing ``.name: PluginId`` as a typed attribute.
- :class:`PluginExtendsCycle` — raised by S2-04's resolver when the
  ``extends`` chain cycles. Placeholder here so the exception hierarchy
  lives in one file; the resolver wires it up.

S2-03 also lands the **tagged-union sum type** :data:`PluginRejected`
(ADR-0010 §Decision 3) — seven frozen dataclass variants, each carrying
only its own evidence. The Phase-3 plugin loader returns ``Err(...)`` over
the union; the CLI maps any variant to exit code 4 via
:func:`exit_code_for_rejection`.

All three legacy exception classes extend :class:`codegenie.errors.CodegenieError`.
The seven :data:`PluginRejected` variants are pure Pydantic ``BaseModel`` value
types — markers + structured payloads — no behavior, no logging, no I/O.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from codegenie.errors import CodegenieError
from codegenie.types.identifiers import BlobDigest, PluginId

__all__ = [
    "IntegrityMismatch",
    "LockFileMalformed",
    "MissingManifest",
    "MissingPluginDirectory",
    "PluginAlreadyRegistered",
    "PluginExtendsCycle",
    "PluginImportError",
    "PluginNotRegistered",
    "PluginRejected",
    "SchemaViolation",
    "SymlinkEscape",
    "UnlockedPlugin",
    "exit_code_for_rejection",
]


# --- Legacy exception hierarchy (S2-01) -------------------------------------


class PluginAlreadyRegistered(CodegenieError):
    """Raised by :meth:`PluginRegistry.register` when a plugin's
    ``manifest.name`` is already registered into the same registry.

    Carries a typed ``.name: PluginId`` attribute so consumers (the S2-03
    loader, the exit-code-4 formatter) read structured data. The message
    names both colliding ``module.qualname`` strings — an operator
    grepping a multi-plugin tree can locate both registrations from the
    message alone (precedent: ``probes/registry.py:154-158``).
    """

    name: PluginId

    def __init__(self, name: PluginId, existing: str, duplicate: str) -> None:
        self.name = name
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(f"duplicate plugin name {name!r}: {existing} and {duplicate}")


class PluginNotRegistered(CodegenieError):
    """Raised by :meth:`PluginRegistry.get` when the requested name is
    not in the registry.

    Carries a typed ``.name: PluginId`` attribute (not just a stringified
    message) so the resolver in S2-04 and CLI formatters can match on a
    structured field.
    """

    name: PluginId

    def __init__(self, name: PluginId) -> None:
        self.name = name
        super().__init__(f"plugin {name!r} is not registered")


class PluginExtendsCycle(CodegenieError):
    """Raised by S2-04's resolver when the ``extends`` chain cycles.

    Placeholder declaration here so the Phase 3 plugin-error hierarchy
    lives in one file — S2-04 wires the raise site and adds the
    cycle-chain payload.
    """


# --- :data:`PluginRejected` tagged-union (S2-03 — ADR-0010 §Decision 3) -----
#
# Each variant carries only the evidence its failure class actually has.
# ``IntegrityMismatch`` is the only variant with both ``expected`` and
# ``actual`` digests (mandatory ``BlobDigest`` — no ``str | None``);
# ``SymlinkEscape`` carries the offending path; ``SchemaViolation`` /
# ``PluginImportError`` / ``LockFileMalformed`` carry ``detail: str``.
# Adding a new failure mode = a new ``BaseModel`` variant + one new arm
# in every consumer-site ``match`` block (Open/Closed at the file boundary).


class IntegrityMismatch(BaseModel):
    """Per-plugin SHA-256 tree-digest disagrees with ``PLUGINS.lock``.

    The ADR-0011 honest-framing language: this is "integrity check"
    failure, NOT "signature failure". Phase 11 substitutes Sigstore via
    the :class:`PluginVerifier` Protocol; the variant name still uses
    "integrity" because the structural meaning — "the bytes on disk do
    not match the bytes the lock attests" — does not change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["integrity_mismatch"] = "integrity_mismatch"
    plugin: PluginId
    expected: BlobDigest
    actual: BlobDigest


class MissingManifest(BaseModel):
    """Plugin directory exists but contains no ``plugin.yaml``."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["missing_manifest"] = "missing_manifest"
    plugin: PluginId


class SchemaViolation(BaseModel):
    """``plugin.yaml`` failed :meth:`PluginManifest.from_yaml`.

    ``detail`` is the rendered field-error string from the underlying
    Pydantic ``ValidationError`` (or the chokepoint's malformed-YAML
    message). The detail is operator-facing diagnostic, never machine-parsed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["schema_violation"] = "schema_violation"
    plugin: PluginId
    detail: str


class UnlockedPlugin(BaseModel):
    """Manifest names a plugin not present in ``PLUGINS.lock``.

    ADR-0011 honest-framing: the lock is the canonical attestation of
    which plugin slugs the repo trusts. A plugin directory whose manifest
    name does not appear in the lock is structurally unverifiable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["unlocked_plugin"] = "unlocked_plugin"
    plugin: PluginId


class MissingPluginDirectory(BaseModel):
    """``PLUGINS.lock`` names a plugin whose directory is absent from disk."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["missing_plugin_directory"] = "missing_plugin_directory"
    plugin: PluginId


class PluginImportError(BaseModel):
    """``importlib.import_module(f"plugins.{slug}.api")`` raised.

    ``detail`` is the formatted ``repr(exc)`` of the originating exception —
    operator-facing only; the structural meaning is "Python could not load
    this plugin's entry module".
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["plugin_import_error"] = "plugin_import_error"
    plugin: PluginId
    detail: str


class SymlinkEscape(BaseModel):
    """The integrity walk encountered a symlink whose target lies outside
    the plugin directory (zip-slip-style escape).

    ``offending_path`` is the path as it appears in the walk (pre-resolve).
    Mirrors the in-codebase ``probes/deployment.py:178-195`` precedent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["symlink_escape"] = "symlink_escape"
    plugin: PluginId
    offending_path: Path


class LockFileMalformed(BaseModel):
    """``PLUGINS.lock`` is unreadable, non-object, or names non-PluginId /
    non-BlobDigest values.

    Surfaced through the loader's outer :data:`PluginRejected` return so the
    CLI maps it to exit code 4 alongside the per-plugin failure modes.
    ``plugin`` is a sentinel ``PluginId("<lockfile>")`` — there is no
    plugin associated with a malformed lock, but the variant shape is kept
    uniform so consumer-site ``match`` blocks read identically.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["lockfile_malformed"] = "lockfile_malformed"
    plugin: PluginId
    detail: str


PluginRejected: TypeAlias = Annotated[
    IntegrityMismatch
    | MissingManifest
    | SchemaViolation
    | UnlockedPlugin
    | MissingPluginDirectory
    | PluginImportError
    | SymlinkEscape
    | LockFileMalformed,
    Field(discriminator="kind"),
]
"""Tagged-union sum type over every loader failure mode (ADR-0010 §Decision 3).

Adding a variant: define a new ``BaseModel`` with its own ``kind`` literal,
extend the union here, and add one arm at every consumer-site ``match``
block. ``mypy --strict`` + the ``assert_never`` exhaustiveness gate at
consumer sites catches every drift.
"""


def exit_code_for_rejection(rejection: PluginRejected) -> Literal[4]:
    """Every :data:`PluginRejected` variant maps to exit code 4
    (Phase-3 ADR-0002 §Consequences).

    The function exists as a single import-site so the CLI / orchestrator
    (S6-04) cannot accidentally branch on the variant ``kind`` and assign a
    different exit code per failure mode. The signature's ``Literal[4]``
    return type makes the invariant a type-check failure if anyone later
    tries to widen it.
    """
    del rejection  # signature placeholder — the contract is per-class.
    return 4
