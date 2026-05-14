# Validation report — S3-06 Manifest fixtures + integration tests + catalog-invalidation scope

**Date:** 2026-05-14
**Validator:** phase-story-validator skill (4 critics + synthesizer; researcher skipped — no `NEEDS RESEARCH` flags)
**Verdict:** **HARDENED**
**Story:** [S3-06-manifest-fixtures-integration.md](../S3-06-manifest-fixtures-integration.md)

---

## Context Brief (Stage 1)

**Story promises (Goal):** Land `node_pnpm_native/` + `node_yarn_legacy/` fixtures, three integration tests, and a catalog-invalidation-scope unit-test extension so `NodeManifestProbe`'s behavior is verified end-to-end with realistic inputs and ADR-0006's cache-scope claim has CI evidence.

**Phase exit criteria the story is on the hook for:**
- `final-design.md "Risks"` #1 (silent catalog staleness) — this story is the **CI evidence** for the structural mitigation.
- ADR-0006 (`(path, size)` cache key derivation including `native_modules.yaml`) — this story's **load-bearing** test.
- Phase-arch-design Gap 2 (raw-artifact budget) — this story is the **first realistic exercise**.
- ADR-0003 (yarn dual-path) — this story is integration-level evidence; **S3-04 is the parser-level evidence**.

**Arch + ADRs that constrain implementation:**
- ADR-0006: cache key is `(path, size)` — same-size YAML edits don't invalidate.
- ADR-0003: yarn `_HAS_PYARN` dispatch lives at `_lockfiles/_yarn._HAS_PYARN`.
- Phase 0 ADR-0007: `Probe` ABC frozen — budgets via `ResourceBudget`, NOT `Probe` class attr.
- CLAUDE.md: extension by addition; surgical changes (Rule 3); fail loud (Rule 12); match conventions (Rule 11).

**Critical files referenced:**
- `tests/fixtures/node_yarn_legacy/` — **already exists** with `lodash@^4.17.21` + `packageManager: "yarn@1.22.19"` + classic `yarn.lock`.
- `tests/integration/probes/conftest.py` — already exposes `_copy_tree`, `_load_envelope`, `WARM_PATH_CACHE_HIT_PROBES` frozenset, `_disable_cli_configure_logging` autouse fixture.
- `tests/unit/test_cache_invalidation_scope.py` — currently tests per-probe-schema-version, not catalog-edit (the story extends it additively).
- `src/codegenie/logging.py:58` — `EVENT_PROBE_RAW_ARTIFACT_TRUNCATED: Final[str] = "probe.raw_artifact.truncated"`.
- `_validation/S1-09-raw-artifact-budget.md` — pinned marker shape: `{"__truncated_at_budget__": True, "original_bytes": <n>, "budget_bytes": <m>, "data": ...}`; capture via `structlog.testing.capture_logs()`, NOT `caplog`.
- `_validation/S3-05-node-manifest-probe.md` T-9 — `os.fstat` monkey-patch is the pattern of record for size-cap tests; do NOT write 30 MB to tmpfs.

**Ambiguity surfaced (resolved during synthesis):** ADR-0003 reversibility-evidence claim. Original story Context #2 said this story's parity test "is the production-time evidence backing ADR-0003's 'Reversibility: high' claim." But S3-04 already lands the parser-level parity oracle with a CI-enforced mutation gate (recent commit `6f77ff8`). Resolved by re-framing S3-06's yarn-legacy test as a probe-level integration smoke (slice-plumbing on yarn-classic), not parser correctness — per Consistency F-4.

---

## Stage 2 — Critic findings

### Coverage critic

**BLOCK:**
- F-1: Catalog-invalidation scope is single-direction (under-invalidation only); over-invalidation invisible. → APPLIED to AC-7 as aggregate `assert {misses} == {"node_manifest"}`.
- F-2: Multi-lockfile case (Edge case #7) absent. → APPLIED as AC-5 parametrized variant on the pnpm-native test.
- F-3: Truncated raw artifact's readability not pinned. → APPLIED to AC-9: `json.loads(...)` succeeds.
- F-4: Truncation event count not pinned to exactly one. → APPLIED to AC-10 (count == 1, not >= 1).

**HARDEN:**
- F-5: Parity test cannot detect both arms silently running hand-rolled. → APPLIED to AC-6 with `mocker.spy` distinctness assertions.
- F-6: `(path, size)` invalidation requires size change; "bump by 1" silently violates. → APPLIED to AC-7: explicit size-change assertion + `xfail` companion.
- F-7: 30 MB lockfile must be structurally parseable. → APPLIED to AC-8 (parse verified BEFORE the probe runs).

**NIT:**
- F-8: First end-to-end multi-probe gather evidence claim has no AC. → APPLIED to AC-4.
- F-9: Missing-lockfile case undefined. → APPLIED in Out of scope.

### Test-quality critic

**BLOCK:**
- F-1: `node_yarn_legacy/` already on disk; story would overwrite. → APPLIED: AC-2 rewritten as REUSE; Files-to-touch updated.
- F-2: Parity passes under silent-fallback mutation. → APPLIED: AC-6 `mocker.spy` assertions on both arms.
- F-3: Catalog-bump guidance contradicts ADR-0006. → APPLIED to AC-7 (size-change requirement explicit).

**HARDEN:**
- F-4: Invalidation-scope "at-least-one" survives surgical-flush mutants. → APPLIED to AC-7 (parametrized over all siblings + aggregate equality).
- F-5: Truncation marker test underspecified. → APPLIED to AC-9 (full marker shape) + AC-10 (`structlog.testing.capture_logs`, not `caplog`).
- F-6: Synthetic 30 MB lockfile should use `os.fstat` monkey-patch, not real bytes. → APPLIED to AC-8 + Notes.
- F-7: Tautology risk in pnpm sample test. → APPLIED to AC-3 (`assert "lodash" in names; assert len(names) >= 3`).

**NIT:**
- F-8: `_run_gather_on_fixture` rule-of-three threshold met. → RESOLVED differently (per Design D-2: reuse existing helpers from conftest, do NOT extract a new helper).
- F-9: `catalog_version` equality not bound. → APPLIED to AC-3 (`== NATIVE_MODULES_CATALOG_VERSION`).

### Consistency critic

**BLOCK:**
- F-1: `node_yarn_legacy/` already exists. → APPLIED (same as Test-Quality F-1).
- F-2: `_HAS_PYARN` symbol depends on S3-03 (not in `Depends on`). → APPLIED: header expanded to include S3-03, S3-04, S1-05, S1-09.

**HARDEN:**
- F-3: License-to-edit S1-05 conflicts with Rule 3. → APPLIED: alternative dropped from Implementation outline + AC + Notes; if monkey-patch isn't hermetic, BLOCK on a separate amendment story.
- F-4: Parity test overlaps with S3-04. → APPLIED: Context §2 re-framed as integration smoke, not parser parity; ADRs-honored line clarifies.
- F-5: Catalog-bump test doesn't enforce size change. → APPLIED to AC-7 (same as Coverage F-6).

**NIT:**
- F-6: Effort sizing M → L. → APPLIED: header shows `Effort: L (was M — re-sized after validation)`.
- F-7: Event-name + field contract verified clean (`probe.raw_artifact.truncated`, `original_bytes`, `budget_bytes`). ✓
- F-8: CLAUDE.md commitments check clean. ✓

### Design-patterns critic

**HARDEN:**
- D-1: TDD-plan code drifts from `CliRunner` precedent. → APPLIED: TDD plan rewritten to use `CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])`.
- D-2: Refactor proposes a NEW helper at WRONG path; existing `_copy_tree`/`_load_envelope` already present. → APPLIED: Refactor section + Implementation outline + TDD sketches all reuse the existing helpers; no new helper extracted.
- D-3: Catalog-invalidation parametrize seam — pin now? → APPLIED softly: noted in Notes-for-implementer for the second consumer (CIProbe / Phase 3 replacement catalogs); NOT extracted in S3-06 per Rule 2 (single application).
- D-4: Catalog-loader DI vs. monkeypatch private symbol. → RESOLVED via Consistency F-3 priority: monkey-patch only; no S1-05 amendment from this story. The DI-cleaner-pattern observation is recorded as a follow-up consideration for the future amendment story.

**NIT:**
- N-1: `_HAS_PYARN` brittleness. → APPLIED in Notes-for-implementer.
- N-2: 30 MB synthetic-fixture generator stays inline (Rule 2). → APPLIED in Refactor section.

**Patterns explicitly NOT applied (Rule 2 / Rule 11):**
- No `RepoRoot` newtype (Rule 11 — match `RepoSnapshot.root: Path`).
- No functional-core/imperative-shell split for the 30 MB lockfile generator (single-use 5-line helper).
- No `CATALOG_INVALIDATION_TARGETS` registry (premature for one consumer).

---

## Stage 3 — Researcher

**Skipped.** No critic finding tagged `NEEDS RESEARCH`. Pattern of record (`os.fstat` monkey-patch, `structlog.testing.capture_logs`, `mocker.spy`, `CliRunner` + `_disable_cli_configure_logging` seam) all derive from in-repo precedents (S3-01/02/03/05, S2-04/05, S1-09 validations). No external library docs or arXiv search needed.

---

## Stage 4 — Conflict resolution

**Conflict 1: Consistency F-3 vs. Design D-4** — both addressed catalog-loader redirection. Design proposed pinning the env-var alternative as a hard dependency; Consistency invoked Rule 3 / extension-by-addition to forbid silent S1-05 widening.

**Resolution:** Consistency wins per priority order. Both critics agreed in spirit (don't silently widen scope); the resolved phrasing requires monkey-patch ONLY in this story; if it can't be made hermetic, fail loud and BLOCK on a separate amendment story (Rule 12). The DI-cleaner observation is recorded as a future consideration, not a S3-06 deliverable.

**Conflict 2: Coverage F-9 (no-lockfile case) vs. story scope.**

**Resolution:** Coverage tagged this NIT; the case is owned by S5-04 (per Out of scope). Added an explicit Out-of-scope bullet rather than an AC.

No other conflicts. The four critics' findings were largely complementary (catalog-invalidation scope; parity test mutation-resistance; raw-artifact marker shape; fixture collision; CLI invocation drift) and reinforce one another.

---

## Stage 4 — Edits applied (summary)

| Section | Change |
|---|---|
| Header | Status → `Ready (HARDENED)`; Effort `M` → `L`; `Validated` date added; `Depends on` expanded with S3-03 / S3-04 / S1-05 / S1-09; ADR honored re-framed for ADR-0003 (integration not parity) |
| **Validation notes** | New block after header: 6 BLOCK + 5 HARDEN + 3 design-pattern caveats + 1 follow-up |
| Context #2 | Re-framed yarn-legacy parity test as probe-level integration smoke (S3-04 owns parser parity) |
| Goal | Tightened — pins catalog-scope evidence in BOTH directions; adds multi-lockfile path |
| **Acceptance criteria** | Restructured into 6 groups (Fixtures, Pnpm-native, Yarn-legacy, Catalog-invalidation, Raw-artifact, Cross-cutting); 13 ACs with mutation-killer rationale on each |
| Implementation outline | Reuse-don't-create for yarn-legacy; CliRunner + reuse `_copy_tree`/`_load_envelope`; mocker.spy distinctness; `os.fstat` monkey-patch; size-changing catalog bump |
| TDD plan | Red snippets fully rewritten — CliRunner pattern, structlog capture_logs, marker-shape assertions, mocker.spy on both arms, size-change assertion, xfail companion test |
| Files to touch | `node_yarn_legacy/{package.json,yarn.lock}` removed; `README.md` flagged as additive append only |
| Out of scope | Expanded: yarn parser parity (S3-04), lockfile-absent (S5-04), `CATALOG_DIR` env var (forbidden), `CATALOG_INVALIDATION_TARGETS` (premature) |
| Notes for the implementer | Rewritten — REUSE not creation, monkey-patch ONLY (no S1-05 edit), size-change requirement, `os.fstat` pattern of record, marker shape, `capture_logs` not `caplog`, `CliRunner` not direct invocation, `_HAS_PYARN` brittleness, multi-lockfile + multi-probe surface-as-callout guidance |

---

## Verdict: HARDENED

The story now bars the executor from a class of subtle silent-pass failure modes that the original would have allowed:
- Fixture overwrite (collision with S2-02a/S3-03/S3-04 dependencies).
- Parity test passing trivially under "both arms aliased to same parser" mutations.
- Catalog-invalidation test passing under "everything except `ci` got flushed" mutations.
- Catalog bump (`1` → `2`) silently failing the `(path, size)` cache key but the test passing for orthogonal reasons.
- Truncation event passing under "30 events emitted" or "wrong marker shape" mutations.
- 30 MB synthetic fixture either blowing CI disk budget OR triggering parse-cap before raw-artifact-write.
- CLI direct-invocation bypassing `_disable_cli_configure_logging` and silently capturing zero events.
- Silent expansion of S3-06's scope into S1-05 catalog-loader edits (Rule 3 violation).

Story is ready for `phase-story-executor`. The ACs collectively guarantee the goal, every AC is individually verifiable, and every AC has at least one mutation killer in the TDD plan.
