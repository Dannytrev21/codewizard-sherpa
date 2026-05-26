# Validation report — Story S8-02 — `codegenie remediate` flags `--sandbox-backend`, `--max-attempts-override`, `--allow-test-network` + `--operator-ack`

**Story:** [`../S8-02-remediate-flags-operator-ack.md`](../S8-02-remediate-flags-operator-ack.md)
**Validated:** 2026-05-26
**Validator:** `phase-story-validator` (single-agent inline mode)
**Validator agent run:** automated (`story-validation-corrector` scheduled task)
**Verdict:** **HARDENED**

## Summary

S8-02 wires three new flags onto `codegenie remediate` (the Phase-3-shipped CLI command from S6-05) and the one explicit safety interlock that protects the production-ADR-0014 three-retry default. The draft's *direction* is sound — right flags, right Click-validator exit-code, right "one audit event per invocation" framing — but it was authored before nine sibling stories in Phase 5 reached HARDENED, and every block-tier finding traces to one of five root causes:

1. **The story was written before S1-01 HARDENED the event-constants kernel.** S1-01 AC line 73 already ships `EVENT_GATE_ATTEMPTS_OVERRIDE: Final[str] = "gate.attempts_override"` in `src/codegenie/gates/logging.py` (NOT `src/codegenie/audit/events.py`, which does not exist). The draft's AC-9 ("Audit event constant `gate.attempts_override` is defined in `src/codegenie/audit/events.py`") would create a duplicate / conflicting constant. Per S1-01 Validation note §"Adding a new event constant": NEVER rename or re-value an existing constant. Fix: AC-EVT-* import the existing constant; do not redefine.
2. **The story was written before S1-02 / S1-04 / S3-01 HARDENED on frozen Pydantic semantics.** `SandboxSpec` is `frozen=True, extra="forbid"` (S1-02 + S3-01 AC-FROZEN-1..-3) and carries a byte-stable `sandbox_spec_hash` computed by `SandboxSpecBuilder.for_gate`. The draft's outline step 4 says "extend each `SandboxSpec.egress_allowlist` with the policy-YAML extras" — a frozen model rejects in-place mutation, and even via `model_copy` the post-widening hash drifts from the catalog-derived hash. `RetryPolicy.max_attempts` is `AttemptNumber` (bounded 1..1024 per S1-04 AC-I-1) on a frozen model. `GateContext` is frozen with a closed field set `{worktree, advisory, recipe, transform_output, prior_attempts, workflow_id, run_id}` per S1-04 AC-G; the draft's outline step 4 says "set a flag on `GateContext` so `collect_trace_signal` knows to keep `new_endpoints` informational" — `extra="forbid"` would reject the new field, and amending S1-04 is out-of-scope for S8-02. Fix: widening is owned by `SandboxSpecBuilder` (DI port at construction time); the trace collector receives `allow_test_network` via the orchestrator-resolved `RemediationSettings`, not via `GateContext`.
3. **The story was written before S1-05 HARDENED the backend registry.** S1-05 AC-BR-11 ships `get_backend(name) -> SandboxClient` keyed on `Literal["docker_in_docker", "firecracker"]` (per S1-02 AC-7b). The CLI's `--sandbox-backend did` requires a `did → docker_in_docker` name mapping; the draft never declares it. Without the mapping, `get_backend("did")` raises `SandboxBackendInvalid`. Fix: `_CLI_TO_REGISTRY_BACKEND_NAME` `Final[Mapping[str, Literal[...]]]` in `cli/_options.py` (reused with S8-01's `_CLI_BACKEND_NAMES`); `auto` calls `auto_detect()`.
4. **The story was written before S3-05 HARDENED the policy YAML's exact field set.** `tools/policy/sandbox-policy.yaml` is digest-pinned (ADR-0013) and per S3-05 AC-GOLDEN-2 + arch §Data model lines 810–824 has exactly three top-level keys: `lockfile`, `runtime_trace`, `test_inventory`. The draft's AC-5 refers to `tools/policy/sandbox-policy.yaml#test_network_extra_hosts` — a key that does not exist. The story must own the additive YAML extension + the BLAKE3 re-digest, or the executor will hit a `KeyError` at runtime. Fix: AC-POLICY-* — append `test_network.extra_hosts: list[str] = []` to the policy YAML; re-pin `tools/digests.yaml#sandbox.policy_yaml` (BLAKE3-128 hex); update `tests/golden/sandbox-policy.yaml.template` byte-for-byte (S3-05 AC-GOLDEN-2 chain).
5. **The story was written before S5-02 HARDENED the async `GateRunner` and before S7-04 HARDENED `cli/exit_codes.py`.** `GateRunner.__init__` is keyword-only with 6 deps (+ S7-03's additive 7th `cost`); a `max_attempts` override must travel through the per-gate `RetryPolicy` via `model_copy(update={"max_attempts": AttemptNumber(...)})`, not by mutating the runner. Exit-code constants live in `cli/exit_codes.py` (S7-04); the draft uses Click's default `UsageError` (exit 2) — correct for the ack-rejection path — but the cross-phase coordination needs an additive `EXIT_OPERATOR_ACK_REQUIRED = 2` alias or explicit reuse of `EXIT_USAGE`. The story must also reuse S7-04's `cli/_errors.py` registry-pattern `EXIT_CODE_FOR` for any non-Click exceptions raised at the validator boundary. Fix: AC-EXIT-* — explicit reuse, no new exit codes.

The HARDENED story carries these changes plus tightening on the "single event per invocation across N gates" contradiction (the draft's event field `gate_id: str` is single-valued; the new shape is a structured `affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...]`), the "raises only" semantics ambiguity (override is `max(catalog_default, override_value)` per gate, not blanket-replace), the operator-ack invocation-only-rule (env-var bypass forbidden — ADR-0014 humans-always-merge), the IntRange upper-bound miss (1024 per `AttemptNumber`), and the structlog-vs-imagined-`codegenie.audit.emit` test-stub bug.

Counting: **41 findings — 12 block-tier, 23 harden-tier, 6 nit-tier.** The blocks would have produced reachable structural bugs the executor's validator would have missed: `ImportError` on `codegenie.audit.events` (module doesn't exist); `SandboxBackendInvalid("did not registered")` from `get_backend("did")`; `ValidationError` on `setattr(spec, "egress_allowlist", ...)` (frozen model); `KeyError("test_network_extra_hosts")` reading the policy YAML; `ValidationError` on `GateContext(..., allow_test_network=True)` (extra="forbid"); `ValueError` on `AttemptNumber(9999)` (1024 bound); a "single event per invocation" pinky-swear with no test, where an implementer emits N events for N gates; an env-var `CODEGENIE_OPERATOR_ACK=1` bypass that lets the override fire without explicit operator consent (security-relevant per ADR-0014); a `monkeypatch.setattr("codegenie.audit.emit", ...)` test stub that patches nothing (the real emit path is `structlog.get_logger().info(EVENT_*, **fields)`); a `monkeypatch.setattr("codegenie.orchestrator.run", ...)` stub against a non-existent module (orchestrator lives at `codegenie.transforms.orchestrator.RemediationOrchestrator`); and a `gate.attempts_override` event emitted on the FAILURE path (missing-ack) because no AC pinned the negative.

The hardens close mutation-resistance gaps (the "no event on failure path" path is now witnessed by AC-EVT-NEG-1; the IntRange max bound is witnessed by `9999` rejection; the env-var bypass is witnessed by AC-INV-1; the per-gate `model_copy` is witnessed by an AST scan AC-COPY-1), surface design-pattern opportunities as observable ACs (the `_CLI_TO_REGISTRY_BACKEND_NAME` mapping is the Open/Closed seam for Phase 7 chainguard; the `GateAttemptsOverrideEvent` Pydantic value type makes illegal log payloads unrepresentable; the `_require_operator_ack` pure helper is the functional-core / imperative-shell split established by S2-01 / S3-01 / S5-02 / S7-04), and tie loose ends to CLAUDE.md commitments (event names live in `gates/logging.py`; exit codes live in `cli/exit_codes.py`; backend names live in `cli/_options.py`; no bare literals; fence test under `tests/fence/`).

**No `RESCUE`-tier findings.** The goal traces cleanly to `phase-arch-design.md §CLI surface (codegenie sandbox)` lines 613–625 + ADRs 0004/0009/0012/0013 + production ADR-0014; every gap was patchable by pinning against HARDENED siblings (S1-01, S1-02, S1-04, S1-05, S3-01, S3-05, S5-02, S7-04, S8-01) and Phase 3 / Phase 5 precedents. **No Stage-3 research needed** — every finding was answerable from in-repo HARDENED sources, the Click documentation, and the Pydantic `BaseSettings` precedence already pinned by arch §839.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Wire `--sandbox-backend {did,firecracker,auto}`, `--max-attempts-override <int>` (gated by `--operator-ack`), and `--allow-test-network` onto `codegenie remediate`, with a Click validator that exits 2 on missing acknowledgement and a single `gate.attempts_override` audit event emitted exactly once per override invocation.
- **Non-goals (Out-of-scope, hardened):** The full E2E retry-2-recover run (S8-03); ADR audit + coverage closure (S8-04); a `--max-attempts-override` that lowers the cap; persisting `--operator-ack` across invocations.

### Phase 5 exit criteria touched

- **Step 8 done-criteria (`High-level-impl.md §Step 8` lines 215, 225):** `codegenie remediate` flags wired; `--max-attempts-override 5` without `--operator-ack` exits Click 2.
- **`phase-arch-design.md §CLI surface (codegenie sandbox)` (lines 620, 625):** flags + Click validator + audit event semantics.
- **`phase-arch-design.md §830 (Decision points + defaults):** "The CLI's `--max-attempts-override <int>` raises (never lowers) the cap, requires `--operator-ack`, emits one `gate.attempts_override` audit event."
- **`phase-arch-design.md §Edge case 14`:** `--max-attempts-override 5` without `--operator-ack` → Click exit 2.
- **`phase-arch-design.md §Open questions §3`:** `--allow-test-network` widens `egress_allowlist`, leaves `trace.new_endpoints` informational; `tests/integration/sandbox/test_allow_test_network.py` exercises both paths.
- **ADR-0004:** `--sandbox-backend {did,firecracker,auto}` — `auto` calls `auto_detect()`.
- **ADR-0009:** `--allow-test-network` widens the host-side nftables egress allowlist (Firecracker); same allowlist semantics for DinD iptables.
- **ADR-0012:** Env-allowlist filtering is unchanged even with `--allow-test-network` — credentials never reach the sandbox.
- **ADR-0013:** `tools/policy/sandbox-policy.yaml` is codegenie-owned + digest-pinned; the additive `test_network.extra_hosts` key requires a BLAKE3 re-digest.
- **Production ADR-0014:** Three retries is the default; override requires `--operator-ack`; audit event records the decision.

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition — no silent edits":** the policy YAML extension (`test_network.extra_hosts`) is additive — no existing field renamed; the `_CLI_TO_REGISTRY_BACKEND_NAME` mapping in `cli/_options.py` is additive (mirrors S8-01's `_CLI_BACKEND_NAMES`); the `RemediationOrchestrator` ctor gains three keyword-only kwargs with safe defaults (`sandbox_backend=None`, `max_attempts_override=None`, `allow_test_network=False`) — backwards-compatible.
- **CLAUDE.md "Match the existing convention":** the audit-event-via-`structlog` pattern (S1-01) + `EVENT_*` constants (S1-01); the `_CLI_TO_REGISTRY_BACKEND_NAME` mapping extends S8-01's precedent; the `GateAttemptsOverrideEvent` Pydantic value type extends S7-04's `RepoLockHolder` precedent (4th concrete consumer; rule-of-three already cleared).
- **CLAUDE.md "Make illegal states unrepresentable":** `--max-attempts-override` is `click.IntRange(min=3, max=1024)` (the `AttemptNumber` envelope); `GateAttemptsOverrideEvent` is frozen Pydantic with `extra="forbid"`; the `_CLI_TO_REGISTRY_BACKEND_NAME` mapping has `Literal`-typed keys/values so a typo at the call site is a `mypy --strict` error; `RetryPolicy.max_attempts` override flows through `model_copy(update={"max_attempts": AttemptNumber(override)})` — never raw int.
- **CLAUDE.md "Functional core / imperative shell":** `_require_operator_ack(value, *, operator_ack) -> None` and `_raise_max_attempts(*, catalog: AttemptNumber, override: AttemptNumber) -> AttemptNumber` are pure module-level helpers (precedents: S5-02 `_dispatch_outcome`, S7-04 `_parse_holder_pid`); AST scan asserts no `structlog.*` / I/O in their bodies.
- **CLAUDE.md "Tests verify intent, not just behavior":** AC-prefixed red tests (executor's Validator uses them as the AC→test map); the four mutation witnesses (M-1 ack-rejection-without-event, M-2 IntRange-upper-bound, M-3 env-var-bypass, M-4 frozen-model-copy) are explicit ACs.
- **CLAUDE.md "Structural defenses live under `tests/fence/`":** the new fence rows extend S8-01's `tests/fence/test_cli_sandbox_backend_addition.py` to cover `cli/remediate.py`.
- **CLAUDE.md "Fail loud":** ack rejection exits Click 2 with verbatim error message text; `--max-attempts-override` upper-bound violation raises Click `UsageError`; `--allow-test-network` cannot bypass env-allowlist filtering (ADR-0012 belt-and-suspenders test).

### Adjacent / prerequisite stories cited

| Story | Status | What S8-02 reuses (or must respect) |
|---|---|---|
| [S1-01](../S1-01-scaffold-packages-errors-structlog.md) | HARDENED | `EVENT_GATE_ATTEMPTS_OVERRIDE: Final[str] = "gate.attempts_override"` already lives in `gates/logging.py` (line 73 of S1-01's validated AC table) — IMPORT, do not redefine; the structlog-via-`get_logger().info(EVENT_*, **fields)` emit pattern (NOT a `codegenie.audit.emit` import — that module does not exist) |
| [S1-02](../S1-02-sandbox-contract-protocol-models.md) | HARDENED | `SandboxClient` Protocol member set `{execute, health}`; `SandboxRun.backend` Literal `{"docker_in_docker", "firecracker"}` (the registry-name set); `SandboxSpec` is frozen with `extra="forbid"` |
| [S1-04](../S1-04-gates-contract-abc-models.md) | HARDENED | `RetryPolicy.max_attempts: AttemptNumber` (bounded 1..1024, frozen model); `GateContext` field set is closed `{worktree, advisory, recipe, transform_output, prior_attempts, workflow_id, run_id}` — `allow_test_network` cannot be added without an ADR amendment; `AttemptNumber` newtype from `types/identifiers.py:102` |
| [S1-05](../S1-05-registries-and-env-allowlist.md) | HARDENED | `register_sandbox_backend`, `get_backend(name)`, `auto_detect()` from `codegenie.sandbox.registry`; `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` emit on `--sandbox-backend auto`; `env_allowlist.filter` is the only host-env → SandboxSpec.env path (belt-and-suspenders against `--allow-test-network` credential bypass) |
| [S3-01](../S3-01-spec-builder-canonical-hash.md) | HARDENED | `SandboxSpecBuilder.__init__` keyword-only DI ports (catalog, filter_fn, host_env_source); `for_gate(gate, attempt: AttemptNumber, ctx: GateContext) -> SandboxSpec`; byte-stable `sandbox_spec_hash` invariant under env reorder; `egress_allowlist` hash CHANGES on widening (AC-PROP-5) — widening MUST happen inside the builder so the hash is computed over the widened list |
| [S3-05](../S3-05-stage6-yaml-catalogs-and-policy.md) | HARDENED | `tools/policy/sandbox-policy.yaml` field set is `{lockfile, runtime_trace, test_inventory}` per arch lines 810–824; the policy is digest-pinned (ADR-0013) — additive `test_network.extra_hosts` requires re-digest + golden template update; `tools/digests.yaml#sandbox.policy_yaml` is BLAKE3-128 (32-char lowercase hex) |
| [S5-02](../S5-02-gate-runner-retry-loop.md) | HARDENED | `GateRunner` is `async def run` with keyword-only ctor `{client, gate, ledger, spec_builder, max_attempts=3, replan_hook=None}` (+ S7-03's additive 7th `cost`); the per-gate `max_attempts` lives on `RetryPolicy`; mutation via `model_copy(update={"max_attempts": AttemptNumber(...)})` (frozen-safe) |
| [S6-05 (Phase 3)](../../03-vuln-deterministic-recipe/stories/S6-05-remediate-cli-flock.md) | HARDENED | `codegenie remediate <repo> --cve <id>` is shipped at `src/codegenie/cli/remediate.py`; the existing Click command this story extends (not rewrites); `parse_cve_id(s) -> Result[CveId, ParseError]` is the existing arg parser |
| [S7-04](../S7-04-concurrent-remediate-repo-lock.md) | HARDENED | `cli/exit_codes.py` kernel with `EXIT_USAGE = 2` (existing); `cli/_errors.py` `EXIT_CODE_FOR: Final[Mapping[type[Exception], int]]` registry; the `cli/remediate.py` Click-command entry pattern (lock acquired before Phase 3/4/5 work) — the override-validator is a Click `callback` running INSIDE this scope; `RepoLockHolder` frozen-Pydantic precedent for `GateAttemptsOverrideEvent` |
| [S8-01](../S8-01-sandbox-cli-subcommands.md) | HARDENED | `cli/_options.py` module ownership; `_CLI_BACKEND_NAMES: Final[Mapping[str, str]]` precedent — S8-02 reuses + extends with `_CLI_TO_REGISTRY_BACKEND_NAME`; `tests/fence/test_cli_sandbox_backend_addition.py` fence — S8-02 extends to cover `cli/remediate.py` (additive row) |

### Existing event-constant ground truth (S1-01 HARDENED canonical table)

`src/codegenie/gates/logging.py` already ships:

| Constant | Value | Notes |
|---|---|---|
| `EVENT_GATE_RUN_STARTED` | `"gate.run.started"` | S1-01 AC table line 69 |
| `EVENT_GATE_RUN_COMPLETED` | `"gate.run.completed"` | S1-01 AC table line 70 |
| `EVENT_GATE_ATTEMPT_STARTED` | `"gate.attempt.started"` | S1-01 AC table line 71 |
| `EVENT_GATE_ATTEMPT_COMPLETED` | `"gate.attempt.completed"` | S1-01 AC table line 72 |
| `EVENT_GATE_ATTEMPTS_OVERRIDE` | `"gate.attempts_override"` | **S1-01 AC table line 73** — this story consumes |
| `EVENT_PRE_EXECUTE_MARKER_WRITTEN` | `"gate.pre_execute.written"` | S1-01 AC table line 74 |

S8-02 does NOT add a new constant. The audit event constant already exists. (S1-01 Validation note §"Adding a new event constant": "**Never** rename or re-value an existing constant.")

### Existing exit-code ground truth (S7-04 HARDENED kernel)

`src/codegenie/cli/exit_codes.py`:

| Constant | Value | Notes |
|---|---|---|
| `EXIT_OK` | 0 | S7-04 |
| `EXIT_GENERAL` | 1 | S7-04 |
| `EXIT_USAGE` | 2 | S7-04 — **S8-02 reuses for ack rejection + IntRange violation** |
| `EXIT_ESCALATE` | 11 | S7-04 |
| `EXIT_FAILED_UNRECOVERABLE` | 12 | S7-04 |
| `EXIT_CHAIN_CORRUPTED` | 13 | S8-01 (HARDENED) |
| `EXIT_REPO_ALREADY_IN_PROGRESS` | 14 | S7-04 |
| `EXIT_INTERRUPTED` | 130 | S7-04 |

S8-02 does NOT add a new exit code. (Click's `UsageError` default-maps to 2; `cli/_errors.py` `EXIT_CODE_FOR` registry already handles non-Click exceptions.)

## Critic findings

The four critics' findings are listed below. Each finding has a severity (`block` / `harden` / `nit`) and an `AC-…` ID that maps to the AC introduced or modified.

### Critic A — Coverage (does the AC set guarantee the goal?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-A-1 | block | The `--operator-ack`-without-emit invariant is in Notes but no AC enforces it. A mutation that emits the audit event before the ack check passes the existing happy-path AC. | **AC-EVT-NEG-1.** `--max-attempts-override 5` without `--operator-ack` → captured `structlog` logs contain ZERO entries with `event == EVENT_GATE_ATTEMPTS_OVERRIDE`. Uses `structlog.testing.capture_logs()`. |
| C-A-2 | block | "Single audit event per invocation" contradicts the draft event field `gate_id: str` (singular). Multi-gate runs would either emit N events or carry one wrong `gate_id`. | **AC-EVT-FIELD-1.** The event payload omits singular `gate_id`. Instead carries `affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...]` where each entry pins `(gate_id, default_max_attempts, override_max_attempts)`. **AC-EVT-COUNT-1** — multi-gate fixture (2 gates) → exactly one event, `len(affected_gate_overrides) == 2`. |
| C-A-3 | block | `test_network_extra_hosts` key does not exist in `tools/policy/sandbox-policy.yaml` per S3-05 AC-GOLDEN-2 + arch lines 810–824. The story prescribes reading a missing key. | **AC-POLICY-1..-5.** Additive `test_network.extra_hosts: list[str]` section appended to `tools/policy/sandbox-policy.yaml`; re-pin `tools/digests.yaml#sandbox.policy_yaml` BLAKE3-128 32-char hex; update `tests/golden/sandbox-policy.yaml.template`; absent key default is `[]`; the read fails loud (`PolicyYamlSchemaError`) if the section is malformed. |
| C-A-4 | block | "Raises only, never lowers" semantic ambiguous when a gate's catalog `max_attempts` > override. If gate has `max_attempts=6` and override is `5`, the draft replace-semantics LOWERS the gate from 6 to 5. | **AC-RAISE-1.** Per-gate override is `max(catalog_default, override_value)`. **AC-RAISE-2.** Test: one gate at 2 (becomes 5), one gate at 6 (stays 6); audit-event `affected_gate_overrides` records both entries with `(gate_id, default_max_attempts=2, override_max_attempts=5)` for the raised gate and skips (or records `override_max_attempts == default_max_attempts`) for the unchanged gate. |
| C-A-5 | block | `--max-attempts-override` upper bound missing. Override of `9999` accepts at the CLI but `AttemptNumber(9999)` raises ValueError deep in the stack. | **AC-RANGE-1.** `click.IntRange(min=3, max=1024)`. Parametrized rejection: `[2, 1, 0, -1, 1025, 10_000]`. |
| C-A-6 | block | `--sandbox-backend did → docker_in_docker` registry-name mapping not pinned. `get_backend("did")` raises `SandboxBackendInvalid`. | **AC-SB-MAP-1.** `_CLI_TO_REGISTRY_BACKEND_NAME: Final[Mapping[str, Literal["docker_in_docker", "firecracker"]]] = MappingProxyType({"did": "docker_in_docker", "firecracker": "firecracker"})` in `cli/_options.py`; `auto` calls `auto_detect()`. **AC-SB-MAP-2.** Mapping keys are exactly the non-`auto` choice values of `_CLI_BACKEND_NAMES`; mapping values are exactly the `SandboxRun.backend` Literal set per S1-02 AC-7b. |
| C-A-7 | block | `--operator-ack` invocation-only rule unenforced. An env var `CODEGENIE_OPERATOR_ACK=1` (or YAML override) would bypass operator intent — security-relevant per ADR-0014 humans-always-merge. | **AC-INV-1.** Setting `CODEGENIE_OPERATOR_ACK=1` env var has NO effect; only the explicit `--operator-ack` CLI flag enables the override path. The Pydantic `BaseSettings` field set excludes `operator_ack`. Test parametrizes `[env-var, YAML-override, .codegenie/config.yaml]` and asserts the override path is rejected in every case. |
| C-A-8 | block | `--allow-test-network` integration with the host-side TAP/nftables (Firecracker) + iptables (DinD) policy modules unpinned. The widened `egress_allowlist` must reach the host-policy modules, not just the SpecBuilder output. | **AC-NET-WIRE-1.** The widened `egress_allowlist` produced by `SandboxSpecBuilder.for_gate(allow_test_network=True)` is the *only* surface; both `sandbox/did/network_policy.py` and `sandbox/firecracker/network_policy.py` consume `SandboxSpec.egress_allowlist` unchanged — no separate `allow_test_network` plumbing into the network-policy modules. **AC-NET-WIRE-2.** Test: golden iptables / nftables rule sets generated for `allow_test_network=True` include the `extra_hosts` entries in append-order. |
| C-A-9 | block | `--help` exit-code-0 + safety-interlock-language AC is vague. A future contributor rewording the help text would silently break operator UX. | **AC-HELP-1.** `--help` output contains verbatim substrings: `"--max-attempts-override requires --operator-ack"`, `"raises (never lowers) the cap"`, `"keeps trace.new_endpoints informational"`. Each substring is a separate parametrized assertion. |
| C-A-10 | block | Test stub `monkeypatch.setattr("codegenie.audit.emit", ...)` patches a non-existent module. The real emit path is `structlog.get_logger().info(EVENT_*, **fields)`. The test never observes the event. | **AC-TEST-EVT-1.** TDD plan uses `structlog.testing.capture_logs()` (S5-02 AC-OBS-1 precedent); assertions reference `EVENT_GATE_ATTEMPTS_OVERRIDE` constant (NOT the string `"gate.attempts_override"`). |
| C-A-11 | block | Test stub `monkeypatch.setattr("codegenie.orchestrator.run", ...)` patches a non-existent module. The orchestrator is `codegenie.transforms.orchestrator.RemediationOrchestrator`. | **AC-TEST-ORC-1.** The CLI exposes a module-level `make_orchestrator: Callable[..., RemediationOrchestrator]` DI port (default = `RemediationOrchestrator`); tests inject a fake orchestrator via this seam instead of monkey-patching imports. Mirrors the S6-04 pattern. |
| C-A-12 | block | The validator-rejection error message is unpinned. Click's default for `IntRange(min=3)` is `"Invalid value for '--max-attempts-override': 3 is not in the range 3<=x"` — but the draft AC-2 asserts the substring `"--max-attempts-override requires --operator-ack"` for a *different* failure mode. Two separate failure paths, two separate verbatim-substring ACs needed. | **AC-MSG-MISSING-ACK.** Exact substring assertion for the missing-ack rejection. **AC-MSG-RANGE.** Exact substring assertion for the `IntRange` rejection. |

### Critic B — Test quality (would the TDD plan catch a wrong implementation?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-B-1 | block | `test_allow_test_network_widens_egress_but_does_not_disable_env_filter` is a `...` stub. The two mutation witnesses (env-filter dropped, network downgraded) have no concrete asserts. | **AC-NET-1.** Concrete fixture: inject a counting `filter_fn` into `SandboxSpecBuilder`; assert call-count >= 1 with `allow_test_network=True`. **AC-NET-2.** Assert `resolved_spec.network == "scoped"` (NOT `"none"`) post-widening. **AC-NET-3.** Assert `set(resolved_spec.env) ⊆ env_allowlist.ALLOWLIST ∪ ALLOWLIST_PREFIXES` (S1-05 surface) — even with `--allow-test-network`. |
| C-B-2 | block | No mutation witness for "no event on failure path (missing ack)". | (Resolved by C-A-1 AC-EVT-NEG-1.) |
| C-B-3 | block | No mutation witness for "single audit event per invocation across N gates". | (Resolved by C-A-2 AC-EVT-COUNT-1.) |
| C-B-4 | block | No mutation witness for `RetryPolicy` frozen-model `model_copy` path. A naive implementer writing `policy.max_attempts = override` would `pydantic.ValidationError` at runtime (correct fail-loud), but a wrapper that mutates a *plain* dict before `RetryPolicy(...)` reconstruction would silently bypass `AttemptNumber` validation. | **AC-COPY-1.** AST scan asserts the substring `model_copy(update={"max_attempts":` exists in `cli/remediate.py`'s override-application codepath. **AC-COPY-2.** Hypothesis property test: for `override ∈ [3, 1024]`, the resolved policy's `max_attempts == max(catalog_default, override)` AND `isinstance(policy.max_attempts, int)` AND `1 <= policy.max_attempts <= 1024`. |
| C-B-5 | harden | `test_sandbox_backend_default_is_auto` only asserts `captured["sandbox_backend"] == "auto"` — doesn't pin the registry call (`auto_detect`) actually fires. | **AC-AUTO-1.** Inject a counting fake `auto_detect`; assert `auto_detect.call_count == 1` when `--sandbox-backend` is omitted (default). **AC-AUTO-2.** When `--sandbox-backend firecracker` is explicit, `auto_detect.call_count == 0` AND `get_backend.call_args == call("firecracker")` (per the mapping). |
| C-B-6 | harden | No property test for the precedence stack (env → YAML → CLI). | **AC-PREC-1.** Parametrize: `[(env="did", cli=None, expected="did"), (env="did", cli="firecracker", expected="firecracker"), (env=None, cli=None, expected="auto"→auto_detect), (env="bogus", cli=None, expected=UsageError)]`. |
| C-B-7 | harden | "`--operator-ack` is a boolean flag, not a value" is in Notes but no AC enforces it. | **AC-FLAG-1.** `--operator-ack=anything` → Click parser error exit 2. The flag is `is_flag=True, default=False`. |
| C-B-8 | harden | No metamorphic invariant test on the audit event. | **AC-INV-EVT-1.** For any successful override invocation, `count(events where event == EVENT_GATE_ATTEMPTS_OVERRIDE) == 1` AND `event.operator_ack is True` AND `event.affected_gate_overrides` is a non-empty `tuple[GateAttemptsOverrideEntry, ...]`. Invariant holds across all happy-path tests. |
| C-B-9 | harden | Help-text test should verify the example block from outline step 6 is present. | **AC-HELP-2.** `--help` output contains one example per flag combination (three substrings: `"codegenie remediate --sandbox-backend firecracker"`, `"--max-attempts-override 5 --operator-ack"`, `"--allow-test-network"`). |
| C-B-10 | harden | No mutation witness for `_CLI_TO_REGISTRY_BACKEND_NAME` Open/Closed property. A future contributor hard-coding `"docker_in_docker"` inside `cli/remediate.py` breaks the seam silently. | **AC-OC-1.** AST scan on `src/codegenie/cli/remediate.py` asserts no string literal in `{"docker_in_docker", "firecracker"}` exists outside imports from `cli/_options.py`. Mirrors S8-01's `_CLI_BACKEND_NAMES` fence. |
| C-B-11 | nit | Missing `from __future__ import annotations` discipline. | **AC-FUTURE-1.** Pure-helper tests assert `from __future__ import annotations` is the first statement after the module docstring (S5-02 / S7-04 precedent). |

### Critic C — Consistency (does the story contradict arch / ADR / commitments?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-C-1 | block | AC-9 ("Audit event constant `gate.attempts_override` is defined in `src/codegenie/audit/events.py`") contradicts S1-01 HARDENED, which already defines `EVENT_GATE_ATTEMPTS_OVERRIDE` in `src/codegenie/gates/logging.py`. The `codegenie.audit` module does not exist. | **AC-EVT-IMPORT-1.** `from codegenie.gates.logging import EVENT_GATE_ATTEMPTS_OVERRIDE`. NO new constant defined. AST scan asserts the constant is not re-defined in `cli/remediate.py` or anywhere outside `gates/logging.py`. |
| C-C-2 | block | Outline step 4 "extend each `SandboxSpec.egress_allowlist`" contradicts S1-02 `frozen=True` and the byte-stable `sandbox_spec_hash` invariant (S3-01 AC-PROP-5). | **AC-WIDEN-LOC-1.** Widening is owned by `SandboxSpecBuilder.for_gate`. **AC-WIDEN-LOC-2.** The builder accepts `allow_test_network: bool` at construction time via a new keyword-only DI port (`SandboxSpecBuilder.__init__(*, catalog, filter_fn=..., host_env_source=..., allow_test_network: bool = False)`). **AC-WIDEN-LOC-3.** Post-widening `sandbox_spec_hash` reflects the widened `egress_allowlist` (no out-of-band hash drift). **AC-WIDEN-LOC-4.** When `allow_test_network=False`, byte-identical hash to the catalog-only spec (regression guard). |
| C-C-3 | block | Outline step 4 "set a flag on `GateContext`" contradicts S1-04 HARDENED — `GateContext` is frozen with `extra="forbid"` and field set `{worktree, advisory, recipe, transform_output, prior_attempts, workflow_id, run_id}`. | **AC-TRACE-WIRE-1.** `--allow-test-network` does NOT add a field to `GateContext`. Instead, the trace-signal collector (`collect_trace_signal`) is constructed by the orchestrator factory with an `allow_test_network: bool` keyword-only argument; the runner does not see the flag. **AC-TRACE-WIRE-2.** Test: when `allow_test_network=True`, the collector returns `TraceSignal(passed=True, details={"new_endpoints": [...]})` (informational) even when new endpoints are observed; when `allow_test_network=False`, the same observation returns `passed=False`. |
| C-C-4 | block | Audit-event field set contradicts S2-01 / S5-02 / S7-04 frozen-Pydantic value-type convention. The draft uses a dict with `gate_id: str`; the precedent is a frozen Pydantic value type (cf. S7-04 `RepoLockHolder`). | **AC-MODEL-1.** `class GateAttemptsOverrideEntry(BaseModel, frozen=True, extra="forbid")` with `(gate_id: str, default_max_attempts: AttemptNumber, override_max_attempts: AttemptNumber)`. **AC-MODEL-2.** `class GateAttemptsOverrideEvent(BaseModel, frozen=True, extra="forbid")` with `(operator_ack: bool, affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...], invocation_id: str, workflow_id: str, run_id: str)`. Both models live in `src/codegenie/gates/events.py` (additive). Structured-logging binding via `structlog.bind(**event_model.model_dump())`. |
| C-C-5 | block | "ADRs honored: ADR-0004, ADR-0009, ADR-0012" omits Phase-5 ADR-0013 (codegenie-owned digest-pinned policy YAML — load-bearing for `test_network.extra_hosts` extension) and production-ADR-0014 (already cited in body, but missing from header). | **Metadata** — ADRs honored line widened to `ADR-0004, ADR-0009, ADR-0012, ADR-0013, production-ADR-0014`. |
| C-C-6 | block | "Depends on: S8-01" omits the real dependency set: S1-01 (event constant), S1-02 (`SandboxClient` Protocol), S1-04 (`RetryPolicy.max_attempts: AttemptNumber`, `GateContext` frozen), S1-05 (registry `get_backend` / `auto_detect`), S3-01 (`SandboxSpecBuilder` ctor surface), S3-05 (policy YAML), S5-02 (`GateRunner` async), S7-04 (`cli/exit_codes.py` kernel). | **Metadata** — Depends-on widened. |
| C-C-7 | harden | The `RemediationOrchestrator` ctor (Phase 3 S6-04) is HARDENED. Adding three kwargs is an additive amendment requiring a cross-phase note. | **AC-ORC-1.** `RemediationOrchestrator.__init__` gains three additive keyword-only params: `sandbox_backend: str | None = None`, `max_attempts_override: AttemptNumber | None = None`, `allow_test_network: bool = False`. **AC-ORC-2.** All three default to "no-op" so Phase 3-only invocations remain byte-stable. **AC-ORC-3.** `inspect.signature(RemediationOrchestrator.__init__)` snapshot test asserts the new params are keyword-only with the documented defaults. **AC-ORC-4.** Cross-phase amendment note added to Phase 3 ADR-0014 (RecipeEngine surfaces Transform via TransformRegistry) — additive constructor params are extension-by-addition compliant. |
| C-C-8 | harden | The Click-callback declaration-order trick (`--operator-ack` before `--max-attempts-override`) is fragile and non-obvious. | **AC-DECL-1.** `inspect.signature(remediate.callback)` parameter-order test asserts the order: `operator_ack` precedes `max_attempts_override`. **AC-DECL-2.** Source-comment requirement (in `cli/remediate.py`) explaining the order dependency (S5-02 AST scan precedent). **AC-DECL-3.** Alternative path documented: a `@remediate.result_callback` (or post-parse hook) accomplishes the same without the order coupling — chosen path is the callback-with-order-comment (simpler; one fewer indirection); the order test prevents accidental reordering. |
| C-C-9 | harden | `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` (S1-05 AC-AD-3) must fire on `--sandbox-backend auto` when KVM is missing. The story is silent on the fallback path. | **AC-FALL-1.** Test: with `--sandbox-backend auto` on a no-KVM mock environment, `structlog.testing.capture_logs()` contains exactly one entry with `event == EVENT_SANDBOX_AUTO_DETECT_FALLBACK` and `extra={"backend": "docker_in_docker"}`. **AC-FALL-2.** With `--sandbox-backend firecracker` on a no-KVM mock, `auto_detect()` is NOT called; `get_backend("firecracker")` proceeds to raise `FirecrackerKvmMissing` at first use; exit code surfaces via `cli/_errors.py` `EXIT_CODE_FOR` (NOT a new exit code). |
| C-C-10 | harden | Module purity / cold-start fence row missing for the new `cli/_options.py` extensions and the new `gates/events.py` module. | **AC-FENCE-1.** Cold-start matrix row added for `gates/events.py` (zero LLM SDK imports, zero subprocess, zero docker/iptables). **AC-FENCE-2.** S8-01's `tests/fence/test_cli_sandbox_backend_addition.py` extends to scan `cli/remediate.py` (additive row in the AST scan's path list). |
| C-C-11 | nit | "ADR-0014 honored" line (production) is in the body but not in the Header `**ADRs honored:**` line. | (Resolved by C-C-5.) |

### Critic D — Design patterns (extensibility / Open-Closed / pure-impure)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-D-1 | block | `_CLI_TO_REGISTRY_BACKEND_NAME` Open/Closed seam missing for Phase 7 chainguard. Without it, Phase 7 adds a backend AND edits `cli/remediate.py` (the "extension by editing" anti-pattern CLAUDE.md forbids). | **AC-OC-1** (test side, see C-B-10) + **AC-OC-2.** The mapping lives in `cli/_options.py` and is the single source of truth. Phase 7 adds one row to the mapping + one row to `_CLI_BACKEND_NAMES` (additive; rule-of-three already cleared — `@register_probe`, `@register_sandbox_backend`, `@register_signal_kind`, `_CLI_BACKEND_NAMES`). Zero edits to `cli/remediate.py`. |
| C-D-2 | block | Functional core / imperative shell split absent. The override-validator and the max-attempts-raise logic are inline in the Click callback — untestable in isolation. | **AC-PURE-1.** `_require_operator_ack(value: int | None, *, operator_ack: bool) -> None` is a module-level pure helper raising `click.UsageError` deterministically; AST scan asserts no `structlog.*` / I/O in its body. **AC-PURE-2.** `_raise_max_attempts(*, catalog: AttemptNumber, override: AttemptNumber) -> AttemptNumber` returns `AttemptNumber(max(catalog, override))`; module-level pure; AST scan asserts no I/O. Both helpers have direct unit tests. |
| C-D-3 | harden | `GateAttemptsOverrideEvent` Pydantic value type (per C-C-4) is also a design-pattern improvement — it elevates the audit event from anaemic dict to typed value, makes illegal payloads unrepresentable (`extra="forbid"`), and serializes to canonical-JSON for the audit chain. | (Resolved by C-C-4.) |
| C-D-4 | harden | The `make_orchestrator` DI port (per C-A-11) is a dependency-inversion seam that decouples the CLI from the concrete `RemediationOrchestrator`. | (Resolved by C-A-11.) |
| C-D-5 | harden | The `_require_operator_ack` validator is also a candidate for the chain-of-responsibility / specification-pattern shape — but at this scale (one check), a pure helper is sufficient (Rule 2: three similar lines beat premature abstraction). | **Notes-for-implementer** — document the future extension seam: if Phase 6+ adds more "operator-ack-required" flags (`--force-promote`, `--bypass-canary`, etc.), the third such flag triggers an extraction (`OperatorAckPolicy: Callable[[click.Context], None]` registry under `cli/_errors.py`). Document but do NOT extract now. |
| C-D-6 | harden | The "single audit event with structured per-gate payload" shape is a tagged-union / discriminated-union opportunity — but the override entries are homogeneous (same fields per gate), so a plain `tuple[GateAttemptsOverrideEntry, ...]` is correct. Premature discrimination here is YAGNI. | (No action; documented in Notes.) |
| C-D-7 | nit | The `cli/_options.py` module is the natural home for *all* shared CLI options across `remediate` and `sandbox` subcommands. Phase 7's recipe-engine flag would slot in here. | **Notes-for-implementer** — document the convention. |

## Stage-3 Researcher — N/A

No findings tagged `NEEDS RESEARCH`. Every gap was answerable from in-repo HARDENED sources (S1-01..S8-01), the four cited Phase-5 ADRs, production ADR-0014, the Pydantic + Click documentation already pinned by arch §839 and S1-04 / S3-01 ACs, and CLAUDE.md load-bearing commitments.

## Conflict resolution

Two critic findings produced overlapping resolutions:

1. **C-C-2 (widen via SandboxSpecBuilder DI) vs C-C-3 (collector receives `allow_test_network` directly).** Both critics agreed `GateContext` cannot carry the flag (frozen, extra="forbid"). Resolution: **two-port wiring**. The `SandboxSpecBuilder` DI port carries `allow_test_network` to compute the widened `egress_allowlist` (Consistency wins for the spec-hash invariant); the trace collector receives the flag via the orchestrator factory. The orchestrator threads the same `allow_test_network: bool` to BOTH ports.
2. **C-D-1 (Open/Closed mapping) vs C-A-6 (Backend name mapping AC).** Same underlying need; merged into the `_CLI_TO_REGISTRY_BACKEND_NAME` mapping in `cli/_options.py`. Single AC family: `AC-SB-MAP-*`.

## Edits applied to the story file

The edits are surgical (Rule 3). The Goal, Out-of-scope, and the overall flag set are preserved. ACs are rewritten / added in-place; the Implementation Outline and the TDD plan are tightened; the Notes-for-implementer is expanded; Files-to-touch is widened to include the new `gates/events.py` module and the policy YAML / digest / golden updates.

### Header changes

- **Status:** `Ready` → `Ready (HARDENED 2026-05-26)`.
- **Depends on:** widened from `S8-01` to the full prerequisite set (S1-01, S1-02, S1-04, S1-05, S3-01, S3-05, S5-02, S7-04, S8-01).
- **ADRs honored:** `ADR-0004, ADR-0009, ADR-0012` → `ADR-0004, ADR-0009, ADR-0012, ADR-0013, production-ADR-0014`.

### Acceptance criteria — wholesale rewrite

The 10-AC draft is replaced with a structured, ID-prefixed AC list:
- **A.** Flag declaration (`AC-SB-MAP-1..2`, `AC-RANGE-1`, `AC-FLAG-1`, `AC-DECL-1..3`).
- **B.** Operator-ack rejection path (`AC-EVT-NEG-1`, `AC-MSG-MISSING-ACK`, `AC-INV-1`).
- **C.** Override-application path (`AC-RAISE-1..2`, `AC-COPY-1..2`, `AC-MSG-RANGE`).
- **D.** Audit event (`AC-EVT-IMPORT-1`, `AC-EVT-FIELD-1`, `AC-EVT-COUNT-1`, `AC-MODEL-1..2`, `AC-INV-EVT-1`).
- **E.** `--allow-test-network` plumbing (`AC-POLICY-1..5`, `AC-WIDEN-LOC-1..4`, `AC-TRACE-WIRE-1..2`, `AC-NET-1..3`, `AC-NET-WIRE-1..2`).
- **F.** Backend resolution (`AC-AUTO-1..2`, `AC-PREC-1`, `AC-FALL-1..2`).
- **G.** `--help` text (`AC-HELP-1..2`).
- **H.** Open/Closed + purity (`AC-OC-1..2`, `AC-PURE-1..2`).
- **I.** Orchestrator amendment (`AC-ORC-1..4`).
- **J.** Fences (`AC-FENCE-1..2`, `AC-FUTURE-1`).
- **K.** Test harness (`AC-TEST-EVT-1`, `AC-TEST-ORC-1`).

### TDD plan changes

- The five sketched tests are kept but tightened.
- `test_max_attempts_override_with_ack_emits_one_audit_event` is rewritten to use `structlog.testing.capture_logs()` + the `EVENT_GATE_ATTEMPTS_OVERRIDE` constant + the `GateAttemptsOverrideEvent` payload model assertion.
- `test_allow_test_network_widens_egress_but_does_not_disable_env_filter` is filled in with concrete asserts.
- New tests added: `test_audit_event_omitted_on_missing_ack` (negative path), `test_audit_event_field_set_is_frozen_pydantic`, `test_sandbox_backend_did_maps_to_docker_in_docker`, `test_env_var_operator_ack_is_ignored`, `test_max_attempts_override_exceeds_attempt_number_envelope`, `test_help_text_contains_safety_interlocks`, `test_orchestrator_ctor_signature_is_additive`, `test_purity_of_require_operator_ack`, `test_purity_of_raise_max_attempts`, AST-scan + fence rows.

### Files-to-touch additions

| Path | Why (new) |
|---|---|
| `src/codegenie/gates/events.py` | New module: `GateAttemptsOverrideEntry` + `GateAttemptsOverrideEvent` frozen-Pydantic value types. |
| `src/codegenie/cli/_options.py` | Add `_CLI_TO_REGISTRY_BACKEND_NAME` mapping (alongside S8-01's `_CLI_BACKEND_NAMES`). |
| `src/codegenie/transforms/orchestrator.py` | Additive ctor kwargs (`sandbox_backend`, `max_attempts_override`, `allow_test_network`). |
| `src/codegenie/sandbox/spec_builder.py` | Additive `allow_test_network: bool = False` DI port on `__init__`. |
| `tools/policy/sandbox-policy.yaml` | Append `test_network.extra_hosts: list[str] = []`. |
| `tools/digests.yaml` | Re-pin `sandbox.policy_yaml` BLAKE3-128. |
| `tests/golden/sandbox-policy.yaml.template` | Update template byte-for-byte (S3-05 AC-GOLDEN-2 chain). |
| `tests/fence/test_cli_sandbox_backend_addition.py` | Extend scan path list to include `cli/remediate.py`. |

### Notes-for-implementer additions

- Explain the Click callback declaration-order trick + the parameter-order test.
- Pin the structlog emit pattern (NOT `codegenie.audit.emit`).
- Document the `make_orchestrator` DI port + when to inject a fake (unit tests) vs the default factory (production).
- Surface the future `OperatorAckPolicy` registry seam (3rd flag triggers extraction).
- Cross-link to S8-03's E2E test (`tests/integration/sandbox/test_allow_test_network.py`) — S8-02 ships the unit-level proofs; the integration test belongs to S8-03 + the dedicated allow-test-network integration test.
- Confirm `--operator-ack` is NEVER in Pydantic `BaseSettings` field set (ADR-0014 humans-always-merge).

## Verdict — HARDENED

The goal is preserved. The ACs now guarantee every claim the goal makes (single event per invocation; raises only, never lowers; ack-rejection without emit; env-allowlist preserved; `--sandbox-backend` precedence; help text safety interlocks). The TDD plan would catch every mutation the original would have missed. The implementation outline composes Open/Closed with the four established kernel-plus-registry precedents (`@register_probe`, `@register_sandbox_backend`, `@register_signal_kind`, `_CLI_BACKEND_NAMES`); Phase 7 chainguard extension is now a pure-additive change with zero edits to `cli/remediate.py`. The story is ready for `phase-story-executor`.
