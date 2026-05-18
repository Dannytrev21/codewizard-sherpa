# Story S3-02 — `VulnIndex` sqlite schema + Alembic migrations + staleness signal

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** Ready
**Effort:** M
**Depends on:** S3-01
**ADRs honored:** Phase 3 ADR-0008 (`vuln_index.digest` participates in Bundle cache key — this story exposes `digest()`), Phase 3 ADR-0005 (two-stream `EventLog` — `StaleVulnIndex` is a spanning event), production ADR-0033 (newtype identifiers — `PackageId`, `CveId`, `BlobDigest`)

## Context

`BundleBuilder` (S3-04) and the orchestrator (S6-04) need a fast `(package, ecosystem) → list[VulnerabilityRecord]` lookup with a content `digest()` that participates in the Bundle cache key (ADR-0008). A per-call JSON parse over the raw CVE feeds is 50–200 ms — over the 18 s p50 envelope this is unacceptable; sqlite with the right indexes lands at ~3 ms (`phase-arch-design.md §C11`). This story ships the schema, the `VulnIndex` class with three methods (`lookup`, `affecting_range`, `digest`), Alembic migrations as the migration substrate, AND the staleness signal: when the sqlite file's `mtime` exceeds `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS` (default `7`) at orchestrator init, a `StaleVulnIndex` spanning event is emitted (warn, NOT block — operators may run against a stale index intentionally).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C11 (supporting). VulnIndex` — interface, schema sketch, ~50 MB steady-state.
  - `../phase-arch-design.md §C9` — `WorkflowSpanningEvent` enum includes `stale_vuln_index`; this story populates the variant.
  - `../phase-arch-design.md §Open questions deferred to implementation` — "`vuln-index.sqlite` staleness threshold. 7 days mtime → warn (not block). Operator-configurable via `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`." This story ships the default.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Decision + §Consequences` — `vuln_index.digest()` is the load-bearing surface for Bundle cache-key correctness.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — "sqlite `VulnIndex` (`lookup`, `affecting_range`, `digest`), Alembic migrations" + done criterion "`StaleVulnIndex` event emitted when `mtime > 7 days` (configurable via `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`)".
- **Existing code:**
  - `src/codegenie/types/identifiers.py` (S1-01) — `PackageId`, `CveId`, `BlobDigest`, `Ecosystem` newtypes. Surface any missing newtype to S1-01 rather than adding here.
  - `src/codegenie/hashing.py` — `content_hash` / `bytes_hash` for `digest()` computation (do NOT import `blake3` directly — ADR-0001 hashing-chokepoint discipline).
  - `src/codegenie/errors.py` — `CodegenieError` markers-only base.

## Goal

`codegenie.vuln_index.VulnIndex` exposes `lookup`, `affecting_range`, and `digest` against an indexed sqlite store; Alembic migrations seed and evolve the schema; `VulnIndex.is_stale()` (driven by `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`, default `7`) feeds the orchestrator's `StaleVulnIndex` emission decision at init.

## Acceptance criteria

- [ ] New package `src/codegenie/vuln_index/` with: `__init__.py` (exports), `index.py` (`VulnIndex`), `models.py` (`VulnerabilityRecord`, `AffectedRange`, `Ecosystem` enum), `migrations/` (Alembic env + initial revision).
- [ ] `VulnerabilityRecord` Pydantic with `frozen=True, extra="forbid"`: `cve_id: CveId`, `ecosystem: Ecosystem`, `package: PackageId`, `affected_range: AffectedRange`, `severity: Literal["low", "medium", "high", "critical"]`, `published_at: datetime`, `source: Literal["nvd", "ghsa", "osv"]`.
- [ ] `AffectedRange` Pydantic with `frozen=True, extra="forbid"`: `introduced: str` (semver), `fixed: str | None` (None = unfixed), `last_affected: str | None`. NO raw ranges as strings — the typed shape is the contract.
- [ ] sqlite schema (Alembic initial revision `0001_initial.py`):
  - Table `vulnerabilities`: `id INTEGER PRIMARY KEY`, `cve_id TEXT NOT NULL`, `ecosystem TEXT NOT NULL`, `package TEXT NOT NULL`, `introduced TEXT NOT NULL`, `fixed TEXT`, `last_affected TEXT`, `severity TEXT NOT NULL`, `published_at TEXT NOT NULL` (ISO 8601), `source TEXT NOT NULL`, `raw_payload BLOB NOT NULL`.
  - Composite index `idx_vuln_pkg_eco ON vulnerabilities(ecosystem, package)` (the lookup hot path).
  - Unique constraint on `(cve_id, ecosystem, package, introduced)` to make ingest idempotent.
  - Table `meta`: `key TEXT PRIMARY KEY`, `value TEXT NOT NULL` — holds `schema_version`, `last_refresh_ts`, `feed_digest_nvd`, `feed_digest_ghsa`, `feed_digest_osv`.
- [ ] `VulnIndex.__init__(path: Path)` opens the sqlite file; `Path.exists() is False` is fine (empty index — `lookup` returns `[]`). `path` stored on `self.path`.
- [ ] `VulnIndex.lookup(package: PackageId, ecosystem: Ecosystem) -> list[VulnerabilityRecord]` returns ALL records matching `(ecosystem, package)` sorted by `(severity desc, published_at desc)`; uses the composite index; returns `[]` (NOT raises) on no-match.
- [ ] `VulnIndex.affecting_range(cve: CveId) -> AffectedRange` returns the first matching row's `AffectedRange`; raises `VulnIndexLookupError(reason="cve_not_found", cve_id=cve)` (markers-only) if no row matches. Document that a CVE spanning multiple packages picks the first by `(package asc, ecosystem asc)` — deterministic.
- [ ] `VulnIndex.digest() -> BlobDigest` returns `BlobDigest("blake3:" + 64-hex)` computed over `BLAKE3(meta.schema_version || meta.feed_digest_nvd || meta.feed_digest_ghsa || meta.feed_digest_osv)`. If `meta` is empty (fresh DB), all four are the empty string — digest still well-defined.
- [ ] `VulnIndex.is_stale(*, now: float | None = None) -> bool`: returns `True` iff `self.path.exists()` and `now() - self.path.stat().st_mtime > _max_age_seconds()`, where `_max_age_seconds()` reads `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS` (default `7`) and multiplies by `86400`. Non-existent path → `False` (an empty index is "fresh" by convention; ingest is the caller's problem).
- [ ] Env var validation: `CODEGENIE_VULN_INDEX_MAX_AGE_DAYS` must parse as a positive int; on miss (non-int, <= 0), the loader raises `VulnIndexConfigError(reason="invalid_max_age", value=...)` and the orchestrator's init logs + exits non-zero — `is_stale()` MUST NOT silently fall back to default.
- [ ] `StaleVulnIndex` event payload includes `path: str`, `mtime_iso: str`, `age_days: float`, `threshold_days: int`. The event TYPE literal is `"stale_vuln_index"` (matches `WorkflowSpanningEvent.event_type`).
- [ ] Alembic env wires to the package's own `migrations/` directory; `alembic upgrade head` on a fresh sqlite produces the schema; `alembic current` reflects the head revision. Migration script header docstrings cite this story ID.
- [ ] Test: `lookup` p99 < 10 ms over 100 lookups on a 10k-row seeded DB (advisory `@pytest.mark.bench`, excluded by default per `pyproject.toml`).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check`, `mypy --strict` clean.

## Implementation outline

1. `src/codegenie/vuln_index/models.py`:
   - `class Ecosystem(str, Enum)` with `NPM = "npm"`, `PYPI = "pypi"`, `MAVEN = "maven"`, `RUBYGEMS = "rubygems"`, `GOMOD = "gomod"` (extensible; Phase 3 only ingests `NPM`, but the column is open).
   - `class AffectedRange(BaseModel)`, `class VulnerabilityRecord(BaseModel)` per ACs.
2. `src/codegenie/vuln_index/index.py`:
   - `class VulnIndexLookupError(CodegenieError)` markers-only; `class VulnIndexConfigError(CodegenieError)` markers-only.
   - Module-level `_DEFAULT_MAX_AGE_DAYS: Final[int] = 7`.
   - `def _max_age_seconds() -> int` — reads env, validates, returns seconds. Surfaces a config error on bad input.
   - `class VulnIndex:` `__init__(path)` opens connection lazily; `lookup` / `affecting_range` / `digest` / `is_stale` per ACs.
   - Use `sqlite3` stdlib (NOT SQLAlchemy ORM — keep this lean; Alembic generates raw `op.execute` SQL for portability).
3. `src/codegenie/vuln_index/migrations/`:
   - `env.py` — minimal Alembic env wired to `sqlite:///<path>` via `VULN_INDEX_PATH` env var (test plumbing); offline mode supported.
   - `script.py.mako` — standard Alembic template.
   - `versions/0001_initial_schema.py` — `op.create_table("vulnerabilities", ...)`, indexes, `meta` table.
4. `src/codegenie/vuln_index/__init__.py` exports `VulnIndex`, `VulnerabilityRecord`, `AffectedRange`, `Ecosystem`, `VulnIndexLookupError`, `VulnIndexConfigError`.
5. Wire `pyproject.toml` to include `alembic` as a runtime dep (NOT dev — runtime needs `alembic upgrade head` to be invokable by the CLI in S3-03). Confirm `alembic` is NOT in the LLM-SDK fence list (it isn't).
6. Add `src/codegenie/vuln_index/migrations/alembic.ini` (or inline in `env.py`) — pin `script_location = src/codegenie/vuln_index/migrations`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/vuln_index/test_index.py`

```python
import os
import time
from pathlib import Path
from datetime import datetime, timezone
import pytest
from codegenie.vuln_index import VulnIndex, VulnerabilityRecord, AffectedRange, Ecosystem
from codegenie.vuln_index.index import VulnIndexLookupError, VulnIndexConfigError
from codegenie.types.identifiers import PackageId, CveId

@pytest.fixture
def seeded_index(tmp_path, alembic_upgrade):
    # alembic_upgrade is a fixture that runs `alembic upgrade head` against tmp_path/vuln-index.sqlite
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    idx._raw_insert(VulnerabilityRecord(
        cve_id=CveId("CVE-2024-21501"), ecosystem=Ecosystem.NPM,
        package=PackageId("express"),
        affected_range=AffectedRange(introduced="0.0.0", fixed="4.19.2", last_affected=None),
        severity="high", published_at=datetime.now(timezone.utc), source="nvd",
    ))
    return idx

def test_lookup_returns_records_for_matching_package(seeded_index):
    # Arrange: seeded with express CVE-2024-21501
    # Act
    results = seeded_index.lookup(PackageId("express"), Ecosystem.NPM)
    # Assert: composite index returns the record (intent: BundleBuilder routes recipe match on this)
    assert len(results) == 1
    assert results[0].cve_id == "CVE-2024-21501"

def test_lookup_missing_package_returns_empty_list(seeded_index):
    # Empty result is NOT an exception — recipe match short-circuits on []
    assert seeded_index.lookup(PackageId("nonexistent-pkg"), Ecosystem.NPM) == []

def test_lookup_sorts_severity_desc_then_published_desc(seeded_index):
    # Insert critical (newer) and high (older); critical comes first
    ...

def test_affecting_range_returns_first_match(seeded_index):
    rng = seeded_index.affecting_range(CveId("CVE-2024-21501"))
    assert rng.fixed == "4.19.2"

def test_affecting_range_missing_cve_raises_typed_error(seeded_index):
    with pytest.raises(VulnIndexLookupError) as exc:
        seeded_index.affecting_range(CveId("CVE-9999-9999"))
    assert exc.value.reason == "cve_not_found"

def test_digest_changes_when_feed_digest_changes(seeded_index):
    # Bundle cache-key correctness (ADR-0008): digest() change invalidates Bundle entries
    before = seeded_index.digest()
    seeded_index._raw_set_meta("feed_digest_nvd", "blake3:" + "a"*64)
    after = seeded_index.digest()
    assert before != after
    assert after.startswith("blake3:") and len(after) == len("blake3:") + 64

def test_is_stale_true_when_mtime_older_than_threshold(tmp_path, monkeypatch, alembic_upgrade):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "7")
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    old_mtime = time.time() - (8 * 86400)
    os.utime(db, (old_mtime, old_mtime))
    assert VulnIndex(db).is_stale() is True

def test_is_stale_false_within_threshold(seeded_index, monkeypatch):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "7")
    assert seeded_index.is_stale() is False

def test_is_stale_respects_env_override(tmp_path, monkeypatch, alembic_upgrade):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "1")
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    os.utime(db, (time.time() - (2 * 86400),) * 2)
    assert VulnIndex(db).is_stale() is True

def test_is_stale_rejects_invalid_env_value(tmp_path, monkeypatch, alembic_upgrade):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "not-an-int")
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    # Fail loud (Rule 12): no silent default fallback
    with pytest.raises(VulnIndexConfigError):
        VulnIndex(db).is_stale()

def test_is_stale_rejects_nonpositive_env_value(tmp_path, monkeypatch, alembic_upgrade):
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "0")
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    with pytest.raises(VulnIndexConfigError):
        VulnIndex(db).is_stale()

def test_default_max_age_is_seven_days(monkeypatch, tmp_path, alembic_upgrade):
    monkeypatch.delenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", raising=False)
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    os.utime(db, (time.time() - (8 * 86400),) * 2)
    assert VulnIndex(db).is_stale() is True
```

Test file: `tests/unit/vuln_index/test_migrations.py`

```python
def test_alembic_upgrade_creates_tables(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"vulnerabilities", "meta", "alembic_version"} <= tables

def test_composite_index_present(tmp_path, alembic_upgrade):
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_vuln_pkg_eco" in indexes
```

Bench (`tests/bench/vuln_index/test_lookup_perf.py`):

```python
@pytest.mark.bench
def test_lookup_p99_under_10ms(seeded_10k_index):
    samples = [_time_one(seeded_10k_index.lookup, PackageId("pkg-42"), Ecosystem.NPM) for _ in range(100)]
    samples.sort()
    assert samples[98] < 0.010   # p99 in seconds
```

### Green

Smallest impl: §Implementation outline; ~280 lines (mostly Alembic boilerplate + sqlite3 wrapper).

### Refactor

- Extract `_open_connection(path)` returning a `sqlite3.Connection` with `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL` — durable enough for the cache layer, fast enough for ingest.
- Add `_raw_insert(record)` and `_raw_set_meta(k, v)` as test seams; production ingest (S3-03) wraps these.
- Lift the `(severity desc, published_at desc)` sort into a SQL `ORDER BY` clause instead of post-fetch Python sort.
- Document the staleness threshold default in `docs/operations/phase03-runbook.md` (S9-04 ships the runbook; just leave a TODO comment).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/vuln_index/__init__.py` | Package exports |
| `src/codegenie/vuln_index/models.py` | `VulnerabilityRecord`, `AffectedRange`, `Ecosystem` |
| `src/codegenie/vuln_index/index.py` | `VulnIndex` + errors + env-reader |
| `src/codegenie/vuln_index/migrations/env.py` | Alembic env |
| `src/codegenie/vuln_index/migrations/script.py.mako` | Standard template |
| `src/codegenie/vuln_index/migrations/versions/0001_initial_schema.py` | Initial migration |
| `src/codegenie/vuln_index/migrations/alembic.ini` | Migration config |
| `tests/unit/vuln_index/test_index.py` | Red unit tests |
| `tests/unit/vuln_index/test_migrations.py` | Migration tests |
| `tests/unit/vuln_index/conftest.py` | `alembic_upgrade` fixture |
| `tests/bench/vuln_index/test_lookup_perf.py` | Advisory bench |
| `pyproject.toml` | Add `alembic` runtime dep |

## Out of scope

- **CVE feed parsers** — S3-03 ships NVD/GHSA/OSV smart-constructor parsers + size/depth caps.
- **`codegenie vuln-index refresh` CLI** — S3-03 owns the CLI subcommand and orchestrates ingest.
- **`StaleVulnIndex` event emission at orchestrator init** — S6-04 wires `VulnIndex.is_stale()` to the orchestrator's startup and emits the spanning event; this story exposes the predicate only.
- **Bundle cache-key composition** — S3-05 reads `VulnIndex.digest()` into the BLAKE3 key; this story exposes the digest only.
- **Multi-ecosystem ingest beyond NPM** — schema is open (column accepts any Ecosystem value), but only NPM is exercised in Phase 3 fixtures.
- **Migration rollback** — Alembic supports `downgrade` mechanically; Phase 3 only exercises `upgrade head`. Don't write hand-tuned downgrades.

## Notes for the implementer

- **`digest()` MUST be deterministic across processes.** Use `codegenie.hashing` helpers (not raw `blake3` import — ADR-0001 hashing-chokepoint discipline). Concatenate with `"\x1f"` (ASCII unit separator) per Phase 0 convention.
- **Empty-DB `digest()` is well-defined.** Hash of four empty strings joined by `\x1f` — always returns the same `blake3:<hex>`. Tests should pin this constant once and assert it remains stable across releases.
- **`Ecosystem` as `str, Enum`** so sqlite stores the string value (not the int variant). Pydantic v2 serializes enums by value with `use_enum_values=True` or by adding `@field_serializer`; pick the simpler.
- **Alembic + sqlite quirks.** `op.create_table` on sqlite supports `op.batch_alter_table` for column drops; you won't need it in 0001, but document the pattern in a comment for future migrations.
- **`fail loud` on bad env (Rule 12).** Tests `test_is_stale_rejects_invalid_env_value` and `test_is_stale_rejects_nonpositive_env_value` are load-bearing — silent default-fallback would mean operators think the threshold is 7 when they typo'd `MAX_AGE_DAY` and get 7-day staleness checks against a malformed value.
- **`affecting_range` uses "first by `(package asc, ecosystem asc)`"** — deterministic, but if a CVE spans multiple packages (rare; CVE-2021-44228 spans many `log4j` artifacts), the choice matters. Pick the deterministic rule and document in the docstring; downstream consumers can call `lookup` and iterate explicitly when needed.
- **Do NOT add a `latest_refresh_succeeded_at` column to `meta` in this story.** S3-03 may want one for ingest auditing; if so, ship as `0002_*.py` — additive migration, not edit-in-place.
- **Test fixture `alembic_upgrade(db)`** — implement once in `conftest.py` by setting `VULN_INDEX_PATH` env and shelling to `alembic upgrade head` via `subprocess.run` (allowed: `alembic` is a Python module, invoke via `python -m alembic` to stay in the allowlist; if not in `ALLOWED_BINARIES`, use `alembic.command.upgrade(config, "head")` directly — preferred).
