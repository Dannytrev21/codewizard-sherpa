# Attempt log — S1-01 (SUT contract types)

## Attempt 1 — 2026-05-25 — GREEN

**Outcome:** All 12 ACs satisfied. 91 new tests pass; full suite passes minus one pre-existing flaky local timing test (`tests/adv/test_tsconfig_pathological.py` fails on master baseline too, unrelated to this story; CI's fresh Linux runner is fast enough).

### What landed

#### Kernel-tier identifiers (Phase-6 catalog, `codegenie.types.identifiers`)
- `VulnCaseId = NewType("VulnCaseId", str)` — ULID-formatted bench-harness case id.
- `RepoFixtureRef = NewType("RepoFixtureRef", str)` — `^[a-z][a-z0-9_-]*$`, ≤ 128 chars; a name, never a path.
- `SutDigest = NewType("SutDigest", str)` — `^blake3:[0-9a-f]{64}$`; Phase-9 S4-05 G5 byte-equality substrate.
- `__all__` extended (sorted) and `_NEWTYPE_REGISTRY` carries the per-newtype one-line docstring with `ADR-0010` + `ADR-0001` citations.

#### Smart constructors (`codegenie.types.parsers`)
- `parse_vuln_case_id`, `parse_repo_fixture_ref`, `parse_sut_digest`.
- Reuse the canonical `_regex_parser` closure helper (ADR-0010 §grammar table).
- `_SUT_DIGEST_RX` mirrors Phase-3 `BundleCacheKey` shape (same wire grammar, different semantic).

#### `codegenie.workflows/` package (new)
- `__init__.py` — re-exports exactly four names: `VulnRemediationCase`, `VulnRemediationResult`, `SutDigest`, `VulnRemediationSut`.
- `_frozen.py` — single canonical home for `_FROZEN_FORBID` (Q1 resolved per ADR-0010 Amendment 2026-05-18; new constant rather than re-exporting `transforms.outcomes`).
- `vuln_sut.py` — Protocol + four models + three frozen sub-models (`GateSummary`, `CostSummary`, `EvidenceRef`) + pure helper `_compute_sut_digest_input`.
- `EvidenceRef` smart constructor rejects: absolute paths (POSIX + Windows), `..` components, null/control chars, secret-shaped substrings (via `SECRET_FIELD_PATTERN`), cleartext secret patterns (via `_PATTERNS` imported by identity from `codegenie.output.sanitizer` — explicitly NOT forked).
- `VulnRemediationResult` `model_validator` enforces three cross-field invariants on `terminal_state ↔ patch_digest ↔ failure_modes`.

#### Tests (10 new files, 1 extended)
- `tests/unit/workflows/test_vuln_sut_shape.py` — AC-1/2/3/4/8 (28 tests).
- `tests/unit/workflows/test_sanitization_properties.py` — AC-5 Hypothesis + parametrized (27 tests).
- `tests/unit/workflows/test_sut_digest_properties.py` — AC-7 stability + sensitivity + AST no-side-effects + grammar (9 tests).
- `tests/fence/test_workflows_public_surface.py` — AC-1/6/12 (4 tests).
- `tests/fence/test_phase6_no_graph_imports_from_phase65.py` — placeholder Phase-6.5 fence (skipped today, fires when harness lands).
- `tests/integration/test_phase6_sut_contract_snapshot.py` — AC-9 byte-equal snapshot test + `classify_snapshot_diff` helper supporting `PHASE6_CONTRACT_GOLDEN_REWRITE=1`.
- `tests/integration/test_phase6_sut_contract_snapshot_meta.py` — AC-9 meta-test pinning every branch of the additive-vs-breaking classifier (12 tests).
- `tests/unit/types/test_identifiers_phase6.py` — AC-10 drift fence for three new identifiers (9 tests).
- `tests/unit/types/test_identifiers_phase3.py` — extended `PHASE6_NEWTYPE_NAMES` set + updated `test_all_is_exact_set` + `test_newtype_registry_matches_all`.
- `tests/golden/phase6-contract/snapshot.json` — generated under `PHASE6_CONTRACT_GOLDEN_REWRITE=1`.

#### `pyproject.toml`
- Added `codegenie.workflows` to both `source_modules` lists (ADR-0010 BudgetToken two-frame fence + ADR-0016 phase4 solved-example mint fence). Without these, `make fence` failed loud at `tests/fence/test_budget_token_scope.py` — exactly the "any new codegenie subpackage must be scoped" assertion (Rule 12 fail-loud working as designed).

### Mutation-resistance checks performed
- `extra="allow"` swap → AC-3/4 extra_field tests fail.
- `Literal[...]` → `str` swap on `execution_mode` / `terminal_state` → AC-3/4 byte-equality tests fail.
- `regex.fullmatch` → `regex.search` swap on `EvidenceRef` → AC-5 substring property tests fail (`"foo /etc/passwd"`).
- `==` → `!=` swap in `classify_snapshot_diff` → 11 of 12 meta-tests fail.
- `runtime_checkable` removal → AC-2 + meta-test fail.

### Decisions of record (one-line each)
- `_FROZEN_FORBID` lives at `codegenie.workflows._frozen` (NOT re-exported from `transforms.outcomes`), per the story Q1 resolution. Single canonical location; AC-4 AST walk pins the import-by-name.
- File naming: `vuln_sut.py` (not `sut.py`) — Open/Closed at the file boundary; the Phase 7 + Phase 9 sibling SUTs land alongside without editing this file.
- No `SutRegistry`, no `BaseSut` ABC — anti-refactor honored. Rule-of-three threshold is Phase 9's `TemporalVulnRemediationSut` + Phase 6.5's bench-fixture SUT.
- The contract-snapshot classifier helper (`classify_snapshot_diff`) lives in the snapshot test module, exported as a public symbol so the meta-test can exercise its branches without re-implementing them.

### Notes for downstream stories
- **S1-02 (ledger sum union):** carries the full payload-bearing terminal-state union including the four non-terminal states. The public `TerminalState` Literal in `VulnRemediationResult` covers only the three terminal states; the ledger union must NOT leak into the public Result.
- **S3-01 (plugin-local subgraph):** consumes `VulnRemediationCase` + `VulnRemediationResult` shapes; treat any new field as an ADR-0001 amendment.
- **S5-01 (stable SUT adapter):** when implementing `digest()`, call `_compute_sut_digest_input(case)` — do not re-hash anything. The AC-7 AST no-side-effects fence starts biting at S5-01 the moment `digest()` references `time`, `os.environ`, etc.
- **Phase 9 S4-05 G5:** byte-equality across Local + Temporal SUTs is reachable because both compute via the same pure helper this story shipped.
