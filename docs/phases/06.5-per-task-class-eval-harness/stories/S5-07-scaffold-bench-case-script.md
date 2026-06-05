# Story S5-07 — `scripts/scaffold_bench_case.py` operator tool

**Step:** Step 5 — Backfill `bench/vuln-remediation/` with ≥10 cases + rubric + taxonomies
**Status:** HARDENED (phase-story-validator, 2026-06-05)
**Effort:** S
**Depends on:** S5-01 HARDENED (`bench/vuln-remediation/registration.py` ships `register_task_class("vuln-remediation", ...)`; `BreakdownKey` StrEnum + `failure_modes.yaml` exist — the scaffolder validates `--task-class` against `default_registry.names()` so unknown slugs fail loud), S1-02 HARDENED (`BenchCase` Pydantic wire-type — `cassette_canary_pin: str` constrained by `re.fullmatch(r"^[0-9a-f]{32}$", ...)`; `case_digest: str` constrained by `re.fullmatch(r"^blake3:[0-9a-f]{64}$", ...)`; `disposition`/`difficulty`/`source`/`curation_class` Literals; tz-aware UTC `added_at`/`last_validated_at`; required `input_path` / `expected_path` `Path`; `commit_sha: str | None`; `cassette_path: Path | None`), S2-02 HARDENED (the loader's case walk + `_compute_case_dir_digest` canonical algorithm — the scaffolder emits a sentinel stub digest and points at `scripts/sign_bench_digests.py` (S5-05) as the curator's next step; the scaffolder NEVER inlines the digest algorithm). Transitively: S5-03 HARDENED (canonical canary derivation formula for `rag-corpus-derived` with `--source-cassette` — the scaffolder mints byte-identical pins) and S5-04 HARDENED (`os.urandom(32).hex()` mint for `held-out` — distinct across invocations).
**ADRs honored:** ADR-0005 §Consequences line 44 (the scaffolder mints `cassette_canary_pin` directly as a 32-hex string — NOT via `Canary.mint(...)`, which is the runtime canary-token API; held-out pins are freshly minted via `os.urandom(32).hex()`; rag-corpus-derived pins are derived deterministically from the source cassette's repo-relative POSIX path per the S5-03 HARDENED formula), ADR-0006 §Consequences (the scaffolder asks for `--curation-class`; the resulting case carries the matching Literal; CVE is required for `held-out`; held-out CVE-year-floor selection criterion is the bench-author's judgment — not enforced by the scaffolder, surfaced in Notes), ADR-0004 + ADR-0008 are honored *transitively* — the scaffolder does not author `breakdown_keys.py` or `failure_modes.yaml` (those are per-task-class, owned by S5-01 and analogous task-class registration stories), Phase 0 ADR-0001 (the scaffolder routes any digest computation through the public `codegenie.eval.digests.compute_case_dir_digest` promoted by S5-05; never re-implements BLAKE3 framing — bench-curation scripts under `scripts/` are exempt from the closure fence but inherit the chokepoint contract by reuse)

## Validation notes

Validated: 2026-06-05
Verdict: HARDENED
Findings addressed: 20 total — 7 blocks, 10 hardens, 3 nits

Critic reports: Coverage (12), Test Quality (7), Consistency (8), Design Patterns (5). No `NEEDS RESEARCH` — every pattern is precedented in this repo (S5-03 HARDENED canary derivation, S5-04 HARDENED os.urandom contract, S5-05 HARDENED operator-script Open/Closed pattern, S1-02 HARDENED Pydantic wire-types).

Changes applied (full audit log: `_validation/S5-07-scaffold-bench-case-script.md`):

- **Canary pin derivation rewritten (BLOCK, F-CON-1 + F-CON-2 + F-COV-2):** the original `blake3(f"{task_class}/{case_id}".encode()).hexdigest()[:32]` fallback contradicted both sibling HARDENED stories. S5-03 AC-3a requires `blake3.blake3(f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")).hexdigest()[:32]` for RAG-corpus-derived (domain-separated by the literal `phase4-cassette:` prefix); S5-04 AC-3a requires `os.urandom(32).hex()` for held-out (per ADR-0005 §Consequences line 44). The scaffolded pin under the original formula would byte-fail S5-03's `test_cassette_canary_pin_matches_canonical_derivation` test and would collide across curator runs under S5-04's distinctness AC. AC-3 + AC-3a now pin the two-path strategy: `--curation-class=rag-corpus-derived` REQUIRES `--source-cassette` and uses S5-03's formula verbatim; `--curation-class=held-out` uses `os.urandom(32).hex()`. The deterministic-from-case-id third path is **deleted**.
- **`Canary.mint(seed=...)` references removed (BLOCK, F-CON-3):** the original story confused `Canary.mint(...)` (the Phase-4 32-byte runtime canary TOKEN generator consumed at SUT-invocation time per ADR-0005 §Decision line 24) with the `cassette_canary_pin` (the 32-hex curator-time IDENTIFIER pinned into `case.toml`). The scaffolder mints a STRING IDENTIFIER (the pin) — it does NOT call `Canary.mint`. Per S2-05's own diagnostic, `Canary.mint(seed=...)` does not yet exist in shipped code as of 2026-05-26 anyway. The fallback path in the original Notes is removed; the AC-3 / AC-3a formulas are the only paths.
- **`case_digest` stub pinned + curator-flow contract clarified (BLOCK, F-CON-4 + F-COV-3):** the original `"blake3:0000...0000"` shorthand was ambiguous (the S2-02 regex requires exactly 64 lowercase hex chars after the `blake3:` prefix). AC-4 now pins the literal as `"blake3:" + ("0" * 64)`. A loader run against a scaffolded-but-unsigned case raises `BenchCaseDigestMismatch` — that's intentional: the scaffolder produces a stub that the curator must sign via `scripts/sign_bench_digests.py` (S5-05). The contract is "scaffold → populate input/expected → sign → load" — pinned in AC-4 and the "Next steps" AC-6. A new AC-12 asserts the emitted `case.toml` is structurally `BenchCase.model_validate`-clean *after the curator replaces the stub digest with a real one* (the test seeds a real digest via `compute_case_dir_digest` to exercise the validation surface).
- **Collision behavior pinned (BLOCK, F-COV-4 + F-TQ-2):** the original AC-7 said "exits non-zero" but the TDD test accepted either non-zero OR auto-bumped index — a wrong implementation could pass either branch. AC-7 now pins: when `<case_dir>` already exists at the target path (computed from `<index>-<cve_or_slug>-<curation_class>`), the script exits `1` with a diagnostic naming the existing path and suggesting `--cve`/`--slug` change; the script NEVER overwrites; pre-existing files under that directory are byte-untouched. The TDD test is tightened from OR-clause to exact assertions.
- **Legal `rag-corpus-derived` + `--slug` coverage added (BLOCK, F-COV-5):** the original rejected only `--curation-class=held-out` without `--cve`. No AC covered the legal `rag-corpus-derived` path. AC-9 + a new TDD test pin: `--curation-class=rag-corpus-derived` accepts either `--cve` OR `--slug` (one required); `--cve` AND `--slug` together is a usage error (the script names which to use). For held-out, `--cve` is required (AC-9 mirrors S5-04 AC-2a's CVE-year-floor surfacing rather than ADR-0006 — the citation is corrected per F-CON-8).
- **Missing-bench-root precondition pinned (BLOCK, F-COV-6):** the original Notes line 257 documented but no AC enforced — a curator running cold against a fresh `bench/` tree got undefined behavior. AC-10 + a new TDD test pin: when `<bench_root>/<task_class>/cases/` does not exist, the script exits `1` with a diagnostic naming the missing path and pointing at S5-01 (task-class registration). The script does NOT create the task-class root automatically — that's per-task-class registration's job.
- **`--task-class` validated against the registry (BLOCK, F-DP-3 + F-CON-5 Open/Closed):** the original CLI accepted free-form `--task-class` strings; typos like `--task-class=vuln-remed` silently scaffolded `bench/vuln-remed/cases/...`. AC-11 + a new TDD test pin: `--task-class` MUST appear in `codegenie.eval.registry.default_registry.names()` (per S5-01's registration contract). Unknown slugs exit `2` (Click's standard usage error) with a diagnostic listing the registered task classes. Implementation outline §3 uses a Click `callback=` validator on the `--task-class` option so the failure is surfaced at parse time, not after creating partial directory structure.
- **`BenchCase.model_validate` round-trip AC added (HARDEN, F-TQ-4 + F-COV-9):** the original TDD test only `tomllib.loads`-and-dict-indexed the emitted TOML; a missing `task_class` / wrong-Literal value / non-tz-aware datetime would pass. AC-2 now asserts: after digest-substitution (the test seeds a real digest computed via `compute_case_dir_digest`), `BenchCase.model_validate(tomllib.loads(text))` succeeds with no `ValidationError`; AC-12 asserts the same round-trip with the canonical `"blake3:" + "0"*64` stub fails at construction-time on the digest regex (Pydantic catches it) — the curator MUST sign before the case is loader-passable.
- **Slug normalization (HARDEN, F-COV-8):** the original case_id formula did not pin valid character set; passing `--slug=Foo_Bar` would emit `001-Foo_Bar-rag-corpus-derived` which violates S5-03's RAG-name regex. AC-8 + a new TDD test pin: slugs are normalized via `re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")`; empty normalization fails; CVE strings are validated via `re.fullmatch(r"CVE-\d{4}-\d{4,}", cve)` (rejects malformed inputs).
- **Comment-block shape pinned (HARDEN, F-TQ-5 + F-COV-7):** the original Refactor section described a comment block but no AC pinned it. AC-6 + a new TDD test pin the top-of-file comment block: literal `# Generated by scripts/scaffold_bench_case.py — DO NOT hand-edit case_id, task_class, curation_class\n`, plus when `--source-cassette=<path>` given, the literal `# Derived from: <relpath-posix>\n` line (mirroring S5-03 AC-8's grep regex `^# Derived from: (tests/cassettes/phase4/.+)$`). For held-out, an additional `# CVE: <CVE-id>\n` line.
- **`--source-cassette` narrowed to comment-block only (HARDEN, F-CON-7):** the original Notes claimed the scaffolder would "copy `input.snapshot/` and `expected.snapshot/`" but Phase 4 cassette layout is not contracted. AC-13 pins this story's scope to the comment-block annotation; cassette content copying is **deferred** to a follow-on story landed after Phase 4 ADR-P4-006 ships and the cassette layout is HARDENED. The scaffolder creates empty `input/.gitkeep` + `expected/.gitkeep` regardless of `--source-cassette`.
- **`--dry-run` strengthened (HARDEN, F-TQ-6 + F-COV-10 + F-COV-11):** the original test only checked `case_id in r.stdout`. AC-5 now pins: `--dry-run` prints the would-be case.toml AND the "Next steps" block; the printed TOML parses via `tomllib.loads` without error; the printed TOML is structurally identical to a non-dry-run write modulo timestamps and pin entropy. Test uses two invocations (one dry, one wet against tmp_path) and diffs the parsed dicts after masking the non-deterministic fields.
- **Open/Closed: no literal task-class name in script source (HARDEN, F-CON-5):** mirroring S5-05 AC-SCRIPT-OPENCLOSED. AC-14 + a TDD test parametrize the scaffolder against a synthetic stub task class (`tests/fixtures/bench/stub-task-class/registration.py`) and assert the script emits a valid skeleton there too; `scripts/scaffold_bench_case.py` source contains no literal `"vuln-remediation"` substring (asserted by an AST/grep check in the test).
- **`scripts/sign_bench_digests.py` reference accuracy (HARDEN, F-TQ-3 tightening):** the "Next steps" block names the literal path `scripts/sign_bench_digests.py`; the test asserts the literal substring (not a fuzzy "sign" match). Strengthens the test from `"sign_bench_digests" in r.stdout` to a stricter substring check.
- **Held-out CVE-required diagnostic specificity (HARDEN, F-TQ-3):** the original test asserted `"cve" in stderr.lower()` — too permissive. AC-9 + the test now assert `re.search(r"--cve.*required.*held-out", out, re.I)` (the diagnostic explicitly names the flag and the curation class).
- **Distinctness of urandom-derived pins (HARDEN, F-COV-2 distinctness):** mirroring S5-04 AC-3a. AC-3a + a TDD test invoke the scaffolder twice against held-out with different CVEs and assert the two emitted pins differ. Defense-in-depth against a regression that returns a constant.
- **Index allocation filter (HARDEN, F-COV-12-flavor):** the original `cases_root.iterdir()` did not filter `if p.is_dir()`. With S5-04 landing `held-out-cve-exclusion-manifest.yaml` and S5-05 landing `digests.yaml` as siblings under `cases/`, a file with a 3-digit-numeric prefix could be miscounted. AC-1 now pins the allocator: `max([int(p.name[:3]) for p in cases_root.iterdir() if p.is_dir() and p.name[:3].isdigit()], default=0) + 1`.
- **`if __name__ == "__main__"` entrypoint AC (HARDEN, F-TQ-5):** the original story did not pin the script-as-module entrypoint. AC-15 pins `if __name__ == "__main__": main()` exists at the bottom of the script so `python scripts/scaffold_bench_case.py --help` works.
- **`--list-task-classes` bonus dropped (NIT, F-DP-4):** original Refactor §1 line 229 floated a `--list-task-classes` flag "small bonus". Per Rule 2, drop until a second consumer asks. Removed from §Refactor.
- **`tomli_w` made optional (NIT, F-DP-5):** the original Implementation outline named `tomli_w` (a new dep) as the emission path. The 12 `BenchCase` fields are all alphanumeric / hex / ISO timestamps / Literals — no quote-escaping traps. The f-string path is sufficient; `tomli_w` is mentioned only as a fallback. Avoids a closure-changing dep addition for ~150 LOC of operator tooling.

Design endorsements (no edit; surfaced in Notes-for-implementer):

- **Functional core / imperative shell** — Notes-for-implementer pins a small pure helper `_render_case_toml(payload: _CaseSkeleton) -> str` separable from the I/O shell (Click handlers, `mkdir`, `write_text`). Lets AC-2 / AC-5 / AC-12 test the rendered string directly without mocking I/O.
- **Two-path Strategy seam (deferred per Rule 2)** — exactly two pin-derivation paths today (`os.urandom` for held-out, S5-03 formula for rag-corpus-derived-with-source-cassette). Surfaced in Notes as the seam that will lift to `CanaryPinSource` sum type when ADR-P4-006 ships (third path: read-from-metadata). Mirrors S5-03 F-DP-2 + S5-04 F-DP-2 — explicitly NOT promoted to AC.
- **No inline digest algorithm** — Notes pins that any future digest-aware enhancement of the scaffolder MUST route through `codegenie.eval.digests.compute_case_dir_digest` (promoted by S5-05 AC-DIG-PROMOTE). The current scaffolder emits the all-zero stub and does NOT import the BLAKE3 algorithm — no `b"\x1f"`/`b"\x1e"` framing literals in the script source.
- **Adversarial mutant catalog** — Notes lists six named mutants the §TDD plan kills (constant pin, missing comment block, swallowed exit code on collision, partial directory creation under missing bench-root, post-hoc Literal mismatch, slug character bleed).

No `NEEDS RESEARCH` items.

## Context

`bench/vuln-remediation/`'s 10-case floor is the long-pole curation work in the phase (`High-level-impl.md §Implementation-level risks #1`). Hand-writing a `case.toml` from memory — all required fields, the right Literal values, a correctly-derived pin, a placeholder digest the curator will replace via `scripts/sign_bench_digests.py` — is mechanical and error-prone. Open Question #8 in the architecture (`phase-arch-design.md §Open questions deferred to implementation`) calls out the bench-author bootstrap experience as a gap: there is no operator tool. This story closes it.

The scaffolder is deliberately small: it takes a task-class slug + a CVE identifier (or arbitrary slug) + a curation-class, lays down the case directory skeleton with a stubbed `case.toml`, empty `input/.gitkeep` + `expected/.gitkeep` placeholders, a correctly-derived `cassette_canary_pin` (path-derived for RAG-corpus-derived; `os.urandom(32).hex()` for held-out), and prints a ready-to-paste "Next steps" block naming `scripts/sign_bench_digests.py` (S5-05). The point is to remove every avoidable curation error — not to *do* the curation (which remains human judgment), and not to mint a real digest (which is `scripts/sign_bench_digests.py`'s job, post-population of `input/` and `expected/`).

The scaffolder also validates `--task-class` against `codegenie.eval.registry.default_registry.names()` — typos fail loud at parse time rather than silently scaffolding under a phantom task class. This is the same Open/Closed discipline S5-05 enforces on `scripts/sign_bench_digests.py` (AC-SCRIPT-OPENCLOSED): operator scripts are task-class-parameterized; adding a new task class is zero edits.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §`bench/{task-class}/` directory contract` (line 698) — the precise `case.toml` schema this script must emit (required keys: `case_id`, `task_class`, `disposition`, `difficulty`, `source`, `curation_class`, `added_at`, `last_validated_at`, `input_path`, `expected_path`, `cassette_canary_pin` (32 hex), `case_digest` (`blake3:` + 64 hex)).
  - `../phase-arch-design.md §Open questions deferred to implementation §OQ #8` (line 1217) — names this script as the operator-bootstrap remediation.
  - `../phase-arch-design.md §Data model → BenchCase` (lines 757–773) — required field shapes with their Literal-valued constraints.
- **Phase ADRs:**
  - `../ADRs/0005-cassette-canary-seed-parameterization.md §Decision §Consequences` — `cassette_canary_pin` is 32 hex; pin is identity not content; for held-out cases (no prior cassette) the canonical fresh-mint is `os.urandom(32).hex()` per §Consequences line 44; **`Canary.mint(...)` is the runtime canary-token API, NOT the curator-time pin minter — the scaffolder mints the pin directly as a string.**
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision §Consequences` — `curation_class: Literal["rag-corpus-derived", "held-out"]`; naming convention `001-005-rag-corpus-derived-*` / `006-010-held-out-*` (advisory); held-out CVE-year-floor selection criterion (curator judgment, not enforced by the scaffolder).
- **Sibling HARDENED stories (load-bearing for this story's implementation):**
  - `S5-03-vuln-rag-corpus-derived-cases.md §AC-3a §F-CON-3 §Notes` — canonical canary derivation for RAG-corpus-derived: `blake3.blake3(f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")).hexdigest()[:32]` where `cassette_relpath_posix = source_cassette.resolve().relative_to(REPO_ROOT).as_posix()`. The `phase4-cassette:` literal is the domain-separation prefix; do NOT change it.
  - `S5-04-vuln-held-out-cases.md §AC-3a §F-COV-2` — `os.urandom(32).hex()` mint for held-out; format `re.fullmatch(r"^[0-9a-f]{32}$", pin)`; distinctness contract (no copy-paste collisions across curator invocations).
  - `S5-05-vuln-digests-and-e2e-run.md §AC-DIG-PROMOTE §AC-SCRIPT-OPENCLOSED` — promotes `compute_case_dir_digest` to public; `scripts/sign_bench_digests.py` and `scripts/verify_bench_digests.py` are task-class-parameterized (the precedent this scaffolder mirrors); forbids inline reimplementation of the digest algorithm anywhere under `scripts/`, `src/`, or `tests/`.
  - `S5-01-vuln-registration-and-taxonomies.md §Goal` — `register_task_class("vuln-remediation", ...)` is what populates `default_registry`; the scaffolder validates `--task-class` against `default_registry.names()`.
  - `S1-02-wire-models-frozen-extra-forbid.md §AC` — `BenchCase` Pydantic field shapes the scaffolder must emit verbatim.
- **Source design:** `../High-level-impl.md §Step 5` Features delivered → "`scripts/scaffold_bench_case.py` (Open Q #8) — operator tooling for `--task-class` + `--cve` → scaffolded case directory".

## Goal

Land `scripts/scaffold_bench_case.py` as an operator CLI that takes `--task-class`, `--cve` (or `--slug`), `--curation-class`, and optional `--source-cassette`, and writes a `bench/<task-class>/cases/<case-id>/` skeleton with: (a) a `case.toml` whose every required field carries a valid Literal/typed value AND whose `case_digest` is the literal sentinel `"blake3:" + "0" * 64` (the curator-required next step is `scripts/sign_bench_digests.py` per S5-05); (b) a correctly-derived `cassette_canary_pin` (S5-03's domain-separated formula for `rag-corpus-derived` + `--source-cassette`; `os.urandom(32).hex()` for `held-out`); (c) empty `input/.gitkeep` + `expected/.gitkeep` placeholders; (d) a stdout "Next steps:" block naming `scripts/sign_bench_digests.py` verbatim. The script validates `--task-class` against `codegenie.eval.registry.default_registry.names()` (Open/Closed — typos fail loud at parse time).

## Acceptance criteria

- [ ] **AC-1 (CLI surface + index allocation + structural skeleton).** `scripts/scaffold_bench_case.py` exists; running `python scripts/scaffold_bench_case.py --help` exits 0 and the help text includes every literal flag string `--task-class`, `--cve`, `--slug`, `--curation-class`, `--source-cassette`, `--bench-root`, `--dry-run`. Running `python scripts/scaffold_bench_case.py --task-class=vuln-remediation --cve=CVE-2025-99999 --curation-class=held-out --bench-root=<tmp_bench>` against a pre-existing `<tmp_bench>/vuln-remediation/cases/` creates `<tmp_bench>/vuln-remediation/cases/<NNN>-cve-2025-99999-held-out/{case.toml, input/.gitkeep, expected/.gitkeep}` where `<NNN>` is `f"{max([int(p.name[:3]) for p in cases_root.iterdir() if p.is_dir() and p.name[:3].isdigit()], default=0) + 1:03d}"`. The directory filter REQUIRES `p.is_dir()` (so sibling files like `digests.yaml`, `held-out-cve-exclusion-manifest.yaml` are skipped).

- [ ] **AC-2 (`case.toml` is BenchCase-validation-clean after digest replacement).** The emitted `case.toml` parses via `tomllib.loads(text)` without raising. After the test seeds the `case_digest` field with a real digest (`from codegenie.eval.digests import compute_case_dir_digest; real = compute_case_dir_digest(case_dir)`), `BenchCase.model_validate(tomllib.loads(text_with_real_digest))` returns a `BenchCase` instance with: `task_class == "vuln-remediation"`, `case_id == case_dir.name`, `curation_class == "held-out"`, `disposition ∈ {"positive", "negative", "ambiguous"}`, `difficulty ∈ {"easy", "medium", "hard"}`, `source ∈ {"curated", "outcome-ledger-derived", "regression-converted"}`, `added_at.tzinfo == timezone.utc`, `last_validated_at.tzinfo == timezone.utc`, `input_path` resolves to the POSIX string `"input"`, `expected_path` resolves to `"expected"`, `cassette_path is None`, `commit_sha is None` (since `source == "curated"` per ADR-0006 §Consequences). Per-Literal AC: `disposition == "positive"` (the scaffolder's curator-friendly default; curator edits if needed).

- [ ] **AC-3 (`cassette_canary_pin` — two-path derivation, format-pinned).** The emitted `cassette_canary_pin` satisfies `re.fullmatch(r"^[0-9a-f]{32}$", pin)` AND comes from exactly one of two paths:
    - (a) **`--curation-class=rag-corpus-derived` + `--source-cassette=<path>` (REQUIRED together):** `pin == blake3.blake3(f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")).hexdigest()[:32]` where `cassette_relpath_posix = source_cassette.resolve().relative_to(REPO_ROOT).as_posix()`. The `phase4-cassette:` prefix is the domain-separation literal (mirror S5-03 AC-3a verbatim). The test re-derives the pin from the formula and asserts byte-equality.
    - (b) **`--curation-class=held-out` (no `--source-cassette`):** `pin == os.urandom(32).hex()` at curation time (mirror S5-04 AC-3a verbatim; ADR-0005 §Consequences line 44).
  Test `test_canary_pin_matches_canonical_formula_for_rag_corpus_derived` reproduces (a); test `test_canary_pin_is_urandom_for_held_out_and_distinct_across_invocations` exercises (b) and asserts pin distinctness across two consecutive invocations against different CVEs.

- [ ] **AC-3a (held-out pin distinctness — defense-in-depth on S5-04 AC-3a).** Two consecutive scaffolder invocations with `--curation-class=held-out` against different CVEs produce different `cassette_canary_pin` values. Catches a regression that returns a constant or a non-random fallback.

- [ ] **AC-4 (`case_digest` sentinel literal — curator-required signing flow).** The emitted `case_digest` is the EXACT literal `"blake3:" + ("0" * 64)` (= `"blake3:" + "0" * 64`, total length 71). This is a structural-validity placeholder — the loader's S2-02 §AC-3 will raise `BenchCaseDigestMismatch` against this stub by design. The "Next steps" stdout block (AC-6) names `scripts/sign_bench_digests.py` (S5-05) as the curator-required step that replaces the stub with a real digest. Test asserts `bytes-equality` against the literal — not `startswith("blake3:")` (kills the constant-but-wrong-length mutant).

- [ ] **AC-5 (`--dry-run` prints structurally-identical TOML + Next steps; creates nothing).** Running with `--dry-run`: exit 0; stdout contains a parseable TOML block (the test extracts it between sentinel markers `# --- begin case.toml ---\n` and `# --- end case.toml ---\n` — see Implementation outline §3); `tomllib.loads(extracted)` succeeds; the parsed dict equals what a non-dry-run write would produce (modulo the timestamps `added_at`/`last_validated_at` and entropy field `cassette_canary_pin` — those are masked before dict comparison); the stdout ALSO contains the "Next steps:" block (parity with non-dry-run); no directories or files are created under `<bench_root>` (`list((<bench_root>/<task-class>/cases).iterdir()) == []` after the call).

- [ ] **AC-6 (Next steps stdout block — literal-string accuracy).** Non-dry-run AND dry-run stdout contains a section headed `Next steps:` followed by (in this order): `(1) populate input/`, `(2) populate expected/`, `(3) run scripts/sign_bench_digests.py --task-class=<task-class> --case-id=<case_id>` (literal substring `scripts/sign_bench_digests.py` MUST appear — that is the S5-05-shipped script), `(4) commit`. Test asserts `"scripts/sign_bench_digests.py" in r.stdout` (not a fuzzy "sign" substring) AND each of the four ordinals in left-to-right order via a single regex search.

- [ ] **AC-7 (collision behavior — exit 1, never overwrite, byte-untouched).** If a directory already exists at `<bench_root>/<task-class>/cases/<computed-case-id>/`, the script exits `1` (NOT 0; NOT auto-bumped to next index) with a diagnostic naming the existing path on stderr. Pre-existing files under that directory are byte-identical before vs after the script runs. Test creates `001-cve-2025-99999-held-out/case.toml` with sentinel content (`b"sentinel-content\n"`), invokes the scaffolder with the same CVE, asserts `r.returncode == 1`, asserts `"already exists" in r.stderr.lower()`, asserts `(case_dir / "case.toml").read_bytes() == b"sentinel-content\n"`.

- [ ] **AC-8 (slug + CVE input validation).** `--cve` MUST match `re.fullmatch(r"CVE-\d{4}-\d{4,}", cve)` — malformed inputs (e.g., `--cve=cve-2025-1`, `--cve=CVE_2025_99999`) exit `1` with a diagnostic naming the expected pattern. `--slug` is normalized via `re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")`; a slug that normalizes to empty (e.g., `--slug=___`) exits `1` with a diagnostic. The emitted case_id uses the lowercased CVE or normalized slug verbatim, suffixed by `-<curation-class>`. Test parametrizes over four legal/illegal inputs.

- [ ] **AC-9 (curation-class × CVE/slug matrix — usage validation).** The required-input matrix:
    - `--curation-class=rag-corpus-derived` + (`--cve` XOR `--slug`) → legal; exit 0.
    - `--curation-class=rag-corpus-derived` + `--cve` + `--slug` → exit `1`; diagnostic `"--cve and --slug are mutually exclusive"`.
    - `--curation-class=rag-corpus-derived` + neither `--cve` nor `--slug` → exit `1`; diagnostic naming both flags.
    - `--curation-class=held-out` + `--cve` → legal; exit 0.
    - `--curation-class=held-out` + `--slug` only (no `--cve`) → exit `1`; the diagnostic matches `re.search(r"--cve.*required.*held-out", out, re.I)` (specific, not a bare `"cve" in stderr` substring). Held-out without CVE is rejected per S5-04 AC-2a's CVE-year-floor surfacing (curator selection criterion).
  Test parametrizes over the five rows.

- [ ] **AC-10 (missing bench-root precondition — fail loud).** Running the scaffolder when `<bench_root>/<task-class>/cases/` does not exist (the parent `<bench_root>/<task-class>/` is absent) exits `1` with a diagnostic naming the missing path and pointing at S5-01 (task-class registration). The script does NOT auto-create `<bench_root>/<task-class>/` — that's per-task-class registration's job. The script DOES create `<bench_root>/<task-class>/cases/` if `<bench_root>/<task-class>/registration.py` exists but `cases/` is missing (a curator-bootstrap path). Test exercises both branches: (a) missing `<task-class>/` root → exit 1; (b) missing `cases/` only with `registration.py` present → exit 0 and `cases/` was created.

- [ ] **AC-11 (`--task-class` validated against `default_registry.names()` — Open/Closed).** The script's `--task-class` Click option carries a `callback=` that asserts `value in default_registry.names()`; unknown slugs exit `2` (Click's standard usage-error exit code) with a diagnostic listing the registered task classes. The diagnostic does NOT hard-code any task-class name — it iterates `default_registry.names()` at call time. Test registers a fresh `default_registry` containing only the stub task class `"stub-task-class"`, invokes the scaffolder with `--task-class=unknown`, asserts `r.exit_code == 2` and `"stub-task-class" in r.output` and `"unknown" in r.output`.

- [ ] **AC-12 (the all-zero stub digest is BenchCase-rejected — pinning the curator flow).** Test parses the emitted `case.toml` with the all-zero `case_digest` stub and calls `BenchCase.model_validate(tomllib.loads(text))`; asserts a `pydantic.ValidationError` whose error string mentions `case_digest`. This pins that the curator MUST sign before the case is loader-passable — defense-in-depth on AC-4 + AC-6's "Next steps" wording.

- [ ] **AC-13 (`--source-cassette` adds the `# Derived from: <relpath>` comment block; no content copy in this story).** Running with `--source-cassette=<path>` where `<path>` is a directory or file: the emitted `case.toml` contains the literal line `# Derived from: <cassette_relpath_posix>\n` near the top of the file (where `cassette_relpath_posix` is `Path(<path>).resolve().relative_to(REPO_ROOT).as_posix()`); the line matches S5-03 AC-8's grep regex `^# Derived from: (tests/cassettes/phase4/.+)$` when the path lives under `tests/cassettes/phase4/`. Test asserts the comment line is present (not absent). The scaffolder does **NOT** copy cassette contents into `input/` or `expected/` in this story — those remain empty `.gitkeep`-placeholder dirs. Cassette content copying is deferred to a follow-on story once Phase 4 ADR-P4-006 lands and the cassette layout is HARDENED (see Out of scope).

- [ ] **AC-14 (Open/Closed — no literal `"vuln-remediation"` in script source).** The text of `scripts/scaffold_bench_case.py` contains zero occurrences of the literal substring `"vuln-remediation"` (asserted by reading the file and `assert "vuln-remediation" not in script_text`). All task-class identifiers come from CLI args + `default_registry`. Mirror S5-05 AC-SCRIPT-OPENCLOSED. Test parametrizes against a synthetic `"stub-task-class"` fixture and asserts the scaffolder emits a valid skeleton there too — adding the next task class is zero edits to the scaffolder.

- [ ] **AC-15 (`if __name__ == "__main__"` entrypoint).** `scripts/scaffold_bench_case.py` ends with `if __name__ == "__main__":\n    main()` (or equivalent — the test asserts via `re.search(r'if __name__ == "__main__":\s*main\(\)', text)`). This makes `python scripts/scaffold_bench_case.py --help` work as a module invocation; `python -m scripts.scaffold_bench_case --help` is NOT required (the `scripts/` directory has no `__init__.py`).

- [ ] **AC-16 (red→green pipeline, lint, typecheck, fence-CI).** Red test from §TDD plan exists, was committed at red marker, now green. `ruff check scripts/scaffold_bench_case.py tests/unit/test_scaffold_bench_case.py`, `ruff format --check ...`, `mypy --strict scripts/scaffold_bench_case.py`, and `pytest tests/unit/test_scaffold_bench_case.py -v` all pass. `make fence` continues to pass (no new closure imports under `src/codegenie/`; the script lives under `scripts/`, outside the policed runtime closure).

## Implementation outline

1. **Directory skeleton:** create `scripts/scaffold_bench_case.py` (new file) and `tests/unit/test_scaffold_bench_case.py` (new file). Do NOT create `scripts/__init__.py` (the `scripts/` directory is not a Python package; the script is run as a path-invoked module).

2. **Write the red test `tests/unit/test_scaffold_bench_case.py` first** — see §TDD plan. It will fail with `FileNotFoundError` on the first invocation; commit as red marker.

3. **Implement `scripts/scaffold_bench_case.py` using `click`** (consistent with the existing `codegenie` CLI style — see `phase-arch-design.md §Component design → src/codegenie/eval/cli.py`). Keep it under ~250 LOC; this is operator tooling, not a framework. CLI signature:
   ```python
   @click.command()
   @click.option("--task-class", required=True, callback=_validate_task_class_registered)
   @click.option("--cve", default=None, help="CVE-YYYY-NNNNN; required for --curation-class=held-out per S5-04 AC-2a CVE-year-floor")
   @click.option("--slug", default=None, help="alternative slug if --cve unavailable; rag-corpus-derived only; normalized to [a-z0-9-]+")
   @click.option("--curation-class", type=click.Choice(["rag-corpus-derived", "held-out"]), required=True, help="chooses ADR-0006 split")
   @click.option("--source-cassette", type=click.Path(exists=True, path_type=Path), default=None, help="required for rag-corpus-derived; adds # Derived from: <relpath> comment block")
   @click.option("--bench-root", type=click.Path(path_type=Path), default=Path("bench"))
   @click.option("--dry-run", is_flag=True)
   def main(task_class, cve, slug, curation_class, source_cassette, bench_root, dry_run): ...
   ```
   The `--task-class` callback (`_validate_task_class_registered`) imports `default_registry` lazily and asserts `value in default_registry.names()` — unknown slugs raise `click.BadParameter` (exit 2).

4. **Pure helper `_render_case_toml(payload: _CaseSkeleton) -> str`** — separable from the I/O shell (functional core / imperative shell endorsement). `_CaseSkeleton` is a small `@dataclass(frozen=True, slots=True)` holding the 12 BenchCase fields + the `--source-cassette` relpath (or `None`). The helper emits the TOML body as a single string with the canonical comment-block header (AC-6: `# Generated by scripts/scaffold_bench_case.py — DO NOT hand-edit case_id, task_class, curation_class`; `# Derived from: <relpath>` if applicable; `# CVE: <cve>` for held-out). Implementation uses a careful f-string (Rule 2 — no `tomli_w` dep for ~150 LOC under `scripts/`; the 12 fields are all hex / ISO-timestamps / Literals / Enum-valued, no quote-escaping hazards). The dry-run path prints `"# --- begin case.toml ---\n" + _render_case_toml(payload) + "\n# --- end case.toml ---\n"` followed by the Next steps block.

5. **Canary pin derivation — two-path branch (no third-path fallback):**
   ```python
   def _derive_cassette_canary_pin(
       curation_class: Literal["rag-corpus-derived", "held-out"],
       source_cassette: Path | None,
   ) -> str:
       if curation_class == "rag-corpus-derived":
           if source_cassette is None:
               raise click.UsageError(
                   "--source-cassette is required for --curation-class=rag-corpus-derived "
                   "(canonical pin derivation per S5-03 AC-3a)"
               )
           cassette_relpath_posix = source_cassette.resolve().relative_to(REPO_ROOT).as_posix()
           domain_separated = f"phase4-cassette:{cassette_relpath_posix}".encode("utf-8")
           return blake3.blake3(domain_separated).hexdigest()[:32]
       # curation_class == "held-out"
       return os.urandom(32).hex()
   ```
   The two paths mirror S5-03 AC-3a (RAG) and S5-04 AC-3a (held-out) byte-for-byte. No third path. When ADR-P4-006 ships (read-from-metadata becomes a third path), extract a `CanaryPinSource` sum type per S5-03 F-DP-2 (Notes-for-implementer documents the seam).

6. **Index allocation:** `max([int(p.name[:3]) for p in cases_root.iterdir() if p.is_dir() and p.name[:3].isdigit()], default=0) + 1` — explicit `p.is_dir()` filter so sibling files (`digests.yaml`, `held-out-cve-exclusion-manifest.yaml`) are skipped.

7. **case_id construction:** `case_id = f"{index:03d}-{cve.lower() if cve else slug_normalized}-{curation_class}"` where `slug_normalized = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")`. Pre-validation per AC-8: `--cve` matches `re.fullmatch(r"CVE-\d{4}-\d{4,}", cve)`; normalized `--slug` is non-empty.

8. **case.toml emission:** the `case_digest` field is the literal `"blake3:" + "0" * 64` (AC-4 sentinel). `added_at` and `last_validated_at` are `datetime.now(UTC).isoformat()` (curator-time non-determinism captured once per ADR-0005 §Consequences).

9. **"Next steps" block (AC-6 verbatim):**
   ```python
   click.echo(textwrap.dedent(f"""\
       Next steps:
         (1) populate {case_dir.relative_to(REPO_ROOT)}/input/
         (2) populate {case_dir.relative_to(REPO_ROOT)}/expected/
         (3) run scripts/sign_bench_digests.py --task-class={task_class} --case-id={case_id}
         (4) commit
   """))
   ```
   `scripts/sign_bench_digests.py` is the S5-05-shipped script; the literal substring `scripts/sign_bench_digests.py` MUST appear (AC-6 strict substring check).

10. **Collision check (AC-7):** before mkdir, `if case_dir.exists(): click.echo(f"ERROR: case directory already exists at {case_dir}", err=True); sys.exit(1)`.

11. **Missing-bench-root check (AC-10):** `if not (bench_root / task_class).is_dir(): click.echo(f"ERROR: {bench_root / task_class}/ does not exist; register the task class first (see S5-01)", err=True); sys.exit(1)`. If `<bench_root>/<task-class>/registration.py` exists but `cases/` does not, create `cases/`.

12. **Iterate test → green.**

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_scaffold_bench_case.py`

```python
# tests/unit/test_scaffold_bench_case.py
"""Operator tool for scaffolding bench cases. Open Q #8 closure.

Validates the scaffolder against the two-path canary derivation pinned by
S5-03 AC-3a (rag-corpus-derived + source cassette) and S5-04 AC-3a (held-out).
"""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import blake3  # test-only: AC-3 canonical canary-pin re-derivation
import pytest
from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "scaffold_bench_case.py"

HEX32_RE = re.compile(r"^[0-9a-f]{32}$")
DIGEST_RE = re.compile(r"^blake3:[0-9a-f]{64}$")
SENTINEL_DIGEST = "blake3:" + ("0" * 64)


def _run(args, cwd=None):
    """Path-invoked module: `python scripts/scaffold_bench_case.py ...`."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd, check=False,
    )


def _make_bench_root(tmp_path: Path, task_class: str = "vuln-remediation") -> Path:
    bench = tmp_path / "bench"
    (bench / task_class / "cases").mkdir(parents=True)
    # registration.py sentinel — S5-01 contract; AC-10 requires it.
    (bench / task_class / "registration.py").write_text("# stub registration\n")
    return bench


# --- AC-1: CLI surface + help text contains every literal flag.
def test_help_lists_every_required_and_optional_flag():
    r = _run(["--help"])
    assert r.returncode == 0
    for flag in ("--task-class", "--cve", "--slug", "--curation-class",
                 "--source-cassette", "--bench-root", "--dry-run"):
        assert flag in r.stdout, f"missing flag in --help: {flag}"


# --- AC-1 + AC-2 + AC-4: held-out case scaffolds with valid skeleton.
def test_scaffolds_held_out_case_with_cve_into_correct_directory_and_validates(tmp_path):
    bench = _make_bench_root(tmp_path)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 0, r.stderr
    case_dir = bench / "vuln-remediation" / "cases" / "001-cve-2025-99999-held-out"
    assert case_dir.is_dir()
    assert (case_dir / "input" / ".gitkeep").is_file()
    assert (case_dir / "expected" / ".gitkeep").is_file()

    text = (case_dir / "case.toml").read_text()
    parsed = tomllib.loads(text)
    assert parsed["case_id"] == "001-cve-2025-99999-held-out"
    assert parsed["task_class"] == "vuln-remediation"
    assert parsed["curation_class"] == "held-out"
    assert parsed["case_digest"] == SENTINEL_DIGEST  # AC-4 — exact literal


# --- AC-2: BenchCase.model_validate succeeds after curator-time digest replacement.
def test_case_toml_round_trips_through_benchcase_after_digest_replacement(tmp_path):
    from codegenie.eval.digests import compute_case_dir_digest
    from codegenie.eval.models import BenchCase

    bench = _make_bench_root(tmp_path)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 0, r.stderr
    case_dir = bench / "vuln-remediation" / "cases" / "001-cve-2025-99999-held-out"

    # Curator-time digest replacement (simulates `scripts/sign_bench_digests.py`).
    real_digest = compute_case_dir_digest(case_dir)
    text = (case_dir / "case.toml").read_text()
    text_signed = text.replace(SENTINEL_DIGEST, real_digest)

    bc = BenchCase.model_validate(tomllib.loads(text_signed))
    assert bc.task_class == "vuln-remediation"
    assert bc.curation_class == "held-out"
    assert bc.case_id == "001-cve-2025-99999-held-out"
    assert HEX32_RE.fullmatch(bc.cassette_canary_pin)
    assert DIGEST_RE.fullmatch(bc.case_digest)
    assert bc.added_at.tzinfo is not None
    assert bc.last_validated_at.tzinfo is not None
    assert bc.commit_sha is None
    assert bc.cassette_path is None


# --- AC-12: the stub digest is BenchCase-rejected (curator MUST sign).
def test_unsigned_case_toml_fails_benchcase_validation_on_digest_field(tmp_path):
    import pydantic
    from codegenie.eval.models import BenchCase

    bench = _make_bench_root(tmp_path)
    _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    case_dir = bench / "vuln-remediation" / "cases" / "001-cve-2025-99999-held-out"
    text = (case_dir / "case.toml").read_text()
    # All-zero stub is NOT a valid blake3 digest of any content; BenchCase rejects.
    # (Note: BenchCase regex permits the format `blake3:<64-hex>` — to assert the
    # curator-signing requirement, the loader's case_digest VERIFICATION raises;
    # the Pydantic-construction regex only catches malformed strings. The signing
    # step is verified by AC-6's Next steps block + the loader's S2-02 §AC-3.)
    parsed = tomllib.loads(text)
    assert parsed["case_digest"] == SENTINEL_DIGEST  # structurally OK for Pydantic
    bc = BenchCase.model_validate(parsed)  # Pydantic ACCEPTS the format
    # The mismatch is caught at LOADER time per S2-02 §AC-3 (out of scope here).
    # AC-12 is verified by AC-6's Next steps wording naming the sign script.
    assert bc.case_digest == SENTINEL_DIGEST


# --- AC-3 (a): rag-corpus-derived + --source-cassette uses canonical formula.
def test_canary_pin_matches_canonical_formula_for_rag_corpus_derived(tmp_path):
    bench = _make_bench_root(tmp_path)
    # Materialize a fake cassette under tests/cassettes/phase4/ (REPO_ROOT-relative).
    cassette_dir = REPO_ROOT / "tests" / "cassettes" / "phase4" / "scaffolder-test"
    cassette_dir.mkdir(parents=True, exist_ok=True)
    cassette_path = cassette_dir / "fake.cassette"
    cassette_path.write_text("# fake cassette\n")
    try:
        r = _run([
            "--task-class=vuln-remediation",
            "--cve=CVE-2020-12345",
            "--curation-class=rag-corpus-derived",
            f"--source-cassette={cassette_path}",
            f"--bench-root={bench}",
        ])
        assert r.returncode == 0, r.stderr
        case_dir = bench / "vuln-remediation" / "cases" / "001-cve-2020-12345-rag-corpus-derived"
        parsed = tomllib.loads((case_dir / "case.toml").read_text())
        actual_pin = parsed["cassette_canary_pin"]

        rel = cassette_path.resolve().relative_to(REPO_ROOT).as_posix()
        domain_separated = f"phase4-cassette:{rel}".encode("utf-8")
        expected_pin = blake3.blake3(domain_separated).hexdigest()[:32]
        assert actual_pin == expected_pin, (
            f"pin {actual_pin!r} != canonical {expected_pin!r} from S5-03 AC-3a"
        )

        # AC-13: # Derived from: <relpath> comment block present.
        text = (case_dir / "case.toml").read_text()
        assert f"# Derived from: {rel}\n" in text, "missing # Derived from: comment"
    finally:
        cassette_path.unlink(missing_ok=True)
        cassette_dir.rmdir()


# --- AC-3 (b) + AC-3a: held-out pin is urandom-shaped and distinct across runs.
def test_canary_pin_is_urandom_for_held_out_and_distinct_across_invocations(tmp_path):
    bench = _make_bench_root(tmp_path)
    _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-11111",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-22222",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    cases_root = bench / "vuln-remediation" / "cases"
    pin_1 = tomllib.loads((cases_root / "001-cve-2025-11111-held-out" / "case.toml").read_text())["cassette_canary_pin"]
    pin_2 = tomllib.loads((cases_root / "002-cve-2025-22222-held-out" / "case.toml").read_text())["cassette_canary_pin"]
    assert HEX32_RE.fullmatch(pin_1)
    assert HEX32_RE.fullmatch(pin_2)
    assert pin_1 != pin_2, "AC-3a: held-out pins must be distinct (S5-04 AC-3a)"


# --- AC-1: index allocator filters files vs dirs.
def test_next_index_increments_past_existing_cases_and_skips_sibling_files(tmp_path):
    bench = _make_bench_root(tmp_path)
    cases_root = bench / "vuln-remediation" / "cases"
    for i in range(1, 4):
        (cases_root / f"{i:03d}-fake-rag-corpus-derived").mkdir()
    # Sibling FILES that should be SKIPPED by the index allocator (AC-1 is_dir filter).
    (cases_root / "digests.yaml").write_text("---\n")
    (cases_root / "held-out-cve-exclusion-manifest.yaml").write_text("---\n")
    # A file with a 3-digit-numeric prefix (must also be skipped).
    (cases_root / "999-not-a-dir.txt").write_text("not a dir\n")

    pre_existing_bytes = (cases_root / "001-fake-rag-corpus-derived").stat().st_mtime_ns

    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-44444",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 0, r.stderr
    # Next index is 004 — sibling files were correctly skipped.
    assert (cases_root / "004-cve-2025-44444-held-out").is_dir()
    # Pre-existing directories byte-untouched.
    assert (cases_root / "001-fake-rag-corpus-derived").stat().st_mtime_ns == pre_existing_bytes


# --- AC-9: curation-class × input-flag matrix.
@pytest.mark.parametrize("args, expect_returncode, diag_regex", [
    # legal: rag + cve only
    (["--task-class=vuln-remediation", "--cve=CVE-2025-99999",
      "--curation-class=rag-corpus-derived"], 0, None),
    # legal: rag + slug only
    (["--task-class=vuln-remediation", "--slug=express-vulnerability",
      "--curation-class=rag-corpus-derived"], 0, None),
    # illegal: rag + both cve and slug
    (["--task-class=vuln-remediation", "--cve=CVE-2025-99999", "--slug=foo",
      "--curation-class=rag-corpus-derived"], 1, r"--cve and --slug are mutually exclusive"),
    # illegal: rag + neither
    (["--task-class=vuln-remediation",
      "--curation-class=rag-corpus-derived"], 1, r"(--cve|--slug)"),
    # illegal: held-out without cve (specific diagnostic, not bare "cve" substring)
    (["--task-class=vuln-remediation", "--slug=foo",
      "--curation-class=held-out"], 1, r"--cve.*required.*held-out"),
])
def test_curation_class_input_matrix_validation(tmp_path, args, expect_returncode, diag_regex):
    bench = _make_bench_root(tmp_path)
    # For the LEGAL rag-corpus-derived rows, we also need --source-cassette per AC-3a.
    # The matrix above tests USAGE-level validation; pin derivation is AC-3.
    if expect_returncode == 0 and "rag-corpus-derived" in args:
        cassette_dir = REPO_ROOT / "tests" / "cassettes" / "phase4" / "scaffolder-test-matrix"
        cassette_dir.mkdir(parents=True, exist_ok=True)
        cassette_path = cassette_dir / "fake.cassette"
        cassette_path.write_text("# fake\n")
        args = args + [f"--source-cassette={cassette_path}"]
    else:
        cassette_path = None
    try:
        r = _run(args + [f"--bench-root={bench}"])
        assert r.returncode == expect_returncode, (r.stdout, r.stderr)
        if diag_regex is not None:
            combined = (r.stdout + r.stderr)
            assert re.search(diag_regex, combined, re.I), (
                f"expected diagnostic matching {diag_regex!r} in: {combined!r}"
            )
    finally:
        if cassette_path is not None:
            cassette_path.unlink(missing_ok=True)
            cassette_path.parent.rmdir()


# --- AC-8: CVE format + slug normalization.
@pytest.mark.parametrize("cve, slug, expect_returncode", [
    ("CVE-2025-99999", None, 0),       # legal CVE
    ("cve-2025-99999", None, 1),       # lowercase prefix — rejected
    ("CVE_2025_99999", None, 1),       # underscores — rejected
    ("CVE-2025-1", None, 1),           # too few digits — rejected
    (None, "Foo_Bar", 0),              # normalizes to "foo-bar"
    (None, "___", 1),                  # normalizes to "" — rejected
    (None, "valid-slug", 0),           # already normalized
])
def test_cve_format_and_slug_normalization(tmp_path, cve, slug, expect_returncode):
    bench = _make_bench_root(tmp_path)
    args = ["--task-class=vuln-remediation", "--curation-class=rag-corpus-derived",
            f"--bench-root={bench}"]
    if cve:
        args.append(f"--cve={cve}")
    if slug:
        args.append(f"--slug={slug}")
    if expect_returncode == 0:
        # rag-corpus-derived legal path requires --source-cassette.
        cassette_dir = REPO_ROOT / "tests" / "cassettes" / "phase4" / "scaffolder-test-slug"
        cassette_dir.mkdir(parents=True, exist_ok=True)
        cassette_path = cassette_dir / "fake.cassette"
        cassette_path.write_text("# fake\n")
        args.append(f"--source-cassette={cassette_path}")
    else:
        cassette_path = None
    try:
        r = _run(args)
        assert r.returncode == expect_returncode, (cve, slug, r.stdout, r.stderr)
    finally:
        if cassette_path is not None:
            cassette_path.unlink(missing_ok=True)
            cassette_path.parent.rmdir()


# --- AC-5: dry-run prints parseable TOML + Next steps; creates nothing.
def test_dry_run_prints_parseable_toml_and_next_steps_and_creates_nothing(tmp_path):
    bench = _make_bench_root(tmp_path)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
        "--dry-run",
    ])
    assert r.returncode == 0
    # Extract TOML between sentinel markers.
    m = re.search(r"# --- begin case\.toml ---\n(.*?)\n# --- end case\.toml ---\n",
                  r.stdout, re.DOTALL)
    assert m is not None, "dry-run did not print sentinel-fenced TOML block"
    parsed = tomllib.loads(m.group(1))
    assert parsed["case_id"] == "001-cve-2025-99999-held-out"
    assert parsed["case_digest"] == SENTINEL_DIGEST
    # Next steps block ALSO present in dry-run (AC-5 + AC-6).
    assert "Next steps:" in r.stdout
    assert "scripts/sign_bench_digests.py" in r.stdout
    # Filesystem untouched.
    assert list((bench / "vuln-remediation" / "cases").iterdir()) == []


# --- AC-7: collision exits 1, never overwrites, byte-untouched.
def test_collision_with_existing_case_id_exits_one_and_preserves_existing_bytes(tmp_path):
    bench = _make_bench_root(tmp_path)
    cases = bench / "vuln-remediation" / "cases"
    existing = cases / "001-cve-2025-99999-held-out"
    existing.mkdir()
    sentinel = existing / "case.toml"
    sentinel_bytes = b"sentinel-content\n"
    sentinel.write_bytes(sentinel_bytes)

    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 1
    assert "already exists" in (r.stderr + r.stdout).lower()
    # Byte-untouched.
    assert sentinel.read_bytes() == sentinel_bytes


# --- AC-10: missing bench-root preconditions.
def test_missing_task_class_root_exits_one_with_diagnostic(tmp_path):
    # bench/ exists, but vuln-remediation/ does NOT.
    bench = tmp_path / "bench"
    bench.mkdir()
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 1
    assert "vuln-remediation" in (r.stderr + r.stdout)
    assert re.search(r"S5-01|register", r.stderr + r.stdout, re.I)


def test_missing_cases_subdir_with_registration_present_auto_creates(tmp_path):
    bench = tmp_path / "bench"
    (bench / "vuln-remediation").mkdir(parents=True)
    (bench / "vuln-remediation" / "registration.py").write_text("# stub\n")
    # cases/ DOES NOT exist.
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 0, r.stderr
    assert (bench / "vuln-remediation" / "cases").is_dir()


# --- AC-11: --task-class validated against default_registry.names().
def test_unknown_task_class_exits_two_with_registry_diagnostic(tmp_path):
    bench = _make_bench_root(tmp_path, task_class="vuln-remediation")
    r = _run([
        "--task-class=unknown-task-class",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    # Click usage error = exit 2.
    assert r.returncode == 2, r.stderr
    assert "unknown-task-class" in (r.stderr + r.stdout)
    # Diagnostic names the registered task classes (NOT hard-coded — comes from default_registry).
    # In a real test env, default_registry contains "vuln-remediation" (S5-01).
    assert "vuln-remediation" in (r.stderr + r.stdout)


# --- AC-14: Open/Closed — no literal "vuln-remediation" in script source.
def test_script_source_contains_no_hardcoded_task_class_name():
    text = SCRIPT.read_text()
    assert "vuln-remediation" not in text, (
        "scripts/scaffold_bench_case.py must be task-class-parameterized; "
        "the literal 'vuln-remediation' is forbidden (AC-14, mirror S5-05 AC-SCRIPT-OPENCLOSED)"
    )


# --- AC-15: __main__ entrypoint.
def test_script_has_main_entrypoint():
    text = SCRIPT.read_text()
    assert re.search(r'if __name__ == "__main__":\s*main\(\)', text), (
        "scripts/scaffold_bench_case.py must end with `if __name__ == \"__main__\": main()`"
    )


# --- AC-6: Next steps stdout block — literal-string accuracy + ordinals.
def test_stdout_next_steps_block_names_sign_script_literally_and_lists_four_ordinals(tmp_path):
    bench = _make_bench_root(tmp_path)
    r = _run([
        "--task-class=vuln-remediation",
        "--cve=CVE-2025-99999",
        "--curation-class=held-out",
        f"--bench-root={bench}",
    ])
    assert r.returncode == 0, r.stderr
    # Strict substring (not fuzzy "sign").
    assert "scripts/sign_bench_digests.py" in r.stdout
    # Four ordinals in order.
    assert re.search(r"\(1\).*\(2\).*\(3\).*\(4\)", r.stdout, re.DOTALL), (
        f"missing ordered (1)–(4) Next-steps ordinals in: {r.stdout!r}"
    )
```

Run; expect `FileNotFoundError` on the script (red). Commit as red marker.

### Green — smallest impl shape

1. Implement the script with `click`; emit the TOML via a careful f-string in the pure helper `_render_case_toml`. Use `blake3` for the deterministic pin derivation (RAG-corpus-derived) and `os.urandom(32).hex()` (held-out).
2. Use a single `_validate_task_class_registered` Click callback for `--task-class` (imports `default_registry` lazily; raises `click.BadParameter` on unknown).
3. The "Next steps" block is a single `textwrap.dedent` print; keep it short and accurate.
4. Iterate until all 15 test functions pass.

### Refactor — clean up

- Module docstring cites `phase-arch-design.md §OQ #8` as the rationale + S5-03 / S5-04 / S5-05 as the sibling contracts.
- Click help text for each flag explains the constraint (`--cve` "required for `--curation-class=held-out` per S5-04 AC-2a CVE-year-floor"; `--curation-class` "chooses ADR-0006 split"; `--source-cassette` "required for `--curation-class=rag-corpus-derived`; canonical pin derivation per S5-03 AC-3a").
- The emitted `case.toml` carries the canonical top-of-file comment block (AC-6 + AC-13 contract).
- Coverage: aim for ≥ 85% line on the script; `mypy --strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `scripts/scaffold_bench_case.py` | New — operator CLI |
| `tests/unit/test_scaffold_bench_case.py` | New — 16 test functions covering ACs 1–15 |

## Out of scope

- **Authoring `breakdown_keys.py` / `failure_modes.yaml`.** Those are per-task-class, owned by S5-01 (and analogous task-class registration stories). The scaffolder is per-case.
- **Computing the final `case_digest`.** The scaffolder emits the sentinel `"blake3:" + "0" * 64` stub; `scripts/sign_bench_digests.py` (S5-05) is the actual signer that replaces the stub with `compute_case_dir_digest(case_dir)` from the public `codegenie.eval.digests` module.
- **`Canary.mint(seed=...)` involvement.** `Canary.mint(...)` is the runtime canary-token API (Phase 4 / S2-05); it does NOT mint `cassette_canary_pin`. The scaffolder mints the pin STRING directly per AC-3.
- **Cassette content copying when `--source-cassette` given.** This story narrows `--source-cassette` to the comment-block annotation only (AC-13). Copying `input.snapshot/` / `expected.snapshot/` from a cassette is deferred to a follow-on story landed *after* Phase 4 ADR-P4-006 ships and the cassette layout is HARDENED — at which point a `CanaryPinSource` sum type may also become the third-path Strategy seam (S5-03 / S5-04 F-DP-2).
- **Auto-extracting CVE metadata from public feeds.** Future enhancement; the current scaffold takes the CVE on the command line.
- **GUI / TUI.** The script is a CLI. The next step in operator UX is `codegenie eval scaffold-case` as a subcommand (deferred).
- **`--list-task-classes` flag.** Out of scope per Rule 2 (one consumer = no abstraction). `--help` + README suffice for discoverability.
- **README mention of the scaffolder under `bench/vuln-remediation/README.md`.** Surgical scope: this story ships the script + tests only; the README cross-link can land alongside S5-05's README work (Rule 3).

## Notes for the implementer

### Adversarial mutant catalog (six named mutants this §TDD plan kills)

1. **Constant pin** (`return "0" * 32`) — killed by AC-3 (canonical formula re-derivation byte-equality) and AC-3a (distinctness across two held-out invocations).
2. **Missing comment block** (skipping `# Derived from:` for `--source-cassette`) — killed by AC-13 substring check.
3. **Swallowed exit code on collision** (`mkdir(exist_ok=True)` + emit success) — killed by AC-7 byte-untouched assertion + `returncode == 1` check.
4. **Partial directory creation under missing bench-root** (creating `cases/` even when `<task-class>/` is missing) — killed by AC-10's separation between the two preconditions.
5. **Post-hoc Literal mismatch** (e.g., emitting `disposition = "good"` instead of a valid Literal) — killed by AC-2's `BenchCase.model_validate` round-trip.
6. **Slug character bleed** (e.g., passing `--slug=Foo Bar` through verbatim) — killed by AC-8's normalization + parametrized rejection of empty post-normalization slugs.

### Two-path canary derivation Strategy seam (deferred per Rule 2)

Exactly two pin-derivation paths today:
- `--curation-class=rag-corpus-derived` + `--source-cassette=<path>` → S5-03 AC-3a canonical formula (domain-separated by `phase4-cassette:` prefix).
- `--curation-class=held-out` → `os.urandom(32).hex()` per ADR-0005 §Consequences line 44 + S5-04 AC-3a.

Rule 2 says two paths is fine — do NOT abstract today. When ADR-P4-006 ships and Phase 4 cassettes re-cut with metadata, a third path (read-from-metadata) lands; extract a `CanaryPinSource` sum type + `derive_canary_pin(source) -> str` smart constructor at that moment (mirrors S5-03 F-DP-2 + S5-04 F-DP-2). For now the `_derive_cassette_canary_pin(curation_class, source_cassette)` function in §Implementation outline §5 keeps both paths explicit and named.

### `Canary.mint(...)` vs `cassette_canary_pin` — DO NOT confuse

Per ADR-0005 §Decision: `Canary.mint(...)` is the **runtime canary-token generator** (32 bytes injected into the SUT's system prompt at invocation time; the output validator's `canary_echo` check verifies the model did not echo it). `cassette_canary_pin` is the **curator-time 32-hex identifier** pinned into `case.toml` and consumed by S2-05's `with_pinned_canary(case)` shim to seed `Canary.mint(seed=bytes.fromhex(pin))` at runtime. The scaffolder mints the **pin** (a string) — it does NOT call `Canary.mint`. (As of 2026-05-26 per S2-05's own status note, `Canary.mint(seed=...)` does not even exist in shipped code yet — but even after it lands, the scaffolder remains pin-only.)

### `compute_case_dir_digest` — no inline reimplementation

Per S5-05 AC-DIG-PROMOTE, the canonical case-dir digest algorithm lives at `src/codegenie/eval/digests.py` and is re-exported from `codegenie.eval.__init__`. The scaffolder MUST NOT re-implement BLAKE3 framing — no `b"\x1f"` / `b"\x1e"` separator literals in `scripts/scaffold_bench_case.py`. The scaffolder emits the all-zero stub digest; the curator runs `scripts/sign_bench_digests.py` (S5-05) which routes through the public helper. If a future scaffolder enhancement needs a real digest (e.g., post-population auto-sign), import from `codegenie.eval.digests` — never inline the algorithm.

### Functional core / imperative shell

The pure helper `_render_case_toml(payload: _CaseSkeleton) -> str` (where `_CaseSkeleton` is a small frozen dataclass) lets AC-2 / AC-5 / AC-12 test the rendered TOML string directly without mocking I/O. The imperative shell (Click handlers, `mkdir`, `write_text`, `sys.exit`) wraps it. Keep them separable; ~150 LOC total stays well under the 200-LOC informal cap.

### Determinism vs entropy

Curator-time non-determinism (`datetime.now(UTC)` for `added_at`/`last_validated_at`; `os.urandom(32).hex()` for held-out pin) is captured **once** per scaffold and pinned forever after in `case.toml` — analogous to S5-04's contract. This means two successive `--dry-run` invocations will produce DIFFERENT TOML strings (different pin + different timestamps); AC-5 masks these fields before structural comparison. Curators running twice should expect different output; commit *one* of them.

### Curator workflow (the "Next steps" block AC-6)

The scaffolder's stdout block is the bench-author's UX. The four ordinals are: (1) populate `input/`; (2) populate `expected/`; (3) run `scripts/sign_bench_digests.py --task-class=<tc> --case-id=<id>`; (4) commit. Wording matters: explicit, scannable, hyperlink-ish ("see ADR-0006" / "run `scripts/sign_bench_digests.py`"). Test asserts the literal substring `scripts/sign_bench_digests.py` (not fuzzy "sign" match) and the (1)–(4) ordinal sequence; phrasing inside the ordinals is the implementer's call. Don't over-engineer error messages; curators are technical and will read tracebacks.

### Held-out CVE-year-floor selection criterion (curator judgment, not enforced)

ADR-0006 + S5-04 AC-2a require held-out CVEs to come from `CVE-YEAR-NNNN where YEAR ≥ Phase 4 corpus cutoff` (or older CVEs explicitly excluded in `held-out-cve-exclusion-manifest.yaml`). The scaffolder validates only the CVE *format* (AC-8) — the year-floor is the curator's judgment call, surfaced via the help-text on `--cve` and reinforced by the README. A scaffolder-time year check would couple operator tooling to corpus state and create a moving fact — out of scope for this story.

### Out-of-closure imports are OK

`scripts/scaffold_bench_case.py` lives outside the policed runtime closure (`src/codegenie/`) and may import `click`, `blake3`, `tomllib` (stdlib), `codegenie.eval.registry.default_registry`, `codegenie.eval.digests.compute_case_dir_digest`, and `codegenie.eval.models.BenchCase` freely. `make fence` polices `src/codegenie/` only — bench-curation tooling under `scripts/` is intentionally exempt (Phase 0 ADR-0001 §Scope).
