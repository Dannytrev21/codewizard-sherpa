# Validation report — Story S6-04 `sandbox.registry.auto_detect` + macOS fallback INFO log

**Date:** 2026-05-25
**Validator:** `phase-story-validator` (single-agent inline mode)
**Verdict:** **HARDENED**

## Context brief

S6-04 is the small but load-bearing seam where the orchestrator picks Firecracker vs DinD at runtime. The draft prescribed a `_probe_kvm() -> tuple[str | None, str]` helper called inside `auto_detect()`, two new structlog events (`sandbox.registry.selected`, `sandbox.registry.fallback_to_did`), and a six-test TDD plan that monkey-patches `Path.exists` / `os.access` / `sys.platform` on the registry module.

Read for context:
- `docs/phases/05-sandbox-trust-gates/phase-arch-design.md §Component design — SandboxClient`, §Edge case 15, §CLI surface, §Logical view, §Data model.
- `docs/phases/05-sandbox-trust-gates/ADRs/0004-dind-default-macos-with-gate-isolation-class.md` (the verbatim consequence S6-04 lands).
- `docs/phases/05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md`.
- `docs/phases/05-sandbox-trust-gates/High-level-impl.md §Step 6`.
- `docs/phases/05-sandbox-trust-gates/stories/S1-05-registries-and-env-allowlist.md` HARDENED — already pins the registry kernel + the stub `auto_detect()` this story replaces, plus `EVENT_SANDBOX_AUTO_DETECT_FALLBACK = "sandbox.auto_detect.fallback"`.
- `docs/phases/05-sandbox-trust-gates/stories/S6-01-firecracker-client-kvm-boot.md` HARDENED — `FirecrackerClient` requires multi-kwarg `__init__`; `FirecrackerKvmMissing.reason == "sandbox.kvm_missing"`; the warning-ID regex is `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.
- `docs/phases/05-sandbox-trust-gates/stories/S6-03-rootfs-digests-and-prepare.md` HARDENED — `from_digests_yaml` is **removed**; the canonical construction is `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=...), artifacts_root=..., ...DI ports...)`.
- `docs/phases/05-sandbox-trust-gates/stories/S3-02-did-client-sdk-core.md` HARDENED — `DockerInDockerClient.__init__(self, *, docker_url=None, docker_factory=_default_docker_factory)`; AC-REG-1 pins `get_backend("docker_in_docker") is DockerInDockerClient` (i.e., `get_backend` returns the **class**, not an instance — the caller instantiates).
- `docs/phases/05-sandbox-trust-gates/stories/S3-06-sandbox-health-probe.md` HARDENED — established the `backend_provider` constructor-injection precedent (Rule 8: hidden-state monkeypatch of `auto_detect` is banned in sibling consumers; mirrors here).
- CLAUDE.md commitments: warning/error-ID regex; "Newtype identifiers"; "Functional core / imperative shell"; "Extension by addition — no silent edits"; "Match the existing convention".

## Four-critic findings (inline-synthesized)

### Coverage critic

| # | Severity | Finding |
|---|---|---|
| C-1 | **block** | Acceptance criteria are bare unnumbered checkboxes; every sibling HARDENED story in this phase (S1-02 / S1-05 / S3-02 / S6-01 / S6-03) carries `AC-XX-N` IDs. Reviewers + the executor's Ralph-Wiggum validator cannot reference items unambiguously without IDs. |
| C-2 | **harden** | No AC pins **what happens on the WSL2 path** (`sys.platform == "linux"` AND `/dev/kvm` present in a Linux-on-Windows VM that exposes nested KVM). Implicit but unstated. |
| C-3 | **harden** | No AC for the dependency-graph fact that `auto_detect` must be safe to call **multiple times** in the same process (orchestrator may resume mid-loop). |
| C-4 | **harden** | No coverage AC (line + branch); every Phase-5 sibling pins ≥95% line + ≥90% branch. |
| C-5 | **harden** | No module-purity AC (`from __future__ import annotations` line 1; `__all__` alphabetized; module docstring cites ADR-0004 / ADR-0001; restricted imports). Every Phase-5 module ships one. |

### Test-quality critic

| # | Severity | Finding |
|---|---|---|
| T-1 | **block** | `os.access(...)` is mocked to return a single bool that ignores its mode argument. An implementer using `os.access("/dev/kvm", os.R_OK)` (missing `W_OK`) would pass every test in the draft. Mutation: silent. The AC text says "both conditions, not either" but the test does not pin the mode. |
| T-2 | **block** | Tests `patch("codegenie.sandbox.registry.Path.exists")` and `patch("codegenie.sandbox.registry.os.access")` — coupling test setup to import-time module names. Equivalent to the S3-06 anti-pattern that was forbidden ("`monkeypatch.setattr("...auto_detect")` is banned; constructor injection only"). An implementer using `os.path.exists("/dev/kvm")` or `pathlib.Path("/dev/kvm").exists()` from a re-import would silently break the test wiring. |
| T-3 | **harden** | The test labeled "macOS short-circuits the KVM probe" only mocks `sys.platform` — it does **not** assert that `Path.exists` and `os.access` are NEVER called. The short-circuit is observable only by a call-count assertion. |
| T-4 | **harden** | No mutation-thinking pass on event-emission ordering. The "log emitted before return" requirement is prose-only; the test must verify that on a construction failure (`get_backend` raises), the log is still emitted (i.e., the log call sits BEFORE the `get_backend(...)` invocation, not in a `finally:`). |
| T-5 | **harden** | No `structlog` test wiring shown — the project uses `caplog` with `logger.info(EVENT, extra={...})` per S1-05 HARDENED. The draft uses `structlog.testing.LogCapture()` which is inconsistent with the established Phase-5 test pattern. |
| T-6 | **harden** | Hypothesis / property test: `auto_detect` is deterministic given the same `KvmProber` state — no property test pins this. Optional but cheap. |

### Consistency critic

| # | Severity | Finding |
|---|---|---|
| K-1 | **block** | **Reason strings violate CLAUDE.md regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`.** Draft uses `"kvm_missing"`, `"kvm_not_accessible"`, `"platform_not_linux"`, `"kvm_available"` — none are namespaced. S6-01 HARDENED explicitly paid this rent (renamed `kvm_missing` → `sandbox.kvm_missing`); S6-04 inherits but draft regresses. The phase-arch §Edge case 15 literal `"kvm_missing"` is an erratum already documented in S6-01 HARDENED. |
| K-2 | **block** | **Logging-constant collision with S1-05 HARDENED.** S1-05 already pins `EVENT_SANDBOX_AUTO_DETECT_FALLBACK = "sandbox.auto_detect.fallback"` and emits it from the stub `auto_detect()`. The draft introduces TWO new event names (`sandbox.registry.selected`, `sandbox.registry.fallback_to_did`) that silently supersede the existing constant — a silent edit forbidden by ADR-0043 ("Extension by addition means no silent edits"). Resolution: REUSE `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` for the fallback path (preserves S1-05 call-site contract); ADD exactly one new constant `EVENT_SANDBOX_REGISTRY_SELECTED = "sandbox.registry.selected"` for the happy path. Append-only to S1-01's canonical table per S1-01 Validation note §6. |
| K-3 | **block** | **`FirecrackerClient` construction path contradicts S6-03 HARDENED.** Draft outline says "via `from_digests_yaml()` if S6-03 has landed, else the constructor with digests loaded inline". S6-03 HARDENED **removed** `from_digests_yaml` (AC-FACTORY-5: "removed — not `_internal`-tagged"). The canonical replacement is `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=Path("tools/digests.yaml")), artifacts_root=..., ...DI ports...)`. Additionally, `registry.get_backend("firecracker")` returns the **class**, not an instance (per S3-02 HARDENED AC-REG-1 identity contract); calling it with zero args would raise — `FirecrackerClient` has no zero-arg constructor. S6-04 must bypass `get_backend("firecracker")()` and use the documented factory. |
| K-4 | **harden** | `Depends on:` line names only S6-01. The real dependency closure is **S6-01, S6-03, S1-05** (registry kernel + the `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` constant being reused). |
| K-5 | **harden** | Reason for happy-path event is `"kvm_available"` — also unnamespaced. Promote to `sandbox.kvm_available`. |
| K-6 | **harden** | The fallback `selected_backend="docker_in_docker"` and happy-path `selected_backend="firecracker"` string literals must reference the canonical `Literal` mirror — `SandboxRun.backend: Literal["docker_in_docker", "firecracker"]` from S1-02 AC-4. Without a `Final` constant, an implementer typoing `"docker-in-docker"` (kebab) would pass tests that hard-code the matching wrong string. |
| K-7 | **nit** | The Notes line "Resist building a 'tier' system (try Firecracker → on `FirecrackerKvmMissing` swap to DinD mid-run)" is correct guidance but should be elevated to an explicit AC: `auto_detect` never catches `FirecrackerKvmMissing` — that error from `FirecrackerClient` construction propagates. |

### Design-patterns critic

| # | Severity | Finding |
|---|---|---|
| D-1 | **harden** (elevated under rule-of-three) | **Hexagonal DI port missing.** Phase 5's pattern lineage (S3-01 → S3-02 → S3-06 → S6-01 → S6-03) consistently injects collaborators via constructor / keyword-arg ports. `auto_detect()` calls `sys.platform`, `Path("/dev/kvm").exists()`, `os.access(...)` — three hidden global I/O dependencies. The fix: introduce a `KvmProber` Protocol returning a tagged-union `KvmStatus` (closed `Literal`). Default impl wraps the three syscalls; tests inject a fake. This is the **sixth** concrete consumer of the Hexagonal-DI pattern in Phase 5 — well past the rule-of-three threshold; resisting here would silently retire the pattern. Sibling precedent: `SandboxHealthProbe(backend_provider=...)` (S3-06 AC-ABC-7) — the exact same shape, banning monkeypatch of import-time helpers. |
| D-2 | **harden** | **Tagged-union / sum-type opportunity** on the `_probe_kvm` return value. Draft returns `tuple[str | None, str]` (an anaemic 2-tuple of magic strings + platform name) — primitive obsession. Promote to a closed `Literal` `KvmStatus = Literal["sandbox.kvm_available", "sandbox.kvm_missing", "sandbox.kvm_not_accessible", "sandbox.platform_not_linux"]` returned alongside the platform string. Mutation: a string typo in the helper would silently flow through the rest of the function. With `Literal`, mypy --strict catches it. |
| D-3 | **harden** | **Module-level `Final` constants for backend names.** Same rationale as S3-02 HARDENED `_BACKEND_NAME: Final[str] = "docker_in_docker"` and S6-01 HARDENED `_BACKEND_NAME: Final[str] = "firecracker"` — single source of truth across the file. Both names appear in `auto_detect()` body; without the `Final` extract, an implementer typoing `"docker-in-docker"` could pass cherry-picked unit tests. |
| D-4 | **nit / Note** | `auto_detect_dry_run()` — Refactor §"Consider exposing" is wishy-washy. Either land it now (Open/Closed for `SandboxHealthProbe` per S3-06) or defer to S8-01 with a named TODO. The validation directs the latter: **explicit deferral to S8-01**; do not ship until the consumer needs it (Rule 2). |
| D-5 | **nit / Note** | Kernel-extract: `_default_kvm_prober` is the seventh DI-port default in this phase. A shared `_default_*_port` test-isolation helper is tempting; **defer** per Rule 2 — the divergent shapes (digest loader vs docker factory vs api socket factory vs kvm prober) still argue against the extract. Document in Notes. |

No `NEEDS RESEARCH` findings — every weakness is answerable from Phase 5 arch + ADRs + the five prior HARDENED reports + CLAUDE.md. **Stage 3 (researcher) skipped.**

## Conflict resolution

The four critics' findings are mutually consistent. The only choice point was Design-pattern critic D-1 ("introduce `KvmProber`") vs Rule 2 ("three similar lines is better than premature abstraction"). Rule of three governs: this is the **sixth** concrete consumer of Hexagonal DI in Phase 5 — well past Rule 2's threshold. The S3-06 HARDENED report literally bans monkey-patching `auto_detect` in favor of constructor injection; mirroring that ban here means the seam must exist. **Design-patterns wins; KvmProber lands as an AC**, not Notes-only.

The `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` ↔ `sandbox.registry.fallback_to_did` collision (K-2) resolves by **reusing the S1-05 constant verbatim** (no silent rename) and adding exactly ONE new constant for the happy path. This honors ADR-0043 (no silent edits) while letting the new selection-event semantics ship additively.

## Edits applied to the story

The story file at `../S6-04-auto-detect-macos-fallback.md` was rewritten in place with the following structural changes (every change traces to one or more findings above):

1. **Status line** — `Ready` → `Ready (HARDENED 2026-05-25)`.
2. **Validation notes block** appended after the header summarizing the changes (mirror of every other HARDENED story in this phase).
3. **`Depends on:`** widened from `S6-01` to `S6-01, S6-03, S1-05` (resolves K-4).
4. **`ADRs honored:`** kept ADR-0004, ADR-0001; added ADR-0043 (no silent edits — the event-name discipline) and noted CLAUDE.md "Functional core / imperative shell" + warning-ID regex inheritance.
5. **Acceptance criteria reorganized into lettered sections with numbered IDs** (sections A–K, ~35 numbered ACs). Resolves C-1.
6. **`KvmProber` Hexagonal DI port** added as section B (resolves D-1). Default impl wraps the three syscalls; tests inject a fake.
7. **`KvmStatus` closed-Literal sum type** pinned (resolves D-2). The four members are `sandbox.kvm_available` / `sandbox.kvm_missing` / `sandbox.kvm_not_accessible` / `sandbox.platform_not_linux` — all namespaced (resolves K-1, K-5).
8. **Module-level `_BACKEND_FIRECRACKER` / `_BACKEND_DIND` `Final` constants** required (resolves D-3, K-6).
9. **Logging contract rewritten** — REUSE `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` from S1-05; ADD exactly ONE new constant `EVENT_SANDBOX_REGISTRY_SELECTED = "sandbox.registry.selected"`. Append-only to S1-01's canonical table per S1-01 Validation note §6 (resolves K-2).
10. **Construction wiring rewritten** — KVM-present path uses `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=...), artifacts_root=..., ...DI ports...)`; KVM-absent path uses `get_backend("docker_in_docker")()` (zero-arg-safe per S3-02 HARDENED). Both `digests_yaml` and `artifacts_root` are constructor-injected ports defaulting to project-root resolution (resolves K-3).
11. **Mode-argument pinning AC** added — every default-`KvmProber` test asserts `os.access` is called with `os.R_OK | os.W_OK`, not a weaker subset (resolves T-1).
12. **DI-port-only test ACs** — banning `patch("codegenie.sandbox.registry.Path.exists")` / `patch("...os.access")` / `patch.object(sys, "platform", ...)` in favor of `auto_detect(kvm_prober=FakeKvmProber(...))` (resolves T-2). The default `KvmProber` unit-tests do exercise the real syscalls (via `tmp_path` for `Path.exists` and via `os.access` mode-arg pinning).
13. **Short-circuit assertion AC** — macOS test asserts `FakeKvmProber.probe_call_count == 1` AND the platform short-circuit happens inside `_default_kvm_prober` itself (the default prober short-circuits on `sys.platform != "linux"` before touching `Path` / `os.access`) (resolves T-3).
14. **Log-before-return AC** — explicit: the log call sits BEFORE the construction call. Test verifies that on a forced construction failure (`load_pinned_digests` raises), the log was emitted (resolves T-4).
15. **`structlog` test wiring removed** — tests use `caplog.set_level(logging.INFO, logger="codegenie.sandbox.registry")` consistent with S1-05 HARDENED (resolves T-5).
16. **Idempotency AC** — `auto_detect` called twice in the same process returns two distinct instances (no caching of the chosen client) (resolves C-3).
17. **Module-purity AC** added (mirror S1-05 / S3-02 HARDENED) (resolves C-5).
18. **Coverage floor** — line ≥ 95% AND branch ≥ 90% (resolves C-4).
19. **Property test (hypothesis)** — `auto_detect` is deterministic for a given `KvmProber` state, parameterized over the four `KvmStatus` values (resolves T-6 optionally; cheap to land).
20. **No-silent-fallback AC** — `auto_detect` never catches `FirecrackerKvmMissing` / `FirecrackerBinaryMissing` / `FirecrackerRootfsMissing` / any other construction error. Mirror of K-7.
21. **`auto_detect_dry_run` deferred explicitly to S8-01** (resolves D-4); removed from Refactor section.
22. **Out-of-scope list** widened to include the dry-run + `--sandbox-backend auto` CLI override (S8-02) + WSL2-specific smoke (still covered implicitly by Linux+KVM-present test).
23. **Forward-seam notes** added — kernel-extract for `_default_*_port` deferred (D-5); the `KvmStatus` Literal widens additively when Phase 7 adds gVisor or a third backend.

## Verdict

**HARDENED.** No findings required RESCUE (the goal traces cleanly to ADR-0004 §Consequences and to the phase-arch Component-design + Edge-case-15 prescriptions). All block-tier issues are patchable inside the story file via numbered ACs + a TDD-plan rewrite. The hardened story is ready for `phase-story-executor`.

## What was NOT changed

- The story's goal (KVM-present → Firecracker; else DinD; structured log every time).
- The orchestrator-wiring deferral to S8-02 (out of scope for S6-04).
- The KVM-gated smoke test deferral to S6-05.
- The arch's §Edge case 15 erratum (`reasons=["kvm_missing"]` lacks namespace) — that's an arch text fix, not in this story's scope; we follow CLAUDE.md regex authoritatively.
- The S1-05 vs S3-02 contract drift about `get_backend()` returning instance-vs-class — flagged for a future cross-story consistency sweep; for this story we follow the most recent contract (S3-02 / S6-01 / S6-03 HARDENED: `get_backend` returns the class; the caller instantiates).

## References inside the story file

The HARDENED story preserves every original reference link and adds the four prior HARDENED reports + the `KvmProber` Hexagonal port + the `KvmStatus` sum-type pattern as `Notes for the implementer`.
