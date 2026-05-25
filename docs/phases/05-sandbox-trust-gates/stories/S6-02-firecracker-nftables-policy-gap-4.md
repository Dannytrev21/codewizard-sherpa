# Story S6-02 — Firecracker host-side TAP + nftables network policy

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** L
**Depends on:**
- S1-01 HARDENED (`sandbox/errors.py` — closed-Literal `SandboxBackendError.reason`; `sandbox/logging.py` event-name canonical-table append-only + sorted `__all__` + `STARTED/COMPLETED/FAILED` verb triples; warning-ID namespace regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`)
- S1-02 HARDENED (`SandboxSpec` frozen `extra="forbid"` 13-field schema, `network: Literal["none","scoped"]`, `egress_allowlist: list[str]`, model_validator `_check_network_implies_no_allowlist`, `RunId` NewType)
- S1-05 HARDENED (`@register_sandbox_backend` decorator — **not consumed by `network_policy.py`** per Rule 2 second-consumer; Notes-for-implementer records the deferral)
- S1-07 HARDENED (`_SUBPROCESS_ALLOWLIST` 4-file frozenset already includes `firecracker/network_policy.py` post-ADR-0009 — **this story consumes the reserved slot; does NOT widen the allowlist**)
- S3-03 HARDENED (DinD `network_policy.py` sibling: `_compute_rules`/`_resolve_egress_allowlist` two-helper FCS split; DI `runner` + `resolver` Hexagonal port; closed-Literal `reason` widening pattern; STARTED/COMPLETED/FAILED + APPLIED/REVERTED/APPLY_FAILED event triples; golden+hypothesis property test convention; partial-apply rollback grid; per-rule revert idempotency)
- S6-01 HARDENED (`FirecrackerClient` surface this story **EDITs additively** — widens AC-H1 health precondition table by one row, AC-C2 `execute()` body wires `apply_policy` + `finally:` teardown, AC-D8/D9 boot_args + `/network-interfaces` API)

**ADRs honored:**
- ADR-0001 — `sandbox/firecracker/network_policy.py` is the 4th of the 4 allowlisted subprocess chokepoints (post-ADR-0009 source-of-truth set; S1-07 reserved the slot — this story consumes it).
- ADR-0004 — Firecracker is Linux-only; native `nft` on Linux is acceptable.
- ADR-0009 — host-side TAP + nftables; trusted boundary is the host kernel; ~50–100 ms per-`execute()` overhead; per-`execute()` DNS re-resolution; golden ruleset goldens.

## Validation notes (2026-05-25 HARDENED)

The draft had thirteen block-tier weaknesses (see [`_validation/S6-02-firecracker-nftables-policy-gap-4.md`](_validation/S6-02-firecracker-nftables-policy-gap-4.md)). Headlines:

- **`apply_policy(spec)` signature missing `run_id`** — `SandboxSpec` does not carry `run_id`; the TAP-device naming pattern `cgsbx-<run_id[:8]>` cannot be derived without it. Signature widened to `apply_policy(spec, *, run_id: RunId, runner=_default_runner, resolver=_default_resolver, clock=_default_clock) -> NetNamespaceConfig`.
- **Closed-Literal `SandboxBackendError.reason` discriminator missing** — Phase-13 cost ledger keys on `(error_class, reason)`; new exception without a closed Literal silently incompatible. S1-01 union widened additively by **seven** members.
- **Warning IDs + event names violate canonical conventions** — single-segment IDs fail CLAUDE.md regex; `network.apply` is wrong noun + wrong verb against the `STARTED/COMPLETED/FAILED` + `APPLIED/REVERTED/APPLY_FAILED` table.
- **DNS rotation problem** — sibling S3-03 paid this rent for iptables (`-d hostname` resolves at rule-add time, not packet-match time). ADR-0009 acknowledges the failure mode but Notes-only mention was insufficient — elevated to AC-DNS-1..-6.
- **TAP-up vs nft-load ordering** — racy without explicit barrier. `ip tuntap add` → `ip addr add` → `nft -f -` → `ip link set <tap> up` must be the order; tests assert via `runner` call-order spy.
- **Fourth concrete consumer of Hexagonal DI + FCS + closed-Literal stack** — S3-01/S3-02/S3-03/S6-01 reached rule-of-three at S3-03; S6-02 inherits mandatorily.
- **TDD fixture used phantom `SandboxSpec.logs_dir` / `copy_out_root`** — same family-bug S6-01 caught; both fields live on `SandboxRun`, not `SandboxSpec`. Plus six required SandboxSpec fields omitted — every test fixture would `ValidationError` at construction.

Resolution: ~80 numbered ACs across 18 sections, a **six-test-file TDD plan** (vs draft's 1), an expanded Files-to-touch table (was 6 entries; now 12), and a Notes-for-implementer block expanded with pattern lineage to S3-03 sibling + S6-01 host client.

## Context

`SandboxSpec.network: Literal["none","scoped"]` + `egress_allowlist: list[str]` is the contract every backend must enforce. DinD enforces via `iptables` in `sandbox/did/network_policy.py` (S3-03 HARDENED, 2026-05-23); Firecracker has no iptables analog inside the guest, and the synthesis was silent on the mechanism — Gap 4 in `phase-arch-design.md`. ADR-0009 commits us to a host-side TAP device + nftables ruleset so the trusted boundary is the host kernel, not the (untrusted) guest. This story closes Gap 4: ship `sandbox/firecracker/network_policy.py::apply_policy(spec, *, run_id, ...)` and wire it into `FirecrackerClient.execute` so `network="scoped"` no longer raises `NotImplementedError` (left there by S6-01's AC-SPEC-DEFER-1 equivalent).

**Pattern lineage:** S6-02 is the **second concrete consumer of the `network_policy` family** (S3-03 ships the DinD `iptables` sibling — rule-of-three not yet closed; Phase 7+ third backend will reach it). It is ALSO the **fourth concrete consumer of the FCS + Hexagonal DI port + closed-Literal `reason` + canonical event-verb + module-purity AST-walker stack** (S3-01/S3-02/S3-03/S6-01 each shipped one). Rule-of-three crossed twice over; what S3-03 surfaced as forward-compat anchors for S6-02 is now mandatory AC-tier inheritance. See `_validation/S3-03-did-build-and-network-chokepoints.md §"Forward-compat anchor"` and `_validation/S6-01-firecracker-client-kvm-boot.md §"Forward-compat anchor"`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 4` (line ~1026) — verbatim statement of the problem and the host-side-TAP + nftables fix.
  - `../phase-arch-design.md §Component design — FirecrackerClient` (line ~495) — `network_policy.py` is the second of two subprocess sites in the Firecracker subpackage.
  - `../phase-arch-design.md §Physical view` (line ~314) — host kernel as enforcement boundary; guest is untrusted.
  - `../phase-arch-design.md §Tool-use safety` (line ~844) — subprocess allowlist post-ADR-0009 includes `sandbox/firecracker/network_policy.py` (S1-07 AC-SP-1 source-of-truth).
- **Phase ADRs:**
  - `../ADRs/0009-firecracker-network-policy-host-side-nftables.md` — decision, options considered (inside-guest filtering, MMDS DNS allowlist, slirp4netns), consequences (`apply_policy` signature, `tests/golden/nftables_rules_*.txt`, KVM-only integration test, ~50–100 ms per-execute overhead, **per-`execute()` re-resolution by design** per Tradeoff row 5).
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — subprocess chokepoint discipline; this module is the 4th allowlisted chokepoint post-ADR-0009.
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — Firecracker is Linux-only; native `nft` on Linux is acceptable.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — sandbox stack target this composes with.
- **Source design:**
  - `../final-design.md §Risk surface` — egress as defense-in-depth.
- **Prior validation (mandatory read):**
  - `_validation/S3-03-did-build-and-network-chokepoints.md` — sibling backend's HARDENED report. Forward-compat anchor names S6-02 explicitly with the patterns to inherit (DI `runner`+`resolver`, FCS split, closed-Literal `reason` widening, event-verb triples, golden+hypothesis convention, partial-apply rollback grid).
  - `_validation/S6-01-firecracker-client-kvm-boot.md` — host `FirecrackerClient` HARDENED report. Forward-compat anchor names this story as the consumer of the boot/exec/copy-out surface this story EDITs additively.
  - `_validation/S1-02-sandbox-contract-protocol-models.md` — the 13-field `SandboxSpec` schema + `_check_network_implies_no_allowlist` model_validator + `RunId` NewType this story consumes.
- **Existing code:**
  - `src/codegenie/sandbox/did/network_policy.py` (from S3-03 HARDENED) — sibling chokepoint; mirror its `_resolve_egress_allowlist` impure shell + `_compute_rules` pure helper + DI `runner` / `resolver` keyword-only parameters + per-rule revert idempotency.
  - `src/codegenie/sandbox/firecracker/client.py` (from S6-01 HARDENED) — `execute()` currently raises `NotImplementedError` on `network="scoped"`; this story replaces with `apply_policy(spec, run_id=run_id)` call + `finally:` teardown. `health()` precondition table widens by one row (`nftables_missing`). `boot_args` widens with the canonical 7-field `ip=` segment. `/network-interfaces` API call added when `cfg.tap_name is not None`.
  - `src/codegenie/sandbox/contract.py` (from S1-02) — `SandboxSpec.network`, `egress_allowlist`, `RunId` NewType.
  - `src/codegenie/sandbox/errors.py` (from S1-01 HARDENED) — `SandboxBackendError.reason` closed Literal; this story widens additively by 7 members + adds `FirecrackerNetworkPolicyError(SandboxBackendError)` subclass.
  - `src/codegenie/sandbox/logging.py` (or wherever S1-01 placed the canonical events table) — append-only six new event constants alphabetized into sorted `__all__`.
- **External docs:**
  - nftables atomic-rule-replacement: <https://wiki.nftables.org/wiki-nftables/index.php/Atomic_rule_replacement> — `nft -f -` is fully atomic; entire ruleset rolled back on any syntax error mid-script.
  - Firecracker TAP networking guide: <https://github.com/firecracker-microvm/firecracker/blob/main/docs/network-setup.md> — `ip tuntap add`, `ip link set` shape.
  - Linux kernel `ip=` boot-arg: `Documentation/admin-guide/nfs/nfsroot.rst` — canonical 7-field form `client-ip:server-ip:gw-ip:netmask:hostname:device:autoconf`.
- **CLAUDE.md anchors:**
  - "Warning + error IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`" — every event/reason in this story matches.
  - "Functional core / imperative shell" — seven pure helpers + impure shell.
  - "Newtype identifiers" — `RunId` consumed at TAP-name derivation site (`_tap_name_for(run_id)`).
  - "Extension by addition" — `SandboxBackendError.reason` Literal widened additively by 7 members; six new event constants appended to canonical table.

## Goal

Ship `src/codegenie/sandbox/firecracker/network_policy.py` exposing `apply_policy(spec, *, run_id, runner=_default_runner, resolver=_default_resolver, clock=_default_clock) -> NetNamespaceConfig` so `FirecrackerClient.execute(spec)` enforces `network="none"` (no NIC at all) and `network="scoped"` (host-side TAP + nftables egress allowlist) using **the host kernel as the trusted boundary**; resolves allowlisted hostnames per-`execute()` (no cross-run cache, per ADR-0009 Tradeoff row 5); loads the entire nftables ruleset atomically via `nft -f -` **before** bringing the TAP up; tears down in reverse order in a `finally:` block; emits namespaced canonical events + closed-Literal `reason`-tagged errors. Coordinated edits to `FirecrackerClient` (S6-01 surface) wire `apply_policy` into `execute()`, widen `health()` by one precondition row (`nftables_missing`), add the `/network-interfaces` API call when a TAP is present, and emit the canonical 7-field `ip=<guest_ip>::<host_ip>:<netmask>::eth0:off` boot-arg segment.

## Acceptance criteria

### §A. Public surface + module discipline

- [ ] **AC-API-1 — Module path + imports:** `from codegenie.sandbox.firecracker.network_policy import apply_policy, NetNamespaceConfig` succeeds with no side effects. Module path: `src/codegenie/sandbox/firecracker/network_policy.py`.
- [ ] **AC-API-2 — `apply_policy` signature:** `apply_policy(spec: SandboxSpec, *, run_id: RunId, runner: Callable[..., subprocess.CompletedProcess[bytes]] = _default_runner, resolver: Callable[[str], list[str]] = _default_resolver, clock: Callable[[], datetime] = _default_clock) -> NetNamespaceConfig`. Keyword-only after `spec`. Pure type-hint contract; `typing.get_type_hints(apply_policy)` returns the byte-exact annotations.
- [ ] **AC-API-3 — `NetNamespaceConfig` is a `@dataclass(frozen=True, slots=True)`:** fields `{tap_name: str | None, guest_ip: str | None, host_ip: str | None, netmask: str | None, nftables_table: str | None, _teardown_state: _TeardownState}` (the `_teardown_state` mutable companion stores the `_torn_down: bool` flag so the dataclass itself can stay frozen). `teardown(self) -> None` method calls into `_teardown_state`.
- [ ] **AC-API-4 — `__all__` sorted + `from __future__ import annotations` first line of module body:** `__all__: Final = ("NetNamespaceConfig", "apply_policy")`.
- [ ] **AC-API-5 — Module docstring cites ADR-0001 + ADR-0004 + ADR-0009 by filename** and quotes the host-as-trusted-boundary invariant verbatim from ADR-0009 Decision. Per-`execute()` re-resolution policy + ~50–100 ms overhead documented in the docstring as a load-bearing tradeoff.

### §B. `apply_policy` contract: `network="none"`

- [ ] **AC-NONE-1 — Zero subprocess calls:** `spec.network == "none"` → `apply_policy(spec, run_id=...)` returns `NetNamespaceConfig(tap_name=None, guest_ip=None, host_ip=None, netmask=None, nftables_table=None, _teardown_state=_TeardownState(torn_down=True))` without calling `runner` once. `RunnerSpy.calls == ()` asserted.
- [ ] **AC-NONE-2 — `cfg.teardown()` is a no-op:** for the `network="none"` config; idempotent; double-call is also no-op; `RunnerSpy.calls == ()` after both calls.
- [ ] **AC-NONE-3 — `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLIED` NOT emitted for `network="none"`** — only `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_REVERTED` may fire (with `tap_name=None`) on teardown if desired; preferable to also suppress on the `network="none"` path so logs remain quiet. AC asserts via `structlog.testing.capture_logs()`: zero `network_policy.*` events on the `network="none"` happy path.

### §C. `apply_policy` contract: `network="scoped"`

- [ ] **AC-SCOPED-1 — Happy path (in order):** (1) `_resolve_egress_allowlist(spec.egress_allowlist, resolver=resolver)` → `tuple[ResolvedHost, ...]`; (2) `_create_tap(run_id, runner=runner)` → `(tap_name, host_ip, guest_ip, netmask)`; (3) `_apply_nft(run_id, resolved=..., runner=runner)` → loads ruleset atomically via `nft -f -` on stdin; (4) `_link_up(tap_name, runner=runner)` → `ip link set <tap> up`; (5) returns populated `NetNamespaceConfig` with `_teardown_state=_TeardownState(torn_down=False)`. Emits `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLIED` with `{run_id, tap_name, allowlist_size, resolved_v4_count, resolved_v6_count, applied_at}`. `RunnerSpy.calls[0..3]` argv tuples asserted byte-exactly.
- [ ] **AC-SCOPED-2 — Empty `egress_allowlist` with `network="scoped"`:** legal per S1-02 model_validator (only `network="none" ∧ allowlist != []` is rejected). Result: a TAP + a ruleset with zero `accept` rules + `policy drop` — all egress denied; only `ct state established,related accept` survives. Golden fixture `tests/golden/nftables_rules_scoped_empty.txt`.
- [ ] **AC-SCOPED-3 — `egress_allowlist=["registry.npmjs.org"]`** (canonical fixture): rendered ruleset is byte-equal to `tests/golden/nftables_rules_scoped_npmjs.txt` for `_render_ruleset(table_name="cgsbx_<run_id_short>", allowed_v4=("104.16.16.35",), allowed_v6=("2606:4700::6810:1023",))`.
- [ ] **AC-SCOPED-4 — Mixed v4 + v6 + IP-literal allowlist** (`["registry.npmjs.org", "192.0.2.5", "2001:db8::1"]`): rendered ruleset is byte-equal to `tests/golden/nftables_rules_scoped_mixed.txt`. Three golden fixtures total (empty / npmjs / mixed); see AC-RENDER-1.
- [ ] **AC-SCOPED-5 — `subprocess` invocations live exclusively** in `sandbox/firecracker/network_policy.py` and `sandbox/firecracker/client.py`; `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green.

### §D. Hexagonal DI ports (fourth concrete consumer; mandatory inheritance)

- [ ] **AC-DI-1 — `_default_runner: Callable[..., subprocess.CompletedProcess[bytes]]`** is the only function in `network_policy.py` whose body contains a `subprocess.run` call. AST walker (AC-PURE-3) asserts.
- [ ] **AC-DI-2 — `_default_resolver: Callable[[str], list[str]]`** is the only function whose body calls `socket.getaddrinfo` (or equivalent). AST walker asserts.
- [ ] **AC-DI-3 — `_default_clock: Callable[[], datetime]`** returns tz-aware UTC; the only function whose body calls `datetime.now(timezone.utc)`. AST walker asserts.
- [ ] **AC-DI-4 — DI seams are keyword-only on `apply_policy`** AND on every private impure helper that needs them (`_resolve_egress_allowlist`, `_create_tap`, `_apply_nft`, `_link_up`, `_destroy_tap`, `_revert_nft`). No `unittest.mock.patch` required at any test site — tests inject `runner=spy`, `resolver=spy`, `clock=spy` directly.
- [ ] **AC-DI-5 — `RunnerSpy` test fixture** (under `tests/sandbox/firecracker/_runner_spy.py` shared with other Firecracker tests) records `(argv: tuple[str, ...], stdin: bytes | None, env: dict[str, str], timeout: float)` tuples + supports `side_effect: list[Exception | subprocess.CompletedProcess]` for ordered failures. Pattern mirrors S3-03's `RunnerSpy`.

### §E. Functional core / imperative shell (pure helpers)

- [ ] **AC-FCS-1 — `_render_ruleset(table_name: str, allowed_v4: tuple[str, ...], allowed_v6: tuple[str, ...]) -> str`** is pure (no I/O, no clock, no logger). Returns the entire nftables script as text. Tested in isolation across the 3 golden fixtures + hypothesis property (AC-RENDER-*).
- [ ] **AC-FCS-2 — `_tap_name_for(run_id: RunId) -> str`** is pure. Returns `f"cgsbx-{run_id[:8]}"` (14 chars total — fits IFNAMSIZ=16 with NUL). Tested with 10 random `RunId`s; all results regex-match `^cgsbx-[0-9a-f]{8}$`.
- [ ] **AC-FCS-3 — `_table_name_for(run_id: RunId) -> str`** is pure. Returns `f"cgsbx_{run_id[:12]}"` (18 chars total — well under nft's 32-char limit; nft table names allow `[A-Za-z_][A-Za-z0-9_]*`). Tested with 10 random `RunId`s; all results regex-match `^cgsbx_[0-9a-f]{12}$`.
- [ ] **AC-FCS-4 — `_subnet_for(run_id: RunId) -> tuple[str, str, str]`** is pure. Returns `(host_ip, guest_ip, netmask)`. Derivation: `blake3(run_id.encode())[:4]` → 32-bit int → mask to `10.x.x.0/30` → return (`.1`, `.2`, `255.255.255.252`). Hypothesis property (AC-SUBNET-2) asserts no `/30` collision across 1000 generated `RunId`s.
- [ ] **AC-FCS-5 — `_partition_ip_literals(allowlist: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]`** is pure. Returns `(literal_v4, literal_v6, hostnames_to_resolve)`. Tested with parametrized fixtures across pure-v4 / pure-v6 / pure-hostname / mixed / invalid-literal cases.
- [ ] **AC-FCS-6 — `_validate_ip_literal(s: str) -> Literal["v4", "v6", "invalid"]`** is pure. Uses stdlib `ipaddress.ip_address` for validation; classifies output. Hypothesis property: every v4-shaped string `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` classified as "v4" or "invalid" (never "v6"); ditto v6.
- [ ] **AC-FCS-7 — `_wrap_subprocess_error(err: BaseException, *, reason: _NetworkPolicyReason) -> FirecrackerNetworkPolicyError`** is pure (no I/O, no logger). Returns a new exception with `details={"reason": reason, "stderr_truncated": _truncate_stderr(getattr(err, "stderr", b""), 4096), "argv": getattr(err, "cmd", ())}`. Tested across the 7 reason values.

### §F. nftables ruleset rendering + golden + hypothesis

- [ ] **AC-RENDER-1 — Three golden fixtures committed:** `tests/golden/nftables_rules_scoped_empty.txt`, `tests/golden/nftables_rules_scoped_npmjs.txt`, `tests/golden/nftables_rules_scoped_mixed.txt`. Each is bytes-canonical (trailing-newline, LF-only, no BOM); regenerable via `python -m tests.golden.regenerate_nftables` (no manual edits). Module-level `_CANONICAL_TABLE_NAME: Final[str] = "cgsbx_test_fixture_00"` is used for golden goldens (fixture-stable independent of `RunId`).
- [ ] **AC-RENDER-2 — `nft -f -` is fully atomic per upstream wiki:** documented in module docstring; on syntax error mid-script the entire ruleset is rolled back. Partial-apply is therefore impossible AT the nft layer (but rollback at the TAP layer per AC-ROLLBACK-1 is still required).
- [ ] **AC-RENDER-3 — Hypothesis property `_render_ruleset`** `@given(st.lists(_v4_addr_strategy, max_size=4, unique=True), st.lists(_v6_addr_strategy, max_size=4, unique=True))`: assertions on output — (a) `table inet <table_name> {` appears exactly once; (b) `chain output { type filter hook output priority 0 ; policy drop ;` appears exactly once; (c) `ct state established,related accept` appears exactly once; (d) each `allowed_v4` appears in exactly one `ip daddr <addr> accept` rule; (e) each `allowed_v6` appears in exactly one `ip6 daddr <addr> accept` rule; (f) every v4 rule comes before every v6 rule (deterministic order for diff-ability); (g) lines are LF-terminated; (h) no trailing whitespace on any line.
- [ ] **AC-RENDER-4 — Determinism property:** for fixed inputs, `_render_ruleset(...)` returns byte-identical output across 100 calls (no clock, no hash, no set-iteration nondeterminism).
- [ ] **AC-RENDER-5 — `_render_ruleset(table_name, (), ())`** → the empty-allowlist ruleset matches golden `nftables_rules_scoped_empty.txt`: table + chain + `policy drop` + `established,related accept` + zero `daddr` rules.
- [ ] **AC-RENDER-6 — `_render_ruleset` rejects invalid table names** (regex `^[A-Za-z_][A-Za-z0-9_]{0,30}$`): raises `ValueError` at function entry (programming-error path; not a runtime user-facing error).

### §G. DNS resolution

- [ ] **AC-DNS-1 — Per-`execute()` re-resolution by design** (ADR-0009 Tradeoff row 5): `_resolve_egress_allowlist` is called once inside every `apply_policy` invocation; **no cross-`apply_policy` cache**. Asserted by a test that calls `apply_policy` twice with the same allowlist and verifies `_default_resolver` is invoked twice.
- [ ] **AC-DNS-2 — `_resolve_egress_allowlist(hostnames: tuple[str, ...], *, resolver) -> tuple[ResolvedHost, ...]`** is impure (calls `resolver`). For each hostname: calls `resolver(hostname)` → returns mixed v4+v6 addresses → splits into `ResolvedHost(hostname, v4: tuple[str, ...], v6: tuple[str, ...])`. Input-order-preserving + deduplicated within each host.
- [ ] **AC-DNS-3 — `socket.gaierror` / `OSError` on resolution** → wrapped to `FirecrackerNetworkPolicyError(reason="sandbox.firecracker.network_policy.dns_resolution_failed", details={"hostname": h, "errno": str(err)})`. Test asserts message contains `"resolve"` (lowercase) AND `"sandbox.firecracker.network_policy.dns_resolution_failed"`.
- [ ] **AC-DNS-4 — DNS-failure error is distinct from rule-load failure** by `reason` field — closed-Literal comparison; the message-substring assertion is in addition, not a replacement.
- [ ] **AC-DNS-5 — Resolution happens on the host** (security-boundary invariant): documented in module docstring; AC-DI-2 ensures the resolver port is the ONLY entry to DNS in the module — guest-side resolution is structurally impossible without editing this story's module-purity walker.
- [ ] **AC-DNS-6 — Mixed v4/v6 returned per hostname** (the canonical `_default_resolver` uses `socket.getaddrinfo(host, None, socket.AF_UNSPEC)` and splits AF_INET / AF_INET6 results). Asserted with a `ResolverSpy` returning `[("104.16.16.35", AF_INET), ("2606:4700::6810:1023", AF_INET6)]`.

### §H. TAP device lifecycle

- [ ] **AC-LIFECYCLE-1 — `_create_tap(run_id, *, runner) -> tuple[str, str, str, str]`** returns `(tap_name, host_ip, guest_ip, netmask)`. Internally calls `runner(["ip","tuntap","add","dev",tap_name,"mode","tap"], ...)` then `runner(["ip","addr","add",f"{host_ip}/30","dev",tap_name], ...)`. Argv golden-snapshotted per AC-SUBPROCESS-3.
- [ ] **AC-LIFECYCLE-2 — `_destroy_tap(tap_name, *, runner)`** calls `runner(["ip","link","set",tap_name,"down"], ...)` then `runner(["ip","tuntap","del","dev",tap_name,"mode","tap"], ...)`. **Idempotent**: a missing link / missing TAP returns exit code 1; `_destroy_tap` catches, logs WARNING `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLY_FAILED` with `reason="sandbox.firecracker.network_policy.tap_destroy_failed"`, and does NOT re-raise (mirrors S3-03 AC-REVERT-3).
- [ ] **AC-LIFECYCLE-3 — `_link_up(tap_name, *, runner)`** calls `runner(["ip","link","set",tap_name,"up"], ...)`. Atomic — one syscall.
- [ ] **AC-LIFECYCLE-4 — `_apply_nft(table_name, ruleset, *, runner)`** calls `runner(["nft","-f","-"], stdin_bytes=ruleset.encode("utf-8"), ...)`. `_revert_nft(table_name, *, runner)` calls `runner(["nft","delete","table","inet",table_name], ...)`; idempotent over missing-table (exit 1) per the same per-rule WARNING-not-raise discipline as `_destroy_tap`.

### §I. Race / ordering (no egress leak window)

- [ ] **AC-RACE-1 — TAP-up happens AFTER nft-load:** `apply_policy` order is strictly (1) TAP add (DOWN), (2) addr add, (3) nft load, (4) link up. The TAP is DOWN until rules are loaded — packets cannot pass even though the interface exists.
- [ ] **AC-RACE-2 — Adversarial test:** monkeypatch `_apply_nft` to sleep 100 ms; assert via `RunnerSpy` that `_link_up` is NOT in `RunnerSpy.calls` until after `_apply_nft` returns.
- [ ] **AC-RACE-3 — FirecrackerClient.execute() ordering:** `apply_policy(spec, run_id=run_id)` runs BEFORE `InstanceStart` API call; if any step in `apply_policy` raises, `InstanceStart` is never reached. Test asserts via `_default_api_socket_factory` spy that `InstanceStart` is not invoked when `_apply_nft` raises.

### §J. Teardown / rollback

- [ ] **AC-TEARDOWN-1 — `NetNamespaceConfig.teardown()` order:** (1) `_revert_nft(table_name)`, (2) `_destroy_tap(tap_name)`. Set `_teardown_state.torn_down = True` after. Test asserts `RunnerSpy.calls[-2:]` argv tuples byte-exactly.
- [ ] **AC-TEARDOWN-2 — `teardown()` is idempotent:** double-call is a no-op the second time; calling on a `_teardown_state.torn_down is True` config short-circuits and returns immediately; `RunnerSpy.call_count` unchanged on the second invocation.
- [ ] **AC-TEARDOWN-3 — Per-step failure isolation:** if `_revert_nft` raises, `_destroy_tap` STILL runs (catches `_revert_nft`'s exception, logs WARNING via canonical event, continues). If `_destroy_tap` also raises, both are logged; no re-raise — primary exception from the workload always wins (mirrors S3-03 AC-REVERT-3..-4).
- [ ] **AC-TEARDOWN-4 — `_TeardownState`** is a separate `@dataclass` class (NOT a method on `NetNamespaceConfig`) so the config dataclass can stay `frozen=True`. `_TeardownState(torn_down: bool, table_name: str | None, tap_name: str | None, runner: Callable)`. Stored as `NetNamespaceConfig._teardown_state` (mutable companion).
- [ ] **AC-ROLLBACK-1 — Partial-apply rollback grid (5 cells):** `apply_policy` failure at step k ∈ {dns_resolve, tap_create, addr_add, nft_apply, link_up} → roll back steps k-1..1 in reverse order BEFORE re-raising. Parametrized test:
  - `fail_at=dns_resolve` → 0 rollback steps; raise `FirecrackerNetworkPolicyError(reason="...dns_resolution_failed")`.
  - `fail_at=tap_create` → 0 rollback steps; raise `reason="...tap_create_failed"`.
  - `fail_at=addr_add` → `_destroy_tap` runs; raise `reason="...tap_create_failed"` (addr-add inside `_create_tap`).
  - `fail_at=nft_apply` → `_destroy_tap` runs; raise `reason="...nftables_apply_failed"`.
  - `fail_at=link_up` → `_revert_nft` + `_destroy_tap` run; raise `reason="...nftables_apply_failed"` (link-up classified under apply boundary).

### §K. Errors + closed-Literal `reason`

- [ ] **AC-ERR-1 — `SandboxBackendError.reason` widened additively by 7 members** (in `sandbox/errors.py`): `"sandbox.firecracker.network_policy.dns_resolution_failed"`, `"sandbox.firecracker.network_policy.nftables_apply_failed"`, `"sandbox.firecracker.network_policy.nftables_teardown_failed"`, `"sandbox.firecracker.network_policy.tap_create_failed"`, `"sandbox.firecracker.network_policy.tap_destroy_failed"`, `"sandbox.firecracker.network_policy.ip_literal_invalid"`, `"sandbox.firecracker.network_policy.nftables_missing"`. `typing.get_args(SandboxBackendError.__init__.__annotations__["reason"])` returns the cumulative union byte-exactly (S1-01 base + S3-03 widening + S6-01 widening + this story's 7 members).
- [ ] **AC-ERR-2 — `FirecrackerNetworkPolicyError(SandboxBackendError)` subclass:** `reason: Literal["sandbox.firecracker.network_policy.dns_resolution_failed", "sandbox.firecracker.network_policy.nftables_apply_failed", "sandbox.firecracker.network_policy.nftables_teardown_failed", "sandbox.firecracker.network_policy.tap_create_failed", "sandbox.firecracker.network_policy.tap_destroy_failed", "sandbox.firecracker.network_policy.ip_literal_invalid", "sandbox.firecracker.network_policy.nftables_missing"]`. `isinstance(exc, SandboxBackendError) is True`.
- [ ] **AC-ERR-3 — `details: Mapping[str, object]`** carries at minimum: `{"reason": ..., "stderr_truncated": bytes_truncated_to_4096_utf8_safe, "argv": tuple[str, ...]}`. Tested across all 7 reason values.
- [ ] **AC-ERR-4 — `_NetworkPolicyReason`** module-level `Final[frozenset[str]]` enumerates the 7 reason strings; imported into the `FirecrackerNetworkPolicyError` class definition via `Literal[*sorted(_NetworkPolicyReason)]` — single source of truth.
- [ ] **AC-ERR-5 — `nft` binary missing → `FileNotFoundError` from `runner`** → wrapped to `FirecrackerNetworkPolicyError(reason="sandbox.firecracker.network_policy.nftables_missing")`. Test injects a `runner` that raises `FileNotFoundError("nft: not found")`; asserts the wrap.

### §L. Events (STARTED/COMPLETED/FAILED + APPLIED/REVERTED/APPLY_FAILED triples)

- [ ] **AC-EVT-1 — Six new event constants appended to `sandbox/logging.py`'s sorted `__all__`:**
  - `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLIED = "sandbox.firecracker.network_policy.applied"`
  - `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_REVERTED = "sandbox.firecracker.network_policy.reverted"`
  - `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLY_FAILED = "sandbox.firecracker.network_policy.apply_failed"`
  - `EVENT_SANDBOX_FIRECRACKER_TAP_CREATED = "sandbox.firecracker.tap.created"`
  - `EVENT_SANDBOX_FIRECRACKER_TAP_DESTROYED = "sandbox.firecracker.tap.destroyed"`
  - `EVENT_SANDBOX_FIRECRACKER_TAP_ORPHAN = "sandbox.firecracker.tap.orphan"` (consumed by S8-01 `sandbox gc`)
- [ ] **AC-EVT-2 — Zero bare-string event names** in `network_policy.py`; AST walker asserts every `structlog`-call event arg is a `Name` referencing one of the six constants imported from `sandbox.logging`.
- [ ] **AC-EVT-3 — `structlog.testing.capture_logs()`** used in `test_network_policy_core.py` to assert each event fires with structured fields (`run_id`, `tap_name`, `allowlist_size`, `resolved_v4_count`, `resolved_v6_count`, `applied_at`, etc.).

### §M. IP-literal handling

- [ ] **AC-IP-LIT-1 — IP-literal entries in `egress_allowlist` skip DNS resolution.** `_partition_ip_literals` separates them; only `hostnames_to_resolve` go through `_resolve_egress_allowlist`.
- [ ] **AC-IP-LIT-2 — Mixed allowlist works:** `["registry.npmjs.org", "192.0.2.5", "2001:db8::1"]` → 1 hostname resolved + 1 v4 literal + 1 v6 literal → all three appear in the rendered ruleset.
- [ ] **AC-IP-LIT-3 — Invalid IP literals raise BEFORE any subprocess call.** Allowlist `["192.0.2.5", "not-a-valid-host-ip"]` (where `not-a-valid-host-ip` is not a valid hostname per `socket.gethostbyname_ex` either) → wait, `_validate_ip_literal` returns `"invalid"` for an obvious-non-IP; the helper still tries DNS resolution. **Pure-IP-literal-invalid** test case: `["192.0.2.999"]` → `_validate_ip_literal` returns "invalid" (out-of-range octet); since input looks IP-shaped, treat as IP-literal-invalid → raise `FirecrackerNetworkPolicyError(reason="...ip_literal_invalid", details={"input": "192.0.2.999"})` BEFORE any subprocess call. (Genuine hostnames that happen to be unresolvable go down the `dns_resolution_failed` path per AC-DNS-3.)

### §N. Subnet allocation

- [ ] **AC-SUBNET-1 — `_subnet_for(run_id)`** derives a `/30` from `blake3(run_id.encode())[:4]` masked to `10.x.x.0/30`; returns `(host_ip=.1, guest_ip=.2, netmask="255.255.255.252")`. The `/30` is unique-per-run with ~2^30 search space.
- [ ] **AC-SUBNET-2 — Hypothesis property:** across 1000 generated `RunId`s, ≤ 1 collision (0.1% rate). On a collision, the implementation re-derives with a 1-byte salt; documented in module docstring. Test asserts the property + that the re-derive logic is exercised at least once across the 1000 samples.

### §O. Subprocess discipline

- [ ] **AC-SUBPROCESS-1 — Module-level `_DEFAULT_RUN_KWARGS: Final[Mapping[str, object]] = MappingProxyType({"check": True, "capture_output": True, "text": False, "timeout": _DEFAULT_NFT_TIMEOUT_SECONDS, "stdin": subprocess.DEVNULL, "start_new_session": True, "env": _MINIMAL_NFT_ENV})`.** `_MINIMAL_NFT_ENV: Final[Mapping[str, str]] = MappingProxyType({"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C", "LC_ALL": "C"})` (no inherited env). `_DEFAULT_NFT_TIMEOUT_SECONDS: Final[int] = 10`.
- [ ] **AC-SUBPROCESS-2 — `nft -f -` invocation overrides `stdin` to `subprocess.PIPE`** + supplies `input=ruleset.encode("utf-8")` keyword; all other kwargs from `_DEFAULT_RUN_KWARGS`.
- [ ] **AC-SUBPROCESS-3 — Golden argv snapshots:** `tests/golden/network_policy_argv_*.txt` for each of the 6 subprocess invocations (`nft -f -`, `nft delete table inet ...`, `ip tuntap add`, `ip link set up`, `ip addr add`, `ip tuntap del`). Tests assert `RunnerSpy.calls[n].argv == tuple(golden.read_text().splitlines())`.
- [ ] **AC-SUBPROCESS-4 — `subprocess.TimeoutExpired`** → wrapped to `FirecrackerNetworkPolicyError(reason="sandbox.firecracker.network_policy.nftables_apply_failed", details={..., "timeout_seconds": _DEFAULT_NFT_TIMEOUT_SECONDS})`.
- [ ] **AC-SUBPROCESS-5 — `subprocess.CalledProcessError`** → wrapped to `FirecrackerNetworkPolicyError` with the appropriate `reason` based on argv shape (`_wrap_subprocess_error` adapter).
- [ ] **AC-SUBPROCESS-6 — Stderr truncated to 4096 bytes** via UTF-8-safe slicing (`stderr[:4096].decode("utf-8", errors="replace")`); test asserts 8 KiB stderr is truncated to exactly 4 KiB of decoded characters.
- [ ] **AC-SUBPROCESS-7 — No `shell=True`, no `os.system`, no `os.popen`** anywhere in `network_policy.py`; AST walker (AC-PURE-5) asserts (belt-and-suspenders on the repo-wide `forbidden-patterns` pre-commit hook).

### §P. FirecrackerClient (S6-01) coordinated EDITs

- [ ] **AC-CLIENT-EDIT-1 — `health()` precondition table widened by one row.** S6-01 AC-H1's 4-row table → 5 rows. New row: `("nft_binary_present", "nft --version exits zero", "sandbox.firecracker.network_policy.nftables_missing")`. Test in `tests/sandbox/firecracker/test_client_core.py` is parametrized over the 5 rows (was 4); S6-01-era goldens NOT regenerated for the existing 4 rows.
- [ ] **AC-CLIENT-EDIT-2 — `execute()` wires `apply_policy` + finally-teardown.** S6-01 AC-C4 happy-path step (e) "configures the VM via `api_socket_factory` PUTs (`/machine-config`, `/boot-source`, `/drives/rootfs`, `/drives/work`, `/actions InstanceStart`)" is amended additively: BEFORE `InstanceStart`, call `cfg = apply_policy(spec, run_id=run_id, runner=self._runner, resolver=self._resolver, clock=self._clock)`; pass `cfg` into the `/network-interfaces` API call when `cfg.tap_name is not None`; in the outer `finally:`, call `cfg.teardown()` unconditionally (also wrapped in try/except so teardown failure does NOT mask primary exception). S6-01's AC-I1/I2 (teardown idempotency) inherits.
- [ ] **AC-CLIENT-EDIT-3 — `boot_args` widened per AC-BOOT-ARGS-1.** S6-01 AC-D9's `boot_args` constant is now suffixed with the canonical 7-field `ip=...` segment **only when `cfg.tap_name is not None`**; when `cfg.tap_name is None` (network="none"), no `ip=` segment is added.
- [ ] **AC-HEALTH-1 — `SandboxHealth.reasons`** can include `"sandbox.firecracker.network_policy.nftables_missing"` (the new reason ID from AC-ERR-1). Asserted by a `health()` test that injects a runner raising `FileNotFoundError("nft: not found")` for `nft --version`.
- [ ] **AC-HEALTH-2 — `health()` confidence on `nft` missing:** `confidence="low"` (mirrors the other 4 precondition-failure rows from S6-01).
- [ ] **AC-HEALTH-3 — `nft --version` check is the precondition.** Argv exact: `("nft", "--version")`. Golden-snapshotted.
- [ ] **AC-BOOT-ARGS-1 — Canonical 7-field `ip=` segment:** `f"ip={guest_ip}::{host_ip}:{netmask}::eth0:off"` (gw-ip empty + hostname empty per Linux kernel `Documentation/admin-guide/nfs/nfsroot.rst`). Test golden-snapshots the resulting full boot_args string for the canonical run_id.

### §Q. Fence + module-purity

- [ ] **AC-FENCE-1 — Subprocess fence allowlist is unchanged.** S1-07 HARDENED `_SUBPROCESS_ALLOWLIST` already includes `Path("src/codegenie/sandbox/firecracker/network_policy.py")` post-ADR-0009 (S1-07 AC-SP-1). This story consumes the reserved slot; does NOT widen S1-07's allowlist; does NOT regenerate `tests/schema/test_no_subprocess_outside_build_chokepoint.py`.
- [ ] **AC-PURE-1 — Module top-of-file:** `from __future__ import annotations` is the first non-comment line; sorted `__all__: Final = ("NetNamespaceConfig", "apply_policy")`; module docstring cites ADR-0001 + ADR-0004 + ADR-0009 by filename.
- [ ] **AC-PURE-2 — Module-purity AST walker:** `tests/sandbox/firecracker/test_network_policy_purity.py` asserts:
  - `subprocess` and `socket` are the only stdlib I/O modules importable here.
  - No `urllib`, no `requests`, no `httpx`, no `os.system`, no `os.popen`.
  - `_default_runner` is the only function whose body contains `subprocess.run` (AST walk over function defs).
  - `_default_resolver` is the only function whose body contains `socket.getaddrinfo`.
  - `_default_clock` is the only function whose body contains `datetime.now`.
  - No `subprocess.Popen` calls (`run` only).
  - No `shell=True` anywhere.
- [ ] **AC-PURE-3 — Event-name AST walker:** AC-EVT-2; every `structlog` call's `event` arg is a `Name` referencing one of the six AC-EVT-1 constants imported from `sandbox.logging`.
- [ ] **AC-PURE-4 — Hardcoded-string fence:** the literal `"firecracker"` does NOT appear in the file body outside the module-level `_BACKEND_NAME: Final[str] = "firecracker"` declaration (S6-01 AC-CANONICAL-1 pattern echoed).
- [ ] **AC-PURE-5 — `forbidden-patterns` checked at file level:** AST walk confirms no `shell=True`, no `os.system`, no `os.popen`, no `eval`, no `exec`, no `__import__`, no `pickle.loads` (mirrors S3-03 AC-PURE-7).
- [ ] **AC-PURE-6 — `_BACKEND_NAME: Final[str] = "firecracker"` constant** at module top; used by every event-payload + every error-detail field that needs the backend name. Single source of truth.
- [ ] **AC-PURE-7 — Sorted-`__all__` check** asserted via `assert sorted(__all__) == list(__all__)` at import time (`raise AssertionError(...)` per CLAUDE.md `forbidden-patterns` no-bare-assert rule).
- [ ] **AC-PURE-8 — Module docstring includes the per-`execute()` re-resolution policy** + the 50–100 ms overhead from ADR-0009 + the host-as-trusted-boundary invariant. Asserted by reading the docstring + grep for the canonical phrases.
- [ ] **AC-CANONICAL-1 — `_BACKEND_NAME: Final[str] = "firecracker"`** (AC-PURE-6 echo with separate AC number for traceability into the S6-01 family).
- [ ] **AC-CANONICAL-2 — `RunId` NewType honored at TAP-name + table-name derivation site.** `_tap_name_for(run_id: RunId)` + `_table_name_for(run_id: RunId)` + `_subnet_for(run_id: RunId)` all type-hint `RunId` (not `str`); `typing.get_type_hints` asserts.

### §R. Integration test + Coverage + Spec invariants + Deps

- [ ] **AC-INTEG-1 — `tests/integration/sandbox/test_firecracker_network_policy.py`** created with module docstring naming S6-05 as the populator. Decorated `@pytest.mark.skip_if_no_kvm`. **NO internal `pytest.skip(...)` call** — S6-05 lands real assertions by editing the test body, not by removing a skip. File contains one placeholder test `test_scoped_egress_allowed_blocked_in_real_guest(tmp_path)` with body `assert True  # populated by S6-05`.
- [ ] **AC-COV-1 — Branch coverage on `src/codegenie/sandbox/firecracker/network_policy.py` ≥ 90%.**
- [ ] **AC-COV-2 — Line coverage on `src/codegenie/sandbox/firecracker/network_policy.py` ≥ 95%.**
- [ ] **AC-FIX-1 — TDD fixtures use `_valid_spec_kwargs`** imported from `tests/sandbox/test_contract_models.py` (the S1-02 precedent). Every required `SandboxSpec` field (13 of them) supplied. No phantom `logs_dir` / `copy_out_root` (those live on `SandboxRun`).
- [ ] **AC-FIX-2 — `pytest --collect-only` succeeds** on the new test files (no ValidationError at construction time).
- [ ] **AC-FIX-3 — S1-02 `_check_network_implies_no_allowlist` model_validator** is exercised in a fixture-construction test: `SandboxSpec(..., network="none", egress_allowlist=["x"])` raises `ValidationError` BEFORE `apply_policy` is reached.
- [ ] **AC-INVALID-SPEC-1 — `apply_policy(spec_with_network_none_and_nonempty_allowlist)` is unreachable** because the model_validator fires at `SandboxSpec.__init__`. No defensive AC needed inside `apply_policy`; documented in module docstring.
- [ ] **AC-DEP-1 — `pyproject.toml` no-change confirmation.** Stdlib `subprocess`, `socket`, `ipaddress`, `dataclasses`, `datetime` only. `blake3` already in the closure. CI fence (`make fence`) remains green.
- [ ] **TDD plan's red tests exist, are committed, and are green.**
- [ ] **`ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/firecracker`, `pytest tests/sandbox/firecracker/`** all pass.

## Implementation outline

1. **Widen `SandboxBackendError.reason` Literal in `src/codegenie/sandbox/errors.py`** by 7 additive members per AC-ERR-1 (existing N members unchanged). Add `FirecrackerNetworkPolicyError(SandboxBackendError)` subclass with narrower Literal type per AC-ERR-2. Add module-level `_NetworkPolicyReason: Final[frozenset[str]]` enumerating the 7 reason strings (AC-ERR-4).
2. **Append six event constants to `src/codegenie/sandbox/logging.py`** alphabetized into the sorted `__all__` per AC-EVT-1. Do NOT remove or rename existing constants (append-only canonical table).
3. **Create `src/codegenie/sandbox/firecracker/network_policy.py`** with this structure:
   - Module docstring (AC-PURE-8) — cites ADR-0001, ADR-0004, ADR-0009; documents per-`execute()` re-resolution policy, ~50–100 ms cost, host-as-trusted-boundary invariant.
   - `from __future__ import annotations` first.
   - Imports: `subprocess`, `socket`, `ipaddress`, `blake3`, `datetime`, `dataclasses`, `typing.{Final, Literal, Callable}`, `types.MappingProxyType`, the 6 event constants, `FirecrackerNetworkPolicyError`, `SandboxSpec`, `RunId`.
   - Module-level constants: `_BACKEND_NAME`, `_NetworkPolicyReason`, `_DEFAULT_NFT_TIMEOUT_SECONDS`, `_DEFAULT_RUN_KWARGS`, `_MINIMAL_NFT_ENV`, `_RULESET_TEMPLATE` (the nftables script template — pure string with placeholders), `_CANONICAL_TABLE_NAME` (test-fixture-only).
   - `@dataclass(frozen=True, slots=True) class NetNamespaceConfig`: `tap_name, guest_ip, host_ip, netmask, nftables_table, _teardown_state`.
   - `@dataclass class _TeardownState`: `torn_down, table_name, tap_name, runner` (mutable companion).
   - Pure helpers (AC-FCS-1..-7): `_render_ruleset`, `_tap_name_for`, `_table_name_for`, `_subnet_for`, `_partition_ip_literals`, `_validate_ip_literal`, `_wrap_subprocess_error`. Plus `_truncate_stderr`.
   - DI defaults (AC-DI-1..-3): `_default_runner`, `_default_resolver`, `_default_clock`.
   - Impure shells (AC-LIFECYCLE-1..-4): `_resolve_egress_allowlist`, `_create_tap`, `_apply_nft`, `_link_up`, `_destroy_tap`, `_revert_nft`.
   - Top-level `apply_policy(spec, *, run_id, runner=..., resolver=..., clock=...) -> NetNamespaceConfig` per AC-API-2 + AC-SCOPED-1, with the partial-apply rollback handler per AC-ROLLBACK-1.
   - Sorted `__all__` final declaration; AssertionError-guarded sort check (AC-PURE-7).
4. **Edit `src/codegenie/sandbox/firecracker/client.py` (S6-01) additively** per AC-CLIENT-EDIT-1..-3:
   - `health()` precondition table grows by one row (`nft_binary_present`).
   - `execute()` body wires `cfg = apply_policy(spec, run_id=run_id, ...)` BEFORE `InstanceStart` per AC-RACE-3; `/network-interfaces` API call added when `cfg.tap_name is not None`; `cfg.teardown()` called in `finally:` (wrapped — teardown failure does NOT mask primary exception); `boot_args` widened per AC-BOOT-ARGS-1.
5. **Generate goldens** under `tests/golden/`:
   - `nftables_rules_scoped_empty.txt`
   - `nftables_rules_scoped_npmjs.txt`
   - `nftables_rules_scoped_mixed.txt`
   - `network_policy_argv_nft_apply.txt`, `..._nft_revert.txt`, `..._tap_add.txt`, `..._tap_del.txt`, `..._link_up.txt`, `..._addr_add.txt`
   - `firecracker_boot_args_scoped.txt`
   - Each via `python -m tests.golden.regenerate_nftables` (committed regenerator under `tests/golden/regenerate_nftables.py`).
6. **Create the six test files** per the TDD plan section below.
7. **Run `make check`** until green: `ruff` + `mypy --strict` + the new tests + coverage floor.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Six test files (mirrors S6-01's five-file pattern):

- `tests/sandbox/firecracker/test_network_policy_core.py` — `apply_policy` end-to-end with `RunnerSpy` + `ResolverSpy` DI; happy paths for `network="none"` and `network="scoped"`; argv assertions via golden snapshots.
- `tests/sandbox/firecracker/test_render_ruleset.py` — pure `_render_ruleset` against the 3 golden fixtures + hypothesis property (AC-RENDER-3) + determinism property (AC-RENDER-4).
- `tests/sandbox/firecracker/test_network_policy_lifecycle.py` — TAP create/destroy, nft apply/revert, idempotency (AC-TEARDOWN-2), per-step failure isolation (AC-TEARDOWN-3), 5-cell partial-apply rollback grid (AC-ROLLBACK-1), TAP-up-AFTER-nft-load race (AC-RACE-1..-2).
- `tests/sandbox/firecracker/test_network_policy_errors.py` — closed-Literal `reason` set (AC-ERR-1); 7 reason values exercised; DNS-failure distinct from rule-load (AC-DNS-3..-4); IP-literal-invalid path (AC-IP-LIT-3); `nft` missing → `nftables_missing` (AC-ERR-5).
- `tests/sandbox/firecracker/test_network_policy_purity.py` — module-purity AST walker (AC-PURE-2..-7); sorted-`__all__`; `_BACKEND_NAME` single source of truth; six event constants in canonical-table.
- `tests/integration/sandbox/test_firecracker_network_policy.py` — KVM-only placeholder (AC-INTEG-1); S6-05 populates real `curl npmjs ok / curl github fails` assertions.

Plus S6-01 amendments (EDITs, not new files):

- `tests/sandbox/firecracker/test_client_core.py` — parametrized over the **5-row** health precondition table (was 4); `execute()` happy-path widened over `[network="none", network="scoped"]` (S6-01 golden frozen-SandboxRun fixtures NOT regenerated).
- `tests/sandbox/firecracker/test_client_health.py` — new row (`nft_binary_present`) exercised.

```python
# tests/sandbox/firecracker/test_network_policy_core.py — happy path
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

from codegenie.sandbox.contract import RunId, SandboxSpec
from codegenie.sandbox.errors import FirecrackerNetworkPolicyError
from codegenie.sandbox.firecracker import network_policy as np
from codegenie.sandbox.firecracker.network_policy import NetNamespaceConfig

from tests.sandbox._valid_spec import _valid_spec_kwargs  # S1-02 precedent
from tests.sandbox.firecracker._runner_spy import RunnerSpy, ResolverSpy


_FIXED_RUN_ID: Final[RunId] = RunId("0190abcd" + "ef" * 12)  # 32 hex chars, fixture-stable


def _spec(network: str, allowlist: list[str]) -> SandboxSpec:
    return SandboxSpec(**_valid_spec_kwargs(network=network, egress_allowlist=allowlist))


def test_network_none_makes_zero_subprocess_calls() -> None:
    """AC-NONE-1: spec.network=='none' → no runner calls."""
    spec = _spec("none", [])
    runner = RunnerSpy()
    resolver = ResolverSpy()
    cfg = np.apply_policy(spec, run_id=_FIXED_RUN_ID, runner=runner, resolver=resolver,
                          clock=lambda: datetime(2026, 5, 25, tzinfo=timezone.utc))
    assert cfg.tap_name is None
    assert cfg.nftables_table is None
    assert runner.calls == ()
    assert resolver.calls == ()


def test_network_none_teardown_is_noop() -> None:
    """AC-NONE-2: cfg.teardown() does not call runner for network='none'."""
    spec = _spec("none", [])
    runner = RunnerSpy()
    cfg = np.apply_policy(spec, run_id=_FIXED_RUN_ID, runner=runner, resolver=ResolverSpy(),
                          clock=lambda: datetime(2026, 5, 25, tzinfo=timezone.utc))
    cfg.teardown()
    cfg.teardown()  # idempotent
    assert runner.calls == ()


def test_network_scoped_calls_runner_in_expected_order_with_golden_argv() -> None:
    """AC-SCOPED-1 + AC-RACE-1 + AC-SUBPROCESS-3: TAP add → addr add → nft apply → link up."""
    spec = _spec("scoped", ["registry.npmjs.org"])
    runner = RunnerSpy()
    resolver = ResolverSpy(returns={"registry.npmjs.org": [("104.16.16.35", "v4"),
                                                            ("2606:4700::6810:1023", "v6")]})
    cfg = np.apply_policy(spec, run_id=_FIXED_RUN_ID, runner=runner, resolver=resolver,
                          clock=lambda: datetime(2026, 5, 25, tzinfo=timezone.utc))
    assert cfg.tap_name == f"cgsbx-{_FIXED_RUN_ID[:8]}"
    argv_calls = tuple(c.argv for c in runner.calls)
    expected = (
        ("ip", "tuntap", "add", "dev", f"cgsbx-{_FIXED_RUN_ID[:8]}", "mode", "tap"),
        ("ip", "addr", "add", f"{cfg.host_ip}/30", "dev", f"cgsbx-{_FIXED_RUN_ID[:8]}"),
        ("nft", "-f", "-"),
        ("ip", "link", "set", f"cgsbx-{_FIXED_RUN_ID[:8]}", "up"),
    )
    assert argv_calls == expected, "TAP-up MUST happen AFTER nft-load"


def test_apply_policy_emits_applied_event_with_structured_fields() -> None:
    """AC-EVT-3 + AC-SCOPED-1: capture_logs() validates structured fields."""
    spec = _spec("scoped", ["registry.npmjs.org"])
    runner = RunnerSpy()
    resolver = ResolverSpy(returns={"registry.npmjs.org": [("104.16.16.35", "v4")]})
    with capture_logs() as cap:
        np.apply_policy(spec, run_id=_FIXED_RUN_ID, runner=runner, resolver=resolver,
                        clock=lambda: datetime(2026, 5, 25, tzinfo=timezone.utc))
    applied = [e for e in cap if e["event"] == "sandbox.firecracker.network_policy.applied"]
    assert len(applied) == 1
    assert applied[0]["allowlist_size"] == 1
    assert applied[0]["resolved_v4_count"] == 1
    assert applied[0]["resolved_v6_count"] == 0


# tests/sandbox/firecracker/test_render_ruleset.py — pure helper goldens + property

import hypothesis.strategies as st
from hypothesis import given

from codegenie.sandbox.firecracker.network_policy import _render_ruleset

_GOLDEN_DIR = Path("tests/golden")


@pytest.mark.parametrize("fixture", ["empty", "npmjs", "mixed"])
def test_render_ruleset_matches_golden(fixture: str) -> None:
    """AC-RENDER-1 + AC-RENDER-3..-5: three golden fixtures."""
    inputs = {
        "empty": {"allowed_v4": (), "allowed_v6": ()},
        "npmjs": {"allowed_v4": ("104.16.16.35",), "allowed_v6": ("2606:4700::6810:1023",)},
        "mixed": {"allowed_v4": ("104.16.16.35", "192.0.2.5"),
                  "allowed_v6": ("2606:4700::6810:1023", "2001:db8::1")},
    }[fixture]
    actual = _render_ruleset(table_name="cgsbx_test_fixture_00", **inputs)
    golden = (_GOLDEN_DIR / f"nftables_rules_scoped_{fixture}.txt").read_text()
    assert actual == golden


@given(
    st.lists(st.ip_addresses(v=4).map(str), max_size=4, unique=True),
    st.lists(st.ip_addresses(v=6).map(str), max_size=4, unique=True),
)
def test_render_ruleset_property_invariants(v4: list[str], v6: list[str]) -> None:
    """AC-RENDER-3: invariants across all v4/v6 input shapes."""
    out = _render_ruleset(table_name="cgsbx_property_test", allowed_v4=tuple(v4), allowed_v6=tuple(v6))
    assert "table inet cgsbx_property_test {" in out
    assert out.count("policy drop") == 1
    assert out.count("ct state established,related accept") == 1
    for addr in v4:
        assert out.count(f"ip daddr {addr} accept") == 1
    for addr in v6:
        assert out.count(f"ip6 daddr {addr} accept") == 1
    # v4 rules precede v6 rules (deterministic diff-ability)
    if v4 and v6:
        v4_pos = min(out.index(f"ip daddr {a}") for a in v4)
        v6_pos = min(out.index(f"ip6 daddr {a}") for a in v6)
        assert v4_pos < v6_pos


# tests/sandbox/firecracker/test_network_policy_lifecycle.py — rollback grid (AC-ROLLBACK-1)

@pytest.mark.parametrize(
    "fail_at, expected_rollback_argv, expected_reason",
    [
        ("dns_resolve",
         (),
         "sandbox.firecracker.network_policy.dns_resolution_failed"),
        ("tap_create",
         (),
         "sandbox.firecracker.network_policy.tap_create_failed"),
        ("addr_add",
         (("ip", "tuntap", "del", "dev", f"cgsbx-{_FIXED_RUN_ID[:8]}", "mode", "tap"),),
         "sandbox.firecracker.network_policy.tap_create_failed"),
        ("nft_apply",
         (("ip", "link", "set", f"cgsbx-{_FIXED_RUN_ID[:8]}", "down"),
          ("ip", "tuntap", "del", "dev", f"cgsbx-{_FIXED_RUN_ID[:8]}", "mode", "tap")),
         "sandbox.firecracker.network_policy.nftables_apply_failed"),
        ("link_up",
         (("nft", "delete", "table", "inet", f"cgsbx_{_FIXED_RUN_ID[:12]}"),
          ("ip", "link", "set", f"cgsbx-{_FIXED_RUN_ID[:8]}", "down"),
          ("ip", "tuntap", "del", "dev", f"cgsbx-{_FIXED_RUN_ID[:8]}", "mode", "tap")),
         "sandbox.firecracker.network_policy.nftables_apply_failed"),
    ],
)
def test_partial_apply_rollback_grid(fail_at: str, expected_rollback_argv: tuple,
                                     expected_reason: str) -> None:
    """AC-ROLLBACK-1: 5-cell parametrized rollback grid."""
    # Wire failure injection per fail_at; assert rollback argv tuples in reverse order
    # before re-raise; assert FirecrackerNetworkPolicyError.reason == expected_reason.
    ...


# tests/sandbox/firecracker/test_network_policy_errors.py — closed-Literal reason set

def test_reason_literal_is_byte_exact_after_widening() -> None:
    """AC-ERR-1: typing.get_args returns cumulative union byte-exactly."""
    from codegenie.sandbox.errors import SandboxBackendError
    import typing
    reasons = typing.get_args(SandboxBackendError.__init__.__annotations__["reason"])
    # Cumulative: S1-01 base + S3-03 widening + S6-01 widening + S6-02 widening
    expected_s6_02_subset = {
        "sandbox.firecracker.network_policy.dns_resolution_failed",
        "sandbox.firecracker.network_policy.nftables_apply_failed",
        "sandbox.firecracker.network_policy.nftables_teardown_failed",
        "sandbox.firecracker.network_policy.tap_create_failed",
        "sandbox.firecracker.network_policy.tap_destroy_failed",
        "sandbox.firecracker.network_policy.ip_literal_invalid",
        "sandbox.firecracker.network_policy.nftables_missing",
    }
    assert expected_s6_02_subset.issubset(set(reasons))


def test_nft_binary_missing_wraps_to_nftables_missing() -> None:
    """AC-ERR-5: FileNotFoundError from runner → reason='...nftables_missing'."""
    spec = _spec("scoped", ["registry.npmjs.org"])
    runner = RunnerSpy(side_effect=[FileNotFoundError("nft: not found")])
    with pytest.raises(FirecrackerNetworkPolicyError) as exc:
        np.apply_policy(spec, run_id=_FIXED_RUN_ID, runner=runner,
                        resolver=ResolverSpy(returns={"registry.npmjs.org": [("1.2.3.4", "v4")]}),
                        clock=lambda: datetime(2026, 5, 25, tzinfo=timezone.utc))
    assert exc.value.reason == "sandbox.firecracker.network_policy.nftables_missing"


# tests/sandbox/firecracker/test_network_policy_purity.py — AC-PURE-2

def test_only_default_runner_calls_subprocess_run() -> None:
    """AC-PURE-2: AST walk asserts _default_runner is the sole caller of subprocess.run."""
    ...  # AST walker enumerates every function def; checks subprocess.run only inside _default_runner
```

### Green — make it pass

Minimal: ship the module per the Implementation outline. Branch on `spec.network`; `none` short-circuits with a no-op `NetNamespaceConfig`. `scoped` runs the 4-step ordered sequence per AC-SCOPED-1 + AC-RACE-1; on raise at step k roll back steps k-1..1 in reverse order per AC-ROLLBACK-1. `teardown()` checks `_teardown_state.torn_down`, calls `_revert_nft` + `_destroy_tap`, then sets `_teardown_state.torn_down = True`.

### Refactor — clean up

- Hoist `_RULESET_TEMPLATE` to module level as a triple-quoted constant (AC-RENDER-4 determinism falls out for free — pure string interpolation).
- Pull TAP-name + table-name + subnet derivation into the three pure helpers (`_tap_name_for`, `_table_name_for`, `_subnet_for`) so each is independently unit-testable.
- Single `_default_runner` is the sole `subprocess.run` callsite — AST walker enforces.
- Single `_default_resolver` is the sole `socket.getaddrinfo` callsite.
- All error messages include both the failing command (argv, no secrets) and stderr first 4096 bytes (UTF-8-safe slicing per AC-SUBPROCESS-6).
- Docstrings on every public + every impure helper cite the AC numbers they implement (S3-03 precedent).

## Files to touch

| Path | Action | Why |
|---|---|---|
| `src/codegenie/sandbox/firecracker/network_policy.py` | NEW | `apply_policy`, `NetNamespaceConfig`, render+resolve+lifecycle helpers, DI defaults — full surface per AC-API-* / AC-FCS-* / AC-LIFECYCLE-* / AC-DI-*. |
| `src/codegenie/sandbox/firecracker/client.py` | EDIT | S6-01 surface widened additively per AC-CLIENT-EDIT-1..-3: `health()` precondition row, `execute()` apply+finally-teardown wiring, `/network-interfaces` API, `boot_args` `ip=` segment. |
| `src/codegenie/sandbox/errors.py` | EDIT | Widen `SandboxBackendError.reason` Literal additively by 7 members; add `FirecrackerNetworkPolicyError(SandboxBackendError)` subclass (AC-ERR-1..-2 + AC-ERR-4). |
| `src/codegenie/sandbox/logging.py` | EDIT | Append six event constants alphabetized into sorted `__all__` (AC-EVT-1). Append-only — no rename of existing constants. |
| `tests/sandbox/firecracker/test_network_policy_core.py` | NEW | End-to-end apply paths + event-capture + argv-call-order. |
| `tests/sandbox/firecracker/test_render_ruleset.py` | NEW | Pure-helper unit + 3 golden fixtures + hypothesis property + determinism property. |
| `tests/sandbox/firecracker/test_network_policy_lifecycle.py` | NEW | TAP create/destroy + nft apply/revert + idempotency + 5-cell rollback grid + race ordering. |
| `tests/sandbox/firecracker/test_network_policy_errors.py` | NEW | Closed-Literal reason set + DNS failure + IP-literal-invalid + nftables_missing. |
| `tests/sandbox/firecracker/test_network_policy_purity.py` | NEW | Module-purity AST walker (AC-PURE-*). |
| `tests/sandbox/firecracker/test_client_health.py` | EDIT | S6-01 health table widened from 4 rows to 5 rows (`nft_binary_present`). |
| `tests/sandbox/firecracker/test_client_core.py` | EDIT | S6-01 happy-path test sweep parametrized over `[network="none", network="scoped"]`. |
| `tests/sandbox/firecracker/_runner_spy.py` | NEW | Shared `RunnerSpy` + `ResolverSpy` fixture (mirrors S3-03's pattern). |
| `tests/integration/sandbox/test_firecracker_network_policy.py` | NEW | KVM-only placeholder; S6-05 populates. |
| `tests/golden/nftables_rules_scoped_empty.txt` | NEW | Golden 1 of 3. |
| `tests/golden/nftables_rules_scoped_npmjs.txt` | NEW | Golden 2 of 3. |
| `tests/golden/nftables_rules_scoped_mixed.txt` | NEW | Golden 3 of 3. |
| `tests/golden/network_policy_argv_*.txt` | NEW | 6 argv golden fixtures (`nft -f -`, `nft delete`, `ip tuntap add/del`, `ip link set up/down`, `ip addr add`). |
| `tests/golden/firecracker_boot_args_scoped.txt` | NEW | Canonical 7-field `ip=` boot_args golden. |
| `tests/golden/regenerate_nftables.py` | NEW | Committed regenerator script (runs `_render_ruleset` for the 3 fixtures + dumps argv goldens). |

## Out of scope

- **Real KVM-gated integration assertions** (`curl npmjs ok / curl github fails`) → S6-05.
- **Auto-detect path** that picks Firecracker on Linux/KVM → S6-04 (consumes the `sandbox.firecracker.network_policy.nftables_missing` reason ID this story ships).
- **Rootfs digest enforcement** → S6-03 (consumes the `_default_runner` DI seam this story ships — the digest-enforced runner replaces `_default_runner` cleanly).
- **Operator CLI surface** (`sandbox health` orphan-TAP detection, `sandbox gc` cleanup) → S8-01 (consumes the `EVENT_SANDBOX_FIRECRACKER_TAP_ORPHAN` event constant + `cgsbx-<run_id[:8]>` naming convention this story ships).
- **IPv6-only allowlist mode** (no v4 fallback) — explicit Phase-5 non-goal; both v4 and v6 are emitted but no v6-only mode is exposed in `SandboxSpec`.
- **Cross-run DNS resolution cache** — explicit non-goal per ADR-0009 Tradeoff row 5. Re-resolution per-`execute()` is the design intent; the ~50–100 ms cost is acceptable.
- **`register_network_policy_backend(...)` registry decorator** — Rule 2 second consumer; defer until Phase 7+ third backend reaches rule-of-three. Notes-for-implementer records the precedent.
- **`NetNamespaceConfig.__enter__` / `__exit__` context-manager** — diverges from S3-03 sibling's `apply()` + `revert()` pair; defer for symmetry. Notes-for-implementer records the opportunity.
- **High-rotation-CDN allowlist** (e.g., S3 buckets with dynamic IP pools) — `ipset` with dynamic DNS is the production answer; out of scope. Documented as a known limitation in module docstring.

## Notes for the implementer

- **nftables atomic ruleset replacement is the load-bearing detail.** Pipe the *entire* ruleset to `nft -f -` once via stdin (`subprocess.run(["nft","-f","-"], input=ruleset.encode("utf-8"), ...)`); do NOT split into multiple `nft add rule` calls. Per the upstream wiki + AC-RENDER-2: atomic — entire ruleset rolled back on any syntax error mid-script.
- **DNS resolution on the host is part of the security boundary.** Do NOT resolve hostnames inside the guest; that re-trusts the guest's resolver. Resolve on the host via `_default_resolver` (which uses `socket.getaddrinfo`); emit literal IPs in the ruleset. Per AC-DI-2 + AC-PURE-2, `_default_resolver` is the only DNS entrypoint in the file.
- **Per-`execute()` re-resolution is the design intent.** ADR-0009 Tradeoff row 5 makes this explicit; ~50–100 ms cost is acceptable. Do NOT cache resolution across `apply_policy` invocations.
- **TAP-up must happen AFTER nft-load.** The TAP is a *bridge* between the host kernel and the guest's virtual NIC. If you bring the link up before nftables rules are loaded, packets can traverse the bridge unfiltered for ~5–50 ms. AC-RACE-1 + AC-RACE-2 + AC-LIFECYCLE-1..-4 pin the order: tuntap add (DOWN) → addr add → nft load → link up. Test asserts via `RunnerSpy.calls` ordering.
- **TAP names must be ≤ 15 chars** (Linux IFNAMSIZ minus the trailing NUL). The `cgsbx-` prefix plus 8 hex chars of `run_id` is 14 chars — safe. AC-FCS-2 enforces.
- **nftables table names** allow `[A-Za-z_][A-Za-z0-9_]*` per the upstream grammar; max 32 chars. The `cgsbx_<run_id[:12]>` form is 18 chars. AC-FCS-3 enforces. **Note the underscore** (`cgsbx_`) vs TAP's dash (`cgsbx-`): nft tables reject `-` in names.
- **Subnet allocation per-run** uses `blake3(run_id.encode())[:4]` masked to `10.x.x.0/30`. Collision probability across 2^30 search space is negligible at expected concurrent-run counts (Phase 5 caps ≤ 8 concurrent gates). On collision, re-derive with a 1-byte salt (acceptable up to 0.1% retry rate). AC-SUBNET-1..-2.
- **The `EVENT_SANDBOX_FIRECRACKER_TAP_ORPHAN` constant is a forward-compat hook** for S8-01's `sandbox gc` subcommand. Emit it with the orphan TAP name(s) so the CLI can act on it. Do NOT consume the event yourself in this story.
- **Be defensive against `egress_allowlist` containing IP literals.** `_partition_ip_literals` separates literals from hostnames; literals skip resolution. AC-IP-LIT-1..-3 enforce. Mixed allowlists work. Invalid IP literals (`192.0.2.999`) raise `FirecrackerNetworkPolicyError(reason="...ip_literal_invalid")` BEFORE any subprocess call.
- **`iptables-nft` compatibility is NOT equivalent to native `nft`.** Require the binary to be `nft` (not `iptables`) on the runner; AC-HEALTH-1..-3 surface mismatch as `sandbox.firecracker.network_policy.nftables_missing` in `FirecrackerClient.health()`.
- **Subprocess fence is already widened by S1-07.** This story consumes the reserved slot for `sandbox/firecracker/network_policy.py`; do NOT edit `tests/schema/test_no_subprocess_outside_build_chokepoint.py`. AC-FENCE-1.
- **`pyproject.toml` does NOT change.** Stdlib only (subprocess, socket, ipaddress, dataclasses, datetime); `blake3` is already in the closure. AC-DEP-1.
- **Closed-Literal `SandboxBackendError.reason` widening is monotone-additive.** Append the 7 new members in `errors.py`; do NOT rename or remove existing members. Phase-13 cost ledger keys on this union; backwards-compat is load-bearing. AC-ERR-1.
- **Event-name canonical-table is append-only.** Six new constants land alphabetized into `sandbox/logging.py`'s sorted `__all__`. Do NOT rename existing constants. AC-EVT-1.
- **Pattern lineage**: this story is the **second concrete consumer of the `network_policy` family** (S3-03 ships the DinD `iptables` sibling). Mirror S3-03's two-helper FCS split (`_resolve_egress_allowlist` impure feeds `_render_ruleset` pure); the DI `runner` + `resolver` pattern from S3-03 is now the **fourth consumer** of the broader Hexagonal port pattern (S3-01 / S3-02 / S3-03 / S6-01 the prior three). Rule-of-three crossed twice — mandatory inheritance.
- **`NetNamespaceConfig` is `@dataclass(frozen=True, slots=True)`** (immutable data) + a separate `_TeardownState` mutable companion that holds the `torn_down` flag. This keeps the frozen-data invariant clean; the state machine is explicit, not hidden. AC-CFG-1..-3.
- **Coordinated S6-01 edits are additive.** Do NOT regenerate S6-01's frozen-SandboxRun goldens. Widen the health precondition table by ONE row (from 4 to 5); widen the `execute()` happy-path test sweep parametrically over `[network="none", network="scoped"]`. AC-CLIENT-EDIT-1..-3.
- **Defer `register_network_policy_backend` registry decorator** to Phase 7+ when the third backend (e.g., gVisor) reaches rule-of-three. S3-03 deferred for the same reason — S6-02 inherits the deferral.
- **Defer `NetNamespaceConfig.__enter__/__exit__` context manager.** Symmetry with S3-03's `apply()` + `revert()` pair (consumed via `try/finally:` in `client.py::execute()`) is more valuable than ergonomics at this point. Phase 7+ third backend may close the rule-of-three on the context-manager surface.
- **Goldens are regenerable.** Ship `tests/golden/regenerate_nftables.py` so the goldens never become hand-edited. `python -m tests.golden.regenerate_nftables` writes deterministic output (`_render_ruleset` is pure; clock-free; AC-RENDER-4 guarantees determinism).
- **`_default_runner` must use `start_new_session=True` to isolate from the parent process group.** Prevents stray SIGINT during build from killing in-flight `nft` calls; AC-SUBPROCESS-1.
- **`stderr` truncation policy is 4 KiB UTF-8-safe.** Use `stderr[:4096].decode("utf-8", errors="replace")` to avoid splitting multi-byte sequences; mirrors S3-03 AC-TRUNC-1. AC-SUBPROCESS-6.
- **`nft delete table` on a missing table** exits non-zero on some `nft` versions, 0 on others. `_revert_nft` catches `CalledProcessError`, logs WARNING via `EVENT_SANDBOX_FIRECRACKER_NETWORK_POLICY_APPLY_FAILED` (with `reason="...nftables_teardown_failed"`), does NOT re-raise. Idempotency falls out. Mirrors S3-03 AC-REVERT-2..-4.
