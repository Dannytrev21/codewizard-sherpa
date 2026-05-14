# Story S5-02 — `RuntimeTraceProbe` — sequential 5-scenario harness + image-digest token

**Step:** Step 5 — Ship Layer C (runtime + container) probes
**Status:** Ready
**Effort:** L
**Depends on:** S5-01 (`ScenarioResult` discriminated union), S1-09 (`ProbeContext.image_digest_resolver`), S1-08 (`@register_probe(heaviness="heavy")`), S1-06 (`docker`, `strace` in `ALLOWED_BINARIES`), S1-07 (`run_external_cli` exists — but Layer C calls `run_allowlisted` *directly*, not via this wrapper), S3-03 (writer chokepoint with `RedactedSlice`), S4-01 (`IndexHealthProbe` consumes `last_traced_image_digest` / `built_image_digest` from this probe's slice — S5-05 wires the freshness check)
**ADRs honored:** 02-ADR-0001 (`docker`/`strace` allowlist), 02-ADR-0003 (`heaviness="heavy"` sort), 02-ADR-0004 (image-digest as `declared_inputs` special token via `ProbeContext.image_digest_resolver`), 02-ADR-0007 (no Plugin Loader, no `plugin.yaml` — the probe is in-tree)

## Context

`RuntimeTraceProbe` is the densest single probe in Phase 2 and the **single most valuable probe for distroless confidence** (`localv2.md` §5.3 C4 — "without this, distroless migration breaks silently in production"). It runs five scenarios (`startup`, `smoke_test`, `healthcheck`, `shutdown`, `error_path`) against the analyzed-repo's container, captures syscalls / loaded libraries / shell invocations / network endpoints via `strace -f -e trace=openat,execve,connect,bind,mmap` (Linux) or deterministically emits `TraceScenarioFailed(StraceUnavailable())` per scenario (macOS — **no sudo prompt, no `dtruss`**, the macOS path is permanent per final-design.md §"Where security/best-practices traded off perf"). The five scenarios serialize through a single asyncio task — **concurrent `docker run` of the same image races resources and confuses trace attribution** (final-design.md §"Components" #6; Implementation risk #7 in final-design.md). Per-scenario timeout 120 s; aggregate 600 s.

The cache-correctness story (02-ADR-0004): a `package.json`-only change with the image rebuilt-and-pushed-with-same-digest must cache-HIT; a `FROM`-line bump or base-image rebuild (new digest) must cache-MISS. The signal is in `declared_inputs` as the special token `image-digest:<resolved>` — Phase 0 `Cache`'s special-token resolver calls `ProbeContext.image_digest_resolver(repo_root) -> str | None`, the **one** Phase 0 contract extension Phase 2 makes (S1-09).

The container-hardening triple `--network=none --cap-drop=ALL --security-opt=no-new-privileges` is **non-negotiable** — `test_adversarial_dockerfile.py` (S5-06) is the proof that a forkbomb/infinite-loop Dockerfile is contained.

## References

- [phase-arch-design.md §"Component design" #6 (`RuntimeTraceProbe`)](../phase-arch-design.md) — the canonical internal-structure prose.
- [phase-arch-design.md §"Edge cases" rows 5, 6, 14](../phase-arch-design.md) — docker-build failure, macOS strace, image-digest resolver returns None.
- [phase-arch-design.md §"Data model" — `ProbeContext` additive field](../phase-arch-design.md) — `image_digest_resolver`.
- [final-design.md §"Components" #6](../final-design.md) — sequential scenarios, p50 ~90 s, image-digest cache key.
- [final-design.md §"Implementation risks" #7](../final-design.md) — "per-scenario sequential `RuntimeTraceProbe` execution can be silently parallelized by a future contributor" — this story's tests are the defense.
- [final-design.md §"Conflict-resolution table" rows 9, 16](../final-design.md) — `cache_key` strategy + cache-key shape.
- [02-ADR-0001](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — `docker`, `strace` in `ALLOWED_BINARIES`; Layer C calls `run_allowlisted` **directly** (not `run_external_cli`).
- [02-ADR-0004](../ADRs/0004-image-digest-as-declared-input-token.md) — image-digest as `declared_inputs` special token; `cache_key()` override refused; resolver is `Optional[Callable]`.
- [High-level-impl.md §"Step 5"](../High-level-impl.md) — Risks specific to Step 5: parallel-scenarios redirect; macOS determinism; container-hardening flags non-negotiable.
- [localv2.md §5.3 C4](../../../localv2.md) — output slice shape (`shared_libs_loaded`, `cert_paths_read`, `files_read_at_runtime`, `shell_invocations`, `network_endpoints_touched`, `trace_coverage_confidence`).
- Phase 0 `run_allowlisted` (`src/codegenie/exec.py`) — direct call site for `docker`/`strace`.
- Phase 0 `Cache` special-token resolver (extended by S1-09 to recognize `image-digest:`).

## Goal

Implement `src/codegenie/probes/layer_c/runtime_trace.py` — a `@register_probe(heaviness="heavy")` probe that builds the analyzed repo's container, runs five scenarios **sequentially** under the container-hardening triple, captures syscalls via `strace -f` (Linux) or emits `StraceUnavailable` per scenario (macOS) deterministically, declares the `image-digest:<resolved>` special token in `declared_inputs`, and emits a `ProbeOutput` whose slice round-trips through the Phase 2 writer chokepoint with `RedactedSlice`. Per-scenario 120 s timeout; aggregate 600 s; `docker build` failure → all five scenarios skip with `confidence="unavailable"`.

## Acceptance criteria

- [ ] `src/codegenie/probes/layer_c/runtime_trace.py` exists; declares `class RuntimeTraceProbe(Probe)` decorated with `@register_probe(heaviness="heavy", runs_last=False)` (S1-08 decorator).
- [ ] `RuntimeTraceProbe.declared_inputs` returns `["Dockerfile", ".codegenie/scenarios.yaml", "image-digest:<resolved>"]` — the literal token string with `<resolved>` placeholder (Phase 0 `Cache`'s special-token resolver expands it via `ctx.image_digest_resolver(repo_root)`). A unit test asserts the literal three-entry shape.
- [ ] `RuntimeTraceProbe.cache_strategy` is **NOT** `"none"` — the probe's whole point is to cache against image-digest equality (`cache_strategy="none"` is reserved for B2, S4-01).
- [ ] Reads `.codegenie/scenarios.yaml` via Phase 1 `safe_yaml.load` chokepoint; Pydantic-validates against an internal `ScenariosConfig` model with required field `scenarios: list[ScenarioSpec]`; falls back to a literal `_DEFAULT_SCENARIOS = ["startup", "smoke_test", "healthcheck", "shutdown", "error_path"]` when the file is absent (file present but malformed → `ScannerFailed` equivalent for the probe envelope; not silent-fallback).
- [ ] **Sequential per-scenario execution** — verified by `tests/unit/probes/layer_c/test_runtime_trace.py::test_concurrent_task_count_le_one`: while the probe runs, an asyncio.Event-driven instrumentation captures `len([t for t in asyncio.all_tasks() if t.get_name().startswith("runtime_trace_scenario_")]) <= 1` at every observation point (≥ 10 sampled points spread across the run). The assertion is on **observed task count**, not absence of `asyncio.gather` (which a future contributor could re-introduce subtly).
- [ ] Per scenario: `docker build` → `docker run --network=none --cap-drop=ALL --security-opt=no-new-privileges -- <image> <scenario-command>` + `strace -f -e trace=openat,execve,connect,bind,mmap` (Linux). The three hardening flags are passed as separate argv tokens (no string-concat); a unit test mocks `run_allowlisted` and asserts the argv contains all three flag tokens in any order plus the explicit `--`.
- [ ] **All `docker` and `strace` calls route through `run_allowlisted` DIRECTLY** — not `run_external_cli`. A grep test (`tests/unit/probes/layer_c/test_runtime_trace_no_external_cli_wrap.py`) asserts the probe's source has zero `run_external_cli` references and ≥ 1 `run_allowlisted` reference (02-ADR-0001 + final-design.md §"Departures" reaffirmation).
- [ ] Per-scenario `asyncio.wait_for(..., timeout=120)`; aggregate guard `asyncio.wait_for(..., timeout=600)` around the for-loop. Both timeouts are constants exported as `_PER_SCENARIO_TIMEOUT_S = 120` and `_AGGREGATE_TIMEOUT_S = 600` (test imports them and asserts the values; a deliberate edit to `60`/`300` flips the test red).
- [ ] **macOS path is deterministic — no sudo prompt**: on `sys.platform == "darwin"` (or `os.uname().sysname == "Darwin"`), the probe **does not invoke `strace` or `dtruss`**; each scenario short-circuits to `TraceScenarioFailed(scenario_name=..., reason=StraceUnavailable())`. Unit test: under monkey-patched `sys.platform = "darwin"`, the probe's run completes without any `run_allowlisted("strace", ...)` invocation and without spawning a subprocess that could prompt for sudo (verified by mock-spy on `run_allowlisted` rejecting any `"strace"` or `"sudo"` argv).
- [ ] `docker build` failure (non-zero exit) → **all five scenarios skip** with `TraceScenarioSkipped(reason=ImageBuildUnavailable(...))`; the probe envelope's `confidence` is `"unavailable"`; the slice's `built_image_digest` is `None`; the slice's `last_traced_image_digest` is `None`; `IndexHealthProbe` (S4-01) will read these and emit `IndexFreshness.Stale(IndexerError(message="upstream_runtime_trace_unavailable"))` — covered by a fixture test that constructs the slice and roundtrips through B2's freshness loop (the S4-01 freshness loop call is exercised in a small integration test).
- [ ] **Image-digest cache HIT skips scenarios.** A test exercises Phase 0 `Cache` with a stubbed `image_digest_resolver` returning a fixed digest; running the probe twice with the same `(Dockerfile, scenarios.yaml, image-digest)` tuple results in the second run hitting cache and the probe's `run()` is **not entered for the scenarios block** (mock-spy on the `_execute_scenario` coroutine asserts it is called five times on the first run and zero times on the second).
- [ ] **`image_digest_resolver` returns `None`** (no built image yet) → the probe emits `confidence="unavailable"`, slice carries `built_image_digest=None`, scenarios are all skipped with `TraceScenarioSkipped(reason=ImageDigestUnresolved())`, cache key falls back to file globs only (phase-arch-design.md §"Edge cases" row 14 + 02-ADR-0004 §Consequences).
- [ ] **`image_digest_resolver` is `None`** on `ProbeContext` (operator never bound one) → identical behavior to "resolver returned None"; the probe never raises. Covered by a separate unit test (the two None paths are *both* valid and the probe distinguishes them only in the structured log field `image_digest_unresolved_reason: Literal["resolver_unbound", "resolver_returned_none"]`).
- [ ] Output slice schema matches the relevant subset of `localv2.md` §5.3 C4: `artifact_uri`, `per_scenario_artifacts: dict[str, Path | None]`, `scenarios_run: list[str]`, `scenarios_failed: list[str]`, `binaries_executed: list[str]`, `shared_libs_loaded: list[str]`, `cert_paths_read: list[str]`, `files_read_at_runtime: {summary, full_list_uri}`, `shell_invocations: int`, `network_endpoints_touched: {outbound, inbound}`, `built_image_digest: str | None`, `last_traced_image_digest: str | None`, `trace_coverage_confidence: Literal["high", "medium", "low", "unavailable"]`. Sub-schema lands as part of S5-03 / S5-04 (`src/codegenie/schema/probes/layer_c/`); this story emits the dict shape that the sub-schema validates.
- [ ] `trace_coverage_confidence` derivation: 5/5 scenarios completed → `"high"`; smoke-only or 2–4 completed → `"medium"`; startup-only → `"low"`; 0 completed → `"unavailable"` (matches `localv2.md` §5.3 C4).
- [ ] Slice flows through the writer chokepoint as `RedactedSlice` (S3-02 / S3-03); a test asserts `secrets_redacted_count == 0` for a clean fixture and `>= 1` for a fixture whose smoke-test command echoes an AWS-format key (the `SecretRedactor` from S3-01 must catch it on the runtime trace path).
- [ ] Structured log fields emitted at least once per probe run: `probe.runtime_trace.dispatch`, `probe.runtime_trace.scenario_started` (per scenario), `probe.runtime_trace.scenario_finished` (per scenario, includes `wall_clock_ms` and the `kind` of the `ScenarioResult`), `probe.runtime_trace.image_digest_resolved` (or `…unresolved`), `probe.runtime_trace.cache_hit` (when applicable), `probe.runtime_trace.finish`.
- [ ] `mypy --strict` clean; `mypy --warn-unreachable` per-module override applies (S1-11 list — if not, this story extends `pyproject.toml`; surface in "Notes for the implementer").
- [ ] Phase 0 `fence` job stays green — no `httpx`, `requests`, `socket`, `anthropic`, `openai`, `langgraph` imports added.
- [ ] `forbidden-patterns` pre-commit stays green — no `model_construct`; no direct `subprocess.run` / `asyncio.create_subprocess_exec` (everything goes through `run_allowlisted`).

## Implementation outline

1. Define `ScenarioSpec` Pydantic model — required `name: str`, optional `command: list[str]` (argv to pass to `docker run`), optional `expected_exit_code: int = 0`. Define `ScenariosConfig(scenarios: list[ScenarioSpec])`.
2. Define `_DEFAULT_SCENARIOS: list[ScenarioSpec]` with the five canonical names; each default carries a minimal `command` argv (e.g., `["sh", "-c", "exit 0"]` for `startup`; smoke/healthcheck/shutdown/error_path defaults follow the localv2.md §5.3 C4 prose).
3. Implement `RuntimeTraceProbe.declared_inputs(self, repo_root: Path) -> list[str]` returning the literal three-entry list (the `image-digest:<resolved>` form is the **literal** string Phase 0 `Cache` recognizes; the resolver substitution happens inside Phase 0 `Cache._resolve_declared_inputs`, not here).
4. Implement `RuntimeTraceProbe.run(self, snapshot: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`:
   - (a) Resolve `image_digest = ctx.image_digest_resolver(snapshot.root) if ctx.image_digest_resolver else None`; structured-log the outcome.
   - (b) If `image_digest is None`: short-circuit → emit `ProbeOutput` with `scenarios_run=[]`, `scenarios_failed=[]`, all-skipped per-scenario list, `built_image_digest=None`, `confidence="unavailable"`.
   - (c) Else: load `scenarios.yaml` (Pydantic-validate); fall back to `_DEFAULT_SCENARIOS` on absence.
   - (d) Detect platform: `if sys.platform != "linux"`: emit one `TraceScenarioFailed(reason=StraceUnavailable())` per scenario; do **not** call `run_allowlisted`.
   - (e) Else (Linux): wrap the for-loop in `asyncio.wait_for(_run_all_scenarios(...), timeout=_AGGREGATE_TIMEOUT_S)`; inside `_run_all_scenarios`, iterate scenarios *with explicit `await` between iterations* (no `asyncio.gather`, no `TaskGroup`). For each scenario: `await asyncio.wait_for(_execute_scenario(...), timeout=_PER_SCENARIO_TIMEOUT_S)`. On `TimeoutError`: emit `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`.
   - (f) `_execute_scenario` calls `run_allowlisted("docker", ["build", ...])` first (only on the first scenario; subsequent scenarios reuse the built image — track via instance-local `self._image_built: bool`); then `run_allowlisted("strace", ["-f", "-e", "trace=openat,execve,connect,bind,mmap", "--", "docker", "run", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges", image_ref, *scenario.command])`. The `docker build` shape: `run_allowlisted("docker", ["build", "-t", "codegenie-trace:<short-digest>", "-f", "Dockerfile", str(repo_root)])`. Capture stdout/stderr; parse strace output into the slice fields.
   - (g) Aggregate per-scenario `ScenarioResult`s into the slice; derive `trace_coverage_confidence`.
5. Implement strace-output parser as a small pure function `_parse_strace_lines(stream: Iterable[str]) -> ParsedTrace` returning `binaries_executed`, `shared_libs_loaded`, `cert_paths_read`, `files_read_at_runtime`, `shell_invocations`, `network_endpoints_touched`. Pure function — unit-tested against a fixture strace output snippet under `tests/fixtures/strace/`.
6. Write artifacts (one `.strace` per scenario + a merged `runtime-trace.json`) under `.codegenie/context/raw/`; the slice carries `artifact_uri` and `per_scenario_artifacts`.
7. Slice flows back to the coordinator as `ProbeOutput.schema_slice: dict[str, JSONValue]`; the writer chokepoint (S3-03) wraps it in `RedactedSlice` via `SecretRedactor`.
8. Register `@register_index_freshness_check("runtime_trace")` — **deferred to S5-05**; this story does not register it.

## TDD plan — red / green / refactor

**Red:**

1. `test_register_probe_heaviness_heavy` — registry introspection asserts `RuntimeTraceProbe` is registered with `heaviness == "heavy"` and `runs_last is False`. Initial state: module import fails.
2. `test_declared_inputs_literal_three_entries` — asserts `declared_inputs(repo_root) == ["Dockerfile", ".codegenie/scenarios.yaml", "image-digest:<resolved>"]`. Failure mode: order or count or token-shape drift.
3. `test_concurrent_task_count_le_one` — instrument the probe via a `_per_scenario_started_event` test hook; observe `asyncio.all_tasks()` filtered by name prefix `runtime_trace_scenario_` at ≥ 10 sampled points across the run; assert `<= 1` at every observation. **This is the load-bearing test** for final-design.md Implementation risk #7.
4. `test_macos_no_strace_invocation` — monkeypatch `sys.platform` to `"darwin"`; mock `run_allowlisted` with a spy that raises on `argv[0] in {"strace", "sudo", "dtruss"}`; run the probe; assert no spy raise occurred; assert every scenario in the output slice is `TraceScenarioFailed(reason=StraceUnavailable())`.
5. `test_macos_no_tty_interaction` — mock `run_allowlisted` to fail-loud if `stdin` is anything other than `DEVNULL`; run on macOS-platform path; assert no failure (the probe never opens a TTY).
6. `test_hardening_flags_in_argv` — mock `run_allowlisted` to capture argv; run a single-scenario fixture on Linux-platform path; assert the captured argv for the `docker run` segment contains all three of `--network=none`, `--cap-drop=ALL`, `--security-opt=no-new-privileges` (order-independent set membership). Mutation test: deleting `--network=none` from the source flips this red.
7. `test_no_run_external_cli_in_source` — open `src/codegenie/probes/layer_c/runtime_trace.py` and `assert "run_external_cli" not in source and "run_allowlisted" in source`.
8. `test_per_scenario_timeout_120s_constant` and `test_aggregate_timeout_600s_constant` — import the module-level constants and assert their values.
9. `test_per_scenario_timeout_triggers_failed` — mock `_execute_scenario` to sleep `200` real-time-mocked seconds (using `asyncio` time mock); assert the result is `TraceScenarioFailed(reason=ScenarioTimeout(seconds=120))`; assert the *aggregate* loop did not also time out.
10. `test_aggregate_timeout_triggers_failed_all_remaining` — mock the first scenario to consume 540 s (~just under 600 s); subsequent scenarios should not start; the slice should reflect 1 completed + 4 `TraceScenarioSkipped` or 1 completed + 4 `TraceScenarioFailed(ScenarioTimeout)` (pick one and document — recommendation: the aggregate-timeout path emits `Skipped(ScenarioTimeout())` for not-yet-started scenarios because they technically never ran).
11. `test_docker_build_failure_all_skipped` — mock `run_allowlisted` to return non-zero exit for the `docker build` argv; assert all five `ScenarioResult` are `Skipped(ImageBuildUnavailable(...))`; assert envelope `confidence == "unavailable"`.
12. `test_image_digest_resolver_returns_none_skipped` — bind a resolver returning `None`; assert all-skipped with `Skipped(ImageDigestUnresolved())`; assert `built_image_digest is None` in slice.
13. `test_image_digest_resolver_unbound_skipped` — `ctx.image_digest_resolver is None`; same envelope shape; assert structured-log field `image_digest_unresolved_reason == "resolver_unbound"`.
14. `test_cache_hit_skips_scenarios` — run twice with the same fixture + same resolver returning the same digest; spy on `_execute_scenario`; assert first-run call count == 5, second-run call count == 0; assert second-run slice JSON byte-identical to first-run (modulo `gathered_at` / wall-clock fields excluded).
15. `test_scenarios_yaml_pydantic_validation` — present a malformed `scenarios.yaml`; assert the envelope reports a load error (not silent default-fallback); a missing file does default-fallback.
16. `test_trace_coverage_confidence_derivation` — table-driven over `(n_completed: 5..0) -> ("high","medium","medium","medium","low","unavailable")` matching the documented derivation.
17. `test_writer_chokepoint_secret_redaction` — fixture whose smoke-test command echoes `AKIA0123456789ABCDEF`; run the probe; capture the writer's `RedactedSlice`; assert `findings_count >= 1` and the plaintext does not appear in any `.codegenie/context/raw/` output file (`grep`-walk asserts plaintext == 0 occurrences).

**Green:**

1. Implement `RuntimeTraceProbe` per the implementation outline.
2. Implement `_parse_strace_lines` against a fixture strace snippet under `tests/fixtures/strace/`.
3. Make all red tests pass; do not introduce mocks the test didn't already expect.

**Refactor:**

1. Extract per-scenario execution into `_execute_scenario(snapshot, ctx, scenario, image_ref)` — pure async function; testable in isolation.
2. Extract strace argv builder + docker run argv builder into named factory functions (`_build_strace_argv`, `_build_docker_run_argv`); each is unit-testable as a pure function and the "hardening flags present" assertion runs against the builder, not against a mocked subprocess.
3. Confirm the structured-log fields land via `structlog`'s context binding (`logger.bind(probe="runtime_trace", scenario=name)`); a single dispatch per scenario carries the binding.
4. Confirm `__all__` exports only `RuntimeTraceProbe`; internal builders are module-private (leading underscore).

## Files to touch

- **New:** `src/codegenie/probes/layer_c/runtime_trace.py`, `tests/fixtures/strace/<minimal>.strace`, `tests/fixtures/scenarios/{empty.yaml,malformed.yaml,three_only.yaml}`.
- **New tests:** `tests/unit/probes/layer_c/test_runtime_trace.py` (covers AC tests 1–17 above), `tests/unit/probes/layer_c/test_runtime_trace_no_external_cli_wrap.py` (the source-grep test).
- **Existing — read-only references:** `src/codegenie/probes/_shared/scanner_outcome.py` (S5-01), `src/codegenie/probes/layer_c/scenario_result.py` (S5-01), `src/codegenie/probes/base.py` (read `ProbeContext.image_digest_resolver` after S1-09), `src/codegenie/exec.py` (`run_allowlisted` direct caller — S1-06 lands `docker`/`strace` in `ALLOWED_BINARIES`), `src/codegenie/output/writer.py` (the writer's `RedactedSlice` signature — S3-03).
- **Possibly extend:** `pyproject.toml` `[tool.mypy]` per-module overrides if S1-11 didn't already pin `codegenie.probes.layer_c.runtime_trace`.

## Out of scope

- The freshness-check registration `@register_index_freshness_check("runtime_trace")` — **S5-05** lands it. This story's probe emits the slice fields B2 reads; S5-05 wires the freshness function.
- The `image_digest_drift` adversarial test — **S5-05**.
- The `adversarial_dockerfile` container-hardening test — **S5-06** (this story makes the hardening flags present and tested at unit level; S5-06 proves the flags actually contain a forkbomb).
- `DockerfileProbe`, `EntrypointProbe`, `ShellUsageProbe`, `CertificateProbe` — **S5-03**.
- `SyftProbe`, `GrypeProbe` — **S5-04** (which `requires=["runtime_trace"]` per the dispatch-ordering ADR — see S5-04's `requires` mechanism).
- Sub-schema `src/codegenie/schema/probes/layer_c/runtime_trace.schema.json` — **S5-03** lands it (this story emits the dict shape; S5-03's sub-schema validates it).
- Bench (cold p50 ~90 s) — **S8-03** lands the canary; this story's unit tests do **not** exercise wall-clock targets.

## Notes for the implementer

- **The single most load-bearing test in this story is `test_concurrent_task_count_le_one`.** It encodes final-design.md Implementation risk #7 — "per-scenario sequential `RuntimeTraceProbe` execution can be silently parallelized by a future contributor." A future PR that introduces `asyncio.gather` over scenarios will flip this red, and the test message should point to final-design.md §"Tradeoffs accepted" + this ADR. Do not weaken the assertion to "no `gather` literal in source" — that is bypassable. Assert on **observed task count**, not on syntax.
- **The macOS path is permanent.** Resist the urge to add a "TODO: implement dtruss with sudo" comment. The synthesis explicitly chose `StraceUnavailable` over a sudo-prompting dtruss path because the sudo prompt would break determinism and CI is Linux-canonical. The macOS path emits the typed failure so S5-05's freshness check + S8-01's renderer surface it loudly.
- **Layer C does NOT use `run_external_cli`.** This is 02-ADR-0001 (final-design.md §"Departures" #1). The `run_external_cli` wrapper (S1-07) adds `bubblewrap --unshare-net` and env-strip for Layer B/G scanners. For Layer C the equivalent isolation is the `--network=none --cap-drop=ALL --security-opt=no-new-privileges` flags constructed at the call site — different mechanism, same outcome. Wrapping `docker` inside `bubblewrap --unshare-net` would prevent `docker build` from working (Docker daemon socket access). The `test_no_run_external_cli_in_source` smoke test is the structural enforcement.
- **`image_digest_resolver` semantics.** The resolver is allowed to return `None` (not-yet-built image) and is allowed to be `None` itself (operator didn't bind one). Both paths are "not an error" — the probe degrades gracefully to `confidence="unavailable"`. The distinguishing structured-log field (`image_digest_unresolved_reason`) is for operator debuggability; both paths produce the same slice shape (`built_image_digest=None`).
- **Cache HIT semantics.** When Phase 0 `Cache` returns a HIT (resolved `image-digest:<digest>` token matches cached token), the probe's `run()` should still be entered, but the scenarios block should not execute — the cached slice is returned. The "second-run `_execute_scenario` call count == 0" assertion guards this. If you find yourself touching `Cache` to make this work, stop — Phase 0 `Cache` already handles HIT short-circuiting; this probe just needs to emit `declared_inputs` correctly and accept the cached envelope.
- **Aggregate timeout semantics.** When the aggregate 600 s budget expires mid-scenario, the not-yet-started scenarios get `TraceScenarioSkipped(ScenarioTimeout())`. The currently-executing scenario, on `asyncio.CancelledError`, gets `TraceScenarioFailed(ScenarioTimeout(seconds=<remaining>))`. Document this in the module docstring so a future maintainer doesn't conflate the two paths.
- **`docker build` is invoked once.** Subsequent scenarios reuse the built image (`-t codegenie-trace:<digest>` tag). The instance-local `self._image_built` flag is the simplest shape; resist building per-scenario.
- **No `pytest-xdist`** — Phase 2 ADR-0009 vetoed parallel test execution. Even this probe's unit tests are serial. Wall-clock cost is paid in CI's `unit` job budget (≤ 90 s per Step 5 README; verify in S8-03's bench canary).
- **The slice's `built_image_digest` and `last_traced_image_digest`** are what S4-01's `IndexHealthProbe` reads. Today they are identical when a fresh trace succeeds; S5-05 introduces the `image_digest_drift` adversarial that mutates them apart so B2 emits `Stale(DigestMismatch(...))`.
- **Strace-parsing is pure.** Test it as a pure function over fixture lines. Do not couple it to subprocess invocation. A future maintainer should be able to grep "what does strace output get parsed to?" and find one named function.
- **Open question — `RuntimeTraceProbe` against an already-distroless base image** (Phase 7 forward-looking): the `distroless-target` fixture (S7-01) exercises this. Today: if `strace` cannot attach (distroless image has no `/proc/self/exe` symlink for the host strace to read against), we emit `TraceScenarioFailed(reason=StraceUnavailable())` per scenario — same shape as macOS — and surface it via structured log. Document this in the module docstring as an open path that S7-01 stresses.
- **Open question — `scenarios.yaml` schema evolution.** The five default names are scoped here; adding a sixth scenario is a `scenarios.yaml` edit by the operator, not a code edit. If `localv2.md` ever names a sixth canonical scenario, it lands as a `_DEFAULT_SCENARIOS` extension, not as a new field on the slice (the slice already accepts `list[str]` for scenario names).
- **mypy enforcement.** The `match` on `ScenarioResult` happens inside `_aggregate_scenarios(results: list[ScenarioResult]) -> SliceFields` — exhaustive over `kind` variants with `assert_never`. The S1-11 `--warn-unreachable` per-module override should cover `codegenie.probes.layer_c.runtime_trace`; if it doesn't, extend `pyproject.toml` in this story's PR and note the diff so S1-11's "Consequences" can be reviewed.
