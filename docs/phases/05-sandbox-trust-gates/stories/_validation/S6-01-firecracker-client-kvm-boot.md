# Validation report: S6-01 — `FirecrackerClient` boot + exec + copy-out

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S6-01 ships the **third concrete consumer** of the `SandboxClient` Protocol + S1-02 contract + the FCS/DI/closed-Literal pattern stack that S3-02 (DinD client) HARDENED on 2026-05-23. The S3-02 validation report explicitly anchors S6-01 forward as completing the rule-of-three on Hexagonal DI ports + functional-core/imperative-shell + `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` Final constants + closed-Literal `reason` discriminator + module-purity AST walker.

The draft correctly identified the surface (boot + exec + copy-out + three structured precondition errors + `health()`), traced cleanly to ADR-0001 / ADR-0004 / ADR-0006, and named S6-04 as the consumer of its error-message contract. But it had **24 findings across all four critic lenses, including thirteen block-tier weaknesses** that an executor following the draft literally would have silently violated or could not have compiled. The most consequential:

1. **`SandboxSpec.logs_dir` / `SandboxSpec.copy_out_root` are phantom fields** — S1-02 places both on `SandboxRun` (the client *outputs* them), never on `SandboxSpec`. AC-2 + every TDD fixture (lines 124-134, 146-156, 177-181 in the draft) construct `SandboxSpec(logs_dir=..., copy_out_root=...)`; `extra="forbid"` rejects this at every fixture call. Family-bug identical to the `EnvAllowlist` phantom S3-02 caught.
2. **Required `SandboxSpec` fields omitted from every fixture** — `pids_limit`, `base_image`, `enable_trace`, `copy_out`, `label`, `sandbox_spec_hash` have no defaults; every test fixture would `ValidationError` on construction. The story cannot reach a single green test as written.
3. **Warning IDs violate the CLAUDE.md namespace regex** `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` — `"kvm_missing"`, `"firecracker_binary_digest_mismatch"`, `"vmlinux_digest_mismatch"`, `"rootfs_digest_mismatch"` are all single-segment. S3-02 already paid this rent (renamed `buildx_missing` → `sandbox.buildx_missing`); S6-01 inherits.
4. **`SandboxRun` 13+4-field coverage absent.** AC-2 pins only `backend` and `gate_isolation_class`. The S3-02 precedent (AC-RUN-FIELDS-1..-17) mandates every field have a stub/computed rule. Mutation: `microvm_seconds=999999` passes the draft tests.
5. **`SendCtrlAltDel` ≠ `SIGKILL`.** AC-8 conflates ACPI graceful shutdown with hard kill. A guest that ignores ACPI satisfies AC-8 and leaks beyond `time_budget_seconds`.
6. **`requests` vs UDS contradiction.** Impl outline §3 adds `requests>=2.31`; Notes line 228 says `requests` doesn't speak UDS — use `requests-unixsocket` or `httpx`. Pyproject change is wrong if the impl picks `httpx`; mock target unstable until decided.
7. **No `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` module-level `Final` constants + AST single-occurrence walk** — S3-02 HARDENED elevated this to AC-tier for rule-of-three consumers. Without it, an inline `"firecracker"` typo is undetectable.
8. **No `_construct_sandbox_run` pure helper / `_wrap_api_error` adapter / factory-injected port.** Refactor §199 mentions splitting the API socket helper post-hoc; S3-02 made this AC-tier (AC-DI / AC-FCS) at the third consumer. `requests.Session` instantiated inside `__init__` is not unit-testable on macOS.
9. **No closed-`Literal` `SandboxBackendError.reason`** across `FirecrackerKvmMissing` / `FirecrackerBinaryMissing` / `FirecrackerRootfsMissing` (and the omitted exec / boot / copy-out / teardown error subclasses). Phase 11/13 key on this.
10. **`RunId` NewType not honored at the generation site.** Jail-dir name `.codegenie/sandbox/runs/<run_id>/` uses raw `str`. Same family-bug S3-02 caught.
11. **TDD plan covers four cases; S3-02 mandates five test files.** No module-purity AST walker, no full-`SandboxRun`-field assert, no structlog `capture_logs()` assertion, no registry round-trip, no Protocol structural conformance, no parametrized cleanup grid, no precondition-ordering test, no `spec.network=="scoped"` → `NotImplementedError` test.
12. **`test_execute_cleans_up_jail_dir_on_exception` is vacuously true.** Asserts no globs under `tmp_path / ".codegenie"` but the impl writes to `Path(".codegenie/sandbox/runs/<id>")` relative to cwd — a leaking impl still passes.
13. **In-guest exec contract unpinned** — Notes mention "`/sbin/init` busybox script reading from `/etc/sandbox-cmd`" but no AC pins how `cmd` enters, how stdout/stderr/exit_code leave, or how copy-out tar streams back. Each is a silent-failure surface.

Resolution: ~75 numbered ACs across 18 structured sections (was 13 unnumbered checkboxes), a **five-test-file TDD plan** mirroring S3-02, an expanded Files-to-touch table (was 8 entries, now 14), and a Notes-for-implementer block expanded with pattern lineage to S3-02 + scope-boundary contracts for S6-02 / S6-03. No Stage-3 research was needed — every finding traces to an existing precedent in S3-02 _validation, S1-02 contract, ADR-0001 / 0004 / 0006, or CLAUDE.md.

## Findings by critic

### Coverage critic (8 block-tier, 5 harden-tier, 1 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | `SandboxRun` 13+4 fields unpinned beyond `backend` + `gate_isolation_class` | AC-RUN-1..-17 |
| block | `spec.logs_dir` / `spec.copy_out_root` are phantom (S1-02 puts them on SandboxRun) | AC-API-2 + rewritten TDD fixtures via `_valid_spec()` helper |
| block | CtrlAltDel ≠ SIGKILL — AC-8 semantically wrong | AC-TIMEOUT-1..-3 (SIGTERM → grace → SIGKILL → teardown) |
| block | `requests` vs UDS dep contradiction | AC-DEP-1 (pick `httpx` per S3-02 ecosystem; unix socket transport); Notes updated |
| block | No `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` Final + AST walker | AC-CANONICAL-1..-4 + `tests/sandbox/firecracker/test_client_purity.py` |
| block | Warning IDs violate CLAUDE.md regex | AC-WID-1..-3 + `_WARNING_IDS` frozenset import-time assertion |
| block | `spec.network=="scoped"` silent ignore | AC-SPEC-DEFER-1..-7 parametrized fail-loud-or-defer table |
| block | OOM mechanism + timeout signal-absence not pinned | AC-OOM-1..-3 + WARNING event on signal absence |
| harden | structlog event verb canonical-table append (S1-01 HARDENED inheritance) | AC-EVT-1..-3 (STARTED/COMPLETED/FAILED triples) |
| harden | `health()` success-confidence value undefined | AC-HEALTH-1..-3 confidence mapping table |
| harden | 5 s boot wait-loop in Notes only | AC-BOOT-WAIT-1 (`FirecrackerApiSocketTimeout` after 5 s) |
| harden | `copy_in` tar helper conditional ("reuse if exists") fragile | AC-COPYIN-1 + Files-to-touch row for `sandbox/firecracker/copy_in.py` |
| harden | `from __future__ import annotations` + `__all__` discipline missing | AC-API-4 + AC-API-5 |
| nit | Coverage floor present (line ≥ 95 / branch ≥ 90) — consistent | Unchanged |

### Test-Quality critic (4 block-tier, 4 harden-tier, 2 NEEDS RESEARCH, 1 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | `test_execute_cleans_up_jail_dir_on_exception` vacuously true (uses `tmp_path / ".codegenie"`, impl uses cwd `.codegenie`) | AC-CLEANUP-1..-5 + `monkeypatch.chdir(tmp_path)` + 8-cell parametrized cleanup grid |
| block | `test_execute_boots_microvm…` skipped on every contributor laptop and CI (until Step 6 Risk resolves) — story can ship with zero positive-boot evidence | TDD plan splits: pure-helper test for `_construct_sandbox_run` (always runs) + KVM-only integration test stays gated |
| block | `test_health_reports_all_four_preconditions` only asserts one reason + low confidence | AC-HEALTH-1..-3 + parametrized 5-row confidence table |
| block | `patch("...Path.exists")` globally False — silently demands precondition order; doesn't pin it positively; reorder invisible | AC-PRECOND-1..-3 + dedicated parametrized precondition-order test using mock `call_count` assertions |
| harden | Mock boundary unstable (`subprocess.Popen + requests.Session` while Notes say UDS-incompatible) | Resolved by AC-DI-1 factory port — tests mock the port, not the transport |
| harden | No `FirecrackerBinaryMissing` 8-char hex-prefix assertion (AC-5 of draft) | AC-ERR-3 pins observable message shape |
| harden | No closed-Literal `SandboxBackendError.reason` test | AC-ERR-1..-2 |
| harden | No `killed_by_oom=True` / `timed_out=True` positive test | AC-OOM-1..-3 + AC-TIMEOUT-1..-3 |
| NEEDS RESEARCH (resolved inline) | Digest-mismatch hypothesis property | Inlined as AC-ERR-3 — hypothesis property over BLAKE3 byte-permutations |
| NEEDS RESEARCH (resolved inline) | Precondition-order metamorphic property | Inlined as AC-PRECOND-3 — mock `call_count==0` for downstream asserts |
| nit | `monkeypatch.chdir(tmp_path)` is project-standard idiom | Adopted in TDD plan |

### Consistency critic (4 block-tier, 4 harden-tier, 2 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | Phantom `SandboxSpec.logs_dir` / `copy_out_root` (S1-02 lines 152-167) | AC-API-2: constructor adds `runs_root: Path = Path(".codegenie/sandbox/runs")`; client *generates* `logs_dir` + `copy_out_root` from `runs_root / run_id /`. AC-2 reworded. |
| block | Required `SandboxSpec` fields omitted from TDD fixtures (`pids_limit`, `base_image`, `enable_trace`, `copy_out`, `label`, `sandbox_spec_hash`) | TDD plan defines a shared `_valid_spec()` fixture helper enumerating every required field. Imports `_valid_spec_kwargs` from `tests/sandbox/test_contract_models.py` (the S1-02 precedent). |
| block | Warning IDs violate CLAUDE.md regex | AC-WID-1..-3 — rename to `sandbox.kvm_missing`, `sandbox.firecracker.binary_digest_mismatch`, `sandbox.firecracker.vmlinux_digest_mismatch`, `sandbox.firecracker.rootfs_digest_mismatch`. Arch §Edge case 15's `"kvm_missing"` is flagged as an arch erratum in Notes-for-implementer — story follows CLAUDE.md, not the arch text. |
| block | CtrlAltDel ≠ SIGKILL (semantic error) | AC-TIMEOUT-1..-3 |
| harden | `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` Final missing | AC-CANONICAL-1..-4 |
| harden | structlog event verbs incomplete + S1-01 canonical-table append-only missing | AC-EVT-1..-3 |
| harden | `RunId` NewType not honored | AC-RUN-1 + AC-API-3 (re-use `sandbox/did/_uuid7.py`'s `generate_run_id() -> RunId`) |
| harden | `SandboxHealth.confidence` success-value unspecified | AC-HEALTH-1 confidence mapping table |
| nit | `requests` vs UDS contradiction (impl outline vs Notes) | AC-DEP-1 picks `httpx` |
| nit | AC-9 subprocess-chokepoint AC could note S6-02's additive widening | Notes-for-implementer paragraph |

### Design-Patterns critic (5 block-tier, 4 harden-tier, 4 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | `execute()` 13-step inline monolith — no pure helpers (FCS violation, S3-02 inheritance) | AC-FCS-1..-5 — `_build_api_socket_requests`, `_construct_sandbox_run`, `_wrap_api_error`, `_parse_oom_evidence`, `_parse_vsock_exit_code` (all pure, all unit-tested) |
| block | `_FirecrackerApiSocket` instantiated inline; Refactor §199 mentions splitting post-hoc | AC-DI-1..-3 — constructor injects `api_socket_factory: Callable[[Path, Path], _ApiSocket] = _default_api_socket_factory` |
| block | Closed-`Literal` `SandboxBackendError.reason` missing | AC-ERR-1..-2 — closed `reason` Literal set: `{"sandbox.kvm_missing", "sandbox.firecracker.binary_digest_mismatch", "sandbox.firecracker.vmlinux_digest_mismatch", "sandbox.firecracker.rootfs_digest_mismatch", "sandbox.firecracker.api_socket_unreachable", "sandbox.firecracker.instance_start_failed", "sandbox.firecracker.vsock_exec_failed", "sandbox.firecracker.copy_out_failed", "sandbox.firecracker.teardown_failed"}` |
| block | `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` Final + AST walker missing | AC-CANONICAL-1..-4 + `test_client_purity.py` (Phase-5 convention) |
| block | `run_id: str` violates `RunId` NewType seam | AC-RUN-1 + AC-API-3 |
| harden | `subprocess.Popen` called inline in `execute()` — coupled to chokepoint binary | AC-DI-2 — `FirecrackerProcessHandle` Port + `_LocalFirecrackerProcess` adapter |
| harden | Cleanup discipline in Refactor §202 only — should be AC | AC-CLEANUP-1..-5 + 8-cell grid |
| harden | In-guest vsock helper boundary unclear | AC-VSOCK-1..-3 pin contract: (a) helper script lives at `tools/firecracker/<rootfs_digest>/sbin/sandbox-exec`, (b) `/etc/sandbox-cmd` carries cmd as `argv0\0argv1\0...\0`, (c) vsock port 52 carries `(exit_code, stdout, stderr)` as `length-prefixed-blake3-sealed protobuf` ... OR explicit deferral to S6-03 with stub raises. Synthesizer picks deferral — see Conflict resolutions. |
| harden | Anaemic `dict[str, Any]` for Firecracker API payloads | AC-API-7 — TypedDict shim `_firecracker_api_types.py` (`MachineConfig`, `BootSource`, `Drive`, `Action`) |
| nit | `uuid7` helper hoisting (S3-02's `_uuid7.py`) | Notes-for-implementer: re-use, not re-vendor. Hoist to `sandbox/_uuid7.py` deferred to a future cleanup task (rule-of-three on the helper not yet reached). |
| nit | `_assert_*` precondition methods → `Precondition` tuple iterated | Notes-for-implementer (first consumer of pattern; YAGNI) |
| nit | `BaseSandboxClient` mixin for replicated `health()` shape | Notes-for-implementer (deferred to Phase 7 fourth backend) |
| nit | `from __future__ import annotations` + `__all__` convention | AC-API-4 + AC-API-5 |

## Conflict resolutions

- **In-guest vsock helper contract (harden, Design-Patterns F8) vs scope (Out-of-scope already defers S6-03).** Defining the wire contract here couples S6-01 to rootfs internals owned by S6-03. Resolution: **defer**. AC-VSOCK-1 stubs the in-guest helper invocation as a Protocol port `_VsockExecPort` with a `NotImplementedError` default implementation; S6-03 / S6-05 wire the real helper. This keeps S6-01 unit-testable (mock the port) without dictating rootfs internals.
- **Coverage vs Rule 2 on TypedDict shim for Firecracker API payloads.** Coverage critic noted anaemic dict; Rule 2 says three similar lines is better than premature abstraction. This is the first consumer of the API-payload shape (no sibling backend uses these structures). Resolution: **add the shim now** because it serves Test-Quality (table tests for `_build_api_socket_requests` need typed inputs) and mypy --strict, not just future extensibility. Rule 9 takes precedence (tests verify intent).
- **Design-Patterns vs Rule 3 on `FirecrackerProcessHandle` Port.** This adds one port for the second consumer of subprocess-in-a-chokepoint (S3-02 has `_DockerBuildxRunner`-shape in `did/build.py`). Rule-of-two-going-on-three — defer mandate. Resolution: **note in implementer**, do NOT mandate AC. (Single inline `subprocess.Popen` inside the chokepoint file is acceptable; the FCS-extracted `_default_api_socket_factory` already gives tests a mock target.)
- **Coverage vs Consistency on `spec.network=="scoped"`.** Coverage wants AC-SPEC-DEFER-1 to raise `NotImplementedError`; Consistency notes ADR-0001 + S6-02 expect this raise as the wiring point. Both convergent. Resolution: **AC-SPEC-DEFER-1** raises `NotImplementedError("network='scoped' deferred to S6-02")`. S6-02 will widen.
- **Test-Quality vs scope on KVM-only integration test.** Test-Quality wants positive-boot evidence in the unit suite; the only positive boot is `skip_if_no_kvm`. Resolution: the new TDD plan adds a pure-helper test for `_construct_sandbox_run` against a hypothesis-generated `SandboxRun` shape — this exercises the full 13+4 field grid without KVM. The KVM-gated integration test remains as-is (S6-05 owns the smoke).

## Edits applied to the story

**Header / status:**
- `Status: Ready` → `Status: Ready (HARDENED 2026-05-25)`.
- `Depends on: S3-02` → `Depends on: S1-01 (errors + logging + warning-ID regex), S1-02 (Protocol + 13+4 SandboxRun fields + RunId NewType + cross-field model_validator), S1-05 (registry), S3-02 HARDENED (FCS + DI port + closed-Literal reason + canonical Literal patterns)`.
- `ADRs honored:` annotated each with the aspect this story enforces.

**Validation notes (new, ~60 lines):** Thirteen block-tier + thirteen harden/nit findings summarized; rationale for every AC change; explicit pattern-lineage callouts (S3-02 → S6-01 completes the rule-of-three on FCS / DI / canonical-Literal / module-purity).

**Context (light edit):** Added paragraph naming this story as the third concrete consumer of the S1-02 contract + S3-02-HARDENED patterns, with the rule-of-three completion explicitly cited.

**References (expanded):** Added explicit line-number anchors into `phase-arch-design.md`; added prior-HARDENED-report reference (S1-02 / S3-02); added Firecracker actions-API doc cross-reference for `SendCtrlAltDel`-vs-SIGKILL semantics; added CLAUDE.md anchors for warning-ID regex + Newtype identifiers.

**Goal (rewritten):** Now explicitly names the 13+4-field S1-02 contract, the `runs_root`-derived `logs_dir` + `copy_out_root` semantics, and the three precondition errors with `reason` discriminator.

**Acceptance criteria (rewritten):** Was 13 unnumbered checkboxes; now ~75 numbered ACs across 18 sections (A through R):
- A. Public surface + module purity (`__all__`, `__future__`, ADR-citing docstring, module-level `Final` constants for canonical Literals, runs_root constructor param)
- B. Hexagonal DI ports (`api_socket_factory`, `vsock_exec_port`)
- C. `execute()` happy-path + precondition ordering (kvm → binary → rootfs → boot → exec → copy-out)
- D. Full 13+4-field `SandboxRun` coverage with S6-01 stub/computed values + Phase pointers
- E. Canonical Literal spelling — positively pinned via AST walk
- F. Closed-Literal error reason discriminator + per-phase mapping
- G. Spec-feature fail-loud + deferred-warning policy (`network=="scoped"` → `NotImplementedError` per S6-02 wiring)
- H. `health()` confidence mapping table + alphabetized lists + namespace regex
- I. Cleanup discipline (8-cell parametrized grid + monkeypatch.chdir)
- J. OOM detection (vsock exit-code 137 → OOM; dmesg fallback; signal-absence WARNING)
- K. Timeout (SIGTERM → grace → SIGKILL → teardown; `timed_out=True`)
- L. Registry round-trip + Protocol structural conformance
- M. RunId / uuid7 helper re-use (no re-vendoring)
- N. Dependencies (`httpx` for UDS; not `requests`)
- O. Module purity (AST walker enforcing import allowlist + canonical-literal counts + zero bare event strings)
- P. Event-name discipline (append-only S1-01 table; STARTED/COMPLETED/FAILED verbs)
- Q. Functional core / imperative shell (five pure helpers + thin shell + TypedDict for API payloads)
- R. Coverage + tooling gates

**Implementation outline (rewritten):** Now ordered: deps (`httpx`, `blake3`) → import `_uuid7.generate_run_id` from sibling → TypedDict shim → `client.py` (module-level Final constants, helper ordering, decorator placement, factory port) → event constants append → test files in red-first order (purity walker first) → refactor pass with explicit `mypy --strict` quarantine note.

**TDD plan (rewritten):** Five test files (was one):
1. `test_client_purity.py` — AST walker (Phase-5 convention); banned imports; canonical-literal occurrence counts; warning-ID regex membership.
2. `test_client_helpers.py` — pure-helper unit tests for `_construct_sandbox_run`, `_wrap_api_error`, `_parse_oom_evidence`, `_parse_vsock_exit_code`, `_build_api_socket_requests`; one hypothesis property test (digest-mismatch metamorphic).
3. `test_client_core.py` — `_valid_spec()` helper + parametrized precondition-order grid + 8-cell cleanup grid + `spec.network=="scoped"` → `NotImplementedError` + structlog event-fields capture + registry round-trip + Protocol conformance + full 17-field `SandboxRun` assertion.
4. `test_client_health.py` — parametrized 5-row confidence-mapping table + canonical reason IDs + `detected_at` UTC + `warnings` alphabetized.
5. `test_client_timeout_and_oom.py` — `killed_by_oom=True` for exit-code-137 + dmesg-parse; `timed_out=True` for SIGTERM-then-SIGKILL grace window; signal-absence WARNING event.

**Files to touch (expanded):** Now lists 14 entries (was 8) including `pyproject.toml` (`httpx`), `_firecracker_api_types.py` TypedDict shim, `sandbox/_events.py` append, `sandbox/firecracker/copy_in.py`, five test files, the AST module-purity test.

**Out of scope (expanded):** Adds explicit deferrals for the in-guest vsock-exec helper (S6-03 / S6-05 owns the real implementation; S6-01 ships the `_VsockExecPort` Protocol with NotImplementedError default).

**Notes for the implementer (expanded):** Pattern-lineage paragraphs (DI ports, FCS, closed-Literal reason, canonical literal AST walk) with S3-02 cross-references; `httpx` UDS transport rationale; `SendCtrlAltDel`-vs-SIGKILL semantics; warning-ID regex + arch §Edge case 15 erratum note; uuid7 re-use guidance; sealed `reason` Literal extension policy (ADR amendment); event-name verb convention; `_VsockExecPort` deferral contract; subprocess-chokepoint forward-compat with S6-02.

## Forward-compat anchor — what's pinned for downstream stories

- **S6-02 (network policy):** widens `spec.network=="scoped"` from AC-SPEC-DEFER-1's `NotImplementedError`; lands `sandbox/firecracker/network_policy.py` as the second chokepoint under ADR-0001. Inherits `_BACKEND_NAME` Final + `_wrap_api_error` adapter pattern + sealed `reason` Literal extension procedure.
- **S6-03 (rootfs + digests):** widens `from_digests_yaml(path)` classmethod factory; ships the real in-guest vsock helper that replaces `_VsockExecPort`'s `NotImplementedError` default; populates `tools/firecracker/<rootfs_digest>/sbin/sandbox-exec`.
- **S6-04 (auto-detect):** consumes `FirecrackerKvmMissing.reason == "sandbox.kvm_missing"` + the literal string `"docker_in_docker"` in the error message; auto-detect's INFO log matches on the canonical reason ID, not message substring.
- **S6-05 (CI smoke + cron):** consumes the now-mockable `_FirecrackerProcessHandle` + the now-untouchable canonical Literal constants; the KVM-gated integration test asserts byte-equally against the unit-suite grid.
- **Phase 7 distroless:** would be the fourth concrete consumer of `SandboxClient`; at that point a `BaseSandboxClient` mixin extraction is warranted (per Design-Patterns nit F12).
- **Phase 11 merge-gate + Phase 13 cost dashboard:** key on `SandboxBackendError.reason: Literal[...]` (closed); the AC-ERR-1 sealed set is the authoritative list — extension requires an ADR amendment.

## No `RESCUE` findings

Every block-tier weakness was patchable by AC tightening + TDD rewrite + helper inheritance from S3-02. The goal is sound, the scope is sound, ADRs honored are correct, the slice boundary with S6-02 / S6-03 / S6-04 / S6-05 is correct. Story remains shippable after hardening.
