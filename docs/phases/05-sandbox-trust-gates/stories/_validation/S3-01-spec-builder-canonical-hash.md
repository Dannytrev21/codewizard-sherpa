# Validation report: S3-01 — `SandboxSpecBuilder.for_gate` + canonical `sandbox_spec_hash`

**Validated:** 2026-05-23
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-01 ships the single translator from `(gate, attempt, GateContext)` → frozen `SandboxSpec`, with a BLAKE3-128 `sandbox_spec_hash` whose byte-stability the entire Phase-3 integration test golden-file suite — and Phase 9's Temporal idempotency design — both rest on. The draft correctly identified the deliverables (canonical-JSON hash, env-allowlist integration, golden + property test) and traced cleanly to ADR-0012 and ADR-0001, but the AC set under-specified the dependency-injection boundaries, the multi-phase → flat-spec semantic gap, and the ADR-0011 "at minimum" hash-input clause. An executor following the draft literally would have:

1. Typed against phantom `EnvAllowlist` and `GateCatalogLoader` classes (S1-05 / S1-06 HARDENED ship module-level functions, not classes).
2. Silently read `os.environ` directly to fill `host_env` (since `GateContext` has no such field — S1-04 HARDENED contract).
3. Omitted `required_signals` from the hash input, violating ADR-0011 Consequences ("the hash includes — at minimum — all `SandboxSpec` fields plus the base-image digest plus the gate's required-signals tuple").
4. Silently collapsed a non-empty `phases` list with an arbitrary rule (since the arch is incomplete on this point), producing a spec that S3-05 would then have had to debug to undo.

22 findings were lodged across all four critic lenses, including ten block-tier. Every finding was patchable in place; the multi-phase collapse problem (the closest-to-RESCUE finding) was contained by scoping S3-01 strictly to the stub's empty-phases shape and fail-loud-ing on non-empty phases — pushing the resolution to S3-05 where it belongs. The story now carries ~70 numbered ACs across 19 structured sections (was 9 unnumbered bullets) plus a five-test-file TDD plan with hypothesis-based property tests, a cross-Python-minor portability gate, a module-purity AST walker, mocked defense-in-depth tests for `SandboxSpecForbidden`, and explicit Notes-for-implementer prose on the phase-collapse semantic gap.

## Findings by critic

### Coverage critic

| Severity | Finding |
|---|---|
| block | `GateContext.host_env` doesn't exist; story silently invented a field — resolved via DI port `host_env_source` (AC-DI-3, AC-ENV-1). |
| block | Multi-phase catalog → flat SandboxSpec collapse rules unpinned and the arch is genuinely incomplete — resolved by scoping S3-01 to the stub's empty `phases` shape (AC-PHASES-1) and `NotImplementedError` raise for non-empty (AC-PHASES-2), deferring the semantic resolution to S3-05. |
| block | `copy_in` derivation hand-waved — resolved with a single-entry default (AC-COPYIN-1). |
| block | `Gate.gate_id` consumption rule unpinned — resolved with AC-LOOKUP-1..AC-LOOKUP-3 plus a `Mock(spec_set=["gate_id"])` test that detects any over-read. |
| block | Hash format (length, charset, lowercase) unpinned — resolved with AC-HASH-FORMAT-1..AC-HASH-FORMAT-4 including a defensive `inspect.getsource` check that the literal `length=16` kwarg appears. |
| harden | Per-attempt overrides positive case (attempt 2 applies the override) was in the TDD plan but not an AC — resolved with AC-OVR-1..AC-OVR-5, including AC-OVR-2 fail-loud on `phases` keys in overrides. |
| harden | ADR-0011 inheritance for `required_signals` in hash inputs missing — resolved with AC-HASH-INPUTS-1..AC-HASH-INPUTS-4, including a `<sorted tuple>` clause that pins the set-like semantics. |
| harden | `attempt_overrides` deep-merge semantics for `phases` ambiguous (list-replace vs by-name) — pinned by AC-OVR-2 (raise rather than guess) since this story doesn't need to resolve it. |
| harden | `EVENT_SANDBOX_SPEC_BUILT` constant missing from S1-01 table — resolved via AC-EVT-1 (append-only addition to `sandbox/logging.py`) and AC-EVT-2 (stable field set on emission). |

### Test-Quality critic

| Severity | Finding |
|---|---|
| block | `SandboxSpecForbidden` belt-and-suspenders code path was dead in practice (S1-05's filter guarantees no denied substring slips through) — resolved with AC-DEFENSE-1/-2 mocking a broken filter to prove the assertion path is LIVE. |
| harden | Property test only varied env-dict keys; missed the order-significance distinction across `cmd`/`copy_in`/`egress_allowlist`/`required_signals` — resolved with AC-PROP-1..AC-PROP-7 (separate INVARIANT vs CHANGES properties for each field class). |
| harden | Cross-Python-minor portability gate missing despite ADR-0011 + arch risk #4 explicitly calling it out — resolved with AC-PORT-1 (sidecar `.hash.txt` portability anchor). |
| harden | Golden test brittleness — resolved by adding AC-STRUCT-1..AC-STRUCT-6 structural assertions that survive golden regen. |
| harden | `_canonical_blake3` private-helper test access not pinned — resolved with AC-INTERNAL-1 (helpers documented as test-accessible module-private). |
| harden | `test_attempt2_override_changes_test_cmd` too narrow (a mutation that always appends the magic flag passes) — replaced by parametrized `test_scalar_override_last_wins` covering each scalar field. |
| harden | `test_for_gate_idempotent` missing — resolved with AC-FROZEN-2 + dedicated test. |

### Consistency critic

| Severity | Finding |
|---|---|
| block | `EnvAllowlist` class type does not exist (S1-05 HARDENED ships module-level `filter`) — resolved with DI port `filter_fn: Callable[...]` (AC-DI-2). |
| block | `GateCatalogLoader` class type does not exist (S1-06 HARDENED ships module-level `load`/`load_all`) — resolved with eager-loaded `catalog: Mapping[str, CatalogEntry]` (AC-DI-1). |
| block | Stale return-type reference in story References: `filter(env: Mapping[str,str]) -> Mapping[str,str]` should be `dict[str, str]` per S1-05 AC-FL-1 — fixed. |
| block | Error module path conflated: `GateCatalogInvalid` lives in `gates/errors.py`, not `sandbox/errors.py` — resolved with AC-ERR-1/-2 + Files-to-touch correction. |
| harden | Module purity AST-walker test missing (every S1-* story shipped one) — resolved with AC-PURE-1..AC-PURE-5 + a dedicated `test_spec_builder_purity.py` file. |
| harden | ADR-0011 not cited in "ADRs honored" line — added. |
| harden | ADR-0014 inheritance (extra="forbid"/frozen + no banned-substring field names) not asserted — added AC-PURE-5 (defensive walker on any new Pydantic models declared in the module). |
| harden | `AttemptNumber` newtype unused — resolved with AC-FG-1 (source-level pinning via `typing.get_type_hints`). |
| harden | `frozen=True` reconstruction idiom (`model_copy`) unpinned — resolved with AC-FROZEN-1 (source-level pin via `inspect.getsource`). |
| harden | Coverage floor wording aligned (line ≥ 95% AND branch ≥ 90%, matching S1-02..S1-06). |

### Design-Patterns critic

| Severity | Finding |
|---|---|
| harden | Hexagonal / DI ports under-specified — resolved by promoting all three DI ports (`catalog`, `filter_fn`, `host_env_source`) to first-class kwarg-only constructor parameters with production defaults that tests can override (AC-DI-1..AC-DI-5). |
| harden | Functional core / imperative shell separation not pinned via testable helpers — resolved with AC-FCS-1/-2 enumerating four pure helpers (`_canonical_blake3`, `_deep_merge`, `_assemble_partial_spec`, `_compute_hash_input`) + three dedicated unit tests on the pure layer. |
| nit (surfaced as Note) | Plugin/strategy framing for phase-collapsing deferred per Rule 2 (Simplicity First). Notes record: when S3-05 + Phase-7 distroless both produce non-empty `phases`, the rule-of-three is reached and a `PhaseCollapser` Protocol becomes the right Open/Closed seam. Until then, a switch on `len(phases)` is correct. |

## Research briefs

**None.** Every gap was answerable from Phase 5 arch + ADR-0011 / ADR-0012 / ADR-0014 + the six prior HARDENED reports (S1-02 / S1-03 / S1-04 / S1-05 / S1-06 / S2-01) + the codebase precedents in `src/codegenie/transforms/policy/lockfile_policy.py` (codegenie-owned trusted YAML) and `src/codegenie/schema/validator.py` (lru_cache validator pattern). The BLAKE3 + canonical-JSON hash recipe is documented inline in arch §Implementation-level risks #4.

## Conflict resolutions

- **Coverage vs Rule 2 (Simplicity First) on phase-collapsing.** Coverage critic wanted a `PhaseCollapser` Protocol + registry ACs. Rule 2 wins (single concrete consumer; YAGNI). Resolution: the plug-in shape is recorded in Notes-for-implementer for the future rule-of-three reach; today the implementation is a switch on `len(phases)`.
- **Coverage vs the multi-phase semantic gap.** Coverage critic surfaced the gap as a block (silent collapse would ship the wrong spec). The synthesizer applied the **Rule 12 fail-loud** principle: scope S3-01 to the stub's empty-phases shape (AC-PHASES-1) and raise `NotImplementedError` for non-empty (AC-PHASES-2). The architectural resolution is hand-off to S3-05; the story does NOT autonomously pick a winner among the three plausible designs (collapse to `sh -c` cmd; widen S1-02 to `phases: list[PhaseSpec]`; return `list[SandboxSpec]`).
- **Design-Patterns vs Coverage on `host_env` injection.** Design-Patterns wanted a full Hexagonal port for host env reading; Coverage wanted to pin where `host_env` comes from. Both convergent — resolved with the DI port `host_env_source: Callable[[], Mapping[str, str]] = lambda: types.MappingProxyType(dict(os.environ))` (AC-DI-3).

## Edits applied

### Edit 1 — Header line "ADRs honored:" expanded
- Source: Consistency F6, F7
- Before: `**ADRs honored:** ADR-0012 (static env allowlist), ADR-0001 (chokepoint discipline — builder itself touches no subprocess)`
- After: `**ADRs honored:** ADR-0001 (chokepoint discipline — builder itself touches no subprocess), ADR-0011 (no verdict cache; `sandbox_spec_hash` is the forward-compat seam — hash inputs include all `SandboxSpec` fields + base-image digest + gate's `required_signals` tuple), ADR-0012 (static env allowlist), ADR-0014 (extra="forbid"/frozen Pydantic models + banned-substring field-name walker)`
- Rationale: ADR-0011 owns the hash recipe's "at minimum" clause; ADR-0014 governs Pydantic config inheritance for any models declared in this module; both were missing.

### Edit 2 — Header `Status: Ready` → `Status: HARDENED`
- Source: synthesis-stage verdict
- Rationale: validator's standard suffix for stories that have been hardened (matches S1-06 / S2-01..S2-03 precedent).

### Edit 3 — Depends-on line expanded
- Source: Consistency F1, F2, F5
- Before: `**Depends on:** S1-05 (registries + `env_allowlist`), S1-06 (YAML catalog schema + loader)`
- After: explicit list of S1-02, S1-04, S1-05, S1-06 (each with the specific symbol the story consumes named in parens)
- Rationale: the executor needs to know which sibling story's contract each import lands against.

### Edit 4 — Inserted "Validation notes" block (top of file, post-header)
- Source: editor.md Step 4
- Content: 22 numbered findings with severity, rationale, and pointer to the new AC code that addresses each
- Rationale: stable breadcrumb visible to anyone reading the story top-down.

### Edit 5 — "References — where to look" section expanded
- Source: Consistency F3, F4; references were stale (`filter(env) -> Mapping[str, str]` should be `-> dict[str, str]`) and incomplete (ADR-0011 missing)
- Before: 18 lines with one stale return-type ref
- After: 30 lines with correct return types, ADR-0011 + ADR-0014 added, codebase precedents for S1-02 / S1-04 / S1-05 / S1-06 each cited with the specific symbols this story consumes, external docs pointer for `model_copy` added
- Rationale: a static reference table the executor's `Read` calls index into.

### Edit 6 — Acceptance criteria — rewrite from 9 unnumbered bullets to 19 structured sections
- Source: Coverage F1..F8, Test-Quality F1..F7, Consistency F1..F9, Design-Patterns F1..F2
- Before: 9 bullets, mixed concerns, vague phrasing on host_env / overrides / hash inputs
- After: 19 sections (A. Public surface, B. Constructor DI, C. for_gate semantics, D. Catalog field mapping, E. Phases collapse, F. copy_in, G. Env filter, H. attempt_overrides, I. Hash recipe inputs, J. Hash invariants property-based, K. Hash format, L. Cross-Python portability, M. Module purity, N. Frozen reconstruction, O. Structlog event, P. Functional core / imperative shell, Q. Golden + structural, R. Errors surface, S. CI floors) with ~70 numbered ACs total
- Rationale: each AC is now individually verifiable; mutation-resistance is encoded; the executor's Validator pass can check each in isolation.

### Edit 7 — Implementation outline — rewritten with explicit dataflow
- Source: Coverage F1 (host_env), F2 (catalog_loader), F4 (copy_in); Design-Patterns F1 (DI port discipline); Consistency F7 (model_copy idiom)
- Before: 5 lines of casual prose with implicit assumptions
- After: 8 explicit steps with concrete dataflow, named pure helpers, named DI ports, named structlog event keys, fail-loud paths called out
- Rationale: a 1:1 map from outline step → AC → test, so the executor's TDD pass has a literal Red list.

### Edit 8 — TDD plan — rewritten with five test files + skeleton code
- Source: Test-Quality F1..F7
- Before: two test files with three+two illustrative tests
- After: five test files (core / property / portability / purity / conftest) with ~20 skeleton tests covering each AC band
- Rationale: each test is mutation-resistant (would fail on an obvious wrong impl); the executor's Validator now has runtime evidence anchors for every AC.

### Edit 9 — Files-to-touch table expanded with explicit action column
- Source: Consistency F8 (errors module path); Test-Quality F2 (portability sidecar); F4 (purity test); F7 (extra fixtures)
- Before: 6 rows, action implied
- After: 10 rows with explicit create/modify column, sandbox/logging.py + sandbox/errors.py + portability sidecar + purity test + expanded conftest fixtures all listed
- Rationale: surgical-change discipline — the executor knows exactly which files to touch and which not to (e.g., GateCatalogInvalid stays in gates/errors.py).

### Edit 10 — Notes-for-implementer expanded
- Source: Design-Patterns F3 (Notes); Coverage F5 (phase-collapse deferred); Consistency F9 (carry-forward from prior validations)
- Before: 6 brief Note bullets
- After: ~30 Note bullets across six themed subsections (carry-forward, hash recipe, frozen idiom, phase-collapse semantic gap, plugin/strategy deferral, DI discipline, common pitfalls, fence-trip diagnostics)
- Rationale: the implementer needs context that doesn't belong in ACs (pattern discussions, prior-validation cross-refs, "what NOT to do") — Notes is the right home.

## Verdict rationale

HARDENED, not RESCUE. The most structural weakness (the multi-phase → flat-spec collapse semantic gap, Coverage F5) is genuinely an architectural under-specification, but it is patchable by scoping S3-01 strictly to the stub's empty-phases shape and raising `NotImplementedError` for non-empty — the populated-catalog case is then a clean S3-05 hand-off with full documentation in Notes. The story's GOAL (translate inputs to a byte-stable SandboxSpec with canonical hash) is correct; only the AC specification needed strengthening.

The phantom-class block findings (`EnvAllowlist`, `GateCatalogLoader`) are real-but-fixable: every other prior phase-5 HARDENED story (S1-02..S2-03) followed the established module-level-function convention, and this story now does too. The ADR-0011 hash-input "at minimum" clause violation is similarly fixable by composing `required_signals` into the hash input dict.

## Recommended next step

`phase-story-executor` to implement.

The story is now ready for the executor:
- Every AC is individually verifiable
- The AC set collectively guarantees the goal
- Every AC has a corresponding test in the TDD plan that would fail on an obviously wrong implementation
- The pure-vs-impure boundary is pinned, so the functional-core unit tests can run in isolation before the imperative shell is wired
- The multi-phase collapse problem is documented as an S3-05 hand-off — no silent shipping of wrong semantics
