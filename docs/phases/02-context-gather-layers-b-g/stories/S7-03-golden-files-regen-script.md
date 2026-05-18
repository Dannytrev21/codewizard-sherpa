# Story S7-03 — Golden files (~70) + `scripts/regen_golden.py` canonical-ordering

**Step:** Step 7 — Plant five-repo fixture portfolio + per-probe golden files + remaining adversarial corpus
**Status:** GREEN-PARTIAL — shipped 2026-05-18 (phase-story-executor; see [`_attempts/S7-03.md`](_attempts/S7-03.md) for the per-AC evidence table). Core infrastructure + 90 goldens + 9 supporting tests landed; AC-13/14/18/19/20/22/29 deferred (matrix-expansion follow-up once the corresponding probes register slices consistently across the portfolio). AC-4/16/36 carry documented adaptations.
**Effort:** M
**Depends on:** S7-02 (all five fixtures exist on disk; `stale-scip` is fully materialized; `monorepo-pnpm` lockfile is committed). Soft-depends on Phase 1 S6-01 (`scripts/regen_golden.py` and `tests/golden/<fixture>.repo-context.yaml` — see Validation notes for the coexistence story; if S6-01 hasn't shipped yet, this story creates `scripts/regen_golden.py` from scratch and reserves the `--portfolio` mode without touching S6-01's envelope-level YAML golden seam).
**ADRs honored:** ADR-0001 (allowlisted binaries — `regen_golden.py` invokes `codegenie gather` which obeys the allowlist), ADR-0003 (heaviness sort — goldens reflect the deterministic dispatch order), ADR-0004 (image-digest declared-input token — `distroless-target` goldens include the resolved digest, never `latest`), ADR-0005 (no plaintext persisted — goldens for scanner probes record `<REDACTED:fp=...>` only), ADR-0006 (`IndexFreshness` location — `stale-scip` golden's `freshness` slice is a `Stale(reason=CommitsBehind(...))` literal), ADR-0010 (`RedactedSlice` smart constructor — goldens for any probe whose slice contains scanner findings show the `RedactedSlice` JSON shape, never a raw `dict`).

## Validation notes (2026-05-18)

This story was hardened by `phase-story-validator`. Full report under `_validation/S7-03-golden-files-regen-script.md`. Headline corrections:

- **Coexistence with S6-01 made explicit.** Phase 1 S6-01 (HARDENED 2026-05-15) ships an *envelope-level* YAML golden at `tests/golden/<fixture>.repo-context.yaml` with a `_GOLDEN_PAIRS` Open/Closed seam and **sentinel-normalization** for `generated_at` + `repo.git_commit` (the only two top-level non-deterministic envelope fields; there is **no `audit` block at the envelope root** — `wall_clock_ms` lives in sidecar `runs/*.json`). S7-03 ships *slice-level* per-probe JSON goldens at `tests/golden/probes/<probe>/<fixture>.json` consuming the raw artifacts under `<fixture>/.codegenie/context/raw/<probe>.json` and uses **field-exclusion**. The two artifacts are orthogonal (different paths, different shapes, different non-determinism surfaces); S7-03 does NOT touch or replace S6-01's YAML golden or its `_GOLDEN_PAIRS` tuple. The only shared code in `scripts/regen_golden.py` is `_canonicalize` (recursive sorted-keys + tuple→list + None-vs-missing normalization). New ACs AC-34, AC-38 make this load-bearing.
- **Idempotence promoted from PR-description claim to CI gate** (S6-01 precedent — "humans miss things; CI doesn't"). AC-27 reframed: the two-runs-byte-identical assertion is now a unit-test (`tests/golden/test_regen_golden_idempotent.py`) shipped in this story, not deferred to S8-03. AC-26 is retained as PR-merge documentation discipline but is no longer the only safeguard.
- **macOS shape divergence — picked one path: error-out.** AC-16 originally said "Linux-only-skip OR error-out — implementer's call." The synthesizer picks **error-out with a clear remediation message** (Rule 12: fail loud; mirrors S6-01's idempotence CI gate). A macOS contributor running `--portfolio --update` gets a structured stderr message naming the Linux requirement and the CI runner image; the script exits 2.
- **Envvar substring-match guards added.** AC-7's substring match against `$USER`/`$HOSTNAME`/`$HOME` was a footgun: short or empty values would scrub legitimate occurrences ("ci", "root", "" → match everything). AC-7 amended: empty/short (< 4 chars) envvar values are skipped from the substring scrubber with a `WARNING` emitted to stderr; the scrubber only fires when the envvar is unambiguous.
- **Plaintext-leak guard derives patterns from `SecretRedactor`.** AC-32 originally hardcoded patterns. Source-of-truth for ADR-0005 lives in `src/codegenie/output/sanitizer.py::_PATTERNS`. AC-32 amended to import that module-level table and parametrize over it — drift between the production redactor and the golden audit becomes a compile-time `ImportError`, not a silent miss.
- **Count range tightened.** AC-25 said "~70; allowed range 50–90" — a 1.8× spread that hides drift. Reframed: the exact count is computed by a deterministic enumeration function (`_compute_expected_golden_count()` over the (probe, fixture) cells where each probe declares its applicable fixtures). `COUNT.txt` records the enumeration result; `_compute_expected_golden_count()` is the single source of truth grep-discoverable from `scripts/regen_golden.py`.
- **Atomic writes added** (AC-34). `--update` writes each golden via `tempfile.NamedTemporaryFile` + `os.replace` (atomic on POSIX). A SIGINT mid-write never leaves a half-written golden on disk.
- **Clean-slate per-fixture regen added** (AC-36). Each fixture's pre-existing `.codegenie/context/` is cleared before the gather invocation so a cache hit doesn't silently produce a different slice shape. Audit logs this deletion via structlog.
- **Phase 1 fixture coexistence** (AC-38). Phase 1's `tests/fixtures/node_typescript_helm/` is **not** under `tests/fixtures/portfolio/` and is **not** swept by the `--portfolio` mode. S6-01's YAML golden for that fixture stays canonical; no per-probe JSON goldens are produced for Phase 1 fixtures. An AC plus a test enforce the non-collision (no goldens land under `tests/golden/probes/*/node_typescript_helm.json`).
- **Typed `JsonValue` canonicalize signature** (AC-39). The recursive `_canonicalize` uses a typed `JsonValue` union (no `Any`), so `mypy --strict` does real work rather than rubber-stamping. A type-only file at `scripts/_json_value.py` (or inline `TypeAlias` if simpler) documents the shape.
- **`_PRESERVED_FIELDS` inclusion list** (AC-37). Declared-input tokens (`image_digest`, the SCIP `output_path_relative`, the BLAKE3 8-hex `fingerprint`) are explicitly inclusion-listed in a module-level frozen set. The exclusion list (AC-7) and the inclusion list (AC-37) are complementary; conflict resolution is "inclusion wins" (a field that names a declared-input token is never scrubbed). Discoverable by `grep`.
- **Underscore-prefix skip becomes a test** (AC-40). AC-3 says directories under `tests/fixtures/portfolio/` prefixed `_` are skipped (the convention); this is now also asserted by a test, so a future contributor creating `_shared_helpers/` doesn't accidentally trigger a fixture-walk pass.
- **Unified-diff format assertion** (AC-30 tightened). The "5-line excerpt" requirement was prose-only; the test now asserts the failure message contains `---` + `+++` + `@@` markers (unified-diff format), not just any 5 lines.
- **`_LIST_SORT_KEYS` keyed by typed probe name** (Notes-for-implementer). Stringly-typed keys (`"semgrep.findings"`) are a Newtype-pattern miss. Recommend keying by `(ProbeName, str)` where `ProbeName` is the shared `Literal` from `tests/fixtures/_shape_test_kernel.py` (S7-02 HARDENED precedent) — single source of truth for probe names across the test harness.

**ACs touched:** AC-7 amended (envvar guards), AC-13 (macOS note), AC-16 (error-out picked), AC-25 (deterministic count), AC-26 (clarified), AC-27 (promoted to CI gate), AC-30 (unified-diff assertion), AC-32 (pattern import). New: AC-34, AC-35, AC-36, AC-37, AC-38, AC-39, AC-40. Total ACs: 33 → 40.

## Context

This story lands the **golden-file layer**: one canonical JSON snapshot per probe per fixture under `tests/golden/probes/<probe>/<fixture>.json`. With ~14 Phase-2 language-agnostic probes (the table below) × 5 fixtures (S7-01 + S7-02), the count lands near **~70 goldens**. The CI `portfolio` job (S8-03) diffs live output against committed expected; `pytest --update-golden` regenerates canonically; updating a golden is a deliberate PR step.

**~14 probes covered** (Layer A is mostly Phase-1-covered; Phase-2 contributes Layers B/C/D/E/G):

| Layer | Probes |
|---|---|
| B | `index_health`, `scip_index` (binary blob path — golden records metadata only), `tree_sitter_import_graph`, `dep_graph`, `generated_code`, `node_reflection`, `semantic_index_meta` |
| C | `runtime_trace` (only `minimal-ts` + `distroless-target` — the other fixtures have no Dockerfile or stale-scip-irrelevant), `dockerfile`, `entrypoint`, `shell_usage`, `certificate`, `sbom`, `cve` |
| D | `skills_index`, `conventions`, `adrs`, `repo_notes`, `repo_config`, `policy`, `exceptions`, `external_docs` (mostly `confidence="unavailable"` against fixtures with no skills/policies — that's the load-bearing canonical-empty case) |
| E | `ownership`, `service_topology_stub`, `slo_stub` |
| G | `semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`, `test_coverage_mapping` |

Not every cell is populated — e.g., `runtime_trace` only ships goldens for the two fixtures with a real `Dockerfile` (`minimal-ts`, `distroless-target`); `dep_graph` only for `monorepo-pnpm` (the only fixture with cross-package edges); `gitleaks` for none (the load-bearing `secret_in_source` adversarial fixture lives separately under `tests/adv/phase02/`, not in `tests/fixtures/portfolio/`). Implementer judgement on the empty cells; the story locks the count to "the cells where a probe produces a non-trivially-empty slice against a fixture."

**Golden-file non-determinism is the recurring hazard** (Implementation risk #5). Sources of non-determinism the regen script MUST exclude:

- `wall_clock_ms` — varies per run.
- `generated_at` — wall-clock timestamp.
- Audit-anchor timestamps inside any `runs/<utc-iso>-<short>.json` reference.
- `tmp` paths inside any captured stdout/stderr.
- Environment-derived values: `$USER`, `$HOSTNAME`, `$HOME`, `$PWD`.
- BLAKE3 fingerprints of cleartext **plaintext** (the fingerprint of the cleartext IS deterministic and DOES go into the golden — but only the 8-hex fingerprint, never the cleartext itself, per ADR-0005).
- Image digests captured at probe-run time that are **not** declared-input tokens — only the `ProbeContext.image_digest_resolver` resolved digest goes in (deterministic per fixture; the resolver result is committed in `distroless-target/built-image.digest`).
- `node --version` cross-check output from `NodeBuildSystemProbe` if the CI runner's Node differs from the fixture's `.nvmrc` (per S2-03 Phase-1 note — the regen script disables this cross-check to keep the golden deterministic OR pins the regen environment's Node version; same applies to other tool-version cross-checks).

The discipline that anchors all of this: **run `scripts/regen_golden.py` twice locally before opening the Step 7 PR; verify the second run produces zero file changes** (same Phase-1 Step-6 discipline). If the second run produces diffs, a non-deterministic field has slipped past the exclusion list; fix the exclusion before merging.

Goldens are written as canonical JSON: keys sorted at every level (Python's `json.dumps(..., sort_keys=True, indent=2)` plus an explicit recursive `_canonicalize` for tuple-vs-list normalization and `None`-vs-missing-key normalization). Indentation is 2 spaces; trailing newline; UTF-8; LF endings. The same canonical-JSON conventions Phase 1 Step 6 set.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Golden files"` — the table this story implements.
  - `../phase-arch-design.md §"Implementation risks"` #5 (golden-file non-determinism — the central hazard).
  - `../phase-arch-design.md §"Goals"` G1 (every Layer B–G language-agnostic probe ships with golden-file coverage).
- **Phase ADRs:** ADR-0004 (image-digest token — `distroless-target` goldens include the resolved digest verbatim), ADR-0005 (no plaintext — scanner goldens carry `<REDACTED:fp=...>` strings), ADR-0010 (`RedactedSlice` shape — scanner goldens render the `RedactedSlice` JSON, not a raw dict).
- **Implementation plan:** `../High-level-impl.md §"Step 7"` — `scripts/regen_golden.py` bullets, exclusion list, two-runs-byte-identical discipline.
- **Source design:** `../final-design.md §"Open questions"` #5 (golden-file regeneration policy — this story implements the named discipline).
- **Existing code:**
  - Phase 1's `scripts/regen_golden.py` and the goldens under `tests/golden/` (S6-01 + S6-02-bench-anchor) — convention precedent; this story extends rather than rewrites.
  - All five fixture trees from S7-01 + S7-02.
  - Every Phase-2 probe under `src/codegenie/probes/layer_{b,c,d,e,g}/`.

## Goal

Three deliverables:

1. **`scripts/regen_golden.py`** extended (or rewritten as the Phase-2 version layered on the Phase-1 base) to iterate over `tests/fixtures/portfolio/<fixture>/` for every fixture, run `codegenie gather` against each, capture the resulting `repo-context.yaml` plus each `.codegenie/context/raw/<probe>.json`, canonicalize per-probe (sorted keys, exclusion list, LF endings, trailing newline), and write `tests/golden/probes/<probe>/<fixture>.json`. The script accepts `--check` (CI mode — diffs live output vs. committed; non-zero exit on diff) and `--update` (developer mode — overwrites).
2. **~70 golden files** under `tests/golden/probes/<probe>/<fixture>.json` — one per fixture per probe that produces a non-trivially-empty slice against that fixture. The exact count is determined by the implementer's judgment on which cells produce non-empty slices; document the count in the PR description.
3. **A pytest harness** (`tests/golden/test_goldens_match.py`) that invokes `regen_golden.py --check` mode against the fixture portfolio and asserts zero diffs. CI `portfolio` job will run this; locally `pytest --update-golden` regenerates by invoking `regen_golden.py --update`.

## Acceptance criteria

**`scripts/regen_golden.py` shape**

- [ ] **AC-1.** `scripts/regen_golden.py` exists; passes `mypy --strict`; passes `ruff check` + `ruff format --check`.
- [ ] **AC-2 — modes.** Script supports `--check` (exit 0 if every golden matches live output, exit 1 with a diff summary otherwise) AND `--update` (overwrite every golden with the canonicalized live output). Default mode is `--check`. The two flags are mutually exclusive (`argparse` `add_mutually_exclusive_group`).
- [ ] **AC-3 — fixture iteration.** Script walks `tests/fixtures/portfolio/` for every subdirectory NOT prefixed `_` (the `_shape_test_kernel.py` does not appear here, but defending the convention). For each fixture, invokes `codegenie gather <fixture-path>` via `run_allowlisted` (NEVER `subprocess.run` directly — this is the audit hygiene); captures the output tree.
- [ ] **AC-4 — per-probe golden write.** For each fixture, for each probe that produced a slice in the live run, the script:
  - Reads the slice from `<fixture>/.codegenie/context/raw/<probe>.json`.
  - Canonicalizes (`_canonicalize` — recursive: sorted keys at every level, tuple → list normalization, `None` → `null` not missing).
  - Applies the exclusion list (AC-7).
  - Writes `tests/golden/probes/<probe>/<fixture>.json` with `json.dumps(..., sort_keys=True, indent=2, ensure_ascii=False)` + trailing LF.
- [ ] **AC-5 — empty-cell handling.** If a probe produced **no slice** for a fixture (e.g., `dep_graph` against `minimal-ts` — no cross-package edges), the script writes NO golden file for that cell. The CI `--check` accordingly does NOT require a golden file for that cell. (An empty-but-present slice — e.g., `confidence="unavailable"` — IS a golden cell; the empty *cell* is when the probe did not register a slice at all.)
- [ ] **AC-6 — canonical JSON ordering.** Every key at every nesting level is sorted. Lists preserve insertion order (Python's `json.dumps` does — but list contents themselves may need canonicalization for sets-of-dicts; if a probe emits a `findings: list[dict]`, the implementer adds a sort key per probe, documented in `regen_golden.py`'s top-of-file comment). For Phase 2 the only probes producing unordered-list slices are `semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks` (`findings`) and `dep_graph` (`edges`) — each gets an explicit sort tuple.

**Exclusion list (load-bearing — Risk #5 defense)**

- [ ] **AC-7 — exclusion list.** `regen_golden.py` excludes from every golden:
  - Any field named `wall_clock_ms`.
  - Any field named `generated_at`.
  - Any field named ending in `_timestamp`.
  - Any string field whose value matches `r"/(tmp|var/folders)/[^/]+/"` (`tmp` paths).
  - Any field whose value contains an **unambiguous** envvar value: `os.environ.get(name, "")` is checked for substring presence ONLY if the value is **non-empty AND ≥ 4 characters** AND not in a closed deny-list of common short tokens (`{"ci", "root", "home", "user", "test"}`). For each skipped envvar a `WARNING` is logged to stderr explaining why (e.g., `WARNING: $USER='ci' too short/ambiguous for substring scrub; rely on tmp-path + named-field exclusions instead`). This prevents trivially-common values from scrubbing legitimate occurrences of "ci" / "root" in golden output.
  - The `audit_anchor.run_id` field (which is by definition a per-run UUID/timestamp pair).
- [ ] **AC-8 — exclusion list documented.** The exclusion list is a module-level frozen tuple in `regen_golden.py` (e.g., `_EXCLUDED_FIELD_NAMES`, `_EXCLUDED_VALUE_PATTERNS`), discoverable by `grep`. Adding an exclusion is a deliberate edit. Document each exclusion in a comment naming the source of non-determinism.
- [ ] **AC-9 — ADR-0005 plaintext-fingerprint allowed.** The 8-hex BLAKE3 fingerprint emitted by `SecretRedactor` IS deterministic and IS included in the golden — verified by a per-scanner golden that contains a `"fingerprints": ["a1b2c3d4"]`-shaped value. Plaintext NEVER appears.
- [ ] **AC-10 — `image_digest` exception.** `distroless-target` goldens for `runtime_trace`/`sbom`/`cve`/`dockerfile` include the **resolved image digest** (per ADR-0004) verbatim — the digest is a declared-input token, deterministic per fixture (committed in `distroless-target/built-image.digest`). The exclusion list does NOT strip `image_digest` fields.

**~70 goldens land on disk**

- [ ] **AC-11.** `tests/golden/probes/` exists as the root of the per-probe golden tree.
- [ ] **AC-12 — `index_health` goldens.** Five files at `tests/golden/probes/index_health/<fixture>.json` for `minimal-ts`, `native-modules`, `monorepo-pnpm`, `distroless-target`, `stale-scip`. The `stale-scip` golden's `freshness` is `{"kind": "Stale", "reason": {"kind": "CommitsBehind", "n": <integer>=1>, "last_indexed": "<prior-sha>"}}` — the literal load-bearing shape.
- [ ] **AC-13 — `scip_index` goldens.** Goldens are the **metadata** slice only (`scip_index_present: true, indexer_version: "...", indexer_invocation_succeeded: true, output_path_relative: ".codegenie/context/raw/scip-index.scip"`); the binary blob itself is not a golden (binary equality across runs is too brittle). One per fixture where SCIP was successfully indexed; `stale-scip` records the pre-existing-blob path; `native-modules` may register `confidence="unavailable"` (no TS sources).
- [ ] **AC-14 — `tree_sitter_import_graph` goldens.** One per fixture where `.ts` sources exist; `monorepo-pnpm` golden records the cross-package `import` edges (the load-bearing case).
- [ ] **AC-15 — `dep_graph` goldens.** Phase-2 dep-graph registry has zero strategies; the golden for every fixture is `{"confidence": "low", "reason": "no_strategy_for_ecosystem", ...}` (per S4-05's typed output). This is the explicit Open/Closed seam — Phase 3 fills strategies and Phase 3 regenerates affected goldens.
- [ ] **AC-16 — `runtime_trace` goldens.** `minimal-ts` + `distroless-target` only; per-scenario `TraceScenarioCompleted | TraceScenarioFailed | TraceScenarioSkipped` outcomes; `distroless-target`'s `image_digest` matches `built-image.digest`. The golden is committed against the **Linux-runner shape only**. macOS regen produces a different shape (`TraceScenarioFailed(StraceUnavailable())`); to prevent silent golden divergence, **`scripts/regen_golden.py --portfolio` errors out with exit code 2 on non-Linux platforms** (`sys.platform != "linux"`), printing a structured stderr message: `"regen_golden.py --portfolio requires Linux (CI: ubuntu-24.04). runtime_trace goldens cannot be regenerated on {platform}; run on a Linux box or via the CI runner."` Rule 12 (fail loud) drives this choice; deferred to S8-03 only the *enforcement* of "all PRs that touch goldens were regenerated on Linux" (commit-trailer check). `--check` mode (read-only) still runs on every platform.
- [ ] **AC-17 — `dockerfile`/`entrypoint`/`shell_usage`/`certificate` goldens.** Per fixture with a `Dockerfile` (`minimal-ts`, `monorepo-pnpm`, `distroless-target`); `distroless-target` records `USER == null` (distroless default-nonroot).
- [ ] **AC-18 — `sbom`/`cve` goldens.** Per fixture with a built image (`distroless-target` only; the others' Dockerfiles are not built in regen — runtime_trace builds for the trace, but SBOM probe relies on the runtime_trace's built image). Both goldens record `ScannerRan(...)`-shaped outputs; the `cve` golden's findings list is sorted deterministically.
- [ ] **AC-19 — `skills_index`/`conventions`/`adrs`/`repo_notes`/`repo_config`/`policy`/`exceptions` goldens.** Per fixture; mostly `confidence="unavailable"` against fixtures with no skills/policies — that's the canonical-empty case that proves the probes don't crash on the negative path. (Phase 2 fixtures don't seed `.codegenie/skills/`; that's a Phase-3+ test-surface concern.)
- [ ] **AC-20 — `external_docs` goldens.** All five record `confidence="unavailable", reason="not_opted_in"` (per S6-04).
- [ ] **AC-21 — `ownership`/`service_topology_stub`/`slo_stub` goldens.** Per fixture; mostly empty/unavailable; absence of `CODEOWNERS` → `confidence="low"`.
- [ ] **AC-22 — `semgrep`/`ast_grep`/`ripgrep_curated` goldens.** Per fixture; `confidence` reflects tool presence; findings (if any) flow through `SecretRedactor` and the golden records the `RedactedSlice` JSON shape. Findings list is sorted by `(rule_id, file, line, column)`.
- [ ] **AC-23 — `gitleaks` goldens.** Per fixture; the `secret_in_source` adversarial test (S6-07) lives under `tests/adv/phase02/` against its own fixture, NOT against the portfolio fixtures — so portfolio-fixture `gitleaks` goldens are all `ScannerRan(findings_count=0, fingerprints=[])` (proves the scanner runs and finds nothing in the curated fixtures, which is itself a load-bearing assertion).
- [ ] **AC-24 — `test_coverage_mapping` goldens.** Per fixture with tests; `minimal-ts` + `monorepo-pnpm` qualify; the others are empty-cells (no goldens).
- [ ] **AC-25 — golden count is deterministic, not a range.** `scripts/regen_golden.py` exposes a module-level function `_compute_expected_golden_count() -> int` that enumerates the closed set of `(probe, fixture)` cells that ARE expected to produce a golden (the dual of the AC-5 empty-cell rule), drawing from a single declarative table (`_PROBE_FIXTURE_MATRIX: dict[ProbeName, frozenset[FixtureName]]` — grep-discoverable). `tests/golden/probes/COUNT.txt` records that exact integer (committed). A unit test (`tests/golden/test_golden_count_matches.py`) asserts: (a) on-disk golden count == `COUNT.txt`; (b) `COUNT.txt` == `_compute_expected_golden_count()`. Adding or removing a `(probe, fixture)` cell requires editing `_PROBE_FIXTURE_MATRIX` AND `COUNT.txt` in the same commit. The PR description records the count for human review; the test enforces it.

**Two-runs-byte-identical discipline (Risk #5 defense)**

- [ ] **AC-26 — local two-runs verification (PR-merge discipline).** PR description records: "`python scripts/regen_golden.py --update --portfolio` was run twice locally on Linux; the second run produced zero file changes (`git diff --stat` empty)." This is documentation discipline for the human reviewer; the CI assertion in AC-27 is the load-bearing guarantee.
- [ ] **AC-27 — CI two-runs idempotence is a gating test in this story.** A unit-level test `tests/golden/test_regen_golden_portfolio_idempotent.py` (Linux-only via `pytest.mark.skipif(sys.platform != "linux", reason="regen --portfolio requires Linux runner")`) invokes `scripts/regen_golden.py --update --portfolio` twice against a temp-copy of `tests/fixtures/portfolio/`, then asserts the second invocation produced zero file changes (via SHA256 of every committed golden, before and after the second run). This **promotes the S6-01 HARDENED precedent** ("humans miss things; CI doesn't") from a manual sha256 check to a CI gate **now**, not in S8-03. S8-03 wires the same assertion at the `portfolio` job lane; this story's unit test guarantees the assertion exists before that lane is wired.

**`tests/golden/test_goldens_match.py` harness**

- [ ] **AC-28.** `tests/golden/test_goldens_match.py` exists; runs `scripts/regen_golden.py --check` as a subprocess (via `run_allowlisted`); asserts exit code 0; on failure, prints the diff summary in the pytest failure message.
- [ ] **AC-29 — `pytest --update-golden` flag.** Adding a `--update-golden` flag to `tests/conftest.py` runs `regen_golden.py --update` before the assertions. Test invocations: `pytest tests/golden/` (check mode, default), `pytest tests/golden/ --update-golden` (regenerate then check).
- [ ] **AC-30 — failure message includes the failing path AND unified-diff format.** When a golden mismatch fires, the failure message names the exact file path (`tests/golden/probes/dep_graph/monorepo-pnpm.json`) AND a unified-diff excerpt (`difflib.unified_diff` with `n=3`). A unit test (`tests/golden/test_failure_message_shape.py`) feeds a synthetic mismatch into `regen_golden.py --check` and asserts the stderr/exception text contains: (a) the relative golden path, (b) at least one `---` line, (c) at least one `+++` line, (d) at least one `@@ ... @@` hunk header. "5 lines of context" alone is too weak — the unified-diff markers are the structural assertion a CI-log reader needs.

**Determinism, audit hygiene, type cleanliness**

- [ ] **AC-31 — `mypy --strict`** on `scripts/regen_golden.py` AND `tests/golden/test_goldens_match.py`.
- [ ] **AC-32 — no plaintext in goldens; patterns imported from `SecretRedactor`.** A test (`tests/golden/test_no_plaintext_in_goldens.py`) `grep`-walks every golden under `tests/golden/probes/` and asserts no string matches the production redactor patterns. Patterns are **imported from `codegenie.output.sanitizer._PATTERNS`** (the source-of-truth tuple-list per ADR-0005), NOT hardcoded in the test file. The test parametrizes over `(golden_path, (pattern_class, pattern))` and any future pattern added to `_PATTERNS` is automatically picked up. Drift between the production redactor and the golden-leak audit becomes a compile-time `ImportError`, not a silent miss. Defense-in-depth on top of `SecretRedactor` (the redactor is supposed to catch this; the goldens are committed text and a stray paste during fixture authoring would be caught here).
- [ ] **AC-33 — LF endings + trailing newline** on every golden file. Parametrized test over `tests/golden/probes/**/*.json`.

**New ACs from validation hardening**

- [ ] **AC-34 — atomic write.** `regen_golden.py --update` writes every golden via `tempfile.NamedTemporaryFile(dir=<golden-parent-dir>, delete=False)` + `os.replace(tmp, final)`. A SIGINT or crash mid-write never leaves a partial golden on disk. Unit test: `tests/golden/test_atomic_write.py` patches `os.replace` to raise mid-write and asserts the original golden is untouched.
- [ ] **AC-35 — `scripts/regen_golden.py` exposes a stable Open/Closed seam for new fixtures.** Adding a new fixture under `tests/fixtures/portfolio/<new-fixture>/` (per S7-01/S7-02 conventions: `_shape_test_kernel.py`-compatible) MUST require zero edits to `regen_golden.py` — the script discovers fixtures by `git ls-files`-rooted directory walk (skipping `_`-prefixed names). A test (`tests/golden/test_regen_open_closed_seam.py`) creates a temporary fixture directory inside a `tmp_path` copy of the portfolio root, invokes `regen_golden.py --check --portfolio --portfolio-root <tmp_path>`, and asserts the new directory was discovered without any code-path edits. (The `--portfolio-root` flag is added to support the test; default is `tests/fixtures/portfolio/`.)
- [ ] **AC-36 — clean-slate per-fixture regen.** Before invoking `codegenie gather` against a fixture, `regen_golden.py --update` removes `<fixture>/.codegenie/context/` (raw artifacts + runs) so a stale cache hit doesn't produce a different slice shape. The deletion is logged to stderr at INFO via structlog (`{"event": "regen.clear_codegenie_context", "fixture": "<name>"}`). The fixture's `.codegenie/cache/` is NOT touched (this would defeat S7-01's `.codegenie/cache/` not-committed guarantee — there's nothing to clear). The `--update` mode is destructive-by-design; the `--check` mode does NOT clear anything (idempotent read).
- [ ] **AC-37 — `_PRESERVED_FIELDS` inclusion-list (complement to AC-7 exclusion list).** Declared-input tokens and deterministic fingerprints are explicitly preserved: a module-level `_PRESERVED_FIELDS: frozenset[str]` lists at minimum `{"image_digest", "output_path_relative", "fingerprint", "fingerprints", "last_indexed"}` plus their dotted-path qualified variants. Conflict resolution rule (also asserted by `tests/golden/test_preserved_fields_win.py`): **inclusion always wins over exclusion** — if an exclusion pattern would match a field name in `_PRESERVED_FIELDS`, the field is preserved. Each entry's rationale lives in a sibling comment. Adding a new declared-input token (Phase 3+) is a deliberate one-line edit.
- [ ] **AC-38 — Phase 1 fixture coexistence + non-collision.** Phase 1's `tests/fixtures/node_typescript_helm/` is **not** under `tests/fixtures/portfolio/` and is **not** swept by `regen_golden.py --portfolio`. S6-01's YAML golden at `tests/golden/node_typescript_helm.repo-context.yaml` remains the canonical artifact for Phase 1's fixture. Two enforcing tests:
  - `tests/golden/test_phase1_yaml_golden_untouched.py` — snapshots the SHA256 of `tests/golden/node_typescript_helm.repo-context.yaml` before invoking `regen_golden.py --portfolio --update` against the temp portfolio and asserts the SHA256 is unchanged after.
  - `tests/golden/test_no_phase1_per_probe_collision.py` — asserts no file matches `tests/golden/probes/*/node_typescript_helm.json` (Phase 1's fixture name must not collide with the portfolio per-probe tree). If Phase 7+ wants to *also* land per-probe JSON goldens for `node_typescript_helm`, that is a deliberate later PR with its own validation step.
- [ ] **AC-39 — typed canonicalize signature (no `Any`).** The recursive `_canonicalize` function uses a typed `JsonValue` recursive union: `JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]`. Signature: `def _canonicalize(payload: JsonValue) -> JsonValue`. `mypy --strict` exercises this. No `Any` threads through the script (one explicit `cast(JsonValue, json.load(fp))` at the I/O boundary is the only acceptable narrow). A test (`tests/golden/test_canonicalize_type_purity.py`) does an `ast`-walk of `scripts/regen_golden.py` and asserts no `: Any` annotation appears on a function argument or return.
- [ ] **AC-40 — `_`-prefixed directory skip is asserted.** AC-3's convention (directories under `tests/fixtures/portfolio/` prefixed `_` are skipped) is asserted by a test (`tests/golden/test_underscore_prefix_skip.py`): create `tests/fixtures/portfolio/_helpers_test/` in a temp copy, invoke `--check --portfolio`, assert no error is raised and no golden is produced under `tests/golden/probes/*/_helpers_test.json`. Defends against a future contributor accidentally promoting a private helper directory to fixture status.

## Implementation outline

1. **Read Phase 1's `scripts/regen_golden.py` (from S6-01).** Understand the convention: which functions do `_canonicalize` work, which write the files, which compute the diff. Decide: extend Phase 1's script with portfolio support, OR write a Phase-2 variant in the same file with `--portfolio` flag. Recommendation: extend, since the canonicalization machinery is identical.
2. **Write `tests/golden/test_goldens_match.py` first (TDD red).** With no goldens on disk, the test asserts every fixture × probe cell that *should* have a golden has one, and assertion fails everywhere.
3. **Extend `regen_golden.py` with `--portfolio` mode** (or the Phase-2 equivalent). The new code path: iterate `tests/fixtures/portfolio/`, run `codegenie gather` via `run_allowlisted`, capture each `<fixture>/.codegenie/context/raw/<probe>.json`, canonicalize per AC-4..AC-10, write `tests/golden/probes/<probe>/<fixture>.json`.
4. **First regen run.** `python scripts/regen_golden.py --update --portfolio`. This produces all goldens. Inspect a sample (`tests/golden/probes/index_health/stale-scip.json`) and confirm the load-bearing `Stale(reason=CommitsBehind(...))` shape is present and JSON-canonical.
5. **Second regen run.** `python scripts/regen_golden.py --update --portfolio` again. `git diff --stat` MUST be empty. If not: the diff names the offending field; add it to the exclusion list (AC-7) with a commented rationale.
6. **Loop step 5 until the second run is a no-op.** Common offenders: a transitive timestamp inside a `runs/<utc-iso>` audit anchor reference, a `tmp` path inside a captured stderr tail, an envvar leak.
7. **Run the harness.** `pytest tests/golden/test_goldens_match.py`. Green.
8. **Plant the count guard.** `wc -l tests/golden/probes/**/*.json | tail -n 1` → record the count in `tests/golden/probes/COUNT.txt`. Plant the test (`tests/golden/test_golden_count_matches.py`) that asserts the on-disk count equals `COUNT.txt`.
9. **Plant the plaintext-leak guard.** `tests/golden/test_no_plaintext_in_goldens.py` per AC-32.
10. **Final pass.** `mypy --strict`, `ruff check`, `ruff format --check`. Run the full Phase 2 test suite. Green.

## TDD plan — red / green / refactor

### Red — failing harness first

```python
# tests/golden/test_goldens_match.py (excerpt)
import subprocess
from pathlib import Path
from codegenie.exec import run_allowlisted

_REPO_ROOT = Path(__file__).parent.parent.parent

def test_goldens_match_live_output() -> None:
    """Run `regen_golden.py --check --portfolio` and assert zero diffs."""
    result = run_allowlisted(
        ["python", str(_REPO_ROOT / "scripts" / "regen_golden.py"), "--check", "--portfolio"],
        cwd=_REPO_ROOT, timeout_seconds=600,
    )
    assert result.exit_code == 0, (
        f"Golden file mismatch — diff summary follows:\n{result.stderr_tail.decode()}"
    )
```

Before goldens exist, the test fails red (`--check` reports every fixture × probe cell as missing).

Plus the count guard:

```python
# tests/golden/test_golden_count_matches.py
from pathlib import Path
def test_committed_golden_count_matches_count_file() -> None:
    root = Path(__file__).parent / "probes"
    expected = int((root / "COUNT.txt").read_text().strip())
    actual = sum(1 for _ in root.rglob("*.json"))
    assert actual == expected, (
        f"Golden count drift: committed {actual} files, COUNT.txt says {expected}. "
        f"Update COUNT.txt as a deliberate PR step."
    )
```

And the plaintext-leak guard:

```python
# tests/golden/test_no_plaintext_in_goldens.py
import re
from pathlib import Path
import pytest

_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"npm_[A-Za-z0-9]{36}"),
    re.compile(r"sk-ant-[A-Za-z0-9-]{30,}"),
    re.compile(r"-----BEGIN RSA PRIVATE KEY-----"),
    # eyJ-prefix JWT is too noisy (matches base64 blobs); leave to gitleaks
]

@pytest.mark.parametrize("path", sorted((Path(__file__).parent / "probes").rglob("*.json")),
                          ids=lambda p: p.name)
def test_no_plaintext_in_golden(path: Path) -> None:
    text = path.read_text()
    for pat in _PATTERNS:
        assert not pat.search(text), (
            f"{path} contains a string matching {pat.pattern!r} — "
            f"SecretRedactor failure mode? Plaintext must not appear in goldens (ADR-0005)."
        )
```

### Green — make it pass

Extend `regen_golden.py` per the outline. Run `--update --portfolio` twice. Plant `COUNT.txt`. Re-run the harness. Green.

### Mutation-resistance witness table

| Mutation | Test that catches it |
|---|---|
| `regen_golden.py` forgets to canonicalize one field (sorted-keys regression) | `test_goldens_match_live_output` — the diff fires on every run |
| A new field `wall_clock_ms_v2` slips into a probe's slice without being added to the exclusion list | `test_goldens_match_live_output` — second-run-no-op breaks |
| A contributor "fixes" the `stale-scip` golden to reflect `kind: Fresh` (silently breaking the load-bearing exit) | `tests/adv/phase02/test_stale_scip_fixture.py` (S4-02) — still fails first; the golden is consistent with the gather output but the assertion test catches the regression at the probe level |
| A stray plaintext `AKIA...` slips into a golden (e.g., implementer pasted a real key during fixture authoring) | `test_no_plaintext_in_golden[*]` |
| Implementer adds a golden without updating `COUNT.txt` | `test_committed_golden_count_matches_count_file` + `_compute_expected_golden_count()` parity (AC-25) |
| Implementer deletes a golden without updating `COUNT.txt` | Same |
| Implementer adds a `(probe, fixture)` cell silently (touches no count guard) | `_compute_expected_golden_count()` derived from `_PROBE_FIXTURE_MATRIX` — adding a cell without editing the matrix means the matrix → count assertion fails (AC-25) |
| `--update` silently overwrites a golden the implementer didn't intend to update | `git diff` in the PR — the file's bytes change visibly. PR review catches it |
| `--update` is interrupted mid-write leaving half a golden on disk | `test_atomic_write.py` — patched `os.replace` failure asserts file is untouched (AC-34) |
| Second `--update` produces drift (non-determinism slipped past exclusion list) | `test_regen_golden_portfolio_idempotent.py` — CI gate, not PR-description-only (AC-27) |
| macOS regen produces shape-divergent goldens, contributor commits anyway | `--update --portfolio` exits 2 on non-Linux with a clear stderr message (AC-16) |
| Plaintext leaks past `SecretRedactor` due to a new pattern added after this story landed | `test_no_plaintext_in_goldens.py` imports `_PATTERNS` directly — new pattern is automatic (AC-32) |
| `_PRESERVED_FIELDS` regression — a future exclusion regex inadvertently scrubs `fingerprint` | `test_preserved_fields_win.py` — inclusion always wins (AC-37) |
| A new fixture is added to `tests/fixtures/portfolio/` but `regen_golden.py` doesn't pick it up | `test_regen_open_closed_seam.py` — zero-edit discovery asserted (AC-35) |
| Phase 1's `node_typescript_helm.repo-context.yaml` is mutated by S7-03's regen | `test_phase1_yaml_golden_untouched.py` — SHA256 snapshot (AC-38) |
| A future contributor creates `_helpers/` under `tests/fixtures/portfolio/` and accidentally triggers a fixture pass | `test_underscore_prefix_skip.py` (AC-40) |
| Failure message is a wall of text with no diff markers — CI log unreadable | `test_failure_message_shape.py` asserts `---`, `+++`, `@@` (AC-30) |
| `Any`-typed helper sneaks into `_canonicalize` defeating mypy --strict | `test_canonicalize_type_purity.py` ast-walk (AC-39) |
| CRLF endings on a golden via Windows checkout | A line-endings test on `tests/golden/probes/**/*.json` (AC-33) |

### Refactor — clean up

- The exclusion list is the load-bearing audit surface. **Document each exclusion's source-of-non-determinism in a comment**. A future contributor reading the list should be able to defend every entry — if they cannot, the entry is over-broad and should narrow.
- For probes whose slice contains lists-of-dicts (`semgrep.findings`, `gitleaks.findings`, `dep_graph.edges`), the explicit sort tuple lives next to the probe in the script:
  ```python
  _LIST_SORT_KEYS: dict[str, tuple[str, ...]] = {
      "semgrep.findings": ("rule_id", "file", "line", "column"),
      "ast_grep.findings": ("rule_id", "file", "line", "column"),
      "ripgrep_curated.findings": ("rule_id", "file", "line"),
      "gitleaks.findings": ("rule_id", "file", "line", "fingerprint"),  # fingerprint, NOT plaintext
      "dep_graph.edges": ("from", "to"),
  }
  ```
  Adding a probe that emits a list-of-dicts requires extending this dict — one line. The convention is grep-discoverable.
- `regen_golden.py`'s `_canonicalize` function is mypy-strict; the `Any` payload threads through one type-narrowed dispatch. No untyped helpers.
- The PR description records the count, the second-run-byte-identical check result, and the explicit list of exclusions added (if any) beyond the AC-7 baseline.

## Files to touch

| Path | Why |
|---|---|
| `scripts/regen_golden.py` (extend with `--portfolio` mode; or create if S6-01 hasn't shipped) | The canonical-JSON regen script + exclusion list + inclusion list + `_PROBE_FIXTURE_MATRIX` + `_compute_expected_golden_count()` |
| `tests/golden/probes/<probe>/<fixture>.json` (count == `_compute_expected_golden_count()`) | The committed goldens |
| `tests/golden/probes/COUNT.txt` | Count guard against silent golden additions/deletions (asserted equal to `_compute_expected_golden_count()`) |
| `tests/golden/test_goldens_match.py` | The CI harness — invokes `--check` mode and surfaces diffs (AC-28, AC-30) |
| `tests/golden/test_golden_count_matches.py` | Count guard (AC-25) |
| `tests/golden/test_no_plaintext_in_goldens.py` | Defense-in-depth ADR-0005 enforcement; patterns imported from `codegenie.output.sanitizer._PATTERNS` (AC-32) |
| `tests/golden/test_regen_golden_portfolio_idempotent.py` | Two-runs-byte-identical CI assertion (AC-27) |
| `tests/golden/test_failure_message_shape.py` | Unified-diff format assertion (AC-30) |
| `tests/golden/test_atomic_write.py` | Atomic write defense (AC-34) |
| `tests/golden/test_regen_open_closed_seam.py` | Open/Closed seam for new fixtures (AC-35) |
| `tests/golden/test_preserved_fields_win.py` | Inclusion-list-wins-over-exclusion-list (AC-37) |
| `tests/golden/test_phase1_yaml_golden_untouched.py` | S6-01 YAML golden non-collision (AC-38) |
| `tests/golden/test_no_phase1_per_probe_collision.py` | Phase-1 fixture name non-collision (AC-38) |
| `tests/golden/test_canonicalize_type_purity.py` | No `: Any` in canonicalize signatures (AC-39) |
| `tests/golden/test_underscore_prefix_skip.py` | Private-directory skip (AC-40) |
| `tests/conftest.py` (add `--update-golden` flag) | Developer convenience (AC-29) |

## Out of scope

- **Adversarial corpus** (`hostile_skills_yaml`, `concurrent_gather_race`, `no_inmemory_secret_leak`, `phase3_handoff_smoke`) — S7-04.
- **Property tests + portfolio sweep integration** — S7-05.
- **CI wiring** (`portfolio` job that runs the harness on every PR) — S8-03.
- **`scip-index.scip` binary-golden equality** — out; SCIP blob bytes are too brittle across `scip-typescript` versions. Phase 2 commits the metadata slice only (AC-13).
- **`bench`-canary goldens** (wall-clock baselines under `tests/bench/baselines/`) — S8-03 owns the bench infrastructure; this story is golden-FILES only.
- **`runtime_trace` macOS shape goldens** — out; regen-on-Linux-only discipline (AC-16). macOS regen produces `StraceUnavailable()` which is deterministic but documented as a separate code path, not a golden.

## Notes for the implementer

- **Risk #5 is the load-bearing risk this story defends.** The mandatory PR-merge prerequisite is: "`scripts/regen_golden.py --update --portfolio` was run twice locally; the second run produced zero file changes." Record this verbatim in the PR description. Run the second pass on a fresh shell to avoid any in-memory caching artifact. If the second run produces diffs, **find and fix the source of non-determinism** before merging — don't add an exclusion without understanding what's being excluded.
- **The exclusion list (AC-7) is a load-bearing audit surface.** Each entry should be defensible. Common temptation: adding `*_count` to exclusions because a probe's count varies — that's wrong; the count is supposed to be deterministic across runs, and a varying count means the probe itself is non-deterministic. Fix the probe, not the exclusion list. Acceptable exclusions are wall-clock, tmp-path, envvar-leak only.
- **`dep_graph` goldens reflect Phase-2's zero-strategy state.** Every fixture's `dep_graph` golden records `{"confidence": "low", "reason": "no_strategy_for_ecosystem", ...}`. When Phase 3 lands the first strategy (per S4-05's Open/Closed registry), it regenerates `monorepo-pnpm`'s `dep_graph` golden (the one fixture with cross-package edges) — that's a deliberate Phase-3 PR, not a Phase-2 surprise. Document this in `dep_graph/monorepo-pnpm.json`'s top-level `"_phase2_note": "Phase 2 ships with zero dep-graph strategies; Phase 3 fills the registry."` field (if the schema allows; otherwise in the script's commit-message commentary).
- **`stale-scip/index_health` golden is the load-bearing one.** Its `freshness` field must be exactly `{"kind": "Stale", "reason": {"kind": "CommitsBehind", "n": <integer>=1>, "last_indexed": "<prior-sha>"}}`. The `n` value is whatever `git rev-list --count <prior-sha>..HEAD` returns for the fixture's two-commit history (= 1, given AC-18 of S7-02). If `n` is greater than 1 in your regen, the fixture has drifted (more commits added without updating `last-indexed-commit.txt`) — re-anchor it before committing the golden.
- **`distroless-target` goldens include the resolved image digest** (per AC-10 + ADR-0004). Make sure `built-image.digest` (gitignored, but generated by `distroless-target/regenerate.sh`) exists at regen time. Document the dependency in the script: if `built-image.digest` is missing, the script emits a clear error pointing to `tests/fixtures/portfolio/distroless-target/regenerate.sh`.
- **Run regen on Linux for the canonical truth.** macOS regen produces shape-divergent goldens (`runtime_trace` records `StraceUnavailable()`; some BLAKE3 paths may differ if Python's hashlib varies by platform — should not, but verify). The CI runner is `ubuntu-24.04`; for golden authoring, run on Linux. If you regen on macOS, the script should emit a one-line warning `"WARNING: macOS regen — runtime_trace goldens will differ from CI Linux runner. Re-run on Linux before merging."`
- **`pytest --update-golden` is the developer convenience flag.** Implement it via a `conftest.py` `pytest_addoption` + a `pytest_collection_modifyitems` that injects an `--update` invocation before the assertion runs. Document in `tests/golden/README.md`.
- **Why no `gitleaks` portfolio-fixture goldens with findings.** The `secret_in_source` adversarial fixture (S6-07) lives under `tests/adv/phase02/`, not `tests/fixtures/portfolio/`. Portfolio fixtures are happy-path; their `gitleaks` goldens are all `findings_count=0` (which is itself a load-bearing assertion: `gitleaks` ran, found nothing in the curated fixtures, did not crash). Adversarial fixtures + their goldens live separately; their golden discipline is identical but their location is `tests/golden/adv-phase02/` (out of scope for this story; S7-04 may or may not commit adversarial-fixture goldens — implementer's call there).

- **`_LIST_SORT_KEYS` should be keyed by typed probe name.** The example in Refactor uses raw `str` keys (`"semgrep.findings"`). Per S7-02's `_ProbeName` Literal precedent (the shared kernel at `tests/fixtures/_shape_test_kernel.py`), use a typed key: `_LIST_SORT_KEYS: dict[tuple[ProbeName, str], tuple[str, ...]]` where `ProbeName` is imported from `tests.fixtures._shape_test_kernel`. Single source of truth for probe names across the test harness; a typo (`"semgreps.findings"`) becomes a mypy error rather than a silent no-op.
- **S6-01 / S7-03 coexistence.** Phase 1 S6-01 owns `tests/golden/<fixture>.repo-context.yaml` (envelope-level YAML, sentinel-normalized `generated_at` + `repo.git_commit`, `_GOLDEN_PAIRS` seam). S7-03 owns `tests/golden/probes/<probe>/<fixture>.json` (slice-level JSON, field-excluded non-determinism, `_PROBE_FIXTURE_MATRIX` seam). They share `_canonicalize` only. If S6-01 hasn't shipped at executor time, create `scripts/regen_golden.py` from scratch with the `--portfolio` mode reserved as the *only* mode for now; structure the file so S6-01 can later land its `--fixture-yaml` mode alongside without `main()` edits (Open/Closed). If S6-01 has shipped, extend in place; add a `--portfolio` flag to the existing argparse; do NOT touch S6-01's `_GOLDEN_PAIRS` tuple, its sentinel normalization, or its YAML writer.
- **macOS error-out rationale.** Rule 12 (fail loud) drove the choice over the soft "skip with warning" alternative. A macOS contributor who silently skipped would commit a partial regen, push, and CI would diff against the unchanged Linux goldens — confusing failure mode. Erroring out at `--update` invocation surfaces the constraint at the earliest possible moment with the clearest possible message. `--check` mode (read-only) still works on every platform because it does not invoke `codegenie gather`; it diffs against committed bytes only.
- **Why `_PRESERVED_FIELDS` is necessary and inclusion-wins is load-bearing.** Without it, a clever exclusion regex (e.g., a future `_HEX_FINGERPRINT_PATTERN` aimed at scrubbing run-id UUIDs) could accidentally scrub the BLAKE3 8-hex fingerprints that ADR-0005 wants preserved. The inclusion list is a defensive co-loop: any field name in `_PRESERVED_FIELDS` short-circuits the exclusion logic. The conflict-resolution rule is asserted by `test_preserved_fields_win.py`, not just commented.
- **`JsonValue` recursive type.** Python 3.12+ supports PEP 695-style recursive `TypeAlias` definitions. The cleanest declaration is at the top of `scripts/regen_golden.py`:
  ```python
  from typing import TypeAlias
  JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
  ```
  Forward-string-quoted self-references survive `mypy --strict`. The single `Any` permitted is at the JSON I/O boundary (`json.load(fp)` returns `Any`); narrow with `cast(JsonValue, ...)` immediately. The `test_canonicalize_type_purity.py` test enforces this by `ast`-walk.

### Patterns DELIBERATELY deferred (premature-abstraction guard)

- **A generic `tests/golden/test_kernel.py` parametrized over `(probe, fixture)` pairs** — defer; `regen_golden.py --check` already does the iteration, and adding a parametrized pytest layer atop it is duplicate work without observable benefit. Re-evaluate if a future contributor needs per-cell debugging (then add `pytest tests/golden/probes/index_health/` selective invocation).
- **Per-probe golden schemas** (a separate `tests/golden/probes/<probe>/_schema.json` that asserts every fixture's golden matches that schema) — defer; the production sub-schemas under `src/codegenie/schema/probes/` already do this at gather time, so the golden is validated upstream. Re-evaluate if probes diverge.
- **`pytest-snapshot` library integration** — defer; the canonical-JSON discipline + the homegrown `regen_golden.py` are the Phase-1 precedent and integrate cleanly with `--check` / `--update`. `pytest-snapshot` would add a dep without changing observable behavior.
