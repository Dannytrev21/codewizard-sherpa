# Validation report — S5-04 vuln-remediation 5 held-out hand-curated cases

Validated: 2026-06-05
Verdict: **HARDENED**
Story file: `docs/phases/06.5-per-task-class-eval-harness/stories/S5-04-vuln-held-out-cases.md`

## Summary

Twenty-five findings: **6 BLOCK**, **13 HARDEN**, **6 surfaced/nit**.
No `NEEDS RESEARCH` items — every pattern is precedented in this repo (S5-03 HARDENED's canonical case-dir digest composition, S2-02 HARDENED loader invariants, ADR-0005 §Consequences "os.urandom(32).hex() for net-new pins", S1-02 HARDENED Pydantic shapes, S5-02 HARDENED rubric-reads-harness_output contract).

## Conflict-resolution priority (Consistency > Coverage > Test-Quality > Design-Patterns)

Several findings cross critics — Consistency wins decisively whenever a sibling HARDENED story already pinned a contract S5-04 was about to silently fork.

## Findings

### Consistency critic (10)

- **F-CON-1 (BLOCK) — expected/ filenames over-prescribed.** Original AC-2 + Implementation outline §3 said `expected/diff.patch` (the actual upstream patch) and `expected/validator_output.json` (the validator's expected JSON output: `{"build_passed": true, "tests_passed": true, "cve_dropped": true}`). S5-02 HARDENED is unambiguous: **the rubric reads `harness_output`, not `expected/`**. The shape of `expected/` is SUT-contract territory (Phase 6's `VulnRemediationSut` or S5-05's deterministic-stub SUT). S5-03 HARDENED's F-CON-9 already pinned this for the RAG-corpus-derived siblings. **Resolution:** Loosen `expected/` requirement to "non-empty regular-file directory; filenames follow the SUT contract (Phase 6 or S5-05 stub). The story does not invent the SUT contract." Defer the concrete-filename pin to S5-05 (the stub SUT defines its contract).

- **F-CON-2 (BLOCK) — `input-pointer.toml` escape hatch reintroduced.** AC-4 + Implementation outline §3 said `input/` "or `input-pointer.toml` if the snapshot lives elsewhere; documented". S2-02 HARDENED §AC-5 raises `BenchCaseLoadError(field="input", reason="input/ directory not found")` if `(case_dir / "input").is_dir()` is False. `input-pointer.toml` is a file, not a directory; the loader will reject any case using it. S5-03's F-CON-2 dropped the same escape hatch. **Resolution:** Drop the pointer escape hatch entirely; commit minimal extracted snapshots under `input/`. Defer pointer support to a future S2-02-amending story if portfolio scale forces it.

- **F-CON-3 (BLOCK) — wrong digest algorithm.** Implementation outline §3 said "`case_digest` — BLAKE3 over `input/` + `expected/` (same algorithm as S5-03)". This is two-walk + ambiguous on ordering, exclusion, framing. The canonical S2-02 §AC-3 algorithm (the only allowed algorithm at the HARDENED loader) is: walk `case_dir.rglob("*")` **once**, sort by POSIX relpath, filter to regular non-symlink files, exclude `case.toml`, frame each as `f"{rel_posix}\x1f{content_hash(p)}".encode("utf-8")`, join records with `\x1e`, BLAKE3-once, prefix with `blake3:`. Every byte the story-prescribed algorithm produces would mismatch what the loader computes. S5-03's F-CON-1 made this resolution; mirror it. **Resolution:** Cite S2-02 §AC-3 verbatim; pin `from codegenie.eval.loader import _compute_case_dir_digest`; forbid inline reimplementation. (Per F-DP-1, when the third non-loader consumer lands — likely S5-05's `scripts/sign_bench_digests.py` — promote the helper to public `codegenie.eval.digests.compute_case_dir_digest`.)

- **F-CON-4 (BLOCK) — `commit_sha is None` vs include-it-for-traceability conflict.** Original Implementation outline §3 said `commit_sha may be the pre-fix commit (this is source="curated" so commit_sha is optional, but include it for traceability)`. S5-03 HARDENED pinned `commit_sha is None` for `source="curated"` (the upstream CVE patch SHA lives in the `# Source upstream patch: <SHA>` comment block at the top of `case.toml`). Held-out cases are also `source="curated"`. Two distinct SHAs were conflated: `BenchCase.commit_sha: str | None` (the Pydantic field) and the CVE-upstream-patch SHA at curation time (the comment block). **Resolution:** Mirror S5-03: `BenchCase.commit_sha is None` for held-out cases; the upstream patch SHA + CVE reference URL live in the comment block at the top of `case.toml`.

- **F-CON-5 (BLOCK) — `cases/digests.yaml` signing missing.** AC-2 / Implementation outline say nothing about appending the 5 held-out digests to `bench/vuln-remediation/cases/digests.yaml`. S5-03 created the file with 5 RAG-corpus-derived entries; S5-04 must **append** 5 held-out entries (preserving alphabetical sort by key). Otherwise S2-02 §AC-6b raises `BenchCaseLoadError(field="digests.yaml", reason="missing entry for case_id ...")` at load time and `load_cases` cannot resolve held-out cases. There is no "stub" path through the HARDENED loader. **Resolution:** New AC-6 + AC-6a (3-way consistency) mirror S5-03. Implementation outline §5 pinned: merge-and-resort, do not overwrite.

- **F-CON-6 (BLOCK) — AC-7 "scores end-to-end" conflicts with §Out of scope.** Original AC-7 said "Each case scores end-to-end through `bench/vuln-remediation/rubric.py`". §Out of scope §2 simultaneously said "E2E run. S5-05." S5-02 HARDENED's rubric reads `harness_output` (not `expected/`); an "end-to-end" run requires the SUT, which lives in Phase 6 (not yet shipped) or S5-05's deterministic-stub SUT. The AC was unrealisable in this story's red-green window. **Resolution:** Drop "scores end-to-end"; replace with a narrower "loader loads all 5 without raising" contract (mirroring S5-03's AC-5). The rubric-smoke layer becomes S5-05's job.

- **F-CON-7 (HARDEN) — `Depends on:` line incomplete.** Original line names only S5-02. S5-04 actually depends on **S5-03 HARDENED** (digests.yaml exists; the merge step is meaningful), **S2-02 HARDENED** (loader contract + canonical digest algorithm), **S1-02 HARDENED** (BenchCase wire-type shapes — including the `Literal` taxonomies), **S2-01 HARDENED** (`load_task_class` is the import surface), and **S5-01 HARDENED** (`bench/vuln-remediation/registration.py` resolves the task class). Mirror S5-03's depends-on quality. **Resolution:** Expand `Depends on:` to name all five with HARDENED markers.

- **F-CON-8 (HARDEN) — ADRs-honored line incomplete.** Original names ADR-0006 + ADR-0005 only. Should also name **Phase 0 ADR-0001** (BLAKE3 hashing chokepoint — for `src/codegenie/`; `tests/` and `bench/` are exempt because they live outside the policed runtime closure; the integration test's `import blake3` for canary-format checks lives under `tests/`). Mirror S5-03's ADRs-honored line. **Resolution:** Expand.

- **F-CON-9 (HARDEN) — sort + total-corpus invariant unspecified.** Original AC-5 says "`loader.load_cases(task_class)` returns 10 total cases sorted by `case_id`" — but the loader returns a tuple sorted ascending by `case_id` per S2-02 §AC-2 (this is the loader's invariant; the story doesn't *enforce* it). The total-corpus count (5 RAG + 5 held-out = 10) is a story-level invariant that should be tested. **Resolution:** Promoted to AC-12 (post-S5-04 corpus has exactly 10 cases; held-out count is exactly 5; RAG-corpus-derived count is exactly 5; sorted ascending by `case_id`).

- **F-CON-10 (HARDEN) — README mapping table not promoted to AC.** Original AC-9 ("CVE selection criterion is documented in `bench/vuln-remediation/README.md`") names that the README documents the *criterion* and *names each held-out CVE*, but the structural mapping-table pattern S5-03 HARDENED locked in (under `## Case mapping` section, with rows containing case_id, CVE, upstream commit, curation_class) is not an AC. **Resolution:** Promoted to AC-11 mirroring S5-03's AC-11 (rows ≥ 5 with curation_class == "held-out"; selection criterion paragraph).

### Coverage critic (8)

- **F-COV-1 (BLOCK) — canonical directory-name regex missing.** Original AC-1 says directory names "follow the pattern `00{6..10}-<cve-id>-held-out/`" but provides no machine-checkable regex. S5-03 pinned `^00[1-5]-[a-z0-9][a-z0-9-]*-rag-corpus-derived$` (fullmatch) and also asserted the no-other-dir-contains-the-substring property. **Resolution:** New AC-1 pins `r"^(00[6-9]|010)-[a-z0-9][a-z0-9-]*-held-out$"` (fullmatch) over the 5 names, plus the "no other directory has the `-held-out` substring outside this regex" guard.

- **F-COV-2 (BLOCK) — canary-pin canonical contract missing.** Original AC-2 says "32-hex `cassette_canary_pin`" but does not pin a *derivation* contract. **ADR-0005 §Consequences line 44** explicitly says held-out / new-bench pins are generated by `os.urandom(32).hex()` at curation time — non-deterministic at curation, durable forever after. S5-03 has a deterministic formula because RAG-corpus-derived cases derive their pin from the source cassette path; held-out cases have no source cassette, so there is nothing to derive from. The right contract for held-out is therefore: **format-checked** (32 lowercase hex) AND **distinct across the 5 cases** (no copy-paste collisions). **Resolution:** New AC-3a pins lowercase 32-hex format + pin-distinctness across the 5. Implementation outline pins `os.urandom(32).hex()` as the canonical pin-minting mechanism.

- **F-COV-3 (HARDEN) — tz-aware UTC timestamps untested.** S1-02 HARDENED requires `added_at` / `last_validated_at` tz-aware UTC. The original AC-2 names them but does not test the invariant. Mirror S5-03's AC-2 timezone check. **Resolution:** Folded into AC-2.

- **F-COV-4 (HARDEN) — `commit_sha is None` not pinned in AC.** Per F-CON-4: pin `BenchCase.commit_sha is None`. **Resolution:** Folded into AC-2.

- **F-COV-5 (HARDEN) — disposition/difficulty distribution unenforced.** Original Notes say "Aim for at least 1 `negative` case" + "At least 1 `hard` case" + "Easy + medium + hard mix" — but no AC enforces. Without enforcement, a curator could ship 5 positive-easy cases and the bench would still claim silver eligibility on memorization-light signal. The point of held-out is judgment evidence; distribution diversity is load-bearing. **Resolution:** New AC-7 pins:
  - At least 1 of 5 has `disposition == "negative"` (the SUT should *refuse* the case — patch reverted upstream / known-bad fix; high-signal judgment evidence)
  - At least 1 of 5 has `disposition == "ambiguous"` OR `disposition == "negative"` (some non-positive evidence beyond "always fix")
  - At least 1 of 5 has `difficulty == "hard"` (multi-file or cross-cutting CVE patch; tests cross-cutting reasoning)
  - At most 3 of 5 have `difficulty == "easy"` (skew away from easy-only; the rationale for held-out is *judgment*, not regression-only)

- **F-COV-6 (HARDEN) — symlink-freeness defense missing.** S5-03 has AC-10 (symlink-freeness defense at the story-test boundary). S5-04 should mirror — even with S2-02 §AC-9 as the lazy backstop, story-level pins surface curator-time mistakes with a clear path diagnostic. **Resolution:** New AC-10 mirrors S5-03's.

- **F-COV-7 (HARDEN) — case_id ↔ directory-name bidirectional invariant missing.** S2-02 §AC-7 catches `case.case_id != case_dir.name` at load time; S5-03's AC-4 enforces it at the story-test boundary as defense-in-depth (a story-level diagnostic names the offending case_id without an opaque loader stack). Mirror. **Resolution:** New AC-4.

- **F-COV-8 (HARDEN) — 3-way digest consistency unenforced.** S5-03's AC-6a (`case.toml#case_digest == digests.yaml[case_id] == _compute_case_dir_digest(case_dir)` triple-equality, per case) catches the curator forgetting to update one of the three after a re-sign. Mirror. **Resolution:** New AC-6a.

### Test Quality critic (4)

- **F-TQ-1 (BLOCK) — `test_held_out_cve_not_in_rag_corpus` silently passes when Phase 4 corpus absent.** Current implementation: `if not RAG_CORPUS_ROOT.exists(): pytest.skip(...)`. At S5-04 execution time, Phase 4 has not yet shipped — `tests/cassettes/phase4/` doesn't exist, so the test always skips. The load-bearing memorization-vs-judgment guard ADR-0006 §Decision pins is silently defeated. A curator could ship `006-cve-2024-99999-held-out` whose CVE is in fact represented in a future Phase 4 corpus, and the test would never catch it. **Resolution:** Replace the skip with a **two-mode** contract:
  - **Mode A (Phase 4 corpus present):** grep `tests/cassettes/phase4/**` for each held-out CVE id; fail with the offending case_id + CVE + cassette path if found.
  - **Mode B (Phase 4 corpus absent):** the story commits to a **structured exclusion-list manifest** at `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` listing each held-out CVE id and the curator's stated rationale ("Phase 4 RAG corpus is built from CVEs disclosed before 2025-04; CVE-YEAR-NNNN with YEAR ≥ 2025 is therefore outside the corpus by construction"). The test in Mode B asserts the manifest contains an entry per held-out case_id with a non-empty rationale; when Phase 4 ships (and the corpus tree appears), the test auto-promotes to Mode A. The manifest is the audit-chain link from a CODEOWNERS-reviewable claim ("this CVE is held out") to a structural test (grep the corpus). Concrete: new AC-3b + the test selects mode at runtime via `if RAG_CORPUS_ROOT.exists(): mode_A_test() else: mode_B_test()` and never skips.

- **F-TQ-2 (BLOCK) — `cve-\d{4}-\d+` regex accepts CVE-1999.** Original `test_case_ids_carry_cve_identifier` matches `cve-\d{4}-\d+` (any year). ADR-0006 §Consequences: "CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff, or older CVEs explicitly excluded from corpus construction (and noted)". A curator using CVE-2010-0001 would pass the test, defeating the contract. **Resolution:** Tighten test:
  - Extract `cve-(\d{4})-\d+` per case_id; require `year >= PHASE_4_CORPUS_CUTOFF_YEAR` where the cutoff is a module-level constant `PHASE_4_CORPUS_CUTOFF_YEAR: Final[int] = 2025` (documented in Notes-for-implementer and the exclusion manifest; the actual cutoff date lives in Phase 4's design — Phase 6.5 commits to the placeholder until Phase 4 ships and pins the real date).
  - Older CVEs are allowed ONLY if the case_id has a `-pre-corpus` suffix marker AND the exclusion manifest entry documents *why* it's pre-corpus (e.g., "CVE-2018-XXXX explicitly excluded from corpus construction during Phase 4 fixture curation; rationale recorded here"). The test parses `case_id` for the `-pre-corpus` marker and grants the older-year exception only if the manifest contains a matching pre-corpus rationale.

- **F-TQ-3 (BLOCK) — digest format-only check is mutation-weak.** Original `test_held_out_cases_have_blake3_digest_and_pin` asserts only `c.case_digest.startswith("blake3:") and len(c.case_digest) == 71`. A curator hand-writing `case_digest = "blake3:" + "0" * 64` passes the test, then fails at S2-02 load-time with `BenchCaseDigestMismatch`. Surfacing the failure at the story-test boundary with a clear diagnostic (curator wrote the wrong algorithm / forgot to re-sign after editing input/) is the higher-signal path. Mirror S5-03's AC-3 test. **Resolution:** New AC-3 + test recomputes via `_compute_case_dir_digest(case_dir)` and asserts byte-equality per case.

- **F-TQ-4 (HARDEN) — pin-distinctness across the 5 untested.** No test asserts the 5 cassette_canary_pins are distinct. A curator copy-paste-error would ship 5 identical pins, which the loader accepts (each pin is independently format-valid), but the harness's per-case canary determinism collapses (two cases share canary → cassette identity collision → byte-for-byte replay breaks). **Resolution:** Folded into AC-3a (pin-distinctness across the 5).

### Design Patterns critic (3 — all surfaced; none promoted to AC)

- **F-DP-1 (surfaced) — `_compute_case_dir_digest` rule-of-three triggers in S5-05, not here.** Consumers of the canonical algorithm: S5-03 (RAG-derived sign), S5-04 (this story — held-out sign), S5-05's `scripts/sign_bench_digests.py`. When S5-05 lands, the private helper graduates to `codegenie.eval.digests.compute_case_dir_digest`. NOT this story's job — S5-04 consumes the private name (one-line edit when S5-05 promotes). Notes-for-implementer surfaces.

- **F-DP-2 (surfaced) — canary derivation Strategy seam preview.** Two concrete derivation paths now exist: (a) RAG-corpus-derived → deterministic-from-cassette-path formula (S5-03); (b) held-out → `os.urandom(32).hex()` at curation (this story, per ADR-0005 §Consequences). Two paths — not three. Rule of three says no abstraction yet. When ADR-P4-006 ships and Phase 4 cassettes re-cut with canary metadata (third path: read-from-cassette-metadata), extract a `CanaryPinSource` sum type (`CassettePath | CassetteMetadata | FreshMint`) and a `derive_canary_pin(source) -> str` smart constructor. NOT this story's job. Notes surfaces.

- **F-DP-3 (surfaced) — exclusion-manifest is an Open/Closed extension point.** The exclusion-manifest pattern introduced by F-TQ-1 Mode B is itself extensible: future task classes (`migration-chainguard-distroless`, Phase 15 `agentic-recipe-authoring`) will need the same "outside-the-RAG-corpus" structural defense. The manifest's path is per-task-class (`bench/{task-class}/cases/held-out-cve-exclusion-manifest.yaml`); a future cross-task-class kernel `codegenie.eval.held_out_manifest.verify(task_class)` could centralize the contract once 3 task classes use it. For now, one manifest in this story; Rule 2 — no abstraction. Notes surfaces.

### Surfaced (no edit) — endorsements

- **Functional-core / imperative-shell.** The canonical S2-02 digest algorithm is the functional core; the curation work (CVE selection, snapshot extraction, comment-block authoring) is imperative-shell. The pattern is sound. Endorsed; no edit.
- **`os.urandom(32).hex()` for fresh-mint pins.** Per ADR-0005 §Consequences this is the canonical pin-mint mechanism for cases without a prior cassette. The non-determinism is at curation-time only; once pinned in case.toml the value is durable. Endorsed; pinned in Implementation outline.

## Edits applied

- **Status** updated to `HARDENED (phase-story-validator, 2026-06-05)`.
- **Depends on** rewritten to name S5-02 HARDENED + S5-03 HARDENED + S2-02 HARDENED + S1-02 HARDENED + S2-01 HARDENED + S5-01 HARDENED with HARDENED contract markers (F-CON-7).
- **ADRs honored** expanded to add Phase 0 ADR-0001 + per-citation rationale (F-CON-8).
- **Validation notes** block appended under the header (this report's audit pointer).
- **Context** expanded to surface the load-bearing memorization-vs-judgment role of the held-out 5 + the exclusion-manifest mode-A/mode-B mechanism + the canonical formulas (F-TQ-1 / F-CON-3 / F-COV-2 collisions surfaced where the curator will see them).
- **References — where to look** expanded with: S5-03 HARDENED (sibling pattern), S2-02 HARDENED §AC-3 / §AC-5 / §AC-6a / §AC-6b / §AC-7 / §AC-9, S5-02 HARDENED (rubric reads harness_output), S1-02 HARDENED (BenchCase Pydantic shape — Literals + tz-aware UTC + commit_sha optional + `blake3:<64 hex>` validator).
- **Acceptance criteria** restructured from 8 prose-only bullets to 13 named ACs with concrete machine-checkable predicates (F-CON-1 through F-CON-6 BLOCKs, F-COV-1 through F-COV-8 hardens, F-TQ-1 through F-TQ-4 hardens). The new ACs mirror S5-03 HARDENED's structure verbatim where the contract is parallel.
- **Implementation outline** rewritten to: cite S2-02 §AC-3 verbatim for the digest; pin `os.urandom(32).hex()` for the canary; drop `input-pointer.toml`; pin `commit_sha is None`; pin the `digests.yaml` merge-and-resort logic; pin the exclusion-manifest schema.
- **TDD plan** rewritten — old 6-test sketch replaced with 13 named, mutation-resistant tests under `tests/integration/test_vuln_held_out_cases_load.py`. Each test cites its AC and uses concrete `pytest.raises` / `assert ... == ...` / parametrized scans (no `pytest.skip` for the load-bearing held-out cross-check).
- **Files to touch** expanded with `bench/vuln-remediation/cases/held-out-cve-exclusion-manifest.yaml` (new) + the integration test (renamed for clarity).
- **Out of scope** expanded — adds the "rubric end-to-end smoke" (S5-05), the held-out canary derivation Strategy seam (F-DP-2 trigger), the `_compute_case_dir_digest` promotion (F-DP-1 trigger), and the cross-task-class manifest kernel (F-DP-3 trigger).
- **Notes for the implementer** expanded with the surfaced design seams + the `PHASE_4_CORPUS_CUTOFF_YEAR` rationale + the durability semantics of `os.urandom(32).hex()` pins + the rubric-reads-harness_output reminder.

## Verdict

**HARDENED.** The story now traces every acceptance criterion to a load-bearing sibling contract or ADR, every TDD test is mutation-resistant, every Implementation outline step has a concrete code-shape, and the design seams the next stories will need (canary Strategy, digest helper promotion, manifest kernel) are surfaced as Notes-for-implementer triggers, not premature ACs.
