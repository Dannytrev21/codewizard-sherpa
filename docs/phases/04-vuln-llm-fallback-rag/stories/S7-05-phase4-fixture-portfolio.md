# Story S7-05 — Phase-4 fixture portfolio

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** HARDENED (validated 2026-05-24 — see [`_validation/S7-05-phase4-fixture-portfolio.md`](_validation/S7-05-phase4-fixture-portfolio.md))
**Effort:** M
**Depends on:** S7-04 (plugin.yaml + skill templates load); **Phase-3 S8-01 GREEN** (the `tests/fixtures/repos/_portfolio.py` typed manifest + three fence tests this story extends — `test_fixtures_load.py`, `test_fixtures_pinning.py`, `test_fixtures_size_cap.py`); **S4-04** (`codegenie.rag.models.SolvedExample.from_yaml` and `RecordProvenance.verify` — required by the `express-rerun/` load test); **S4-01** (`fastembed-embedder-bootstrap` — exports the `model_digest()` constant the seeded record's `embedding_model` field must match per edge case #19). Soft: S6-02 (retry-bypass test consumes `cassette-attempt-1-fails-attempt-2-passes/`); S5-04 (calibration smoke consumes the `vuln-major-bump/*` fixtures); S7-03 (vuln_provenance adapter consumes `glibc-on-node/` — story lands the fixture, not the classification assertion); S7-06 / S7-07 (E2E tests consume every fixture).
**ADRs honored:** ADR-0008 (the calibration smoke test S5-04 depends on this portfolio), ADR-0009 (inline-harvest confidence gate — the `express-rerun/` seeded record is the substrate for the harvest-shapes-LLM second-run path), ADR-0011 (RAG bypass on retry — `cassette-attempt-1-fails-attempt-2-passes/` is the simulator anchor; ACs here land the fixture shape, S6-02 asserts the bypass behaviour), ADR-0012 (provenance gate explicit tier-zero — `glibc-on-node/` is the refuse anchor; ACs here land the fixture, S7-03 asserts the classification), ADR-0014 (cassette discipline — defines the typed cassette stub shape AC-11 enforces), ADR-0017 (AttemptAnchor event schema — the golden JSONL goldens that depend on these fixtures land in S7-06; called out here for scope), production-ADR-0031 (plugin scoping — every fixture is a Node+npm repo).

## Validation notes

**Validated:** 2026-05-24 · **Verdict:** HARDENED · **Validator:** `phase-story-validator` (automated, scheduled task `story-validation-corrector`)

Four critics returned ~45 findings; the synthesizer collapsed them to one structural rewrite (the AC set) plus targeted TDD-plan replacements. The story's **goal** (land five Phase-4 fixtures the exit-criterion / calibration / retry / provenance / RAG-hit tests consume) is sound and traces cleanly to arch §G1, §G6, §G7, §G11, §"Fixture portfolio" (line 976), and Step 7's "Features delivered" Fixtures bullet — hence **HARDENED**, not RESCUE.

The defects were almost entirely at the **mechanism layer**, not the goal layer: the story forked every discipline Phase-3 S8-01 had just hardened — ad-hoc per-fixture `cve.yaml` files instead of the typed `_portfolio.py` manifest, a parallel inline `FIXTURES = {...}` dict instead of `FixtureSpec`/`CveId`/`parse_cve_id`, raw `text.count("it(") + text.count("test(")` substring proxies instead of real parses, a same-file-read-twice "determinism" check instead of the field-shape pinning fence, and no Open/Closed extension AC. The story also understated its dependency graph (no `S4-04` / `S4-01` / `S7-03` / `Phase-3 S8-01` lines) so the TDD red phase was unrunnable as written (`from codegenie.rag.models import SolvedExample` would error at collection), and was silent on two High-level-impl §Step 7 deliverables (`tests/e2e/scenarios.yaml` Phase-4 rows; `tests/golden/events/` JSONL) that no other story explicitly owns.

Key corrections — twelve block-class, fourteen harden-class, eight nit-class addressed:

1. **`cve.yaml` premise replaced by `_portfolio.py` manifest extension.** The "template" `tests/fixtures/repos/express-cve-2024-21501/` is **empty of `cve.yaml`** on disk (verified: contains only `package.json` + `package-lock.json`). Phase-3 S8-01 explicitly chose the typed manifest, not per-fixture YAML, as the source of truth for CVE ids — every original `cve.yaml` AC has been rewritten to extend the Phase-3 manifest with `FixtureSpec` rows carrying `cve_ids: tuple[CveId, ...]` constructed via `parse_cve_id`. (CN-B-2 / CO-B-1 / DP-B-1 / DP-B-3 / TQ-B-3.)
2. **Inline `FIXTURES = {...}` dict replaced by manifest import.** Story now mandates extending `tests/fixtures/repos/_portfolio.py`'s `Final[tuple[FixtureSpec, ...]]` with five new entries; load test parametrizes over the import. Open/Closed-at-the-file-boundary lifted from S8-01 AC-8 verbatim — adding a sixth Phase-4 fixture is one row + one directory, zero fence-test edits. (CN-B-3 / DP-B-2 / CO-H-7.)
3. **Shared shape-test kernel `tests/fixtures/_shape_test_kernel.py` is now mandated.** The 8-consumer kernel exports `assert_file_exists` / `assert_file_parses` / `assert_file_line_endings` / `assert_no_forbidden_subpath` / `assert_tree_is_closed_set` plus `_FORBIDDEN_SUBPATHS` (bans `node_modules`/`.codegenie`/`dist`/`coverage`/`build`). Story now requires the load test delegate to these helpers; raw `json.loads` / `yaml.safe_load` replaced with `safe_json.load` / `safe_yaml.load` (size + depth caps mirror production §C12). (CN-B-4 / DP-H-5 / TQ-H-4 / TQ-H-5 / TQ-H-8.)
4. **Determinism-theatre test removed.** `b1 = lf.read_bytes(); b2 = lf.read_bytes(); assert b1 == b2` proves nothing about pinning — filesystem physics. Replaced by inheriting S8-01 AC-2's positive field-shape pinning fence (`version` exact-semver, `integrity` sha512 shape, `resolved` registry.npmjs.org prefix). (TQ-B-2 / CO-B-4.)
5. **Jest-test count proxy hardened.** `text.count("it(") + text.count("test(")` substring-counted comments, regex literals, identifier prefixes, and string content. Replaced with a tree-sitter-TypeScript parse counting top-level `call_expression` nodes whose `function` is `Identifier(text in {"it","test"})`; the grammar kernel is already in the repo (`codegenie.grammars.lock.language_for("typescript")`). (TQ-B-1 / CO-B-5.)
6. **`embedding_model` digest pinning elevated from Notes to AC-11.** The story warned this was "the **critical piece**" for the S7-07 replay-lands-RAG E2E test but had no AC enforcing it; a wrong-model digest would silently degenerate the E2E to a cold LLM call (edge case #19). AC now asserts `seeded_record.embedding_model == embedder.model_digest()` via the constant exported by `codegenie.rag.embeddings` (S4-01 dependency made explicit). (TQ-H-1 / CO-H-2 / DP-H-7.)
7. **`tsc --noEmit` baseline AC made executable.** Original AC asserted "passes `tsc --noEmit --pretty false` cleanly on Express-4" but the TDD plan invoked no tsc. AC-8 now mandates a fixture-shape test that runs the contract-pinned `tsc` (from `tests/contract/`) through `run_external_cli` and asserts `returncode == 0` + empty stderr. Without this, S7-06's downstream test would conflate "tsc fails on Express-5 patch" with "tsc was already broken". (CO-B-5 / TQ-H-2.)
8. **Cassette-stub content-discrimination AC.** Original AC accepted any two YAML files (`len(cassettes) == 2`); ADR-0011's structural claim (attempt-2 carries no RAG few-shot; attempt-1's proposal fails the smart-constructor) was untested. AC-12 now requires both stubs round-trip through a typed `CassetteStub` Pydantic model with explicit `outcome: Literal["fail","pass"]` and `proposal_kind` markers; cross-references ADR-0014 (cassette discipline shape). (TQ-B-5 / CN-H-7 / DP-H-3.)
9. **Semver-bump invariant added as AC-9.** Originally only loose YAML keys (`vulnerable: ">=4.0.0 <5.0.0"`, `fixed: ">=5.0.0"`) with no shape check — a wrong-fixture `fixed: ">=4.18.0"` (no major bump) would defeat the headline exit-criterion silently. Parsed at manifest import via `packaging.specifiers` (or npm-semver shim); asserts `fixed.lower_bound.major > vulnerable.upper_bound.major`. (TQ-H-9.)
10. **Provenance refuse AC scope tightened — fixture-only, not adapter behaviour.** Original AC `cve.yaml declaring a glibc CVE that the vuln_provenance adapter (S7-03) must classify as BaseImage` blended fixture shape with adapter classification. Story lands the fixture; S7-03 / `tests/integration/test_phase4_provenance_short_circuits.py` asserts the classification. Avoids a story-graph cycle. (CN-H-6 / CO-H-3.)
11. **Scope gaps surfaced — `tests/e2e/scenarios.yaml` rows + `tests/golden/events/` JSONL goldens.** High-level-impl §Step 7 (lines 217–218) explicitly requires both as part of Step 7; the original story owned neither and named no other story. Explicit Out-of-scope lines added naming **S7-06** (cassettes + e2e rows) and **S7-07** (replay-lands-RAG event goldens) as owners; if those stories don't take them, the validator's follow-up surfaces it. (CN-H-12 / CO-B-2 / CO-B-3.)
12. **Four-section README discipline lifted from S8-01 AC-3.** Each Phase-4 fixture's `README.md` now must have the four ordered `##` sections (`What this fixture is` / `Edge case(s) covered` / `Expected outcome` / `Maintenance`); load test extracts heading list and asserts equality. (CO-H-9 / DP-H-6.)
13. **Cardinality off-by-two surfaced in Notes.** Arch §1014 / §1148 / Out-of-scope all say "four `vuln-major-bump/*` fixtures" but the portfolio lists only two (`express-cve-2026-1234/`, `lodash-cve-2026-9876/`); `express-rerun/` is `vuln-rag-hit/`, `glibc-on-node/` is `vuln-provenance/`, `cassette-…` is `vuln-retry/`. Surfaced as a known arch-text-vs-portfolio mismatch the implementer must reconcile (either amend arch text to "two", or add two more `vuln-major-bump/*` fixtures — out of scope here; do not silently let S5-04 attempt to seed from a missing fourth). (CN-H-8 / CO-H-13.)
14. **Path-scheme reconciliation made explicit.** Arch §"Fixture portfolio" uses category-prefixed paths (`fixtures/vuln-major-bump/express-cve-2026-1234/`); Phase-3 S8-01 HARDENED to flat `tests/fixtures/repos/<name>/`. Story now picks flat (Rule 11 — match conventions of the more recent hardened precedent) and flags the arch path as cleanup; the `vuln-major-bump`/`vuln-provenance`/etc. dimension is recorded as a `category` field on the `FixtureSpec` so arch §1014's "for each `vuln-major-bump/*` example" glob can be expressed as `[f for f in PORTFOLIO if f.category == "vuln-major-bump"]`. (CN-B-1 / CO-H-8.)
15. **Express fixture cardinality narrowed.** Arch says "~80 / ~120"; original AC said "≥60 / ≥100" — a 25%/17% under-floor. Tightened to `~80 ± 10` / `~120 ± 15` (so 70 / 105 floors) with a `target` field documenting intent. (CN-H-9 / CO-N-1.)
16. **Sum-type opportunity for `FixtureRole` recorded as a design note (not mandated).** Three of five fixtures have semantically-different shapes that the current single-FixtureSpec model flattens into Optional fields; a tagged union (`AppLayerCve | ProvenanceRefuse | RagSeed | RetryCassette`) would make illegal states unrepresentable. **Not elevated to an AC** because (a) Phase-3 S8-01's `FixtureSpec` is the established convention and a sum-type split would either fork that or require a coordinated S8-01 amendment; (b) Rule 2 — five fixtures with four roles is at the threshold, not over it. Recorded in `Notes for the implementer` as the moment the third Phase-5/6/7 fixture-with-a-new-role lands ("the elevation moment"). (DP-B-4 / DP-H-1.)
17. **Synthetic CVE ids called out.** `CVE-2026-1234` / `CVE-2026-9876` parse cleanly through `parse_cve_id` (regex `^CVE-\d{4}-\d{4,7}$`) but do not exist in MITRE. Added a one-line Note so a future reader doesn't waste time looking them up. (CN-N-14.)

Full audit log: [`_validation/S7-05-phase4-fixture-portfolio.md`](_validation/S7-05-phase4-fixture-portfolio.md).

## Context

Phase-4's exit-criterion tests (S7-06, S7-07), the calibration smoke test (S5-04), the provenance short-circuit test (referenced in S7-06), and the retry-bypass test (S6-02) all consume small, hermetic fixture repos. This story lands the **five** fixtures listed in arch §"Fixtures" — they are the integration-test ground truth.

Each fixture is a checked-in npm repo (with `package.json`, `package-lock.json`, and just enough source to exercise the relevant code path) **plus a `FixtureSpec` row** in the Phase-3-established `tests/fixtures/repos/_portfolio.py` manifest carrying the CVE metadata, the `is_adversarial` flag, the `category` (one of `vuln-major-bump` / `vuln-provenance` / `vuln-rag-hit` / `vuln-retry`), and any role-specific data (`embedding_model_digest` for the RAG-seed fixture; `cassette_paths` for the retry-cassette fixture). The express major-bump fixture is the headline (~80 `.ts` files, ~120 unit tests — the breaking-change CVE exit criterion fixture); the rest are smaller.

The arch is clear about the cardinality: "Land all five fixtures." Missing any one breaks a downstream test; missing the major-bump fixture breaks the roadmap exit criterion. This story does not include cassettes (those are recorded in S7-06 against the express fixture) or the `RagHit` seed records (those are pre-populated under the `vuln-rag-hit/express-rerun/` fixture's `.codegenie/rag/records/` directory).

**Reconciliation with on-disk reality (validator).** The original story instructed the implementer to "mirror" the Phase-3 `tests/fixtures/repos/express-cve-2024-21501/` directory as a structural template. The on-disk reality is that this directory contains **exactly two files** (`package.json`, `package-lock.json`) — no `cve.yaml`, no `src/`, no `tests/`, no `README.md`. The "template" is empty of the very thing the original story instructed mirroring (`cve.yaml`). Phase-3 S8-01 (HARDENED 2026-05-20) deliberately chose a **single-source typed `_portfolio.py` manifest** with `CveId` newtypes as the source of truth for CVE metadata, **not** per-fixture YAML files. This Phase-4 story therefore **extends** that manifest with five `FixtureSpec` rows; per-fixture `cve.yaml` is dropped from the design. Note also that Phase-3 S8-01 is HARDENED but **not yet executed on disk** — `tests/fixtures/repos/_portfolio.py` does not exist as of validation (verified). The hard dependency on `Phase-3 S8-01 GREEN` is now declared in `Depends on:`.

**Path scheme reconciliation.** Arch §"Fixture portfolio" (lines 974–982) uses category-prefixed paths (`fixtures/vuln-major-bump/express-cve-2026-1234/`, `fixtures/vuln-provenance/glibc-on-node/`, etc.); arch §"Cross-cutting test-architecture additions" (line 1014) and §"calibration smoke test" (line 1148) glob on `fixtures/vuln-major-bump/*`. Phase-3 S8-01 HARDENED to **flat** `tests/fixtures/repos/<name>/` instead. This story picks **flat** (Rule 11 — match the more recent hardened convention) and preserves the category dimension as a `FixtureSpec.category` field so arch §1014's glob can be expressed as `[f for f in PORTFOLIO if f.category == "vuln-major-bump"]`. The arch's literal-path glob is flagged as cleanup; do not silently make both layouts coexist.

The risk to manage: the express fixture is the slowest to construct (real `.ts` files, a real `tsconfig.json`, a runnable test suite). The story is `M`, not `L`, because the fixture is a one-time construction; once it lands, every downstream test consumes it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Fixtures` — the five fixture paths and one-line descriptions for each:
    - `fixtures/vuln-major-bump/express-cve-2026-1234/` — peer-dep transitive case + major-version-bump CVE (~80 `.ts` files; ~120 unit tests). **The headline exit-criterion fixture.**
    - `fixtures/vuln-major-bump/lodash-cve-2026-9876/` — major-bump callsite rewrite; smaller (~20 files) for faster unit coverage.
    - `fixtures/vuln-provenance/glibc-on-node/` — CVE not in app layer; `ProvenanceGate` refuse case.
    - `fixtures/vuln-rag-hit/express-rerun/` — pre-populated `.codegenie/rag/records/` for re-run "RAG-shapes-LLM" test.
    - `fixtures/vuln-retry/cassette-attempt-1-fails-attempt-2-passes/` — Phase-5 retry simulator fixture.
  - `../phase-arch-design.md §Goals — G1` — exit-criterion E2E fixture description.
  - `../phase-arch-design.md §Edge case #1` — the glibc-on-Node fixture exercises the provenance refuse path.
  - `../phase-arch-design.md §Edge case #11` — the `vuln-retry/...` fixture exercises the retry RAG-bypass.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — the four `fixtures/vuln-major-bump/*` fixtures feed S5-04's calibration smoke (`each fixture's re-run scores RagHit; crossing-CVE queries score RagMiss`).
  - `../ADRs/0011-rag-bypass-on-retry.md` — the `vuln-retry/...` fixture is the simulator anchor for retry-bypass behavior.
  - `../ADRs/0012-provenance-gate-explicit-tier-zero.md` — the `glibc-on-node` fixture is the provenance refuse anchor.
- **Source design:**
  - `../final-design.md §Fixtures`.
- **High-level impl:**
  - `../High-level-impl.md §Step 7` — "Land all five fixtures."
- **Existing code (precedents to extend, not duplicate):**
  - `tests/fixtures/repos/_portfolio.py` (**shipped by Phase-3 S8-01** — hard dependency) — the single-source typed `Final[tuple[FixtureSpec, ...]]` manifest. `FixtureSpec(name: str, path: Path, is_adversarial: bool, cve_ids: tuple[CveId, ...], edge_cases: tuple[str, ...], expected_outcome: str)`. **This story extends the tuple with five new rows.** The five Phase-3 fence files (`test_fixtures_load.py`, `test_fixtures_pinning.py`, `test_fixtures_size_cap.py`) all import this tuple — the five new rows inherit those fences with zero edits to fence-test bodies (Open/Closed at the file boundary; see AC-3).
  - `tests/fixtures/_shape_test_kernel.py` — the **established fixture-shape-test kernel** (8 consumers today). Exports `_FileSpec`, the closed `_ParserKind` Literal, `_FORBIDDEN_SUBPATHS` (`node_modules`, `.codegenie`, `dist`, `coverage`, `build`), and flat helpers `assert_file_exists` / `assert_file_parses` / `assert_file_line_endings` / `assert_no_forbidden_subpath` / `assert_tree_is_closed_set`. **The Phase-4 load test delegates to these helpers** — it does not re-invent file-presence or parseability assertions.
  - `tests/fixtures/README.md` — the inventory + conventions doc (LF endings, no build artifacts, the one-tuple-entry Open/Closed rule). New fixtures must satisfy it.
  - `tests/fixtures/repos/express-cve-2024-21501/` (Phase 3) — the on-disk Phase-3 fixture; **minimal stub** (package.json + package-lock.json only; no cve.yaml, no src/, no tests/). The "template" the original story claimed to mirror is empty of the per-fixture metadata file premise — see Context §"Reconciliation". **This story does not modify this fixture** (Rule 3 — surgical changes).
  - `tests/fixtures/repos/malicious-npmrc/` (Phase 3) — the second pre-existing Phase-3 fixture under `repos/`. Not modified by this story.
  - `docs/phases/03-vuln-deterministic-recipe/stories/S8-01-fixture-portfolio.md` — the precedent story that built the Phase-3 fixture portfolio + manifest; mirror the construction discipline. **Read its HARDENED `_validation/` report** for the rationale behind every fence-test choice — this Phase-4 story inherits those choices wholesale.
  - `src/codegenie/types/identifiers.py:86` — `CveId = NewType("CveId", str)`.
  - `src/codegenie/types/parsers.py` — `parse_cve_id(s: str) -> Result[CveId, ParseError]` (regex `^CVE-\d{4}-\d{4,7}$`). Used by the manifest at import time; malformed CVE ids fail-loud at module load.
  - `src/codegenie/parsers/safe_json.py`, `src/codegenie/parsers/safe_yaml.py` — depth-capped + byte-capped parsers (arch §C12 caps `package.json` at 1 MiB / depth 16, `package-lock.json` at 32 MiB / depth 24). The load test uses these, not raw `json.loads` / `yaml.safe_load`.
  - `src/codegenie/grammars/lock.py` — `language_for("typescript") -> tree_sitter.Language`. The Jest test counter parses each `.test.ts` with this grammar and counts top-level `call_expression` nodes whose `function` is an `Identifier` with text `it` or `test` — replaces the brittle `text.count("it(")` substring proxy.
  - `src/codegenie/exec/run_external_cli.py` (or sibling at the same path) — the Phase-2 wrapper around `ALLOWED_BINARIES`. AC-8's tsc baseline test calls `tsc --noEmit --pretty false` through this wrapper, not raw `subprocess.run`.
  - `tests/contract/` — the version-pinned subprocess contract directory; arch §"Cross-cutting test-architecture additions" requires `tsc` lands here in Step 7 (owned by S7-06 / sibling). AC-8 reuses whatever Phase-3 / Phase-4 pinned `tsc` binary path is exposed.

## Goal

Land the five Phase-4 fixture repos at `tests/fixtures/repos/<name>/` (flat layout, matching Phase-3 S8-01 HARDENED — see Context §"Path scheme reconciliation") **plus** five new `FixtureSpec` rows in `tests/fixtures/repos/_portfolio.py` (the Phase-3-shipped typed manifest), such that: the three Phase-3 fence files (`test_fixtures_load.py`, `test_fixtures_pinning.py`, `test_fixtures_size_cap.py`) inherit the new fixtures via the manifest with **zero edits to their bodies** (Open/Closed at the file boundary, AC-3); the `express-cve-2026-1234/` fixture has ~80 `.ts` files (≥70) and a runnable Jest suite of ~120 tests (≥105) and passes `tsc --noEmit --pretty false` cleanly on Express-4 (AC-8); the `express-rerun/` fixture has a pre-populated `.codegenie/rag/records/<id>.yaml` whose `embedding_model` digest matches `codegenie.rag.embeddings.MODEL_DIGEST` (AC-11); the `cassette-attempt-1-fails-attempt-2-passes/` fixture has two cassette stubs round-tripping through a typed `CassetteStub` Pydantic model and structurally distinguishable by `outcome: Literal["fail","pass"]` (AC-12); the `glibc-on-node/` fixture has a `Dockerfile FROM node:20-bullseye` and a manifest entry recording a glibc CVE id (the **classification** assertion is S7-03's job — out of scope here, AC-13). The story does **not** ship per-fixture `cve.yaml` files — CVE metadata lives only in the manifest (CveId newtype via `parse_cve_id`).

## Acceptance criteria

- [ ] **AC-1 — the portfolio gains exactly five Phase-4 fixtures (and only five), each at `tests/fixtures/repos/<name>/`.** The five new directories are: `express-cve-2026-1234/`, `lodash-cve-2026-9876/`, `glibc-on-node/`, `express-rerun/`, `cassette-attempt-1-fails-attempt-2-passes/`. No `cve.yaml` (or any per-fixture CVE-metadata file) is shipped — CVE ids live only in the manifest (AC-2). Per-fixture file contents:
  - **`express-cve-2026-1234/`** — `package.json` declaring `"dependencies": { "express": "^4.18.x" }` + devDeps `jest` + `typescript`; pinned `package-lock.json` (lockfileVersion 3, AC-5); `tsconfig.json` (strict-mode — the `typecheck.typescript` SignalKind needs it); `src/**/*.ts` with **≥70 and target ~80** `.ts` files containing realistic Express-4 idioms that must change for Express 5 (`req.param()` deprecated, `app.del()` removed, async middleware error handling); `tests/**/*.test.ts` with **≥105 and target ~120** Jest tests verified by tree-sitter parse (AC-7), at least 10 of which exercise the call sites an Express 4→5 bump breaks; `README.md` per AC-6; `.gitignore` for `node_modules/` and `.codegenie/`. The fixture passes `tsc --noEmit --pretty false` cleanly (AC-8).
  - **`lodash-cve-2026-9876/`** — smaller (~20 `.ts` file) Node project pinned to `lodash@^4.17.x`; ~30 Jest tests; `README.md` per AC-6.
  - **`glibc-on-node/`** — `Dockerfile FROM node:20-bullseye` (or whatever distroless base ships glibc); `package.json` declaring **no app-layer vulnerable package** (load test asserts via the manifest's `category: "vuln-provenance"` flag — no `express`/`lodash`/etc. CVE-bearing deps); `README.md` per AC-6. The CVE id is recorded only in the manifest entry; **classification of this CVE as `Provenance.BaseImage` is S7-03's responsibility — out of scope here** (see Out of scope).
  - **`express-rerun/`** — small Express-4 project (~1 source file is fine; this is the RAG-seed substrate, not the call-site corpus); `package.json`; pinned `package-lock.json`; `.codegenie/rag/records/<id>.yaml` pre-populated with one solved-example record for the express major-bump CVE — the record round-trips through `SolvedExample.from_yaml` (S4-04) and `RecordProvenance.verify` (S4-05) without error and its `embedding_model` field equals the constant exported by `codegenie.rag.embeddings.MODEL_DIGEST` (AC-11); `README.md` per AC-6.
  - **`cassette-attempt-1-fails-attempt-2-passes/`** — minimal Node project; `.codegenie/rag/cassettes/` directory containing exactly two cassette stub YAML files (`attempt-1.yaml`, `attempt-2.yaml`); both round-trip through a typed `CassetteStub` Pydantic model and are structurally distinguishable per AC-12; `README.md` per AC-6 documenting the structural markers.
- [ ] **AC-2 — every Phase-4 fixture is a `FixtureSpec` row in `tests/fixtures/repos/_portfolio.py`** (the Phase-3 typed manifest, extended additively). Each row carries: `name: str`, `path: Path`, `is_adversarial: bool` (all five are `False` — these are application fixtures, not malformed-input adversarial fixtures), `category: Literal["vuln-major-bump","vuln-provenance","vuln-rag-hit","vuln-retry"]`, `cve_ids: tuple[CveId, ...]` constructed via `parse_cve_id` (a malformed id fails-loud at manifest import), `edge_cases: tuple[str, ...]` (e.g., `("E1",)` for `glibc-on-node`, `("E11",)` for `cassette-…`, `("E19",)` for `express-rerun`), `expected_outcome: str`, and **role-specific fields** (`embedding_model_digest: BlobDigest | None` for `express-rerun`; `cassette_paths: tuple[Path, Path] | None` for the retry fixture; `vulnerable_range: str | None` + `fixed_range: str | None` for the two app-layer-CVE fixtures — fed to AC-9's semver-bump invariant). All fields are `Final`-tagged at module level; `mypy --strict` passes.
- [ ] **AC-3 — adding a sixth Phase-4 fixture is one `FixtureSpec` row + one directory; zero edits to fence-test bodies.** Mirrors Phase-3 S8-01 AC-8 verbatim. A test (or comment-anchored assertion) in `test_fixtures_load.py` demonstrates this Open/Closed property is real for the five new rows. CLAUDE.md "Extension by addition — no silent edits".
- [ ] **AC-4 — the smoke loader `tests/fixtures/repos/test_fixtures_load.py` (Phase-3-shipped) covers every Phase-4 fixture via manifest parametrization, delegating structural checks to `tests/fixtures/_shape_test_kernel.py` helpers.** No new ad-hoc file-presence / parseability assertions. `package.json` is parsed via `safe_json.load(..., max_bytes=1*1024*1024, max_depth=16)` (matching production §C12 caps); `cassette` and `rag-record` YAMLs via `safe_yaml.load`. The loader uses `assert_file_exists`, `assert_file_parses`, `assert_file_line_endings`, `assert_no_forbidden_subpath` (banning `node_modules` / `.codegenie` only where appropriate — `express-rerun/` and `cassette-…/` deliberately ship a `.codegenie/` subtree as their fixture content; the load test threads the manifest's `allowed_codegenie_subtrees: tuple[Path, ...]` exception), and `assert_tree_is_closed_set` per fixture. (Validator hardening: original TDD plan re-invented these.)
- [ ] **AC-5 — every non-adversarial Phase-4 fixture's `package-lock.json` is byte-exact and machine-enforced by the Phase-3 pinning fence.** `tests/fixtures/repos/test_fixtures_pinning.py` (Phase-3-shipped) inherits the five new rows via the manifest with no body edits and asserts, for every entry under `packages`: **(a)** `version` matches `^\d+\.\d+\.\d+([-+].+)?$` — no `^`/`~`/`*`/`>`/`<`/`||`/`x`; **(b)** `integrity` matches `^sha512-[A-Za-z0-9+/]+={0,2}$`; **(c)** `resolved` starts with `https://registry.npmjs.org/`. (Validator hardening: original "deterministic" test was a same-file-read-twice tautology and is removed.)
- [ ] **AC-6 — every new fixture `README.md` has exactly four `##`-level sections in this exact order: `## What this fixture is`, `## Edge case(s) covered`, `## Expected outcome`, `## Maintenance`.** The smoke loader extracts the ordered list of `^## ` headings via `re.findall` and asserts equality with the four expected titles **in order** — a fifth rogue section, a missing section, a reordering, or a typo fails. (Mirrors Phase-3 S8-01 AC-3.)
- [ ] **AC-7 — the express fixture's Jest test count is verified by a tree-sitter-TypeScript parse, not a string-substring proxy.** A new test (`tests/fixtures/repos/test_express_cve_2026_1234_test_count.py` or co-located in `test_fixtures_load.py` parametrized over `category == "vuln-major-bump" and name == "express-cve-2026-1234"`) loads each `tests/**/*.test.ts` file with `codegenie.grammars.lock.language_for("typescript")`, queries for `(call_expression function: (identifier) @id (#match? @id "^(it|test)$"))` at the top level of `describe` blocks (or at file scope), and asserts the count is ≥ 105 (target ~120). A comment like `// TODO: write tests with it( and test(` no longer satisfies the count.
- [ ] **AC-8 — the express fixture passes `tsc --noEmit --pretty false` cleanly on Express-4, executable as a fixture-shape test.** A test in `test_fixtures_load.py` (parametrized over `category == "vuln-major-bump" and name == "express-cve-2026-1234"`) calls `tsc --noEmit --pretty false` via `run_external_cli` (Phase-2 wrapper) against the fixture's root, asserts `returncode == 0`, and asserts `stderr` is empty. The pinned `tsc` binary is the one `tests/contract/` exposes (shipped by S7-06's `tsc-contract` row or by Step 6's S6-04 `tsc-allowed-binary` story — `Depends on:` row `S6-04` may need to be added at executor time). Without this AC's executable test, S7-06's downstream "tsc fails on faulty Express-5 patch" assertion would conflate two failure modes silently. (Validator hardening: original AC was prose-only with no test.)
- [ ] **AC-9 — semver-bump invariant for app-layer-CVE fixtures.** For every `FixtureSpec` row whose `vulnerable_range` and `fixed_range` are non-`None` (today: `express-cve-2026-1234`, `lodash-cve-2026-9876`), the manifest's import-time validator parses both with `packaging.specifiers` (or the npm-semver shim) and asserts `min(fixed_range).major > max(vulnerable_range).major`. A wrong-fixture `fixed: ">=4.18.0"` (no major bump) fails at module load, not at calibration time. Surfaces silently-defeating-the-headline-exit-criterion mistakes immediately. (Validator added — TQ-H-9.)
- [ ] **AC-10 — every CVE id in the manifest is a `CveId` newtype constructed via `parse_cve_id`** (CLAUDE.md "Newtype identifiers ... never raw `str` for domain IDs"). A malformed id (`"cve-2026-1234"`, `"CVE-26-1234"`, `"NOT-A-CVE"`) fails-loud at manifest import via the `Result[CveId, ParseError]` `Err` arm. No raw-`str` CVE comparison anywhere in the load test.
- [ ] **AC-11 — `express-rerun/.codegenie/rag/records/*.yaml` round-trips through `SolvedExample.from_yaml` AND its `embedding_model` field equals `codegenie.rag.embeddings.MODEL_DIGEST`.** Test: `tests/fixtures/repos/test_fixtures_load.py::test_express_rerun_seeded_record_has_pinned_embedding_model_digest` — parses every record, asserts each `embedding_model` matches the digest constant exported by S4-01's bootstrap, asserts the record's `cve_id` matches the express major-bump CVE id from the manifest. Without this AC, a wrong-digest record would silently exclude itself via S5-03's model-mismatch guard at retrieval time and the S7-07 E2E would degenerate to a cold LLM call without surfacing the cause. (Validator hardening — elevated from Notes-only to executable AC; edge case #19.)
- [ ] **AC-12 — cassette stubs are typed and structurally distinguishable.** A `CassetteStub` Pydantic model (defined in `tests/fixtures/repos/_phase4_cassette_stub.py` or co-located near the manifest) carries: `attempt: Literal[1, 2]`, `outcome: Literal["fail", "pass"]`, `proposal_kind: Literal["faulty_callsite_rewrite", "correct_callsite_rewrite"]`, `interactions: list[CassetteInteraction]` (one entry with stub `request` + `response.body` shaped like a `PlanProposalCallsiteRewrite` JSON). The load test parses both stubs through this model, asserts `attempt_1.outcome == "fail"`, `attempt_2.outcome == "pass"`, `attempt_1.proposal_kind == "faulty_callsite_rewrite"`, `attempt_2.proposal_kind == "correct_callsite_rewrite"`, and `attempt_1 != attempt_2`. Two empty placeholder YAML files no longer satisfy the AC. (Validator hardening — TQ-B-5; aligns with ADR-0014 cassette discipline. ADR-0011's full retry-bypass behavioural assertion remains S6-02's responsibility — see Out of scope.)
- [ ] **AC-13 — `glibc-on-node/`'s `package.json` declares zero app-layer vulnerable dependencies.** Asserted at load time by checking the fixture's `package.json` `dependencies` + `devDependencies` against a per-manifest `forbidden_app_layer_packages: frozenset[str]` (which includes at minimum `express`, `lodash`, and any package named in another fixture's `vulnerable_range`). Provides the **fixture-side** invariant that the provenance adapter (S7-03) tests against; the classification assertion (`Provenance.BaseImage`) remains S7-03's responsibility. (Validator scope tightening — CN-H-6.)
- [ ] **AC-14 — no duplicate-named fixture directories under `tests/fixtures/`.** Mirrors S8-01 AC-9. A check in `test_fixtures_load.py` asserts no two `_portfolio.py` rows resolve to the same `path` and no two `path` `.name` values collide. Protects against accidentally authoring a second `express-rerun/` under, e.g., `tests/fixtures/phase04/`.
- [ ] **AC-15 — zero edits to pre-existing Phase-3 fixtures.** `tests/fixtures/repos/express-cve-2024-21501/` and `tests/fixtures/repos/malicious-npmrc/` (and any fixture from Phase-3's `_portfolio.py` whose row is not modified by Phase-4) are byte-identical pre-and-post Phase-4. Verified by the executor's checklist (manual diff inspection of the merge commit) or, optionally, by a content-hash baseline recorded in the manifest. (Rule 3 — surgical changes.)
- [ ] **AC-16 — per-fixture size cap.** S8-01 AC-6's 256 KiB cap (`test_fixtures_size_cap.py`) is inherited by the five new manifest rows. If the `express-cve-2026-1234/` fixture exceeds 256 KiB (likely, given ≥70 `.ts` files), its `FixtureSpec` row sets an explicit `size_cap_bytes_override: int` (e.g., `1024 * 1024`) with a one-line rationale; otherwise the default cap applies.
- [ ] **AC-17 — `make check` clean.** Includes `mypy --strict` on the extended `_portfolio.py` rows, the new `_phase4_cassette_stub.py`, and any AC-8 / AC-11 test code — no `Any`, no untyped function signatures, no untyped `dict` shuffling. (Excluding `npm install` / `npm test` against the fixtures, which run only in E2E inside `SubprocessJail`.)
- [ ] **AC-18 — TDD red test exists, was committed failing, and is green** after the fixtures and manifest rows land.

## Implementation outline

1. **Reconcile with on-disk reality first.** Confirm `tests/fixtures/repos/_portfolio.py` exists (the hard dependency on Phase-3 S8-01 GREEN). Read it end-to-end. Confirm the on-disk shape of `tests/fixtures/repos/express-cve-2024-21501/` (it is **minimal** — package.json + package-lock.json only; no `cve.yaml`, no `src/`, no `tests/` — see Context §"Reconciliation"). Read `tests/fixtures/_shape_test_kernel.py` and `tests/fixtures/README.md` so the new fixtures match LF-endings, final-newline, no-build-artifact, deterministic-content conventions. Confirm `src/codegenie/rag/models.py` exists (S4-04 dependency) and that `codegenie.rag.embeddings.MODEL_DIGEST` is exported (S4-01 dependency); if either is missing, surface the blocker before any fixture work begins. (Validator-mandated; replaces the original "mirror the empty template" instruction.)
2. **Extend the manifest first.** Add the five new `FixtureSpec` rows to `tests/fixtures/repos/_portfolio.py` (one tuple-entry insertion per row, no body edits to the existing tuple's surrounding code). Each row's `cve_ids` is built via `parse_cve_id` so malformed ids fail at module import (AC-10). The `vulnerable_range` / `fixed_range` fields on the app-layer-CVE rows feed AC-9's semver-bump invariant — wire that validator at module load time. The `_portfolio.py` extension is the design centre; everything else follows from it.
3. **Build the five fixtures (slowest first).** Construct `express-cve-2026-1234/` first — ≥70 `.ts` files (target ~80) covering routing, middleware, error handling; ≥105 Jest tests (target ~120) exercising the call sites an Express 4→5 bump breaks (`req.param`, async error handling, `app.del`); pinned `package-lock.json` (lockfileVersion 3 — every entry has exact `version`, sha512 `integrity`, registry.npmjs.org `resolved` per AC-5); `tsconfig.json` strict-mode; four-section `README.md` (AC-6); `.gitignore` for `node_modules/` + `.codegenie/`. Verify the file count via the tree-sitter parse before declaring done (AC-7) and verify `tsc --noEmit --pretty false` is clean (AC-8). Then `lodash-cve-2026-9876/` (smaller variant of the same pattern), `glibc-on-node/`, `express-rerun/`, `cassette-attempt-1-fails-attempt-2-passes/`.
4. **Express-rerun seeded record.** Hand-craft `.codegenie/rag/records/<id>.yaml` using S4-04's canonical `SolvedExample` YAML shape; set `embedding_model` to the literal value of `codegenie.rag.embeddings.MODEL_DIGEST` (do not hard-code a string — import the constant in a one-line seed script if necessary, or assert at AC-11 time and document the value in the fixture's README so reviewers can verify). Ensure `RecordProvenance.verify` accepts the record.
5. **Cassette stubs.** Author `tests/fixtures/repos/_phase4_cassette_stub.py` defining the typed `CassetteStub` Pydantic model (AC-12 shape). Hand-write two YAML files (`attempt-1.yaml` with `outcome: fail` + `proposal_kind: faulty_callsite_rewrite`; `attempt-2.yaml` with `outcome: pass` + `proposal_kind: correct_callsite_rewrite`). Document the structural markers in the fixture's README's `## Maintenance` section.
6. **Wire the new rows into the three Phase-3 fence tests with zero body edits.** `test_fixtures_load.py`, `test_fixtures_pinning.py`, `test_fixtures_size_cap.py` already iterate over the manifest tuple. The Open/Closed property (AC-3) means the new rows are picked up automatically. If any of these tests need NEW per-AC checks (AC-7 tree-sitter parse, AC-8 tsc baseline, AC-11 embedding-digest pinning, AC-12 cassette typing, AC-13 glibc no-app-layer-vuln, AC-15 zero-Phase-3-edits) that don't fit existing parametrizations, add new test files alongside (`test_express_fixture_intent.py`, `test_phase4_seeded_records.py`, etc.) — but those new files also parametrize over the manifest, never re-declare the fixture list.
7. **Refactor pass.** Confirm `git status` shows no `node_modules/` accidentally committed. Confirm `make check` (lint + mypy --strict + tests) is clean. Confirm `git diff --name-only` does not touch `tests/fixtures/repos/express-cve-2024-21501/` or `tests/fixtures/repos/malicious-npmrc/` (AC-15).

## TDD plan — red / green / refactor

### Red — write the failing tests first

Tests live alongside the manifest in `tests/fixtures/repos/` (co-located with Phase-3's existing `test_fixtures_load.py` / `test_fixtures_pinning.py` / `test_fixtures_size_cap.py`). All Phase-4-specific tests parametrize over `_portfolio.py`'s `PORTFOLIO` tuple, filtered by `category` / `is_adversarial` / role-specific fields — **no inline `FIXTURES = {...}` dict; no raw `json.loads` / `yaml.safe_load`; no string-substring count proxies; no same-file-read-twice "determinism" tautology.** The original story's `test_phase4_fixtures_load.py` shape is deliberately discarded — these are the replacements.

```python
# tests/fixtures/repos/test_phase4_fixtures_load.py  (NEW — extends the Phase-3 file's coverage; does not replace it)
from __future__ import annotations
from pathlib import Path
from typing import Final
import re

import pytest

from codegenie.parsers import safe_json, safe_yaml
from codegenie.rag.embeddings import MODEL_DIGEST as EMBEDDER_MODEL_DIGEST  # S4-01
from codegenie.rag.models import RecordProvenance, SolvedExample              # S4-04 / S4-05
from codegenie.types.identifiers import CveId

from tests.fixtures._shape_test_kernel import (
    assert_file_exists,
    assert_file_line_endings,
    assert_no_forbidden_subpath,
)
from tests.fixtures.repos._portfolio import PORTFOLIO, FixtureSpec
from tests.fixtures.repos._phase4_cassette_stub import CassetteStub

PHASE4_FIXTURES: Final[tuple[FixtureSpec, ...]] = tuple(
    f for f in PORTFOLIO if f.category in ("vuln-major-bump", "vuln-provenance", "vuln-rag-hit", "vuln-retry")
)
assert len(PHASE4_FIXTURES) == 5, "Phase-4 portfolio must have exactly five fixtures"

_README_SECTIONS: Final[tuple[str, ...]] = (
    "## What this fixture is",
    "## Edge case(s) covered",
    "## Expected outcome",
    "## Maintenance",
)


@pytest.mark.parametrize("spec", PHASE4_FIXTURES, ids=lambda s: s.name)
def test_phase4_fixture_dir_and_package_json(spec: FixtureSpec) -> None:
    """Every Phase-4 fixture has a parseable package.json within production caps."""
    assert_file_exists(spec.path / "package.json")
    data = safe_json.load(spec.path / "package.json", max_bytes=1 * 1024 * 1024, max_depth=16)
    assert isinstance(data, dict)


@pytest.mark.parametrize("spec", PHASE4_FIXTURES, ids=lambda s: s.name)
def test_phase4_fixture_readme_four_ordered_sections(spec: FixtureSpec) -> None:
    """AC-6 — README has exactly four ##-sections in the canonical order."""
    readme = (spec.path / "README.md").read_text(encoding="utf-8")
    found = tuple(line.rstrip() for line in re.findall(r"^## .*$", readme, flags=re.MULTILINE))
    assert found == _README_SECTIONS, f"{spec.name}: README sections {found!r} != {_README_SECTIONS!r}"


@pytest.mark.parametrize("spec", PHASE4_FIXTURES, ids=lambda s: s.name)
def test_phase4_fixture_no_forbidden_subpath(spec: FixtureSpec) -> None:
    """Kernel-delegated forbidden-subpath check, with .codegenie allowed only where the manifest says so."""
    allowed = getattr(spec, "allowed_codegenie_subtrees", ())
    assert_no_forbidden_subpath(spec.path, allowed_codegenie_subtrees=allowed)


@pytest.mark.parametrize("spec", PHASE4_FIXTURES, ids=lambda s: s.name)
def test_phase4_fixture_cve_ids_are_newtype(spec: FixtureSpec) -> None:
    """AC-10 — every CVE id is a CveId newtype; raw-str sneak attempts would have failed at manifest import."""
    for cve in spec.cve_ids:
        # If parse_cve_id rejected the id, the manifest import would have raised; assert the type here.
        assert isinstance(cve, str) and cve.startswith("CVE-")


def _major_bump_specs() -> tuple[FixtureSpec, ...]:
    return tuple(f for f in PHASE4_FIXTURES if f.category == "vuln-major-bump")


@pytest.mark.parametrize("spec", _major_bump_specs(), ids=lambda s: s.name)
def test_phase4_vuln_major_bump_semver_invariant(spec: FixtureSpec) -> None:
    """AC-9 — fixed.lower_bound.major > vulnerable.upper_bound.major (so the major-bump is real)."""
    from packaging.specifiers import SpecifierSet  # or the npm-semver shim if mypy --strict trips on stubs
    assert spec.vulnerable_range is not None and spec.fixed_range is not None
    vuln = SpecifierSet(spec.vulnerable_range)
    fixed = SpecifierSet(spec.fixed_range)
    # Concrete shape check: assert at least one explicit upper-bound on vuln; explicit lower-bound on fixed.
    vuln_upper_majors = [int(s.version.split(".")[0]) for s in vuln if s.operator in ("<", "<=")]
    fixed_lower_majors = [int(s.version.split(".")[0]) for s in fixed if s.operator in (">=", "==", ">")]
    assert vuln_upper_majors and fixed_lower_majors
    assert min(fixed_lower_majors) > max(vuln_upper_majors), (
        f"{spec.name}: fixed_range={spec.fixed_range} does not strictly exceed "
        f"vulnerable_range={spec.vulnerable_range} in major version"
    )


# ---- Express-fixture-specific intent tests ----

EXPRESS_SPEC: Final[FixtureSpec] = next(f for f in PHASE4_FIXTURES if f.name == "express-cve-2026-1234")


def test_express_fixture_has_target_ts_file_count() -> None:
    """AC-1 — ≥70 .ts source files (target ~80)."""
    files = tuple((EXPRESS_SPEC.path / "src").rglob("*.ts"))
    assert len(files) >= 70, f"need ≥70 .ts files, got {len(files)}"


def test_express_fixture_jest_tests_via_tree_sitter() -> None:
    """AC-7 — Jest test count verified by tree-sitter TypeScript parse, not text.count('it(')."""
    from codegenie.grammars.lock import language_for
    import tree_sitter

    lang = language_for("typescript")
    parser = tree_sitter.Parser()
    parser.set_language(lang)
    # query: top-level (call_expression function: (identifier) @id (#match? @id "^(it|test)$"))
    query = lang.query(
        '(call_expression function: (identifier) @id (#match? @id "^(it|test)$"))'
    )
    total = 0
    for test_file in (EXPRESS_SPEC.path / "tests").rglob("*.test.ts"):
        tree = parser.parse(test_file.read_bytes())
        total += sum(1 for _node, _cap in query.captures(tree.root_node))
    assert total >= 105, f"need ≥105 Jest tests (target ~120), got {total}"


def test_express_fixture_tsc_noemit_clean_baseline() -> None:
    """AC-8 — `tsc --noEmit --pretty false` returns 0 with empty stderr against Express-4."""
    from codegenie.exec import run_external_cli  # the Phase-2 wrapper around ALLOWED_BINARIES

    result = run_external_cli(
        ["tsc", "--noEmit", "--pretty", "false"],
        cwd=EXPRESS_SPEC.path,
        timeout_seconds=120,
    )
    assert result.returncode == 0, f"tsc returned {result.returncode}; stderr={result.stderr!r}"
    assert result.stderr == "", f"tsc emitted stderr (Express-4 baseline must be clean): {result.stderr!r}"


# ---- express-rerun seeded RAG record ----

EXPRESS_RERUN_SPEC: Final[FixtureSpec] = next(f for f in PHASE4_FIXTURES if f.name == "express-rerun")


def test_express_rerun_seeded_record_roundtrips_and_pins_embedding_model() -> None:
    """AC-11 — record parses via SolvedExample.from_yaml AND embedding_model == MODEL_DIGEST."""
    records_dir = EXPRESS_RERUN_SPEC.path / ".codegenie" / "rag" / "records"
    yaml_files = tuple(records_dir.glob("*.yaml"))
    assert yaml_files, f"no seeded record under {records_dir}"

    parsed = [SolvedExample.from_yaml(safe_yaml.load(p, max_bytes=256 * 1024)) for p in yaml_files]
    assert parsed, "no records parsed"

    # Every record's embedding_model must match the production digest exactly — a wrong
    # digest would silently exclude itself via S5-03's mismatch guard at retrieval time.
    for example in parsed:
        assert example.embedding_model == EMBEDDER_MODEL_DIGEST, (
            f"record {example.cve_id}: embedding_model={example.embedding_model!r} != "
            f"production MODEL_DIGEST={EMBEDDER_MODEL_DIGEST!r}"
        )
        # Provenance round-trip — S4-05 must accept it (chain-head verifies in the integration test).
        RecordProvenance.verify(example.provenance, allow_missing_spanning_log=True)

    # The seeded record's CVE id matches the express major-bump CVE recorded in the manifest.
    target_cve: CveId = next(f for f in PHASE4_FIXTURES if f.name == "express-cve-2026-1234").cve_ids[0]
    assert any(p.cve_id == target_cve for p in parsed)


# ---- cassette stubs ----

CASSETTE_SPEC: Final[FixtureSpec] = next(
    f for f in PHASE4_FIXTURES if f.name == "cassette-attempt-1-fails-attempt-2-passes"
)


def test_cassette_stubs_are_typed_and_distinguishable() -> None:
    """AC-12 — two stubs round-trip through CassetteStub and are structurally distinct."""
    stubs_dir = CASSETTE_SPEC.path / ".codegenie" / "rag" / "cassettes"
    files = sorted(stubs_dir.glob("*.yaml"))
    assert len(files) == 2, f"expected exactly 2 cassette stubs, got {len(files)}"

    stub_1 = CassetteStub.from_yaml(safe_yaml.load(files[0], max_bytes=256 * 1024))
    stub_2 = CassetteStub.from_yaml(safe_yaml.load(files[1], max_bytes=256 * 1024))

    assert {stub_1.attempt, stub_2.attempt} == {1, 2}
    by_attempt = {s.attempt: s for s in (stub_1, stub_2)}
    assert by_attempt[1].outcome == "fail"
    assert by_attempt[2].outcome == "pass"
    assert by_attempt[1].proposal_kind == "faulty_callsite_rewrite"
    assert by_attempt[2].proposal_kind == "correct_callsite_rewrite"
    assert by_attempt[1] != by_attempt[2]


# ---- glibc-on-node fixture-side invariant (NOT the classification — that's S7-03) ----

GLIBC_SPEC: Final[FixtureSpec] = next(f for f in PHASE4_FIXTURES if f.name == "glibc-on-node")
_FORBIDDEN_APP_LAYER_PACKAGES: Final[frozenset[str]] = frozenset({"express", "lodash"})


def test_glibc_fixture_declares_no_app_layer_vulnerable_package() -> None:
    """AC-13 — package.json has no dep in _FORBIDDEN_APP_LAYER_PACKAGES (provenance refuse anchor)."""
    pj = safe_json.load(GLIBC_SPEC.path / "package.json", max_bytes=1 * 1024 * 1024, max_depth=16)
    deps = {**pj.get("dependencies", {}), **pj.get("devDependencies", {})}
    leaked = _FORBIDDEN_APP_LAYER_PACKAGES & set(deps)
    assert not leaked, f"glibc-on-node leaked app-layer vuln deps: {leaked!r}"
    # Dockerfile presence — the substrate the provenance adapter inspects.
    assert (GLIBC_SPEC.path / "Dockerfile").is_file()


# ---- Open/Closed extension property (AC-3) ----


def test_phase4_fixture_addition_is_open_closed() -> None:
    """AC-3 — comment-anchored proof: this test imports PORTFOLIO directly and never re-declares names.

    A future sixth Phase-4 fixture is added by:
      (1) appending one FixtureSpec row to tests/fixtures/repos/_portfolio.py
      (2) creating the directory under tests/fixtures/repos/<new-name>/
    Zero edits to this file's body. The parametrized tests above pick up the new row automatically.
    """
    assert len(PHASE4_FIXTURES) >= 5  # enforced upstream; this is the documentary anchor


# ---- AC-14: no duplicate-named fixtures ----


def test_no_duplicate_fixture_names_or_paths() -> None:
    names = [f.name for f in PORTFOLIO]
    paths = [str(f.path.resolve()) for f in PORTFOLIO]
    assert len(set(names)) == len(names), f"duplicate fixture names: {names}"
    assert len(set(paths)) == len(paths), f"duplicate fixture paths: {paths}"
```

Run: `.venv/bin/pytest tests/fixtures/repos/test_phase4_fixtures_load.py -v --no-cov` — every test fails RED on a clean tree (no fixtures, no manifest rows, no `CassetteStub` model). Commit the failing tests **before** any fixture or manifest work begins.

**Mutation-resistance check** (mental — do not commit): for each fixture, ask "if I shipped this fixture *almost right but wrong in one obvious way*, would at least one test fail?":
- `express-cve-2026-1234` with 60 `.ts` files and 100 fake `it(` comments → AC-7's tree-sitter parse catches (`call_expression` count, not substring).
- `express-cve-2026-1234` with a type error in one `.ts` file → AC-8's tsc baseline catches.
- `express-rerun/` seeded record with `embedding_model: "all-MiniLM-L6-v2"` (wrong model) → AC-11 catches.
- Cassettes shipped as two empty placeholders → AC-12 catches (CassetteStub.from_yaml raises).
- `glibc-on-node/package.json` accidentally lists `express` as a dep → AC-13 catches.
- A `^4.18.0` smuggled into a lockfile → S8-01 AC-2 pinning fence (inherited) catches.
- Fixed-range `>=4.18.0` (no major bump) in the manifest → AC-9 catches at module import.

If any of the above mutations would slip through, the AC is still too weak — sharpen before going green.

### Green — make the tests pass

1. **Extend `_portfolio.py` with the five `FixtureSpec` rows.** The `parse_cve_id` validation and `AC-9` semver-bump invariant fire at module import — if the rows are malformed, import fails and every test errors at collection time (loud failure mode).
2. **Author `tests/fixtures/repos/_phase4_cassette_stub.py`** with the `CassetteStub` Pydantic model and its `from_yaml` constructor.
3. **Construct fixtures in slowest-to-fastest order** (express → lodash → express-rerun → glibc-on-node → cassette). Run the test suite after each fixture to walk RED → GREEN incrementally; surface every blocker explicitly per Global Rule 12 — do not paper over.
4. **For `express-cve-2026-1234/`**, run a one-time sanity script: `tsc --noEmit --pretty false` against the fixture, then `pytest tests/fixtures/repos/test_phase4_fixtures_load.py::test_express_fixture_tsc_noemit_clean_baseline`. Any tsc error message in stderr is a Rule 12 surface, not a fixture-quality "good enough" judgment.

### Refactor — clean up

- Confirm `git diff --name-only origin/master...HEAD tests/fixtures/repos/express-cve-2024-21501/ tests/fixtures/repos/malicious-npmrc/` is empty (AC-15).
- Confirm `git status` shows no `node_modules/` accidentally committed (the per-fixture `.gitignore` is the safety net).
- Update `tests/fixtures/README.md`'s inventory table with five new rows naming each Phase-4 fixture, its category, edge case, and downstream test (one tuple-entry-style insertion per row — the README is itself documentation of the Open/Closed pattern).
- Re-run `make check`; fixtures must not break Phase-3 tests (the Phase-3 fences `test_fixtures_load.py` / `test_fixtures_pinning.py` / `test_fixtures_size_cap.py` are now also exercising the five new manifest rows).

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/repos/_portfolio.py` | **Extend** with five new `FixtureSpec` rows (Phase-3-shipped manifest). |
| `tests/fixtures/repos/_phase4_cassette_stub.py` | New typed `CassetteStub` Pydantic model + `from_yaml` (AC-12). |
| `tests/fixtures/repos/express-cve-2026-1234/**` | Headline exit-criterion fixture (≥70 `.ts`, ≥105 Jest tests; target ~80/~120). |
| `tests/fixtures/repos/lodash-cve-2026-9876/**` | Smaller major-bump fixture for faster unit coverage. |
| `tests/fixtures/repos/glibc-on-node/**` | Provenance-refuse fixture (CVE not in app layer). |
| `tests/fixtures/repos/express-rerun/**` | RAG-hit fixture with pre-populated `.codegenie/rag/records/`. |
| `tests/fixtures/repos/cassette-attempt-1-fails-attempt-2-passes/**` | Retry simulator fixture (S6-02 consumer). |
| `tests/fixtures/repos/test_phase4_fixtures_load.py` | Phase-4-specific load/intent tests (AC-6, AC-7, AC-8, AC-11, AC-12, AC-13, AC-9, AC-3, AC-14). |
| `tests/fixtures/README.md` | Inventory table — five new rows describing each Phase-4 fixture + its downstream test. |

**Not touched (Rule 3 — AC-15):** `tests/fixtures/repos/express-cve-2024-21501/`, `tests/fixtures/repos/malicious-npmrc/`, all Phase-1/Phase-2 fixtures under `tests/fixtures/{empty_repo,js_only,polyglot,node_*,non_node_go,portfolio,phase03}/`. The three Phase-3 fence test bodies (`test_fixtures_load.py`, `test_fixtures_pinning.py`, `test_fixtures_size_cap.py`) are likewise not modified — they pick up the new manifest rows automatically (Open/Closed).

## Out of scope

- **Recording live Anthropic cassettes** for the E2E tests — owned by **S7-06** (cf. `make refresh-cassettes` per S3-06). This story ships only the cassette *stub* substrate (typed YAML files round-tripping through `CassetteStub`); S7-06 records the real interactions on top of the same fixture.
- **Running `npm install` / `npm test`** against the fixtures — happens only inside `SubprocessJail` in **S7-06's** E2E test.
- **The calibration smoke test S5-04** — consumes the `vuln-major-bump/*` portfolio but lives in Step 5's story. (Note: arch §1014 / §1148 says "four `vuln-major-bump/*` fixtures" but this portfolio ships only **two** — `express-cve-2026-1234`, `lodash-cve-2026-9876` — with `express-rerun` in `vuln-rag-hit`, `glibc-on-node` in `vuln-provenance`, and the cassette fixture in `vuln-retry`. The arch-vs-portfolio cardinality mismatch is **surfaced for reconciliation** at the time S5-04 lands; this story does not add two more `vuln-major-bump/*` fixtures unilaterally.)
- **Phase-4 rows in `tests/e2e/scenarios.yaml`** — required by High-level-impl §Step 7 (line 217). **Owned by S7-06** (the E2E story consuming these fixtures). If S7-06 does not take this work, escalate via a new validator-generated story.
- **`tests/golden/events/` JSONL goldens** (`attempt_anchor.{success,refusal}.jsonl`, `two_stream.express-cve.{spanning,internal}.jsonl`) — required by High-level-impl §Step 7 (line 218; ADR-0017). **Owned by S7-07** (the replay-lands-RAG E2E story that produces the golden event sequence). Same escalation path.
- **`tsc` row in `tests/contract/`** — High-level-impl §Step 7 (line 219). **Owned by S6-04** (`tsc-allowed-binary` story) and/or sibling S7-06 work that pins the binary version. AC-8 *consumes* whatever `tsc` `tests/contract/` exposes; it does not author the contract row.
- **`Provenance.BaseImage` classification of the `glibc-on-node/` fixture** — **owned by S7-03** (`vuln-provenance-adapter`). This story asserts only the fixture-side invariant (AC-13: no app-layer vuln deps + Dockerfile present); the classification assertion is S7-03's integration test.
- **ADR-0011 retry-bypass behavioural assertion** (attempt-2 carries no RAG few-shot in the prompt body) — **owned by S6-02** (`retry-bypass-rag`). This story ships only the cassette stub *shape* the retry simulator consumes.
- **Updating Phase-3 fixtures** — those are owned by the Phase-3 phase. AC-15 forbids edits.

## Notes for the implementer

- **The express fixture is the bottleneck.** Budget time accordingly. If you find yourself spending more than half the story's effort on contrived Express-4 idioms, consider seeding from a real OSS Express starter (with appropriate license attribution in the fixture's README's `## Maintenance` section).
- **The `express-rerun/` seeded record is the critical piece for S7-07.** AC-11 makes this executable. Concretely: run `python -c "from codegenie.rag.embeddings import MODEL_DIGEST; print(MODEL_DIGEST)"` first; pin that exact string in the seeded YAML's `embedding_model` field. A wrong digest (typo, stale model name, "fastembed:BAAI/bge-small-en-v1.5" with a leading space) would silently exclude the record via S5-03's mismatch guard at retrieval time — AC-11 catches it at fixture-load time so the failure surfaces at the right layer (Rule 12).
- **The `cassette-attempt-1-fails-attempt-2-passes/` fixture is not the cassette content** (real HTTP request/response YAMLs) — it's the *fixture-level* scaffolding that S6-02's retry-bypass test inspects via the typed `CassetteStub` model. Placeholder stubs are acceptable; document the structural markers (`outcome: fail` / `outcome: pass`, `proposal_kind`) in the fixture README's `## Maintenance` section.
- **Deterministic `package-lock.json`** is the difference between a green CI and a flaky one — generate with `npm install --package-lock-only --omit=optional` so transitive resolution is reproducible, never let `npm install` run during tests, commit the lockfile byte-for-byte. The Phase-3 pinning fence (AC-5) is the safety net.
- **Resist "improving" Phase-3 fixtures** while you're in `tests/fixtures/` — AC-15 + Global Rule 3 are the law. If you spot a real Phase-3 fixture defect, surface it as a separate spawn-task; do not bundle.
- **Synthetic CVE ids.** `CVE-2026-1234` and `CVE-2026-9876` parse cleanly through `parse_cve_id` but do not exist in MITRE — do not waste time looking them up. The fixture's `README.md` `## What this fixture is` section should call this out so a future reader doesn't, either.
- **Design opportunity (not mandated this story): `FixtureRole` sum type.** Three of the five fixtures (`glibc-on-node`, `express-rerun`, `cassette-…`) carry role-specific fields (`embedding_model_digest`, `cassette_paths`, no app-layer vuln) that a tagged union (`AppLayerCve | ProvenanceRefuse | RagSeed | RetryCassette`) would make unrepresentable-when-wrong instead of optional-when-N/A. Phase-3 S8-01 settled on a single `FixtureSpec` shape with optional fields; elevating to a sum type would either fork that convention or require a coordinated S8-01 amendment. **Don't do it this story** (Rule 2 — five fixtures with four roles is at the rule-of-three threshold, not over it). **Mark this comment as "the elevation moment"** for whichever Phase-5/6/7 story is the third to add a role-specific manifest field — at that point the sum type earns its keep, and the amendment to `_portfolio.py` is worth the coordination cost. (DP-B-4 from validation; deferred.)
- **Open/Closed-at-the-file-boundary is the design centre.** Every Phase-4-specific test parametrizes over `PORTFOLIO`; never re-declare fixture names. If you find yourself typing `"express-cve-2026-1234"` as a literal anywhere outside the manifest itself, you have introduced a Rule-of-three drift point — go back and import.
- **If Phase-3 S8-01 is not yet GREEN when you pick this up**, surface that as a hard blocker per Global Rule 12. Do not attempt to land Phase-4 fixtures without the manifest the `Depends on:` line requires; you will end up forking exactly the conventions this validation report was written to prevent forking. Confirm `tests/fixtures/repos/_portfolio.py` exists and `tests/fixtures/repos/test_fixtures_load.py` + `test_fixtures_pinning.py` + `test_fixtures_size_cap.py` are GREEN before writing the first line of fixture code.
