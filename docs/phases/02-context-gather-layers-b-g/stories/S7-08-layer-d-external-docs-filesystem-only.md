# Story S7-08 — Layer D: `ExternalDocsProbe` filesystem-only + `ExternalDocsIndexProbe`

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** M
**Depends on:** S2-07
**ADRs honored:** ADR-0009 (filesystem-only in Phase 2), ADR-0010 (`tantivy` opt-in)

## Context

`ExternalDocsProbe` (D8) and `ExternalDocsIndexProbe` (D9) ingest organizational documentation for Phase 4's RAG retrieval. ADR-0009 makes them **filesystem-only in Phase 2** — URL / Confluence / Notion fetching is deferred to a follow-up because the SSRF-guard + private-IP deny + scoped fetch sandbox + credential management is substantial security infrastructure for a feature `localv2.md §12 Week 5` labels "stretch". Phase 2 ships the contract surface that Phase 4 binds against. ADR-0010 makes the BM25 backend ripgrep by default; `tantivy` is `codegenie[search]` opt-in. The two adversarial tests are load-bearing: `test_external_doc_zip_slip.py` (path escape refused) and `test_huge_external_doc.py` (200 MB → size cap). The integration test asserts URL fetcher never launches with no config.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #20` — Layer D summary.
  - `../phase-arch-design.md §"Non-goals" #10` — explicit URL fetcher deferral.
  - `../phase-arch-design.md §"Edge cases"` — zip-slip, oversized doc, no-config-no-fetch.
- **Phase ADRs:**
  - `../ADRs/0009-external-docs-filesystem-only-phase-2.md` — ADR-0009 (filesystem-only contract).
  - `../ADRs/0010-tantivy-as-opt-in-extra.md` — ADR-0010 (BM25 backend).
- **Source design:**
  - `../final-design.md §"Components" §5.4 ExternalDocsProbe + ExternalDocsIndexProbe — filesystem-only in Phase 2`.
  - `../final-design.md §"Conflict-resolution table" D17`.
- **Existing code:**
  - `src/codegenie/output_sanitizer.py` (S1-09) — Pass 5 scan reused by `ExternalDocsProbe` (same shape as S7-07).
  - `src/codegenie/probes/grep.py` (S7-04) — `_BACKEND` detection pattern; `ExternalDocsIndexProbe` uses the same detection.
  - `markdown-it-py` (Phase 1 dep) — used to parse markdown for the index.

## Goal

Ship `src/codegenie/probes/external_docs.py` and `src/codegenie/probes/external_docs_index.py` plus two sub-schemas — `ExternalDocsProbe` is filesystem-only; copies each markdown into `.codegenie/context/raw/external-docs/` at `0600`; never inlines body; Pass-5 scans each; `ExternalDocsIndexProbe` builds BM25 (ripgrep default, `tantivy` opt-in) over the filesystem corpus and records `index_backend` in slice.

## Acceptance criteria

- [ ] `src/codegenie/probes/external_docs.py` exports `ExternalDocsProbe(Probe)` with `name="external_docs"`, `declared_inputs=[]` (sources come from `ctx.config.external_docs.sources`), `requires=[]`, `applies_to_languages=["*"]`, `timeout_seconds=60`.
- [ ] `ExternalDocsProbe` reads `ctx.config.get("external_docs", {}).get("sources", [])` — a list of **filesystem paths only** (Phase 2). URL / Confluence / Notion schema entries are recognized but **rejected with a typed error** (`ExternalDocsURLNotSupported`); the gather continues with the unsupported source omitted.
- [ ] For each filesystem source:
  1. Iterate `(source).rglob("*.md")`.
  2. **Zip-slip guard:** resolve each file's path; assert it is under the configured source root (`Path.resolve()` strictly within `source.resolve()`); refuse otherwise.
  3. **Size cap:** check `st_size` ≤ 10 MB per file. If oversized → `confidence: medium`, `warnings=["external_docs.body_too_large"]`, skip copy.
  4. Copy to `<repo>/.codegenie/context/raw/external-docs/<source_alias>/<rel_path>.md`; `os.chmod(dest, 0o600)`.
  5. Run Pass 5 marker scan on the body.
  6. Append to `slice["external_docs"]`.
- [ ] Emit `slice = {"external_docs": [{path: "raw/external-docs/...", source_alias: str, body_char_count: int, prompt_injection_marker_count: int}], "total_docs": int, "url_sources_rejected": int}`. **Body never appears in slice.**
- [ ] `src/codegenie/probes/external_docs_index.py` exports `ExternalDocsIndexProbe(Probe)` with `name="external_docs_index"`, `requires=["external_docs"]`, `applies_to_languages=["*"]`. Reads the copied corpus under `raw/external-docs/`; detects backend at startup (`try: import tantivy; backend = "tantivy"; except ImportError: backend = "ripgrep"`); builds BM25 index into `.codegenie/index/external-docs-bm25/` (per-repo); emits `slice = {"index_backend": <"ripgrep"|"tantivy">, "doc_count": int, "index_built_at_utc": str}`.
- [ ] Two sub-schemas at `src/codegenie/schema/probes/{external_docs,external_docs_index}.schema.json`. `external_docs.schema.json` forbids `body` field; `external_docs_index.schema.json` declares `index_backend` as a closed enum `["ripgrep", "tantivy"]`.
- [ ] `tests/unit/probes/test_external_docs.py` — happy path on `tests/fixtures/external_docs_fixture/` (3 markdown files under a configured source); URL source in config → rejected with `url_sources_rejected: 1`; no `external_docs` config → empty slice + URL fetcher never launches.
- [ ] **`tests/adv/test_external_doc_zip_slip.py`** — fixture with a symlink (or `..` traversal) attempting to write outside the source root → refused; assert no file is written outside `raw/external-docs/`.
- [ ] **`tests/adv/test_huge_external_doc.py`** — fixture with a 200 MB markdown file (constructed programmatically; do not commit) → size cap hits; `confidence: medium`; warning emitted; **file not copied**.
- [ ] **`tests/integration/test_phase2_external_docs_disabled_by_default.py`** — gather with no `external_docs` config; assert no URL fetcher launches (`monkeypatch` on `httpx` / `urllib.request` would fail the import-banlist anyway; this test asserts no probe invokes any network primitive); `index_backend == "ripgrep"` (default extras).
- [ ] Two goldens at `tests/golden/{external_docs,external_docs_index}/happy/expected.json`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/probes/external_docs.py`:
   - `ExternalDocsProbe(Probe)` with class attributes.
   - `_validate_source(source) -> Path | None` — if source is a string URL or Confluence/Notion shape, raises `ExternalDocsURLNotSupported`; otherwise returns absolute path.
   - `_resolve_safely(source_root: Path, candidate: Path) -> Path | None` — `Path.resolve()` both; assert `candidate` is within `source_root` (use `Path.relative_to` + try/except `ValueError`); refuse on escape.
   - Main loop per acceptance criteria.
2. Create `src/codegenie/probes/external_docs_index.py`:
   - `_BACKEND` detection at module scope (same shape as S7-04).
   - `_build_index_ripgrep(corpus_dir, index_dir) -> int` — same pure-Python BM25 as `GrepProbe`.
   - `_build_index_tantivy(corpus_dir, index_dir) -> int` — schema + index + commit.
3. Add `ExternalDocsURLNotSupported` to `errors.py`.
4. Two sub-schemas with the right `additionalProperties: false` + closed-enum.
5. Register both probes in `probes/__init__.py`.
6. Plant fixtures: `tests/fixtures/external_docs_fixture/` (3 clean .md), `tests/fixtures/external_docs_zipslip_fixture/` (with symlink attempting escape), and a test helper that **programmatically writes** the 200 MB file in the test (do not commit it).

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_external_docs.py`.

```python
async def test_happy_path_filesystem_only(external_docs_fixture, ctx_with_sources):
    out = await ExternalDocsProbe().run(external_docs_fixture.snapshot, ctx_with_sources)
    assert out.slice["total_docs"] == 3
    assert all("body" not in d for d in out.slice["external_docs"])
    assert all(d["path"].startswith("raw/external-docs/") for d in out.slice["external_docs"])

async def test_url_source_rejected(external_docs_fixture, ctx_with_url_source):
    out = await ExternalDocsProbe().run(external_docs_fixture.snapshot, ctx_with_url_source)
    assert out.slice["url_sources_rejected"] == 1
    assert out.confidence in {"high", "medium"}  # gather doesn't fail

async def test_no_config_no_fetch(empty_repo, ctx_empty):
    out = await ExternalDocsProbe().run(empty_repo.snapshot, ctx_empty)
    assert out.slice["total_docs"] == 0
    assert out.slice["url_sources_rejected"] == 0
```

Adversarial: `tests/adv/test_external_doc_zip_slip.py`.

```python
async def test_zip_slip_path_refused(zipslip_fixture, ctx_with_zipslip_source):
    out = await ExternalDocsProbe().run(zipslip_fixture.snapshot, ctx_with_zipslip_source)
    # Assert no file written outside raw/external-docs/.
    raw_root = zipslip_fixture.root / ".codegenie/context/raw/external-docs"
    written = list(raw_root.rglob("*.md")) if raw_root.exists() else []
    for f in written:
        assert raw_root.resolve() in f.resolve().parents
```

`tests/adv/test_huge_external_doc.py`.

```python
async def test_200mb_doc_size_capped(tmp_path, ctx):
    src = tmp_path / "huge_docs"
    src.mkdir()
    (src / "big.md").write_bytes(b"x" * (200 * 1024 * 1024))
    ctx_with_src = ctx.with_external_docs_source(src)
    out = await ExternalDocsProbe().run(snapshot_for(tmp_path), ctx_with_src)
    assert out.confidence == "medium"
    assert any("external_docs.body_too_large" in w for w in out.warnings)
    # Assert big.md not copied:
    assert not (tmp_path / ".codegenie/context/raw/external-docs").exists() or \
           not list((tmp_path / ".codegenie/context/raw/external-docs").rglob("big.md"))
```

Integration: `tests/integration/test_phase2_external_docs_disabled_by_default.py`.

```python
def test_no_external_docs_config_no_url_fetcher(tmp_clean_repo):
    # gather_main with default config (no external_docs key).
    result = gather_main(tmp_clean_repo)
    # No URL fetcher attempted; the existing `fence` job's import-banlist asserts this at a different layer.
    # Here, assert the probe's slice is empty + index_backend defaults to ripgrep.
    assert result.slices["external_docs"]["total_docs"] == 0
    assert result.slices["external_docs_index"]["index_backend"] == "ripgrep"
```

### Green

Minimal impl per outline. `_resolve_safely` is the critical helper — `Path.resolve()` + `Path.relative_to` is the idiomatic check; catch `ValueError` on escape.

### Refactor

- Module docstrings naming `phase-arch-design.md §"Component design" #20`, `final-design.md` D17, ADR-0009, ADR-0010.
- `_BACKEND` detection: extract a small helper `detect_search_backend() -> Literal["ripgrep", "tantivy"]` shared with `GrepProbe` (S7-04) — DRY.
- Size-cap constant at module scope: `_MAX_BODY_BYTES: Final[int] = 10 * 1024 * 1024`.
- URL detection: pattern-match on source — `str.startswith(("http://", "https://"))` → URL; `dict` with `type: "confluence" | "notion"` → also URL-like; raise.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/external_docs.py` | New — filesystem-only D8. |
| `src/codegenie/probes/external_docs_index.py` | New — BM25 index. |
| `src/codegenie/schema/probes/external_docs.schema.json` | New — `body` field forbidden. |
| `src/codegenie/schema/probes/external_docs_index.schema.json` | New — `index_backend` enum. |
| `src/codegenie/errors.py` | Surgical — add `ExternalDocsURLNotSupported`. |
| `src/codegenie/probes/__init__.py` | Register 2 probes. |
| `tests/unit/probes/test_external_docs.py` | New — 3 unit tests. |
| `tests/adv/test_external_doc_zip_slip.py` | New — path-escape refusal. |
| `tests/adv/test_huge_external_doc.py` | New — 200 MB size cap. |
| `tests/integration/test_phase2_external_docs_disabled_by_default.py` | New — no-config no-fetch. |
| `tests/fixtures/external_docs_fixture/` + `external_docs_zipslip_fixture/` | New — 2 fixtures. |
| `tests/golden/{external_docs,external_docs_index}/happy/expected.json` | New — 2 goldens. |

## Out of scope

- **URL / Confluence / Notion fetching** — ADR-0009 defers; this story rejects with a typed error and continues.
- **SSRF guard infrastructure** — deferred per ADR-0009; the future-amendment surface is documented in ADR-0009 itself.
- **HTML→Markdown conversion** — `markdownify` was scoped for the deferred URL pipeline; not needed for filesystem-only.
- **Cross-language doc indexes** — single corpus per repo in Phase 2.
- **Index incremental update** — Phase 14 tunes; Phase 2 rebuilds.

## Notes for the implementer

- **`Path.resolve()` is your friend, but only after `os.stat`.** Symlink resolution can race; resolve once at the start of the file iteration and again per-candidate. The witness for the zip-slip test is that no file is *written* outside `raw/external-docs/` — not that no file is *read* outside the source (reads can be benign).
- **`url_sources_rejected` is a count, not a list of strings.** Don't leak URL contents into the slice (one could embed credentials in a URL). The count is enough for downstream visibility.
- **The size cap is per-file, not aggregate.** A directory with 1000 × 1 MB files (1 GB total) is fine; one 200 MB file is not. Phase 14 may add an aggregate cap.
- **`_BACKEND` detection is module-level** — same pattern as `GrepProbe` (S7-04). Extract a shared helper into `src/codegenie/util/search_backend.py` or similar; both probes call it. Don't duplicate the `try/except ImportError`.
- **`ExternalDocsIndexProbe` requires `external_docs`** — wave ordering ensures D8 runs first; D9 reads the copied corpus from `raw/external-docs/`. If D8 emits `total_docs: 0`, D9 emits `doc_count: 0` + `confidence: high` (zero is a valid count).
- **`index_built_at_utc`** — `datetime.now(timezone.utc).isoformat()` at the start of `_build_index_*`. This is one of the fields the goldens must exclude (`scripts/regen_golden.py` from S8-04 will handle).
- **No outbound network from `codegenie/`** — the Phase 0 `fence` already forbids `httpx`/`requests`/`socket`/`urllib3`. This story does not add any network-capable imports. The integration test is the witness; the fence is the structural defense.
- **Future ADR / Phase-4 hook** — when URL fetching lands, this probe adds a new "url" source kind that *does* dispatch to a network-egress path. The future ADR will reference ADR-0009; the URL fetcher will live in a separate module (`url_fetch.py`) with its own `network="scoped"` sandbox profile. Don't pre-build this; the rejection-with-typed-error is the contract.
