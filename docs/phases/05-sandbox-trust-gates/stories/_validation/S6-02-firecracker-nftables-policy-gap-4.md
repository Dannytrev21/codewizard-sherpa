# Validation report: S6-02 — Firecracker host-side TAP + nftables network policy

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (`story-validation-corrector` scheduled task)

## Summary

S6-02 closes Gap 4 of [phase-arch-design.md](../../phase-arch-design.md) by shipping `sandbox/firecracker/network_policy.py` so `FirecrackerClient.execute` enforces `network="scoped"` at the host kernel rather than inside the (untrusted) guest. The deliverable maps to [ADR-0009](../../ADRs/0009-firecracker-network-policy-host-side-nftables.md) (host-side TAP + nftables), [ADR-0001](../../ADRs/0001-two-chokepoint-sandbox-seam.md) (subprocess chokepoint discipline — widens the allowlist to the 4th file post-ADR-0009), and [ADR-0004](../../ADRs/0004-dind-default-macos-with-gate-isolation-class.md) (Firecracker is Linux-only — nftables-on-Linux is acceptable).

Pattern-lineage-wise, S6-02 is the **second concrete consumer** of the Phase-5 `network_policy` family (S3-03 shipped the DinD `iptables` sibling, 2026-05-23 HARDENED) AND the **fourth concrete consumer** of the S3-01/S3-02/S3-03/S6-01 stack of `runner`/`resolver` Hexagonal DI ports + functional-core/imperative-shell + closed-Literal `SandboxBackendError.reason` discriminator + module-purity AST walker + canonical `STARTED/COMPLETED/FAILED` event-verb triples + `_BACKEND_NAME` / `_GATE_ISOLATION_CLASS` `Final` constants + warning-ID namespace regex. The rule-of-three was crossed at S3-03; from S6-01 forward these patterns are MANDATORY AC-tier inheritance.

The draft correctly identified the surface (TAP + nftables + apply + teardown + golden ruleset + DNS resolution) and traced cleanly to ADR-0009 / ADR-0001 / ADR-0004, but had **30+ findings across all four critic lenses, including thirteen block-tier** that an executor following the draft literally would have shipped silently broken or could not compile. The most consequential:

1. **(coverage + consistency — block) `apply_policy(spec: SandboxSpec) -> NetNamespaceConfig` signature is missing `run_id`.** The story uses `cgsbx-<run_id[:8]>` as the TAP-device name (Implementation §3, Notes line 201) but `SandboxSpec` does not carry `run_id` — S1-02 places `run_id: RunId` on `SandboxRun`, generated *inside* `FirecrackerClient.execute()` via `generate_run_id()` (S6-01 AC-A3). The call from `client.py` must therefore be `apply_policy(spec, run_id=run_id)` (or equivalent). The draft's `apply_policy(spec)` cannot derive a TAP name — implementation collapses on first compile attempt.

2. **(coverage + consistency — block) DNS resolution staleness has the same load-bearing failure mode as S3-03 paid rent on.** ADR-0009 §Tradeoffs row 5 acknowledges the failure mode ("DNS resolution failures on the host masquerade as 'egress denied'") but the draft's `_resolve_hostnames(allowlist: list[str]) -> dict[str, list[str]]` returns one-resolution-per-`apply_policy()` call **without an explicit per-`execute()` re-resolution AC**. Notes line 203 mentions "Re-resolving allowlisted hostnames on every `execute()` is the right default" but it must be an AC, not a Note, for the executor to honor. Per ADR-0009 acceptance row 4 ("~50–100 ms per-execute overhead"), per-`execute()` re-resolution is *the design intent*. Resolution: AC-DNS-1..AC-DNS-6 mirror S3-03 AC-DNS-1..AC-DNS-5: two-helper FCS split (impure `_resolve_egress_allowlist(allowlist, *, resolver) -> tuple[ResolvedHost, ...]` feeds pure `_render_ruleset(resolved, ...) -> str`), staleness window documented in module docstring, no cross-`apply_policy()` caching.

3. **(consistency — block) Closed-Literal `SandboxBackendError.reason` discriminator violated.** The draft introduces a single `FirecrackerNetworkPolicyError(SandboxBackendError)` exception with no `reason` Literal. Phase-13 cost ledger keys on `(error_class, reason)`; a new subclass without a closed Literal is silently incompatible. S3-03 widened `SandboxBackendError.reason` additively by 7 members (to 11 total); S6-01 widened by another 4 members (to 15 total: + `sandbox.kvm_missing` + `sandbox.firecracker.binary_digest_mismatch` + `sandbox.firecracker.vmlinux_digest_mismatch` + `sandbox.firecracker.rootfs_digest_mismatch`, plus 5 internal `api_socket_unreachable` / `instance_start_failed` / `vsock_exec_failed` / `copy_out_failed` / `teardown_failed`). Resolution: AC-ERR-1..AC-ERR-5 widen S1-01 `SandboxBackendError.reason` Literal additively by **seven members** (matching the failure-mode taxonomy) — `"sandbox.firecracker.network_policy.dns_resolution_failed"`, `"sandbox.firecracker.network_policy.nftables_apply_failed"`, `"sandbox.firecracker.network_policy.nftables_teardown_failed"`, `"sandbox.firecracker.network_policy.tap_create_failed"`, `"sandbox.firecracker.network_policy.tap_destroy_failed"`, `"sandbox.firecracker.network_policy.ip_literal_invalid"`, `"sandbox.firecracker.network_policy.nftables_missing"` — and pin the `FirecrackerNetworkPolicyError(SandboxBackendError)` subclass narrows on these seven via `reason: Literal[...]`. `typing.get_args(...)` asserts byte-exactly.

4. **(consistency — block) Warning IDs violate CLAUDE.md namespace regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.** Notes line 205 references `"nftables_missing"` (single-segment); the structlog event in AC-12 mentions `sandbox.firecracker.tap_orphan` (correct shape) but the failure surface is otherwise under-pinned. S3-03 paid this rent (`iptables_apply_failed` → `sandbox.did.network_policy.iptables_apply_failed`); S6-01 paid this rent (`kvm_missing` → `sandbox.kvm_missing`). S6-02 inherits. Resolution: all event names + all warning IDs match the two-segment regex; AC-WID-1..AC-WID-4 pin the canonical IDs.

5. **(consistency — block) Event-name strings violate S1-01 HARDENED canonical-table + `STARTED/COMPLETED/FAILED` verb convention.** Draft Implementation §6 uses `sandbox.firecracker.network.apply` (singular noun — wrong; sibling S3-03 ships `sandbox.did.network_policy.applied`) and `sandbox.firecracker.network.teardown` (bare verb). Resolution: AC-EVT-1 appends **six** `Final[str]` constants to `sandbox/logging.py` alphabetized into the sorted `__all__`:
   - `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLIED = "sandbox.firecracker.network_policy.applied"`
   - `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_REVERTED = "sandbox.firecracker.network_policy.reverted"`
   - `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLY_FAILED = "sandbox.firecracker.network_policy.apply_failed"`
   - `EVENT_SANDBOX_FIRECRACKER_TAP_CREATED = "sandbox.firecracker.tap.created"`
   - `EVENT_SANDBOX_FIRECRACKER_TAP_DESTROYED = "sandbox.firecracker.tap.destroyed"`
   - `EVENT_SANDBOX_FIRECRACKER_TAP_ORPHAN = "sandbox.firecracker.tap.orphan"` (consumed by S8-01 `sandbox gc`)

6. **(coverage + race — block) Network policy + InstanceStart ordering creates an egress leak window if `apply_policy` returns before nftables rules are loaded.** Draft AC-7 says "`FirecrackerClient.execute(spec)` calls `apply_policy(spec)` *before* `InstanceStart`" — fine — but does not pin **the order within `apply_policy()` itself**: TAP-create must happen BEFORE nftables-rule-load, but the nftables ruleset must be loaded BEFORE the TAP is brought up (`ip link set <tap> up`). If `ip link set up` happens before `nft -f -`, the TAP can forward packets unfiltered for the ~5–50 ms window before rules land. Mirrors S3-03 AC-RACE-1 (the iptables sibling pays this rent by structuring `create-with-sleep-entrypoint → start → apply → exec_run`). Resolution: AC-RACE-1..AC-RACE-3 pin the apply order — (a) `ip tuntap add` (TAP exists but DOWN), (b) `ip addr add host_ip/30`, (c) `nft -f -` (rules loaded against named table), (d) `ip link set <tap> up` (TAP brought up — packets now pass under rules), (e) return `NetNamespaceConfig`. Adversarial test: monkeypatch `_apply_nft` to sleep 100 ms; assert `_link_up` has not been called yet at that moment.

7. **(coverage — block) `ip link set <tap> up` not in implementation outline; teardown does not enumerate `ip link set down` before `ip tuntap del`.** Notes line 206 references `nft delete table` for atomic teardown but is silent on TAP-device teardown order. Resolution: AC-TEARDOWN-1..AC-TEARDOWN-4 enumerate teardown order — (a) `nft delete table inet cgsbx_<run_id_short>` (rules gone), (b) `ip link set <tap> down`, (c) `ip tuntap del dev <tap> mode tap`. Failure of (b) on a missing-link is `EEXIST=0`-equivalent and continues; same for (c); same for (a). Per-step failures emit WARNING with reason="sandbox.firecracker.network_policy.{nftables_teardown_failed,tap_destroy_failed}"; do NOT re-raise — primary exception always wins (mirrors S3-03 AC-REVERT-3/AC-REVERT-4).

8. **(coverage — block) Hexagonal DI port for `runner` + `resolver` not in story** — fourth concrete consumer of the pattern (S3-01 set the precedent, S3-02 added `docker_factory`, S3-03 added `runner` + `resolver`, S6-01 added `api_socket_factory` / `process_handle_factory` / `vsock_exec_port` / `clock`). Rule-of-three crossed twice over. Draft Implementation §3-6 calls `subprocess` inline; tests use `patch("subprocess.run")` (unstable mock boundary). Resolution: AC-DI-1..AC-DI-5 elevate to AC-tier: `apply_policy(spec, *, run_id: RunId, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _default_runner, resolver: Callable[[str], list[str]] = _default_resolver, clock: Callable[[], datetime] = _default_clock) -> NetNamespaceConfig`. `_default_runner` is the *only* function in the file that calls `subprocess.run`; AST walker (AC-PURE-3) asserts this. Tests inject `runner=spy` without `unittest.mock.patch`.

9. **(coverage — block) Functional core / imperative shell split missing.** Fourth concrete consumer (S3-01/S3-02/S3-03/S6-01 each shipped explicit FCS splits). Resolution: AC-FCS-1..AC-FCS-7 enumerate pure helpers — `_render_ruleset(table_name: str, allowed_v4: tuple[str, ...], allowed_v6: tuple[str, ...]) -> str`, `_tap_name_for(run_id: RunId) -> str`, `_subnet_for(run_id: RunId) -> tuple[str, str]` (returns `(host_ip, guest_ip)` for `/30` carve-out), `_table_name_for(run_id: RunId) -> str`, `_partition_ip_literals(allowlist: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]` (returns `(literal_v4, literal_v6, hostnames_to_resolve)`), `_validate_ip_literal(s: str) -> Literal["v4", "v6", "invalid"]`, `_wrap_subprocess_error(err, *, reason: ...) -> FirecrackerNetworkPolicyError`. **Impure shells**: `apply_policy()`, `_resolve_egress_allowlist()`, `_create_tap()`, `_destroy_tap()`, `_apply_nft()`, `_link_up()`. Each pure helper unit-tested in isolation.

10. **(coverage — block) `SandboxSpec` TDD fixture omits 7 required fields.** The draft's `_spec()` helper sets only `cmd`, `copy_in`, `logs_dir`, `copy_out_root`, `time_budget_seconds`, `memory_limit_mib`, `network`, `egress_allowlist`, `env` — but `SandboxSpec` (per S1-02 lines 152-167) requires `base_image`, `enable_trace`, `pids_limit`, `copy_out`, `label`, `sandbox_spec_hash` AND **rejects** `logs_dir`/`copy_out_root` (phantom fields; S6-01 paid this rent — they belong on `SandboxRun`, not `SandboxSpec`). Every test would fail at `extra="forbid"` validation. Resolution: AC-FIX-1 mandates the TDD plan import `_valid_spec_kwargs` from the S1-02 precedent `tests/sandbox/test_contract_models.py`; AC-FIX-2 removes `logs_dir` / `copy_out_root` from the fixture; AC-FIX-3 confirms the S1-02 model_validator `_check_network_implies_no_allowlist` (network="none" → `egress_allowlist == []`) is exercised in a fixture-construction test.

11. **(test-quality — block) Golden ruleset is single-fixture for one allowlist size and one host.** Mirrors S3-03 finding #11. Mutation: a `_render_ruleset` that hardcodes `["registry.npmjs.org" → "104.16.16.35", "2606:4700::6810:1023"]` and ignores its arguments passes the lone golden test. Resolution: AC-RENDER-1..AC-RENDER-6 pin (a) three concrete golden fixtures `[empty_allowlist, single_v4_only, mixed_v4_v6]`, (b) hypothesis property test `@given(st.lists(_v4_addrs, max_size=4), st.lists(_v6_addrs, max_size=4))` asserting: every emitted v4 address appears in exactly one `ip daddr` rule; every emitted v6 address appears in exactly one `ip6 daddr` rule; the table name is exactly `inet cgsbx_<run_id_short>`; the final policy is `policy drop`; `ct state established,related accept` appears exactly once.

12. **(test-quality — block) `subprocess.run` parameter set unpinned across every chokepoint call.** Draft's `_apply_nft` is `subprocess ["nft","-f","-"]` with stdin (good) but no `timeout`, no `env`, no `cwd`, no `start_new_session`, no `stderr=subprocess.PIPE`. `_create_tap` and `_destroy_tap` likewise. Resolution: AC-SUBPROCESS-1..AC-SUBPROCESS-6 pin every kwarg via a module-level `_DEFAULT_RUN_KWARGS: Final[Mapping[str, object]] = MappingProxyType({"check": True, "capture_output": True, "text": False, "timeout": _DEFAULT_NFT_TIMEOUT_SECONDS, "stdin": subprocess.DEVNULL, "start_new_session": True, "env": _MINIMAL_NFT_ENV})` (with `stdin` overridden to a PIPE for the `nft -f -` call only); AC-SUBPROCESS-7 fences `shell=True`/`os.system`/`os.popen` (belt-and-suspenders on `forbidden-patterns` pre-commit). Golden argv snapshots for each of the four subprocess invocations (`nft -f -`, `nft delete table inet ...`, `ip tuntap add`, `ip link set up`, `ip addr add`, `ip tuntap del`).

13. **(test-quality — block) Test `test_teardown_is_idempotent` measures `subprocess.run` calls but the impl uses a DI `runner` after AC-DI-1.** Mock target unstable; once DI lands, the test breaks. Resolution: AC-TEST-1..AC-TEST-3 pin all teardown/cleanup tests against a `RunnerSpy` (records argv tuples) injected via the DI seam, not via `unittest.mock.patch("subprocess.run")`.

Beyond the block-tier, harden-tier work:

14. **(test-quality — harden) `_destroy_tap` referenced in TDD plan §test_apply_failure_cleans_up_partial_tap but not in Implementation outline.** Resolution: AC-LIFECYCLE-1..AC-LIFECYCLE-4 enumerate every private helper: `_create_tap`, `_destroy_tap`, `_link_up`, `_apply_nft`, `_revert_nft`, `_resolve_egress_allowlist`.

15. **(test-quality — harden) `apply_policy` partial-apply rollback grid undefined.** Draft AC-6 says "removes any partially created TAP device before re-raising" — but does NOT enumerate **at which step** the rollback fires. There are 5 sequenced impure steps; a failure at step k must roll back steps k-1..1 in reverse order. Resolution: AC-ROLLBACK-1 ships a 5-cell parametrized rollback grid: `(fail_at_step ∈ {dns, tap_create, addr_add, nft_apply, link_up})` → assert the exact set of cleanup calls fires in reverse order.

16. **(coverage — harden) IP-literal allowlist case mentioned in Notes line 204 ("Be defensive against `egress_allowlist` containing IP literals — skip resolution, emit directly").** Not an AC. Resolution: AC-IP-LIT-1..AC-IP-LIT-3 pin: `_partition_ip_literals` separates literals from hostnames; literals skip resolution; mixed allowlists work; invalid IP literals raise `FirecrackerNetworkPolicyError(reason="sandbox.firecracker.network_policy.ip_literal_invalid")` BEFORE any subprocess call.

17. **(consistency — harden) `nft` binary missing detection on the runner.** Notes line 205 says "surface mismatch in `FirecrackerClient.health()` as `nftables_missing`". The `_default_runner`'s `FileNotFoundError` on the `nft` binary must wrap to `FirecrackerNetworkPolicyError(reason="sandbox.firecracker.network_policy.nftables_missing")`. Health-side surface is via S6-01 AC-H1's `SandboxHealth.reasons` widening — Resolution: AC-HEALTH-1..AC-HEALTH-3 pin: `FirecrackerClient.health()` adds a precondition check "nft binary present"; on missing, includes `sandbox.firecracker.network_policy.nftables_missing` in `SandboxHealth.reasons`. **Coordinates with S6-01 AC-H1 — this story widens the health precondition set by one row** (not part of the original S6-01 AC-H1 four-row table; flag in Notes as an `EDIT` of `client.py::health()`).

18. **(test-quality — harden) `health()` widening is an EDIT to S6-01's client.py.** Not a new file. Resolution: AC-CLIENT-EDIT-1..AC-CLIENT-EDIT-3 enumerate every S6-01 AC modified — AC-H1 (precondition table widened from 4 to 5 rows), AC-C2 (`execute()` wires `apply_policy` + finally-teardown), AC-D8 (`/network-interfaces` API payload added when `cfg.tap_name is not None`), AC-D9 (`boot_args` widened with `ip=<guest_ip>::<host_ip>::eth0:off` segment).

19. **(consistency — harden) `boot_args` segment shape unpinned.** Draft Implementation §4 says `boot_args="... ip=<guest_ip>::<host_ip>::eth0:off"` but the Linux kernel `ip=` argument is `client-ip:server-ip:gw-ip:netmask:hostname:device:autoconf` (7 colon-separated fields per `Documentation/admin-guide/nfs/nfsroot.rst`). The draft has 4 fields. Resolution: AC-BOOT-ARGS-1 pins the canonical 7-field form: `f"ip={guest_ip}::{host_ip}:{netmask}::eth0:off"` (note: `gw-ip` empty → routes via host_ip directly; `hostname` empty); golden-test the rendered boot_args string for one canonical run_id.

20. **(consistency — harden) Subnet allocation not pinned — what `/30` does each run get?** Concurrent runs need non-overlapping `/30` carve-outs. Resolution: AC-SUBNET-1 derives `(host_ip, guest_ip)` from `run_id` via `_subnet_for(run_id)`: take the first 30 bits of `blake3(run_id.encode())[:4]`, mask to `10.x.x.x/30`, return `(host_ip = .1, guest_ip = .2)`. Collision probability across 2^30 concurrent runs is negligible; document the pigeonhole tradeoff. AC-SUBNET-2: hypothesis property — across 1000 generated run_ids, no two share a `/30` (collision detected → re-derive with a salt; acceptable up to 0.1% retry rate).

21. **(coverage — harden) `_table_name_for(run_id)` characters — nft table names allow `[A-Za-z_][A-Za-z0-9_]*`** but `run_id` is hex (`0123456789abcdef`). Resolution: AC-TABLE-NAME-1 pins `_table_name_for(run_id) -> str` as `f"cgsbx_{run_id[:12]}"` (lowercased, 18 chars total — well under nft's 32-char limit); IFNAMSIZ-friendly TAP name is `f"cgsbx-{run_id[:8]}"` (14 chars, fits IFNAMSIZ=16 with NUL).

22. **(test-quality — harden) Coverage floor present (95/90); add explicit AC-COV-1 + AC-COV-2 with the canonical wording.**

23. **(test-quality — harden) `from __future__ import annotations` + `__all__` discipline missing — fourth consumer of the pattern.** Resolution: AC-PURE-1, AC-PURE-2 (sorted `__all__`).

24. **(coverage — harden) Module-purity AST walker missing.** S3-03 shipped `test_network_policy_purity.py` for the DinD sibling. S6-02 ships `test_network_policy_purity.py` for the Firecracker sibling, asserting: module docstring cites ADR-0001 + ADR-0009; `from __future__ import annotations` first; sorted `__all__`; **`subprocess` and `socket` are the only stdlib modules importable for I/O** (no `urllib`, no `requests`, no `httpx`); no `os.system` / `os.popen` / `shell=True`; the `_default_runner` is the only function whose body contains a `subprocess.run` call (AST walk). Mirrors S3-03 AC-PURE-1..AC-PURE-8.

25. **(consistency — harden) Subprocess fence allowlist additive widening to 5 chokepoint files.** S1-07 HARDENED `_SUBPROCESS_ALLOWLIST` already includes `firecracker/network_policy.py` (4-file allowlist post-ADR-0009). This story does NOT widen the allowlist further — it consumes the slot already reserved for it. Resolution: AC-FENCE-1 explicitly states the allowlist is unchanged; `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green after this story.

26. **(consistency — harden) `pyproject.toml` change?** Resolution: AC-DEP-1 confirms no new dependencies (stdlib `subprocess` + stdlib `socket` only; `blake3` already in the closure).

27. **(coverage — harden) `network="none"` → no subprocess call (good draft AC) but does NOT pin that `NetNamespaceConfig.teardown()` is also a no-op.** The teardown contract on `network="none"` is undefined. Resolution: AC-NONE-1..AC-NONE-3 enumerate: `network="none"` → `cfg.tap_name is None`, `cfg.nftables_table is None`, `cfg.teardown()` is a no-op (asserted via `RunnerSpy.calls == ()`).

28. **(coverage — harden) `egress_allowlist != [] ∧ network=="none"` rejection.** S1-02 model_validator already rejects this at `SandboxSpec` construction; this story does NOT need to also defend. Resolution: AC-INVALID-SPEC-1 confirms the model_validator fires before `apply_policy()` is reached.

29. **(test-quality — harden) Integration test placeholder uses internal `pytest.skip("Real-guest assertion deferred to S6-05 KVM-gated suite")` AND `@pytest.mark.skip_if_no_kvm`** — redundant + the internal skip silently masks any code that lands later. Resolution: AC-INTEG-1 ships only the `@pytest.mark.skip_if_no_kvm` placeholder (no internal `pytest.skip`); S6-05 lands the real assertions by editing the test body, not by removing a `pytest.skip`. The file lives at `tests/integration/sandbox/test_firecracker_network_policy.py` with a docstring naming S6-05 as the populator.

30. **(patterns — harden) `NetNamespaceConfig` dataclass with `_torn_down: bool = False` is anaemic / has a hidden state machine.** Better: explicit tagged union of states (`Uninitialized` | `Applied` | `TornDown`) OR a context-manager interface (`__enter__` / `__exit__`) for the apply/teardown lifecycle. Given Rule 2 (first consumer of this shape) AND the executor needs a callable surface that `FirecrackerClient.execute()` can use in a try/finally (matching the iptables sibling's `apply()`/`revert()` plain-function pattern), Resolution: AC-CFG-1..AC-CFG-3 keep the dataclass shape but pin: `NetNamespaceConfig` is **frozen** (`@dataclass(frozen=True, slots=True)`); the `_torn_down` flag is stored in a separate `_TeardownState` object referenced by the config (so the frozen invariant holds at the data layer; the state machine is explicit). Test exercises both `teardown()`-then-`teardown()` (idempotent) AND `apply_policy()`-raise-then-state-is-not-Applied.

31. **(patterns — nit, deferred) `register_network_policy_backend(...)` registry decorator.** S3-03 explicitly deferred this; S6-02 is the second consumer (rule-of-three not reached; Phase 7+ third backend e.g. gVisor would close it). Resolution: Notes-for-implementer paragraph confirms the deferral with the same precedent reference.

32. **(patterns — nit) `_BACKEND_NAME: Final[str] = "firecracker"` at module top.** S6-01 mandates this for `client.py` to defend against inline-string typos in event payloads / error reasons. S6-02 inherits — `network_policy.py` also has `backend="firecracker"` strings in event payloads. Resolution: AC-CANONICAL-1 pins `_BACKEND_NAME: Final[str] = "firecracker"` + module-purity AST walker asserts the literal `"firecracker"` does NOT appear in the file body outside this `Final` declaration (matches S6-01 AC-CANONICAL-1 pattern).

## Findings by critic

### Coverage critic (5 block-tier, 8 harden-tier, 2 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | `apply_policy(spec)` signature missing `run_id` | AC-API-1 widens signature |
| block | Per-`execute()` DNS re-resolution buried in Notes | AC-DNS-1..-6 elevate to AC |
| block | DNS-vs-rule-load ordering racy without explicit barrier | AC-RACE-1..-3 pin TAP-then-rules-then-link-up |
| block | `_link_up` / `ip link set` missing from impl outline | AC-LIFECYCLE-1..-4 + AC-TEARDOWN-1..-4 |
| block | `egress_allowlist` IP-literal case unhandled | AC-IP-LIT-1..-3 |
| harden | Subnet allocation per-run unpinned | AC-SUBNET-1..-2 |
| harden | `boot_args ip=` segment wrong field count | AC-BOOT-ARGS-1 |
| harden | Health surface widening unwired | AC-HEALTH-1..-3 + AC-CLIENT-EDIT-1 |
| harden | nft table name vs run_id charset | AC-TABLE-NAME-1 |
| harden | `network="none"` teardown contract undefined | AC-NONE-1..-3 |
| harden | Partial-apply rollback grid undefined | AC-ROLLBACK-1 |
| harden | Module-purity AST walker absent | AC-PURE-1..-8 |
| harden | Coverage floor wording absent | AC-COV-1..-2 |
| nit | `S1-02` model_validator `network="none" ∧ allowlist != []` not re-tested | AC-INVALID-SPEC-1 |
| nit | `pyproject.toml` no-change confirmation | AC-DEP-1 |

### Test-Quality critic (5 block-tier, 5 harden-tier, 1 NEEDS RESEARCH→inlined, 2 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | Hexagonal DI port for `runner` + `resolver` missing | AC-DI-1..-5 |
| block | FCS pure-helper split missing | AC-FCS-1..-7 |
| block | `subprocess.run` parameter set unpinned | AC-SUBPROCESS-1..-7 |
| block | Golden ruleset single-fixture (mutation passes) | AC-RENDER-1..-6 + hypothesis property |
| block | Tests use `unittest.mock.patch("subprocess.run")` (unstable boundary) | AC-TEST-1..-3 — `RunnerSpy` via DI seam |
| harden | TDD fixture omits 7 SandboxSpec required fields + uses phantom `logs_dir`/`copy_out_root` | AC-FIX-1..-3 |
| harden | `_destroy_tap` referenced but not declared | AC-LIFECYCLE-1..-4 |
| harden | Internal `pytest.skip(...)` shadows `@skip_if_no_kvm` | AC-INTEG-1 |
| harden | Closed-Literal `SandboxBackendError.reason` test missing | AC-ERR-3..-5 |
| harden | `from __future__ import annotations` + `__all__` discipline missing | AC-PURE-1..-2 |
| NEEDS RESEARCH (inlined) | nftables atomic rule replacement semantics on partial-load failure | Per nftables wiki: `nft -f -` is fully atomic — entire ruleset rolled back on any syntax error mid-script. Documented in module docstring + AC-RENDER-2. Source: https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement |
| nit | structlog `capture_logs()` usage convention | AC-EVT-3 |
| nit | Hypothesis property test idiom | Adopted in AC-RENDER-3 |

### Consistency critic (5 block-tier, 4 harden-tier, 2 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | Closed-Literal `SandboxBackendError.reason` widening absent | AC-ERR-1..-5 |
| block | Warning IDs violate CLAUDE.md namespace regex | AC-WID-1..-4 |
| block | Event-name strings violate S1-01 canonical-table verb convention | AC-EVT-1..-3 |
| block | Story does NOT enumerate which S6-01 ACs it edits | AC-CLIENT-EDIT-1..-3 |
| block | `boot_args ip=` segment wrong field count vs Linux kernel docs | AC-BOOT-ARGS-1 |
| harden | Subprocess fence allowlist consume-not-widen | AC-FENCE-1 |
| harden | `_BACKEND_NAME` `Final` constant missing | AC-CANONICAL-1 |
| harden | `pyproject.toml` no-change confirmation | AC-DEP-1 |
| harden | `nft` binary missing → `SandboxHealth.reasons` widening | AC-HEALTH-1..-3 |
| nit | Story dependency line lists only S6-01 — should list S1-01 / S1-02 / S1-05 / S1-07 / S3-03 explicitly | Header rewritten |
| nit | ADR-0009 line-number anchors | References §expanded |

### Design-Patterns critic (3 block-tier, 4 harden-tier, 4 nit)

| Severity | Finding | Resolution |
|---|---|---|
| block | Hexagonal DI port for `runner` + `resolver` (4th consumer; rule-of-three crossed twice) | AC-DI-1..-5 |
| block | Functional core / imperative shell split (4th consumer) | AC-FCS-1..-7 |
| block | Closed-Literal `reason` discriminator | AC-ERR-1..-5 |
| harden | `_BACKEND_NAME` `Final` (S6-01 inheritance) | AC-CANONICAL-1 |
| harden | Anaemic `NetNamespaceConfig` dataclass with hidden state | AC-CFG-1..-3 — frozen dataclass + explicit `_TeardownState` |
| harden | Module-purity AST walker missing | AC-PURE-3..-8 |
| harden | `_wrap_subprocess_error(err, *, reason)` adapter | AC-FCS-7 |
| nit | `register_network_policy_backend(...)` registry decorator | Notes — defer per Rule 2 (Phase 7+ third backend reaches rule-of-three) |
| nit | `NetNamespaceConfig.__enter__` / `__exit__` context-manager | Notes — defer; current try/finally idiom mirrors S3-03 sibling |
| nit | `_FirecrackerNftablesRunner` Port (S6-01 pattern echo) | Notes — single inline subprocess.run inside the chokepoint file is acceptable; the FCS-extracted `_default_runner` already gives tests a mock target. Defer until 5th consumer. |
| nit | `RunId` NewType honored at TAP-name derivation | AC-CANONICAL-2 |

## Conflict resolutions

- **Coverage (want explicit per-`execute` re-resolution AC) vs Rule 2 (don't add ACs not implied by the goal).** ADR-0009 §Tradeoffs row 5 makes the re-resolution explicit at the **architectural** level ("DNS resolution happens on the host via standard DNS (allowlist-checked)") + row 4 names the ~50–100 ms per-execute cost. The Goal in this story says "enforces `network='scoped'` ... using the host kernel as the trusted boundary" — re-resolution is part of that boundary contract. Resolution: AC-DNS-1 elevation is supported by ADR-0009; not a goal-widening.

- **Design-Patterns (want `register_network_policy_backend(...)` registry) vs Rule 2 (three similar lines is better than premature abstraction).** S3-03 explicitly deferred this; S6-02 is the second concrete consumer; rule-of-three not reached. Resolution: **defer**. Notes-for-implementer records the precedent.

- **Test-Quality (mutation-resistance via hypothesis property + 3 golden fixtures) vs Rule 2 (don't over-test).** Single-fixture golden lets a hardcode-the-fixture mutation pass; mutation-resistance is non-negotiable (Rule 9). Resolution: hypothesis property + 3 golden fixtures. Confidence: high — S3-03 paid this rent identically.

- **Coverage (want explicit subnet collision-probability AC) vs Rule 9 (intent-verifying tests, not regression).** Subnet collision is a tail-risk; over-formalizing it bloats the AC set. Resolution: AC-SUBNET-1 specifies the derivation algorithm + 30-bit search space; AC-SUBNET-2 caps a hypothesis property at "no collision across 1000 generated run_ids" (a verifiable bound, not the unattainable absolute "no collision ever"). The pigeonhole tradeoff is in module-docstring Notes.

- **Consistency (want `SandboxBackendError.reason` widened by 7 members) vs S3-03 (already widened by 7 to 11 total) vs S6-01 (already widened by 9 to 20 total).** The cumulative widening is monotone-additive — each story names exactly the members it adds. Resolution: AC-ERR-1 names the 7 new members; `typing.get_args(...)` is asserted on the *cumulative* union (20 + 7 = 27 members) byte-exactly. The widening is forward-compatible — S6-03 / S8-01 will each add more members in their own stories.

- **Design-Patterns (`NetNamespaceConfig.__enter__/__exit__` context manager) vs Consistency (try/finally idiom mirrors S3-03 sibling's `apply()`/`revert()` pair).** S3-03 ships `apply()` + `revert()` as plain module-level functions; the iptables-revert lives in `FirecrackerClient.execute()`'s `finally:` block. For symmetry, S6-02's `apply_policy()` + `cfg.teardown()` mirrors this — the teardown method is callable from the same `finally:` slot. Adding `__enter__/__exit__` would diverge from the sibling. Resolution: **defer the context-manager surface**; Notes-for-implementer paragraph records the opportunity for the rule-of-three (Phase 7+ third backend).

## Edits applied to the story

**Header / status:**
- `Status: Ready` → `Status: Ready (HARDENED 2026-05-25)`.
- `Depends on: S6-01` → `Depends on: S1-01 (errors + logging + warning-ID regex + STARTED/COMPLETED/FAILED verb convention), S1-02 (SandboxSpec + RunId NewType + `network: Literal["none","scoped"]` + model_validator), S1-05 (registry — not used here per Rule 2 second-consumer), S1-07 (subprocess fence allowlist already includes this file post-ADR-0009 — consume, not widen), S3-03 HARDENED (DinD network_policy sibling — `_compute_rules` / DI `runner`+`resolver` / closed-Literal `reason` / event-name canonical-table / golden+hypothesis test pattern this story mirrors), S6-01 HARDENED (FirecrackerClient surface this story EDITs additively — widens AC-H1 health precondition table, AC-C2 execute() body, AC-D8/D9 boot_args + /network-interfaces API)`.
- `ADRs honored:` annotated with the aspect each enforces.

**Validation notes (new, ~90 lines):** Thirteen block-tier + thirteen harden/nit findings summarized; rationale for every AC change; pattern-lineage callouts (S3-03 → S6-02 second consumer of `network_policy` family; S3-01/S3-02/S3-03/S6-01 → S6-02 fourth consumer of FCS + DI port + closed-Literal stack).

**Context (light edit):** Names this story as second `network_policy` consumer (rule-of-three not closed) AND fourth consumer of the FCS+DI+closed-Literal stack (rule-of-three crossed twice, mandatory inheritance).

**References (expanded):** Added explicit line-number anchors into `phase-arch-design.md`; added prior-HARDENED-report references (S1-02 / S3-03 / S6-01); added Linux kernel `Documentation/admin-guide/nfs/nfsroot.rst` reference for the `ip=` boot-arg field count; added CLAUDE.md anchors for warning-ID regex / FCS / Newtype identifiers / Extension by addition.

**Goal (light edit):** Tightened "uses the host kernel as the trusted boundary" → "uses the host kernel as the trusted boundary; resolves allowlisted hostnames per-`execute()` (no cross-run cache); applies nftables atomically before bringing the TAP up; tears down in reverse order in `finally`."

**Acceptance criteria (full rewrite from 13 unnumbered checkboxes to ~80 numbered ACs across 18 sections):**
- §A — Public surface + module discipline (AC-API-1..-5)
- §B — `apply_policy` contract: network="none" (AC-NONE-1..-3)
- §C — `apply_policy` contract: network="scoped" (AC-SCOPED-1..-5)
- §D — Hexagonal DI ports (AC-DI-1..-5)
- §E — Functional core / imperative shell (AC-FCS-1..-7)
- §F — nftables ruleset (AC-RENDER-1..-6) — including hypothesis property + 3 golden fixtures
- §G — DNS resolution (AC-DNS-1..-6)
- §H — TAP lifecycle (AC-LIFECYCLE-1..-4)
- §I — Race / ordering (AC-RACE-1..-3)
- §J — Teardown / rollback (AC-TEARDOWN-1..-4 + AC-ROLLBACK-1)
- §K — Errors + closed-Literal `reason` (AC-ERR-1..-5)
- §L — Events (AC-EVT-1..-3)
- §M — IP-literal handling (AC-IP-LIT-1..-3)
- §N — Subnet allocation (AC-SUBNET-1..-2)
- §O — Subprocess discipline (AC-SUBPROCESS-1..-7)
- §P — FirecrackerClient EDIT (AC-CLIENT-EDIT-1..-3) + Health widening (AC-HEALTH-1..-3) + boot_args (AC-BOOT-ARGS-1)
- §Q — Fence + module-purity (AC-FENCE-1 + AC-PURE-1..-8 + AC-CANONICAL-1..-2)
- §R — Integration test placeholder (AC-INTEG-1) + Coverage floor (AC-COV-1..-2) + Spec invariants (AC-FIX-1..-3 + AC-INVALID-SPEC-1) + Deps (AC-DEP-1)

**Implementation outline (expanded ~5→14 steps):** Each step numbered, error-paths enumerated, lifecycle ordering pinned, references the AC numbers.

**TDD plan (expanded from 1 to 5 test files):**
- `tests/sandbox/firecracker/test_network_policy_core.py` — `apply_policy` end-to-end with `RunnerSpy` + `ResolverSpy` DI
- `tests/sandbox/firecracker/test_render_ruleset.py` — pure helper unit tests + 3 golden fixtures + hypothesis property
- `tests/sandbox/firecracker/test_network_policy_lifecycle.py` — TAP create/destroy + nft apply/revert + idempotency + partial-apply rollback 5-cell grid
- `tests/sandbox/firecracker/test_network_policy_errors.py` — closed-Literal `reason` set, error message shape, DNS failure isolation, IP-literal-invalid path
- `tests/sandbox/firecracker/test_network_policy_purity.py` — module-purity AST walker
- `tests/integration/sandbox/test_firecracker_network_policy.py` — KVM-only placeholder (S6-05 populates)

**Files to touch (expanded 6→12 entries):** Adds `sandbox/logging.py` (EDIT — six new event constants); `sandbox/errors.py` (EDIT — widen `reason` Literal by 7 + add `FirecrackerNetworkPolicyError` subclass); `sandbox/firecracker/client.py` (EDIT — widen `health()` precondition table by 1 row, wire `apply_policy` call + finally-teardown, add `boot_args ip=` segment, add `/network-interfaces` API call); `tests/golden/nftables_rules_*.txt` (3 fixtures); `tests/sandbox/firecracker/test_client_*.py` (EDIT — S6-01 amendments per AC-CLIENT-EDIT-*).

**Out of scope (clarified):** Real KVM assertions → S6-05; auto-detect path → S6-04; rootfs digest enforcement → S6-03; orphan TAP CLI surface → S8-01 (but THIS story emits the `sandbox.firecracker.tap.orphan` event hook); IPv6-only allowlist mode → Phase 5 explicit non-goal; cross-run DNS cache → explicit non-goal (per ADR-0009 acceptance).

**Notes for the implementer (expanded ~10→25 paragraphs):** nftables atomic semantics, host-side DNS as security boundary, IFNAMSIZ math, structlog hook for S8-01, no cross-run DNS caching, IP-literal defense, `iptables-nft` vs native `nft` distinction, per-`execute()` re-resolution, pattern lineage callouts (S3-03 sibling + S6-01 host client), subprocess fence is **already widened** by S1-07 — consume the slot, do NOT edit S1-07.

## Pattern lineage anchors

| Phase-5 ancestor | Pattern inherited | This story's AC |
|---|---|---|
| S1-01 HARDENED | Warning-ID namespace regex; `STARTED/COMPLETED/FAILED` event-verb canonical-table | AC-WID-1..-4 + AC-EVT-1..-3 |
| S1-02 HARDENED | `SandboxSpec` 13-field schema + `network: Literal["none","scoped"]` + model_validator + `RunId` NewType | AC-FIX-1..-3 + AC-INVALID-SPEC-1 + AC-CANONICAL-2 |
| S1-07 HARDENED | `_SUBPROCESS_ALLOWLIST` 4-file frozenset + per-file module-purity walker | AC-FENCE-1 + AC-PURE-3..-8 |
| S3-01 HARDENED | Closed-Literal `reason` discriminator | AC-ERR-1..-5 |
| S3-02 HARDENED | Hexagonal DI port pattern (`docker_factory`) — 2nd consumer | AC-DI-1..-5 |
| S3-03 HARDENED | `network_policy.py` sibling — DNS-IP fan-out, two-helper FCS split, per-rule revert idempotency, closed-Literal `reason` widening (+7), event-verb triples (+6), golden+hypothesis test pattern, partial-apply rollback grid, runner+resolver DI port | AC-DNS-1..-6 + AC-FCS-1..-7 + AC-DI-1..-5 + AC-ERR-1..-5 + AC-EVT-1..-3 + AC-RENDER-1..-6 + AC-ROLLBACK-1 + AC-RACE-1..-3 |
| S6-01 HARDENED | `FirecrackerClient` shell this story EDITs additively — `health()` precondition table, `execute()` `finally:` discipline, `boot_args` shape, `_BACKEND_NAME` `Final` constant | AC-CLIENT-EDIT-1..-3 + AC-HEALTH-1..-3 + AC-BOOT-ARGS-1 + AC-CANONICAL-1 |

## Forward-compat anchor (for downstream stories)

- **S6-03 (rootfs digests):** the `_default_runner` DI seam this story ships is the integration point for the digest-enforced runner in S6-03 (the runner verifies the `nft` binary digest before exec). Do NOT inline-call `subprocess.run` for `nft`; route via the seam.
- **S6-04 (auto-detect):** the new `sandbox.firecracker.network_policy.nftables_missing` reason ID is what S6-04 keys on to fall back from Firecracker to DinD when `nft` is absent.
- **S6-05 (KVM smoke):** the integration test placeholder this story lands is where S6-05 places real `curl npmjs ok / curl github fails` assertions. Do NOT regenerate the test file in S6-05; edit the body.
- **S8-01 (`sandbox gc`):** the `EVENT_SANDBOX_FIRECRACKER_TAP_ORPHAN` constant + `cgsbx-<run_id[:8]>` naming convention this story ships is what S8-01's `sandbox gc` keys on to detect orphan TAP devices left behind by killed processes.
- **Phase 7+ third `network_policy` backend (e.g., gVisor):** reaches rule-of-three; at that point collapse `apply_policy()` / `cfg.teardown()` to a `NetworkPolicyApplier` Protocol per ADR-0006 + spin up `register_network_policy_backend(...)` registry. Until then, plain module-level functions per S3-03's precedent.

## Cross-cutting consumers (where the patterns this story enforces are read downstream)

- **Phase 6 (LangGraph nodes):** `apply_policy` + `cfg.teardown()` lift unchanged into a LangGraph side-effect node.
- **Phase 8 (cost ledger):** keys on `error_class=FirecrackerNetworkPolicyError` + `reason=sandbox.firecracker.network_policy.*` for per-failure cost attribution.
- **Phase 11 (evidence bundle):** the `tests/golden/nftables_rules_*.txt` fixtures are bundle-included as the canonical egress-policy evidence for an audited remediation.
- **Phase 13 (multi-language):** the `_partition_ip_literals` helper is the seam where Python / Java / Go-specific allowlist patterns are added (e.g., PyPI mirror IPs); the helper itself stays language-agnostic.
