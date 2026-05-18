# Story S3-03 — NVD 2.0 / GHSA / OSV feed-registry kernel + size/depth caps + `codegenie vuln-index refresh` CLI

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** HARDENED
**Effort:** L
**Depends on:** S3-02
**ADRs honored:** Phase 3 ADR-0008 (`vuln_index.digest` participates in Bundle cache key — feed digests update on refresh, **deterministically across fetch order**), Phase 3 ADR-0010 (sum-type / newtype discipline — closed `Literal` reasons + `SemverVersion` newtype), Phase 0 ADR-0001 (BLAKE3 chokepoint via `codegenie.hashing`), production ADR-0005 (no LLM SDK in this loop — pure parsers; cold-start budget — `import codegenie.vuln_index.parsers` does NOT load `alembic` or `urllib.request`), production ADR-0033 (newtype identifiers + smart constructors)

## Validation notes (2026-05-18 — phase-story-validator)

This story was hardened from `Ready` → `HARDENED`. Headline changes:

- **`VulnParseError` redesigned as a frozen Pydantic `BaseModel` with closed `Literal[...]` reason.** S3-01's `TCCMParseError` and S3-02's `VulnIndexLookupError` precedents apply verbatim: markers-only `CodegenieError` subclasses cannot carry typed `.reason` state; frozen BaseModel + `Literal[...]` reason + `details: dict[str, str | int] = {}` is the canonical shape. Closed set: `{"payload_too_large", "json_too_deep", "bad_json", "missing_required_field", "unsupported_ecosystem", "bad_cve_id", "bad_ghsa_id", "missing_tz", "bad_semver", "bad_ecosystem"}`. Adding a variant requires an explicit story amendment.
- **`PackageName` + `"npm"` adopted from S3-02.** All TDD references to `PackageId("express")` / `Ecosystem.NPM` replaced with `PackageName("express")` / `"npm"` (string literal). `Ecosystem` is `Literal["npm","pypi","maven","rubygems","gomod"]`, NOT an Enum.
- **Plugin / registry kernel for feeds — `@register_vuln_feed("nvd"|"ghsa"|"osv")`.** Crosses rule-of-three at three peers. Mirrors `@register_index_freshness_check` (`src/codegenie/indices/registry.py`) and `@register_dep_graph_strategy` (`src/codegenie/depgraph/registry.py`) in-repo precedents. CLAUDE.md "Extension by addition" + "Open/Closed seams" — adding a Phase 4 feed (e.g., RustSec) is one new `feeds/<source>.py` module + one row in `vuln_index/__init__.py`'s explicit-import list. CLI `--source` choices read from the registry. Zero edits to `cli.py`, `parsers.py` (shared helpers only), or `ingest.py`.
- **`SemverVersion` newtype lands in `codegenie.types.identifiers`.** Deferred from S3-02 Notes ("S3-03 is the natural parsing boundary"). Additive extension mirroring S3-02's `PackageName` precedent. `AffectedRange.introduced/fixed/last_affected` migrate from `str` to `SemverVersion | None`.
- **Hexagonal fetcher port via `Feed` Protocol.** `class Feed(Protocol)` exposes `source: Literal[...]`, `parse_one(raw)`, and `fetch(*, since=None, timeout_s=30.0) -> Iterator[bytes]`. Tests inject cassette feeds via `_test_register_feed` helper, NOT `monkeypatch.setattr` on module attributes — renames survive.
- **Deterministic `_update_feed_digest` concat order.** Signature is `_update_feed_digest(idx, source, records: Sequence[VulnerabilityRecord]) -> None`; canonicalizes by `cve_id ASC` before concat. Same upstream content → same digest regardless of fetch order — load-bearing for ADR-0008 Bundle cache stability under feed-source churn.
- **Typed exit-code dispatch through `_EXIT_CODE_DISPATCH`.** Three new typed exceptions (`VulnRefreshPartialError=4`, `VulnFeedFetchError=5`, `VulnIndexMigrationNotApplied=7` — code 6 already taken by `SecretLikelyFieldNameError`) extend the existing `cli.py::_EXIT_CODE_DISPATCH` table. No inline `sys.exit(N)`.
- **Lazy alembic + lazy urllib.** `alembic.command.upgrade` imports inside `_apply_migrations(db_path)`; `urllib.request` imports inside each `Feed.fetch` impl. Cold-start fence: `import codegenie.vuln_index.parsers` adds neither to `sys.modules`.
- **HTTP timeout + URL allowlist.** Module-level `_FEED_URLS: Final[Mapping[Literal[...], str]]` allowlist; `urllib.request.urlopen(url, timeout=30.0)` mandatory. AST fence forbids `requests` / `httpx` / `urllib3` imports anywhere in `vuln_index/`.
- **Boundary-exact parametrized tests.** Size cap at `len(raw) == 1_048_576` accepts, `== 1_048_577` rejects. Depth cap at depth `== 16` accepts, `== 17` rejects. Hypothesis property test for parser determinism (same `raw` → same `Result`).
- **Functional core / imperative shell on ingest.** Pure `_record_to_row(record) -> tuple[str, ...]` separable from impure `_persist(conn, rows)` boundary. Pure mapper has its own property test.
- **Cassette fixture corpus pinned.** Happy-path + 5 malformed variants per feed (`malformed-depth`, `malformed-size`, `malformed-no_tz`, `malformed-bad_cve`, `malformed-wrong_eco`). README documents the schema.
- **`raw_payload BLOB` size cap (256 KB per row).** Deferred from S3-02 Notes; over-cap records become `VulnParseError(reason="payload_too_large", details={"size": ..., "limit": 262144})`.

See [`_validation/S3-03-vuln-index-ingest-cli.md`](_validation/S3-03-vuln-index-ingest-cli.md) for the full audit log.

## Context

S3-02 ships the sqlite schema + `VulnIndex` surface; this story fills it. Three CVE-feed parsers (NVD JSON 2.0, GHSA, OSV) project upstream payloads into typed `VulnerabilityRecord`s via smart constructors with **hard size and depth caps** (`1 MiB` per fetch chunk, JSON depth `16`) — a malformed-or-malicious feed must never crash the parser or amplify into a memory exhaustion. The `codegenie vuln-index refresh` CLI subcommand orchestrates HTTP fetch + parse + idempotent UPSERT into the sqlite store, then updates `meta.feed_digest_{source}` so `VulnIndex.digest()` (consumed by `BundleBuilder` cache-key, ADR-0008) reflects the refresh **deterministically across fetch order**.

The three feeds are the third occurrence of "per-source strategy" in the codebase (after `IndexFreshness` and `DepGraphStrategy`), which crosses the rule-of-three threshold. Following the established precedent, this story lands a `@register_vuln_feed` registry kernel: each `Feed` is a class implementing the protocol + a one-line `@register_vuln_feed("source")` decoration. Phase 4 widens by file addition only.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C11` — "Each feed projects into typed Pydantic records via smart constructors with size (1 MiB) + depth (16) caps." + "`codegenie vuln-index refresh` pulls NVD JSON 2.0 delta, GHSA `since`-cursor, OSV via GCS zsync."
  - `../phase-arch-design.md §Edge cases` — malformed/over-sized payloads must fail typed, not OOM.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Consequences` — refresh updates `vuln_index.digest`; Bundle cache hit rate drops slightly after refresh; correctness preserved.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `Literal[...]`-typed reasons on error models; newtype identifiers.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — "Smart-constructor parsers with 1 MiB / depth-16 caps; `codegenie vuln-index refresh` CLI subcommand." + done criterion "`codegenie vuln-index refresh` end-to-end populates a test sqlite."
- **Sibling validation reports (load-bearing precedent):**
  - `_validation/S3-01-tccm-context-query-models.md` — `TCCMParseError` redesign-as-frozen-Pydantic-BaseModel; closed `Literal` reason set; mypy-strict meta-test pattern.
  - `_validation/S3-02-vuln-index-sqlite.md` — `PackageName` + `Ecosystem` additive extension to `identifiers.py`; lazy-alembic pattern; AST fence + cold-start fence patterns; deterministic sort tiebreaker for digest stability.
- **Existing code:**
  - `src/codegenie/vuln_index/` (S3-02) — `VulnIndex`, `VulnerabilityRecord`, `AffectedRange`, sqlite schema; reuse `_raw_insert` and `_raw_set_meta` instance methods.
  - `src/codegenie/indices/registry.py` — `FreshnessRegistry` + `@register_index_freshness_check` — registry-pattern precedent.
  - `src/codegenie/depgraph/registry.py` — `DepGraphRegistry` + `@register_dep_graph_strategy` — registry-pattern precedent.
  - `src/codegenie/cli.py::_EXIT_CODE_DISPATCH` — typed-exception → exit-code dispatch table; this story extends additively.
  - `src/codegenie/result.py` — `Result[T, E]` for smart-constructor returns.
  - `src/codegenie/errors.py` — `CodegenieError` markers-only base. Three new typed exceptions (`VulnRefreshPartialError`, `VulnFeedFetchError`, `VulnIndexMigrationNotApplied`) land here.
  - `src/codegenie/hashing.py` — `content_hash` / `identity_hash` for per-feed digest computation.
  - `src/codegenie/types/identifiers.py` — additive boundary for kernel-tier types. This story extends with `SemverVersion` + `parse_semver`.

## Goal

`codegenie.vuln_index` exposes a `@register_vuln_feed(source)` registry kernel + three concrete `Feed` implementations (`NvdFeed`, `GhsaFeed`, `OsvFeed`) under `src/codegenie/vuln_index/feeds/`. Each feed conforms to a `Feed(Protocol)` with `source: Literal["nvd","ghsa","osv"]`, `parse_one(raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]`, and `fetch(*, since=None, timeout_s=30.0) -> Iterator[bytes]`. Parsers honor 1 MiB / depth-16 caps; the per-record persisted `raw_payload` is capped at 256 KB. `codegenie vuln-index refresh [--source SOURCE|all] [--index-path PATH]` reads CLI choices from `registry.feed_sources()`, fetches via the registered feeds in `sorted` order (deterministic), parses, idempotently UPSERTs into the sqlite store, and updates `meta.feed_digest_{source}` from records sorted `cve_id ASC` (deterministic — same upstream content → same digest regardless of fetch order). Exit codes thread through the existing `cli.py::_EXIT_CODE_DISPATCH` via three new typed exceptions: `VulnRefreshPartialError=4` (any per-record parse error), `VulnFeedFetchError=5` (all feeds failed HTTP), `VulnIndexMigrationNotApplied=7` (caller must apply alembic head first). `SemverVersion` newtype lands in `codegenie.types.identifiers` (additive); `AffectedRange.introduced/fixed/last_affected` migrate to `SemverVersion | None`.

## Acceptance criteria

### C — Error model

- [ ] **AC-C1** `src/codegenie/vuln_index/parsers.py` defines `VulnParseError` as a frozen Pydantic `BaseModel` (NOT a `CodegenieError` subclass). `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields: `reason: Literal["payload_too_large", "json_too_deep", "bad_json", "missing_required_field", "unsupported_ecosystem", "bad_cve_id", "bad_ghsa_id", "missing_tz", "bad_semver", "bad_ecosystem"]` (closed; additions require an ADR / story amendment) and `details: dict[str, str | int] = {}`.
- [ ] **AC-C2** `VulnParseException(Exception)` is a thin wrapper carrying a single attribute `model: VulnParseError`. Production code paths construct the model and either return `Result.err(model)` (parser API) or `raise VulnParseException(model)` (CLI orchestration). Tests assert `exc.value.model.reason == "..."`.
- [ ] **AC-C3** `VulnParseError` lives in `codegenie.vuln_index.parsers.__all__`; `VulnParseException` lives in `codegenie.vuln_index.__all__`.
- [ ] **AC-C4** Parametrized mypy-strict meta-test (mirrors S3-02 AC-C4 / S3-01): a snippet `VulnParseError(reason="typo", details={})` raises `pydantic.ValidationError` at runtime AND fails `mypy --strict` (subprocess invocation with a temp `*.py`).

### P — Parser surface (per `Feed`)

- [ ] **AC-P1** Each registered feed's `parse_one(raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]` invokes the S1-01 smart constructor `parse_cve_id(s)` on the extracted CVE identifier; failure returns `VulnParseError(reason="bad_cve_id", details={"value": s})`. Test: a payload with `cve.id="not-a-cve"` yields `bad_cve_id`, NOT silent acceptance.
- [ ] **AC-P2** `unsupported_ecosystem` rejection is **parametric over the registered `Ecosystem` set**, not hardcoded. Phase 3 fixtures exercise `"npm"` only; non-npm CPE / `package.ecosystem` rows return `VulnParseError(reason="unsupported_ecosystem", details={"ecosystem": <value>})`. Phase 4 widens by adding entries to the per-feed `_CPE_VENDOR_TO_ECOSYSTEM: Final[Mapping[str, Ecosystem]]` (NVD) / package-ecosystem map (GHSA / OSV); no parser code edits.
- [ ] **AC-P3** Each parser populates `VulnerabilityRecord(published_at=...)` from the upstream ISO 8601 field directly; Pydantic coerces. Missing or naive datetimes (no `tzinfo`) → `VulnParseError(reason="missing_tz")`. No hand-rolled ISO parsing.
- [ ] **AC-P4** **Parser-determinism property (Hypothesis)** in `tests/unit/vuln_index/test_parsers_property.py`: for valid `raw: bytes` drawn from each feed's cassette corpus, `parse_one(raw) == parse_one(raw)` over 50 runs. Catches hash-seed / set-iteration / global-state contamination.

### S — Size and depth caps (shared parser kernel)

- [ ] **AC-S1** Module-level `_MAX_PAYLOAD_BYTES: Final[int] = 1_048_576` and `_MAX_JSON_DEPTH: Final[int] = 16` and `_MAX_RAW_PAYLOAD_BYTES: Final[int] = 262_144` (per-record persisted-blob cap; S3-02 Notes deferral).
- [ ] **AC-S2** `_safe_json_load(raw: bytes) -> Result[object, VulnParseError]` performs the size check BEFORE invoking `json.loads(raw)`. Wraps `json.JSONDecodeError` → `VulnParseError(reason="bad_json", details={"message": str(e)})`.
- [ ] **AC-S3** `_check_depth(value: object, max_depth: int = _MAX_JSON_DEPTH) -> None` recursively walks dict / list nesting. Returns at depth `<= 16`; raises `VulnParseException(VulnParseError(reason="json_too_deep", details={"depth": <breach_depth>}))` at depth `> 16`. **Boundary-exact tests:** depth = 16 accepts; depth = 17 rejects.
- [ ] **AC-S4** **Size-cap boundary tests:** `len(raw) == 1_048_576` accepts (returns `Ok` if otherwise valid); `len(raw) == 1_048_577` rejects with `payload_too_large` and `details={"size": 1_048_577, "limit": 1_048_576}`.
- [ ] **AC-S5** **Per-record raw_payload cap test:** a single record whose `raw_payload` bytes (post-JSON-canonicalize) exceeds 262_144 → `VulnParseError(reason="payload_too_large", details={"size": ..., "limit": 262144})`. Distinct from the fetch-chunk cap (AC-S4).

### R — Feed registry kernel (Open/Closed)

- [ ] **AC-R1** `src/codegenie/vuln_index/registry.py` defines `FeedRegistry` + `default_feed_registry` + `@register_vuln_feed(source: Literal["nvd","ghsa","osv"])` decorator. Mirrors `src/codegenie/indices/registry.py` shape (`FreshnessRegistry` / `register_index_freshness_check`).
- [ ] **AC-R2** `src/codegenie/vuln_index/protocol.py` defines `class Feed(Protocol)` with: class attribute `source: ClassVar[Literal["nvd","ghsa","osv"]]`; instance methods `parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]` and `fetch(self, *, since: datetime | None = None, timeout_s: float = 30.0) -> Iterator[bytes]`.
- [ ] **AC-R3** Three concrete feed modules `src/codegenie/vuln_index/feeds/{nvd,ghsa,osv}.py`. Each module file exports `class NvdFeed` / `GhsaFeed` / `OsvFeed`, decorated with `@register_vuln_feed("...")`. Feed instantiation is lazy: `registry.get_feed("nvd") -> NvdFeed()`.
- [ ] **AC-R4** `src/codegenie/vuln_index/__init__.py` does an **explicit import** of each `feeds/*.py` module (mirrors `probes/__init__.py` discipline — no `importlib.metadata` entry-point scan). Adding a Phase 4+ feed = new module + one new explicit-import line. Test: removing one of the three explicit imports causes `registry.feed_sources()` to return only 2 sources.
- [ ] **AC-R5** **Iteration order is deterministic:** `refresh --source all` iterates `sorted(registry.feed_sources())` (lexicographic) regardless of registration order.
- [ ] **AC-R6** **Open/Closed observable AC:** adding a hypothetical 4th feed (`feeds/_test_feed.py` registering source `"_test"`) — via the `_test_register_feed(feed)` test helper — surfaces a new value in `registry.feed_sources()` and a new choice in the CLI `--source` option, **without any source-file edits to `cli.py`, `parsers.py`, or `ingest.py`**. Asserted via subprocess `--help` output snapshot in `tests/integration/cli/test_vuln_index_refresh.py`.

### D — Ingest + digest (functional core / imperative shell)

- [ ] **AC-D1** `src/codegenie/vuln_index/ingest.py` defines `class IngestStats(BaseModel, frozen=True)` with fields `inserted: int = 0`, `skipped: int = 0`, `errors: list[VulnParseError] = []`, `errors_truncated: int = 0`. **Error-list cap:** `errors` is capped at module-level `_MAX_ERROR_REPORT: Final[int] = 100`; surplus errors increment `errors_truncated`. Total error count = `len(errors) + errors_truncated`.
- [ ] **AC-D2** `_update_feed_digest(idx: VulnIndex, source: str, records: Sequence[VulnerabilityRecord]) -> None` canonicalizes by `sorted(records, key=lambda r: r.cve_id)`, then concatenates `r.cve_id || \x1f || canonical_raw_payload(r) || \x1e` for each record (BLAKE3 via `codegenie.hashing.content_hash`). **Same upstream content → same digest regardless of fetch order.** Parse errors are NOT included in the digest input. Writes `meta.feed_digest_{source}` via `_raw_set_meta`.
- [ ] **AC-D3** **Functional-core split:** pure `_record_to_row(r: VulnerabilityRecord) -> tuple[str, ...]` returns the sqlite column tuple (no I/O). Impure `_persist(conn: sqlite3.Connection, rows: Iterable[tuple[str, ...]]) -> tuple[int, int]` performs `INSERT OR IGNORE` and returns `(inserted, skipped)`. Pure helper has its own Hypothesis property test (round-trip: `_record_to_row(r)` produces the column count + types pinned by the schema).
- [ ] **AC-D4** **Idempotency:** `ingest_records(idx, records)` followed by `ingest_records(idx, records)` against the same input → `stats_2.inserted == 0, stats_2.skipped == len(records)`. Tested both directly and as a Hypothesis property: insert N → `random.shuffle(records)` → ingest again → 0 net rows added.
- [ ] **AC-D5** **No-op refresh keeps `digest()` byte-identical:** `digest()` before refresh == `digest()` after a refresh against the SAME cassette content. Critical for ADR-0008 — operators running `codegenie vuln-index refresh` on a stale cron must not thrash the Bundle cache. Property test: shuffle the input cassette → digest unchanged.
- [ ] **AC-D6** **Digest changes under content change:** refresh against a cassette with one added / removed / mutated record → `digest()` value differs from the prior. Parametrized over `(add, remove, mutate_severity, mutate_range)`.

### X — CLI surface + typed exit-code dispatch

- [ ] **AC-X1** `codegenie vuln-index` click subgroup; `codegenie vuln-index refresh [--source SOURCE | all] [--index-path PATH]`. `--source` choices come from `default_feed_registry.feed_sources() + ["all"]` (computed at click-callback time so test-helper registrations are picked up).
- [ ] **AC-X2** Three new typed exceptions in `src/codegenie/errors.py`: `VulnRefreshPartialError(CodegenieError)`, `VulnFeedFetchError(CodegenieError)`, `VulnIndexMigrationNotApplied(CodegenieError)`. Markers-only (no `__init__`, mirroring existing discipline).
- [ ] **AC-X3** `src/codegenie/cli.py::_EXIT_CODE_DISPATCH` is extended additively to include `{VulnRefreshPartialError: 4, VulnFeedFetchError: 5, VulnIndexMigrationNotApplied: 7}`. Exit code `6` is NOT used (already mapped to `SecretLikelyFieldNameError`). The dispatch table is the single source of truth; the CLI handler raises typed exceptions, click catches and converts. NO inline `sys.exit(N)` in the refresh handler.
- [ ] **AC-X4** **Empty-feed contract:** if all feeds yield zero bytes / zero parsed records (transient empty delta from upstream) → `IngestStats(0, 0, [], 0)` → CLI exits `0`. Refresh ran cleanly, no data this delta. Tested with a cassette directory containing zero files.
- [ ] **AC-X5** **Per-record parse error → partial refresh:** at least one parse error AND at least one successful parse → CLI exits `4`. `_update_feed_digest` consumes only the successfully-parsed records.
- [ ] **AC-X6** **All feeds fail HTTP:** every registered feed's `fetch()` raises (e.g., simulated `URLError`) → CLI exits `5` and emits one `vuln_index.fetch_failed` structured log line per feed.
- [ ] **AC-X7** **Schema not migrated:** `--index-path` points to a file whose `alembic_version` row is absent OR the file does not exist → CLI exits `7` (NOT 6) with `VulnIndexMigrationNotApplied`. Operator runs `codegenie vuln-index migrate` (S3-02) or the CLI auto-applies on first refresh (auto-apply pinned to AC-X9).
- [ ] **AC-X8** `--index-path` precedence: CLI flag > `CODEGENIE_VULN_INDEX_PATH` env > default `<cwd>/.codegenie/cache/vuln-index.sqlite`. Click `default_factory` reads env at command invocation.
- [ ] **AC-X9** **Auto-apply migrations on first refresh:** if the DB path doesn't exist, the refresh handler creates it and applies `alembic.command.upgrade(cfg, "head")` (via S3-02's in-process `_apply_migrations` helper) BEFORE invoking any feed. If the DB exists but is not at head → exit `7` (do NOT auto-upgrade an existing-but-stale DB; operator must opt in).
- [ ] **AC-X10** CLI emits exactly one structured `vuln_index.refresh.completed` event with payload `{source: list[str], inserted: int, skipped: int, errors: int, exit_code: int, digest_changed: bool}` regardless of success / failure path. (Observability — Phase 9 projector consumes.)

### S — `SemverVersion` newtype (additive to identifiers)

- [ ] **AC-S6** `src/codegenie/types/identifiers.py` extended (additive — does not edit existing definitions) with `SemverVersion = NewType("SemverVersion", str)` plus `parse_semver(s: str) -> Result[SemverVersion, ParseError]`. Grammar: `^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$` (canonical npm/semver-2.0.0 shape). `SemverVersion` appears in `__all__`; `_NEWTYPE_REGISTRY` for `SemverVersion` cites `"ADR-0033"`.
- [ ] **AC-S7** `AffectedRange` Pydantic model (S3-02) migrates `introduced/fixed/last_affected` from `str` to `SemverVersion | None`. The `introduced` field stays required (`SemverVersion` smart-constructed at parse boundary); `fixed` and `last_affected` are independent optionals. Pydantic validator routes through `parse_semver` and surfaces `bad_semver` on failure during ingest.
- [ ] **AC-S8** Parametrized happy-path / rejection corpus for `parse_semver`: accepts `["1.0.0", "0.1.2", "1.2.3-alpha.1", "1.2.3+build.42", "1.2.3-rc.1+build.5"]`; rejects `["", "1", "1.2", "01.2.3", "1.2.3-", "1.2.3+", "v1.2.3", "1.2.3 "]`.

### N — Network port + lazy imports

- [ ] **AC-N1** `src/codegenie/vuln_index/feeds/{nvd,ghsa,osv}.py` use `urllib.request.urlopen(url, timeout=30.0)` (timeout is mandatory, NOT optional). Module-level `_FEED_URLS: Final[Mapping[str, str]]` allowlist pins the canonical upstream URL per feed (e.g., `"nvd": "https://services.nvd.nist.gov/rest/json/cves/2.0"`); a `Feed` that constructs a request URL outside this allowlist must fail at construction time. Test: a feed pointing at `"http://evil.example.com"` (via monkeypatched `_FEED_URLS`) raises `VulnFeedFetchError` at construction.
- [ ] **AC-N2** **AST module-purity fence** `tests/unit/vuln_index/test_module_purity_parsers.py`: no `import requests` / `from requests` / `import httpx` / `from httpx` / `import urllib3` / `from urllib3` ANYWHERE under `src/codegenie/vuln_index/`. No `import subprocess` either. Mirrors S3-02 AC-L1 / L3 patterns.
- [ ] **AC-N3** `urllib.request` is **lazy-imported inside each `Feed.fetch` method body**, not at module top. **Cold-start fence** `tests/unit/vuln_index/test_cold_start_parsers.py`: snapshot `sys.modules`, `import codegenie.vuln_index.parsers`, snapshot again. Diff must NOT contain `alembic`, `alembic.command`, `alembic.config`, `urllib.request`, or any submodule thereof.
- [ ] **AC-N4** `alembic.command.upgrade` is **lazy-imported inside `_apply_migrations(db_path)`** in `cli.py`'s refresh handler (or a co-located private helper module). Cold-start fence: `import codegenie.cli` adds no `alembic*` to `sys.modules`.

### T — Cassette fixture corpus

- [ ] **AC-T1** `tests/fixtures/cve-feeds/{nvd,ghsa,osv}/` contains:
  - `express-min.json` — happy-path minimal record (CVE-2024-21501 for NVD; analogous for GHSA / OSV).
  - `malformed-depth.json` — 17-deep nesting (triggers `json_too_deep`).
  - `malformed-size.json` — > 1 MiB synthesized (triggers `payload_too_large`).
  - `malformed-no_tz.json` — `published_at` is naive (triggers `missing_tz`).
  - `malformed-bad_cve.json` — `cve.id = "not-a-cve"` (triggers `bad_cve_id`).
  - `malformed-wrong_eco.json` — non-npm CPE / `package.ecosystem` (triggers `unsupported_ecosystem`).
  Plus a top-level `README.md` documenting the schema. Files are minimal — ~5 records each — to keep the test suite fast.
- [ ] **AC-T2** Each cassette file's filename is referenced verbatim in at least one parametrized test (no dangling fixtures).
- [ ] **AC-T3** A `_test_register_feed(feed: Feed)` helper in `tests/unit/vuln_index/conftest.py` adds a Feed to `default_feed_registry`; an `_unregister` finalizer reverts. Tests using cassette feeds use this helper, NOT `monkeypatch.setattr` on module-level functions. Survives renames; matches S3-02's registry-test discipline.

### F — Fences + gates

- [ ] **AC-F1** `make fence` green — `requests`, `httpx`, `urllib3` are explicitly forbidden by AC-N2 / import-linter contract for `vuln_index/`. `urllib.request` (stdlib) is allowed but only inside `Feed.fetch` method bodies.
- [ ] **AC-F2** `make lint-imports` green — no new forbidden imports.
- [ ] **AC-F3** `ruff format`, `ruff check`, `mypy --strict src/codegenie/vuln_index src/codegenie/types/identifiers.py` clean. No `subprocess` / `os.system` / `eval` / `exec` / `shell=True` patterns (forbidden-patterns hook gate).

## Implementation outline

1. **Extend `src/codegenie/types/identifiers.py` (additive):**
   - Add `SemverVersion = NewType("SemverVersion", str)`.
   - Add `parse_semver(s: str) -> Result[SemverVersion, ParseError]` (semver-2.0.0 grammar).
   - Append to `__all__`. Cite ADR-0033 in `_NEWTYPE_REGISTRY` docstring.
2. **`src/codegenie/vuln_index/protocol.py`:**
   - `class Feed(Protocol)` — `source: ClassVar[Literal["nvd","ghsa","osv"]]`, `parse_one`, `fetch`.
3. **`src/codegenie/vuln_index/registry.py`:**
   - `class FeedRegistry` mirroring `FreshnessRegistry` (register / get / list).
   - `default_feed_registry = FeedRegistry()`.
   - `register_vuln_feed(source) -> Callable[[type[Feed]], type[Feed]]` decorator.
   - `feed_sources() -> tuple[str, ...]` returns sorted registered sources.
   - `_test_register_feed` / `_test_unregister` test seams.
4. **`src/codegenie/vuln_index/parsers.py`:**
   - `class VulnParseError(BaseModel)` — frozen, closed `Literal` reason.
   - `class VulnParseException(Exception)` — thin wrapper.
   - `_MAX_PAYLOAD_BYTES`, `_MAX_JSON_DEPTH`, `_MAX_RAW_PAYLOAD_BYTES`, `_MAX_ERROR_REPORT` module-level `Final` constants.
   - `_safe_json_load`, `_check_depth` shared helpers.
   - `canonical_raw_payload(record) -> bytes` — deterministic JSON canonicalization (sorted keys, no whitespace) for `_update_feed_digest` input.
5. **`src/codegenie/vuln_index/feeds/{nvd,ghsa,osv}.py`:**
   - Each file: `_FEED_URLS` membership check; per-feed CPE/package-ecosystem map (`Final[Mapping[str, Ecosystem]]`); `class NvdFeed`/`GhsaFeed`/`OsvFeed` decorated with `@register_vuln_feed(...)`.
   - `parse_one` body: `_safe_json_load(raw)` → `_check_depth(parsed)` → field extraction via `parse_cve_id` + `parse_semver` + ecosystem lookup → `VulnerabilityRecord(...)` or `VulnParseError(...)`.
   - `fetch` body: lazy-imports `urllib.request`; calls `urlopen(url, timeout=timeout_s)`; yields raw record bytes.
6. **`src/codegenie/vuln_index/ingest.py`:**
   - `class IngestStats(BaseModel, frozen=True)` — inserted / skipped / errors / errors_truncated.
   - Pure `_record_to_row(r) -> tuple[str, ...]`.
   - Impure `_persist(conn, rows) -> tuple[int, int]`.
   - `ingest_records(idx, records: Iterable[VulnerabilityRecord | VulnParseError]) -> IngestStats` — drives both.
   - `_update_feed_digest(idx, source, records)` — sort + concat + BLAKE3 + write meta.
7. **`src/codegenie/vuln_index/__init__.py`:**
   - Explicit imports: `from . import parsers, ingest, registry; from .feeds import nvd as _nvd, ghsa as _ghsa, osv as _osv  # noqa: F401`.
   - `__all__` exports: `Feed`, `VulnParseError`, `VulnParseException`, `IngestStats`, `ingest_records`, `register_vuln_feed`, `default_feed_registry`.
8. **`src/codegenie/errors.py`:**
   - Add `VulnRefreshPartialError`, `VulnFeedFetchError`, `VulnIndexMigrationNotApplied` (markers-only).
9. **`src/codegenie/cli.py`:**
   - Add `@cli.group("vuln-index")` and `@vuln_index.command("refresh")`.
   - `--source` choices computed via `click.Choice(["all", *default_feed_registry.feed_sources()])`.
   - Handler: `_apply_migrations(db) → registry.get_feed(s).fetch() → parser → ingest_records → _update_feed_digest`. Raise typed exceptions; click catches via `_EXIT_CODE_DISPATCH`.
   - Extend `_EXIT_CODE_DISPATCH` additively.
   - `_apply_migrations` lazy-imports `alembic`.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/unit/types/test_identifiers_semver.py`**

- Parametrized happy-path for `parse_semver`: `["1.0.0", "0.1.2", "1.2.3-alpha.1", "1.2.3+build.42", "1.2.3-rc.1+build.5"]`.
- Parametrized rejection: `["", "1", "1.2", "01.2.3", "1.2.3-", "1.2.3+", "v1.2.3", "1.2.3 "]`.
- `__all__` membership.

**Test file: `tests/unit/vuln_index/test_parsers.py`** — error model + caps + per-feed parse

```python
from __future__ import annotations
import json
import pytest
from codegenie.vuln_index import VulnParseException
from codegenie.vuln_index.parsers import VulnParseError, _check_depth, _safe_json_load
from codegenie.vuln_index.registry import default_feed_registry

# AC-C1..C3 — error model shape
def test_vuln_parse_error_is_frozen_basemodel():
    e = VulnParseError(reason="bad_json", details={"message": "bad"})
    with pytest.raises(Exception):  # frozen
        e.reason = "bad_cve_id"

def test_vuln_parse_error_rejects_unknown_reason_at_runtime():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VulnParseError(reason="typo", details={})

# AC-S3 — depth boundary (exact)
def test_depth_cap_accepts_exactly_16():
    payload: dict = {}
    cur = payload
    for _ in range(15):
        cur["x"] = {}
        cur = cur["x"]
    _check_depth(payload)  # MUST NOT raise

def test_depth_cap_rejects_17():
    payload: dict = {}
    cur = payload
    for _ in range(16):
        cur["x"] = {}
        cur = cur["x"]
    with pytest.raises(VulnParseException) as exc:
        _check_depth(payload)
    assert exc.value.model.reason == "json_too_deep"
    assert exc.value.model.details["depth"] == 17

# AC-S4 — size boundary (exact)
def test_size_cap_accepts_exactly_1mib():
    raw = b"a" * 1_048_576
    result = _safe_json_load(raw)
    # NOT payload_too_large; json parse fails because "a..." isn't valid JSON
    assert result.is_err() and result.unwrap_err().reason == "bad_json"

def test_size_cap_rejects_1mib_plus_one():
    raw = b"a" * 1_048_577
    result = _safe_json_load(raw)
    assert result.is_err()
    err = result.unwrap_err()
    assert err.reason == "payload_too_large"
    assert err.details == {"size": 1_048_577, "limit": 1_048_576}

# AC-P1 — cve_id smart-constructor invocation
@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_malformed_cve_id(source, cassette):
    feed = default_feed_registry.get_feed(source)
    raw = cassette(source, "malformed-bad_cve.json")
    result = feed.parse_one(raw)
    assert result.is_err() and result.unwrap_err().reason == "bad_cve_id"

# AC-P3 — missing tz
@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_naive_datetime(source, cassette):
    feed = default_feed_registry.get_feed(source)
    raw = cassette(source, "malformed-no_tz.json")
    result = feed.parse_one(raw)
    assert result.is_err() and result.unwrap_err().reason == "missing_tz"

# AC-P2 — ecosystem rejection
@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_unsupported_ecosystem(source, cassette):
    feed = default_feed_registry.get_feed(source)
    raw = cassette(source, "malformed-wrong_eco.json")
    result = feed.parse_one(raw)
    err = result.unwrap_err()
    assert err.reason == "unsupported_ecosystem"
    assert "ecosystem" in err.details

# Happy-path per feed (no `...` stubs)
@pytest.mark.parametrize("source,expected_cve", [
    ("nvd", "CVE-2024-21501"),
    ("ghsa", "GHSA-rv95-896h-c2vc"),
    ("osv", "GHSA-rv95-896h-c2vc"),
])
def test_minimal_record_parses(source, expected_cve, cassette):
    from codegenie.types.identifiers import PackageName
    feed = default_feed_registry.get_feed(source)
    raw = cassette(source, "express-min.json")
    result = feed.parse_one(raw)
    assert result.is_ok()
    rec = result.unwrap()
    assert rec.cve_id == expected_cve
    assert rec.package == PackageName("express")
    assert rec.ecosystem == "npm"   # Literal, NOT Ecosystem.NPM
```

**Test file: `tests/unit/vuln_index/test_parsers_property.py`** — AC-P4

```python
from hypothesis import given, settings
from hypothesis import strategies as st
from codegenie.vuln_index.registry import default_feed_registry

CASSETTE_RAW = [...]  # loaded from cassette corpus at module import

@given(idx=st.integers(min_value=0, max_value=len(CASSETTE_RAW) - 1))
@settings(max_examples=50, deadline=None)
def test_parse_one_is_deterministic(idx):
    raw, source = CASSETTE_RAW[idx]
    feed = default_feed_registry.get_feed(source)
    r1 = feed.parse_one(raw)
    r2 = feed.parse_one(raw)
    assert r1 == r2
```

**Test file: `tests/unit/vuln_index/test_registry.py`** — AC-R1..R6

```python
def test_feed_sources_returns_three_registered_feeds():
    from codegenie.vuln_index.registry import default_feed_registry
    assert default_feed_registry.feed_sources() == ("ghsa", "nvd", "osv")  # sorted

def test_register_vuln_feed_decorator_adds_feed(default_feed_registry_isolated):
    from codegenie.vuln_index.registry import register_vuln_feed
    @register_vuln_feed("_test_feed")
    class TestFeed: ...
    assert "_test_feed" in default_feed_registry_isolated.feed_sources()

def test_explicit_imports_drive_registration():
    """AC-R4: removing one explicit import → registry has only 2 feeds."""
    # Subprocess test: spawn a Python with `codegenie.vuln_index` patched to skip
    # one feed import; assert registry returns 2 sources.
    ...
```

**Test file: `tests/unit/vuln_index/test_ingest.py`** — AC-D1..D6

```python
def test_record_to_row_is_pure(sample_record):
    row1 = _record_to_row(sample_record)
    row2 = _record_to_row(sample_record)
    assert row1 == row2

def test_ingest_records_inserts_new_rows(seeded_index, sample_records):
    stats = ingest_records(seeded_index, sample_records)
    assert stats.inserted == len(sample_records) and stats.skipped == 0

def test_ingest_records_is_idempotent(seeded_index, sample_records):
    ingest_records(seeded_index, sample_records)
    stats = ingest_records(seeded_index, sample_records)
    # ADR-0008 cache-key correctness depends on no spurious row churn on no-op refresh
    assert stats.inserted == 0 and stats.skipped == len(sample_records)

def test_errors_truncated_when_over_100(seeded_index):
    # Synthesize 150 parse errors
    records = [VulnParseError(reason="bad_json", details={"i": i}) for i in range(150)]
    stats = ingest_records(seeded_index, records)
    assert len(stats.errors) == 100
    assert stats.errors_truncated == 50

# AC-D5 — no-op refresh keeps digest byte-identical
def test_no_op_refresh_keeps_digest_byte_identical(seeded_index, sample_records):
    ingest_records(seeded_index, sample_records)
    _update_feed_digest(seeded_index, "nvd", sample_records)
    digest_1 = seeded_index.digest()
    # Re-ingest the SAME records (shuffled)
    import random
    random.shuffle(list(sample_records))
    ingest_records(seeded_index, sample_records)
    _update_feed_digest(seeded_index, "nvd", sample_records)
    digest_2 = seeded_index.digest()
    assert digest_1 == digest_2

# AC-D6 — digest changes when content changes
@pytest.mark.parametrize("mutation", ["add", "remove", "mutate_severity", "mutate_range"])
def test_digest_changes_under_content_change(seeded_index, sample_records, mutation):
    _update_feed_digest(seeded_index, "nvd", sample_records)
    before = seeded_index.digest()
    mutated = apply_mutation(sample_records, mutation)
    _update_feed_digest(seeded_index, "nvd", mutated)
    after = seeded_index.digest()
    assert before != after

# AC-D4 — Hypothesis idempotence
from hypothesis import given, strategies as st
@given(records=st.lists(record_strategy, min_size=1, max_size=20))
@settings(max_examples=30, deadline=None)
def test_ingest_idempotence_property(tmp_path_factory, alembic_upgrade, records):
    db = tmp_path_factory.mktemp("p") / "vi.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    ingest_records(idx, records)
    import random; random.shuffle(records)
    stats_2 = ingest_records(idx, records)
    assert stats_2.inserted == 0 and stats_2.skipped == len(records)
```

**Test file: `tests/integration/cli/test_vuln_index_refresh.py`** — AC-X1..X10, AC-R6

```python
def test_source_choices_include_all_registered_feeds(runner):
    result = runner.invoke(cli, ["vuln-index", "refresh", "--help"])
    assert result.exit_code == 0
    assert "nvd" in result.output and "ghsa" in result.output and "osv" in result.output

# AC-R6 — Open/Closed observable
def test_adding_a_test_feed_surfaces_in_choices(runner, _test_register_feed):
    @_test_register_feed("_test_feed_x")
    class TestFeedX: ...
    result = runner.invoke(cli, ["vuln-index", "refresh", "--help"])
    assert "_test_feed_x" in result.output

# AC-X1, X9 — happy path
def test_refresh_nvd_end_to_end(tmp_path, _test_register_feed, nvd_cassette_dir, runner):
    from codegenie.types.identifiers import PackageName  # NOT PackageId
    @_test_register_feed("nvd_cassette")
    class NvdCassetteFeed:
        source = "nvd_cassette"
        def parse_one(self, raw): return NvdFeed().parse_one(raw)
        def fetch(self, *, since=None, timeout_s=30.0):
            for f in sorted(nvd_cassette_dir.glob("*.json")):
                yield f.read_bytes()
    db = tmp_path / "vi.sqlite"
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "nvd_cassette", "--index-path", str(db)])
    assert result.exit_code == 0
    assert VulnIndex(db).lookup(PackageName("express"), "npm")  # NOT Ecosystem.NPM

# AC-X4 — empty feed
def test_empty_feed_exits_0(tmp_path, _test_register_feed, runner):
    @_test_register_feed("empty")
    class EmptyFeed:
        source = "empty"
        def parse_one(self, raw): ...
        def fetch(self, *, since=None, timeout_s=30.0):
            return iter([])
    db = tmp_path / "vi.sqlite"
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "empty", "--index-path", str(db)])
    assert result.exit_code == 0

# AC-X5 — partial parse error
def test_partial_parse_error_exits_4(tmp_path, _test_register_feed, nvd_malformed_cassette, runner):
    @_test_register_feed("mixed")
    class MixedFeed: ...  # yields one good + one malformed
    db = tmp_path / "vi.sqlite"
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "mixed", "--index-path", str(db)])
    assert result.exit_code == 4

# AC-X6 — all feeds fail HTTP
def test_all_feeds_fail_http_exits_5(tmp_path, _test_register_feed, runner):
    @_test_register_feed("broken")
    class BrokenFeed:
        source = "broken"
        def parse_one(self, raw): ...
        def fetch(self, *, since=None, timeout_s=30.0):
            from urllib.error import URLError
            raise URLError("simulated network failure")
    db = tmp_path / "vi.sqlite"
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "broken", "--index-path", str(db)])
    assert result.exit_code == 5

# AC-X7 — schema not migrated; X9 — auto-apply only on missing
def test_existing_unmigrated_db_exits_7(tmp_path, runner):
    db = tmp_path / "vi.sqlite"
    db.touch()  # exists but no alembic_version
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "nvd", "--index-path", str(db)])
    assert result.exit_code == 7

def test_missing_db_auto_applies_migrations_and_succeeds(tmp_path, _test_register_feed, runner):
    @_test_register_feed("nvd_cassette") ...
    db = tmp_path / "nope.sqlite"  # does NOT exist
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "nvd_cassette", "--index-path", str(db)])
    assert result.exit_code == 0
    assert db.exists()

# AC-X8 — env precedence
def test_env_precedence(tmp_path, monkeypatch, _test_register_feed, runner):
    env_db = tmp_path / "env-vi.sqlite"
    flag_db = tmp_path / "flag-vi.sqlite"
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_PATH", str(env_db))
    # CLI flag wins
    result = runner.invoke(cli, ["vuln-index", "refresh", "--index-path", str(flag_db), "--source", "..."])
    assert flag_db.exists() and not env_db.exists()

# AC-X10 — observability event
def test_refresh_emits_completion_event(...):
    ...  # asserts on captured log events
```

**Test file: `tests/unit/vuln_index/test_module_purity_parsers.py`** — AC-N2

```python
import ast
from pathlib import Path

VULN_INDEX_ROOT = Path("src/codegenie/vuln_index")
FORBIDDEN = {"requests", "httpx", "urllib3", "subprocess"}

def test_no_forbidden_http_libs():
    for py in VULN_INDEX_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                top = n.split(".")[0]
                assert top not in FORBIDDEN, f"forbidden import {n} in {py}"
```

**Test file: `tests/unit/vuln_index/test_cold_start_parsers.py`** — AC-N3, N4

```python
import sys

def test_importing_parsers_does_not_load_alembic_or_urllib():
    for mod in list(sys.modules):
        if mod.startswith(("alembic", "urllib", "codegenie.vuln_index")):
            del sys.modules[mod]
    before = set(sys.modules)
    import codegenie.vuln_index.parsers  # noqa: F401
    after = set(sys.modules) - before
    forbidden = {m for m in after if m.startswith(("alembic", "urllib.request"))}
    assert forbidden == set(), f"cold-start regression: {forbidden}"

def test_importing_cli_does_not_load_alembic():
    for mod in list(sys.modules):
        if mod.startswith(("alembic", "codegenie.cli")):
            del sys.modules[mod]
    before = set(sys.modules)
    import codegenie.cli  # noqa: F401
    after = set(sys.modules) - before
    forbidden = {m for m in after if m.startswith("alembic")}
    assert forbidden == set()
```

**Test file: `tests/unit/vuln_index/test_mypy_strict_meta.py`** — AC-C4

```python
import subprocess, textwrap
def test_invalid_reason_literal_rejected_by_mypy(tmp_path):
    snippet = textwrap.dedent("""
        from codegenie.vuln_index.parsers import VulnParseError
        e: VulnParseError = VulnParseError(reason="typo", details={})  # type: ignore[assignment]
    """)
    f = tmp_path / "snip.py"; f.write_text(snippet)
    # Remove the type:ignore to make mypy bite
    f.write_text(snippet.replace("  # type: ignore[assignment]", ""))
    proc = subprocess.run([sys.executable, "-m", "mypy", "--strict", str(f)], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "reason" in proc.stdout or "Literal" in proc.stdout
```

### Green

Smallest impl: §Implementation outline. ~520 lines (registry + protocol + three feed modules + parsers shared helpers + ingest + CLI). Empty-DB-after-refresh `digest()` value is computed once on first green run and pinned in `tests/unit/vuln_index/test_ingest.py::EMPTY_FEED_DIGEST_LITERAL` (drift sentinel; same pattern as S3-02 AC-H2).

### Refactor

- Lift per-feed CPE/package-ecosystem maps into a shared `feeds/_ecosystems.py` module if duplication crosses three rows per feed; otherwise leave per-feed (rule of three).
- Add a `--dry-run` flag to the CLI that parses + counts but does not UPSERT — operator debugging. Defer to a follow-up story; not in this story's scope.
- Document the deferred opportunities (async fetch, `OutboundUrl` newtype, `parse_many` helper, `--since` cursor support) in the attempt log.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Add `SemverVersion` + `parse_semver` (additive) |
| `src/codegenie/vuln_index/protocol.py` | `Feed(Protocol)` |
| `src/codegenie/vuln_index/registry.py` | `FeedRegistry` + `@register_vuln_feed` decorator |
| `src/codegenie/vuln_index/parsers.py` | `VulnParseError` (Pydantic) + shared `_safe_json_load`, `_check_depth`, `canonical_raw_payload` |
| `src/codegenie/vuln_index/feeds/__init__.py` | Empty / package marker |
| `src/codegenie/vuln_index/feeds/nvd.py` | `NvdFeed` + per-feed CPE map |
| `src/codegenie/vuln_index/feeds/ghsa.py` | `GhsaFeed` |
| `src/codegenie/vuln_index/feeds/osv.py` | `OsvFeed` |
| `src/codegenie/vuln_index/ingest.py` | `IngestStats`, `ingest_records`, `_record_to_row`, `_persist`, `_update_feed_digest` |
| `src/codegenie/vuln_index/__init__.py` | Explicit imports drive registration; updated `__all__` |
| `src/codegenie/errors.py` | Three new typed exceptions (markers-only) |
| `src/codegenie/cli.py` | Add `vuln-index refresh` subgroup; extend `_EXIT_CODE_DISPATCH` |
| `tests/unit/types/test_identifiers_semver.py` | `parse_semver` corpus |
| `tests/unit/vuln_index/test_parsers.py` | Per-feed parsers + caps + error model |
| `tests/unit/vuln_index/test_parsers_property.py` | Hypothesis determinism |
| `tests/unit/vuln_index/test_registry.py` | Registry kernel + observable Open/Closed |
| `tests/unit/vuln_index/test_ingest.py` | Functional-core split + idempotence + digest stability |
| `tests/unit/vuln_index/test_module_purity_parsers.py` | AST fence |
| `tests/unit/vuln_index/test_cold_start_parsers.py` | Cold-start fence |
| `tests/unit/vuln_index/test_mypy_strict_meta.py` | mypy --strict closed-Literal rejection |
| `tests/integration/cli/test_vuln_index_refresh.py` | End-to-end CLI tests, exit-code dispatch, Open/Closed observable |
| `tests/fixtures/cve-feeds/nvd/*.json` | Hand-curated minimal + 5 malformed variants |
| `tests/fixtures/cve-feeds/ghsa/*.json` | Hand-curated minimal + 5 malformed variants |
| `tests/fixtures/cve-feeds/osv/*.json` | Hand-curated minimal + 5 malformed variants |
| `tests/fixtures/cve-feeds/README.md` | Schema documentation |
| `pyproject.toml` | No new deps (alembic already added by S3-02; urllib.request is stdlib) |

## Out of scope

- **`--since` cursor support** — Phase 4 widens delta-fetch semantics; this story does full-fetch only.
- **Async fetch (`AsyncIterator[bytes]` on `Feed.fetch`)** — Phase 8 network parallelism; today's three feeds in serial is well within the 18 s envelope.
- **Real HTTP fetch in tests** — explicit non-goal; everything cassettized. Real-network refresh runs only via operator invocation.
- **`StaleVulnIndex` emission** — S6-04 wires `VulnIndex.is_stale()` at orchestrator init; the CLI does NOT emit this event (it's a refresh, not a workflow).
- **Bundle cache invalidation hooks** — the cache key (S3-05) reads `VulnIndex.digest()` at next workflow start; no push-invalidation.
- **Multi-ecosystem ingest beyond NPM** — `unsupported_ecosystem` parse error is the contract; Phase 4 widens the per-feed CPE/ecosystem maps additively. Parser code does not change.
- **Schema evolution** — S3-02 owns the migration substrate; this story uses the existing `0001` schema and adds no migration.
- **Editing existing `cli.py` argument structure beyond additive extension** — surgical addition only; do NOT refactor adjacent click groups.
- **`OutboundUrl` newtype** — `_FEED_URLS` mapping values stay as `str`; validation happens at urlopen time. Defer until a second consumer (Phase 4 Snyk feed adds outbound HTTP semantics).
- **`Feed.parse_many` convenience method** — consumers use `(feed.parse_one(b) for b in feed.fetch())` generator; do NOT add a method that adds nothing over the generator expression.
- **`OpenRewriteRecipeEngine` Feed analog** — Phase 7 lands a parallel registry for recipe engines; NOT a copy-paste of `FeedRegistry`. Defer until that story is written.

## Notes for the implementer

- **`Feed` registry IS the extensibility surface.** The CLI `--source` choices, the `--source all` iteration order, and `_update_feed_digest`'s per-feed meta-key derive from `default_feed_registry`. Adding a Phase 4 feed (e.g., RustSec, Snyk) means one new file under `feeds/` + one explicit-import row in `__init__.py`. Test AC-R6 is the contract: a `_test_register_feed("_test_feed_x")` MUST surface in `--source` choices without touching `cli.py`. This crosses CLAUDE.md's rule-of-three at three peers and mirrors the established `@register_index_freshness_check` + `@register_dep_graph_strategy` precedents.
- **`VulnParseError` is a frozen Pydantic `BaseModel`, NOT a `CodegenieError` subclass.** S3-01 + S3-02 set the precedent explicitly: typed `.reason` reads contradict the markers-only `CodegenieError` discipline. Closed `Literal[...]` reason set is load-bearing for ADR-0010 sum-type discipline AND for mypy-strict typo-rejection. Adding a new reason variant = one entry in the `Literal[...]` + new test parameter + (if domain semantics shift) a story amendment.
- **`SemverVersion` newtype IS the deferred-from-S3-02 work.** S3-02 Notes pin it explicitly: "S3-03 is the natural parsing boundary." Lands additively in `identifiers.py` (mirroring S3-02's `PackageName` precedent). `AffectedRange.introduced/fixed/last_affected` migrate from `str` to `SemverVersion | None`; tests in S3-02 that used raw strings now exercise valid semver inputs (this is the migration cost — small).
- **Deterministic digest is load-bearing for ADR-0008.** `_update_feed_digest` MUST canonicalize records by `cve_id ASC` before concat. Otherwise: feed-source fetch order is implementation-defined (NVD's delta API has no guaranteed order); same upstream content yields different digests yields Bundle cache thrash on every cron. AC-D5 (no-op refresh keeps digest byte-identical) is the property test that catches this — and the load-bearing AC for ADR-0008 cache stability under feed churn.
- **Parse-error records are EXCLUDED from `_update_feed_digest` input.** Otherwise a transient parse error (upstream malformed for one delta) thrashes the Bundle cache. AC-D2 + AC-X5 pin this. Successful parses contribute to the digest; failed ones contribute to `IngestStats.errors` (capped at 100; see AC-D1).
- **Typed exit-code dispatch via `_EXIT_CODE_DISPATCH`.** Reuse `src/codegenie/cli.py`'s existing pattern. Three new markers-only exceptions in `errors.py`; one additive extension to the dispatch dict. NO inline `sys.exit(N)` in the refresh handler — click catches typed exceptions and converts via the table. Exit code 6 is already mapped to `SecretLikelyFieldNameError`; this story uses `4`, `5`, `7`.
- **`urllib.request` is lazy-imported inside each `Feed.fetch` body, AND `alembic.command.upgrade` is lazy-imported inside `_apply_migrations`.** Cold-start fence is the gate. `import codegenie.vuln_index.parsers` must add neither to `sys.modules`. Production ADR-0005 (cold-start budget) applies by analogy to ANY heavyweight import — `alembic` in particular is a > 10 ms cold-start tax.
- **`_FEED_URLS` allowlist is a security harden.** Without it, a feed-class typo or misconfig could redirect refresh traffic at construction. The allowlist is module-level `Final`; tests verify a feed pointing at a non-allowed URL raises at construction.
- **AST fence forbids `requests` / `httpx` / `urllib3` anywhere in `vuln_index/`.** Story prescribes stdlib `urllib.request` only — bring-in of `httpx` to "fix" the testability story is a discipline violation; the right fix is the `Feed` protocol injection (already pinned).
- **`raw_payload BLOB` 256 KB per-record cap (AC-S5)** is distinct from the 1 MiB top-of-fetch chunk cap (AC-S4). The fetch cap protects the parser; the per-record cap protects the on-disk DB from a single pathological record blowing past 256 KB.
- **Coordinate with S3-05 on cache invalidation timing.** After this story lands, `VulnIndex.digest()` changes ONLY when upstream content changes (AC-D5 guarantees this). S3-05's `BundleCacheGc` runs on a daily cadence regardless. Operator runbook (S9-04) will document `codegenie vuln-index refresh && codegenie cache prune` for explicit invalidation, but it's optional — the cache key reads the digest at workflow start.
- **Deferred design opportunities** (record in attempt log, do NOT implement here): (a) async fetch — Phase 8; (b) `OutboundUrl` newtype — defer until 2nd consumer; (c) `--since` delta-fetch cursor — Phase 4; (d) `Feed.parse_many` convenience — adds nothing over generator expression; (e) per-feed schema validation via `pydantic.TypeAdapter` — defer to a refactor pass when JSON shape drift is the actual bug.
