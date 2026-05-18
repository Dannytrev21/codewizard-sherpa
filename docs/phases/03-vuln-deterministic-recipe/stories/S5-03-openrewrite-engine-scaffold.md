# Story S5-03 — `OpenRewriteRecipeEngine` scaffold (Protocol-conformant, Phase-7 preview)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Ready
**Effort:** M
**Depends on:** S5-01
**ADRs honored:** ADR-0009, ADR-0006, ADR-0012, ADR-0010

## Context

`OpenRewriteRecipeEngine` is the **second** day-1 `RecipeEngine` implementation per ADR-0009 Option C. It is **scaffolded** — Protocol-conformant, JVM-subprocess wrapped in `SubprocessJail`, ships one working Phase-7-tagged Dockerfile-base-image-swap fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap/` — alpine → cgr.dev/chainguard/node:latest is the natural shape per `../phase-arch-design.md §Open implementation questions`), and is **never invoked by any Phase-3 npm workflow**. The whole point of the scaffold is to pay the "two genuine implementations from day one" rent ADR-0009 commits to — so that Phase 7's distroless plugin adds Dockerfile-rewrite recipes as a *recipe addition*, not an engine + recipe + dispatch invention under the "zero edits to existing code" exit criterion.

The critic correctly identified the risk in `critique.md §Shared blind spots #1`: shipping `RecipeEngine` Protocol with only `NpmLockfileRecipeEngine` would be the toolkit's textbook "Strategy with a single implementation = unnecessary indirection" anti-pattern. The fix is the scaffold — small enough that it doesn't bloat Phase 3 (per ADR-0009 tradeoffs: +~250 LOC + 1 fixture), large enough that Phase 7 inherits a working engine.

**Key non-decisions Phase 3 makes explicitly:**

- The `java` binary is **NOT** in Phase 3's `ALLOWED_BINARIES`. ADR-0012 (Phase 3) amends `ALLOWED_BINARIES` with `npm`, `bwrap`, `sandbox-exec`, `jq` — no `java`. ADR-0009 §Consequences: "added only when Phase 7 enables it (`OpenRewriteRecipeEngine` is scaffolded, but the binary it would spawn is gated)." The scaffold is structurally complete — it builds the `JailedSubprocessSpec`, it knows the JVM command shape, it conforms to the Protocol — but the **integration test that actually invokes JVM** is gated behind `@pytest.mark.phase_7_preview` (a marker that's collected but skipped by default in Phase 3 CI; Phase 7 enables it).
- The **OpenRewrite recipe DSL itself is NOT shipped** in Phase 3. The fixture carries the recipe YAML; the engine knows how to invoke it; Phase 7 ships the actual Dockerfile recipe content.
- **No JVM SecurityManager.** Rejected per critic Security Issue 4 — deprecated upstream. The `SubprocessJail` boundary IS the defense for the JVM subprocess (`../phase-arch-design.md §Goals and non-goals`).

The scaffold's job per `../phase-arch-design.md §C12`: (1) construct a `JailedSubprocessSpec` whose `cmd` invokes `java -jar <openrewrite-cli>` against the Phase-7 fixture; (2) implement `apply(repo, plan, capability)` matching the `RecipeEngine` Protocol shape; (3) return `RecipeOutcome.Applied(DockerfileBaseImageTransform(...))` on success; (4) ship the one fixture + the `@pytest.mark.phase_7_preview` test that exercises the whole shape end-to-end **when** Phase 7 enables the marker.

The conformance test (`tests/integration/test_recipe_engine_protocol.py` — per ADR-0009 Consequences) runs in Phase 3 CI and asserts both engines satisfy the `RecipeEngine` Protocol structurally. That test is the rent-payment receipt.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C12` — the scaffold description (the load-bearing two paragraphs).
  - `../phase-arch-design.md §Goals and non-goals` — "No JVM SecurityManager." line.
  - `../phase-arch-design.md §Design patterns applied row 2` — Strategy on `RecipeEngine` with two implementations.
  - `../phase-arch-design.md §Anti-patterns flagged and rejected — Premature pluggability` row.
  - `../phase-arch-design.md §Departures from all three inputs #3` — "All three demoted OpenRewrite; spec ships scaffold."
  - `../phase-arch-design.md §Open implementation questions` — "OpenRewriteRecipeEngine Phase-7 fixture content (alpine → cgr.dev/chainguard/node:latest is the natural shape)" — this story picks and ships the one fixture.
  - `../phase-arch-design.md §Phase 7 readiness P3-004` — `OpenRewriteRecipeEngine scaffolded with Phase-7 fixture`.
- **Phase ADRs:**
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — ADR-0009 — the load-bearing decision; §Consequences spells out `java` is NOT in `ALLOWED_BINARIES` for Phase 3.
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — ADR-0012 — confirms the `ALLOWED_BINARIES` amendment excludes `java`.
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — ADR-0006 — `SubprocessJail` Port; the boundary that wraps the JVM subprocess.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `Transform` ABC subclass `DockerfileBaseImageTransform`; `RecipeOutcome` tagged union.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "OpenRewriteRecipeEngine ship-or-defer"` (score 15/15).
- **High-level impl:**
  - `../High-level-impl.md §Step 5 — Features delivered` bullet 4 (`engines/openrewrite.py`); `Done criteria` line 2 (`-m phase_7_preview` test).
- **Sibling stories:**
  - `S5-01-recipe-registry.md` — the `RecipeEngine` Protocol this story conforms to.
  - `S4-01-subprocess-jail-port.md` / `S4-02-bwrap-adapter-linux.md` — `SubprocessJail` substrate; the JVM subprocess runs under bwrap on Linux.
  - `S1-04-transform-abc-apply-context.md` — `Transform` ABC; `DockerfileBaseImageTransform` is a subclass.
  - Phase 7 will spawn a follow-up story that flips `@pytest.mark.phase_7_preview` to a per-PR-required mark and adds `java` to `ALLOWED_BINARIES`.

## Goal

Ship `src/codegenie/transforms/engines/openrewrite.py` exposing `OpenRewriteRecipeEngine` and `DockerfileBaseImageTransform`. The engine structurally satisfies `RecipeEngine` Protocol (S5-01). One Phase-7-preview fixture (`tests/fixtures/openrewrite/dockerfile-base-image-swap/`) carries the recipe YAML + a Dockerfile + the expected post-rewrite Dockerfile. One `@pytest.mark.phase_7_preview` integration test exists and asserts the engine, when invoked under a real `SubprocessJail` with `java` available, returns `RecipeOutcome.Applied(DockerfileBaseImageTransform(...))` whose `diff_bytes` matches the golden. The conformance test in `tests/integration/test_recipe_engine_protocol.py` asserts both `NpmLockfileRecipeEngine` and `OpenRewriteRecipeEngine` satisfy the Protocol (ADR-0009 Consequences).

## Acceptance criteria

- [ ] `from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine, DockerfileBaseImageTransform` succeeds.
- [ ] `OpenRewriteRecipeEngine` structurally satisfies `RecipeEngine` Protocol (S5-01) — `isinstance(OpenRewriteRecipeEngine(jail), RecipeEngine)` is True.
- [ ] `DockerfileBaseImageTransform(Transform)` is an ABC subclass with the four required attrs (`transform_id`, `diff_bytes`, `files_changed`, `provenance`).
- [ ] **`OpenRewriteRecipeEngine.apply(repo, plan, capability)` builds a `JailedSubprocessSpec`** whose `cmd[0] == "java"` and includes `"-jar"` + an OpenRewrite-CLI jar path argument + the recipe YAML path; `cmd` is asserted exactly in a unit test.
- [ ] **Time / memory budget envelope** (Phase 7 will tune): `time_budget_s=300.0` (5 min for a JVM cold start + recipe run), `memory_mib=2048`, `pids_max=64`. Defaults documented in the engine docstring.
- [ ] **Network policy is `DenyAll`** for the OpenRewrite invocation — Dockerfile recipes do not need network egress; ADR-0006 boundary is the defense.
- [ ] **Phase 3 CI never invokes JVM**: the unit tests use a `FakeJail` returning `Completed(0, b"...", b"")` and assert the spec shape; no test outside `@pytest.mark.phase_7_preview` calls `java`.
- [ ] **`java` is NOT in `ALLOWED_BINARIES`** at Phase 3 — a fence test (`tests/fence/test_no_java_in_allowed_binaries.py`) asserts `"java" not in ALLOWED_BINARIES`. (This story adds the fence test; Phase 7 deletes it when it amends.)
- [ ] **Phase-7-preview integration test exists**: `tests/integration/test_openrewrite_engine_phase7_preview.py` marked `@pytest.mark.phase_7_preview` — runs the engine against the fixture, asserts `RecipeOutcome.Applied(DockerfileBaseImageTransform(...))`, `diff_bytes` matches `tests/fixtures/openrewrite/dockerfile-base-image-swap/expected.diff`. Skipped by default in Phase 3 CI.
- [ ] **Conformance test runs in Phase 3 CI**: `tests/integration/test_recipe_engine_protocol.py` (per ADR-0009) asserts (a) `NpmLockfileRecipeEngine` satisfies the Protocol; (b) `OpenRewriteRecipeEngine` satisfies the Protocol; (c) both produce typed `RecipeOutcome` variants. **Not** marked `phase_7_preview`; runs every PR.
- [ ] **Phase-7-preview marker registered**: `pyproject.toml` declares `phase_7_preview` under `[tool.pytest.ini_options].markers` with a description string; `pytest --collect-only -m phase_7_preview` lists the new integration test; `pytest -m "not phase_7_preview"` (the Phase 3 default) excludes it.
- [ ] **Fixture content**: `tests/fixtures/openrewrite/dockerfile-base-image-swap/`:
  - `Dockerfile` — `FROM node:20-alpine`-style baseline.
  - `expected.Dockerfile` — `FROM cgr.dev/chainguard/node:latest`.
  - `expected.diff` — unified diff (the byte-equal target).
  - `recipe.yml` — OpenRewrite recipe YAML targeting the Dockerfile FROM line. (Stub content — Phase 7 will rewrite when the actual rewrite recipe is authored; this story ships a placeholder that the JVM accepts.)
  - `README.md` — one paragraph explaining the fixture's role and that Phase 7 owns its content.
- [ ] `mypy --strict src/codegenie/transforms/engines/openrewrite.py` clean.
- [ ] `ruff check`, `ruff format --check`, `pytest tests/unit/transforms/test_openrewrite_engine.py tests/integration/test_recipe_engine_protocol.py` all green.
- [ ] Branch coverage on `openrewrite.py` ≥ 85% (slightly lower floor than `npm_lockfile.py` because the scaffold's body intentionally has fewer branches; the missing 15% is the JVM-result post-processing path, exercised only by the `phase_7_preview` test).
- [ ] **Story-level invariant**: a grep across `src/codegenie/{plugins,transforms}/` and `plugins/` for `from codegenie.transforms.engines.openrewrite` returns zero hits outside `transforms/__init__.py` and the conformance test — confirming "Not invoked by any Phase-3 npm workflow."

## Implementation outline

1. Create `src/codegenie/transforms/engines/openrewrite.py`.
2. Constants module-top:
   ```python
   _OPENREWRITE_TIME_BUDGET_S: Final[float] = 300.0
   _OPENREWRITE_MEMORY_MIB:    Final[int] = 2048
   _OPENREWRITE_PIDS_MAX:      Final[int] = 64
   _JAVA_BINARY:               Final[str] = "java"  # NOT in ALLOWED_BINARIES at Phase 3
   _OPENREWRITE_CLI_JAR:       Final[str] = "/opt/openrewrite/rewrite-cli.jar"  # Phase 7 enables
   ```
3. `OpenRewriteRecipeEngine.__init__(self, jail: SubprocessJail, *, cli_jar_path: str | None = None)` — constructor-injected jail; `cli_jar_path` overridable for test fixtures (default points to a Phase-7-provisioned location).
4. `async def apply(self, repo, plan, capability) -> RecipeOutcome` — builds the `JailedSubprocessSpec`, awaits, matches on `JailedSubprocessResult`, returns `RecipeOutcome.Applied(DockerfileBaseImageTransform(...))` on `Completed(0)` or `RecipeOutcome.Failed(reason=...)` on non-zero / non-Completed.
5. Build the `JailedSubprocessSpec`:
   - `cmd = ("java", "-jar", self._cli_jar_path, "run", "--recipe", "<recipe.yml path inside repo>", "--in-place")`.
   - `env = JvmEnv(java_home="/opt/java", _max_heap_mib=1024)` — a typed env wrapper analogous to `NpmEnv` (S4-01). If `JvmEnv` does not yet exist, this story adds it under `codegenie.transforms.sandbox_jail` as a minimal Pydantic frozen model. Phase 7 widens.
   - `network = DenyAll()`.
   - `time_budget_s = _OPENREWRITE_TIME_BUDGET_S` etc.
6. Define `DockerfileBaseImageTransform(Transform)` subclass; `transform_id = blake3(diff_bytes).hexdigest()`; `files_changed = [repo / "Dockerfile"]`.
7. Compute `diff_bytes` by reading the Dockerfile pre/post via `SandboxedPath` (`O_NOFOLLOW`) and `difflib.unified_diff` over the two byte sequences.
8. Conformance test `tests/integration/test_recipe_engine_protocol.py` — minimal isinstance checks; ADR-0009 §Consequences names this file.
9. Phase-7-preview test (`@pytest.mark.phase_7_preview`) — runs against the fixture under real bwrap + real `java`; skipped by default.
10. Fence test `tests/fence/test_no_java_in_allowed_binaries.py` — asserts `"java" not in ALLOWED_BINARIES` (Phase 3 invariant; Phase 7 removes).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/transforms/test_openrewrite_engine.py`, `tests/integration/test_recipe_engine_protocol.py`, `tests/integration/test_openrewrite_engine_phase7_preview.py`, `tests/fence/test_no_java_in_allowed_binaries.py`.

```python
# tests/unit/transforms/test_openrewrite_engine.py
import pytest
from codegenie.transforms.engines.openrewrite import (
    OpenRewriteRecipeEngine, DockerfileBaseImageTransform,
)
from codegenie.transforms.recipe_engine import RecipeEngine, RecipeOutcome, RecipePlan
from codegenie.transforms.sandbox_jail import Completed, DenyAll, NetworkDenied

class FakeJail:
    def __init__(self, result):
        self.result = result; self.calls = []
    async def run(self, spec):
        self.calls.append(spec); return self.result

def test_engine_satisfies_recipe_engine_protocol():
    assert isinstance(OpenRewriteRecipeEngine(jail=FakeJail(None)), RecipeEngine)

@pytest.mark.asyncio
async def test_spec_invokes_java_jar(tmp_path, dockerfile_plan):
    jail = FakeJail(Completed(0, b"", b""))
    await OpenRewriteRecipeEngine(jail=jail, cli_jar_path="/test/rewrite.jar").apply(
        SandboxedPath(tmp_path), dockerfile_plan, capability=...)
    spec = jail.calls[0]
    assert spec.cmd[0] == "java"
    assert "-jar" in spec.cmd
    assert "/test/rewrite.jar" in spec.cmd

@pytest.mark.asyncio
async def test_network_policy_is_deny_all(tmp_path, dockerfile_plan):
    jail = FakeJail(Completed(0, b"", b""))
    await OpenRewriteRecipeEngine(jail=jail).apply(SandboxedPath(tmp_path), dockerfile_plan, ...)
    assert isinstance(jail.calls[0].network, DenyAll)

@pytest.mark.asyncio
async def test_time_budget_300_memory_2048(tmp_path, dockerfile_plan):
    jail = FakeJail(Completed(0, b"", b""))
    await OpenRewriteRecipeEngine(jail=jail).apply(SandboxedPath(tmp_path), dockerfile_plan, ...)
    spec = jail.calls[0]
    assert spec.time_budget_s == 300.0 and spec.memory_mib == 2048 and spec.pids_max == 64

@pytest.mark.asyncio
async def test_non_zero_exit_returns_failed(tmp_path, dockerfile_plan):
    out = await OpenRewriteRecipeEngine(jail=FakeJail(Completed(2, b"", b"recipe parse err"))).apply(
        SandboxedPath(tmp_path), dockerfile_plan, ...)
    assert out.kind == "failed" and out.reason == "openrewrite_nonzero_exit"

@pytest.mark.asyncio
async def test_network_denied_variant_mapped(tmp_path, dockerfile_plan):
    out = await OpenRewriteRecipeEngine(jail=FakeJail(NetworkDenied(host="x"))).apply(
        SandboxedPath(tmp_path), dockerfile_plan, ...)
    assert out.kind == "failed" and out.reason == "network_policy_violation"
```

```python
# tests/integration/test_recipe_engine_protocol.py  (ADR-0009 Consequences names this file)
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine
from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine

def test_npm_lockfile_engine_satisfies_protocol(fake_jail):
    assert isinstance(NpmLockfileRecipeEngine(jail=fake_jail), RecipeEngine)

def test_openrewrite_engine_satisfies_protocol(fake_jail):
    assert isinstance(OpenRewriteRecipeEngine(jail=fake_jail), RecipeEngine)

def test_both_engines_in_recipe_engine_namespace():
    # both are exported from transforms/__init__.py per ADR-0001 export-list fence
    from codegenie.transforms import RecipeEngine as ReExportedProtocol
    assert ReExportedProtocol is RecipeEngine
```

```python
# tests/integration/test_openrewrite_engine_phase7_preview.py
import shutil, pytest
from pathlib import Path

@pytest.mark.phase_7_preview
@pytest.mark.skipif(shutil.which("java") is None, reason="requires java")
@pytest.mark.asyncio
async def test_dockerfile_base_image_swap_under_real_jvm():
    fixture = Path("tests/fixtures/openrewrite/dockerfile-base-image-swap")
    # set up SandboxedPath, BwrapAdapter, plan, run, compare diff_bytes to fixture/expected.diff
    ...
```

```python
# tests/fence/test_no_java_in_allowed_binaries.py
from codegenie.exec import ALLOWED_BINARIES

def test_java_not_in_allowed_binaries_phase3():
    assert "java" not in ALLOWED_BINARIES, (
        "Phase 3 must NOT add 'java' to ALLOWED_BINARIES — gated for Phase 7 enabling per ADR-0009. "
        "Delete this test only via a Phase 7 ADR amendment."
    )
```

Run; confirm `ImportError`; commit; implement.

### Green — make it pass

- Implement `OpenRewriteRecipeEngine.apply` as a thin orchestration: build spec, await `jail.run(spec)`, `match` on result variant, return `RecipeOutcome`. No JVM-specific parsing here — that's Phase 7's job.
- `JvmEnv` minimal Pydantic frozen model with `java_home: str` and `max_heap_mib: int`; the value is serialized into `-Xmx<n>m` JVM flags by the bwrap adapter (S4-02) or passed as `JAVA_TOOL_OPTIONS` env (cleaner). Document the chosen route in a `# noqa: D401` docstring on `JvmEnv`.
- `DockerfileBaseImageTransform` — minimal subclass; `provenance` is built from the `plan` and a synthetic `capability_use_id` (Phase 7 will populate properly).
- `pyproject.toml` — add the marker:
  ```toml
  [tool.pytest.ini_options]
  markers = [
    ...,
    "phase_7_preview: Phase 7 preview tests; skipped in Phase 3 CI by default",
  ]
  ```
- The default `pytest` invocation in `Makefile` (`make test`) should pass `-m "not phase_7_preview"` if not already implicitly excluded; verify.

### Refactor — clean up

- Confirm the scaffold is **structurally complete but functionally inert** — `apply` builds the spec and awaits the jail, but does not parse OpenRewrite's stdout into structured results. That parsing is Phase 7's job. The scaffold's responsibility ends at "spec built, jail invoked, result mapped to `RecipeOutcome`." Document this in the engine's docstring with a `Phase 7 will extend by:` block.
- Cross-check `../phase-arch-design.md §C12` — every commitment ("Protocol-conformant", "JVM-subprocess wrapped in SubprocessJail", "one fixture", "Phase-7-tagged test", "not invoked by Phase 3 npm workflows") has a matching acceptance criterion. If a criterion is missing, add it before merging.
- Verify the conformance test (`test_recipe_engine_protocol.py`) is **NOT** marked `phase_7_preview` — it runs every PR and is the load-bearing rent-payment test for ADR-0009. The Protocol-satisfaction check is pure structural typing; no JVM needed.
- The fence test for `java` is one-line; consider extending S1-05's existing fence test rather than adding a new file if S1-05 has a single "ALLOWED_BINARIES invariants" suite. Surface the choice in the PR (Rule 7 — pick one location, don't average).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/engines/openrewrite.py` | New — `OpenRewriteRecipeEngine` + `DockerfileBaseImageTransform` + `JvmEnv` (if not already in `sandbox_jail.py`) |
| `tests/unit/transforms/test_openrewrite_engine.py` | New — spec-shape unit tests (FakeJail) |
| `tests/integration/test_recipe_engine_protocol.py` | New — Protocol conformance for both engines (ADR-0009 names this) |
| `tests/integration/test_openrewrite_engine_phase7_preview.py` | New — `@pytest.mark.phase_7_preview` real-JVM test (skipped in Phase 3 CI) |
| `tests/fence/test_no_java_in_allowed_binaries.py` | New — Phase 3 invariant; Phase 7 deletes |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/Dockerfile` | New — fixture baseline |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/expected.Dockerfile` | New — fixture post-swap target |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/expected.diff` | New — golden diff |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/recipe.yml` | New — placeholder recipe (Phase 7 owns content) |
| `tests/fixtures/openrewrite/dockerfile-base-image-swap/README.md` | New — one-paragraph fixture purpose statement |
| `pyproject.toml` | Register `phase_7_preview` marker under `[tool.pytest.ini_options].markers` |
| `src/codegenie/transforms/__init__.py` | Re-export `OpenRewriteRecipeEngine`, `DockerfileBaseImageTransform` |

## Out of scope

- **Actual OpenRewrite Dockerfile-rewrite recipe content** — Phase 7. The fixture's `recipe.yml` is a placeholder.
- **Adding `java` to `ALLOWED_BINARIES`** — Phase 7 (this story explicitly forbids it via a fence test).
- **Phase 7's distroless plugin** registration / subgraph / TCCM — Phase 7.
- **OpenRewrite stdout-parsing** of structured recipe-application results — Phase 7.
- **Multi-Dockerfile or multi-stage Dockerfile** support — Phase 7 (the fixture is a single Dockerfile).
- **Maven / Gradle / other JVM-ecosystem recipes** — Phase 8+.
- **JVM SecurityManager / JEP-411 compatibility** — explicitly rejected per critic Security Issue 4; `SubprocessJail` is the boundary.

## Notes for the implementer

- **The scaffold's value is structural, not functional.** It proves the `RecipeEngine` Protocol can accommodate a wildly-different implementation (JVM subprocess vs. pure-Python npm parser) without contract distortion. If you find yourself adding a Protocol method to make OpenRewrite "fit," stop — the Protocol shape is the contract Phase 7 will inherit; distortion now is distortion forever (the snapshot test from S6-06 will pin the surface).
- **Why `JvmEnv` and not `Dict[str, str]`**: ADR-0010 + ADR-0006 — typed env, never raw `dict`. Even though Phase 3 doesn't run JVM, the *typed surface* is what Phase 7 inherits. If you skip the typed env now and Phase 7 has to retrofit one, that's an edit-not-addition (violates the "zero edits" exit criterion).
- **`@pytest.mark.phase_7_preview` lifecycle**: registered here; collected by `pytest --collect-only -m phase_7_preview` so reviewers can see what's deferred; excluded by `make test`'s default. Phase 7's first PR flips this — adds `java` to `ALLOWED_BINARIES` (its own ADR amendment), deletes the fence test from S5-03, and removes `-m "not phase_7_preview"` exclusion (or extends to `-m "not phase_8_preview"` etc.). Document this lifecycle in the marker's description string.
- **Network policy `DenyAll`** is not a guess — OpenRewrite recipes for Dockerfile rewrites operate on local files; the recipe YAML is checked in; the JVM doesn't need to fetch from Maven Central at run-time (the CLI jar is provisioned ahead of time, not downloaded). If Phase 7 needs Maven access for a recipe that pulls AST grammars, that's a per-plugin override at the spec construction site, not a default loosening.
- **CLI-jar provisioning**: the default `_OPENREWRITE_CLI_JAR = "/opt/openrewrite/rewrite-cli.jar"` path is intentionally a Phase-7-provisioned location. Phase 3 fixture tests inject a stub jar path via the `cli_jar_path=` kwarg (test fixtures download/cache the jar under `tests/fixtures/openrewrite/_cli.jar` once if Phase-7 marker is enabled). The constant is documented as "overridable; production path TBD by Phase 7 distroless plugin TCCM".
- **`DockerfileBaseImageTransform` is the second concrete `Transform` subclass**; the first is `NpmLockfileTransform` (S5-02). The `Transform` ABC (S1-04) has a sealed hierarchy by convention — every subclass lives under `src/codegenie/transforms/` or `plugins/*/recipes/`. Document this subclass at its definition with a one-liner: "Phase-7-preview. Provenance carries OpenRewrite recipe id."
- **Coverage floor 85% (vs. 95% for npm_lockfile.py)** is deliberate — the missing 15% is the JVM-stdout post-processing path that only runs under `phase_7_preview`. Coverage tools should be configured to exclude that file from the 95% gate (per-file override in `pyproject.toml` `[tool.coverage.report]` if needed; otherwise file the gap as a Phase-7 hand-off).
- **Don't ship JVM code yet.** No Java sources, no `pom.xml`, no Maven config in the codebase. The scaffold is Python-only — the JVM is an *external dependency invoked via `SubprocessJail`*. If you find yourself adding `.java` files, you've gone past the scaffold's scope.
