# Validation report — S5-03 vuln-remediation 5 RAG-corpus-derived cases

**Validated:** 2026-06-05
**Validator:** phase-story-validator
**Verdict:** HARDENED
**Findings:** 26 total — 6 block, 14 harden, 6 nit
**Conflict-resolution priority applied:** Consistency > Coverage > Test-Quality > Design-Patterns

The story's *goal* (land 5 `BenchCase` directories under `bench/vuln-remediation/cases/` with `curation_class="rag-corpus-derived"`, each derived mechanically from a `tests/cassettes/phase4/` cassette) is sound and traces directly to phase ADR-0006 §Decision §Consequences, ADR-0005 §Decision, arch §Testing strategy → Fixture portfolio, and High-level-impl §Step 5. **But the story as authored predates the HARDENED S2-02 (`load_cases` + BLAKE3 digests) contract and an executor following it verbatim would (a) prescribe a digest algorithm in Implementation outline §3 that produces different bytes from the canonical S2-02 §AC-3 algorithm — every `case_digest` written would mismatch `_compute_case_dir_digest` at load time, raising `BenchCaseDigestMismatch` on AC-4; (b) leave an `input-pointer.toml` escape hatch in AC-2 that the S2-02 HARDENED loader does not support — `(case_dir / "input").is_dir()` is required by S2-02 §AC-5 and a `case_dir / "input-pointer.toml"` file (not directory) would raise `BenchCaseLoadError(field="input", reason="input/ directory not found")`; (c) describe `cassette_canary_pin` extraction from "the cassette's canary metadata" — but Phase 4 cassettes pre-date ADR-0005's amendment (the amendment ships with this phase), so the metadata does not exist on any source cassette, leaving the implementer with no canonical derivation; (d) ship 5 cases on disk without their corresponding `cases/digests.yaml` entries — S2-02 §AC-6b raises `BenchCaseLoadError` for any case_id present on disk without a matching entry, so AC-4 ("loader loads without raising") is unreachable as written; (e) declare AC-7 (an end-to-end `codegenie eval run` exiting 0) that the story itself names in §Out-of-scope §3 as belonging to S5-05 — AC-7 also requires the full 10-case floor satisfied (S5-04) plus a deterministic stub SUT (S5-05); (f) leave the `case_id == directory-name` invariant from S2-02 §AC-7 unpinned, so a curator typo would slip past every story test and only surface at the loader.** Every issue is patchable in place → **HARDENED**, not RESCUE. The goal is correct; the contract surface is stale against the post-S2-02 ground truth.

The dominant lens was **Consistency** — six of seven issues above are direct contradictions with the hardened S2-02 loader contract or ADR-0005's pre-amendment fact pattern. The Design-Patterns critic identified one rule-of-three threshold (the canonical `case_digest` algorithm now has four upstream consumers: S5-03 cases, S5-04 cases, S5-05's `sign_bench_digests` script, S5-07's scaffolder); the synthesis pins the canonical algorithm as a citation of S2-02 §AC-3 with a Notes-for-implementer paragraph naming the future Open/Closed seam (promote `_compute_case_dir_digest` to a public `codegenie.eval.digests.compute_case_dir_digest` when the second non-loader consumer (S5-05's signing script) lands, rather than four parallel re-implementations). The promotion is not made an AC of this story (Rule 2 — the helper does not yet exist as a public name) but is now an explicit Notes-for-implementer hand-off so the next consumer story (S5-04 or S5-05) lands the public seam.

No `NEEDS RESEARCH` items — every pattern is precedented in this repo (S2-02 HARDENED's canonical digest composition, ADR-0005 §Consequences "case_digest excludes case.toml", ADR-0006's naming-convention advisory, S5-01 HARDENED's `_HERE`-style module-local constants, the `from structlog.testing import capture_logs` pattern at `tests/unit/parsers/test_safe_yaml.py:32`, the hyphen→underscore loader translation at S2-01 HARDENED).

---

## Critic: Consistency (lens: does the story contradict hardened arch / ADRs / sibling HARDENED stories?)

### F-CON-1 (BLOCK) — Digest algorithm in §Implementation outline §3 contradicts HARDENED S2-02 §AC-3

The story's §Green / §Implementation outline §3 snippet (lines 151–161) computes `case_digest` as:

```python
h = blake3.blake3()
for p in sorted((case_dir / "input").rglob("*"), key=lambda x: str(x)):
    if p.is_file():
        h.update(str(p.relative_to(case_dir)).encode())
        h.update(p.read_bytes())
for p in sorted((case_dir / "expected").rglob("*"), key=lambda x: str(x)):
    if p.is_file():
        h.update(str(p.relative_to(case_dir)).encode()); h.update(p.read_bytes())
return "blake3:" + h.hexdigest()
```

HARDENED S2-02 §AC-3 (lines 88–92 of `S2-02-loader-cases-and-digests.md`) pins the canonical algorithm:

```python
paths = sorted(
    p for p in case_dir.rglob("*")
    if p.is_file() and not p.is_symlink() and p.name not in {"case.toml"}
)
# key: p.relative_to(case_dir).as_posix() (NOT str(p) — absolute path)
records = [f"{p.relative_to(case_dir).as_posix()}\x1f{content_hash(p)}".encode("utf-8") for p in paths]
digest = "blake3:" + blake3(b"\x1e".join(records)).hexdigest()
```

Five concrete divergences: (i) the story walks `(case_dir / "input").rglob("*")` then `(case_dir / "expected").rglob("*")` separately; the canonical algorithm walks `case_dir.rglob("*")` once. A curator file under `case_dir/` outside `input/` and `expected/` (e.g., `README.md`) would be hashed by the loader but not by the story's snippet → digest mismatch. (ii) Sort key `str(p)` is the absolute filesystem path; on developer-1's machine it might be `/Users/alice/repo/...` and on developer-2's `/Users/bob/repo/...` — same content, different sort, different digest. The canonical `p.relative_to(case_dir).as_posix()` is filesystem-independent. (iii) The canonical algorithm explicitly **excludes** `case.toml` (per ADR-0005 §Consequences "case_digest intentionally excludes case.toml so a pin update is not a poisoning event"); the story's snippet doesn't exclude it either (because it only walks `input/` and `expected/`), and any future Open/Closed extension that walks `case_dir/` directly would break. (iv) Symlinks: S2-02 §AC-9 rejects ANY symlink under the case dir; the story's snippet silently follows them via `p.read_bytes()`. (v) Framing bytes (`\x1f` between relpath and per-file hash; `\x1e` between records) — the canonical algorithm hashes via Phase 0's `content_hash(p)` per-file primitive composed with framing, NOT a single `blake3.update()` stream of (relpath || filebytes). The bytes-on-the-wire differ; the digests differ.

**Consequence:** Every `case_digest` the story computes and writes into `case.toml`/`digests.yaml` would mismatch what `load_cases` recomputes. AC-4 (loader loads without raising) and AC-5 (BLAKE3 verification) both fail. AC-7 (E2E run) is unreachable a fortiori.

**Resolution:** §Implementation outline §3 now cites S2-02 §AC-3 verbatim as the canonical algorithm and prohibits inlining a divergent version. The story imports the loader's private helper for verification in the integration test:

```python
from codegenie.eval.loader import _compute_case_dir_digest  # private; canonical
```

The Design-Patterns finding (F-DP-1, below) surfaces the rule-of-three promotion path — when the second non-loader consumer (S5-05's `sign_bench_digests` script) lands, the helper should be promoted to `codegenie.eval.digests.compute_case_dir_digest`. The promotion is a follow-on story's job, not S5-03's (Rule 2 — three concrete consumers crossed at that future point, not now).

Conflict resolution: Consistency wins over the story's original algorithm prescription. Coverage's new AC-7 (re-compute digest in test and assert equality with `case.toml#case_digest`) pins the contract observably.

### F-CON-2 (BLOCK) — `input-pointer.toml` escape hatch contradicts S2-02 §AC-5 input/-must-be-a-directory invariant

The story's AC-2 sub-bullet (line 36) and Notes line 195 prescribe:

> `input/` directory with the bench-case's frozen input snapshot (or `input-pointer.toml` if pointing into `tests/cassettes/phase4/`; documented in `case.toml`).

> `input/` may be large. Use `input-pointer.toml` (a TOML file pointing into `tests/cassettes/phase4/<path>`) if the snapshot is > ~1 MiB. The loader resolves pointers transparently; `case_digest` is computed over the *resolved* path content.

HARDENED S2-02 §AC-5 (lines 94) pins:

> If `(case_dir / "input").is_dir()` is False, raise `BenchCaseLoadError(case_dir, field="input", reason="input/ directory not found")`. Fires before digest computation. Parametrized test covers: directory entirely absent; `input` exists but is a regular file; `input` exists but is a symlink.

The loader **does not resolve pointers**. There is no `input-pointer.toml` handling anywhere in the S2-02 HARDENED loader. A case with `input-pointer.toml` instead of `input/` directory raises `BenchCaseLoadError` immediately.

**Resolution:** The escape hatch is dropped. `input/` MUST be a real directory containing the bench-case's frozen pre-fix snapshot. If the snapshot is genuinely large enough that committing it bloats the repo (the story's Notes claim > 1 MiB), the curator either (a) commits a minimal extracted snapshot (the file(s) touched by the fix, not the whole repo), or (b) defers the question to a follow-on story that lands loader-side pointer resolution. Phase 6.5 ships without pointers; Phase 7 may revisit if migration cases demand them.

Conflict resolution: Consistency wins; Coverage tightens AC-2 to require `(case_dir / "input").is_dir() and not (case_dir / "input-pointer.toml").exists()` to surface the drift if a future story re-adds the pointer.

### F-CON-3 (BLOCK) — `cassette_canary_pin` derivation references metadata that does not exist on any Phase 4 cassette

The story's AC-2 (line 35) requires `cassette_canary_pin` "exactly 32 hex chars"; §Implementation outline §3 (line 53) says the pin is "extracted from the cassette's canary metadata (32 hex chars)"; Notes line 194 provides a fallback:

> The `cassette_canary_pin` value is the canary from the *source cassette*, not a fresh one. Phase 4 cassettes carry a canary metadata field; extract it (32 hex chars). If the source cassette pre-dates ADR-0005 (Phase 4 amendment), pick a deterministic 32-hex derivation: `blake3.blake3(cassette_path.encode()).hexdigest()[:32]` — and note this in `case.toml`.

**The "extract from cassette metadata" path is unreachable.** ADR-0005 §Decision pins that Phase 4's `Canary.mint(seed: bytes | None = None)` kwarg is the **additive amendment shipped *with* Phase 6.5 work** ("Phase 4 ships **`ADR-P4-006-canary-seed-kwarg.md`** as part of Phase 6.5 work"). The amendment has not landed on `master` at the time S5-03 executes (sibling story S2-05 is the canonical-seed-shim story; per the story index at `docs/phases/06.5-per-task-class-eval-harness/stories/`, S2-05 status is BLOCKED). All existing Phase 4 cassettes under `tests/cassettes/phase4/` pre-date the amendment by construction and carry no `canary_pin` / `canary_seed` metadata field. The fallback derivation is the **always-path**, not an edge case.

Two corollary bugs in the fallback formula: (i) `cassette_path.encode()` is ambiguous — is it the absolute path, repo-relative POSIX path, repo-relative filesystem path? The chosen encoding determines reproducibility across contributor machines. (ii) No domain separation — a future caller computing `blake3(path.encode())[:32]` for a different purpose collides on the same 128-bit prefix.

**Resolution:** Pin the canonical derivation:

```python
# Canonical cassette_canary_pin derivation for Phase 4 cassettes lacking
# ADR-P4-006 metadata. Domain-separated by the "phase4-cassette:" prefix.
from codegenie.hashing import content_hash  # NOT direct blake3 import
import blake3  # Allowed ONLY inside scripts/ and bench/; NOT in src/codegenie/eval/

REPO_ROOT = Path(__file__).parents[N]  # appropriate parents count
relpath = source_cassette_path.resolve().relative_to(REPO_ROOT).as_posix()
domain_separated_input = f"phase4-cassette:{relpath}".encode("utf-8")
cassette_canary_pin = blake3.blake3(domain_separated_input).hexdigest()[:32]
```

The `phase4-cassette:` prefix domain-separates from any future canary scheme. The repo-relative POSIX path is reproducible across contributor machines and platforms. When ADR-P4-006 ships and Phase 4 cassettes start carrying `canary_pin` metadata (a later phase), the derivation switches to "read metadata if present, else derive" — a one-line strategy upgrade.

The `import blake3` direct import is acceptable in this story because (i) the work is in `bench/vuln-remediation/cases/*/case.toml` (data, not Phase 0 chokepoint-policed code) and (ii) the deriver script lives outside `src/codegenie/` (either `scripts/scaffold_bench_case.py` from S5-07 or a one-off curator command). Phase 0 ADR-0001's hashing chokepoint applies to `src/codegenie/**/*.py`, not to bench-curation scripts.

Conflict resolution: Consistency wins; new AC-3a pins the formula; Test-Quality F-TQ-3 (below) pins a test that re-computes the pin and asserts byte-equality.

### F-CON-4 (BLOCK) — `digests.yaml` entries unspecified; AC-4 (loader loads) unreachable

S2-02 HARDENED §AC-6b (line 96):

> After iterating case dirs, the loader cross-checks: every case_id discovered on disk must have a `digests.yaml` entry; every `digests.yaml` entry must have a matching directory. A `case_id` on disk with no entry → `BenchCaseLoadError(case_dir, field="digests.yaml", reason=f"no entry for case_id '{case_id}'")`.

The story's §Implementation outline §5 acknowledges this in one sentence: "Add a digests-yaml stub entry for each case (the full signing happens in S5-05)." But:

(i) S2-02 §AC-6a pins `re.fullmatch(r"blake3:[0-9a-f]{64}", v)` on every value; a literal stub of `"blake3:" + "0" * 64` passes the regex BUT (ii) the digest then fails comparison against the canonical recomputation (S2-02 §AC-3 step (c) — `BenchCaseDigestMismatch`).

There is no "stub" path through the HARDENED loader. The only ways AC-4 (loader loads without raising) can hold for this story's 5 cases are:

- (a) sign the 5 cases' real digests in `cases/digests.yaml` here (don't wait for S5-05); OR
- (b) defer AC-4 to S5-05 and have S5-03 only ship the on-disk directories without a `load_cases` success contract; OR
- (c) sign only the 5 here and leave the held-out 5 (S5-04) for S5-04 to append to the same `digests.yaml`.

**Resolution: (c)**. S5-03 signs its 5; S5-04 signs its 5 (appends to the same file); S5-05's `sign_bench_digests` script is the canonical signer for future re-signing operations after curator edits to `input/` or `expected/`. This is the only path that keeps AC-4 reachable as written, satisfies CLAUDE.md "Fail loud", and allows the integration test to load the 5 cases. Files-to-touch gains `bench/vuln-remediation/cases/digests.yaml`. The integration test of S5-04 will see 10 entries; this story's test sees 5.

The "stub" language in §Implementation outline §5 is replaced with explicit signing.

Conflict resolution: Consistency wins (HARDENED S2-02 admits no stubs). Coverage tightens AC-5/-6 to assert `digests.yaml` exists, parses, contains 5 entries with case_ids matching directory names, and that each digest equals the canonical recomputation.

### F-CON-5 (BLOCK) — AC-7 (end-to-end `eval run`) contradicts §Out-of-scope §3 and is unreachable in this story's scope

AC-7 (line 42):

> Running `codegenie eval run --task-class=vuln-remediation --cases='00{1..5}-*'` (subset to just these 5) exits 0 and produces a `BenchRunReport` whose `per_case` entries' `case_id`s match the 5 directory names.

§Out of scope §3 (line 187):

> **The E2E run.** S5-05 exercises the cases through `codegenie eval run`. Here we only assert they *load*.

AC-7 and §Out of scope §3 contradict directly. The §Out-of-scope claim is factually correct for several reasons: (i) the real `vuln-remediation` SUT lives in Phase 6 (`graph/`+`engines/`+`gates/`+`sandbox/`+`recipes/`); Phase 6.5 only has Phase 6 stubs. The deterministic stub SUT is built in S5-05 (`tests/fixtures/sut/deterministic_vuln_sut.py`) — it does not exist when S5-03 executes. (ii) S2-02 §AC-3 requires every signed case to have a matching `digests.yaml` entry; if the held-out 5 (S5-04) haven't shipped, `load_cases` would still return only the 5 RAG-corpus-derived cases (loader is permissive — S2-02 §AC-11 returns `()` for zero), but the `--cases` CLI filter (`--cases='00{1..5}-*'`) requires CLI glob-filter support that S4-02 may not provide — S4-02 specifies `--case-id` selectors but does not commit to glob syntax. (iii) the `min_cases_for_promotion["bronze"]=10` floor from S5-01 + `fence-CI #2` would arguably fail before any E2E run can produce a green report (depending on whether `eval run` gates on the floor — S3-01/S3-02's runner is permissive per arch §Control flow).

**Resolution:** AC-7 is dropped. The narrower AC-4 ("loader loads all 5 without raising") is the right contract for this story. The full E2E run is S5-05's job, and S5-05's AC-3 already enforces it on the full 10 cases via the deterministic stub SUT.

Conflict resolution: Consistency wins (§Out-of-scope §3 was correct; AC-7 was the drift). The reduced scope is also more aligned with Rule 3 (Surgical Changes) — S5-03 does one thing.

### F-CON-6 (BLOCK) — `case_id == directory-name` invariant from S2-02 §AC-7 unpinned by story tests

S2-02 HARDENED §AC-7 (line 97):

> If `case.case_id == "A"` but the case lives in `cases/B/`, raise `BenchCaseLoadError(case_dir=cases/B, field="case_id", reason=f"declared 'A' but lives in directory 'B'")`. Defense-in-depth against fence-CI assertion #7.

A curator writing `001-cve-2024-12345-rag-corpus-derived/case.toml` with `case_id = "001-cve-2024-99999-rag-corpus-derived"` (typo) would pass the story's `test_case_ids_follow_naming_convention` (the regex matches both); pass `test_exactly_five_rag_corpus_derived_cases_exist`; and only fail at `load_cases` → `BenchCaseLoadError(field="case_id", ...)`. The story's `test_case_toml_documents_source_cassette_path` would also not catch it.

**Resolution:** New AC pinning `case.case_id == directory.name` for each of the 5 cases. The test is independent of the loader (it directly compares case.toml#case_id to the directory's basename); defense-in-depth catches curator typos that pre-date even the loader walk. This also closes the "5 cases mechanically derived but each `case_id` is hand-written" gap from §Implementation outline §3.

Conflict resolution: Consistency wins; new AC + new test.

### F-CON-7 (HARDEN) — Symlink-freeness of case directories not asserted by story tests

S2-02 §AC-9 rejects ANY symlink under `case_dir.rglob("*")`. If a curator's scaffolder (S5-07) or hand-build accidentally creates a symlink (`input/large.tar.gz -> ../../shared/large.tar.gz` to save disk), the loader raises. The story's tests don't directly assert symlink-freeness — they delegate to AC-4 (loader loads), which would surface the error but with an opaque diagnostic at the load layer.

**Resolution:** Add a positive test that walks each case_dir, asserts every `p.is_symlink() == False`, and produces a diagnostic naming the offending path. Cheap, defense-in-depth, makes curator-time mistakes loud.

### F-CON-8 (HARDEN) — `commit_sha` vs source-cassette derivation SHA conflation

AC-3 (line 38):

> Each case is **mechanically traceable** to a `tests/cassettes/phase4/` cassette — a comment block at the top of each `case.toml` names the source cassette path and its commit SHA at derivation time.

Two distinct SHAs are involved: (a) `BenchCase.commit_sha: str | None` (the optional Pydantic field; per ADR-0006 §Consequences "no commit_sha required" for `source="curated"`); (b) the comment-block SHA at derivation time (the git SHA of `tests/cassettes/phase4/<cassette>/` when the curator extracted the cassette content). Conflating these confuses curators.

**Resolution:** AC-3 now distinguishes: `BenchCase.commit_sha` stays `None` (per ADR-0006); the comment block carries `# Derived from: tests/cassettes/phase4/<cassette-path>` + `# Source cassette commit: <40-char SHA>` (the SHA of `master` at curation time). The integration test asserts the comment block carries both lines per case_dir.

### F-CON-9 (HARDEN) — Story Notes line 200 mis-describes the rubric's relationship to `expected/`

Notes line 199:

> The `case_digest` computation must be deterministic and reproducible: sorted recursive walk by relative path; `blake3` over (relative-path-bytes || file-bytes) for each file.

This description matches the story's original (now-rejected) algorithm, NOT the canonical S2-02 §AC-3. Updated to reference the canonical algorithm.

Notes line 198:

> If two RAG-derived cases overlap on CVE (e.g., two cassettes both fix CVE-2024-12345), pick one — the bench is fact, not redundancy. The other becomes either a held-out case (if it represents independent judgment) or discarded.

Fine as guidance, but ADR-0006 §Decision splits at *curation class*, not CVE id. A held-out case requires a CVE outside the Phase 4 corpus per ADR-0006 §Consequences ("CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff") — repurposing a Phase-4-cassette CVE as held-out violates the held-out definition. Updated to "discarded" only.

Also: the story's AC-2 says "ground-truth artifacts the rubric reads (e.g., `expected/diff.patch`, `expected/validator_output.json`)" — but S5-02 HARDENED makes clear the **rubric does not read `expected/` from disk**; the rubric reads `harness_output` only. `expected/` is consumed by the SUT (Phase 6 `VulnRemediationSut.run_case` reads `expected/diff.patch` to populate `harness_output["validator"]["cve_dropped"]` etc.). Updated AC-2 phrasing to "ground-truth artifacts the SUT compares against (per S5-05 / Phase 6's SUT contract)."

---

## Critic: Coverage (lens: do the ACs collectively guarantee the goal?)

### F-COV-1 (BLOCK) — see F-CON-4 (digests.yaml; loader-loads unreachable)

### F-COV-2 (BLOCK) — see F-CON-5 (E2E AC unreachable)

### F-COV-3 (BLOCK) — see F-CON-6 (case_id == dir.name)

### F-COV-4 (HARDEN) — `disposition` not pinned to "positive" for RAG-corpus-derived cases

Notes line 196:

> The `disposition` field: positive (the SUT *should* fix this CVE), negative (the SUT *should* refuse to fix), ambiguous (unclear). For RAG-corpus-derived cases, expect ~5 positive (the cassette corpus is solved examples).

But no AC enforces this. A curator marking a RAG-derived case `disposition="negative"` would silently pass story tests; the contradiction (RAG-derived = solved cassette = positive case) would only surface as bad scoring downstream.

**Resolution:** New AC: at least 4 of 5 RAG-corpus-derived cases have `disposition="positive"` (allow ≤ 1 `ambiguous` for the rare cassette that's a partial fix). `disposition="negative"` is rejected for RAG-corpus-derived (the cassette demonstrates a fix; the SUT should not refuse it).

### F-COV-5 (HARDEN) — `source="curated"` not pinned by test assertion

AC-2 says it ("`source="curated"` (no `commit_sha` required; ADR-0006 §Consequences)"), but no test asserts it on the loaded cases. A curator writing `source="outcome-ledger-derived"` would slip past structural shape tests.

**Resolution:** Tighten existing loader-loads test to assert `c.source == "curated"` for all 5 RAG-corpus-derived cases.

### F-COV-6 (HARDEN) — Source-cassette path existence not verified

AC-3 says the comment block names a source cassette path; no test asserts the path actually exists. A curator typo or a renamed/moved cassette lands a fake reference.

**Resolution:** New test `test_each_case_source_cassette_path_exists_under_phase4`: for each case.toml, extract the `# Derived from: tests/cassettes/phase4/...` line, parse the path, assert the resolved absolute path exists, is under `tests/cassettes/phase4/`, and `path.exists()`.

### F-COV-7 (HARDEN) — 5 source cassettes must be distinct (regression coverage is illusory if same cassette derives 2+ cases)

Notes line 198 mentions "if two RAG-derived cases overlap on CVE ... pick one." But no test enforces. A curator deriving 5 cases from the same cassette (zero variance) trivially passes all existing structural tests.

**Resolution:** New test: the set of source-cassette paths extracted from the 5 case.toml comment blocks has cardinality 5.

### F-COV-8 (HARDEN) — `case_digest` in `case.toml` not asserted against canonical recomputation

S2-02 §AC-3 catches digest mismatch at *load* time and raises `BenchCaseDigestMismatch`. But the story should additionally pin (defense-in-depth at the story-test boundary) that each case.toml's declared `case_digest` matches what the canonical algorithm produces over the case dir.

**Resolution:** New test invokes `_compute_case_dir_digest(case_dir)` per case and asserts equality with `case.toml#case_digest`. Reuses the loader's private helper for the algorithm (no inline reimplementation).

### F-COV-9 (HARDEN) — `case_digest` consistency between `case.toml` and `digests.yaml`

S2-02 §AC-3 step (c) compares `digests[case_id]` (from `cases/digests.yaml`) to the recomputed digest, not to `case.toml#case_digest`. The two are independent fields; if a curator updates one but not the other, `case.toml#case_digest` could lie about the truth that `digests.yaml` and the loader enforce. The integration test should pin all three values match.

**Resolution:** New test asserts for each case: `case.toml#case_digest == digests.yaml[case_id] == _compute_case_dir_digest(case_dir)`.

### F-COV-10 (HARDEN) — Test `test_exactly_five_rag_corpus_derived_cases_exist` ignores directory naming

The test filters loaded cases by `c.curation_class == "rag-corpus-derived"`, then asserts `len == 5`. A case mistagged `curation_class="held-out"` in a directory named `001-foo-rag-corpus-derived/` would (a) be filtered out, so the count drops, breaking this test. But a case mistagged `curation_class="rag-corpus-derived"` in a directory named `001-foo-held-out/` would pass this test and the naming-pattern test (the regex would fail) — actually it depends on the regex. The original `^00[1-5]-.+-rag-corpus-derived$` pattern requires the directory to end with `-rag-corpus-derived`, which the wrong directory wouldn't. OK so this is partially covered, but the bidirectional check (directory_name endswith `-rag-corpus-derived` ⇔ curation_class == "rag-corpus-derived") is not directly pinned.

**Resolution:** Tighten test: assert that the set of directories ending in `-rag-corpus-derived` equals the set of case_ids with `curation_class="rag-corpus-derived"`.

### F-COV-11 (NIT) — Directory-naming index `00{1..5}` overlap with held-out's `00{6..10}` not verified

ADR-0006 §Consequences (line 40): "case IDs marked `001-005-rag-corpus-derived-*` and `006-010-held-out-*` (naming convention; not enforced)." S5-04 will land `006-...`–`010-...`. The story's AC-1 enforces `00[1-5]` for RAG-derived; defense against `006-foo-rag-corpus-derived/` (an index collision with S5-04) is implicit in the regex but not pinned.

**Resolution:** No additional AC — the AC-1 regex `^00[1-5]-.+-rag-corpus-derived$` already pins it. Notes-for-implementer reinforces the convention.

---

## Critic: Test-Quality (lens: would the TDD plan catch an obviously wrong implementation?)

### F-TQ-1 (HARDEN) — `test_every_case_has_32_hex_cassette_canary_pin` lets `"a" * 32` pass

The test verifies length and hex chars but doesn't verify the pin matches the canonical formula. A curator hand-writing `cassette_canary_pin = "a" * 32` (or any random 32-hex string) silently passes. The pin is then untethered from the source cassette → if the cassette is moved/renamed, the bench-author has no canonical way to regenerate.

**Resolution:** New test re-derives each pin via the canonical formula (`F-CON-3` resolution) from the comment block's source-cassette path and asserts byte-equality. Kills "random 32-hex" and "wrong-prefix domain-separation" mutants.

### F-TQ-2 (HARDEN) — `test_every_case_has_blake3_digest_with_64_hex` is weak

Tests prefix + length but not content match. A stub digest of `"blake3:" + "0" * 64` passes the test, then fails at load time. The story should kill this earlier.

**Resolution:** Replaced by F-COV-8's canonical-recomputation test.

### F-TQ-3 (HARDEN) — `test_case_toml_documents_source_cassette_path` substring match too lax

The test just `assert "tests/cassettes/phase4/" in text`. A literal `"# tests/cassettes/phase4/ — fake reference"` line passes. A typo'd cassette name `tests/cassettes/phase4/lol-fake-cassette/` passes.

**Resolution:** Per F-COV-6, replaced with a path-existence test. The regex parse also fishes the SHA (per F-CON-8) and verifies it's a 40-char hex string.

### F-TQ-4 (HARDEN) — `test_every_case_directory_has_input_and_expected_subdirs` silently OK with symlinks

The test uses `c.input_path.is_dir()` which returns `True` for symlinks-to-directories. A symlink `input -> ../shared/large-snapshot/` would pass this test, then fail at loader's symlink scan (S2-02 §AC-9).

**Resolution:** Tighten — `c.input_path.is_dir() and not c.input_path.is_symlink()`. Also asserts `(case_dir / "input-pointer.toml").exists() is False` (F-CON-2 backstop).

### F-TQ-5 (HARDEN) — `test_case_ids_follow_naming_convention` allows duplicate case_ids

The test asserts each case_id matches the regex; doesn't enforce the 5 case_ids are distinct. Loader's collision-check (S2-02 §AC-8) catches it but story-level test should also.

**Resolution:** Add `len(set(c.case_id for c in rag)) == 5`.

### F-TQ-6 (HARDEN) — No test exercises the deterministic-digest property

A curator running the scaffolder twice should produce byte-identical case directories. No test enforces. While individual `case_digest` mismatches are caught by F-COV-8, a non-deterministic *scaffolder* (e.g., embedding `datetime.now()` in case.toml's `added_at` makes scaffolding non-idempotent) is not directly tested.

**Resolution:** Pin in Notes-for-implementer: `added_at` is set once at curation time, never updated; `last_validated_at` is updated only on intentional re-validation. Not promoted to AC (the deterministic-rerun test is S5-07's scaffolder territory; for hand-built cases the property is the bench-author's discipline).

### F-TQ-7 (HARDEN) — No mutation test for `disposition` and `difficulty`

Per F-COV-4 and Notes, disposition skews positive and difficulty skews easy for RAG-derived cases. Add ACs + tests so a curator marking everything `difficulty="hard"` doesn't pass silently (a hard cassette case suggests the curator didn't actually mechanically derive from a solved cassette).

**Resolution:** New AC: at least 4 of 5 cases have `difficulty="easy"`; at least 4 of 5 have `disposition="positive"`.

### F-TQ-8 (HARDEN) — No test verifies `bench/vuln-remediation/README.md` mapping table

§Refactor §1 says "README documents the selection criterion and the source-cassette → case mapping (a table: case_id ↔ cassette path ↔ derivation commit SHA)." But no AC enforces.

**Resolution:** New AC: README has a "Case mapping" section containing a table whose rows count exactly 5 RAG-corpus-derived rows and each row names a `tests/cassettes/phase4/...` path that matches the comment-block in the corresponding case.toml.

### F-TQ-9 (NIT) — Hypothesis property test not warranted at this scale

The story ships 5 hand-curated cases; introducing Hypothesis here would be testing the scaffolder, not the cases. S5-07's TDD plan is the right home.

**Resolution:** No change.

### F-TQ-10 (NIT) — `tomllib` parse error path not tested

Tested transitively by loader's AC-12; no need to re-pin at the story level.

**Resolution:** No change.

---

## Critic: Design-Patterns (lens: is the prescribed implementation easy to extend by addition?)

### F-DP-1 (HARDEN — surfaced in Notes; not an AC of this story) — Promote `_compute_case_dir_digest` to public on third consumer landing

The canonical case-dir digest algorithm has rule-of-three momentum:

1. S2-02 (HARDENED) — `_compute_case_dir_digest` lives private in `src/codegenie/eval/loader.py`.
2. S5-03 (this story) — needs to compute digests for case.toml and digests.yaml; consumes the private helper.
3. S5-04 (sibling) — same shape, same need.
4. S5-05 — `scripts/sign_bench_digests.py` (re-signs after curator edits).
5. S5-07 — `scripts/scaffold_bench_case.py` initial-digest emission.

The current story uses the private helper (`from codegenie.eval.loader import _compute_case_dir_digest`). When the second non-loader consumer lands (S5-05's signing script, or S5-07's scaffolder, whichever ships first), the helper should be promoted to a public name. The most surgical promotion is a new module `src/codegenie/eval/digests.py` exporting `compute_case_dir_digest(case_dir: Path) -> str` (or a public re-export from `loader.py`), with `loader.py` consuming it. This pays the Rule-of-three rent for adding a new task class (`migration-chainguard-distroless`'s scripts will reuse it).

**This is not an AC of S5-03** — the story should not promote a public surface (Rule 2; the loader's HARDENED contract is the source of truth). Surfaced in Notes-for-implementer as the trigger condition for a future cleanup story.

Conflict resolution: Design-Patterns deferred; Coverage / Test-Quality use the private name pragmatically.

### F-DP-2 (NIT — surfaced) — Strategy seam for `cassette_canary_pin` derivation

Two derivation paths will eventually exist:

1. Today: deterministic-from-path (`blake3("phase4-cassette:" + relpath)[:32]`).
2. Future (ADR-P4-006 + cassette re-cut): read from cassette metadata field.

For one path today, Rule 2 says no abstraction. When the second path lands, extract a `CanaryPinSource` sum type (`Path | CassetteMetadata`) + `derive_canary_pin(source: CanaryPinSource) -> str` smart-constructor. The future seam is documented in Notes; no AC.

### F-DP-3 (NIT — surfaced) — `expected/` shape is SUT-contract territory

S5-02 HARDENED makes clear the rubric reads `harness_output`, not `expected/`. The shape of `expected/` (whether it contains `diff.patch`, `validator_output.json`, or other files) is a contract between the curator and Phase 6's SUT. S5-03's story should mention this without prescribing the file names (the SUT design is downstream). Notes updated.

### F-DP-4 (NIT — surfaced) — Functional core / imperative shell

The canonical algorithm in S2-02 is already a functional core (pure given the file tree). The story's curation work (selecting 5 cassettes, copying snapshots) is imperative-shell territory. Notes endorse the existing split; no change.

---

## Synthesis — edits applied to the story

Edits in-place per the Editor reference:

- **Status line** updated to `HARDENED (phase-story-validator, 2026-06-05)`.
- **Validation notes block** added under the Status line, naming this report.
- **AC list** restructured: ACs 1–7 strengthened; AC-7 (E2E run) **dropped** per F-CON-5; **new ACs added** (AC-3a pinned canary derivation; AC-4 case_id==dir.name; AC-6a digests.yaml signed by this story; AC-7 disposition/difficulty distribution; AC-8 source-cassette-path existence + distinct count; AC-9 canonical-digest recomputation; AC-10 symlink-freeness; AC-11 README mapping table); total ACs grow from 8 → 13.
- **Implementation outline** rewritten: §3 cites S2-02 §AC-3 verbatim and prohibits inlining a divergent algorithm; §5 (digests-yaml stub) replaced with "sign 5 cases in `digests.yaml` per F-CON-4 resolution"; §3 also pins the canonical `cassette_canary_pin` derivation formula.
- **TDD plan** rewritten: 6 thin tests → 11 mutation-resistant tests, each with concrete assertions; new tests cover canonical-digest recomputation, canonical canary-pin recomputation, case_id↔dir.name, source-cassette-path existence + uniqueness, disposition/difficulty distribution, symlink-freeness, digests.yaml exists + parses + entries match canonical, README mapping table existence.
- **Files to touch** gains `bench/vuln-remediation/cases/digests.yaml`.
- **Out of scope** clarified: "full 10-case `digests.yaml` signing" is S5-05 (this story's 5 entries; S5-04 appends its 5); "E2E run" remains S5-05; "loader-side `input-pointer.toml` resolution" added explicitly.
- **Notes for the implementer** rewritten to: cite the canonical algorithm by S2-02 §AC-3 reference; pin the canonical canary-pin derivation; surface F-DP-1 (rule-of-three promotion); surface F-DP-2 (canary derivation strategy); clarify that the rubric does not read `expected/`; clarify the `commit_sha` vs derivation-commit-SHA distinction; clarify ADR-P4-006 not yet shipped means the deterministic-derivation path is the always-path today; remove the now-incorrect "input-pointer.toml" guidance.

---

## Verdict

**HARDENED.** 26 findings (6 block, 14 harden, 6 nit). All BLOCK findings patched in place; all HARDEN findings either promoted to AC + TDD or surfaced in Notes. The goal (5 RAG-corpus-derived cases, mechanically derived) is unchanged. The contract surface is now consistent with HARDENED S2-02, ADR-0005 (including the pre-amendment fact pattern), ADR-0006, and the sibling S5-02 HARDENED rubric story. The TDD plan now kills the obvious mutants (wrong digest algorithm, undocumented canary pin, mistagged disposition, missing digests.yaml, hand-written wrong digest, symlinks, duplicate cassettes).

Ready for `phase-story-executor`.
