# Validation report: S5-03 — Layer C marker probes (`Dockerfile`, `Entrypoint`, `ShellUsage`, `Certificate`)

**Validated:** 2026-05-16
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-03 lands four marker-and-parse probes under `src/codegenie/probes/layer_c/`. The original draft contained two phase-wide Phase-2 architectural mis-statements that propagate the same gap S4-01 already had to fix: (1) `requires=` is **not** a `@register_probe` kwarg (per 02-ADR-0003 Option D) — it lives on the Probe ABC as a class attribute (per `localv2.md §4` and the S5-02 precedent); (2) `ctx.sibling_slices` does **not** exist on the contract-frozen `ProbeContext` (per Phase 0 ADR-0007 and the S4-01 validation report) — sibling-slice access must route through the `read_raw_slices(raw_dir(...))` helper that S4-01 introduced. The story's `ShellUsageProbe`/`EntrypointProbe`/`CertificateProbe` ACs encoded both errors. We also found that the Phase-2 coordinator does NOT topologically sort by `requires` (rejected as Option C in 02-ADR-0003), which means intra-`heaviness="light"` dispatch order is non-deterministic — so the three sibling-slice readers must degrade to `confidence="unavailable"` when the upstream raw artifact isn't yet on disk (mirroring `IndexHealthProbe.IndexerError("upstream_<name>_unavailable")`). Beyond the three consistency blocks, the Dockerfile parser ACs missed nine concrete edge cases (comments, line continuations, case sensitivity, JSON-array vs shell-form `ENTRYPOINT`/`CMD`, multi-pair `ENV`/`LABEL`, `HEALTHCHECK NONE` vs `CMD`, `Containerfile` synonym positive test, `COPY --from=<missing-stage>` typed signal, `ARG` directive); the LOC-budget AC had a 50-line slack that masked real bloat; the directive-coverage test was monolithic; and there was no property-based or mutation-resistance test. The Design-Patterns critic surfaced (a) the rule-of-three threshold for `read_raw_slices` (now 4 consumers — kernel reuse is mandatory) and (b) a tagged-union `Directive` sum-type opportunity for the parser (recorded as an implementer-choice note, not mandated as an AC, per Rule 2 because the LOC budget is the harder constraint). All findings were fixable in place — 4 blocks resolved by AC corrections + new ACs V1/V2/V3; 6 hardens by per-edge-case ACs V4–V11 + parametrized/property/mutation tests; 1 nit by tightening the LOC budget. Verdict: HARDENED.

## Findings by critic

### Coverage critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| K1 | block | `ShellUsageProbe`/`EntrypointProbe`/`CertificateProbe` may race the upstream producers under `heaviness="light"` concurrent dispatch. Story has no AC for the absent-upstream path. | Add AC-V2: emit `confidence="unavailable"`, never raise. Per-probe unit test. |
| K2 | harden | Parser AC misses `#` line comments + `\` line-continuation handling. | Add AC-V4 + dedicated test. |
| K3 | harden | Parser AC misses case-insensitive directives (Dockerfile reference allows `FROM`/`from`/`From`). | Add AC-V5 + parametrized test. |
| K4 | harden | `ENTRYPOINT`/`CMD` AC says "exec vs shell form distinguished" but doesn't pin the JSON-array vs shell-string distinction, nor the malformed-array typed signal. | Add AC-V6 + per-form tests + malformed-array test. |
| K5 | harden | `ENV`/`LABEL` multi-pair on one line not covered (`ENV A=1 B=2`). | Add AC-V7 + test. |
| K6 | harden | `HEALTHCHECK NONE` vs `HEALTHCHECK CMD` distinction not in the AC set. | Add AC-V8 + test. |
| K7 | harden | `Containerfile` synonym named in the marker-absent AC but no positive parse test. | Add AC-V9 + positive parse test. |
| K8 | harden | `COPY --from=<stage>` referencing a non-existent stage has no typed signal. | Add AC-V10 — `from_stage_resolved: bool` flag in the slice. |
| K9 | harden | `ARG` is named in the Implementation outline directive list but missing from the AC set; global ARG before `FROM ${VAR}` semantics (no expansion) not pinned. | Add AC-V11 + test for global + per-stage forms + literal-`${VAR}` capture. |

### Test-Quality critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| T1 | harden | Test 7 `test_dockerfile_directive_coverage` is a single fixture with one of each directive type — failure of any one directive masks the others. | Parametrize per directive; each parametrization minimal; spurious-capture assertion ("all other fields empty"). |
| T2 | harden | No property-based test for the parser; Dockerfile grammar is small enough for a Hypothesis strategy. | Add Test 15 (round-trip property: `parse(text)` → slice → re-render → `parse'` → structurally equal). |
| T3 | harden | No mutation-resistance suite. Tests are mostly happy-path — a parser that silently dropped `RUN` directives or only matched lowercase could still pass. | Add Test 16 — a `parametrize` table of intentionally-broken parser stubs; assert each stub fails at least one named test. |
| T4 | harden (subsumed by Coverage K1) | No tests for the absent-upstream path. | Test 17 (parametrized across three readers). |
| T5 | harden | No structural tests for the `requires` metadata-only commitment or the `read_raw_slices` kernel reuse. | Tests 18 + 19 (docstring grep + AST-walk audit). |
| N1 | nit | LOC-budget AC has a 50-line slack ("≤ 100 LOC, raw < 150") — masks real bloat. | Tighten AC-V12: `cloc`-counted code lines ≤ 100, no slack. |

### Consistency critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| C1 | block | Story says `@register_probe(...requires=[...])`. 02-ADR-0003 picked Option D: decorator accepts only `heaviness` + `runs_last`. `requires` is on the Probe ABC (`localv2.md §4`, frozen). S5-02 set the precedent (`requires: list[str] = []`). | Rewrite ShellUsage/Certificate ACs to declare `requires` as class attribute; explicitly forbid passing `requires=` to the decorator. |
| C2 | block | Story says `requires=[...]` "enforces dispatch order". 02-ADR-0003 explicitly rejected Option C ("rely on `requires=` topology and luck") — the coordinator does NOT topologically sort by `requires`. | Make explicit that `requires` is metadata-only in Phase 2; correctness comes from AC-V2 (graceful absent-upstream), not dispatch ordering. |
| C3 | block | `EntrypointProbe` reads the `dockerfile` slice but the story never declares `requires=["dockerfile"]` for it. Asymmetric with `ShellUsageProbe`/`CertificateProbe`. | Add `requires: list[str] = ["dockerfile"]` to EntrypointProbe AC. |
| C4 | block | `ctx.sibling_slices` does not exist on the contract-frozen `ProbeContext` (Phase 0 ADR-0007; S4-01 validation report F1 explicitly catalogues this). Story implies in-context sibling-slice access. | Rewrite to disk-anchored access via `read_raw_slices(raw_dir(repo.root))` (the S4-01 helper). Add AC-V1 (structural assertion: only sanctioned reader path) + AC-V3 (`requires is metadata-only` docstring requirement). |

### Design-Patterns critic

| ID | Severity | Finding | Proposed fix |
|---|---|---|---|
| D1 | harden | `shell_usage` static-evidence slice is loosely described ("`final_stage_run_commands`") — primitive obsession risk; the slice will land as a list-of-dicts unless typed. | Specify `StaticShellEvidence` + `RunCommandEntry` Pydantic models (`extra="forbid"`, `frozen=True`) — make illegal states unrepresentable. |
| D2 | harden | With B2 (S4-01) + 3 Layer-C readers, this is the **4th** consumer of `read_raw_slices`. Rule-of-three is well past — the helper IS the kernel. Story doesn't mandate reuse. | Add AC-V1 (AST audit: every reader uses the helper, none reimplements disk IO) + Notes-for-implementer paragraph naming the kernel. |
| D3 | harden | `_tokenize_dockerfile_line` is a natural home for a tagged-union sum type (`Directive = FromDirective \| RunDirective \| …`) — exhaustive `match` via mypy `--warn-unreachable` would catch any future-directive omission at compile time. Story names the helper but not the type-shape opportunity. | Promote to Notes-for-implementer (not AC, per Rule 2 — LOC budget is the harder constraint and the alternative `tuple[Literal[...], dict]` shape is acceptable within budget). |

## Research briefs (if any)

None — no findings were tagged `NEEDS RESEARCH`. All issues had clear in-repo precedents (S4-01 validation report for the disk-anchored sibling-slice mechanism; S5-02 for the `requires`-as-class-attribute pattern; S1-08 hardening for the property-based testing precedent; `phase-arch-design.md §"Component design" #4` SecretRedactor for the mutation-test discipline; ADR-0003 for the decorator-signature decision).

## Conflict resolutions

- **Design-Patterns D3 vs Rule 2 (Simplicity First).** D3 initially proposed mandating the `Directive` tagged-union sum type as an AC. Rule 2 wins on the AC question — pattern proposals don't add new ACs that don't trace to the goal; the `_tokenize_dockerfile_line` extract (already in the Refactor step) is the only behaviour-level mandate. The sum-type shape is recorded in Notes-for-implementer with explicit framing: implementer chooses between `Directive` sum type (preferred, structural enforcement via `match` exhaustiveness) and `tuple[Literal[...], dict]` (acceptable, exhaustiveness via convention) based on the AC-V12 LOC budget. Per the editor priority chain: `Consistency > Coverage > Test-Quality > Design-Patterns`, and Rule 2 demotes D3 to a `nit` for the AC layer.
- **Coverage proposal vs scope.** Coverage proposed an AC asserting "two concurrent gathers of the same repo produce byte-identical Layer C slices". Resolved against — that's a Phase-2-wide coordinator-race property, not S5-03's contract. Per-probe AC-V2 (graceful absent-upstream) is the right scope; the cross-probe race is S7-04 (Phase 5) territory.
- **Test-Quality T5 vs Design-Patterns D2.** Both wanted structural enforcement of `read_raw_slices` reuse. Merged: AC-V1 is the behavioral contract; Test 19 is its verification.

## Edits applied

### Edit 1 — Header `Depends on:` + `ADRs honored:` corrected

- **Source:** Consistency C1, C2, C4
- **Before:** `Depends on: S5-02 ..., S3-03 ..., S1-08 (@register_probe)` and `ADRs honored: 02-ADR-0001, 02-ADR-0007`
- **After:** Surfaced S4-01 dependency (the `read_raw_slices` helper), corrected S1-08 to clarify the decorator does **not** accept `requires=`, added 02-ADR-0003 to the ADRs-honored list.
- **Rationale:** The story's dependencies were structurally incomplete — S4-01's helper IS the sibling-slice access mechanism, and 02-ADR-0003 is the load-bearing decision on the decorator signature.

### Edit 2 — `ShellUsageProbe` AC corrected (Consistency C1 + Design-Patterns D1)

- **Before:** `@register_probe(heaviness="light")` ... reads ... slices (`requires=["dockerfile", "runtime_trace"]` enforces dispatch order); ... static evidence: `final_stage_entrypoint_form`, `final_stage_cmd_form`, `final_stage_run_commands` ...
- **After:** Decorator clarified to accept only `heaviness`+`runs_last`; `requires` declared as class attribute matching S5-02 precedent; disk-anchored access via `read_raw_slices(raw_dir(repo.root))` made explicit; typed `StaticShellEvidence` + `RunCommandEntry` Pydantic models named.
- **Rationale:** Restores ADR-0003 consistency; closes the primitive-obsession risk on the slice shape.

### Edit 3 — `CertificateProbe` AC corrected (Consistency C1)

- Same shape as Edit 2: decorator clarified, class-attribute `requires`, disk-anchored access via `read_raw_slices`.

### Edit 4 — `EntrypointProbe` AC corrected (Consistency C1 + C3)

- **Before:** Reads the `dockerfile` slice's `dockerfiles[].entrypoint` field; classifies as exec/shell form. **No `requires` declared.**
- **After:** Declared `requires: list[str] = ["dockerfile"]` as class attribute (matching the C1 fix); disk-anchored access via `read_raw_slices` made explicit.
- **Rationale:** Closes the C3 asymmetry; restores ADR-0003 consistency.

### Edit 5 — AC-V1 through AC-V11 added

- **V1:** Sibling-slice access via `read_raw_slices` (kernel reuse) — Consistency C4 + Design-Patterns D2.
- **V2:** Upstream-slice absent → `confidence="unavailable"`, never raises — Coverage K1.
- **V3:** `requires` is metadata-only docstring requirement — Consistency C4.
- **V4:** `#` comments + line continuations — Coverage K2.
- **V5:** Case-insensitive directives — Coverage K3.
- **V6:** `ENTRYPOINT`/`CMD` JSON-array vs shell-form distinction + malformed-array typed signal — Coverage K4.
- **V7:** `ENV`/`LABEL` multi-pair on one line — Coverage K5.
- **V8:** `HEALTHCHECK NONE` vs `HEALTHCHECK CMD` — Coverage K6.
- **V9:** `Containerfile` synonym positive test — Coverage K7.
- **V10:** `COPY --from=<missing-stage>` typed signal — Coverage K8.
- **V11:** `ARG` directive (global + per-stage; literal `${VAR}` in `FROM`) — Coverage K9.

### Edit 6 — AC-V12 (LOC budget tightened)

- **Before:** "≤ 100 LOC excluding docstrings; enforce via `wc -l` smoke that asserts `< 150` raw lines (allow 50-line slack for docstrings)" — original AC kept for diff continuity but marked superseded.
- **After:** `cloc`-counted (or equivalent) `code` lines per module ≤ 100, no slack — Test-Quality N1.

### Edit 7 — Test 7 parametrized

- **Before:** "single fixture with one of each directive type; assert each is parsed into the matching field"
- **After:** Parametrized per-directive (18 directives), each parametrization minimal, with spurious-capture assertion. Mutation-resistant.

### Edit 8 — Tests 15–21 added

- **15:** Property-based round-trip (Hypothesis) — Test-Quality T2.
- **16:** Mutation-resistance suite — Test-Quality T3.
- **17:** Sibling-slice absent → `confidence="unavailable"` (3 parametrizations) — AC-V2 verification.
- **18:** `requires is metadata-only` docstring grep (3 parametrizations) — AC-V3 verification.
- **19:** AST audit: `read_raw_slices` is the only sanctioned sibling-slice reader (3 parametrizations) — AC-V1 + Design-Patterns D2 verification.
- **20:** Edge-case parser tests (cover AC-V4 → AC-V11).
- **21:** LOC-budget smoke test (`cloc` or equivalent) — AC-V12 verification.

### Edit 9 — Implementation outline rewritten for `entrypoint.py`, `shell_usage.py`, `certificate.py`

- Each: explicit disk-anchored access via `read_raw_slices`; class-attribute `requires`; AC-V2 absent-upstream discipline; for `shell_usage.py` also names `StaticShellEvidence` + `RunCommandEntry`.

### Edit 10 — Green step #2 rewritten + new step #3

- Step 2: Declare `requires` as class attribute, not decorator kwarg; cite S5-02 + 02-ADR-0003.
- Step 3 (new): Reuse `read_raw_slices` from S4-01; no per-probe disk IO duplication.

### Edit 11 — Notes for the implementer expanded

- New paragraph: `requires` is class attribute + metadata-only; cite S5-02 + S4-01 + ADR-0003. Forbids re-litigation.
- New paragraph: sibling-slice access is disk-anchored; reuse the S4-01 helper; rule-of-three threshold passed.
- New paragraph: `Directive` tagged-union sum-type opportunity, with explicit Rule 2 trade-off; implementer's call within the AC-V12 LOC budget.
- Deprecated note retained: explains why the original "S5-04 introduces the `requires` mechanism" framing was wrong, so future readers don't carry it forward.

## Verdict rationale

HARDENED. The story's goal (4 marker-and-parse probes, no shell evaluation, ≤ 100 LOC each) is intact and aligned with the phase's Step 5 + Layer C arch decisions. All findings were fixable in place: 4 Consistency blocks were resolved by AC corrections rooted in existing ADRs and prior-story validation reports (no new architectural decisions needed); 9 Coverage hardens were addressed by per-edge-case ACs; 3 Test-Quality hardens added mutation-resistance + property-based discipline; 2 Design-Patterns hardens promoted kernel reuse and tightened the slice shape (the tagged-union opportunity is documented but optional per Rule 2). The story is now ready for `phase-story-executor`, with structural tests (AC-V1, AC-V3, Test 18, Test 19) that will fail loudly if a future contributor reintroduces either the `requires=`-as-decorator-kwarg phantom or the `ctx.sibling_slices` phantom.

## Recommended next step

`phase-story-executor` for S5-03 — the story is now structurally complete and the four probes can be implemented in red-green-refactor with mutation-resistant tests guarding the load-bearing invariants.
