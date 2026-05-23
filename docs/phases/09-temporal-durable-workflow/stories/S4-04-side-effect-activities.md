# Story S4-04 — `github_open_pr` + `sandbox_build_and_test` activities (the side-effecting pair)

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (`_POLICIES`)
**ADRs honored:** ADR-0009 (NO `merge_pr` activity — only `open_pr`; humans always merge); ADR-0008 (typed-credential blocklist on returns — `github_open_pr` never returns a `GitHubToken`); ADR-0010 (per-activity timeouts: `github_open_pr=60s`, `sandbox_build_and_test=15min`); ADR-0007 (both live on `vuln-remediation-node-npm` queue)

## Context

These are the two **side-effecting** Activities — the only ones in Phase 9 that touch the world outside Postgres + Temporal + the local filesystem. `github_open_pr` opens a PR via the GitHub API; `sandbox_build_and_test` spawns a Phase-5 `SubprocessJail` (microVM-equivalent for trusted-code execution). Both are heartbeat-emitting (5 s cadence) so Temporal's heartbeat-timeout (30 s) re-dispatches on worker SIGKILL without losing observable progress.

`github_open_pr` is also the **only** activity in Phase 9 that holds a `PrOpenCapability` (typed Pydantic record — ADR-0008's process-level capability, not cryptographic). The capability is minted at worker startup by S6-02 from the K8s ServiceAccount mount; this Activity threads it from the worker → wrapper → API call site (max 3 frames per the discipline). **No `github_merge_pr` Activity exists** — enforced by S4-07's fence; humans always merge (production ADR-0009).

`sandbox_build_and_test` wraps Phase-5's `SubprocessJail` — the trusted-code execution gate. Phase-5 already ships the sandbox primitive; this Activity is a thin Temporal wrapper that (a) marshals inputs as Pydantic, (b) records start/end events, (c) heartbeats during long sandbox runs, (d) idempotency-keys on `(patch_digest, build_inputs_digest)` so re-dispatch reuses the prior sandbox's result instead of re-running the build.

**Why idempotency is load-bearing here.** `github_open_pr` keyed on `(repo, attempt_id)` means: if the PR was already opened on attempt N and the activity worker SIGKILLs before the workflow records the result, the re-dispatched activity finds the existing PR and returns its URL — **not** opens a duplicate PR. Without this, every kill-resume cycle would create a fresh PR; G1's durability test (S8-01) would fail loud immediately, and even worse, the test repos would silently accumulate orphan PRs. The "exactly-once at the data layer" invariant is the cross-cutting Phase-9 contract; this story is the most visible enforcement point.

**Scope reminder.** This story ships the two Activity wrappers + their input/output models + capability threading. The PR opener's HTTP machinery is Phase-11-preview code (the Phase-9 architect's reference); the sandbox itself is Phase-5's `SubprocessJail`. Both pre-exist; this story does NOT re-author them.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` lines 482-486 — performance envelope.
  - `../phase-arch-design.md §Sequence diagrams Scenario 1` — `github_open_pr` → `PrOpened` (batched); position in the happy-path flow.
  - `../phase-arch-design.md §Sequence diagrams Scenario 4 — adversarial` — typed-credential blocklist rejects a `GitHubToken`-typed return at seal time; this Activity is the prototypical defense surface.
  - `../phase-arch-design.md §Tool-use safety` — "`github_open_pr` is the only Activity that calls a side-effectful external API … No `github_merge_pr` Activity exists — enforced by `tests/fence/test_no_merge_activity.py`."
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` — `PrOpenCapability` is a typed Pydantic record threaded explicitly; capability is process-level, not cryptographic.
  - `../ADRs/0010-activity-granularity-asymmetric.md` §Consequences — `sandbox_build_and_test` heartbeat cadence.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` — the autonomy boundary; no `merge_pr` Activity is fence-enforced (S4-07).
  - `../../../production/adrs/0008-secret-redaction.md` — the secret-redaction discipline this Activity respects.
- **Existing code (the wrapped layers):**
  - `src/codegenie/exec/` — Phase-5 `SubprocessJail` + `run_external_cli`; the sandbox primitive.
  - Phase-11-preview PR opener (path is forward-referenced; S4-04 may have to land a placeholder if Phase-11 preview isn't merged yet — see Notes §4).
- **Sibling stories:**
  - `S4-02-system-queue-activities.md` — the template (idempotence, seal, capability threading).
  - `S4-07-no-merge-fence.md` — the fence that asserts no `merge_pr` activity exists.
  - `S6-02-capability-minting.md` — where `PrOpenCapability` is constructed.

## Goal

Ship two `@activity.defn`-decorated functions under `src/codegenie/durable/activities/` — `github_open_pr.py` and `sandbox_build_and_test.py` — each (a) typed Pydantic input + `RedactedActivityResult`-derived output, (b) idempotent (`github_open_pr` on `(repo, attempt_id)`; `sandbox_build_and_test` on `(patch_digest, build_inputs_digest)`), (c) heartbeating every 5 s, (d) capability-threaded (`PrOpenCapability` on `github_open_pr`; `SandboxCapability` on `sandbox_build_and_test`), (e) registered on the `vuln-remediation-node-npm` task queue.

## Acceptance criteria

- [ ] **AC-1 — `github_open_pr` input/output.** `src/codegenie/durable/activities/github_open_pr.py` defines `class GithubOpenPrInput(BaseModel, frozen=True, extra="forbid")` with `repo: RepoSlug`, `branch: str`, `title: str`, `body_ref: BlobRef` (PR body crosses as `BlobRef` if >8 KiB), `patch_ref: BlobRef`, `attempt_id: AttemptId`, `capability: PrOpenCapability`. Defines `class GithubOpenPrOutput(RedactedActivityResult)` with `pr_url: PrUrl`, `pr_number: int`, `was_reused: bool` (True if idempotency matched a prior PR).
- [ ] **AC-2 — `github_open_pr` body shape + capability honoring.** Body: (a) idempotence check — `existing_pr = await github_client.find_pr_by_marker(repo, attempt_id)`; if exists, return `GithubOpenPrOutput.seal(pr_url=..., pr_number=..., was_reused=True)`; (b) capability check — `if input.repo not in input.capability.allowed_repos: raise CapabilityScopeError(repo=input.repo)`; (c) PR open via `github_client.open_pr(...)`; (d) emit `PrOpened` (batched); (e) return sealed. A test asserts the GitHub client mock receives the request with the `attempt_id` written into the PR body footer (the idempotency marker mechanism).
- [ ] **AC-3 — `github_open_pr` NEVER returns `GitHubToken`.** A test asserts `GithubOpenPrOutput.model_fields` contains no field whose type annotation is or unions `GitHubToken`. The seal-time check (S3-06's typed-credential blocklist) would catch it at runtime; this test catches it at design time so a contributor can't even ship the typed return. AC-3 of S4-07 ships the broader adversarial test.
- [ ] **AC-4 — `sandbox_build_and_test` input/output.** `src/codegenie/durable/activities/sandbox_build_and_test.py` defines `class SandboxBuildInput(BaseModel, frozen=True, extra="forbid")` with `repo_snapshot_ref: BlobRef`, `patch_ref: BlobRef`, `build_inputs: BuildInputs` (frozen Pydantic), `attempt_id: AttemptId`, `capability: SandboxCapability`. Defines `class SandboxBuildOutput(RedactedActivityResult)` with `build_outcome: BuildOutcome` (sum type: `BuildPassed | BuildFailed | TestsFailed`), `log_ref: BlobRef`, `patch_digest: BlobDigest`, `build_inputs_digest: BlobDigest`, `wall_clock_seconds: float`.
- [ ] **AC-5 — `sandbox_build_and_test` idempotence + heartbeats.** Body: (a) compute `idempotency_key = (patch_digest, build_inputs_digest)`; (b) lookup prior sandbox result in `events.events` by that key; if found, return sealed prior result; (c) else spawn `SubprocessJail.run(...)`; **while running**, an `asyncio.create_task` heartbeats every 5 s via `temporalio.activity.heartbeat(...)`; (d) on completion, emit `TrustGatePassed` or `TrustGateFailed` (one is `@critical_event` — synchronous flush). A test asserts ≥3 heartbeats over a 15-second sandbox run.
- [ ] **AC-6 — Idempotence reuses prior PR (`github_open_pr`).** Test: invoke `github_open_pr` with `attempt_id="a-1"` (returns `pr_number=42, was_reused=False`); invoke again with identical input; second call returns `pr_number=42, was_reused=True` and the GitHub mock receives ZERO additional PR-open API calls. The mechanism: `find_pr_by_marker` greps for a footer marker `<!-- codegenie-attempt: a-1 -->` in the PR body. Without this, every retry doubles open PRs in the test repo.
- [ ] **AC-7 — Idempotence reuses prior sandbox (`sandbox_build_and_test`).** Test: invoke twice with identical `(patch_ref, build_inputs)`; second call returns the prior `build_outcome` without re-spawning `SubprocessJail`. Asserted by a `SubprocessJail.spawn_count` counter (test fixture).
- [ ] **AC-8 — Capability scope enforcement.** `github_open_pr` with a `PrOpenCapability` whose `allowed_repos: frozenset[RepoSlug]` excludes `input.repo` raises `CapabilityScopeError(repo=input.repo)`. `sandbox_build_and_test` with a `SandboxCapability` whose `allowed_languages: frozenset[str]` excludes the build's language raises `CapabilityScopeError(language=...)`. Both errors include `.repo` / `.language` typed attributes (NOT just stringified messages).
- [ ] **AC-9 — `_EXPECTED_BUT_UNSHIPPED` trim.** Remove `ActivityName("github_open_pr")` and `ActivityName("sandbox_build_and_test")` from S4-01's set. Test: `policy_for(ActivityName("github_open_pr")).start_to_close_timeout == timedelta(seconds=60)`; `policy_for(ActivityName("sandbox_build_and_test")).heartbeat_timeout == timedelta(seconds=30)`.
- [ ] **AC-10 — Explicit-import collection extension.** Two new import lines in `__init__.py`; the collection test now asserts eight activity names register.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `make lint-imports` clean.

## Implementation outline

1. **`github_open_pr.py`**: input/output models + body. The GitHub client itself is a forward-referenced placeholder (`src/codegenie/integrations/github/client.py`) — if Phase-11-preview isn't merged, ship a `Protocol` + an in-memory `FakeGithubClient` for tests; the production client lands additively under S6-02's capability-minting story. See Notes §4.
2. **`sandbox_build_and_test.py`**: input/output models + body. The `SubprocessJail` from Phase-5 already exists; this Activity wraps it. The heartbeat task is a small `asyncio.create_task` that loops `await asyncio.sleep(5); temporalio.activity.heartbeat()` until the wrapped `SubprocessJail.run` returns.
3. **`BuildOutcome` sum type** lives in `codegenie.durable.activities.sandbox_build_and_test` (colocated until a second consumer lands). Variants: `BuildPassed`, `BuildFailed(reason: str)`, `TestsFailed(failing_signals: tuple[str, ...])`. The `failing_signals` field is what the workflow's retry-count machinery (per the workflow body) consumes.
4. **Capability records** (`PrOpenCapability`, `SandboxCapability`) — defined in S1-06 (`codegenie.durable.capabilities`); this story imports and consumes.
5. **`__init__.py`**: add two explicit-import lines.
6. **`_EXPECTED_BUT_UNSHIPPED`**: remove two names.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/unit/durable/activities/test_github_open_pr.py
import pytest
from codegenie.durable.activities.github_open_pr import (
    github_open_pr, GithubOpenPrInput,
)
from codegenie.durable.capabilities import PrOpenCapability
from codegenie.types.identifiers import AttemptId, RepoSlug


async def test_github_open_pr_idempotent_reuses_existing(
    fake_github_client, fake_event_log,
):
    """AC-6 — second dispatch with identical attempt_id MUST reuse the
    existing PR. The reason this is the red test: Temporal at-least-once
    semantics + a workflow that crashes after the PR opens but before the
    result is recorded means the activity will re-run. Without idempotency,
    every kill creates a duplicate PR; the G1 durability test (S8-01) would
    leave orphan PRs in the test repo across every CI run, and the audit
    trail would lie about how many remediation attempts the system made."""
    cap = PrOpenCapability(
        task_queue=TaskQueueName("vuln-remediation-node-npm"),
        allowed_repos=frozenset({RepoSlug("acme/widget")}),
    )
    inp = GithubOpenPrInput(
        repo=RepoSlug("acme/widget"), branch="fix/cve-2024",
        title="Bump lodash", body_ref=BlobRef(...), patch_ref=BlobRef(...),
        attempt_id=AttemptId("a-1"), capability=cap,
    )
    first = await github_open_pr(inp)
    second = await github_open_pr(inp)
    assert first.pr_number == second.pr_number
    assert second.was_reused is True
    assert fake_github_client.open_pr_call_count == 1  # not 2
```

Why it fails: `codegenie.durable.activities.github_open_pr` doesn't exist yet.

### Green — minimal pass

- Ship both activity modules.
- `github_open_pr` body: capability check → idempotency check (find by marker) → either reuse or open → emit event → seal.
- `sandbox_build_and_test` body: capability check → idempotency check by `(patch_digest, build_inputs_digest)` → either reuse or `SubprocessJail.run` with heartbeats → emit event → seal.

### Required follow-on tests (per AC)

```python
async def test_github_open_pr_capability_scope_enforced(fake_github_client):
    """AC-8 — repo outside allowed_repos surfaces a typed error. G9 at the
    activity layer; S8-03 is the cross-process version."""
    cap = PrOpenCapability(
        task_queue=TaskQueueName("vuln-remediation-node-npm"),
        allowed_repos=frozenset({RepoSlug("acme/widget")}),
    )
    inp = GithubOpenPrInput(repo=RepoSlug("evil/repo"), ..., capability=cap)
    with pytest.raises(CapabilityScopeError) as exc_info:
        await github_open_pr(inp)
    assert exc_info.value.repo == RepoSlug("evil/repo")
    assert fake_github_client.open_pr_call_count == 0


async def test_github_open_pr_output_has_no_github_token_field():
    """AC-3 — design-time defense: GithubOpenPrOutput.model_fields contains
    no GitHubToken-typed field. Catches a contributor who tries to 'return
    the token alongside the PR url' before runtime even gets a chance."""
    from codegenie.types.credentials import GitHubToken
    for field_name, field in GithubOpenPrOutput.model_fields.items():
        assert field.annotation is not GitHubToken, (
            f"field {field_name!r} is typed as GitHubToken — ADR-0008 violation"
        )
        # Also catch union-with-GitHubToken cases:
        import typing
        args = typing.get_args(field.annotation) or ()
        assert GitHubToken not in args, (
            f"field {field_name!r} unions GitHubToken — ADR-0008 violation"
        )


async def test_sandbox_idempotent_on_patch_and_inputs(
    fake_subprocess_jail, fake_event_log,
):
    """AC-7 — identical (patch_digest, build_inputs_digest) reuses prior
    SubprocessJail result. The reason: sandbox runs are 5–10 minutes; the
    G1 durability test SIGKILLs the activity worker mid-flight; re-dispatch
    MUST NOT re-spawn the jail (which would burn the 10 minutes again AND
    invalidate the prior result if it had test ordering side effects)."""
    inp = SandboxBuildInput(...)
    first = await sandbox_build_and_test(inp)
    second = await sandbox_build_and_test(inp)
    assert first.build_outcome == second.build_outcome
    assert fake_subprocess_jail.spawn_count == 1


async def test_sandbox_heartbeats_every_5_seconds(
    fake_subprocess_jail, fake_event_log,
):
    """AC-5 — long sandbox runs heartbeat at 5 s cadence. Temporal's
    heartbeat-timeout is 30 s; without heartbeats, the activity dies and
    re-dispatches mid-build, repeatedly, until max_attempts. The 5 s cadence
    gives 6x margin even under slow Postgres flush latency."""
    fake_subprocess_jail.set_run_duration(seconds=15)
    heartbeat_counter = []
    fake_subprocess_jail.on_heartbeat(lambda: heartbeat_counter.append(1))
    await sandbox_build_and_test(SandboxBuildInput(...))
    assert len(heartbeat_counter) >= 3  # 3 heartbeats in 15s at 5s cadence
```

### Refactor

- Both module docstrings cite the production ADRs they honor: `github_open_pr.py` cites ADR-0009 (no merge); `sandbox_build_and_test.py` cites the Phase-5 `SubprocessJail` contract.
- The idempotency-marker convention for `github_open_pr` (`<!-- codegenie-attempt: a-1 -->` HTML comment in PR body) is documented in the module docstring; if S6-02 / Phase 11 changes the convention, the docstring is the audit anchor.
- The `BuildOutcome` sum type carries a docstring naming the workflow consumer (S5-02's `match` arm).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/activities/github_open_pr.py` | Activity + input/output + idempotency-marker logic. |
| `src/codegenie/durable/activities/sandbox_build_and_test.py` | Activity + `BuildOutcome` sum type + heartbeat machinery. |
| `src/codegenie/durable/activities/__init__.py` | Two new explicit-import lines. |
| `src/codegenie/durable/activities/retry_policies.py` | Trim two names from `_EXPECTED_BUT_UNSHIPPED`. |
| `tests/unit/durable/activities/test_github_open_pr.py` | Red test + per-AC follow-on. |
| `tests/unit/durable/activities/test_sandbox_build_and_test.py` | Per-activity test file. |
| `tests/unit/durable/activities/conftest.py` | Add `fake_github_client`, `fake_subprocess_jail`, `pr_open_capability`, `sandbox_capability` fixtures. |

## Out of scope

- The GitHub client production implementation (HTTP machinery, auth, rate-limit handling) — Phase-11-preview; this story uses a `Protocol` + in-memory fake.
- The `SubprocessJail` itself — Phase-5; this story wraps it.
- `PrOpenCapability` / `SandboxCapability` Pydantic record definitions — S1-06.
- Capability *minting* from K8s ServiceAccount — S6-02.
- The G9 cross-process blast-radius adversarial — S8-03.
- The `merge_pr` fence — S4-07 (this story respects the rule; S4-07 enforces it as a fence).
- `RetryPolicy` for these two — S4-01 (already declared; this story consumes via `_POLICIES`).

## Notes for the implementer

### §1 — Why `github_open_pr` is the *only* GitHub-side-effect Activity

Production ADR-0009 ("Humans always merge") is the autonomy boundary of the whole system. Phase 9's contribution is the *fence* (S4-07's `tests/fence/test_no_merge_activity.py`); this story is the *positive example* — `open_pr` is the only GitHub state mutation the autonomous agent ever performs. Approvals, merges, branch deletions: all human. If a future contributor proposes `github_close_pr` or `github_resolve_conversation`, surface the ADR-0009 trade-off — those Activities cross the autonomy boundary in a way that requires an ADR amendment, not just a new story.

### §2 — Idempotency marker convention

The chosen marker (`<!-- codegenie-attempt: {attempt_id} -->` in the PR body footer) is the simplest reliable mechanism because:
1. GitHub preserves HTML comments in PR bodies.
2. Search-by-substring is cheap.
3. The marker is human-readable for forensic incidents ("which attempt opened this PR?").

Alternatives considered and rejected: GitHub Labels (clutter the UI, race conditions on label creation), GitHub Issues cross-references (heavier API surface), GraphQL custom metadata (Phase-11 may need it for other reasons — defer that decision).

If a future story needs a different mechanism (e.g., Phase-11's project-board sync), update the marker convention in *one place* (this Activity's module docstring + body); don't fork the convention across multiple Activities.

### §3 — Heartbeat under back-pressure

5-second cadence × 30-second heartbeat-timeout = 6× margin. The architect's lessons from prior incidents (per `phase-arch-design.md §Implementation risks specific to this step`) is that "slow Postgres flush latency" can stretch the heartbeat path beyond 5 s under load. 6× margin survives that. Going to 10-second cadence (3× margin) is brittle; going to 1-second cadence is wasteful. 5 s is the right point.

The heartbeat task IS the canary that surfaces back-pressure problems. If S8-04's perf canary shows the heartbeat path itself blocking, the right response is a back-pressure scenario in the bench, not a faster cadence — the bench will catch it before merge.

### §4 — Phase-11-preview GitHub client

If `src/codegenie/integrations/github/client.py` doesn't exist when this story lands, ship a `Protocol` (`GitHubClient` with `open_pr`, `find_pr_by_marker` methods) in `src/codegenie/durable/activities/_github_client.py` + an `InMemoryGitHubClient` for tests. The production client lands later (Phase-11 or under S6-02); the Activity body uses the Protocol so the swap is transparent. Document the deferral in the module docstring.

### §5 — `SandboxCapability` carries a language allowlist

Phase 9 ships only Node/npm support (the `vuln-remediation-node-npm` queue name says it). Phase 7.5 / Phase 10 will add Python / Java queues; each queue's `SandboxCapability.allowed_languages` is the explicit gate. AC-8's test asserts the in-process check; S8-03's adversarial test asserts the cross-process version. Without this, a compromised Node activity worker could spawn a Python sandbox and the `allowed_languages` check would silently miss — the typed Pydantic field is the only defense.

### §6 — `BuildOutcome` is a sum type, not a bool

`BuildOutcome = BuildPassed | BuildFailed | TestsFailed` (three variants) — NOT `passed: bool` + `error_message: str`. The workflow body's `match` arm with `assert_never` is what makes the difference: adding a fourth outcome (e.g., `BuildTimedOut` if Phase 10 wants per-outcome routing) is a fourth variant, and every consumer surfaces a mypy error until they handle it. Open/Closed at the file boundary.

### §7 — Resist runtime metrics inside the activity body

Tempting: "let's log `wall_clock_seconds` and tag with `attempt_id`." Don't. The Activity already returns `wall_clock_seconds` in its output, which lands in the canonical event log via `emit_event`. Projection time (S7) is where metrics roll up. Adding a Prometheus counter inline duplicates the data path and creates the eventual-consistency surface the architect explicitly avoided (the canonical log IS the observability substrate).
