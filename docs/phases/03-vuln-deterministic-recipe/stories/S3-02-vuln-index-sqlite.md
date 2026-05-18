# Story S3-02 — `VulnIndex` sqlite schema + Alembic migrations + staleness signal

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** HARDENED
**Effort:** M
**Depends on:** S3-01
**ADRs honored:** Phase 3 ADR-0008 (`vuln_index.digest` participates in Bundle cache key), Phase 3 ADR-0005 (two-stream `EventLog` — `StaleVulnIndex` is a spanning event), Phase 3 ADR-0010 (sum-type / newtype discipline), production ADR-0033 (newtype identifiers), Phase 0 ADR-0001 (BLAKE3 chokepoint via `codegenie.hashing`), production ADR-0005 (cold-start budget — no LLM-SDK in `--help` closure; analogously: no heavyweight import on `import codegenie.vuln_index`).

## Validation notes (2026-05-18 — phase-story-validator)

This story was hardened from `Ready` → `HARDENED`. Headline changes:

- **`BlobDigest` grammar reconciled with S1-01.** S1-01 HARDENED `parse_blob_digest` as `^[0-9a-f]{64}$` (no prefix). `digest()` now returns `BlobDigest(<64-hex>)` (no `"blake3:"` prefix); downstream consumers needing the algorithm-tagged form (BundleBuilder cache-key concat per ADR-0008) prepend the prefix explicitly.
- **`PackageName` + `Ecosystem` added to `codegenie.types.identifiers` as additive extension.** S1-01's `PackageId` grammar (`<name>@<pinned-semver>`) does not fit vulnerability-lookup semantics (per-name across versions). `PackageName` (bare npm package name, scoped or unscoped) and `Ecosystem` (closed `Literal[...]` + smart constructor) land in `identifiers.py` mirroring the S2-02 `ConventionId` and S1-04 `ProbeId` precedents — `identifiers.py` is the additive boundary for kernel-tier types.
- **`VulnIndexLookupError` / `VulnIndexConfigError` redesigned as frozen Pydantic `BaseModel`s.** S3-01's `TCCMParseError` resolution applies verbatim: markers-only error subclasses cannot carry `.reason` state; typed `Literal["..."]` reason + `details: dict[str, str | int] = {}` is the precedent.
- **`alembic` lazy-imported inside `_upgrade()`; cold-start fence test ships.** Mirrors `codegenie.hashing`'s `from blake3 import blake3 as _blake3` inside-function pattern.
- **Alembic invocation pinned to in-process** `alembic.command.upgrade(config, "head")` — no subprocess. Avoids `ALLOWED_BINARIES` amendment.
- **`is_stale` split into functional core + imperative shell.** Pure `_is_stale_pure(now, mtime, max_age_seconds) -> bool` + impure wrapper reads env + stats. Both tested directly.
- **Unique constraint corrected** to cover the full `AffectedRange` — `(cve_id, ecosystem, package, introduced, fixed, last_affected)`. Ingest semantics pinned: `INSERT OR IGNORE` (idempotent).
- **Connection lifecycle made explicit.** `close()` + context-manager protocol; post-close `lookup` raises typed error; 1024-open regression test.
- **Mutation-vulnerable tests rewritten.** Multi-record seeds spanning `{(npm,express), (npm,lodash), (pypi,express)}` for selectivity; sort test seeds 4 records + a tiebreak pair with exact-order assertion; round-trip property test added.
- **Sort tiebreaker pinned** to `cve_id ASC` for determinism (load-bearing for `digest()` stability under ties).
- **`_raw_insert` / `_raw_set_meta` test seams stay private** — kept off `__all__`; S3-03 accesses them via the class, not via package re-export.

See [`_validation/S3-02-vuln-index-sqlite.md`](_validation/S3-02-vuln-index-sqlite.md) for the full audit log.

## Context

`BundleBuilder` (S3-04) and the orchestrator (S6-04) need a fast `(name, ecosystem) → list[VulnerabilityRecord]` lookup with a content `digest()` that participates in the Bundle cache key (ADR-0008). A per-call JSON parse over the raw CVE feeds is 50–200 ms — over the 18 s p50 envelope this is unacceptable; sqlite with the right indexes lands at ~3 ms (`phase-arch-design.md §C11`). This story ships the schema, the `VulnIndex` class with three methods (`lookup`, `affecting_range`, `digest`), Alembic migrations as the migration substrate, AND the staleness signal: when the sqlite file's `mtime` exceeds `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS` (default `7`) at orchestrator init, a `StaleVulnIndex` spanning event is emitted (warn, NOT block — operators may run against a stale index intentionally).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C11 (supporting). VulnIndex` — interface, schema sketch, ~50 MB steady-state.
  - `../phase-arch-design.md §C9` — `WorkflowSpanningEvent` enum includes `stale_vuln_index`; this story exposes the predicate, S6-04 emits.
  - `../phase-arch-design.md §Edge cases E15` — staleness threshold "7 days mtime → warn (not block). Operator-configurable via `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`."
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Decision + §Consequences` — `vuln_index.digest()` is the load-bearing surface for Bundle cache-key correctness.
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — `StaleVulnIndex` lives on the workflow-spanning stream; `event_type: Literal[..., "stale_vuln_index", ...]`.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `Literal[...]`-typed reasons on error models.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — "sqlite `VulnIndex` (`lookup`, `affecting_range`, `digest`), Alembic migrations" + done criterion "`StaleVulnIndex` event emitted when `mtime > 7 days`".
- **Sibling validation:**
  - `_validation/S3-01-tccm-context-query-models.md` — the `TCCMParseError` redesign-as-Pydantic-BaseModel precedent applied here verbatim.
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — additive boundary for kernel-tier types. This story extends it with `PackageName` and `Ecosystem` (precedent: S2-02 added `ConventionId`, S1-04 added `ProbeId`).
  - `src/codegenie/hashing.py` — `content_hash_bytes` / `identity_hash` for `digest()` computation (do NOT import `blake3` directly — ADR-0001).
  - `src/codegenie/errors.py` — markers-only `CodegenieError` base. NOT used for the typed-`.reason` error models in this story (mirrors S3-01 resolution).
  - `tests/unit/probes/layer_b/test_node_reflection.py` — precedent for AST-walk module-purity fence tests.

## Goal

`codegenie.vuln_index.VulnIndex` exposes `lookup(name: PackageName, ecosystem: Ecosystem)`, `affecting_range(cve: CveId)`, and `digest() -> BlobDigest` against an indexed sqlite store; Alembic migrations seed and evolve the schema; `VulnIndex.is_stale()` (driven by `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`, default `7`) feeds the orchestrator's `StaleVulnIndex` emission decision at init. The returned `BlobDigest` conforms to S1-01's `^[0-9a-f]{64}$` grammar (no `blake3:` prefix). `PackageName` and `Ecosystem` land in `codegenie.types.identifiers` as additive extensions; both have smart constructors returning `Result[T, ParseError]`.

## Acceptance criteria

### A — Package surface

- [ ] **AC-A1** New package `src/codegenie/vuln_index/` with: `__init__.py` (exports), `index.py` (`VulnIndex`), `models.py` (`VulnerabilityRecord`, `AffectedRange`), `errors.py` (`VulnIndexLookupError`, `VulnIndexConfigError`, `VulnIndexException`), `migrations/` (Alembic env + initial revision).
- [ ] **AC-A2** `src/codegenie/vuln_index/__all__` exports exactly: `{VulnIndex, VulnerabilityRecord, AffectedRange, VulnIndexLookupError, VulnIndexConfigError, VulnIndexException}`. `_raw_insert` and `_raw_set_meta` are instance methods on `VulnIndex` but NOT in `__all__`.
- [ ] **AC-A3** `_raw_insert(record)` rejects non-`VulnerabilityRecord` arguments with `TypeError`; `_raw_set_meta(key, value)` rejects non-`str` arguments with `TypeError`. Test seams remain typed at the boundary.

### B — Domain types (newtypes + Pydantic models)

- [ ] **AC-B1** `src/codegenie/types/identifiers.py` extended (additive — does not edit existing definitions) with:
  - `PackageName = NewType("PackageName", str)` plus `parse_package_name(s) -> Result[PackageName, ParseError]` grammar `^(?:@[a-z0-9][a-z0-9_.-]*/)?[a-z0-9][a-z0-9_.-]*$` (npm scoped + unscoped; no `@version`).
  - `Ecosystem = Literal["npm", "pypi", "maven", "rubygems", "gomod"]` (closed; shape parity with `severity` and `source`) plus `parse_ecosystem(s) -> Result[Ecosystem, ParseError]`.
  - Both names appear in `__all__`; `_NEWTYPE_REGISTRY` for `PackageName` carries an `"ADR-0033"` citation in its docstring.
- [ ] **AC-B2** `VulnerabilityRecord` Pydantic `ConfigDict(frozen=True, extra="forbid")` with fields: `cve_id: CveId`, `ecosystem: Ecosystem`, `package: PackageName`, `affected_range: AffectedRange`, `severity: Literal["low", "medium", "high", "critical"]`, `published_at: datetime` (Pydantic coerces ISO 8601), `source: Literal["nvd", "ghsa", "osv"]`.
- [ ] **AC-B3** `AffectedRange` Pydantic `ConfigDict(frozen=True, extra="forbid")` with fields: `introduced: str`, `fixed: str | None`, `last_affected: str | None`. Docstring documents: `fixed` and `last_affected` are independent (patched line vs EOL'd line); both `None` ⇒ open vuln. Semver shape validation is S3-03's ingest concern; this story accepts non-empty strings only.
- [ ] **AC-B4** `VulnerabilityRecord.published_at` round-trips through the sqlite TEXT column preserving tz info (`datetime.now(timezone.utc)` in → `datetime` with `tzinfo=UTC` out).

### C — Error model

- [ ] **AC-C1** `VulnIndexLookupError` is a `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`, fields: `reason: Literal["cve_not_found", "closed"]`, `details: dict[str, str | int] = {}`. NOT a `CodegenieError` subclass.
- [ ] **AC-C2** `VulnIndexConfigError` is a `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")`, fields: `reason: Literal["invalid_max_age", "non_positive_max_age"]`, `details: dict[str, str | int] = {}`.
- [ ] **AC-C3** `VulnIndexException` is a thin `Exception` subclass with a single typed attribute `model: VulnIndexLookupError | VulnIndexConfigError`. Production call sites construct the Pydantic model then `raise VulnIndexException(model)`. Tests assert `exc.value.model.reason == "cve_not_found"` etc.
- [ ] **AC-C4** A mypy-strict snippet `VulnIndexLookupError(reason="typo", details={})` raises a `ValidationError` at runtime AND `mypy --strict` rejects the assignment (parametrized mypy meta-test mirrors S1-01's pattern).

### D — sqlite schema + Alembic migrations

- [ ] **AC-D1** Alembic initial revision `versions/0001_initial_schema.py` creates table `vulnerabilities` with columns: `id INTEGER PRIMARY KEY`, `cve_id TEXT NOT NULL`, `ecosystem TEXT NOT NULL`, `package TEXT NOT NULL`, `introduced TEXT NOT NULL`, `fixed TEXT`, `last_affected TEXT`, `severity TEXT NOT NULL`, `published_at TEXT NOT NULL`, `source TEXT NOT NULL`, `raw_payload BLOB NOT NULL`.
- [ ] **AC-D2** Composite index `idx_vuln_pkg_eco ON vulnerabilities(ecosystem, package)`. Column ORDER pinned: `(ecosystem, package)` — verified by `PRAGMA index_info('idx_vuln_pkg_eco')` returning `[(0, 'ecosystem'), (1, 'package')]`.
- [ ] **AC-D3** Unique constraint on `(cve_id, ecosystem, package, introduced, fixed, last_affected)` — covers the full `AffectedRange` shape; multiple non-overlapping ranges for the same CVE+package permitted.
- [ ] **AC-D4** Ingest semantics: `_raw_insert` uses `INSERT OR IGNORE` (idempotent — double-insert of an identical record is a no-op, row count unchanged).
- [ ] **AC-D5** Table `meta`: `key TEXT PRIMARY KEY`, `value TEXT NOT NULL` — holds `schema_version`, `last_refresh_ts`, `feed_digest_nvd`, `feed_digest_ghsa`, `feed_digest_osv`.
- [ ] **AC-D6** `alembic.command.upgrade(config, "head")` on a fresh sqlite produces the schema; re-running on an already-migrated DB is a no-op (revision unchanged, no errors).
- [ ] **AC-D7** `EXPLAIN QUERY PLAN SELECT ... FROM vulnerabilities WHERE ecosystem=? AND package=?` output contains `USING INDEX idx_vuln_pkg_eco` — pinned via test.

### E — Connection lifecycle + Alembic invocation

- [ ] **AC-E1** `import codegenie.vuln_index` does NOT load `alembic` into `sys.modules`. `alembic` is lazy-imported inside `_upgrade()` (mirrors `hashing.py`'s `from blake3 import blake3 as _blake3` inside-function pattern). Cold-start fence test enforces.
- [ ] **AC-E2** Alembic invocation pinned to `alembic.command.upgrade(config, "head")` in-process. The `alembic_upgrade(db)` test fixture calls this directly; no subprocess, no `python -m alembic` shell-out. `ALLOWED_BINARIES` is NOT amended for this story.
- [ ] **AC-E3** `VulnIndex` implements `close()` and the context-manager protocol (`__enter__`, `__exit__`). `close()` is idempotent (double-close is a no-op).
- [ ] **AC-E4** Post-`close()` calls to `lookup`, `affecting_range`, `digest`, `is_stale` raise `VulnIndexException(model=VulnIndexLookupError(reason="closed"))`.
- [ ] **AC-E5** On `__init__`, the sqlite connection sets `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`. A reader transaction is not blocked by a concurrent writer (WAL semantics smoke test).
- [ ] **AC-E6** Regression test opens 1024 sequential `with VulnIndex(db): ...` blocks without `OSError: Too many open files` — verifies fd lifecycle.

### F — `lookup` behavior

- [ ] **AC-F1** `VulnIndex.lookup(name: PackageName, ecosystem: Ecosystem) -> list[VulnerabilityRecord]` returns ALL records matching `(ecosystem, name)`, sorted `severity DESC, published_at DESC, cve_id ASC` (deterministic tiebreaker).
- [ ] **AC-F2** **Selectivity:** Given seeded records `{(npm,express), (npm,lodash), (pypi,express)}`, `lookup(PackageName("express"), "npm")` returns only the `(npm,express)` record; `(npm,lodash)` and `(pypi,express)` are excluded. Mutation-resistant against "ignore filter" / "filter by name only" / "filter by ecosystem only" implementations.
- [ ] **AC-F3** Missing-package lookup returns `[]` (NOT raises). Tested as a standalone case + paired with selectivity (#F2) so an "always-empty" mutant fails the selectivity test.
- [ ] **AC-F4** **Sort order:** Given seeded records `{critical/older, high/newer, high/older, medium/newer}` for `(npm, X)`, the returned `cve_id` sequence matches the explicit expected list. A second seed pair `{(critical, t0, "CVE-A"), (critical, t0, "CVE-B")}` (collision on severity+published_at) returns `[CVE-A, CVE-B]` (cve_id ASC tiebreak).
- [ ] **AC-F5** **Round-trip property test (Hypothesis):** Generate N random valid `VulnerabilityRecord`s; `_raw_insert` each; for each unique `(ecosystem, name)` lookup, assert the returned set equals the inserted subset partitioned by that key.

### G — `affecting_range` behavior

- [ ] **AC-G1** `affecting_range(cve: CveId) -> AffectedRange` returns the first matching row's `AffectedRange`, deterministic by `(package ASC, ecosystem ASC, introduced ASC)`. Test seeds CVE-A and CVE-B with distinct `fixed` versions; lookup by CVE-B returns CVE-B's range (verifies WHERE clause).
- [ ] **AC-G2** No-match raises `VulnIndexException(model=VulnIndexLookupError(reason="cve_not_found", details={"cve_id": str(cve)}))`. Test asserts `exc.value.model.reason == "cve_not_found"` AND `exc.value.model.details["cve_id"] == "CVE-9999-9999"`.

### H — `digest` shape + stability

- [ ] **AC-H1** `digest() -> BlobDigest` returns a `BlobDigest` matching S1-01's grammar `^[0-9a-f]{64}$` — 64 lowercase hex chars, NO `blake3:` prefix. Computed as `identity_hash` (or `content_hash_bytes`-derived equivalent stripped of prefix) over `meta.schema_version || \x1f || meta.feed_digest_nvd || \x1f || meta.feed_digest_ghsa || \x1f || meta.feed_digest_osv`. Test: `parse_blob_digest(idx.digest())` returns `Ok` (round-trip clean).
- [ ] **AC-H2** **Empty-DB digest is a pinned literal constant.** Fresh DB (post-`alembic upgrade head`, no `meta` rows) → `digest()` returns a specific `BlobDigest("<64-hex>")` literal hard-coded in the test (computed once, frozen). Drift in joiner or field order fails this test loudly.
- [ ] **AC-H3** `digest()` is deterministic across processes — calling from two distinct Python processes against an identical DB yields byte-identical output (subprocess-based test, mirrors S1-01's mypy meta-test pattern).
- [ ] **AC-H4** Changing any `feed_digest_*` meta value via `_raw_set_meta` changes `digest()` (covers all four meta inputs in a parametrized test).

### I — `is_stale` + env reader (functional core)

- [ ] **AC-I1** Pure helper `_is_stale_pure(now: float, mtime: float, max_age_seconds: int) -> bool` returns `True` iff `0 < (now - mtime) > max_age_seconds`. No I/O, no env access. Hypothesis property test covers `(days ∈ [1, 365], age_days ∈ [0, 730])`.
- [ ] **AC-I2** `VulnIndex.is_stale(*, now: float | None = None) -> bool` is the impure wrapper: reads `os.environ`, validates, stats the path, composes `_is_stale_pure`. Non-existent path → `False` (an empty index is "fresh" by convention).
- [ ] **AC-I3** **Clock-skew / TOCTOU:** if `mtime > now` (file is in the future — clock skew on NFS/shared FS), `is_stale` returns `False`. `FileNotFoundError` between `path.exists()` and `path.stat()` → `False`.
- [ ] **AC-I4** **Env validation rejection corpus** (parametrized): `{"not-an-int", "", " ", "7.5", "+7", "-1", "0", "007 "}` each raise `VulnIndexException(model=VulnIndexConfigError(reason="invalid_max_age" | "non_positive_max_age", details={"value": s}))`. `"0"` and `"-1"` map to `"non_positive_max_age"`; the rest map to `"invalid_max_age"`. `"7"`, `" 7 "` (post-strip), `"7\n"` (post-strip) accept as 7.
- [ ] **AC-I5** **Strict `>` boundary:** Setting `os.utime(db, (now - 7*86400, now - 7*86400))` with `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS=7` returns `False` (exactly at threshold is NOT stale; matches High-level-impl.md "mtime > 7 days").
- [ ] **AC-I6** **Default 7-day threshold:** With env var unset, an 8-day-old file is stale; a 6-day-old file is not.

### J — `StaleVulnIndex` event payload shape (contract for S6-04)

- [ ] **AC-J1** `VulnIndex.stale_payload() -> dict[str, str | int | bool | float | list[str]]` returns `{"path": str, "mtime_iso": str, "age_days": float, "threshold_days": int}`. Test validates the dict via `pydantic.TypeAdapter[dict[str, str | int | bool | float | list[str]]]` round-trip (no coupling to S6-01's `WorkflowSpanningEvent` import — S6-04 will compose the event using this payload). The event_type literal `"stale_vuln_index"` is exposed as `_STALE_VULN_INDEX_EVENT_TYPE: Final[Literal["stale_vuln_index"]] = "stale_vuln_index"` for downstream import.

### K — Bench (advisory)

- [ ] **AC-K1** `tests/bench/vuln_index/conftest.py` defines `seeded_10k_index`: 10k rows of `(npm, pkg-{i})` for `i in 0..9999`, severity round-robin over `{low, medium, high, critical}`, `published_at` monotonically increasing. `tests/bench/vuln_index/test_lookup_perf.py::test_lookup_p99_under_10ms` performs 100 lookups of `pkg-42`, asserts p99 < 10 ms (`@pytest.mark.bench`, excluded by default).

### L — Module purity / cold-start fence

- [ ] **AC-L1** AST-walk fence `tests/unit/vuln_index/test_module_purity.py`:
  - `PackageName` and `Ecosystem` are defined in `src/codegenie/types/identifiers.py`, NOT in `src/codegenie/vuln_index/`. (Grep + AST search.)
  - `src/codegenie/vuln_index/index.py` has zero `import blake3` / `from blake3` statements (ADR-0001 chokepoint) — mirrors `tests/unit/probes/layer_b/test_node_reflection.py` pattern.
- [ ] **AC-L2** **Cold-start fence** `tests/unit/vuln_index/test_cold_start.py`: snapshot `sys.modules`, `import codegenie.vuln_index`, snapshot again. Diff must NOT contain `alembic`, `alembic.command`, `alembic.config`, `sqlalchemy`, or any submodule thereof.
- [ ] **AC-L3** No raw `subprocess` import in `src/codegenie/vuln_index/`. Alembic is invoked in-process only.

### M — Gates

- [ ] **AC-M1** `ruff format`, `ruff check`, `mypy --strict src/codegenie/vuln_index src/codegenie/types/identifiers.py` clean.
- [ ] **AC-M2** `make lint-imports` green — no new forbidden imports.
- [ ] **AC-M3** `make fence` green — `alembic` is not in `FORBIDDEN_LLM_SDKS` (verified by reading `tests/unit/test_pyproject_fence.py`).

## Implementation outline

1. **Extend `src/codegenie/types/identifiers.py` (additive):**
   - Add `PackageName = NewType("PackageName", str)` and `Ecosystem = Literal["npm", "pypi", "maven", "rubygems", "gomod"]`.
   - Add `parse_package_name(s) -> Result[PackageName, ParseError]` (npm name regex, scoped + unscoped, no version).
   - Add `parse_ecosystem(s) -> Result[Ecosystem, ParseError]` (closed set membership).
   - Append both to `__all__`. Update `_NEWTYPE_REGISTRY` docstrings to cite ADR-0033.
2. **`src/codegenie/vuln_index/models.py`:**
   - `class AffectedRange(BaseModel)`: `frozen=True, extra="forbid"`. Independence docstring on `fixed` / `last_affected`.
   - `class VulnerabilityRecord(BaseModel)`: `frozen=True, extra="forbid"`. Imports `PackageName`, `Ecosystem` from `codegenie.types.identifiers`.
3. **`src/codegenie/vuln_index/errors.py`:**
   - `class VulnIndexLookupError(BaseModel)` with `reason: Literal["cve_not_found", "closed"]`, `details: dict[str, str | int] = {}`.
   - `class VulnIndexConfigError(BaseModel)` with `reason: Literal["invalid_max_age", "non_positive_max_age"]`, `details: dict[str, str | int] = {}`.
   - `class VulnIndexException(Exception)` carrying a single `model: VulnIndexLookupError | VulnIndexConfigError` attribute.
   - Module-level `_STALE_VULN_INDEX_EVENT_TYPE: Final[Literal["stale_vuln_index"]] = "stale_vuln_index"`.
4. **`src/codegenie/vuln_index/index.py`:**
   - Module-level `_DEFAULT_MAX_AGE_DAYS: Final[int] = 7`, `_PRAGMAS: Final[tuple[str, ...]] = ("PRAGMA journal_mode=WAL", "PRAGMA synchronous=NORMAL")`.
   - `def _parse_max_age_seconds(env: Mapping[str, str] | None = None) -> int` — reads `env or os.environ`, strips whitespace, accepts decimal-int strings only; raises `VulnIndexException(VulnIndexConfigError(...))` on miss.
   - `def _is_stale_pure(now: float, mtime: float, max_age_seconds: int) -> bool` — pure, side-effect-free.
   - `class VulnIndex:` `__init__(path)` opens sqlite connection (or defers if path missing), applies `_PRAGMAS`; `__enter__`/`__exit__`/`close()`; `lookup` / `affecting_range` / `digest` / `is_stale` / `stale_payload` per ACs; `_raw_insert(record)` / `_raw_set_meta(k, v)` test seams.
   - `digest()` calls `codegenie.hashing.identity_hash(...)` over `(schema_version, feed_digest_nvd, feed_digest_ghsa, feed_digest_osv)` and strips the `sha256:` prefix to yield a 64-hex string — OR computes BLAKE3 via `content_hash_bytes` and strips `blake3:`. Pick `identity_hash` (it's the joiner that already implements `\x1f`-arity-witness shape). Wrap in `BlobDigest(...)` after `parse_blob_digest`-equivalent validation.
   - Use `sqlite3` stdlib (NOT SQLAlchemy ORM).
5. **`src/codegenie/vuln_index/migrations/`:**
   - `env.py` — Alembic env wired to `sqlite:///<path>` via `VULN_INDEX_PATH` env var (test plumbing); offline mode supported.
   - `script.py.mako` — standard template.
   - `versions/0001_initial_schema.py` — `op.create_table("vulnerabilities", ...)`, indexes, `meta` table, unique constraint. Header docstring cites story S3-02.
   - `def _upgrade(db: Path) -> None`: lazy-imports `from alembic import command; from alembic.config import Config` inside the function; invokes `command.upgrade(config, "head")`.
6. **`src/codegenie/vuln_index/__init__.py`** exports per AC-A2 (no `_raw_*`).
7. **`pyproject.toml`** — add `alembic` (and any minimal transitive — typically `Mako`, `SQLAlchemy`) as runtime deps. Verify against `FORBIDDEN_LLM_SDKS` (clean).

## TDD plan — red / green / refactor

### Red

**Test file: `tests/unit/types/test_identifiers_phase3_vuln_index.py`** (additive extension to S1-01's test suite)

- Parametrized happy-path for `parse_package_name`: `["express", "@scope/pkg", "lodash", "a", "@a/b"]`.
- Parametrized rejection for `parse_package_name`: `["", "EXPRESS", "express@4.19.2", "express ", "@scope", "@/pkg", "scope/pkg", "../etc/passwd", "@scope/PKG"]`.
- Parametrized happy-path for `parse_ecosystem`: each member of the closed set.
- Rejection: `["NPM", "rust", "", " npm "]`.
- `__all__` membership: `assert "PackageName" in identifiers.__all__ and "Ecosystem" in identifiers.__all__`.

**Test file: `tests/unit/vuln_index/test_index.py`**

```python
from __future__ import annotations

import os
import time
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pytest
from codegenie.vuln_index import (
    VulnIndex, VulnerabilityRecord, AffectedRange,
    VulnIndexLookupError, VulnIndexConfigError, VulnIndexException,
)
from codegenie.types.identifiers import PackageName, CveId, parse_blob_digest

# --- Selectivity (AC-F2) ---

@pytest.fixture
def multi_seeded_index(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    for cve, eco, pkg, fixed in [
        ("CVE-2024-21501", "npm",  "express",  "4.19.2"),
        ("CVE-2023-26136", "npm",  "lodash",   "4.17.21"),
        ("CVE-2024-11111", "pypi", "express",  "0.0.2"),
    ]:
        idx._raw_insert(VulnerabilityRecord(
            cve_id=CveId(cve), ecosystem=eco, package=PackageName(pkg),
            affected_range=AffectedRange(introduced="0.0.0", fixed=fixed, last_affected=None),
            severity="high", published_at=datetime.now(timezone.utc), source="nvd",
        ))
    yield idx
    idx.close()

def test_lookup_selectivity_excludes_other_packages_and_ecosystems(multi_seeded_index):
    results = multi_seeded_index.lookup(PackageName("express"), "npm")
    cves = {r.cve_id for r in results}
    assert cves == {"CVE-2024-21501"}  # not lodash, not pypi/express

def test_lookup_missing_package_returns_empty_list(multi_seeded_index):
    assert multi_seeded_index.lookup(PackageName("nonexistent-pkg"), "npm") == []

# --- Sort + tiebreak (AC-F4) ---

def test_lookup_sorts_severity_desc_published_desc_cveid_asc(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t1 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    seeds = [
        ("CVE-2026-0001", "high",     t0),
        ("CVE-2026-0002", "critical", t0),
        ("CVE-2026-0003", "high",     t1),
        ("CVE-2026-0004", "medium",   t1),
        ("CVE-2026-0005", "critical", t0),  # tiebreak with 0002
    ]
    for cve, sev, ts in seeds:
        idx._raw_insert(VulnerabilityRecord(
            cve_id=CveId(cve), ecosystem="npm", package=PackageName("X"),
            affected_range=AffectedRange(introduced="0.0.0", fixed=None, last_affected=None),
            severity=sev, published_at=ts, source="nvd",
        ))
    cves = [r.cve_id for r in idx.lookup(PackageName("X"), "npm")]
    # critical > high > medium; within critical: same ts → cve_id ASC; within high: t1 before t0
    assert cves == ["CVE-2026-0002", "CVE-2026-0005",
                    "CVE-2026-0003", "CVE-2026-0001", "CVE-2026-0004"]

# --- affecting_range (AC-G) ---

def test_affecting_range_returns_matching_row_not_first(multi_seeded_index):
    rng = multi_seeded_index.affecting_range(CveId("CVE-2023-26136"))
    assert rng.fixed == "4.17.21"  # not express's 4.19.2

def test_affecting_range_missing_cve_raises_typed_exception(multi_seeded_index):
    with pytest.raises(VulnIndexException) as exc:
        multi_seeded_index.affecting_range(CveId("CVE-9999-9999"))
    assert exc.value.model.reason == "cve_not_found"
    assert exc.value.model.details["cve_id"] == "CVE-9999-9999"

# --- digest (AC-H) ---

def test_digest_roundtrips_through_parse_blob_digest(multi_seeded_index):
    d = multi_seeded_index.digest()
    parsed = parse_blob_digest(d)  # from S1-01
    assert parsed.is_ok()
    assert len(d) == 64
    assert ":" not in d  # NO "blake3:" prefix

EMPTY_DB_DIGEST_LITERAL = "<computed-once-frozen-here>"  # replaced post-first-run

def test_empty_db_digest_is_pinned_constant(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    assert idx.digest() == EMPTY_DB_DIGEST_LITERAL  # drift-fail-loud
    idx.close()

@pytest.mark.parametrize("meta_key", ["feed_digest_nvd", "feed_digest_ghsa", "feed_digest_osv", "schema_version"])
def test_digest_changes_when_any_meta_input_changes(multi_seeded_index, meta_key):
    before = multi_seeded_index.digest()
    multi_seeded_index._raw_set_meta(meta_key, "z" * 64)
    after = multi_seeded_index.digest()
    assert before != after

# --- is_stale (AC-I) ---

def test_is_stale_pure_strictly_greater_boundary():
    from codegenie.vuln_index.index import _is_stale_pure
    assert _is_stale_pure(now=100.0, mtime=100.0 - 7*86400, max_age_seconds=7*86400) is False
    assert _is_stale_pure(now=100.0, mtime=100.0 - 7*86400 - 1, max_age_seconds=7*86400) is True

def test_is_stale_pure_clock_skew_returns_false():
    from codegenie.vuln_index.index import _is_stale_pure
    # mtime in the future
    assert _is_stale_pure(now=100.0, mtime=200.0, max_age_seconds=7*86400) is False

@pytest.mark.parametrize("bad_value,expected_reason", [
    ("not-an-int", "invalid_max_age"),
    ("", "invalid_max_age"),
    ("7.5", "invalid_max_age"),
    ("+7", "invalid_max_age"),
    ("007 garbage", "invalid_max_age"),
    ("0", "non_positive_max_age"),
    ("-1", "non_positive_max_age"),
])
def test_env_validation_rejection_corpus(tmp_path, monkeypatch, alembic_upgrade, bad_value, expected_reason):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", bad_value)
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    with pytest.raises(VulnIndexException) as exc:
        idx.is_stale()
    assert exc.value.model.reason == expected_reason

@pytest.mark.parametrize("good_value", ["7", " 7 ", "7\n", "1"])
def test_env_validation_accepts_clean_whitespace_int(tmp_path, monkeypatch, alembic_upgrade, good_value):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", good_value)
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    idx.is_stale()  # MUST NOT raise

# --- Property: staleness is correctly defined for all (days, age_days) ---

from hypothesis import given, strategies as st, settings

@given(days=st.integers(min_value=1, max_value=365),
       age_days=st.integers(min_value=0, max_value=730))
@settings(max_examples=50, deadline=None)
def test_is_stale_property(tmp_path_factory, monkeypatch, days, age_days, alembic_upgrade):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", str(days))
    db = tmp_path_factory.mktemp("p") / "vuln-index.sqlite"
    alembic_upgrade(db)
    age_seconds = age_days * 86400
    os.utime(db, (time.time() - age_seconds,) * 2)
    expected = age_seconds > days * 86400  # strict
    assert VulnIndex(db).is_stale() is expected

# --- Connection lifecycle (AC-E3, E4, E6) ---

def test_close_then_lookup_raises_closed(multi_seeded_index):
    idx = multi_seeded_index
    idx.close()
    with pytest.raises(VulnIndexException) as exc:
        idx.lookup(PackageName("express"), "npm")
    assert exc.value.model.reason == "closed"

def test_double_close_is_idempotent(multi_seeded_index):
    multi_seeded_index.close()
    multi_seeded_index.close()  # MUST NOT raise

def test_no_fd_leak_over_1024_open_close(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    for _ in range(1024):
        with VulnIndex(db) as idx:
            _ = idx.digest()  # touch the connection

# --- Stale payload (AC-J1) ---

def test_stale_payload_round_trips_pydantic_type_adapter(tmp_path, alembic_upgrade, monkeypatch):
    from pydantic import TypeAdapter
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "7")
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    os.utime(db, (time.time() - 8 * 86400,) * 2)
    idx = VulnIndex(db)
    payload = idx.stale_payload()
    Adapter = TypeAdapter(dict[str, str | int | bool | float | list[str]])
    Adapter.validate_python(payload)  # MUST NOT raise
    assert set(payload.keys()) == {"path", "mtime_iso", "age_days", "threshold_days"}
```

**Test file: `tests/unit/vuln_index/test_migrations.py`**

```python
def test_alembic_upgrade_creates_tables(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"vulnerabilities", "meta", "alembic_version"} <= tables

def test_composite_index_columns_in_order(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    cols = [(r[0], r[2]) for r in conn.execute("PRAGMA index_info('idx_vuln_pkg_eco')")]
    assert cols == [(0, "ecosystem"), (1, "package")]

def test_explain_query_plan_uses_composite_index(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM vulnerabilities WHERE ecosystem=? AND package=?",
        ("npm", "express"),
    ).fetchall()
    assert any("idx_vuln_pkg_eco" in str(r) for r in plan)

def test_double_upgrade_is_idempotent(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    alembic_upgrade(db)  # MUST NOT raise
    conn = sqlite3.connect(db)
    revs = list(conn.execute("SELECT version_num FROM alembic_version"))
    assert len(revs) == 1

def test_insert_or_ignore_idempotent(tmp_path, alembic_upgrade):
    # AC-D4 — re-inserting an identical record is a no-op
    ...  # full body in green phase
```

**Test file: `tests/unit/vuln_index/test_module_purity.py`** (AC-L1, L3)

```python
import ast
from pathlib import Path

VULN_INDEX = Path("src/codegenie/vuln_index/index.py")

def test_no_raw_blake3_import():
    tree = ast.parse(VULN_INDEX.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("blake3"), \
                    f"ADR-0001 violation: raw blake3 import in {VULN_INDEX}"
        if isinstance(node, ast.ImportFrom):
            assert node.module is None or not node.module.startswith("blake3"), \
                f"ADR-0001 violation: from blake3 import in {VULN_INDEX}"

def test_no_subprocess_in_vuln_index():
    for py in Path("src/codegenie/vuln_index").rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in (node.names if isinstance(node, ast.Import) else [])]
                if isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                for n in names:
                    assert "subprocess" not in n, f"in-process Alembic only: {py}"

def test_package_name_and_ecosystem_live_in_identifiers_module():
    from codegenie.types import identifiers
    assert "PackageName" in identifiers.__all__
    assert "Ecosystem" in identifiers.__all__
    vi_models_src = Path("src/codegenie/vuln_index/models.py").read_text()
    assert "NewType(\"PackageName\"" not in vi_models_src
    assert "Literal[\"npm\"" not in vi_models_src  # Ecosystem definition lives elsewhere
```

**Test file: `tests/unit/vuln_index/test_cold_start.py`** (AC-L2)

```python
import sys

def test_importing_vuln_index_does_not_load_alembic():
    # Drop any cached imports so the snapshot is honest.
    for mod in list(sys.modules):
        if mod.startswith(("alembic", "sqlalchemy", "codegenie.vuln_index")):
            del sys.modules[mod]
    before = set(sys.modules)
    import codegenie.vuln_index  # noqa: F401
    after = set(sys.modules) - before
    forbidden = {m for m in after if m.startswith(("alembic", "sqlalchemy"))}
    assert forbidden == set(), \
        f"cold-start regression: {forbidden} loaded by importing codegenie.vuln_index"
```

**Test file: `tests/unit/vuln_index/conftest.py`**

```python
import pytest
from pathlib import Path

@pytest.fixture
def alembic_upgrade():
    """In-process Alembic upgrade — no subprocess. AC-E2."""
    def _upgrade(db: Path) -> None:
        from alembic import command  # noqa: PLC0415 — cold-start budget (ADR cold-start)
        from alembic.config import Config
        cfg = Config()
        cfg.set_main_option("script_location", "src/codegenie/vuln_index/migrations")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
        command.upgrade(cfg, "head")
    return _upgrade
```

**Bench (`tests/bench/vuln_index/test_lookup_perf.py`):**

```python
import time
import pytest
from codegenie.types.identifiers import PackageName

@pytest.mark.bench
def test_lookup_p99_under_10ms(seeded_10k_index):
    samples = []
    for _ in range(100):
        t0 = time.perf_counter()
        seeded_10k_index.lookup(PackageName("pkg-42"), "npm")
        samples.append(time.perf_counter() - t0)
    samples.sort()
    assert samples[98] < 0.010
```

### Green

Smallest impl: §Implementation outline. ~350 lines (Alembic boilerplate + sqlite3 wrapper + pydantic models + smart constructors). Replace `EMPTY_DB_DIGEST_LITERAL` placeholder with the actual computed hex after first green run; commit the constant as the drift sentinel.

### Refactor

- Lift the sort into a SQL `ORDER BY` clause (`ORDER BY CASE severity ... END DESC, published_at DESC, cve_id ASC`).
- Document the staleness threshold default in `docs/operations/phase03-runbook.md` (S9-04 ships the runbook; leave a TODO comment with `# story-S3-02` reference).
- Add a `__repr__` on `VulnIndex` showing `(path, closed)`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `PackageName`, `Ecosystem`, `parse_package_name`, `parse_ecosystem` (additive) |
| `src/codegenie/vuln_index/__init__.py` | Package exports |
| `src/codegenie/vuln_index/models.py` | `VulnerabilityRecord`, `AffectedRange` |
| `src/codegenie/vuln_index/errors.py` | Pydantic error models + `VulnIndexException` |
| `src/codegenie/vuln_index/index.py` | `VulnIndex`, `_is_stale_pure`, `_parse_max_age_seconds` |
| `src/codegenie/vuln_index/migrations/env.py` | Alembic env |
| `src/codegenie/vuln_index/migrations/script.py.mako` | Template |
| `src/codegenie/vuln_index/migrations/versions/0001_initial_schema.py` | Initial migration |
| `tests/unit/types/test_identifiers_phase3_vuln_index.py` | `PackageName`/`Ecosystem` smart-constructor tests |
| `tests/unit/vuln_index/test_index.py` | Red unit tests |
| `tests/unit/vuln_index/test_migrations.py` | Migration + index-usage tests |
| `tests/unit/vuln_index/test_module_purity.py` | AST fence tests |
| `tests/unit/vuln_index/test_cold_start.py` | Cold-start fence |
| `tests/unit/vuln_index/conftest.py` | `alembic_upgrade` fixture |
| `tests/bench/vuln_index/conftest.py` | `seeded_10k_index` fixture |
| `tests/bench/vuln_index/test_lookup_perf.py` | Advisory bench |
| `pyproject.toml` | Add `alembic` runtime dep |

## Out of scope

- **CVE feed parsers + semver validation** — S3-03 ships NVD/GHSA/OSV smart-constructor parsers with size/depth caps AND validates `AffectedRange.introduced/fixed/last_affected` as semver. This story accepts non-empty strings only.
- **`codegenie vuln-index refresh` CLI** — S3-03 owns the CLI subcommand and orchestrates ingest.
- **`StaleVulnIndex` event emission at orchestrator init** — S6-04 wires `VulnIndex.is_stale()` + `stale_payload()` to the orchestrator's startup and emits the spanning event; this story exposes the predicate + payload only.
- **Bundle cache-key composition** — S3-05 reads `VulnIndex.digest()` into the BLAKE3 key; this story exposes the digest only.
- **Multi-ecosystem ingest beyond NPM** — schema is open (column accepts any `Ecosystem` value), but only NPM is exercised in Phase 3 fixtures.
- **Migration rollback** — Alembic supports `downgrade` mechanically; Phase 3 only exercises `upgrade head`. Don't write hand-tuned downgrades.
- **`raw_payload BLOB` size cap** — S3-03's ingest enforces (~256 KB per row); no schema-level CHECK in this story.
- **`VulnIndex` as `Protocol`/`ABC`** — defer to Phase 8 if `RedisVulnIndex` lands. Today: one consumer, one impl. Rule 2 / YAGNI.

## Notes for the implementer

- **`digest()` MUST be deterministic across processes.** Use `codegenie.hashing.identity_hash(*parts)` (sha256-based; returns `"sha256:<hex>"`); strip the `"sha256:"` prefix to yield the 64-hex form. Alternatively use `content_hash_bytes(b"...")` and strip `"blake3:"`. Either way, the return value of `digest()` is the raw 64-hex string (no prefix) — this is required to round-trip through S1-01's `parse_blob_digest` (grammar `^[0-9a-f]{64}$`). Downstream consumers (BundleBuilder cache-key concat per ADR-0008) prepend an algorithm tag when they need self-describing storage.
- **Empty-DB `digest()` is a pinned literal.** Compute once on first green run (`make test -k empty_db_digest` will fail and show the actual value); paste the constant into `EMPTY_DB_DIGEST_LITERAL`; commit. A future change to the joiner / field order / hash algorithm forces an intentional update of this constant — that IS the drift sentinel.
- **`PackageName` / `Ecosystem` are kernel-tier additions to `identifiers.py`.** Mirror the precedent set by S2-02 (`ConventionId`) and S1-04 (`ProbeId`): edit `identifiers.py` additively, append to `__all__`, update the `_NEWTYPE_REGISTRY` docstring with the ADR-0033 citation. AC-L1 verifies these names DO NOT also exist in `vuln_index/models.py` — the kernel-tier home is `identifiers.py`, period.
- **Error model mirrors S3-01's `TCCMParseError` resolution.** `VulnIndexLookupError` and `VulnIndexConfigError` are frozen Pydantic `BaseModel`s with `Literal[...]` reason. Production code constructs the model and raises `VulnIndexException(model)`. Tests assert `exc.value.model.reason == "..."`. Adding a new reason variant = one entry in the `Literal[...]` + new test parameter.
- **`alembic` is lazy-imported.** Module top of `vuln_index/index.py` and `__init__.py` has NO `import alembic`. The import lives inside `_upgrade()` and inside the `alembic_upgrade` test fixture. The cold-start fence (`test_cold_start.py`) is load-bearing — production ADR-0005's "no LLM-SDK in `--help` closure" applies by analogy to any heavyweight import here.
- **Alembic invocation is in-process, never subprocess.** `alembic.command.upgrade(config, "head")` directly. This avoids `ALLOWED_BINARIES` amendment AND keeps the test fixture hermetic. The `subprocess` module is not imported anywhere in `src/codegenie/vuln_index/` (AC-L3 enforces).
- **`is_stale` env reading is intentionally per-call.** Each `is_stale()` invocation re-reads `os.environ` so operators flipping `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS` mid-run take effect immediately (12-factor dynamic config). If a future caller needs cached behavior, they bind the value once at orchestrator init and pass it into `_is_stale_pure` directly.
- **Sort tiebreaker `cve_id ASC` is load-bearing.** Without it, sqlite returns rows in indexed order which is implementation-defined; the `digest()`-stability property test (which feeds ADR-0008's BundleBuilder cache-key correctness) would be flaky on multi-record fixtures.
- **`_raw_insert` / `_raw_set_meta` are S3-03's only public-by-convention seams.** S3-03 calls them from its ingest CLI; no other module should. Kept off `__all__` to signal the boundary. If S3-03 needs additional seams (e.g., bulk-insert), surface as an AC there, not as drift here.
- **Deferred design opportunities** (record in attempt log, don't implement here): (a) `SemverVersion` newtype + smart constructor — S3-03 is the natural parsing boundary; (b) `VulnIndex` as `Protocol` — defer to Phase 8 `RedisVulnIndex`; (c) context-manager pattern is supported but optional — typical use is `with VulnIndex(p) as idx: ...`; (d) `__repr__` for debugging — flag for the refactor pass.
- **`StaleVulnIndex` event-type literal** is exposed via `_STALE_VULN_INDEX_EVENT_TYPE: Final[Literal["stale_vuln_index"]]` so S6-04 imports the constant instead of duplicating the string. The story does NOT import `WorkflowSpanningEvent` (S6-01 ships it); coupling is via the `Final[Literal[...]]` constant + the typed-dict round-trip in `test_stale_payload_round_trips_pydantic_type_adapter`.
