# Validation report — S5-07 `scripts/scaffold_bench_case.py` operator tool

**Story file:** `docs/phases/06.5-per-task-class-eval-harness/stories/S5-07-scaffold-bench-case-script.md`
**Validated:** 2026-06-05
**Validator:** phase-story-validator skill
**Verdict:** **HARDENED**
**Finding count:** 20 total — 7 blocks · 10 hardens · 3 nits
**NEEDS RESEARCH:** none

---

## Stage 1 — Context Brief (one page)

**What the story promises.** Ship `scripts/scaffold_bench_case.py` as an operator CLI that scaffolds a structurally-valid `bench/<task-class>/cases/<case-id>/` skeleton from `--task-class` + `--cve`/`--slug` + `--curation-class` + optional `--source-cassette`. Produces a stub `case.toml`, empty `input/.gitkeep` + `expected/.gitkeep`, a `cassette_canary_pin`, and a "Next steps" stdout block. Closes Phase 6.5 Open Question #8 (bench-author bootstrap experience).

**What the phase's exit criteria demand.** Phase 6.5 ships the `bench/vuln-remediation/` 10-case floor; OQ #8 names this script as the operator-bootstrap remediation that makes case curation mechanical-not-error-prone. The scaffolder's output must satisfy: (a) the S2-02 loader's `case.toml`-shape contract (BenchCase Pydantic round-trip); (b) the S2-02 `case_digest` + `digests.yaml` workflow (the curator-required signing step is `scripts/sign_bench_digests.py` per S5-05); (c) the canonical `cassette_canary_pin` derivation in S5-03 (RAG) and S5-04 (held-out).

**What the arch + ADRs constrain.**
- `phase-arch-design.md §bench/{task-class}/ directory contract` (line 698) — the precise case.toml schema.
- `phase-arch-design.md §OQ #8` (line 1217) — names the script as operator-bootstrap.
- ADR-0005 §Consequences line 44 — `os.urandom(32).hex()` for net-new pins; `Canary.mint(...)` is the runtime canary-TOKEN API, separate from `cassette_canary_pin` (the curator-time IDENTIFIER).
- ADR-0006 — `curation_class: Literal["rag-corpus-derived", "held-out"]`; CVE-year-floor for held-out is curator judgment.
- S5-03 HARDENED §AC-3a — canonical RAG pin formula `blake3(f"phase4-cassette:{cassette_relpath_posix}".encode()).hexdigest()[:32]`.
- S5-04 HARDENED §AC-3a — `os.urandom(32).hex()` for held-out; 32-hex format + distinctness.
- S5-05 HARDENED §AC-DIG-PROMOTE + AC-SCRIPT-OPENCLOSED — `compute_case_dir_digest` is public; operator scripts are task-class-parameterized with no hard-coded literal task-class names.
- S5-01 HARDENED — `default_registry.names()` is the source of truth for valid `--task-class` slugs.
- CLAUDE.md "Extension by addition" — new task class = new bench/<slug>/ directory + zero edits to operator scripts.

**Ambiguities surfaced before critic spawn.**
- The story's pin derivation formula `blake3(f"{task_class}/{case_id}").hexdigest()[:32]` does not match either S5-03 (cassette-derived) or S5-04 (urandom). This is a structural-contradiction symptom worth surfacing to both Consistency and Coverage critics.
- The story conflates `Canary.mint(seed=...)` (a runtime token generator) with `cassette_canary_pin` minting (a curator-time string identifier). Worth surfacing to Consistency.
- AC numbering is missing (HARDENED siblings all use AC-1, AC-2, AC-DIG-PROMOTE-style mnemonics).
- The collision-behavior contract in the AC ("exits non-zero") vs the TDD test (accepts OR-clause) is internally contradictory.

---

## Stage 2 — Critic reports (run in parallel)

### Coverage critic (12 findings)

| ID | Sev | Title | Evidence | Proposed fix |
|---|---|---|---|---|
| F-COV-1 | block | `case.toml` not asserted to validate as `BenchCase` | story L34 + TDD L118–138 | Add AC + test that calls `BenchCase.model_validate(tomllib.loads(text))` after digest replacement |
| F-COV-2 | block | Pin format contradicts ADR-0005 + S5-04; deterministic-from-case-id fallback has no precedent | story L35 + TDD L136–137 | Two-path branch: S5-03 formula for RAG + source cassette; `os.urandom(32).hex()` for held-out |
| F-COV-3 | block | Regex shape of pin + digest not asserted | TDD L136–138 | Replace `startswith("blake3:")` + `len==32` with `re.fullmatch(r"^blake3:[0-9a-f]{64}$", ...)` and `re.fullmatch(r"^[0-9a-f]{32}$", pin)` |
| F-COV-4 | block | Collision behavior is contradictory; AC-bullet says exit, test accepts OR-clause | story L37 + TDD L184–199 | Pick exit-1-on-collision; tighten test |
| F-COV-5 | block | Held-out-without-CVE rejection has no positive coverage of legal `rag-corpus-derived + slug` path | story L40 + TDD L156–166 | Add legal-path AC + parametrized test for the full 5-row matrix |
| F-COV-6 | block | `bench/<task-class>/` missing precondition has no AC | Notes L257 | Add AC + test for missing-task-class-root → exit 1 |
| F-COV-7 | harden | `--source-cassette` "Derived from" comment not asserted | story L39 + no TDD | Add test asserting `# Derived from: <relpath>` line matches S5-03 grep regex |
| F-COV-8 | harden | case_id slug-only path has no naming-regex AC | impl L60 | Add AC for slug normalization + CVE format validation |
| F-COV-9 | harden | `tomli_w` is suggested but not pinned; f-string risks TOML invalidity | green L219 | Pin `tomllib.loads(text)` round-trip AC |
| F-COV-10 | harden | `--dry-run` has no parseable-TOML assertion | TDD L169–181 | Strengthen to extract TOML between sentinel markers + parse |
| F-COV-11 | nit | `--dry-run` Next-steps presence is unclear | AC L36 | Pin Next-steps prints in dry-run too |
| F-COV-12 | nit | `--bench-root` default path is untested | AC L32 | Optional smoke test under tmp_path |

### Test Quality critic (7 findings)

| ID | Sev | Title | Evidence | Proposed fix |
|---|---|---|---|---|
| F-TQ-1 | block | Pin-derivation test tautological under fallback | TDD L118–138 | Re-derive canonical formula and assert byte-equality |
| F-TQ-2 | block | `test_collision_with_existing_case_id_fails` accepts both outcomes | TDD L195–199 | Pin returncode==1 + "already exists" + byte-untouched |
| F-TQ-3 | harden | `test_held_out_requires_cve_identifier` is too-loose substring check | TDD L166 | Strengthen to `re.search(r"--cve.*required.*held-out", out, re.I)` |
| F-TQ-4 | harden | `case.toml` parses but `BenchCase.model_validate` never runs | TDD L118–138 | Add Pydantic round-trip (also F-COV-1) |
| F-TQ-5 | harden | No assertion of canonical comment-block shape | Refactor L228 | Add AC + test asserting top-of-file comment block |
| F-TQ-6 | harden | Dry-run does not assert structural equivalence to wet run | TDD L169–181 | Two invocations + masked-dict comparison |
| F-TQ-7 | nit | `test_next_index_increments` doesn't assert pre-existing dirs untouched | TDD L141–153 | Add mtime_ns assertion |

### Consistency critic (8 findings)

| ID | Sev | Title | Evidence | Proposed fix |
|---|---|---|---|---|
| F-CON-1 | block | Canary derivation contradicts S5-03 HARDENED canonical formula | story L35 vs S5-03 AC-3a | Use S5-03's domain-separated formula verbatim for RAG-corpus-derived |
| F-CON-2 | block | Held-out canary derivation contradicts ADR-0005 + S5-04 HARDENED | story L35 vs ADR-0005 L44 + S5-04 AC-3a | Use `os.urandom(32).hex()` for held-out; drop the case-id fallback |
| F-CON-3 | block | `Canary.mint` conflated with `cassette_canary_pin` | story L23 + L254 | Remove every reference to `Canary.mint(...)` — those are different APIs |
| F-CON-4 | block | `case_digest` stub fails the loader's S2-02 §AC-3 immediately | story L34 | Pin sentinel literal `"blake3:" + "0"*64`; clarify curator-signing flow in AC + Notes |
| F-CON-5 | harden | Operator-script Open/Closed pattern not honored (S5-05 AC-SCRIPT-OPENCLOSED) | story L227 | Add AC: no literal `"vuln-remediation"` in script source |
| F-CON-6 | harden | `--bench-root` default safety story unclear | story L55 | Document; the test should exercise the default path |
| F-CON-7 | harden | `--source-cassette` deep-parse is underspecified | Notes L256 | Narrow scope to comment-block-only; defer content copying |
| F-CON-8 | nit | Help-text citation wrong (ADR-0006 vs S5-04 AC-2a) | story L227 | Cite S5-04 AC-2a CVE-year-floor |

### Design Patterns critic (5 findings)

| ID | Sev | Title | Evidence | Proposed fix |
|---|---|---|---|---|
| F-DP-1 | harden | Missed reuse of `codegenie.eval.digests.compute_case_dir_digest` | S5-05 AC-DIG-PROMOTE | Notes pin: route through public helper; no inline algorithm |
| F-DP-2 | harden | Missed Strategy seam for pin derivation (cross-ref to S5-03/S5-04 F-DP-2) | story has no mention | Document two paths + seam-extraction trigger when ADR-P4-006 ships |
| F-DP-3 | harden | Primitive obsession on `task_class`/`cve`/`slug`/`case_id` | impl L60 | Validate `--task-class` against `default_registry`; small `make_case_id` helper |
| F-DP-4 | nit | `--list-task-classes` bonus is premature abstraction | Refactor L229 | Drop until second consumer asks |
| F-DP-5 | nit | `tomli_w` introduces a new dependency | green L219 | Prefer f-string (~150 LOC tooling) |

---

## Stage 3 — Researcher

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. Every proposed fix is precedented in this repo:
- Canary derivation patterns: S5-03 F-CON-3 + S5-04 F-COV-2.
- Operator-script Open/Closed: S5-05 AC-SCRIPT-OPENCLOSED.
- Adversarial mutant catalog convention: S5-02 / S5-05 Notes-for-implementer sections.
- BenchCase round-trip testing: S5-03 AC-2 / S5-04 AC-2.

---

## Stage 4 — Synthesis

**Conflict resolution.** No direct conflicts between critics — Consistency, Coverage, and Test-Quality all converged on the canary-derivation block (F-CON-1 + F-CON-2 + F-COV-2 + F-TQ-1 are the same root cause: the story's case-id-derived fallback has no precedent in HARDENED siblings). Design-Patterns endorsed the two-path Strategy seam (F-DP-2) as deferred per Rule 2 — no abstraction today, document the seam.

**Priority queue (block → harden → nit):**

1. **B1** — F-CON-1 + F-CON-2 + F-COV-2 + F-TQ-1: Canary pin two-path branch.
2. **B2** — F-CON-3: Remove `Canary.mint` references.
3. **B3** — F-CON-4 + F-COV-1 + F-COV-3 + F-TQ-4: Pin sentinel digest literal + `BenchCase.model_validate` round-trip + canonical regex assertions.
4. **B4** — F-COV-4 + F-TQ-2: Collision behavior — exit 1, byte-untouched.
5. **B5** — F-COV-5: Legal `rag-corpus-derived` paths + 5-row matrix test.
6. **B6** — F-COV-6: Missing-bench-root AC.
7. **B7** — F-DP-3 + F-CON-5 (Open/Closed): `--task-class` validated against `default_registry.names()`; no hard-coded literal task-class name in script source.

**Hardens applied:**
- H1 (F-TQ-3): `--cve` required diagnostic specificity.
- H2 (F-COV-8): Slug normalization + CVE format validation.
- H3 (F-COV-9): `tomllib.loads` round-trip AC.
- H4 (F-COV-10 + F-TQ-6): `--dry-run` strengthened to sentinel-fenced TOML extraction.
- H5 (F-COV-11): `--dry-run` also prints Next steps.
- H6 (F-TQ-5): Comment-block shape AC.
- H7 (F-CON-7): `--source-cassette` narrowed to comment-block only.
- H8 (F-CON-8): Help-text citation corrected.
- H9 (F-DP-1): No inline digest algorithm — route through `codegenie.eval.digests`.
- H10 (F-COV-7): `# Derived from:` comment block assertion + S5-03 grep regex compat.

**Nits applied:**
- N1 (F-DP-4): Dropped `--list-task-classes` bonus.
- N2 (F-DP-5): Prefer f-string over `tomli_w`.
- N3 (F-TQ-7): `test_next_index_increments` asserts pre-existing dirs untouched via `mtime_ns`.

**Design endorsements (Notes-for-implementer):**
- Functional core / imperative shell: pure `_render_case_toml(payload) -> str` helper.
- Two-path Strategy seam deferred per Rule 2 (cross-ref to S5-03/S5-04 F-DP-2).
- No inline digest algorithm (cross-ref to S5-05 AC-DIG-PROMOTE).
- Adversarial mutant catalog (six named mutants).

---

## Edits applied

### Story file (in place)

- **Header** updated: `Status: HARDENED (phase-story-validator, 2026-06-05)`; `Depends on:` widened from S5-01 only to S5-01 / S1-02 / S2-02 / transitively S5-03 + S5-04; `ADRs honored:` expanded to ADR-0005 (with explicit `Canary.mint`-vs-pin distinction) + ADR-0006 + ADR-0004 + ADR-0008 + Phase 0 ADR-0001.
- **Validation notes block** appended under the header — full audit log of every finding addressed.
- **Acceptance criteria** fully renumbered AC-1 through AC-16; new ACs for canary two-path derivation, distinctness, sentinel digest, dry-run parseability, Next-steps literal substring, collision exit, slug+CVE validation, curation-class × input matrix, missing-bench-root precondition, registry validation, BenchCase round-trip, source-cassette comment block, no-hardcoded-task-class, `__main__` entrypoint, lint+typecheck.
- **Implementation outline** rewritten with explicit two-path pin derivation code, `_validate_task_class_registered` Click callback, `_render_case_toml` pure helper (functional core / imperative shell), index allocation with `p.is_dir()` filter, sentinel digest, missing-bench-root branching.
- **TDD plan §Red** rewritten with 16 test functions corresponding 1-to-1 with AC-1 through AC-16. Tests use `subprocess.run` for end-to-end CLI exercise, mirror S5-03 / S5-04 patterns, parametrize the validation matrix.
- **TDD plan §Refactor** updated: cite S5-03 / S5-04 / S5-05 as sibling contracts; drop `--list-task-classes` bonus.
- **Files to touch** narrowed to two files; the `bench/vuln-remediation/README.md` optional row dropped (Rule 3 — surgical scope; cross-link can land with S5-05's README work).
- **Out of scope** expanded: `Canary.mint` involvement; cassette content copying (deferred until ADR-P4-006); `--list-task-classes`; README cross-link.
- **Notes for the implementer** rewritten: adversarial mutant catalog (six named mutants); two-path Strategy seam (deferred per Rule 2); `Canary.mint` vs `cassette_canary_pin` distinction (explicit); no-inline-digest-algorithm pin; functional-core/imperative-shell shape; determinism vs entropy (curator-time non-determinism captured once); curator workflow ordinal sequence; CVE-year-floor curator judgment; out-of-closure imports allowed.

### `_validation/S5-07-scaffold-bench-case-script.md`

This file — the full audit log.

---

## Verdict: HARDENED

The story has been edited in place to address every block + harden finding. The two-path canary derivation is now byte-aligned with S5-03 and S5-04; `Canary.mint` references are removed; the sentinel digest + curator-signing flow is pinned; collision behavior is unambiguous; the missing-bench-root precondition is enforced; `--task-class` is validated against the registry; the BenchCase round-trip is asserted; the operator-script Open/Closed pattern (no literal `"vuln-remediation"` in source) mirrors S5-05 AC-SCRIPT-OPENCLOSED. The adversarial mutant catalog and design-pattern endorsements are surfaced in Notes-for-implementer for the executor and PR reviewers.

The story is ready for the executor.
