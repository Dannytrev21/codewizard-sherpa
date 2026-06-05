# Story S5-04 — vuln-remediation 5 held-out hand-curated cases

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-05)
**Effort:** L
**Depends on:** S5-02 HARDENED (rubric scores these end-to-end; rubric reads `harness_output` only — not `expected/`), S5-03 HARDENED (`bench/vuln-remediation/cases/digests.yaml` exists with 5 RAG-corpus-derived entries; this story **appends** 5 held-out entries preserving alphabetical sort by key; the `# Source upstream patch:` comment-block convention is mirrored verbatim), S2-02 HARDENED (`load_cases` is the loader; **the canonical case-dir digest algorithm at S2-02 §AC-3 is the only allowed algorithm for `case_digest`**; the loader requires `(case_dir / "input").is_dir()` per §AC-5; raises on `case.case_id != case_dir.name` per §AC-7; rejects symlinks per §AC-9; raises on missing/extra `digests.yaml` entries per §AC-6b), S1-02 HARDENED (`BenchCase` Pydantic wire-type shapes — `cassette_canary_pin: str` (32 hex), `case_digest: str` (`blake3:<64 hex>`), `disposition: Literal["positive","negative","ambiguous"]`, `difficulty: Literal["easy","medium","hard"]`, `source: Literal["curated","outcome-ledger-derived","regression-converted"]`, `curation_class: Literal["rag-corpus-derived","held-out"]`, `commit_sha: str | None`, tz-aware UTC `added_at`/`last_validated_at`), S2-01 HARDENED (`load_task_class("vuln-remediation", bench_root=...)` resolves the hyphenated package), S5-01 HARDENED (`bench/vuln-remediation/registration.py` registers the task class — `min_cases_for_promotion["silver"] = 25` declared per S5-01; once silver appears, fence-CI #3 requires ≥ 5 held-out)
**ADRs honored:** ADR-0006 (these 5 cases are `curation_class="held-out"`; their existence is the structural precondition for any `min_cases_for_promotion` tier ≥ silver; fence-CI assertion #3 enforces the count; the held-out-CVE selection criterion is "CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff, or older CVEs explicitly excluded from corpus construction (and noted)"), ADR-0005 (`cassette_canary_pin` is 32 hex chars; for held-out cases — which have no prior cassette — the pin is freshly minted via `os.urandom(32).hex()` at curation time per ADR-0005 §Consequences line 44; pin is identity, not content; `case_digest` excludes `case.toml` so pin rotation is a content-neutral edit), Phase 0 ADR-0001 (BLAKE3 hashing chokepoint — for `src/codegenie/**/*.py`; tests under `tests/` and curator scripts under `bench/` / `scripts/` are exempt because they live outside the policed runtime closure)

## Validation notes

Validated: 2026-06-05
Verdict: HARDENED
Findings addressed: 25 total — 6 block, 13 harden, 6 nit
Critic reports: Consistency (10), Coverage (8), Test-Quality (4), Design-Patterns (3). No `NEEDS RESEARCH` — every pattern is precedented in this repo (S5-03 HARDENED's canonical case-dir digest composition, S2-02 HARDENED loader invariants, ADR-0005 §Consequences "os.urandom(32).hex() for net-new pins", S1-02 HARDENED Pydantic wire-types, S5-02 HARDENED rubric-reads-harness_output).

**Conflict resolutions** (priority: Consistency > Coverage > Test-Quality > Design-Patterns):

- **B-EXPECTED-FILENAMES-OVERPRESCRIBED (F-CON-1 — BLOCK).** Consistency wins. The original AC-4 / Implementation outline §3 prescribed `expected/diff.patch` (the actual upstream patch), `expected/validator_output.json` (`{"build_passed": true, "tests_passed": true, "cve_dropped": true}`). S5-02 HARDENED makes clear the rubric reads `harness_output` only, never `expected/`. `expected/` is consumed by the SUT (Phase 6's `VulnRemediationSut.run_case` or S5-05's deterministic-stub SUT). The shape of `expected/` is SUT-contract territory; this story does NOT invent it. AC-2 loosened to "non-empty directory of regular files; filenames follow Phase 6 / S5-05 contract" with a sensible default documented in Notes when neither has shipped.
- **B-INPUT-POINTER-DROPPED (F-CON-2 — BLOCK).** Consistency wins. The original AC-4 / Implementation outline §3 had an `input-pointer.toml` escape hatch ("if pointing to a vendored snapshot under bench/vuln-remediation/snapshots/<cve>/ ... acceptable if the snapshot is large"). S2-02 §AC-5 raises `BenchCaseLoadError(field="input", reason="input/ directory not found")` if `(case_dir / "input").is_dir()` is False; `input-pointer.toml` is a file, not a directory. S5-03 HARDENED's F-CON-2 dropped the same escape hatch. Dropped here too — `input/` MUST be a real, populated directory. If the pre-fix snapshot is genuinely large, the resolution is "commit a minimal extracted snapshot covering only the files the recipe touches" — defer pointer support to a future S2-02-amending story.
- **B-DIGEST-ALGORITHM (F-CON-3 — BLOCK).** Consistency wins decisively. Original §Implementation outline §3 said `case_digest` "BLAKE3 over `input/` + `expected/` (same algorithm as S5-03)". That description is wrong on multiple counts: it walks `input/` + `expected/` separately rather than `case_dir.rglob("*")` once (per S2-02 §AC-3); it does not exclude `case.toml` (per ADR-0005); it is silent on symlink filtering, POSIX-relpath sorting, and `\x1f`/`\x1e` framing. Every byte the prescribed algorithm produces would mismatch the loader's. §Implementation outline §3 now cites S2-02 §AC-3 verbatim and pins `from codegenie.eval.loader import _compute_case_dir_digest` (private helper; promotes to public per F-DP-1 when S5-05 lands).
- **B-COMMIT-SHA-NONE (F-CON-4 — BLOCK).** Consistency wins. Original Implementation outline §3 said `commit_sha may be the pre-fix commit (this is source="curated" so commit_sha is optional, but include it for traceability)`. S5-03 HARDENED pins `commit_sha is None` for `source="curated"`; the upstream CVE-patch SHA lives in the `# Source upstream patch:` comment block at the top of `case.toml`. Two distinct SHAs were conflated. Pinned: `BenchCase.commit_sha is None`; the CVE-upstream-patch SHA + CVE reference URL live in the comment block.
- **B-DIGESTS-YAML-APPEND (F-CON-5 — BLOCK).** Consistency wins. The original story said nothing about appending 5 entries to `bench/vuln-remediation/cases/digests.yaml`. S5-03 created the file with 5 RAG-corpus-derived entries; S5-04 must append 5 held-out entries (sorted alphabetically by key, single merged file). Otherwise S2-02 §AC-6b raises `BenchCaseLoadError(field="digests.yaml", reason="missing entry for case_id ...")` at load time and `load_cases` cannot resolve held-out cases. There is no "stub" path through the HARDENED loader. New AC-6 + AC-6a (3-way consistency) mirror S5-03.
- **B-E2E-DROPPED (F-CON-6 — BLOCK).** Consistency wins. The original AC-7 ("Each case scores end-to-end through `bench/vuln-remediation/rubric.py`") contradicts §Out of scope §2 ("E2E run. S5-05"). S5-02 HARDENED rubric reads `harness_output` (not `expected/`); an "end-to-end" run requires the SUT, which lives in Phase 6 or S5-05's deterministic-stub SUT. The AC was unrealisable in this story's red-green window. Dropped; replaced with the narrower "loader loads all 5 without raising" contract (AC-5).
- **B-HELD-OUT-CVE-CROSS-CHECK (F-TQ-1 — BLOCK).** Test-Quality wins. The original `test_held_out_cve_not_in_rag_corpus` used `pytest.skip(...)` if `RAG_CORPUS_ROOT` doesn't exist. Phase 4 has not yet shipped; the test would always skip; ADR-0006's load-bearing memorization-vs-judgment defense would silently collapse. Replaced with a two-mode contract: **Mode A** (Phase 4 corpus present) → grep-scan; **Mode B** (corpus absent) → require a structured exclusion-manifest at `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` with a non-empty rationale per held-out CVE. When Phase 4 ships and the corpus tree appears, the test auto-promotes from Mode B → Mode A. The manifest is the audit-chain link from a CODEOWNERS-reviewable claim to a structural test. New AC-3b.
- **B-CVE-YEAR-FLOOR (F-TQ-2 — BLOCK).** Test-Quality wins. The original `test_case_ids_carry_cve_identifier` accepts any year via `cve-\d{4}-\d+`. ADR-0006 requires YEAR ≥ Phase 4 corpus cutoff. New AC-2a + test extract `cve-(\d{4})-\d+` per case_id and require `year >= PHASE_4_CORPUS_CUTOFF_YEAR` (module-level `Final[int] = 2025`, documented in Notes). Older CVEs allowed ONLY when case_id carries a `-pre-corpus-` infix AND the exclusion manifest entry contains a `pre_corpus_rationale` field.
- **B-DIGEST-FORMAT-ONLY (F-TQ-3 — BLOCK).** Test-Quality wins. The original `test_held_out_cases_have_blake3_digest_and_pin` checked only `startswith("blake3:") and len == 71`. A curator hand-writing `blake3:` + `"0"*64` passes the test and fails at S2-02 load time with `BenchCaseDigestMismatch`. Surfacing failure at the story-test boundary with a curator-friendly diagnostic is the right discipline. Mirror S5-03's AC-3. Test recomputes via `_compute_case_dir_digest` and asserts byte-equality per case (AC-3).
- **Directory-name canonical regex (F-COV-1 — BLOCK).** Coverage wins. Original AC-1 says "names follow the pattern `00{6..10}-<cve-id>-held-out/`" but provides no machine-checkable regex. Mirror S5-03 AC-1: `r"^(00[6-9]|010)-[a-z0-9][a-z0-9-]*-held-out$"` fullmatch over the 5 names, plus no-other-dir-contains-the-substring guard.
- **Canary-pin canonical contract (F-COV-2 — BLOCK).** Coverage wins. ADR-0005 §Consequences line 44 specifies `os.urandom(32).hex()` as the canonical fresh-mint mechanism for cases with no prior cassette. There is no derivation formula (held-out has no source cassette to derive from). The right contract is therefore: format (32 lowercase hex) + distinctness across the 5 (no copy-paste collisions). New AC-3a.
- **Defense-in-depth invariants (F-COV-5 / F-COV-6 / F-COV-7 / F-COV-8 — HARDEN).** Coverage wins. Mirror S5-03's AC-4 (case_id ↔ dir name bidirectional), AC-7 (disposition/difficulty distribution), AC-10 (symlink-freeness), AC-6a (3-way digest consistency). All four are story-test-level surfacings of invariants S2-02 / S1-02 catch lazily.
- **Total-corpus invariant pinned (F-CON-9 — HARDEN).** Consistency wins. Post-S5-04: corpus has exactly 10 cases (5 RAG-corpus-derived + 5 held-out), sorted ascending by `case_id`. New AC-12 enforces.
- **README mapping table (F-CON-10 — HARDEN).** Mirror S5-03 AC-11 — `bench/vuln-remediation/README.md` `## Case mapping` section with markdown table; ≥ 5 rows with `curation_class = held-out`; selection criterion + corpus-cutoff-date paragraph. New AC-11.
- **disposition / difficulty diversity enforced (F-COV-5 — HARDEN).** Original Notes ("at least 1 negative", "at least 1 hard", "easy + medium + hard mix") promoted to AC-7. Held-out is judgment evidence; distribution diversity is load-bearing. Pinned: ≥1 `negative`, ≥1 (`negative` or `ambiguous`), ≥1 `hard`, ≤3 `easy`.
- **Pin-distinctness across 5 (F-TQ-4 — HARDEN).** Folded into AC-3a — the 5 pins form a set of size 5.
- **tz-aware UTC + commit_sha = None pinned in AC (F-COV-3 / F-COV-4 — HARDEN).** Folded into AC-2.
- **Depends-on + ADRs-honored expanded (F-CON-7 / F-CON-8 — HARDEN).** Names all five HARDENED predecessors + Phase 0 ADR-0001 BLAKE3-chokepoint exemption rationale.
- **`_compute_case_dir_digest` promotion deferred (F-DP-1 — surfaced; NOT promoted to AC).** Rule-of-three threshold: S5-03 + S5-04 + S5-05's `scripts/sign_bench_digests.py` = third consumer triggers extraction to public `codegenie.eval.digests.compute_case_dir_digest`. NOT this story's job. Surfaced in Notes.
- **Canary derivation Strategy seam (F-DP-2 — surfaced).** Two paths today: deterministic-from-cassette-path (S5-03 — RAG-corpus-derived); `os.urandom(32).hex()` (this story — held-out). Two paths < three — Rule 2 says no abstraction. When ADR-P4-006 ships and Phase 4 cassettes re-cut with metadata (third path), extract `CanaryPinSource` sum type. Surfaced.
- **Held-out exclusion manifest is itself an extension point (F-DP-3 — surfaced).** Future task classes (Phase 7 `migration-chainguard-distroless`, Phase 15 `agentic-recipe-authoring`) will need the same "outside-the-RAG-corpus" structural defense. Per-task-class manifest path is the right shape today; cross-task-class kernel `codegenie.eval.held_out_manifest.verify(task_class)` waits for 3 task classes per Rule 2. Surfaced.

Full audit log: `_validation/S5-04-vuln-held-out-cases.md`

## Context

ADR-0006 is unambiguous about why this story is the long pole: hand-curated held-out cases are the **only** evidence base that can distinguish memorization from judgment for `vuln-remediation`. The 5 cases must be drawn from CVEs **outside** Phase 4's RAG corpus (`CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff`, or older CVEs explicitly excluded — and noted in a structured exclusion manifest). Each case requires hand-built ground truth: a pre-fix repo snapshot under `input/`, ground-truth artifacts under `expected/` (SUT-contract-shaped — not invented here), a 32-hex `cassette_canary_pin` freshly minted via `os.urandom(32).hex()` (ADR-0005 §Consequences line 44 — held-out cases have no prior cassette, so the deterministic-derivation path used by S5-03 does not apply), and a BLAKE3 `case_digest` computed via the canonical S2-02 §AC-3 algorithm.

The phase-level schedule risk is acknowledged in `High-level-impl.md §Implementation-level risks #1`: "Hand-curating CVE-fix ground truth ... is slow and easy to underestimate. Signal it's going sideways: Step 5 stretches past one week with < 5 held-out cases written." This story's effort is **L** because curation is real work, not because the contract is complex.

The held-out-vs-RAG-corpus cross-check is the load-bearing memorization-vs-judgment guard. At S5-04 execution time, Phase 4 has not yet shipped (`tests/cassettes/phase4/` does not exist). The story therefore commits to a **two-mode** test discipline: when the corpus tree exists, grep-scan it directly (Mode A); when it does not, require a structured exclusion-manifest at `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` recording the curator's rationale per held-out CVE (Mode B). The manifest is the audit-chain link from a CODEOWNERS-reviewable claim ("this CVE is held out") to a structural test (grep the corpus). When Phase 4 ships, the test auto-promotes Mode B → Mode A.

The story executes against a HARDENED S2-02 loader. The canonical case-dir digest algorithm at S2-02 §AC-3 is the only algorithm allowed for `case_digest`. The rubric (S5-02 HARDENED) reads `harness_output` only — `expected/` is consumed by the SUT (Phase 6 or S5-05's deterministic-stub). The 5 held-out entries land in the **same** `bench/vuln-remediation/cases/digests.yaml` S5-03 created; the merge preserves alphabetical sort by key.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy → Fixture portfolio` — production-fixture half of the 5+5 split.
  - `../phase-arch-design.md §Risks (top 5) #1` — "RAG-corpus-derived cases conflate memorization with judgment" and the held-out floor as the structural remediation.
  - `../phase-arch-design.md §Edge cases #9` — fence-CI counts `c.curation_class == "held-out"` and fails if < 5 when silver is declared.
  - `../phase-arch-design.md §Data model → BenchCase` — required field shapes; `case_digest: str` is `"blake3:<hex>"`; `cassette_canary_pin: str` is 32 hex chars; both `input_path` and `expected_path` are required `Path`.
- **Phase ADRs:**
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision, §Consequences` — held-out selection criterion ("CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff" — Phase 6.5 pins `PHASE_4_CORPUS_CUTOFF_YEAR = 2025` until Phase 4 ships the real cutoff; cases are hand-curated; `source="curated"`).
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Consequences line 44` — held-out / net-new pins use `os.urandom(32).hex()` (non-deterministic at curation, durable forever after); `case_digest` excludes `case.toml` so pin rotation is identity not content.
- **Production ADRs:** `../../../production/adrs/0009-humans-always-merge.md` — the curation discipline is the human-in-the-loop boundary at the bench layer.
- **Sibling HARDENED stories (load-bearing contracts):**
  - `S5-03-vuln-rag-corpus-derived-cases.md` (HARDENED) — the parallel half of the 5+5 split; pattern to mirror for case-dir layout, comment-block shape, digests.yaml append discipline, README mapping table, AC structure.
  - `S5-02-vuln-rubric-and-unit-tests.md` (HARDENED) — **the rubric reads `harness_output`, not `expected/`**; the `expected/` filename shape is SUT-contract territory.
  - `S2-02-loader-cases-and-digests.md §AC-3` — **the canonical case-dir digest algorithm; the only algorithm allowed for `case_digest`**.
  - `S2-02-loader-cases-and-digests.md §AC-5 §AC-6a §AC-6b §AC-7 §AC-9` — input-dir invariant, digests.yaml schema + ↔-filesystem completeness, case_id ↔ dir name, symlink rejection.
- **Source design:** `../High-level-impl.md §Step 5` + `§Implementation-level risks #1`.

## Goal

Curate exactly 5 `BenchCase` directories under `bench/vuln-remediation/cases/` with `curation_class="held-out"`, each from an independent CVE *not* represented in Phase 4's RAG corpus, each carrying hand-built `input/` and `expected/` snapshots, a freshly-minted 32-hex `cassette_canary_pin` (via `os.urandom(32).hex()`), and a BLAKE3 `case_digest` computed via the canonical S2-02 §AC-3 algorithm. The 5 cases are appended to `bench/vuln-remediation/cases/digests.yaml` (the merge preserves alphabetical sort by key). A structured exclusion-manifest at `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` records the curator's rationale per held-out CVE so the memorization-vs-judgment cross-check has audit-chain evidence whether or not the Phase 4 corpus tree has yet shipped. The 5 cases satisfy fence-CI assertion #3 so the bench can declare `silver` in `min_cases_for_promotion`.

## Acceptance criteria

- [ ] **AC-1 (directory naming + count).** `bench/vuln-remediation/cases/` contains exactly 5 directories whose basenames match `re.fullmatch(r"^(00[6-9]|010)-[a-z0-9][a-z0-9-]*-held-out$", name)`. The 5 basenames form a set of size 5. The test enumerates `sorted(p.name for p in (BENCH_ROOT/"vuln-remediation"/"cases").iterdir() if p.is_dir())` — filtering nothing — and asserts (a) the count of names matching the regex equals 5 AND (b) no directory's name contains the substring `-held-out` outside this regex (defense against `005-cve-foo-held-out/` index collision with S5-03's territory or `011-cve-bar-held-out/` getting in early).

- [ ] **AC-2 (each case directory's filesystem shape + BenchCase invariants).** Each of the 5 case directories contains:
  - `case.toml` (regular file, UTF-8) validating into `BenchCase` via `BenchCase.model_validate(tomllib.loads(text))` with: `task_class == "vuln-remediation"`, `curation_class == "held-out"`, `source == "curated"`, `disposition ∈ {"positive", "negative", "ambiguous"}` (the full Literal set is permitted — distribution constraints in AC-7), `difficulty ∈ {"easy", "medium", "hard"}`, `commit_sha is None` (per ADR-0006 §Consequences for `source="curated"`), `added_at.tzinfo` is non-None and equals `timezone.utc` (tz-aware UTC), `last_validated_at` likewise tz-aware UTC, `cassette_canary_pin` is 32 lowercase hex characters (`re.fullmatch(r"^[0-9a-f]{32}$", pin)`), `case_digest` matches `re.fullmatch(r"^blake3:[0-9a-f]{64}$", value)`, `input_path` resolves to the string `"input"` (relative POSIX), `expected_path` resolves to the string `"expected"` (relative POSIX), `cassette_path is None`.
  - `input/` is a real directory (`(case_dir / "input").is_dir() and not (case_dir / "input").is_symlink()`), is non-empty, and contains the pre-fix snapshot of the file(s) the recipe touches (minimal — not the full repo; F-CON-2 dropped the pointer escape hatch).
  - `expected/` is a real directory (`(case_dir / "expected").is_dir() and not (case_dir / "expected").is_symlink()`), is non-empty, and contains the ground-truth artifacts the **SUT** consults at run time. Filenames follow the SUT contract (Phase 6's `VulnRemediationSut` or S5-05's deterministic-stub SUT); this story does NOT invent the contract. When neither has shipped at the time of execution, follow the Phase 7 + Phase 6 conventions documented in Notes-for-implementer; document the choice in the case.toml comment block.
  - **No `input-pointer.toml` file exists at the case_dir root** (F-CON-2 backstop).
  - **No file or directory anywhere under `case_dir.rglob("*")` is a symlink** (defense-in-depth on S2-02 §AC-9).

- [ ] **AC-2a (CVE identifier + year ≥ Phase 4 corpus cutoff).** Each `case_id` carries a CVE identifier matching `re.search(r"cve-(\d{4})-\d+", case_id, re.IGNORECASE)`. The extracted year MUST satisfy `year >= PHASE_4_CORPUS_CUTOFF_YEAR` (`Final[int] = 2025`, documented in Notes) UNLESS the case_id carries a `-pre-corpus-` infix marker AND the exclusion manifest entry for that case_id contains a non-empty `pre_corpus_rationale: str` field documenting why this older CVE was explicitly excluded from Phase 4 corpus construction. The 5 CVE identifiers (lower-cased) form a set of size 5 (distinct CVEs).

- [ ] **AC-3 (case_digest = canonical S2-02 §AC-3 algorithm; no inline reimplementation).** Each case.toml's `case_digest` field equals the canonical algorithm S2-02 §AC-3 prescribes:
  - (a) `paths = sorted(p for p in case_dir.rglob("*") if p.is_file() and not p.is_symlink() and p.name not in {"case.toml"}, key=lambda p: p.relative_to(case_dir).as_posix())`.
  - (b) `records = [f"{p.relative_to(case_dir).as_posix()}\x1f{content_hash(p)}".encode("utf-8") for p in paths]` where `content_hash` is `codegenie.hashing.content_hash` (Phase 0 per-file content BLAKE3).
  - (c) `case_digest = "blake3:" + blake3(b"\x1e".join(records)).hexdigest()`.
  The integration test imports `_compute_case_dir_digest` from `codegenie.eval.loader` and asserts byte-equality with `case.toml#case_digest` per case. The story does NOT inline a re-implementation. (Per F-DP-1, when S5-05's `scripts/sign_bench_digests.py` lands the helper graduates to public `codegenie.eval.digests.compute_case_dir_digest` and this test's import switches in one line.)

- [ ] **AC-3a (`cassette_canary_pin` format + distinctness).** Each case.toml's `cassette_canary_pin` matches `re.fullmatch(r"^[0-9a-f]{32}$", pin)` (32 lowercase hex; per ADR-0005). The set `{c.cassette_canary_pin for c in held_out_cases}` has cardinality 5 (no copy-paste collisions across the 5 cases). Held-out cases have no source cassette to derive a deterministic formula from; per ADR-0005 §Consequences line 44 the canonical fresh-mint mechanism is `os.urandom(32).hex()`. Two curators of the same CVE produce different pins; either pin is durable for the lifetime of the case.

- [ ] **AC-3b (held-out-vs-RAG-corpus cross-check; auto-mode).** The integration test `test_held_out_cves_outside_rag_corpus` selects mode at runtime — it **never** uses `pytest.skip` for the load-bearing cross-check:
  - **Mode A** (when `tests/cassettes/phase4/` exists): grep-scan every regular file under the tree (utf-8, errors="ignore") for each held-out CVE id (lower-cased). On any hit, fail with a diagnostic naming the held-out case_id, the CVE, and the source-cassette path.
  - **Mode B** (when `tests/cassettes/phase4/` does NOT exist): require `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` to exist and parse as a mapping; require an entry per held-out case_id with the schema `{case_id: {cve_id: "<CVE-YYYY-NNNN>", rationale: "<≥1 non-whitespace char>", pre_corpus_rationale: "<optional, non-empty iff case_id has -pre-corpus- infix>"}}`. Any missing/extra entries or empty `rationale` field fails with a curator-friendly diagnostic. The test thus surfaces the held-out claim at PR time even before Phase 4 lands; when Phase 4 ships, the test auto-promotes Mode B → Mode A without code edit.

- [ ] **AC-4 (case_id ↔ directory-name + curation_class ↔ directory-name-suffix invariants; case_id distinctness).** For each of the 5 case directories `case_dir`: `BenchCase.case_id == case_dir.name` (byte-equality, story-test–level defense-in-depth on S2-02 §AC-7). Additionally, `case_dir.name.endswith("-held-out")` ⇔ `BenchCase.curation_class == "held-out"`. The set `{c.case_id for c in held_out_cases}` has cardinality 5.

- [ ] **AC-5 (`loader.load_cases` succeeds; returns exactly 5 held-out cases when filtered).** `load_cases(load_task_class("vuln-remediation", bench_root=BENCH_ROOT))` returns a `tuple[BenchCase, ...]` without raising; the 5 cases whose `curation_class == "held-out"` are present. All 5 have `source == "curated"`, `task_class == "vuln-remediation"`, `commit_sha is None`. Returned tuple is sorted ascending by `case_id` (S2-02 §AC-2 invariant; story-test-level confirmation).

- [ ] **AC-6 (`bench/vuln-remediation/cases/digests.yaml` signs all 5 held-out canonically; append-and-resort).** The file already exists (S5-03 created it with 5 RAG-corpus-derived entries). This story APPENDS 5 held-out entries — merging the existing dict with the held-out digests, dumping via `yaml.safe_dump(data, sort_keys=True)` so the result is sorted alphabetically by key. For each held-out case_id, the file contains `{case_id: "blake3:<64 hex>"}` matching `re.fullmatch(r"^blake3:[0-9a-f]{64}$", value)`. The S5-03 RAG-corpus-derived entries are preserved byte-for-byte (the test reads digests.yaml before and after — see Implementation outline §5 for the merge logic).

- [ ] **AC-6a (3-way digest consistency for held-out 5).** For each of the 5 held-out cases: `case.toml#case_digest == digests.yaml[case_id] == _compute_case_dir_digest(case_dir)` (all three byte-equal). The integration test asserts this triple-equality per case. Catches the curator forgetting to update one of the three after a re-sign.

- [ ] **AC-7 (disposition + difficulty distribution — judgment evidence floor).** Held-out is judgment evidence; distribution diversity is load-bearing:
  - At least 1 of 5 has `disposition == "negative"` (a CVE the SUT should *refuse* to "fix" because the proposed patch is wrong / reverted upstream / introduces a regression; highest-signal judgment evidence).
  - At least 1 of 5 has `disposition ∈ {"negative", "ambiguous"}` (covered by the negative requirement above; explicit for clarity).
  - At least 1 of 5 has `difficulty == "hard"` (multi-file or cross-cutting CVE patch; exercises cross-cutting reasoning).
  - At most 3 of 5 have `difficulty == "easy"` (skew away from easy-only; held-out is judgment-not-regression).
  Test produces a diagnostic listing the (case_id, disposition, difficulty) triples on any failure.

- [ ] **AC-8 (source-CVE traceability: comment block + exclusion-manifest entry).** Each `case.toml` contains a comment block at the top with the literal lines (or equivalent, same content):
  ```
  # curation_class per ADR-0006
  # CVE: <CVE-YYYY-NNNN>
  # CVE reference: <public URL, e.g., https://nvd.nist.gov/vuln/detail/CVE-YYYY-NNNN>
  # Source upstream patch: <40-char lowercase hex SHA>
  ```
  The integration test parses each `case.toml` text and extracts each line via regex. For each extracted CVE: it appears in the exclusion-manifest's entry for this case_id (Mode B) or grep-scanning the corpus for it fails to find a match (Mode A). For each extracted upstream-patch SHA: matches `re.fullmatch(r"^[0-9a-f]{40}$", sha)`. The set of 5 CVE identifiers (lower-cased) has cardinality 5.

- [ ] **AC-9 (curation-class-held-out set ↔ directory-name set).** `{p.name for p in cases_root.iterdir() if p.is_dir() and p.name.endswith("-held-out")} == {c.case_id for c in loaded_cases if c.curation_class == "held-out"}` (set equality). Catches a case mistagged `curation_class="rag-corpus-derived"` in a `*-held-out/` directory and vice-versa.

- [ ] **AC-10 (symlink-freeness — story-level defense-in-depth on S2-02 §AC-9).** For each of the 5 held-out case directories, walking `rglob("*")` yields zero symlinks. Test produces a diagnostic naming the offending case_id and relpath if any symlink is found.

- [ ] **AC-11 (README mapping table — held-out half).** `bench/vuln-remediation/README.md` contains a `## Case mapping` section (or extends the one S5-03 created) with a markdown table whose header row is `| case_id | CVE | CVE reference | upstream patch SHA | curation class |` (column count = 5, columns 2+3 carry CVE id + reference URL, column 4 carries the 40-hex SHA). The table contains at least 5 rows with `curation class` cell = `held-out`. The README also documents the `PHASE_4_CORPUS_CUTOFF_YEAR` value and the exclusion-manifest mechanism (Mode B). The integration test extracts the markdown table, asserts row count ≥ 5 with `held-out`, and asserts the case_id column matches the 5 case directory basenames.

- [ ] **AC-12 (total corpus shape after this story).** After this story merges:
  - The corpus has exactly 10 cases (S5-03's 5 RAG-corpus-derived + S5-04's 5 held-out).
  - Held-out count is exactly 5; RAG-corpus-derived count is exactly 5.
  - `digests.yaml` has exactly 10 entries; the 5 from S5-03 are byte-preserved.
  - Fence-CI assertion #3 passes when `min_cases_for_promotion["silver"] = 25` is declared in S5-01's `registration.py` (per S5-01 HARDENED): the held-out count of 5 meets the ≥ 5 floor. A synthetic-removal test moves one held-out directory aside in a `tmp_path` clone and asserts fence-CI fails with a diagnostic naming `vuln-remediation` and the count `4` (defense the fence is actually enforcing).

- [ ] **AC-13 (lint + typecheck + red→green).** Red tests from §TDD plan (`tests/integration/test_vuln_held_out_cases_load.py`) exist, were committed at red, now green. `ruff check tests/integration/test_vuln_held_out_cases_load.py bench/vuln-remediation/`, `ruff format --check tests/integration/test_vuln_held_out_cases_load.py`, `mypy --strict tests/integration/test_vuln_held_out_cases_load.py`, and `pytest tests/integration/test_vuln_held_out_cases_load.py -v` all green. `make fence` continues to pass — no new closure imports introduced under `src/codegenie/`.

## Implementation outline

1. **Write the red tests** `tests/integration/test_vuln_held_out_cases_load.py` first — see §TDD plan. Commit as the red marker; the test should fail with `BenchCaseLoadError` (digests.yaml missing held-out entries) or empty-held-out-directories.

2. **Identify 5 CVEs** outside Phase 4's RAG corpus. Curator selection:
   - Source candidates from public CVE feeds (NVD / GHSA) where YEAR ≥ `PHASE_4_CORPUS_CUTOFF_YEAR = 2025`.
   - Prefer CVEs with public, well-documented patches (Apache, CPython, popular libs).
   - Mix of language ecosystems (e.g., 2 Python, 2 Java, 1 Node) to avoid single-language bias.
   - Distribution constraints (AC-7): at least 1 with `disposition="negative"` (e.g., a known-bad / reverted upstream patch — the SUT should refuse); at least 1 with `difficulty="hard"`; at most 3 with `difficulty="easy"`.
   - Record each chosen CVE id + reference URL + upstream-patch 40-hex SHA — these go into both the `case.toml` comment block AND the exclusion manifest.

3. **For each CVE, hand-build the case directory** under `bench/vuln-remediation/cases/00N-<cve-slug>-held-out/` (N ∈ {6..10}; `<cve-slug>` is `cve-YYYY-NNNN` lowercased):
   - **case.toml** with:
     - The canonical 4-line comment block at the top (per AC-8).
     - All required `BenchCase` fields per AC-2. `commit_sha` is `None` (omit the key — `commit_sha: str | None` defaults to `None`).
     - `input_path = "input"`, `expected_path = "expected"`.
     - `cassette_canary_pin = os.urandom(32).hex()` (one-time mint; durable forever; ADR-0005 §Consequences line 44).
     - `case_digest` computed via `_compute_case_dir_digest(case_dir)` **after** populating `input/` and `expected/` — the digest pins content, so compute it last.
   - **input/** populated with the pre-fix snapshot of the file(s) the recipe touches — minimal extracted snapshot (NOT the full repo). Files must be regular files (no symlinks). Non-empty.
   - **expected/** populated with the SUT-contract-shaped ground-truth artifacts. When Phase 6 / S5-05 has not yet defined the contract, follow the Phase 7 + Phase 6 conventions: `expected/diff.patch` (the upstream patch as ground truth) + `expected/validator_output.json` (placeholder SUT-output JSON — note in the case.toml comment block that this follows S5-05 contract when shipped). Files must be regular files. Non-empty.

4. **Write the exclusion-manifest** at `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml`:
   ```yaml
   # held-out CVE exclusion manifest — ADR-0006 §Decision; AC-3b Mode B
   # When Phase 4 ships and tests/cassettes/phase4/ appears, AC-3b auto-promotes to Mode A.
   006-cve-YYYY-NNNN-held-out:
     cve_id: CVE-YYYY-NNNN
     rationale: |
       Phase 4 RAG corpus is built from CVEs disclosed before 2025-04 (PHASE_4_CORPUS_CUTOFF_YEAR=2025).
       CVE-YYYY-NNNN (disclosed 2025-MM-DD) is therefore outside the corpus by construction.
   # ... 4 more entries
   ```
   For any case_id carrying the `-pre-corpus-` infix marker, the entry includes a `pre_corpus_rationale: str` field (per AC-2a). CODEOWNERS reviews the manifest at PR time; the test surfaces missing/empty rationale entries.

5. **Append the 5 held-out digests to `bench/vuln-remediation/cases/digests.yaml`** preserving alphabetical sort by key:
   ```python
   from codegenie.eval.loader import _compute_case_dir_digest
   import yaml, pathlib
   cases_root = pathlib.Path("bench/vuln-remediation/cases")
   held_out_dirs = sorted(p for p in cases_root.iterdir() if p.is_dir() and p.name.endswith("-held-out"))
   held_out_digests = {p.name: _compute_case_dir_digest(p) for p in held_out_dirs}
   existing = yaml.safe_load((cases_root / "digests.yaml").read_text()) or {}
   merged = {**existing, **held_out_digests}  # S5-03 entries preserved; S5-04 entries added
   (cases_root / "digests.yaml").write_text(yaml.safe_dump(merged, sort_keys=True))
   ```
   Verify parity per AC-6a: `case.toml#case_digest == digests.yaml[case_id] == _compute_case_dir_digest(case_dir)`.

6. **Update `bench/vuln-remediation/README.md`** per AC-11: extend the `## Case mapping` section with 5 held-out rows; add a `### Held-out selection criterion` paragraph naming `PHASE_4_CORPUS_CUTOFF_YEAR` and the exclusion-manifest mechanism.

7. **Iterate test → green.** Each failure points at a specific case_id and field (typed errors); fix per-case issues until all 13 ACs are green.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/integration/test_vuln_held_out_cases_load.py`

```python
# tests/integration/test_vuln_held_out_cases_load.py
"""5 held-out cases must exist, be distinct CVEs at YEAR >= PHASE_4_CORPUS_CUTOFF_YEAR,
be outside Phase 4's RAG corpus (auto Mode A/B), satisfy fence-CI assertion #3, and
load via codegenie.eval.loader. ADR-0006 §Decision is the load-bearing contract;
ADR-0005 §Consequences line 44 governs the canary-pin discipline.

Every test is concrete and mutation-resistant: digest re-computation via the canonical
S2-02 §AC-3 algorithm, year-floor enforcement, set-equality on directory-naming ↔
curation-class, source-CVE traceability against an exclusion manifest, disposition/
difficulty distribution caps. The held-out cross-check NEVER uses pytest.skip — it
selects Mode A (Phase 4 corpus present) or Mode B (exclusion manifest required) at
runtime so the load-bearing memorization-vs-judgment guard always has bite.
"""

from __future__ import annotations

import re
import tomllib
from datetime import timezone
from pathlib import Path
from typing import Final

import pytest
import yaml

from codegenie.eval.loader import (
    _compute_case_dir_digest,  # canonical S2-02 §AC-3 algorithm; private until F-DP-1 promotes
    load_cases,
    load_task_class,
)
from codegenie.eval.models import BenchCase

REPO_ROOT: Final[Path] = Path(__file__).parents[2]
BENCH_ROOT: Final[Path] = REPO_ROOT / "bench"
CASES_ROOT: Final[Path] = BENCH_ROOT / "vuln-remediation" / "cases"
RAG_CORPUS_ROOT: Final[Path] = REPO_ROOT / "tests" / "cassettes" / "phase4"
EXCLUSION_MANIFEST: Final[Path] = CASES_ROOT / "held-out-cve-exclusion-manifest.yaml"

PHASE_4_CORPUS_CUTOFF_YEAR: Final[int] = 2025

HELD_OUT_NAME_RE = re.compile(r"^(00[6-9]|010)-[a-z0-9][a-z0-9-]*-held-out$")
CVE_RE = re.compile(r"cve-(\d{4})-(\d+)", re.IGNORECASE)
PRE_CORPUS_MARKER = "-pre-corpus-"
BLAKE3_DIGEST_RE = re.compile(r"^blake3:[0-9a-f]{64}$")
HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")

CVE_LINE_RE = re.compile(r"^# CVE: (CVE-\d{4}-\d+)$", re.MULTILINE)
CVE_REF_LINE_RE = re.compile(r"^# CVE reference: (https?://\S+)$", re.MULTILINE)
PATCH_SHA_LINE_RE = re.compile(r"^# Source upstream patch: ([0-9a-f]{40})$", re.MULTILINE)


def _load_held_out_cases() -> tuple[BenchCase, ...]:
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    return tuple(c for c in load_cases(tc) if c.curation_class == "held-out")


def _list_held_out_dirs() -> list[Path]:
    return sorted(p for p in CASES_ROOT.iterdir() if p.is_dir() and p.name.endswith("-held-out"))


def _read_case_toml_text(case_dir: Path) -> str:
    return (case_dir / "case.toml").read_text(encoding="utf-8")


# --- AC-1: directory naming + count ----------------------------------------

def test_exactly_five_held_out_directories_with_canonical_names():
    held_out_dirs = _list_held_out_dirs()
    assert len(held_out_dirs) == 5, (
        f"expected 5 held-out dirs, found {len(held_out_dirs)}: {[p.name for p in held_out_dirs]}"
    )
    for p in held_out_dirs:
        assert HELD_OUT_NAME_RE.fullmatch(p.name), f"{p.name!r} does not match the canonical regex"
    all_dirs = [p.name for p in CASES_ROOT.iterdir() if p.is_dir()]
    intruders = [n for n in all_dirs if "-held-out" in n and not HELD_OUT_NAME_RE.fullmatch(n)]
    assert intruders == [], f"directory(ies) with -held-out suffix outside 006-010: {intruders}"


# --- AC-2: per-case filesystem shape + BenchCase field invariants -----------

@pytest.mark.parametrize("idx", range(5), ids=lambda i: f"case-{i+6}")
def test_each_held_out_case_directory_shape_and_bench_case_invariants(idx):
    held_out_dirs = _list_held_out_dirs()
    if len(held_out_dirs) <= idx:
        pytest.fail(f"only {len(held_out_dirs)} held-out dirs; case index {idx} missing")
    case_dir = held_out_dirs[idx]
    case_toml = case_dir / "case.toml"
    assert case_toml.is_file() and not case_toml.is_symlink()
    parsed = tomllib.loads(_read_case_toml_text(case_dir))
    bc = BenchCase.model_validate(parsed)
    assert bc.task_class == "vuln-remediation"
    assert bc.curation_class == "held-out"
    assert bc.source == "curated"
    assert bc.disposition in {"positive", "negative", "ambiguous"}
    assert bc.difficulty in {"easy", "medium", "hard"}
    assert bc.commit_sha is None, f"{bc.case_id}: commit_sha must be None for source=curated"
    assert bc.added_at.tzinfo is not None and bc.added_at.utcoffset() == timezone.utc.utcoffset(None)
    assert bc.last_validated_at.tzinfo is not None and bc.last_validated_at.utcoffset() == timezone.utc.utcoffset(None)
    assert HEX32_RE.fullmatch(bc.cassette_canary_pin), f"{bc.case_id}: cassette_canary_pin not 32 lowercase hex"
    assert BLAKE3_DIGEST_RE.fullmatch(bc.case_digest), f"{bc.case_id}: case_digest not blake3:<64 hex>"
    assert str(bc.input_path) == "input"
    assert str(bc.expected_path) == "expected"
    assert bc.cassette_path is None
    assert (case_dir / "input").is_dir() and not (case_dir / "input").is_symlink()
    assert (case_dir / "expected").is_dir() and not (case_dir / "expected").is_symlink()
    assert any((case_dir / "input").iterdir()), f"{bc.case_id}: input/ empty"
    assert any((case_dir / "expected").iterdir()), f"{bc.case_id}: expected/ empty"
    assert not (case_dir / "input-pointer.toml").exists(), f"{bc.case_id}: input-pointer.toml forbidden (F-CON-2)"


# --- AC-2a: CVE identifier + year ≥ PHASE_4_CORPUS_CUTOFF_YEAR --------------

def _load_exclusion_manifest() -> dict[str, dict[str, str]]:
    if not EXCLUSION_MANIFEST.is_file():
        return {}
    raw = yaml.safe_load(EXCLUSION_MANIFEST.read_text()) or {}
    assert isinstance(raw, dict), "exclusion manifest root must be a mapping"
    return raw


def test_cve_year_floor_and_distinctness():
    cases = _load_held_out_cases()
    assert len(cases) == 5
    manifest = _load_exclusion_manifest()
    seen_cves: set[str] = set()
    for c in cases:
        m = CVE_RE.search(c.case_id)
        assert m, f"{c.case_id}: no CVE identifier in case_id"
        year = int(m.group(1))
        cve_lower = m.group(0).lower()
        assert cve_lower not in seen_cves, f"duplicate CVE {cve_lower} across held-out cases"
        seen_cves.add(cve_lower)
        if year < PHASE_4_CORPUS_CUTOFF_YEAR:
            assert PRE_CORPUS_MARKER in c.case_id, (
                f"{c.case_id}: CVE year {year} < cutoff {PHASE_4_CORPUS_CUTOFF_YEAR} "
                f"but case_id missing -pre-corpus- marker"
            )
            entry = manifest.get(c.case_id, {})
            assert entry.get("pre_corpus_rationale", "").strip(), (
                f"{c.case_id}: pre-corpus CVE requires non-empty pre_corpus_rationale in manifest"
            )
    assert len(seen_cves) == 5


# --- AC-3: case_digest = canonical S2-02 §AC-3 algorithm -------------------

@pytest.mark.parametrize("idx", range(5), ids=lambda i: f"case-{i+6}")
def test_held_out_case_digest_matches_canonical_algorithm(idx):
    held_out_dirs = _list_held_out_dirs()
    if len(held_out_dirs) <= idx:
        pytest.fail(f"only {len(held_out_dirs)} held-out dirs")
    case_dir = held_out_dirs[idx]
    declared = tomllib.loads(_read_case_toml_text(case_dir))["case_digest"]
    canonical = _compute_case_dir_digest(case_dir)
    assert declared == canonical, (
        f"{case_dir.name}: case.toml#case_digest={declared!r} != canonical {canonical!r}. "
        f"Curator wrote the wrong algorithm or forgot to re-sign after editing input/ or expected/."
    )


# --- AC-3a: canary pin format + distinctness -------------------------------

def test_canary_pins_are_format_correct_and_distinct():
    cases = _load_held_out_cases()
    pins = [c.cassette_canary_pin for c in cases]
    for pin in pins:
        assert HEX32_RE.fullmatch(pin), f"pin {pin!r} not 32 lowercase hex"
    assert len(set(pins)) == 5, (
        f"the 5 held-out canary pins must be distinct (per-case determinism contract); "
        f"got {len(set(pins))} distinct from {pins}"
    )


# --- AC-3b: held-out CVEs outside RAG corpus (Mode A or Mode B; never skip) -

def test_held_out_cves_outside_rag_corpus():
    cases = _load_held_out_cases()
    held_out_cves = {CVE_RE.search(c.case_id).group(0).lower() for c in cases}
    if RAG_CORPUS_ROOT.exists() and any(RAG_CORPUS_ROOT.iterdir()):
        # Mode A — grep-scan the corpus.
        corpus_text = "\n".join(
            p.read_text(encoding="utf-8", errors="ignore")
            for p in RAG_CORPUS_ROOT.rglob("*")
            if p.is_file()
        ).lower()
        for cve in held_out_cves:
            assert cve not in corpus_text, (
                f"{cve} appears in Phase 4 RAG corpus tests/cassettes/phase4/ — "
                f"violates ADR-0006 held-out contract (memorization-vs-judgment guard)"
            )
    else:
        # Mode B — require structured exclusion manifest with per-case rationale.
        assert EXCLUSION_MANIFEST.is_file(), (
            f"Phase 4 corpus absent — AC-3b Mode B requires {EXCLUSION_MANIFEST.relative_to(REPO_ROOT)} "
            f"with a rationale per held-out case_id. See ADR-0006 §Decision."
        )
        manifest = _load_exclusion_manifest()
        for c in cases:
            entry = manifest.get(c.case_id)
            assert entry is not None, f"manifest missing entry for held-out case {c.case_id}"
            assert isinstance(entry, dict), f"manifest entry for {c.case_id} must be a mapping"
            rationale = entry.get("rationale", "")
            assert isinstance(rationale, str) and rationale.strip(), (
                f"manifest entry for {c.case_id} missing or empty 'rationale' (held-out claim is unevidenced)"
            )
            cve_id = entry.get("cve_id", "")
            assert isinstance(cve_id, str) and re.fullmatch(r"CVE-\d{4}-\d+", cve_id), (
                f"manifest entry for {c.case_id} missing or malformed 'cve_id' (need CVE-YYYY-NNNN)"
            )


# --- AC-4: case_id ↔ directory-name + curation_class ↔ suffix + distinctness

def test_case_id_equals_directory_name_and_curation_class_matches_suffix():
    cases = _load_held_out_cases()
    assert len(cases) == 5
    case_ids = [c.case_id for c in cases]
    assert len(set(case_ids)) == 5, f"duplicate case_ids: {case_ids}"
    for c in cases:
        case_dir = CASES_ROOT / c.case_id
        assert case_dir.is_dir(), f"case_id {c.case_id!r} has no matching directory"
        parsed = tomllib.loads(_read_case_toml_text(case_dir))
        assert parsed["case_id"] == case_dir.name, (
            f"{case_dir.name}: case.toml#case_id={parsed['case_id']!r} != directory name"
        )
        assert c.case_id.endswith("-held-out")


# --- AC-5: loader returns exactly 5 held-out cases --------------------------

def test_loader_returns_exactly_five_held_out_with_curated_source():
    cases = _load_held_out_cases()
    assert len(cases) == 5
    for c in cases:
        assert c.source == "curated"
        assert c.task_class == "vuln-remediation"
        assert c.commit_sha is None
    # Sorted ascending by case_id:
    assert list(cases) == sorted(cases, key=lambda c: c.case_id)


# --- AC-6 / AC-6a: digests.yaml signs all held-out canonically; S5-03 preserved

def test_digests_yaml_signs_five_held_out_canonically_and_preserves_rag():
    digests_path = CASES_ROOT / "digests.yaml"
    assert digests_path.is_file()
    parsed = yaml.safe_load(digests_path.read_text())
    assert isinstance(parsed, dict)
    # Held-out entries:
    held_out_case_ids = {c.case_id for c in _load_held_out_cases()}
    for case_id in held_out_case_ids:
        assert case_id in parsed, f"digests.yaml missing entry for {case_id}"
        value = parsed[case_id]
        assert isinstance(value, str) and BLAKE3_DIGEST_RE.fullmatch(value)
        canonical = _compute_case_dir_digest(CASES_ROOT / case_id)
        assert value == canonical, f"digests.yaml[{case_id}] != canonical"
    # S5-03 entries preserved:
    rag_dirs = [p for p in CASES_ROOT.iterdir() if p.is_dir() and p.name.endswith("-rag-corpus-derived")]
    for p in rag_dirs:
        assert p.name in parsed, f"S5-03's entry for {p.name} was dropped from digests.yaml"
        assert parsed[p.name] == _compute_case_dir_digest(p), (
            f"S5-03's {p.name} digest was rewritten — append-and-merge corrupted RAG entries"
        )


def test_case_toml_and_digests_yaml_and_canonical_three_way_consistency():
    digests_yaml = yaml.safe_load((CASES_ROOT / "digests.yaml").read_text())
    for c in _load_held_out_cases():
        case_dir = CASES_ROOT / c.case_id
        ct = tomllib.loads(_read_case_toml_text(case_dir))["case_digest"]
        dy = digests_yaml[c.case_id]
        ca = _compute_case_dir_digest(case_dir)
        assert ct == dy == ca, (
            f"{c.case_id}: 3-way digest divergence — case.toml={ct!r}, digests.yaml={dy!r}, canonical={ca!r}"
        )


# --- AC-7: disposition + difficulty distribution ---------------------------

def test_held_out_disposition_and_difficulty_distribution():
    cases = _load_held_out_cases()
    dispositions = [c.disposition for c in cases]
    difficulties = [c.difficulty for c in cases]
    negative_count = dispositions.count("negative")
    nonpositive_count = sum(1 for d in dispositions if d in {"negative", "ambiguous"})
    hard_count = difficulties.count("hard")
    easy_count = difficulties.count("easy")
    triples = [(c.case_id, c.disposition, c.difficulty) for c in cases]
    assert negative_count >= 1, (
        f"held-out must include ≥1 disposition=negative (judgment evidence); got {dispositions}; triples={triples}"
    )
    assert nonpositive_count >= 1  # implied; explicit for diagnostic clarity
    assert hard_count >= 1, f"held-out must include ≥1 difficulty=hard; got {difficulties}; triples={triples}"
    assert easy_count <= 3, f"held-out skews away from easy; ≤3 easy; got {easy_count}; triples={triples}"


# --- AC-8: source-CVE traceability + exclusion-manifest cross-reference -----

def test_each_held_out_case_documents_cve_reference_and_upstream_patch_sha():
    cases = _load_held_out_cases()
    cve_ids: list[str] = []
    for c in cases:
        text = _read_case_toml_text(CASES_ROOT / c.case_id)
        cve_m = CVE_LINE_RE.search(text)
        ref_m = CVE_REF_LINE_RE.search(text)
        sha_m = PATCH_SHA_LINE_RE.search(text)
        assert cve_m, f"{c.case_id}: case.toml missing `# CVE: CVE-YYYY-NNNN` line"
        assert ref_m, f"{c.case_id}: case.toml missing `# CVE reference: <URL>` line"
        assert sha_m, f"{c.case_id}: case.toml missing `# Source upstream patch: <40 hex>` line"
        assert HEX40_RE.fullmatch(sha_m.group(1))
        cve_ids.append(cve_m.group(1).lower())
    assert len(set(cve_ids)) == 5, f"5 CVE ids must be distinct; got {cve_ids}"


# --- AC-9: curation_class set ↔ directory-name set --------------------------

def test_directory_suffix_set_equals_curation_class_held_out_set():
    suffix_set = {p.name for p in CASES_ROOT.iterdir() if p.is_dir() and p.name.endswith("-held-out")}
    class_set = {c.case_id for c in _load_held_out_cases()}
    assert suffix_set == class_set


# --- AC-10: symlink-freeness defense-in-depth -------------------------------

def test_no_symlinks_anywhere_under_any_held_out_case_directory():
    for case_dir in _list_held_out_dirs():
        symlinks = [p for p in case_dir.rglob("*") if p.is_symlink()]
        assert symlinks == [], (
            f"{case_dir.name}: forbidden symlinks at "
            f"{[p.relative_to(case_dir).as_posix() for p in symlinks]}"
        )


# --- AC-11: README mapping table — held-out half ----------------------------

def test_readme_documents_case_mapping_table_with_at_least_five_held_out_rows():
    readme_path = BENCH_ROOT / "vuln-remediation" / "README.md"
    assert readme_path.is_file()
    text = readme_path.read_text(encoding="utf-8")
    section_match = re.search(r"##\s+Case mapping\b.*?(?=^##\s|\Z)", text, re.DOTALL | re.MULTILINE)
    assert section_match, "README missing `## Case mapping` section"
    section = section_match.group(0)
    held_out_rows = [
        line for line in section.splitlines()
        if line.strip().startswith("|") and "held-out" in line and "---" not in line
    ]
    assert len(held_out_rows) >= 5, f"Case mapping table has {len(held_out_rows)} held-out rows; expected ≥ 5"
    held_out_case_ids = {c.case_id for c in _load_held_out_cases()}
    for case_id in held_out_case_ids:
        assert any(case_id in row for row in held_out_rows), f"README missing row for {case_id}"
    # PHASE_4_CORPUS_CUTOFF_YEAR documented:
    assert str(PHASE_4_CORPUS_CUTOFF_YEAR) in text, "README must document PHASE_4_CORPUS_CUTOFF_YEAR"


# --- AC-12: total corpus shape after this story -----------------------------

def test_corpus_has_exactly_ten_cases_after_s5_04():
    tc = load_task_class("vuln-remediation", bench_root=BENCH_ROOT)
    all_cases = load_cases(tc)
    rag = [c for c in all_cases if c.curation_class == "rag-corpus-derived"]
    held = [c for c in all_cases if c.curation_class == "held-out"]
    assert len(all_cases) == 10, f"expected 10 cases after S5-04; got {len(all_cases)}"
    assert len(rag) == 5, f"expected 5 RAG-corpus-derived; got {len(rag)}"
    assert len(held) == 5, f"expected 5 held-out; got {len(held)}"
    digests = yaml.safe_load((CASES_ROOT / "digests.yaml").read_text())
    assert len(digests) == 10, f"expected 10 digests.yaml entries; got {len(digests)}"


# --- AC-12 (fence #3 enforcement) -- moved-out clone of one held-out case ---

def test_fence_ci_assertion_three_fires_when_one_held_out_removed(tmp_path):
    """Pin that fence-CI's held-out floor is actually enforcing. Copy the bench tree
    to tmp_path, remove one held-out directory + its digests.yaml entry + its
    manifest entry, run the fence-CI assertion, expect a diagnostic naming
    'vuln-remediation' and the count 4."""
    # Skeleton — implementer wires the real fence-CI invocation per S7-01.
    pytest.importorskip("codegenie.eval.fence")  # may not yet exist; S7-01 ships it
    from codegenie.eval.fence import assert_held_out_floor  # type: ignore[attr-defined]
    import shutil
    shutil.copytree(BENCH_ROOT, tmp_path / "bench")
    cloned = tmp_path / "bench" / "vuln-remediation" / "cases"
    held_dirs = sorted(p for p in cloned.iterdir() if p.is_dir() and p.name.endswith("-held-out"))
    removed = held_dirs[0]
    shutil.rmtree(removed)
    digests = yaml.safe_load((cloned / "digests.yaml").read_text())
    digests.pop(removed.name, None)
    (cloned / "digests.yaml").write_text(yaml.safe_dump(digests, sort_keys=True))
    with pytest.raises(AssertionError) as exc_info:
        assert_held_out_floor(bench_root=tmp_path / "bench", task_class="vuln-remediation", min_held_out=5)
    msg = str(exc_info.value)
    assert "vuln-remediation" in msg and "4" in msg
```

Run it; confirm the held-out tree empty / BenchCaseLoadError. Commit as the red marker.

### Green — smallest impl shape

1. CVE selection (the heavy lift, per `High-level-impl.md §Risks #1`).
2. Hand-build 5 case directories per §Implementation outline §3, satisfying AC-7's distribution.
3. Write the exclusion manifest per §Implementation outline §4.
4. Compute canary pins via `os.urandom(32).hex()`; compute digests via `_compute_case_dir_digest`; record both in each `case.toml`.
5. Merge-and-resort `bench/vuln-remediation/cases/digests.yaml` per §Implementation outline §5.
6. Update `bench/vuln-remediation/README.md` per AC-11.
7. Iterate the integration test until all 13 ACs / 15 named tests are green.

### Refactor — clean up

- `bench/vuln-remediation/README.md` `## Case mapping` extension is sortable / scannable; `### Held-out selection criterion` paragraph names `PHASE_4_CORPUS_CUTOFF_YEAR` + the exclusion-manifest mode mechanism.
- Each `case.toml`'s comment block follows the canonical 4-line shape (per AC-8).
- `last_validated_at` set once at curation; loader's "stale > 90 days" warning (Phase 6.5 arch Edge case #20) fires eventually — flag in README.
- The CVE → case mapping reviewed by CODEOWNERS at PR time; the exclusion manifest is the audit-chain link from CODEOWNERS-reviewable claim to structural test.
- Per F-DP-1: when S5-05's `scripts/sign_bench_digests.py` lands, promote `_compute_case_dir_digest` to public `codegenie.eval.digests.compute_case_dir_digest`. This story consumes the private name; the promotion is a follow-on story's one-line edit.

## Files to touch

| Path | Why |
|---|---|
| `bench/vuln-remediation/cases/006-<cve-slug>-held-out/{case.toml, input/*, expected/*}` | New — first held-out case |
| `bench/vuln-remediation/cases/007-<cve-slug>-held-out/{case.toml, input/*, expected/*}` | New — second |
| `bench/vuln-remediation/cases/008-<cve-slug>-held-out/{case.toml, input/*, expected/*}` | New — third |
| `bench/vuln-remediation/cases/009-<cve-slug>-held-out/{case.toml, input/*, expected/*}` | New — fourth |
| `bench/vuln-remediation/cases/010-<cve-slug>-held-out/{case.toml, input/*, expected/*}` | New — fifth |
| `bench/vuln-remediation/cases/digests.yaml` | Extend — merge-and-resort 5 held-out entries with S5-03's 5 RAG entries (10 total) |
| `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` | New — AC-3b Mode B audit-chain link; CODEOWNERS-reviewable rationale per held-out CVE |
| `bench/vuln-remediation/README.md` | Extend — `## Case mapping` adds 5 held-out rows; new `### Held-out selection criterion` paragraph names `PHASE_4_CORPUS_CUTOFF_YEAR` + exclusion-manifest mechanism |
| `tests/integration/test_vuln_held_out_cases_load.py` | New — 15 named tests pinning all 13 ACs |

## Out of scope

- **Signing in `digests.yaml` for re-validation.** S5-05 ships `scripts/sign_bench_digests.py` as the canonical re-sign script. This story signs the initial 5 held-out entries inline (the loader cannot tolerate stubs).
- **E2E run / stub SUT.** S5-05 exercises the cases through `codegenie eval run` against the deterministic stub SUT and ships the stub SUT's `expected/` contract. This story only asserts the 5 cases *load* via `load_cases` and follows the Phase 7 + Phase 6 default `expected/` convention until S5-05 pins it.
- **Cache invalidation tests.** S5-06.
- **The recipe / Phase 4 / Phase 6 SUT.** This story does not touch Phase 4 / Phase 6 internals. The held-out cases will be executed against whatever SUT Phase 6.5 wires in (S5-05's stub or Phase 6's real SUT). The rubric is the scoring layer; this story is the corpus layer.
- **CVE-specific recipe authoring.** The bench measures the SUT; it does not author recipes for the SUT. If a held-out CVE doesn't fix correctly through the current pipeline, that is *data* — the rubric will score the failure honestly.
- **`scripts/scaffold_bench_case.py`.** Built in S5-07; this story may hand-build the 5 cases. Both paths must produce byte-identical artifacts (the canonical formulas in AC-3 are the contract).
- **Loader-side `input-pointer.toml` resolution.** Rejected per F-CON-2; not supported by the HARDENED S2-02 loader.
- **Promoting `_compute_case_dir_digest` to a public name.** Per F-DP-1, the promotion happens when S5-05's signing script lands (third non-loader consumer). This story consumes the private helper.
- **Canary derivation Strategy seam.** Per F-DP-2, deferred until ADR-P4-006 ships (third path: read-from-cassette-metadata).
- **Cross-task-class exclusion-manifest kernel.** Per F-DP-3, deferred until 3 task classes use the per-task-class manifest pattern (Phase 6.5 ships 1; Phase 7 + Phase 15 will add 2).
- **Phase 4 corpus cutoff date authoritative pinning.** `PHASE_4_CORPUS_CUTOFF_YEAR = 2025` is Phase 6.5's placeholder; Phase 4 will pin the real cutoff when its corpus design lands.

## Notes for the implementer

- **Start early.** Per `High-level-impl.md §Implementation-level risks #1`, this story is the long pole. Scaffold case directories (S5-07 if merged, else hand-built) in parallel with other Step 5 work.
- **Real CVEs only.** Synthesized "fake CVE-2099-99999" cases are not acceptable — the cases must measure judgment on real vulnerability patches the LLM has plausibly not seen.
- **Public-data discipline.** CVE snapshots and upstream patches are public. Do not vendor proprietary or undisclosed-vulnerability material. CODEOWNERS review is the human gate; if in doubt, ask.
- **Snapshot size discipline.** `input/` is a real directory of regular files; `input-pointer.toml` is forbidden (F-CON-2). Commit a **minimal extracted snapshot** containing only the file(s) the recipe touches — NOT the whole repo. If size becomes a real problem (>>1 MiB), that is a follow-on story amending S2-02 to support pointers.
- **`cassette_canary_pin` minting — `os.urandom(32).hex()` is the canonical mechanism for held-out.** Per ADR-0005 §Consequences line 44. Pin is non-deterministic at curation, durable forever after (pinned in `case.toml`). The 5 pins must form a set of size 5 (per AC-3a; the test catches copy-paste).
- **Canonical case_digest algorithm — load-bearing.** Use `_compute_case_dir_digest` from `codegenie.eval.loader` (`from codegenie.eval.loader import _compute_case_dir_digest`). DO NOT inline a re-implementation — S2-02 HARDENED has five subtle invariants (POSIX relpath sort, `case.toml` exclusion, symlink rejection, `\x1f`/`\x1e` framing, BLAKE3-once over joined records) a hand-written version will reliably break. When the helper graduates to public per F-DP-1, the test's import switches in one line.
- **The rubric does NOT read `expected/`.** S5-02 HARDENED's rubric reads `harness_output` only. `expected/` is consumed by the SUT (Phase 6 or S5-05's stub). The filename shape inside `expected/` is the SUT's contract; if neither has pinned it at execution time, follow the Phase 7 + Phase 6 default (`expected/diff.patch` + `expected/validator_output.json`) and document in the case.toml comment block. S5-05 may amend.
- **`commit_sha` is `None`; the upstream-patch SHA lives in the comment block.** `BenchCase.commit_sha: str | None` is `None` for `source="curated"` per ADR-0006 §Consequences. The 40-char upstream-patch SHA documenting the canonical fix lives in `# Source upstream patch: <SHA>`.
- **Auto Mode A / Mode B cross-check.** AC-3b never uses `pytest.skip`. When Phase 4 ships and `tests/cassettes/phase4/` appears, the test promotes Mode B → Mode A with no code edit — the manifest stays as a curator-author-time record but the corpus grep takes over as the structural defense.
- **`PHASE_4_CORPUS_CUTOFF_YEAR = 2025` is Phase 6.5's placeholder.** Documented in the README and the manifest. When Phase 4 lands, the cutoff date is updated (one-line constant edit + manifest rationale review).
- **Disposition diversity is load-bearing.** At least 1 `disposition="negative"` (e.g., a CVE whose proposed patch is wrong / reverted upstream; the SUT *should refuse* to apply it — highest-signal judgment evidence). At least 1 `difficulty="hard"` (multi-file or cross-cutting patch). At most 3 `easy` (held-out is judgment, not regression).
- **Symlink hygiene.** `input/`, `expected/`, `case.toml` — all real files. Loader rejects symlinks at load time (S2-02 §AC-9); story test (AC-10) surfaces at the story-test boundary with a clear path diagnostic.
- **No `input-pointer.toml`.** Rejected per F-CON-2.
- **digests.yaml signs all 10 after this story.** S5-03's 5 RAG entries are preserved byte-for-byte in the merge. S5-05's re-sign script (when shipped) is the canonical re-sign mechanism for future curator edits.
- **F-DP-1 hand-off: promote `_compute_case_dir_digest` to public when S5-05 lands.** S5-05's `scripts/sign_bench_digests.py` is the third non-loader consumer (after S5-03, S5-04). Surface this in the S5-05 implementer's notes.
- **F-DP-2 hand-off: canary derivation Strategy seam.** When ADR-P4-006 ships and a third path lands, extract `CanaryPinSource` sum type.
- **F-DP-3 hand-off: cross-task-class manifest kernel.** When a third task class uses the per-task-class exclusion-manifest pattern, extract `codegenie.eval.held_out_manifest.verify(task_class)`.
- **`yaml.safe_load`, `yaml.safe_dump`.** Never `yaml.load` / `yaml.dump` — `forbidden-patterns` pre-commit hook bans unsafe variants.
- **Determinism by construction.** Curator-time non-determinism (`os.urandom` for the pin, `datetime.now(timezone.utc)` for `added_at`) is captured **once** in `case.toml` and pinned forever after. Snapshot bytes under `input/` and `expected/` MUST be deterministic — no machine-specific paths, no embedded timestamps, no curator-host artifacts.
- **Coordination with S5-05.** S5-05 signs all 10 cases via the canonical re-sign script and runs the full E2E. If `case_digest` recomputation reveals drift (a curator edits `input/` after computing the digest), S5-05's signing step will fail. Stabilize `input/` / `expected/` before computing the digest; do not re-edit after.
