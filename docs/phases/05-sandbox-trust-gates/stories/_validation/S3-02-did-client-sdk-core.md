# Validation report: S3-02 — `DockerInDockerClient` SDK core (create/start/exec/inspect/remove)

**Validated:** 2026-05-23
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-02 ships the macOS-default sandbox backend's SDK-only happy path — the second Hexagonal-port + functional-core/imperative-shell consumer after S3-01, and the contract surface every later S3 story (S3-03 build chokepoint, S3-04 copy-out/timeout/OOM, S3-07 integration) extends additively. The draft correctly identified the deliverables (SDK-only `execute()` + `health()` + cleanup discipline + AST fence) and traced cleanly to ADR-0001 / ADR-0004 / ADR-0006, but had **27 findings across all four critic lenses, including twelve block-tier weaknesses** that an executor following the draft literally would have silently violated. The most consequential:

1. Typed `__init__` against a **phantom `EnvAllowlist` class** (same family bug S3-01 caught) — and the parameter was vestigial anyway: env filtering is `SandboxSpecBuilder`'s job (S3-01); by the time `client.execute(spec)` runs, `spec.env` is already filtered. Dropping the parameter eliminated both the phantom class and dead hidden state.
2. Stamped `run_id: str` instead of S1-02 HARDENED's `RunId` NewType — generating the run-id with raw string would have defeated the NewType seam at the GENERATION site, forcing every downstream consumer (S2-01 ledger, S5-02 runner, S7-03 cost, S8-01 CLI) to cast or accept `str`.
3. Listed only 9 of the 13 required `SandboxRun` fields ("On success, SandboxRun carries…") — `extra="forbid"`/`frozen=True` means literal construction is impossible without the full set, but the seven unspecified fields (`spec`, `microvm_seconds`, `image_pull_bytes`, `build_cache_hit`, `trace_path`, `timed_out`, `killed_by_oom`) carry forever-stub values for `backend=="docker_in_docker"` that Phase 13's cost ledger and Phase 11's evidence bundle key on.
4. Canonical Literal spellings (`"docker_in_docker"`, `"shared_kernel"`) asserted by side-effect only — a refactor stamping `"dind"` would be caught at the model layer (ValidationError), indistinguishable from "any Literal would fail".
5. Silently ignored `spec.network`, `spec.egress_allowlist`, `spec.enable_trace`, `spec.copy_in`, `spec.copy_out`, `spec.time_budget_seconds` — Rule 12 "fail loud" violation; a `SandboxSpec(network="scoped", egress_allowlist=…)` would run as `network=none` with no warning.
6. Open free-form `SandboxBackendError.reason` — Phase 13 and Phase 11 key on it; pinned closed `Literal["create_failed","start_failed","stream_failed","wait_failed","remove_failed"]`.
7. APIError tested only at `create`; `start`/`logs`/`wait`/`remove` paths untested (arch §Edge case #1 specifies "APIError during exec").
8. Image-pull failure (`ImageNotFound` per arch §Edge case #2) collapsed into generic `SandboxBackendError`; operator visibility for digest issues lost.
9. `SandboxHealth.confidence` value undefined per branch + `detected_at` silently absent — construction would have raised `ValidationError`.
10. Cleanup-failure path untested — the `finally` clause swallowing exceptions IS the silent-failure mode Rule 12 forbids.
11. Event names as bare strings — bypasses S1-01 HARDENED canonical-table + append-only policy + sorted `__all__` discipline.
12. New runtime deps (`docker`, uuid7 source) absent from `pyproject.toml`; the draft's `uuid_extensions` is the **least maintained** of three PyPI alternatives (`uuid7`, `uuid_utils`, `uuid_extensions`).

Resolution: ~80 numbered ACs across 19 structured sections (was 8 unnumbered checkboxes) plus a **five-test-file TDD plan** (uuid7 helper unit test, module-purity AST walker, pure-helper unit tests, core test suite with parametrized error-grid + cleanup-grid + spec-defer-grid + structlog event-fields assertion, dedicated health test suite with confidence-mapping table + strace-probe caching + Linux-skip + 5 s budget). The two Stage-3 research findings — uuid7 source + Docker SDK type stubs — were consumed inline (vendor a 20-LOC RFC-9562 helper; add `types-docker` to dev deps + a thin `_docker_types.py` TypedDict shim).

## Findings by critic

### Coverage critic

| Severity | Finding | Resolution |
|---|---|---|
| block | `SandboxRun` field set 9/13 — `spec`, `microvm_seconds`, `image_pull_bytes`, `build_cache_hit`, `trace_path`, `timed_out`, `killed_by_oom` unpinned | AC-RUN-FIELDS-1..-17 enumerate every field + S3-02 stub value + Phase pointer for who populates later. |
| block | `run_id` typed `str`, not `RunId` NewType (S1-02 HARDENED AC-6) | AC-RUN-FIELDS-1 + source-level `typing.get_type_hints` pin in pure helper. |
| block | `uuid_extensions` package not in pyproject; vague "stdlib UUID7 helper if vendored" | AC-UUID-1 vendors `_uuid7.py` (≤25 LOC, stdlib only); AC-UUID-2..-4 unit-test. |
| block | `started_at`/`ended_at` types + capture points unpinned | AC-TIME-1 + AC-RUN-FIELDS-5/-6 — both `tzinfo=timezone.utc`, captured immediately before `start()` / after `wait()`; `duration_ms` computed in pure helper. |
| block | Canonical Literal spellings asserted by side-effect only | AC-CANONICAL-1..-4 pin module-level `Final` constants `_BACKEND_NAME`/`_GATE_ISOLATION_CLASS`; AST walk counts string-literal occurrences = 1 each. |
| block | `SandboxHealth.confidence` + `detected_at` absent | AC-HEALTH-1..-5 pin confidence mapping table + UTC `detected_at` + alphabetical `reasons`/`warnings` ordering + namespace regex. |
| block | Phantom `EnvAllowlist` class type | AC-DI-1 forbids any `EnvAllowlist` reference; constructor parameter dropped entirely (dead — S3-01 already filtered env upstream). |
| block | Six `SandboxSpec` fields silently ignored | AC-SPEC-DEFER-1..-7 parametrized fail-loud-or-warn table. |
| block | APIError tested only at `create`; missing `start`/`logs`/`wait` | AC-APIERR-1 parametrized over four phases; AC-ERR-2 mapping table. |
| block | Cleanup-failure path untested | AC-CLEANUP-1..-5 + 12-cell parametrized grid. |
| harden | `logs_dir` path semantics unpinned | AC-LOGS-1 pins resolved absolute path + `mkdir(exist_ok=True)` idempotency. |
| harden | `container.logs(stream=True, demux=True)` `None` halves not pinned | AC-STREAM-1 + AC-STREAM-2 + AC-STREAM-3 (hypothesis property test). |
| harden | Edge case #2 (image-pull failure) not addressed | AC-IMG-1 pins `ImageNotFound` → `SandboxImageUnavailable` distinct subclass. |
| harden | strace SYS_PTRACE health probe expensive + uncached | AC-HEALTH-CACHE-1..-3. |
| harden | `confidence` for `buildx_missing` warning unspecified | Resolved in AC-HEALTH-2 table. |
| harden | structlog event names bare strings | AC-EVT-1..-3 + append-only S1-01 canonical-table extension. |
| harden | Module purity walker missing (every prior phase-5 story shipped one) | AC-PURE-1..-7 ship `tests/sandbox/did/test_client_purity.py`. |
| harden | Coverage floor wording absent | AC-COV-1 + AC-COV-2 ("line ≥ 95% AND branch ≥ 90%"). |
| harden | Registry registration not asserted | AC-REG-1 (`get("docker_in_docker") is DockerInDockerClient`) + AC-REG-2 (`isinstance(…, SandboxClient)`). |
| harden | `network='scoped'` silent downgrade | Resolved by AC-SPEC-DEFER-1. |

### Test-Quality critic

| Severity | Finding | Resolution |
|---|---|---|
| block | Mock target `docker.from_env` fails to import — `docker` SDK absent from pyproject | AC-DEP-1..-3 add runtime + dev deps; `make fence` stays green. |
| block | Canonical Literal not POSITIVELY pinned at call site | AC-CANONICAL-1..-4 + AST walk. |
| block | `stderr.log` never tested with non-empty content | AC-STREAM-2 + parametrized chunk grid + happy-path test fixture uses `(b"", b"oops\n")`. |
| block | Cleanup discipline tested for ONE error path only | AC-CLEANUP-5 12-cell parametrized grid `[start, logs, wait]` × `[RuntimeError, APIError]` × `{success, raises_APIError}`. |
| block | `SandboxRun` field coverage incomplete (mutation `started_at=ended_at=datetime.min` passes) | AC-RUN-FIELDS-* + happy-path assertion of every field. |
| harden | `logs_dir` path discipline not pinned | AC-LOGS-1 absolute path equality. |
| harden | `SandboxBackendError.reason` field not introspected | AC-ERR-1 closed Literal + AC-APIERR-1 asserts `exc.reason` per phase. |
| harden | APIError-during-{start, wait, logs} untested | AC-APIERR-1 parametrized over four phases. |
| harden | `DockerClient(base_url=docker_url)` branch untested | AC-DI-3 dedicated test. |
| harden | structlog event emission unasserted | AC-LOG-2 + AC-EVT-2 use `structlog.testing.capture_logs()`. |
| harden | Successful + warning health paths untested | AC-HEALTH-2 five-scenario parametrized confidence table. |
| harden | WARNING log on cleanup-failure not asserted | AC-CLEANUP-2 + AC-CLEANUP-4. |
| harden | `container.wait()` `Error` key handling untested | AC-WAIT-1 dedicated test. |
| harden | `network_mode="none"` not asserted in create kwargs | AC-EXEC-4 + happy-path test assertion. |
| harden | `spec.network/enable_trace/copy_in/copy_out` silent-ignore | AC-SPEC-DEFER-1..-7 parametrized test. |
| harden | `time_budget_seconds` not honored | AC-SPEC-DEFER-6 surfaces with WARNING event; full enforcement deferred to S3-04 (documented in Notes). |
| harden | strace probe creates+removes container per `health()` call | AC-HEALTH-CACHE-1 memoization + assertion via mock call count. |

### Consistency critic

| Severity | Finding | Resolution |
|---|---|---|
| block | Phantom `EnvAllowlist` — S1-05 ships module-level `filter` function, not a class | Parameter dropped (dead anyway — see Coverage block #7). |
| block | `run_id: str` violates S1-02 HARDENED `RunId` NewType | AC-RUN-FIELDS-1. |
| block | `enable_trace` silently dropped (arch §Component design line 493 requires `trace_path` plumbing through the contract) | AC-SPEC-DEFER-5 emits WARNING + sets `trace_path=None`; explicit no-op until S4-03 owns trace capture. |
| block | Event names bare strings — bypasses S1-01 HARDENED canonical-table + append-only policy | AC-EVT-1..-3; verbs corrected to `STARTED/COMPLETED/FAILED`. |
| block | `docker`, `uuid_extensions` absent from pyproject.toml | AC-DEP-1..-3 + AC-UUID-1 vendored helper (avoids the unmaintained `uuid_extensions`). |
| harden | Module-purity AST walker missing | AC-PURE-1..-7. |
| harden | Canonical Literal spellings not pinned positively at the client layer | AC-CANONICAL-1..-4. |
| harden | Protocol structural conformance not asserted | AC-REG-2 (`isinstance(…, SandboxClient)`). |
| harden | Cleanup discipline under-specified | AC-CLEANUP-1..-5. |
| harden | `health()` strace probe cost not capped | AC-HEALTH-CACHE-3 (≤ 5 s budget). |
| harden | Coverage floor not pinned | AC-COV-1. |
| harden | Undefined `allowlist` pytest fixture | Disappears with the `allowlist` parameter removal. |
| nit | `from __future__ import annotations` discipline | AC-API-4. |
| nit | `SandboxImageUnavailable` collapsed into generic `SandboxBackendError` | AC-IMG-1 preserves distinct subclass. |
| nit | `pytest-mock` named but absent from dev deps | Replaced with `unittest.mock` + `monkeypatch` (codebase convention); `docker_factory` Hexagonal port (AC-DI-2) makes most monkeypatches unnecessary. |

### Design-Patterns critic

| Severity | Finding | Resolution |
|---|---|---|
| block | `allowlist: EnvAllowlist` parameter is dead code AND phantom class | Constructor parameter dropped; `docker_factory: Callable[[str \| None], DockerClient]` injected per S3-01 Hexagonal-port precedent. |
| block | `execute()` is a pure-impure tangled monolith — drops S3-01 HARDENED FCS discipline | AC-FCS-1..-5 enumerate four pure helpers (`_build_container_kwargs`, `_construct_sandbox_run`, `_wrap_api_error`, `_demux_chunks`) + one impure (`_ensure_logs_dir`); thin imperative shell in `execute()`. **Elevated to AC** (rule-of-three reached: S3-01 + S3-02 + S6-01 forward). |
| block | `run_id: str` ignores `RunId` NewType | Covered by Coverage/Consistency block. |
| harden-note | `docker.from_env` constructed inside `__init__`, not injected as port | Elevated to AC-DI-1..-5 (the rule-of-three for DI ports is reached at S6-01; second consumer here cements the pattern). |
| harden-note | Confidence mapping under-specified — non-deterministic mid case | AC-HEALTH-2 deterministic five-row table. |
| harden-note | `self._client` (DockerClient) never closed | Note for the implementer + Phase 6 forward-pointer (Rule 2 wins for S3-02; promote to context manager when a Phase-6 leak is observed). |
| harden-note | `_build_container_kwargs` return type `dict[str, Any]` anaemic | `_docker_types.py` `TypedDict` shim (AC-PURE-5 import allowlist). |
| nit | Warning ID `buildx_missing` violates CLAUDE.md namespace regex | AC-HEALTH-4 enforces `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; renamed to `sandbox.buildx_missing` etc. |
| nit | Log-demux strategy choice in Notes only | Pinned in AC-EXEC-2 (`container.logs(stream=True, demux=True)` mandatory). |
| nit | `gate_isolation_class="shared_kernel"` inline hardcode | Module-level `_GATE_ISOLATION_CLASS: Final` constant (AC-API-5 + AC-CANONICAL-4). |
| elevated to AC | Extension by addition (per CLAUDE.md commitment) | AC-CANONICAL-4 + Files-to-touch enforces no edits to existing files in `sandbox/contract.py` or `sandbox/did/` when Firecracker lands. |
| elevated to AC | Cleanup discipline tightening | AC-CLEANUP-1..-5. |
| pattern-note | Per-platform health probe Strategy | Notes-for-implementer: rule-of-three not reached (one branch); refactor when a third per-platform probe lands. |
| pattern-note | Backend-shape replication seam (`did/`, `firecracker/`, etc.) | Notes-for-implementer: Phase 7 distroless adds by addition (third backend); consider `BaseSandboxClient` mixin if a fourth lands. |
| pattern-note | `SandboxBackendName` NewType promotion | Notes-for-implementer: defer to Phase 7 (third backend triggers rule-of-three). |

## Research briefs

**Two Stage-3 questions surfaced; both answered inline:**

### Research 1 — uuid7 source

- **Question:** Which Python package supplies `uuid7`? The draft's `uuid_extensions` is one of three PyPI alternatives.
- **Sources consulted:** PyPI listings for `uuid7`, `uuid_utils`, `uuid_extensions`; RFC 9562 §5.7 (UUIDv7 spec); Python 3.14 release notes (stdlib `uuid.uuid7()` added per PEP 9562). Repo `pyproject.toml` (current CI matrix is 3.11 × 3.12; no uuid7-related dep present).
- **Recommendation:** **Vendor** a 20-LOC `codegenie/sandbox/did/_uuid7.py` helper using stdlib `secrets` + `time.time_ns()` per RFC 9562 §5.7. Rationale: (a) keeps the `make fence` LLM-SDK closure surface unchanged (no new PyPI dep); (b) avoids choosing between the three packages (the draft chose `uuid_extensions` — the least maintained); (c) stdlib `uuid.uuid7()` lands in 3.14, so when the CI matrix bumps, the helper is a one-line swap. AC-UUID-1..-4 pin the format, version nibble, variant bits, monotonicity, and single call site in `client.py`.

### Research 2 — Docker SDK type stubs

- **Question:** Implementation outline §refactor says "Docker SDK is typed via `docker-stubs`; vendor a `py.typed` shim if missing." Is `docker-stubs` real?
- **Sources consulted:** PyPI listings for `docker-stubs`, `types-docker`, `python-docker-stubs`; docker-py 7.x source (inline annotations partially present).
- **Finding:** `docker-stubs` does **NOT** exist on PyPI. The community stubs package is `types-docker` (`python-docker-stubs` repo). `docker>=7` itself ships partial inline annotations.
- **Recommendation:** Add `types-docker` to dev deps; quarantine remaining `Any` behind `_docker_types.py` (`TypedDict` for `ContainerKwargs`, alias `LogChunk = tuple[bytes | None, bytes | None]`). `mypy --strict src/codegenie/sandbox/did/` passes against the shim, not against the Docker SDK directly. AC-DEP-2 + AC-PURE-5 + AC-PURE-7 pin the boundary.

## Conflict resolutions

- **Coverage vs Design-Patterns on the `allowlist` parameter.** Coverage block #7 said "drop or rename to `filter_fn`"; Design-Patterns block #1 said "drop entirely — vestigial". Both convergent. Resolution: drop. The `docker_factory` Hexagonal port satisfies the DI-port pattern; no env-filter port is needed (S3-01 already filtered).
- **Design-Patterns vs Rule 2 on FCS extraction.** Rule 2 says "three similar lines is better than a premature abstraction." S3-01 was the first FCS consumer; S3-02 is the second; S6-01 (Firecracker) will be the third. Two consumers + one named-forward third meets rule-of-three. Resolution: **elevate from Note to AC** (AC-FCS-1..-5). If S6-01 doesn't replicate the pattern, the synthesizer's bet is wrong and the pattern collapses to single-use; this is judged acceptable because the helper extraction also serves the *mutation-resistance* goal (single source of truth for canonical literals; Adapter for error wrapping; independent unit-testability per Rule 9).
- **Coverage vs Consistency on `enable_trace`.** Coverage block #5 wanted fail-loud on `enable_trace=True`; Consistency block #3 noted arch §Component design line 493 implies `trace_path` plumbing (S4-03's collector concern). Resolution: AC-SPEC-DEFER-5 surfaces with WARNING event + `trace_path=None` on the run — does NOT raise. The `enable_trace` flag is part of the `sandbox_spec_hash` (S3-01); silent ignore on the client side is the right migration story until S4-03 lands the strace-in-VM collector. Rule 12 satisfied by the explicit WARNING.
- **Test-Quality vs Rule 2 on hypothesis adoption.** Test-Quality wanted hypothesis property tests for log-streaming + uuid7 monotonicity. Adding hypothesis is not free, but the codebase already depends on it. Resolution: keep hypothesis — AC-STREAM-3 + AC-UUID-3.

## Edits applied to the story

**Header / status:**
- `Status: Ready` → `Status: Ready (HARDENED 2026-05-23)`.
- `Depends on:` corrected from `S1-05 only` to `S1-01 (errors + logging), S1-02 (Protocol + models + RunId), S1-05 (registry)`.
- `ADRs honored:` annotated each with the specific aspect this story enforces.

**Validation notes (new, ~70 lines):** Twelve block-tier + fifteen harden/nit findings summarized; rationale for every AC change; pattern-lineage callouts (S3-01 → S3-02 → S6-01 for DI ports + FCS).

**Context (light edit):** Added paragraph naming this story as the second concrete consumer of the S3-01 patterns.

**References (expanded):** Added explicit line-number anchors into `phase-arch-design.md`; added prior-HARDENED-report references (S1-02 / S1-05 / S3-01); added `pydantic.model_copy` + RFC 9562 external docs.

**Goal (rewritten):** Now explicitly names the 13-field S1-02 contract + the seven stub-field values + `health()` cached strace probe.

**Acceptance criteria (rewritten):** Was 8 unnumbered checkboxes; now ~80 numbered ACs across 19 sections (A through S):
- A. Public surface + module purity (`__all__`, `__future__`, ADR-citing docstring, module-level `Final` constants for canonical Literals)
- B. Hexagonal DI ports (`docker_factory`)
- C. `execute()` SDK happy path
- D. Full 13+4-field `SandboxRun` coverage with S3-02 stub values + Phase pointers
- E. Canonical Literal spelling — positively pinned via AST walk
- F. Closed-Literal error reason discriminator + per-phase mapping table
- G. Spec-feature fail-loud + deferred-warning policy
- H. `health()` confidence mapping table + alphabetized lists + namespace regex
- I. Cleanup discipline (12-cell grid)
- J. Log streaming — byte-faithful demux (hypothesis property test)
- K. `logs_dir` + `copy_out_root` discipline
- L. Registry round-trip + Protocol structural conformance
- M. uuid7 vendored helper (format, version nibble, monotonicity, single call site)
- N. Dependencies
- O. Module purity (AST walker enforcing import allowlist + canonical-literal counts + zero bare event strings)
- P. Event-name discipline (append-only S1-01 table; `STARTED/COMPLETED/FAILED` verbs)
- Q. Functional core / imperative shell (four pure helpers, each unit-tested)
- R. structlog observability (`bind_contextvars`)
- S. Coverage + tooling gates

**Implementation outline (rewritten):** Now ordered: deps → vendored uuid7 → TypedDict shim → `client.py` (with explicit module-level Final constants, helper ordering, decorator placement) → event constants in `sandbox/logging.py` → test files in red-first order → refactor pass with explicit `mypy --strict` quarantine note.

**TDD plan (rewritten):** Five test files (was one):
1. `test_uuid7.py` — RFC 9562 conformance + monotonicity.
2. `test_client_purity.py` — AST walker for purity (Phase-5 convention).
3. `test_client_helpers.py` — pure-helper unit tests with hypothesis property test.
4. `test_client_core.py` — 12-cell cleanup grid, parametrized APIError grid, parametrized spec-defer grid, full `SandboxRun` field coverage, structlog event-fields assertion, registry round-trip, Protocol conformance.
5. `test_client_health.py` — parametrized confidence-mapping table, strace cache, Linux skip, 5 s budget.

**Files to touch (expanded):** Now lists 13 file entries (was 5) including `pyproject.toml`, `_uuid7.py`, `_docker_types.py`, `sandbox/logging.py` append, five test files.

**Out of scope (corrected):** Renumbered to match arch story IDs (S3-03 = build chokepoint, S3-04 = copy/timeout/OOM, S3-06 = health probe wrapper, S3-07 = integration, S4-03 = trace capture).

**Notes for the implementer (expanded):** Pattern-lineage paragraphs (DI ports, FCS, resource-handle lifecycle); uuid7 vendoring rationale; Docker stubs explanation; sealed error-reason discriminator + how to extend (ADR amendment); event-name verb convention.

## Forward-compat anchor — what's pinned for downstream stories

- **S3-03 (build + iptables chokepoint):** widens `network="scoped"` from AC-SPEC-DEFER-1's `NotImplementedError`; lands `did/build.py` (subprocess) + `did/network_policy.py` (iptables). Inherits the `_BACKEND_NAME` constant + `_wrap_api_error` adapter pattern.
- **S3-04 (copy-out, OOM, timeout):** widens `copy_out != []` (AC-SPEC-DEFER-4), `time_budget_seconds != default` (AC-SPEC-DEFER-6), and populates `image_pull_bytes`, `timed_out`, `killed_by_oom` (currently AC-RUN-FIELDS-10/-15/-16 stub-zeros). Uses `_construct_sandbox_run` helper (single source of truth for those fields).
- **S3-06 (`SandboxHealthProbe`):** consumes `client.health()` from this story; AC-HEALTH-CACHE-3's ≤5 s budget makes the Phase-1 probe wrapper feasible.
- **S3-07 (integration):** removes the mock; runs the real Docker daemon; asserts the same test grid passes byte-equally on live DinD.
- **S6-01 (Firecracker):** third concrete consumer of the Hexagonal DI port + FCS patterns, completing the rule-of-three; ships its own `_BACKEND_NAME = "firecracker"` + `_GATE_ISOLATION_CLASS = "microvm"` Final constants.
- **Phase 7 distroless:** consumes `SandboxRun.gate_isolation_class` for Phase 11 merge-gate decisions; AC-RUN-FIELDS-4's byte-exact `"shared_kernel"` pin is the load-bearing annotation.

## No `RESCUE` findings

The most structural weakness (Block #1 — phantom `EnvAllowlist`) was patchable by elimination + S3-01-style DI-port replacement; downstream stories inherit a clean, documented hand-off. Story remains shippable.
