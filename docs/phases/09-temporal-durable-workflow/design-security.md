# Phase 09 — Durable workflow envelope: Temporal: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-23

---

## Lens summary

Phase 9 is the moment the system grows a **persistent, queryable record of everything that has ever happened**, and the moment workers stop being ephemeral in-process actors and become **long-lived daemons holding cluster credentials, Postgres credentials, GitHub credentials, microVM control-plane credentials, and LLM API keys** simultaneously. The security center of gravity therefore shifts: Phases 1–8 worried about the *gather pipeline runtime closure* (no LLM, no subprocess escape, sanitized output) and the *sandboxed gate VM* (ADR-0012). Phase 9 adds three brand-new high-value attack surfaces — **(i)** the Temporal cluster + its workflow history store, **(ii)** the Postgres side-channel event log (canonical audit substrate per ADR-0034), and **(iii)** the long-lived activity worker process — and one new supply-chain entry-point, **alembic migrations**.

The security posture this design adopts:

1. **Workflow history is treated as PII-and-secret-equivalent storage** from day 1. Anything an activity returns is preserved in Temporal history *forever* unless we explicitly redact it. Therefore: **redaction at the seam, not at the sink** — activity inputs/outputs are `RedactedWorkflowPayload` smart-constructed values, never raw `dict`s.
2. **Each Temporal worker holds the smallest possible set of credentials** — partitioned by **task-class-scoped task queues** with worker-side allowlists, not one omnibus "do everything" worker. A compromise of the npm-lockfile recipe worker must not give an attacker GitHub-PR-write or LLM-billing access.
3. **The Postgres event log is append-only by enforcement, not by convention.** A `REVOKE UPDATE, DELETE, TRUNCATE` on the `events` table plus a `BEFORE UPDATE OR DELETE` trigger that raises, plus a per-event `prev_hash` BLAKE3-chained envelope, mean tampering requires database-superuser plus content-chain forgery — not just an SQL injection in a downstream projection.
4. **Replay-determinism is a security property, not a correctness property.** A non-deterministic workflow read of ambient state (env var, clock, file) means a forensic replay shows different events than what actually executed. We forbid it at the type level (`LangGraphActivityPort` Protocol with no I/O methods) and prove it at the test level (`WorkflowEnvironment` replay-determinism gate).
5. **Alembic is a supply-chain entry-point and is fenced accordingly.** Migration scripts are reviewed under CODEOWNERS, their SHAs are pinned in a `tools/alembic-revisions.lock`, the CI runs each migration against a real Postgres and snapshots the resulting schema, and the migration runner runs as a **dedicated DDL-only Postgres role** that has no access to application data.
6. **temporal-ui is local-only, full stop.** Phase 9 does not introduce a network-reachable Temporal UI under any condition. Local dev binds to `127.0.0.1` only, with a `start-dev` wrapper that rejects `--ip 0.0.0.0`. A separate Phase (15+/operator portal — already governed by ADR-0035 and Phase 13.5) owns the authenticated, role-scoped read view.
7. **Humans always merge — and now, humans always migrate.** ADR-0009 applies in spirit to schema changes too: alembic `upgrade head` is never run by an automated worker against production; it is a separately-authenticated human-gated CD step.

This design **does not** introduce a KMS, a secrets broker, or hardware-tokenized worker identities — those land in Phase 13/13.5 alongside the operator portal and ROI dashboard. Phase 9's discipline is *invariants that are cheap-to-add-now-and-impossible-to-retrofit*: typed redacted payloads, append-only chain, role-scoped Postgres grants, task-queue partitioning, replay-determinism fences.

---

## Threat model

### Assets to protect

| # | Asset | Why it matters |
|---|---|---|
| A1 | **Temporal workflow history** | Contains every activity input/output for every workflow. A naive activity that takes `GitHubToken` as an arg writes the token into history *forever*. History is the long-tail attack surface. |
| A2 | **Postgres event log (`events` table)** | Canonical audit primitive per ADR-0034. Cost ledgers, KG writes, gate decisions, plugin resolutions, merge outcomes all project from it. Tampering with one row poisons every projection downstream. |
| A3 | **Activity worker process credentials** | Each worker holds: GitHub PAT (PR open + commit), LLM API key (cost-attributable), microVM control-plane creds (sandbox spawn), Postgres event-log write creds, Temporal namespace mTLS cert. A compromised worker is a portfolio-wide blast radius. |
| A4 | **Temporal cluster credentials** | Namespace mTLS cert + Temporal Cloud API key (if Cloud). Lets an attacker enumerate every workflow ever run, fake signals, and (with admin scope) terminate or replay arbitrary workflows. |
| A5 | **Postgres data-at-rest** | Workflow checkpointer state + event log. If exfiltrated, attacker reads every past workflow's decisions, every CVE-remediation strategy, every Knowledge-Graph projection. |
| A6 | **Alembic migration scripts + their dependency closure** | A poisoned migration can `CREATE EXTENSION ... LANGUAGE plpython3u` and execute arbitrary SQL — including reading the event log and exfiltrating to a remote host via `COPY ... TO PROGRAM`. |
| A7 | **temporal-ui credential surface** | If exposed beyond loopback, it's an authn-less workflow-history reader (the local dev UI has no auth by default). |
| A8 | **The replay-determinism contract** | A workflow that reads ambient state silently de-anchors the forensic audit trail. A forensic replay shows what we *thought* we ran; production shows what we *actually* ran. |

### Adversaries assumed

| Adversary | Capability | In scope this phase? |
|---|---|---|
| **External network attacker** | Internet-facing — only matters if temporal-ui or Postgres is exposed. | Yes — fenced by binding to loopback + `pg_hba.conf` `local` + `host 127.0.0.1`. |
| **Prompt-injection in a workflow input** | Adversarial content reaches an activity that calls an LLM. Activity output gets logged into workflow history. | Yes — output redaction + LangGraph subgraph already treats repo content as untrusted (Phase 8 `ContextBundle.contains_repo_content` flag). |
| **Compromised activity worker** | An attacker has RCE inside one worker process. | **Primary new threat this phase.** Mitigated by task-queue partitioning + per-queue credential scoping + capability tokens. |
| **Insider with DB read** | Read-only Postgres credentials leaked (e.g. via env file). | Yes — encryption-at-rest + column-level encryption for `events.payload` (`pgcrypto`) limits damage; redaction at write time means encrypted-but-still-tokenless is the state at rest. |
| **Insider with DB write** | A developer (or compromised migration) wants to silently rewrite an event. | Yes — `REVOKE UPDATE`/`DELETE` + `BEFORE` trigger + BLAKE3 prev-hash chain. Defeating all three requires DB-superuser AND content-forgery AND committing to the source-controlled trigger removal. |
| **Supply-chain attacker via PyPI** | A malicious `temporalio`/`alembic`/`psycopg` release. | Yes — `uv.lock` SHA-pin, plus the existing `tests/unit/test_pyproject_fence.py` extended to assert these packages remain at locked digests; `make lint-imports` ensures only sanctioned modules import them. |
| **Supply-chain attacker via Postgres extension** | A `CREATE EXTENSION` in a migration brings in C code with a backdoor. | Yes — migration role grants do not include `CREATE EXTENSION`; the allowlist is `{pgcrypto, pg_stat_statements}` set up at cluster init by a separate bootstrap role. |
| **Sandbox-escaped code from Phase 5 gate** | Already covered by ADR-0012 (microVM). Phase 9 must not *re-open* that boundary. | Yes — no shared volume between activity-worker host and microVM; no Temporal-cluster network reachability from inside the microVM. |
| **Disgruntled operator** | Authenticated team member runs `temporal workflow terminate` on a hot workflow, or `DELETE` on an event row. | Yes — operator actions emit audit events; destructive Temporal admin actions require a second-factor (`--operator-ack`-style) and emit `temporal.admin.action` events. |
| **Replay-determinism subversion** | A bug or malicious commit smuggles an `os.environ` read into workflow code. | Yes — Phase 9 ships a static check (AST walker over `platform/temporal/workflows/*.py`) that bans `os.environ`, `time.time`, `datetime.now`, `random`, `uuid.uuid4`, `socket`, `open`, `requests`. The fence pattern is the project-standard mechanism. |

### Attack surfaces specific to this phase

| Surface | Adversarial input shape | Containment |
|---|---|---|
| **Temporal worker `Activity.start` payload** | `WorkflowInput` Pydantic model deserialized from a `Signal` or workflow-start request. Adversary may smuggle large strings, base64-bombs, secret material, untrusted repo content. | Pydantic `extra="forbid"` + size caps + redaction via `RedactedWorkflowPayload` smart constructor that scrubs known secret shapes (`AWS_*`, `GITHUB_*`, `*_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`, JWTs by regex). |
| **Temporal workflow history readback** | Whatever an activity returned. | Returned values cross the `OutputSanitizer` (extends Phase 1 sanitizer) before the `return` statement; an `_sanitized: Literal[True]` discriminator on the return type means an unsanitized return is a type error. |
| **Postgres `events.payload` JSONB column** | App-controlled but cross-cutting: cost amounts, plugin IDs, signals — all derive from gate runs that consume untrusted content. | (a) Pydantic-typed at write; (b) `pgcrypto` symmetric-encrypted at rest with a key issued via `psql ... \set` rather than env (key never lands on disk in the worker container); (c) per-row BLAKE3 `prev_hash` chain so tamper is detectable by projection-side verification. |
| **Alembic upgrade path** | `.py` file imported and executed at migration time. | Dedicated DDL-only role + `tools/alembic-revisions.lock` + CI step that runs every migration against a fresh Postgres and snapshots the resulting schema diff into `tests/fence/test_alembic_schema_snapshot.py`. |
| **Workflow-history secret leakage via exception traceback** | An activity raises an exception whose `__str__` includes a credential (libraries do this). | Custom `ActivityErrorSanitizer` middleware on the worker registers a Temporal `failure_converter` that runs the message + traceback through the same regex/Pydantic redactor used for return values. |
| **Event-log tampering via direct SQL** | A maintainer or compromised credential issues `UPDATE events SET payload = ... WHERE event_id = ?`. | `REVOKE UPDATE, DELETE, TRUNCATE ON events FROM application_role`; `BEFORE UPDATE OR DELETE` trigger raises `EXCEPTION 'events is append-only'`. Defeat requires owning the `migrations_role` *and* deploying a migration that drops the trigger — visible in source control diff. |
| **temporal-ui exposure** | `temporal server start-dev` default-binds `127.0.0.1:8233` but a `--ip 0.0.0.0` flag exposes it network-wide with no auth. | A wrapper script `scripts/temporal-dev.sh` is the only sanctioned invocation; rejects any non-loopback `--ip`; CI test asserts no checked-in invocation uses `0.0.0.0`. |
| **`WorkflowEnvironment` test escape into CI** | A test that thinks it's in `WorkflowEnvironment.from_local()` but actually points at production-like cluster credentials. | `WorkflowEnvironment` fixture asserts `NEXT_PUBLIC_TEMPORAL_HOST` is unset or `localhost`; CI gates fail if a real cluster cert is present in the test env. |
| **`LangGraph ↔ Temporal bridge`** | A LangGraph node reads `os.getpid()` for a "trace id"; under Temporal replay, the pid differs → determinism violation → silent state divergence. | The `LangGraphActivityPort` Protocol disallows direct LangGraph execution inside workflow code: workflows call `await execute_activity(LangGraphSubgraphActivity, ...)`. The activity is the determinism boundary. |

### Trust boundaries

```
   ┌──────────────────────────────────────────────────────────────────┐
   │   ZONE 0 — Untrusted (internet, repo content, LLM output)        │
   └───────────────────────────────┬──────────────────────────────────┘
                                   │  PR webhooks, repo bytes, LLM responses
                                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   ZONE 1 — microVM (ADR-0012)                                    │
   │   - No host filesystem, no Temporal reach, no Postgres reach     │
   │   - No credentials at all                                        │
   │   - Returns ONLY a typed ObjectiveSignals struct                 │
   └───────────────────────────────┬──────────────────────────────────┘
                                   │  ObjectiveSignals (typed, validated)
                                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   ZONE 2 — Activity Worker (NEW — Phase 9)                       │
   │   - Holds: scoped credentials per task queue                     │
   │   - Network: Temporal frontend + Postgres + LLM endpoint +       │
   │              GitHub API + microVM control plane                  │
   │   - All outbound calls behind capability tokens                  │
   │   - Output sanitizer mandatory before any return                 │
   └───────────────────────────────┬──────────────────────────────────┘
                                   │  RedactedWorkflowPayload only
                                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   ZONE 3 — Workflow Code (deterministic, pure)                   │
   │   - No I/O, no clock, no env, no random, no network              │
   │   - Static check enforces (`tests/fence/workflow_determinism.py`)│
   │   - Sees only RedactedWorkflowPayload values                     │
   └───────────────────────────────┬──────────────────────────────────┘
                                   │  Pydantic typed events
                                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   ZONE 4 — Temporal cluster                                      │
   │   - mTLS namespace isolation                                     │
   │   - History store encrypted-at-rest (Postgres TDE)               │
   │   - temporal-ui bound 127.0.0.1 only                             │
   └───────────────────────────────┬──────────────────────────────────┘
                                   │
                                   ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   ZONE 5 — Postgres event log (canonical, append-only)           │
   │   - REVOKE UPDATE/DELETE on `events` from application_role       │
   │   - BLAKE3 prev_hash chain                                       │
   │   - pgcrypto column-level encryption on payload                  │
   │   - DDL role distinct from DML role distinct from read role      │
   └──────────────────────────────────────────────────────────────────┘
```

**Trust direction:** Zone N can read from Zone N+1 only through a typed Port; Zone N+1 must validate Zone N's input through a smart constructor. **No zone reads through more than one level.** The activity worker (Zone 2) is the *only* place that holds credentials; the workflow (Zone 3) sees only opaque tokens it cannot use directly.

---

## Goals (concrete, measurable)

| # | Goal | Target | Why |
|---|---|---|---|
| G1 | **Sandbox escape risk** | Phase 9 introduces **zero new pathways from microVM-resident code to the Temporal cluster, Postgres, or any credential**. CI test: a microVM with the gate-runner image cannot resolve the Temporal frontend DNS name and cannot reach Postgres on its private CIDR. | ADR-0012 stays intact. |
| G2 | **Credential blast radius if a worker is compromised** | A compromised `vuln-remediation-node-worker` cannot: (a) open PRs on a repo outside the active workflow's allowlist; (b) call an LLM for any task class except its own; (c) write Postgres events for `event_type` outside its allowlist; (d) terminate or signal any workflow except its own. Enforced by per-task-queue credentials + capability tokens; verified by 4 explicit "what a hostile worker can do" tests. | Task-queue partitioning is the only credential-segmentation primitive Temporal gives us natively. We use it fully. |
| G3 | **Audit completeness target** | **100%** of `TrustGate*`, `LlmInvoked`, `PrOpened`, `WorkflowTerminated`, `ActivityFailed` events land in the Postgres event log within 5 s of the underlying activity completion. Lost-event SLO: **0 events** allowed to be dropped silently — drops are detected by gap-detection in BLAKE3 chain monotonic sequence. | ADR-0034 makes the event log canonical; partial coverage means partial audit, which is worse than honest "we don't audit X." |
| G4 | **Allowed network egress** | **Activity worker:** Temporal frontend (mTLS), Postgres (`5432`), GitHub API (`api.github.com:443`), LLM endpoint (provider-specific `:443`), microVM control plane (internal RPC). **Temporal cluster:** Postgres, intra-cluster only. **Postgres:** none (no outbound). **microVM:** as per ADR-0012 (registry + gate-result endpoint only). | Default-deny egress at the container/pod NetworkPolicy level; allowlist documented in `platform/temporal/network-policy.yaml`. |
| G5 | **Workflow-history retention + redaction policy** | History retention: **365 days** (matches ADR-0040 data lifecycle for audit-class data). Redaction: every activity input and output passes through `RedactedWorkflowPayload` smart constructor — type-system enforced, not convention. Test: introspect every `@activity.defn` and assert its signature uses `RedactedWorkflowPayload` (or a `Sealed*` subclass) at every parameter and return. | History is forever-until-expired; we cannot redact retroactively without rewriting history (a security-aside cost we refuse to pay). |
| G6 | **Append-only event-log integrity** | An attacker with `application_role` Postgres credentials cannot mutate or delete a row in `events`. Verified by an `adv-integration` test that connects as that role and asserts each of `UPDATE`, `DELETE`, `TRUNCATE`, `DROP TABLE`, `ALTER TABLE events DISABLE TRIGGER` raises `InsufficientPrivilege`. | Defense in depth: grants + trigger + chain hash. |
| G7 | **Replay-determinism gate** | The CI suite replays every fixture workflow's recorded history (via `Replayer`) and asserts deterministic equivalence. A diff between recorded and replayed history fails the build. | Determinism is the security primitive that makes the audit trail trustworthy. |
| G8 | **temporal-ui exposure** | `temporal-ui` reachable on `127.0.0.1:8233` only. No checked-in invocation uses `--ip 0.0.0.0`. A `grep` fence test asserts this on every PR. | We do not invent an auth story for the dev UI; we do not let it leak. |
| G9 | **Alembic supply-chain integrity** | (a) Every migration in `alembic/versions/` has a SHA pinned in `tools/alembic-revisions.lock`; CI verifies; (b) the migration role has no `SELECT`/`INSERT`/`UPDATE`/`DELETE` on application tables, only DDL; (c) running each migration against a fresh Postgres in CI produces a schema snapshot that diffs against the in-repo `tests/fence/alembic_schema.sql.snapshot`. | Migrations are code execution against the most sensitive store; their supply chain is treated like recipe code. |
| G10 | **Capability-token discipline** | Every privileged side-effect call inside an activity (PR open, LLM invoke, event-log write of cost > $0.01, workflow signal) takes a typed capability token (e.g. `PrOpenCapability`, `LlmSpendCapability(budget_usd)`, `EventLogWriteCapability(event_types: frozenset[EventType])`). Tokens are minted at worker startup based on task-queue identity and are non-forgeable (typed, not stringly-typed). | Capabilities are the cheapest way to make "who can do what" auditable at the type level. |

---

## Architecture

```
EXTERNAL (Zone 0)
═════════════════════════════════════════════════════════════════════
  GitHub webhooks · CVE feeds · operator CLI · PR review responses
       │                              │                    │
       ▼ (HTTPS only)                 ▼                    ▼
═════════════════════════════════════════════════════════════════════
TEMPORAL FRONTEND (Zone 4 — mTLS namespace boundary)
   - mTLS-terminated; client certs scoped to {namespace, task-queue}
   - No public DNS; behind internal LB only
   - Workflow-start API: rate-limited per client cert
       │
       │ workflow_id, run_id, signals, queries
       ▼
═════════════════════════════════════════════════════════════════════
WORKFLOW CODE (Zone 3 — DETERMINISTIC SHELL)
                                                ┌───────────────────────┐
                                                │ Fence test:           │
                                                │ AST walker over       │
   ┌────────────────────────────────────┐       │ workflows/*.py rejects│
   │ Workflow:                           │      │ os.environ, time.time,│
   │   - sees ONLY RedactedWorkflowPayload│ ◀──── datetime.now, random, │
   │   - calls execute_activity(...)     │      │ uuid.uuid4, socket,   │
   │   - emits AppendEvent(...) via      │      │ open, requests.       │
   │     EventLogActivity ONLY           │      │ Enforced in CI.       │
   └─────────────┬───────────────────────┘      └───────────────────────┘
                 │ activity name + RedactedPayload
                 ▼
═════════════════════════════════════════════════════════════════════
ACTIVITY WORKERS (Zone 2 — TASK-QUEUE-PARTITIONED)
                                                          ┌─────────────────────┐
   ┌──────────────────────┐    ┌──────────────────────┐   │ Worker startup:     │
   │ Worker A             │    │ Worker B             │   │  - Reads task queue │
   │ task_queue:          │    │ task_queue:          │   │    identity         │
   │   "vuln-node-npm"    │    │   "migration-py-pip" │   │  - Mints capability │
   │ Has credentials for: │    │ Has credentials for: │   │    tokens scoped    │
   │  - GitHub:           │    │  - GitHub: (none —   │   │    to that identity │
   │     scoped to        │    │    Phase 7+ scope)   │   │  - Tokens injected  │
   │     vuln-PR opens    │    │  - LLM: migration    │   │    into activities  │
   │  - LLM: vuln budget  │    │    budget            │   │    via DI; never on │
   │  - Postgres:         │    │  - Postgres:         │   │    network          │
   │    event_types ⊂     │    │    event_types ⊂     │   └─────────────────────┘
   │    {vuln.*, cost.*}  │    │    {migration.*}     │
   │  - microVM:          │    │  - microVM:          │
   │    gate-runner only  │    │    gate-runner only  │
   └────────┬─────────────┘    └─────────┬────────────┘
            │                            │
            │  Each activity invocation:                  ┌────────────────────────┐
            │   (1) Validates input via Pydantic           │ OUTPUT SANITIZER       │
            │   (2) Calls side-effect through              │   - extends Phase 1    │
            │       capability token                        │     sanitizer          │
            │   (3) Sanitizes output via                    │   - regex + Pydantic   │
            │       OutputSanitizer ─────────────────────▶  │     scrub of           │
            │   (4) Returns RedactedWorkflowPayload          │     known secret       │
            │                                                │     shapes             │
            ▼                                                │   - introspection test │
═════════════════════════════════════════════════════════════└────────────────────────┘
EXTERNAL SIDE-EFFECT TARGETS
   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
   │ GitHub API      │  │ LLM provider    │  │ microVM control │
   │ (per-workflow   │  │ (per-task-class │  │ plane (ADR-0012)│
   │  PAT, short TTL)│  │  API key)       │  │                 │
   └─────────────────┘  └─────────────────┘  └─────────────────┘
            │
            │ Side-effect outcomes
            ▼
═════════════════════════════════════════════════════════════════════
POSTGRES (Zone 5 — append-only, role-scoped)
   ┌────────────────────────────────────────────────────────────────┐
   │ Database: codegenie                                            │
   │ Roles:                                                          │
   │   - migrations_role: DDL only; no SELECT/INSERT/UPDATE/DELETE   │
   │     on application tables. Used by alembic. Owned password,    │
   │     rotated each deploy.                                        │
   │   - application_role: INSERT on events; SELECT on events;       │
   │     SELECT on materialized projections; NO UPDATE/DELETE       │
   │     anywhere; NO DDL.                                          │
   │   - read_role: SELECT on materialized projections only;        │
   │     used by ROI dashboard, operator portal (Phase 13.5).       │
   │   - temporal_role: full ownership of temporal_state schema     │
   │     (separate logical DB from application data).                │
   │                                                                 │
   │ Tables (events table; append-only):                            │
   │   events (                                                      │
   │     event_id    uuid PRIMARY KEY,                              │
   │     workflow_id text NULL,                                      │
   │     event_type  text NOT NULL,                                  │
   │     timestamp   timestamptz NOT NULL,                          │
   │     payload     bytea NOT NULL,  -- pgcrypto symmetric         │
   │     prev_hash   bytea NOT NULL,  -- BLAKE3(prev row's hash     │
   │                                  --  || canonical_payload)     │
   │     row_hash    bytea NOT NULL,  -- BLAKE3 of this row         │
   │     seq         bigint GENERATED ALWAYS AS IDENTITY,           │
   │     UNIQUE (workflow_id, seq)                                  │
   │   );                                                            │
   │                                                                 │
   │ Trigger: events_immutable BEFORE UPDATE OR DELETE OR TRUNCATE  │
   │   RAISE 'events is append-only; mutation denied';              │
   │                                                                 │
   │ Encryption: pgcrypto column on `payload` with key supplied via │
   │   per-session psql variable (never on disk in worker          │
   │   container).                                                  │
   └────────────────────────────────────────────────────────────────┘

═════════════════════════════════════════════════════════════════════
TEMPORAL-UI (Zone 4, local-dev only)
   ┌─────────────────────────────────────┐
   │ temporal server start-dev wrapper   │
   │   - bind 127.0.0.1:8233 only        │
   │   - rejects --ip 0.0.0.0            │
   │   - per-developer ephemeral DB      │
   │   - not deployed to any shared env  │
   └─────────────────────────────────────┘
```

**Trust boundaries are marked by the `═══` lines.** Each crossing is a typed Port; each Port has a documented adversarial-input shape; each Port has a sanitizer or capability check.

---

## Components

### 1. Workflow definitions (`platform/temporal/workflows/`)

- **Purpose.** Deterministic orchestration of the 7-stage pipeline; each LangGraph subgraph is wrapped as a Temporal Activity payload (per ADR-0003).
- **Trust level.** Zone 3 — fully deterministic, no I/O, no credentials.
- **Interface.** `@workflow.defn` classes. All inputs are `RedactedWorkflowPayload` subtypes (smart-constructed). Adversarial inputs: workflow-start arg may contain untrusted repo content (already sanitized at gather time, but treated as untrusted again here per Phase 8 `contains_repo_content` flag).
- **Isolation.** Static AST fence (`tests/fence/test_workflow_determinism.py`) bans `os.environ`, `time.time`, `datetime.now`, `random.*`, `uuid.uuid4`, `socket`, `open`, `requests`, `httpx`, `subprocess`. Allowed: `workflow.now()`, `workflow.uuid4()`, `workflow.logger`, `workflow.execute_activity`. Pre-commit hook + CI enforce.
- **Credentials & TTL.** **None.** Workflow code never touches credentials. Any privileged operation routes through an Activity holding a capability token.
- **Audit emissions.** Workflows emit events via the `EventLogActivity` (the *only* sanctioned writer to the Postgres event log). Direct DB access from workflow code is impossible because workflow code has no DB driver in its import closure (enforced by `import-linter`).
- **Tradeoffs.** Determinism rules are surprising to new contributors. We pay for the fence test + onboarding doc; we keep the security primitive.

### 2. Activity workers (`platform/temporal/workers/`)

- **Purpose.** Imperative shell — runs activities, holds credentials, calls side-effect endpoints.
- **Trust level.** Zone 2 — highest local trust; primary new attack surface.
- **Interface.** `@activity.defn` async functions. Input: `Sealed[T]` smart-constructed payload; output: `RedactedWorkflowPayload`. **No `Any`, no `dict`, no `**kwargs` at activity boundaries** (mypy strict + a fence test that introspects every registered activity).
- **Isolation.**
  - **One worker process per task queue**, partitioned by `(task_class, language, build_system)` — same scoping primitive as plugin IDs. Examples: `worker.vuln-remediation--node--npm`, `worker.migration--node--npm`, `worker.assessment--*--*`.
  - Each worker process: distinct Linux user, distinct container with read-only root filesystem, distinct credentials at mount time (Kubernetes Secret + per-Pod ServiceAccount).
  - Worker processes do **not** import each other's activity modules — registry-based import discipline + `import-linter` boundary tests.
- **Credentials & TTL.**
  - **GitHub PAT:** short-lived GitHub App installation token, scoped to the active workflow's repo + the `pull-requests:write` and `contents:write` scopes only. TTL: 1 hour, refreshed by the worker via the App's JWT.
  - **LLM API key:** per-task-class key (`ANTHROPIC_API_KEY_VULN`, `ANTHROPIC_API_KEY_MIGRATION`). Per-key billing alerts at 110% of the workflow-level cap (ADR-0025).
  - **Postgres event-log write:** `application_role` credential, scoped per-task-class via the `EventLogWriteCapability(event_types: frozenset[EventType])` token.
  - **Temporal namespace mTLS cert:** scoped to the worker's task queue. Cert rotation: 30 days.
  - **microVM control plane:** workload-identity (JWT) rather than long-lived API key; minted at activity start, exchanged for a short-lived scoped credential.
- **Audit emissions.** Every activity emits exactly one terminal event (`ActivitySucceeded` / `ActivityFailed`) into the event log via the `EventLogActivity`. A wrapper decorator `@audited_activity` enforces this; failure to emit raises at activity-completion time.
- **Tradeoffs.** Operating many workers > operating one. Bought back by: (a) blast radius capped per task class; (b) credential rotation per worker is cheaper than per-system; (c) per-queue resource limits map to per-queue cost caps (ADR-0025). The dev experience cost (developers need to know which worker they're poking) is paid by a `make workers` aggregator + uniform logging.

### 3. Temporal cluster auth (mTLS namespace isolation)

- **Purpose.** Cluster-edge authentication and namespace-level workflow isolation.
- **Trust level.** Zone 4.
- **Interface.** mTLS-terminated frontend. Each client (worker, operator CLI, CI tester) presents a cert that names a namespace + task queue. Namespaces are partitioned by environment (`dev`, `ci`, `staging`, `prod`) and never share workflow data.
- **Isolation.** Cluster runs as its own deployment, no shared kernel with worker pods. Cluster pods cannot reach the GitHub API, LLM endpoints, or microVM control plane — purely internal.
- **Credentials & TTL.** mTLS certs from an internal CA, 30-day rotation. Temporal "API key" only on Cloud (subscription tier) — if used, mounted via short-lived vended credential, never checked in.
- **Audit emissions.** Cluster emits its own audit log (workflow.created, workflow.terminated, signal.sent) to the Postgres event log via a sidecar `TemporalAuditForwarder` activity.
- **Tradeoffs.** Cluster ops > no-cluster. ADR-0003 already accepted this tradeoff.

### 4. Postgres checkpointer (`platform/postgres/checkpointer/`)

- **Purpose.** Persist LangGraph state across `interrupt()` calls per ADR-0016. Replaces the Phase 6 SQLite checkpointer.
- **Trust level.** Zone 5.
- **Interface.** LangGraph's `PostgresSaver`. Workflow-id → serialized state map.
- **Isolation.**
  - **Row-level: separate logical database** (`codegenie_checkpoints`) from the canonical event log (`codegenie_events`). Different roles, different connection pools.
  - **State serialization is canonicalized** (deterministic field order) so that two checkpoints of the same state are byte-identical — enables tamper detection by hash comparison.
  - **Encryption at rest:** Postgres TDE (or LUKS at the volume level) + pgcrypto column on `state` blob with key per-environment.
- **Credentials & TTL.** `checkpointer_role` — `INSERT`, `SELECT`, `DELETE` on the checkpoints table only (deletes are normal lifecycle, not the events table). Per-worker connection pool with short connection lifetime (5 min).
- **Audit emissions.** Each checkpoint write emits a `WorkflowCheckpointed(workflow_id, version)` event into the canonical event log. Out-of-band tamper detection compares the hash of the latest checkpoint to the most recent `WorkflowCheckpointed` event's hash field.
- **Tradeoffs.** Two DBs > one DB. Bought back by: tamper-detection invariant + reduced blast radius if checkpointer creds leak (attacker gets state, not the audit trail).

### 5. Postgres event log (`platform/postgres/events/`)

- **Purpose.** Canonical append-only event log per ADR-0034.
- **Trust level.** Zone 5.
- **Interface.** Three Pydantic-typed write paths only, all routed through the `EventLogActivity`:
  - `AppendEvent(envelope: EventEnvelope, capability: EventLogWriteCapability)` — workflow code's only handle.
  - `AppendAuditEvent(envelope: EventEnvelope, capability: AuditWriteCapability)` — for operator-initiated and Temporal-cluster-sourced audit events.
  - `AppendSystemEvent(envelope: EventEnvelope, capability: SystemWriteCapability)` — for migration and bootstrap events; held only by the bootstrap process.
- **Isolation.**
  - **Append-only enforcement** at three layers: (a) Postgres `REVOKE UPDATE, DELETE, TRUNCATE`; (b) `BEFORE UPDATE OR DELETE` trigger raises; (c) BLAKE3 `prev_hash` chain.
  - **Per-row encryption** of `payload` JSONB column via `pgcrypto`. Key supplied via per-session `\set` from a sidecar credential broker, never on disk in the worker container.
  - **No `SELECT` for `application_role` on encrypted payload** — workers append, but cannot read other workers' events. Read-side projections run as `read_role` which has decryption capability scoped to read-time only.
- **Credentials & TTL.** See "Roles" in the architecture diagram. Migration role rotated each deploy; application_role rotated quarterly; read_role rotated quarterly with the operator portal's session lifetime aligned.
- **Audit emissions.** The event log audits itself: every `INSERT` into `events` triggers a row in `events_audit` (separate table) recording `(event_id, inserted_by_role, inserted_at, source_ip)`. This is the "who wrote this event" forensic trail.
- **Tradeoffs.** Three roles + triggers + encryption = significant DBA surface. Bought back by: defense-in-depth on the most-valuable single artifact in the entire system.

### 6. Alembic migration discipline (`alembic/`)

- **Purpose.** Schema evolution.
- **Trust level.** Zone 5 (operationally), but treated as supply-chain (a poisoned migration is code execution against the most sensitive store).
- **Interface.** `alembic upgrade head` invoked by a dedicated CD job, gated by human approval (ADR-0009 in spirit). Migrations are reviewed under CODEOWNERS.
- **Isolation.** `migrations_role` has `CREATE`/`ALTER`/`DROP` on schemas, but no `SELECT`/`INSERT`/`UPDATE`/`DELETE` on application tables. Cannot read `events.payload`. Cannot install extensions (allowlist is `{pgcrypto, pg_stat_statements}`, installed at cluster init by a separate `bootstrap_role`).
- **Credentials & TTL.** `migrations_role` credential is ephemeral, vended by the CD system for the migration window only (5–15 min), revoked at job end.
- **Audit emissions.** Each migration emits `MigrationApplied(revision_id, applied_at, applied_by)` via `AppendSystemEvent`. The `tools/alembic-revisions.lock` SHA chain provides offline tamper detection.
- **Tradeoffs.** Two roles + a lock file + a snapshot test = more ops surface. Bought back by: a poisoned `alembic/versions/*.py` is detected at PR review (CODEOWNERS), at CI (lock-SHA mismatch + schema-snapshot diff), and at deploy time (CD job uses ephemeral creds).

### 7. Workflow-history redaction (`platform/temporal/redaction/`)

- **Purpose.** Make secret leakage into Temporal history *impossible at the type level*, not "we're careful."
- **Trust level.** Zone 2 / Zone 3 boundary.
- **Interface.**
  - `RedactedWorkflowPayload` — Pydantic base class with `model_config = ConfigDict(extra="forbid", frozen=True)` and a `_sanitized: Literal[True]` marker field set only by the smart constructor `RedactedWorkflowPayload.seal(model)`.
  - `seal(model)` runs the regex/Pydantic scrubber over the model: rejects field names matching `^(.*_)?(KEY|TOKEN|SECRET|PASSWORD|PAT|CRED|JWT)(_.*)?$` (case-insensitive), and values matching JWT shape (`eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`), AWS-key shape (`AKIA[0-9A-Z]{16}`), GitHub-PAT shape (`ghp_[A-Za-z0-9]{36}` or `github_pat_`).
  - `RedactedWorkflowPayload` is the **only** type allowed at activity boundaries — enforced by a fence test that introspects every `@activity.defn` and every `@workflow.run` method signature.
- **Isolation.** The `_sanitized: Literal[True]` marker means an unsealed value is a type error at the boundary. Defeat requires constructing a bogus `_sanitized=True` literal, which is reviewable in source control.
- **Credentials & TTL.** N/A.
- **Audit emissions.** Each `seal()` call that *would have* let a secret through (regex matched, then redacted) emits a `RedactionFired(field_path, redaction_kind, workflow_id)` event. **High signal — even a single fire is a code-review trigger.**
- **Tradeoffs.** Smart-constructor pattern requires discipline. Bought back by: type system enforces "did you redact?" rather than humans hoping they remembered.

### 8. `SearchAttribute` vs `Memo` vs activity-input scrubbing

- **`SearchAttribute`** (queryable Temporal index) — restricted to a closed set of non-sensitive fields: `workflow_id`, `repo_id` (newtype), `task_class`, `status`, `created_at`. Fence test: any `SearchAttribute` added that isn't in this allowlist fails CI.
- **`Memo`** (non-queryable workflow annotation) — permitted for human-readable summaries, but each value passes through `seal()` first. Memos are not indexed; treat them as durable comments.
- **Activity-input scrubbing** — every activity input is a sealed `RedactedWorkflowPayload`. No exceptions.

### 9. temporal-ui exposure (`scripts/temporal-dev.sh`)

- **Purpose.** Local dev workflow inspection only.
- **Trust level.** Zone 4 boundary, dev-only.
- **Interface.** `scripts/temporal-dev.sh` wraps `temporal server start-dev` with a fixed `--ip 127.0.0.1 --port 8233 --ui-port 8233` and a check that rejects `0.0.0.0` or any non-loopback CIDR.
- **Isolation.** Binds to loopback. The `dev` Postgres is per-developer (ephemeral). No shared multi-user dev cluster.
- **Credentials & TTL.** None; no auth on the dev UI. This is *only* acceptable because it's loopback-only.
- **Audit emissions.** Dev UI usage is not audited; production has no UI in this phase.
- **Tradeoffs.** Dev convenience > prod-grade UI in Phase 9. The operator portal (Phase 13.5, ADR-0035) is the authenticated path; Phase 9 does not invent that.

### 10. LangGraph ↔ Temporal bridge (`platform/temporal/activities/langgraph_subgraph.py`)

- **Purpose.** Run a LangGraph subgraph as a Temporal Activity payload (per Phase 6's `VulnRemediationSut` contract).
- **Trust level.** Zone 2.
- **Interface.** `LangGraphSubgraphActivity(input: SealedSubgraphInput) -> RedactedSubgraphResult`. The subgraph internals (per Phase 6) remain plugin-local; the Temporal boundary sees only the Sealed input/output pair.
- **Isolation.** LangGraph runs *inside* the activity, never inside workflow code. This is the determinism boundary — LangGraph nodes are free to do clock reads, random, etc., because they're in the imperative shell.
- **Credentials & TTL.** Inherited from the activity worker — same capability tokens injected into the LangGraph state.
- **Audit emissions.** Each LangGraph node emits a `SubgraphNodeCompleted(workflow_id, subgraph_id, node_id, outcome)` event. The Phase 8 `RouteDecided` event remains as designed.
- **Tradeoffs.** A LangGraph node that wants to read ambient state still can — but only at the imperative-shell layer, where it's expected. The workflow stays deterministic; the activity is where reality enters. Forensic replay replays workflow code; the activity outputs are read from history (already final).

---

## Data flow

```
1) Workflow start
   GitHub webhook ──HTTPS──▶ Temporal frontend (mTLS)
                                       │
   [Zone 0 → Zone 4: client cert + namespace check]
                                       │
                                       ▼
2) Workflow code runs (Zone 3 — deterministic shell)
   await execute_activity(GatherActivity, RedactedRepoRequest.seal(req))
                                       │
   [Zone 3 → Zone 2: typed Sealed input, no credentials cross]
                                       │
                                       ▼
3) Activity worker (Zone 2 — credential-holding)
   - Worker validates input via Pydantic
   - Mints scoped capability tokens for this activity
   - Calls side-effect through tokens:
        ──── GitHub API (PrOpenCapability, scoped repo + TTL) ────▶ [Zone 0]
        ──── LLM provider (LlmSpendCapability, scoped budget) ───▶ [Zone 0]
        ──── microVM control plane (MicroVmSpawnCapability) ─────▶ [Zone 1]
   - microVM runs untrusted code (Zone 1), returns ObjectiveSignals (typed)
                                       │
   [Zone 1 → Zone 2: returns only typed signals; credentials never enter Zone 1]
                                       │
   - Activity assembles result, calls OutputSanitizer
   - OutputSanitizer: regex + Pydantic scrub of secret shapes
   - Returns RedactedWorkflowPayload.seal(result)
                                       │
   [Zone 2 → Zone 3: only sealed/redacted payload crosses back]
                                       │
                                       ▼
4) Workflow records outcome — calls EventLogActivity
   execute_activity(EventLogActivity, AppendEvent(envelope, capability))
                                       │
   [Zone 3 → Zone 2: AppendEvent activity scrubs payload again]
                                       │
                                       ▼
5) EventLogActivity writes to Postgres (Zone 5)
   - Connects as application_role (INSERT-only on events)
   - Computes prev_hash = BLAKE3(prev_row.row_hash || canonical_payload)
   - INSERT INTO events (... encrypted payload via pgcrypto ...)
   - Trigger events_immutable would block UPDATE/DELETE
                                       │
                                       ▼
6) Replay-driven audit (any time later)
   - Operator CLI / projection / forensic tool queries events
   - Verifies BLAKE3 chain integrity
   - Decrypts payload with read_role
   - Constructs audit view
```

**Credential mint/use/revoke points are explicit:**

- **Mint:** Worker startup (mTLS cert), GitHub App JWT exchange (per-activity), microVM control-plane workload identity (per-activity).
- **Use:** Inside the activity body only, via capability tokens — never passed back to workflow code.
- **Revoke:** TTL expiry (1 h for GitHub PAT, 30 d for mTLS cert), worker restart (clears in-memory tokens), capability-token scope expiration (per-activity).

---

## Failure modes & recovery

| # | Failure | Detected by | Containment | Recovery |
|---|---|---|---|---|
| F1 | **Sandbox escape from a Phase 5 gate VM** | Host-side eBPF monitor (Linux/CI); microVM hypervisor anomaly detection (Firecracker). | microVM has zero credentials and no Temporal/Postgres network reachability. Escape gives an attacker access to a credential-free, network-restricted process. | Kill microVM; emit `SandboxEscapeDetected` audit event; quarantine workflow; human reviews. ADR-0012 remains the boundary. |
| F2 | **Poisoned event written into Postgres** (compromised worker writes a fake `MergeOutcome`) | BLAKE3 prev_hash chain mismatch detected by projection verification. Each projection recomputes the chain head from its event window and compares to the latest. A divergence is a tamper signal. | Compromised worker can only INSERT events of its own scoped types — cannot UPDATE/DELETE prior events. The chain forces the fake event to be linked from a real prev_hash, so the chain is detectable from any later row. | Halt all projections; emit `EventChainBreak(detected_seq, expected_hash, actual_hash)`; human forensic review reconstructs the canonical chain. |
| F3 | **Prompt-injection in a workflow input** smuggles malicious instruction to LLM-leaf node | Phase 8's `contains_repo_content` provenance flag on `ContextBundle` marks repo bytes as untrusted; Phase 4 prompt-injection guard fires on activity-side LLM call. | LLM-leaf is inside the activity worker (Zone 2). Even if the model is jailbroken, its output is sandboxed in a microVM gate (Zone 1), and any side-effect attempts are bounded by capability tokens. | Gate fails → retry counter increments → ADR-0014 escalation to HITL. |
| F4 | **Compromised activity worker** (process RCE) | Anomalous capability-token usage pattern (e.g. PR-open for a repo outside the workflow's allowlist); LLM-spend cap breach; outbound network connection to unallowlisted host. | Per-task-queue partitioning means blast radius is bounded to that task class. Capability tokens reject out-of-scope calls. NetworkPolicy denies unallowlisted egress. | Drain worker (Temporal stops scheduling activities to it); rotate all credentials for that task queue; replay history from event log to reconstruct any in-flight workflow's true state. |
| F5 | **Alembic supply-chain compromise** (poisoned migration in a PR) | (a) CODEOWNERS review at PR time; (b) `tools/alembic-revisions.lock` SHA mismatch in CI; (c) schema-snapshot diff in CI; (d) migration role privilege ceiling at runtime. | Migration role cannot SELECT/UPDATE/DELETE application data, cannot CREATE EXTENSION outside allowlist, cannot install C extensions. A poisoned `DROP TABLE events` is fine — the role can't read the events to exfiltrate them first, and the BLAKE3 chain's tamper-trail is in the projections. | Revert the migration PR; reapply prior schema; investigate. The migration's blast radius is "schema corrupted but data not exfiltrated." |
| F6 | **temporal-ui exposed beyond loopback** (e.g. someone runs `--ip 0.0.0.0` on a shared dev box) | `tests/fence/test_temporal_ui_loopback.py` greps for `0.0.0.0` in checked-in scripts; runtime test asserts UI port is loopback-only on dev boxes. | Loopback bind means an attacker needs host access. Dev clusters are per-developer ephemeral; no production UI. | Kill UI process; rotate any credentials that may have been visible (workflow inputs are sealed, so the exposure is "workflow IDs and task names" — sensitive but not catastrophic). |
| F7 | **Replay-determinism violation** (workflow code reads ambient state) | (a) Static AST fence at CI time; (b) `Replayer`-based replay test in CI; (c) production canary that replays a workflow's history and diffs against recorded outcome. | Determinism violation makes audit trail unreliable; not directly exploitable but is a precondition to "forensic replay shows what we wanted to see, not what ran." | Fail the build; never deploy non-deterministic workflow code. Production canary catches drift introduced by upstream library changes (e.g. a new `random` call inside a vendor lib). |
| F8 | **Workflow-history secret leakage** (activity returns a credential by accident) | `OutputSanitizer` regex/Pydantic scrub fires; fence test introspects all activity signatures and asserts `RedactedWorkflowPayload` everywhere; canary scan over recent history for secret shapes. | Sanitizer fires before history write. History never sees raw. | Audit the offending code path; rotate the credential if a real leak ever ships. ADR-0040 retention means a leaked credential lives in history until expiry — so rotation is mandatory upon detection. |
| F9 | **Temporal cluster compromise** | Cluster audit log shows workflow.terminated for non-operator clients; signal.sent from unknown cert. | Cluster mTLS cert rotation; per-task-queue cert pinning; cluster pods isolated from worker pods (no shared kernel). | Rotate cluster CA; reissue all worker certs; replay all in-flight workflows from event log. |
| F10 | **Postgres data-at-rest exfiltration** (volume snapshot leaked) | Not directly detectable — assume eventual disclosure of any data-at-rest. | `pgcrypto` column-encryption on `events.payload` with key not on the volume; TDE/LUKS at the volume layer; `RedactedWorkflowPayload` scrubbing means even decrypted payload is secret-free. | Rotate column-encryption key; replay/re-derive projections against decrypted events; investigate disclosure path. |
| F11 | **Disgruntled-operator workflow termination** | `temporal workflow terminate` emits `WorkflowTerminatedByOperator(operator_id)` event into the audit table. | Destructive operator actions require an `--operator-ack` second factor; rate-limited per operator; non-revocable audit trail. | Operator is identified; postmortem follows; in-flight work is recovered from the event log (event-sourcing is the recovery mechanism). |
| F12 | **LangGraph subgraph node reads ambient state** (workflow-history-equivalent risk) | The LangGraph node runs inside an Activity (Zone 2), not the workflow code — so it CAN read ambient state. But its output crosses back through the OutputSanitizer. | The boundary is the Activity, not the LangGraph node. Determinism only matters at the workflow layer. | No recovery needed — by design. |

---

## Resource & cost profile

The cost of these controls (so the synthesizer can evaluate the tradeoff):

| Control | Cost | What's cheaper without it |
|---|---|---|
| Task-queue partitioning (one worker per task class) | Operating N workers vs one — ~2× container cost, ~1.5× cert/credential ops cost | One omnibus worker with all credentials. Saves ops, multiplies blast radius. |
| `RedactedWorkflowPayload` smart constructor everywhere | ~50–100 lines of seal/unseal boilerplate per phase; ~10% activity-author cognitive load | Direct Pydantic models at activity boundaries. Saves boilerplate, loses type-level secret-leak prevention. |
| Postgres role separation (3 roles + bootstrap) | ~80 lines of `pg_hba.conf` + `GRANT` discipline; one extra rotation flow | One application_role with full privileges. Saves DBA work, multiplies blast radius of credential leak. |
| BLAKE3 prev_hash chain on events | ~30 lines of trigger logic + ~5 ms write latency per event + per-projection chain-verify pass | Plain `INSERT` with no chain. Saves write latency, loses cryptographic tamper-detection. |
| `pgcrypto` column-encryption on payload | ~20% query latency overhead on the read path; key management complexity | Plain JSONB. Saves latency, loses encryption-at-rest of the most-valuable column. |
| AST fence on workflow determinism | One CI step (~5 s); one onboarding-friction tax | Convention-based determinism discipline. Saves onboarding; one stray `time.time()` poisons forensic replay forever. |
| Capability-token discipline | ~3–5 lines per privileged side-effect site; one capability type per side-effect class | Boolean `is_authorized` checks. Saves lines, loses type-level auditability. |
| Per-PR alembic SHA lock + schema snapshot | One CI step; one developer-friction tax on schema changes | Trust-the-PR-author. Saves CI minutes, loses supply-chain integrity on the most sensitive store. |

**Net assessment.** ~3× security-overhead in raw lines vs an unfenced design. The compounding-benefit primitive (Postgres event log + BLAKE3 chain + role separation) is impossible to retrofit later without rewriting history — Phase 9 is the only place these invariants are cheap-to-add.

---

## Test plan

### Adversarial tests (must ship in Phase 9)

| Test | What it proves |
|---|---|
| `tests/fence/test_workflow_determinism.py` | AST walker over `platform/temporal/workflows/*.py` asserts no banned import or call. |
| `tests/integration/test_workflow_replay_determinism.py` | Replays every fixture workflow history via `Replayer`, asserts no `NonDeterministicError` raised, asserts replayed outcome equals recorded outcome byte-for-byte. |
| `tests/fence/test_activity_payload_typing.py` | Introspects every `@activity.defn`, asserts all params and return types are `RedactedWorkflowPayload`-derived. |
| `tests/fence/test_workflow_input_typing.py` | Same, for `@workflow.run` methods. |
| `tests/adv/test_secret_leakage_in_history.py` | Constructs an activity input that smuggles each known secret shape (JWT, AWS-key, GitHub-PAT, env-var name regex). Asserts `seal()` rejects each. |
| `tests/adv/test_events_append_only_enforcement.py` | Connects as `application_role`, asserts each of `UPDATE`, `DELETE`, `TRUNCATE`, `DROP TABLE`, `ALTER TABLE events DISABLE TRIGGER` raises `InsufficientPrivilege`. |
| `tests/adv/test_event_chain_tamper_detection.py` | Inserts a row with an incorrect `prev_hash` (forcibly, via `bootstrap_role`); asserts a downstream projection's chain-verify pass detects the break. |
| `tests/adv/test_alembic_revision_lock.py` | For every file in `alembic/versions/`, computes SHA-256; asserts presence in `tools/alembic-revisions.lock`; lock file is the contract. |
| `tests/integration/test_alembic_schema_snapshot.py` | Runs every migration against a fresh Postgres in CI; dumps schema; diffs against `tests/fence/alembic_schema.sql.snapshot`; mismatch fails. |
| `tests/adv/test_temporal_ui_loopback.py` | Greps repo for `0.0.0.0`, `--ip 0.0.0.0` in any temporal-dev script; asserts none present. |
| `tests/adv/test_capability_token_scope.py` | A worker for `task_queue: "vuln-node-npm"` attempts to mint a `PrOpenCapability` for a repo not in the active workflow's allowlist; asserts the mint refuses. Same for LLM spend cap, event-log write capability, microVM spawn capability. |
| `tests/adv/test_microvm_network_isolation.py` | Inside a Phase-5 microVM, asserts: cannot resolve `temporal-frontend.internal`, cannot reach Postgres CIDR, cannot reach LLM provider, cannot reach worker host. Inherited from Phase 5 but re-tested here because Phase 9 adds the Temporal/Postgres targets. |
| `tests/adv/test_workflow_history_pii_canary.py` | Runs a canary workflow with a known fake secret as input (post-`seal()` it must be redacted); asserts the canary's recorded history does not contain the fake secret's value. Repeated for each secret shape. |
| `tests/adv/test_redaction_audit_event.py` | Runs `seal()` on a payload containing a fake secret; asserts a `RedactionFired` event lands in the event log. |
| `tests/adv/test_operator_action_audit.py` | Asserts `temporal workflow terminate` (test fixture) emits a `WorkflowTerminatedByOperator` event with operator identity. |
| `tests/adv/test_worker_credential_blast_radius.py` | Simulates a compromised `vuln-node-npm` worker (steal its credentials, attempt the four privileged actions on a `migration-py-pip` workflow); asserts all four fail. |

### `WorkflowEnvironment` based unit tests

- Activity-level: each activity tested with mocked side-effects, `RedactedWorkflowPayload` round-trips, capability-token enforcement.
- Workflow-level: in-process `WorkflowEnvironment` from `temporalio.testing`; durability tests kill the worker mid-activity, restart, assert continuation per roadmap exit criterion.

### Property-based tests

- `RedactedWorkflowPayload.seal()` is **idempotent**: `seal(seal(x)) == seal(x)`. Hypothesis-generated payloads.
- BLAKE3 chain construction is **monotonic**: appending events in order preserves chain validity; reordering breaks it.
- Capability tokens are **non-forgeable** at the type level: hypothesis-generated raw `str`/`dict` payloads cannot be passed where a `PrOpenCapability` is required.

### Mutation tests

- Mutate the `OutputSanitizer` regex (drop a token-shape pattern); assert the `test_secret_leakage_in_history.py` adversarial test catches the mutant.
- Mutate the `events_immutable` trigger (allow UPDATE in some condition); assert the append-only fence catches the mutant.

---

## Design patterns applied

| # | Pattern | Where in Phase 9 | What it buys |
|---|---|---|---|
| DP1 | **Capability pattern** (`PrOpenCapability`, `LlmSpendCapability`, `EventLogWriteCapability`, `MicroVmSpawnCapability`, `AuditWriteCapability`) | Every privileged side-effect call inside an activity takes a typed capability token, minted at worker startup against the worker's task queue identity. | Replaces "trust the caller" + "is_authorized" booleans with type-level authority. A compromised worker cannot forge a capability for another task class — the token isn't `str`-shaped, it's a `frozen=True` Pydantic record signed (HMAC) at mint time and verified at use time. |
| DP2 | **Smart constructor** (`RedactedWorkflowPayload.seal(model)`) | Every activity input/output crosses through `seal()` — Pydantic-validated, regex-scrubbed, marked `_sanitized=True`. | "Did you redact?" is a type error, not a code-review hope. The `_sanitized: Literal[True]` marker is the only construction path. |
| DP3 | **Tagged union for workflow state** (`WorkflowState = Pending | Running | AwaitingHITL | Completed | TerminatedByOperator | Failed`) — extending Phase 6's `VulnLedger` sum type to the Temporal envelope | LangGraph state per Phase 6, projected from event-log fold. `match` + `assert_never` per ADR-0033. | Illegal states unrepresentable — no `is_running: bool, is_paused: bool` confusion. Forensic replay reconstructs state via fold over events, which is exhaustively typed. |
| DP4 | **Hexagonal architecture — Sandbox port preserved across phases** | Phase 5's `SandboxClient` Protocol + Phase 9's `LangGraphSubgraphActivity` both expose Ports that hide their implementation; Temporal Activities are the adapters. | Replacing the microVM stack (Firecracker → gVisor) or the Temporal substrate (Temporal OSS → Cloud) is an adapter swap, not a phase-9 redesign. |
| DP5 | **Command pattern for privileged activities** (`EventLogActivity`, `PrOpenActivity`, `WorkflowTerminateActivity`) | Each privileged side-effect is a typed Pydantic record + an executor; serialized form is what the event log stores. Includes a `serialize()` for replay. | "What did the system do?" is a `SELECT FROM events WHERE event_type = ...` query, not a log-scrape. Replay re-executes the same Commands deterministically. |
| DP6 | **Event-sourced audit chain** (BLAKE3 prev_hash chain on `events` table) | Per ADR-0034. Each row's `prev_hash = BLAKE3(prev.row_hash || canonical(payload))`. Projections verify the chain at read time. | Tamper-detection without trust in the DB superuser. The chain is content-addressable; an attacker who can write Postgres can append, but cannot insert into the middle without breaking the chain from that row forward — visible to any projection. |
| DP7 | **Registry pattern for typed events** (`@register_event_type(EventType.PluginResolved)`) | Each event variant registers at import time; the event-log dispatcher reads the registry to deserialize. | Adding an event variant in a future phase is one decorator + one import line — extension by addition per ADR-0043. The dispatch logic doesn't change. |

### Patterns deliberately rejected

- **Centralized "secrets broker" microservice** — overkill for Phase 9. Capability tokens + per-worker credentials handle the credential-scoping problem without inventing a new service. A KMS lands in Phase 13/13.5 if/when it pays its way.
- **Workflow-history encryption via Temporal-cluster-side codec** — the `temporalio` SDK supports a `payload_codec` that encrypts/decrypts at the SDK boundary. Tempting, but the codec key has to live somewhere, and centralizing it means the cluster-side codec is a single point of compromise. `RedactedWorkflowPayload.seal()` redacts at the type boundary — secrets *never enter* history, rather than entering encrypted. We may add codec later for defense-in-depth, but the primary control is non-entry.
- **Per-activity microVM** — re-running Phase 5 isolation for *every* activity (not just gate activities) was considered for credential isolation. Rejected: capability tokens are a cheaper, more precise primitive for credential scoping; microVMs are the right tool for *untrusted code execution* (the gate), not for *trusted credential-holding* (the activity worker).

---

## Risks (top 5)

| # | Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|---|
| R1 | **The `RedactedWorkflowPayload.seal()` regex misses a new secret shape** (a new cloud provider, a custom JWT format). | Medium — secret shapes evolve faster than our regex. | High — silent leak into history retained for 365d. | (a) Canary scan over history weekly for any new secret-shape patterns; (b) Pydantic field-name allowlist is the second layer (no `*_KEY` field-named values ever pass); (c) `RedactionFired` events trigger code review when *any* shape fires, indicating the regex is doing work. |
| R2 | **Replay-determinism subversion** via a transitive dependency that adds non-determinism (e.g. `langchain` adds `time.time()` to a code path). | Medium — third-party code mutates. | High — corrupts the forensic audit substrate. | (a) Static AST fence runs on every dependency upgrade; (b) production canary replays a workflow daily and diffs; (c) `import-linter` boundary tests prevent `time`, `random`, `os` from being imported in `platform/temporal/workflows/` or its closure. |
| R3 | **Per-task-queue credential rotation becomes operationally unwieldy** as task classes proliferate (Phases 10–16). | Medium-High. | Medium — operator fatigue → rotation skipped → credential lifetime drifts up. | Automate rotation via `make rotate-worker-creds` + CI deadline (creds older than 30d fail the deploy gate). |
| R4 | **`pgcrypto` column-encryption key management drifts** — the key ends up in an env file someone commits. | Low-Medium. | High — encryption is now decorative. | (a) `pre-commit` hook scans for the env-var name pattern; (b) key is supplied via per-session `\set` from a credential broker (not from disk); (c) key rotation tested in CI quarterly. |
| R5 | **Postgres performance under high event-log write volume** at portfolio scale — BLAKE3 trigger + pgcrypto encryption + chain verification could become the throughput ceiling. | Medium at Phase 10+ scale; low at Phase 9 scale. | Medium — would force a security/perf tradeoff. | Phase 9 ships at Phase-6-scale throughput; if Phase 10's portfolio scan exceeds capacity, add a partitioned `events` table (per-month) and a write-through batcher activity — Postgres + role discipline scales horizontally with partitioning. The chain is preserved across partitions. |

---

## Acknowledged blind spots

- **HSM / KMS-backed worker identities are not in scope.** Phase 9 uses Kubernetes Secrets + per-Pod ServiceAccounts + short-TTL mTLS certs. A proper HSM or vault solution (HashiCorp Vault, AWS KMS) is appropriate at Phase 13.5 alongside the operator portal — earlier is overengineering.
- **No DLP scan of workflow history retained today.** Adding a periodic DLP sweep over the historical history store is good ops hygiene but isn't part of the Phase 9 ship — Phase 13's audit dashboard is the natural home.
- **Network-layer enforcement of the egress allowlist is assumed at the K8s NetworkPolicy / firewall level**, not implemented inside the worker process. A compromised worker that bypasses the NetworkPolicy (kernel exploit) is a separate threat model that goes back to "treat the worker host like a Phase 5 microVM" — out of scope here.
- **No real-time intrusion detection on the worker hosts.** Adding eBPF-based runtime threat detection (Falco, Tetragon) is good defense-in-depth but adds operational complexity disproportionate to Phase 9. Phase 15+ may add.
- **The `pgcrypto` key is symmetric and per-environment, not per-tenant.** At portfolio scale (many orgs), per-tenant encryption keys would be appropriate; Phase 9 is single-tenant.
- **Temporal Cloud vs self-hosted — security implications differ.** Cloud puts the cluster under a vendor's threat model (better in some ways, worse in others — data residency). Phase 9 ships self-hosted-local for dev + leaves the prod choice open per ADR-0003. The capability-token / event-log primitives are cluster-agnostic.

---

## Open questions for the synthesizer

1. **Capability-token signing primitive** — HMAC-with-worker-secret is the minimum; do we want Ed25519-signed tokens with a per-worker signing key? HMAC is simpler; Ed25519 enables third-party verification (e.g. by the projection layer) without sharing the secret. Synth pick should consider Phase 13.5 operator-portal needs.
2. **Workflow-history retention window** — Phase 9 ships 365d to align with ADR-0040 audit-class data. Should `RedactionFired` events trigger an automatic accelerated re-redaction sweep of older history? Probably yes; the cost is non-trivial.
3. **temporal-ui authentication for shared dev clusters** — Phase 9 says "loopback only, no shared dev cluster." If the team wants a shared dev cluster (cost amortization), we need an auth story *now*, not later. Synthesizer should decide.
4. **Per-task-queue worker isolation strategy** — process-per-queue (this design's pick), container-per-queue (more isolation, more ops), VM-per-queue (Phase-5-microVM-equivalent for credentials, overkill IMO). Synth should pick.
5. **Activity output sanitization layering with Phase 1's output sanitizer** — the gather pipeline's sanitizer already scrubs absolute paths and secret-shaped fields. Phase 9's `OutputSanitizer` overlaps. Synthesizer should decide: extend Phase 1's sanitizer (additive) vs ship a new one (separation of concerns).
6. **Alembic migration role bootstrap** — the `migrations_role` itself has to be created by some role. Phase 9 says `bootstrap_role` runs once at cluster init. Is that human-operated or CD-automated? Synth should pick the lifecycle.
7. **LangGraph subgraph determinism** — the design says LangGraph nodes run *inside* the activity (Zone 2) so non-determinism is fine. But Phase 6's `VulnRemediationSut` already has a determinism story for replay. Synth should reconcile: does Phase 9's event-log fold cover what Phase 6's checkpoint-resume covers, and what's the relationship?
8. **`SearchAttribute` allowlist enforcement** — should the allowlist be a closed `Literal[...]` type (compile-time), a registry decorator (`@register_search_attribute`), or a config-file allowlist (runtime)? The toolkit suggests registry; security prefers closed Literal. Synth pick.

---

**End of design-security.md.**
