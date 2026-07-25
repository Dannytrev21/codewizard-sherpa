# Story S6-01 — `bench/migration-chainguard-distroless/` registration, taxonomies, and stub rubric

**Step:** Step 6 — Seed `bench/migration-chainguard-distroless/`
**Status:** HARDENED (phase-story-validator, 2026-07-25)
**Effort:** M
**Depends on:** S1-03 HARDENED (`@register_task_class` kwarg surface: `breakdown_keys`, `failure_mode_taxonomy`, `bench_path`, `min_cases_for_promotion`, imperative-application form against a `type[Rubric]`), S1-04 (`Rubric` Protocol — the stub rubric class must satisfy it structurally), S2-01 HARDENED (`load_task_class` is the import surface for tests; hyphen→underscore translation lives there; PEP 420 implicit namespace package contract — no `__init__.py` anywhere under `bench/`), S5-01 HARDENED (the mirrored pattern this story extends by addition). Transitively: S5-02 HARDENED (subprocess-entrypoint discipline for a *working* rubric — this story ships the second such rubric).
**ADRs honored:** ADR-0001 (subprocess rubric; `if __name__ == "__main__"`; no module-level side effects; non-zero exit on malformed stdin), ADR-0004 (`failure_modes.yaml` taxonomy; runner-internal always-block codes replicated per task class per §Tradeoffs; runtime taxonomy is severity-only, descriptions live in YAML for fence-CI #6), ADR-0006 (curation-class split — bronze-only floor keeps held-out ≥5 fence-CI inactive for this task class until Phase 7 raises the bar), ADR-0008 (`BreakdownKey` StrEnum + substring ban at value level; `rubric.unknown_breakdown_key` block code required in the taxonomy), Phase 5 ADR-0014 (substring-ban source-of-truth shared with ADR-0008)

## Validation notes

Validated: 2026-07-25
Verdict: HARDENED
Findings addressed: 21 total — 8 blocks, 10 hardens, 3 nits

Changes applied (full audit log: `_validation/S6-01-distroless-registration-and-stub-rubric.md`):

- **Status line** updated to `HARDENED (phase-story-validator, 2026-07-25)` (F-N-3).
- **Depends-on** rewritten to name S1-03 HARDENED, S1-04, S2-01 HARDENED, S5-01 HARDENED (F-CON-3). The original single-line "S5-05" was misleading — this story mirrors S5-01's pattern, not S5-05's E2E surface.
- **`bench/migration-chainguard-distroless/__init__.py` + `.../cases/__init__.py` hard-banned (BLOCK, F-CON-1):** the original Files-to-touch listed both as "package markers." That directly contradicts HARDENED S2-01 + HARDENED S5-01's PEP 420 discipline — no `__init__.py` files anywhere under `bench/`. The hyphenated directory can't have one (invalid Python identifier) and the underscore-named cases/ variant would break S2-01's namespace-package contract. Rows removed; hard-ban paragraph added to Notes-for-implementer.
- **Red test module prefix fixed (BLOCK, F-CON-2):** original Red test imported `_codegenie_bench.migration_chainguard_distroless.rubric` — that prefix does not exist in the codebase. HARDENED S5-01 imports through `bench.<underscore-slug>.*` after `load_task_class(...)` has resolved the on-disk hyphenated directory via `spec_from_file_location`. Red test rewritten to call `load_task_class("migration-chainguard-distroless", bench_root=...)` and then import `bench.migration_chainguard_distroless.rubric` — mirroring S5-01 F-CON-3.
- **Imperative-application form pinned (BLOCK, F-COV-1):** original ACs did not pin `register_task_class(...)(MigrationChainguardDistrolessRubric)`. An executor could ship `@register_task_class(...) class _Marker: pass` and every original AC would pass — but S1-03's `type[Rubric]` Protocol contract would fail at runner invocation. AC-1 now pins (a) exactly one call to `register_task_class`, (b) first positional arg is `ast.Constant["migration-chainguard-distroless"]`, (c) imperative-application form applied to the rubric class imported from `bench.migration_chainguard_distroless.rubric`.
- **Rubric-class-identity AC added (BLOCK, F-COV-2):** AC-1 asserts `tc.rubric_class is MigrationChainguardDistrolessRubric` (S1-03 AC-5 — decorator returns the class unmodified). Guards against a regression that wraps the rubric with a side-effecting proxy.
- **`MappingProxyType` immutability ACs added (BLOCK, F-COV-3):** original ACs did not assert `isinstance(tc.min_cases_for_promotion, types.MappingProxyType)` or `isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)`, nor did they assert attempted mutation raises `TypeError`. S1-03 AC-9 pins both; without the assertions here, an executor could ship a plain `dict` and S1-03's typed-at-the-edge contract silently breaks. AC-2 + AC-6 pin both layers.
- **Always-block codes replicated per task class (BLOCK, F-COV-4):** ADR-0004 §Tradeoffs explicitly requires runner-internal always-block codes to be replicated per task class. Original story listed only 3 migration-specific block codes. Without `sut.timeout` (and the six other always-block codes) in this YAML, the first SUT subprocess timeout in Phase 7 production emits `sut.timeout` → resolver sees unknown code → falls back to `rubric.unknown_failure_mode` → operator gets a misleading error. AC-5 expanded to require exactly 3 migration-specific + 7 runner-internal always-block block codes (10 total) plus `migration.dockerfile_unparseable` warn.
- **`__main__` non-zero exit on malformed stdin (BLOCK, F-COV-5):** ADR-0001 §Consequences pins `rubric.malformed_output` as the runner's reaction to non-zero rubric exit. S5-02 AC-2 pins the discipline. Story did not have an AC for this — a `try/except` swallow would silently pass. AC-4 + `test_main_exits_nonzero_on_malformed_envelope_json` mirror S5-02.
- **YAML schema exact-key strictness (HARDEN, F-COV-6):** S5-01 AC-7 pins three parametrized tests on the YAML shape. Story asserted only severity + description informally; extras like `owner:` would slip through. AC-7 now pins the three: (a) exact `{severity, description}` per entry, (b) severity in literal set, (c) non-empty string description. Plus a `yaml.safe_load` monkeypatch discipline test (F-TQ-5).
- **Taxonomy value shape AC (HARDEN, F-COV-7):** AC-5 asserts `for code, sev in tc.failure_mode_taxonomy.items(): isinstance(sev, str) and sev in {"block","warn","info"}`. Guards against the loader accidentally projecting the full `{severity, description}` dict into the taxonomy value.
- **Double-load idempotence AC (HARDEN, F-COV-8):** AC-8 mirrors S5-01 AC-6 — `tc1 is tc2` and `tc1 is registry.get(name)`. Defense-in-depth on S2-01 AC-6, bench-fixture-specific.
- **Unverifiable "or the existing fence" hedge removed (HARDEN, F-COV-9):** original AC-6 said "…extended to walk this task class proves it (or the existing fence already does — verify which)." Ambiguity is not a spec. Rewritten to name the deterministic behavior: per S1-05, `tests/unit/test_breakdown_keys_static.py` auto-discovers registered task classes — a properly-wired registration is picked up without a story-local extension. AC-9 pins runtime substring-ban test locally as defense-in-depth.
- **"No module-level I/O" test pinned (HARDEN, F-COV-10):** original Implementation outline §5 said "Determinism is on the bench-author's shoulders" — enforcement was aspirational. ADR-0001 requires no module-level side effects; an executor could ship `open(config, "r")` at module top-level and break subprocess startup latency + load-order guarantees. AC-10 + `test_rubric_module_has_no_module_level_io_or_side_effects` AST-walk the top-level nodes and reject `Call` outside function/class defs, plus reject `time`/`random`/`uuid`/`os.environ` imports/reads. Mirrors S5-02 AC-9.
- **Semantic-symmetry inversions pinned as AC (HARDEN, F-COV-11):** original story had three signals but never paired them with failure codes explicitly. AC-11 documents the three inversions: `base_image_swapped ↔ migration.base_image_not_chainguard`, `shell_free ↔ migration.shell_invocation_present`, `build_passes ↔ migration.build_failed`. Documentation-only for this story; Phase 7 owns rubric-hardening enforcement.
- **Tautology `hasattr(mod, "__name__")` replaced (HARDEN, F-TQ-1):** original `test_distroless_rubric_is_subprocess_entrypoint_only` asserted `hasattr(mod, "__name__")` — every Python module has `__name__`. Replaced with an AST-walk: (a) `if __name__ == "__main__":` block exists at module top-level, (b) no top-level `Call` invokes `score(...)` outside the `__main__` guard.
- **`breakdown_keys` assertion tightened from subset → equality (HARDEN, F-TQ-2):** original `required.issubset(tc.breakdown_keys)` passes for any superset; kills no mutants. Assertion changed to exact set + length pin: `tc.breakdown_keys == frozenset({"base_image_swapped", "shell_free", "build_passes"})` and `len == 3`. Kills empty-enum, single-member, and lowercased-member mutants.
- **`failure_modes` existence tightened from subset → exact (HARDEN, F-TQ-3):** original iteration over 3 required codes silently accepts a rubric author who omits `migration.build_failed`. Combined with F-COV-4's expansion, AC-5 now asserts `set(tc.failure_mode_taxonomy.keys()) == REQUIRED_ALL_CODES`.
- **`BreakdownKey` ast.Constant local check (HARDEN, F-TQ-4):** AC-3 + `test_breakdown_key_values_are_ast_constant_strings` walks the module source and asserts every `Assign.value` inside `class BreakdownKey(StrEnum)` is `ast.Constant[str]`. Fires before fence-CI #5 (S7-01) in a typical PR pipeline; kills f-string / concat / prefix+suffix mutants.
- **`_severity_taxonomy_from_yaml` helper pinned (HARDEN, F-DP-2):** original Implementation outline had inline YAML loading. HARDENED S5-01 uses a file-local private helper `_severity_taxonomy_from_yaml(path) -> Mapping[str, Literal["block","warn","info"]]`. Story is the SECOND consumer (S5-01 was the first); Phase 15's third task class is the rule-of-three lift trigger to `_load_failure_mode_taxonomy` in `src/codegenie/eval/loader.py`. Implementation outline §2 pins the helper verbatim; Notes-for-implementer names the deferred lift target.
- **Score-formula extension-friendliness (HARDEN, F-DP-1):** original "`score=mean_of_three_booleans`" hard-codes the signal count — Phase 7 adding a 4th signal would silently corrupt scores. Amended to `score = statistics.mean(breakdown.values())` — extends automatically when a new `BreakdownKey` member ships.
- **Test file relocated (NIT, F-N-1):** `tests/unit/test_distroless_registration.py` → `tests/unit/eval/test_bench_distroless_registration.py`. Inherits S2-01 HARDENED AC-22's autouse `conftest.py` (sys.path/sys.modules/default_registry snapshot+restore).
- **README.md row added to Files-to-touch (NIT, F-N-2):** `bench/migration-chainguard-distroless/README.md` — stub naming S6-02 (3 held-out cases + digests) and S6-03 (E2E + verdict).

Design endorsements (no edit; surfaced in Notes-for-implementer):
- **Extension-by-addition seam at `bench/{task-class}/`** — S6-01 is the second consumer of the S5-01 seam. Zero edits to `src/codegenie/eval/` required. Phase 7's rubric-hardening (semver checks on Chainguard tags, multi-stage detection, `RUNTIME_CAPABILITY_MATCH`) extends this task class's four files.
- **Functional-core / imperative-shell** — `score()` pure, `__main__` shell. Same discipline S5-02 landed for vuln-remediation. F-TQ-6 (a `_dockerfile_facts` frozen-dataclass extractor) is a design opportunity Phase 7 may take when the rubric grows — not promoted to AC here (Rule 2 — three lines is fine today).
- **Adversarial mutant catalog (this story's §TDD plan kills these five):**
  1. **Empty BreakdownKey** — `class BreakdownKey(StrEnum): pass`. Killed by AC-3's exact-set equality.
  2. **BreakdownKey subset (only `BASE_IMAGE_SWAPPED`)** — Killed by AC-3's `len == 3`.
  3. **`failure_modes.yaml` with extra `owner:` key per entry** — silent schema drift. Killed by AC-7's exact-key-set assertion.
  4. **`registration.py` decorating a marker class** — fails Protocol contract; runner can't invoke. Killed by AC-1's `tc.rubric_class is MigrationChainguardDistrolessRubric`.
  5. **Rubric wraps `score(...)` in `try/except Exception: return passing_score`** — swallows internal failure. Killed by AC-4's `test_main_exits_nonzero_on_malformed_envelope_json` (partial — full catch requires S6-02's held-out cases exercising real signal paths).

No `NEEDS RESEARCH` items — every pattern is precedented in HARDENED S5-01 + S5-02 + S1-03 + S2-01.

## Context

Phase 7 introduces `migration-chainguard-distroless` as the second task class without editing any Phase 0–6 source — the *extension-by-addition* invariant in `CLAUDE.md`. For that to work, Phase 6.5 must ship a complete directory skeleton (`registration.py`, `breakdown_keys.py`, `failure_modes.yaml`, `rubric.py`) that fence-CI is already asserting against and that mirrors the `bench/vuln-remediation/` pattern landed in S5-01/S5-02. The rubric is a *working stub*: at N=3 held-out cases (S6-02) it only needs to demonstrate the subprocess contract and the three Dockerfile-derived signals; Phase 7 will harden scoring as the corpus grows.

The registration declares **only** `bronze: 10` in `min_cases_for_promotion` — silver/gold are Phase 7's call. This deliberately keeps fence-CI assertion #3 (held-out floor ≥ 5 for tier ≥ silver) inactive for this task class until Phase 7 raises the bar.

Unlike S5-01's `NotImplementedError` stub, this story's rubric ships a **working** stub — three coarse signals (regex on `FROM` line, regex on `RUN sh|bash`, `expected/build.log` last-line check). That distinction matters: S5-02 replaced S5-01's stub body byte-for-byte later; here the working stub *is* the initial rubric, and S6-02's held-out cases exercise it end-to-end without a separate story replacing the body. Phase 7 hardens the signals in place (semver checks on Chainguard tags, multi-stage detection, `RUNTIME_CAPABILITY_MATCH`) — those edits stay inside `bench/migration-chainguard-distroless/rubric.py`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"bench/{task-class}/ directory contract"` — the four files this story creates and their structural roles; fence-CI walks the directory shape.
  - `../phase-arch-design.md §"What new task classes will need" §Step 1` (bench/migration-chainguard-distroless/ subsection).
  - `../phase-arch-design.md §"Component design → loader.py"` — how `_load_breakdown_keys` and `_load_failure_mode_taxonomy` consume these files; the loader's `_load_failure_mode_taxonomy` helper is the rule-of-three lift target (arch line 564).
  - `../phase-arch-design.md §"Scenarios → Scenario 3"` — fence-CI walking `bench/*/registration.py`.
  - `../phase-arch-design.md §Fence-CI test` — assertions #4 (literal name), #5 (StrEnum substring ban), #6 (taxonomy validity) all gate this story; local tests are defense-in-depth.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md §Decision, §Consequences` — `if __name__ == "__main__"` entrypoint; JSON over stdin/stdout; no module-level side effects; non-zero exit on `json.JSONDecodeError`/`pydantic.ValidationError` (the runner reacts with `rubric.malformed_output`).
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md §Decision + §Consequences + §Tradeoffs` — YAML schema (`severity ∈ {block, warn, info}`, non-empty `description`); §Tradeoffs (last row) requires runner-internal always-block codes to be replicated per task class.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md §Decision` — declaring silver commits to held-out ≥ 5; this story declares bronze only, so the fence stays inactive here until Phase 7.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md §Decision` — `BreakdownKey` StrEnum member *values* (not just names) are walked; `rubric.unknown_breakdown_key` block code required in the taxonomy.
- **Sibling HARDENED stories (load-bearing for this story's implementation):**
  - `S1-03-taskclass-dataclass-and-registry.md` — HARDENED decorator kwarg surface; imperative-application form; `MappingProxyType` normalization; decorated class returned unmodified.
  - `S1-04-rubric-protocol.md` — `Rubric` Protocol (one method, `score(case, harness_output) -> BenchScore`).
  - `S2-01-bench-import-path-resolution.md` — `load_task_class` is the import surface; hyphen→underscore translation; PEP 420 implicit namespace package (NO `__init__.py` under `bench/`); autouse conftest at `tests/unit/eval/`.
  - `S5-01-vuln-registration-and-taxonomies.md` — HARDENED pattern this story mirrors byte-for-byte in structure.
  - `S5-02-vuln-rubric-and-unit-tests.md` — HARDENED subprocess-CLI discipline for a working rubric (this story's rubric ships in one shot, but the same subprocess contract applies).
- **Production ADRs:** `../../../production/adrs/0008-objective-signal-trust-score.md` — facts not judgments; Dockerfile-derived signals are the right shape.
- **Source design:** `../High-level-impl.md §"Step 6"`.
- **Existing precedent:** `bench/vuln-remediation/{registration.py, rubric.py, breakdown_keys.py, failure_modes.yaml}` from S5-01/S5-02.

## Goal

Land `bench/migration-chainguard-distroless/{registration.py, breakdown_keys.py, failure_modes.yaml, rubric.py}` declaring exactly one `register_task_class("migration-chainguard-distroless", bench_path=..., min_cases_for_promotion={"bronze": 10}, breakdown_keys=frozenset(m.value for m in BreakdownKey), failure_mode_taxonomy=_TAXONOMY)(MigrationChainguardDistrolessRubric)` imperative-application call, a `BreakdownKey` StrEnum with three literal-value members, a `failure_modes.yaml` with 3 migration-specific + 7 runner-internal always-block codes (+ warn/info as needed), and a working stub rubric that scores three Dockerfile-derived signals via a subprocess entrypoint — all files importable via HARDENED `load_task_class("migration-chainguard-distroless", bench_root=Path("bench"))` and validated by fence-CI assertions #4–#6.

## Acceptance criteria

- [ ] **AC-1 (imperative registration call, HARDENED-S1-03-conformant).** `bench/migration-chainguard-distroless/registration.py` contains exactly one call to `register_task_class` with: (a) first positional arg the *literal* `ast.Constant` string `"migration-chainguard-distroless"`; (b) kwargs `bench_path=Path(__file__).parent`, `min_cases_for_promotion={"bronze": 10}`, `breakdown_keys=frozenset(m.value for m in BreakdownKey)`, `failure_mode_taxonomy=_TAXONOMY`; (c) **imperative-application form** `register_task_class(...)(MigrationChainguardDistrolessRubric)` against the rubric class imported from `bench.migration_chainguard_distroless.rubric`. The decorator-on-marker-class form `@register_task_class(...) class _Marker: pass` is forbidden (fails S1-03's `type[Rubric]` Protocol contract). Test `test_registered_rubric_class_is_imported_class_unmodified` asserts `tc.rubric_class is MigrationChainguardDistrolessRubric` (S1-03 AC-5). Local AST-walking test asserts exactly one `register_task_class` call at module top level, first arg is `ast.Constant[str]`.

- [ ] **AC-2 (TaskClass shape post-load, bronze-only).** After `tc = load_task_class("migration-chainguard-distroless", bench_root=tmp_bench_root, registry=fresh_registry)`: (a) `tc.name == "migration-chainguard-distroless"`; (b) `tc.bench_path == (tmp_bench_root / "migration-chainguard-distroless").resolve()` (absolute, symlink-resolved per S2-01 AC-13); (c) `tc.min_cases_for_promotion == MappingProxyType({"bronze": 10})` — both value equality AND `isinstance(tc.min_cases_for_promotion, types.MappingProxyType)` (S1-03 AC-9a); (d) `"silver" not in tc.min_cases_for_promotion` and `"gold" not in tc.min_cases_for_promotion` — ADR-0006 held-out floor stays inactive for this task class; (e) `dataclasses.fields(TaskClass)` still has exactly six entries (S1-03 AC-2 pin holds — this story adds no field).

- [ ] **AC-3 (BreakdownKey StrEnum — exact-set equality + ast.Constant + len pin).** `bench/migration-chainguard-distroless/breakdown_keys.py` defines `class BreakdownKey(StrEnum)` with **exactly** the three members `BASE_IMAGE_SWAPPED = "base_image_swapped"`, `SHELL_FREE = "shell_free"`, `BUILD_PASSES = "build_passes"`. Test asserts `frozenset(m.value for m in BreakdownKey) == frozenset({"base_image_swapped", "shell_free", "build_passes"})` AND `len(list(BreakdownKey)) == 3` — kills empty-enum, single-member, and lowercased-member mutants. Test `test_breakdown_key_values_are_ast_constant_strings` ASTs the module source and asserts every `Assign.value` inside `class BreakdownKey(StrEnum)` is `ast.Constant[str]` (no `f"..."`, no `prefix + suffix`) — defense-in-depth on fence-CI #5 (S7-01).

- [ ] **AC-4 (`__main__` entrypoint shape + non-zero exit on malformed stdin).** `rubric.py` has an `if __name__ == "__main__":` block that reads `sys.stdin.buffer.read()`, parses it as JSON, validates via `codegenie.eval.models.BenchCase.model_validate(payload["case"])` + a local `_HarnessOutput` Pydantic model, calls `score(...)`, writes the resulting `BenchScore` as JSON to `sys.stdout.buffer`, and exits 0 on success. On `json.JSONDecodeError` or `pydantic.ValidationError` the process exits non-zero (`sys.exit(2)`) — no broad `try/except` that would emit a misleadingly-passing `BenchScore`. Test `test_main_exits_nonzero_on_malformed_envelope_json` (integration) feeds `b"not-json"` on stdin via `subprocess.run` and asserts `returncode != 0` (ADR-0001 §Consequences `rubric.malformed_output`).

- [ ] **AC-5 (failure_modes.yaml taxonomy — exact 10 block + optional warn codes).** `bench/migration-chainguard-distroless/failure_modes.yaml` declares **exactly** the following codes (any addition or omission fails fence-CI #6 and the local schema tests):
  - `block` (10 codes — 3 migration-specific + 7 runner-internal always-block per ADR-0004 §Tradeoffs replication requirement):
    - migration-specific: `migration.base_image_not_chainguard`, `migration.shell_invocation_present`, `migration.build_failed`
    - runner-internal always-block: `sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key` (ADR-0008 §Decision), `rubric.malformed_output` (ADR-0001 §Consequences)
  - `warn` (1 — rubric-internal): `migration.dockerfile_unparseable` (rubric emits this when the SUT-produced Dockerfile cannot be tokenized enough to score signals; keeps the case surfacing an actionable warn rather than a silent zero).
  Each entry has `severity ∈ {"block", "warn", "info"}` and a non-empty `description` str. After load, for every code in the required set, `tc.failure_mode_taxonomy[code]` returns the declared severity. Severity-shape AC: `for code, sev in tc.failure_mode_taxonomy.items(): isinstance(sev, str) and sev in {"block","warn","info"}` (guards against projecting the full `{severity, description}` dict). Set-exactness AC: `set(tc.failure_mode_taxonomy.keys()) == REQUIRED_ALL_CODES`.

- [ ] **AC-6 (`MappingProxyType` immutability on both mappings).** `isinstance(tc.min_cases_for_promotion, types.MappingProxyType)` AND `isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)`. Both `with pytest.raises(TypeError): tc.min_cases_for_promotion["silver"] = 25` and `with pytest.raises(TypeError): tc.failure_mode_taxonomy["new.code"] = "block"`. S1-03 AC-9 typed-at-the-edge — the decorator normalizes; without these assertions an executor could ship a plain `dict` and never notice.

- [ ] **AC-7 (failure_modes.yaml schema fence — three parametrized tests).** (a) `test_failure_modes_yaml_top_level_is_dict_of_dicts_with_exactly_two_keys` — for every entry, `set(entry) == {"severity", "description"}` (no extras, no missing). (b) `test_failure_modes_yaml_severity_values_are_in_literal_set` — `entry["severity"] in {"block", "warn", "info"}`. (c) `test_failure_modes_yaml_descriptions_are_nonempty_strings` — `isinstance(entry["description"], str) and entry["description"].strip() != ""`. Plus `test_failure_modes_yaml_loads_via_safe_load_only` monkeypatches `yaml.load` to raise and asserts the safe_load path is what registration.py takes.

- [ ] **AC-8 (double-load idempotence — bench-fixture-specific).** `tc1 = load_task_class(...); tc2 = load_task_class(...)` does NOT raise `TaskClassAlreadyRegistered`, returns `tc1 is tc2`, and `tc1 is fresh_registry.get("migration-chainguard-distroless")`. Defense-in-depth on S2-01 AC-6 — catches a bench-fixture-specific regression (e.g., a `for _ in range(2)` wrapping the imperative-application call).

- [ ] **AC-9 (substring ban — static + runtime).** *Static:* every `BreakdownKey` member value passes the substring ban (`confidence|llm|self_reported|model_says` absent). *Runtime:* `for v in tc.breakdown_keys: for banned in BANNED_SUBSTRINGS: assert banned not in v` on the loader-produced set. The existing `tests/unit/test_breakdown_keys_static.py` (S1-05) auto-discovers registered task classes and picks this task class up without a story-local extension (no verify-which hedge). Bench-specific defense-in-depth via the runtime test lives in this story's test file.

- [ ] **AC-10 (rubric.py has no module-level I/O or side effects).** `test_rubric_module_has_no_module_level_io_or_side_effects` parses `bench/migration-chainguard-distroless/rubric.py` via `ast.parse` and asserts: (a) no `ast.Call` node appears at module top-level outside `FunctionDef`/`AsyncFunctionDef`/`ClassDef`/`If` (only the `if __name__ == "__main__":` guard's body permits top-level effects, and the check confirms that guard is the only top-level `If`); (b) no `import time`/`from time`, no `import random`/`from random`, no `import uuid`/`from uuid`; (c) no `os.environ` attribute access outside the `__main__` guard. Mirrors S5-02 AC-9 discipline. Required for subprocess startup latency + audit-chain byte-stability.

- [ ] **AC-11 (semantic-symmetry inversions documented).** The three breakdown↔failure-mode pairs this task class commits to (Phase 7 rubric-hardening enforces the inversion at score time):
  - `base_image_swapped` ↔ `migration.base_image_not_chainguard`
  - `shell_free` ↔ `migration.shell_invocation_present`
  - `build_passes` ↔ `migration.build_failed`
  Documentation-only for this story; no test forces the rubric's emit to invert. When Phase 7 hardens the rubric, that story owns a parametrized `test_each_falsy_breakdown_condition_emits_its_paired_failure_code` (mirror of S5-02 AC-5). The pairing pins the contract so the hardening story doesn't have to re-derive it.

- [ ] **AC-12 (no LLM SDK).** The rubric does **not** import any LLM SDK (`anthropic`, `openai`, `langchain`, `langgraph`, `transformers`, `torch`, `sentence-transformers`). S5-02 AC-12's fence-CI extension already walks `bench/**/rubric.py`, so no additional wiring is needed — this story's rubric stays green under the existing extended walk.

- [ ] **AC-13 (red→green pipeline, lint, typecheck, fence-CI).** Red test from §TDD plan exists, was committed at red marker, now green. `ruff check`, `ruff format --check`, `mypy --strict bench/migration-chainguard-distroless/registration.py bench/migration-chainguard-distroless/breakdown_keys.py bench/migration-chainguard-distroless/rubric.py bench/migration-chainguard-distroless/tests/test_rubric_unit.py tests/unit/eval/test_bench_distroless_registration.py tests/integration/test_rubric_subprocess_distroless.py` all pass. Fence-CI assertions #4 (literal name), #5 (BreakdownKey substring ban), #6 (taxonomy validity) all pass in S7-01's ≤ 2 s budget.

## Implementation outline

1. **Directory skeleton.** Create `bench/migration-chainguard-distroless/{registration.py, breakdown_keys.py, failure_modes.yaml, rubric.py, README.md}` plus `bench/migration-chainguard-distroless/tests/test_rubric_unit.py`. **Do NOT create** `bench/migration-chainguard-distroless/__init__.py` or `bench/migration-chainguard-distroless/cases/__init__.py` — S2-01 HARDENED uses PEP 420 implicit namespace packages; the hyphenated directory can't have one anyway (invalid Python identifier). `cases/` is empty until S6-02 lands the held-out three.

2. **`registration.py`** (imperative-application form; `_severity_taxonomy_from_yaml` helper mirrored from S5-01):
   ```python
   """ADR-0004, ADR-0006, ADR-0008 — task-class identity for migration-chainguard-distroless.

   Second task class; extends the S5-01 pattern by addition. Bronze-only floor
   (ADR-0006) — silver/gold are Phase 7's call.
   """
   from pathlib import Path
   from types import MappingProxyType
   from typing import Final, Literal, Mapping

   import yaml

   from codegenie.eval.registry import register_task_class
   from bench.migration_chainguard_distroless.breakdown_keys import BreakdownKey
   from bench.migration_chainguard_distroless.rubric import MigrationChainguardDistrolessRubric

   _HERE: Final[Path] = Path(__file__).parent


   def _severity_taxonomy_from_yaml(
       path: Path,
   ) -> Mapping[str, Literal["block", "warn", "info"]]:
       """File-local helper (second consumer; Phase 15's task class is the
       rule-of-three lift trigger to `src/codegenie/eval/loader.py` as
       `_load_failure_mode_taxonomy` — arch line 564)."""
       raw = yaml.safe_load(path.read_text())
       if not isinstance(raw, dict):
           raise ValueError(
               f"failure_modes.yaml top-level must be dict, got {type(raw).__name__}"
           )
       return MappingProxyType({code: spec["severity"] for code, spec in raw.items()})


   _TAXONOMY: Final[Mapping[str, Literal["block", "warn", "info"]]] = (
       _severity_taxonomy_from_yaml(_HERE / "failure_modes.yaml")
   )

   register_task_class(
       "migration-chainguard-distroless",
       bench_path=_HERE,
       min_cases_for_promotion={"bronze": 10},
       breakdown_keys=frozenset(m.value for m in BreakdownKey),
       failure_mode_taxonomy=_TAXONOMY,
   )(MigrationChainguardDistrolessRubric)
   ```

3. **`breakdown_keys.py`** — three literal-value members (Phase 7 may add e.g. `RUNTIME_CAPABILITY_MATCH` later; values must pass the substring ban):
   ```python
   """ADR-0008 — per-task-class BreakdownKey StrEnum for migration-chainguard-distroless."""
   from enum import StrEnum


   class BreakdownKey(StrEnum):
       BASE_IMAGE_SWAPPED = "base_image_swapped"
       SHELL_FREE = "shell_free"
       BUILD_PASSES = "build_passes"
   ```

4. **`failure_modes.yaml`** — 10 block + 1 warn = 11 entries total; flat mapping `{code: {severity, description}}`; top-of-file comment names ADR-0004 + ADR-0001. Severities are literal lowercase strings.

5. **`rubric.py`** — working stub. Pure `score()` + `__main__` shell. Score = `statistics.mean(breakdown.values())` (extends automatically when a new `BreakdownKey` member ships):
   - Parse `harness_output["dockerfile"]` (the SUT's produced Dockerfile string).
   - Compute three boolean signals: (a) `FROM` line targets `cgr.dev/chainguard/*` → `BASE_IMAGE_SWAPPED`; (b) no `RUN sh|bash|/bin/sh` in the Dockerfile → `SHELL_FREE`; (c) `harness_output["build_log_last_line"]` matches `Successfully built` or equivalent → `BUILD_PASSES`.
   - `breakdown = {BreakdownKey.X.value: 1.0 if condition else 0.0, ...}` for all three keys.
   - `passed = all(v == 1.0 for v in breakdown.values())`; `score = statistics.mean(breakdown.values())`.
   - Emit paired failure codes (AC-11) for each falsy signal.
   - Emit `migration.dockerfile_unparseable` (warn) when the Dockerfile string is empty / has no `FROM` line.
   - `__main__` block reads stdin JSON, validates, calls `score(...)`, writes stdout, exits 0; exits 2 on `json.JSONDecodeError`/`pydantic.ValidationError`.

6. **`tests/test_rubric_unit.py`** (bench-author, in-process) — direct `score(case, harness_output)` calls covering: all-pass, swap-not-done, shell-present, build-failed, dockerfile-empty (dockerfile_unparseable warn). Assert `set(result.breakdown.keys()) == {m.value for m in BreakdownKey}`; assert emitted failure codes are in the YAML-declared set.

7. **`tests/unit/eval/test_bench_distroless_registration.py`** — pins identity, StrEnum, taxonomy, YAML schema, immutability, double-load per §TDD plan. Lives under `tests/unit/eval/` to inherit S2-01 HARDENED AC-22's autouse `conftest.py`.

8. **`tests/integration/test_rubric_subprocess_distroless.py`** — exercises the subprocess path (`subprocess.run` with `SCRUBBED_ENV` per ADR-0001 + Phase 5 ADR-0012); asserts wall-clock ≤ 60 s on a representative envelope; asserts `returncode != 0` on `b"not-json"` stdin (AC-4).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/eval/test_bench_distroless_registration.py` (under `tests/unit/eval/` to inherit S2-01 HARDENED AC-22's autouse `conftest.py`).

```python
# tests/unit/eval/test_bench_distroless_registration.py
import ast
import types
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

import pytest
import yaml

BANNED_SUBSTRINGS = ("confidence", "llm", "self_reported", "model_says")

EXPECTED_BREAKDOWN_VALUES = frozenset({
    "base_image_swapped",
    "shell_free",
    "build_passes",
})

REQUIRED_BLOCK_CODES = frozenset({
    # migration-specific
    "migration.base_image_not_chainguard",
    "migration.shell_invocation_present",
    "migration.build_failed",
    # ADR-0004 §Tradeoffs replication requirement: runner-internal always-block
    "sut.exception",
    "sut.timeout",
    "sut.cancelled",
    "rubric.timeout",
    "rubric.unknown_failure_mode",
    "rubric.unknown_breakdown_key",   # ADR-0008 §Decision
    "rubric.malformed_output",         # ADR-0001 §Consequences
})

REQUIRED_WARN_CODES = frozenset({
    "migration.dockerfile_unparseable",
})

REQUIRED_ALL_CODES = REQUIRED_BLOCK_CODES | REQUIRED_WARN_CODES


@pytest.fixture()
def fresh_registry():
    from codegenie.eval.registry import default_registry as reg
    return reg


@pytest.fixture()
def bench_root(tmp_path: Path) -> Path:
    """Materialize bench/migration-chainguard-distroless/* under tmp_path."""
    bench = tmp_path / "bench"
    src = Path(__file__).parents[3] / "bench" / "migration-chainguard-distroless"
    target = bench / "migration-chainguard-distroless"
    target.mkdir(parents=True)
    for name in ("registration.py", "breakdown_keys.py", "failure_modes.yaml", "rubric.py"):
        (target / name).write_bytes((src / name).read_bytes())
    return bench


# --- AC-1 / AC-2 — registered TaskClass shape ----------------------------------


def test_registration_via_load_task_class_uses_literal_name_and_bronze_only_floor(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class

    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    assert tc.name == "migration-chainguard-distroless"
    assert tc.bench_path == (bench_root / "migration-chainguard-distroless").resolve()
    # ADR-0006: bronze-only; silver/gold are Phase 7's call, held-out floor stays inactive.
    assert tc.min_cases_for_promotion == MappingProxyType({"bronze": 10})
    assert isinstance(tc.min_cases_for_promotion, types.MappingProxyType)
    assert "silver" not in tc.min_cases_for_promotion
    assert "gold" not in tc.min_cases_for_promotion


def test_registered_rubric_class_is_imported_class_unmodified(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class

    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    from bench.migration_chainguard_distroless.rubric import MigrationChainguardDistrolessRubric
    assert tc.rubric_class is MigrationChainguardDistrolessRubric


def test_registration_has_exactly_one_register_task_class_call_with_literal_name(
    bench_root: Path,
):
    """AC-1: AST-walk pins the imperative-application form."""
    src = (bench_root / "migration-chainguard-distroless" / "registration.py").read_text()
    tree = ast.parse(src)
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "register_task_class"
    ]
    assert len(calls) == 1, f"expected one register_task_class call, found {len(calls)}"
    call = calls[0]
    assert isinstance(call.args[0], ast.Constant), "first arg must be ast.Constant literal"
    assert call.args[0].value == "migration-chainguard-distroless"


# --- AC-3 — BreakdownKey StrEnum shape ----------------------------------------


def test_breakdown_key_strenum_has_expected_three_members(bench_root: Path, fresh_registry):
    from codegenie.eval.loader import load_task_class
    load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    from bench.migration_chainguard_distroless.breakdown_keys import BreakdownKey

    assert issubclass(BreakdownKey, StrEnum)
    values = frozenset(m.value for m in BreakdownKey)
    assert values == EXPECTED_BREAKDOWN_VALUES
    assert len(list(BreakdownKey)) == 3


def test_breakdown_key_values_are_ast_constant_strings(bench_root: Path):
    """AC-3: defense-in-depth on fence-CI #5 (S7-01). Catches f-string / concat mutants."""
    src = (bench_root / "migration-chainguard-distroless" / "breakdown_keys.py").read_text()
    tree = ast.parse(src)
    enum_cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "BreakdownKey"
    )
    for node in enum_cls.body:
        if isinstance(node, ast.Assign):
            assert isinstance(node.value, ast.Constant), (
                f"BreakdownKey.{node.targets[0].id} value is not ast.Constant"
            )
            assert isinstance(node.value.value, str)


# --- AC-9 — substring ban (static + runtime) ---------------------------------


def test_breakdown_key_strenum_static_substring_ban(bench_root: Path, fresh_registry):
    from codegenie.eval.loader import load_task_class
    load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    from bench.migration_chainguard_distroless.breakdown_keys import BreakdownKey

    for m in BreakdownKey:
        for banned in BANNED_SUBSTRINGS:
            assert banned not in m.value


def test_breakdown_keys_runtime_substring_ban(bench_root: Path, fresh_registry):
    from codegenie.eval.loader import load_task_class
    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    for v in tc.breakdown_keys:
        for banned in BANNED_SUBSTRINGS:
            assert banned not in v


# --- AC-5 — failure_modes.yaml taxonomy + set-exactness -----------------------


def test_failure_modes_taxonomy_has_exactly_required_codes_with_correct_severity(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class
    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    tax = tc.failure_mode_taxonomy
    for code in REQUIRED_BLOCK_CODES:
        assert tax[code] == "block", f"{code} should be block-severity"
    for code in REQUIRED_WARN_CODES:
        assert tax[code] == "warn"
    assert set(tax.keys()) == set(REQUIRED_ALL_CODES), (
        f"taxonomy set drift: extras={set(tax.keys()) - REQUIRED_ALL_CODES}, "
        f"missing={REQUIRED_ALL_CODES - set(tax.keys())}"
    )


def test_failure_mode_taxonomy_value_shape_is_literal_str_severity(
    bench_root: Path, fresh_registry,
):
    """Guards against accidentally projecting the full {severity, description}
    dict into the taxonomy value instead of the bare severity."""
    from codegenie.eval.loader import load_task_class
    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    for code, sev in tc.failure_mode_taxonomy.items():
        assert isinstance(sev, str), f"{code} severity is not str: {type(sev).__name__}"
        assert sev in {"block", "warn", "info"}


# --- AC-6 — MappingProxyType immutability ------------------------------------


def test_min_cases_for_promotion_is_mapping_proxy_type_and_immutable(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class
    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    assert isinstance(tc.min_cases_for_promotion, types.MappingProxyType)
    with pytest.raises(TypeError):
        tc.min_cases_for_promotion["silver"] = 25  # type: ignore[index]


def test_failure_mode_taxonomy_is_mapping_proxy_type_and_immutable(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class
    tc = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    assert isinstance(tc.failure_mode_taxonomy, types.MappingProxyType)
    with pytest.raises(TypeError):
        tc.failure_mode_taxonomy["new.code"] = "block"  # type: ignore[index]


# --- AC-8 — double-load idempotence ------------------------------------------


def test_double_load_task_class_does_not_raise_and_returns_same_taskclass(
    bench_root: Path, fresh_registry,
):
    from codegenie.eval.loader import load_task_class

    tc1 = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    tc2 = load_task_class(
        "migration-chainguard-distroless", bench_root=bench_root, registry=fresh_registry,
    )
    assert tc1 is tc2
    assert tc1 is fresh_registry.get("migration-chainguard-distroless")


# --- AC-7 — failure_modes.yaml schema fence ----------------------------------


def _load_yaml(bench_root: Path) -> dict:
    return yaml.safe_load(
        (bench_root / "migration-chainguard-distroless" / "failure_modes.yaml").read_text(),
    )


def test_failure_modes_yaml_top_level_is_dict_of_dicts_with_exactly_two_keys(
    bench_root: Path,
):
    raw = _load_yaml(bench_root)
    assert isinstance(raw, dict)
    for code, entry in raw.items():
        assert isinstance(entry, dict), f"{code} entry is not a dict"
        assert set(entry.keys()) == {"severity", "description"}, (
            f"{code} has unexpected keys: {set(entry.keys())}"
        )


@pytest.mark.parametrize("legal_severity", ["block", "warn", "info"])
def test_failure_modes_yaml_severity_values_are_in_literal_set(
    bench_root: Path, legal_severity: str,
):
    raw = _load_yaml(bench_root)
    severities = {entry["severity"] for entry in raw.values()}
    assert severities <= {"block", "warn", "info"}
    # "info" is absent in this task class's YAML — the sanity check only fires for
    # severities that MUST appear (block, warn).
    if legal_severity in {"block", "warn"}:
        assert legal_severity in severities


def test_failure_modes_yaml_descriptions_are_nonempty_strings(bench_root: Path):
    raw = _load_yaml(bench_root)
    for code, entry in raw.items():
        assert isinstance(entry["description"], str), f"{code} description is not str"
        assert entry["description"].strip() != "", f"{code} description is empty"


def test_failure_modes_yaml_loads_via_safe_load_only(
    bench_root: Path, monkeypatch: pytest.MonkeyPatch,
):
    """If unsafe yaml.load were used, this monkeypatch would fail the read."""
    monkeypatch.setattr(
        yaml, "load",
        lambda *a, **kw: pytest.fail("yaml.load called; safe_load discipline broken"),
    )
    raw = yaml.safe_load(
        (bench_root / "migration-chainguard-distroless" / "failure_modes.yaml").read_text(),
    )
    assert isinstance(raw, dict)


# --- AC-10 — rubric.py has no module-level I/O or side effects ---------------


def test_rubric_module_has_no_module_level_io_or_side_effects(bench_root: Path):
    """ADR-0001 §Consequences: no module-level side effects. AST-walk top-level nodes;
    only `if __name__ == "__main__":` may permit statements with effects."""
    src = (bench_root / "migration-chainguard-distroless" / "rubric.py").read_text()
    tree = ast.parse(src)

    # (a) no top-level Call outside function/class/if guard bodies.
    for node in tree.body:
        assert not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call), (
            f"top-level Call at line {node.lineno} violates ADR-0001 no-side-effects"
        )

    # (b) no time/random/uuid imports.
    banned_modules = {"time", "random", "uuid"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in banned_modules, (
                    f"banned import: {alias.name}"
                )
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned_modules, (
                f"banned from-import: {node.module}"
            )

    # (c) no os.environ access outside the __main__ guard body.
    def _visit(nodes, inside_main_guard: bool) -> None:
        for n in nodes:
            if isinstance(n, ast.If) and _is_main_guard(n.test):
                _visit(n.body, inside_main_guard=True)
                continue
            if not inside_main_guard:
                for child in ast.walk(n):
                    if (
                        isinstance(child, ast.Attribute)
                        and isinstance(child.value, ast.Name)
                        and child.value.id == "os"
                        and child.attr == "environ"
                    ):
                        pytest.fail(f"os.environ access at module scope line {child.lineno}")

    def _is_main_guard(test: ast.expr) -> bool:
        return (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "__name__"
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__"
        )

    _visit(tree.body, inside_main_guard=False)


# --- AC-1 (subprocess-entrypoint shape, not tautology) -----------------------


def test_rubric_module_has_main_guard_and_no_top_level_score_invocation(bench_root: Path):
    """AC-1 / F-TQ-1: replaces the `hasattr(mod, "__name__")` tautology."""
    src = (bench_root / "migration-chainguard-distroless" / "rubric.py").read_text()
    tree = ast.parse(src)
    main_guards = [
        n for n in tree.body
        if isinstance(n, ast.If)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "__name__"
    ]
    assert len(main_guards) == 1, "rubric.py must have exactly one `if __name__ == '__main__':`"

    for node in tree.body:
        if isinstance(node, ast.If) and node in main_guards:
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "score"
            ):
                pytest.fail(
                    f"top-level `score(...)` call at line {child.lineno}; "
                    "score must only be invoked inside the __main__ guard or bench-author tests",
                )
```

Run it; confirm `ModuleNotFoundError` (registration module doesn't exist yet) or `TaskClassNotFound`. Commit as red marker.

### Green — smallest impl shape

1. Create the four artifact files + the two test files per §Implementation outline §1–§8. Smallest shape: registration is one imperative-application call using `_severity_taxonomy_from_yaml`; breakdown_keys lists exactly the three members; YAML lists exactly the 11 codes (10 block + 1 warn); rubric is a `score()` pure function + `__main__` reading stdin, parsing the Dockerfile string with regex, writing JSON to stdout with non-zero exit on malformed input.

2. `bench/migration-chainguard-distroless/tests/test_rubric_unit.py` (in-process, per S5-02 pattern): four unit tests covering all-pass, swap-not-done, shell-present, build-failed. Test file lives under `bench/**/tests/` and imports the rubric directly via `from bench.migration_chainguard_distroless.rubric import score` after loading through the autouse conftest (mirrors S5-02 F-CON-3's conftest bridge).

3. Run `pytest tests/unit/eval/test_bench_distroless_registration.py bench/migration-chainguard-distroless/tests/ tests/integration/test_rubric_subprocess_distroless.py`; iterate to green.

### Refactor — clean up

- Module docstrings on `registration.py`, `breakdown_keys.py`, `rubric.py` cite ADR-0001, ADR-0004, ADR-0008. `failure_modes.yaml` top-of-file comment names ADR-0004 + ADR-0001.
- `mypy --strict` clean on all touched files. `rubric.py`'s `main() -> None` annotation is required.
- Rubric's regex set is conservative — false-positive on shell detection is preferable to false-negative in a stub (Phase 7 hardens).
- `bench/migration-chainguard-distroless/README.md` — one-paragraph stub naming what S6-02 (3 held-out cases + `digests.yaml`) and S6-03 (E2E `codegenie eval run` + verdict) will add.

## Files to touch

| Path | Why |
|---|---|
| `bench/migration-chainguard-distroless/registration.py` | New — imperative-application `register_task_class("migration-chainguard-distroless", ...)(MigrationChainguardDistrolessRubric)` + `_severity_taxonomy_from_yaml` helper (second consumer; Phase 15 triggers the rule-of-three lift) |
| `bench/migration-chainguard-distroless/breakdown_keys.py` | New — `BreakdownKey` StrEnum with 3 literal-value members |
| `bench/migration-chainguard-distroless/failure_modes.yaml` | New — 10 block + 1 warn = 11 entries; 3 migration-specific + 7 runner-internal always-block per ADR-0004 §Tradeoffs |
| `bench/migration-chainguard-distroless/rubric.py` | New — `score(case, harness_output) -> BenchScore` pure function + `__main__` subprocess entrypoint scoring Dockerfile-derived signals |
| `bench/migration-chainguard-distroless/README.md` | New — stub naming S6-02 and S6-03 |
| `bench/migration-chainguard-distroless/tests/test_rubric_unit.py` | New — bench-author unit tests, in-process (per S5-02 pattern) |
| `tests/unit/eval/test_bench_distroless_registration.py` | New — pins identity, StrEnum, taxonomy, YAML schema, immutability, double-load, no-side-effects, main-guard-not-tautology |
| `tests/integration/test_rubric_subprocess_distroless.py` | New — subprocess-CLI test with `SCRUBBED_ENV`, wall-clock ≤ 60 s, non-zero exit on `b"not-json"` stdin |

## Out of scope

- **Seed cases** (`cases/001-*`, `cases/002-*`, `cases/003-*`, `cases/digests.yaml`) — S6-02 owns case curation and signing.
- **E2E `codegenie eval run`** + N=3 verdict documentation — S6-03.
- **Hardening the rubric** (multi-stage detection, build sandboxing, semver checks on Chainguard image tags, `RUNTIME_CAPABILITY_MATCH`, semantic-symmetry inversion enforcement per AC-11) — Phase 7.
- **Adding `silver`/`gold` to `min_cases_for_promotion`** — Phase 7 raises the bar once ≥10 cases with ≥5 held-out exist.
- **Rule-of-three lift of `_severity_taxonomy_from_yaml`.** Today there are two consumers (`bench/vuln-remediation/registration.py` + this task class's `registration.py`); Phase 15's task class is the third. At that point the helper moves to `src/codegenie/eval/loader.py` as `_load_failure_mode_taxonomy` (the arch already names the function at line 564).
- **`_dockerfile_facts` functional-core extractor.** Design-pattern opportunity surfaced in Notes-for-implementer; Rule 2 keeps it out of scope until the rubric grows.

## Notes for the implementer

- **Stub-quality is correct.** The signals are coarse (regex on `FROM` line, regex on `RUN sh|bash`). That is the Phase 6.5 commitment; Phase 7 expands. Resist gold-plating — `Rule 2 Simplicity First` and `Rule 3 Surgical Changes`.
- **The `if __name__ == "__main__"` discipline is load-bearing** (ADR-0001). The runner spawns `python rubric.py` as a subprocess; any module-level import of e.g., `docker` would either fail at subprocess startup or slow every case by hundreds of ms. Keep imports minimal — stdlib + `codegenie.eval.models` + `pydantic` ideally. Do NOT do any I/O at module top level.
- **Non-zero exit on malformed stdin is load-bearing** (ADR-0001 §Consequences). The runner reacts to non-zero rubric exit with `FailureMode(code="rubric.malformed_output", severity="block")`. A `try/except Exception: emit passing BenchScore` would swallow the fail-loud path and silently pass a broken run. Use `sys.exit(2)` on `json.JSONDecodeError`/`pydantic.ValidationError` — mirror S5-02 AC-2 exactly.
- **All 10 block codes are required per ADR-0004 §Tradeoffs.** Runner-internal always-block codes (`sut.exception`, `sut.timeout`, `sut.cancelled`, `rubric.timeout`, `rubric.unknown_failure_mode`, `rubric.unknown_breakdown_key`, `rubric.malformed_output`) must be replicated per task class or the resolver falls back to `rubric.unknown_failure_mode` on drift and gives operators a misleading error. This is not optional.
- **Breakdown-key values are the substring-ban surface, not member names** (ADR-0008). `BASE_IMAGE_SWAPPED = "base_image_swapped"` — the `value` is what fence-CI walks. Source-of-truth for the substring list is Phase 5 ADR-0014 + ADR-0008.
- **`bench_path` in `@register_task_class`** must be `Path(__file__).parent` of `registration.py` so the loader can locate sibling files. Mirror `bench/vuln-remediation/registration.py` exactly.
- **`tests/unit/test_breakdown_keys_static.py`** auto-discovers registered task classes — if you wired registration correctly, the existing static test picks this task class up without edit. Verify the test file already ships in `src/codegenie/` (per S1-05) before assuming; do not duplicate.
- **`migration-chainguard-distroless` slug uses hyphens** in `@register_task_class("...")` but the Python package directory must use underscores (`migration_chainguard_distroless/`) for Option A `sys.path`-prep imports. Loader (HARDENED S2-01 AC-9) handles the slug→module-name translation via `spec_from_file_location`; mirror vuln-remediation's pattern.
- **Do NOT create `bench/__init__.py`, `bench/migration-chainguard-distroless/__init__.py`, or `bench/migration-chainguard-distroless/cases/__init__.py`.** S2-01 HARDENED uses PEP 420 implicit namespace packages; the hyphenated leaf can't have one anyway (invalid Python identifier). Adding any of them breaks S2-01's contract and is caught by the fence.
- **`_severity_taxonomy_from_yaml` is a file-local helper (second consumer).** HARDENED S5-01 landed the first copy in `bench/vuln-remediation/registration.py`; this story ships the second copy inline. The rule-of-three lift trigger is Phase 15's task class; at that point the helper moves to `src/codegenie/eval/loader.py` as `_load_failure_mode_taxonomy` (arch line 564). Copy-paste is deliberate — Rule 2 keeps abstraction deferred until the third data point.
- **`score = statistics.mean(breakdown.values())`, not `mean_of_three_booleans`.** The mean formula extends automatically when Phase 7 adds a 4th `BreakdownKey` member. Hard-coding "three" bakes in a landmine.
- **Semantic-symmetry inversions (AC-11) — pinned, not enforced.** The three signal↔failure pairs live in AC-11 as documentation; Phase 7 owns rubric-hardening enforcement via a parametrized `test_each_falsy_breakdown_condition_emits_its_paired_failure_code` (mirror of S5-02 AC-5). Ship the pairings in the rubric docstring so Phase 7 doesn't have to re-derive them.
- **Design opportunity — `_dockerfile_facts` functional-core extractor.** The Dockerfile-parsing regex logic is a candidate for a `_dockerfile_facts(text: str) -> _DockerfileFacts` frozen-dataclass helper. Benefits: (a) separates pure logic from `__main__` shell (functional-core / imperative-shell pattern the repo prefers), (b) makes regex behavior testable without stdin/stdout plumbing. Not promoted to AC — Rule 2 keeps it deferred until the rubric grows (Phase 7 likely triggers it when adding multi-stage detection).
