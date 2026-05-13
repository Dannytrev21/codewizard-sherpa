"""Audit-record Pydantic models — Gap 2 closure (ADR-0004).

Two frozen, ``extra="forbid"`` models that downstream features key off without
extending:

- :class:`ProbeExecutionRecord` — one per probe per gather run. Carries the
  **dual audit anchors** that close Gap 2: ``cache_key`` (the SHA-256 identity
  tuple from :mod:`codegenie.hashing`) for the *what was asked*, and
  ``blob_sha256`` (SHA-256 of the *sanitized* blob bytes) for the *what was
  delivered*. Both are required so ``codegenie audit verify`` (S3-06 / S4-02)
  can recompute either anchor in isolation and pinpoint which side drifted.
- :class:`RunRecord` — one per gather invocation. Aggregates the per-probe
  records plus environment fingerprints. Phase 11's PR provenance and Phase
  13's cost ledger consume ``RunRecord`` directly; ``extra="forbid"`` keeps
  a rogue field from silently appearing in the JSON shape they parse.

The ``AuditWriter`` class (writing ``runs/<utc-iso>-<short>.json`` at mode
``0600``) is S3-06's job, not this story's. A stub is provided so callers
can ``from codegenie.audit import AuditWriter`` without an ``ImportError``,
but invoking it raises ``NotImplementedError`` pointing at the story that
ships the body.

Field-name precedence note: ``RunRecord.os_kernel_sha`` matches
``phase-arch-design.md §Data model`` (the canonical schema source). The
arch §Component design line spells this ``os_kernel``; the inconsistency
is logged in this story's validation notes as a follow-up arch correction.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProbeExecutionRecord(BaseModel):
    """One row in :class:`RunRecord.probes` — per-probe per-run audit anchor.

    The dual anchors are load-bearing: ``cache_key`` identifies *what the
    coordinator asked for* (SHA-256 over the identity tuple ``(name, version,
    schema_version, content_hash_of_inputs)``); ``blob_sha256`` identifies
    *what the coordinator received* (SHA-256 over the sanitized blob bytes
    after the two-pass sanitizer, ADR-0008). Recomputing either anchor in
    isolation reveals whether the cache lied, the sanitizer mutated bytes,
    or the producer was non-deterministic.

    When ``exit_status == "skipped"`` (the probe was filtered out before it
    ran), ``blob_sha256`` carries the empty-string sentinel ``""`` per
    ADR-0004 §Consequences — there is no blob to hash. The model accepts
    this; non-skipped statuses ship a real ``sha256:<64-hex>``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    cache_hit: bool
    wall_clock_ms: int
    exit_status: Literal["ok", "error", "timeout", "skipped"]
    cache_key: str
    blob_sha256: str


class RunRecord(BaseModel):
    """One gather-run audit record. Aggregates per-probe rows + environment.

    ``os_kernel_sha`` is the SHA-256 of ``uname -srv`` (or equivalent),
    *not* the raw kernel string — the canonical phrasing in
    ``phase-arch-design.md §Data model`` redacts host-identifying detail
    while keeping kernel-class differences attributable.

    ``yaml_sha256`` is the SHA-256 of the rendered
    ``.codegenie/context/repo-context.yaml`` bytes; it is the whole-output
    fingerprint S5-02's audit verify rebuilds and compares.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cli_version: str
    sherpa_commit: str
    python_version: str
    os_kernel_sha: str
    probes: list[ProbeExecutionRecord]
    tool_versions: dict[str, str]
    yaml_sha256: str


class AuditWriter:
    """Audit writer stub — body lives in S3-06.

    Provided so callers that ``import AuditWriter`` (and only construct, not
    invoke) don't ``ImportError`` against an in-flight Phase 0. Calling
    :meth:`record` before S3-06 lands fails loud per Rule 12.
    """

    def record(self, run: RunRecord) -> None:
        """Write ``run`` to ``<output_dir>/runs/<utc-iso>-<short>.json`` (S3-06)."""
        raise NotImplementedError("AuditWriter.record body is delivered by S3-06")
