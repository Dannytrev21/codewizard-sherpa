# Story S3-03 — NVD 2.0 / GHSA / OSV ingest parsers + size/depth caps + `codegenie vuln-index refresh` CLI

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** Ready
**Effort:** M
**Depends on:** S3-02
**ADRs honored:** Phase 3 ADR-0008 (`vuln_index.digest` participates in Bundle cache key — feed digests update on refresh), production ADR-0005 (no LLM SDK in this loop — pure parsers), production ADR-0033 (newtype identifiers + smart constructors)

## Context

S3-02 ships the sqlite schema; this story fills it. Three CVE-feed parsers (NVD JSON 2.0, GHSA, OSV) project upstream payloads into typed `VulnerabilityRecord` via smart constructors with **hard size and depth caps** (`1 MiB` per payload, JSON depth `16`) — a malformed-or-malicious feed must never crash the parser or trigger a memory blow-up. The `codegenie vuln-index refresh` CLI subcommand orchestrates HTTP fetch + parse + idempotent UPSERT into the sqlite store, then updates `meta.feed_digest_{source}` so `VulnIndex.digest()` (consumed by `BundleBuilder` cache-key, ADR-0008) reflects the refresh.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C11` — "Each feed projects into typed Pydantic records via smart constructors with size (1 MiB) + depth (16) caps." + "`codegenie vuln-index refresh` pulls NVD JSON 2.0 delta, GHSA `since`-cursor, OSV via GCS zsync."
  - `../phase-arch-design.md §Edge cases` — malformed/over-sized payloads must fail typed, not OOM.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Consequences` — refresh updates `vuln_index.digest`; Bundle cache hit rate drops slightly after refresh; correctness preserved.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — "Smart-constructor parsers with 1 MiB / depth-16 caps; `codegenie vuln-index refresh` CLI subcommand." + done criterion "`codegenie vuln-index refresh` end-to-end populates a test sqlite."
- **Existing code:**
  - `src/codegenie/vuln_index/` (S3-02) — `VulnIndex`, `VulnerabilityRecord`, sqlite schema; reuse `_raw_insert` and `_raw_set_meta`.
  - `src/codegenie/cli.py` (Phase 0) — click root; add the `vuln-index` subgroup here.
  - `src/codegenie/result.py` — `Result[T, E]` for smart-constructor returns.
  - `src/codegenie/errors.py` — `CodegenieError` markers-only base.
  - `src/codegenie/hashing.py` — `content_hash`/`bytes_hash` for per-feed digest computation.

## Goal

`codegenie.vuln_index.parsers` exposes `NvdParser`, `GhsaParser`, `OsvParser` smart-constructor parsers with 1 MiB / depth-16 caps; `codegenie vuln-index refresh [--source nvd|ghsa|osv|all]` CLI command end-to-end fetches, parses, idempotently UPSERTs into the sqlite store, updates `meta.feed_digest_*`, and exits `0` on success, `4` on any per-record validation failure (logged + counted, but ingest continues to honor "best-effort partial refresh").

## Acceptance criteria

- [ ] New module `src/codegenie/vuln_index/parsers.py` exports `NvdParser`, `GhsaParser`, `OsvParser`, `VulnParseError`. Each parser exposes `classmethod parse_one(raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]`.
- [ ] **Size cap (1 MiB):** `parse_one(raw)` returns `Result.err(VulnParseError(reason="payload_too_large", size=len(raw), limit=1048576))` when `len(raw) > 1_048_576`. Hard rejection BEFORE invoking the JSON parser — defends against decompression bombs in the upstream cassette path.
- [ ] **Depth cap (16):** parsers use `json.loads(raw)` then walk the result with a depth-tracking visitor that raises `VulnParseError(reason="json_too_deep", depth=...)` if any nesting exceeds 16. Centralize via `_check_depth(value, max_depth=16) -> None` helper.
- [ ] **NVD 2.0 shape:** `NvdParser.parse_one` extracts `cve.id` → `CveId`; `cve.configurations[].nodes[].cpeMatch[]` projected to `(package, ecosystem)` via a small `_cpe_to_package_id` map (npm-only in Phase 3; raise `VulnParseError(reason="unsupported_ecosystem", cpe=...)` on non-`a:` `a:nodejs:*` rows); `cve.metrics.cvssMetricV31[0].cvssData.baseSeverity` → `severity` (lowercase).
- [ ] **GHSA shape:** `GhsaParser.parse_one` reads `id` (`GHSA-*` prefix expected; if not, `reason="bad_ghsa_id"`); `vulnerabilities[].package.ecosystem` matches `Ecosystem`; `vulnerabilities[].vulnerable_version_range` parsed to `AffectedRange`.
- [ ] **OSV shape:** `OsvParser.parse_one` reads `id`, `affected[].package.{ecosystem, name}`, `affected[].ranges[].events[]` (`introduced` / `fixed` events) → `AffectedRange`.
- [ ] All three parsers convert `published` (ISO 8601) → `datetime` with `tzinfo=timezone.utc`; missing or naive datetimes → `VulnParseError(reason="missing_tz")`.
- [ ] **Idempotent ingest:** `ingest_records(idx: VulnIndex, records: Iterable[VulnerabilityRecord]) -> IngestStats` performs `INSERT OR IGNORE` against the `(cve_id, ecosystem, package, introduced)` unique constraint (S3-02); re-ingesting the same feed twice produces zero net inserts. Returns `IngestStats(inserted: int, skipped: int, errors: list[VulnParseError])`.
- [ ] **Per-feed digest update:** after a successful refresh, `_update_feed_digest(idx, source, raw_payload_concat: bytes)` writes `meta.feed_digest_{source} = blake3(<concat>)`; `VulnIndex.digest()` reflects the change (verified end-to-end).
- [ ] **CLI:** `codegenie vuln-index refresh [--source nvd|ghsa|osv|all] [--index-path PATH]` click subcommand. `--source all` runs all three parsers in declared order (`nvd, ghsa, osv`). `--index-path` defaults to `<repo>/.codegenie/cache/vuln-index.sqlite` (or `CODEGENIE_VULN_INDEX_PATH` env override).
- [ ] **CLI exit codes:** `0` on full success (any inserts/skips); `4` on any per-record parse error (still partial-refresh; non-zero so CI can fail loud); `5` on full HTTP fetch failure (network down); `6` on schema migration not applied (caller must `alembic upgrade head` first).
- [ ] **CLI fetches via cassettes in tests:** real-network calls live behind `codegenie.vuln_index.fetchers` (`fetch_nvd(since: datetime) -> Iterable[bytes]`, etc.); a `tests/fixtures/cve-feeds/{nvd,ghsa,osv}/` cassette path stubs each via `pytest`'s `monkeypatch`. Real HTTP is NEVER invoked in tests.
- [ ] **End-to-end test:** `codegenie vuln-index refresh --source nvd --index-path tmp/vi.sqlite` (after `alembic upgrade head`) populates the sqlite with the fixture's record set; `VulnIndex(tmp/vi.sqlite).lookup(PackageId("express"), Ecosystem.NPM)` returns a non-empty list.
- [ ] **Refresh updates `digest()`:** call `VulnIndex.digest()` before refresh, run refresh against a fresh fixture, call `digest()` again — values differ.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean. No `subprocess`/`os.system`/`eval`/`exec`/`shell=True` patterns (forbidden-patterns hook gate).

## Implementation outline

1. `src/codegenie/vuln_index/parsers.py`:
   - `class VulnParseError(CodegenieError)` markers-only; carries `reason` + arbitrary `**details`.
   - Module-level `_MAX_PAYLOAD_BYTES: Final[int] = 1_048_576` and `_MAX_JSON_DEPTH: Final[int] = 16`.
   - `def _check_depth(value: object, max_depth: int = _MAX_JSON_DEPTH, _current: int = 0) -> None` — recursive walk; raises `VulnParseError(reason="json_too_deep", depth=_current)` at the breach.
   - `def _safe_json_load(raw: bytes) -> Result[object, VulnParseError]` — size-cap check then `json.loads(raw)`, catching `json.JSONDecodeError` → `VulnParseError(reason="bad_json", message=...)`.
   - Three classes (`NvdParser`, `GhsaParser`, `OsvParser`) each with `@classmethod parse_one(cls, raw)`.
2. `src/codegenie/vuln_index/ingest.py`:
   - `class IngestStats(BaseModel)` with `inserted`, `skipped`, `errors`.
   - `def ingest_records(idx, records) -> IngestStats` — `INSERT OR IGNORE` loop, returns stats.
   - `def _update_feed_digest(idx, source, raw_concat) -> None` — writes `meta.feed_digest_{source}`.
3. `src/codegenie/vuln_index/fetchers.py`:
   - `def fetch_nvd(since: datetime | None) -> Iterator[bytes]`, `def fetch_ghsa(cursor: str | None) -> Iterator[bytes]`, `def fetch_osv() -> Iterator[bytes]`. Each yields raw record payloads. Use `urllib.request` (no extra deps; stays in the runtime fence).
4. `src/codegenie/cli.py`:
   - Add `@cli.group("vuln-index")` and `@vuln_index.command("refresh")` with `--source`, `--index-path`, `--since` options.
   - Wire to `VulnIndex(path)`, run `alembic.command.upgrade(cfg, "head")` first (or fail with exit 6 if not on head), iterate parsers, call `ingest_records`, call `_update_feed_digest`.
5. Map exit codes per ACs; emit a final structured summary line via `codegenie.logging`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/vuln_index/test_parsers.py`

```python
import json
import pytest
from codegenie.vuln_index.parsers import NvdParser, GhsaParser, OsvParser, VulnParseError

class TestSizeAndDepthCaps:
    def test_payload_over_1_mib_rejected(self):
        # Hard cap before json.loads — defends against compression-bomb feeds
        raw = b"{" + b'"x":1,' * 200_000 + b'"end":1}'  # > 1 MiB
        result = NvdParser.parse_one(raw)
        assert result.is_err() and result.unwrap_err().reason == "payload_too_large"

    def test_json_depth_over_16_rejected(self):
        # Nested 20 levels deep; depth-cap defends parser stack/memory
        payload: dict = {}
        cur = payload
        for _ in range(20):
            cur["x"] = {}
            cur = cur["x"]
        result = NvdParser.parse_one(json.dumps(payload).encode())
        assert result.is_err() and result.unwrap_err().reason == "json_too_deep"

    def test_invalid_json_rejected(self):
        result = NvdParser.parse_one(b"{not valid json")
        assert result.is_err() and result.unwrap_err().reason == "bad_json"

class TestNvdParser:
    def test_minimal_nvd_record_parses(self, nvd_express_fixture):
        # Arrange: CVE-2024-21501 in NVD 2.0 shape (fixture under tests/fixtures/cve-feeds/nvd/)
        # Act
        result = NvdParser.parse_one(nvd_express_fixture)
        # Assert: smart-ctor returns typed VulnerabilityRecord with correct cve_id + package
        assert result.is_ok()
        record = result.unwrap()
        assert record.cve_id == "CVE-2024-21501"
        assert record.ecosystem.value == "npm"
        assert record.package == "express"
        assert record.severity == "high"

    def test_nvd_missing_timezone_rejected(self, nvd_naive_dt_fixture):
        assert NvdParser.parse_one(nvd_naive_dt_fixture).unwrap_err().reason == "missing_tz"

    def test_nvd_unsupported_ecosystem_rejected(self, nvd_pypi_fixture):
        # Phase 3 ingests npm only; pypi rows are typed errors, not silent drops
        assert NvdParser.parse_one(nvd_pypi_fixture).unwrap_err().reason == "unsupported_ecosystem"

class TestGhsaParser:
    def test_ghsa_id_prefix_enforced(self):
        result = GhsaParser.parse_one(json.dumps({"id": "NOT-GHSA-123", "vulnerabilities": []}).encode())
        assert result.is_err() and result.unwrap_err().reason == "bad_ghsa_id"

    def test_minimal_ghsa_record_parses(self, ghsa_express_fixture): ...

class TestOsvParser:
    def test_minimal_osv_record_parses(self, osv_express_fixture): ...
    def test_osv_range_event_parsed_into_affected_range(self, osv_range_fixture): ...
```

Test file: `tests/unit/vuln_index/test_ingest.py`

```python
def test_ingest_records_inserts_new_rows(seeded_index, sample_records):
    stats = ingest_records(seeded_index, sample_records)
    assert stats.inserted == len(sample_records) and stats.skipped == 0

def test_ingest_records_is_idempotent(seeded_index, sample_records):
    ingest_records(seeded_index, sample_records)
    stats = ingest_records(seeded_index, sample_records)
    # ADR-0008 cache-key correctness depends on no spurious row churn on no-op refresh
    assert stats.inserted == 0 and stats.skipped == len(sample_records)

def test_update_feed_digest_changes_index_digest(seeded_index):
    before = seeded_index.digest()
    _update_feed_digest(seeded_index, "nvd", b"new-feed-bytes")
    assert seeded_index.digest() != before
```

Test file: `tests/integration/cli/test_vuln_index_refresh.py`

```python
def test_refresh_nvd_end_to_end(tmp_path, monkeypatch, nvd_cassette_dir, runner):
    # monkeypatch fetch_nvd to yield bytes from the fixture cassette
    monkeypatch.setattr("codegenie.vuln_index.fetchers.fetch_nvd",
                        lambda since=None: iter(nvd_cassette_dir.glob("*.json")))
    db = tmp_path / "vi.sqlite"
    alembic_upgrade(db)
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "nvd", "--index-path", str(db)])
    assert result.exit_code == 0
    assert VulnIndex(db).lookup(PackageId("express"), Ecosystem.NPM)

def test_refresh_exits_6_when_schema_not_migrated(tmp_path, runner):
    db = tmp_path / "vi.sqlite"   # never upgraded
    result = runner.invoke(cli, ["vuln-index", "refresh", "--index-path", str(db)])
    assert result.exit_code == 6

def test_refresh_exits_4_on_per_record_parse_error(tmp_path, monkeypatch, nvd_malformed_cassette, runner):
    # Some records parse; one is malformed (over depth cap)
    monkeypatch.setattr("codegenie.vuln_index.fetchers.fetch_nvd",
                        lambda since=None: iter(nvd_malformed_cassette))
    db = tmp_path / "vi.sqlite"
    alembic_upgrade(db)
    result = runner.invoke(cli, ["vuln-index", "refresh", "--source", "nvd", "--index-path", str(db)])
    assert result.exit_code == 4   # partial refresh; CI fails loud
```

### Green

Smallest impl: §Implementation outline; ~360 lines (parsers dominate; CLI is ~50 lines).

### Refactor

- Extract a `_BaseParser` base class with `parse_one` template that calls `_safe_json_load`, `_check_depth`, then the subclass's `_project_record(parsed: object) -> Result[VulnerabilityRecord, VulnParseError]`. Three parsers become ~30 lines each.
- Push the CPE → `PackageId` map into a module-level `_CPE_VENDOR_TO_ECOSYSTEM: Final[dict[str, Ecosystem]]` so adding a new ecosystem in Phase 4 is one row, not branching code.
- Add a `--dry-run` flag to the CLI that parses + counts but does not UPSERT — operator debugging.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/vuln_index/parsers.py` | Three parsers + `VulnParseError` |
| `src/codegenie/vuln_index/ingest.py` | `ingest_records`, `IngestStats`, `_update_feed_digest` |
| `src/codegenie/vuln_index/fetchers.py` | NVD / GHSA / OSV HTTP fetch helpers |
| `src/codegenie/cli.py` | Add `vuln-index refresh` subgroup + command |
| `tests/unit/vuln_index/test_parsers.py` | Unit tests for caps + parsers |
| `tests/unit/vuln_index/test_ingest.py` | Idempotency + digest-update |
| `tests/integration/cli/test_vuln_index_refresh.py` | End-to-end CLI test |
| `tests/fixtures/cve-feeds/nvd/*.json` | Hand-curated minimal CVE-2024-21501 fixture |
| `tests/fixtures/cve-feeds/ghsa/*.json` | Hand-curated GHSA fixture |
| `tests/fixtures/cve-feeds/osv/*.json` | Hand-curated OSV fixture |

## Out of scope

- **Real HTTP fetch in tests** — explicit non-goal; everything cassettized. Real-network refresh runs only via operator invocation.
- **`StaleVulnIndex` emission** — S6-04 wires `VulnIndex.is_stale()` at orchestrator init; the CLI does NOT emit this event (it's a refresh, not a workflow).
- **Bundle cache invalidation hooks** — the cache key (S3-05) reads `VulnIndex.digest()` at next workflow start; no push-invalidation.
- **Multi-ecosystem ingest** — `unsupported_ecosystem` parse error is the contract; Phase 4 widens the CPE map additively.
- **Schema evolution** — S3-02 owns the migration substrate; this story uses the existing `0001` schema.
- **Editing existing `cli.py` argument structure** — surgical addition only; do NOT refactor adjacent click groups.

## Notes for the implementer

- **Stay inside `ALLOWED_BINARIES`.** No `subprocess` to `curl`/`wget`; use `urllib.request` (stdlib). If `alembic` is invoked via `python -m alembic`, that's fine; preferred is `alembic.command.upgrade(cfg, "head")` programmatically — no subprocess at all.
- **Depth check must NOT recurse on dict values infinitely.** A cycle (`a["a"] = a`) is rare in JSON but possible after `model_dump`; use an `id()`-set if you want belt-and-suspenders, OR rely on `_MAX_JSON_DEPTH=16` to terminate. Document the choice.
- **`json.loads(raw)` returns `Any`** — `mypy --strict` will complain at the dict-walk site. Either annotate at the boundary (`parsed: object = json.loads(raw)`) and `cast`/`isinstance`-narrow, or use `pydantic.TypeAdapter[NvdRawPayload]` for typed projection (heavier; pick based on parser complexity).
- **Idempotency via `INSERT OR IGNORE`** matches sqlite's `ON CONFLICT DO NOTHING` and relies on S3-02's unique constraint. Verify the unique constraint EXISTS before relying on it (a unit test against `sqlite_master.sql` is cheap insurance).
- **Per-feed digest concatenation order matters.** Pick "raw payloads concatenated in fetch order" and document; alternative is "sorted by `cve_id`" which is more deterministic against transient feed reordering but loses fetch-time correlation. Recommend sorted-by-id for the determinism property test (S8-03) friendliness.
- **CLI exit code `4` for partial parse failure is intentional.** CI should fail loud (Rule 12); operators who *want* to ignore per-record errors can add `--ignore-parse-errors` later (NOT in this story).
- **Fixtures should be tiny.** ~5 records per feed is enough for the integration test; do NOT mirror a real NVD delta (multi-MB; slows the suite). Real-feed coverage is an operator-time concern.
- **`fetchers.py` is a thin Hexagonal port.** Production code calls `fetch_nvd(since)`; tests `monkeypatch` it. Do NOT inline `urllib.request` calls into `ingest_records` — testability degrades.
- **Coordinate with S3-05 on cache invalidation timing.** After this story lands, `VulnIndex.digest()` changes on every refresh; S3-05's `BundleCacheGc` may want to be invoked *after* refresh too (operator runs `codegenie vuln-index refresh && codegenie cache prune` to clear stale Bundle entries). Surface to S3-05 as a no-op suggestion; not load-bearing here.
