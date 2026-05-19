# Story S7-02 — `ShellInvocationTraceProbe` (heavy, sandbox-only) + AST isolation fence

**Step:** Step 7 — `BaseImageProbe` + `ShellInvocationTraceProbe` under the plugin (sandboxed)
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (`SandboxClient.spawn(role: SandboxRole = SandboxRole.GATE)` additive parameter — `Role.PROBE` enum value must exist or this story's `run()` body is type-illegal).
**ADRs honored:** Phase 7 ADR-0002 (`ShellInvocationTraceProbe` runs ONLY in the Phase 5 microVM via `SandboxClient.spawn(role=Role.PROBE, ..., capture_trace=True)` — the threat-model-binding decision; this is the first piece of gather-time code execution); Phase 7 ADR-0005 (probe lives under `plugins/distroless-migration--node--npm/probes/`, NOT `src/codegenie/probes/`); Phase 7 ADR-0009 (this story is net-new-files only — no allowlist row consumed); Phase 7 ADR-0015 (`strace` is NOT added to `ALLOWED_BINARIES`; in-VM `strace` is informational only — Phase 5's host-side eBPF capture is the canonical trace surface); Phase 0 ADR-0007 (frozen Probe ABC); Phase 1 ADR-0007 (warning-ID regex); Phase 3 ADR-0006 (Hexagonal `SubprocessJail` Port precedent — the same port-and-adapter discipline applies here).

## Context

`ShellInvocationTraceProbe` answers the **load-bearing precondition for distroless migration**: "does this repo's container actually invoke a shell at runtime?" Distroless base images do not ship `/bin/sh`; a migration is safe iff the container makes zero shell invocations. The shell-invocation count gates the `DistrolessBuildGate` (S10-04) and is re-run by `ShellInvocationDeltaGate` (S10-05) against the migrated image. Without this probe, the migration plugin has no honest answer to the precondition; the entire task class is a bet, not evidence.

The probe is **the first piece of gather-time code execution in the whole pipeline** — every other probe (`DockerfileProbe`, `BaseImageProbe`, the Phase 1 + 2 ecosystem probes) is pure-Python or `subprocess.run` against allowlisted CLIs without executing target-repo code. This probe executes `docker buildx build --target=builder .` against the repo. That's a threat-model-binding event. Phase 7 ADR-0002 records the synthesis-departure decision: the probe must run **inside Phase 5's microVM** (Firecracker on Linux, Lima on macOS), with trace observation happening **outside the VM** via Phase 5's existing eBPF host-side capture.

The probe is `heaviness="heavy"`, `runs_last=True`, Layer D, `requires=["BaseImage"]`. Coordinator ADR (Phase 2 02-ADR-0003) dispatches `heavy` probes after `medium` and `light`; `runs_last=True` dominates heaviness so this probe runs at the absolute tail of the gather pipeline. `cache_strategy="content"` with `declared_inputs=["Dockerfile", "**/Dockerfile", "package.json", "image-digest:<resolved>"]` — the warm-cache path is ≤ 100 ms (the cold path is seconds, accepted in §Resource & cost profile).

The **AST isolation fence** is the structural keystone of this entire phase: `tests/fence/test_shell_trace_probe_isolation.py` AST-walks the probe module and rejects **every** form of out-of-sandbox execution. No `subprocess.run`. No `os.system`. No `os.popen`. No `subprocess.Popen`. No `shell=True`. No `eval`. No `exec`. No `__import__`. No `pickle.loads`. The only privileged exit is `SandboxClient.spawn(role=Role.PROBE, ...)`. Without this fence the probe could silently grow a `dive` invocation or a `os.popen("docker ps")` call and the threat model would degrade without anyone noticing.

A surfacing note: Phase 7 ADR-0015 records that `strace` is **not** added to `ALLOWED_BINARIES`. The existing `src/codegenie/exec/__init__.py` allowlist (from Phase 0 era) does include `strace`; that is a pre-Phase-7 entry not authorized by Phase 7's amendment. **This story does not invoke `strace`** — observation happens via Phase 5's host-side eBPF, returned in the `SandboxClient.spawn(..., capture_trace=True)` result envelope. The AST fence forbids `subprocess.run` regardless of the binary, so the design holds whether `strace` is in the allowlist or not.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §9 (ShellInvocationTraceProbe)` — pins the slice fields, the `SandboxClient.spawn` invocation shape, and the AST-walk fence requirement.
  - `../phase-arch-design.md §Edge cases #2 (microVM boot failure) #5 (target build fails)` — both fold to `confidence: "low"` with typed warnings; no exception escapes.
  - `../phase-arch-design.md §Testing strategy §Fence / structural` — the AST fence is the keystone.
- **Phase ADRs:**
  - `../ADRs/0002-shell-invocation-trace-probe-runs-in-microvm.md` — sandbox-only execution; eBPF host-side observation; the four-row tradeoff table; AST fence requirement.
  - `../ADRs/0003-sandbox-role-additive-enum-on-spawn.md` — `Role.PROBE` is the enum value this story consumes.
  - `../ADRs/0005-probes-live-under-plugin-not-core-tree.md` — `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`.
  - `../ADRs/0015-allowed-binaries-amendment-dive-buildx.md` — `strace` is NOT added; eBPF host-side is the canonical trace surface.
- **Phase 5 references (precondition):**
  - `../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md` — the `SandboxClient` port + microVM adapter shape.
  - The actual Phase 5 source: `src/codegenie/sandbox/client.py` (the `SandboxClient.spawn(...)` signature this story calls; verify the parameter list at impl time).
- **Existing code:**
  - `src/codegenie/probes/base.py` — Probe ABC.
  - `src/codegenie/probes/registry.py` — `@register_probe(heaviness="heavy", runs_last=True)`.
  - `src/codegenie/probes/layer_c/shell_usage.py` (Phase 2 — STATIC shell-usage probe, NOT a runtime trace) — useful as a comparative precedent for the slice-naming convention; do not confuse the two.
  - `tests/fence/test_capability_fence.py` (Phase 3 — ruff-custom-rule capability fence) — the AST-fence style precedent. Mirror it.
- **Sibling stories:**
  - `S6-02-sandbox-spawn-role-parameter.md` — MUST land first.
  - `S6-03-sandbox-role-probe-integration.md` — landed first; pins the integration contract this probe writes against. **Per Step-7 risk note in High-level-impl: pin the S6-03 integration test BEFORE writing this probe's body.**
  - `S7-03-probe-sub-schemas-and-goldens.md` — sub-schema + golden files for the slice.
  - `S10-05-shell-invocation-delta-gate.md` — downstream consumer (re-runs the same probe against the migrated image).

## Goal

Land `ShellInvocationTraceProbe` under `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` as a Probe-ABC-conformant, `@register_probe(heaviness="heavy", runs_last=True)`-decorated, Layer-D, `task_specific`, `requires=["BaseImage"]` probe that observes shell invocations during the target repo's builder-stage build **only** through `ctx.sandbox_client.spawn(role=SandboxRole.PROBE, ..., command=["docker", "buildx", "build", "--target=builder", "."], capture_trace=True)`. Land the AST isolation fence (`tests/fence/test_shell_trace_probe_isolation.py`) that rejects every non-sandbox execution path — the structural enforcer for ADR-0002's threat-model commitment.

## Acceptance criteria

**Probe ABC conformance (AC-1 through AC-3)**
- [ ] **AC-1** `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` exists. `ShellInvocationTraceProbe(Probe)` is defined with class attributes `name = "shell_invocation_trace"`, `layer = "D"`, `tier = "task_specific"`, `applies_to_tasks = ["distroless-migration"]`, `applies_to_languages = ["*"]`, `requires = ["base_image"]` (the consumed slice key), `declared_inputs = ["Dockerfile", "**/Dockerfile", "package.json", "image-digest:<resolved>"]`, `cache_strategy = "content"`, `timeout_seconds = 600`. Verified by `tests/unit/plugins/distroless_migration_node_npm/probes/test_shell_trace_probe_metadata.py`.
- [ ] **AC-2** Registered via `@register_probe(heaviness="heavy", runs_last=True)`. Verified by the same metadata test: a fresh `Registry` instance imports the module and asserts `entry.heaviness == "heavy" AND entry.runs_last is True`.
- [ ] **AC-3** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` matches the frozen ABC byte-for-byte (parameter list `["self", "repo", "ctx"]`). AST signature test fails on drift.

**Sandbox-only execution discipline (AC-4 through AC-8) — the keystone**
- [ ] **AC-4** **AST isolation fence file** `tests/fence/test_shell_trace_probe_isolation.py` exists. Visits every `ast.Call` / `ast.Attribute` / `ast.Name` node in `shell_trace_probe.py`'s `run()` method (and every helper it calls within the module) and **rejects** any of: `subprocess.run`, `subprocess.Popen`, `subprocess.call`, `subprocess.check_call`, `subprocess.check_output`, `os.system`, `os.popen`, `os.spawn*`, `eval`, `exec`, `__import__`, `pickle.loads`, `shutil.which` followed by execution, `requests.*`, `urllib.request.*`, `httpx.*`, and any `Call` carrying a `keyword(arg="shell", value=Constant(value=True))`. The walker emits `Violation(node, reason)` per finding and raises `AssertionError(f"shell-trace probe isolation violated: {violations!r}")` — bare `assert` is forbidden by the `forbidden-patterns` pre-commit hook.
- [ ] **AC-5** **Planted-violation parametrize matrix** (red-by-construction inside the test): each row plants a forbidden snippet in a `tmp_path` copy of `shell_trace_probe.py`, runs the walker over the modified file, asserts a `Violation` fires:

  | planted snippet (placed inside `run()` body) | should be flagged? |
  |---|---|
  | `subprocess.run(["echo", "x"], check=True)` | True |
  | `import subprocess; subprocess.Popen(["ls"])` | True |
  | `os.system("echo x")` | True |
  | `os.popen("echo x").read()` | True |
  | `result = subprocess.run("ls", shell=True)` | True |
  | `eval("1 + 1")` | True |
  | `exec("x = 1")` | True |
  | `__import__("subprocess").run(["ls"])` | True |
  | `pickle.loads(b"x")` | True |
  | `import requests; requests.get("https://x")` | True |
  | `import urllib.request; urllib.request.urlopen("https://x")` | True |
  | `await ctx.sandbox_client.spawn(role=Role.PROBE, ...)` (the actual call) | False |
  | `path = Path("./foo")` | False |

  Each row is one parametrized test. **Twelve red-by-construction guards = twelve mutation guards.** A future engineer who removes the walker's `subprocess.run` check has eleven other parametrize cases still failing.
- [ ] **AC-6** **Live-file check** (zero-violation today): the same walker run against the actual `shell_trace_probe.py` finds zero violations. This is the "this story landed clean" assertion.
- [ ] **AC-7** **Sandbox-spawn presence check**: the walker also asserts **at least one `Call` node** matches `ctx.sandbox_client.spawn(role=...)` (or equivalent attribute-chain). A `run()` body that does **nothing** (returns a zeroed slice without calling the sandbox) would otherwise green the fence; this check forces the body to actually hit the sandbox port. Test name: `test_at_least_one_sandbox_spawn_call_present`.
- [ ] **AC-8** **Fence-file lint discipline**: the test file uses `raise AssertionError("...")` (not bare `assert`); `ruff check tests/fence/test_shell_trace_probe_isolation.py` clean; `mypy --strict` clean. The module-level docstring names ADR-0002 + ADR-0015 + ADR-0005 explicitly so a future reader finds the chain of decisions in one read.

**Slice shape (AC-9 through AC-12)**
- [ ] **AC-9** Slice shape (returned in `ProbeOutput.schema_slice["shell_invocation_trace"]`):
  ```python
  {
      "count": <int>,                   # total shell invocations observed
      "invocations": [
          {
              "shell": "<sh|bash|dash|...>",
              "argv": ["<arg0>", "<arg1>", ...],
              "captured_at_phase": "build|startup",
              "source_dockerfile_line": <int | None>,
          }, ...
      ],
      "trace_available": <bool>,        # False if microVM boot failed or eBPF capture failed
      "build_target": "builder",        # which Dockerfile target was built
      "image_digest": "<sha256:...>",   # the digest of the built image (post-build)
      "confidence": "high|medium|low",
  }
  ```
  Verified against `tests/golden/probes/shell_invocation_trace/*.json` (S7-03 owns the goldens; this story pins the **field set**).
- [ ] **AC-10** **`count == 0` happy path** (the distroless-ready case): fixture `tests/fixtures/portfolio/node-distroless-target/Dockerfile` (a Dockerfile that uses no shell during build); a stub `SandboxClient` returns `SpawnResult(exit_code=0, trace=ShellTrace(invocations=[]), image_digest="sha256:abc...")`; probe emits `count: 0, trace_available: True, confidence: "high"`.
- [ ] **AC-11** **`count > 0` path**: fixture with a `RUN apt-get update && rm -rf /var/lib/apt/lists/*` line; stub returns `trace.invocations == [ShellInvocation(shell="sh", argv=["-c", "apt-get update && rm -rf ..."], captured_at_phase="build", source_dockerfile_line=4)]`; probe emits `count: 1, invocations: [{...}], confidence: "high"`.
- [ ] **AC-12** **Build-failed degradation**: stub raises `SandboxBuildFailedError(exit_code=2, stderr="...")` (or equivalent typed exception per Phase 5's port contract); probe returns `ProbeOutput(confidence="low", warnings=["shell_invocation_trace.build_failed"], schema_slice={..., "count": 0, "trace_available": False})`. **No exception escapes `run()`.** Verified by `pytest.raises(BaseException)` returning False against the run-call.

**Warning-ID + sandbox-boot discipline (AC-13 through AC-15)**
- [ ] **AC-13** Module-level `_WARNING_IDS: Final[frozenset[str]] = frozenset({"shell_invocation_trace.sandbox_boot_failed", "shell_invocation_trace.build_failed"})`; import-time `raise AssertionError(...)` checks each ID matches `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- [ ] **AC-14** **Sandbox-boot-failed path**: stub raises `SandboxBootError(reason="firecracker_boot_timeout")` (or equivalent typed exception); probe returns `ProbeOutput(confidence="low", warnings=["shell_invocation_trace.sandbox_boot_failed"], schema_slice={..., "trace_available": False, "count": 0})`. Test `test_sandbox_boot_failed::test_returns_low_confidence_no_exception`.
- [ ] **AC-15** **`ctx.sandbox_client is None` discipline**: if `ctx.sandbox_client` is None (Phase 5 not wired — e.g., dev-laptop without microVM available), the probe returns `ProbeOutput(confidence="low", warnings=["shell_invocation_trace.sandbox_unavailable"], schema_slice={..., "trace_available": False, "count": 0})` AND the warning ID is **also** in `_WARNING_IDS` (the frozenset gains a third entry `"shell_invocation_trace.sandbox_unavailable"`). The probe does NOT fall back to `subprocess` — that would defeat the threat model. **NB:** `ctx.sandbox_client` is the existing Phase 5-wired attribute on `ProbeContext` per the ADR-0002 §Consequences clause ("no new top-level context attribute is needed beyond what Phase 5 already wires"); if Phase 5 has not wired it, this story's executor surfaces the gap as a blocker, not a TODO.

**Cache discipline (AC-16 + AC-17)**
- [ ] **AC-16** `declared_inputs` includes `"image-digest:<resolved>"` verbatim; the cache key incorporates the resolved base-image digest so a base-image-pin change invalidates the cache without a Dockerfile-byte change. Round-trip test asserts the token is admitted by `cache/keys.py`.
- [ ] **AC-17** No `cache_key(...)` override; defaults to the ABC's content-addressed default.

**Fence + lint (AC-18 through AC-20)**
- [ ] **AC-18** `tests/fence/test_shell_trace_probe_isolation.py` green (live + 12 planted-violation cases + sandbox-spawn-presence). This is the load-bearing fence for the entire phase's threat-model commitment.
- [ ] **AC-19** `make lint-imports` green; no LLM-SDK import path; `mypy --strict plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` clean. **No `Any` in annotations.**
- [ ] **AC-20** Phase 7 ADR-0009 byte-edit allowlist fence green: this story adds files only under `plugins/distroless-migration--node--npm/`, `tests/`, and a fence file; no Phase 0–6.5 file is byte-edited.

## Implementation outline

1. **Pin the integration test first (per Step-7 risk note).** Read `tests/integration/test_sandbox_client_role_probe.py` (landed by S6-03) and copy the exact `SpawnResult` / `ShellTrace` / `SandboxBootError` / `SandboxBuildFailedError` type names. This story's probe writes against those types verbatim.

2. **Net-new files only** — no edits to Phase 0–6.5:
   - `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` — the probe.
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_shell_trace_probe_metadata.py`
   - `tests/unit/plugins/distroless_migration_node_npm/probes/test_shell_trace_probe_behavior.py`
   - `tests/fence/test_shell_trace_probe_isolation.py` — the keystone AST fence.
   - Three fixtures under `tests/fixtures/portfolio/`: `node-distroless-target/Dockerfile` (no shell), `node-with-shell/Dockerfile` (with shell RUN), and a `tests/fixtures/sandbox_stubs/spawn_results.py` module with canned `SpawnResult` instances.

3. **Module-level data in `shell_trace_probe.py`:**
   ```python
   from typing import Final
   import re

   _WARNING_IDS: Final[frozenset[str]] = frozenset({
       "shell_invocation_trace.sandbox_boot_failed",
       "shell_invocation_trace.build_failed",
       "shell_invocation_trace.sandbox_unavailable",
   })
   _WARNING_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
   for _id in _WARNING_IDS:
       if not _WARNING_ID_RE.fullmatch(_id):
           raise AssertionError(f"warning id {_id!r} violates Phase 1 ADR-0007 regex")

   _BUILD_COMMAND: Final[tuple[str, ...]] = ("docker", "buildx", "build", "--target=builder", ".")
   ```

4. **`async def run(self, repo, ctx) -> ProbeOutput`** — the entire body:
   ```python
   async def run(self, repo, ctx):
       t0 = time.perf_counter()
       if ctx.sandbox_client is None:
           return self._unavailable(t0)
       try:
           spawn_result = await ctx.sandbox_client.spawn(
               role=SandboxRole.PROBE,
               workspace=repo.root,
               command=list(_BUILD_COMMAND),
               capture_trace=True,
           )
       except SandboxBootError as exc:
           return self._boot_failed(t0, exc)
       if spawn_result.exit_code != 0:
           return self._build_failed(t0, spawn_result)
       return self._success(t0, spawn_result)
   ```
   - `_unavailable`, `_boot_failed`, `_build_failed`, `_success` are pure helpers in the same module. **No additional `subprocess` call anywhere — the AST fence will catch it.**
   - `_success` extracts `spawn_result.trace.invocations` (list of `ShellInvocation` named-tuples from Phase 5), maps each to the slice's invocation dict, computes `count = len(invocations)`, sets `confidence = "high"`.

5. **The AST isolation fence (`tests/fence/test_shell_trace_probe_isolation.py`):**
   - `class _ForbiddenCallVisitor(ast.NodeVisitor)` with `visit_Call(self, node)`:
     - Walk `node.func` to its dotted-name string (`subprocess.run`, `os.popen`, etc.).
     - Check against a `_FORBIDDEN_DOTTED: Final[frozenset[str]] = frozenset({"subprocess.run", "subprocess.Popen", ...})`.
     - Check `node.keywords` for `keyword(arg="shell", value=Constant(value=True))`.
     - Append to `self.violations`.
   - `class _SandboxSpawnVisitor(ast.NodeVisitor)` — counts attribute-chain calls matching `sandbox_client.spawn`.
   - Helper `_run_walker_against(source: str) -> list[Violation]`.
   - **Parametrized planted-violation test**: for each row in the AC-5 matrix, build a synthetic source string (the original `shell_trace_probe.py` text with the snippet inserted into the `run()` body), run the walker, assert violation count > 0 (or == 0 for the legal rows).
   - **Live-file test**: run the walker against the real file; assert violations == 0.
   - **Sandbox-spawn-presence test**: run `_SandboxSpawnVisitor` against the real file; assert spawn-call count ≥ 1.
   - The fence file's module-level docstring cites ADR-0002, ADR-0005, ADR-0015, and notes "this fence is the structural enforcer of Phase 7's threat-model commitment."

6. **Fixtures** (under `tests/fixtures/`):
   - `portfolio/node-distroless-target/Dockerfile` (FROM gcr.io/distroless/nodejs:18; no RUN with shell).
   - `portfolio/node-with-shell/Dockerfile` (FROM node:18-alpine; multiple `RUN sh -c "..."` lines).
   - `sandbox_stubs/spawn_results.py` — a module with `@dataclass(frozen=True) ShellInvocation`, `SpawnResult`, and three pre-built canned instances (`SUCCESS_NO_SHELL`, `SUCCESS_WITH_SHELL`, `BUILD_FAILED`); used by behavior tests to dependency-inject into the stub `SandboxClient`.

7. **Tests:**
   - Behavior tests use a `_StubSandboxClient` defined inline or in `conftest.py` that implements the same protocol as the real client. AC-10 / AC-11 / AC-12 / AC-14 / AC-15 each parametrize the stub's response.
   - The metadata test uses a fresh `Registry` to avoid pollution.

## TDD plan (red → green → refactor)

**Red 1 (the fence first — the keystone, before the probe body).** Write `tests/fence/test_shell_trace_probe_isolation.py` with the planted-violation parametrize matrix referencing a not-yet-existent `shell_trace_probe.py`. Pytest fails with `FileNotFoundError`.

**Green 1** — create the probe file with an **empty stub** body: `async def run(self, repo, ctx): raise NotImplementedError`. The fence's live-file test now finds zero forbidden calls AND zero `sandbox_client.spawn` calls — AC-7 (sandbox-spawn-presence) fails red. **This is the intended state**: the fence is forcing the implementer to land the sandbox call.

**Red 2** — write `test_shell_trace_probe_metadata.py` (AC-1, AC-2, AC-3). Fails on class attributes / `register_probe` decoration.

**Green 2** — add metadata + `@register_probe(heaviness="heavy", runs_last=True)`. Metadata test green; behavior tests still red.

**Red 3** — write `test_shell_trace_probe_behavior.py::test_count_zero_happy_path` (AC-10). Pytest fails on `NotImplementedError`.

**Green 3** — implement `_success` + the `try/except` skeleton in `run()`. Test green. **Re-run the fence**: now AC-7 (sandbox-spawn-presence) is green AND AC-6 (live-file zero-violation) is green AND all 12 planted-violation rows still red-by-construction.

**Red 4..6** — write the remaining behavior tests (`count > 0`, build-failed, boot-failed, unavailable). Each fails; each prompts one helper.

**Green 4..6** — implement `_unavailable`, `_boot_failed`, `_build_failed`. All behavior tests green.

**Refactor** — extract `_BUILD_COMMAND`, `_WARNING_IDS`, and the slice-builder helpers into module-level. Verify the AST fence still green (refactor cannot introduce subprocess by accident).

**Adversarial planted-violation evidence (Rule 12 fail-loud)** — in a throwaway local commit, paste `subprocess.run(["ls"])` into the live `run()` body. Run `pytest tests/fence/test_shell_trace_probe_isolation.py`. The live-file test fails red. Remove the line. Re-run; green. Record the SHAs in `_attempts/S7-02.md` as a 3-line evidence block (red SHA / green-after-removal SHA / pytest output snippet).

## Files to touch

**New files (no Phase 0–6.5 byte-edits):**
- `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_shell_trace_probe_metadata.py`
- `tests/unit/plugins/distroless_migration_node_npm/probes/test_shell_trace_probe_behavior.py`
- `tests/fence/test_shell_trace_probe_isolation.py`
- `tests/fixtures/portfolio/node-distroless-target/Dockerfile`
- `tests/fixtures/portfolio/node-with-shell/Dockerfile`
- `tests/fixtures/sandbox_stubs/__init__.py`
- `tests/fixtures/sandbox_stubs/spawn_results.py`

**Files NOT touched.** No edits to `src/codegenie/probes/`, `src/codegenie/sandbox/`, `src/codegenie/exec/`, `pyproject.toml`, or `src/codegenie/schema/repo_context.schema.json`. Sub-schema + envelope `$ref` live in S7-03; ALLOWED_BINARIES amendment + dep declaration live in S7-04; loader wiring lives in S8-03.

## Out of scope

- **Sub-schema + envelope `$ref` + golden files** — S7-03 owns these.
- **`ALLOWED_BINARIES` amendment for `docker buildx`** — S7-04 owns `src/codegenie/exec/__init__.py` row #8 of the byte-edit allowlist. **But: this story's stub-based tests do not invoke `docker buildx`** (the stub returns canned `SpawnResult`s); the real `docker buildx` invocation happens at the integration-test layer (S7-05) and in the e2e suite (S12-02). Sequencing: S7-04 SHOULD land before S12-02 actually runs; S7-04 MAY land in the same PR as this story.
- **`SandboxClient.spawn(role=SandboxRole.PROBE)` body / behavior** — Phase 5 owns; S6-02 + S6-03 land it.
- **The `ShellInvocationDeltaGate`** — S10-05 reuses this probe; not in scope here.
- **Plugin loader wiring + `api.py` side-effect imports** — S8-03.
- **Performance benchmark** — S12-05's `tests/perf/test_shell_trace_probe.py` (a `@pytest.mark.bench` warm-cache test); reserved-AC for traceability.

## Notes for the implementer

- **Rule 1 — think before coding.** The AST fence is the single most important file this story produces. If the planted-violation matrix is weak, the fence is decorative. **Write the matrix FIRST, then the probe body second**. The matrix is the contract; the probe body is the implementation.
- **Rule 12 — fail loud.** Every exception path returns a typed `ProbeOutput` with `confidence: "low"` and a known warning ID. Never swallow `SandboxBootError`, `SandboxBuildFailedError`, or `OSError` into "success with empty trace" — that's the exact failure mode ADR-0002 §Consequences calls out (microVM boot failure → `confidence: "low"` with `reason: "build_failed"`). **No `confidence: "high"` ever ships unless trace data was actually captured.**
- **Rule 8 — read before you write.** Read S6-02 + S6-03 first. The `SandboxClient.spawn` signature MUST match what's shipped in `src/codegenie/sandbox/client.py`. Do not invent parameter names. The exception classes (`SandboxBootError`, `SandboxBuildFailedError`) come from Phase 5; if they have different names, mirror Phase 5's vocabulary verbatim — the executor should grep `src/codegenie/sandbox/` for the actual class names before writing `except` clauses.
- **Rule 11 — match conventions.** `tests/fence/test_capability_fence.py` (Phase 3) is the precedent AST-fence style; mirror its module structure. Reuse its `Violation` dataclass shape if it exposes one; otherwise define a local one but match the naming.
- **Open/Closed at the file boundary.** The `_FORBIDDEN_DOTTED` frozenset in the fence is the catalog; adding a new forbidden API (e.g., `httpx.AsyncClient.send`) is **one new row**, not a new `if` branch. The walker iterates the catalog; it does not branch on individual names.
- **The fence's planted-violation evidence is auditable**. Three independent commit SHAs (red / green-after-removal / pytest snippet) go in `_attempts/S7-02.md`. A future engineer reading the audit trail should be able to reproduce the red-green-red cycle in under 60 seconds.
- **`async def run` body must not block the loop.** `SandboxClient.spawn` is async per Phase 5's port contract. The `try/except` wraps an `await`. **Do not** use `subprocess.run` "just to call docker quickly" — the fence will catch it. If you need synchronous helpers (e.g., for slice construction), keep them pure — the helpers are exempt from the sandbox call (the AC-7 check requires ≥ 1 spawn call in the module, not in every helper).
- **The `requires=["base_image"]` value is metadata-only** per Phase 2 02-ADR-0003 (the coordinator doesn't topo-sort by it). The dispatcher uses `runs_last=True` + `heaviness="heavy"` to land this probe at the tail. If the BaseImageProbe slice isn't present at dispatch time, this probe still runs — it doesn't read the slice; it computes its own evidence. The `requires` value is documentation for downstream consumers (the recipe + gates) more than a contract for the coordinator.
- **Token-budget guard (Rule 6).** The fence file is the load-bearing artifact; budget the largest share of session tokens there. The probe body is ≤ 100 LOC. If you find yourself reaching for `# type: ignore` to satisfy `mypy --strict`, STOP — Phase 5's types should already cover the `spawn` return shape; the gap is a Phase 5 contract issue, not a Phase 7 one.
- **Don't add `strace`.** Phase 7 ADR-0015 is explicit. Observation happens via `capture_trace=True` → Phase 5's eBPF host-side view; the trace JSON shape is Phase 5's contract. Do not add a `strace` invocation as "backup."
