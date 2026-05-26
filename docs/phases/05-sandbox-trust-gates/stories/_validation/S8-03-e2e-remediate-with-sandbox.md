# Validation report: S8-03 — E2E `tests/e2e/test_remediate_with_sandbox.py` against `breaking-change-cve`

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S8-03 is the **headline exit-criterion test** for Phase 5 — it ties every Phase 5 surface (DinD/Firecracker auto-detect, `RetryLedger` BLAKE3 chain, replan hook into Phase 4, cost emitter, audit events) into one black-box CLI invocation. The Goal and AC set were directionally correct, but the draft regressed two block-tier lessons that sibling validations (`S5-05`, `S8-01`, `S8-02`) had already locked into the phase's contract surfaces:

| Draft assumption / shape | Reality / hardened shape |
|---|---|
| JSONL discriminator field is `"kind"` (lines 115–117, 44) | `"type"`, per S2-01 AC-T-1 / ADR-0007 §Decision / S8-01 HARDENED §"discriminator KeyError". The draft would silently partition into two empty lists. Hardened: route every ledger row read through `RetryLedger.entries()` returning the `LedgerEntry = PreExecuteMarker \| Attempt` typed sum, and `RetryLedger.attempts()` for the `Attempt`-only slice. The strings `"kind"` and bare `json.loads(line)["kind"]` must not appear in the test body. |
| VCR cassettes at `tests/fixtures/vcr/cassette-attempt-{1,2}.yaml` (two files, lines 19, 31, 43) | One cassette at `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` with two interactions in order, per S5-05 HARDENED line 108 + S7-02 HARDENED finding (which absorbed the same correction). The draft references files that do not exist. |
| `(run_dir.parent / "chain_head.bin")` in Implementation outline step 3 | `run_dir / "chain_head.bin"` — the per-run dir is the right level (per AC line 47 and S2-03). The test stub had the path right; the outline contradicted itself. |
| Test signature accepts `monkeypatch` but never uses it (and never sets `CODEGENIE_HOME` despite outline step 3 prescribing it) | Either set `CODEGENIE_HOME` via `monkeypatch.setenv` (matches outline) or drop the parameter. Hardened: set it — `e2e_repo`-isolation is required for cross-run cleanliness. |
| No `@pytest.mark.vcr(...)` / no `block_network` fixture | A typo in the cassette path silently re-records when `CODEGENIE_LIVE_LLM=1` is set. Hardened: decorate with `@pytest.mark.vcr(...)` AND consume `block_network` (mirrors S5-05 AC-OFFLINE-1). |
| `run_dir = next((... / "remediation").iterdir())` — non-deterministic on fixture pollution | `Path.iterdir()` is arbitrary-order. Hardened: assert exactly one child dir AND parse the run-id from `result.output`'s structured `remediate.completed` event. Silent fall-through to an arbitrary run dir is disallowed. |
| `len(pre) == 2 and len(att) == 2` (count-only, lines 117) | A writer that emits `[attempt(1), attempt(2), pre_execute(1), pre_execute(2)]` (wrong order, defeating ADR-0007 resume-safety) passes. Hardened: assert the *ordered* sequence `["pre_execute", "attempt", "pre_execute", "attempt"]`, then derive the typed `LedgerEntry` partition via `ledger.entries()`. |
| `att[0]["sandbox_run_id"] != att[1]["sandbox_run_id"]` and `att[0]["patch_blake3"] != att[1]["patch_blake3"]` (lines 121–122) | A mutation that uses ascending integer IDs like `"1"`, `"2"` instead of UUID7 passes distinctness. Hardened: positive shape check (UUID7 regex for `sandbox_run_id`, 32-or-64-hex-char for `patch_blake3`) **before** distinctness; also assert distinct `evidence_paths["patch"]` (S5-05 precedent — paths-first-then-content). |
| `head_bin.read_bytes() == ledger.head()` (line 132) — internal consistency only | A bug where Phase 5 ignores Phase 4's chain head and starts fresh, then writes the new head, passes. Hardened: snapshot `pre_run_head` before invoking; assert `post_run_head != pre_run_head` (chain advanced through Phase 5 per ADR-0005), AND `len(post_run_head) == 32` (no empty bytes), AND `post_run_head == ledger.head()`. |
| `sorted(p.attempt_id for p in parsed) == [1, 2]` (cost rows, line 138) | A cost emitter that writes `attempt_id=1, sandbox_run_id="bogus"` and `attempt_id=2, sandbox_run_id="bogus2"` independently of the ledger's actual sandbox IDs passes. AC-line-48 said the cross-link must hold; the test stub never verified it. Hardened: `{p.sandbox_run_id for p in parsed} == {a.sandbox_run_id for a in attempts}` — bijection between the two ledgers. |
| `policy.json` AC "present (digest-pinned per ADR-0013)" (AC line 49) | A 0-byte file passes. Hardened: parse as JSON, assert the three top-level keys ADR-0013/S3-05 pin (`lockfile`, `runtime_trace`, `test_inventory`). |
| `(ev / "trace.jsonl").exists() or (ev / "trace.unavailable").exists()` (line 148) | A 0-byte `trace.unavailable` passes; both can co-exist (ambiguous which path was taken). Hardened: XOR not OR; if `trace.unavailable` exists, assert it's structured JSON with a `reason` field and `platform in {"darwin", "linux"}`. |
| Deny-substring grep `_DENY_SUBSTRINGS = ("KEY", "TOKEN", "SECRET", "PASSWORD")` (line 99) | Naming-based (false negatives on `sk-ant-api03-...`, false positives on `KEYBOARD`/`MONKEY`/audit-event-names). Hardened: regex catalog targeting credential *shape* (`<ENV_NAME>_(KEY\|TOKEN\|SECRET\|PASSWORD)\s*[:=]\s*\S+`, `sk-ant-api03-…`, `ghp_…`, `AKIA…`) — and extract to `src/codegenie/sandbox/env_allowlist.py` as the SSOT (rule-of-three: this test + `test_env_allowlist_no_credentials.py` + Phase-7 distroless E2E). |
| "Wherever the backend is recorded" (Implementation outline step 4, line 74) | Stringly-typed field-path guessing. Hardened: per ADR-0010, `SandboxCostEntry.backend: Literal["docker_in_docker", "firecracker"]` is the canonical location — read it via the typed Pydantic model, not by hunting for a dict key. |
| Goal claims test exercises "every Phase 5 surface" but no AC verifies a *real* sandbox was invoked — a CLI that fakes the artifacts (writes `attempts.jsonl` + `sandbox.jsonl` + evidence files without calling `SandboxClient.execute`) passes | Hardened (path-b from F-TQ-14): inject a `ReplanHookSpy` Decorator via S8-02's `make_orchestrator` DI port (S8-02 AC-TEST-ORC-1 — this is the rule-of-three+1 consumer of the spy). Assert `spy.call_count == 1`, `spy.calls[0].prior_attempts[0].attempt_id == 1`, AND assert the cassette's two `Phase4Interaction`s were both replayed via `extract_phase4_interactions(cassette).play_count`. |
| AC line 51 "on macOS DinD; on Linux-KVM CI Firecracker; *or* parametrize via monkeypatch" — OR-escape-hatch | The "OR" makes the AC trivially satisfiable by the cheapest path while *implying* cross-OS CI matrix coverage. Hardened: pick the single-runner monkeypatch path explicitly (covers branch coverage of `_kvm_available`); cross-OS *real* coverage is owned by S6-05 (KVM smoke) + the matrix CI workflow already present, not by this story. |
| `pytest -m e2e tests/e2e/test_remediate_with_sandbox.py` in AC line 54 | Default addopts include `--cov-fail-under=85`; a single-test invocation cannot satisfy that. Hardened: AC pins the invocation as `pytest -m e2e tests/e2e/test_remediate_with_sandbox.py --no-cov` (per CLAUDE.md cassette workflow guidance on coverage-and-subset runs). |
| "Optionally add `addopts = '--strict-markers'`" (outline step 5) | Already set in `pyproject.toml`. Hardened: drop "optionally"; the executor only needs to register the marker. |
| `Depends on: S6-05, S8-02` (line 6) | Under-stated by ~10 stories. Hardened: widen to `S2-01, S2-02, S2-03, S3-05, S5-01, S5-02, S5-05, S6-04, S6-05, S7-03, S8-01, S8-02` — every story whose surface is asserted by an AC. |
| "ADRs honored: ADR-0002, ADR-0005, ADR-0007, ADR-0010" | AC line 49 invokes ADR-0013 (digest-pinned policy); AC line 50 invokes ADR-0012 (env-allowlist deny). Hardened: add ADR-0012, ADR-0013. |
| `--cve <fixture-cve>` placeholder + drift between `CVE-2026-FIXTURE` (stub line 105) and `CVE-2026-XXXX` (outline line 64); fixture metadata never named | A third-party reviewer cannot binary-check this without reading the fixture. Hardened: pin the canonical CVE id at `tests/fixtures/repos/breaking-change-cve/metadata.yaml#cve_id` (S5-05 contract extension — a `cve_id` field becomes part of the `.expected/` Specification-pattern). The test reads it: `cve_id = yaml.safe_load((e2e_repo / "metadata.yaml").read_text())["cve_id"]; CliRunner().invoke(cli, ["remediate", "--cve", cve_id, ...])`. No literal CVE id in the test body. |
| AC line 41 "runs in 60–300 s wall-clock" — prose, unenforced | Hardened: `@pytest.mark.timeout(300)`; drop the 60-s floor (not enforceable per-test). |
| macOS auto-detect test asserts `exit_code == 0` and `backend == "docker_in_docker"` but never proves the DinD path was actually taken | A no-op fallback (skip remediation, exit 0) passes. Hardened: capture structlog events via `structlog.testing.capture_logs()`; assert exactly one `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` event fired with `backend == "docker_in_docker"` (S8-02 AC-FALL-1 precedent). |
| `pre_execute` ↔ BLAKE3 chain not explicitly verified | A runner that emits non-chained `pre_execute` rows (regression on ADR-0007 §Consequences) advances the head while corrupting marker-row chaining. Hardened: `entries()` re-verifies the chain across mixed rows per S2-02 AC-DR-1 — assert it returns without raising `AuditChainCorrupted`. |

The remaining slice — what S8-03 actually owns once the upstream surfaces hold their contracts:

1. The headline E2E test against `breaking-change-cve` with all hardened ACs below.
2. A second test (`test_e2e_macos_auto_detect_uses_did`) exercising the DinD-forced path via `monkeypatch` + structlog capture.
3. A sibling cassette-stability triple-replay test (`test_remediate_with_sandbox_replay_stable.py`) asserting process-level determinism — exit code, ledger head, and cost-row tuple identical across three back-to-back runs in fresh `tmp_path` dirs.
4. The `tests/e2e/_paths.py` helper module (extract resolved path logic — S8-04 will consume it).
5. The `CREDENTIAL_DENY_SUBSTRINGS` extraction to `src/codegenie/sandbox/env_allowlist.py` (rule-of-three SSOT; the deny set used by the *filter* must equal the deny set used by the *audit*).

The hardened story is now ready for the executor. **No `NEEDS RESEARCH` items remain unresolved** — both research candidates (behavior-implication testing at CLI level, secret-shape catalog) resolved to "consume the in-codebase kernel" (S8-02's `make_orchestrator` DI port; ADR-0012's filter constants).

---

## Critic findings — full audit

(See the inline `## Validation notes` block in the story for the *applied* edits + before/after summary. The full critic reports are recorded here verbatim, abbreviated where redundant with the table above.)

### Coverage critic — 17 findings (2 BLOCK, 12 HARDEN, 3 NIT)

- **F-COV-1 (HARDEN)**: Wall-clock budget not measurable → add `@pytest.mark.timeout(300)`, drop 60-s floor.
- **F-COV-2 (BLOCK)**: `CliRunner` short-circuits the sandbox without a provenance assertion → inject `ReplanHookSpy` via `make_orchestrator` DI; assert backend Literal value from `SandboxCostEntry`.
- **F-COV-3 (HARDEN)**: `failed_unrecoverable` outcome class never tested in E2E → explicitly defer via "Out of scope"; cite arch §test-architecture `scenarios.yaml` row plan.
- **F-COV-4 (HARDEN)**: S7-04 repo-lock interaction unacknowledged → document as exercised-implicitly + add `not (run_dir.parent / ".lock").exists()` post-run assertion.
- **F-COV-5 (BLOCK)**: Fixture CVE id drift between stub and outline → read from fixture metadata file; pin contract.
- **F-COV-6 (HARDEN)**: `policy.json` content invariant → assert three top-level keys.
- **F-COV-7 (HARDEN)**: `trace.unavailable` content + XOR.
- **F-COV-8 (HARDEN)**: `patch_blake3` schema-required assertion.
- **F-COV-9 (HARDEN)**: `iterdir()` non-determinism → assert len==1 + parse run-id from output.
- **F-COV-10 (HARDEN)**: Cost ↔ attempts cross-link in test body, not just AC text.
- **F-COV-11 (NIT)**: Assertion ordering for diagnostic clarity.
- **F-COV-12 (HARDEN)**: Cross-OS matrix is OR-escape-hatch → pick single-runner monkeypatch explicitly.
- **F-COV-13 (NIT)**: Deny-substring fragile on `KEY` → tighten patterns.
- **F-COV-14 (HARDEN)**: `chain_head.bin` advancement not verified → snapshot pre-run head.
- **F-COV-15 (HARDEN)**: `ledger.verify_chain()` / chain-across-markers not called.
- **F-COV-16 (NIT)**: Cassette byte-identity tradeoff — surface as Notes, do not pin.
- **F-COV-17 (NIT)**: `_paths.py` in Refactor vs Files-to-touch → make it an AC.

### Test Quality critic — 15 findings (5 BLOCK, 9 HARDEN, 1 NIT)

- **F-TQ-1 (BLOCK)**: Cassette path conflicts with canonical layout (S5-05 HARDENED used `tests/integration/gates/cassettes/stage6_retry_recovers.yaml`, single file with two interactions).
- **F-TQ-2 (BLOCK)**: `@pytest.mark.vcr(...)` + `block_network` fixture missing.
- **F-TQ-3 (BLOCK)**: TDD plan reinvents primitives S5-05 hardened (ReplanHookSpy, Phase4Interaction, assert_stage6_chokepoint_clean).
- **F-TQ-4 (BLOCK)**: `sandbox_run_id` / `patch_blake3` shape not verified before distinctness.
- **F-TQ-5 (BLOCK)**: Pre_execute / attempt ordering never asserted.
- **F-TQ-6 (HARDEN)**: `head_bin == ledger.head()` passes on `b"" == b""` + chain-advance not checked.
- **F-TQ-7 (BLOCK)**: Cost ↔ attempts cross-link missing.
- **F-TQ-8 (HARDEN)**: Deny-substring overly broad; misses real exfil shapes.
- **F-TQ-9 (HARDEN)**: `trace.unavailable` empty-file escape.
- **F-TQ-10 (NIT)**: `--strict-markers` already set.
- **F-TQ-11 (BLOCK)**: `--cov-fail-under=85` blocks single-test AC invocation → pin `--no-cov`.
- **F-TQ-12 (BLOCK)**: macOS auto-detect proves nothing about path taken → structlog event capture.
- **F-TQ-13 (HARDEN)**: Cassette-stability triple-replay absent at process level.
- **F-TQ-14 (HARDEN)**: Hook-firing observability at process level — picked path (b): inject spy via `make_orchestrator`.
- **F-TQ-15 (HARDEN)**: `RetryLedger(..., prev_chain_head=None)` re-read semantics ambiguous → use a separate `open_existing` or pure helper.

### Consistency critic — 13 findings (3 BLOCK, 9 HARDEN, 1 NIT)

- **F-CN-1 (BLOCK)**: JSONL discriminator `"type"` not `"kind"`.
- **F-CN-2 (BLOCK)**: Cassette path doesn't exist; canonical is single file in `tests/integration/gates/cassettes/`.
- **F-CN-3 (BLOCK)**: `chain_head.bin` path contradicts itself (outline vs stub vs AC).
- **F-CN-4 (HARDEN)**: ADR-0013 invoked but not in "ADRs honored".
- **F-CN-5 (HARDEN)**: `<fixture-cve>` placeholder; pin via fixture metadata.
- **F-CN-6 (HARDEN)**: `Depends on:` under-stated by ~10 stories.
- **F-CN-7 (HARDEN)**: Default-3-retry assumption not documented in Notes.
- **F-CN-8 (HARDEN)**: `trace.unavailable` upstream owner unidentified.
- **F-CN-9 (HARDEN)**: backend field path "wherever it's recorded" → use `SandboxCostEntry.backend` Literal.
- **F-CN-10 (NIT)**: `RunId` raw-string at E2E boundary — add Notes explaining the deliberate boundary.
- **F-CN-11 (HARDEN)**: Deny-substring grep is a tripwire, not the primary credential-leak defense (ADR-0012 own + adversarial tests).
- **F-CN-12 (HARDEN)**: Cross-OS OR-escape-hatch — pick monkeypatch path.
- **F-CN-13 (NIT)**: References paraphrase "two cost rows" ambiguous on re-read.

### Design-Patterns critic — 13 findings (2 BLOCK, 6 HARDEN, 5 NIT)

- **F-DP-1 (BLOCK)**: Discriminator `kind` vs `type` — same as F-CN-1; resolved via `RetryLedger.entries()` typed sum.
- **F-DP-2 (HARDEN)**: Primitive obsession on identifiers — consume typed `Attempt` accessors.
- **F-DP-3 (HARDEN)**: `_DENY_SUBSTRINGS` rule-of-three crossed — extract to `src/codegenie/sandbox/env_allowlist.py`.
- **F-DP-4 (BLOCK)**: `iterdir()` non-determinism — same as F-COV-9.
- **F-DP-5 (HARDEN)**: Backend field-path "wherever it's recorded" — same as F-CN-9; resolved via typed Literal on `SandboxCostEntry`.
- **F-DP-6 (NIT)**: Literal narrowing follows from F-DP-2.
- **F-DP-7 (HARDEN)**: Duplicate parse paths — single via `entries()` / `attempts()`.
- **F-DP-8 (HARDEN)**: Wall-clock unenforced — same as F-COV-1.
- **F-DP-9 (NIT)**: Backend parametrize deferred to n=3.
- **F-DP-10 (HARDEN)**: Chain-verify across markers — same as F-COV-15.
- **F-DP-11 (NIT)**: `e2e_repo_factory` deferred to Phase-7.
- **F-DP-12 (NIT)**: Optional `assert_stage6_chokepoint_clean` at E2E end.
- **F-DP-13 (BLOCK)**: Dead `monkeypatch` parameter / missing `CODEGENIE_HOME` setenv.

### Conflict resolution

No critic-critic conflicts at block tier. The Design-Patterns critic's nudge to consume kernels (`entries()`, `Attempt` accessors, `Literal` backend) aligns with Consistency's "match S2-01/S8-01 HARDENED contracts" and Test-Quality's "consume S5-05 primitives." Conflict-resolution rule `Consistency > Coverage > Test-Quality > Design-Patterns` was applied only on F-COV-3 (Coverage wanted a `failed_unrecoverable` second test; Consistency-with-Goal kept it out-of-scope, deferred to `scenarios.yaml`) and F-COV-13 (Coverage flagged the deny-substring fragility; Consistency framed it as a tripwire-not-primary-defense per ADR-0012) — both resolved with explicit framing rather than scope expansion.

### Verdict: HARDENED

The story had directionally-right intent, a thorough References list, and the right Goal sentence. But it was importing block-tier lessons sibling stories (`S5-05`, `S8-01`, `S8-02`) already paid the cost of — `"kind"` vs `"type"`, the two-cassette layout that doesn't exist, the `iterdir()` non-determinism, the cost↔attempts cross-link AC-text-without-test-body. With the edits applied below, every AC is binary-verifiable, the TDD plan exercises the load-bearing causal chain (hook fires → `prior_attempts` carries → second LLM call differs → distinct patch), and the design-pattern alignment with the rest of Phase 5 (typed Pydantic accessors, `Literal` discriminators, SSOT for deny-substrings) is enforced as observable ACs rather than aspirational Notes.

---

*This validation report is append-only history. The story file has been edited in place to reflect the hardened shape.*
