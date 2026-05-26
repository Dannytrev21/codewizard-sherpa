# Validation report — Story S8-01 — `codegenie sandbox {health,inspect,gc,prepare}` Click subcommands

**Story:** [`../S8-01-sandbox-cli-subcommands.md`](../S8-01-sandbox-cli-subcommands.md)
**Validated:** 2026-05-26
**Validator:** `phase-story-validator` (single-agent inline mode)
**Validator agent run:** automated (`story-validation-corrector` scheduled task)
**Verdict:** **HARDENED**

## Summary

S8-01 lands the four operator-facing Click subcommands that close Phase 5 §Goal 15. The draft's *intent* was directionally correct — right four subcommands, right exit-code behavior, right idempotence story — but it was written before eight sibling stories reached HARDENED, and every block-tier finding traces to one of four root causes:

1. **The story was written before S1-02 HARDENED on the `SandboxClient` Protocol shape.** S1-02 AC-2a pins the Protocol member set to *exactly* `{execute, health}`; the draft's `_FakeClient.gate_isolation_class = "shared_kernel"` test mocks a class attribute that the locked Protocol forbids. The real source of truth for the isolation class is a module-level mapping in `sandbox/contract.py` (also consumed by `SandboxRun`'s `@model_validator` per S1-02 AC-7b), not a `SandboxClient` attribute.
2. **The story was written before S2-02 HARDENED `entries()`.** S2-02 AC-DR-1 ships `RetryLedger.entries() -> list[LedgerEntry]` (where `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt`) that re-verifies the BLAKE3 chain across mixed rows in one pass. The draft uses `attempts()` (which filters out markers by design) and then opens `attempts.jsonl` a *second* time line-by-line — duplicate parse, no chain check on marker rows, and references `payload["kind"]` while the actual discriminator (S2-01 AC-T-1) is `payload["type"]`. A `KeyError` waiting to happen.
3. **The story was written before S7-04 HARDENED `cli/exit_codes.py`.** S7-04 created the exit-code kernel with `EXIT_REPO_ALREADY_IN_PROGRESS = 14` and explicitly reserved `13` for chain corruption. The draft hard-codes `13` as a magic number; HARDENED, this story extends the kernel additively (`EXIT_CHAIN_CORRUPTED: Final[int] = 13`), preserving the S7-04 invariants byte-stable.
4. **The story was written before the Phase-5 Open/Closed contract for backends crystallized.** Note 3 says "Do not import anything from `sandbox/did/` or `sandbox/firecracker/` directly in `cli/sandbox.py`" but no AC enforces it; the draft implementation outline step 5 directly imports `codegenie.sandbox.firecracker.rootfs.bake`. Without the registry-dispatched preparer pattern, Phase 7's chainguard backend would need a CLI edit — exactly the "extension by editing" failure mode CLAUDE.md's "Extension by addition" commitment forbids. The HARDENED story lifts `prepare` behind a `BackendPreparer` Protocol with a `register_preparer` decorator + `get_preparer` lookup.

Counting: **34 findings — 11 block-tier, 18 harden-tier, 5 nit-tier.** The blocks would have produced reachable structural bugs the executor's validator would have missed: `AttributeError` on `client.gate_isolation_class` (no such attribute on a HARDENED `SandboxClient`); `KeyError` on `payload["kind"]` (the discriminator is `"type"`); a magic-number `13` that wouldn't survive a future renumbering; a direct `sandbox.firecracker.rootfs` import that would break the moment Phase 7 added a third backend; a multi-GB BLAKE3 rehash on every `prepare` invocation; stub `...` tests for chain-tamper and digest-skip (the two highest-value mutation witnesses); a `pytest.fail`-less digest-skip test that would pass even with the fast path deleted; a wall-clock-second racy idempotence assertion; and an `attempts.jsonl`-only survival set that would have missed `manifest.yaml`, `chain_head.bin`, and `cost.jsonl` (S7-03).

The hardens close mutation-resistance gaps (the fast-path `bake` skip is now witnessed by an explicit `pytest.fail` sentinel; the chain-verify path is witnessed by a byte-tamper subprocess test; the event-constant kernel is witnessed by an AST scan), surface design-pattern opportunities as observable ACs (the `BackendPreparer` Protocol + `_CLI_BACKEND_NAMES` + `_BACKEND_TO_ISOLATION` triplet is the Open/Closed seam for Phase 7), and tie loose ends to CLAUDE.md commitments (event names live in the `sandbox/logging.py` kernel; exit codes live in `cli/exit_codes.py`; no bare literals; fence test under `tests/fence/`).

**No `RESCUE`-tier findings.** The goal traces cleanly to `phase-arch-design.md §CLI surface (codegenie sandbox)` + ADRs 0004/0005/0007/0013; every gap was patchable by pinning against HARDENED siblings (S1-02, S1-05, S2-01, S2-02, S3-06, S6-03, S6-04, S7-04) and Phase 0/5 precedents (the kernel-plus-registry-of-capabilities shape `@register_probe` + `@register_sandbox_backend` + `@register_signal_kind` + `@register_dep_graph_strategy` already use). **No Stage-3 research needed** — every finding was answerable from in-repo HARDENED sources.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Ship the four Click subcommands `codegenie sandbox {health, inspect <gate-run-id>, gc [--older-than 7d], prepare [--backend firecracker]}` with chain verification on `inspect`, idempotent housekeeping for `gc` and `prepare`, and structured exit codes.
- **Non-goals (Out-of-scope, hardened):** `codegenie remediate` flag wiring (S8-02); the E2E test (S8-03); coverage report + ADR audit (S8-04); third-party table libraries; Phase 11 evidence-bundle export; concurrent-invocation safety on `gc`.

### Phase 5 exit criteria touched

- **Step 8 done-criteria (`High-level-impl.md §Step 8`):** all four `sandbox` subcommand done-criteria bullets (lines 221–224); `tests/cli/test_sandbox_cli.py ≥ 90% line` (line 226).
- **`phase-arch-design.md §CLI surface (codegenie sandbox)` (lines 613–625):** verbatim subcommand surface + performance envelope + failure behavior.
- **ADR-0004:** `health` must surface `gate_isolation_class` per backend.
- **ADR-0005:** `inspect` reads Phase 4 chain-head; warns on mismatch but does not abort.
- **ADR-0007:** `inspect` renders `pre_execute` markers distinctly from `attempt` rows.
- **ADR-0013:** `prepare` validates `tools/digests.yaml#sandbox.policy_yaml` before rebake (note: rootfs digest is a separate field — `tools/digests.yaml#sandbox.rootfs` — which is what `prepare --backend firecracker` actually consumes; the policy YAML is `SandboxHealthProbe`'s concern per S3-06).
- **Production ADR-0007:** `health` is a probe surface; output schema is contract-stable.

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition — no silent edits":** the `cli/exit_codes.py` kernel extends additively (S7-04 created it; this story appends `EXIT_CHAIN_CORRUPTED`); the `sandbox/logging.py` event-constant kernel extends additively (S1-01 created it; this story appends four `EVENT_CLI_SANDBOX_*`); the `sandbox/registry.py` extends additively (adds `BackendPreparer` + `register_preparer` alongside the existing `register_sandbox_backend` + `register_signal_kind`).
- **CLAUDE.md "Match the existing convention":** the kernel-plus-registry-of-capabilities pattern this story applies to `prepare` mirrors the four precedents shipped earlier in the repo (`@register_probe`, `@register_sandbox_backend`, `@register_signal_kind`, `@register_dep_graph_strategy`).
- **CLAUDE.md "Make illegal states unrepresentable":** `PrepareOutcome` is a frozen Pydantic model with `extra="forbid"`; `RootfsDigestMismatch` carries structured `.expected` / `.actual` / `.path` attributes; the `_BACKEND_TO_ISOLATION` mapping has Literal-typed keys and values so a typo at the call site is a `mypy --strict` error.
- **CLAUDE.md "Functional core / imperative shell":** `_parse_age_window` and `resolve_gate_run` are pure module-level helpers with focused tests; the four subcommand bodies are ≤ 20 LOC because the kernels carry the variant data.
- **CLAUDE.md "Tests verify intent, not just behavior":** every red test is AC-prefixed (the executor's Validator uses these comments as the AC→test map); the three mutation witnesses (M-1 fast-path skip, M-2 chain re-verify skip, M-3 bare-literal regression) are explicit ACs.
- **CLAUDE.md "Structural defenses live under `tests/fence/`":** the new `tests/fence/test_cli_sandbox_backend_addition.py` enforces the Open/Closed contract for backends.
- **CLAUDE.md "Fail loud":** chain corruption exits 13 with a structured stderr JSON line, never silently. The fast-path digest mismatch under `--verify` raises `RootfsDigestMismatch` rather than silently rebuilding.

### Adjacent / prerequisite stories cited

| Story | Status | What S8-01 reuses (or must respect) |
|---|---|---|
| [S1-02](../S1-02-sandbox-contract-protocol-models.md) | HARDENED | `SandboxClient` Protocol member set frozen at `{execute, health}` (AC-2a); `SandboxHealth` Pydantic model field set frozen; `SandboxRun.backend` Literal set is `{"docker_in_docker", "firecracker"}` (AC-7b) — single source of truth for the `_BACKEND_TO_ISOLATION` keys |
| [S1-05](../S1-05-registries-and-env-allowlist.md) | HARDENED | `register_sandbox_backend` + `get_backend` + `auto_detect` registry kernel (AC-BR-1..-11, AC-AD-1..-4); the kernel-plus-registry pattern this story extends with `BackendPreparer`; `__all__` discipline |
| [S2-01](../S2-01-retry-ledger-blake3-chain.md) | HARDENED | `RetryLedger(run_dir, gate_id, prev_chain_head=None)` ctor surface; `.attempts() -> list[Attempt]` (filters by `type == "attempt"` per AC-T-2); `.head() -> bytes` 16-byte invariant (AC-H-4); structured `AuditChainCorrupted` (`.kind`, `.row_index`, `.attempt_id`, AC-AT-2) and `LedgerAttemptOutOfOrder` exceptions; on-disk discriminator field is `"type"` (AC-T-1) — **not `"kind"`** |
| [S2-02](../S2-02-pre-execute-marker-gap-1.md) | HARDENED | `record_pre_execute` + `.entries() -> list[LedgerEntry]` reader (AC-DR-1); `PreExecuteMarker` Pydantic model with `type: Literal["pre_execute"]`; `LedgerEntry: TypeAlias = PreExecuteMarker | Attempt` discriminated union; the seam `inspect` consumes |
| [S3-06](../S3-06-sandbox-health-probe.md) | HARDENED | `SandboxHealthProbe` exists as a Phase 1 probe; the CLI does NOT instantiate it (probe needs `RepoSnapshot`/`ProbeContext`); the CLI calls `client.health()` for the same data |
| [S6-03](../S6-03-rootfs-digests-and-prepare.md) | (parent story for `bake`) | `codegenie.sandbox.firecracker.rootfs.bake(...)` surface; `tools/digests.yaml#sandbox.rootfs` schema |
| [S6-04](../S6-04-auto-detect-macos-fallback.md) | (depends-on) | `auto_detect()` platform branch; `FirecrackerKvmMissing` error class |
| [S7-03](../S7-03-cost-emitter-sandbox-cost-entry.md) | HARDENED | `cost.jsonl` lives at `.codegenie/remediation/<run-id>/gates/<gate_id>/cost.jsonl` — new file in the gc survival set |
| [S7-04](../S7-04-concurrent-remediate-repo-lock.md) | HARDENED | `cli/exit_codes.py` kernel created with `EXIT_REPO_ALREADY_IN_PROGRESS = 14`; `13` reserved for chain corruption; `.lock` file in `.codegenie/remediation/` — new file in the gc survival set; the `contextlib.ExitStack` lifecycle pattern |

### Existing exit-code ground truth

| Exit | Semantics | Source |
|---|---|---|
| 0 | `passed` (`EXIT_OK`) | arch §830 |
| 1 | general error (`EXIT_GENERAL`) | conventional |
| 2 | Click usage error (`EXIT_USAGE`) | arch §865, §866 |
| 11 | `escalate` (`EXIT_ESCALATE`) | arch §830, §847 |
| 12 | `failed_unrecoverable` (`EXIT_FAILED_UNRECOVERABLE`) | arch §830, §869 |
| **13** | `AuditChainCorrupted` / `LedgerAttemptOutOfOrder` (`EXIT_CHAIN_CORRUPTED`) | **new — this story's kernel addition** |
| 14 | `RepoAlreadyInProgress` (`EXIT_REPO_ALREADY_IN_PROGRESS`) | S7-04 HARDENED |
| 130 | Ctrl+C (Unix convention; `EXIT_INTERRUPTED`) | Python stdlib convention |

## Critic findings

The four critics' findings are listed below. Each finding has a severity (`block` / `harden` / `nit`) and an `AC-…` ID that maps to the AC introduced or modified.

### Critic A — Coverage (does the AC set guarantee the goal?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-A-1 | block | `--backend` choice set unpinned in the draft AC ("the one passed via `--backend`"). A Click bare-string option accepts any input → "unknown backend" surfaces only at registry lookup time → confusing UX and exit code 1 instead of 2. | AC-H-1 pins `click.Choice(["did", "firecracker", "auto"])`, default `"auto"`; rejected values fail with Click `UsageError` exit 2. Parametrized table covers `["dind", "docker", "kvm", ""]`. |
| C-A-2 | block | `gate_isolation_class` source unpinned. The draft test mocks `_FakeClient.gate_isolation_class` — but per S1-02 HARDENED AC-2a, `SandboxClient` Protocol's member set is exactly `{execute, health}` with no class attributes. Production code reading `client.gate_isolation_class` raises `AttributeError`. | AC-H-4 introduces `_BACKEND_TO_ISOLATION: Final[Mapping[...]]` in `sandbox/contract.py`; the CLI consumes `_BACKEND_TO_ISOLATION[health.backend]`. The mapping is also adopted as the source of truth by S1-02's `SandboxRun` `@model_validator` (additive). Unit test asserts mapping keys == `SandboxRun.backend` Literal arg set. |
| C-A-3 | block | `inspect` ambiguous-gate-run-id behavior unspecified. Glob fallback to `.codegenie/remediation/*/gates/<raw>/` can match multiple runs; draft says "exits 2 on unknown" but not on ambiguous. | AC-I-2 introduces explicit `UsageError("ambiguous gate-run-id: <raw> matched {n} runs; use <run-id>:<gate_id> form")` and the parametrized test covers both branches. |
| C-A-4 | block | Exit code 13 is a magic literal in the draft. S7-04 HARDENED created `cli/exit_codes.py` as the kernel and reserved 13 for chain corruption. Hard-coding 13 inline diverges from the convention. | AC-I-6 + AC-X-4 — append `EXIT_CHAIN_CORRUPTED: Final[int] = 13` to `cli/exit_codes.py`; the CLI imports the constant. Existing S7-04 constants byte-stable. |
| C-A-5 | block | `prepare` AC-8 says "compute the on-disk BLAKE3 of `tools/firecracker/<rootfs_digest>/rootfs.ext4`" — re-hashing a multi-GB file on every `prepare` invocation is multi-second. Operators run `prepare` routinely. | AC-P-3 — file-existence is the fast path (default); AC-P-5 — `--verify` opts into the full rehash with `RootfsDigestMismatch` on tamper. |
| C-A-6 | block | DinD `prepare` behavior unspecified. Draft only covers `--backend firecracker`. Operators omitting `--backend` and getting "unsupported" surface friction. | AC-P-2 — DinD preparer is a no-op returning `PrepareOutcome(already_prepared=True, bake_invoked=False, ...)`. |
| C-A-7 | block | `chain-head-match` line shape allows only `yes` / `no` in the draft. When `chain_head.bin` is absent (legitimate state — Phase 4 hasn't run), distinguishing absent from no is load-bearing. | AC-I-8 — three explicit branches: `chain-head-match: yes` / `no` / `absent`; tested independently. |
| C-A-8 | block | The `gc` survival set lists only `attempts.jsonl`. Per S7-03 (`cost.jsonl`) and S7-04 (`.lock` file), the gate dir now carries multiple kernel files. A wrong glob root that recurses one level too deep would delete any of them. | AC-G-4 — survival set expanded to `{attempts.jsonl, manifest.yaml, chain_head.bin, cost.jsonl, .lock}` with byte-identical content assertion. |
| C-A-9 | block | `gc` idempotence assertion uses "same wall-clock second" — racy on slow CI. | AC-G-3 — idempotence assertion is structural (`removed >= 1` first call, `removed == 0` second call, survival-set still intact), no wall-clock dependency. |
| C-A-10 | block | KeyboardInterrupt / SystemExit lifecycle unspecified. `gc` mid-walk Ctrl+C could leave partially-deleted state and no output. | AC-G-7 — `gc` wraps in `contextlib.ExitStack`; canonical JSON output includes `partial: true` and exits 130 on interrupt. |
| C-A-11 | block | Open/Closed contract for backends is in Note 3 but no AC enforces it. Without enforcement, a future contributor adding a third backend would edit `cli/sandbox.py` (the very "edit, don't add" failure mode CLAUDE.md forbids). | AC-X-3 + `tests/fence/test_cli_sandbox_backend_addition.py` — AST scan + grep enforce zero direct backend imports and zero backend-name string literals outside `_CLI_BACKEND_NAMES`. |
| C-A-12 | harden | `--verify` option not surfaced for `prepare`. Without it, operators who suspect tampered rootfs have no CLI path. | AC-P-5 introduces `--verify`. |
| C-A-13 | harden | `prepare` digest-mismatch error path lacks a typed error. The draft says "raise `FirecrackerKvmMissing`" only on no-KVM. Tampered rootfs is silently re-baked or produces an opaque error. | AC-P-5 introduces `RootfsDigestMismatch(SandboxError)` with structured attributes. |
| C-A-14 | harden | `inspect` happy-path attempt-row columns unpinned (sets like `failing_signals` could mean different things). | AC-I-4 — `failing_signals` is the sorted list of `signal.kind` where `signal.passed is False`. |
| C-A-15 | harden | `►` Unicode codepoint unpinned. A future contributor swapping it for `>` or `▶` would break visual distinguishability tests. | AC-I-5 pins U+25BA exactly. |
| C-A-16 | harden | `PrepareOutcome` shape unspecified. Without it, the JSON output shape drifts and consumers (operators, Phase 11 evidence bundle) can't rely on it. | AC-P-7 introduces a frozen Pydantic model with pinned fields. |
| C-A-17 | harden | Event field set unpinned. S5-02 HARDENED introduced per-event field-set pinning via `capture_logs()`; S8-01 should match. | AC-X-2 pins each of the four events' field sets. |
| C-A-18 | nit | Status not marked HARDENED. | Status updated to `Ready (HARDENED 2026-05-26)`. |
| C-A-19 | nit | Implementation outline references `_events.py` but S1-01's kernel lives at `sandbox/logging.py`. | Implementation outline + Files-to-touch updated. |

### Critic B — Test Quality (mutation thinking)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-B-1 | block | Two test stubs in the TDD plan are literally `...`: `test_inspect_exits_13_on_tampered_chain` and `test_prepare_skips_when_digest_matches`. These are the two highest-value mutation witnesses (chain integrity + fast-path skip) and they are blank. The executor's Validator pass would see "tests exist" and pass; the actual bugs slip through. | Both stubs filled in with full bodies. The chain-tamper test flips one byte at the file midpoint and asserts exit code 13 + structured stderr JSON. The fast-path test uses `pytest.fail` as a sentinel: `monkeypatch.setattr("codegenie.sandbox.firecracker.rootfs.bake", lambda **kw: pytest.fail(...))` — the test passes iff `bake` is never called. |
| C-B-2 | block | `payload["kind"] == "pre_execute"` in implementer Note 4 is wrong (the discriminator per S2-01 AC-T-1 is `payload["type"]`). The draft test never reads this raw dict — but the implementation does, and the Notes are wrong. A future implementer following the Notes literally produces a `KeyError`. | Notes rewritten — and `inspect` now uses `entries()` (S2-02), so raw-dict parsing is removed entirely. |
| C-B-3 | block | `attempts()` + secondary parse is a duplicate-read smell. S2-02 ships `entries()` precisely for this use case (returns both row types with chain verification across mixed rows in one pass). The draft's pattern is "missed the kernel" — there is a kernel; use it. | AC-I-3 + AST scan: `attempts.jsonl` is opened by the CLI exactly zero times outside `RetryLedger`. The renderer dispatches on `isinstance(e, PreExecuteMarker)` vs `isinstance(e, Attempt)`. |
| C-B-4 | block | The `health` test mocks `auto_detect` via `monkeypatch.setattr("codegenie.sandbox.registry.auto_detect", ...)` — but tests `_FakeClient.gate_isolation_class = "shared_kernel"`. The Protocol per S1-02 AC-2a forbids that attribute; the mock test passes but the production code wouldn't be calling `client.gate_isolation_class` at all. The test verifies a mockery that isn't real. | Test rewritten to verify the contract: `gate_isolation_class` is sourced from `_BACKEND_TO_ISOLATION[health.backend]`. |
| C-B-5 | harden | No Hypothesis property for the gc window parser. Parametrized rejection is good but doesn't pin the positive side (the parser never returns a non-positive timedelta). | AC-G-1 adds a Hypothesis property covering `(n, unit) ∈ [1..10_000] × "dhm"`. |
| C-B-6 | harden | No test for `RetryLedger(prev_chain_head=None)` invariant from ADR-0005. A future contributor passing the on-disk bytes into the constructor (the obvious mistake) would change behavior silently. | AC-I-7 — source-level assertion that `prev_chain_head=None` appears exactly once in the CLI source and is the literal `None`. |
| C-B-7 | harden | No test for the four-event field set (S5-02 precedent). Without it, a regression that adds `repo_path: Path` to a structlog event would leak absolute paths. | AC-X-2 + `test_event_cli_sandbox_health_field_set` (mirrored for the other three). |
| C-B-8 | harden | No AST scan for bare event literals. The kernel discipline only holds if a contributor can't accidentally `structlog.bind(event="cli.sandbox.health")` somewhere. | AC-X-1 + `test_no_bare_cli_sandbox_event_literals_in_src`. |
| C-B-9 | harden | No coverage assertion at the file level. Story says "≥ 90% line coverage on `src/codegenie/cli/sandbox.py`" but Phase 5 also wants 80% branch. | AC-T-1 explicit — 90% line + 80% branch via `--cov-fail-under`. |
| C-B-10 | harden | No mutation backstop for `GC_ROOTS` length. A future contributor adding a third root without thinking about the survival set could break gc semantics. | AC-G-2 asserts `len(GC_ROOTS) == 2`. |
| C-B-11 | harden | No test for `rebake` path (digest mismatch under `--verify` and rootfs file missing under default). Only the fast-path skip is tested in the draft. | AC-P-4 + `test_prepare_invokes_bake_when_rootfs_missing` + AC-P-5 + `test_prepare_verify_mismatch_exits_1`. |
| C-B-12 | nit | The four-test plan doesn't map each test to ACs. The executor's Validator works best when the map is explicit. | Every test now has an `# AC-…` prefix comment. |
| C-B-13 | nit | `test_health_prints_backend_and_isolation_class` uses positional `monkeypatch, capsys` but never references `capsys` (Click captures via the runner). | `capsys` removed. |

### Critic C — Consistency (arch / ADR / commitment)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-C-1 | block | The draft's "calls `SandboxClient.health()`" (correct) conflicts with `phase-arch-design.md §613` ("calls `SandboxHealthProbe.run()`"). The arch is loose — probe needs `RepoSnapshot` + `ProbeContext` the CLI cannot synthesize. The story bends to the executable surface. | AC-H-3 pins `client.health()` and Notes-for-implementer documents the arch phrasing. |
| C-C-2 | block | Draft implementer outline directly imports `codegenie.sandbox.firecracker.rootfs.bake(...)`. Violates Note 3 ("Do not import anything from `sandbox/did/` or `sandbox/firecracker/` directly in `cli/sandbox.py`"). Worse: violates CLAUDE.md "Extension by addition" — Phase 7's chainguard backend cannot land without editing `cli/sandbox.py`. | AC-P-1 + AC-X-3 — `prepare` calls `registry.get_preparer(backend_name).prepare(verify=...)`; `cli/sandbox.py` has zero backend imports. |
| C-C-3 | block | Draft event names (`cli.sandbox.health`, etc.) are bare strings. S1-01 HARDENED's extension-by-addition contract requires all event names to be `Final[str]` constants in `sandbox/logging.py` under `__all__`. | AC-X-1 — four `EVENT_CLI_SANDBOX_*` constants appended; AST scan enforces zero bare literals. |
| C-C-4 | block | The draft says `RetryLedger.attempts()` "re-verifies the BLAKE3 chain end-to-end." Per S2-01 AC-T-2 this is correct for `Attempt` rows, BUT the chain involves `PreExecuteMarker` rows too. `attempts()` re-verifies only the attempt subchain. The mixed-row chain check needs `entries()` per S2-02 AC-DR-2. | AC-I-3 — switch to `entries()`. |
| C-C-5 | harden | Draft references `cli/_events.py` — but S1-01 ships `sandbox/logging.py` as the event kernel. A new `cli/_events.py` would fork the convention. | Implementation outline updated to extend `sandbox/logging.py`. |
| C-C-6 | harden | The `SandboxRun.backend` Literal arg set (S1-02) and `_BACKEND_TO_ISOLATION` keys need to stay in sync. Without a unit test asserting set equality, drift is silent. | AC-H-4's `test_backend_to_isolation_keys_match_sandboxrun_backend_literal`. |
| C-C-7 | harden | Story's reference to ADR-0013 mentions `tools/digests.yaml#sandbox.policy_yaml`, but `prepare`'s actual consumer is `#sandbox.rootfs`. Two distinct fields under the same digest YAML. | Validation notes clarify; the ADR-0013 reference stays (the same ADR governs all digest-pinned files), but the implementer Notes explicitly say `sandbox.rootfs`. |
| C-C-8 | nit | `cli/sandbox.py` referenced as both a flat file and as a package (`cli/sandbox/`). | Implementation outline pins the package layout. |

### Critic D — Design Patterns (Open/Closed, DIP, sum types)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-D-1 | block | The draft `prepare` branches on `--backend firecracker` and directly calls `bake`. With Phase 7's chainguard backend coming, this is the "edit the kernel for the third sibling" anti-pattern CLAUDE.md "Extension by addition" forbids. **Rule-of-three threshold:** DinD + Firecracker + chainguard = three concrete preparers; the kernel-plus-registry is the right shape *now*, not "wait until the third lands." | AC-P-1 elevates the `BackendPreparer` Protocol + `register_preparer` decorator + `get_preparer` lookup to an observable AC (the AST scan that `cli/sandbox.py` has no direct backend imports). |
| C-D-2 | block | The draft `_CLI_BACKEND_NAMES` mapping doesn't exist (the four subcommands each branch on `--backend` inline). Without it, the CLI carries the variation; with it, the data is one place. | AC-H-2 introduces `_CLI_BACKEND_NAMES: Final[Mapping[str, str]]`. |
| C-D-3 | block | `gate_isolation_class` was originally going to be read from `client` (a primitive-obsession smell on the `SandboxClient` Protocol). The right shape is a Literal-typed mapping with explicit Literal keys — `_BACKEND_TO_ISOLATION` makes illegal pairs unrepresentable at the type level. | AC-H-4 introduces the mapping. |
| C-D-4 | block | Two `Path.glob` patterns hard-coded in `gc` body. With Phase 9 Temporal worker state coming, a third pattern is inevitable. The "module-level `Final` tuple, iterate not branch" pattern (CLAUDE.md §Conventions) is the convention here. | AC-G-2 introduces `GC_ROOTS: Final[tuple[str, ...]]`. |
| C-D-5 | harden | `PrepareOutcome` doesn't exist in the draft — `prepare` returns a raw `dict` printed as JSON. A frozen Pydantic model gives the consumer a typed contract. | AC-P-7 introduces `PrepareOutcome`. |
| C-D-6 | harden | `RootfsDigestMismatch` doesn't exist. Tampered rootfs under `--verify` would surface as `AssertionError` or a generic `RuntimeError`. A typed error with structured attributes is the convention (mirrors S2-01 `AuditChainCorrupted`). | AC-P-5 introduces it. |
| C-D-7 | harden | Functional core / imperative shell — the window parser and the gate-run-id resolver are pure functions but the draft has them inline in the subcommand body. | Pure helpers extracted into `_gc.py` + `_resolve.py` with focused tests (`tests/cli/sandbox/test_gc_parser.py`, `test_resolve.py`). |
| C-D-8 | nit | The two-line "go through the registry" Note 3 is the right design but never enforced. Notes that aren't ACs are aspirational. | AC-X-3 + fence test. |

## Conflict resolution

- **Coverage vs Consistency on `SandboxHealthProbe.run` vs `client.health()`:** Coverage said "AC must pin the callable"; Consistency said "the arch says `SandboxHealthProbe.run()`." Consistency loses here because the arch phrasing is *loose* (the probe surface is contract-stable per Production ADR-0007, but the *callable* for CLI use is `client.health()` — they return the same data). Resolution: AC-H-3 pins `client.health()` and Notes document the arch phrasing.
- **Design-Patterns vs Rule 2 ("three similar lines is better than premature abstraction") on the `BackendPreparer` Protocol:** DinD's preparer is a no-op (1 line); Firecracker's is non-trivial; Phase 7's chainguard is coming. That's the **rule-of-three** threshold. Design-Patterns wins.
- **Coverage vs Rule 3 (surgical changes) on extending `sandbox/contract.py` with `_BACKEND_TO_ISOLATION`:** Rule 3 says "touch only what you must." But the alternative is duplicating the backend → isolation mapping (once in `SandboxRun`'s `@model_validator`, once in `cli/sandbox`). Single source of truth wins; the additive extension to `sandbox/contract.py` is the minimum-change shape (one new constant, one validator rewrite, S1-02 tests stay green).

## Edits applied to the story

Every edit is in-place; the story file's diff against pre-validation state will show:

1. **Status line:** `Ready` → `Ready (HARDENED 2026-05-26)`.
2. **New "Validation notes (2026-05-26)" block** under the header with the eleven headline corrections.
3. **Depends-on widened** to include S1-02 (Protocol member set), S1-05 (registry kernel), S2-01 (`.attempts/.head`), S2-02 (`.entries`), S3-06, S6-03, S6-04 platform branch, S7-04 (`cli/exit_codes.py` kernel).
4. **Acceptance criteria** restructured into six groups (A health / B inspect / C gc / D prepare / E cross-cutting + Open/Closed / F test hygiene + harness) with **34 numbered ACs** (was 13 unnumbered checkboxes).
5. **Implementation outline** rewritten as a 12-step ordered list grounded in the registry-dispatched preparer kernel.
6. **TDD plan red tests** rewritten — the two `...` stubs filled in with real bodies; every test prefixed with its AC; the `attempts()` + secondary-parse pattern replaced with `entries()`; the `payload["kind"]` reference removed (it was wrong); the `_FakeClient.gate_isolation_class` mock replaced with the `_BACKEND_TO_ISOLATION` lookup; the Hypothesis property test added.
7. **Files-to-touch** expanded with the new package layout, the additive kernel extensions, and the two new preparer modules.
8. **Notes-for-implementer** rewritten with seven sections (architecture-shaping constraints, exit-code kernel, discriminator key, `prepare` fast path, macOS Firecracker, `gc` discipline, event-name discipline, CLI package migration, coverage + fence).

## Stage 3 — Researcher

**Skipped.** No findings were tagged `NEEDS RESEARCH`. Every gap was answerable from in-repo HARDENED sources (S1-02, S1-05, S2-01, S2-02, S3-06, S6-04, S7-03, S7-04) + the phase arch + ADRs 0004/0005/0007/0013 + the canonical kernel-plus-registry pattern that `@register_probe` + `@register_sandbox_backend` + `@register_signal_kind` + `@register_dep_graph_strategy` already use.

## Verdict — HARDENED

The story is now ready for `phase-story-executor`. The Open/Closed contract, the kernel extensions (`cli/exit_codes.py`, `sandbox/logging.py`, `sandbox/contract.py`, `sandbox/registry.py`), and the mutation witnesses make this a story where a wrong implementation produces a failing test, not a silent regression.
