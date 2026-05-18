# Validation report: S7-03 — Golden files (~70) + `scripts/regen_golden.py` canonical-ordering

**Validated:** 2026-05-18
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1 (four-critic consolidated pass)

## Summary

S7-03 ships the slice-level per-probe JSON golden tree under `tests/golden/probes/<probe>/<fixture>.json` over the S7-01/S7-02 five-repo portfolio, plus the `--portfolio` mode of `scripts/regen_golden.py`, plus three pytest harnesses (match-check, count guard, plaintext-leak guard). The story's intent and scope are sound and trace cleanly to `phase-arch-design.md §"Golden files"` + `High-level-impl.md §Step 7` + Risk #5 (golden-file non-determinism).

The story already had above-average rigor (33 ACs, mutation-resistance table, deferred-pattern section). However, four block-tier issues and ten harden-tier issues surfaced that — if left in — would let the executor ship something subtly weaker than what S6-01's HARDENED precedent established for the envelope-level YAML golden.

The block-tier set centers on one root pattern: S7-03 was written before S6-01 was hardened, and didn't pick up two of S6-01's HARDENED lessons (idempotence-as-CI-gate; fail-loud on macOS). Eight harden-tier issues tighten audit surfaces (envvar guards, atomic writes, typed canonicalize, preserved-fields inclusion-list, etc.). All fourteen are mechanically fixable in place; none requires re-running `phase-story-writer`. Story edited in place. **Verdict: HARDENED.**

## Stage 1 — Context Brief

**What the story promises.** Three deliverables:
1. `scripts/regen_golden.py` extended (or written from scratch — see ambiguity below) with `--portfolio` mode: iterates `tests/fixtures/portfolio/<fixture>/`, runs `codegenie gather` via `run_allowlisted`, captures each `<fixture>/.codegenie/context/raw/<probe>.json`, canonicalizes (sorted keys, exclusion list, LF endings, trailing newline), writes `tests/golden/probes/<probe>/<fixture>.json`.
2. ~70 golden files under `tests/golden/probes/<probe>/<fixture>.json`.
3. A pytest harness (`tests/golden/test_goldens_match.py`) that invokes `--check` and asserts zero diffs.

**Arch + ADR constraints (load-bearing).**

- `phase-arch-design.md §"Golden files"` — one golden per probe per portfolio fixture; CI diffs live vs. committed; `pytest --update-golden` regenerates; updating is a deliberate PR step.
- `phase-arch-design.md §"Implementation risks"` #5 — golden-file non-determinism is the central hazard; wall-clock + tmp paths + envvar leaks + audit timestamps must be excluded.
- `phase-arch-design.md §"Goals"` G1 — every Layer B–G language-agnostic probe ships with golden-file coverage.
- ADR-0001 (closed binary set), ADR-0003 (heaviness sort → dispatch order in goldens), ADR-0004 (image-digest as declared-input token — must be preserved, not excluded), ADR-0005 (no plaintext persisted — `SecretRedactor` chokepoint), ADR-0006 (`IndexFreshness` location — `Stale(reason=CommitsBehind(...))` literal), ADR-0010 (`RedactedSlice` smart constructor shape).
- **Phase 1 S6-01 HARDENED (2026-05-15)** lessons (CRITICAL precedent — this story did not pick all of them up): (a) the canonical envelope has top-level `{schema_version, generated_at, repo, probes}` — **no `audit` block** (audit `RunRecord` is a sidecar at `.codegenie/context/runs/*.json`); the only top-level non-deterministic fields are `generated_at` and `repo.git_commit`; (b) sentinel-normalization preserves required-field shape rather than field deletion; (c) two-run-byte-identical is **a CI test**, not a PR-description claim ("humans miss things; CI doesn't"); (d) `_GOLDEN_PAIRS` is the Open/Closed seam.

**Existing implementation state (read at validation time).**

- `scripts/regen_golden.py` does NOT yet exist on disk (Phase 1 S6-01 is HARDENED but not yet executed per attempt-log scan up to S5-05).
- `tests/golden/` does NOT yet exist on disk.
- `src/codegenie/output/sanitizer.py::_PATTERNS` exists at module level (line 283); 5 pattern classes (`aws_access_key`, `github_token`, ..., `anthropic_key`) — importable source-of-truth for ADR-0005 (verified by grep).
- S7-01 + S7-02 both HARDENED; portfolio fixtures and `_shape_test_kernel.py` (at `tests/fixtures/_shape_test_kernel.py`) ready to be consumed.

**Critical ambiguity surfaced.** Story's Implementation Outline §1 says "Read Phase 1's `scripts/regen_golden.py` (from S6-01). Understand the convention" — but S6-01 hasn't been executed. The story's "Depends on" only lists S7-02. If the executor runs S7-03 before S6-01 has executed, the script must be created from scratch. **Resolved by editing**: "Depends on" annotated; `Notes for the implementer` describes both branches (extend if S6-01 has shipped; create from scratch with the `--portfolio` mode reserved as the only mode if not, leaving the `--fixture-yaml` mode open for S6-01 to land later — Open/Closed).

## Stage 2 — Critic reports (consolidated)

### Coverage critic — Verdict: HARDEN

- **[block] Cv1** — AC-27 defers the two-runs-byte-identical to "advisory in this story; gated in S8-03." But S6-01's HARDENED report explicitly elevated this from manual sha256 to a unit test: "humans miss things; CI doesn't." S7-03 must pick that lesson up *now*, not defer. **Fix applied** — AC-27 rewritten: ships a unit test `test_regen_golden_portfolio_idempotent.py` in this story; S8-03 inherits and runs at portfolio-job lane.
- **[block] Cv2** — AC-16 leaves "Linux-only-skip OR error-out — implementer's call." This is a load-bearing choice and the synthesizer (not the implementer) must pick. Rule 12 (fail loud) dictates error-out; soft-skip on macOS would let a macOS contributor silently commit a partial regen. **Fix applied** — AC-16 picks error-out with structured stderr; documents rationale in `Notes for the implementer`.
- **[harden] Cv3** — AC-25 "target ~70; allowed range 50–90" is a 1.8× spread that hides drift. A future contributor could silently drop a fixture and the count test would still pass. **Fix applied** — AC-25 rewritten: deterministic enumeration via `_compute_expected_golden_count()` + `_PROBE_FIXTURE_MATRIX: dict[ProbeName, frozenset[FixtureName]]`. `COUNT.txt` == matrix size; assertion catches both file-level drift AND matrix-level drift.
- **[harden] Cv4** — No AC for atomicity. SIGINT mid-write leaves a half-written golden; the next `--check` fires confusingly. **Fix applied** — new AC-34: `tempfile.NamedTemporaryFile` + `os.replace`.
- **[harden] Cv5** — No AC for clean-slate per-fixture regen. A stale `.codegenie/cache/` hit could silently produce a different slice shape from the cold path. **Fix applied** — new AC-36: clear `<fixture>/.codegenie/context/` before each gather; log via structlog at INFO.
- **[harden] Cv6** — No AC for Phase 1 fixture coexistence. The story doesn't say whether `node_typescript_helm/` gets per-probe JSON goldens or stays exclusively under S6-01's YAML golden. The two artifacts could collide. **Fix applied** — new AC-38: Phase 1 fixture is NOT swept by `--portfolio`; S6-01's YAML golden is sha256-snapshot-protected; per-probe collision test added.
- **[harden] Cv7** — No AC for "skip `_`-prefixed directories" beyond the prose. **Fix applied** — new AC-40: assert the skip via a temp `_helpers_test/` fixture.

### Test-Quality critic — Verdict: HARDEN

- **[harden] Tq1** — AC-32 hardcodes patterns (`AKIA*`, `ghp_*`, ...) — but `codegenie.output.sanitizer._PATTERNS` is the source of truth. Drift between SecretRedactor and the audit is a silent miss. **Fix applied** — AC-32 amended to import `_PATTERNS` from the production module and parametrize over it.
- **[harden] Tq2** — AC-30 says "5-line unified-diff excerpt" but tests no structural property of the failure message. A future contributor could swap `difflib.unified_diff` for a plain `repr(a) + repr(b)` and AC-30's test would still pass. **Fix applied** — AC-30 rewritten: test asserts `---`, `+++`, and `@@` markers (unified-diff format), not just "5 lines."
- **[harden] Tq3** — AC-7's envvar substring match is a footgun for short/empty envvar values (`$USER == "ci"` would scrub every "ci" string in goldens; empty default `""` would match everywhere). **Fix applied** — AC-7 amended: skip envvars whose value is empty OR < 4 chars OR in a closed deny-list `{"ci", "root", "home", "user", "test"}`; emit WARNING to stderr when skipping.
- **[harden] Tq4** — No mutation test for `_canonicalize` itself. A regression that emits keys un-sorted at level ≥ 2 would only surface as a `--check` diff after the first regen drift — but the first regen would be authored on a developer's machine and the diff suppressed. **Fix applied** — `_compute_expected_golden_count()` derivation (AC-25) + idempotence CI gate (AC-27) cover this together; explicit "_canonicalize unit test" not added since the property is observable via the existing assertions.
- **[harden] Tq5** — `_LIST_SORT_KEYS` is keyed by raw `str` (`"semgrep.findings"`). A typo (`"semgreps.findings"`) is a silent no-op. S7-02's HARDENED `_ProbeName` Literal pattern is the precedent. **Fix applied** — Notes-for-implementer: key the dict by typed `(ProbeName, str)` where `ProbeName` comes from the shared kernel.
- **[harden] Tq6** — `mypy --strict` on the script (AC-31) but the script's recursive `_canonicalize` likely uses `Any` (the story's example shows `payload: Any`). Strict mypy on `Any` is vacuous. **Fix applied** — new AC-39: typed `JsonValue` recursive union; ast-walk test asserts no `: Any` on function args/returns.
- **[harden] Tq7** — `_PRESERVED_FIELDS` inclusion list is implicit in AC-10's "exclusion list does NOT strip `image_digest`" prose, but a future exclusion regex aimed at run-id UUIDs could accidentally scrub `fingerprint` (8-hex BLAKE3). **Fix applied** — new AC-37: module-level `_PRESERVED_FIELDS: frozenset[str]`; inclusion-wins rule; explicit conflict-resolution test.
- **[harden] Tq8** — No AC asserts the Open/Closed seam ("adding a new fixture requires zero `regen_golden.py` edits"). The story states it as a goal but doesn't test it. **Fix applied** — new AC-35: temp `tests/fixtures/portfolio/<new>/` discovery test; `--portfolio-root` flag added to support the test.

### Consistency critic — Verdict: HARDEN

- **[block] Cn1** — Story's Implementation Outline §1 says "Read Phase 1's `scripts/regen_golden.py`" but the file doesn't exist on disk (S6-01 HARDENED but not executed). Executor blocks on a phantom precondition. **Fix applied** — Depends-on annotated; Notes-for-implementer describes the dual-branch (extend if shipped; create from scratch if not, leaving room for S6-01's `--fixture-yaml` mode).
- **[block] Cn2** — S6-01's HARDENED-2026-05-15 lessons #3 ("manual sha256 in PR body promoted to CI gate") was not applied to AC-27. Source-of-truth (S6-01 HARDENED validation report) wins. **Fix applied** — see Cv1.
- **[harden] Cn3** — Story doesn't address that S6-01's golden mechanism (envelope YAML, sentinel-normalization, `_GOLDEN_PAIRS`) and S7-03's mechanism (slice JSON, field-exclusion, walks `tests/fixtures/portfolio/`) coexist in the same script. A reader concludes one replaces the other; the actual story arc has them orthogonal. **Fix applied** — Validation-notes block explains; Notes-for-implementer paragraph spells out the coexistence and the soft-dependency on S6-01.
- **[harden] Cn4** — AC-13's `output_path_relative: ".codegenie/context/raw/scip-index.scip"` — could be scrubbed by AC-7's `tmp` path regex if the regex is broadened (currently safe because `.codegenie/` ≠ `tmp/` ≠ `var/folders/`). But the absence of an explicit inclusion-list (AC-37) means this safety is implicit. **Fix applied** — AC-37 adds `output_path_relative` to `_PRESERVED_FIELDS`.
- **[harden] Cn5** — Phase 1 fixture (`tests/fixtures/node_typescript_helm/`) not under `portfolio/` — story doesn't say what happens to it. S6-01 owns it; S7-03 must not collide. **Fix applied** — see Cv6 / AC-38.

### Design-Patterns critic — Verdict: HARDEN

- **[harden] DP1** — Registry pattern for `_EXCLUDED_FIELD_NAMES` + `_EXCLUDED_VALUE_PATTERNS` is good. Complementary inclusion list `_PRESERVED_FIELDS` for declared-input tokens is missing. **Fix applied** — AC-37.
- **[harden] DP2** — `_LIST_SORT_KEYS` is stringly-typed. **Fix applied** — see Tq5; Notes-for-implementer recommends typed `(ProbeName, str)` keys.
- **[harden] DP3** — Open/Closed seam: "adding a new fixture is a new directory; no script edits." Story states it; doesn't test it. **Fix applied** — see Tq8 / AC-35.
- **[harden] DP4** — `_PROBE_FIXTURE_MATRIX` (newly required by AC-25) is also an Open/Closed seam — adding a probe is one row in the dict, adding a fixture is one entry in each row's frozenset. Pure data; grep-discoverable; mypy-typed. **Endorse**; documented in Notes-for-implementer.
- **[harden] DP5** — Functional-core / imperative-shell: `_canonicalize` should be pure (`JsonValue -> JsonValue`); only `_write_atomic`, `_clear_codegenie_context`, `_run_gather` should be impure. The mypy-strict requirement (AC-31) + AC-39's typed signature force this discipline. **Endorse**; documented in Notes-for-implementer.
- **[harden] DP6** — The `_PRESERVED_FIELDS` vs `_EXCLUDED_FIELD_NAMES` conflict-resolution rule (inclusion wins) is a tagged-union-style protocol but lives in two flat frozensets. A future contributor might invert the order. **Fix applied** — AC-37's `test_preserved_fields_win.py` is the contract test that pins the order.
- **[nit] DP7** — `--portfolio` and (future) `--fixture-yaml` modes — could use argparse subparsers rather than top-level mutually-exclusive flags as the family grows past 2. Not promoted; current 1-mode reality doesn't justify subparsers. Documented in Notes-for-implementer as a deferred Refactor opportunity (Rule 2).

## Stage 3 — Research

Skipped — no critic finding tagged `NEEDS RESEARCH`. All fixes have direct precedents:
- Atomic file write: `tempfile.NamedTemporaryFile` + `os.replace` is the POSIX-portable Python idiom (stdlib).
- Idempotence-as-CI-gate: S6-01 HARDENED precedent (`test_regen_golden_idempotent.py`).
- Pattern import from source-of-truth module: existing `from codegenie.output.sanitizer import _PATTERNS` (`src/codegenie/output/sanitizer.py:283`).
- Typed `JsonValue` recursive alias: PEP 695 / forward-string self-reference is the cleanest Python 3.12 form.
- Inclusion-wins-over-exclusion: Phase 0 ADR-0008 sanitizer + Phase 2 ADR-0005 `RedactedSlice` smart-constructor precedent (preserve 8-hex fingerprints; redact the surrounding cleartext).
- Typed probe-name key: S7-02 HARDENED `_ProbeName` Literal precedent.

## Stage 4 — Synthesizer + conflict resolution

**No critic conflicts.** All four lenses agree on the directional fixes. The block-tier set is mechanically applicable; the harden-tier set tightens audit surfaces, picks up S6-01's HARDENED lessons, and elevates implicit story claims to explicit ACs with test enforcement.

**Edits applied to the story (in order):**

1. `Status:` `Ready → HARDENED (validated 2026-05-18)`.
2. `Depends on:` amended to note Phase 1 S6-01 soft-dependency and dual-branch path.
3. Inserted `## Validation notes (2026-05-18)` block under header documenting every change.
4. **AC-7** amended — envvar substring scrubber gets length + deny-list guards + WARNING-on-skip.
5. **AC-16** rewritten — error-out on non-Linux at `--update`; clear stderr; exit 2; `--check` still works on every platform.
6. **AC-25** rewritten — deterministic count via `_compute_expected_golden_count()` + `_PROBE_FIXTURE_MATRIX`.
7. **AC-26** clarified — PR-description discipline retained but no longer the only safeguard.
8. **AC-27** rewritten — promoted from "advisory in S8-03" to a unit test shipped in this story.
9. **AC-30** rewritten — unified-diff format markers (`---`, `+++`, `@@`) asserted.
10. **AC-32** amended — patterns imported from `codegenie.output.sanitizer._PATTERNS`.
11. **New AC-34** — atomic write (`tempfile.NamedTemporaryFile` + `os.replace`).
12. **New AC-35** — Open/Closed seam test for new fixtures.
13. **New AC-36** — clean-slate `.codegenie/context/` clearance per fixture; structlog-INFO logged.
14. **New AC-37** — `_PRESERVED_FIELDS` inclusion-list + inclusion-wins rule + contract test.
15. **New AC-38** — Phase 1 fixture coexistence; SHA256 snapshot of `node_typescript_helm.repo-context.yaml`; per-probe collision test.
16. **New AC-39** — typed `JsonValue`; ast-walk test against `Any`.
17. **New AC-40** — `_`-prefixed directory skip is an asserted test.
18. **Files-to-touch** — expanded to include all new test files.
19. **Mutation-resistance witness table** — expanded with 11 new rows mapping mutations to the new ACs.
20. **Notes for the implementer** — added paragraphs on:
    - `_LIST_SORT_KEYS` typed-key pattern.
    - S6-01 / S7-03 coexistence and dual-branch path.
    - macOS error-out rationale (Rule 12 / fail loud).
    - Why `_PRESERVED_FIELDS` is necessary and inclusion-wins is load-bearing.
    - `JsonValue` recursive type and the I/O-boundary `cast`.

**ACs touched:** AC-7, AC-13 (implicit via Notes), AC-16, AC-25, AC-26, AC-27, AC-30, AC-32 modified. New: AC-34, AC-35, AC-36, AC-37, AC-38, AC-39, AC-40. Total ACs net: 33 → 40.

## Final verdict

**HARDENED.** The story now:

- Picks up Phase 1 S6-01's HARDENED lessons that were written *after* this story was originally drafted: idempotence-as-CI-gate (not PR-description claim) and fail-loud on platform divergence (not implementer's call).
- Specifies how the slice-JSON golden mechanism (S7-03) coexists with the envelope-YAML golden mechanism (S6-01) — two artifacts, two paths, two shapes, one shared `_canonicalize` helper, zero collisions.
- Tightens the deterministic-count guarantee: `_PROBE_FIXTURE_MATRIX` is the single source of truth; the count is computed, not estimated; both matrix-level and file-level drift trip the same test.
- Picks up source-of-truth references for ADR-0005 (`SecretRedactor._PATTERNS`) — drift becomes ImportError, not silent miss.
- Adds inclusion/exclusion complementarity (`_PRESERVED_FIELDS` vs `_EXCLUDED_FIELD_NAMES`) with an explicit "inclusion wins" contract test.
- Asserts the Open/Closed seam for new fixtures with a real test (zero edits to `regen_golden.py` to add a fixture).
- Enforces functional-core/imperative-shell discipline via the typed `JsonValue` signature; mypy --strict does real work on `_canonicalize`.
- Guards against atomicity, clean-slate, envvar-substring, macOS divergence, and Phase 1 fixture collision failure modes — each with a specific test, not just prose.

Ready for `phase-story-executor`.
