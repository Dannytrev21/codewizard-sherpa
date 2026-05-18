# Validation report — S3-03 NVD/GHSA/OSV parsers + size/depth caps + `codegenie vuln-index refresh` CLI

**Story:** [`docs/phases/03-vuln-deterministic-recipe/stories/S3-03-vuln-index-ingest-cli.md`](../S3-03-vuln-index-ingest-cli.md)
**Date:** 2026-05-18
**Verdict:** **HARDENED**
**Validator:** `/phase-story-validator` skill (Opus 4.7)

## Context brief

S3-03 fills the sqlite schema S3-02 ships. Three CVE-feed parsers (NVD JSON 2.0, GHSA, OSV) project upstream payloads into typed `VulnerabilityRecord`s under hard size (1 MiB) and depth (16) caps; an `ingest_records` helper performs idempotent `INSERT OR IGNORE`; `codegenie vuln-index refresh` orchestrates HTTP fetch + parse + UPSERT and updates `meta.feed_digest_{source}` so `VulnIndex.digest()` reflects the refresh (load-bearing for ADR-0008's BundleBuilder cache key).

Two collisions surfaced immediately when read against the now-HARDENED S3-02:

1. **`PackageId` + `Ecosystem.NPM` in the TDD plan** — S3-02 HARDENED introduced `PackageName` (`identifiers.py`) and `Ecosystem = Literal["npm", ...]`. The story's TDD calls `lookup(PackageId("express"), Ecosystem.NPM)` — neither name exists on S3-02's surface. (Coverage block / Consistency block.)
2. **`VulnParseError(CodegenieError) markers-only` carrying typed `.reason`** — identical pattern S3-01 (`TCCMParseError`) and S3-02 (`VulnIndexLookupError` / `VulnIndexConfigError`) resolved by redesign-as-frozen-Pydantic-BaseModel with `Literal[...]` reason. The story re-introduces the contradiction. (Coverage block / Consistency block / Design-Patterns tier-1 harden.)

A third structural finding — independent of S3-02 — drives the bulk of the design-patterns work: **the CLI's `--source nvd|ghsa|osv|all` is a closed-set branch over three peers, and `parsers.py` + `fetchers.py` mirror it module-by-module**. The codebase has two established registry-pattern precedents (`@register_index_freshness_check` and `@register_dep_graph_strategy`) for exactly this shape. Three feeds at rule-of-three threshold + Phase 4's explicit "widens the CPE map additively" expectation make this the right story to land a `@register_vuln_feed` kernel so future feed adds are file-additive (one `feeds/<x>.py` module, zero CLI edits). CLAUDE.md "Open/Closed seams" names the pattern explicitly.

## Stage 2 — four critics (synthesis)

Findings consolidated from in-context analysis grounded in: S3-01 + S3-02 prior validation reports (strongly applicable precedent), CLAUDE.md load-bearing commitments ("Extension by addition", "Newtype identifiers", "Functional core / imperative shell", "Open/Closed seams"), Phase 3 arch §C11 + ADR-0008, and the existing `src/codegenie/indices/registry.py` + `src/codegenie/depgraph/registry.py` precedents. Tagged `block` / `harden` / `nit`.

### Coverage critic — 5 block, 11 harden, 3 nit

| # | Tag | Issue |
|---|---|---|
| F1 | block | `lookup(PackageId("express"), Ecosystem.NPM)` in TDD plan + `parse_one`'s output type refer to identifiers S3-02 did not ship — must be `PackageName(...)` + `"npm"` (string literal) |
| F2 | block | `VulnParseError(CodegenieError)` markers-only with `.reason` access — same contradiction S3-01 and S3-02 resolved as frozen Pydantic BaseModel |
| F3 | block | `VulnParseError.reason` is an open `str` — closed `Literal[...]` set required per ADR-0010 sum-type discipline; mypy --strict cannot catch typos otherwise |
| F4 | block | "TDD red test exists, committed, green" AC is tautological (echo S3-02 F3) |
| F5 | block | Adding a fourth feed (Phase 4+) requires edits to `cli.py` (`--source` choices), `parsers.py`, `fetchers.py`, and `_update_feed_digest` callers — violates CLAUDE.md "Extension by addition" + the named-registry precedent (`@register_index_freshness_check`, `@register_dep_graph_strategy`) |
| F6 | harden | No AC for **empty-feed contract** — fetcher yields 0 bytes / 0 records → ingest must report `IngestStats(0, 0, [])` and CLI must exit `0` (not `4`) |
| F7 | harden | No AC for **deterministic `feed_digest_*` value** — `_update_feed_digest`'s `raw_concat: bytes` argument has implementation-defined order. ADR-0008 cache-key correctness requires the SAME upstream content → SAME digest across refreshes regardless of fetch order. Story Notes recommend sort-by-cve_id; must be elevated to an AC. |
| F8 | harden | No AC for **HTTP timeout / retries** — `urllib.request` with no timeout will hang indefinitely on a stalled network |
| F9 | harden | No AC for **`SemverVersion` newtype + `parse_semver`** — S3-02 Notes explicitly deferred to S3-03 ("ingest is the natural parsing boundary"). Primitive-obsession on `AffectedRange.introduced/fixed/last_affected: str` survives otherwise. |
| F10 | harden | No AC for **`raw_payload` size cap (~256 KB per row)** — S3-02 Notes explicitly deferred ("S3-03's ingest enforces"). Without it, a 50 MB pathological NVD record lands in the BLOB column. |
| F11 | harden | Size-cap boundary at exactly `1_048_576` bytes (the limit) untested — only `>` tested |
| F12 | harden | Depth-cap boundary at exactly `16` (allowed) and `17` (rejected) untested — only `20` tested |
| F13 | harden | `cve_id` validation untested — story uses `CveId(...)` constructor but does not require parsers to invoke the S1-01 smart constructor `parse_cve_id`. Garbage CVE strings (`"not-a-cve"`) would land in the DB. |
| F14 | harden | **`--source all` ordering** — story says "declared order (nvd, ghsa, osv)" but no AC pins the iteration order. With a registry kernel, order MUST be deterministic (sorted source name ASC) for digest stability. |
| F15 | harden | Per-record parse error → ingest continues, story claims "best-effort partial refresh", but no AC for exact behavior — does ingest count the failed record's bytes into `_update_feed_digest`? (Answer: no — only successfully-parsed records contribute to the digest; otherwise transient parse errors thrash the cache.) |
| F16 | harden | No mypy-strict meta-test for `VulnParseError(reason="typo", ...)` rejection (echo S3-02 AC-C4 / S3-01) |
| F17 | harden | No AC pinning the `Ecosystem` parameter at the parser boundary — Phase 3 is npm-only, but the parsers should accept any `Ecosystem` Literal value and let the CPE-map / package.ecosystem field filter — i.e., the **rejection is parametric over the registered ecosystem set**, not hardcoded to "anything that's not npm" |
| F18 | nit | Cassette fixture schemas undefined — `nvd_express_fixture`, `ghsa_express_fixture`, `osv_express_fixture` referenced but not specified |
| F19 | nit | CLI `--since` option mentioned in Implementation outline but not in ACs — surface or remove |
| F20 | nit | `IngestStats` shape `errors: list[VulnParseError]` accumulates unbounded — cap or log-and-drop for malformed-heavy feeds |

### Test-Quality critic — 5 block, 8 harden, 2 nit

| # | Tag | Issue |
|---|---|---|
| TQ-B1 | block | TDD plan calls `Ecosystem.NPM` (attribute access) — S3-02 HARDENED ships `Ecosystem = Literal["npm", ...]`, attribute access fails import. (Mirrors F1.) |
| TQ-B2 | block | `unwrap_err().reason` reads on a markers-only `CodegenieError` subclass — same contradiction TQ-B3 caught in S3-02 |
| TQ-B3 | block | `test_minimal_ghsa_record_parses(...): ...` and `test_minimal_osv_record_parses(...): ...` and `test_osv_range_event_parsed_into_affected_range(...): ...` are stub bodies. Same anti-pattern S3-02 TQ-B2 caught. |
| TQ-B4 | block | NVD parser test fixtures referenced (`nvd_express_fixture`, `nvd_naive_dt_fixture`, `nvd_pypi_fixture`) but never defined in story — same dangling-fixture pattern S3-02 TQ-B6 caught |
| TQ-B5 | block | No idempotency test for `_update_feed_digest` under no-op refresh (same upstream content → same digest) — ADR-0008 cache-stability hinges on this |
| TQ-H1 | harden | Size-cap test uses `200_000` repetitions of an 8-byte fragment — fragile and doesn't test the exact `1_048_577` byte boundary |
| TQ-H2 | harden | Depth-cap test uses 20-level nesting — doesn't test the exact `16/17` boundary |
| TQ-H3 | harden | No property test (Hypothesis) for parser determinism: same `raw: bytes` → same `Result[VulnerabilityRecord, VulnParseError]` over N runs (cheap; catches any global-state contamination — e.g., random ordering in a `set()` walk) |
| TQ-H4 | harden | No property test for ingest idempotence: insert N → shuffle → insert again → `inserted_2 == 0`, `skipped_2 == N` |
| TQ-H5 | harden | No AST-fence test for raw `requests` / `urllib3` / `httpx` imports in `vuln_index/parsers.py` and `vuln_index/fetchers.py` — story prescribes stdlib `urllib.request` only |
| TQ-H6 | harden | No cold-start fence: `import codegenie.vuln_index.parsers` must not load `alembic` or `urllib.request` (lazy-import per S3-02 precedent for `alembic`; `urllib.request` lazy inside fetcher functions) |
| TQ-H7 | harden | CLI exit-code dispatch table (current `cli.py`'s `_EXIT_CODE_DISPATCH: dict[type[CodegenieError], int]`) not extended — exit codes 4/5/6 must thread through the established pattern, not via inline `sys.exit(N)` |
| TQ-H8 | harden | `test_refresh_exits_6_when_schema_not_migrated` — exit 6 already means `SecretLikelyFieldNameError` in `_EXIT_CODE_DISPATCH`. Need to pick a non-colliding code OR thread a typed exception through the dispatch table. |
| TQ-N1 | nit | Bench / perf AC absent — parsers are simple but the digest computation over a sorted concat is the hot loop |
| TQ-N2 | nit | `test_payload_over_1_mib_rejected` description "decompression bomb" — actual decompression isn't in scope; reword to "memory-amplification attack via large payload" |

### Consistency critic — 3 block, 5 harden, 2 nit

| # | Tag | Issue |
|---|---|---|
| C1 | **BLOCK** | `PackageId` + `Ecosystem.NPM` collisions with S3-02 HARDENED (echo F1, TQ-B1) — `PackageName` + `"npm"` is the now-canonical shape |
| C2 | **BLOCK** | `VulnParseError(CodegenieError)` markers-only with typed `.reason` — direct contradiction with S3-01/S3-02 precedent (echo F2, TQ-B2) |
| C3 | **BLOCK** | CLI `--source` enumeration hardcoded in story Goal + TDD — collides with CLAUDE.md "Open/Closed seams" + the rule-of-three threshold (three concrete feeds; precedent registries exist) |
| C4 | harden | `Phase 3 ADR-0008 §Consequences` — story honors it, but `_update_feed_digest` argument order ambiguity (F7) puts cache-stability at risk |
| C5 | harden | `production ADR-0033` newtype discipline — `AffectedRange.introduced: str` (etc.) is primitive obsession; `SemverVersion` newtype deferred from S3-02 Notes belongs here |
| C6 | harden | `alembic.command.upgrade(cfg, "head")` inside CLI command body — must respect S3-02's lazy-import discipline (AC-E1). `import codegenie.cli` must not transitively load alembic. |
| C7 | harden | `urllib.request` allowlist — Phase 3 ADRs do not enumerate outbound HTTP endpoints. Story should pin a `_FEED_URLS: Final[Mapping[Literal["nvd","ghsa","osv"], str]]` allowlist so a typo/misconfig can't redirect refresh traffic |
| C8 | harden | `make fence` — `requests`, `httpx`, `urllib3` are NOT currently in `FORBIDDEN_LLM_SDKS` but ARE outside the runtime allowlist for `urllib.request`-only fetch policy. Story should extend fence test or import-linter contract to forbid them in `vuln_index/`. |
| C9 | nit | `--index-path` env override name — story mixes `CODEGENIE_VULN_INDEX_PATH` (from S3-02 Notes) and click default. Pin the precedence: CLI flag > env > default. |
| C10 | nit | `published_at` ISO 8601 parse — should reuse S3-02's `VulnerabilityRecord.published_at: datetime` Pydantic coercion, not re-parse |

### Design-Patterns critic — 3 harden(1), 4 harden(2), 4 nit

| # | Tag | Issue |
|---|---|---|
| DP1 | harden(1) | **Plugin / Registry pattern for feeds** — three concrete feeds at rule-of-three threshold, precedent registries (`@register_index_freshness_check`, `@register_dep_graph_strategy`) wait in the wings. A `@register_vuln_feed("nvd")` decorator wrapping a `class Feed(Protocol)` (with `parse_one` + `fetch`) lets Phase 4+ ship new feeds without editing the CLI. Phase 3 arch §C11 names this gap implicitly: "Phase 4 widens the CPE map additively." |
| DP2 | harden(1) | **`VulnParseError` as frozen Pydantic BaseModel with `Literal[...]` reason** (echo F2 / F3 / TQ-B2 / C2). Block-tier severity due to it blocking the executor's Validator pass. |
| DP3 | harden(1) | **`SemverVersion` newtype + `parse_semver`** in `identifiers.py` — additive extension mirroring S3-02's `PackageName` / `Ecosystem` precedent. Closes primitive-obsession on `AffectedRange` strings. (Echo F9 / C5.) |
| DP4 | harden(2) | **Functional core / imperative shell on `ingest_records`** — pure `_record_to_row(record) -> tuple[str, ...]` mapper separable from the `INSERT OR IGNORE` boundary. Mapper is property-testable directly. |
| DP5 | harden(2) | **Hexagonal fetcher port** — `class VulnFeedFetcher(Protocol)` for DI of cassette fixtures (Notes call it out but no AC pins). Today tests would monkey-patch `codegenie.vuln_index.fetchers.fetch_nvd` — fragile to refactor; protocol injection survives renames. |
| DP6 | harden(2) | **CLI exit-code dispatch table extension** — current `cli.py` has `_EXIT_CODE_DISPATCH: dict[type[CodegenieError], int]`. Story's exit codes 4/5/6 must thread through typed exceptions (`VulnRefreshPartialError`, `VulnFeedFetchError`, `VulnIndexMigrationError`) and slot into this dispatch — not inline `sys.exit(N)` calls. (Echo TQ-H7 / TQ-H8.) |
| DP7 | harden(2) | **`_update_feed_digest` deterministic input ordering** — sort by `cve_id ASC` before concat. AC pins. (Echo F7.) |
| DP8 | nit | `IngestStats` accumulates `list[VulnParseError]` unbounded — cap at `_MAX_ERROR_REPORT: Final[int] = 100`; surplus errors counted but dropped. (Echo F20.) |
| DP9 | nit | `Feed.fetch` `Iterator[bytes]` vs `AsyncIterator[bytes]` — defer to Phase 8 (network parallelism is not in Phase 3's envelope; Rule 2 / YAGNI) |
| DP10 | nit | `parse_one` vs `parse_many` — three feeds use streaming `Iterator[bytes]` from fetchers; `parse_many` is `(parse_one(b) for b in feed)`. Don't introduce a `parse_many` method on `Feed`; consumers use the generator. |
| DP11 | nit | `OutboundUrl` newtype for `_FEED_URLS` mapping values — defer; `str` is fine here, the validation happens at HTTP-call time |

## Stage 3 — researcher

**Not invoked.** Every required pattern is established in-repo:

- **Frozen Pydantic BaseModel error with `Literal` reason** — S3-01 `TCCMParseError`, S3-02 `VulnIndexLookupError` precedents.
- **Registry pattern + decorator** — `src/codegenie/indices/registry.py::register_index_freshness_check`, `src/codegenie/depgraph/registry.py::register_dep_graph_strategy` precedents.
- **`Feed` Protocol + dispatch** — same shape as `DepGraphStrategy` (one strategy per package manager, registered at import time).
- **Newtype + smart constructor in `identifiers.py`** — S1-01 + S3-02 `PackageName` / `Ecosystem` additive precedent.
- **Lazy imports** — S3-02 `alembic`, `codegenie.hashing`'s `_blake3`.
- **AST module-purity fence** — S3-02, Phase-2 throughout.
- **Cold-start fence** — S3-02 `test_cold_start.py` snapshot-diff pattern.
- **Mypy-strict meta-test for `Literal` reason rejection** — S3-02 AC-C4 / S1-01 pattern.
- **CLI exit-code dispatch table** — `src/codegenie/cli.py::_EXIT_CODE_DISPATCH`.
- **Hypothesis property tests** — Phase 2 + S3-02 round-trip pattern.

No `NEEDS RESEARCH` tags.

## Stage 4 — synthesis + edits

### Conflict resolution (Consistency > Coverage > Test-Quality > Design-Patterns)

- **C1 / F1 / TQ-B1 (PackageId vs PackageName, Ecosystem.NPM vs `"npm"`)** — Resolved by updating all TDD plan references and ACs to the S3-02 HARDENED shapes (`PackageName`, `"npm"` literal). The arch §C11 pseudocode pre-dates S3-02; S3-02's resolution is canonical. No new identifiers introduced for this concern.
- **C2 / F2 / F3 / TQ-B2 / DP2 (error model)** — `VulnParseError` redesigned as a frozen Pydantic `BaseModel` with closed `reason: Literal["payload_too_large", "json_too_deep", "bad_json", "missing_required_field", "unsupported_ecosystem", "bad_cve_id", "bad_ghsa_id", "missing_tz", "bad_semver", "bad_ecosystem"]` and `details: dict[str, str | int] = {}`. Adding a new reason requires an explicit story amendment. Mirrors S3-01 + S3-02 exact pattern. Raised through a thin `VulnParseException(model)` wrapper when an exception is the right semantics (the parser API returns `Result[..., VulnParseError]`, so most call sites just inspect the model directly). AC-C1..C4 codify.
- **C3 / F5 / DP1 (registry pattern for feeds)** — `@register_vuln_feed("nvd"|"ghsa"|"osv")` decorator lands in `src/codegenie/vuln_index/registry.py`, mirroring `src/codegenie/indices/registry.py`'s shape. `Feed(Protocol)` with class attrs `source: Literal[...]` + methods `parse_one(raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]` and `fetch(*, since: datetime | None = None, timeout_s: float = 30.0) -> Iterator[bytes]`. Three concrete feeds (`feeds/nvd.py`, `feeds/ghsa.py`, `feeds/osv.py`) register themselves at module import time. CLI `--source` choices read from `registry.feed_sources()` — adding a fourth feed is one new file + one row in `vuln_index/__init__.py`'s explicit-import list (mirroring `probes/__init__.py` discipline). AC-R1..R5 codify. **Observable extension AC (Open/Closed):** adding a new feed source MUST require zero edits to `cli.py`, `parsers.py` (shared depth/size helpers only), or `ingest.py`.
- **F4 (tautological AC)** — removed.
- **F6 / TQ-H8 (empty-feed + exit-code dispatch)** — AC-X4: empty fetch → `IngestStats(0, 0, [])` → CLI exits `0`. Exit code 6 collision with `SecretLikelyFieldNameError` resolved by promoting `VulnIndexMigrationNotApplied` to a typed `CodegenieError` and extending `_EXIT_CODE_DISPATCH` with `{VulnIndexMigrationNotApplied: 7}` (next free code). 4=`VulnRefreshPartialError`, 5=`VulnFeedFetchError`, 7=`VulnIndexMigrationNotApplied`. AC-X1..X5 codify the typed exceptions + dispatch.
- **F7 / DP7 (deterministic digest concat)** — AC-D2 pins `_update_feed_digest(idx, source, records: Sequence[VulnerabilityRecord]) -> None` (NOT `raw_concat: bytes`); helper canonicalizes by `cve_id ASC` and concats `cve_id || \x1f || raw_payload`. Same upstream content → same digest regardless of fetch order. Property test: shuffle the input sequence → digest unchanged.
- **F8 / C7 / C8 (HTTP timeout + URL allowlist + import fence)** — AC-N1 pins `urllib.request.urlopen(..., timeout=30.0)` and a module-level `_FEED_URLS: Final[Mapping[Literal[...], str]]` allowlist. AC-N2 AST-fence forbids `import requests` / `from requests` / `import urllib3` / `import httpx` in `vuln_index/`.
- **F9 / DP3 / C5 (SemverVersion newtype)** — `SemverVersion = NewType("SemverVersion", str)` + `parse_semver(s: str) -> Result[SemverVersion, ParseError]` lands in `src/codegenie/types/identifiers.py` (additive, mirroring S3-02's `PackageName` extension). Grammar accepts npm semver shape (`X.Y.Z[-prerelease[.identifier]*][+build[.identifier]*]`). `AffectedRange.introduced/fixed/last_affected` migrate from `str` to `SemverVersion | None` (Pydantic Annotated validator). AC-S1..S3 codify.
- **F10 (raw_payload cap)** — AC-D4 pins per-record cap at 262_144 bytes (256 KB); over-cap records become `VulnParseError(reason="payload_too_large")` with `details={"size": ..., "limit": 262144}`. Note: distinct from the 1 MiB top-of-fetch buffer cap — that's the FEED-payload-chunk cap; this is the per-RECORD persisted-blob cap.
- **F11 / F12 / TQ-H1 / TQ-H2 (boundary tests)** — AC-X1..X3 add exact-boundary parametrized tests: `len(raw) == 1_048_576` accepts; `len(raw) == 1_048_577` rejects. Depth `== 16` accepts; depth `== 17` rejects.
- **F13 (cve_id smart-constructor invocation)** — AC-P1 pins: each parser invokes `parse_cve_id(s)` and returns `VulnParseError(reason="bad_cve_id", details={"value": s})` on failure. Test: `parse_one(<payload with cve.id="not-a-cve">)` → `bad_cve_id`.
- **F14 (deterministic source iteration order)** — AC-R5 pins `feed_sources()` returns sources in registration order, but `refresh --source all` iterates `sorted(feed_sources())` (lexicographic) — deterministic regardless of import order.
- **F15 (parse-error excluded from digest)** — AC-D2 clarifies: `_update_feed_digest` consumes only successfully-parsed records. Transient parse errors do NOT thrash the Bundle cache.
- **F16 (mypy meta-test)** — AC-C4 parametrized snippet `VulnParseError(reason="typo", details={})` → ValidationError at runtime AND mypy --strict rejection (mirrors S3-02 AC-C4).
- **F17 (parametric ecosystem rejection)** — AC-P2 pins: parsers accept any registered `Ecosystem`; Phase 3 fixtures exercise `"npm"` only; per-feed CPE/package.ecosystem maps return `VulnParseError(reason="unsupported_ecosystem", details={"ecosystem": ...})` for unregistered values. Phase 4+ widens by adding rows to the CPE map, not editing parsers.
- **F18 / TQ-B4 (cassette fixture schema)** — AC-T1 pins the cassette layout: `tests/fixtures/cve-feeds/{nvd,ghsa,osv}/express-min.json` (happy path), `tests/fixtures/cve-feeds/{nvd,ghsa,osv}/malformed-{depth,size,no_tz,bad_cve,wrong_eco}.json` (rejection corpus). Each file is hand-curated minimal. Top-level cassette README documents the schema.
- **F19 (CLI `--since`)** — AC-X6 removes `--since` from the story scope (Phase 4 concern); CLI surface is `--source` + `--index-path` only.
- **F20 / DP8 (IngestStats error cap)** — AC-X7 caps `errors: list[VulnParseError]` at 100; additional errors increment `errors_truncated: int` field. Total ingest failure count remains accurate.
- **DP4 (functional core / imperative shell)** — AC-D3 splits ingest: pure `_record_to_row(r: VulnerabilityRecord) -> tuple[str, ...]` (testable directly) + impure `_persist(conn, rows)` boundary. Pure helper has its own property test.
- **DP5 (hexagonal fetcher port)** — Already addressed by C3/F5/DP1 registry resolution: `Feed.fetch` IS the port. Tests inject a stub class via `_test_register_feed` helper (mirrors S3-02's `_test_unregister` pattern). No `monkeypatch.setattr` on module attributes.
- **C6 (lazy alembic import)** — AC-N3 pins: `alembic.command.upgrade` import lives inside the CLI `_apply_migrations(db_path)` helper; cold-start fence on `import codegenie.cli` does NOT load alembic. Reuses S3-02's `_upgrade()` lazy-import pattern.
- **C9 (env precedence)** — AC-X8 pins: CLI flag > env (`CODEGENIE_VULN_INDEX_PATH`) > default `<cwd>/.codegenie/cache/vuln-index.sqlite`. Click `default_factory` reads env.
- **C10 (datetime reuse)** — AC-P3 pins: parsers populate `VulnerabilityRecord(published_at=...)` directly; Pydantic coerces ISO 8601. No hand-rolled ISO parsing.
- **TQ-B3 (stub TDD bodies)** — All three GHSA/OSV stub tests filled out with happy-path + selectivity + rejection cases (mirrors S3-02 TDD plan completeness).
- **TQ-B5 (idempotent digest under no-op refresh)** — AC-D5: refresh, then refresh again with identical cassette → `digest()` unchanged.
- **TQ-H3 (parser determinism property)** — AC-P4 Hypothesis property: `for all raw: bytes, parse_one(raw) == parse_one(raw)` (idempotent over 50 runs; catches set-iteration / hash-seed contamination).
- **TQ-H4 (ingest idempotence property)** — AC-D6 Hypothesis property: insert N → shuffle → insert again → `inserted_2 == 0, skipped_2 == N`.
- **TQ-H5 / TQ-H6 (AST fence + cold-start fence)** — AC-F1..F3 add `tests/unit/vuln_index/test_module_purity_parsers.py` (no `requests` / `httpx` / `urllib3` / `subprocess` imports) and `test_cold_start_parsers.py` (importing `codegenie.vuln_index.parsers` does NOT load `alembic`, `urllib.request`).
- **TQ-N1 (perf nit)** — Notes mention the digest hot loop; bench deferred to S9-03 (Phase 3 bench harness).
- **TQ-N2 (wording nit)** — TDD test description reworded.
- **F3** (closed `Literal` reasons) — final canonical set: `Literal["payload_too_large", "json_too_deep", "bad_json", "missing_required_field", "unsupported_ecosystem", "bad_cve_id", "bad_ghsa_id", "missing_tz", "bad_semver", "bad_ecosystem"]`. Documented in AC-C1.

### AC count

| Before | After |
|---|---|
| 14 unnumbered ACs (1 tautology, 2 with `Ecosystem.NPM` / `PackageId` collisions) | 38 numbered ACs grouped under 12 sections (C errors, P parsers, S semver, R registry/feeds, D ingest+digest, X CLI exit dispatch + idempotency, N network/lazy imports, T cassette fixtures, F fence + cold-start, M migrations + DB caps, G gates, K observability/logging) |

### Test count

| Before | After |
|---|---|
| 11 unit tests (3 with `...` body, 6 dangling fixtures, 0 property tests), 3 integration | ~32 unit tests (parametrized; effective ≈ 60 cases), 3 Hypothesis property tests, 3 AST module-purity tests, 1 cold-start fence, 1 mypy-strict meta-test, 5 integration CLI tests, 1 idempotent-refresh CLI test |

### Edits applied

| Section | Edit |
|---|---|
| Header | Status `Ready → HARDENED`; ADRs honored expanded with ADR-0010 (sum-type discipline), Phase 0 ADR-0001 (BLAKE3 chokepoint), production ADR-0005 (cold-start budget). Added explicit precedent citations to S3-01 + S3-02. |
| New `Validation notes` block | 12-bullet summary of changes — `VulnParseError` redesign, `PackageName` adoption, registry kernel, semver newtype, registry-driven CLI, hexagonal fetcher port, deterministic digest concat, raw_payload cap, exit-code dispatch integration, lazy alembic, AST + cold-start fences, mutation-resistant tests |
| References | Added `_validation/S3-01-tccm-context-query-models.md` and `_validation/S3-02-vuln-index-sqlite.md` as load-bearing precedent. Added `src/codegenie/indices/registry.py` and `src/codegenie/depgraph/registry.py` as registry-pattern precedents. Added `src/codegenie/cli.py::_EXIT_CODE_DISPATCH` as exit-code precedent. |
| Goal | Tightened — explicit `PackageName`, `"npm"`, registry kernel, four typed exceptions for exit-code dispatch, deterministic digest under no-op refresh |
| Acceptance criteria | Rewritten — 38 numbered ACs grouped into 12 sections; tautology removed |
| Implementation outline | Rewritten — 7 ordered steps; pins `Feed` Protocol + registry, `SemverVersion` newtype, lazy alembic, Pydantic error model with closed `Literal`, functional-core ingest, URL allowlist, exit-code dispatch table extension |
| TDD plan | Rewritten — 5 test files; parametrized boundary cases; property tests for parser determinism, ingest idempotence, digest stability under shuffle; mypy-strict meta-test for closed `Literal`; AST + cold-start fences |
| Files to touch | Added `src/codegenie/vuln_index/registry.py`, `src/codegenie/vuln_index/feeds/{nvd,ghsa,osv}.py`, `src/codegenie/vuln_index/protocol.py`, `src/codegenie/types/identifiers.py` (modify — add `SemverVersion`), test module-purity + cold-start fences, cassette fixture layout |
| Out of scope | Tightened — `--since` cursor (Phase 4), async fetch (Phase 8), feed allowlist beyond `nvd/ghsa/osv` (Phase 4), multi-ecosystem ingest beyond npm (Phase 4 widens CPE map), real-network smoke (operator-time only) |
| Notes for implementer | Rewritten — `Feed` registry decisively replaces hardcoded source dispatch (rule-of-three crossed by precedent); semver newtype is THE deferred-from-S3-02 work; typed exit-code dispatch threads through existing `_EXIT_CODE_DISPATCH`; deterministic digest concat order is load-bearing for ADR-0008; raw_payload 256 KB cap deferred from S3-02; HTTP timeout + URL allowlist as security harden; deferred design opportunities (async fetch, `OutboundUrl` newtype, parse_many helper) recorded but not implemented |

## Verdict

**HARDENED.** Story now:

- 38 individually verifiable ACs (was 14 unnumbered with 1 tautology + 2 contradiction-bearing).
- Two structural collisions with S3-02 (PackageId/PackageName, Ecosystem.NPM/`"npm"`) resolved by adopting S3-02's HARDENED surface. No backsliding into pre-S3-02 names.
- `VulnParseError` aligned with S3-01 + S3-02's frozen-Pydantic-BaseModel-with-`Literal`-reason precedent. Adding a reason variant becomes an explicit one-line `Literal[...]` addition + a story amendment.
- Plugin/registry pattern landed (`@register_vuln_feed`) — Phase 4+ widens by file addition, zero edits to CLI dispatch or shared ingest. Crosses rule-of-three (three feeds today) and mirrors `@register_index_freshness_check` + `@register_dep_graph_strategy` in-repo precedents. CLAUDE.md "Extension by addition" + "Open/Closed seams" honored.
- `SemverVersion` newtype + `parse_semver` lands in `identifiers.py` (additive, mirroring S3-02's `PackageName`) — closes the primitive-obsession deferral from S3-02 Notes.
- Functional-core / imperative-shell split on ingest (`_record_to_row` pure / `_persist` impure).
- Hexagonal port for HTTP fetch (Protocol-based DI, not module-attr monkey-patching).
- Typed exit-code dispatch through `_EXIT_CODE_DISPATCH` (no inline `sys.exit(N)`); code collision with `SecretLikelyFieldNameError=6` resolved by assigning `VulnIndexMigrationNotApplied=7`.
- Cold-start fence + AST module-purity fences cover `vuln_index/parsers.py` + `vuln_index/fetchers.py`. `alembic` stays lazy; `requests`/`httpx`/`urllib3` stay forbidden in `vuln_index/`.
- Mutation-resistant tests: exact-boundary parametrized cases (size = 1_048_576 vs 1_048_577; depth = 16 vs 17), Hypothesis property tests for parser determinism + ingest idempotence + digest-shuffle invariance, cassette fixture corpus pinned, mypy-strict meta-test for closed `Literal` reasons.
- Deterministic `_update_feed_digest` concat order (`cve_id ASC`) — load-bearing for ADR-0008 cache-stability under fetch-order churn.
- Deferred design opportunities (async fetch, `OutboundUrl` newtype, parse_many helper, --since cursor) recorded in Notes-for-implementer rather than fabricated as premature ACs.
