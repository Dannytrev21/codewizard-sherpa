# Story S5-03 — Zip-slip + symlink escape + tsconfig pathological adversarial corpus

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready
**Effort:** M
**Depends on:** S4-02, S5-01
**ADRs honored:** ADR-0007 (warnings-id pattern; typed-exception IDs land on `ProbeOutput.errors`), ADR-0008 (in-process parse caps, no per-probe sandbox), ADR-0009 (no new C-extension parser dependencies), ADR-0011 (no Helm render / no HCL / no `npm ls`)

## Validation notes

Validated by `phase-story-validator` skill (2026-05-15); full audit log at `_validation/S5-03-adversarial-zip-slip-symlink-tsconfig.md`. Verdict: **HARDENED**. The four-lens critique surfaced **eight BLOCK-tier failures** (mostly signature/contract drift between the original story and the just-shipped codebase — `safe_json.load` missing required `max_bytes` kwarg, wrong probe name `language_stack` vs `language_detection`, typed-exception ID asserted on `warnings[]` instead of `errors[]` per ADR-0007, non-existent `probe.symlink_refused` structlog event, fictional `run_gather` fixture, non-existent `tsconfig.malformed` WarningId, conflated three-vector tsconfig fixture, missing `Depends on: S5-01`) and **eleven HARDEN-tier weaknesses** (sentinel-exfiltration replaces `/etc/passwd`-substring canary on both symlink and zip-slip per S1-02 / S4-02 hardening precedent; closed-world `out.errors == [<id>]` per S5-01 CV-3; three-layer observation for the symlink test; explicit `subdir/..` AC instead of clause-iv mention; tsconfig split into three mutation-distinct sub-cases; wall-clock budget aligned with S5-01/S5-02; `pytest.skipif(win32)` promoted from Notes to AC; `mypy --strict` clean AC; `asyncio.run` over `pytest.mark.asyncio` per S4-02 TQ-2). ACs expanded from 6 bullets to **21 individually-verifiable observables** in 6 named groups + a 3-item Out-of-scope cross-reference list. Three-layer observation pattern (parser / probe / CLI) documented in Notes as a reusable convention for future multi-layer-defense adversarial tests. No `NEEDS RESEARCH` findings; every weakness resolvable from ADRs + existing implementations + sibling validations (S5-01, S5-02, S4-02, S1-02, S1-04).

## Context

The third and final adversarial-test story in Step 5. S5-03 owns the **path-traversal + hand-rolled-parser-pathology** family: three tests pinning the structural defenses that turn untrusted file paths and untrusted JSONC bytes into bounded failures.

The `O_NOFOLLOW`-on-symlink defense (`phase-arch-design.md §"Adversarial tests"` #5) is what prevents a hostile repo's `package.json` symlink to an out-of-repo target from ever surfacing sensitive contents in the gather output. The defense lives in `parsers/safe_json.py` and `parsers/safe_yaml.py`; this story exercises **three layers of observation** for that single defense: (Layer 1) the parser raises `SymlinkRefusedError` directly; (Layer 2) `LanguageDetectionProbe` catches and maps to `package_json.symlink_refused` on `ProbeOutput.errors` with `confidence: "low"`; (Layer 3) the gather YAML + raw artifacts + audit record do not contain any byte derived from the symlink target.

The zip-slip-on-kustomize defense (`phase-arch-design.md §"Adversarial tests"` #6, `phase-arch-design.md §"Edge cases"` row 4) is the load-bearing path-containment check inside `DeploymentProbe`. The mitigation is `Path.resolve()` + `Path.is_relative_to(repo_root)`. The test asserts that a hostile `kustomization.yaml` listing a resource outside the repo (a sentinel manifest carrying `containerPort: 31337` — the S4-02 AC-24 smoking-gun convention) is rejected, while valid resources in the same kustomization (including one whose path contains `..` segments that resolve **inside** the repo) are still processed. The `containerPort: 31337` is the **structurally-impossible-to-fake** observable: a naive substring-on-`..` wrong impl provably leaks 31337 into `exposed_ports`.

The pathological-`tsconfig` test (`phase-arch-design.md §"Adversarial tests"` #8) is the JSONC parser's stress test, split into **three sub-cases** so each mutation surface is independently observable: (A) nested block comments + unterminated string → `jsonc.load` raises `MalformedJSONError("unterminated string")` in O(n) wall-clock; (B) circular `extends` → `_walk_extends` emits `tsconfig.extends_cycle` and returns `({}, ["tsconfig.extends_cycle"])`; (C) depth-exceeded chain → `_walk_extends` emits `tsconfig.extends_depth_exceeded`. The defense lives in `parsers/jsonc.py` (the state-machine comment stripper, S1-04) and `probes/node_build_system.py::_walk_extends` (depth-cap + cycle detection, S2-02).

The risk specific to this story (`High-level-impl.md §"Step 5 — Risks"`): same as S5-01 — assert the **specific** typed exception or specific in-system observable, never just `exit 0 + confidence: low`. The sentinel-exfiltration pattern (`containerPort: 31337` for K8s; `"leaked-sentinel"` for JSON) is the post-S4-02 convention for catching wrong impls that pass vacuous canary checks.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Adversarial tests"` items 5, 6, 8 — the three tests this story lands.
  - `../phase-arch-design.md §"Edge cases"` rows 3, 4, 5 — the in-system behavior these tests assert (symlink refused; kustomize path outside repo; `tsconfig.extends` cycle).
  - `../phase-arch-design.md §"Component design" #6 (DeploymentProbe)` — zip-slip mitigation (`Path.resolve()` + `is_relative_to`).
  - `../phase-arch-design.md §"Component design" #8 (parsers)` — `O_NOFOLLOW` open before read.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-warnings-id-pattern.md` — typed-exception-raised IDs go in `errors[]`; `warnings[]` is the soft-degrade vocabulary. Bare dotted ID convention (no colon-suffix).
  - `../ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md` — `O_NOFOLLOW` is the symlink-escape defense at parse time, not a separate sandbox layer.
  - `../ADRs/0009-no-new-c-extension-parser-dependencies.md` — `jsonc.py` is hand-rolled stdlib; pathological inputs must not require adding a new parser.
  - `../ADRs/0011-no-helm-render-no-hcl-no-npm-ls.md` — `DeploymentProbe` does Kustomize traversal one level deep with a containment check, not full kustomize-build render.
- **Source design:**
  - `../final-design.md §"Adversarial tests"` items 5, 6, 8.
  - `../final-design.md §"Failure modes & recovery"` rows for "Path traversal in kustomization.yaml#resources" and "package.json is a symlink pointing outside repo" and "tsconfig.json#extends chain exceeds 4 levels".
  - `../High-level-impl.md §"Step 5"` adversarial-test list items 5, 6, 8.
- **Existing code (lands earlier — must be on disk before this story starts):**
  - `src/codegenie/parsers/safe_json.py:60` (S1-02) — `load(path, *, max_bytes, max_depth=64)`; `O_NOFOLLOW`; raises `SymlinkRefusedError` on ELOOP.
  - `src/codegenie/parsers/jsonc.py:125` (S1-04) — `load(path, *, max_bytes, max_depth=64)`; same defenses + state-machine comment stripper; pathological JSONC must complete or raise in < 1 s.
  - `src/codegenie/probes/language_detection.py:188-194` (S2-01) — `_PKG_JSON_FAILURE` maps `SymlinkRefusedError → ("package_json.symlink_refused", "low")` and appends to `ProbeOutput.errors`.
  - `src/codegenie/probes/node_build_system.py:373-436` (S2-02) — `_walk_extends(tsconfig_path, repo_root, max_depth=4)` returns `(deepest_compiler_options, warnings_emitted)`; emits `tsconfig.extends_cycle` / `tsconfig.extends_depth_exceeded`; **silently swallows** `MalformedJSONError` / `SizeCapExceeded` / `SymlinkRefusedError` via `break` (no warning surfaces for malformed jsonc at the gather layer).
  - `src/codegenie/probes/deployment.py` (S4-02, lands before this story) — zip-slip containment check; `_WARNING_IDS` contains `kustomization.resource_outside_repo`; slice field `kustomization_resource_path_outside_repo: bool`.
  - `src/codegenie/errors.py` — `SymlinkRefusedError`, `MalformedJSONError`, `SizeCapExceeded`, `DepthCapExceeded` (markers-only; positional formatted-message construction).
  - `tests/adv/_helpers.py::invoke_gather` (S5-01, lands before this story) — the canonical CLI-invocation helper returning a `GatherResult(exit_code, output, context)` dataclass.
  - `tests/adv/test_symlink_escape.py` (S4-05, Phase-0 walker test) — **distinct surface** from this story (walker-side `_classify_symlink`, not parser-side `O_NOFOLLOW`); see Notes.
  - `pyproject.toml` — `[tool.pytest.ini_options]` markers list; `adv` marker registered by S5-01 (not by this story).
- **Style references:** S5-01 (parser-cap adversarial corpus) and S5-02 (lockfile + exec adversarial corpus) for the established adversarial-test layout, helper imports, sentinel-cleanup discipline, and structlog-event payload assertions.

## Goal

Three adversarial tests under `tests/adv/` exist and pass, each exercising the **specific** structural defense against a hostile fixture and pinning observable invariants at the right defense layer: (a) a `package.json` symlink to an out-of-repo JSON sentinel file is refused by `O_NOFOLLOW` at the parser layer, surfaces `package_json.symlink_refused` on `ProbeOutput.errors` at the probe layer, and the sentinel content never appears in the gather output at the CLI layer; (b) a `kustomization.yaml` listing a resource outside `repo_root` (a K8s manifest sentinel carrying `containerPort: 31337`) is rejected by the `Path.resolve()` containment check while a sibling resource using `./subdir/../deployment.yaml` (which resolves **inside** the repo) is still processed; (c) a pathological `tsconfig.json` is exercised across three sub-cases — nested-block-comments + unterminated string (raises `MalformedJSONError("unterminated string")`), circular `extends` (emits `tsconfig.extends_cycle`), depth-exceeded chain (emits `tsconfig.extends_depth_exceeded`) — each completing in under 0.5 s wall-clock. `pytest -m adv tests/adv/test_symlink_escape_in_declared_inputs.py tests/adv/test_zip_slip_kustomize.py tests/adv/test_tsconfig_pathological.py` completes in under 10 s wall-clock.

## Acceptance criteria

### Group A — Symlink-parser (Layer 1)

- [ ] **AC-1 (parser-level pin).** `tests/adv/test_symlink_escape_in_declared_inputs.py::test_safe_json_refuses_package_json_symlink` synthesizes a sentinel JSON file at `tmp_path.parent / "S5-03-leaked-sentinel.json"` containing `{"name": "leaked-sentinel", "version": "99.99.99-sentinel", "scripts": {"start": "leaked-sentinel"}}` (the canary; presence of `"leaked-sentinel"` in any output proves the symlink was followed). Creates a Node-repo skeleton in `tmp_path` with `package.json` as a symlink to the sentinel: `os.symlink(str(tmp_path.parent / "S5-03-leaked-sentinel.json"), tmp_path / "package.json")`. Calls `safe_json.load(tmp_path / "package.json", max_bytes=5_000_000)` and asserts `pytest.raises(SymlinkRefusedError, match=str(tmp_path / "package.json"))` (the path appears in the marker-message per S1-02 AC-5 hardening). Cleanup: `(tmp_path.parent / "S5-03-leaked-sentinel.json").unlink(missing_ok=True)` in `finally`.

### Group B — Symlink-probe (Layer 2)

- [ ] **AC-2 (probe-level mapping).** `tests/adv/test_symlink_escape_in_declared_inputs.py::test_language_detection_surfaces_symlink_refused_on_errors` reuses the same sentinel-symlink fixture; invokes `LanguageDetectionProbe().run(ctx)` via `asyncio.run(...)` (per S4-02 TQ-2 / `tests/unit/probes/test_node_build_system.py:93`); asserts closed-world: `out.errors == ["package_json.symlink_refused"]` AND `out.confidence == "low"` AND `out.warnings == []` (typed-exception IDs go to `errors[]` per ADR-0007). The probe-level layer is where the typed-exception → errors[] contract pins; the CLI envelope does NOT carry `ProbeOutput.errors` (only `schema_slice` is shallow-merged per `cli.py:284`), so this is the load-bearing assertion for the contract.

### Group C — Symlink-CLI-canary (Layer 3)

- [ ] **AC-3 (CLI-level data-leak canary).** Same sentinel-symlink fixture; calls `invoke_gather(tmp_path)` (the S5-01 helper imported via `from tests.adv._helpers import invoke_gather`); asserts:
  - (i) `result.exit_code == 0` (the surviving sibling-probe gate — gather continues despite the symlink-refused error).
  - (ii) `"leaked-sentinel"` does NOT appear in `result.context_yaml_text` (the full YAML bytes).
  - (iii) `"leaked-sentinel"` does NOT appear in any value under `result.raw_jsons` (concatenated raw artifact JSONs).
  - (iv) `"leaked-sentinel"` does NOT appear in the audit record JSON at `tmp_path / ".codegenie/context/audit.json"`.
  - (v) `"99.99.99-sentinel"` does NOT appear anywhere in the above (a second-axis canary; mutation against the "name only" leak path).
  The smoking-gun observable is **structural**: without O_NOFOLLOW, the parser reads the sentinel and `LanguageDetectionProbe._post_walk` derives `primary == "leaked-sentinel"`-shaped fields into the slice — those bytes WOULD reach the YAML. With O_NOFOLLOW, `SymlinkRefusedError` raises at `os.open` time, `framework_hints` stays empty, and the sentinel name never enters the slice.
- [ ] **AC-4 (structlog event pin — walker observable).** Same fixture; assert `structlog.testing.capture_logs()` records exactly one `probe.symlink.escaped` event (emitted by `LanguageDetectionProbe._walk` per `language_detection.py:101`) with `path == "package.json"` and **no `/path/to/sentinel/` leak in the event payload** (mirrors `tests/adv/test_symlink_escape.py:64-71`). Assert NO `probe.parser.cap_exceeded` events fire (the parser raises ELOOP silently per `safe_json.py`; if a future regression replaces ELOOP-raise with a size-cap path the test catches it).

### Group D — Zip-slip

- [ ] **AC-5 (sentinel-exfiltration zip-slip pin — replaces `/etc/passwd` substring canary; mirrors S4-02 AC-24).** `tests/adv/test_zip_slip_kustomize.py::test_kustomize_zip_slip_refused_sentinel_isolated` writes a sentinel manifest at `tmp_path.parent / "S5-03-SENTINEL-LEAK.yaml"` containing a `kind: Deployment` document with `spec.template.spec.containers[0].ports[0].containerPort: 31337` (the smoking-gun port — structurally-impossible-to-fake). Writes the legitimate sibling at `tmp_path / "k8s" / "deployment.yaml"` (kind: Deployment, `containerPort: 8080`). Writes the dot-dot-resolves-inside canary directory: `tmp_path / "k8s" / "subdir"` (must exist for `./subdir/../deployment.yaml` to resolve). Writes `tmp_path / "k8s" / "kustomization.yaml"`:
  ```yaml
  apiVersion: kustomize.config.k8s.io/v1beta1
  kind: Kustomization
  resources:
    - "../../S5-03-SENTINEL-LEAK.yaml"        # zip-slip: resolves OUTSIDE tmp_path
    - "./deployment.yaml"                      # legitimate
    - "./subdir/../deployment.yaml"            # canary: resolves INSIDE tmp_path
  ```
  Plus a `tmp_path / "package.json"` (minimal `{"name":"x","version":"0.0.0"}`) so the gather emits a deployment slice. Calls `invoke_gather(tmp_path)`. Asserts:
  - **31337 not in `result.context["probes"]["deployment"]["exposed_ports"]`** — the load-bearing observable (sentinel content did not reach the slice; the naive `str(root) + str(resource)` + `.startswith` wrong impl provably leaks 31337 because `Path("/tmp/x") / "../sentinel.yaml"` stringifies to `/tmp/x/../sentinel.yaml` which **does** start with `/tmp/x`; the correct `.resolve().is_relative_to(root.resolve())` defense rejects).
  - `result.context["probes"]["deployment"]["kustomization_resource_path_outside_repo"] is True` (S4-02 slice field).
  - `"kustomization.resource_outside_repo" in result.context["probes"]["deployment"]["warnings"]` (the S4-02 soft-degrade signal; bare ID per ADR-0007).
  Cleanup: `(tmp_path.parent / "S5-03-SENTINEL-LEAK.yaml").unlink(missing_ok=True)` in `finally`.
- [ ] **AC-6 (positive control — legitimate sibling still processed).** Same fixture, same gather call; asserts `8080 in result.context["probes"]["deployment"]["exposed_ports"]` (the legitimate sibling resource was processed despite the hostile co-resident in the same kustomization). A regression that broke processing for ALL resources (not just the escaped one) fails this assertion.
- [ ] **AC-7 (load-bearing `subdir/..` canary — proves the mechanism is `Path.resolve()`, not substring-on-`..`).** Same fixture; asserts that `./subdir/../deployment.yaml` (which `Path.resolve()`s to `tmp_path / "k8s" / "deployment.yaml"` — inside the repo) **is** processed. The most likely wrong impl — "simplifying" the check to substring-match on `..` — rejects this valid resource. The assertion: `result.context["probes"]["deployment"]["exposed_ports"].count(8080) >= 1` (8080 appears at least once; appears twice if both sibling references are processed AND ports are not deduped, depending on S4-02's `_aggregate_exposed_ports` shape). The canary's failure surfaces immediately on a substring-on-`..` regression. **Do not remove this canary during refactor.**
- [ ] **AC-8 (no sentinel string-leak — defense-in-depth substring check).** Same fixture; asserts the sentinel-revealing strings `"S5-03-SENTINEL-LEAK"`, `"containerPort: 31337"`, and `31337` (as a number coerced via JSON dump) do NOT appear in `result.context_yaml_text` or any value under `result.raw_jsons`. Belt-and-suspenders against a regression where the structural check at AC-5 passes but bytes leak via an unexpected slice field.

### Group E — Tsconfig (three sub-cases)

- [ ] **AC-9 (Sub-case A — nested block comments + unterminated string).** `tests/adv/test_tsconfig_pathological.py::test_jsonc_load_nested_blocks_plus_unterminated_string_raises_under_one_second` writes `tmp_path / "tsconfig.json"` with body `(b"/*" * 100) + (b"*/" * 100) + b'\n{ "extends": "./other.json", "compilerOptions": { "out'` (100 nested block-comment opens + 100 closes + an unterminated string in `compilerOptions.out`). `t0 = time.monotonic(); with pytest.raises(MalformedJSONError, match="unterminated string"): jsonc.load(tsconfig, max_bytes=1_000_000); elapsed = time.monotonic() - t0; assert elapsed < 0.5, f"jsonc.load took {elapsed:.2f}s"`. The `match="unterminated string"` is mutation-resistance against a regression where the stripper falls through to `json.loads` and the `MalformedJSONError` carries a `json.JSONDecodeError`-derived message instead. (The cycle file is NOT written in this sub-case — `jsonc.load` raises before `_walk_extends` would resolve `extends`.)
- [ ] **AC-10 (Sub-case B — circular `extends`, well-formed JSONC).** `tests/adv/test_tsconfig_pathological.py::test_walk_extends_detects_cycle_under_one_second` writes two well-formed JSONC files:
  - `tmp_path / "tsconfig.json"`: `{"extends": "./tsconfig.cycle.json", "compilerOptions": {"strict": true}}`
  - `tmp_path / "tsconfig.cycle.json"`: `{"extends": "./tsconfig.json"}`
  Calls `t0 = time.monotonic(); deepest, warnings = _walk_extends(tmp_path / "tsconfig.json", tmp_path); elapsed = time.monotonic() - t0`. Asserts:
  - `elapsed < 0.5`.
  - `"tsconfig.extends_cycle" in warnings` (the soft-degrade signal at `node_build_system.py:405`).
  - `deepest == {"strict": True}` (the first level's compilerOptions IS recorded before the cycle is detected — preserves S2-02's "deepest-reached config" semantic).
- [ ] **AC-11 (Sub-case C — depth-exceeded `extends` chain).** `tests/adv/test_tsconfig_pathological.py::test_walk_extends_emits_depth_exceeded_on_six_level_chain` writes six well-formed JSONC files chained linearly (`tsconfig.json → t1.json → t2.json → t3.json → t4.json → t5.json`, six levels total; depth 5 exceeds the `_TSCONFIG_EXTENDS_MAX_DEPTH=4` cap at `node_build_system.py`). The terminal file omits `extends`. Calls `deepest, warnings = _walk_extends(tmp_path / "tsconfig.json", tmp_path)`. Asserts:
  - `"tsconfig.extends_depth_exceeded" in warnings`.
  - `"tsconfig.extends_cycle" not in warnings` (closed-world; mutation against a regression where cycle and depth-exceeded are conflated).
- [ ] **AC-12 (Sub-case A gather-level silent-swallow observable).** Same fixture as AC-9, plus a `tmp_path / "package.json"` (`{"name":"x","version":"0.0.0"}`) so gather emits both slices; calls `invoke_gather(tmp_path)`. Asserts:
  - `result.exit_code == 0`.
  - `result.context["probes"]["node_build_system"]["typescript"]["resolved_compiler_options"] == {}` (the silent-swallow observable — `_walk_extends` breaks on `MalformedJSONError` per `node_build_system.py:421` with no warning surfaced; `typescript.resolved_compiler_options` is the empty dict per the silent-swallow contract).
  - `"tsconfig.extends_cycle" not in result.context["probes"]["node_build_system"]["warnings"]` AND `"tsconfig.extends_depth_exceeded" not in ...` AND `"tsconfig.depth_cap_exceeded" not in result.context["probes"]["node_build_system"]["errors"]` (closed-world — only silent-swallow, no spurious IDs).
  - The end-to-end gather completes in under 2 s wall-clock (catches a regression where the gather hangs because the pathological body forces the parser into a non-terminating path).

### Group F — Hygiene & convention

- [ ] **AC-13 (`invoke_gather` import).** Every CLI-level test imports `from tests.adv._helpers import invoke_gather, GatherResult` (the S5-01 helper). No test reimplements the CLI invocation pattern.
- [ ] **AC-14 (skip-on-Windows).** All three test files carry `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW / Path.resolve() / O_NOFOLLOW semantics")` on every test function. Mirrors S5-01 AC-18 / `tests/adv/test_symlink_escape.py:34`.
- [ ] **AC-15 (`adv` marker registration).** All three test files apply `@pytest.mark.adv` on every test function. The marker itself is registered by **S5-01** (not by this story); this story declares `Depends on: S5-01` and asserts the collection-time invariant `pytest --collect-only tests/adv/test_symlink_escape_in_declared_inputs.py tests/adv/test_zip_slip_kustomize.py tests/adv/test_tsconfig_pathological.py` exits 0 with no `PytestUnknownMarkWarning`.
- [ ] **AC-16 (`mypy --strict` clean).** All three test files type-check under the project's `mypy --strict` config (no `Any`, no untyped functions, explicit `Path` / `Literal` types at every boundary). Mirrors S5-01 AC-17.
- [ ] **AC-17 (sentinel cleanup hygiene).** Each test using a `tmp_path.parent / "S5-03-*"` sentinel file wraps the test body in `try:/finally:` with explicit `Path.unlink(missing_ok=True)` for every sentinel path. (`tmp_path.parent` is the pytest-shared root; pytest's `tmp_path` cleanup does NOT remove files outside `tmp_path`.)
- [ ] **AC-18 (wall-clock budget).** `pytest -m adv tests/adv/test_symlink_escape_in_declared_inputs.py tests/adv/test_zip_slip_kustomize.py tests/adv/test_tsconfig_pathological.py` completes in under 10 s wall-clock on a developer machine. Record peak in PR body. Aligns with S5-01 (15 s, 4 tests + 600 MB writer) / S5-02 (10 s, 3 tests including subprocess spawn).
- [ ] **AC-19 (`tmp_path` discipline for non-sentinel files).** Every non-sentinel fixture file (kustomization, deployment manifests, tsconfig chain, package.json) is synthesized under `tmp_path` by the test; no test reads from `tests/fixtures/` or `tests/adv/data/`. (Static-grep assertion: `grep -rn "tests/fixtures/\|tests/adv/data/" tests/adv/test_symlink_escape_in_declared_inputs.py tests/adv/test_zip_slip_kustomize.py tests/adv/test_tsconfig_pathological.py` returns nothing.) Sentinel files at `tmp_path.parent / "S5-03-*"` are the documented exception (per AC-17 cleanup).
- [ ] **AC-20 (no `pytest.mark.asyncio`).** The probe-level layer of the symlink test (AC-2) uses `asyncio.run(probe.run(ctx))` inline, not `@pytest.mark.asyncio`. Mirrors S4-02 TQ-2 / Rule 11 / `tests/unit/probes/test_node_build_system.py:93`.

### Group G — Out-of-scope cross-references

- [ ] **OOS-1 (Phase-0 walker-side symlink test is unchanged).** `tests/adv/test_symlink_escape.py` (S4-05) is the walker-side symlink test (`LanguageDetectionProbe._classify_symlink` driven; emits `probe.symlink.escaped` for symlinks-elsewhere-in-walk). This story adds `tests/adv/test_symlink_escape_in_declared_inputs.py` — a **distinct surface** (parser-O_NOFOLLOW on the `package.json` symlink itself). Both files coexist; this story does NOT edit `tests/adv/test_symlink_escape.py`.
- [ ] **OOS-2 (S4-02 probe-PR unit-level zip-slip is owned upstream).** `tests/unit/probes/test_deployment.py::test_kustomize_resource_outside_repo_refused` (S4-02) is the probe-PR unit-level zip-slip test. S5-03 adds the **adversarial-corpus-level** counterpart at the CLI layer. This story does NOT edit `tests/unit/probes/test_deployment.py`.
- [ ] **OOS-3 (property-based `_walk_extends` fuzz is Phase-2 deferred).** A `hypothesis.strategies.lists(small_paths)` property-test against `_walk_extends`'s cycle-detection invariant is documented in Notes (DP-4) but not landed in this story. Phase 2 may add it as a separate story.

## Implementation outline

1. **`tests/adv/test_symlink_escape_in_declared_inputs.py`** — three test functions (Layers 1 / 2 / 3) sharing a module-level fixture builder for the sentinel JSON file. Each test wraps in `try:/finally:` with explicit cleanup.
   - **Sentinel content** (module constant): `_SENTINEL_JSON = '{"name": "leaked-sentinel", "version": "99.99.99-sentinel", "scripts": {"start": "leaked-sentinel"}}'`. Bytes-shaped; written via `Path.write_text(...)`.
   - **Sentinel path** (per-test, parametrized on `tmp_path`): `_sentinel_path(tmp_path) = tmp_path.parent / "S5-03-leaked-sentinel.json"`. Living under `tmp_path.parent` (not `tmp_path`) is required so the symlink target is OUTSIDE the analyzed repo root — the whole point of the test.
   - **Symlink creation**: `os.symlink(str(_sentinel_path(tmp_path)), tmp_path / "package.json")`.
   - **Test 1 (AC-1, Layer 1):** `pytest.raises(SymlinkRefusedError, match=str(tmp_path / "package.json"))` on `safe_json.load(tmp_path / "package.json", max_bytes=5_000_000)`.
   - **Test 2 (AC-2, Layer 2):** build `ctx` (per `tests/unit/probes/test_language_detection_extended.py` pattern); `out = asyncio.run(LanguageDetectionProbe().run(ctx))`; assert closed-world `out.errors == ["package_json.symlink_refused"]` AND `out.confidence == "low"` AND `out.warnings == []`.
   - **Test 3 (AC-3 + AC-4, Layer 3):** `result = invoke_gather(tmp_path)`; assert exit 0 + the four no-leak invariants (YAML / raw / audit / second-axis); assert structlog observables via `capture_logs()`.
2. **`tests/adv/test_zip_slip_kustomize.py`** — one test function (AC-5 + AC-6 + AC-7 + AC-8 share the same fixture; one gather invocation; multiple assertions). Sentinel cleanup in `finally`.
   - **Sentinel manifest** (module constant): `_SENTINEL_DEPLOY` — a well-formed `kind: Deployment` YAML with `containerPort: 31337`.
   - **Legit sibling** (module constant): `_VALID_DEPLOY` — `kind: Deployment` with `containerPort: 8080`.
   - **Kustomization body** (module constant): the three-resource YAML body shown in AC-5.
   - **Test body:** synthesize all four files (sentinel at `tmp_path.parent`, three under `tmp_path / "k8s"`); ensure `tmp_path / "k8s" / "subdir"` exists; write `tmp_path / "package.json"`; `result = invoke_gather(tmp_path)`; assert AC-5 through AC-8.
3. **`tests/adv/test_tsconfig_pathological.py`** — three test functions (sub-cases A / B / C), one per AC-9 / AC-10 / AC-11, plus one for AC-12 (gather-level silent-swallow). No sentinel cleanup needed (no files outside `tmp_path`).
   - **Sub-case A** uses bytes-mode write: `(tmp_path / "tsconfig.json").write_bytes((b"/*" * 100) + (b"*/" * 100) + body)`. Direct `jsonc.load` call.
   - **Sub-case B** uses `Path.write_text` with the two well-formed JSONC bodies. Direct `_walk_extends` call (imported from `codegenie.probes.node_build_system`).
   - **Sub-case C** uses a small helper `_build_extends_chain(root: Path, depth: int) -> Path` (module-local pure function — files are written deterministically; depth is parametrizable). Returns the head `tsconfig.json`. Direct `_walk_extends` call.
   - **Sub-case A gather-level (AC-12):** same fixture as Sub-case A plus a minimal `package.json`; `invoke_gather`; assert silent-swallow + closed-world ID-absence + 2 s wall-clock.
4. **No new test-helper extraction.** The two sentinel patterns (JSON package skeleton + K8s manifest with port 31337) have one consumer each in Phase 1; CLAUDE.md Rule 2 (three-similar-lines threshold) is not met. Module-level constants in each test file are correct.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Land each test file independently. Start with the symlink test (simplest fixture surface), then zip-slip, then tsconfig (three sub-cases in one file).

```python
# tests/adv/test_symlink_escape_in_declared_inputs.py
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Final

import pytest
import yaml
from structlog.testing import capture_logs

from codegenie.errors import SymlinkRefusedError
from codegenie.parsers import safe_json
from codegenie.probes.language_detection import LanguageDetectionProbe
from tests.adv._helpers import invoke_gather

_SENTINEL_JSON: Final[str] = (
    '{"name": "leaked-sentinel", "version": "99.99.99-sentinel", '
    '"scripts": {"start": "leaked-sentinel"}}'
)


def _sentinel_path(tmp_path: Path) -> Path:
    return tmp_path.parent / "S5-03-leaked-sentinel.json"


def _setup_symlink_fixture(tmp_path: Path) -> Path:
    sentinel = _sentinel_path(tmp_path)
    sentinel.write_text(_SENTINEL_JSON, encoding="utf-8")
    link = tmp_path / "package.json"
    os.symlink(str(sentinel), str(link))
    return sentinel


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW semantics")
def test_safe_json_refuses_package_json_symlink(tmp_path: Path) -> None:
    """AC-1 — Layer 1: parser raises SymlinkRefusedError on O_NOFOLLOW ELOOP."""
    sentinel = _setup_symlink_fixture(tmp_path)
    try:
        with pytest.raises(SymlinkRefusedError, match=str(tmp_path / "package.json")):
            safe_json.load(tmp_path / "package.json", max_bytes=5_000_000)
    finally:
        sentinel.unlink(missing_ok=True)


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW semantics")
def test_language_detection_surfaces_symlink_refused_on_errors(
    tmp_path: Path, build_ctx  # build_ctx fixture lifted from test_language_detection_extended
) -> None:
    """AC-2 — Layer 2: probe maps SymlinkRefusedError to errors[] with confidence=low."""
    sentinel = _setup_symlink_fixture(tmp_path)
    try:
        ctx = build_ctx(tmp_path)
        out = asyncio.run(LanguageDetectionProbe().run(ctx))
        assert out.errors == ["package_json.symlink_refused"]
        assert out.confidence == "low"
        assert out.warnings == []
    finally:
        sentinel.unlink(missing_ok=True)


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only O_NOFOLLOW semantics")
def test_gather_under_symlink_no_sentinel_leak(tmp_path: Path) -> None:
    """AC-3 + AC-4 — Layer 3: sentinel content never reaches gather output."""
    sentinel = _setup_symlink_fixture(tmp_path)
    try:
        with capture_logs() as logs:
            result = invoke_gather(tmp_path)
        assert result.exit_code == 0
        # AC-3: closed-world no-leak across YAML + raw + audit
        all_text = result.context_yaml_text + "\n".join(result.raw_jsons.values())
        audit_path = tmp_path / ".codegenie" / "context" / "audit.json"
        if audit_path.exists():
            all_text += audit_path.read_text(encoding="utf-8")
        assert "leaked-sentinel" not in all_text, "sentinel name reached gather output"
        assert "99.99.99-sentinel" not in all_text, "sentinel version reached gather output"
        # AC-4: walker observable
        escaped = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
        assert len(escaped) == 1, f"expected 1 probe.symlink.escaped event, got {len(escaped)}"
        assert escaped[0].get("path") == "package.json"
        assert str(sentinel) not in str(escaped[0]), "resolved target leaked into event payload"
        # AC-4: no cap_exceeded event (parser raises silently on ELOOP)
        cap_events = [e for e in logs if e.get("event") == "probe.parser.cap_exceeded"]
        assert cap_events == [], f"unexpected cap_exceeded events: {cap_events}"
    finally:
        sentinel.unlink(missing_ok=True)
```

```python
# tests/adv/test_zip_slip_kustomize.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import pytest

from tests.adv._helpers import invoke_gather

_SENTINEL_DEPLOY: Final[str] = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sentinel-leak
spec:
  template:
    spec:
      containers:
        - name: leak
          image: alpine
          ports:
            - containerPort: 31337
"""

_VALID_DEPLOY: Final[str] = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webapp
spec:
  template:
    spec:
      containers:
        - name: web
          image: alpine
          ports:
            - containerPort: 8080
"""

_KUSTOMIZATION: Final[str] = """\
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - "../../S5-03-SENTINEL-LEAK.yaml"
  - "./deployment.yaml"
  - "./subdir/../deployment.yaml"
"""


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only Path.resolve() semantics")
def test_kustomize_zip_slip_refused_sentinel_isolated(tmp_path: Path) -> None:
    """AC-5/6/7/8 — sentinel exfiltration refused; legit sibling + subdir-canary processed."""
    sentinel = tmp_path.parent / "S5-03-SENTINEL-LEAK.yaml"
    sentinel.write_text(_SENTINEL_DEPLOY, encoding="utf-8")
    try:
        k8s = tmp_path / "k8s"
        k8s.mkdir()
        (k8s / "subdir").mkdir()
        (k8s / "deployment.yaml").write_text(_VALID_DEPLOY, encoding="utf-8")
        (k8s / "kustomization.yaml").write_text(_KUSTOMIZATION, encoding="utf-8")
        (tmp_path / "package.json").write_text('{"name":"x","version":"0.0.0"}', encoding="utf-8")

        result = invoke_gather(tmp_path)
        assert result.exit_code == 0

        dep = result.context["probes"]["deployment"]
        # AC-5: structural — sentinel content did NOT reach slice
        assert 31337 not in dep["exposed_ports"], (
            "zip-slip exfiltration: sentinel containerPort reached slice"
        )
        assert dep["kustomization_resource_path_outside_repo"] is True
        assert "kustomization.resource_outside_repo" in dep["warnings"]
        # AC-6: legit sibling still processed
        assert 8080 in dep["exposed_ports"]
        # AC-7: subdir/.. canary — proves Path.resolve() is the mechanism
        assert dep["exposed_ports"].count(8080) >= 1
        # AC-8: belt-and-suspenders string-leak check
        all_text = result.context_yaml_text + "\n".join(result.raw_jsons.values())
        assert "S5-03-SENTINEL-LEAK" not in all_text
        assert "31337" not in all_text
    finally:
        sentinel.unlink(missing_ok=True)
```

```python
# tests/adv/test_tsconfig_pathological.py
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from codegenie.errors import MalformedJSONError
from codegenie.parsers import jsonc
from codegenie.probes.node_build_system import _walk_extends
from tests.adv._helpers import invoke_gather


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_jsonc_load_nested_blocks_plus_unterminated_string_raises_under_one_second(
    tmp_path: Path,
) -> None:
    """AC-9 — Sub-case A: nested block comments + unterminated string → MalformedJSONError < 0.5 s."""
    body = (b"/*" * 100) + (b"*/" * 100) + b'\n{ "extends": "./other.json", "compilerOptions": { "out'
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_bytes(body)

    t0 = time.monotonic()
    with pytest.raises(MalformedJSONError, match="unterminated string"):
        jsonc.load(tsconfig, max_bytes=1_000_000)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5, f"jsonc.load took {elapsed:.2f}s on pathological tsconfig"


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_walk_extends_detects_cycle_under_one_second(tmp_path: Path) -> None:
    """AC-10 — Sub-case B: circular extends → tsconfig.extends_cycle warning + deepest preserved."""
    (tmp_path / "tsconfig.json").write_text(
        '{"extends": "./tsconfig.cycle.json", "compilerOptions": {"strict": true}}',
        encoding="utf-8",
    )
    (tmp_path / "tsconfig.cycle.json").write_text(
        '{"extends": "./tsconfig.json"}',
        encoding="utf-8",
    )

    t0 = time.monotonic()
    deepest, warnings = _walk_extends(tmp_path / "tsconfig.json", tmp_path)
    elapsed = time.monotonic() - t0

    assert elapsed < 0.5
    assert "tsconfig.extends_cycle" in warnings
    assert deepest == {"strict": True}


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_walk_extends_emits_depth_exceeded_on_six_level_chain(tmp_path: Path) -> None:
    """AC-11 — Sub-case C: depth-exceeded chain → tsconfig.extends_depth_exceeded."""
    # Chain: tsconfig.json → t1 → t2 → t3 → t4 → t5  (depth 5 > cap 4)
    names = ["tsconfig.json", "t1.json", "t2.json", "t3.json", "t4.json", "t5.json"]
    for i, name in enumerate(names[:-1]):
        nxt = names[i + 1]
        (tmp_path / name).write_text(f'{{"extends": "./{nxt}"}}', encoding="utf-8")
    (tmp_path / names[-1]).write_text("{}", encoding="utf-8")

    deepest, warnings = _walk_extends(tmp_path / "tsconfig.json", tmp_path)
    assert "tsconfig.extends_depth_exceeded" in warnings
    assert "tsconfig.extends_cycle" not in warnings


@pytest.mark.adv
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only path semantics")
def test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds(
    tmp_path: Path,
) -> None:
    """AC-12 — Sub-case A end-to-end: gather completes, silent swallow, no ID surfaces."""
    body = (b"/*" * 100) + (b"*/" * 100) + b'\n{ "compilerOptions": { "out'
    (tmp_path / "tsconfig.json").write_bytes(body)
    (tmp_path / "package.json").write_text('{"name":"x","version":"0.0.0"}', encoding="utf-8")

    t0 = time.monotonic()
    result = invoke_gather(tmp_path)
    elapsed = time.monotonic() - t0

    assert result.exit_code == 0
    assert elapsed < 2.0, f"gather took {elapsed:.2f}s on pathological tsconfig"
    nbs = result.context["probes"]["node_build_system"]
    assert nbs["typescript"]["resolved_compiler_options"] == {}
    assert "tsconfig.extends_cycle" not in nbs["warnings"]
    assert "tsconfig.extends_depth_exceeded" not in nbs["warnings"]
    assert "tsconfig.depth_cap_exceeded" not in nbs["errors"]
```

Run reds, commit per file, proceed.

### Green — make it pass

All structural defenses (S1-02 `O_NOFOLLOW`, S1-04 stripper, S2-01 `_PKG_JSON_FAILURE` map, S2-02 `_walk_extends` cycle + depth, S4-02 zip-slip containment) exist in the just-landed codebase. The expected outcome: all twelve test bodies (across the three files) go green on first run with the production code unchanged.

**If a red fails for the wrong reason** (e.g., `safe_json.load` raises a generic `OSError` instead of `SymlinkRefusedError`, or `_walk_extends` returns the cycle warning but with the wrong ID, or `LanguageDetectionProbe.run` returns `out.errors == []` despite the symlink), surface that as an upstream-story regression in the PR body. The fix is small (correct exception mapping, correct ID literal); do NOT land the fix in this PR — file a separate follow-up against the responsible upstream story (S1-02 / S2-01 / S2-02 / S4-02). The S5-03 story scope is the adversarial tests, not the defenses themselves.

**Layer separation discipline.** If the Layer-1 parser test (AC-1) fails because `safe_json.load` doesn't raise `SymlinkRefusedError`, this is an S1-02 regression. If the Layer-2 probe test (AC-2) fails because the probe doesn't surface `package_json.symlink_refused`, this is an S2-01 regression. If the Layer-3 CLI test (AC-3) fails because sentinel content reaches the YAML, **either** the parser regressed (Layer 1 also fails) **or** the probe regressed (Layer 2 also fails) **or** the writer regressed (Layer 1 + 2 pass but Layer 3 fails — investigate `cli._seam_shallow_merge` and `OutputSanitizer`). The three-layer structure makes diagnostic localization deterministic.

**Zip-slip canary discipline.** If AC-5 (`31337 not in exposed_ports`) fails, the most likely cause is a substring-on-`..` wrong impl in `DeploymentProbe._kustomize_walk_resources` (or whatever S4-02 named it). The `subdir/..` canary (AC-7) provides the diagnostic: if AC-5 fails AND AC-7 fails, the wrong impl is substring-based; if AC-5 fails AND AC-7 passes, the wrong impl reads but doesn't detect (a different failure mode — e.g., the `Path.is_relative_to` check is correct but the slice merge leaks the read bytes). The two assertions together pin both axes of the defense.

**Tsconfig sub-case discipline.** Each sub-case (A / B / C) pins one `_walk_extends` invariant independently:
- Sub-case A fail → `jsonc.load` stripper regression (S1-04).
- Sub-case B fail → `_walk_extends` cycle-detection regression (S2-02; `visited: set[Path]` of resolved-absolute paths).
- Sub-case C fail → `_walk_extends` depth-cap regression (S2-02; `_TSCONFIG_EXTENDS_MAX_DEPTH=4`).
A regression that drops just one defense (e.g., the cycle-detection `visited` set is replaced with a depth-only counter) passes Sub-case A and Sub-case C but fails Sub-case B. The combined-vector original fixture would have passed all three with a single check; the split is the mutation-resistance gain.

### Refactor — clean up

After green:

- **Skip-on-Windows guards on every test function** (POSIX-only adversarial surface; explicit > implicit).
- **No sentinel cleanup left to GC.** Every test using `tmp_path.parent / "S5-03-*"` wraps in `try:/finally:` with `Path.unlink(missing_ok=True)`. (`tmp_path.parent` is `/tmp/pytest-of-<user>/` shared across pytest sessions; lingering sentinel files on shared CI runners would cause weird false positives on subsequent test runs.)
- **Verify the `invoke_gather` helper exposes both `context` (parsed YAML) and `context_yaml_text` (raw bytes) AND `raw_jsons: dict[str, str]`.** If the S5-01 helper doesn't, extend it once and reuse here. The S5-01 hardening already promised these three accessors (per `_validation/S5-01` AC-7); confirm they exist before landing this PR.
- **No new test-helper extraction.** The two sentinel patterns each have one consumer in Phase 1; CLAUDE.md Rule 2 rule-of-three threshold is not met. Resist lifting `_sentinel_path` / `_setup_symlink_fixture` to `tests/adv/_helpers.py`; the inline module constants are the right shape at this consumer count.
- **`mypy --strict` clean.** All three test files type-check under the project's `mypy --strict` config; explicit `Path` / `Literal` annotations at every boundary.

## Files to touch

| Path | Why |
|---|---|
| `tests/adv/test_symlink_escape_in_declared_inputs.py` | New test file — three tests across three observation layers (parser / probe / CLI) for the `O_NOFOLLOW` symlink-refused defense |
| `tests/adv/test_zip_slip_kustomize.py` | New test file — sentinel-exfiltration zip-slip pin with `containerPort: 31337` smoking-gun observable, plus the `subdir/..` canary that proves the mechanism is `Path.resolve()` |
| `tests/adv/test_tsconfig_pathological.py` | New test file — three sub-cases (nested-blocks+unterminated-string, circular extends, depth-exceeded chain) plus gather-level silent-swallow observable |

## Out of scope

- **Cap-family adversarial tests** (yaml billion-laughs, JSON bombs, oversized lockfile) — owned by S5-01.
- **Yarn regex-DoS / planted `node` shim / `!!python/object` tests** — owned by S5-02.
- **Refining `DeploymentProbe`'s containment check** — if the test fails because the check is wrong, file a follow-up against S4-02; do not land the fix here (Rule 3 — surgical changes).
- **Helm template rendering attacks** — explicitly out per ADR-0011 (no Helm render in Phase 1).
- **Property-based fuzzing of `jsonc.py` or `_walk_extends`** — Phase 0 / Step 1 author was responsible for local fuzz before merging S1-04 (`High-level-impl.md §"Step 1 — Risks"`); Phase 2 may property-fuzz `_walk_extends` against a `hypothesis.strategies.lists(small_paths)` strategy.
- **Editing the Phase-0 walker test `tests/adv/test_symlink_escape.py`** — a distinct surface (walker-side `_classify_symlink`); this story adds a parallel test at the parser-side surface. See OOS-1.
- **Editing the S4-02 unit-level zip-slip test `tests/unit/probes/test_deployment.py`** — owned upstream; this story adds the adversarial-corpus-level CLI counterpart. See OOS-2.

## Notes for the implementer

- **Three-layer observation pattern (Layer 1 / 2 / 3) is the load-bearing test-design choice for multi-layer-defense adversarial tests.** Layer 1 (parser-level `pytest.raises`) pins the structural defense at the most precise point. Layer 2 (probe-level `asyncio.run(probe.run(ctx))` + closed-world `out.errors == [<id>]`) pins the typed-exception → errors[] contract that lives on `ProbeOutput.errors` (NOT in the schema_slice — the slice's `warnings`/`errors` arrays are forward-compatible empty in Phase 1 per the language_detection schema). Layer 3 (CLI-level `invoke_gather` + sentinel canary) pins the data-leak invariant. A regression in O_NOFOLLOW makes all three layers fail; a regression in the probe's `_PKG_JSON_FAILURE` map makes only Layer 2 fail; a regression in `_seam_shallow_merge` or `OutputSanitizer` makes only Layer 3 fail. The layered structure is the diagnostic-localization mechanism. **Future Phase-2+ adversarial tests for multi-layer defenses should adopt this pattern.**
- **Why the `package_json.symlink_refused` ID is asserted on `out.errors`, not on the gather YAML.** `_seam_shallow_merge` at `cli.py:284` shallow-merges only `output.schema_slice` into the envelope; `ProbeOutput.errors` is NOT copied. The slice-level `warnings`/`errors` arrays under `language_detection.language_stack` are forward-compatible empty in Phase 1 (per the schema's description string at `language_detection.schema.json:47`). The only way to observe the typed-exception ID is at the probe-output object, which is why Layer 2 invokes the probe directly. This is **not** a bug — it's the explicit ADR-0007 design: typed-exception IDs live on `ProbeOutput.errors` (machine-observed by the coordinator + audit chain); soft-degrade signals live in `schema_slice.*.warnings` (human-observed in the YAML). S5-03 tests both surfaces.
- **The sentinel JSON file (`tmp_path.parent / "S5-03-leaked-sentinel.json"`) is the load-bearing data-leak canary.** `/etc/passwd`-substring checks fail false-negative on broken impls because `json.JSONDecodeError.__str__` doesn't include doc bytes (the `doc` attribute is the bytes; `__str__` returns `"Expecting value: line N column M (char K)"` only; `safe_json.py:98` truncates `str(exc)` to 200 chars; the document content never reaches the YAML even with O_NOFOLLOW removed). The sentinel JSON pattern is structurally distinguishable: without O_NOFOLLOW, the parser successfully reads the sentinel and `LanguageDetectionProbe._post_walk` derives `framework_hints` from the sentinel `scripts` block; with O_NOFOLLOW, ELOOP raises at `os.open` time and no bytes are read. The `"leaked-sentinel"` substring is the smoking gun. (Mirrors `_validation/S1-02-safe-json-parser.md` AC-5 sentinel-content hardening.)
- **The `subdir/..` canary in the zip-slip test is the load-bearing assertion that the implementation uses `Path.resolve()`.** Without it, a substring-match-on-`..` implementation passes the negative case (the `../../S5-03-SENTINEL-LEAK.yaml` path is rejected) but fails on legitimate dot-dot inside repos. If a future refactor "simplifies" `DeploymentProbe` to use a substring check, this canary fails immediately. **Do not remove this canary during refactor.**
- **`Path.is_relative_to` is Python 3.9+ and works on 3.11+.** S4-02's implementation may use `is_relative_to` directly (Python 3.12) or the `Path.resolve()` + ancestor-walk fallback (Python 3.11). The test doesn't care which the implementation uses, but the implementation should be consistent — confirm at land-time by reading the S4-02 source.
- **`safe_json.load` and `jsonc.load` both require `max_bytes` as a keyword-only argument.** Per `parsers/safe_json.py:60` and `parsers/jsonc.py:125`. Calling `safe_json.load(path)` without `max_bytes` raises `TypeError: load() missing 1 required keyword-only argument: 'max_bytes'`. The 5 MiB / 1 MiB defaults used in the tests align with `language_detection._PKG_JSON_MAX_BYTES` and `node_build_system._PARSE_MAX_BYTES`.
- **No structlog event fires on `SymlinkRefusedError` from the parser.** `safe_json.py` and `jsonc.py` raise the marker silently; only `probe.symlink.escaped` (from `LanguageDetectionProbe._walk` at `language_detection.py:101`) is the observable structlog event for symlinks. `probe.parser.cap_exceeded` fires only on size or depth caps — never on ELOOP. AC-4 asserts both observables: `probe.symlink.escaped` fires once with `path="package.json"` (walker observable); no `probe.parser.cap_exceeded` fires (mutation guard against a regression that replaces the ELOOP check with a size-cap path).
- **`_walk_extends` silently swallows `MalformedJSONError` / `SizeCapExceeded` / `SymlinkRefusedError` via `break`** (per `node_build_system.py:421`). No warning surfaces in the gather YAML for malformed-jsonc paths; `typescript.resolved_compiler_options` stays empty. This is the AC-12 silent-swallow observable. Do NOT add a `tsconfig.malformed` ID — it does not exist in `_WARNING_IDS` or `_ERROR_IDS` (the only tsconfig IDs are `tsconfig.extends_cycle`, `tsconfig.extends_depth_exceeded`, `tsconfig.depth_cap_exceeded`).
- **Sentinel-cleanup discipline is non-optional.** `tmp_path.parent` is the pytest-shared root (`/tmp/pytest-of-<user>/`); pytest's `tmp_path` autouse cleanup does NOT remove files outside `tmp_path`. A test that writes `tmp_path.parent / "S5-03-SENTINEL-LEAK.yaml"` and crashes mid-test leaves the sentinel behind, where it may cause false positives on subsequent test runs (the next test's `tmp_path.parent` is the same dir; a `../S5-03-SENTINEL-LEAK.yaml` reference resolves to the leftover file). Every test using a sentinel wraps in `try:/finally:` with explicit `Path.unlink(missing_ok=True)` for every sentinel path.
- **`pytest.mark.adv` is registered by S5-01, not by this story.** This story `Depends on: S5-01`; do NOT add another marker registration in `pyproject.toml`. AC-15 asserts the collection-time invariant: `pytest --collect-only ...` exits 0 with no `PytestUnknownMarkWarning`.
- **`invoke_gather` is the S5-01 helper** at `tests/adv/_helpers.py::invoke_gather(repo: Path) -> GatherResult`. It returns a thin `@dataclass GatherResult(exit_code: int, output: str, context: dict, context_yaml_text: str, raw_jsons: dict[str, str])`. The `context_yaml_text` and `raw_jsons` accessors are required by AC-3 / AC-8 — if the S5-01 implementation doesn't yet expose them, extend `_helpers.py` in this PR (one-line addition; the existing helper already reads the YAML).
- **`asyncio.run(probe.run(ctx))` is the convention for probe-level tests** per `tests/unit/probes/test_node_build_system.py:93` and S4-02 TQ-2 hardening (Rule 11 — match the codebase's conventions). Do NOT use `pytest.mark.asyncio` — it's not in `pyproject.toml`'s markers list and would require adding a new dev dep (`pytest-asyncio`), which is out of scope.
- **The `build_ctx` fixture for Layer 2** can be lifted from `tests/unit/probes/test_language_detection_extended.py` (the existing pattern). If it's not yet a shared fixture, the cleanest path is to inline the `ProbeContext` construction in the test body (it's ~5 lines: `repo`, `policy`, `parsed_manifest`, `cancellation_token`); do NOT create a new shared fixture in `tests/adv/conftest.py` unless a second test in this story needs it.
- **The `containerPort: 31337` smoking-gun convention** is established by `_validation/S4-02-deployment-probe.md` AC-24. S5-03 reuses the exact port number so the canary is recognizable across the test suite (a future grep for `31337` finds every zip-slip canary).
- **The Phase-0 walker test (`tests/adv/test_symlink_escape.py`) is a distinct surface and is unchanged by this story.** That test exercises `LanguageDetectionProbe._classify_symlink` (a symlink in the file walk whose target is outside the repo gets classified as `"escaped"` and skipped). S5-03's symlink test exercises `safe_json.load`'s `os.open(..., O_NOFOLLOW)` — a different defense layer (the symlink IS `package.json` itself, not a file the walker encounters). Both tests coexist; the threat model and observable invariants are different. See OOS-1.
- **Three-similar-lines threshold for helper extraction.** The two sentinel patterns (JSON package skeleton + K8s manifest with `containerPort: 31337`) each have one consumer in Phase 1. Rule of three (CLAUDE.md Rule 2) not met; do NOT lift `_setup_symlink_fixture` or the kustomization fixture builders to `tests/adv/_helpers.py`. If S5-04 or a Phase-2 adversarial story introduces a third sentinel-using test, that's the moment to extract.
- **Phase-2 design opportunity (Notes-only, NOT in this story's scope).** `_walk_extends` currently returns `tuple[dict[str, Any], list[str]]` — anaemic; a tagged-union `_TsconfigOutcome = Resolved(deepest) | Cycle | DepthExceeded | Absent` would make illegal states unrepresentable (per CLAUDE.md "make illegal states unrepresentable" pattern). This is a Phase-2 refactor opportunity against the S2-02 surface, not S5-03 scope. Surface in PR body as a documented design observation.
