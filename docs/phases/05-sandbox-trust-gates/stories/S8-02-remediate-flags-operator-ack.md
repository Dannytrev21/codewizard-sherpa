# Story S8-02 — `codegenie remediate` flags `--sandbox-backend`, `--max-attempts-override`, `--allow-test-network` + `--operator-ack`

**Step:** Step 8 — Operator CLI surface + end-to-end smoke
**Status:** Ready (HARDENED 2026-05-26)
**Effort:** S
**Depends on:** S1-01 (`EVENT_GATE_ATTEMPTS_OVERRIDE` constant in `gates/logging.py` — HARDENED), S1-02 (`SandboxClient` Protocol + `SandboxSpec` frozen with `sandbox_spec_hash` byte-stability — HARDENED), S1-04 (`RetryPolicy.max_attempts: AttemptNumber` 1..1024 + frozen `GateContext` closed field set — HARDENED), S1-05 (`get_backend` / `auto_detect` + `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` — HARDENED), S3-01 (`SandboxSpecBuilder` DI ports + `egress_allowlist` hash invariant — HARDENED), S3-05 (`tools/policy/sandbox-policy.yaml` digest-pinned, `tests/golden/sandbox-policy.yaml.template` — HARDENED), S5-02 (`GateRunner` async ctor — HARDENED), S7-04 (`cli/exit_codes.py` + `cli/_errors.py` `EXIT_CODE_FOR` registry — HARDENED), S8-01 (`cli/_options.py` + `_CLI_BACKEND_NAMES` + `tests/fence/test_cli_sandbox_backend_addition.py` — HARDENED)
**ADRs honored:** ADR-0004 (DinD-on-macOS + `gate_isolation_class`), ADR-0009 (Firecracker nftables host policy), ADR-0012 (env-allowlist + denied-substring CI test — `--allow-test-network` MUST NOT relax), ADR-0013 (codegenie-owned digest-pinned policy YAML — additive `test_network.extra_hosts` + re-digest), production-ADR-0014 (three-retry default per gate — `--max-attempts-override` is the documented override path)

## Validation notes (2026-05-26 — phase-story-validator)

Four-critic pass (coverage / test-quality / consistency / design-patterns). Verdict: **HARDENED**. The draft's goal + flag set + Click-validator exit-2 framing were sound, but every block-tier finding traced to one of five root causes: (a) the draft was written before S1-01 reached HARDENED — `EVENT_GATE_ATTEMPTS_OVERRIDE = "gate.attempts_override"` is *already defined* in `src/codegenie/gates/logging.py`, NOT in a nonexistent `src/codegenie/audit/events.py`; the executor following the draft would `ImportError` or create a duplicate constant in violation of the "Never rename or re-value an existing constant" rule; (b) the draft was written before S1-02 / S1-04 / S3-01 reached HARDENED on frozen Pydantic — `SandboxSpec` and `RetryPolicy` and `GateContext` are all `frozen=True, extra="forbid"`, so "extend each `SandboxSpec.egress_allowlist`" and "set a flag on `GateContext`" both raise `ValidationError`; (c) the draft was written before S1-05 reached HARDENED — `--sandbox-backend did` requires a `did → docker_in_docker` registry-name mapping per S1-02 AC-7b, never declared in the draft; (d) the draft was written before S3-05 reached HARDENED — `tools/policy/sandbox-policy.yaml` has exactly three top-level keys per S3-05 AC-GOLDEN-2 + arch lines 810–824, none of them `test_network_extra_hosts`; (e) the draft was written before S7-04 reached HARDENED — `cli/exit_codes.py` is the canonical exit-code kernel and Click `UsageError` already maps to `EXIT_USAGE = 2`. Headline edits — every one would have caught a structurally-wrong implementation that the executor's validator would have missed:

1. **(consistency — block) `EVENT_GATE_ATTEMPTS_OVERRIDE` already exists in `gates/logging.py` per S1-01.** Draft AC-9 said "Audit event constant `gate.attempts_override` is defined in `src/codegenie/audit/events.py`" — that module doesn't exist; the constant is already in S1-01's canonical event table. Fix: AC-EVT-IMPORT-1 imports the existing constant; AST scan asserts no redefinition anywhere outside `gates/logging.py`.
2. **(consistency — block) `SandboxSpec.egress_allowlist` cannot be mutated; the spec hash drifts on widening.** S1-02 + S3-01 AC-FROZEN-1..-3 pin frozen-model semantics; S3-01 AC-PROP-5 pins that `egress_allowlist` reorder/widen CHANGES `sandbox_spec_hash`. Widening MUST happen inside `SandboxSpecBuilder.for_gate` so the hash is computed over the widened list (and is byte-identical to catalog-only when `allow_test_network=False`). Fix: AC-WIDEN-LOC-* adds `allow_test_network: bool = False` to `SandboxSpecBuilder.__init__` as a new keyword-only DI port.
3. **(consistency — block) `GateContext` cannot carry `allow_test_network`.** S1-04 HARDENED freezes the field set `{worktree, advisory, recipe, transform_output, prior_attempts, workflow_id, run_id}` with `extra="forbid"`. Fix: AC-TRACE-WIRE-* threads `allow_test_network` to `collect_trace_signal` via the orchestrator factory's collector-construction site, NOT via `GateContext`.
4. **(consistency / coverage — block) `--sandbox-backend did → docker_in_docker` mapping missing.** Without it, `get_backend("did")` raises `SandboxBackendInvalid`. Fix: AC-SB-MAP-* introduces `_CLI_TO_REGISTRY_BACKEND_NAME` in `cli/_options.py` alongside S8-01's `_CLI_BACKEND_NAMES` — Open/Closed seam for Phase 7 chainguard.
5. **(coverage — block) `tools/policy/sandbox-policy.yaml#test_network_extra_hosts` key does not exist.** S3-05 AC-GOLDEN-2 + arch lines 810–824 pin the field set to `{lockfile, runtime_trace, test_inventory}`. The policy YAML is digest-pinned (ADR-0013). Adding the key requires re-pinning the BLAKE3 + updating the golden template. Fix: AC-POLICY-1..-5 owns the additive `test_network.extra_hosts: list[str] = []` extension + re-digest + golden-template byte-for-byte update.
6. **(coverage — block) "Raises only, never lowers" ambiguous when a gate's catalog `max_attempts` > override.** Draft REPLACES; if a gate had `max_attempts=6` and override=5, draft lowers it (violates the rule). Fix: AC-RAISE-1 per-gate override is `max(catalog_default, override_value)`; AC-RAISE-2 multi-gate test asserts the rule.
7. **(consistency — block) "Exactly one event per invocation" contradicts the draft event field `gate_id: str` (singular).** Multi-gate runs would either emit N events or carry one wrong `gate_id`. Fix: AC-EVT-FIELD-1 omits singular `gate_id`; carries `affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...]` (frozen Pydantic value type per S7-04 `RepoLockHolder` precedent); AC-EVT-COUNT-1 multi-gate test pins exactly one event.
8. **(coverage / security — block) `--operator-ack` invocation-only rule unenforced.** Per ADR-0014 humans-always-merge, an env var `CODEGENIE_OPERATOR_ACK=1` or YAML override must NOT bypass operator intent. Fix: AC-INV-1 asserts env-var / YAML cannot fire the override path; only the explicit CLI flag works.
9. **(coverage — block) `--max-attempts-override` upper bound missing.** `AttemptNumber` is bounded 1..1024 per S1-04 AC-I-1. Draft only had `min=3`. Fix: AC-RANGE-1 `click.IntRange(min=3, max=1024)`; parametrized rejection of `[9999, 10000, -1, 0, 1, 2]`.
10. **(test-quality — block) "No event on failure path (missing ack)" has no test.** A mutation emitting the event before the ack check passes the happy-path AC. Fix: AC-EVT-NEG-1 via `structlog.testing.capture_logs()` asserts ZERO entries with `event == EVENT_GATE_ATTEMPTS_OVERRIDE` on the rejection path.
11. **(test-quality — block) `monkeypatch.setattr("codegenie.audit.emit", ...)` patches nothing.** The real emit path is `structlog.get_logger().info(EVENT_*, **fields)`. Fix: AC-TEST-EVT-1 uses `structlog.testing.capture_logs()` (S5-02 AC-OBS-1 precedent).
12. **(test-quality — block) `monkeypatch.setattr("codegenie.orchestrator.run", ...)` patches nothing.** The orchestrator is `codegenie.transforms.orchestrator.RemediationOrchestrator`. Fix: AC-TEST-ORC-1 + AC-ORC-1..-4 — CLI exposes `make_orchestrator: Callable[..., RemediationOrchestrator]` as a module-level DI port; tests inject a fake; production uses the default. Cross-phase additive amendment: `RemediationOrchestrator.__init__` gains three keyword-only kwargs (`sandbox_backend=None`, `max_attempts_override=None`, `allow_test_network=False`) with safe defaults.
13. **(design — harden) Functional core / imperative shell split missing.** S5-02 + S7-04 + S3-01 established the pattern (fourth concrete consumer — past rule-of-three). Fix: AC-PURE-1 `_require_operator_ack(value, *, operator_ack) -> None` pure helper; AC-PURE-2 `_raise_max_attempts(*, catalog: AttemptNumber, override: AttemptNumber) -> AttemptNumber` pure helper; AST scan asserts no I/O / `structlog.*` in either body.
14. **(design — harden) Click-callback declaration-order trick is fragile.** Per Click semantics, `ctx.params` is populated as parameters are processed; declaring `--operator-ack` before `--max-attempts-override` makes the validator order-correct, but a future contributor reordering is silent breakage. Fix: AC-DECL-1 `inspect.signature` parameter-order test; AC-DECL-2 source-comment requirement (mirrors S5-02 AST scan precedent); AC-DECL-3 documents the alternative (`result_callback`) path.
15. **(design — harden) `GateAttemptsOverrideEvent` frozen-Pydantic value type makes illegal log payloads unrepresentable.** Mirrors S7-04 `RepoLockHolder` (4th concrete consumer). Fix: AC-MODEL-1..-2 introduce `GateAttemptsOverrideEntry` + `GateAttemptsOverrideEvent` in new module `src/codegenie/gates/events.py` (cold-start fence row + module purity AC).

Full audit log: [`_validation/S8-02-remediate-flags-operator-ack.md`](_validation/S8-02-remediate-flags-operator-ack.md) — 41 findings (12 block, 23 harden, 6 nit). No Stage-3 research was needed — every gap was answerable from in-repo HARDENED sources (S1-01..S8-01) + the four cited Phase-5 ADRs + production ADR-0014 + Click / Pydantic docs already pinned by arch §839.

## Context

`codegenie remediate` is the operator-facing entry point that drives Phase 3 → 4 → 5 end-to-end. Phase 5 introduces three new flags that must compose with existing flags without breaking them and must enforce one explicit safety interlock: `--max-attempts-override` is acknowledged operator override of the production-ADR-0014 three-retry default and may only proceed with `--operator-ack`. This story wires those flags, the Click validator that rejects missing acknowledgement with exit code 2, and the `gate.attempts_override` audit event that the override path emits exactly once.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — CLI surface (codegenie sandbox)` — the three flags' exact spelling and semantics.
  - `../phase-arch-design.md §Cross-cutting concerns — Decision points and defaults` — override raises (never lowers) the cap; one audit event per invocation.
  - `../phase-arch-design.md §Edge cases §14` — `--max-attempts-override 5` without `--operator-ack` is Click exit 2; precise error message.
  - `../phase-arch-design.md §Open questions §3` — `--allow-test-network` widens `egress_allowlist` and leaves `trace.new_endpoints` informational (do NOT promote to failed); `test_allow_test_network.py` exercises both paths.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — `--sandbox-backend auto` is the default; `auto_detect()` chooses; explicit `did` or `firecracker` overrides.
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — `--allow-test-network` interacts with the Firecracker nftables policy by extending the host-side allowlist; the policy module must accept the widened spec without code changes.
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — even with `--allow-test-network`, env-allowlist filtering is unchanged.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — three retries is the default; `--max-attempts-override` is the documented exception path requiring acknowledgement.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Operator ack on attempt override"`.
- **Existing code:**
  - `src/codegenie/cli/remediate.py` — existing remediate command; this story extends, does not rewrite.
  - `src/codegenie/cli/sandbox.py` (S8-01) — for shared `--sandbox-backend` option definition (move to a shared helper if needed).
  - `src/codegenie/audit/events.py` — emit `gate.attempts_override` here, mirroring existing audit-event constants.

## Goal

Wire `--sandbox-backend {did,firecracker,auto}`, `--max-attempts-override <int>` (gated by `--operator-ack`), and `--allow-test-network` onto `codegenie remediate`, with a Click validator that exits 2 on missing acknowledgement and a single `gate.attempts_override` audit event emitted exactly once per override invocation.

## Acceptance criteria

### A. Flag declaration (Click surface)

- [ ] **AC-SB-MAP-1.** `_CLI_TO_REGISTRY_BACKEND_NAME: Final[Mapping[str, Literal["docker_in_docker", "firecracker"]]] = MappingProxyType({"did": "docker_in_docker", "firecracker": "firecracker"})` exists in `src/codegenie/cli/_options.py` alongside S8-01's `_CLI_BACKEND_NAMES`. The mapping keys equal the non-`auto` choice values of `_CLI_BACKEND_NAMES`; the mapping values equal the `SandboxRun.backend` Literal set per S1-02 AC-7b. Parametrized type test.
- [ ] **AC-SB-MAP-2.** `--sandbox-backend` uses `click.Choice` derived from `_CLI_BACKEND_NAMES` (NOT a hard-coded list literal in `cli/remediate.py`); default is `"auto"`. Bogus value (e.g., `"dind"`, `"kvm"`, `""`) → `click.UsageError` exit 2 with verbatim substring `"Invalid value for '--sandbox-backend'"`.
- [ ] **AC-RANGE-1.** `--max-attempts-override` is `click.IntRange(min=3, max=1024, clamp=False)`; default `None`. Parametrized rejection: `[2, 1, 0, -1, 1025, 9999, 10_000]` each → Click `UsageError` exit 2.
- [ ] **AC-FLAG-1.** `--operator-ack` is `is_flag=True, default=False`. `--operator-ack=anything` → Click parser error exit 2 (Click's `is_flag` parameter rejects assignment).
- [ ] **AC-FLAG-2.** `--allow-test-network` is `is_flag=True, default=False`.
- [ ] **AC-DECL-1.** `inspect.signature(remediate.callback).parameters` order: `operator_ack` precedes `max_attempts_override` (so the callback on `--max-attempts-override` reads `ctx.params["operator_ack"]` correctly). Parameter-order regression test.
- [ ] **AC-DECL-2.** A source-line comment in `cli/remediate.py` explains the declaration-order coupling (S5-02 AC-PH-4 / S7-04 AC-PURE comment-discipline precedent). AST scan asserts the comment exists in the same docstring or comment block as the `--operator-ack` and `--max-attempts-override` click.option decorators.
- [ ] **AC-DECL-3.** Notes for the implementer cite the alternative `@remediate.result_callback` path (order-independent); the chosen path is the inline callback with the declaration-order comment.

### B. Operator-ack rejection path (no audit event)

- [ ] **AC-MSG-MISSING-ACK.** `codegenie remediate --cve CVE-2026-0001 ./fixture --max-attempts-override 5` (no `--operator-ack`) → exit code 2; stderr (or `result.output`) contains the verbatim substring `"--max-attempts-override requires --operator-ack"`.
- [ ] **AC-EVT-NEG-1.** On the missing-ack rejection path, `structlog.testing.capture_logs()` contains ZERO entries with `event == EVENT_GATE_ATTEMPTS_OVERRIDE`. Mutation witness: an implementer emitting the event before the ack check fails this test.
- [ ] **AC-INV-1.** Setting `CODEGENIE_OPERATOR_ACK=1` env var (or any other Pydantic `BaseSettings` route, including a `.codegenie/config.yaml` entry) has NO effect. Only the explicit `--operator-ack` CLI flag enables the override path. Parametrized over `[env-var, repo-yaml, user-yaml]`. The Pydantic `BaseSettings` field set excludes `operator_ack` (ADR-0014 humans-always-merge).

### C. Override-application path

- [ ] **AC-RAISE-1.** Per-gate override is `max(catalog_default, override_value)`. If a gate's catalog `max_attempts == 6` and the override is `5`, the resolved per-gate `max_attempts == 6` (the override does NOT lower). If the catalog is `2` and override is `5`, resolved is `5`.
- [ ] **AC-RAISE-2.** Multi-gate fixture (gate A `max_attempts=2`, gate B `max_attempts=6`, override `5`) → gate A's resolved policy has `max_attempts=5`; gate B's resolved policy has `max_attempts=6` (unchanged).
- [ ] **AC-COPY-1.** AST scan on `src/codegenie/cli/remediate.py` (or the call site that applies the override) asserts the substring `model_copy(update={"max_attempts":` exists — the resolved `RetryPolicy` is produced via `model_copy`, never via raw construction or in-place mutation (frozen-safe).
- [ ] **AC-COPY-2.** Hypothesis property test: for `override ∈ [3, 1024]` and `catalog_default ∈ [1, 1024]`, the resolved policy satisfies `policy.max_attempts == max(catalog_default, override)` AND `isinstance(policy.max_attempts, int)` AND `1 <= policy.max_attempts <= 1024`.
- [ ] **AC-MSG-RANGE.** `--max-attempts-override 9999 --operator-ack` → exit 2; output contains the verbatim Click `IntRange` substring `"is not in the range"` AND the substring `"<=1024"`.
- [ ] **AC-PURE-2.** `_raise_max_attempts(*, catalog: AttemptNumber, override: AttemptNumber) -> AttemptNumber` is a module-level pure helper in `cli/remediate.py` (or `cli/_options.py`); returns `AttemptNumber(max(catalog, override))`; AST scan asserts no `structlog.*`, no `os.environ`, no `Path.*`, no `subprocess.*` in the function body.

### D. Audit event (single per invocation)

- [ ] **AC-EVT-IMPORT-1.** `from codegenie.gates.logging import EVENT_GATE_ATTEMPTS_OVERRIDE` succeeds; the constant is imported from S1-01's canonical table, NOT redefined. AST scan asserts no other module in `src/codegenie/` assigns `EVENT_GATE_ATTEMPTS_OVERRIDE`.
- [ ] **AC-MODEL-1.** `class GateAttemptsOverrideEntry(BaseModel)` exists in `src/codegenie/gates/events.py` with `model_config = ConfigDict(extra="forbid", frozen=True)` and fields `gate_id: str`, `default_max_attempts: AttemptNumber`, `override_max_attempts: AttemptNumber`. `model_config['frozen'] is True` and `model_config['extra'] == 'forbid'` (direct introspection).
- [ ] **AC-MODEL-2.** `class GateAttemptsOverrideEvent(BaseModel)` exists in `src/codegenie/gates/events.py` with `model_config = ConfigDict(extra="forbid", frozen=True)` and fields `operator_ack: bool`, `affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...]`, `invocation_id: str`, `workflow_id: str`, `run_id: str`. `affected_gate_overrides` is a tuple (immutable), not a list.
- [ ] **AC-EVT-FIELD-1.** The audit event payload has NO singular `gate_id` field. Per-gate detail lives inside the `affected_gate_overrides` tuple.
- [ ] **AC-EVT-COUNT-1.** Multi-gate fixture (two gates) with `--max-attempts-override 5 --operator-ack` → captured logs contain EXACTLY ONE entry with `event == EVENT_GATE_ATTEMPTS_OVERRIDE`; that entry's `affected_gate_overrides` has length 2; each entry's `default_max_attempts` and `override_max_attempts` reflect the per-gate `max(catalog, override)` rule.
- [ ] **AC-TEST-EVT-1.** Tests use `structlog.testing.capture_logs()` (S5-02 AC-OBS-1 precedent); assertions reference the `EVENT_GATE_ATTEMPTS_OVERRIDE` constant (NOT the bare string `"gate.attempts_override"`).
- [ ] **AC-INV-EVT-1.** Metamorphic invariant across every happy-path test: `count(captured where event == EVENT_GATE_ATTEMPTS_OVERRIDE) == 1` AND `entry.operator_ack is True` AND `len(entry.affected_gate_overrides) >= 1`.

### E. `--allow-test-network` plumbing

- [ ] **AC-POLICY-1.** `tools/policy/sandbox-policy.yaml` is extended additively with a new top-level section `test_network:\n  extra_hosts: []` (default empty list). No existing key renamed or re-valued.
- [ ] **AC-POLICY-2.** `tools/digests.yaml#sandbox.policy_yaml` is re-pinned to `blake3.blake3(Path("tools/policy/sandbox-policy.yaml").read_bytes()).hexdigest(length=16)` (32 lowercase hex chars, BLAKE3-128). `re.fullmatch(r"^[a-f0-9]{32}$", value)` matches.
- [ ] **AC-POLICY-3.** `tests/golden/sandbox-policy.yaml.template` (S3-05 AC-GOLDEN-2 chain) is updated byte-for-byte; `test_sandbox_policy_matches_arch_template` (S3-05 AC-GOLDEN-3) remains green.
- [ ] **AC-POLICY-4.** Reading `test_network.extra_hosts` returns `[]` when the section is omitted (back-compat with older repos pre-S8-02); reading from the updated policy returns a `list[str]`; a malformed `extra_hosts` (non-list, contains non-string) raises `PolicyYamlSchemaError`.
- [ ] **AC-POLICY-5.** The `sandbox/signals/policy.py` reader (S3-05) is extended additively with a `test_network_extra_hosts() -> list[str]` accessor; no existing accessor's signature or return type changes.
- [ ] **AC-WIDEN-LOC-1.** `SandboxSpecBuilder.__init__` gains a new keyword-only DI port `allow_test_network: bool = False`. `inspect.signature(SandboxSpecBuilder.__init__).parameters["allow_test_network"]` exists; kind is `KEYWORD_ONLY`; default is `False`.
- [ ] **AC-WIDEN-LOC-2.** When `allow_test_network=True`, `SandboxSpecBuilder.for_gate` appends the policy YAML's `test_network.extra_hosts` to `SandboxSpec.egress_allowlist` for every gate whose collapsed `network == "scoped"`. Gates with `network == "none"` are unchanged.
- [ ] **AC-WIDEN-LOC-3.** Post-widening `sandbox_spec_hash` is computed over the widened `egress_allowlist` (no out-of-band hash drift). Hash is deterministic across runs with identical inputs.
- [ ] **AC-WIDEN-LOC-4.** When `allow_test_network=False`, `sandbox_spec_hash` is byte-identical to the spec produced by the catalog alone (regression guard — Phase 9 cache key stability).
- [ ] **AC-TRACE-WIRE-1.** `--allow-test-network` does NOT add a field to `GateContext` (S1-04 frozen + `extra="forbid"`). Instead, the trace-signal collector (`collect_trace_signal`) is constructed by the orchestrator factory with an `allow_test_network: bool` keyword-only argument; the runner does not see the flag.
- [ ] **AC-TRACE-WIRE-2.** When `allow_test_network=True`, `collect_trace_signal` returns `TraceSignal(passed=True, details={"new_endpoints": [...], "allow_test_network": True})` even when new endpoints are observed (informational); when `allow_test_network=False`, the same observation returns `passed=False, details={"new_endpoints": [...]}`. Parametrized.
- [ ] **AC-NET-1.** Concrete env-filter assertion: inject a counting `filter_fn` into `SandboxSpecBuilder`; with `--allow-test-network`, `filter_fn.call_count >= 1` and the returned env contains zero denied substrings (ADR-0012 belt-and-suspenders).
- [ ] **AC-NET-2.** Post-widening `SandboxSpec.network == "scoped"` (NOT downgraded to `"none"`); the widened list extends, never replaces, the catalog `egress_allowlist`.
- [ ] **AC-NET-3.** `set(resolved_spec.env.keys()) ⊆ env_allowlist.ALLOWLIST | {prefix for prefix in env_allowlist.ALLOWLIST_PREFIXES}` (per S1-05 surface) — even with `--allow-test-network`.
- [ ] **AC-NET-WIRE-1.** Both `sandbox/did/network_policy.py` and `sandbox/firecracker/network_policy.py` consume `SandboxSpec.egress_allowlist` unchanged — no separate `allow_test_network` plumbing into the network-policy modules. The widening is observable only at the `SandboxSpec` boundary.
- [ ] **AC-NET-WIRE-2.** Golden iptables / nftables rule sets generated for `allow_test_network=True` include the `test_network.extra_hosts` entries (in append-order; S3-01 AC-PROP-5 reading).

### F. Backend resolution

- [ ] **AC-AUTO-1.** When `--sandbox-backend` is omitted (default `"auto"`), `auto_detect()` is called exactly once; `get_backend(...)` is NOT called. Inject counting fakes.
- [ ] **AC-AUTO-2.** When `--sandbox-backend firecracker` is explicit, `auto_detect()` is NOT called; `get_backend("firecracker")` is called exactly once. When `--sandbox-backend did` is explicit, `get_backend("docker_in_docker")` is called exactly once (per the `_CLI_TO_REGISTRY_BACKEND_NAME` mapping).
- [ ] **AC-PREC-1.** Pydantic `BaseSettings` precedence (arch §839): parametrized table `[(env="did", cli=None, expected="docker_in_docker"), (env="did", cli="firecracker", expected="firecracker"), (env=None, cli=None, expected="auto_detect"), (env="bogus", cli=None, expected=UsageError)]`. CLI flag wins over env var.
- [ ] **AC-FALL-1.** With `--sandbox-backend auto` on a no-KVM mock environment, captured logs contain EXACTLY ONE entry with `event == EVENT_SANDBOX_AUTO_DETECT_FALLBACK` and structured field `backend == "docker_in_docker"` (per S1-05 AC-AD-3).
- [ ] **AC-FALL-2.** With `--sandbox-backend firecracker` on a no-KVM mock, `auto_detect()` is NOT called; the eventual `get_backend("firecracker")` proceeds and the first sandbox `execute` call raises `FirecrackerKvmMissing`; the exit code is surfaced via `cli/_errors.py` `EXIT_CODE_FOR` (NOT a new exit code).

### G. `--help` text safety interlocks

- [ ] **AC-HELP-1.** `codegenie remediate --help` exits 0 and contains the following verbatim substrings (each a separate parametrized assertion):
  - `"--max-attempts-override requires --operator-ack"`
  - `"raises (never lowers) the cap"`
  - `"keeps trace.new_endpoints informational"`
- [ ] **AC-HELP-2.** `--help` output contains one example per flag combination (three substrings):
  - `"codegenie remediate --sandbox-backend firecracker"`
  - `"--max-attempts-override 5 --operator-ack"`
  - `"--allow-test-network"`

### H. Open/Closed + functional core

- [ ] **AC-OC-1.** AST scan on `src/codegenie/cli/remediate.py` asserts no string literal in `{"docker_in_docker", "firecracker"}` exists outside imports from `cli/_options.py`. Mirrors S8-01's `_CLI_BACKEND_NAMES` fence — extends `tests/fence/test_cli_sandbox_backend_addition.py` with a new path entry.
- [ ] **AC-OC-2.** Phase 7's chainguard backend slots in by appending one row to `_CLI_TO_REGISTRY_BACKEND_NAME` + one row to `_CLI_BACKEND_NAMES` (additive) + one `@register_sandbox_backend("chainguard")` decoration — zero edits to `cli/remediate.py`. Documented in Out of scope.
- [ ] **AC-PURE-1.** `_require_operator_ack(value: int | None, *, operator_ack: bool) -> None` is a module-level pure helper (in `cli/remediate.py` or `cli/_options.py`). When `value is not None and not operator_ack`, raises `click.UsageError("--max-attempts-override requires --operator-ack")`. AST scan asserts no `structlog.*`, no `os.environ`, no `Path.*`, no `subprocess.*` in the function body. Direct unit tests cover all four input combinations.
- [ ] **AC-FUTURE-1.** Both new pure helpers and `gates/events.py` begin with `from __future__ import annotations` as the first statement after the module docstring (S5-02 / S7-04 / S3-01 module-purity precedent).

### I. Orchestrator amendment (Phase 3 additive)

- [ ] **AC-ORC-1.** `codegenie.transforms.orchestrator.RemediationOrchestrator.__init__` gains three additive keyword-only parameters: `sandbox_backend: str | None = None`, `max_attempts_override: AttemptNumber | None = None`, `allow_test_network: bool = False`. All defaults are "no-op" so Phase 3-only invocations remain byte-stable.
- [ ] **AC-ORC-2.** `inspect.signature(RemediationOrchestrator.__init__)` snapshot test asserts the three new params are `KEYWORD_ONLY` with the documented defaults; the existing parameter set is unchanged in name and order (additive at the end).
- [ ] **AC-ORC-3.** When `sandbox_backend is None` (Phase 3-only invocation), the orchestrator uses its existing default backend selection (back-compat). When `sandbox_backend in {"did", "firecracker"}`, the orchestrator routes through `get_backend(_CLI_TO_REGISTRY_BACKEND_NAME[sandbox_backend])`; when `sandbox_backend == "auto"`, the orchestrator calls `auto_detect()`.
- [ ] **AC-ORC-4.** Cross-phase amendment note appended to Phase 3 `ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md` (or a new Phase-5 ADR rider — pick the lighter touch) documenting that the orchestrator ctor accepts the three additive kwargs. The amendment is extension-by-addition compliant.

### J. Fences + structural defenses

- [ ] **AC-FENCE-1.** Cold-start matrix row added for `src/codegenie/gates/events.py` asserting the module imports nothing from `{anthropic, openai, langgraph, langchain, transformers, sentence-transformers, torch, subprocess, docker}` and no `os.system`, no `eval`, no `exec`.
- [ ] **AC-FENCE-2.** S8-01's `tests/fence/test_cli_sandbox_backend_addition.py` extends its `_CLI_SCAN_PATHS` (or equivalent) list to include `src/codegenie/cli/remediate.py`. AST scan asserts no `from codegenie.sandbox.did import …` / `from codegenie.sandbox.firecracker import …` direct backend imports in `cli/remediate.py`.

### K. Test harness + gating

- [ ] **AC-TEST-ORC-1.** `cli/remediate.py` exposes a module-level `make_orchestrator: Callable[..., RemediationOrchestrator]` DI port (default = `RemediationOrchestrator`); unit tests inject a fake orchestrator via `monkeypatch.setattr("codegenie.cli.remediate.make_orchestrator", fake_factory)`. NO `monkeypatch.setattr("codegenie.orchestrator.run", ...)` (that module does not exist).
- [ ] `tests/cli/test_remediate_flags.py` ≥ 90% line coverage on the new validator + flag-handler functions; exercises every failure-mode message string verbatim (per AC-MSG-* and AC-HELP-*).
- [ ] TDD plan's red tests exist, are committed, and turn green only when every AC above is met.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/cli src/codegenie/gates src/codegenie/sandbox/spec_builder.py src/codegenie/transforms/orchestrator.py`, `pytest tests/cli/test_remediate_flags.py tests/sandbox/test_spec_builder.py tests/gates/test_events.py tests/fence/test_cli_sandbox_backend_addition.py` all pass.

## Implementation outline

1. **Extend `src/codegenie/cli/_options.py` additively** (S8-01 created the module):
   - Append `_CLI_TO_REGISTRY_BACKEND_NAME: Final[Mapping[str, Literal["docker_in_docker", "firecracker"]]] = MappingProxyType({"did": "docker_in_docker", "firecracker": "firecracker"})`.
   - Export from `__all__`. Do NOT edit existing rows.
2. **Add the four `click.option` decorators to `codegenie remediate`** in declaration order (Click `ctx.params` population order matters):
   - First: `@click.option("--operator-ack", is_flag=True, default=False, help="Acknowledge that --max-attempts-override raises the production-ADR-0014 three-retry default (humans always merge).")`.
   - Second: `@click.option("--max-attempts-override", type=click.IntRange(min=3, max=1024), default=None, callback=_validate_operator_ack_required, help="Raise (never lowers) the per-gate max_attempts; requires --operator-ack.")`.
   - Third: `@click.option("--sandbox-backend", type=click.Choice(tuple(_CLI_BACKEND_NAMES)), default="auto", help="Sandbox backend; auto → auto_detect().")`.
   - Fourth: `@click.option("--allow-test-network", is_flag=True, default=False, help="Widen egress_allowlist with tools/policy/sandbox-policy.yaml#test_network.extra_hosts; keeps trace.new_endpoints informational.")`.
   - Add a one-line source comment ABOVE the `--operator-ack` decorator explaining the declaration-order coupling (AC-DECL-2).
3. **Add the two pure module-level helpers** to `cli/remediate.py`:
   ```python
   def _require_operator_ack(value: int | None, *, operator_ack: bool) -> None:
       if value is not None and not operator_ack:
           raise click.UsageError("--max-attempts-override requires --operator-ack")

   def _raise_max_attempts(*, catalog: AttemptNumber, override: AttemptNumber) -> AttemptNumber:
       return AttemptNumber(max(catalog, override))
   ```
   The Click callback `_validate_operator_ack_required(ctx, param, value)` is a thin wrapper that reads `ctx.params["operator_ack"]` and delegates to `_require_operator_ack(value, operator_ack=...)`.
4. **Land the new module `src/codegenie/gates/events.py`** with the two frozen Pydantic value types (AC-MODEL-1 + AC-MODEL-2):
   ```python
   class GateAttemptsOverrideEntry(BaseModel):
       gate_id: str
       default_max_attempts: AttemptNumber
       override_max_attempts: AttemptNumber
       model_config = ConfigDict(extra="forbid", frozen=True)

   class GateAttemptsOverrideEvent(BaseModel):
       operator_ack: bool
       affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...]
       invocation_id: str
       workflow_id: str
       run_id: str
       model_config = ConfigDict(extra="forbid", frozen=True)
   ```
   `__all__` is sorted and exact. The module imports only stdlib + `pydantic` + `codegenie.types.identifiers` (cold-start fence row, AC-FENCE-1).
5. **Land the additive policy YAML extension** (AC-POLICY-1..-5):
   - Append `test_network:\n  extra_hosts: []` to `tools/policy/sandbox-policy.yaml` (end of file, before the trailing LF).
   - Compute the new BLAKE3-128 (32 hex chars): `python -c "import blake3, pathlib; print(blake3.blake3(pathlib.Path('tools/policy/sandbox-policy.yaml').read_bytes()).hexdigest(length=16))"`.
   - Update `tools/digests.yaml#sandbox.policy_yaml` to the new hex.
   - Update `tests/golden/sandbox-policy.yaml.template` byte-for-byte (S3-05 AC-GOLDEN-2 / AC-GOLDEN-3 chain).
   - Add `test_network_extra_hosts() -> list[str]` accessor to `src/codegenie/sandbox/signals/policy.py` (or wherever the policy reader lives per S3-05).
6. **Widen `SandboxSpecBuilder`** (AC-WIDEN-LOC-1..-4):
   - Add `allow_test_network: bool = False` to `SandboxSpecBuilder.__init__` as a new keyword-only DI port (additive — S3-01 AC-DI parameter set extends by 1).
   - Inside `for_gate`, after the catalog-derived `egress_allowlist` is assembled and BEFORE the `sandbox_spec_hash` is computed: if `self._allow_test_network` AND the collapsed `network == "scoped"`, extend `egress_allowlist` with `policy_reader.test_network_extra_hosts()`.
   - The hash is computed over the widened list (byte-identical to catalog-only when the flag is `False`).
7. **Update the orchestrator factory** (AC-ORC-1..-4):
   - `RemediationOrchestrator.__init__` gains three additive keyword-only kwargs: `sandbox_backend: str | None = None`, `max_attempts_override: AttemptNumber | None = None`, `allow_test_network: bool = False`.
   - Resolve the `SandboxClient`: `None → existing default; "auto" → auto_detect(); "did"/"firecracker" → get_backend(_CLI_TO_REGISTRY_BACKEND_NAME[name])`.
   - Build `SandboxSpecBuilder(catalog=..., allow_test_network=allow_test_network, ...)`.
   - When `max_attempts_override is not None`, for each gate's catalog `RetryPolicy`, produce the resolved policy via `policy.model_copy(update={"max_attempts": _raise_max_attempts(catalog=policy.max_attempts, override=max_attempts_override)})`. Collect the per-gate entries.
   - Emit exactly one `EVENT_GATE_ATTEMPTS_OVERRIDE` log record before the first gate runs, with the `GateAttemptsOverrideEvent.model_dump()` payload bound via `structlog.get_logger().info(EVENT_GATE_ATTEMPTS_OVERRIDE, **event.model_dump())`. NO emission on the rejection path (AC-EVT-NEG-1).
   - Construct `collect_trace_signal` with `allow_test_network=allow_test_network` (AC-TRACE-WIRE-1).
8. **Expose `make_orchestrator` DI port** in `cli/remediate.py` (AC-TEST-ORC-1):
   ```python
   make_orchestrator: Callable[..., RemediationOrchestrator] = RemediationOrchestrator
   ```
   The CLI calls `make_orchestrator(sandbox_backend=..., max_attempts_override=..., allow_test_network=..., ...).run(...)`. Unit tests `monkeypatch.setattr("codegenie.cli.remediate.make_orchestrator", fake_factory)`.
9. **Extend `tests/fence/test_cli_sandbox_backend_addition.py`** (AC-FENCE-2) — add `src/codegenie/cli/remediate.py` to the scanned-path list; the existing AST assertions cover it automatically.
10. **Update `--help` epilog** with the verbatim safety-interlock substrings (AC-HELP-1) and the three example invocations (AC-HELP-2).
11. **Cross-phase amendment note** appended to Phase 3 `ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md` (or a small Phase-5 ADR rider — choose the lighter touch) documenting the three additive `RemediationOrchestrator` ctor kwargs (AC-ORC-4).

## TDD plan — red / green / refactor

### Red

Test file path: `tests/cli/test_remediate_flags.py` (CLI tests), `tests/sandbox/test_spec_builder.py` (builder widening — extend existing S3-01 file), `tests/gates/test_events.py` (new — event models), `tests/fence/test_cli_sandbox_backend_addition.py` (extend S8-01 fence).

```python
# tests/cli/test_remediate_flags.py
from __future__ import annotations

import inspect
import os
from collections.abc import Callable

import pytest
import structlog
from click.testing import CliRunner

from codegenie.cli import cli
from codegenie.cli import remediate as remediate_module
from codegenie.cli._options import _CLI_TO_REGISTRY_BACKEND_NAME, _CLI_BACKEND_NAMES
from codegenie.gates.events import GateAttemptsOverrideEntry, GateAttemptsOverrideEvent
from codegenie.gates.logging import EVENT_GATE_ATTEMPTS_OVERRIDE
from codegenie.sandbox.logging import EVENT_SANDBOX_AUTO_DETECT_FALLBACK
from codegenie.types.identifiers import AttemptNumber


# ───────── A. Flag declaration ─────────

def test_sandbox_backend_choice_derives_from_kernel():
    # AC-SB-MAP-1, AC-SB-MAP-2
    param = next(p for p in remediate_module.remediate.params if p.name == "sandbox_backend")
    assert set(param.type.choices) == set(_CLI_BACKEND_NAMES)
    assert set(_CLI_TO_REGISTRY_BACKEND_NAME.keys()) == set(_CLI_BACKEND_NAMES) - {"auto"}
    assert set(_CLI_TO_REGISTRY_BACKEND_NAME.values()) == {"docker_in_docker", "firecracker"}


@pytest.mark.parametrize("bogus", ["dind", "kvm", ""])
def test_sandbox_backend_rejects_unknown(bogus):
    # AC-SB-MAP-2
    result = CliRunner().invoke(cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
                                       "--sandbox-backend", bogus])
    assert result.exit_code == 2
    assert "Invalid value for '--sandbox-backend'" in (result.output or "")


@pytest.mark.parametrize("bad", [2, 1, 0, -1, 1025, 9999, 10_000])
def test_max_attempts_override_range_rejected(bad):
    # AC-RANGE-1
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
              "--max-attempts-override", str(bad), "--operator-ack"],
    )
    assert result.exit_code == 2


def test_max_attempts_override_above_1024_message_pins_max():
    # AC-MSG-RANGE
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
              "--max-attempts-override", "9999", "--operator-ack"],
    )
    assert "is not in the range" in result.output
    assert "<=1024" in result.output


def test_operator_ack_is_pure_flag():
    # AC-FLAG-1 (=anything is rejected by Click)
    result = CliRunner().invoke(cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
                                       "--operator-ack=anything"])
    assert result.exit_code == 2


def test_param_declaration_order_pinned():
    # AC-DECL-1 — operator_ack must precede max_attempts_override in the param list
    names = [p.name for p in remediate_module.remediate.params]
    assert names.index("operator_ack") < names.index("max_attempts_override"), names


# ───────── B. Operator-ack rejection path ─────────

def test_max_attempts_override_without_ack_exits_2_with_message():
    # AC-MSG-MISSING-ACK
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001", "--max-attempts-override", "5"],
    )
    assert result.exit_code == 2, result.output
    assert "--max-attempts-override requires --operator-ack" in result.output


def test_no_audit_event_on_missing_ack():
    # AC-EVT-NEG-1 — mutation witness: an implementer emitting before the ack check fails this
    with structlog.testing.capture_logs() as captured:
        CliRunner().invoke(
            cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001", "--max-attempts-override", "5"],
        )
    override_events = [e for e in captured if e["event"] == EVENT_GATE_ATTEMPTS_OVERRIDE]
    assert override_events == []


@pytest.mark.parametrize("env_var", [
    {"CODEGENIE_OPERATOR_ACK": "1"},
    {"CODEGENIE_OPERATOR_ACK": "true"},
    {"CODEGENIE_REMEDIATE_OPERATOR_ACK": "1"},
])
def test_env_var_operator_ack_is_ignored(env_var, monkeypatch):
    # AC-INV-1 — env-var bypass forbidden (ADR-0014 humans-always-merge)
    for k, v in env_var.items():
        monkeypatch.setenv(k, v)
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001", "--max-attempts-override", "5"],
    )
    assert result.exit_code == 2
    assert "--max-attempts-override requires --operator-ack" in result.output


# ───────── C. Override-application path ─────────

def test_per_gate_override_is_max_not_replace(fake_orchestrator):
    # AC-RAISE-1 + AC-RAISE-2 — multi-gate: A(catalog=2) becomes 5; B(catalog=6) stays 6
    fake_orchestrator.gate_catalog = {"A": 2, "B": 6}
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
              "--max-attempts-override", "5", "--operator-ack"],
    )
    assert result.exit_code == 0
    assert fake_orchestrator.resolved_max_attempts == {"A": 5, "B": 6}


def test_override_applied_via_model_copy_ast_scan():
    # AC-COPY-1 — frozen-safe RetryPolicy rebuild via model_copy
    import inspect as _inspect
    source = _inspect.getsource(remediate_module)
    assert 'model_copy(update={"max_attempts":' in source


# AC-COPY-2 hypothesis property test
from hypothesis import given, strategies as st

@given(catalog=st.integers(min_value=1, max_value=1024),
       override=st.integers(min_value=3, max_value=1024))
def test_raise_max_attempts_pure_property(catalog, override):
    # AC-PURE-2 — direct unit test on the pure helper
    resolved = remediate_module._raise_max_attempts(
        catalog=AttemptNumber(catalog), override=AttemptNumber(override),
    )
    assert resolved == max(catalog, override)
    assert 1 <= resolved <= 1024


# ───────── D. Audit event ─────────

def test_audit_event_constant_imported_not_redefined():
    # AC-EVT-IMPORT-1
    from codegenie.gates.logging import EVENT_GATE_ATTEMPTS_OVERRIDE as canonical
    assert EVENT_GATE_ATTEMPTS_OVERRIDE is canonical
    assert canonical == "gate.attempts_override"


def test_event_models_frozen_and_extra_forbid():
    # AC-MODEL-1 + AC-MODEL-2
    for cls in (GateAttemptsOverrideEntry, GateAttemptsOverrideEvent):
        assert cls.model_config["extra"] == "forbid"
        assert cls.model_config["frozen"] is True


def test_event_payload_omits_singular_gate_id():
    # AC-EVT-FIELD-1
    assert "gate_id" not in GateAttemptsOverrideEvent.model_fields
    assert "affected_gate_overrides" in GateAttemptsOverrideEvent.model_fields


def test_single_audit_event_across_multi_gate_invocation(fake_orchestrator):
    # AC-EVT-COUNT-1 + AC-INV-EVT-1
    fake_orchestrator.gate_catalog = {"A": 2, "B": 6}
    with structlog.testing.capture_logs() as captured:
        result = CliRunner().invoke(
            cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
                  "--max-attempts-override", "5", "--operator-ack"],
        )
    assert result.exit_code == 0
    override_events = [e for e in captured if e["event"] == EVENT_GATE_ATTEMPTS_OVERRIDE]
    assert len(override_events) == 1
    payload = override_events[0]
    assert payload["operator_ack"] is True
    assert len(payload["affected_gate_overrides"]) == 2


# ───────── E. --allow-test-network plumbing ─────────

def test_allow_test_network_widens_egress_in_spec_builder(fake_orchestrator):
    # AC-WIDEN-LOC-1..-4, AC-NET-1, AC-NET-2, AC-NET-WIRE-1
    fake_orchestrator.policy_extras = ["registry.npmjs.org", "deno.land"]
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001", "--allow-test-network"],
    )
    assert result.exit_code == 0
    spec = fake_orchestrator.last_sandbox_spec
    assert spec.network == "scoped"  # AC-NET-2
    assert "deno.land" in spec.egress_allowlist
    # filter_fn was called at least once (env_allowlist still enforced)
    assert fake_orchestrator.filter_call_count >= 1  # AC-NET-1


def test_allow_test_network_off_byte_stable_hash(fake_orchestrator):
    # AC-WIDEN-LOC-4 — regression guard
    fake_orchestrator.policy_extras = ["deno.land"]
    h1 = fake_orchestrator.build_spec(allow_test_network=False).sandbox_spec_hash
    h2 = fake_orchestrator.build_spec(allow_test_network=False).sandbox_spec_hash
    assert h1 == h2


def test_env_allowlist_preserved_under_allow_test_network(fake_orchestrator):
    # AC-NET-3 — ADR-0012 belt-and-suspenders
    from codegenie.sandbox import env_allowlist
    fake_orchestrator.host_env = {"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "leak", "NODE_ENV": "test"}
    result = CliRunner().invoke(
        cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001", "--allow-test-network"],
    )
    spec = fake_orchestrator.last_sandbox_spec
    assert "ANTHROPIC_API_KEY" not in spec.env
    assert set(spec.env) <= set(env_allowlist.ALLOWLIST) | {f"{p}*" for p in env_allowlist.ALLOWLIST_PREFIXES}


@pytest.mark.parametrize("allow,expected_passed", [(True, True), (False, False)])
def test_trace_collector_receives_allow_test_network(fake_orchestrator, allow, expected_passed):
    # AC-TRACE-WIRE-1 + AC-TRACE-WIRE-2
    fake_orchestrator.new_endpoints_observed = ["evil.example.com"]
    args = ["remediate", "./fixture", "--cve", "CVE-2026-0001"]
    if allow:
        args.append("--allow-test-network")
    CliRunner().invoke(cli, args)
    assert fake_orchestrator.last_trace_signal.passed is expected_passed


# ───────── F. Backend resolution ─────────

def test_sandbox_backend_auto_calls_auto_detect(fake_orchestrator):
    # AC-AUTO-1
    fake_orchestrator.has_kvm = True
    CliRunner().invoke(cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001"])
    assert fake_orchestrator.auto_detect_call_count == 1
    assert fake_orchestrator.get_backend_call_count == 0


def test_sandbox_backend_did_maps_to_docker_in_docker(fake_orchestrator):
    # AC-AUTO-2 + AC-SB-MAP-1
    CliRunner().invoke(cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
                              "--sandbox-backend", "did"])
    assert fake_orchestrator.get_backend_calls == ["docker_in_docker"]


def test_sandbox_backend_precedence_cli_over_env(fake_orchestrator, monkeypatch):
    # AC-PREC-1
    monkeypatch.setenv("CODEGENIE_SANDBOX_BACKEND", "did")
    CliRunner().invoke(cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001",
                              "--sandbox-backend", "firecracker"])
    assert fake_orchestrator.get_backend_calls == ["firecracker"]


def test_auto_detect_fallback_event_on_no_kvm(fake_orchestrator):
    # AC-FALL-1
    fake_orchestrator.has_kvm = False
    with structlog.testing.capture_logs() as captured:
        CliRunner().invoke(cli, ["remediate", "./fixture", "--cve", "CVE-2026-0001"])
    fallbacks = [e for e in captured if e["event"] == EVENT_SANDBOX_AUTO_DETECT_FALLBACK]
    assert len(fallbacks) == 1
    assert fallbacks[0]["backend"] == "docker_in_docker"


# ───────── G. --help text safety interlocks ─────────

@pytest.mark.parametrize("needle", [
    "--max-attempts-override requires --operator-ack",
    "raises (never lowers) the cap",
    "keeps trace.new_endpoints informational",
    "codegenie remediate --sandbox-backend firecracker",
    "--max-attempts-override 5 --operator-ack",
    "--allow-test-network",
])
def test_help_contains_safety_interlock(needle):
    # AC-HELP-1 + AC-HELP-2
    result = CliRunner().invoke(cli, ["remediate", "--help"])
    assert result.exit_code == 0
    assert needle in result.output


# ───────── H. Open/Closed + purity ─────────

def test_pure_helper_require_operator_ack_no_io():
    # AC-PURE-1
    import ast
    source = inspect.getsource(remediate_module._require_operator_ack)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert not (isinstance(node.value, ast.Name) and node.value.id in {"structlog", "os", "subprocess"})


def test_pure_helper_raise_max_attempts_no_io():
    # AC-PURE-2 (companion of test above)
    import ast
    source = inspect.getsource(remediate_module._raise_max_attempts)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert not (isinstance(node.value, ast.Name) and node.value.id in {"structlog", "os", "subprocess"})


def test_no_hardcoded_backend_names_in_remediate_module():
    # AC-OC-1
    source = inspect.getsource(remediate_module)
    # ban naked literals outside the _options import
    for forbidden in ('"docker_in_docker"', '"firecracker"'):
        assert forbidden not in source or source.count(forbidden) == 0


# ───────── I. Orchestrator amendment ─────────

def test_orchestrator_ctor_has_three_additive_kwargs():
    # AC-ORC-1 + AC-ORC-2
    from codegenie.transforms.orchestrator import RemediationOrchestrator
    sig = inspect.signature(RemediationOrchestrator.__init__)
    for name, expected_default in [
        ("sandbox_backend", None),
        ("max_attempts_override", None),
        ("allow_test_network", False),
    ]:
        param = sig.parameters[name]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY
        assert param.default == expected_default


# ───────── K. DI port ─────────

def test_make_orchestrator_di_port_exists():
    # AC-TEST-ORC-1
    assert callable(remediate_module.make_orchestrator)


# ───────── Fixtures ─────────

@pytest.fixture
def fake_orchestrator(monkeypatch):
    # See conftest.py for the fake factory; injected via the make_orchestrator DI port.
    fake = _make_fake_orchestrator()
    monkeypatch.setattr("codegenie.cli.remediate.make_orchestrator", lambda **kw: fake.bind(kw))
    return fake
```

Plus the new tests in `tests/gates/test_events.py` (frozen + extra="forbid"), `tests/sandbox/test_spec_builder.py` extension (the `allow_test_network` DI port property tests covering AC-WIDEN-LOC-3 hash stability), and `tests/fence/test_cli_sandbox_backend_addition.py` extension (one new path entry — the existing AST scan does the work).

### Green

The validator is one `callback=` on `--max-attempts-override` calling `_require_operator_ack` (pure). The orchestrator factory accepts three additive kwargs; the override path produces per-gate `RetryPolicy.model_copy(update=...)` via `_raise_max_attempts` (pure) and emits ONE `EVENT_GATE_ATTEMPTS_OVERRIDE` log record via `structlog`. The SpecBuilder grows one DI port; the trace collector grows one kwarg. The policy YAML extension is additive (+ re-digest). The CLI / `_options.py` extension is one mapping row.

### Refactor

- Promote the `--sandbox-backend` Click decorator into `cli/_options.py` as a `shared_sandbox_backend_option()` factory once a third command needs it (Rule 2: three similar lines beat premature abstraction).
- If `--operator-ack` extends to a second / third "humans-always-merge" flag (e.g., `--force-promote`), extract the validator into an `OperatorAckPolicy: Callable[[click.Context], None]` registry under `cli/_errors.py` (NOT now — documented in Notes).
- Push the override semantics docstring ("raises only, single dial across gates, per-gate `max(catalog, override)`") onto `RemediationOrchestrator.__init__` so future flags don't accidentally allow per-gate overrides without a contract change.
- Once Phase 7 lands `chainguard`, audit that the only edits are one row each in `_CLI_TO_REGISTRY_BACKEND_NAME` and `_CLI_BACKEND_NAMES` plus one `@register_sandbox_backend("chainguard")` — the fence enforces the rest.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/cli/remediate.py` | Add the four flags + Click callback + pure helpers `_require_operator_ack`, `_raise_max_attempts` + `make_orchestrator` DI port. |
| `src/codegenie/cli/_options.py` (extends S8-01) | Append `_CLI_TO_REGISTRY_BACKEND_NAME: Final[Mapping[str, Literal[...]]]` alongside the existing `_CLI_BACKEND_NAMES`. Additive only. |
| `src/codegenie/gates/events.py` (NEW) | `GateAttemptsOverrideEntry` + `GateAttemptsOverrideEvent` frozen-Pydantic value types. Cold-start fence row required. |
| `src/codegenie/transforms/orchestrator.py` (Phase 3 amendment) | Three additive keyword-only ctor kwargs (`sandbox_backend`, `max_attempts_override`, `allow_test_network`) with safe defaults; override-application loop + structlog emit of the single `EVENT_GATE_ATTEMPTS_OVERRIDE` log record. |
| `src/codegenie/sandbox/spec_builder.py` (S3-01 amendment) | Add `allow_test_network: bool = False` to `__init__` as a new keyword-only DI port; widen `egress_allowlist` inside `for_gate` before hashing. |
| `src/codegenie/sandbox/signals/policy.py` (S3-05 extension) | Add `test_network_extra_hosts() -> list[str]` accessor. |
| `src/codegenie/sandbox/signals/trace.py` (or wherever `collect_trace_signal` is constructed) | Accept `allow_test_network: bool` kwarg; flip `passed` semantics on `new_endpoints` observation. |
| `tools/policy/sandbox-policy.yaml` | Append `test_network.extra_hosts: []` section (additive). |
| `tools/digests.yaml` | Re-pin `sandbox.policy_yaml` BLAKE3-128 (32 hex chars). |
| `tests/golden/sandbox-policy.yaml.template` | Update byte-for-byte to match the new policy YAML (S3-05 AC-GOLDEN-2 chain). |
| `tests/cli/test_remediate_flags.py` (NEW) | Red + green tests per the TDD plan. |
| `tests/gates/test_events.py` (NEW) | `extra="forbid", frozen=True` introspection + payload-field-set tests. |
| `tests/sandbox/test_spec_builder.py` (extends S3-01) | New AC-WIDEN-LOC-* property tests for the `allow_test_network` DI port. |
| `tests/fence/test_cli_sandbox_backend_addition.py` (extends S8-01) | Add `src/codegenie/cli/remediate.py` to the scanned-path list. |
| `docs/phases/03-vuln-deterministic-recipe/ADRs/0014-recipe-engine-surfaces-transform-via-transform-registry.md` (amendment note) | One-paragraph cross-phase amendment recording the three additive `RemediationOrchestrator` ctor kwargs. |

## Out of scope

- The full E2E run that exercises retry-2-recover with these flags — **S8-03** (this story ships only the unit-level proofs; the integration test under `tests/integration/sandbox/test_allow_test_network.py` is owned by S8-03 / the dedicated allow-test-network integration story).
- ADR audit and coverage closure — **S8-04**.
- New sandbox backends added by Phase 7 (chainguard) — they slot in additively via **one row each** in `_CLI_TO_REGISTRY_BACKEND_NAME` + `_CLI_BACKEND_NAMES` + one `@register_sandbox_backend("chainguard")` decoration. **Zero edits to `cli/remediate.py`** (enforced by AC-OC-1 fence).
- A `--max-attempts-override` that *lowers* the cap — explicitly out per arch §830 + AC-RAISE-1 (`max(catalog, override)`).
- Persisting `--operator-ack` across invocations or to disk — single-invocation only (AC-INV-1 — no Pydantic `BaseSettings` route).
- Per-gate `--max-attempts-override-<gate-id>` flag families — single-dial only (documented on the orchestrator docstring per Refactor §3).
- Adding `allow_test_network` to `GateContext` — explicitly disallowed (S1-04 frozen field set). Threaded via SpecBuilder DI port + trace-collector kwarg.

## Notes for the implementer

- **Event constant comes from `gates/logging.py`** (S1-01 HARDENED, AC table line 73). Do NOT redefine `EVENT_GATE_ATTEMPTS_OVERRIDE` anywhere. Do NOT create `codegenie.audit.events` — that module doesn't exist.
- **Emit via `structlog`, not via a hypothetical `codegenie.audit.emit`.** The pattern is `structlog.get_logger().info(EVENT_GATE_ATTEMPTS_OVERRIDE, **event.model_dump())` where `event` is a `GateAttemptsOverrideEvent` instance (S7-04 `RepoLockHolder` precedent — 4th concrete consumer of the frozen-value-type-for-structlog pattern).
- **The Click-callback declaration-order trick is fragile but correct.** Click populates `ctx.params` in *parameter declaration order on the command function*. Declaring `@click.option("--operator-ack", ...)` BEFORE `@click.option("--max-attempts-override", ..., callback=...)` ensures `ctx.params["operator_ack"]` is set when the callback runs. The source comment is mandatory (AC-DECL-2) so a future contributor doesn't reorder silently. The alternative is `@remediate.result_callback` — chosen path is the inline callback (one fewer indirection).
- **Override is `max(catalog, override)`, NOT replace.** A gate whose YAML catalog has `max_attempts=6` keeps 6 even when the operator passes `--max-attempts-override 5`. The "raises only" rule means lowering is forbidden. Audit event records both before and after per gate; gates whose `max == catalog` (override has no effect) are still recorded — explicit-is-better-than-implicit for audit consumers.
- **`RetryPolicy` is frozen.** Apply the override via `policy.model_copy(update={"max_attempts": AttemptNumber(_raise_max_attempts(catalog=policy.max_attempts, override=override))})`. AC-COPY-1 AST scan catches the lazy `policy.max_attempts = ...` mutation.
- **`SandboxSpec` is frozen.** The `--allow-test-network` widening lives in `SandboxSpecBuilder.for_gate` BEFORE the `sandbox_spec_hash` is computed. NEVER mutate the produced `SandboxSpec`. AC-WIDEN-LOC-3 + AC-WIDEN-LOC-4 cover both forks.
- **The policy YAML re-digest is load-bearing.** Forgetting to update `tools/digests.yaml#sandbox.policy_yaml` after appending `test_network` will trip the S3-05 digest-check tests on the next commit. Run the BLAKE3 computation step explicitly (AC-POLICY-2).
- **`GateContext` is closed.** Do NOT add `allow_test_network` as a field — S1-04 HARDENED freezes the field set. Thread the flag to `collect_trace_signal` directly at orchestrator-factory construction time (AC-TRACE-WIRE-1).
- **`--operator-ack` is NEVER in Pydantic `BaseSettings`** (AC-INV-1). Adding it would make the env var `CODEGENIE_OPERATOR_ACK=1` a silent bypass, violating ADR-0014 humans-always-merge. The flag is CLI-only.
- **One audit event per invocation, structured per-gate payload.** Multi-gate runs produce ONE event with `affected_gate_overrides: tuple[GateAttemptsOverrideEntry, ...]` of length N. Emitting N events for N gates fails AC-EVT-COUNT-1.
- **Future extension seam for `--operator-ack` (documented, NOT extracted now).** If Phase 6+ adds a second "humans-always-merge" flag (`--force-promote`, `--bypass-canary`, etc.), the third such flag triggers extraction of an `OperatorAckPolicy` registry under `cli/_errors.py` (chain-of-responsibility / specification pattern). Rule 2: three similar lines beat premature abstraction at two.
- **The `make_orchestrator` DI port pattern.** `cli/remediate.py` exposes `make_orchestrator: Callable[..., RemediationOrchestrator] = RemediationOrchestrator` as a module-level binding; the CLI calls `make_orchestrator(**kwargs)`. Unit tests inject a fake via `monkeypatch.setattr("codegenie.cli.remediate.make_orchestrator", fake_factory)`. Production paths are byte-stable.
- **`cli/_options.py` is the home for ALL shared CLI options across `codegenie remediate` and `codegenie sandbox` subcommands.** Phase 7's recipe-engine flag will slot in here. Documented for future contributors.
- **Phase 7 chainguard backend extension path (documented for the next sibling story):** (1) append `"chainguard": "chainguard_distroless"` to `_CLI_TO_REGISTRY_BACKEND_NAME`; (2) append `"chainguard"` to `_CLI_BACKEND_NAMES`; (3) add `@register_sandbox_backend("chainguard_distroless")` to the new backend class. The fence (AC-OC-1) catches any stray edit to `cli/remediate.py`.
