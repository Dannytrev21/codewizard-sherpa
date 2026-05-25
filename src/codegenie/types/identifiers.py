"""Kernel-tier identifier ``NewType``s — production ADR-0033 + Phase-3 ADR-0010.

Production ADR-0033 §3 names primitive-obsession on domain identifiers as a
review-blocker pattern. Each ``NewType`` below is a nominal type under
``mypy --strict`` (passing an :data:`IndexId` where a :data:`SkillId` is
expected is a type error); at runtime each is identity-to-``str`` (zero
overhead, full ``str`` interop). ``AttemptNumber`` is the lone ``int``-backed
member of the catalog (Phase-3 retry counter).

``PackageManager`` (the Phase 1 ADR-0013 closed-set Literal) is **defined
here**: ``codegenie.types`` is the kernel-tier home for every domain
identifier and closed-set enum, and leaf packages (``probes``, ``depgraph``,
``indices``) import it from this module — the reverse direction is forbidden
(ADR-0013 Amendment 2026-05-20, which broke a 28-module cold-start cycle).

The Phase-3 catalog (14 names) lands the kernel-tier types every Step-1+
story imports: plugin contract IDs, recipe + transform IDs, workflow / event
ULIDs, CVE IDs, package + branch + blob digest, registry URLs, and the
``SignalKind`` / ``PrimitiveName`` / ``TransformKind`` taxonomies the trust
scorer + recipe registry consume. Smart-constructor parsers live next door
at :mod:`codegenie.types.parsers`; ``ParseError`` lives at
:mod:`codegenie.types.errors`; the canonical ``Result`` sum type lives at
:mod:`codegenie.result` (Phase-2 S1-04 — never forked).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, Literal, NewType, TypeAlias

if TYPE_CHECKING:  # pragma: no cover — type-checker-only imports
    # Phase 7 S1-01 — forward refs for the S2-01 enums (lands
    # ``Layer`` / ``Ecosystem`` in ``codegenie.primitives.vuln_provenance.registry``).
    # Aliased to underscored names to break the symbol collision with the
    # Phase 3 ``Ecosystem`` Literal defined later in this module — the Phase 7
    # enum lives in a DIFFERENT module with DIFFERENT membership (ADR-0006).
    # These stay TYPE_CHECKING-guarded because both sides are type-only — no
    # runtime cycle exists (contrast the former runtime ``PackageManager``
    # re-export, removed in ADR-0013 Amendment 2026-05-20).
    from codegenie.primitives.vuln_provenance.registry import (  # noqa: F401
        Ecosystem as _PhVnEcosystem,
    )
    from codegenie.primitives.vuln_provenance.registry import (  # noqa: F401
        Layer as _PhVnLayer,
    )

# --- Phase-1 catalog (ADR-0013) -------------------------------------------

# Closed-set Node package-manager tag. Phase 1 ADR-0013 fixes the five values
# (yarn split into classic/berry for plugin dispatch). ADR-0013 Amendment
# 2026-05-20 moved the definition home here, so the kernel ``types`` package
# no longer depends on the ``probes`` leaf; ``probes`` / ``depgraph`` import
# this name FROM here. A ``Literal`` (closed set), not a ``NewType``.
PackageManager = Literal["bun", "pnpm", "yarn-classic", "yarn-berry", "npm"]

# --- Phase-2 catalog (5 + 3 amendments) -----------------------------------

IndexId = NewType("IndexId", str)
SkillId = NewType("SkillId", str)
TaskClassId = NewType("TaskClassId", str)
IndexName = NewType("IndexName", str)
# Probe identifier — landed alongside S1-04's TCCM model (which carries
# ``required_probes: list[ProbeId]``). Phase 0/1 did not ship a ProbeId
# newtype; S1-04 routes the kernel-tier addition through this module.
ProbeId = NewType("ProbeId", str)
# Programming-language identifier (S2-01). Phase 1 already detects languages
# as raw ``str`` (``RepoSnapshot.detected_languages``); S2-01 introduces the
# newtype so the kernel-side ``Skill.applies_to_languages`` is typed against
# accidental ``TaskClassId`` substitution (ADR-0033 §1 primitive-obsession).
Language = NewType("Language", str)
# Convention identifier — landed alongside S2-02's ``ConventionsCatalogLoader``.
ConventionId = NewType("ConventionId", str)

# --- Phase-3 catalog (14 new — S1-01) -------------------------------------

# Plugin contract IDs.
PluginId = NewType("PluginId", str)
RecipeId = NewType("RecipeId", str)
# BLAKE3-hex digest of a transform diff; arch §C4 (ADR-0010).
TransformId = NewType("TransformId", str)
# ULID — orchestrator workflow id; consumed by S1-04 ApplyContext + S6-04.
WorkflowId = NewType("WorkflowId", str)
# ULID — append-only event log entry id; S6-01 two-stream event log.
EventId = NewType("EventId", str)
# MITRE CVE ID; S5-04 lockfile recipes consume it as input.
CveId = NewType("CveId", str)
# npm ``<name>@<pinned-semver>`` package coordinate; S7-02 npm recipes.
PackageId = NewType("PackageId", str)
# Git branch name (lowercase, slash-allowed); S6-04 RemediationOrchestrator.
BranchName = NewType("BranchName", str)
# 64-char lowercase hex digest (algorithm-agnostic at the type level).
BlobDigest = NewType("BlobDigest", str)
# Strict-``https://`` ASCII registry URL; ADR-0001 RegistryAllowlist.
RegistryUrl = NewType("RegistryUrl", str)
# snake-case open-registry signal name; S6-02 trust scorer.
SignalKind = NewType("SignalKind", str)
# snake-case open-registry primitive name; S4-05 capabilities catalog.
PrimitiveName = NewType("PrimitiveName", str)
# snake-case open-registry transform kind; S5-01 recipe registry.
TransformKind = NewType("TransformKind", str)
# Bounded retry counter (1..1024); S1-04 AttemptSummary.attempt.
AttemptNumber = NewType("AttemptNumber", int)
# Dotted snake-case error identifier (``^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$``,
# Phase-1 ADR-0007 warning/error-ID format). Carried by ``RecipeError`` and
# ``RemediationError`` on the ``Failed`` variants in S1-03's outcomes module.
ErrorId = NewType("ErrorId", str)

# --- Phase-3 catalog (S3-02 additive — VulnIndex) -------------------------

# Bare npm package name (scoped or unscoped, no ``@<version>``); S3-02
# VulnIndex lookup key. S1-01's ``PackageId`` (``<name>@<pinned-semver>``)
# does not fit per-name-across-versions vuln semantics — this newtype is the
# additive companion to ``PackageId`` at the kernel-tier identifier home.
PackageName = NewType("PackageName", str)

# Closed-set ecosystem tag — Phase-3 ships ``npm``; the remaining four are
# admitted by ADR amendment when their plugin scaffold lands (mirrors the
# ``severity`` / ``source`` Literal-discipline on ``VulnerabilityRecord``).
Ecosystem = Literal["npm", "pypi", "maven", "rubygems", "gomod"]

# --- Phase-3 catalog (S3-03 additive — semver parsing boundary) -----------

# Canonical semver-2.0.0 version string. The smart constructor
# :func:`codegenie.types.parsers.parse_semver` is the only sanctioned way to
# build a :data:`SemverVersion` from external input. S3-03's CVE-feed
# parsers route ``AffectedRange.introduced / fixed / last_affected`` through
# it at the ingest boundary. Production ADR-0033 §1 (primitive obsession)
# names version strings explicitly as a "review-blocker" raw-``str`` site.
SemverVersion = NewType("SemverVersion", str)

# --- Phase-3 catalog (S3-05 additive — Bundle cache key) ------------------

# ``"blake3:<64-hex>"`` Bundle cache key (S3-05). The smart constructor
# :func:`codegenie.plugins.cache.compose_bundle_cache_key` is the only
# sanctioned way to build a :data:`BundleCacheKey` value — direct
# ``BundleCacheKey(...)`` construction outside the composer is forbidden
# by an AST chokepoint test (story S3-05 §AC-4 + DP-D). Rule-of-three
# (composer + ``BundleCacheStore.put`` + ``BundleCacheStore.get``) met.
BundleCacheKey = NewType("BundleCacheKey", str)

# --- Phase-4 catalog (S1-01 — LLM fallback + solved-example RAG) ----------

# BLAKE3 hex of canonical solved-example YAML. S4-04 owns canonical records.
SolvedExampleId = NewType("SolvedExampleId", str)
# Kernel-tier vector carrier. Shape/dtype validation belongs to S4-01's embedder.
EmbeddingVector = NewType("EmbeddingVector", tuple)  # type: ignore[type-arg]
# BLAKE3 digest of the embedded Chroma/YAML store state. S4-03/S4-04 consume.
StoreDigest = NewType("StoreDigest", str)
# Cosine similarity score in [-1.0, 1.0]. S5-02 consumes as threshold input.
Similarity = NewType("Similarity", float)
# Provider/model slug such as ``claude-sonnet-4-5-20250929``. S3-02 consumes.
ModelId = NewType("ModelId", str)
# Non-negative bounded token count. S2-05 budget guard consumes.
TokenCount = NewType("TokenCount", int)
# Provider response identifier. Constructed by S3-02's Anthropic adapter.
LeafResponseId = NewType("LeafResponseId", str)
# UUID4 budget capability identifier. S2-05 consumes.
BudgetTokenId = NewType("BudgetTokenId", str)
# Cassette lock relpath key. Constructed by S3-04/S3-05 cassette discipline.
CassetteId = NewType("CassetteId", str)
# 16-byte lowercase hex canary nonce. S2-03 consumes.
HexNonce = NewType("HexNonce", str)
# BLAKE3-rolled manifest chain head. S4-04/S4-05 consume.
ChainHead = NewType("ChainHead", str)

# --- Phase-6 catalog (S1-01 — VulnRemediationSut contract substrate) ------

# ULID identifying a single vulnerability-remediation case the bench harness
# feeds the SUT. Smart constructor :func:`codegenie.types.parsers.parse_vuln_case_id`.
# Phase 6 ADR-0001 + production ADR-0010.
VulnCaseId = NewType("VulnCaseId", str)

# Name of a repo fixture (NOT a path) — ``^[a-z][a-z0-9_-]*$``, ≤ 128 chars.
# The harness resolves the name to a working-tree path; the SUT receives only
# the reference. Phase 6 ADR-0001 + production ADR-0010.
RepoFixtureRef = NewType("RepoFixtureRef", str)

# ``blake3:<64 lowercase hex>`` digest of a SUT's stable behaviour. Phase 9
# S4-05 G5 conformance later asserts ``LocalVulnRemediationSut.digest()`` and
# ``TemporalVulnRemediationSut.digest()`` produce byte-identical output for
# byte-identical input — the pure helper that computes this digest lives in
# :mod:`codegenie.workflows.vuln_sut`. Phase 6 ADR-0001 + production ADR-0010.
SutDigest = NewType("SutDigest", str)

# --- Phase-6 catalog (S1-02 — Ledger state union + transition event) ------

# ULID (26-char Crockford base32) identifying a single ledger transition
# event. Distinct from ``EventId`` (the Phase-3 two-stream forensic event
# log id): ``TransitionId`` is chained for replay-determinism via
# :func:`codegenie.workflows._chain._compute_chain_head` and consumed by the
# Phase-6 S2-01 checkpoint store + S2-02 replay verifier. Conflating with
# ``EventId`` would couple the replay path to the forensic-log path and
# break the Phase-9 S4-05 substrate-portability story.
# Phase 6 ADR-0001 + Phase 6 ADR-0003 + production ADR-0010.
TransitionId = NewType("TransitionId", str)

# --- Phase-7 catalog (S1-01) ----------------------------------------------

# OCI image reference (``registry/name[:tag]`` or ``name[:tag]``). The smart
# constructor :func:`codegenie.types.parsers.parse_image_ref` is a tight
# floor — non-empty, ≤ 256 chars, no whitespace, no C0/DEL controls, at most
# one ``:`` (and the tag must be non-empty when ``:`` is present). Full
# Distribution-spec validation is a deferred follow-up. Consumed by the
# Phase 7 ``BaseImageStage.ref`` and Dockerfile recipes (ADR-0004).
ImageRef = NewType("ImageRef", str)

# OCI image content digest. ``sha256:<64 lowercase hex>`` — the ``sha256:``
# prefix is asserted by the smart constructor (load-bearing per ADR-0004 +
# ADR-0006). Other algorithms (sha512, blake3, ...) require an additive
# ADR amendment, not a parser tweak. Carried by the ``BaseImage`` variant
# of the Phase 7 ``Provenance`` discriminated union + ``BaseImageStage.digest``.
ImageDigest = NewType("ImageDigest", str)

# OCI layer content digest. Same grammar as :data:`ImageDigest` but the
# semantic difference is provenance: a layer is one slice of an image. The
# smart constructor instantiates a separate ``_layer_digest_match`` closure
# so error messages name the correct newtype (ADR-0004 + SyftSbom layer
# attribution).
LayerDigest = NewType("LayerDigest", str)

# Runtime identifier — ``^[a-z][a-z0-9_-]{0,63}$``. Examples: ``node20``,
# ``python3-11``, ``openjdk21``. Lowercase only. Consumed by the
# ``RuntimeBundled`` variant of the Phase 7 ``Provenance`` union and the
# runtime-bundled adapter (ADR-0004).
RuntimeId = NewType("RuntimeId", str)

# Dockerfile ``AS <stage>`` name — ``^[a-z][a-z0-9_-]{0,63}$`` per BuildKit's
# stage-name normalisation. Leading digit + uppercase rejected. Consumed by
# ``BaseImageStage.name`` and Dockerfile recipes (ADR-0004).
DockerStageName = NewType("DockerStageName", str)

# Phase 7 provenance-adapter registry key. The arch + ADR-0006 specify
# ``tuple[Layer, Ecosystem]``; ``NewType`` over a generic tuple is unsupported
# in mypy --strict, so this is a ``TypeAlias`` with TYPE_CHECKING-guarded
# forward references (the real enums land in S2-01 inside
# ``codegenie.primitives.vuln_provenance.registry``). The underscored
# ``_PhVnLayer`` / ``_PhVnEcosystem`` aliases above keep the Phase 7
# ``Ecosystem`` Enum distinct from the Phase 3 ``Ecosystem`` Literal also
# defined in this module (Validator AC-11 sentinel — fail loud, Rule 12).
ProvenanceAdapterId: TypeAlias = tuple["_PhVnLayer", "_PhVnEcosystem"]


__all__ = [
    "AttemptNumber",
    "BlobDigest",
    "BranchName",
    "BudgetTokenId",
    "BundleCacheKey",
    "CassetteId",
    "ChainHead",
    "ConventionId",
    "CveId",
    "DockerStageName",
    "Ecosystem",
    "EmbeddingVector",
    "ErrorId",
    "EventId",
    "HexNonce",
    "ImageDigest",
    "ImageRef",
    "IndexId",
    "IndexName",
    "Language",
    "LayerDigest",
    "LeafResponseId",
    "ModelId",
    "PackageId",
    "PackageManager",
    "PackageName",
    "PluginId",
    "PrimitiveName",
    "ProbeId",
    "ProvenanceAdapterId",
    "RecipeId",
    "RegistryUrl",
    "RepoFixtureRef",
    "RuntimeId",
    "SemverVersion",
    "SignalKind",
    "Similarity",
    "SkillId",
    "SolvedExampleId",
    "StoreDigest",
    "SutDigest",
    "TaskClassId",
    "TokenCount",
    "TransformId",
    "TransformKind",
    "TransitionId",
    "VulnCaseId",
    "WorkflowId",
]


# AC-15 — machine-verifiable docstring registry. Every public name in
# ``__all__`` maps to a one-line docstring naming ADR-0010 and (for Phase-3
# additions) the consuming story / arch component. The test in
# ``tests/unit/types/test_identifiers_phase3.py::test_newtype_registry_matches_all``
# fences this against drift.
_NEWTYPE_REGISTRY: Final[Mapping[str, str]] = {
    # Phase-2 carryover (ADR-0033 § primitive-obsession).
    "IndexId": "Phase-2 index id (ADR-0010 lineage; ADR-0033).",
    "SkillId": "Phase-2 skill id (ADR-0010 lineage; ADR-0033).",
    "TaskClassId": "Phase-2 task-class id (ADR-0010 lineage; ADR-0033).",
    "IndexName": "Phase-2 index name (ADR-0010 lineage; ADR-0033).",
    "ProbeId": "Phase-2 probe id (ADR-0010 lineage; ADR-0033).",
    "Language": "Phase-2 programming-language id (ADR-0010 lineage; ADR-0033).",
    "ConventionId": "Phase-2 convention id (ADR-0010 lineage; ADR-0033).",
    "PackageManager": (
        "Phase-1 package-manager Literal (ADR-0013 + Amendment 2026-05-20; ADR-0010 §catalogue)."
    ),
    # Phase-3 (S1-01).
    "PluginId": "Phase-3 plugin id (ADR-0010); S2-01 PluginRegistry key.",
    "RecipeId": "Phase-3 recipe id (ADR-0010); S5-01 RecipeRegistry key.",
    "TransformId": "Phase-3 transform id (ADR-0010); arch §C4 BLAKE3 diff digest.",
    "WorkflowId": "Phase-3 workflow ULID (ADR-0010); arch §C5 ApplyContext.",
    "EventId": "Phase-3 event ULID (ADR-0010); S6-01 two-stream event log.",
    "CveId": "Phase-3 MITRE CVE id (ADR-0010); S5-04 lockfile recipe input.",
    "PackageId": "Phase-3 npm coordinate (ADR-0010); S7-02 npm recipes.",
    "BranchName": "Phase-3 branch name (ADR-0010); S6-04 orchestrator branch.",
    "BlobDigest": "Phase-3 64-hex blob digest (ADR-0010); arch §C4 cache key.",
    "RegistryUrl": "Phase-3 strict-https registry URL (ADR-0010); ADR-0001 allowlist.",
    "SignalKind": "Phase-3 trust signal kind (ADR-0010); S6-02 scorer registry.",
    "PrimitiveName": "Phase-3 sandbox primitive (ADR-0010); S4-05 capabilities.",
    "TransformKind": "Phase-3 transform kind (ADR-0010); S5-01 recipe registry.",
    "AttemptNumber": "Phase-3 retry counter (ADR-0010); S1-04 AttemptSummary.",
    "ErrorId": "Phase-3 dotted snake-case error id (ADR-0010); S1-03 RecipeError/RemediationError.",
    # Phase-3 (S3-02 — VulnIndex additive).
    "PackageName": (
        "Phase-3 bare npm package name (ADR-0010, ADR-0033); S3-02 VulnIndex lookup key."
    ),
    "Ecosystem": (
        "Phase-3 closed-set ecosystem tag (ADR-0010); S3-02 VulnIndex.lookup ecosystem filter."
    ),
    # Phase-3 (S3-03 — CVE-feed ingest additive).
    "SemverVersion": (
        "Phase-3 semver-2.0.0 version string (ADR-0010, ADR-0033); "
        "S3-03 AffectedRange parse boundary."
    ),
    # Phase-3 (S3-05 — Bundle cache key additive).
    "BundleCacheKey": (
        "Phase-3 ``blake3:<64-hex>`` Bundle cache key (ADR-0010); "
        "S3-05 smart-constructed via ``compose_bundle_cache_key``."
    ),
    # Phase-4 (S1-01 — LLM fallback + solved-example RAG).
    "SolvedExampleId": "Phase-4 solved-example YAML id (ADR-0016); S4-04 canonical record key.",
    "EmbeddingVector": (
        "Phase-4 embedding vector carrier (ADR-0007); S4-01 validates BGE-small shape."
    ),
    "StoreDigest": "Phase-4 RAG store digest (ADR-0016); S4-03/S4-04 store verification.",
    "Similarity": "Phase-4 cosine similarity score (ADR-0008); S5-02 threshold classifier.",
    "ModelId": "Phase-4 provider model id (ADR-0005); S3-02 Anthropic adapter.",
    "TokenCount": "Phase-4 token-count budget primitive (ADR-0010); S2-05 budget guard.",
    "LeafResponseId": "Phase-4 leaf LLM response id (ADR-0005); S3-02 adapter boundary.",
    "BudgetTokenId": "Phase-4 budget token id (ADR-0010); S2-05 capability issuer.",
    "CassetteId": "Phase-4 cassette lock id (ADR-0014); S3-04/S3-05 cassette discipline.",
    "HexNonce": "Phase-4 canary nonce (ADR-0013); S2-03 injection guard.",
    "ChainHead": "Phase-4 manifest chain head (ADR-0016); S4-04/S4-05 provenance verify.",
    # Phase-7 (S1-01 — vuln.provenance newtype catalog).
    "ImageRef": "Phase-7 OCI image reference (ADR-0004); BaseImageStage.ref + Dockerfile recipes.",
    "ImageDigest": (
        "Phase-7 sha256:<64-hex> image digest (ADR-0004 + ADR-0006); "
        "BaseImage variant + BaseImageStage.digest."
    ),
    "LayerDigest": (
        "Phase-7 sha256:<64-hex> OCI layer digest (ADR-0004); "
        "BaseImage variant + SyftSbom layer-attribution."
    ),
    "RuntimeId": (
        "Phase-7 runtime identifier (ADR-0004); RuntimeBundled variant + runtime-bundled adapter."
    ),
    "DockerStageName": (
        "Phase-7 Dockerfile AS-stage name (ADR-0004); BaseImageStage.name + Dockerfile recipes."
    ),
    # Phase-6 (S1-01 — VulnRemediationSut contract substrate).
    "VulnCaseId": (
        "Phase-6 vulnerability-remediation case ULID (ADR-0010 + Phase-6 ADR-0001); "
        "VulnRemediationCase.case_id."
    ),
    "RepoFixtureRef": (
        "Phase-6 named repo-fixture reference (ADR-0010 + Phase-6 ADR-0001); "
        "VulnRemediationCase.repo_fixture — name, never an absolute path."
    ),
    "SutDigest": (
        "Phase-6 ``blake3:<64-hex>`` SUT digest (ADR-0010 + Phase-6 ADR-0001); "
        "Phase-9 S4-05 G5 byte-equality substrate across Local/Temporal SUTs."
    ),
    # Phase-6 (S1-02 — Ledger state union + transition event).
    "TransitionId": (
        "Phase-6 ULID per ledger transition event (ADR-0010 + Phase-6 ADR-0001 + "
        "Phase-6 ADR-0003); chained for replay-determinism via "
        "``codegenie.workflows._chain._compute_chain_head``."
    ),
}
