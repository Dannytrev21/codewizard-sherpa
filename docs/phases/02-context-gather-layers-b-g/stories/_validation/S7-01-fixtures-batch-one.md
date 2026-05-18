# Validation report: S7-01 — Fixtures batch 1 (`minimal-ts` + `native-modules` + `distroless-target`)

**Validated:** 2026-05-17
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S7-01 plants three of the five Phase-2 portfolio fixtures (`minimal-ts`, `native-modules`, `distroless-target`). The story's intent and scope are sound and trace cleanly to `phase-arch-design.md §"Fixture portfolio engineering"` + `High-level-impl.md §Step 7`. Four critic lenses (Coverage, Test-Quality, Consistency, Design-Patterns) found 11 substantive issues, of which two are `block`-tier:

1. **`pnpm` is not in `ALLOWED_BINARIES`** (current frozen set per ADR-0001 + S1-06 AC-10 amendment) — the original story's `regenerate.sh` plan for `native-modules` invoked `pnpm install --ignore-scripts`, which would either fail the static AC-31 check OR force a silent ADR-0001 expansion (forbidden).
2. **AC-22's `regenerate.sh` invokes `docker build` "via `run_allowlisted(...)`"** — `run_allowlisted` is a Python function in `src/codegenie/exec/__init__.py`; bash cannot call it. The architectural mismatch is mechanical.

Both block-tier issues are mechanically fixable in-place without rewriting the story's goal or scope. The remaining 9 harden-tier issues tighten ACs, lift mutation-table entries into the AC battery (so they're enforced rather than descriptive), and pin two cross-probe contracts (`_ProbeName` Literal vs. probe registry; `built-image.digest` byte shape vs. `image_digest_resolver`).

Story edited in place. Verdict: HARDENED.

## Stage 1 — Context Brief

**What the story promises.** Three fixture trees under `tests/fixtures/portfolio/{minimal-ts, native-modules, distroless-target}/`, each with `README.md`, `regenerate.sh`, `.gitignore`, plus per-fixture body files; per-fixture shape test modeled on Phase 1's `test_fixture_node_typescript_helm_shape.py` (closed-set complement, line endings, content invariants, README cross-reference); central no-`.codegenie/cache/`-committed pytest. Mirrors Phase 1 S2-03 pattern.

**Arch + ADR constraints (load-bearing).**

- `phase-arch-design.md §"Fixture portfolio engineering"` — fixtures ≤ 200 files; `regenerate.sh` reviewed-as-code; `.codegenie/cache/` NOT committed (transparent diff; regenerate on every CI run).
- `phase-arch-design.md §"Golden files"` — five-fixture table; these three are listed.
- ADR-0001 closed binary set: `{git, node, semgrep, syft, grype, gitleaks, scip-typescript, ast-grep, ripgrep, tree-sitter, docker, strace}`. `pnpm`, `npm`, `node-gyp` are NOT in the set; adding any requires a new ADR amendment.
- ADR-0004 — image-digest as declared-input token; `ProbeContext.image_digest_resolver: Callable[[Path], str | None]` consumes `built-image.digest`.
- ADR-0007 — no plugin loader (no fixture seeds `plugins/`; story is clean here).
- ADR-0009 — pytest-xdist veto preserved.

**Phase-1 pattern to replicate.** `tests/unit/test_fixture_node_typescript_helm_shape.py` defines: `_ProbeName = Literal[...]` (closed Phase-1 set); `_ParserKind = Literal["safe_json","safe_yaml","jsonc","text"]`; `class _FileSpec(NamedTuple): relpath, consumers, parser, content_checks`; `_FILE_SPECS: tuple[_FileSpec, ...]`; parametrized tests `test_fixture_file_exists`, `test_fixture_file_parses`, `test_fixture_file_content_invariants`, `test_fixture_file_line_endings`; `test_no_forbidden_subpaths[forbidden]` parametrized; `_enumerate_tracked` walks `rglob("*")` with explicit `_FIXTURE_NOISE_NAMES = frozenset({"__pycache__", ".pytest_cache", ".DS_Store"})`; `test_fixture_tree_is_closed_set` asserts `actual == expected`; `test_readme_references_every_spec`; `test_probe_name_literal_matches_phase_1_closed_set` (equality, not subset); `test_fixture_bytes_not_copied_from_production_sources`.

**Current code state.** `tests/fixtures/portfolio/stale-scip/` already exists (planted in a prior story); its `regenerate.sh` invokes only `git` + POSIX coreutils; `.codegenie/` is gitignored and untracked in git; `_seed/` carries tracked seed bytes. `tests/fixtures/portfolio/{minimal-ts, native-modules, distroless-target}/` do NOT yet exist. `tests/unit/test_fixture_*_shape.py` already has three Phase-1 instances (`node_typescript_helm`, `node_monorepo_turbo`, `non_node_go`); each duplicates the `_FileSpec` + parametrized-tests pattern — three is exactly the rule-of-three threshold but the project deliberately defers extraction (per Phase 1's S2-03 Notes-for-implementer).

**Ambiguities surfaced (resolved by edits).**

- Story said "the regen script uses `pnpm install --ignore-scripts`" — but pnpm not allowlisted. Resolved by mirroring Phase 1 lockfile-hand-author precedent (no install at regen time).
- Story said `regenerate.sh` calls `run_allowlisted("docker", ...)` — bash can't call Python. Resolved.
- Story said closed-set test excludes "dotfiles created by editors" — vague. Resolved to explicit Phase-1 noise frozenset + `git ls-files`-primary enumeration.
- Story did not specify the shell-tokenizer for AC-31. Resolved with explicit token-drop list and a shared `_fixture_regen_allowlist.py` module.

## Stage 2 — Critic reports

### Coverage critic — Verdict: HARDEN

- **[block] C1** — `pnpm` not in `ALLOWED_BINARIES` ⇒ AC-31 contradicts AC-15/AC-16/Implementation Outline §4. Fix applied — hand-authored lockfile, no install at regen.
- **[harden] C2** — AC-26 closed-set test will fail after `regenerate.sh` because `built-image.digest` is in the working tree though `.gitignored`. Fix applied — enumerate via `git ls-files`.
- **[harden] C3** — `binding.gyp` parser pin is implicit. Fix applied — AC-13 pins strict RFC-8259 JSON.
- **[harden] C4** — AC-22 "via `run_allowlisted(\"docker\", ...)`" mis-prescribes shell-side dispatch. Fix applied — AC-22 rewritten with explicit clarifier.
- **[harden] C5** — AC-16's "post-install" assertion required `pnpm install` to have run. Fix applied — AC-16b reframes as a stale-output assertion.
- **[nit] C6** — AC-30 byte-identical scope was implicit. Fix applied — scoped to `git ls-files`-tracked files.

### Test-Quality critic — Verdict: HARDEN

- **[harden] T1** — Dockerfile digest-format mutation was in the witness table but not an AC. Fix applied — AC-21b adds the regex predicate as a positive AC.
- **[harden] T2** — `_ProbeName` Literal can silently drift from registered probe names. Fix applied — AC-37 (subset-semantics runtime check).
- **[harden] T3** — `regenerate.sh` static check (AC-31) had no concrete tokenizer spec; would be fragile. Fix applied — AC-31 specifies the tokenizer and `_SHELL_COREUTILS_ALLOWLIST`; shared module under `tests/unit/_fixture_regen_allowlist.py`.
- **[harden] T4** — `built-image.digest` byte-shape was undefined; consumers (resolver) need a contract. Fix applied — AC-38 pins `^sha256:[0-9a-f]{64}\n$`.
- **[harden] T5** — Witness table additions: short-digest, eval-shell-injection, pnpm-invocation, missing-`sha256:`-prefix, gitignored-but-tracked. Fix applied.
- **[nit] T6** — `_FILE_SPECS` sort/dedupe invariant. Deferred — Rule 2 (three similar lines OK; mypy + closed-set test together catch duplicates effectively).

### Consistency critic — Verdict: HARDEN

- **[block] Cn1** — Same as C1 (`pnpm` ∉ `ALLOWED_BINARIES`). Source-of-truth (ADR-0001) wins over the implementation-pattern wish; story rewritten accordingly.
- **[block] Cn2** — Same as C4 (shell can't call Python). AC-22 rewritten.
- **[harden] Cn3** — Layer-D probe-name enumeration verified against `src/codegenie/probes/layer_d/` modules. Story Literal is correct; AC-37 backstops future drift.

### Design-Patterns critic — Verdict: HARDEN

- **[harden] DP1** — `_ProbeName` + `_FileSpec` + parametrized tests duplicate 3× across new fixture shape tests (and 3× more from Phase 1). Six duplications is past Rule of Three for the structure; the story already defers kernel extraction to S7-02. Endorsed — defer; the kernel extraction at S7-02 is the cleanest landing (5 consumers).
- **[harden] DP2** — `_fixture_regen_allowlist.py` is a Rule-of-Three carve-out for load-bearing-policy ownership (one source of truth for the AC-31 invariant; copy-pasting weakens ADR-0001 enforcement). Fix applied — module lifts now (not S7-02). Notes-for-implementer documents the rationale.
- **[harden] DP3** — `built-image.digest` byte-shape is a value-typed contract with `image_digest_resolver`. Fix applied — AC-38 pins the shape; the contract is now mechanically enforced rather than implicit.
- **[nit] DP4** — Per-fixture content predicates inline in each shape test (Phase 1 precedent). Defer to S7-02 kernel extraction (composition-over-inheritance — pure predicate functions consumed by a parametrized kernel).
- **[nit] DP5** — `_ParserKind` Literal duplicates across shape tests. Same kernel-extraction landing point.

## Stage 3 — Research

Skipped — no critic finding tagged `NEEDS RESEARCH`. All fixes have direct precedents in the codebase (Phase 1 fixture, Phase 1 shape test, stale-scip fixture's regen-script discipline, ADR-0001 closed set, `image_digest_resolver` contract).

## Stage 4 — Synthesizer + conflict resolution

**No critic conflicts.** All four critics agree on the directional fixes; severity differs but priorities align.

**Edits applied to the story (in order):**

1. `Status:` `Ready → HARDENED (validated 2026-05-17)`.
2. Inserted `## Validation notes (2026-05-17)` block under header documenting every change.
3. `AC-13` — added strict-JSON pin for `binding.gyp`.
4. `AC-15` — rewritten to require hand-authored `pnpm-lock.yaml`; explicit "no `pnpm install` at regen time".
5. `AC-16` — split into AC-16 (`.npmrc` shape) + AC-16b (`build/Release/` absent-assertion as stale-output guard rather than post-install verification).
6. `AC-21b` — new AC; final-stage `FROM` digest regex pin.
7. `AC-22` — rewritten; removed "via `run_allowlisted(...)`"; documented the structural-vs-functional guarantee.
8. `AC-26` — rewritten; primary enumeration via `git ls-files`; explicit noise frozenset as defense-in-depth.
9. `AC-30` — explicit "tracked-files scope".
10. `AC-31` — concrete tokenizer spec; shared `_fixture_regen_allowlist.py` module; explicit "never" set.
11. `AC-37` — new AC; runtime registry pin (subset semantics).
12. `AC-38` — new AC; `built-image.digest` byte-shape contract.
13. Implementation Outline §4 — rewritten to remove `pnpm install` invocation; lockfile is hand-author bytes.
14. Mutation-resistance witness table — added 6 new mutation rows tied to AC-21b, AC-31, AC-37, AC-38.
15. Files-to-touch table — added shared module + 3 regen-allowlist test files + 1 built-image-digest shape test.
16. Notes-for-implementer — documented the Rule-of-Three carve-out for `_fixture_regen_allowlist.py` (load-bearing policy ownership); explained subset-semantics rationale for AC-37; deferred predicate-kernel extraction to S7-02 alongside the shape-test kernel.

**ACs touched:** 8 modified (AC-13, AC-15, AC-16, AC-22, AC-26, AC-30, AC-31); 3 added (AC-21b, AC-37, AC-38).
**ACs net:** 36 → 39.

## Final verdict

**HARDENED.** The story now:

- Conforms structurally to ADR-0001 (no silent binary expansion).
- Removes the bash-calls-Python architectural mismatch.
- Pins three cross-probe / cross-layer contracts as observable ACs (Dockerfile digest format, `_ProbeName` Literal vs. registry, `built-image.digest` byte shape).
- Eliminates the `built-image.digest` false-positive in the closed-set test.
- Specifies the AC-31 static check concretely so it's enforceable and reproducible.
- Records the Rule-of-Three carve-out (`_fixture_regen_allowlist.py` lifts now; everything else defers to S7-02) with explicit rationale.
- Defers the shape-test + predicate-kernel extraction to S7-02 per Rule 2 (no premature abstraction).

Ready for `phase-story-executor`.
