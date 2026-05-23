# Story S6-02 — Capability minting from K8s ServiceAccount mount

**Step:** Step 6 — Worker process model + LangGraph↔Temporal bridge
**Status:** Ready
**Effort:** M
**Depends on:** S6-01 (`build_worker`, `WorkerKind`)
**ADRs honored:** ADR-0007 (per-task-queue Capability allowlist is the trust root), ADR-0008 (typed-credential-class blocklist; Capability tokens are typed Pydantic records, not bearer strings — trust root is the *type*, not HMAC), production ADR-0043 (extension by addition: new Capability classes land additively in `codegenie.durable.capabilities`)

## Context

S6-01 brought up the worker processes; the activities they register still receive ad-hoc capability objects constructed in test fixtures. In production, a worker on the `vuln-remediation-node-npm` queue must NOT be able to mint an `EventLogWriteCapability` for an event `kind` outside its allowlist, or mint a `PrOpenCapability` for a repo outside the active workflow's allowlist. The trust root, per ADR-0008, is the **typed Pydantic record** of the Capability (not an HMAC bearer token) — but minting must be gated at worker startup so a compromised worker process literally cannot construct the Capability instance for a kind it isn't allowed.

This is the load-bearing G9 ("per-task-queue credential blast radius") seam. After this story:
- `vuln-remediation-node-npm` worker can mint `EventLogWriteCapability(allowed_kinds={PluginResolved, BundleBuilt, RouteDecided, TrustGatePassed, TrustGateFailed, RecipeApplied, PatchApplied, PrOpened, SubgraphPausedHITL, RouteStalenessDescent, RedactionFired})` but NOT `MergeOutcome` (that's reserved for the workflow worker which observes the `human_review_decision` signal).
- `system` worker can mint `EventLogWriteCapability` for the full `EventPayload` union (it IS the event-log appender) but NOT `PrOpenCapability` or `LlmSpendCapability`.
- Worker bootstrap reads `/var/run/secrets/codegenie/queue-identity` (K8s mount) in prod or `.env`-loaded fixture in dev; constructs the `CapabilityMint` and threads it into every activity invocation via the Worker's `interceptor` chain.

The whole point of two queues (ADR-0007) is the blast-radius reduction this story operationalizes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C8 — Worker process model` — "Capability minting happens at worker startup: each worker process reads its task-queue identity from the K8s ServiceAccount mount (`/var/run/secrets/codegenie/queue-identity`) and constructs the `Capability` types it is allowed to mint."
  - `../phase-arch-design.md §Edge case #20` — "Capability minted by wrong task queue → Activity fails with `CapabilityScopeError`; **G9 verification** for the audit case."
  - `../phase-arch-design.md §Sanitizer + the credential blocklist that does the work` L430–445 — typed-credential-class blocklist is the load-bearing check.
- **Phase ADRs:**
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — Consequences: "A worker on `vuln-remediation-node-npm` cannot mint an `EventLogWriteCapability` for kinds outside its allowlist; cannot mint a `PrOpenCapability` for repos outside the active workflow's allowlist."
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — typed-Pydantic-record framing; type is the trust root; no HMAC ceremony.
- **Existing code:**
  - `src/codegenie/durable/capabilities.py` (S1-06) — `EventLogWriteCapability`, `PrOpenCapability`, `LlmSpendCapability` Pydantic records with `allowed_kinds: frozenset[...]` shape.
  - `src/codegenie/types/credentials.py` (S1-01) — `SECRET_TYPES` registry.
  - `src/codegenie/durable/workers/__init__.py` (S6-01) — `build_worker` factory; this story extends it with a `mint: CapabilityMint` parameter threaded into activity-worker interceptors.
- **External:**
  - `temporalio.worker.Interceptor` — for the activity-input interceptor chain that injects the mint.
  - Kubernetes projected volume documentation (`/var/run/secrets/...` mount semantics; readable by the pod's UID only).

## Goal

Land `src/codegenie/durable/workers/_mint.py` defining `CapabilityMint(BaseModel)` (frozen) — the per-queue allowlist of which Capability shapes a worker may construct — and `load_mint(*, kind: WorkerKind, settings: DurableSettings) -> CapabilityMint` which reads the K8s ServiceAccount mount (`/var/run/secrets/codegenie/queue-identity`) in prod or an `.env`-loaded fixture in dev. Wire the mint into `build_worker` so every activity invocation on a worker receives only those Capabilities the worker is allowed to mint. The G9 adversarial test `tests/adv/test_capability_token_scope.py` asserts that a `vuln-remediation-node-npm` worker attempting to construct `EventLogWriteCapability(allowed_kinds={MergeOutcome})` raises `CapabilityScopeError` at mint time — before any activity runs.

## Acceptance criteria

### `CapabilityMint` shape

- [ ] **AC-1 — `CapabilityMint` is a frozen Pydantic record.** `src/codegenie/durable/workers/_mint.py` defines `class CapabilityMint(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields:
  - `queue: WorkerKind`
  - `event_log_allowed_kinds: frozenset[type[EventPayload]]` — the set of `EventPayload` variant classes this queue may write
  - `pr_open_repos: frozenset[RepoSlug] | None = None` — `None` ⇒ no PR-open capability; otherwise the allowlist of repos
  - `llm_spend_ceiling_usd: Decimal | None = None` — `None` ⇒ no LLM-spend capability
- [ ] **AC-1a — `mint_event_log_capability(kinds: frozenset[type[EventPayload]]) -> EventLogWriteCapability` is the only construction path.** Direct `EventLogWriteCapability(allowed_kinds=...)` from outside the worker module is rejected by an import-linter rule (see AC-7); the mint's method enforces `kinds <= self.event_log_allowed_kinds` or raises `CapabilityScopeError`. Test: attempt to mint a Capability for a kind outside the allowlist; assert `CapabilityScopeError` with the offending kind named.
- [ ] **AC-1b — `mint_pr_open_capability(repo: RepoSlug) -> PrOpenCapability` enforces the repo allowlist.** Mint a Capability for an allowed repo: success. For a disallowed repo: `CapabilityScopeError` with the offending repo named. For a `vuln-remediation-node-npm` worker whose `pr_open_repos` was `None` (system worker): any call raises `CapabilityScopeError("queue=system cannot mint PrOpenCapability")`.
- [ ] **AC-1c — `mint_llm_spend_capability(amount: Decimal) -> LlmSpendCapability` enforces the ceiling.** Amount ≤ ceiling: success. Amount > ceiling: `CapabilityScopeError`. None ceiling: any call raises.

### Per-queue allowlist defaults

- [ ] **AC-2 — `_DEFAULT_MINTS: dict[WorkerKind, CapabilityMint]` ships the Phase-9 defaults.** Module-level `Final`:
  - `WorkerKind.SYSTEM`: `event_log_allowed_kinds = <all 21 EventPayload variants>` (the system worker IS the appender); `pr_open_repos = None`; `llm_spend_ceiling_usd = None`.
  - `WorkerKind.VULN_REMEDIATION_NODE_NPM`: `event_log_allowed_kinds = {PluginResolved, BundleBuilt, RouteDecided, TrustGatePassed, TrustGateFailed, RecipeApplied, PatchApplied, PrOpened, SubgraphPausedHITL, RouteStalenessDescent, RedactionFired}` — NOT `WorkflowStarted` / `WorkflowCompleted` / `WorkflowTerminated` / `MergeOutcome` / `BudgetExhausted` / `ChainTamperDetected` (these belong to the workflow worker via system-queue dispatch); `pr_open_repos` defaults to the workflow's per-run allowlist (threaded via `WorkflowContext`); `llm_spend_ceiling_usd = Decimal("5.00")` per attempt.
  - `WorkerKind.WORKFLOW`: workflow worker does NOT directly mint capabilities (workflows are IO-free per ADR-0007 §C8); the registration is the empty `CapabilityMint(queue=WORKFLOW, event_log_allowed_kinds=frozenset(), pr_open_repos=None, llm_spend_ceiling_usd=None)`. The integration test asserts a workflow worker that attempts to mint anything raises immediately.
- [ ] **AC-2a — `_DEFAULT_MINTS` is exhaustive over `WorkerKind`.** Test: `set(_DEFAULT_MINTS) == set(WorkerKind)`. Adding a Phase-7.5 `VULN_REMEDIATION_PYTHON_PIP` requires landing a row here — the test forces the deliberate decision.
- [ ] **AC-2b — `MergeOutcome` is NOT in `VULN_REMEDIATION_NODE_NPM`'s allowlist.** Load-bearing per ADR-0007 §Consequences: the `MergeOutcome` `@critical_event` is emitted from the workflow body's signal handler (S5-02 happy path step "emits `MergeOutcome` (**synchronous** — `@critical_event`)"), which dispatches through the `system` queue's `emit_event` activity. A vuln-remediation worker that could emit `MergeOutcome` would falsely close out a workflow without the human-review signal. Test asserts `MergeOutcome` is in `SYSTEM`'s allowlist (which threads workflow-body events) and NOT in `VULN_REMEDIATION_NODE_NPM`'s.

### Mount loader

- [ ] **AC-3 — `load_mint(*, kind, settings) -> CapabilityMint` reads the K8s ServiceAccount mount.** Production path: opens `/var/run/secrets/codegenie/queue-identity` (a JSON file), parses to a `MountIdentity` Pydantic record (`{queue: str, build_id: str, signature: str}`), asserts `MountIdentity.queue == kind.value` or raises `CapabilityMountError("worker started with kind=X but mount declares queue=Y")`, then looks up `_DEFAULT_MINTS[kind]`. The mount file's `signature` is verified against `settings.mount_pubkey` (`ed25519`); this prevents a compromised pod from forging its own queue identity.
- [ ] **AC-3a — Dev path reads from `.env`-loaded fixture.** When `settings.mount_path` is `None` (not set in env), load from `settings.dev_mint_fixture: dict[WorkerKind, CapabilityMint]` (defaults to `_DEFAULT_MINTS`). The test asserts the dev path and prod path produce byte-identical `CapabilityMint` objects for the same queue.
- [ ] **AC-3b — Missing mount in prod is fatal.** If `settings.mount_path` is set but the file doesn't exist OR `signature` verification fails, `load_mint` raises `CapabilityMountError`; the worker process exits non-zero before any activity runs. Test: `monkeypatch.setattr(Path, "exists", lambda self: False)` + assert `SystemExit` from `_main`.
- [ ] **AC-3c — Mount has restrictive permissions in prod.** The mount file's `stat().st_mode & 0o077 == 0` (no group/other access). On violation, raise `CapabilityMountError("mount /var/run/secrets/codegenie/queue-identity is world-readable")`. This catches an operator who mounted the secret with `defaultMode: 0644` instead of `0400`. Test: create a tempfile with `chmod 0644`; assert mount load rejects.

### Wiring into `build_worker`

- [ ] **AC-4 — `build_worker` accepts a `mint: CapabilityMint` keyword and threads it via interceptor.** The factory signature extends to `build_worker(*, kind, settings, client, mint: CapabilityMint | None = None) -> Worker`. `None` default ⇒ call `load_mint(kind=kind, settings=settings)`. The mint is wrapped in a `_CapabilityInterceptor(temporalio.worker.Interceptor)` that injects the mint into each activity's `info.headers` or `info.context` (whichever the Temporal Python SDK exposes); the activity code reads via `activity.payload_converter().from_payload(activity.info().headers["mint"], CapabilityMint)`.
- [ ] **AC-4a — Mint queue must match worker kind.** `build_worker(kind=SYSTEM, mint=CapabilityMint(queue=VULN_REMEDIATION_NODE_NPM, ...))` raises `CapabilityScopeError("mint queue=vuln-remediation-node-npm does not match worker kind=system")` at factory time. Defense against operator misconfig.
- [ ] **AC-4b — Workflow worker rejects a non-empty mint.** `build_worker(kind=WORKFLOW, mint=<any non-empty>)` raises. The workflow worker is IO-free; minting from it is a category error.

### G9 adversarial — the load-bearing test

- [ ] **AC-5 — `tests/adv/test_capability_token_scope.py` ships the G9 audit-case evidence.** Three concrete adversarial paths, parametrized:
  - **AC-5a — Out-of-allowlist event kind.** A `VULN_REMEDIATION_NODE_NPM` worker's mint cannot mint `EventLogWriteCapability(allowed_kinds={MergeOutcome})`; raises `CapabilityScopeError`.
  - **AC-5b — Out-of-allowlist repo.** A `VULN_REMEDIATION_NODE_NPM` worker whose workflow context allows `{"acme/api"}` cannot mint `PrOpenCapability(repo="acme/secret-vault")`.
  - **AC-5c — System worker has no PR capability.** A `SYSTEM` worker calling `mint_pr_open_capability(...)` raises (`pr_open_repos is None`).
- [ ] **AC-5d — `CapabilityScopeError` carries forensic fields.** Error class has `queue: WorkerKind`, `attempted: str` (Capability shape name), `offending_value: str` fields. Test asserts the error's `__str__` includes all three. Without these, a production triage operator has no clue which worker tried to escalate.
- [ ] **AC-5e — Capability misuse emits `CapabilityScopeViolation` event.** Per `phase-arch-design.md §Edge case #20`, the failed mint also fires an event into the canonical log (so a `retry_histogram` or future projection can rollup near-misses across the portfolio). The event variant lands as part of S1-02's 21-variant union; this story asserts the wire-up (mint failure ⇒ `EventLog.append(CapabilityScopeViolation(...))` via the `system` queue's `emit_event` capability — this is one of the few cases the system queue's broader allowlist is load-bearing).

### Mount-path code-path identity

- [ ] **AC-6 — Dev mount path and prod mount path produce byte-identical `CapabilityMint` outputs.** `phase-arch-design.md §Step 6 §Risks`: "the capability-minting code must work identically in both; the test fixture should mock the mount path explicitly." Test: parametrize over `(dev_settings, prod_settings_with_fake_mount)`; load mint for each kind; assert `dev_mint == prod_mint` (Pydantic value equality). This catches the risk where a `.env` dev fixture and a K8s mount fixture diverge silently.

### Import-linter contract

- [ ] **AC-7 — `import-linter` rule: only `codegenie.durable.workers._mint` may construct `EventLogWriteCapability` / `PrOpenCapability` / `LlmSpendCapability` directly.** `make lint-imports` rule under a new contract name `codegenie.durable.capabilities-construction-restricted`. Every other module must go through `CapabilityMint.mint_*(...)`. The contract uses `import-linter`'s `forbidden` shape: `codegenie.durable.capabilities` may not be imported by anything except `codegenie.durable.workers._mint` and the tests. Deliberate-violation xfail fixture under `tests/fence/_violations/` so the rule is exercised.

### Gates

- [ ] **AC-8** — `mypy --strict src/codegenie/durable/workers/` clean.
- [ ] **AC-9** — `ruff check` + `ruff format --check` clean.
- [ ] **AC-10** — `make lint-imports` green (AC-7 contract live).
- [ ] **AC-11** — TDD plan's red test (no mint module exists; G9 adversarial fails) committed before green.

## Implementation outline

1. **`src/codegenie/durable/workers/_mint.py` (NEW)**: `CapabilityMint(BaseModel)` frozen; mint methods; `_DEFAULT_MINTS: Final` dict; `CapabilityScopeError`, `CapabilityMountError` exception classes; `MountIdentity(BaseModel)` for the JSON wire shape; `load_mint(*, kind, settings)`.
2. **`src/codegenie/durable/workers/_interceptor.py` (NEW)**: `_CapabilityInterceptor(Interceptor)` that injects the mint into `activity.info().headers`. Activities read via a thin `codegenie.durable.activities.context.current_mint() -> CapabilityMint` accessor.
3. **`src/codegenie/durable/workers/__init__.py` (EXTEND from S6-01)**: `build_worker` accepts `mint: CapabilityMint | None`; default-loads via `load_mint`; rejects queue-mismatched or workflow-kind-with-non-empty mint.
4. **`src/codegenie/events/payloads.py` (EXTEND from S1-02)**: add `CapabilityScopeViolation` variant (`kind: Literal["CapabilityScopeViolation"]`, `queue`, `attempted`, `offending_value`, `at: datetime`). The 21→22-variant union grows additively per ADR-0034.
5. **`src/codegenie/durable/config.py` (EXTEND from S6-01)**: add `mount_path: Path | None = None`, `mount_pubkey: bytes | None = None`, `dev_mint_fixture: dict[WorkerKind, CapabilityMint] | None = None`.
6. **Tests**:
   - `tests/unit/durable/workers/test_mint_construction.py` — `_DEFAULT_MINTS` exhaustive + `MergeOutcome` not in `vuln-remediation-node-npm`.
   - `tests/unit/durable/workers/test_load_mint.py` — prod path (with fake mount + ed25519 signature), dev path; equivalence; missing-mount fatal; world-readable rejected.
   - `tests/adv/test_capability_token_scope.py` — AC-5 suite (G9 audit case).
   - `tests/fence/_violations/test_capability_construction_violation.py` (xfail) — the deliberate-violation fixture for AC-7.
7. **`.import-linter` config (EXTEND)**: add the `codegenie.durable.capabilities-construction-restricted` contract.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/adv/test_capability_token_scope.py`

```python
from decimal import Decimal
import pytest
from codegenie.durable.workers import WorkerKind, load_mint
from codegenie.durable.workers._mint import CapabilityScopeError
from codegenie.events.payloads import MergeOutcome, PluginResolved

def test_vuln_worker_cannot_mint_merge_outcome(dev_settings):
    mint = load_mint(kind=WorkerKind.VULN_REMEDIATION_NODE_NPM, settings=dev_settings)
    # Allowed: PluginResolved is in the allowlist
    mint.mint_event_log_capability(frozenset({PluginResolved}))
    # Forbidden: MergeOutcome is NOT in the allowlist
    with pytest.raises(CapabilityScopeError) as excinfo:
        mint.mint_event_log_capability(frozenset({MergeOutcome}))
    assert "MergeOutcome" in str(excinfo.value)
    assert "vuln-remediation-node-npm" in str(excinfo.value)

def test_system_worker_has_no_pr_capability(dev_settings):
    mint = load_mint(kind=WorkerKind.SYSTEM, settings=dev_settings)
    with pytest.raises(CapabilityScopeError):
        mint.mint_pr_open_capability("acme/api")

def test_llm_ceiling_enforced(dev_settings):
    mint = load_mint(kind=WorkerKind.VULN_REMEDIATION_NODE_NPM, settings=dev_settings)
    mint.mint_llm_spend_capability(Decimal("3.00"))   # under ceiling
    with pytest.raises(CapabilityScopeError):
        mint.mint_llm_spend_capability(Decimal("10.00"))   # over Decimal("5.00")
```

Why it fails: `ModuleNotFoundError: codegenie.durable.workers._mint` and `cannot import name 'load_mint'`.

### Green — minimal pass
- Land `_mint.py` with `CapabilityMint` + `_DEFAULT_MINTS` + the mint methods + `CapabilityScopeError` + `CapabilityMountError`.
- Land `load_mint`; dev path reads `_DEFAULT_MINTS`.
- Land `CapabilityScopeViolation` event variant in `payloads.py`.

### Refactor
- Pull the prod-path mount-loading into a tiny `_mount_io.py` so the IO seam is testable in isolation (signature verification, perm check, JSON parse).
- Add structured-log `worker.mint.loaded` (queue, build_id) at load time and `worker.mint.violation` (queue, attempted, offending_value) on every `CapabilityScopeError` (these are the operator's near-miss canary).
- Confirm the `_CapabilityInterceptor` wraps both `intercept_activity` and `intercept_workflow_inbound`; workflows never see a non-empty mint by construction (AC-4b) so the workflow interceptor is a defense-in-depth no-op.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/workers/_mint.py` | NEW — `CapabilityMint`, `_DEFAULT_MINTS`, mint methods, `load_mint`, exception classes. |
| `src/codegenie/durable/workers/_mount_io.py` | NEW — file read, ed25519 signature verify, perm check; isolated for testability. |
| `src/codegenie/durable/workers/_interceptor.py` | NEW — `_CapabilityInterceptor` injects mint into activity headers. |
| `src/codegenie/durable/workers/__init__.py` | EXTEND — `build_worker(mint=...)`; queue-mismatch + workflow-with-mint rejections. |
| `src/codegenie/durable/activities/context.py` | NEW — `current_mint() -> CapabilityMint` accessor activities use. |
| `src/codegenie/events/payloads.py` | EXTEND — `CapabilityScopeViolation` variant; union grows 21→22. |
| `src/codegenie/durable/config.py` | EXTEND — `mount_path`, `mount_pubkey`, `dev_mint_fixture`. |
| `tests/unit/durable/workers/test_mint_construction.py` | NEW — `_DEFAULT_MINTS` exhaustive; `MergeOutcome` exclusion; mint method allow/deny. |
| `tests/unit/durable/workers/test_load_mint.py` | NEW — prod ed25519 path; dev path; missing-mount fatal; world-readable rejected. |
| `tests/adv/test_capability_token_scope.py` | NEW — G9 audit case (AC-5a/b/c/d/e). |
| `tests/fence/_violations/test_capability_construction_violation.py` | NEW xfail — exercises AC-7 import-linter rule. |
| `.importlinter` (or `pyproject.toml` `[tool.importlinter]`) | EXTEND — `codegenie.durable.capabilities-construction-restricted` contract. |

## Out of scope

- **Phase-16 Worker Versioning compatibility sets.** S6-01 stamps `build_id`; this story does not consume it.
- **HMAC bearer tokens or cryptographic Capability signatures.** Per ADR-0008, the trust root is the *typed Pydantic record*; no in-process HMAC ceremony. ed25519 in `MountIdentity` protects the mount-time identity assertion only, not in-flight Capability passes.
- **Full G9 worker-credential blast-radius test** — S8-03. This story ships the audit-case test for one privileged action (event kind / PR repo / LLM spend); S8-03 widens to four actions including cross-task-queue signal/terminate.
- **K8s manifests** — Phase 16. Phase 9 reads from `/var/run/secrets/codegenie/queue-identity`; the manifests that create the secret are deferred.
- **Per-workflow `pr_open_repos` injection from workflow context.** This story ships the queue-level allowlist; per-workflow narrowing (Capability mint at workflow start, not just worker start) lands as a follow-up if Phase 10 needs it. Currently AC-1b's `pr_open_repos` is queue-level static.

## Notes for the implementer

- **The trust root is the type, not HMAC** — per ADR-0008. Don't add `hmac.compare_digest` to `EventLogWriteCapability`; the mint method's `kinds <= self.event_log_allowed_kinds` is the check. If you reach for HMAC, re-read ADR-0008's Decision and "What does the work" sections.
- **`MergeOutcome` exclusion from `vuln-remediation-node-npm` is load-bearing.** A naive "give every queue every kind" default collapses the G9 blast-radius rationale. The list above is hand-curated against the S5-02 happy-path; if you add a kind, trace it to which body emits it and which queue's worker hosts that body.
- **Mount file is `0400` in prod (owner-read-only).** If you skip the perm check, an operator who mounts with `defaultMode: 0644` ships world-readable credentials to a multi-tenant node. The AC-3c test catches this; ship the check.
- **ed25519 signature on `MountIdentity`** — Phase 9 ships verification; the *signing* side (the operator tool that produces the mount file) is deferred to Phase 16's K8s-manifest story. For dev, the signature field can be `b""` and `mount_pubkey=None` skips verification. Document this honestly in the module docstring — don't pretend the dev path is cryptographically equivalent.
- **`_DEFAULT_MINTS` is `Final` and exhaustive over `WorkerKind`.** When Phase-7.5 adds `VULN_REMEDIATION_PYTHON_PIP`, the AC-2a test forces a new row here. Drift between `WorkerKind` and `_DEFAULT_MINTS` is the worst silent-failure mode this story can ship.
- **Workflow worker has an empty mint.** Per ADR-0007 §C8 §Internal structure: workflow worker is IO-free. AC-4b's structural rejection catches the operator who tries to mint a Capability from a workflow body (a workflow-determinism violation the AST fence may miss; ID and reject at worker construction).
- **Don't bypass the mint via direct Capability construction.** AC-7's import-linter contract is the structural defense; the deliberate-violation xfail proves the rule is live. If you find yourself wanting `EventLogWriteCapability(allowed_kinds=...)` outside `_mint.py`, you're either testing (use the xfail fixture pattern) or building a new minting site (extend `CapabilityMint`).
- **`CapabilityScopeViolation` event emission** uses the `system` queue's broader allowlist — this is one of the cases the system queue's wider mint is load-bearing. A vuln-remediation worker that hits a `CapabilityScopeError` cannot emit the violation event itself (it would just hit another `CapabilityScopeError`); instead, it raises the exception, the Temporal interceptor catches it, dispatches a synthetic `emit_event` activity on the `system` queue, then re-raises to fail the offending activity non-retryably.
- **Equivalence test between dev and prod paths (AC-6) is the most-likely-to-rot test.** If a contributor adds a new field to `MountIdentity` and forgets to update `_DEFAULT_MINTS`, the dev path's mint will diverge from prod silently. The AC-6 test asserts byte-identical equality — keep it.
- **`pr_open_repos: frozenset[RepoSlug] | None = None`** — `None` is "no PR capability", NOT "all repos." Python's truthy-falsy semantics on empty `frozenset()` and `None` differ; the `None` branch is the deny-all path. Document explicitly in the class docstring.
