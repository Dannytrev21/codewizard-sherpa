# Validation report — S2-02 `NodeBuildSystemProbe`

**Story:** [S2-02-node-build-system-probe.md](../S2-02-node-build-system-probe.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S2-02 is the **first new probe of Phase 1** — the proof point that Phase 0's frozen spine + Step-1's shared primitives compose into a working probe without editing chokepoints. It is also the only Phase-1 probe that invokes an external binary (`node --version`, ADR-0001-gated). The story was directionally sound and well-anchored in the arch, but three blocking issues and ~15 harden-tier gaps surfaced from running the four parallel critics:

- **One ABC-contract violation** (tuple class attributes vs. frozen `list[str]` ABC at `src/codegenie/probes/base.py:70-73`) that would have failed `mypy --strict` + `tests/unit/test_probe_contract.py` from the first commit.
- **One missing load-bearing AC** for the ADR-0001 env-strip path (the entire `node --version` cross-check is admissible only via `exec.run_allowlisted`; an implementer could ship a passing-test direct `subprocess.run` and silently break the security defense).
- **One missing test-infrastructure preamble** (`_run_probe`, `_stub_exec_returning`, monkeypatch targets all undefined — a `monkeypatch.setattr(subprocess, ...)` instead of `codegenie.exec.run_allowlisted` would bypass the env-strip wrapper entirely).

The synthesizer rewrote ACs from **13 single-bullet items + 8 TDD tests** to **22 individually-verifiable ACs + 18 TDD tests** (10 of which are parametrized to multiply the effective coverage), introduced **three module-level precedence tuples** as Open/Closed extension points (`_LOCKFILE_PRECEDENCE`, `_BUNDLERS_SORTED`, `_NODE_VERSION_PINNED_SOURCES`) following S2-01's `_MONOREPO_PRECEDENCE` precedent, and pinned typed-exception → `errors[]` semantics matching the S1-08/S2-01 hardening pattern.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (Phase 1 arch + ADR-0001/0002/0004/0007/0008/0010 + the frozen Phase 0 ABC) plus the S2-01 hardened-story precedent. Stage 3 (researcher) skipped per skill's token-economy guidance.

## Most load-bearing fixes (block-tier)

1. **ABC-contract violation — tuple class attributes (Consistency Finding 1).** Original AC-1 specified `applies_to_languages=("javascript","typescript")`, `applies_to_tasks=("*",)`, `requires=("language_detection",)`. The frozen `Probe` ABC at `src/codegenie/probes/base.py:70-73` declares `list[str]`; Phase 0's `LanguageDetectionProbe` uses `list[str] = ["*"]`. Tuple class attributes would fail `mypy --strict` against the override (LSP-bound), and `Registry.for_task`'s `set(cls.applies_to_languages)` works coincidentally on tuples — fragile. Hardened: AC-1 now mandates `list[str]` exactly matching the ABC; a new T-9 (`test_probe_contract_attributes_match_arch_design`) anchors the contract against the frozen ABC.

2. **Missing ADR-0001 env-strip AC (Coverage Finding 3).** The whole `node --version` cross-check is admissible *only* because `exec.run_allowlisted` strips secret-bearing env vars (`SSH_AUTH_SOCK`, `AWS_*`, `GITHUB_TOKEN`, …) before exec. The original story buried this in Notes-for-implementer with no AC enforcing it. An implementer could `subprocess.run(["node", "--version"])` and pass every test. Hardened: new AC-12 mandates `exec.run_allowlisted` as the sole subprocess entry, names the `timeout_s=5` literal, and prescribes a sentinel test (T-15) that proves the seam (a stub installed on `codegenie.exec.run_allowlisted` *is* what the probe calls — implementer cannot import-alias around the seam).

3. **Test-infrastructure preamble undefined (Test-Quality Finding 1, cross-listed with Design-Patterns Finding 5).** Five test helpers (`_run_probe`, `_stub_exec_returning`, `_stub_exec_raising`, `_minimal_envelope_with_node_build_system`, `_expect_schema_violation_at`) were referenced but never defined. Most dangerously, the `monkeypatch` target for the exec stub was unspecified — patching `subprocess.run` bypasses the env-strip; patching `codegenie.exec.run_allowlisted` verifies the seam. Hardened: TDD plan now opens with an explicit **Test helpers preamble** defining all five inline, and Notes-for-implementer mandate `from codegenie import exec as _exec` import discipline so the monkeypatch target is unambiguous.

## Coverage gaps closed (harden-tier)

- **AC-4 split** into AC-4a (depth>4 with no cycle → `tsconfig.extends_depth_exceeded`) and AC-4b (cycle → `tsconfig.extends_cycle`); the arch's edge-case row 5 distinguishes both triggers, but the original story collapsed them. T-3 (cycle) is now parametrized over self-cycle, 2-hop with relative-path aliasing, and 3-hop; T-10 is new for depth boundary (depth-4 OK, depth-5 warns).
- **AC-6 split** into AC-6a (regex match → resolved set), AC-6b (regex failure → `node.version_unparseable` + confidence stays high), AC-6c (binary absent / `TimeoutExpired` / `ExecError` → null, *no warning emitted*). Original AC conflated paths; the "no warning when binary is absent" subtlety needs to be its own observable.
- **AC-7 new** for `node.version_declared_resolved_disagree` testing — original story listed the warning but had zero TDD coverage for either the disagreement OR the agreement (silent-skip) case.
- **AC-8 new** for `packageManager` agreement negative-case (when `package.json#packageManager` agrees with the lockfile pick, no warning fires). Original T-7 only covered the disagreement case; a naive "always emit the warning" implementation passed.
- **AC for memo-consumption invariant (AC-13)** — original AC-3 said "via memo when available; fallback when None" but had no observable that pinned the *ordering* (memo first, fallback second). Hardened: when `ctx.parsed_manifest` is not None, the probe consults it exactly once for `package.json`; an implementation that ignores the memo and calls `safe_json.load` always would pass AC-3 (claiming memo "was None") but fail AC-13. T-17 (memo branch) + T-18 (fallback branch) anchor both.
- **AC for typed-exception → `errors[]` (AC-14)** matching S2-01's hardening pattern: `SizeCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError`, `DepthCapExceeded` land typed IDs in `ProbeOutput.errors` (NOT `warnings`), per ADR-0007 line 50. T-16 parametrized over the three `package.json` failure modes; symlink case uses a real symlink creation under `tmp_path`.
- **AC for `output_artifacts` rule (AC-15)** — resolves the Green-vs-Refactor internal contradiction. Pin: `output_artifacts = package.json#files` when present as a list of strings, else `[]`. Removes the "if cheap" unverifiable hedge.
- **AC for `package_manager_version` (AC-16)** — Phase 1 explicitly leaves it `null`. The lockfile parses (S3-05) will populate it later. Silence in the original was a coverage smell flagged by Coverage Finding 7.
- **AC for `engines.node` / version source routing (AC-17)** — anchors the `BuildSystemSlice` field semantics (constraint vs. pinned), not the precedence chain order. Closes Consistency Finding 8.
- **AC for `scripts` edge cases (AC-18)** — missing key / null / empty / non-string-values rule. Pin: missing/null/empty → `commands = {}`; non-string values **skipped** (not coerced) with no warning emitted (silent — `scripts` non-string values are a `package.json` schema violation upstream; the probe is not a `package.json` linter). Original AC-3 was silent on all three.
- **AC for single-lockfile sanity (AC-19)** — `package-lock.json` alone → `package_manager: "npm"`, `additional_lockfiles: []`, NO `multi_lockfile` warning, `confidence: high`. An "always emit warning" mutation would pass every other AC.
- **AC for registry membership (AC-20)** extends original AC-10 to test both `frozenset({"javascript"})` and `frozenset({"typescript"})` and `frozenset({"go"})` (skip case).

## Test-Quality gaps closed (harden-tier)

- **Contract-attributes test (T-9 new)** anchors AC-1 — class attributes drift would silently break Wave-1 ordering (`requires=[]` instead of `["language_detection"]`) and cache-key invalidation (14-entry `declared_inputs` shrinking to 13). Asserts every attribute *and* the verbatim 14-entry `declared_inputs` list.
- **Lockfile-precedence total-ordering (T-1 parametrized)** — replaces the 2-lockfile original with 5 parameter cases covering all-four-present (proves precedence ordering), 3-of-4 (pnpm wins), 2-of-4 (yarn vs npm), single (no warning), and a non-adjacent pair (bun + npm — proves runners-up ordering is *by precedence*, not by alpha).
- **`extends` depth boundary (T-10 new)** — depth-4 must NOT warn; depth-5 MUST warn `tsconfig.extends_depth_exceeded`. An off-by-one mutation (`if depth > 5:`) would have passed the original cycle test.
- **`extends` cycle parametrized (T-3 expanded)** — covers self-cycle, 2-hop with relative-path aliasing (`./a.json` vs `a.json` resolving to the same absolute path — this is the Notes-for-implementer gotcha that was previously untested), and 3-hop.
- **Node-version-pinned precedence parametrized (T-4 expanded)** — covers the four-source chain via four parameter cases proving each source wins in turn when the higher-precedence sources are absent. A mutation that swaps `.node-version` and `.tool-versions` order would have passed the original test.
- **`packageManager` agreement negative test (T-7b new)** — when `packageManager == "pnpm@8.6.0"` agrees with the pnpm lockfile, the disagree warning must NOT fire.
- **`version_declared_resolved_disagree` (T-13 + T-14 new)** — disagree case warns + confidence stays high; agree case emits no warning. The "parseable as semver" rule pinned: leading `v` is stripped; `^v?\d+\.\d+\.\d+` must match both sides; unparseable on either side → silent skip (no false-positive on `.nvmrc` content `lts/hydrogen`).
- **Bundler determinism parametrized (T-12 new)** — three parameter cases proving sort-determinism across shuffled dep orderings; one negative case (no bundler dep → `bundler: null`).
- **ADR-0007 pattern self-assertion in T-5** — strengthens hostile-shim test: every warning ID emitted by the probe matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. A mutation emitting `"NodeVersionUnparseable"` would have failed the schema check downstream; this test catches it at the unit boundary.
- **`node` exception family parametrized (T-6 expanded)** — `FileNotFoundError`, `TimeoutExpired`, `ExecError` all map to `node_version_resolved_locally: null` + no warning + confidence unaffected. Original only tested `FileNotFoundError`.
- **Memo branch tests (T-17 + T-18 new)** — verify both the memo-consulted branch (`ctx.parsed_manifest` is a counting wrapper; `call_count == 1`) and the fallback branch (`ctx.parsed_manifest is None`; `safe_json.load` invoked).
- **Typed-exception → errors[] (T-16 parametrized)** — `SizeCapExceeded` (6 MB body), `MalformedJSONError` (truncated JSON), `SymlinkRefusedError` (real symlink to outside `tmp_path`). All three IDs land in `out.errors`, NOT `out.warnings`.
- **Two-run determinism (T-19 new)** — same input, two runs, `json.dumps(slice, sort_keys=True)` must be byte-equal. Catches any insertion-order-dependent behavior in bundler/lockfile/scripts dict iteration.
- **`probe.parser.cap_exceeded` + `parser_kind` log field (T-20 new)** — observability anchor; `structlog.testing.capture_logs` verifies the `parser_kind` field appears with value `"jsonc"` on tsconfig parse.
- **env-strip sentinel (T-15 new)** — proves the probe routes through `codegenie.exec.run_allowlisted` and nowhere else; if the implementer slips a direct `subprocess.run` call, this test fails.

## Design-Pattern opportunities lifted into ACs (Open/Closed at file boundary)

Three precedence chains live inside this one probe (lockfile, bundler, node-version-pinned). The within-file rule of three is met three times over. Each was originally prescribed as branching code; each is now mandated as a module-level precedence-ordered tuple — matching S2-01's `_MONOREPO_PRECEDENCE` precedent.

- **AC-2 strengthened — `_LOCKFILE_PRECEDENCE: tuple[tuple[str, str], ...]`** (filename, package_manager_name) pairs. Adding Deno in Phase 2 = one tuple-entry insertion + one `Literal` addition + one fixture test, **zero edits to selection logic**. T-1 includes a sibling assertion locking the tuple order.
- **AC-9 strengthened — `_BUNDLERS_SORTED: tuple[str, ...]`** module-level alpha-sorted tuple (matches the arch's "deterministic-sorted" prescription verbatim; the Design-Patterns critic's "vite-before-esbuild" counter-proposal is recorded in Notes-for-implementer as a deferred Phase-2 consideration but **not** elevated here — Rule 7, surface conflicts, don't average; the arch wins).
- **Implementation outline strengthened — `_NODE_VERSION_PINNED_SOURCES: tuple[tuple[str, Callable[[Path], str | None]], ...]`** with three pure extractor functions (`_read_nvmrc`, `_read_node_version`, `_read_tool_versions_node`). The `run(...)` body iterates this tuple in one line. Phase-2 Volta addition becomes a one-line insertion. The three extractors are unit-testable in isolation, closing Design-Pattern Finding 4's pure-vs-impure tangle.

The pure-helper refactor also extracts `_parse_node_version_output(stdout: str) -> str | None` and `_select_package_manager(present: Sequence[str]) -> tuple[str | None, list[str]]` — each independently testable; the hostile-shim regex test (T-5) becomes a trivial table-driven test against the pure helper.

## Patterns DELIBERATELY deferred (premature-abstraction guard)

- **Shared `probes/_precedence.py` kernel** (`first_match(root, precedence) -> (picked, runners_up)`). Within-file rule-of-three is met (3 tuples in S2-02 alone); but cross-probe rule-of-three is NOT (S3-05 has a different precedence list — no bun for `NodeManifestProbe`'s lockfile parsing; sharing forces a parameterized callable for a 5-line scan in each module). Defer until a fourth file replicates the shape. Documented in Notes-for-implementer.
- **`LockfileSelection` tagged union** (`SinglePresent | MultiplePresent(list[str]) | Absent`). Dict shape is JSON-schema-validated and consumed once. Re-evaluate at the fourth consumer.
- **`NodeVersionOutcome` sum type** (`ResolvedLocally | Unparseable | Absent | Timeout`). One callsite. Notes-for-implementer mentions it as a Phase-2 candidate when more probes invoke external binaries.
- **`ParserKind: TypeAlias = Literal[...]`** in `codegenie.logging`. Only `jsonc` + `safe_json` are emitted from this probe; defer the closed-set type until a fourth probe emits the field.
- **YAML catalog extraction for bundlers / lockfiles.** Same rule-of-three guard as S2-01's framework-seed.

## Conflict resolutions surfaced (per Rule 7)

- **CV-10 vs DP-2 (bundler sort order):** Coverage critic said "alpha-sorted via module tuple"; Design-Patterns critic proposed intentional priority order with rationale ("vite uses esbuild internally → vite wins"). Per validator priority `Consistency > Coverage > Test-Quality > Design-Patterns`, and per Rule 7 (surface, don't average), the arch's "deterministic-sorted" wording is interpreted as **alpha-sorted** — the simplest, most-reviewable reading. The Design-Patterns critic's intentional-priority alternative is recorded in Notes-for-implementer as a deferred Phase-2 consideration, **not** elevated here. If a future Phase-2 ADR opts in to intentional priority, the constant gains a comment block; the file-boundary seam is unchanged.
- **DP-8 (iterative walker) vs the story's recursive `_walk_extends`:** Design-Patterns critic preferred iterative-with-explicit-stack (matching `language_detection._walk`). Per Rule 11 (match codebase conventions), the iterative shape is recommended in Notes-for-implementer; but the recursive form with `visited: set[Path]` + explicit `depth` parameter is admissible given the depth-4 cap. The story keeps the recursive form in the outline (Rule 3 — surgical changes) and mentions the iterative alternative as a refactor opportunity.

## Departures from arch surfaced (per Rule 7)

- **Open Question #3 (`packageManager` vs lockfile)** is resolved by this story as "lockfile wins" with `package_manager.declaration_lockfile_disagree` warning. The arch §"Open questions" #3 calls it a *recommendation*, not a ratified decision. The story now flags this in Notes-for-implementer with a TODO pointing to a future Phase-1.5 or Phase-2 ADR upgrade. (Consistency Finding 9.)
- **ADR-0007 citation in `ADRs honored` line** disambiguated: this story cites *Phase 1* ADR-0007 (warning-ID pattern), and *honors* Phase 0 ADR-0007 (probe contract frozen — preserved by subclassing). Both are now named explicitly.
- **Phase-0 vs Phase-1 schema cap convention.** The story now mandates `safe_json.load(path, max_bytes=5*1024*1024, max_depth=64)` for the `package.json` fallback path, matching `ParsedManifestMemo._MAX_BYTES`. Original AC was silent (would have failed because `safe_json.load`'s `max_bytes` is a required keyword argument).

## Context Brief (Stage 1)

**Story intent.** Lands `NodeBuildSystemProbe` — the first new probe of Phase 1 and the proof point that Phase-0 spine + Step-1 primitives compose without editing chokepoints. Populates `build_system` slice from: lockfile-precedence existence check (no parse), `package.json` via memo, `tsconfig.json` via `jsonc` with depth-4 `extends` walker + cycle detection, four-source Node-version precedence chain, optional `node --version` cross-check (ADR-0001-gated), bundler dict-lookup, scripts verbatim. Cold p50 ~250 ms; warm ~5 ms.

**Phase-1 exit criteria the story must satisfy.** ADR-0001 (env-strip; display-only output regex), ADR-0002 (`parsed_manifest` memo consumed), ADR-0004 (sub-schema `additionalProperties: false` at root), ADR-0007 (warning-ID pattern), ADR-0010 (slice optional at envelope). Phase-0 chokepoints (`base.py`, `registry.py`, sanitizer, coordinator) untouched — extension by addition.

**Load-bearing constraints from arch.** Component-design #2 (lines 475–490 of `phase-arch-design.md`) specifies internal structure precisely. Edge cases 5 (tsconfig cycle / depth>4), 6 (hostile-shim garbage output → confidence stays high), 7 (multi-lockfile), 16 (memo TOCTOU safety) are named explicitly. Errors go to `ProbeOutput.errors[]` (typed exception IDs per ADR-0007 line 50); warnings to `slice["warnings"]` (soft-degrade IDs per ADR-0007 pattern).

**Sibling pattern to mirror.** `src/codegenie/probes/language_detection.py` — `@register_probe` decorator, module-level structlog `_log`, structured `EVENT_*` constants in `codegenie.logging`, iterative walker with explicit stack, frozen module-level constants.

**The S2-01 hardening precedent.** Just landed: `_MONOREPO_PRECEDENCE` precedence-ordered tuple as file-boundary Open/Closed extension point; typed-exception IDs in `ProbeOutput.errors` (NOT slice warnings); ADR-0007 pattern constraint on **both** `warnings[]` and `errors[]` in sub-schema; import-time frozenset assertion that every emitted ID matches the pattern. S2-02 inherits the discipline.

## Critic reports (Stage 2 — condensed)

### Coverage critic — Verdict: HARDEN

13 findings; 1 block (env-strip AC missing), 9 harden, 3 nit. Highlights:

- F-3 [BLOCK]: Add AC for ADR-0001 env-strip path via `exec.run_allowlisted` + sentinel test.
- F-1: Split AC-4 (depth>4 ≠ cycle); F-2: Split AC-6 (success / unparseable / absent each distinct outcomes).
- F-4: Extend ADR-0007 pattern constraint to both `warnings[]` and `errors[]`; add import-time frozenset assertion.
- F-5: Enforce memo-consumption invariant; F-6: Pin `output_artifacts` rule; F-7: Decide `package_manager_version` field; F-8: Add single-lockfile sanity AC; F-9: Pin "parseable as semver" rule for the disagree warning; F-10: Pin bundler tuple ordering; F-11: Add JS-only registry filter test; F-12: Verifiable ADR-0010 envelope-optional check; F-13: Decide scripts edge cases.

### Test-Quality critic — Verdict: HARDEN

15 findings; 3 block, 11 harden, 1 nit. Highlights:

- F-1 [BLOCK]: Test helpers undefined + monkeypatch target unspecified (env-strip bypass risk).
- F-2 [BLOCK]: Contract-attributes test missing (T-9).
- F-3 [BLOCK]: Replace lockfile-precedence test with parametrized total-ordering (T-1).
- F-4–F-14: Add depth-4-OK-vs-5-warn, parametrize cycle (3 cases), parametrize node-version precedence, add packageManager agreement test, add disagree warning test, parametrize bundler determinism, strengthen T-5 with ADR-0007 pattern, parametrize exec exceptions, add memo+fallback tests, add typed-exception tests, add determinism test.
- F-15 [nit]: Add `parser_kind` log-field test.

### Consistency critic — Verdict: BLOCK → HARDENED after edits

9 findings; 1 block (tuple vs list ABC), 4 harden, 4 nit. Highlights:

- F-1 [BLOCK]: Tuple class attributes violate frozen ABC `list[str]`.
- F-2: Specify `safe_json.load` cap on fallback (5 MB / depth 64).
- F-3: Document the S1-08-landed `content_hash`-keyed adapter in Notes.
- F-4: Internal contradiction on `output_artifacts` Green vs Refactor.
- F-5: Typed-exception → `errors[]` should be AC, not just outline.
- Nits: tier/requires orthogonality; ADR-0007 Phase 0 vs Phase 1; routing rule clarity; "lockfile wins" needs ADR.

### Design-Patterns critic — Verdict: HARDEN

8 findings; 0 block, 5 harden, 3 nit. Highlights:

- F-1: `_LOCKFILE_PRECEDENCE` tuple as data, not branching.
- F-2: `_BUNDLERS_SORTED` ordered tuple (resolution: alpha per arch).
- F-3: `_NODE_VERSION_PINNED_SOURCES` tuple + pure extractors.
- F-4: Functional core / imperative shell — extract 3 more pure helpers.
- F-5: Pin `monkeypatch` target via `from codegenie import exec as _exec`.
- F-6 nit: defer `ParserKind` Literal until 4th probe.
- F-7 nit: document `output_artifacts` entries as globs.
- F-8 nit: prefer iterative-with-explicit-stack walker (Rule 11).

## Edits applied (summary)

| Region | Before | After |
|---|---|---|
| Header `Depends on:` | S1-04 + S1-10 | S1-04 + S1-07 + S1-08 + S1-10 (memo + adapter dependencies) |
| Header `ADRs honored:` | ADR-0007 ambiguous | ADR-0007 (Phase 1; warning-ID pattern); Phase 0 ADR-0007 preserved via subclassing |
| Validation notes block | absent | added (records this validation) |
| AC count | 13 | 22 |
| TDD test count | 8 | 18 (10 parametrized) |
| AC-1 | tuple attrs | `list[str]` attrs matching frozen ABC |
| AC-3 | "via memo when available; fallback when None" | + explicit `max_bytes=5*1024*1024, max_depth=64` for fallback path + memo-consumed-exactly-once observable |
| AC-4 | merged depth + cycle | split into AC-4a (depth>4) + AC-4b (cycle); each anchored to the correct warning ID |
| AC-6 | merged 3 paths | split into AC-6a (success) + AC-6b (unparseable warn) + AC-6c (absent silent) |
| AC-7 (new) | — | `node.version_declared_resolved_disagree` rule with explicit "parseable as semver" definition |
| AC-9 | bundler set + "deterministic-sorted" | `_BUNDLERS_SORTED` module-level alpha tuple + first-hit rule |
| AC-12 (new) | — | env-strip via `exec.run_allowlisted` (load-bearing) |
| AC-13 (new) | — | memo-consumption invariant (`call_count == 1`) |
| AC-14 (new) | — | typed-exception → `errors[]` IDs (matches ADR-0007 + S1-08/S2-01 pattern) |
| AC-15 (new) | — | `output_artifacts` from `package.json#files` rule |
| AC-16 (new) | — | `package_manager_version: null` in Phase 1 (deferred to S3-05) |
| AC-17 (new) | — | version routing rule anchored to `BuildSystemSlice` field semantics |
| AC-18 (new) | — | `scripts` edge cases (missing / null / empty / non-string) |
| AC-19 (new) | — | single-lockfile sanity (no spurious warning) |
| AC-20 | original AC-10 minus duplicates | registry filter tested for `frozenset({"javascript"})` + `frozenset({"typescript"})` + `frozenset({"go"})` (skip) |
| Impl outline | inline branching | 3 module-level precedence tuples + 4 pure helpers (functional core) |
| Refactor step | extract `_walk_extends` only | extract 4 pure helpers (`_walk_extends`, `_select_package_manager`, `_parse_node_version_output`, `_read_*` triple) |
| Notes-for-implementer | 6 bullets | 11 bullets (adds: import `exec` as `_exec`, monkeypatch target discipline, iterative-walker alternative, deferred patterns guard, packageManager-vs-lockfile ADR TODO, bundler intentional-priority deferred consideration) |

## Verdict

**HARDENED.** Story is ready for `phase-story-executor`. The TDD plan now mutation-resists a deliberately-wrong implementation (precedence inversion, dict-insertion-order bundler, naive subprocess bypass, off-by-one extends depth, swallowed typed exceptions). Open/Closed seams are pinned at the file boundary for three independent extension axes (new lockfile kinds, new bundlers, new Node-version-pinned sources).
