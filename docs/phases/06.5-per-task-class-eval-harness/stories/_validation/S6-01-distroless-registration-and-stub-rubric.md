# Validation report — S6-01 `bench/migration-chainguard-distroless/` registration + stub rubric

**Story:** [`S6-01-distroless-registration-and-stub-rubric.md`](../S6-01-distroless-registration-and-stub-rubric.md)
**Validated:** 2026-07-25
**Verdict:** HARDENED
**Validator:** phase-story-validator (scheduled `story-validation-corrector` task)

## Executive summary

S6-01 is a direct mirror of HARDENED S5-01 for the second task class (`migration-chainguard-distroless`) — the seed the extension-by-addition invariant depends on for Phase 7. As-drafted it inherits **none** of the tightening the phase-story-validator applied to S5-01 in 2026-06-04 and **contradicts** two load-bearing HARDENED decisions (PEP 420 `__init__.py` ban; hyphen→underscore module-path translation). The rubric outline additionally omits the ADR-0001 subprocess CLI contract (non-zero exit on malformed stdin) and the ADR-0004 §Tradeoffs "always-block codes replicated per task class" requirement.

Twenty-one findings — 8 blocks, 10 hardens, 3 nits — applied in this pass. Story now inherits the S5-01 pattern faithfully with adaptations for (a) bronze-only floor (ADR-0006), (b) Dockerfile-derived signals (this task class is a *working* stub, not a `NotImplementedError` stub), and (c) three-signal semantic-symmetry inversions.

## Critic lenses run (consolidated)

Four validator lenses (Coverage, Test-Quality, Consistency, Design-Patterns) run inline as one analysis pass against the S5-01 HARDENED baseline. No `NEEDS RESEARCH` items — every pattern is precedented in HARDENED S5-01 + S5-02 + S1-03 + S2-01. Priority: `Consistency > Coverage > Test-Quality > Design-Patterns`.

## Findings

### Blocking (must fix before executor)

**F-CON-1 [CONSISTENCY] — `bench/migration-chainguard-distroless/__init__.py` hard-banned.**
The Files-to-touch table lists `bench/migration-chainguard-distroless/__init__.py` and `bench/migration-chainguard-distroless/cases/__init__.py` as "package markers." Both **directly contradict** HARDENED S2-01 + HARDENED S5-01's PEP 420 discipline: no `__init__.py` files anywhere under `bench/`. The hyphenated leaf can't have one (invalid Python identifier) and the migration variant's would break S2-01's namespace-package contract. S5-01 F-CON-5 already applied this ban; S6-01 must inherit it. **Fix:** Remove both rows. Add a hard-ban paragraph to Notes-for-implementer citing S2-01 + S5-01.

**F-CON-2 [CONSISTENCY] — wrong module prefix in Red test.**
Red test imports `_codegenie_bench.migration_chainguard_distroless.rubric`. The `_codegenie_bench.` prefix appears nowhere in the codebase — HARDENED S5-01 uses `bench.vuln_remediation.rubric`. This test would fail with `ModuleNotFoundError` at Red *for the wrong reason*, then continue to fail at Green because the loader translates to `bench.<underscore-slug>.*`, not `_codegenie_bench.*`. **Fix:** Rewrite Red test to use `load_task_class(...)` (mirror S5-01 F-CON-3) and import via `bench.migration_chainguard_distroless.rubric`.

**F-CON-3 [CONSISTENCY] — Depends-on omits load-bearing precedents.**
Depends-on names only S5-05. But the ACs are structurally load-bearing on: S1-03 HARDENED (kwarg surface), S1-04 (Rubric Protocol), S2-01 HARDENED (`load_task_class` import surface + hyphen→underscore translation), S5-01 HARDENED (the mirrored pattern). S5-05 is about digests/E2E and is *not* what this story mirrors. **Fix:** Rewrite Depends-on to name S1-03 HARDENED, S1-04, S2-01 HARDENED, S5-01 HARDENED (transitively S5-02 HARDENED for the working-rubric contract). Drop the misleading S5-05.

**F-COV-1 [COVERAGE] — no AC pins imperative-application form.**
S1-03 HARDENED requires `register_task_class(...)(RubricClass)` (imperative application) — the decorator-on-marker-class form silently passes at import time but fails the runner's `type[Rubric]` invocation contract. S5-01 AC-1 pins this via an AST-walking test. S6-01 has no equivalent AC — an executor could ship `@register_task_class(...)\nclass _Marker: pass` and all current ACs would pass. **Fix:** Add AC pinning (a) one call to `register_task_class`, (b) first positional arg is `ast.Constant` `"migration-chainguard-distroless"`, (c) imperative-application form applied to the rubric class imported from `bench.migration_chainguard_distroless.rubric`.

**F-COV-2 [COVERAGE] — no AC for rubric-class-identity `is`-check.**
S5-01 AC-1 asserts `tc.rubric_class is VulnRemediationRubric` — catches a regression that wraps the rubric with a side-effecting proxy (S1-03 AC-5: decorator returns class unmodified). S6-01 has no equivalent. **Fix:** Add AC + `test_registered_rubric_class_is_imported_class_unmodified` mirroring S5-01.

**F-COV-3 [COVERAGE] — no AC for `MappingProxyType` immutability.**
S1-03 AC-9 typed-at-the-edge: the decorator normalizes `min_cases_for_promotion` and `failure_mode_taxonomy` to `types.MappingProxyType`. S5-01 AC-2 + AC-5 assert both `isinstance(..., MappingProxyType)` AND `with pytest.raises(TypeError): tax["new.code"] = "block"`. S6-01 misses both — an executor could ship a plain `dict` and never notice the S1-03 contract violation. **Fix:** Add MappingProxyType assertion and mutation-raises test for both `min_cases_for_promotion` and `failure_mode_taxonomy`.

**F-COV-4 [COVERAGE] — always-block codes not replicated in required set.**
ADR-0004 §Tradeoffs (last row) explicitly requires codes shared across task classes to be replicated per task class: `sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`. S6-01 lists only 3 migration-specific block codes (`migration.base_image_not_chainguard`, `migration.shell_invocation_present`, `migration.build_failed`). Without the always-block set, the first SUT timeout in production Phase 7 emits `sut.timeout` → resolver sees unknown code → falls back to `rubric.unknown_failure_mode` → operator gets a misleading error. S5-01 F-CON-6 already applied this fix; S6-01 must inherit. **Fix:** Expand AC-3 (renumbered) to require exactly the 10 required block codes (3 migration + 7 runner-internal always-block) plus any migration-internal codes the stub rubric might emit (e.g., `migration.dockerfile_unparseable`).

**F-COV-5 [COVERAGE] — no AC for `__main__` non-zero exit on malformed stdin.**
ADR-0001 §Consequences pins `rubric.malformed_output` as the runner's reaction to a rubric non-zero exit. S5-02 AC-2 pins the rubric's `__main__` exits non-zero on `json.JSONDecodeError` / `pydantic.ValidationError`. S6-01's rubric-outline text says "read stdin JSON" but no AC or test asserts the rubric exits non-zero on bad input — a `try/except: emit passing BenchScore` implementation would silently pass. **Fix:** Add AC + `test_main_exits_nonzero_on_malformed_envelope_json` mirroring S5-02 AC-2 (subprocess.run with `b"not-json"` on stdin; assert `returncode != 0`).

### Hardening (should fix)

**F-COV-6 [COVERAGE] — no AC for YAML schema exact-key strictness.**
S5-01 AC-7 pins three parametrized tests: (a) top-level is dict-of-dicts with exactly `{severity, description}` keys per entry (no extras), (b) severity in the literal set, (c) description is a non-empty str. S6-01 asserts only (b) and (c) informally. An executor could ship `{code: {severity, description, owner: "..."}}` — silent schema drift that fence-CI #6 (S7-01) may or may not catch. **Fix:** Add three parametrized tests mirroring S5-01 F-COV-3.

**F-COV-7 [COVERAGE] — no AC for taxonomy value shape.**
S5-01 AC-5 asserts `for code, sev in tc.failure_mode_taxonomy.items(): isinstance(sev, str) and sev in {"block","warn","info"}`. Guards against a regression where the loader accidentally projects the full `{severity, description}` dict into the taxonomy value instead of the bare severity. **Fix:** Add mirror AC + test.

**F-COV-8 [COVERAGE] — no AC for double-load idempotence.**
S5-01 AC-6 exercises `tc1 = load_task_class(...); tc2 = load_task_class(...)` — asserts no `TaskClassAlreadyRegistered`, `tc1 is tc2`, `tc1 is registry.get(name)`. Defense-in-depth on S2-01 AC-6, bench-fixture-specific. **Fix:** Add mirror AC + test.

**F-COV-9 [COVERAGE] — AC-6 "or the existing fence already does — verify which" is unverifiable.**
Original AC-6 hedges: "or the existing fence already does — verify which". Story must pin the deterministic answer. Per S1-05, `tests/unit/test_breakdown_keys_static.py` auto-discovers registered task classes — so a properly-wired registration will be picked up without a story-local extension. **Fix:** Reword AC to name the deterministic behavior ("this task class is auto-discovered by `test_breakdown_keys_static.py` via the registered `BreakdownKey.<value>` set") and add a local defense-in-depth test that walks `tc.breakdown_keys` at runtime for banned substrings.

**F-COV-10 [COVERAGE] — no test for "no module-level I/O or import side effects" in rubric.py.**
The Implementation outline §5 says "**Determinism** is on the bench-author's shoulders" but no AC or test enforces ADR-0001's "no module-level side effects" invariant. An executor could ship a rubric with a module-level `open(some_config, "r")` that would break subprocess startup latency and load-order guarantees. **Fix:** Add AC + `test_rubric_module_has_no_module_level_io_or_side_effects` that ASTs the module, walks top-level nodes, and rejects any `Call` outside function/class defs (plus rejects `import os` if not needed, `import time`, `import random`, `os.environ` reads). Mirror S5-02 AC-9 pattern.

**F-COV-11 [COVERAGE] — no AC for semantic-symmetry inversions.**
S5-01 AC-3 documented four breakdown↔failure-mode pairs. S6-01 has three signals but doesn't pair them explicitly with failure codes: `base_image_swapped ↔ migration.base_image_not_chainguard`, `shell_free ↔ migration.shell_invocation_present`, `build_passes ↔ migration.build_failed`. Missing pairing means the rubric-emit tests (S6-02/03) have no anchor for "which failure code should emit when which signal is falsy." **Fix:** Add AC documenting the three inversions; pin in Notes-for-implementer that Phase 7 owns the score↔failure inversion enforcement at rubric-hardening time.

**F-TQ-1 [TEST-QUALITY] — `test_distroless_rubric_is_subprocess_entrypoint_only` is a tautology.**
Current test asserts `hasattr(mod, "__name__")` — every Python module has `__name__`. Test passes for **any** module. **Fix:** Replace with an AST-walk asserting (a) `if __name__ == "__main__":` block exists at module top-level, (b) no top-level `Call` invokes `score(...)` outside the `__main__` guard.

**F-TQ-2 [TEST-QUALITY] — breakdown_keys assertion is subset, not equality.**
Current test: `required.issubset(tc.breakdown_keys)` — passes if the enum has any superset of the three required members. If Phase 7 later adds `RUNTIME_CAPABILITY_MATCH`, that's fine; but for the Phase 6.5 landing the story should pin the exact members it commits to. **Fix:** Assert `tc.breakdown_keys == frozenset({"base_image_swapped", "shell_free", "build_passes"})` + `len(tc.breakdown_keys) == 3`. Kills empty-enum, single-member, and lowercased-member mutants.

**F-TQ-3 [TEST-QUALITY] — failure_modes existence-check is subset, silent on omission.**
`test_distroless_failure_modes_have_severities_and_descriptions` iterates over 3 required codes. A rubric author who omits `migration.build_failed` but keeps the other two would silently pass — the test only asserts the code that IS present has severity+description. **Fix:** After F-COV-4's always-block expansion, assert exact set equality (`set(tc.failure_mode_taxonomy.keys()) == REQUIRED_ALL_CODES`); iterate through `REQUIRED_ALL_CODES` for severity checks so a missing code raises `KeyError`.

**F-TQ-4 [TEST-QUALITY] — no AST-level test that BreakdownKey values are `ast.Constant`.**
S5-01 AC-3 has `test_breakdown_key_values_are_ast_constant_strings` (ASTs the module source; kills f-string / concat mutants; defense-in-depth on fence-CI #5). Story says values must be "`ast.Constant` literals" but the AC doesn't include the test. **Fix:** Add mirror test.

**F-TQ-5 [TEST-QUALITY] — no test that yaml.safe_load discipline holds.**
S5-01 AC-7's `test_failure_modes_yaml_loads_via_safe_load_only` monkeypatches `yaml.load` to raise; a regression to unsafe-load slips through without it. **Fix:** Add mirror test.

**F-TQ-6 [TEST-QUALITY] — no functional-core split for Dockerfile parsing.**
The rubric parses Dockerfile strings via regex inline in `score()`. A tiny `_dockerfile_facts(text: str) -> _DockerfileFacts` frozen-dataclass helper would (a) separate pure logic from the `__main__` shell, (b) make regex behavior testable in isolation without stdin/stdout plumbing, (c) match the functional-core/imperative-shell pattern the repo prefers. **Fix:** Surface as Notes-for-implementer design opportunity (do NOT promote to AC per Rule 2 — three lines vs premature abstraction; three signals today may still be at threshold, but the split pays off in S6-02 when the rubric grows).

**F-DP-1 [DESIGN-PATTERNS] — score formula couples to signal count.**
Implementation outline §5: `score=mean_of_three_booleans`. If Phase 7 adds a 4th signal, the string "three" is a landmine. **Fix:** Amend Implementation outline §5 to `score = mean(breakdown.values())` — the semantics extend automatically when a new `BreakdownKey` member ships. Surface in Notes-for-implementer.

**F-DP-2 [DESIGN-PATTERNS] — `_severity_taxonomy_from_yaml` helper omitted.**
S5-01 pins a file-local `_severity_taxonomy_from_yaml(path) -> Mapping[str, Literal["block","warn","info"]]` helper in registration.py — with a Notes-for-implementer explanation that Phase 15's task class is the third consumer that triggers the rule-of-three lift to `src/codegenie/eval/loader.py` as `_load_failure_mode_taxonomy`. S6-01 should include the identical helper. This story is the SECOND consumer; the third-consumer lift trigger doesn't fire yet. **Fix:** Add the helper to Implementation outline §2 verbatim; add Notes-for-implementer paragraph naming Phase 15 as the lift trigger. This is copy-paste-with-eyes-open on purpose — the extraction is deferred until the third data point.

### Nits

**F-N-1 [CONSISTENCY] — Test file location.**
Red test path is `tests/unit/test_distroless_registration.py` (top-level `tests/unit/`). S5-01 puts its test under `tests/unit/eval/test_bench_vuln_registration.py` to inherit S2-01 HARDENED AC-22's autouse `conftest.py` (sys.path/sys.modules/default_registry snapshot+restore). Same pattern applies here. **Fix:** Move to `tests/unit/eval/test_bench_distroless_registration.py`.

**F-N-2 [CONSISTENCY] — README.md missing from Files-to-touch.**
S5-01 ships a README.md stub in the task-class directory naming what future stories will add. S6-01 mentions it in Refactor but not in Files-to-touch table. **Fix:** Add `bench/migration-chainguard-distroless/README.md` row; text names S6-02 (3 held-out cases + digests) and S6-03 (E2E + verdict).

**F-N-3 [CONSISTENCY] — Status line, header conventions.**
Match HARDENED sibling formatting: `**Status:** HARDENED (phase-story-validator, 2026-07-25)` and add a Validation-notes block after the header. **Fix:** Apply the two edits.

## Design endorsements (no edit; surfaced in Notes-for-implementer)

- **Extension-by-addition seam at `bench/{task-class}/`** — this story is the second consumer of the S5-01 seam; extension works, no kernel edits required in `src/codegenie/eval/`. Reaffirms F-DP-3 in S5-01. Phase 7's hardening (adding e.g. `RUNTIME_CAPABILITY_MATCH`, semver checks on Chainguard tags) extends this task class's four files without touching Phase 6.5 code.
- **Functional-core / imperative-shell** — `score()` pure, `__main__` shell. Same discipline S5-02 landed for vuln-remediation.
- **`_severity_taxonomy_from_yaml` deferred rule-of-three lift** — deliberate. Phase 15 is the third consumer; the extraction to `src/codegenie/eval/loader.py` happens then.

## Verdict

**HARDENED.** 21 findings applied; story now inherits S5-01 HARDENED's tightening + adapts for bronze-only floor and Dockerfile-derived working-stub signals. Ready for `phase-story-executor`.
