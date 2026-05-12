# Story S3-02 — `BuildGraphProbe` (B5) + `--ignore-scripts` wrapper-invariant + `resolution_status`

**Step:** Step 3 — Ship `IndexHealthProbe` (B2) and `BuildGraphProbe` (B5)
**Status:** Ready
**Effort:** M
**Depends on:** S1-05 (`tools/semgrep|syft|grype` wrappers — shows the wrapper pattern + `network="none"` invariant we mirror), S2-07 (`SCHEMA-EVOLUTION-POLICY.md`)
**ADRs honored:** ADR-0007 (`BuildGraphProbe` `--ignore-scripts` + `resolution_status`), ADR-0003 (sandbox-profile extension: `network="none"`), ADR-0004 from Phase 1 (`additionalProperties: false`), Phase 1 ADR-0007 (warning-ID pattern), Phase 1 ADR-0011 (sanctioned/unsanctioned package-manager invocation precedent)

## Context

`BuildGraphProbe` is `localv2.md §5.2 B5`'s resolved monorepo dependency-graph oracle. The synthesis (ADR-0007) is the **two-stage** design: stage 1 is always a static parse via Phase 1's `ParsedManifestMemo`; stage 2 invokes `pnpm list -r --depth -1 --json --ignore-scripts` (yarn / npm equivalents) only when a package manager is on `$PATH` **and** the repo is a monorepo. The output's `resolution_status: {static_only | resolved | resolved_with_discrepancy}` is the **facts-not-judgments** seam — consumers reading `static_only` know the resolved graph is *unknown*, not *empty* (closes critic §S.1 "fabricated graph dressed as evidence").

The single load-bearing security invariant is `--ignore-scripts`. Without it, a hostile `package.json` with `scripts.postinstall: "curl ... | sh"` becomes RCE every time `BuildGraphProbe` runs on it. This story enforces the flag **at the wrapper layer**, not the probe — so a future probe author writing `tools.pnpm.run(..., flags=["list", "-r"])` for a non-`BuildGraphProbe` use case **cannot** drop the flag. The wrapper-level unit test (`tests/unit/tools/test_pnpm_invariant.py`) lands here as the first line of defense; the end-to-end adversarial test against a `postinstall_rce_attempt/` fixture lands in S3-05 as the integration check.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #6 BuildGraphProbe (B5) — two-stage with --ignore-scripts` — full interface (`declared_inputs`, `applies()` keyed on `LanguageDetectionProbe.monorepo`, two-stage logic, performance envelope ~2–5 s).
  - `../phase-arch-design.md §"Data model" BuildGraphSlice` — `resolution_status: Literal["static_only", "resolved", "resolved_with_discrepancy"]`, `declared_edges: list[DepEdge]`, `resolved_edges: list[DepEdge] | None`, `workspaces: list[Workspace]`; `DepEdge` shape (`from_pkg, to_pkg, version_constraint, edge_type`).
  - `../phase-arch-design.md §"Failure modes & recovery"` row 8 — legacy npm without `--ignore-scripts` support → static-only with `build_graph.legacy_npm_no_ignore_scripts` warning.
  - `../phase-arch-design.md §"Implementation-level risks" #4` — `--ignore-scripts` enforced at wrapper level (the explicit move this story implements).
- **Phase ADRs:**
  - `../ADRs/0007-buildgraph-ignore-scripts-and-resolution-status.md` — ADR-0007 — two-stage output, mandatory `--ignore-scripts`, three-value `resolution_status` enum (closed; immutable).
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — ADR-0003 — `run_in_sandbox` with `network="none"` for `pnpm list` invocation.
  - `../ADRs/0005-allowed-binaries-additions.md` — `ALLOWED_BINARIES` extension that admits `pnpm / yarn / npm`.
- **Production ADRs:**
  - `../../../production/adrs/0006-deterministic-gather-no-llm.md` — `resolution_status` is the evidence-vs-judgment seam.
- **Source design:**
  - `../final-design.md §"Components" §3.5 BuildGraphProbe` — synthesizer ledger row; "static graph dressed as `medium`" pathology closed.
  - `../final-design.md §"Risks" #1` — `--ignore-scripts` discipline as ongoing convention.
- **High-level impl:**
  - `../High-level-impl.md §"Step 3"` deliverable bullet for `build_graph.py` + the wrapper-level invariant.
- **Existing code (Phase 0/1 + Step 1 output):**
  - `src/codegenie/exec.py` — `run_in_sandbox(network="none", argv=..., ro_bind=...)` extension landed in S1-02.
  - `src/codegenie/parsers/parsed_manifest_memo.py` — Phase 1's `ParsedManifestMemo` providing memo-ized package.json reads.
  - `src/codegenie/probes/node_build_system.py` — Phase 1's `NodeBuildSystemProbe` (provides `monorepo: bool` via `LanguageDetectionProbe`).
  - `src/codegenie/errors.py` — `ToolInvariantViolation` registered in S1-01.
  - `src/codegenie/probes/__init__.py` — explicit additive import seam.

## Goal

Ship a deterministic two-stage `BuildGraphProbe` that always emits a declared edge set from the static manifest parse, optionally emits a resolved edge set via `pnpm list -r --depth -1 --json --ignore-scripts` (or `yarn workspaces list --json --no-default-rc` / `npm ls --json --workspaces --omit=dev`) inside `run_in_sandbox(network="none")`, surfaces the truth via a closed-enum `resolution_status`, and enforces the `--ignore-scripts` invariant **at the wrapper layer** so the postinstall-RCE path is closed by construction.

## Acceptance criteria

- [ ] `src/codegenie/probes/build_graph.py` exists; `class BuildGraphProbe(Probe)` declares `name = "build_graph"`, `declared_inputs` matching `phase-arch-design.md §"Component design" #6` (`pnpm-workspace.yaml`, `package.json`, `packages/*/package.json`, `apps/*/package.json`, `libs/*/package.json`, `lerna.json`, `nx.json`, `turbo.json`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`), `requires = ["language_detection", "node_build_system"]`, `applies_to_languages = ["typescript", "javascript"]`, `timeout_seconds = 60`.
- [ ] `applies(snapshot)` returns `True` only when `snapshot.detected_languages.monorepo` is `True` (Phase 1 flag).
- [ ] `src/codegenie/schema/probes/build_graph.schema.json` exists, Draft 2020-12, `schema_version: "v1"`, `additionalProperties: false` at root and every nested object; declares `resolution_status` as the closed enum `["static_only", "resolved", "resolved_with_discrepancy"]`; declares `declared_edges: list[DepEdge]`, `resolved_edges: list[DepEdge] | null`, `workspaces: list[Workspace]`.
- [ ] **Stage 1 always runs.** `run()` builds the declared edge set from `ctx.parsed_manifest_memo` reads of workspace manifests; this stage **never** invokes a package manager.
- [ ] **Stage 2 runs only when** (a) `pnpm` / `yarn` / `npm` is on `$PATH` (one of, in that precedence order), **and** (b) the repo is a monorepo (already guarded by `applies()`). The chosen PM is recorded in the slice as `resolved_via: "pnpm" | "yarn" | "npm" | null`.
- [ ] **`--ignore-scripts` is wrapper-enforced for `pnpm`.** A new helper `src/codegenie/tools/_pm_invariants.py::assert_ignore_scripts(argv: Sequence[str], pm: Literal["pnpm","yarn","npm"]) -> None` raises `ToolInvariantViolation` (typed exception from S1-01) when `pm == "pnpm"` and `--ignore-scripts` is absent from `argv`. `yarn workspaces list` and `npm ls` do **not** run scripts; the invariant is a no-op for those PMs and the schema's failure-mode commentary documents it.
- [ ] Stage 2 invocation flows through `run_in_sandbox(network="none", argv=[pm, ...], ro_bind=[repo_root])` (ADR-0003). The wrapper-invariant helper is called **before** the sandbox launches.
- [ ] `resolution_status` selection logic:
  - Stage 2 didn't run (no PM on `$PATH` or `applies()=False` upstream → probe didn't execute, but if execution reaches `run()` with no PM: `static_only`).
  - Stage 2 ran, declared and resolved edge sets are equivalent (set equality on `(from_pkg, to_pkg, edge_type)` tuples): `resolved`.
  - Stage 2 ran, edge sets disjoint or partially overlapping: `resolved_with_discrepancy`; both graphs recorded; warning `build_graph.resolved_with_discrepancy` emitted.
- [ ] Legacy npm without `--ignore-scripts` flag support → static-only with `confidence: medium` + `warnings: ["build_graph.legacy_npm_no_ignore_scripts"]`. (Detected by wrapper raising `ToolInvariantViolation` from a probe-internal flag check, not by parsing npm's stderr.)
- [ ] `src/codegenie/probes/__init__.py` adds one explicit additive import line registering `BuildGraphProbe`.
- [ ] Red test exists and was committed failing; green tests cover:
  - `tests/unit/probes/test_build_graph.py`: (a) static-only path (no PM on `$PATH` — monkeypatch `shutil.which` to return `None`); (b) resolved path (PM available, declared == resolved); (c) `resolved_with_discrepancy` (PM available, declared and resolved disagree); (d) `applies()=False` on non-monorepo snapshot.
  - `tests/unit/tools/test_pnpm_invariant.py`: (e) `assert_ignore_scripts(["pnpm","list","-r","--json"], "pnpm")` raises `ToolInvariantViolation`; (f) `assert_ignore_scripts(["pnpm","list","-r","--json","--ignore-scripts"], "pnpm")` is a no-op; (g) `assert_ignore_scripts(["yarn","workspaces","list","--json"], "yarn")` is a no-op (yarn doesn't need it); (h) `assert_ignore_scripts(["npm","ls","--json","--workspaces"], "npm")` is a no-op.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict src/codegenie/probes/build_graph.py src/codegenie/tools/_pm_invariants.py`, `pytest tests/unit/probes/test_build_graph.py tests/unit/tools/test_pnpm_invariant.py -q` all pass.

## Implementation outline

1. **Sub-schema first.** `src/codegenie/schema/probes/build_graph.schema.json` mirroring `BuildGraphSlice`. `resolution_status` enum is closed and immutable per ADR-0007. `additionalProperties: false` at every level. `$comment` linking SCHEMA-EVOLUTION-POLICY.md per S2-07.
2. **Wrapper-invariant helper** at `src/codegenie/tools/_pm_invariants.py`:
   ```
   def assert_ignore_scripts(argv: Sequence[str], pm: Literal["pnpm","yarn","npm"]) -> None
   ```
   For `pm == "pnpm"`, raise `ToolInvariantViolation("build_graph.missing_ignore_scripts", argv=argv)` if `"--ignore-scripts"` not in `argv`. For `yarn` / `npm`, no-op (with an inline comment documenting the asymmetry from ADR-0007).
3. **Probe class** at `src/codegenie/probes/build_graph.py`:
   - **Stage 1.** Walk `ctx.parsed_manifest_memo.workspace_manifests(snapshot.root)`; build `declared_edges` via the dependency-graph shape in `DepEdge`. Static parse only — no subprocess.
   - **PM detection.** `_detect_pm() -> Literal["pnpm","yarn","npm"] | None` using `shutil.which` in precedence order pnpm > yarn > npm.
   - **Stage 2.** If a PM was detected, build `argv` per the chosen PM, call `assert_ignore_scripts(argv, pm)`, then `await run_in_sandbox(argv=argv, network="none", ro_bind=[snapshot.root], timeout_s=...)`. Parse stdout via `safe_json.loads` (per-tool wrapper pattern from S1-04). Translate to `resolved_edges`.
   - **Compare.** Set-equality on `(from_pkg, to_pkg, edge_type)` tuples → `resolved` else `resolved_with_discrepancy`.
   - **Warning + confidence rollup.** `static_only` → `confidence: medium` + `warnings: ["build_graph.legacy_npm_no_ignore_scripts"]` if the PM was npm and the wrapper raised; `static_only` without a wrapper raise → `confidence: medium` + `warnings: ["build_graph.pm_missing_from_path"]`. `resolved` → `confidence: high`. `resolved_with_discrepancy` → `confidence: medium` + `warnings: ["build_graph.resolved_with_discrepancy"]`.
4. **Register** in `src/codegenie/probes/__init__.py` with one additive import.
5. **Wire envelope** — `$ref` compose `build_graph.schema.json` under `probes.build_graph` (optional).

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/probes/test_build_graph.py` and `tests/unit/tools/test_pnpm_invariant.py`.

```python
# tests/unit/tools/test_pnpm_invariant.py
"""Pins: the postinstall-RCE invariant is wrapper-level, not probe-level.
Traces to: phase-arch-design.md §"Implementation-level risks" #4; ADR-0007."""
import pytest
from codegenie.errors import ToolInvariantViolation
from codegenie.tools._pm_invariants import assert_ignore_scripts

def test_pnpm_missing_ignore_scripts_raises():
    with pytest.raises(ToolInvariantViolation):
        assert_ignore_scripts(["pnpm", "list", "-r", "--json"], "pnpm")

def test_pnpm_with_ignore_scripts_ok():
    assert_ignore_scripts(["pnpm", "list", "-r", "--json", "--ignore-scripts"], "pnpm") is None

def test_yarn_no_op():
    assert_ignore_scripts(["yarn", "workspaces", "list", "--json"], "yarn") is None

def test_npm_no_op():
    assert_ignore_scripts(["npm", "ls", "--json", "--workspaces"], "npm") is None
```

```python
# tests/unit/probes/test_build_graph.py
"""Pins: two-stage with closed-enum resolution_status; --ignore-scripts wrapper-enforced.
Traces to: phase-arch-design.md §Component design #6; ADR-0007; ADR-0003."""
import pytest
from codegenie.probes.build_graph import BuildGraphProbe

@pytest.mark.asyncio
async def test_static_only_when_no_pm_on_path(monkeypatch, monorepo_snapshot, ctx):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    out = await BuildGraphProbe().run(monorepo_snapshot, ctx)
    assert out.slice["resolution_status"] == "static_only"
    assert out.slice["resolved_edges"] is None
    assert out.slice["declared_edges"]   # stage 1 always runs
    assert out.confidence == "medium"

@pytest.mark.asyncio
async def test_resolved_when_pm_agrees(monkeypatch, monorepo_snapshot, ctx, fake_pnpm_list):
    out = await BuildGraphProbe().run(monorepo_snapshot, ctx)  # fake_pnpm_list patches the sandbox
    assert out.slice["resolution_status"] == "resolved"
    assert out.confidence == "high"

@pytest.mark.asyncio
async def test_resolved_with_discrepancy_emits_warning(monkeypatch, monorepo_snapshot, ctx,
                                                       fake_pnpm_list_extra_edge):
    out = await BuildGraphProbe().run(monorepo_snapshot, ctx)
    assert out.slice["resolution_status"] == "resolved_with_discrepancy"
    assert "build_graph.resolved_with_discrepancy" in out.slice["warnings"]
    assert out.confidence == "medium"

def test_applies_false_on_non_monorepo(non_monorepo_snapshot):
    assert BuildGraphProbe().applies(non_monorepo_snapshot) is False
```

Run both test files. Expect import failures + assertion failures. Commit red.

### Green — smallest impl shape

1. Sub-schema first.
2. `_pm_invariants.py` with `assert_ignore_scripts`.
3. `build_graph.py` per **Implementation outline**.
4. Register.
5. Iterate to green.

### Refactor — bounded cleanup

- Extract `_compare_edge_sets(declared, resolved) -> Literal["resolved","resolved_with_discrepancy"]` if the inline comparison passes ~15 LOC.
- Pull each PM's invocation argv-builder into a private helper `_argv_for(pm, repo_root)` to keep the dispatch readable.
- Keep `_pm_invariants.py` minimal — one function plus a typed `Literal["pnpm","yarn","npm"]` alias.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/build_graph.py` | New — `BuildGraphProbe` two-stage implementation |
| `src/codegenie/schema/probes/build_graph.schema.json` | New — strict sub-schema; closed-enum `resolution_status` |
| `src/codegenie/tools/_pm_invariants.py` | New — wrapper-layer `--ignore-scripts` enforcement |
| `src/codegenie/probes/__init__.py` | Edit — one additive import line |
| `src/codegenie/schema/repo_context.schema.json` | Edit — `$ref` compose under `probes.build_graph` (optional) |
| `tests/unit/probes/test_build_graph.py` | New — unit tests for the four `resolution_status` paths + `applies()` |
| `tests/unit/tools/test_pnpm_invariant.py` | New — wrapper-level invariant tests |

## Out of scope

- **End-to-end postinstall-RCE adversarial fixture** — `tests/fixtures/postinstall_rce_attempt/` + `tests/adv/test_buildgraph_postinstall_blocked.py` land in S3-05.
- **`tests/integration/test_buildgraph_static_vs_resolved.py`** (the three-case integration on a real PM install) — Step 8 (S8-05) hardens this with seeded fixtures.
- **Cross-probe `if/then` envelope rule** — S3-03 (independent of `build_graph`, but adjacent — both extend the envelope).
- **Phase 3 vuln-remediation consumer of `resolved_edges`** — Phase 3 reads `build_graph.resolved_edges` (or falls back to `declared_edges` if `static_only`); not Phase 2's concern.
- **Adding a fourth PM (e.g., `bun`)** — extend `_pm_invariants.py` plus a new argv-builder when a consumer demands. Phase 2 ships pnpm / yarn / npm only per ADR-0007.

## Notes for the implementer

- The **wrapper-level** enforcement is the load-bearing security move. If you find yourself adding the `--ignore-scripts` flag inside `build_graph.py` rather than in `_pm_invariants.py`, stop — a future probe author writing `tools.pnpm.run(..., flags=["list", "-r"])` (without going through `build_graph.py`) would open the RCE path. Fail at the wrapper. Document it inline.
- The `resolution_status` enum is **immutable** per ADR-0007 reversibility. If you find a fourth case (e.g., "resolver crashed mid-run"), file a follow-up ADR proposing an additive value — do not silently extend the enum.
- `assert_ignore_scripts` raises a **typed exception** (`ToolInvariantViolation` from S1-01); it does not return a bool. The wrapper's contract is "fail loud or do nothing." The probe catches `ToolInvariantViolation` from the wrapper and translates to the `static_only` + warning path; the **wrapper** does not silently degrade.
- `run_in_sandbox(network="none", ...)` is the only network policy used here. Even `pnpm list` does not need network access (the resolver works off the on-disk lockfile + `node_modules` if present). If you find yourself reaching for `network="scoped"`, you're solving a different problem — file a question.
- The set-equality comparison for `declared` vs `resolved` is on `(from_pkg, to_pkg, edge_type)` tuples — **not** including `version_constraint`. Version constraints differ between manifest-declared and resolver-output ("^1.2.0" vs "1.2.7") legitimately; including them in the comparison would make every monorepo a `resolved_with_discrepancy`. Document the omission inline.
- The legacy-npm detection (`build_graph.legacy_npm_no_ignore_scripts`) is detected by `assert_ignore_scripts` raising when the probe's argv-builder for npm forgets the flag — but `npm ls` doesn't need it in the first place. The warning ID exists for a hypothetical future where npm changes behavior; the inline argv-builder for npm passes `--ignore-scripts` defensively for future-proofing. (This pattern matches phase-arch-design.md row 8.)
- The `monorepo: bool` flag comes from Phase 1's `LanguageDetectionProbe` via `snapshot.detected_languages.monorepo`. If you find that field missing on the snapshot, check Phase 1's `S2-01-language-detection-extension.md` — Phase 1 lands the field; Phase 2 only reads it.
- Do **not** add a `package_managers_available: list[str]` field to the slice. Stage 2 chooses one PM in precedence order; the slice records the chosen one in `resolved_via`. Listing all available PMs is judgment-dressed-as-evidence.
