# Story S5-03 — vuln-remediation 5 RAG-corpus-derived cases

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-05)
**Effort:** M
**Depends on:** S5-02 HARDENED (rubric exists and is testable end-to-end; without it the cases are inert), S2-02 HARDENED (`load_cases` walks `bench/{tc}/cases/*`, BLAKE3-verifies each case against `cases/digests.yaml`, raises typed errors; the canonical case-dir digest algorithm at S2-02 §AC-3 is the *only* algorithm allowed for `case_digest`), S1-02 HARDENED (`BenchCase` Pydantic wire-type shapes — `cassette_canary_pin: str` (32 hex), `case_digest: str` (`blake3:<64 hex>`), `disposition: Literal["positive","negative","ambiguous"]`, `difficulty: Literal["easy","medium","hard"]`, `source: Literal["curated","outcome-ledger-derived","regression-converted"]`, `curation_class: Literal["rag-corpus-derived","held-out"]`, tz-aware UTC `added_at`/`last_validated_at`), S5-01 HARDENED (`bench/vuln-remediation/registration.py` ships `register_task_class("vuln-remediation", ...)` so `load_task_class("vuln-remediation", bench_root="bench")` resolves)
**ADRs honored:** ADR-0005 (`cassette_canary_pin` is 32 hex; pin is identity not content; `case_digest` excludes `case.toml` — Phase 4 cassettes pre-date the `Canary.mint(seed=...)` amendment, so the deterministic-derivation path is the always-path and is pinned in AC-3a), ADR-0006 (these 5 cases are `curation_class="rag-corpus-derived"`; they verify the recipe/RAG pipeline doesn't regress against the corpus it was tuned on; they are **not** sufficient evidence for silver-tier promotion on their own — that's the held-out 5 from S5-04), Phase 0 ADR-0001 (BLAKE3 hashing chokepoint — for `src/codegenie/**/*.py`; bench-curation scripts under `bench/` and `scripts/` are exempt because they live outside the policed runtime closure)

## Validation notes

Validated: 2026-06-05
Verdict: HARDENED
Findings addressed: 26 total — 6 block, 14 harden, 6 nit
Critic reports: Consistency (9), Coverage (11), Test-Quality (10), Design-Patterns (4). No `NEEDS RESEARCH` — every pattern is precedented in this repo (S2-02 HARDENED's canonical digest composition, ADR-0005 §Consequences "case_digest excludes case.toml" + pre-amendment fact pattern, S5-01 HARDENED's `_HERE`-style module-local constants, `structlog.testing.capture_logs` at `tests/unit/parsers/test_safe_yaml.py:32`).

**Conflict resolutions** (priority: Consistency > Coverage > Test-Quality > Design-Patterns):

- **B-DIGEST-ALGORITHM (F-CON-1 — BLOCK).** Consistency wins. The original §Implementation outline §3 prescribed a digest algorithm that walks `(case_dir/"input").rglob("*")` + `(case_dir/"expected").rglob("*")` separately, sorts by `str(p)` (absolute path → cross-machine non-determinism), does not exclude `case.toml`, follows symlinks, and frames bytes as `(relpath || filebytes)` per file. The HARDENED S2-02 §AC-3 canonical algorithm walks `case_dir.rglob("*")` *once*, sorts by `p.relative_to(case_dir).as_posix()`, excludes `case.toml` (per ADR-0005 §Consequences), rejects symlinks (S2-02 §AC-9), and frames bytes as records `f"{rel_posix}\x1f{content_hash(p)}".encode()` joined by `\x1e` and BLAKE3'd once. **Every byte the story-prescribed algorithm produces would mismatch what the loader computes.** §Implementation outline §3 now cites S2-02 §AC-3 verbatim and the integration test imports `_compute_case_dir_digest` from the loader (private helper; the `from codegenie.eval.loader import _compute_case_dir_digest` form is the contract; the helper graduates to a public `codegenie.eval.digests.compute_case_dir_digest` when the third non-loader consumer lands per F-DP-1).
- **B-INPUT-POINTER-DROPPED (F-CON-2 — BLOCK).** Consistency wins. The original AC-2 left an `input-pointer.toml` escape hatch ("if pointing into tests/cassettes/phase4/"); the loader does not support pointers — S2-02 §AC-5 raises `BenchCaseLoadError(field="input", reason="input/ directory not found")` if `(case_dir / "input").is_dir()` is False, and `input-pointer.toml` is a file, not a directory. Dropped the escape hatch; `input/` MUST be a real, populated directory. If a curator's pre-fix snapshot is genuinely large, the resolution is "commit a minimal extracted snapshot covering only the files the recipe needs to read/touch" — defer pointer support to a future story if portfolio scale forces it.
- **B-CANARY-DERIVATION (F-CON-3 — BLOCK).** Consistency wins. The original §Implementation outline §3 said "`cassette_canary_pin` extracted from the cassette's canary metadata" — but ADR-0005 itself names ADR-P4-006 (the Phase 4 amendment) as *shipping with Phase 6.5 work*; no existing Phase 4 cassette under `tests/cassettes/phase4/` carries the metadata, so the "extract" path is unreachable. The fallback in Notes line 194 (`blake3(cassette_path.encode())[:32]`) lacks domain separation and an unspecified path encoding (absolute vs repo-relative). Pinned the canonical deterministic derivation in AC-3a: `cassette_canary_pin = blake3.blake3(f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")).hexdigest()[:32]`, where `cassette_relpath_posix` is `source_cassette.resolve().relative_to(REPO_ROOT).as_posix()`. The `phase4-cassette:` prefix domain-separates from future canary schemes; the repo-relative POSIX path is reproducible across contributors and platforms. When ADR-P4-006 ships and Phase 4 cassettes re-cut with metadata, the derivation upgrades to "read metadata if present, else derive" — a one-line strategy upgrade.
- **B-DIGESTS-YAML-SIGNED-HERE (F-CON-4 — BLOCK).** Consistency wins. The original §Implementation outline §5 said "Add a digests-yaml stub entry for each case (the full signing happens in S5-05)" — but S2-02 §AC-6a requires every value match `re.fullmatch(r"blake3:[0-9a-f]{64}", v)` AND S2-02 §AC-3 step (c) compares the entry to the canonical recomputation; a literal stub of `"blake3:" + "0" * 64` passes the regex but raises `BenchCaseDigestMismatch` immediately. There is no "stub" path through the HARDENED loader. This story signs its 5 cases in `cases/digests.yaml`; S5-04 appends its 5; S5-05 ships `scripts/sign_bench_digests.py` for future re-signing operations and runs the full E2E. Added `bench/vuln-remediation/cases/digests.yaml` to Files-to-touch.
- **B-E2E-DROPPED (F-CON-5 — BLOCK).** Consistency wins. The original AC-7 prescribed `codegenie eval run --task-class=vuln-remediation --cases='00{1..5}-*'` exits 0 — directly contradicting §Out of scope §3 ("The E2E run. S5-05 exercises the cases through `codegenie eval run`. Here we only assert they *load*.") which is correct on multiple counts: the real `vuln-remediation` SUT lives in Phase 6 (not yet shipped); the deterministic stub SUT is built in S5-05 (not yet shipped); the `--cases` glob filter requires CLI support S4-02 may not provide. Dropped AC-7 entirely; kept the narrower "loader loads all 5 without raising" contract (AC-4).
- **B-CASE-ID-DIR-INVARIANT (F-CON-6 — BLOCK).** Consistency wins. S2-02 §AC-7 raises `BenchCaseLoadError(field="case_id")` when `case.case_id != directory.name`; a curator typo on case_id silently passes the original `test_case_ids_follow_naming_convention` (the regex matches both correct and typo'd IDs) and only surfaces at the loader. New AC-4 pins the bidirectional invariant; new test asserts `case.case_id == case_dir.name` for each of the 5 directly (independent of the loader walk).
- **Symlink-freeness pinned at story-test boundary (F-CON-7 — HARDEN).** Defense-in-depth: even though S2-02 §AC-9 catches symlinks at load time, the story tests assert symlink-freeness directly so curator-time mistakes surface with a path-naming diagnostic at the story-test boundary, not as an opaque loader error.
- **commit_sha vs derivation SHA disambiguated (F-CON-8 — HARDEN).** Two distinct SHAs were conflated: `BenchCase.commit_sha: str | None` (the Pydantic field; stays `None` per ADR-0006 §Consequences for `source="curated"`) and the source-cassette commit SHA at derivation time (lives in the comment block at top of `case.toml`). Clarified throughout.
- **rubric ≠ reader-of-expected (F-CON-9 — HARDEN).** AC-2 originally said "ground-truth artifacts the rubric reads (e.g., `expected/diff.patch`, ...)". S5-02 HARDENED makes clear the rubric reads `harness_output` only, never `expected/`. `expected/` is consumed by the SUT (Phase 6's `VulnRemediationSut.run_case` reads it to populate `harness_output["validator"]["cve_dropped"]` etc.). AC-2 rephrased; Notes-for-implementer updated.
- **disposition / difficulty distribution pinned (F-COV-4 + F-TQ-7 — HARDEN).** Original Notes "expect ~5 positive" and "skew easy" weren't enforced. New AC-7: at least 4 of 5 cases have `disposition="positive"`; at least 4 of 5 have `difficulty="easy"`. `disposition="negative"` rejected entirely for RAG-corpus-derived (the cassette demonstrates a fix; the SUT should not refuse it).
- **Source-cassette path existence + distinctness (F-COV-6 + F-COV-7 + F-TQ-3 — HARDEN).** Original `test_case_toml_documents_source_cassette_path` was a substring check (`assert "tests/cassettes/phase4/" in text`) — a typo'd or fake path passes. New test parses `# Derived from: tests/cassettes/phase4/<path>` line per case, asserts the resolved path exists, is under `tests/cassettes/phase4/`, and the 5 derived-from paths form a set of size 5 (no duplicate-derivation regression illusion).
- **Canonical digest recomputation + 3-way consistency (F-COV-8 + F-COV-9 + F-TQ-2 — HARDEN).** Original `test_every_case_has_blake3_digest_with_64_hex` only checked prefix+length; a curator hand-writing the wrong digest passes the story test and only fails at load time. New test recomputes via `_compute_case_dir_digest(case_dir)` and asserts `_compute_case_dir_digest(case_dir) == case.toml#case_digest == digests.yaml[case_id]`.
- **Canonical canary-pin recomputation (F-TQ-1 — HARDEN).** Original test allowed any 32-hex string. New test recomputes via the canonical formula (per AC-3a) from the comment-block source-cassette path and asserts byte-equality.
- **Bidirectional curation-class ↔ directory-naming check (F-COV-10 + F-TQ-5 — HARDEN).** New test pins that the set of `cases/*/` directories ending in `-rag-corpus-derived` equals the set of case_ids whose `BenchCase.curation_class == "rag-corpus-derived"`, AND that the 5 case_ids are distinct.
- **input/ not a symlink, no input-pointer.toml present (F-TQ-4 — HARDEN).** Original test `c.input_path.is_dir()` silently passes symlinks-to-directories. Tightened to `c.input_path.is_dir() and not c.input_path.is_symlink() and not (case_dir / "input-pointer.toml").exists()`.
- **README mapping table pinned (F-TQ-8 — HARDEN).** §Refactor §1 referenced a mapping table but no AC enforced. New AC-11: `bench/vuln-remediation/README.md` has a "Case mapping" section containing a markdown table with ≥ 5 RAG-corpus-derived rows; each row's cassette path matches the comment-block in the corresponding `case.toml`.
- **Digests algorithm extraction surfaced (F-DP-1 — surfaced; NOT promoted to AC).** Rule-of-three threshold: the canonical digest algorithm lives private in `src/codegenie/eval/loader.py` (S2-02 HARDENED). Consumers stacking up: S5-03 (this story), S5-04 (sibling), S5-05's `scripts/sign_bench_digests.py`, S5-07's scaffolder. When the second *non-loader* consumer lands (likely S5-05's signing script), promote `_compute_case_dir_digest` to public `codegenie.eval.digests.compute_case_dir_digest` (new module). NOT this story's job (Rule 2 — the loader's HARDENED contract is the source of truth; promoting a public surface from S5-03 would be cross-cutting). Surfaced in Notes as the trigger condition for the next consumer story.
- **Canary derivation strategy seam (F-DP-2 — surfaced).** Two paths will eventually exist (deterministic-from-path today, read-from-metadata after ADR-P4-006 lands). For one path today, Rule 2 says no abstraction. When the second path lands, extract a `CanaryPinSource` sum type (`Path | CassetteMetadata`) + `derive_canary_pin(source) -> str` smart-constructor. Surfaced in Notes.
- **Functional core / imperative shell endorsed (F-DP-4 — surfaced).** The canonical S2-02 digest algorithm is already a functional core. The curation work (selecting cassettes, copying snapshots) is imperative-shell territory. No structural change; surfaced.

Full audit log: `_validation/S5-03-vuln-rag-corpus-derived-cases.md`

## Context

ADR-0006 splits the bench corpus into two curation classes. The 5 RAG-corpus-derived cases land **first** and **mechanically** — they're constructed by extracting solved examples from Phase 4's `tests/cassettes/phase4/` cassette tree, which is the same corpus Phase 4's recipe-first/RAG-fallback path was tuned against. The point of these cases is *regression* coverage: if the pipeline degrades on cases it has already solved once, the harness will surface it. The point is explicitly **not** judgment evidence — ADR-0006 §Decision is unambiguous that promotion to silver requires 5 held-out cases (S5-04). These 5 are the schedule-permitting half of the 5+5 floor.

Mechanical construction matters because the long-pole curation work (S5-04) is hand-built CVE-fix ground truth. Shipping these 5 mechanically buys schedule margin for S5-04 without compromising the memorization-vs-judgment distinction.

The story executes against a HARDENED S2-02 loader. The canonical case-dir digest algorithm at S2-02 §AC-3 is the *only* algorithm allowed for `case_digest`. The `cassette_canary_pin` derivation is the deterministic-from-path formula (ADR-P4-006 has not shipped yet; every existing Phase 4 cassette pre-dates the amendment). `cases/digests.yaml` is signed by this story for its 5 cases (S5-04 appends, S5-05 ships the re-sign script). The E2E run is S5-05's job (Phase 6 SUT + deterministic stub).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §bench/{task-class}/ directory contract` (line 698) — `case.toml` schema; required keys (`case_id`, `task_class`, `disposition`, `difficulty`, `source`, `curation_class`, `added_at`, `last_validated_at`, `cassette_canary_pin`, `case_digest`); optional `commit_sha` (required iff `source != "curated"`).
  - `../phase-arch-design.md §Data model → BenchCase` (lines 757–773) — required field shapes; `case_digest: str` is `"blake3:<hex>"`; `cassette_canary_pin: str` is 32 hex chars; both `input_path` and `expected_path` are required `Path`.
  - `../phase-arch-design.md §Testing strategy → Fixture portfolio` — names `bench/vuln-remediation/` as the production fixture, with the 5+5 split.
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Decision §Consequences` — `Canary.mint(seed=bytes.fromhex(case.cassette_canary_pin))` is the per-case binding; ADR-P4-006 ships with this phase as an amendment to Phase 4; `case_digest` excludes `case.toml` so pin rotation is identity not content.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision §Consequences` — naming convention `001-005-rag-corpus-derived-<slug>` (advisory; not fence-enforced); the cassette-derivation script is the curator's tool; `source="curated"` for RAG-corpus-derived cases.
- **Production ADRs:** `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the upstream commitment these cases regression-test against.
- **Sibling HARDENED stories (load-bearing contracts):**
  - `S2-02-loader-cases-and-digests.md §AC-3` — **the canonical case-dir digest algorithm; the only algorithm allowed for `case_digest`**.
  - `S2-02-loader-cases-and-digests.md §AC-5` — `(case_dir / "input").is_dir()` invariant.
  - `S2-02-loader-cases-and-digests.md §AC-6a §AC-6b` — `digests.yaml` schema + ↔-filesystem completeness rules.
  - `S2-02-loader-cases-and-digests.md §AC-7` — `case.case_id == case_dir.name` invariant.
  - `S2-02-loader-cases-and-digests.md §AC-9` — symlink rejection rule.
  - `S5-02-vuln-rubric-and-unit-tests.md` (HARDENED) — the rubric reads `harness_output`, not `expected/`.
- **Source design:** `../High-level-impl.md §Step 5` — "5 cases mechanically derived from `tests/cassettes/phase4/`".

## Goal

Construct exactly 5 `BenchCase` directories under `bench/vuln-remediation/cases/` with `curation_class="rag-corpus-derived"`, each derived from a distinct `tests/cassettes/phase4/` solved-example cassette via the canonical mechanical procedure pinned in AC-3 / AC-3a; each carrying `case.toml`, a real `input/` directory, a real `expected/` directory, a deterministically-derived `cassette_canary_pin` (32 hex), and a `case_digest` computed via the canonical S2-02 §AC-3 algorithm; the 5 cases are signed in `bench/vuln-remediation/cases/digests.yaml`; `codegenie.eval.loader.load_cases(task_class)` returns all 5 without raising; defense-in-depth structural tests pin the bidirectional invariants the loader catches lazily.

## Acceptance criteria

- [ ] **AC-1 (directory naming + count).** `bench/vuln-remediation/cases/` contains exactly 5 directories whose names match `re.fullmatch(r"^00[1-5]-[a-z0-9][a-z0-9-]*-rag-corpus-derived$", name)`. The 5 directory basenames form a set of size 5. The test enumerates `sorted(p.name for p in (BENCH_ROOT/"vuln-remediation"/"cases").iterdir() if p.is_dir())` — filtering nothing — and asserts the count of names matching the regex equals 5 AND that no other directory's name *contains* the substring `-rag-corpus-derived` (defense against `006-cve-2024-99999-rag-corpus-derived/` index collision with S5-04's territory).

- [ ] **AC-2 (each case directory's filesystem shape).** Each of the 5 case directories contains:
  - `case.toml` (regular file, UTF-8) validating into a `BenchCase` (via `BenchCase.model_validate(tomllib.loads(text))`) with: `task_class == "vuln-remediation"`, `curation_class == "rag-corpus-derived"`, `source == "curated"`, `disposition ∈ {"positive", "ambiguous"}` (NOT "negative" — see AC-7), `difficulty ∈ {"easy", "medium", "hard"}`, `commit_sha is None` (per ADR-0006 §Consequences — `source="curated"` does not require it), `added_at` and `last_validated_at` are tz-aware UTC `datetime`s (`tzinfo == timezone.utc`), `cassette_canary_pin` is 32 lowercase hex characters, `case_digest` matches `re.fullmatch(r"^blake3:[0-9a-f]{64}$", value)`, `input_path` resolves to the string `"input"` (relative POSIX), `expected_path` resolves to the string `"expected"` (relative POSIX), `cassette_path is None` (the cassette is referenced from the comment block, not the optional `cassette_path` field — that's Phase 4's resolution territory).
  - `input/` is a real directory (`(case_dir / "input").is_dir() and not (case_dir / "input").is_symlink()`), is non-empty, and contains the pre-fix snapshot of the file(s) the recipe touches (minimal — not the full repo, per F-CON-2 dropping the pointer escape hatch).
  - `expected/` is a real directory (`(case_dir / "expected").is_dir() and not (case_dir / "expected").is_symlink()`), is non-empty, and contains the ground-truth artifacts the **SUT** consults at run time (the rubric reads `harness_output` only, never `expected/` — see Notes-for-implementer). The exact filenames inside `expected/` are SUT-contract territory (Phase 6); this story's curator follows Phase 6's contract or, for the Phase-6.5 deterministic-stub SUT (built in S5-05), follows the stub's contract.
  - **No `input-pointer.toml` file exists at the case_dir root** (defense against re-adding the dropped escape hatch — F-CON-2).
  - **No file or directory anywhere under `case_dir.rglob("*")` is a symlink** (defense-in-depth on S2-02 §AC-9).

- [ ] **AC-3 (case_digest = canonical S2-02 §AC-3 algorithm; no inline reimplementation).** Each case.toml's `case_digest` field equals the canonical algorithm S2-02 §AC-3 prescribes:
  - (a) `paths = sorted(p for p in case_dir.rglob("*") if p.is_file() and not p.is_symlink() and p.name not in {"case.toml"}, key=lambda p: p.relative_to(case_dir).as_posix())`.
  - (b) `records = [f"{p.relative_to(case_dir).as_posix()}\x1f{content_hash(p)}".encode("utf-8") for p in paths]` where `content_hash` is `codegenie.hashing.content_hash` (Phase 0 per-file content BLAKE3).
  - (c) `case_digest = "blake3:" + blake3(b"\x1e".join(records)).hexdigest()`.
  The integration test imports `_compute_case_dir_digest` from `codegenie.eval.loader` (private helper; the contracted name is `from codegenie.eval.loader import _compute_case_dir_digest`) and asserts byte-equality with `case.toml#case_digest` per case. The story does **NOT** inline a re-implementation of the algorithm — every consumer goes through the loader's helper. (When the next consumer story promotes the helper to a public name per F-DP-1, this story's test switches to the public name in one line.)

- [ ] **AC-3a (`cassette_canary_pin` = canonical deterministic-from-path formula).** Each case.toml's `cassette_canary_pin` equals:
  ```python
  REPO_ROOT = <repo root resolved>
  cassette_relpath_posix = source_cassette.resolve().relative_to(REPO_ROOT).as_posix()
  domain_separated = f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")
  cassette_canary_pin = blake3.blake3(domain_separated).hexdigest()[:32]
  ```
  where `source_cassette` is the path parsed from the case.toml comment-block line `# Derived from: tests/cassettes/phase4/<path>`. The `phase4-cassette:` prefix is the domain-separation token (literal; no whitespace; ends with colon). The 32-hex result is lowercased. The integration test re-derives each pin from the comment-block path and asserts byte-equality with `case.toml#cassette_canary_pin`. This is the deterministic-derivation path required because all existing Phase 4 cassettes pre-date ADR-P4-006 (the metadata-emitting amendment; landing as part of Phase 6.5 work). When ADR-P4-006 ships and cassettes are re-cut with metadata, a follow-on story upgrades the derivation to a Strategy seam (F-DP-2); for now, the formula is pinned.

- [ ] **AC-4 (case_id ↔ directory-name + curation_class ↔ directory-name-suffix invariants; case_id distinctness).** For each of the 5 case directories `case_dir`: `BenchCase.case_id == case_dir.name` (byte-equality). Additionally, `case_dir.name.endswith("-rag-corpus-derived")` ⇔ `BenchCase.curation_class == "rag-corpus-derived"`. The set `{c.case_id for c in rag_cases}` has cardinality 5. These are story-test–level defense-in-depth on S2-02 §AC-7 (case_id↔dir) and S2-02 §AC-8 (collision).

- [ ] **AC-5 (`loader.load_cases` succeeds; returns exactly 5 RAG-corpus-derived cases when filtered).** `load_cases(load_task_class("vuln-remediation", bench_root=BENCH_ROOT))` returns a `tuple[BenchCase, ...]` without raising; the 5 cases whose `curation_class == "rag-corpus-derived"` are present (other curation classes may also be present once S5-04 lands; this story's test filters by `curation_class` and asserts exactly 5 of that class). All 5 have `source == "curated"`, `task_class == "vuln-remediation"`, `commit_sha is None`. Returned tuple is sorted ascending by `case_id`.

- [ ] **AC-6 (`bench/vuln-remediation/cases/digests.yaml` exists, parses, signs 5 cases canonically).** `bench/vuln-remediation/cases/digests.yaml` is committed; `yaml.safe_load(text)` returns a `dict[str, str]`; for each of the 5 RAG-corpus-derived case_ids, the file contains an entry `{case_id: "blake3:<64-hex>"}` matching `re.fullmatch(r"^blake3:[0-9a-f]{64}$", value)`; each digest value equals `_compute_case_dir_digest(BENCH_ROOT/"vuln-remediation"/"cases"/case_id)` byte-for-byte. The file is sorted alphabetically by key (`yaml.safe_dump(data, sort_keys=True)`). The 5 entries from this story coexist peacefully with the 5 from S5-04 (S5-04 appends; this story does not pre-allocate held-out entries).

- [ ] **AC-6a (3-way digest consistency).** For each of the 5 cases: `case.toml#case_digest == digests.yaml[case_id] == _compute_case_dir_digest(case_dir)` (all three byte-equal). The integration test asserts this triple-equality per case. Defense-in-depth: catches the curator forgetting to update one of the three after a re-sign.

- [ ] **AC-7 (disposition + difficulty distribution).** At least 4 of the 5 cases have `disposition == "positive"`; at most 1 has `disposition == "ambiguous"`. ZERO have `disposition == "negative"` (the source cassette demonstrates a *fix*; an SUT-should-refuse case is structurally incompatible with RAG-corpus-derivation). At least 4 of 5 have `difficulty == "easy"` (RAG-derived cases skew easy — the pipeline already solved them). A curator wanting a higher-difficulty mechanically-derived case must justify in the case.toml comment block.

- [ ] **AC-8 (source-cassette path traceability: exists + distinctness).** Each `case.toml` contains a comment block at the top with the literal lines (or equivalent, same content) `# Derived from: tests/cassettes/phase4/<path>` and `# Source cassette commit: <40-char lowercase hex SHA>`. The integration test parses each `case.toml` text, extracts both lines per case via regex `^# Derived from: (tests/cassettes/phase4/.+)$` and `^# Source cassette commit: ([0-9a-f]{40})$`. For each extracted `tests/cassettes/phase4/<path>` value: the path resolves under `<REPO_ROOT>/tests/cassettes/phase4/`, exists on disk, and is either a file or a directory (cassette layout shape is Phase 4's). For each extracted SHA: matches the 40-hex regex. The set of 5 extracted source-cassette paths has cardinality 5 (no duplicate-derivation regression illusion). The set of 5 commit SHAs may have any cardinality (multiple cassettes may share a commit).

- [ ] **AC-9 (curation_class-derived-case set ↔ directory-name set).** `directory_names_ending_rag = {p.name for p in cases_root.iterdir() if p.is_dir() and p.name.endswith("-rag-corpus-derived")}` equals `{c.case_id for c in loaded_cases if c.curation_class == "rag-corpus-derived"}` (set equality). Catches a case mistagged `curation_class="held-out"` in a `*-rag-corpus-derived/` directory (and vice-versa).

- [ ] **AC-10 (symlink-freeness — story-level defense-in-depth on S2-02 §AC-9).** For each of the 5 case directories, walking `rglob("*")` yields zero symlinks. Test produces a diagnostic naming the offending case_id and relpath if any symlink is found.

- [ ] **AC-11 (README mapping table).** `bench/vuln-remediation/README.md` contains a section whose markdown header text is `## Case mapping` (or equivalent unambiguous header). Under it: a markdown table with header row `| case_id | source cassette | derivation SHA | curation class |` (or equivalent; column count = 4, column 3 contains 40-hex SHAs). The table contains a row per RAG-corpus-derived case_id; the column-2 cell value matches the `# Derived from:` comment block in the corresponding `case.toml`. Also includes a "Selection criterion" paragraph naming what made these 5 cassettes the chosen 5 (e.g., "5 most representative across the recipe-first and RAG-fallback paths"). The integration test parses the README, extracts the markdown table, and asserts row count ≥ 5 with the constraints above.

- [ ] **AC-12 (typed-error parity surface — no story-introduced regressions).** Running the integration test before any of the 5 cases are present (red marker) produces a clear `BenchCaseLoadError` naming `cases/digests.yaml` (the file is missing); after step (1) of §Implementation outline (digests.yaml stubbed empty), the test produces a clear failure mentioning the 5 expected case_ids; after each case is signed, the count converges. This pins that no failure path emits an `OSError`/`KeyError`/`AssertionError` directly — all failures route through `codegenie.eval.errors`.

- [ ] **AC-13 (lint + typecheck + red→green).** Red test from §TDD plan (`tests/integration/test_vuln_rag_corpus_derived_cases_load.py`) exists, was committed at red, now green. `ruff check tests/integration/test_vuln_rag_corpus_derived_cases_load.py bench/vuln-remediation/`, `ruff format --check tests/integration/test_vuln_rag_corpus_derived_cases_load.py`, `pytest tests/integration/test_vuln_rag_corpus_derived_cases_load.py -v` all green. `mypy --strict tests/integration/test_vuln_rag_corpus_derived_cases_load.py` green (test file imports `BenchCase`, `load_cases`, `load_task_class`, and `_compute_case_dir_digest`; all typed surfaces). `make fence` continues to pass — no new closure imports introduced under `src/codegenie/`; the test's `import blake3` (for AC-3a recomputation) lives under `tests/` and is outside the policed runtime closure.

## Implementation outline

1. **Write the red test** `tests/integration/test_vuln_rag_corpus_derived_cases_load.py` first — see §TDD plan. Commit as the red marker; the test should fail with `BenchCaseLoadError` naming `cases/digests.yaml` (file not yet present).

2. **Identify 5 source cassettes** under `tests/cassettes/phase4/` representing distinct solved examples (CVE fixes the Phase 4 pipeline successfully resolved at recipe-first or RAG-fallback). Document the selection criterion in `bench/vuln-remediation/README.md` (e.g., "5 most representative cassettes across the recipe-first and RAG-fallback paths, mix of language ecosystems where available"). For each chosen cassette, record its repo-relative POSIX path and the master commit SHA at curation time — these go into the `case.toml` comment block.

3. **For each of the 5 cassettes**, build the case directory under `bench/vuln-remediation/cases/00N-<slug>-rag-corpus-derived/` (where N ∈ {1..5} and `<slug>` is derived from the CVE id or a short descriptor; lowercase):
   - **case.toml** with:
     - A comment block at the top with literally:
       ```
       # curation_class per ADR-0006
       # Derived from: tests/cassettes/phase4/<cassette-path>
       # Source cassette commit: <40-char SHA at derivation time>
       ```
     - All required `BenchCase` fields per AC-2. `commit_sha` is `None` (omit the key or set `commit_sha = ""` followed by Pydantic coercion — confirm S1-02's Pydantic shape accepts the `null`/missing form; safest: do not emit the key when `source = "curated"`, since `commit_sha: str | None` defaults to `None` if absent).
     - `input_path = "input"`, `expected_path = "expected"`.
     - `cassette_canary_pin` derived via AC-3a's canonical formula (compute via a one-off curator command or S5-07's scaffolder once it lands).
     - `case_digest` computed via `_compute_case_dir_digest(case_dir)` *after* populating `input/` and `expected/` — the digest pins content, so it's computed last.
   - **input/** populated from the cassette's pre-fix snapshot — extract only the files the recipe touches (NOT the whole repo). Files must be regular files (no symlinks). Per AC-2: `input/` non-empty.
   - **expected/** populated from the cassette's post-fix snapshot — the SUT contract decides the filenames (typically `expected/diff.patch` + `expected/validator_output.json` for the Phase-6.5 stub SUT or Phase 6's real SUT; follow S5-05's deterministic-stub-SUT contract when defined). Files must be regular files. Per AC-2: `expected/` non-empty.

4. **Sign the 5 cases in `bench/vuln-remediation/cases/digests.yaml`**:
   ```python
   from codegenie.eval.loader import _compute_case_dir_digest
   import yaml, pathlib
   cases_root = pathlib.Path("bench/vuln-remediation/cases")
   rag_dirs = sorted(p for p in cases_root.iterdir() if p.is_dir() and p.name.endswith("-rag-corpus-derived"))
   digests = {p.name: _compute_case_dir_digest(p) for p in rag_dirs}
   # If digests.yaml already exists (S5-04 has shipped first), merge:
   existing = yaml.safe_load((cases_root / "digests.yaml").read_text()) if (cases_root / "digests.yaml").exists() else {}
   existing.update(digests)
   (cases_root / "digests.yaml").write_text(yaml.safe_dump(existing, sort_keys=True))
   ```
   Verify parity per AC-6a: `case.toml#case_digest == digests.yaml[case_id] == _compute_case_dir_digest(case_dir)`.

5. **Update `bench/vuln-remediation/README.md`** per AC-11: add the "Case mapping" section with the table (≥ 5 RAG-corpus-derived rows) and the selection-criterion paragraph.

6. **Iterate test → green.** The integration test's failures are typed (per AC-12) — each failure points at a specific case_id and field, not a generic "load failed."

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_vuln_rag_corpus_derived_cases_load.py`

```python
# tests/integration/test_vuln_rag_corpus_derived_cases_load.py
"""5 RAG-corpus-derived cases must load cleanly and satisfy ADR-0005/ADR-0006
contracts. ADR-0006 §Consequences names this curation class; we assert structural
shape + cross-field invariants — not scoring correctness (S5-05's E2E job).

Every test is concrete and mutation-resistant: digest re-computation via the
canonical S2-02 §AC-3 algorithm, canary-pin re-derivation via the canonical
AC-3a formula, set-equality on directory-naming↔curation-class, source-cassette
path existence + distinctness, disposition/difficulty distribution caps.
"""

from __future__ import annotations

import re
import tomllib
from datetime import timezone
from pathlib import Path

import blake3  # test-only: AC-3a canonical canary-pin re-derivation
import pytest
import yaml

from codegenie.eval.loader import (
    _compute_case_dir_digest,  # canonical S2-02 §AC-3 algorithm; private until F-DP-1 promotes
    load_cases,
    load_task_class,
)
from codegenie.eval.models import BenchCase

REPO_ROOT = Path(__file__).parents[2]
BENCH_ROOT = REPO_ROOT / "bench"
CASES_ROOT = BENCH_ROOT / "vuln-remediation" / "cases"

RAG_NAME_RE = re.compile(r"^00[1-5]-[a-z0-9][a-z0-9-]*-rag-corpus-derived$")
DERIVED_FROM_RE = re.compile(r"^# Derived from: (tests/cassettes/phase4/.+)$", re.MULTILINE)
SOURCE_SHA_RE = re.compile(r"^# Source cassette commit: ([0-9a-f]{40})$", re.MULTILINE)
BLAKE3_DIGEST_RE = re.compile(r"^blake3:[0-9a-f]{64}$")
HEX32_RE = re.compile(r"^[0-9a-f]{32}$")


def _load_rag_cases() -> tuple[BenchCase, ...]:
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    cases = load_cases(tc)
    return tuple(c for c in cases if c.curation_class == "rag-corpus-derived")


def _list_rag_dirs() -> list[Path]:
    return sorted(p for p in CASES_ROOT.iterdir() if p.is_dir() and p.name.endswith("-rag-corpus-derived"))


def _read_case_toml_text(case_dir: Path) -> str:
    return (case_dir / "case.toml").read_text(encoding="utf-8")


# --- AC-1: directory naming + count ----------------------------------------

def test_exactly_five_rag_corpus_derived_directories_with_canonical_names():
    rag_dirs = _list_rag_dirs()
    assert len(rag_dirs) == 5, f"expected 5 RAG-corpus-derived dirs, found {len(rag_dirs)}: {[p.name for p in rag_dirs]}"
    for p in rag_dirs:
        assert RAG_NAME_RE.fullmatch(p.name), f"{p.name!r} does not match the canonical regex"
    # No other directory has the substring (catches 006-…-rag-corpus-derived index collision):
    all_dirs = [p.name for p in CASES_ROOT.iterdir() if p.is_dir()]
    intruders = [name for name in all_dirs if "-rag-corpus-derived" in name and not RAG_NAME_RE.fullmatch(name)]
    assert intruders == [], f"directory(ies) with -rag-corpus-derived suffix outside 001-005: {intruders}"


# --- AC-2: per-case filesystem shape + BenchCase field invariants -----------

@pytest.mark.parametrize("case_dir_index", range(5), ids=lambda i: f"case-{i+1}")
def test_each_case_directory_shape_and_bench_case_invariants(case_dir_index):
    rag_dirs = _list_rag_dirs()
    if len(rag_dirs) <= case_dir_index:
        pytest.skip(f"only {len(rag_dirs)} dirs; case {case_dir_index+1} not yet present")
    case_dir = rag_dirs[case_dir_index]
    # case.toml exists, parses, validates into BenchCase:
    case_toml = case_dir / "case.toml"
    assert case_toml.is_file() and not case_toml.is_symlink()
    parsed = tomllib.loads(_read_case_toml_text(case_dir))
    bc = BenchCase.model_validate(parsed)
    # Field constraints per AC-2:
    assert bc.task_class == "vuln-remediation"
    assert bc.curation_class == "rag-corpus-derived"
    assert bc.source == "curated"
    assert bc.disposition in {"positive", "ambiguous"}, f"{bc.case_id}: disposition={bc.disposition!r}, must be positive or ambiguous"
    assert bc.difficulty in {"easy", "medium", "hard"}
    assert bc.commit_sha is None, f"{bc.case_id}: commit_sha must be None for source=curated"
    assert bc.added_at.tzinfo is not None and bc.added_at.utcoffset() == timezone.utc.utcoffset(None)
    assert bc.last_validated_at.tzinfo is not None and bc.last_validated_at.utcoffset() == timezone.utc.utcoffset(None)
    assert HEX32_RE.fullmatch(bc.cassette_canary_pin), f"{bc.case_id}: cassette_canary_pin not 32 lowercase hex"
    assert BLAKE3_DIGEST_RE.fullmatch(bc.case_digest), f"{bc.case_id}: case_digest not blake3:<64 hex>"
    assert str(bc.input_path) == "input"
    assert str(bc.expected_path) == "expected"
    assert bc.cassette_path is None
    # Filesystem shape:
    assert (case_dir / "input").is_dir() and not (case_dir / "input").is_symlink(), f"{bc.case_id}: input/ missing or symlink"
    assert (case_dir / "expected").is_dir() and not (case_dir / "expected").is_symlink(), f"{bc.case_id}: expected/ missing or symlink"
    assert any((case_dir / "input").iterdir()), f"{bc.case_id}: input/ empty"
    assert any((case_dir / "expected").iterdir()), f"{bc.case_id}: expected/ empty"
    # Negative: no input-pointer.toml (F-CON-2 backstop):
    assert not (case_dir / "input-pointer.toml").exists(), f"{bc.case_id}: input-pointer.toml is forbidden (F-CON-2)"


# --- AC-3: case_digest == canonical S2-02 §AC-3 algorithm ------------------

@pytest.mark.parametrize("case_dir_index", range(5), ids=lambda i: f"case-{i+1}")
def test_case_digest_matches_canonical_algorithm(case_dir_index):
    rag_dirs = _list_rag_dirs()
    if len(rag_dirs) <= case_dir_index:
        pytest.skip(f"only {len(rag_dirs)} dirs")
    case_dir = rag_dirs[case_dir_index]
    parsed = tomllib.loads(_read_case_toml_text(case_dir))
    declared = parsed["case_digest"]
    canonical = _compute_case_dir_digest(case_dir)
    assert declared == canonical, (
        f"{case_dir.name}: case.toml#case_digest={declared!r} != "
        f"_compute_case_dir_digest={canonical!r}. The curator wrote the wrong "
        f"algorithm or forgot to re-sign after editing input/ or expected/."
    )


# --- AC-3a: cassette_canary_pin == canonical deterministic-from-path formula

@pytest.mark.parametrize("case_dir_index", range(5), ids=lambda i: f"case-{i+1}")
def test_cassette_canary_pin_matches_canonical_derivation(case_dir_index):
    rag_dirs = _list_rag_dirs()
    if len(rag_dirs) <= case_dir_index:
        pytest.skip(f"only {len(rag_dirs)} dirs")
    case_dir = rag_dirs[case_dir_index]
    text = _read_case_toml_text(case_dir)
    m = DERIVED_FROM_RE.search(text)
    assert m, f"{case_dir.name}: case.toml has no `# Derived from: tests/cassettes/phase4/...` line"
    cassette_relpath_posix = m.group(1).strip()
    # The canonical AC-3a formula:
    expected_pin = blake3.blake3(
        f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")
    ).hexdigest()[:32]
    parsed = tomllib.loads(text)
    actual_pin = parsed["cassette_canary_pin"]
    assert actual_pin == expected_pin, (
        f"{case_dir.name}: cassette_canary_pin={actual_pin!r} does not match "
        f"the canonical formula blake3('phase4-cassette:{cassette_relpath_posix}')[:32] "
        f"= {expected_pin!r}. Until ADR-P4-006 ships, this is the only allowed derivation."
    )


# --- AC-4: case_id ↔ directory-name + curation_class ↔ suffix + distinctness

def test_case_id_equals_directory_name_and_curation_class_matches_suffix():
    cases = _load_rag_cases()
    assert len(cases) == 5, f"loader returned {len(cases)} RAG-corpus-derived cases; expected 5"
    # case_id distinctness:
    case_ids = [c.case_id for c in cases]
    assert len(set(case_ids)) == 5, f"duplicate case_ids: {case_ids}"
    # case_id ↔ directory-name (independent of loader's S2-02 §AC-7 check):
    for c in cases:
        case_dir = CASES_ROOT / c.case_id
        assert case_dir.is_dir(), f"case_id {c.case_id!r} has no matching directory"
        parsed = tomllib.loads(_read_case_toml_text(case_dir))
        assert parsed["case_id"] == case_dir.name, (
            f"{case_dir.name}: case.toml#case_id={parsed['case_id']!r} != directory name"
        )
    # curation_class ↔ suffix:
    for c in cases:
        assert c.case_id.endswith("-rag-corpus-derived"), f"{c.case_id}: missing suffix"


# --- AC-5: loader returns exactly 5 RAG-corpus-derived cases ----------------

def test_loader_returns_exactly_five_rag_corpus_derived_with_curated_source():
    cases = _load_rag_cases()
    assert len(cases) == 5
    for c in cases:
        assert c.source == "curated", f"{c.case_id}: source must be curated"
        assert c.task_class == "vuln-remediation"
        assert c.commit_sha is None
    # Sorted ascending by case_id:
    assert list(cases) == sorted(cases, key=lambda c: c.case_id)


# --- AC-6 + AC-6a: digests.yaml exists, parses, signs each case canonically -

def test_digests_yaml_signs_five_rag_corpus_derived_cases_canonically():
    digests_path = CASES_ROOT / "digests.yaml"
    assert digests_path.is_file(), "bench/vuln-remediation/cases/digests.yaml missing"
    parsed = yaml.safe_load(digests_path.read_text())
    assert isinstance(parsed, dict), f"digests.yaml root must be a mapping; got {type(parsed).__name__}"
    rag_case_ids = {c.case_id for c in _load_rag_cases()}
    for case_id in rag_case_ids:
        assert case_id in parsed, f"digests.yaml missing entry for {case_id}"
        value = parsed[case_id]
        assert isinstance(value, str) and BLAKE3_DIGEST_RE.fullmatch(value), (
            f"digests.yaml[{case_id}]={value!r}: must be blake3:<64 lowercase hex>"
        )
        # Canonical recomputation:
        canonical = _compute_case_dir_digest(CASES_ROOT / case_id)
        assert value == canonical, (
            f"digests.yaml[{case_id}]={value!r} != canonical {canonical!r}; "
            f"curator must re-sign after editing input/ or expected/"
        )


def test_case_toml_and_digests_yaml_and_canonical_are_three_way_consistent():
    """AC-6a: case.toml#case_digest == digests.yaml[case_id] == canonical algorithm."""
    digests_yaml = yaml.safe_load((CASES_ROOT / "digests.yaml").read_text())
    for c in _load_rag_cases():
        case_dir = CASES_ROOT / c.case_id
        case_toml_digest = tomllib.loads(_read_case_toml_text(case_dir))["case_digest"]
        digests_yaml_digest = digests_yaml[c.case_id]
        canonical = _compute_case_dir_digest(case_dir)
        assert case_toml_digest == digests_yaml_digest == canonical, (
            f"{c.case_id}: 3-way digest divergence — "
            f"case.toml={case_toml_digest!r}, digests.yaml={digests_yaml_digest!r}, "
            f"canonical={canonical!r}"
        )


# --- AC-7: disposition + difficulty distribution ----------------------------

def test_disposition_distribution_at_least_four_positive_none_negative():
    cases = _load_rag_cases()
    dispositions = [c.disposition for c in cases]
    positive_count = dispositions.count("positive")
    negative_count = dispositions.count("negative")
    ambiguous_count = dispositions.count("ambiguous")
    assert negative_count == 0, (
        f"RAG-corpus-derived cases must NOT have disposition=negative "
        f"(the source cassette demonstrates a fix); found {negative_count}"
    )
    assert positive_count >= 4, f"≥4 of 5 must be positive; found {positive_count}: {dispositions}"
    assert ambiguous_count <= 1, f"≤1 of 5 may be ambiguous; found {ambiguous_count}"


def test_difficulty_distribution_at_least_four_easy():
    cases = _load_rag_cases()
    easy_count = sum(1 for c in cases if c.difficulty == "easy")
    assert easy_count >= 4, (
        f"≥4 of 5 RAG-corpus-derived cases must be difficulty=easy "
        f"(the pipeline already solved them); found {easy_count}: "
        f"{[(c.case_id, c.difficulty) for c in cases]}"
    )


# --- AC-8: source-cassette path traceability — exists, distinct, has SHA ----

def test_each_case_documents_existing_source_cassette_and_distinct_paths():
    cases = _load_rag_cases()
    cassette_paths = []
    for c in cases:
        text = _read_case_toml_text(CASES_ROOT / c.case_id)
        m = DERIVED_FROM_RE.search(text)
        assert m, f"{c.case_id}: case.toml missing `# Derived from: tests/cassettes/phase4/...`"
        rel = m.group(1).strip()
        cassette_paths.append(rel)
        resolved = (REPO_ROOT / rel).resolve()
        assert resolved.exists(), f"{c.case_id}: source cassette {rel} does not exist"
        assert (REPO_ROOT / "tests" / "cassettes" / "phase4") in resolved.parents or resolved == (REPO_ROOT / "tests" / "cassettes" / "phase4"), (
            f"{c.case_id}: source cassette {rel} not under tests/cassettes/phase4/"
        )
        m2 = SOURCE_SHA_RE.search(text)
        assert m2, f"{c.case_id}: case.toml missing `# Source cassette commit: <40-char SHA>`"
    assert len(set(cassette_paths)) == 5, (
        f"5 cases must derive from 5 distinct cassettes; got {len(set(cassette_paths))} distinct: {cassette_paths}"
    )


# --- AC-9: bidirectional set equality directory-suffix ↔ curation_class ----

def test_directory_suffix_set_equals_curation_class_rag_set():
    suffix_set = {p.name for p in CASES_ROOT.iterdir() if p.is_dir() and p.name.endswith("-rag-corpus-derived")}
    class_set = {c.case_id for c in _load_rag_cases()}
    assert suffix_set == class_set, (
        f"directory-suffix set {suffix_set} != curation_class set {class_set}; "
        f"a case has curation_class mistagged or a directory has the wrong suffix"
    )


# --- AC-10: symlink-freeness defense-in-depth -------------------------------

def test_no_symlinks_anywhere_under_any_rag_case_directory():
    for case_dir in _list_rag_dirs():
        symlinks = [p for p in case_dir.rglob("*") if p.is_symlink()]
        assert symlinks == [], (
            f"{case_dir.name}: forbidden symlinks at "
            f"{[p.relative_to(case_dir).as_posix() for p in symlinks]}"
        )


# --- AC-11: README mapping table --------------------------------------------

def test_readme_documents_case_mapping_table_with_at_least_five_rag_rows():
    readme_path = BENCH_ROOT / "vuln-remediation" / "README.md"
    assert readme_path.is_file()
    text = readme_path.read_text(encoding="utf-8")
    # Locate the "Case mapping" section:
    section_match = re.search(r"##\s+Case mapping\b.*?(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    assert section_match, "README missing `## Case mapping` section"
    section = section_match.group(0)
    # Extract markdown table rows (lines starting with `|` after a `|---|` separator):
    table_rows = [line for line in section.splitlines() if line.strip().startswith("|") and "---" not in line and not line.strip().startswith("| case_id")]
    # Filter only RAG-corpus-derived rows (defense if S5-04 also adds rows):
    rag_rows = [r for r in table_rows if "rag-corpus-derived" in r]
    assert len(rag_rows) >= 5, f"Case mapping table has {len(rag_rows)} RAG rows; expected ≥ 5"
    # Each row's column-2 (source cassette) must reference tests/cassettes/phase4/:
    for row in rag_rows:
        assert "tests/cassettes/phase4/" in row, f"README row missing cassette path: {row!r}"
```

Run it; confirm BenchCaseLoadError (digests.yaml missing) or empty-rag-directories. Commit as the red marker.

### Green — smallest impl shape

1. Hand-build (or scaffold via S5-07 once it merges) 5 case directories under `bench/vuln-remediation/cases/`, each with `case.toml`, `input/`, `expected/` per §Implementation outline §3.
2. Compute `cassette_canary_pin` via the canonical AC-3a formula; record in each `case.toml`.
3. Compute `case_digest` via `_compute_case_dir_digest(case_dir)` (after `input/` + `expected/` populated); record in each `case.toml`.
4. Sign `bench/vuln-remediation/cases/digests.yaml` per §Implementation outline §4.
5. Update `bench/vuln-remediation/README.md` per AC-11.
6. Iterate the integration test until all 13 ACs / 14 named tests are green.

### Refactor — clean up

- `bench/vuln-remediation/README.md` documents the selection criterion + the case-mapping table (per AC-11). Make the table sortable / scannable.
- Each `case.toml`'s comment block follows the canonical 3-line shape (`# curation_class per ADR-0006` / `# Derived from: ...` / `# Source cassette commit: ...`).
- Sort the case directories alphabetically by `case_id` on disk — the loader sorts anyway, but readable directory listing helps reviewers.
- Per F-DP-1: when the second non-loader consumer of `_compute_case_dir_digest` lands (S5-05's `scripts/sign_bench_digests.py` is the canonical trigger), open a follow-on story to promote it to public `codegenie.eval.digests.compute_case_dir_digest`. This story consumes the private name; the next story promotes.

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/cases/001-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — first RAG-derived case |
| `bench/vuln-remediation/cases/002-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — second case |
| `bench/vuln-remediation/cases/003-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — third case |
| `bench/vuln-remediation/cases/004-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — fourth case |
| `bench/vuln-remediation/cases/005-<slug>-rag-corpus-derived/{case.toml, input/*, expected/*}` | New — fifth case |
| `bench/vuln-remediation/cases/digests.yaml` | New — signs the 5 RAG-corpus-derived cases per S2-02 §AC-6a (S5-04 appends its 5; S5-05 ships the re-sign script) |
| `bench/vuln-remediation/README.md` | Extend — "Case mapping" section + selection-criterion paragraph per AC-11 |
| `tests/integration/test_vuln_rag_corpus_derived_cases_load.py` | New — 14 named tests pinning all 13 ACs |

## Out of scope

- **The held-out 5 cases.** S5-04 owns those (the long-pole). S5-04 will append 5 entries to the same `digests.yaml` this story creates.
- **`digests.yaml` re-signing tooling.** S5-05 ships `scripts/sign_bench_digests.py` as the canonical re-sign script (used after curator edits to `input/` or `expected/`). This story signs the initial 5 entries inline (because the loader cannot tolerate stubs); future re-signs use S5-05's script.
- **The E2E run.** S5-05 exercises the cases through `codegenie eval run` against the deterministic stub SUT. This story only asserts the 5 cases *load* via `load_cases`.
- **`scripts/scaffold_bench_case.py`.** Built in S5-07; this story may or may not depend on it depending on merge order. If S5-07 hasn't merged, hand-build the 5 cases. Both paths must produce byte-identical artifacts (the canonical formulas in AC-3 + AC-3a are the contract).
- **Promotion verdict.** With 5/10 cases, fence-CI #3 fails for any `min_cases_for_promotion` tier ≥ silver (per ADR-0006); running `codegenie eval run --task-class=vuln-remediation` against the *full* bench requires S5-04 + S5-05's stub SUT. This story does not run the full pipeline.
- **Loader-side `input-pointer.toml` resolution.** The escape hatch was rejected per F-CON-2; pointers are not supported by the HARDENED S2-02 loader. If portfolio-scale snapshots demand pointer support, that's a follow-on story amending S2-02 (an ADR-shaped change).
- **Promoting `_compute_case_dir_digest` to a public name.** Per F-DP-1, the promotion happens when the second non-loader consumer lands (likely S5-05). This story consumes the private helper; the promotion is a follow-on story's surgical edit.
- **`disposition="negative"` RAG-corpus-derived cases.** Structurally rejected (the cassette demonstrates a fix). If a curator finds a Phase 4 cassette where the SUT correctly *refused* to fix something, that's evidence for a held-out (S5-04) case, not a RAG-corpus-derived one.

## Notes for the implementer

- **Canonical case_digest algorithm — load-bearing.** Use `_compute_case_dir_digest` from `codegenie.eval.loader` (private helper; the import is `from codegenie.eval.loader import _compute_case_dir_digest`). DO NOT inline a re-implementation, no matter how tempting — the S2-02 HARDENED loader algorithm has five subtle invariants (POSIX relpath sort, `case.toml` exclusion, symlink rejection, `\x1f`/`\x1e` framing, BLAKE3-once over joined records) that a hand-written version will reliably break. The test `test_case_digest_matches_canonical_algorithm` will catch divergence loudly. When the helper graduates to public per F-DP-1, the test's import switches in one line.
- **Canonical `cassette_canary_pin` derivation.** Until ADR-P4-006 ships (the Phase 4 amendment adding `Canary.mint(seed=...)` + cassette canary-metadata emission), every Phase 4 cassette under `tests/cassettes/phase4/` lacks the metadata. The deterministic-derivation path is the ONLY path. The formula is `blake3.blake3(f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")).hexdigest()[:32]` where `cassette_relpath_posix = source_cassette.resolve().relative_to(REPO_ROOT).as_posix()`. The `phase4-cassette:` literal is the domain-separation prefix; do NOT change it (a future canary scheme will use a different prefix to avoid collisions). The test `test_cassette_canary_pin_matches_canonical_derivation` re-derives and asserts byte-equality.
- **`commit_sha` is `None`; the derivation SHA lives in the comment block.** `BenchCase.commit_sha: str | None` is `None` for `source="curated"` per ADR-0006 §Consequences. The 40-char SHA documenting *when the cassette was extracted into this case* lives in the `# Source cassette commit: <SHA>` comment block at the top of `case.toml`. These are two distinct values; don't conflate them.
- **The rubric does NOT read `expected/`.** S5-02 HARDENED's rubric reads `harness_output` only. `expected/` is consumed by the SUT (Phase 6's `VulnRemediationSut.run_case` or S5-05's deterministic stub SUT). The shape of `expected/` (filenames, contents) is the SUT's contract; this story follows that contract, doesn't invent it. If S5-05's stub SUT hasn't defined the contract yet at the time this story executes, a sensible default is `expected/diff.patch` + `expected/validator_output.json` (the Phase 7 + Phase 6 conventions); document the choice in the case.toml comment block and the README.
- **Mechanical derivation ≠ no review.** Each case is CODEOWNERS-gated under `bench/vuln-remediation/cases/` and must reflect a real solved cassette. Synthesized or fabricated inputs are not acceptable.
- **5 distinct cassettes.** The 5 source cassettes form a set of size 5 (test enforces). Avoid "5 cassettes that all fix the same CVE" — regression coverage is illusory.
- **disposition = positive ≥ 4 of 5; never negative.** RAG-corpus-derived cassettes demonstrate fixes; a `disposition="negative"` (SUT should refuse to fix) is structurally incompatible. If a Phase 4 cassette where the pipeline correctly refused exists, that's S5-04 territory.
- **`difficulty` skews easy.** The cassette tree contains examples the pipeline already solved; honesty requires marking them easy unless a specific cassette captured edge-case behavior worth flagging. At least 4 of 5 must be `difficulty="easy"`.
- **Symlink hygiene.** `input/` and `expected/` are real directories with regular files only. The loader will reject symlinks at load time (S2-02 §AC-9); the story's `test_no_symlinks_anywhere_under_any_rag_case_directory` catches it at the story-test boundary with a path-naming diagnostic.
- **No `input-pointer.toml`.** The pointer escape hatch was rejected per F-CON-2. Commit a minimal extracted pre-fix snapshot under `input/` — only the files the recipe needs to read/touch, not the whole repo. If size becomes a real problem (>>1 MiB), defer the discussion to a follow-on story amending S2-02 to support pointers.
- **digests.yaml signs 5 here; S5-04 appends 5.** The shape is `{case_id: "blake3:<64 hex>"}`, sorted alphabetically by key. When S5-04 ships, the file grows to 10 entries; S5-05 ships the canonical re-sign script (`scripts/sign_bench_digests.py`). For now, sign inline using `_compute_case_dir_digest` + `yaml.safe_dump(data, sort_keys=True)`.
- **F-DP-1 hand-off: promote `_compute_case_dir_digest` to public when the next consumer lands.** This story uses the private name. The next consumer of the canonical algorithm — likely S5-05's `scripts/sign_bench_digests.py` — should be the trigger to extract a public `codegenie.eval.digests.compute_case_dir_digest` (new module). Surface this in the S5-05 / S5-04 implementer's notes when picking up those stories.
- **F-DP-2 hand-off: canary derivation Strategy seam.** When ADR-P4-006 ships and Phase 4 cassettes re-cut with metadata, the canary derivation gains a second path (read-from-metadata). At that point: extract a `CanaryPinSource` sum type (`Path | CassetteMetadata`) and a `derive_canary_pin(source) -> str` smart constructor. For now (one path), Rule 2 says no abstraction.
- **`yaml.safe_load`, `yaml.safe_dump`.** Never `yaml.load`/`yaml.dump` — the `forbidden-patterns` pre-commit hook bans the unsafe variants.
- **Determinism by construction.** Two curators running the same scaffolder against the same source cassette must produce byte-identical `case.toml` + `input/` + `expected/`. `added_at` is set once at curation time; `last_validated_at` is updated only at intentional re-validation. The canonical formulas (AC-3, AC-3a) are deterministic by construction; the curator's job is to not introduce non-determinism (no `datetime.now()` baked into snapshot bytes, no machine-specific paths leaked into snapshots, etc.).
