# Phase 6.5 — Per-task-class eval harness + first benches: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-12

## Lens summary

I treat the eval harness as a **trust-laundering target**. Its single output — `bench_score` — feeds the gate that decides whether a task class graduates from bronze to silver to gold trust tiers, and trust-tier promotion expands what the planner is allowed to *do* in real repositories ([ADR-0016 §Decision §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md), [production ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md)). An adversary who can move that one number — by poisoning a bench case, tampering a cassette, swapping a rubric, or rewriting score history — can engineer a fake "promotion-ready" track record without ever touching production code. The harness is a control-plane component pretending to be a test runner; I design it as the former.

**Threat model assumed.** Adversaries are (a) contributors with bench-write access whose intent is to "fix a flaky case" but who in fact relax detection of a real failure mode; (b) an attacker with shell on an operator's laptop attempting to forge `BenchScore` history to trigger promotion; (c) a malicious or compromised dependency in the rubric's import closure; (d) a poisoned outcome-ledger entry (Phase 13) that auto-converts into a bench case under [ADR-0016 §Decision §6](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)'s `regression-converted` provenance class; (e) cassette swap by a contributor with `tests/cassettes/` write access. I assume each layer will eventually be breached and require the next.

**Optimized for:** integrity over throughput; audit completeness over operator UX; default-deny in every component; explicit, code-enforced trust boundaries; cryptographic chaining of every score that ever influences a promotion decision; and *humans always promote* as the corollary to [production ADR-0009](../../production/adrs/0009-humans-always-merge.md)'s "humans always merge."

**Explicitly deprioritized:** wall-clock harness runtime, per-case cost minimization, developer ergonomics of adding new cases (extra friction is the intended security control), the LLM-Judge un-deferral surface ([Phase 5 ADR-0008](../05-sandbox-trust-gates/ADRs/0008-llm-judge-persona-deferral.md)) — un-deferral remains future work and the security shape I leave behind is sufficient.

## Threat model

### Assets to protect

1. **Bench-case bodies (the curated input + expected-output corpus under `bench/{task-class}/cases/{case-id}/`).** Integrity and provenance. A bench case is a signed claim that *this input should produce that output*; if the claim is wrong, the harness measures the wrong thing.
2. **Rubric source (`bench/{task-class}/rubric.py`).** This is executable Python invoked by the harness on every run. A malicious rubric is RCE on the operator's host with whatever privileges the harness runs under, *including* the ability to forge its own `BenchScore` returns and corrupt the audit chain in the same process.
3. **Cassette corpus (`tests/cassettes/` extended for bench, per Phase 4 final-design §VCR cassette discipline).** Bench runs replay frozen LLM responses. A swapped cassette skews scores without touching the bench case itself — invisible to bench-case integrity checks alone.
4. **Score history (`.codegenie/bench/history/`).** The append-only ledger of every `BenchScore` ever produced. Rewriting the past lets an attacker synthesize a promotion-eligible track record.
5. **Trust-tier promotion authority.** The act of changing a task class from bronze → silver → gold. This is not data; it is an authorization decision. Whoever holds this authority effectively widens or narrows the system's blast radius across the portfolio.
6. **The inference itself.** "bench_score ≥ threshold → safe to promote." If the threshold is set from a forged distribution, every downstream promotion is unsafe even if the cryptography holds.

### Adversaries assumed

- **A1 — Compromised internal contributor with bench-case write access.** Lands a "fix" that softens detection of a known failure mode, or adds a high-scoring synthetic case that anchors the rubric's mean upward. Most likely adversary; full social-engineering plausibility.
- **A2 — Compromised contributor with rubric-edit access.** Lands a `rubric.py` change that returns `passed=True` on a poisoned input pattern, or that silently mutates global harness state during scoring.
- **A3 — Attacker with shell on operator's laptop.** Has write access to `.codegenie/bench/history/`, `tests/cassettes/`, and possibly the audit chain anchor. Goal: forge enough history to make the promotion gate trigger.
- **A4 — Poisoned outcome ledger entry (Phase 13).** A regression that *should* convert into a `regression-converted` bench case is filtered out by the conversion logic, or — worse — a benign incident is converted with `disposition: positive` so it adds a "real production failure we caught" to the bench-score numerator.
- **A5 — Supply-chain attacker via rubric dependencies.** `rubric.py` imports `numpy` or a YAML parser; a pinned dependency rolls forward to a malicious version.
- **A6 — Cassette-swap attacker.** Replaces `tests/cassettes/bench/.../foo.yaml.zst` with one whose response is the "correct" answer to every case, neutering the entire benchmark.
- **A7 — CI-config tamperer.** Silently disables the fence-CI test that enforces "task class registered → `bench/{name}/` exists." Or disables the bench job entirely. The harness still runs locally and looks healthy.
- **A8 — Promotion forger.** Has commit access. Pushes a `promotion.yaml` (or equivalent) that flips a task class to gold by hand, claiming the bench history justifies it.

### Attack surfaces specific to this phase

- The `bench/{task-class}/cases/{case-id}/case.yaml` provenance block — easy to lie in YAML.
- The `bench/{task-class}/rubric.py` import-time side effects.
- The `score(harness_output, expected) -> BenchScore` call site — the rubric runs inside the harness's Python process by default.
- The `.codegenie/bench/history/` append-only ledger — filesystem; vulnerable to local-shell tampering.
- The cassette directory the harness shares with Phase 4 — both phases must agree on integrity rules or one undermines the other.
- The fence-CI test asserting `bench/{name}/` exists when a task class is registered — meta-control; its disablement is itself a finding.
- The trust-tier promotion gate's read of `bench_score` — if it reads "the latest history file" rather than "the latest *verified* history entry," it inherits any tamper the audit chain catches.
- The outcome-ledger reconciliation hook (deferred to Phase 13 per [ADR-0016](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)) — this phase must define the boundary now, not when Phase 13 reaches it.

### Trust boundaries (explicit)

| Boundary | From (less-trusted) | To (more-trusted) | Crossing control |
|---|---|---|---|
| TB-1 | bench-case curator (human or LLM-assisted) | `bench/{task-class}/cases/` on disk | CODEOWNERS-protected path; two-reviewer rule; case-content BLAKE3 digest pinned in `bench/{task-class}/cases/digests.yaml`; `case.yaml` provenance signed (see Components → case format) |
| TB-2 | `bench/{task-class}/rubric.py` source | rubric *executor* | Rubric runs in a microVM (Firecracker on Linux/CI, gVisor-on-Lima on macOS dev) — never in the harness's Python process. Output is a JSON `BenchScore` over an RPC; no shared memory |
| TB-3 | rubric microVM | harness orchestrator | Schema validation on the JSON `BenchScore`; `extra="forbid"` mirroring [Phase 5 ADR-0014](../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md); range checks on every numeric field; hard wall-clock + cost cap enforced by the harness, not the rubric |
| TB-4 | harness orchestrator | `.codegenie/bench/history/` ledger | Every `BenchScore` is hashed + chained (BLAKE3-over-SHA-256, matching Phase 0 `audit.py`); per-run `run-record.json` mode `0600`; `codegenie bench verify` re-walks the chain |
| TB-5 | `.codegenie/bench/history/` ledger | trust-tier promotion gate (`promotion.py`) | Gate reads only verified chain entries; refuses to read on chain-tamper detection; emits a `block`-severity audit event |
| TB-6 | promotion gate | actual tier change | **The gate produces a recommendation, not a side effect.** Tier change is a separate, human-authorized PR amending `bench/{task-class}/registration.py`'s `current_tier` field with a CODEOWNERS-approved diff (see Component → `promotion.py`) |
| TB-7 | outcome ledger (Phase 13) | `regression-converted` bench cases | Conversion is a *proposal* — produces a draft case in `bench/{task-class}/cases-pending/`; promotion to `bench/{task-class}/cases/` requires the same CODEOWNERS rule as TB-1 |
| TB-8 | cassette corpus | bench runner | Cassette digest pinned per bench case in `case.yaml#cassette_digest`; startup integrity check refuses to run a case whose cassette hash drifts |

## Goals (concrete, measurable)

1. **Bench-case poisoning detection.** Every case-content byte BLAKE3-digested at the `cases/digests.yaml` level (one digest per case directory's tar-serialization); every `case.yaml` field carries `provenance.signed_by` (the GPG fingerprint or Sigstore identity of the human who approved it) and `provenance.signed_at`. CI rejects a PR that changes a case's contents without updating its digest *and* re-signing — mitigates A1, A4.
2. **Rubric malicious-code execution risk.** Rubric runs in a microVM with **no network**, **no host FS**, and **no env inheritance** (`env_allowlist.filter({})` returns `{}` — even `PATH` is microVM-default). Inputs are JSON-over-pipe; output is JSON-over-pipe. CODEOWNERS rule on `bench/{task-class}/rubric.py` requires two reviewers, one of whom must hold the `security` role. Mitigates A2, A5.
3. **Score-history tamper detection.** `.codegenie/bench/history/` is a BLAKE3-chained append-only log following the Phase 0 `audit.py` pattern (Phase 0 final-design §2.12). Each `bench-run-<utc-iso>-<short>.json` carries `prev_hash` linking the chain; `codegenie bench verify` re-walks the chain on every promotion-gate read. A new "audit anchor" is published nightly to a separate path (`audit/anchors/bench/<date>.json`) signed by the operator and stored alongside the regular audit anchors. Mitigates A3.
4. **Trust-tier auto-promotion: forbidden.** Matches [ADR-0016 §Decision §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) ("wired but does not auto-promote — promotion remains a deliberate, ADR-anchored decision") and extends [production ADR-0009](../../production/adrs/0009-humans-always-merge.md)'s "humans always merge" to "humans always promote." The harness *recommends*; a human merges the promotion PR. Mitigates A8.
5. **Audit completeness target.** Every harness run emits exactly one chained `run-record.json` containing: harness version, rubric digest, cassette digest set, case-digest set, `bench_score`, runtime, cost, microVM image digest, operator fingerprint, `prev_hash`. Coverage measured by `codegenie bench verify --strict` returning zero gaps for 30 trailing days.
6. **Allowed network egress.** Rubric microVMs: **none**. Harness orchestrator (the trust-aware caller that drives LLM cassettes): network **off** by default; `cassette-record-only` mode enables network behind a `--unsafe-record` flag plus operator confirmation, never in CI. Mitigates A6 (cassette regeneration in CI is forbidden).
7. **Fence-CI extension is itself fenced.** The fence test asserting `bench/{name}/` exists when a task class is registered is checksummed and a *second* CI job verifies the checksum of the first. Disabling the fence is detectable via a third meta-job that asserts the second job ran. Mitigates A7.
8. **Two-person curation rule.** No bench case, no rubric edit, no `case.yaml` provenance change, and no `bench/{task-class}/registration.py` edit lands without two reviewer approvals (CODEOWNERS-enforced).

## Architecture

```
                  ┌────────────────────────────────────────────────────────────┐
                  │  CODEOWNERS-protected territory (TB-1, TB-2 source side)   │
                  │                                                            │
                  │   bench/{task-class}/                                      │
                  │     ├─ cases/{case-id}/                                    │
                  │     │    ├─ input/...        (fixture)                     │
                  │     │    ├─ expected/...    (ground truth)                 │
                  │     │    └─ case.yaml       (signed provenance)            │
                  │     ├─ cases/digests.yaml   (BLAKE3 per case dir)          │
                  │     ├─ rubric.py            (signed; two-reviewer)         │
                  │     └─ registration.py      (current_tier; ADR-anchored)   │
                  └──────────────┬─────────────────────────────────────────────┘
                                 │ TB-1 verified at startup
                                 ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │ Harness orchestrator (src/codegenie/eval/)                       │
       │ - Runs as the codegenie process; no extra privileges             │
       │ - Reads cases, verifies digests, looks up cassette digests       │
       │ - Drives the system-under-test via Phase 4 cassettes (no net)   │
       │ - Spawns rubric microVM per case (TB-2)                         │
       │ - Validates rubric output (TB-3) against BenchScore schema      │
       │ - Writes chained run-record to .codegenie/bench/history/ (TB-4) │
       └──────────────────────────────┬───────────────────────────────────┘
                                      │ TB-2: process boundary
                                      ▼
                           ┌──────────────────────────┐
                           │  Rubric microVM          │
                           │  (Firecracker / gVisor)  │
                           │  - No network            │
                           │  - No host FS            │
                           │  - Empty env             │
                           │  - JSON stdin/stdout     │
                           │  - Hard wall-clock cap   │
                           └──────────────────────────┘

       ┌──────────────────────────────────────────────────────────────────┐
       │ .codegenie/bench/history/                                        │
       │ - Append-only, mode 0600                                          │
       │ - BLAKE3-chained; SHA-256 identity tuple                          │
       │ - `codegenie bench verify` walks chain                           │
       │ - Daily signed anchor published to audit/anchors/bench/          │
       └────────────────────────┬──────────────────────────────────────────┘
                                │ TB-5: chain-verified read only
                                ▼
                  ┌────────────────────────────────────┐
                  │ Trust-tier promotion gate          │
                  │ src/codegenie/eval/promotion.py    │
                  │ - Reads verified history           │
                  │ - Emits *recommendation* artifact  │
                  │ - DOES NOT mutate registration.py  │
                  └────────────────┬───────────────────┘
                                   │ TB-6: humans always promote
                                   ▼
                       ┌────────────────────────────┐
                       │ Promotion PR (human)       │
                       │ - Amends registration.py   │
                       │ - CODEOWNERS + ADR amend   │
                       │ - Branch protection        │
                       └────────────────────────────┘
```

**Defense-in-depth layers** (for each, what an attacker has to defeat):

- L1 — **CODEOWNERS + branch protection on `bench/**` and `src/codegenie/eval/**`.** Attacker must compromise two reviewers including one with `security` role.
- L2 — **Digest pinning + provenance signatures on every case + rubric.** Even with a merged PR, mismatched digests fail startup integrity check.
- L3 — **Rubric microVM isolation (TB-2).** Even with a malicious rubric merged through L1+L2, it cannot reach the harness's process, network, or filesystem.
- L4 — **Chain-walked audit history.** Even if the rubric or harness lies about a score, the chain makes rewriting the past detectable.
- L5 — **Humans always promote.** Even if every layer above is breached, no tier change happens without a separate, reviewed PR.
- L6 — **Daily signed anchor publication.** Even if `.codegenie/bench/history/` is rewritten on the operator's machine, the published anchor diverges; a watcher (Phase 16 hardening) alerts.

To get to tier promotion, an attacker must defeat all six.

## Components

### `src/codegenie/eval/registry.py`

- **Purpose:** `@register_task_class` decorator + in-process registry with collision detection.
- **Trust level:** trusted (code under codegenie's control).
- **Interface:**
  ```python
  @register_task_class(
      "migration-chainguard-distroless",
      bench_path=Path("bench/migration-chainguard-distroless"),
      rubric_module="bench.migration_chainguard_distroless.rubric",
      min_cases_for_promotion={"bronze": 10, "silver": 30, "gold": 100},
      current_tier="bronze",  # ADR-anchored; security gate refuses unknown values
  )
  class MigrationChainguardDistrolessTaskClass: ...
  ```
  Inputs trusted at *import time* but cross-checked at *registration time* against `bench/{name}/cases/digests.yaml` existence and `rubric.py` digest.
- **Isolation:** import-time only; no network, no subprocess, no filesystem writes.
- **Credentials accessed:** none.
- **Audit emissions:** one `task_class.registered` event per `@register_task_class` call, into the Phase 0 audit chain (re-using `codegenie/audit.py`'s writer).
- **Tradeoffs accepted:** import-time validation requires bench directories to be on disk during `pytest` discovery; this is intentional — the fence-CI test depends on it.

Collision behavior matches [Phase 5 ADR-0003](../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)'s `SignalKindAlreadyRegistered` — raises `TaskClassAlreadyRegistered` loudly. No silent overrides; matches CLAUDE.md "Fail loud."

### `src/codegenie/eval/models.py`

- **Purpose:** `BenchScore` Pydantic model + companion `BenchRunRecord` (the chained audit entry).
- **Trust level:** trusted.
- **Interface:**
  ```python
  class BenchScore(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      passed: bool
      score: float                    # [0.0, 1.0], validated
      breakdown: dict[str, float]     # keys: str; values: float; no nesting
      failure_modes: list[str]        # str-only; no nested dicts
      cost_usd: float
      duration_seconds: float
      # Forbidden by static test (mirrors ADR-0014): any field name matching
      # /confidence|llm|self_reported|model_says/ raises in CI.
  ```
  `extra="forbid", frozen=True` mirrors [Phase 5 ADR-0014](../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) exactly — same threat (LLM judgment smuggling), same control. A `tests/eval/test_bench_score_static.py` walks `BenchScore`'s field graph and rejects banned substrings. This is non-negotiable: the moment a rubric is allowed to emit `confidence`, the strict-AND discipline at the per-task-class layer collapses into the per-PR-LLM-self-assessment trap [production ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md) explicitly forbids.

- **Isolation:** pure Pydantic; no I/O.
- **Credentials accessed:** none.
- **Audit emissions:** none directly (`BenchScore` is data, not an event).
- **Tradeoffs accepted:** range-validation forces rubrics to clamp; a rubric that wants to emit "-0.1" to signal "worse than baseline" must instead use `breakdown` keys. Intentional friction — keeps the score in `[0, 1]` where the promotion threshold lives.

`BenchRunRecord` (the chain entry) extends:

```python
class BenchRunRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    task_class: str
    case_id: str
    case_digest: str          # BLAKE3 of the case tar-serialization
    rubric_digest: str        # BLAKE3 of rubric.py
    cassette_digest: str | None
    harness_version: str
    microvm_image_digest: str
    score: BenchScore
    started_at: str           # UTC ISO
    finished_at: str
    operator_fingerprint: str # GPG / Sigstore identity
    prev_hash: str            # SHA-256 of the previous chain entry; "0"*64 at genesis
```

### `src/codegenie/eval/runner.py`

- **Purpose:** Orchestrates one bench run end-to-end: walk cases, verify digests, invoke system-under-test via Phase 4 cassettes, spawn rubric microVM, validate output, write chained record.
- **Trust level:** trusted, but minimal-privilege.
- **Interface:**
  - Input: `TaskClass` registration object + optional filter (case-ids).
  - Output: `BenchRunSummary` aggregating `BenchScore`s.
  - Errors: `BenchCaseDigestMismatch`, `RubricDigestMismatch`, `CassetteDigestMismatch`, `RubricSandboxEscape` (heuristic), `ChainTamperDetected`. All raised loudly; `--continue-on-error` is **forbidden** by design (CLAUDE.md "Fail loud" + the entire point of integrity checks).
- **Isolation:** the runner itself runs as the codegenie process; the *rubric* runs in a microVM per-case. The runner never `exec`s untrusted code in-process. `import bench.{task-class}.rubric` is forbidden by an `import-linter` rule mirroring Phase 0's lazy-import discipline — rubric source is read as **bytes**, copied into the microVM rootfs at run time, and executed by a stub interpreter inside the microVM. This is the same shape as [production ADR-0012](../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)'s sandbox-for-agent-output, applied to the *rubric* (also untrusted from the harness's perspective).
- **Credentials accessed:** **none.** Following [Phase 5 ADR-0012](../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md), the env passed to the rubric microVM is `env_allowlist.filter({})`. The bench harness *itself* needs no API keys at run time — cassettes are deterministic replays. If the operator runs `--unsafe-record` (cassette regeneration), the orchestrator briefly receives `ANTHROPIC_API_KEY` but never propagates it into the microVM and never logs it. CI never has access to `--unsafe-record`.
- **Audit emissions:** `bench.run.started`, `bench.case.completed`, `bench.case.failed`, `bench.run.finished`, and the chained `BenchRunRecord` per case.
- **Tradeoffs accepted:** per-case microVM cold-start cost (100ms Firecracker, seconds for gVisor-on-Lima) multiplied by N cases dominates wall-clock. I accept this; it is the cost of TB-2. No warm pool — same reasoning as Phase 5 final-design rejecting warm pools (snapshot reuse is itself an attack surface).

### `src/codegenie/eval/audit.py`

- **Purpose:** Append-only chain over `BenchRunRecord`s; daily anchor publication.
- **Trust level:** trusted.
- **Interface:**
  - `append(record: BenchRunRecord) -> str` — returns the new chain head SHA-256. Writes `.codegenie/bench/history/<utc-iso>-<short>.json` mode `0600`, computes `BLAKE3(record_bytes)`, wraps in `SHA-256(prev_hash || blake3)` identity tuple matching Phase 0 final-design §2.12.
  - `verify(since: str | None = None) -> VerifyResult` — re-walks the chain; returns mismatches.
  - `publish_anchor(date: str) -> Path` — writes `audit/anchors/bench/<date>.json` containing `{chain_head, count, signature}`; signature is the operator's Sigstore identity or GPG-fingerprint signing the chain head.
  - Errors: `ChainTamperDetected` (raised by `verify` and on every `append` that finds a torn write), `MissingAnchor`, `AnchorSignatureInvalid`.
- **Isolation:** filesystem-only; no network for `append` and `verify`; `publish_anchor` uses Sigstore's transparency log (network egress allowlisted in CI; off in local).
- **Credentials accessed:** Sigstore short-lived identity (OIDC) for anchor publication; never persisted; ephemeral per `publish_anchor` call.
- **Audit emissions:** itself the audit.
- **Tradeoffs accepted:** chain verification is `O(N)` per promotion-gate read. For Phase 6.5 N is small (hundreds); fine. Phase 16 may add per-month anchor checkpointing if N grows.

Hash choice deliberately mirrors Phase 0 (BLAKE3 content, SHA-256 identity tuple) for two reasons: (a) operators already trust this pattern; (b) sharing the `codegenie/hashing.py` module from Phase 0 means there is exactly one place either algorithm is named — same load-bearing commitment as Phase 0 final-design §2.11.

### `src/codegenie/eval/promotion.py`

- **Purpose:** Read verified history, emit a *recommendation*, never mutate.
- **Trust level:** trusted, write-restricted by code.
- **Interface:**
  - `recommend(task_class: str) -> PromotionRecommendation` — returns `{current_tier, recommended_tier, evidence: list[BenchRunRecord], rationale: str, requires_human_approval: True}`.
  - `apply(task_class: str, target_tier: str) -> NoReturn` — **raises `PromotionMustBeHumanAuthorized` unconditionally.** The function exists to prevent anyone from writing it; the only path to a tier change is a human-authored PR amending `bench/{task-class}/registration.py#current_tier`, which is CODEOWNERS-protected and (per the new invariant added by [ADR-0016 §Consequences](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)) must carry an ADR amendment.
- **Isolation:** read-only against the audit chain; no filesystem writes outside `.codegenie/bench/recommendations/<utc-iso>.json` (the recommendation artifact a human reviewer reads).
- **Credentials accessed:** none.
- **Audit emissions:** `promotion.recommendation.emitted` per recommendation; `promotion.apply.blocked` if `apply()` is ever called (alarms loudly — only happens if someone is trying).
- **Tradeoffs accepted:** the "promotion" interface is intentionally asymmetric — recommendation flows automatically, application never does. This is the operationalization of [ADR-0016 §Decision §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) and the corollary to [production ADR-0009](../../production/adrs/0009-humans-always-merge.md) at the meta level. Demotion behavior from [ADR-0016 §Decision §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) ("Demotion is automatic on any production regression") deserves scrutiny — see Open questions §3. My read of the ADR: demotion is automatic in the sense that the *recommendation* drops; the *applied tier* still moves only on a human-authored PR. If the ADR meant automatic side-effect demotion, that contradicts the security argument here and should be amended.

### `bench/{task-class}/cases/{case-id}/case.yaml`

The provenance schema:

```yaml
schema_version: 1
case_id: "GHSA-2024-0001-axios-ssrf"
title: "Axios SSRF — minor bump available"
disposition: positive | negative | ambiguous   # per ADR-0016 §Decision §1
difficulty: easy | medium | hard
provenance:
  source: curated | outcome-ledger-derived | regression-converted
  source_ref:                                  # e.g., ledger entry id, GHSA id, commit SHA
    type: ghsa | ledger | commit | synthetic
    value: "GHSA-xxxx-xxxx-xxxx"
  added_at: "2026-05-12T14:00:00Z"
  added_by:
    identity: "alice@codewizard.example"       # Sigstore identity or verified GPG fingerprint
    signature: "MEUCIQ..."                     # signature over (case_id || added_at || case_digest)
  reviewed_by:                                 # second reviewer mandatory (two-person rule)
    identity: "bob@codewizard.example"
    signature: "MEUCIQ..."
  last_validated_at: "2026-05-12T14:00:00Z"   # IndexHealthProbe-style freshness signal
expected:
  recipe_id: "axios-bump-minor"
  cve_delta: -1
  validator_verdict: pass
cassette_digest: "blake3:abcdef..."            # the Phase 4 cassette this case replays
case_digest: "blake3:123456..."                # BLAKE3 of the tar-serialized cases/{case-id}/ dir minus case.yaml itself
```

- **Trust level:** untrusted as code; provenance fields verified by code.
- **Isolation:** the `case.yaml` is read by the runner; `disposition` and `expected` are passed to the rubric microVM as inputs.
- **Credentials accessed:** none.
- **Audit emissions:** `case.verified` on every load (logs the digest).
- **Tradeoffs accepted:** two-signature requirement (CODEOWNERS-mirror at the data layer) makes case-add a slower workflow than just a PR. Intentional. Without the second signature the case is *valid YAML* but *invalid provenance*; the runner refuses to use it.

The `bench/{task-class}/cases/digests.yaml` top-level file:

```yaml
schema_version: 1
cases:
  "GHSA-2024-0001-axios-ssrf": "blake3:123456..."
  "CVE-2024-9999-lodash-proto-pollution": "blake3:789abc..."
```

The startup integrity check (`SandboxHealthProbe`-style, borrowing the pattern from [Phase 5 ADR-0013](../05-sandbox-trust-gates/ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md)) refuses to run any case whose computed digest mismatches.

### `bench/{task-class}/rubric.py`

- **Purpose:** Score one `(harness_output, expected)` pair into a `BenchScore`.
- **Trust level:** **untrusted** for execution purposes (even though under CODEOWNERS). The harness assumes the rubric is hostile.
- **Interface:** Inside the microVM, the rubric is invoked as `python /work/rubric.py < inputs.json > output.json`. `inputs.json` is `{harness_output, expected, case_metadata}`; `output.json` is a `BenchScore` JSON dump.
- **Isolation:** microVM, no network, no host FS, empty env, hard wall-clock + RSS cap (60s, 1GB defaults; rubric-author may *request* up to 5min / 4GB via `case.yaml#rubric_limits`, enforced by the harness, never by the rubric).
- **Credentials accessed:** none.
- **Audit emissions:** runner emits `rubric.invoked`, `rubric.completed`, `rubric.killed_oom`, `rubric.killed_timeout`, `rubric.malformed_output`.
- **Tradeoffs accepted:** microVM-per-case spawn cost is real. Some rubrics will be trivially short and yet pay a 100ms-to-seconds penalty. I accept this entirely — the per-call cost is the security premium, and Phase 6.5's offline-nightly cadence ([ADR-0016 §Decision §5](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)) absorbs it.

A `tests/adversarial/test_rubric_isolation.py` plants a deliberately malicious `rubric.py` in a fixture (attempts: env var read, `urlopen`, `socket.gethostbyname`, `open("/etc/passwd")`, fork+exec) and asserts the resulting `BenchScore` is `RubricSandboxEscape` *or* shows the malicious operations produced no observable host effect.

### Fence-CI extensions

Three new gates:

1. **`test_task_class_has_bench_dir`** — for each registered task class, asserts `bench/{name}/{cases,rubric.py,registration.py}` exist and pass startup digest checks. Mirrors [ADR-0016 §Consequences §Fence-CI extends](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md).
2. **`test_bench_score_static_introspection`** — the [Phase 5 ADR-0014](../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md)-style introspection over `BenchScore`'s reachable fields; rejects `confidence | llm | self_reported | model_says` substrings.
3. **`test_fence_ci_is_alive`** — meta-gate: hashes the CI workflow file's bench-job stanza and asserts it matches `tools/digests.yaml#ci.bench_job`. Disabling the bench job changes the digest and fails this gate.

CODEOWNERS additions:

```
bench/                              @codewizard-sherpa/security @codewizard-sherpa/eval-curators
bench/**/rubric.py                  @codewizard-sherpa/security
bench/**/registration.py            @codewizard-sherpa/security
src/codegenie/eval/                 @codewizard-sherpa/security
src/codegenie/eval/promotion.py     @codewizard-sherpa/security (single-owner; second approval external)
tools/digests.yaml                  @codewizard-sherpa/security
.github/workflows/bench.yml         @codewizard-sherpa/security
```

## Data flow

One representative end-to-end run for `migration-chainguard-distroless`:

1. **Startup integrity (TB-1, TB-8).** `codegenie bench run migration-chainguard-distroless` boots. The runner reads `bench/migration-chainguard-distroless/cases/digests.yaml`. For each case directory it computes the BLAKE3 of the tar-serialization (excluding `case.yaml` itself) and compares to the pinned digest. **One mismatch → abort.** It then reads each `case.yaml`, verifies the two Sigstore/GPG signatures against the case-content digest. **One unverifiable signature → abort.** It reads `bench/.../rubric.py`, compares its BLAKE3 to `tools/digests.yaml#bench.migration_chainguard_distroless.rubric`. **Mismatch → abort.**
2. **Cassette verification (TB-8).** For each case, the runner looks up `case.yaml#cassette_digest` and verifies the cassette file at `tests/cassettes/bench/migration-chainguard-distroless/{case-id}.yaml.zst` matches. **Mismatch → abort.**
3. **Chain integrity (TB-4).** The runner calls `audit.verify()` on the existing chain. **Tamper → abort and emit a `block`-severity audit event reachable by Phase 16 alerting.**
4. **Per-case execution.** For each case, in serial (no parallelism in Phase 6.5 — concurrency is an integrity-correlation risk this phase does not need):
   - Spawn rubric microVM. The microVM image digest comes from `tools/digests.yaml#bench.rubric_image`. Hard wall-clock cap, hard RSS cap, network=none, env=`{}`.
   - Invoke system-under-test against `case_input` using the verified cassette. The SUT path is the Phase 6 SHERPA state machine — its execution within the microVM is the same shape as the Phase 5 trust-aware gates, *not* a special bench-only path. The cassette ensures determinism.
   - Pipe `(harness_output, expected, case_metadata)` JSON into the rubric microVM stdin.
   - Read `BenchScore` JSON from rubric microVM stdout. Validate against the Pydantic schema (`extra="forbid"`). **Schema violation or malformed JSON → record `BenchScore(passed=False, failure_modes=["rubric_malformed"])` and continue; the case counts as a failure.**
   - Construct `BenchRunRecord` with all digests, the operator's Sigstore identity (short-lived OIDC), `prev_hash` set to the current chain head.
   - `audit.append(record)` — writes the file, computes new chain head.
5. **Aggregation.** Compute `bench_score.mean`, `failure_modes` union, `cost_usd` sum. Emit `bench_run_summary.json` to `.codegenie/bench/runs/<utc-iso>-<short>.json` mode `0600`.
6. **Promotion recommendation.** `promotion.recommend("migration-chainguard-distroless")` reads only verified chain entries from the last N days (configurable; default 30). Returns a `PromotionRecommendation`. Writes it to `.codegenie/bench/recommendations/<utc-iso>.json`. **Does not modify any registration.**
7. **Daily anchor.** Nightly job calls `audit.publish_anchor(today)`. Sigstore OIDC token is fetched, the chain head signed, and the anchor written to `audit/anchors/bench/<date>.json`. This file is committed via PR (one-line, auto-generated) so the public chain head lives in git history — diverging local tampering becomes visible at `git pull`.

Trust-boundary crossings are tagged at each step (the runner emits a structured event whose field set marks the boundary). A `tests/integration/test_eval_data_flow.py` walks the full flow against a hello-world bench fixture and asserts the boundary-event set matches a golden list — any new boundary crossing without a matching audit event fails.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| Poisoned bench case (A1, A4) — content edited without digest update | Startup `cases/digests.yaml` integrity check | `BenchCaseDigestMismatch` raised; entire run aborts; no `BenchRunRecord` written | Re-curate the case; update digest in PR with two-reviewer approval; CI runs fresh |
| Malicious rubric (A2) — RCE attempt via `rubric.py` | Rubric microVM (no network, no FS, no env); `tests/adversarial/test_rubric_isolation.py` | Rubric is in its own kernel; cannot affect harness; output rejected by schema | Revert `rubric.py`; rotate any operator credentials reachable via the orchestrator (paranoia) |
| Forged operator identity in `BenchRunRecord` | Sigstore identity verification at chain-append time | `audit.append()` refuses to write record without verifiable identity | Re-run from a workstation with valid OIDC |
| Local tampering of `.codegenie/bench/history/` (A3) | `audit.verify()` re-walks the chain; mismatch on prev_hash | `ChainTamperDetected` raised; promotion gate refuses to read | Restore from the last anchor; investigate the host (likely compromised) |
| Cassette swap (A6) | Per-case `cassette_digest` check | `CassetteDigestMismatch` raised; run aborts | Re-record cassette via `--unsafe-record` from a clean environment; PR with `cassettes-reviewed` label, mirroring Phase 4 final-design §VCR cassette discipline |
| Fence-CI disabled (A7) | `test_fence_ci_is_alive` checksumming the workflow file | Meta-job fails CI | Investigate why the fence was changed; revert |
| Forged promotion PR (A8) | CODEOWNERS protection on `bench/**/registration.py` + branch protection + the new invariant (ADR amendment required for tier change) | PR blocked from merge until two reviewers approve | Standard PR review |
| `regression-converted` bench case from poisoned outcome ledger (A4) | Conversion always produces a `cases-pending/` draft, not a `cases/` entry; two-signature rule applies | Pending draft never enters scoring | Reviewers reject the draft |
| Anchor signature unverifiable | `audit.publish_anchor` signature check | `AnchorSignatureInvalid` raised; nightly job fails red | Rotate the operator's signing identity; re-publish |
| Rubric runs forever (livelock) | Wall-clock cap enforced by microVM | `rubric.killed_timeout` event; case scored failure | Investigate rubric; lower-bound the rubric's cost |
| Rubric OOMs | RSS cap | `rubric.killed_oom`; case scored failure | Same as above |
| `BenchScore` smuggles a hidden field via dict | `extra="forbid"` + static introspection test (`test_bench_score_static.py`) | CI fails before merge | Rename the field; never bypass |
| Sigstore network outage at anchor-publish time | OIDC fetch fails | Anchor not published; nightly job red | Operator gets paged; chain-head still local-verifiable; anchor catches up next day |

Two non-failure-modes worth explicitly stating: a bench case representing a hostile real-world scenario (e.g., a repo with a known sandbox-escape attempt) is **curated intentionally** under `disposition: negative` — its `case.yaml` carries the same two signatures and the same digest as any other case. The distinction between *curated adversarial case* and *poisoned case* is bytes-on-disk identical until you read the provenance: a poisoned case is one whose `added_by` is unverifiable or whose `reviewed_by` is missing. Provenance integrity is therefore the load-bearing distinction, exactly as [ADR-0016 §Open questions §1](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) anticipates.

## Resource & cost profile

Per-case execution (concrete):

- Rubric microVM cold-start: 100–500ms (Firecracker) / 1–3s (gVisor-on-Lima for macOS dev).
- Cassette replay (system-under-test under bench, no live LLM): single-digit ms.
- Rubric scoring runtime: typically <1s; cap at 60s.
- Digest verification (per case): <50ms (BLAKE3 over a small directory).
- Chain append (per case): <10ms (one file write + one hash chain).

For a 30-case `migration-chainguard-distroless` bench run on Linux/CI: ~1 minute wall-clock total (dominated by microVM cold starts). On macOS dev under gVisor-on-Lima: 2–4 minutes.

**Cost of security (the explicit delta vs a security-naïve design):**

- Without microVM per rubric (in-process import): -100ms to -3s per case; **but eliminates TB-2 entirely**, opening RCE-on-operator-host.
- Without per-case cassette digest check: -50ms per case total; **but eliminates TB-8**, opening cassette-swap.
- Without Sigstore anchor: -2s per day; **but eliminates L6** (the divergence-detection layer that survives local-host compromise).
- Without two-signature requirement on bench cases: developer ergonomics +50%; **but eliminates the L1 control entirely** since merge-by-default contributors can act unilaterally.

I judge each cost worth paying. The nightly cadence ([ADR-0016 §Decision §5](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)) absorbs the wall-clock; the bench corpus is small and grows slowly; promotion is weeks-to-months ([ADR-0016 §Tradeoffs](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)), so the dev-loop friction is mostly invisible.

LLM cost per eval run (deferred to Phase 13 per [ADR-0016 §Open questions §3](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)): zero at run time under cassette discipline; nonzero only during `--unsafe-record`. The `BenchScore.cost_usd` field is populated from the cassette metadata (recorded cost at record-time), not from live charges, so the field is meaningful without re-spending.

## Test plan

Adversarial tests are first-class:

- **`tests/adversarial/test_rubric_malicious_outbound.py`** — `rubric.py` attempts `urllib.request.urlopen("http://attacker.example")`; assert `RubricSandboxEscape` recorded and harness emits a `block`-severity audit event; network never reached (verified via a tcpdump-monitored CI runner).
- **`tests/adversarial/test_rubric_env_read.py`** — `rubric.py` attempts `os.environ.get("ANTHROPIC_API_KEY")`; assert returned value is `None` because env is empty (mirrors [Phase 5 ADR-0012](../05-sandbox-trust-gates/ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md)'s adversarial test).
- **`tests/adversarial/test_case_poisoning_detected.py`** — flip one byte in a case directory's `expected/diff.patch` without updating `cases/digests.yaml`; assert `BenchCaseDigestMismatch` aborts the run.
- **`tests/adversarial/test_case_provenance_forged.py`** — author a `case.yaml` whose `added_by.signature` is a random string; assert startup verifies the signature and refuses the case.
- **`tests/adversarial/test_chain_tamper_detected.py`** — rewrite the second-newest `BenchRunRecord` in `.codegenie/bench/history/`; assert `audit.verify()` returns mismatch at that point and `promotion.recommend()` refuses to read.
- **`tests/adversarial/test_cassette_swap_detected.py`** — replace a cassette with a different one (different digest); assert `CassetteDigestMismatch`.
- **`tests/adversarial/test_promotion_apply_blocked.py`** — call `promotion.apply()` programmatically; assert `PromotionMustBeHumanAuthorized` raised, `promotion.apply.blocked` event emitted.
- **`tests/adversarial/test_bench_score_extra_forbid.py`** — attempt to construct `BenchScore(passed=True, score=1.0, breakdown={}, failure_modes=[], cost_usd=0.0, duration_seconds=0.0, confidence=0.95)`; assert Pydantic raises.
- **`tests/schema/test_bench_score_static.py`** — recursive field-name walk; rejects banned substrings (mirrors `test_objective_signals_static.py`).
- **`tests/schema/test_digests_yaml_bench.py`** — `tools/digests.yaml` has entries for every registered task class's rubric and microVM image.
- **`tests/fence/test_task_class_has_bench_dir.py`** — for each `@register_task_class`, assert directory contract.
- **`tests/fence/test_fence_ci_is_alive.py`** — workflow stanza checksum.
- **`tests/integration/test_eval_data_flow.py`** — golden hello-world bench fixture; end-to-end run; chain head matches expected.
- **`tests/integration/test_anchor_publication.py`** — Sigstore-mocked CI test; publishes an anchor; verifies signature and chain head.

A passing test plan means: (i) every adversarial test green; (ii) `codegenie bench verify --strict` returns zero gaps over 30 trailing simulated days; (iii) no `bench_score` reaches `promotion.recommend()` without a verified chain entry; (iv) no path in the codebase can construct a `BenchScore` carrying a forbidden field name; (v) the `apply()` interface is provably uncallable by code (only humans + git can move tiers).

## Risks (top 5)

1. **The microVM stack on macOS dev (gVisor-on-Lima) is operational debt.** Phase 5 picked DinD on macOS for trust-aware gates, accepting shared-kernel verdicts on developer laptops. I propose gVisor-on-Lima for the rubric (a different sandbox stack from Phase 5's), which means two macOS-dev stacks coexist. Cost: real. Alternative: accept shared-kernel rubric execution on macOS dev with `gate_isolation_class: "shared_kernel"` annotation propagated to the `BenchRunRecord`, and refuse to use shared-kernel-produced records for promotion decisions. This is the cleaner choice; I commit to it: **production-quality `BenchRunRecord`s come from Linux/CI Firecracker only; macOS dev records are flagged and ignored by `promotion.recommend()`.** Mirrors Phase 5 final-design §3 ("gate_isolation_class: shared_kernel always") for DinD.

2. **Two-person curation rule creates a single-point-of-failure on the second reviewer.** If the `security` role has only one human, every bench-case PR queues on one inbox. Mitigation: at least three humans with `security` role; reviewer-fatigue monitoring (Phase 13 dashboard hook). This is an org-policy risk, not a code risk.

3. **The demotion-on-regression behavior from [ADR-0016 §Decision §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) is ambiguous.** "Demotion is automatic on any production regression that the bench set fails to catch" — if "automatic" means "the next promotion recommendation drops the recommended tier," that aligns with humans-always-promote. If it means "the runner side-effects a tier change," that violates TB-6. **I commit to the first reading and flag this for the synthesizer.** A poisoned outcome ledger (A4) that synthesizes a fake "regression" entry is a path to *automatic demotion* — humiliating but non-catastrophic — but a path to *automatic promotion* via the same mechanism would be catastrophic.

4. **Sigstore dependency widens supply-chain attack surface.** Anchor publication requires the Sigstore transparency log being honest. If Sigstore is compromised, anchors are forgeable. Compensating control: maintain a parallel offline operator-signed anchor (GPG-detached signature alongside the Sigstore one). Belt + suspenders; cost is one extra signature per day.

5. **`bench/` checked into the same repo (per Phase 6.5 default) means every contributor with repo-read access can read all bench cases.** For vuln-remediation bench cases this is fine. For migration-chainguard-distroless cases that snapshot real customer repos under permissive license, it may not be. The decision to split into `codewizard-sherpa-benches` is deferred per [ADR-0016 §Open questions §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md); I lean toward splitting for the migration bench specifically once it grows, with stricter access control.

## Acknowledged blind spots

- **Wall-clock optimization.** I have not designed for parallelism (deliberately — sequential makes audit-chain integrity simpler). The performance lens will argue for it. Synthesizer should weigh.
- **Cost minimization.** Every per-case microVM spawn is paid. I have not designed cost-recovery via case-caching across runs; cache invalidation under my integrity model is non-trivial and worth deferring.
- **Operator UX.** Adding a bench case is a multi-step ceremony (two signatures, digest update, ADR amendment for new task class). This is the intended friction. Best-practices lens may reasonably push back.
- **The LLM-Judge un-deferral path.** [Phase 5 ADR-0008](../05-sandbox-trust-gates/ADRs/0008-llm-judge-persona-deferral.md) un-deferral is downstream of this harness ([ADR-0016 §"What this ADR explicitly resolves"](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)). I have not designed `bench/judgment-arbitration/` — leaving it for the synthesizer to decide whether the security shape I leave behind (microVM-isolated rubric, signed cases, chained scores) is sufficient when the Judge enters the loop. My read: it is. The Judge becomes one more "rubric-like" thing, isolated identically.
- **Reconciliation timing.** Outcome-ledger reconciliation (Phase 13) is the path from production regression → new `regression-converted` bench case. I have set the TB-7 contract but not the *cadence*. Phase 13 inherits the question; my design tolerates any cadence because each conversion is a `cases-pending/` draft requiring human approval.
- **Cassette regeneration drift.** Cassette-record-mode is `--unsafe-record` only; I have not designed a "re-record without paying full LLM cost" path. This is a Phase 13 cost concern.

## Open questions for the synthesizer

1. **Is the rubric microVM cost-justified on Phase 6.5's small bench?** With 10–30 cases per task class on the bronze tier, the overhead is ~30s per nightly run total. Performance lens will likely argue for `import bench.{name}.rubric` in-process with `bandit` static analysis as the control. My read: the security premium is worth it because the rubric is *control-plane code* — it gates promotion, and promotion gates blast radius. The synthesizer must resolve whether the security argument or the cost argument wins.

2. **Does `promotion.recommend()` need to be itself isolated?** I run it in the harness orchestrator process. If the orchestrator is compromised, recommendations can be forged — but humans-always-promote (TB-6) is the catch. Should `recommend()` also run in a microVM? My read: no — the recommendation is advisory and the audit chain it reads is independently verifiable from the published anchor; forging a recommendation in memory is useless without forging the chain on disk, which the chain verify catches.

3. **The [ADR-0016 §Decision §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) demotion clause — does "automatic" mean side-effect or recommendation-shift?** See risk #3. I have committed to the recommendation-shift reading. If the synthesizer disagrees, the design needs the `apply()` interface to be writable for demotion only, which is a non-trivial asymmetry; I would argue against it on the grounds that asymmetric authorization is a frequent source of bugs.

4. **Should the daily anchor PR be auto-merged?** It is generated by a job, contains exactly one new file under `audit/anchors/bench/<date>.json`, and serves the L6 purpose only if it lands in git. Two options: (a) auto-merge with a narrow exception to "humans always merge" — the precedent [production ADR-0009](../../production/adrs/0009-humans-always-merge.md) reserves for "narrow exceptions to be ADR-amendable"; (b) require human merge, accepting that anchor publication may lag. My lean: option (a) with an ADR amendment, because the anchor is *self-attesting data* not new code. Synthesizer should weigh.

5. **Is `bench/` in the same repo, or split?** [ADR-0016 §Open questions §4](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) defers this. Security argument: split, so bench-write-access is governed separately from code-write-access. Operational argument: same repo, so the fence-CI tests run atomically with code changes. My lean: same repo for Phase 6.5; split when migration-chainguard-distroless graduates to silver (~tier promotion would itself trigger the split). The synthesizer can confirm or push back.

6. **Should the operator's Sigstore OIDC identity be persisted in `BenchRunRecord.operator_fingerprint` as the identity string, or as a hash thereof?** Identity string is auditable but leaks who ran the bench. Hash is privacy-respecting but un-auditable post-hoc without a side channel. My lean: hash, with the side channel being a `audit/operators.yaml` mapping that itself is two-signature-protected. Synthesizer can resolve.
