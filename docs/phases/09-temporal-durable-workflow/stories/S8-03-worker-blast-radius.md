# Story S8-03 — G9 worker credential blast-radius adversarial

**Step:** Step 8 — Durability test pass + adversarial sweep + CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S6-03 (`TemporalVulnRemediationSut` bridge — exposes the worker shape under test; S6-02's capability-minting from K8s ServiceAccount mount is the load-bearing piece)
**ADRs honored:** P9-ADR-0007 (two task-queue partitioning — the per-queue capability allowlist is what this test attacks), P9-ADR-0008 (typed-credential blocklist — the type-system trust root, not HMAC), P9-ADR-0009 (humans always merge — `github_open_pr` allowlist scope is asserted here), production ADR-0035 (capability passing — the runtime-system honoring of "I have a token therefore I can act" boundary).

## Context

G9 ("Per-task-queue credential blast radius") is one of the four exit criteria S8 closes with adversarial evidence. The arch design names this test explicitly (§Goals item 9 line 24, §Testing strategy line 1062, §Adversarial sweep). The promise: a **compromised** activity worker — assume the attacker has full code execution inside the worker process, and the K8s ServiceAccount mount with that worker's queue identity — still cannot reach beyond its queue's allowlist. The four privileged actions enumerated:

1. **(a)** Open PRs outside the active workflow's allowlist (the `github_open_pr` activity's `PrOpenCapability` is minted with a repo-scoped GitHub token, not a broad PAT — a worker for plugin-A cannot open PRs for plugin-B's repos).
2. **(b)** Write events of a `kind` outside its task queue's allowlist (the `EventLogWriteCapability` is constructed at worker startup with a `kinds: frozenset[Literal[...]]` allowlist — events outside the set fail typed validation at `seal()`).
3. **(c)** Signal/terminate a workflow on a *different* task queue (the worker's Temporal client identity is scoped to its task queue; cross-queue signal attempts fail at the Temporal SDK level).
4. **(d)** Read `events.events` rows for workflows other than its own (the `read_role` Postgres grant is scoped per-queue — a worker that tries `SELECT * FROM events.events WHERE workflow_id = <foreign_wid>` gets zero rows or a permission error).

The mechanism: a test fixture builds a **deliberately-malicious worker** — same shape as the production worker, but the activity body tries each of the four privileged actions. Each attempt is asserted to fail with a specific typed error (not a generic `Exception`). The test is structured as a four-row parametrize so each blast-radius failure mode is one independent assertion — a regression in one (e.g., GitHub token scope widening) does not hide regressions in the others.

The framing is **type-system-as-trust-root** (ADR-0008), not runtime-signing. The capability types declared in S1-06 are the gates — `PrOpenCapability(repo=Repo("plugin-a/X"))` simply does not have a field that says "I can open PRs in plugin-b/X". The test asserts the type-system gate holds even under malicious worker code.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals item 9` (line 24) — G9 acceptance phrasing.
  - `../phase-arch-design.md §Testing strategy §Adversarial sweep` (line 1062) — names this test.
  - `../phase-arch-design.md §Capability discipline` — explains the four privileged actions and how typed capabilities gate each.
- **Phase ADRs:**
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — the partitioning that makes per-queue allowlists possible.
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — type-system trust root.
- **Production ADRs:** `../../production/adrs/0035-capability-passing-vs-llm-tool-discovery.md` — broader capability framework.
- **Stories that feed this:**
  - `S6-02-capability-minting.md` — where capabilities are constructed at worker startup; the test attacks that boundary.
  - `S1-06-checkpointer-port-capabilities.md` — defines the `Capability` types (`EventLogWriteCapability`, `PrOpenCapability`, `LlmSpendCapability`).
  - `S2-03-alembic-initial-migration.md` — defines `application_role` Postgres grants; AC-4 (d) attacks that boundary.
- **High-level-impl:** `../High-level-impl.md §Step 8 §Features delivered` line 230.

## Goal

Ship `tests/adv/test_worker_credential_blast_radius.py` proving that a compromised worker on one task queue cannot perform any of the four privileged actions (a)–(d) above against workflows / repos / event kinds outside its allowlist.

## Acceptance criteria

**The test — four parametrized blast-radius cases (AC-1 through AC-4)**

- [ ] **AC-1** **(a) GitHub PR scope:** a worker bound to task queue `vuln-remediation-node-npm` for `repo=org/plugin-a` is dispatched an activity that attempts to call `github_open_pr(repo=Repo("org/plugin-b"), ...)`. The attempt fails with a typed `CapabilityScopeError("PrOpenCapability does not cover repo org/plugin-b")` — the exception type and message substring `"does not cover"` are asserted exactly. A `pytest.raises` is **not** sufficient on its own — the test also asserts no actual GitHub API call was attempted (e.g., via `respx` / `httpx_mock` recording zero requests to `api.github.com/repos/org/plugin-b/pulls`).
- [ ] **AC-2** **(b) Event kind allowlist:** the same worker attempts `emit_event(payload=ChainTamperDetected(...))` (a `@critical_event` variant that no `vuln-remediation-node-npm`-queue worker should be allowed to emit — that's the `system` queue's privilege). The attempt fails with a typed `EventKindNotAllowedError("kind 'ChainTamperDetected' not in EventLogWriteCapability.kinds for task queue 'vuln-remediation-node-npm'")` and the Postgres `events.events` table has zero new rows of that kind for that workflow.
- [ ] **AC-3** **(c) Cross-queue signal:** the worker (`vuln-remediation-node-npm` queue) attempts to `client.get_workflow_handle("foreign-workflow-on-system-queue").signal("cancel")`. The attempt fails — depending on Temporal SDK semantics, either with a `PermissionDeniedError`, a `WorkflowNotFoundError` (the worker's namespace scoping hides the foreign workflow), or a typed `TaskQueueScopeError` raised by a `BoundTemporalClient` adapter the bootstrap (S6-01) constructs. The story's job is to ensure **one** of those typed errors fires deterministically — surface the chosen mechanism in `_attempts/S8-03.md`. A naked `Exception` is unacceptable.
- [ ] **AC-4** **(d) Cross-workflow event-log read:** the worker attempts `event_log.read_workflow(workflow_id=<foreign_wid>)`. Implementation choice: either (i) `EventLog.read_workflow` is constructor-injected with a `ReadScope` capability that allow-lists workflow IDs minted at activity dispatch time (typed gate), OR (ii) the Postgres `application_role` is per-queue, with a row-level-security policy or per-queue grant that fails the underlying `SELECT` with `psycopg.errors.InsufficientPrivilege`. Either works; the chosen route is surfaced in `_attempts/S8-03.md`. The test asserts the typed error fires + (under route (ii)) that the Postgres logs record the denied SELECT (so a forensic SOC review sees the attempt).

**Test infrastructure (AC-5 through AC-7)**

- [ ] **AC-5** `tests/adv/test_worker_credential_blast_radius.py` parametrizes over the four cases (`@pytest.mark.parametrize("blast_radius_case", ["pr_scope", "event_kind", "cross_queue_signal", "cross_workflow_read"])`). Each case is independent — a failure in case 1 does not skip cases 2–4.
- [ ] **AC-6** A fixture `compromised_worker_factory(queue, allowed_repos, allowed_event_kinds)` constructs the malicious-activity worker. The factory is reused by the four cases — the only difference between cases is which privileged action the activity attempts. Surface in `tests/adv/_fixtures/compromised_worker.py`.
- [ ] **AC-7** The malicious activity bodies are **explicitly named** in the test file (not hidden behind `lambda`s or runtime-constructed functions) so a code reviewer can read the four attempted privileged actions in five seconds. Each malicious activity is decorated with `@activity.defn(name="adv_test_<action>")` and registered on the compromised worker only — they MUST NOT be registered on any production worker bootstrap. A meta-assertion (`tests/fence/test_adv_activities_not_in_production.py`) greps `src/codegenie/durable/workers/__init__.py` for `adv_test_` and asserts zero matches.

**Type-system framing (AC-8)**

- [ ] **AC-8** The story's docstring at the top of `test_worker_credential_blast_radius.py` names ADR-0008 (typed-credential blocklist) and ADR-0007 (two-queue partitioning) as the load-bearing ADRs. Each of AC-1's `CapabilityScopeError`, AC-2's `EventKindNotAllowedError`, etc., is defined as a `frozen` dataclass under `src/codegenie/durable/capabilities.py` (extending S1-06's shape), so a regression that downgrades any of them to a `RuntimeError("scope denied")` fails `mypy --strict` on the import (the test imports the type explicitly).

**Hygiene (AC-9 through AC-11)**

- [ ] **AC-9** Test runs in ≤ 30 s total (four parametrize cases × ≤ 7.5 s each).
- [ ] **AC-10** `ruff check`, `ruff format --check`, `mypy --strict` clean.
- [ ] **AC-11** `_attempts/S8-03.md` records (a) the chosen mechanism for AC-3 (which typed error fires) and AC-4 (typed scope vs Postgres grant), and (b) commit SHAs proving each case red-then-green during development.

## Implementation outline

1. Ensure typed errors exist under `src/codegenie/durable/capabilities.py`:
   - `CapabilityScopeError(BaseModel, frozen=True)` (already there from S1-06; verify).
   - `EventKindNotAllowedError` — NEW if not present.
   - `TaskQueueScopeError` — NEW if AC-3 picks route (iii).
2. Implement the `BoundTemporalClient` wrapper (if AC-3 route (iii) is chosen) under `src/codegenie/durable/workers/_bound_client.py` — wraps `temporalio.client.Client`, rejects `get_workflow_handle` calls whose target workflow is on a different task queue. Surface this in `_attempts/S8-03.md` as a real production code change, not just test scaffolding.
3. Add `tests/adv/__init__.py` if not present; add `tests/adv/_fixtures/__init__.py` + `tests/adv/_fixtures/compromised_worker.py` exposing `compromised_worker_factory(queue, allowed_repos, allowed_event_kinds)`.
4. Implement `tests/adv/test_worker_credential_blast_radius.py`:
   - Four `@activity.defn` malicious-activity functions named `adv_test_pr_scope`, `adv_test_event_kind`, `adv_test_cross_queue_signal`, `adv_test_cross_workflow_read`.
   - `@pytest.mark.parametrize` over the four cases.
   - Each case: build compromised worker via factory; dispatch the workflow that calls the malicious activity; assert typed error + no side effect.
5. Add `tests/fence/test_adv_activities_not_in_production.py` (AC-7 meta-fence).
6. Run `make check`. Record SHAs in `_attempts/S8-03.md`.

## TDD plan — red / green / refactor

**Red:** Write the four cases against typed errors that may not exist yet (`EventKindNotAllowedError`, `TaskQueueScopeError`). Import fails → test errors at collection → red. For the cases whose errors already exist (`CapabilityScopeError`), red comes from the production code path not yet raising them — e.g., `github_open_pr` may currently raise a generic `ValueError("bad repo")` if no scope-check guard exists. Red-by-construction.

**Green:** Ship the typed errors; ship the per-case scope checks in the production code paths (`github_open_pr`, `emit_event`, the `BoundTemporalClient`, the `EventLog.read_workflow` scope check). Each green is a real production hardening, not just a test artifact — this is the story that **wires the gates production needs**, with the adversarial test as the acceptance bar.

**Refactor:** The four typed errors all extend a common base `CapabilityScopeViolation(BaseModel, frozen=True)` with a `denied_capability: str` field; each subclass adds context. Avoid premature ABC if the subclasses don't share behavior — they share *shape*, which is the dataclass-inheritance pattern that's fine here (per ADR-0010's "anaemic types where sum types would do" guidance).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/capabilities.py` | EDIT — add `EventKindNotAllowedError`, `TaskQueueScopeError` (and a common base if used). Extend S1-06's surface. |
| `src/codegenie/durable/workers/_bound_client.py` | NEW (if AC-3 picks route (iii)) — `BoundTemporalClient` rejecting cross-queue handle access. |
| `src/codegenie/durable/activities/github_open_pr.py` | EDIT — add the scope-check guard that raises `CapabilityScopeError` on out-of-allowlist repo (S4-04 may have left this implicit). |
| `src/codegenie/durable/activities/emit_event.py` | EDIT — add the kind-allowlist check raising `EventKindNotAllowedError` (S4-02 may have left this implicit). |
| `src/codegenie/events/log.py` | EDIT — if AC-4 picks route (i), add `ReadScope` capability check; if route (ii), no change here (Postgres grants do it). |
| `tests/adv/__init__.py` | NEW (if missing) — package marker. |
| `tests/adv/_fixtures/__init__.py` | NEW — fixture package marker. |
| `tests/adv/_fixtures/compromised_worker.py` | NEW — `compromised_worker_factory` + the four malicious-activity definitions. |
| `tests/adv/test_worker_credential_blast_radius.py` | NEW — the four-case parametrized test. |
| `tests/fence/test_adv_activities_not_in_production.py` | NEW — meta-fence ensuring `adv_test_*` activities are not registered in production worker bootstrap. |

## Out of scope

- **Production-shape K8s ServiceAccount rotation testing** — Phase 16.
- **Cross-tenant isolation** — implicit in the per-queue allowlist; explicit multi-tenant story is Phase 10+.
- **Cassette-vs-live GitHub API** — the test uses `respx` / `httpx_mock` to assert zero outbound requests; live-API contract tests are out of scope.
- **`pgcrypto` column encryption** — explicitly ruled out by ADR-0009; do not retrofit "encrypt the token at rest" here.
- **Network-egress firewalling** — defense in depth lives elsewhere; this story tests the *capability* layer specifically.

## Notes for the implementer

- **This story does real production hardening, not just test scaffolding.** The scope-check guards in `github_open_pr` / `emit_event` (and the `BoundTemporalClient`) may not exist yet — S4-02 / S4-04 / S6-02 shipped the *types* but the runtime guards that consult them are the load-bearing piece this story finishes. If you find the guards already in place, great; if not, ship them in the same PR.
- **Naked `pytest.raises(Exception)` is insufficient.** Each case asserts a *specific* typed error + a specific message substring + zero side effect. Generic exception matching is the failure mode ADR-0008 was written to prevent.
- **The "no side effect" assertion is load-bearing.** It's not enough to say "the activity raised"; the test must confirm zero outbound GitHub call (AC-1's `respx`), zero new Postgres event-log row (AC-2's row count), zero Temporal signal delivered (AC-3's `WorkflowExecutionSignaled` history-event count == pre-attempt). Without the side-effect check, a future change that raises *after* the side effect ships goes undetected.
- **`BoundTemporalClient` is potentially a real new code path (S6-01 may have shipped the raw `temporalio.client.Client`).** Surface the choice in `_attempts/S8-03.md`. The lighter alternative is to rely on Temporal's namespace/task-queue scoping at the SDK level — verify in the Python SDK docs whether a worker on queue A can actually obtain a handle for a workflow on queue B (it likely can, because the Client object is shared infra). The wrapper is the deterministic-trust-root the test needs.
- **AC-4 routes (i) vs (ii):** route (i) (typed scope on `EventLog.read_workflow`) is more in the spirit of ADR-0008's type-system trust root; route (ii) (Postgres grants) is defense-in-depth. Prefer route (i) for AC-4's primary assertion, route (ii) as a secondary forensic-trail assertion if Postgres grants are wired in S2-03. Both layers green = strongest evidence.
- **The four typed errors land under `capabilities.py`, not `errors.py`.** Capability boundary violations are part of the capability surface; co-locating with the types they protect keeps cohesion high.
