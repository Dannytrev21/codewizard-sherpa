# Validation report — S3-02 `VulnIndex` sqlite schema + Alembic migrations + staleness signal

**Story:** [`docs/phases/03-vuln-deterministic-recipe/stories/S3-02-vuln-index-sqlite.md`](../S3-02-vuln-index-sqlite.md)
**Date:** 2026-05-18
**Verdict:** **HARDENED**
**Validator:** `/phase-story-validator` skill (Opus 4.7)

## Context brief

S3-02 ships the sqlite-backed `VulnIndex` (`lookup`, `affecting_range`, `digest`, `is_stale`) plus the Alembic migration substrate plus the `StaleVulnIndex` staleness predicate. Three downstream consumers depend on the surface: S3-04 (`BundleBuilder` cache key — `vuln_index.digest` is the load-bearing input per ADR-0008), S3-03 (`vuln-index refresh` CLI — uses the schema + `_raw_*` seams), S6-04 (`RemediationOrchestrator` startup — reads `is_stale()` and emits the `WorkflowSpanningEvent` per ADR-0005). The story is the supporting C11 component in the phase architecture.

Two structural collisions surfaced immediately on the first read against S1-01 HARDENED:

1. `BlobDigest` grammar (`^[0-9a-f]{64}$`, no prefix) vs. the story returning `BlobDigest("blake3:" + 64-hex)`.
2. `PackageId` grammar (`<name>@<pinned-semver>`) vs. the story's `lookup(package: PackageId, ...)` semantics — vulnerability lookups are per package NAME across all versions, not per pinned name@version.

Both collisions originate in arch §C11 pseudo-code that pre-dates the S1-01 HARDENED resolutions. The story inherited the arch shapes without reconciling against S1-01's tighter grammars. Synthesis fixes both by adding `PackageName` + `Ecosystem` to `codegenie.types.identifiers` (additive extension, mirroring the precedent set by S2-02 adding `ConventionId` and S1-04 adding `ProbeId`) and by stripping the `blake3:` prefix at the `digest()` boundary so the return value parses cleanly through `parse_blob_digest`.

## Stage 2 — four critics (parallel)

Critics ran in parallel as `general-purpose` subagents. Findings tagged `block` / `harden` / `nit`.

### Coverage critic — 6 block, 11 harden, 4 nit

| # | Tag | Issue |
|---|---|---|
| F1 | block | `lookup(package: PackageId, ...)` collides with S1-01's `<name>@<pinned-semver>` grammar — VulnIndex lookups need package name, not name+version |
| F2 | block | `digest()` returns `BlobDigest("blake3:" + 64-hex)` — fails S1-01's `^[0-9a-f]{64}$` grammar |
| F3 | block | "TDD red test exists, committed, green" AC is tautological |
| F4 | block | No AC for connection lifecycle (`close()`, context manager); sqlite3 fd leaks |
| F5 | block | `is_stale` couples env-read + predicate — must be split for testable functional core |
| F6 | block | Unique constraint `(cve_id, ecosystem, package, introduced)` is wrong; multiple `AffectedRange` entries can share `introduced` with different `fixed` |
| F7 | harden | `AffectedRange.introduced/fixed/last_affected: str` accepts non-semver strings |
| F8 | harden | Empty-DB digest "stable constant" claim has no AC pinning the literal |
| F9 | harden | `is_stale` edge cases missing: mtime-in-future (clock skew), TOCTOU between `exists()` and `stat()` |
| F10 | harden | Env-var boundary cases missing: float, whitespace, `"+7"`, leading zeros |
| F11 | harden | `StaleVulnIndex` payload not round-tripped through `WorkflowSpanningEvent.model_validate` |
| F12 | harden | Bench fixture `seeded_10k_index` undefined; row shape not pinned |
| F13 | harden | No WAL concurrency AC (reader-not-blocked-by-writer smoke test) |
| F14 | harden | `alembic_upgrade` fixture path ambiguous (subprocess vs in-process) |
| F15 | harden | `alembic upgrade head` idempotency on already-migrated DB unverified |
| F16 | harden | `_raw_insert` / `_raw_set_meta` test-seam exports leak across modules |
| F17 | harden | `raw_payload BLOB` has no size cap (500MB malformed feed entry would land in DB) |
| F18 | nit | `published_at TEXT` ISO 8601 format not validated at Pydantic boundary |
| F19 | nit | `fixed` and `last_affected` relationship undocumented (mutually exclusive? both?) |
| F20 | nit | `Ecosystem` enum vs `Literal` shape inconsistency with `severity`/`source` |
| F21 | nit | `StaleVulnIndex` event_type literal location should be `WorkflowSpanningEvent.event_type` membership check, not string equality |

### Test-Quality critic — 7 block, 9 harden, 3 nit

| Item | Tag | Issue |
|---|---|---|
| TQ-B1 | block | `test_lookup_returns_records_for_matching_package` seeds ONE record — "ignore filter" mutant passes |
| TQ-B2 | block | `test_lookup_sorts_severity_desc_then_published_desc` body is literal `...` — stub, not test |
| TQ-B3 | block | `test_affecting_range_missing_cve_raises_typed_error` reads `exc.value.reason` — contradicts markers-only `CodegenieError` discipline (S3-01 precedent) |
| TQ-B4 | block | `test_affecting_range_returns_first_match` is single-row mutation-blind |
| TQ-B5 | block | Sort tiebreaker undefined → flaky cache-key digests downstream |
| TQ-B6 | block | Bench test references undefined `seeded_10k_index` fixture |
| TQ-B7 | block | Ingest idempotency untested (echo of F6) |
| TQ-H1 | harden | Empty-DB digest stable-constant test missing (echo F8) |
| TQ-H2 | harden | Staleness boundary (`>` vs `>=`) untested |
| TQ-H3 | harden | `VulnIndexConfigError.reason` not pinned in rejection tests |
| TQ-H4 | harden | `test_composite_index_present` doesn't pin column order or `EXPLAIN QUERY PLAN` usage |
| TQ-H5 | harden | Unique-constraint enforcement untested (gated on F6 resolution) |
| TQ-H6 | harden | No property test for staleness predicate (off-by-one survives) |
| TQ-H7 | harden | No AST-fence test for raw `blake3` import (ADR-0001 chokepoint) |
| TQ-H8 | harden | No round-trip property test (insert → lookup) |
| TQ-H9 | harden | `_raw_insert` doesn't reject non-Pydantic input |
| TQ-N1 | nit | Subsumed by TQ-B1 |
| TQ-N2 | nit | `test_default_max_age_is_seven_days` could be parametrized |
| TQ-N3 | nit | `PRAGMA journal_mode=WAL` actually-applied untested |

### Consistency critic — 2 block, 3 harden, 3 nit

| Item | Tag | Issue |
|---|---|---|
| C1 | **BLOCK** | **`BlobDigest` grammar contradiction with S1-01 HARDENED** — `"blake3:" + hex` is 71 chars, fails `^[0-9a-f]{64}$` |
| C2 | **BLOCK** | **`Ecosystem` newtype ownership** — story Reference says "surface to S1-01" but Outline declares locally; S1-01 shipped without `Ecosystem` |
| C3 | harden | `PackageId` lookup semantic mismatch (echo Coverage F1) |
| C4 | harden | `is_stale` threshold direction: impl plan says `>`, story AC implied `>=` — undefined |
| C5 | harden | `StaleVulnIndex.event_type` literal must round-trip via `WorkflowSpanningEvent` discriminator |
| C6 | nit | `digest()` joiner shape (`\x1f`) ambiguous — `content_hash_bytes` vs `content_hash_strings` |
| C7 | nit | `alembic` runtime-vs-dev dep not pinned |
| C8 | nit | No-event-emission-inside-VulnIndex contract not made explicit |

### Design-Patterns critic — 3 harden tier 1, 3 harden tier 2, 5 nit

| Item | Tag | Issue |
|---|---|---|
| DP1 | harden(1) | `VulnIndexLookupError` / `VulnIndexConfigError` declared markers-only but used with typed `.reason` — mirror S3-01's `TCCMParseError` resolution (frozen Pydantic BaseModel with `Literal` reason) |
| DP2 | harden(1) | `alembic` not lazy-imported — cold-start budget regression risk |
| DP3 | harden(1) | Alembic invocation path not pinned (in-process vs subprocess) |
| DP4 | harden(2) | `severity` / `source` `Literal` vs `Ecosystem` `Enum` shape inconsistency |
| DP5 | harden(2) | `is_stale` env coupling — extract `_max_age_seconds(env)` with injection seam |
| DP6 | harden(2) | `_raw_*` exports hygiene — keep out of `__all__` |
| DP7 | nit | `VulnIndex` Protocol/ABC — defer to Phase 8 (rule-of-three not crossed) |
| DP8 | nit | `SemverVersion` newtype — defer to S3-03 (ingest is the boundary) |
| DP9 | nit | `raw_payload` size cap — defer to S3-03 |
| DP10 | nit | Context-manager pattern — flag in Notes, not AC |
| DP11 | nit | Pin empty-DB digest constant (echo TQ-H1) |

## Stage 3 — researcher

**Not invoked.** Every required pattern is established in-repo:

- Frozen Pydantic `BaseModel` errors with `Literal` reason — S3-01 `TCCMParseError` resolution.
- Lazy-import inside function — `src/codegenie/hashing.py` `from blake3 import blake3 as _blake3` pattern.
- AST-walk fence test — `tests/unit/probes/layer_b/test_node_reflection.py` precedent.
- Newtype + smart constructor — S1-01 (`PackageId`, `BlobDigest`, etc.) and the additive-extension precedent (S2-02 `ConventionId`, S1-04 `ProbeId` adding to `identifiers.py`).
- Property tests via Hypothesis — Phase 2 throughout, S1-01 round-trip tests.
- `EXPLAIN QUERY PLAN` index-usage assertion — standard sqlite pattern; no research required.

No `NEEDS RESEARCH` tags. Synthesizer applied in-repo precedents directly.

## Stage 4 — synthesis + edits

### Conflict resolution (precedence: Consistency > Coverage > Test-Quality > Design-Patterns)

- **C1 (Consistency BLOCK — BlobDigest grammar):** Resolved by **stripping the `blake3:` prefix** at the `digest()` boundary. The returned value is `BlobDigest(<64-hex>)`, matching `parse_blob_digest`. Notes document that downstream consumers needing the prefixed form (e.g., the BundleBuilder cache-key concat per ADR-0008) prepend it explicitly. This preserves S1-01's invariant without re-opening the shipped grammar. AC-D5 + AC-H1 codify; TDD plan `test_digest_roundtrips_through_parse_blob_digest` enforces.
- **C2 (Consistency BLOCK — Ecosystem ownership):** Resolved by **adding `Ecosystem` and `PackageName` to `src/codegenie/types/identifiers.py`** as an additive extension within S3-02 (mirroring the S2-02 `ConventionId` + S1-04 `ProbeId` precedent — `identifiers.py` is the additive boundary for kernel-tier types, not S1-01-only). `Ecosystem` lands as a `Literal["npm", "pypi", "maven", "rubygems", "gomod"]` plus a smart constructor `parse_ecosystem(s)` for shape parity with `severity` / `source` (DP4 resolution). `PackageName = NewType("PackageName", str)` with `parse_package_name(s)` grammar `^(?:@[a-z0-9][a-z0-9_.-]*/)?[a-z0-9][a-z0-9_.-]*$` (npm scoped + unscoped, no version). AC-B1 codifies. The story's References block is rewritten — `identifiers.py` accepts additive extensions, period. AC-L1 fence test asserts `PackageName` and `Ecosystem` live in `identifiers.py`, not in `vuln_index/models.py`.
- **F1 / C3 (PackageId vs PackageName):** Resolved by C2 — `VulnIndex.lookup(name: PackageName, ecosystem: Ecosystem)`. The `package TEXT` sqlite column holds the bare name. The story's TDD `seeded_index.lookup(PackageName("express"), ...)` is now type-correct under the smart constructor.
- **DP1 / TQ-B3 (error model contradiction):** `VulnIndexLookupError` and `VulnIndexConfigError` redesigned as **frozen Pydantic `BaseModel`s** with `reason: Literal[...]` and `details: dict[str, str | int] = {}`. Mirrors S3-01's `TCCMParseError` precedent. Note: these are RAISED via a thin wrapper `VulnIndexException(model: VulnIndexLookupError | VulnIndexConfigError)` so `pytest.raises` semantics work AND the typed model is preserved on `exc.value.model.reason`. AC-C1, C2 codify. TDD plan asserts `exc.value.model.reason == "cve_not_found"`.
- **F6 / TQ-B7 (unique constraint):** Resolved by changing the unique constraint to `(cve_id, ecosystem, package, introduced, fixed, last_affected)` — captures the full `AffectedRange` shape. Ingest semantics pinned: `INSERT OR IGNORE` (idempotent — re-ingest is a no-op). AC-D3, D4 codify.
- **DP2 (lazy-import alembic):** AC-E1 pins lazy-import inside `_upgrade()`; AC-L2 fence test asserts `import codegenie.vuln_index` does NOT load `alembic` (using `sys.modules` snapshot bookend pattern from production cold-start fence precedent).
- **DP3 (in-process Alembic only):** AC-E2 pins `alembic.command.upgrade(config, "head")` — no subprocess. Notes drop the `python -m alembic` alternative entirely.
- **F4 (connection lifecycle):** AC-E3 pins `close()` + `__enter__`/`__exit__`; AC-E4 pins post-close `lookup` raises `VulnIndexLookupError(reason="closed")`. Regression test exercises 1024 sequential `with VulnIndex(...)` blocks without fd exhaustion.
- **F5 / DP5 (functional core):** AC-I1 splits into pure `_is_stale_pure(now: float, mtime: float, max_age_seconds: int) -> bool` + impure `is_stale(*, now=None)` wrapper that reads env + stat. Tests exercise both. The pure function is reusable + cheap-to-test; the wrapper is exercised through the env-injection tests.
- **TQ-B1 / TQ-B2 / TQ-B4 / TQ-B5 (mutation-vulnerable tests):** Fixtures seed ≥3 records across `{(npm,express), (npm,lodash), (pypi,express)}` for selectivity. Sort test seeds 4 records `{critical/older, high/newer, high/older, medium/newer}` + a tiebreak pair → asserts EXACT order. Sort tiebreaker `cve_id ASC` pinned as AC-F4.
- **F9 (clock skew / TOCTOU):** AC-I3 pins `mtime > now → returns False`; `FileNotFoundError` between `exists()` and `stat()` → returns `False`.
- **F10 (env boundary cases):** AC-I4 enumerates the rejection corpus (`"7.5"`, `" 7 "`, `"+7"`, `"007"`, `"0"`, `"-1"`, `"not-an-int"`, `""`).
- **F11 / C5 (StaleVulnIndex payload contract):** AC-J1 pins the payload schema and round-trips via `WorkflowSpanningEvent.model_validate({"event_type": "stale_vuln_index", "payload": {...}, ...})`. Importing `WorkflowSpanningEvent` here is fine — ADR-0005 places it in `src/codegenie/plugins/events.py` (S6-01); pre-S6-01 story dependencies are honored: this AC is gated on S6-01 landing, so S3-02 ships the SHAPE today and the round-trip test is `@pytest.mark.skipif(not events_module_present)` until S6-01 lands. **Alternative pin (preferred):** the payload-shape test asserts the dict structure directly via a Pydantic `TypeAdapter[dict[str, str | int | bool | float | list[str]]].validate_python(payload)`, avoiding the S6-01 ordering coupling entirely.
- **F12 (bench fixture):** AC-K1 pins the 10k-row seed shape: `pkg-{i}` for `i in 0..9999` × 1 CVE each, all `Ecosystem.NPM`, severity round-robin. `seeded_10k_index` fixture lives in `tests/bench/vuln_index/conftest.py`.
- **F13 (WAL concurrency):** AC-E5 pins `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`. Test `test_wal_reader_not_blocked_by_writer` opens two connections; reader holds a SELECT; writer inserts; reader is not blocked.
- **F14 / F15 (alembic fixture + idempotency):** AC-E6 pins in-process call; AC-D6 pins re-upgrade idempotency.
- **F16 / DP6 (test-seam hygiene):** AC-A2 pins `__all__` excludes `_raw_*`. The seams stay as instance methods, not package exports.
- **F17 / DP9 (raw_payload cap):** Out-of-scope (S3-03 owns ingest); Notes pin the 256 KB cap for S3-03 to enforce. No schema-level CHECK in this story.
- **F7 / DP8 (semver validation):** Deferred to S3-03 (ingest is the parsing boundary); Notes pin: "tests in S3-02 must NOT seed obviously-malformed semvers — those are S3-03's rejection corpus."
- **TQ-H1 / DP11 (empty-DB digest constant):** AC-H2 pins the literal constant `BlobDigest("<64-hex>")` after first compute. Drift-fail-loud pattern.
- **TQ-H2 (boundary):** AC-I5 pins `>` vs `>=`. Resolution: **strict `>`** (matches High-level-impl.md verbatim "mtime > 7 days"). `test_is_stale_at_exact_threshold_returns_false` enforces.
- **TQ-H3:** rejection tests pin `exc.value.model.reason == "invalid_max_age"` / `"non_positive_max_age"`.
- **TQ-H4 (index-usage):** AC-D7 pins `PRAGMA index_info` + `EXPLAIN QUERY PLAN` assertions.
- **TQ-H5:** subsumed by F6 resolution.
- **TQ-H6 (property test):** AC-I6 adds Hypothesis property test over `(days, age_days)`.
- **TQ-H7 (AST fence):** AC-L3 adds `test_vuln_index_no_raw_blake3_import` AST walker (mirrors `test_node_reflection.py` precedent).
- **TQ-H8 (round-trip property):** AC-F5 adds insert-N → lookup-by-key property test.
- **TQ-H9:** AC-A3 pins `_raw_insert` raises `TypeError` on non-`VulnerabilityRecord` input.
- **C4 (threshold direction):** resolved as strict `>` (see TQ-H2).
- **F3 (tautological AC):** removed.
- **F18, F19, F20, F21:** elevated to ACs where they have observable consequences (F18 → `published_at: datetime` with Pydantic ISO 8601 coercion; F19 → docstring + test for `fixed`/`last_affected` independence; F21 → import-and-membership-check assertion).
- **DP7, DP8, DP10:** Notes for implementer only (rule-of-three not crossed; deferred to Phase 8 / S3-03).

### AC count

| Before | After |
|---|---|
| 16 unnumbered ACs (incl. 1 tautology) | 28 numbered ACs grouped under 11 sections (A package surface, B types, C errors, D schema + migrations, E connection lifecycle, F lookup, G affecting_range, H digest, I is_stale + env, J event payload, K bench, L module purity / cold-start, M gates) |

### Test count

| Before | After |
|---|---|
| 11 unit tests (1 with `...` body, 1 with undefined fixture, several mutation-blind), 1 bench | ~28 unit tests (parametrized; effective ≈ 50 cases), 2 Hypothesis property tests, 2 AST module-purity tests, 1 cold-start fence, 1 WAL concurrency smoke, 1 bench |

### Edits applied

| Section | Edit |
|---|---|
| Header | Status `Ready → HARDENED`; ADRs honored expanded with ADR-0010 (sum-type discipline), Phase 0 ADR-0001 (hashing chokepoint), production ADR-0005 (cold-start budget) |
| New `Validation notes` block | 11-bullet summary of changes for the implementer |
| References | Rewritten — `identifiers.py` accepts additive extensions; S1-01's catalog is informational, not exclusive |
| Goal | Tightened — `lookup` parameter type changed to `PackageName`; `digest()` returns `BlobDigest` matching S1-01 grammar |
| Acceptance criteria | Rewritten — 28 numbered ACs grouped into 13 sections |
| Implementation outline | Rewritten — pins `PackageName` + `Ecosystem` additive extension to `identifiers.py`; Pydantic error models with `Literal` reason; lazy-import alembic; pure `_is_stale_pure` + impure wrapper; `INSERT OR IGNORE` for idempotent ingest |
| TDD plan | Rewritten — 3 test files; parametrized selectivity seeds; exact sort + tiebreak assertions; round-trip property test; Hypothesis property test for staleness; AST source-scan for raw `blake3`; cold-start fence; WAL concurrency smoke test |
| Files to touch | Added `src/codegenie/types/identifiers.py` (modify), `tests/unit/vuln_index/test_module_purity.py`, `tests/unit/vuln_index/test_cold_start.py` |
| Out of scope | Tightened — semver validation, raw_payload size cap, Protocol/ABC abstraction all explicitly deferred to S3-03 / Phase 8 |
| Notes for implementer | Rewritten — documents the BlobDigest prefix-strip choice, the additive `identifiers.py` extension, the markers-only-vs-typed-error resolution mirroring S3-01, the lazy-import + in-process Alembic policy, the WAL concurrency expectation, and the deferred design opportunities (semver newtype to S3-03, Protocol abstraction to Phase 8, context-manager pattern as optional refinement) |

## Verdict

**HARDENED.** Story now:

- 28 individually verifiable ACs, every one mutation-resistant per the TDD plan.
- Two structural collisions with S1-01 resolved by surgical additive extension to `identifiers.py` (`PackageName`, `Ecosystem`) + prefix-strip at the `digest()` boundary — no shipped grammar touched.
- Error model aligned with S3-01's `TCCMParseError` precedent (frozen Pydantic BaseModel with `Literal` reason).
- Cold-start budget protected by lazy-import + AST fence test.
- Functional core / imperative shell honored — pure `_is_stale_pure` separated from env-reading wrapper.
- Mutation-vulnerable tests (single-row seeding, `...` stub bodies, tiebreaker omissions) rewritten with multi-record seeds + explicit ordering + Hypothesis property tests.
- Deferred design opportunities (semver newtype, Protocol abstraction, raw_payload size cap, context-manager pattern) recorded in Notes-for-implementer rather than fabricated as premature ACs today.
