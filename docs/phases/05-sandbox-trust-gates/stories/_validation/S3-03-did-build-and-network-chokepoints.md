# Validation report: S3-03 — DinD `build.py` + `network_policy.py` subprocess chokepoints

**Validated:** 2026-05-23
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S3-03 ships the two `subprocess` chokepoint files ADR-0001 carves out under `sandbox/did/` — `build.py` (`docker buildx`) and `network_policy.py` (`iptables`) — and is the **third concrete consumer** of two Phase-5 patterns: the Hexagonal DI port (S3-01 → S3-02 → here) and functional-core/imperative-shell split (same lineage). Rule-of-three reached for both; both are elevated from Notes to ACs in this story.

The draft correctly identified the deliverables (subprocess wrappers + golden-tested argv) and traced cleanly to ADR-0001 / ADR-0004, but had **30+ findings across all four critic lenses, including thirteen block-tier** that an executor following the draft literally would have shipped silently broken. The most consequential:

1. **DNS resolution semantic gap** — `iptables -d <hostname>` resolves at rule-add time only; rotating CDN hostnames silently fail. Fix: pre-resolve to IP fan-out in `_resolve_egress_allowlist` impure helper, golden file uses canonical IP.
2. **New exception classes violated the S1-01 HARDENED closed-`reason` Literal discriminator** — fix: subclass `SandboxBackendError`, widen union additively (eleven members).
3. **Event names** (`sandbox.did.build.done`) violated S1-01 HARDENED `STARTED/COMPLETED/FAILED` verb convention — fix: six `EVENT_*` constants appended.
4. **`BuildResult` and `AppliedPolicy`** referenced as load-bearing return types but never defined — fix: frozen Pydantic models (extra="forbid"), per-model field set pinned, ADR-0014 banned-substring walker applies.
5. **S3-02 ACs being widened** (AC-SPEC-DEFER-1/-2, AC-EXEC-4) not enumerated — fix: AC-WIDEN-1..-5 + AC-CLIENT-1..-7 explicitly name every S3-02 AC modified.
6. **Race window** between `container.start()` and policy install — fix: structural change to `entrypoint=("sleep","infinity")` + `exec_run(spec.cmd)` AFTER `apply()` returns.
7. **Container IP resolution path undefined** — fix: pass the `container` SDK object directly into `apply(spec, *, container, ...)`; raise `NetworkPolicyApplyFailed("container_ip_unknown")` if `attrs["NetworkSettings"]["IPAddress"]` is empty.
8. **`revert()` failure semantics undefined** — fix: per-rule isolation; idempotent; never re-raises; primary exception always wins.
9. **Subprocess parameter set unpinned** — fix: shared `_DEFAULT_RUN_KWARGS` (capture_output, text=False, check=False, stdin=DEVNULL, start_new_session=True); single `_default_runner` call site; forbidden-patterns hook fence.
10. **Argv test disjunction was tautological** — fix: byte-exact golden snapshots indexed by fixture (`minimal`, `with_dockerfile`, `with_build_args`, `with_dockerfile_and_build_args`).
11. **`_compute_rules` single-fixture golden** — fix: hypothesis property test (rule_count invariant, DROP-last invariant, container_ip-positional invariant, input-order stability) + three concrete golden fixtures (empty, single, multi).
12. **`test_revert_runs_even_when_workload_raises` mocked the function under test** — fix: mock at the Docker SDK boundary, exercise the real `network_policy.revert` from `execute()`'s finally; 12-cell cleanup grid.
13. **Hexagonal DI port + FCS pattern** elevated from Note to AC under rule-of-three (S3-01 + S3-02 + S3-03).

Resolution: ~70 numbered ACs across 20 structured sections (was ~10 unnumbered checkboxes) plus an **eight-test-file TDD plan** (purity-walker × 2, helpers × 2, core × 2, revert, client-integration). Two Stage-3 research findings consumed inline (netfilter DNS semantics, BuildKit `--progress=plain` stderr format).

## Findings by critic

### Coverage critic

| Severity | Finding | Resolution |
|---|---|---|
| block | DNS resolution semantics: `-d <hostname>` resolves once at add-time, not per-packet — rotating CDN IPs silently fail | AC-DNS-1..AC-DNS-5: impure `_default_resolver` calls `socket.gethostbyname_ex`; pure `_compute_rules` takes pre-resolved IPs; module docstring documents staleness window. |
| block | `BuildResult` and `AppliedPolicy` referenced but never defined | AC-MODELS-1..AC-MODELS-8: frozen Pydantic models with closed field sets + golden JSON round-trip tests. |
| block | S3-02 ACs widened without enumeration | AC-WIDEN-1..AC-WIDEN-5 + AC-CLIENT-1..AC-CLIENT-7 explicitly list every S3-02 AC modified. |
| block | Race window between `container.start()` and `network_policy.apply()` completion | AC-RACE-1..AC-RACE-3 restructure to `entrypoint=("sleep","infinity")` + `exec_run(spec.cmd)` after apply; integration test sleeps in `apply` spy to assert exec_run.call_count == 0 mid-sleep. |
| block | Container IP resolution path unpinned | AC-IP-1..AC-IP-3: pass `container` SDK object directly into `apply`; read `attrs["NetworkSettings"]["IPAddress"]`; raise `container_ip_unknown` on empty. |
| block | `revert()` failure semantics undefined | AC-REVERT-1..AC-REVERT-5: per-rule isolation, idempotency, primary-exception-wins; 12-cell parametrized test grid. |
| block | `subprocess.run` parameter set unpinned | AC-SUBPROCESS-1..AC-SUBPROCESS-8: shared `_DEFAULT_RUN_KWARGS` MappingProxyType; explicit kwarg-by-kwarg coverage. |
| block | `network_mode="bridge"` change collides with S3-02 AC-EXEC-4 (`"none"` hardcoded) | AC-CLIENT-1: new pure helper `_resolve_network_mode(spec) -> Literal["none","bridge"]`; AC-CLIENT-2 EDITS `_build_container_kwargs`. |
| block | Network policy ordering racy without happens-before barrier | AC-CLIENT-4 pins try/finally structure with conditional apply/revert. |
| harden | `BuildResult` model definition unspecified | Pinned to `did/build.py` module (not contract.py); fields enumerated; `image_digest` regex validator. |
| harden | Stderr truncation policy `≤ 4 KB` not byte-exact | AC-TRUNC-1: `_MAX_STDERR_BYTES: Final[int] = 4096`; UTF-8-safe slicing. |
| harden | Build subprocess timeout unspecified | AC-TIMEOUT-1: `_DEFAULT_BUILD_TIMEOUT_SECONDS: Final[int] = 1800`; on `TimeoutExpired` raise `SandboxBuildFailed("build_timeout")`. |
| harden | Golden iptables container IP hardcoded to magic-string `172.17.0.2` | AC-RULES-7: `_FIXTURE_CONTAINER_IP: Final[str]` module-level constant in test. |
| harden | Module purity AST walker missing | AC-PURE-1..AC-PURE-9 ship two walkers (build.py + network_policy.py). |
| harden | Coverage floor wording absent | AC-COV-1..AC-COV-4. |
| harden | Edge case 5 (postinstall egress dropped by allowlist) — story should explicitly defer to S3-07 | Out of scope section cites S3-07. |
| harden | `image_digest` regex `sha256:[0-9a-f]{64}` — mutation `sha256:[0-9]{64}` passes lucky fixtures | AC-DIGEST-1..AC-DIGEST-3: anchored full-match regex; uppercase-digest fixture must NOT match. |
| nit | `pyproject.toml` confirmed unchanged | AC-DEP-1. |

### Test-Quality critic

| Severity | Finding | Resolution |
|---|---|---|
| block | `argv[:4]` assertion + `"-t" in argv` disjunction is tautological | AC-ARGV-1..AC-ARGV-4: byte-exact golden snapshots indexed by 4-fixture set. |
| block | `_compute_rules` golden test is single-fixture | AC-RULES-1..AC-RULES-6: hypothesis property test + 3 concrete fixtures (empty, single, multi). |
| block | `test_revert_runs_even_when_workload_raises` mocks `network_policy.apply`/`revert` directly | AC-INTEG-1: mock at Docker SDK boundary; exercise real `network_policy.revert` from `execute()`'s finally. |
| block | Stderr truncation untested on > 4 KB input | AC-TRUNC-2: 8 KiB UTF-8 `é` fixture asserts exactly 2048 chars decoded. |
| block | APIError tested on build only; iptables `CalledProcessError` paths untested | AC-ERR-3 mapping table parametrized over all 7 rows. |
| block | `apply()` partial-failure rollback path untested | AC-APPLY-3 + test: inject runner spy failing on rule 3/4; verify reverts of rules 0/1 (reverse order) before re-raise. |
| block | `_default_runner` single-call-site discipline unenforced | AC-DI-4 + AC-PURE-9: AST walk over both files counts `subprocess.run` == 1. |
| block | Mock-patch drift defense missing | AC-DI-5: meta-test greps `tests/sandbox/did/` for `mock.patch("subprocess` and asserts zero hits. |
| harden | Hypothesis property test for `_compute_rules` invariants | AC-RULES-3 (5 properties). |
| harden | DNS resolver failure path untested | AC-DNS-4: inject resolver raising `socket.gaierror`; assert zero rules applied. |
| harden | Revert idempotency untested | AC-REVERT-3: call revert twice; assert 2N runner invocations + per-rule WARNING on second pass. |
| harden | iptables-binary-missing path untested | AC-REVERT-4: runner raises `FileNotFoundError`; revert logs once, does not re-raise. |
| harden | structlog event-fields assertion missing | AC-EVT-3 + AC-LOG-3 parametrized over all six events. |
| harden | UTF-8 mid-multibyte truncation untested | AC-TRUNC-1 + test fixture (stranded `\xc3` continuation byte). |
| harden | `BuildResult` / `AppliedPolicy` model round-trip untested | AC-MODELS-6 / AC-MODELS-7 golden JSON fixtures. |
| harden | Pydantic frozen enforcement untested | AC-MODELS-8: direct attribute set raises ValidationError. |

### Consistency critic

| Severity | Finding | Resolution |
|---|---|---|
| block | New exception classes violate S1-01 HARDENED closed-`reason` Literal | AC-ERR-1: widen `SandboxBackendError.reason` Literal additively (eleven members); AC-ERR-2: subclass with narrower Literal. |
| block | Event names violate S1-01 HARDENED verb convention (`done` → `completed`) | AC-EVT-1: six `Final[str]` constants with `STARTED/COMPLETED/FAILED/APPLIED/REVERTED/APPLY_FAILED`. |
| block | S3-02 AC-SPEC-DEFER-1/-2 widening not enumerated | AC-CLIENT-6/-7 explicitly remove these raise-paths. |
| block | `network_mode="bridge"` collides with S3-02 AC-EXEC-4 (`"none"` hardcoded) | AC-CLIENT-1/-2: `_resolve_network_mode` pure helper widens additively. |
| block | iptables binary execution context (macOS host vs Docker Desktop VM) undocumented | Notes-for-implementer paragraph documents the deferral to S3-07-time; AC-DNS-5 module-docstring `Known limitation:` block carries the marker. |
| harden | ADR-0006 / ADR-0009 / ADR-0014 not cited in story header | "ADRs honored" line expanded. |
| harden | Module purity walker missing | AC-PURE-1..AC-PURE-9 ship two walkers. |
| harden | `forbidden-patterns` pre-commit (shell=True ban) not surfaced as AC | AC-SUBPROCESS-8 + AC-COV-3. |
| harden | S1-07 AST fence allowlist edit unspecified | AC-FENCE-1: one-line additive extension. |
| harden | S3-02 `test_client_purity.py` edit (allowed-helper widening) unspecified | AC-FENCE-2. |
| harden | Verb namespace regex assertion missing | AC-EVT-2: events match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. |

### Design-Patterns critic

| Severity | Finding | Resolution |
|---|---|---|
| block (rule-of-three reached) | Hexagonal DI port (`runner`/`resolver`) — S3-01 + S3-02 + S3-03 = three consumers | Elevated from Note to AC: AC-DI-1..AC-DI-5; kwarg-only ports with production defaults; tests inject directly. |
| block (rule-of-three reached) | Functional core / imperative shell — same lineage | Elevated from Note to AC: AC-FCS-1..AC-FCS-7; both files have explicit pure-helper set + impure-shell set + dedicated `test_*_helpers.py`. |
| harden | Closed Literal discriminator on new error subclasses | AC-ERR-1/-2 (consistent with S1-01 HARDENED / S3-02 HARDENED). |
| harden | `_wrap_subprocess_error` Adapter pattern | AC-ERR-3: single call site + parametrized mapping table; mirrors S3-02's `_wrap_api_error`. |
| harden | `AppliedPolicy` containing stdout/stderr would leak networking topology to Phase 11 | AC-MODELS-5: closed field set excludes raw subprocess output. |
| harden | `BuildResult` re-export to contract.py is YAGNI | AC-MODELS-3: keep internal to `did/build.py`. |
| pattern-note | `NetworkPolicyApplier` Protocol abstraction | Rule-of-three NOT reached (S3-03 + S6-02 = two); deferred per Notes paragraph; collapse to Protocol when third backend lands. |
| pattern-note | Shared `_DEFAULT_RUN_KWARGS` between build.py + network_policy.py | Two consumers ≠ rule-of-three; duplicate rather than hoist. |
| pattern-note | `Host = NewType("Host", str)` for egress_allowlist | YAGNI per Rule 2; one validation path; no boundary crossings. |
| pattern-note | Registry for network policy backends | YAGNI per Rule 2; plain module functions; promote at rule-of-three. |

## Research briefs

**Two Stage-3 questions surfaced; both answered inline:**

### Research 1 — `iptables -d <hostname>` DNS resolution semantics

- **Question:** Does iptables resolve `-d <hostname>` per-packet or at rule-add time? CDN hostnames with rotating IPs (`registry.npmjs.org`) would silently fail under the latter.
- **Sources consulted:** Netfilter HOWTO ([packet-filtering-HOWTO](https://www.netfilter.org/documentation/HOWTO/packet-filtering-HOWTO.html)), `iptables(8)` man page, `iptables-nft` source (Debian package); cross-referenced with Docker Desktop's Alpine-based embedded VM iptables version.
- **Finding:** iptables resolves `-d <hostname>` to a **single IP at rule-add time**, NOT at packet-match time. The DNS lookup happens once, the rule is pinned to that one IP, and rotating CDN hosts will resolve to other IPs that the rule does NOT cover. The kernel's netfilter does not re-resolve.
- **Recommendation:** Pre-resolve hosts via stdlib `socket.gethostbyname_ex` in the impure shell of `apply()` (`_default_resolver`); pass the resulting tuple of IP literals to `_compute_rules`. Document the per-`apply()` re-resolution semantics + the no-caching policy in the module docstring (AC-DNS-5). High-rotation CDN hosts are an acknowledged Phase-7+ migration item (`ipset` with dynamic DNS); for Phase-5's npm-registry-only allowlist, the limitation is acceptable. AC-DNS-1..AC-DNS-5 pin the resolution path, fail-loud semantics, IP-literal short-circuit, and the staleness-window doc string.

### Research 2 — BuildKit `--progress=plain` stderr format

- **Question:** Is the digest extraction regex `sha256:[0-9a-f]{64}` sufficient, or does the BuildKit stderr contain other `sha256:` hits that would false-positive?
- **Sources consulted:** Docker BuildKit docs ([progress configuration](https://docs.docker.com/build/buildkit/configure/#progress)); BuildKit source `frontend/dockerfile/dockerfile2llb` + `progressui/textmux.go`; live `docker buildx build --progress=plain` runs.
- **Finding:** `--progress=plain` writes structured `#<step> <event>` lines to stderr. The final image digest appears on the success path as `#<N> writing image sha256:<64-hex> done` (e.g., `#15 writing image sha256:abc... done`). Cache-hit lines also contain `sha256:` hashes (`#3 CACHED [internal] load metadata for sha256:...`), so an unanchored regex would false-positive. The production-grade pattern is to anchor on `writing image ` prefix.
- **Recommendation:** `_IMAGE_DIGEST_RE = re.compile(r"writing image (sha256:[0-9a-f]{64})")` — capturing group for the digest, anchored on the BuildKit-canonical prefix. AC-DIGEST-1 pins the regex; AC-DIGEST-3 tests parametrized over five fixtures including `cache_hit_only.txt` (must return `None`) and `uppercase_digest.txt` (must return `None` — canonical form is lowercase).

## Conflict resolutions

- **Coverage vs Design-Patterns on `NetworkPolicyApplier` Protocol.** Coverage wanted to pin a future Protocol abstraction now; Design-Patterns invoked Rule 2 (rule-of-three not reached — only S3-03 and S6-02 are known consumers). Design-Patterns wins; resolution recorded as Notes-for-implementer paragraph with a precise trigger condition ("when a third backend lands").
- **Coverage vs Consistency on iptables binary execution context (macOS host vs Docker Desktop VM).** Coverage critic flagged the missing decision as a block; Consistency noted the live-execution path is owned by S3-07 (this story unit-tests against a `runner` spy). Resolution: surface as `TODO(S3-07):` marker in module docstring + Notes-for-implementer paragraph; AC-DNS-5's `Known limitation:` paragraph carries the placeholder. This is a Rule 12 "fail loud" — the deferral is loud, not hidden.
- **Design-Patterns vs Rule 2 on `_DEFAULT_RUN_KWARGS` shared module.** Design-Patterns wanted a `sandbox/did/_subprocess.py` shared module; Rule 2 invoked YAGNI (two consumers ≠ rule-of-three). Rule 2 wins; duplicate the constant; AC-SUBPROCESS-1 carries the value in both files; future hoist documented in Notes.
- **Test-Quality vs S3-02-hardened-precedent on `unittest.mock` vs `pytest-mock`.** S3-02 HARDENED dropped `pytest-mock` (not in dev deps); this story inherits. AC-DI-5 adds a meta-test asserting zero `mock.patch("subprocess` occurrences — defense against drift.

## Edits applied to the story

**Header:**
- `Status: Ready` → `Status: Ready (HARDENED 2026-05-23)`.
- `Depends on:` corrected from `S3-02 only` to `S1-01 + S1-02 + S3-02` with the specific symbols each contributes named in parens.
- `ADRs honored:` expanded from ADR-0001 + ADR-0004 to add ADR-0006 (Protocol deferral), ADR-0009 (forward-compat with Firecracker host-side nftables), ADR-0014 (frozen Pydantic models).

**Validation notes (new, ~85 lines):** Thirteen block-tier + seventeen harden/nit findings summarized; rationale for every AC change; pattern-lineage callouts (S3-01 → S3-02 → S3-03 for DI ports + FCS); two research findings consumed inline.

**Context (rewritten):** Added explicit S3-02 widening narrative; added rule-of-three pattern-elevation paragraph.

**References (expanded):** Added line-number anchors into arch design; added prior HARDENED reports (S1-01, S3-01, S3-02); added external docs for netfilter HOWTO + BuildKit progress format + stdlib socket.

**Goal (rewritten):** Now explicitly names the AC-SPEC-DEFER-1/-2 widening on S3-02, the new error subclasses + closed Literal discriminator, the six new event constants, the byte-exact argv goldens, and the hypothesis property tests on `_compute_rules`.

**Acceptance criteria (rewritten):** Was ~10 unnumbered checkboxes; now ~70 numbered ACs across 20 sections (A through T):
- A. Public surface + module purity
- B. Constructor / runner DI ports
- C. `build_image()` SDK shell
- D. `BuildResult` and `AppliedPolicy` contracts (frozen, extra="forbid")
- E. `_compute_rules` pure helper + golden + hypothesis
- F. `_parse_image_digest` pure helper
- G. `apply()` / `revert()` flow + AppliedPolicy
- H. DNS resolution + IP fan-out
- I. Subprocess discipline (no shell=True, single call site, closed kwargs)
- J. Closed error-reason discriminator + per-phase mapping
- K. `DockerInDockerClient` edit (additive widening of S3-02)
- L. Race-window closure
- M. Stderr truncation (Phase-11-evidence safety)
- N. Module purity (AST walker)
- O. Event-name discipline (append-only to S1-01 + S3-02 table)
- P. Functional core / imperative shell (rule-of-three elevation)
- Q. structlog observability
- R. Argv golden snapshots (build)
- S. Tests stay green + AST fence allowlist
- T. Dependencies + tooling

**Implementation outline (rewritten):** Now ordered: events first → error widening → `network_policy.py` → `build.py` → `client.py` edit → S1-07 fence allowlist edit → S3-02 purity test edit → eight test files in red-first order → golden fixture generation → refactor pass.

**TDD plan (rewritten):** Eight test files (was three):
1. `test_build_helpers.py` — `_build_argv` byte-exact golden, `_parse_image_digest` parametrized, `_truncate_stderr` UTF-8-boundary.
2. `test_network_policy_helpers.py` — `_compute_rules` golden + hypothesis property, `_validate_ip_literal` parametrized.
3. `test_build.py` — core happy path + error grid (build_failed/build_timeout/buildx_missing) + no-mock-patch defense.
4. `test_network_policy.py` — `apply` happy + DNS failure + IP-unknown + partial-failure rollback + revert idempotency.
5. `test_network_policy_revert.py` — idempotency + per-rule failure swallow + binary-missing.
6. `test_client_network_integration.py` — race-window closure + workload-via-exec_run + revert-on-workload-failure.
7. `test_build_purity.py` — module-purity AST walker for `build.py`.
8. `test_network_policy_purity.py` — module-purity AST walker for `network_policy.py`.

**Files to touch (expanded):** Now lists 25 file entries (was 8) including the four edited existing files (errors.py, logging.py, client.py, _docker_types.py, S1-07 fence test, S3-02 purity test) + two new source files + six new test files + four argv goldens + three iptables-rule goldens + five buildx-stderr fixtures + two Pydantic-model JSON fixtures + conftest.py.

**Out of scope (renumbered + expanded):** Explicitly defers Firecracker (S6-02), live integration (S3-07), `--allow-test-network` (S8-02), behavioral verification of iptables drops (S3-07), multi-phase collapse (S3-05), `copy_in`/`copy_out` (S3-04), `time_budget_seconds` (S3-04), `enable_trace` (S4-03), `NetworkPolicyApplier` Protocol (Phase-7+), `ipset` migration (Phase-7+), and `pyproject.toml` changes (none).

**Notes for the implementer (expanded):** Pattern-lineage paragraphs (DI ports rule-of-three, FCS rule-of-three, NetworkPolicyApplier deferral, shared subprocess constants deferral); DNS staleness window explanation; race-window structural-change rationale; macOS-vs-Linux iptables execution context deferral marker for S3-07; closed Literal discriminator pattern; structlog redaction; coverage floor; cross-story forward-pointers (S3-04, S6-02, S3-07, Phase 13).

## Forward-compat anchor — what's pinned for downstream stories

- **S3-04 (copy-out, OOM, timeout):** widens S3-02 AC-SPEC-DEFER-3 (`copy_in`), AC-SPEC-DEFER-4 (`copy_out`), AC-SPEC-DEFER-6 (`time_budget_seconds`); populates `SandboxRun.copy_out_root`, `timed_out`, `killed_by_oom`. `_default_runner`'s `timeout=` kwarg is the precedent shape; `build.py`'s `_DEFAULT_BUILD_TIMEOUT_SECONDS` is the per-chokepoint timeout-constant precedent.
- **S3-05 (multi-phase YAML collapse):** the per-phase `network` field now has flat-spec semantic precedent: `network="none"` → `network_mode="none"`, no policy; `network="scoped"` → `network_mode="bridge"` + `network_policy.apply/revert`. The per-phase split adds N rounds of apply/revert per gate.
- **S3-07 (live integration):** removes the `runner` and `resolver` injection; runs real `subprocess.run(["docker", "buildx", ...])` and real `subprocess.run(["iptables", ...])` against a live Docker daemon; resolves the macOS-vs-Linux iptables execution context question + amends the module docstring's `Known limitation:` paragraph at that time.
- **S6-02 (Firecracker host-side nftables):** ships `sandbox/firecracker/network_policy.py::apply/revert` with the same `(spec, *, container, runner) -> AppliedPolicy` callable signature (or a Firecracker-specific variant if rule semantics diverge substantially — ADR amendment if so). This is the second backend; the third backend triggers the rule-of-three collapse to a `NetworkPolicyApplier` Protocol + registry per ADR-0006.
- **Phase 11 (evidence bundle):** consumes `SandboxRun.exit_code` + `logs_dir`; never `BuildResult` directly. `AppliedPolicy.applied_rules` is the audit-trail anchor.
- **Phase 13 (cost ledger):** keys on `SandboxBackendError.reason` for cost-attribution buckets. The eleven-member union AC-ERR-1 widens to is the closed Literal contract.

## No `RESCUE` findings

The DNS-vs-IP block was the closest to structural — it could have invalidated the golden file's argv form entirely — but the resolution is patchable: pre-resolve to IPs, re-resolve per `apply()`, golden tests use a monkeypatched resolver. The race-window finding was also structural (the create-with-cmd → start → stream pattern from S3-02 cannot guarantee policy-before-egress) but the fix is a clean restructure to `entrypoint=("sleep","infinity")` + `exec_run(spec.cmd)`. Both fixes are documented; downstream stories inherit clean hand-offs.

## Recommended next step

`phase-story-executor` to implement.

The story is now ready for the executor:
- Every AC is individually verifiable.
- The AC set collectively guarantees the goal (egress is locked down BEFORE the workload runs; subprocess argv is byte-exact; cleanup is best-effort but ordered; primary exception always wins).
- Every AC has a corresponding test in the TDD plan that would fail on an obviously wrong implementation (mutation-resistance via golden snapshots, hypothesis properties, byte-exact argv, closed-Literal `typing.get_args` asserts).
- The race-window structural change is documented as the load-bearing pattern, not a sleep-hack.
- The macOS-vs-Linux iptables execution context is deferred to S3-07 with an explicit `TODO(S3-07):` marker — no silent shipping of wrong semantics.
- The rule-of-three pattern elevations (DI port, FCS) are encoded as ACs with positive AST-walk pins — the patterns now live in the test suite, not in tribal knowledge.
