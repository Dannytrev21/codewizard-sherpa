# Story S6-04 — `sandbox.registry.auto_detect` + macOS fallback INFO log

**Step:** Step 6 — FirecrackerClient backend + KVM-gated CI smoke test
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** S
**Depends on:** S1-05 (registry kernel + reused `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`), S6-01 (FirecrackerClient surface + the three structured KVM-related errors), S6-03 (`load_pinned_digests` + `FirecrackerClient.from_pinned_digests` factory)
**ADRs honored:** ADR-0004 (DinD macOS default + `gate_isolation_class` propagation), ADR-0001 (`SandboxClient` is the gate seam), production ADR-0043 (extension by addition — no silent edits to S1-05's logging constant)

## Validation notes (2026-05-25 HARDENED)

This draft had three **block-tier** weaknesses and eleven **harden-tier** weaknesses (see `_validation/S6-04-auto-detect-macos-fallback.md`). Headlines:

1. **Reason strings violated CLAUDE.md regex.** Draft used bare `"kvm_missing"` / `"platform_not_linux"` / `"kvm_available"`; CLAUDE.md mandates `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. S6-01 HARDENED already paid this rent (`sandbox.kvm_missing`); S6-04 now inherits — every reason is namespaced.
2. **Logging-constant collision with S1-05 HARDENED resolved by reuse + one additive constant.** S1-05 HARDENED pinned `EVENT_SANDBOX_AUTO_DETECT_FALLBACK = "sandbox.auto_detect.fallback"` and emits it from the stub `auto_detect()`. The draft would have silently superseded it with two brand-new event names — banned by ADR-0043. Resolution: REUSE the existing constant for the fallback path; ADD exactly one new `EVENT_SANDBOX_REGISTRY_SELECTED = "sandbox.registry.selected"` for the happy path. Append-only to S1-01's canonical table.
3. **`FirecrackerClient` construction path contradicted S6-03 HARDENED.** Draft referenced the **removed** `from_digests_yaml` classmethod. Resolution: build via `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=...), artifacts_root=..., ...DI ports...)`. The DinD path uses `get_backend("docker_in_docker")()` (zero-arg-safe per S3-02 HARDENED); the Firecracker path bypasses `get_backend("firecracker")()` because `FirecrackerClient` has no zero-arg constructor.
4. **Hexagonal DI port `KvmProber` added (sixth concrete consumer of the Phase-5 DI pattern; rule-of-three reached long ago).** Draft monkey-patched `Path.exists` / `os.access` / `sys.platform` at the registry-module level — the exact anti-pattern S3-06 HARDENED banned for `auto_detect`. Tests now inject `kvm_prober=FakeKvmProber(...)` directly through the constructor; the default `KvmProber` impl wraps the three syscalls + has its own unit tests that exercise the real `Path.exists` and pin the `os.access` mode argument to `os.R_OK | os.W_OK`.
5. **`KvmStatus` closed-Literal sum type** replaces the `tuple[str | None, str]` anaemic return — primitive obsession eliminated. Members are the four namespaced reason IDs.
6. **Module-level `_BACKEND_FIRECRACKER` / `_BACKEND_DIND` `Final` constants** — single source of truth for the two backend-name string literals across the file. An implementer typoing `"docker-in-docker"` (kebab) gets a single-location compile-time mismatch instead of silently selecting nothing.
7. **`os.access` mode-arg pinning** — the draft test could not distinguish an implementer asking for `R_OK` only (missing `W_OK`) from one asking for both. Default-`KvmProber` test records the mode-arg via `side_effect` and asserts it equals `os.R_OK | os.W_OK`.
8. **Short-circuit count assertion** — the macOS test now asserts `FakeKvmProber.probe_call_count == 1` AND the default prober's `_check_dev_kvm()` was never called (a separate spy proves the platform short-circuit fires inside the prober itself).
9. **Log-before-return** — explicit AC. The selection log is emitted BEFORE `FirecrackerClient.from_pinned_digests(...)` is called. Test forces `load_pinned_digests` to raise and verifies the log was already emitted.
10. **`structlog.testing.LogCapture()` removed.** Tests use `caplog` with `logger="codegenie.sandbox.registry"` consistent with S1-05 HARDENED.
11. **No silent fallback on construction failure.** `auto_detect` never catches `FirecrackerKvmMissing` / `FirecrackerBinaryMissing` / `FirecrackerRootfsMissing` (S6-01 HARDENED errors) — they propagate to the caller. Mid-run backend swaps would invalidate the audit chain (S2-01) and `gate_isolation_class` (ADR-0004).
12. **Module-purity AC** mirroring S1-05 / S3-02 HARDENED — `from __future__ import annotations` line 1; `__all__` alphabetized; module docstring cites ADR-0004 / ADR-0001 / ADR-0043; restricted imports.
13. **Coverage floor** aligned at line ≥ 95% AND branch ≥ 90% (matches every other Phase-5 module).
14. **`auto_detect_dry_run` deferred explicitly to S8-01** — the wishy-washy "Consider exposing" Refactor line removed.

No `RESCUE`-tier findings — every gap was patchable. No Stage-3 research was needed.

## Context

Both `SandboxClient` backends now exist (DinD from S3-02, Firecracker from S6-01 + S6-03), but no caller knows which to pick at runtime. `phase-arch-design.md §Component design — SandboxClient` and `ADR-0004` commit us to `sandbox.registry.auto_detect()`: if `/dev/kvm` is readable+writable on a Linux host, return Firecracker; otherwise return DinD with a structured INFO log of the fallback reason. S1-05 HARDENED already shipped a **stub** `auto_detect()` that always emits `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` and returns `get_backend("docker_in_docker")` — S6-04 replaces that stub with the real platform-detection logic while reusing the same logging constant (no silent rename, per ADR-0043). The orchestrator passes `auto_detect()` (default) into `GateRunner` unless `--sandbox-backend {did,firecracker,auto}` overrides it (wiring lands in S8-02). This story is small but it is the **only** seam where a Linux/CI run silently picks the wrong backend if we get it wrong — so the test must exercise both branches plus the on-macOS log line that operators rely on to diagnose surprises.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxClient` — `sandbox.registry` exposes `get_backend(name)` and `auto_detect() -> SandboxClient`.
  - `../phase-arch-design.md §Edge cases §15` — `/dev/kvm` absent → auto-detect falls back to DinD with INFO log. **Note:** the literal `reasons=["kvm_missing"]` is an arch erratum already documented in S6-01 HARDENED (CLAUDE.md regex requires `sandbox.kvm_missing`).
  - `../phase-arch-design.md §CLI surface` — `--sandbox-backend {did,firecracker,auto}` defaults to `auto`.
- **Phase ADRs:**
  - `../ADRs/0004-dind-default-macos-with-gate-isolation-class.md` — "`codegenie sandbox auto-detect` returns Firecracker if `/dev/kvm` is readable, else DinD; structured fallback INFO log on macOS." Verbatim consequence we land.
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `SandboxClient` is the seam; `auto_detect` returns one, never both.
- **Production ADRs:**
  - `../../../production/adrs/0019-sandbox-stack.md` — auto-detect picks the production-shaped backend; evidence feeds eventual resolution.
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — drives the reuse of `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`.
- **Source design:**
  - `../final-design.md §Synthesis ledger row "Sandbox stack default macOS"` — fallback semantics in plain language.
- **Prior validation (mandatory read):**
  - `_validation/S1-05-registries-and-env-allowlist.md` — pins `EVENT_SANDBOX_AUTO_DETECT_FALLBACK = "sandbox.auto_detect.fallback"`; pins the registry kernel + `.fresh()` + `registry=` kwarg discipline; documents the stub `auto_detect()` this story replaces.
  - `_validation/S6-01-firecracker-client-kvm-boot.md` — Hexagonal DI ports; closed-Literal `reason` discriminator; `FirecrackerKvmMissing.reason == "sandbox.kvm_missing"`; `_BACKEND_NAME: Final[str]` discipline; the warning-ID regex enforcement.
  - `_validation/S6-03-rootfs-digests-and-prepare.md` — `from_digests_yaml` removed; canonical construction is `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=...), artifacts_root=..., DI ports)`.
  - `_validation/S3-02-did-client-sdk-core.md` — `DockerInDockerClient(*, docker_url=None, docker_factory=_default_docker_factory)`; AC-REG-1 pins `get_backend("docker_in_docker") is DockerInDockerClient` (registry returns the **class**; caller instantiates).
  - `_validation/S3-06-sandbox-health-probe.md` — bans `monkeypatch.setattr("...auto_detect")` in favor of constructor injection; the exact pattern this story mirrors via `KvmProber`.
- **CLAUDE.md anchors:**
  - "Warning + error IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`" — every `KvmStatus` member is namespaced.
  - "Functional core / imperative shell" — `_default_kvm_prober` is the pure-ish core; `auto_detect()` is the thin shell.
  - "Extension by addition — no silent edits" — reuses S1-05's logging constant.
- **Existing code:**
  - `src/codegenie/sandbox/registry.py` (from S1-05 HARDENED) — already exposes `get_backend(name)`, `auto_detect()` (stub), `@register_sandbox_backend`, `SandboxBackendRegistry.fresh()`, `sandbox_backend_registry`. This story **edits** this file to replace the stub `auto_detect` body and append a `KvmProber` Protocol + `_default_kvm_prober`.
  - `src/codegenie/sandbox/did/client.py` (from S3-02 HARDENED) — `DockerInDockerClient()` constructable with zero args (all kwargs have defaults).
  - `src/codegenie/sandbox/firecracker/client.py` (from S6-01 + S6-03 HARDENED) — `FirecrackerClient.from_pinned_digests(digests, *, artifacts_root, ...)` factory.
  - `src/codegenie/digests/__init__.py` (from S6-03 HARDENED) — `load_pinned_digests(*, digests_yaml: Path) -> PinnedDigests`.
  - `src/codegenie/sandbox/logging.py` — append-only the one new `EVENT_SANDBOX_REGISTRY_SELECTED` constant.
- **External docs:** None — pure host-detection logic.

## Goal

Replace S1-05's stub `auto_detect()` with the real platform-detection logic so that KVM-capable Linux hosts get `FirecrackerClient` (built via `from_pinned_digests`), every other host gets `DockerInDockerClient` (via `get_backend("docker_in_docker")()`), and **every** call emits exactly one structured INFO log line — either `sandbox.registry.selected` (Firecracker chosen) or `sandbox.auto_detect.fallback` (DinD chosen). All four possible reason strings are namespaced per CLAUDE.md regex. The kvm-probe logic is encapsulated behind a `KvmProber` Hexagonal DI port so tests inject a fake instead of monkey-patching `Path` / `os` / `sys`.

## Acceptance criteria

### A. Public surface + module discipline

- [ ] **AC-A1 — Imports.** `from codegenie.sandbox.registry import auto_detect, KvmProber, KvmStatus, _default_kvm_prober` succeeds; `from codegenie.sandbox.logging import EVENT_SANDBOX_AUTO_DETECT_FALLBACK, EVENT_SANDBOX_REGISTRY_SELECTED` succeeds; both modules are idempotent on re-import (`id(mod_first) == id(mod_second)`).
- [ ] **AC-A2 — `auto_detect` signature.** `inspect.signature(auto_detect)` matches `(*, kvm_prober: KvmProber = _default_kvm_prober, digests_yaml: Path = _DEFAULT_DIGESTS_YAML, artifacts_root: Path = _DEFAULT_ARTIFACTS_ROOT) -> SandboxClient`. All three parameters are keyword-only with production-shaped defaults; tests inject fakes (Hexagonal DI pattern — sixth concrete consumer in Phase 5).
- [ ] **AC-A3 — `__all__` discipline.** `set(codegenie.sandbox.registry.__all__) ⊇ {"KvmProber", "KvmStatus", "auto_detect", "get_backend", "register_sandbox_backend", "sandbox_backend_registry", "SandboxBackendRegistry"}` (the four S1-05 names + the three new ones). `mod.__all__ == sorted(mod.__all__)`. `_default_kvm_prober`, `_BACKEND_FIRECRACKER`, `_BACKEND_DIND`, `_DEFAULT_DIGESTS_YAML`, `_DEFAULT_ARTIFACTS_ROOT` are module-private (leading underscore) and NOT in `__all__`.
- [ ] **AC-A4 — `from __future__ import annotations`** is the first non-docstring statement of `registry.py` (already pinned by S1-05; re-asserted here so the executor's diff cannot drop it).
- [ ] **AC-A5 — Module docstring cites ADR-0004, ADR-0001, ADR-0043** by ID (additive — S1-05 already cites ADR-0003 / ADR-0006; we widen).
- [ ] **AC-A6 — Module-level `Final` backend-name constants.**
  ```python
  _BACKEND_FIRECRACKER: Final[Literal["firecracker"]] = "firecracker"
  _BACKEND_DIND: Final[Literal["docker_in_docker"]] = "docker_in_docker"
  ```
  Both are typed against the `SandboxRun.backend` Literal from S1-02 AC-4. Inline string literals of either value anywhere else in `registry.py` (outside this declaration) are forbidden — AST-walker test pins it (AC-PURE-5).

### B. `KvmProber` Hexagonal DI port

- [ ] **AC-B1 — `KvmStatus` closed `Literal` sum type.**
  ```python
  KvmStatus = Literal[
      "sandbox.kvm_available",
      "sandbox.kvm_missing",
      "sandbox.kvm_not_accessible",
      "sandbox.platform_not_linux",
  ]
  ```
  Every member matches the CLAUDE.md regex `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Exposed in `__all__`.
- [ ] **AC-B2 — `KvmProber` Protocol.** `@runtime_checkable class KvmProber(Protocol): def probe(self) -> tuple[KvmStatus, str]: ...` — returns `(status, platform_name)` where `platform_name` is the raw `sys.platform` (`"darwin"` / `"linux"` / `"win32"` / etc.) at the time of probing.
- [ ] **AC-B3 — `_default_kvm_prober` implements `KvmProber`.** `isinstance(_default_kvm_prober, KvmProber)` is `True` (structural conformance check at test time).
- [ ] **AC-B4 — Default-prober logic is pure of imports / well-isolated.** Implementation:
  ```python
  class _DefaultKvmProber:
      def probe(self) -> tuple[KvmStatus, str]:
          platform_name = sys.platform
          if platform_name != "linux":
              return ("sandbox.platform_not_linux", platform_name)
          if not Path("/dev/kvm").exists():
              return ("sandbox.kvm_missing", platform_name)
          try:
              accessible = os.access("/dev/kvm", os.R_OK | os.W_OK)
          except (OSError, PermissionError):
              return ("sandbox.kvm_not_accessible", platform_name)
          if not accessible:
              return ("sandbox.kvm_not_accessible", platform_name)
          return ("sandbox.kvm_available", platform_name)

  _default_kvm_prober: Final[KvmProber] = _DefaultKvmProber()
  ```
- [ ] **AC-B5 — `KvmProber.probe()` is total** — it never raises. The default impl traps `OSError` / `PermissionError` from `os.access` and folds them into `"sandbox.kvm_not_accessible"`. Test forces `os.access` to `raise PermissionError` and asserts the result.
- [ ] **AC-B6 — Mode-arg pinning for `os.access`.** Default-prober test wraps `os.access` with a `side_effect` that records `(path, mode)` calls; on the happy-path test, it asserts the call is exactly `os.access(Path("/dev/kvm"), os.R_OK | os.W_OK)` — both bits, not a subset. Mutation: an implementer using `os.R_OK` only would flip this assertion red.
- [ ] **AC-B7 — Platform short-circuit observable.** Default-prober test on `sys.platform == "darwin"`: `Path.exists` and `os.access` are wrapped with spies and the assertion is `path_exists_spy.call_count == 0 and os_access_spy.call_count == 0` — the prober short-circuits before touching them.

### C. `auto_detect()` selection logic

- [ ] **AC-C1 — Body shape (pseudo-code):**
  ```python
  def auto_detect(*, kvm_prober=_default_kvm_prober,
                  digests_yaml=_DEFAULT_DIGESTS_YAML,
                  artifacts_root=_DEFAULT_ARTIFACTS_ROOT) -> SandboxClient:
      status, platform_name = kvm_prober.probe()
      if status == "sandbox.kvm_available":
          logger.info(
              EVENT_SANDBOX_REGISTRY_SELECTED,
              extra={
                  "selected_backend": _BACKEND_FIRECRACKER,
                  "reason": status,
                  "platform": platform_name,
              },
          )
          digests = load_pinned_digests(digests_yaml=digests_yaml)
          return FirecrackerClient.from_pinned_digests(
              digests, artifacts_root=artifacts_root,
          )
      logger.info(
          EVENT_SANDBOX_AUTO_DETECT_FALLBACK,
          extra={
              "selected_backend": _BACKEND_DIND,
              "reason": status,
              "platform": platform_name,
          },
      )
      cls = get_backend(_BACKEND_DIND)   # returns the class (S3-02 AC-REG-1)
      return cls()                       # zero-arg construction
  ```
  Body must not contain any string literal equal to `"firecracker"`, `"docker_in_docker"`, or any `KvmStatus` member except via the named constants (enforced by AC-PURE-5).
- [ ] **AC-C2 — Happy-path return type.** When `kvm_prober.probe()` returns `("sandbox.kvm_available", "linux")`, the returned object satisfies `isinstance(result, SandboxClient)` (runtime-checkable Protocol from S1-02). Test injects a fake `FirecrackerClient` via the `digests_yaml` / `artifacts_root` ports → wrapping the construction call site is sufficient (no need to monkey-patch the class).
- [ ] **AC-C3 — Fallback-path return type.** When `kvm_prober.probe()` returns any of the three non-available `KvmStatus` values, the returned object is an instance of `DockerInDockerClient` (`isinstance(result, DockerInDockerClient) is True`).
- [ ] **AC-C4 — Idempotency / non-cached.** Two successive `auto_detect(kvm_prober=fake)` calls return **distinct** `SandboxClient` instances (`a is not b`). The function does not memoize. Rationale: the orchestrator may resume mid-loop or a backend instance may carry per-run state.
- [ ] **AC-C5 — Selection is final; no mid-run swap.** `auto_detect` never catches `FirecrackerKvmMissing` / `FirecrackerBinaryMissing` / `FirecrackerRootfsMissing` (or any other exception from `load_pinned_digests` / `from_pinned_digests`). Construction failures propagate. Test forces `load_pinned_digests` to raise `FirecrackerBinaryMissing` (via a fake `digests_yaml` resolver) and asserts `pytest.raises(FirecrackerBinaryMissing)`.

### D. Reason-string + event-name discipline

- [ ] **AC-D1 — All four `KvmStatus` members match the CLAUDE.md namespace regex** `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Asserted programmatically: `for m in typing.get_args(KvmStatus): assert _NAMESPACE_REGEX.fullmatch(m)`.
- [ ] **AC-D2 — `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` is REUSED from S1-05** — its value is byte-exact `"sandbox.auto_detect.fallback"` (already pinned by S1-05 AC-LG-3); the import path is `codegenie.sandbox.logging`. This story does NOT redefine, rename, or shadow it. Verified by `from codegenie.sandbox.logging import EVENT_SANDBOX_AUTO_DETECT_FALLBACK; assert EVENT_SANDBOX_AUTO_DETECT_FALLBACK == "sandbox.auto_detect.fallback"`.
- [ ] **AC-D3 — `EVENT_SANDBOX_REGISTRY_SELECTED` is new.** Added to `codegenie.sandbox.logging` as `Final[str] = "sandbox.registry.selected"`. Appended to `__all__` (alphabetized). Matches the namespace regex.
- [ ] **AC-D4 — No-value-collision check.** The union of values of all `EVENT_*` constants in `codegenie.sandbox.logging` has the same cardinality as the union of names (mirror of S1-05 AC-LG-4). Adding a constant whose value collides with an existing one fails the test.

### E. Logging-emission ordering and payload shape

- [ ] **AC-E1 — Exactly one event emitted per call.** For each of the four `KvmStatus` values, `auto_detect` emits exactly one record on the `codegenie.sandbox.registry` logger at level INFO. No duplicates; no second event from a downstream constructor (the test asserts `len(records_for_logger) == 1`).
- [ ] **AC-E2 — Happy-path event payload.** When status is `"sandbox.kvm_available"`, the single emitted record has `message == EVENT_SANDBOX_REGISTRY_SELECTED` and `extra` (or record attributes via stdlib `logging` `LogRecord.__dict__`) contains `selected_backend == _BACKEND_FIRECRACKER`, `reason == "sandbox.kvm_available"`, `platform == "linux"`.
- [ ] **AC-E3 — Fallback-path event payload.** For each of the three non-available statuses, the single emitted record has `message == EVENT_SANDBOX_AUTO_DETECT_FALLBACK` and `extra` contains `selected_backend == _BACKEND_DIND`, `reason == <the status value>`, `platform == <prober's platform string>`. Parametrized over the three statuses + two platforms (`"darwin"`, `"linux"`).
- [ ] **AC-E4 — Log emitted BEFORE construction.** On the happy path, force `load_pinned_digests` to raise (inject a fake that raises `FirecrackerBinaryMissing`). Assert the `EVENT_SANDBOX_REGISTRY_SELECTED` log record was emitted BEFORE the raise — i.e., `caplog.records` contains exactly one record matching the event AND `pytest.raises(FirecrackerBinaryMissing)` fired. The assertion is order-pinning: a `finally`-block implementation would NOT emit the log when construction raises mid-statement; the AC forces emission to sit on a separate line BEFORE the construction call.
- [ ] **AC-E5 — No structured-log dependency on `structlog`.** Tests use stdlib `caplog` (`caplog.set_level(logging.INFO, logger="codegenie.sandbox.registry")`) consistent with S1-05 HARDENED. `structlog.testing.LogCapture` is NOT used here.

### F. Construction wiring

- [ ] **AC-F1 — `_DEFAULT_DIGESTS_YAML` default is the project-root-relative pin.** `_DEFAULT_DIGESTS_YAML: Final[Path] = find_project_root() / "tools" / "digests.yaml"` — same helper S6-03 HARDENED uses for `FirecrackerClient.from_project`. If `find_project_root()` returns `None` at import (e.g., outside a repo), the constant resolves to `Path("tools/digests.yaml")` (relative — fails loudly at first `auto_detect` call rather than at import).
- [ ] **AC-F2 — `_DEFAULT_ARTIFACTS_ROOT` default is `Path(".codegenie/sandbox/artifacts")`** — mirror of the S6-01 + S6-03 default.
- [ ] **AC-F3 — Firecracker construction uses `from_pinned_digests`.** `auto_detect`'s happy path call site is byte-exact `FirecrackerClient.from_pinned_digests(digests, artifacts_root=artifacts_root)` — NOT the (removed) `FirecrackerClient.from_digests_yaml(...)`, NOT the (removed) string-arg constructor. AST walker pin: no `FirecrackerClient(...)` direct construction or `FirecrackerClient.from_digests_yaml(...)` reference appears in `registry.py`.
- [ ] **AC-F4 — DinD construction uses `get_backend(_BACKEND_DIND)()`.** Calls `get_backend` (registered by S3-02 HARDENED `@register_sandbox_backend("docker_in_docker")` on `DockerInDockerClient`), receives the **class**, then instantiates with zero args (S3-02 HARDENED guarantees zero-arg-safe construction).
- [ ] **AC-F5 — Construction-error propagation enumerated.** Parametrized table: `FirecrackerBinaryMissing`, `FirecrackerKvmMissing`, `FirecrackerRootfsMissing`, `FirecrackerVmlinuxMissing` (per S6-01 + S6-03 HARDENED error set), `FileNotFoundError`, `ValidationError` (from `load_pinned_digests`). Each test injects a fake digest loader / Firecracker factory that raises the respective error and asserts `pytest.raises(<Error>)` fires from `auto_detect`. **No `except Exception:` catch-all** appears anywhere in `auto_detect`.

### G. Idempotency + determinism

- [ ] **AC-G1 — Same prober state → same selection.** Hypothesis property: for any `kvm_prober` whose `probe()` returns a fixed `(status, platform)` pair, two `auto_detect(kvm_prober=...)` calls produce instances of the same concrete class (`type(a) is type(b)`). Parametrized over the four `KvmStatus` values.
- [ ] **AC-G2 — No global state mutation.** `auto_detect` does not mutate `sandbox_backend_registry`, `_default_kvm_prober`, or any module-level dict. Verified by snapshotting `sandbox_backend_registry._backends` before and after a call: `dict_before == dict_after` (identity-equal on values).

### H. Module purity + AST guards

- [ ] **AC-PURE-1 — `from __future__ import annotations`** is the first non-docstring statement of `registry.py` (re-asserted from S1-05 AC-PURE-1).
- [ ] **AC-PURE-2 — Module docstring cites ADR-0004, ADR-0001, ADR-0043** (in addition to S1-05's ADR-0003 / ADR-0006). AST walker asserts each ADR ID substring appears in the module docstring.
- [ ] **AC-PURE-3 — `__all__` alphabetized.** AST walker on the `__all__` assignment asserts `found_all == sorted(found_all)`.
- [ ] **AC-PURE-4 — Imports restricted.** Allowed module prefixes: stdlib + `codegenie.errors`, `codegenie.sandbox.{errors, contract, logging, did.client, firecracker.client}`, `codegenie.digests`, `codegenie.types.identifiers`, `codegenie.transforms.signal_kinds` (the S1-05 delegation chain). Banned: `anthropic`, `langgraph`, `chromadb`, `sentence_transformers`, `pydantic` (registry ships no Pydantic models), `requests`, `httpx` (the network/transport ports live behind the FC + DiD DI seams, not here).
- [ ] **AC-PURE-5 — No bare backend / status string literals in function bodies.** AST walker on `auto_detect` AND `_DefaultKvmProber.probe` asserts no `ast.Constant(value="firecracker")` / `value="docker_in_docker"` and no `value` matching any `KvmStatus` member appears as a function-body string — every occurrence must be via the named `_BACKEND_*` constants or `Literal` members. Mutation: an implementer typoing `"docker-in-docker"` (kebab) fails this walker.

### I. TDD plan tests inject through the port — no monkey-patching

- [ ] **AC-TDD-1 — No `patch("codegenie.sandbox.registry.Path.exists")` / `patch("codegenie.sandbox.registry.os.access")` / `patch.object(sys, "platform", ...)` in `auto_detect` test functions.** Tests pass a `FakeKvmProber` through the `kvm_prober=` kwarg. AST walker on the test file asserts zero `mock.patch` / `monkeypatch.setattr` calls targeting `Path`, `os`, or `sys` inside `auto_detect`-named test functions. (The DEFAULT-prober tests in a separate `test_default_kvm_prober.py` DO exercise the real syscalls + the mode-arg pin — that's where the monkeypatching is allowed.)
- [ ] **AC-TDD-2 — `FakeKvmProber` is a tiny dataclass.** `class FakeKvmProber: status: KvmStatus; platform: str; probe_call_count: int = 0; def probe(self): self.probe_call_count += 1; return (self.status, self.platform)`. Tests instantiate per-case; assertions on `probe_call_count == 1` pin the short-circuit semantics.
- [ ] **AC-TDD-3 — Five parametrized cases for `auto_detect`:** (1) `("sandbox.kvm_available", "linux")` → Firecracker, `EVENT_SANDBOX_REGISTRY_SELECTED` logged; (2) `("sandbox.kvm_missing", "linux")` → DinD, `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` logged with `reason="sandbox.kvm_missing"`; (3) `("sandbox.kvm_not_accessible", "linux")` → DinD, fallback logged with that reason; (4) `("sandbox.platform_not_linux", "darwin")` → DinD, fallback logged with that reason; (5) idempotency — call twice, assert two distinct instances.
- [ ] **AC-TDD-4 — Default-prober tests in `tests/sandbox/test_default_kvm_prober.py`** — five cases: (a) `sys.platform == "darwin"` → `("sandbox.platform_not_linux", "darwin")` AND `Path.exists` + `os.access` spies have `call_count == 0`; (b) `sys.platform == "linux"` + `Path("/dev/kvm").exists() is False` → `("sandbox.kvm_missing", "linux")`; (c) `sys.platform == "linux"` + Path exists + `os.access` returns `False` → `("sandbox.kvm_not_accessible", "linux")`; (d) `sys.platform == "linux"` + Path exists + `os.access` raises `PermissionError` → `("sandbox.kvm_not_accessible", "linux")`; (e) `sys.platform == "linux"` + Path exists + `os.access` returns `True` → `("sandbox.kvm_available", "linux")` AND assert `os.access` was called with mode `os.R_OK | os.W_OK`.
- [ ] **AC-TDD-5 — Log-before-construction test.** Injects a fake `digests_yaml=tmp_path/"bad.yaml"` resolver + a fake `FirecrackerClient.from_pinned_digests` that raises `FirecrackerBinaryMissing` (via constructor-injected port). Asserts: `pytest.raises(FirecrackerBinaryMissing)` AND `caplog` contains exactly one `EVENT_SANDBOX_REGISTRY_SELECTED` record emitted BEFORE the raise. **Implementation note:** to inject the FC factory, the test patches the `from_pinned_digests` classmethod on `FirecrackerClient` (one allowed exception to AC-TDD-1, scoped narrowly to this single test — the rationale is the factory is the construction port itself and the alternative would be widening `auto_detect`'s public signature with yet another DI port, which Rule 2 rejects).

### J. Process gates

- [ ] **AC-PG-1 — `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/sandbox/registry.py`** all exit 0.
- [ ] **AC-PG-2 — `pytest tests/sandbox/test_auto_detect.py tests/sandbox/test_default_kvm_prober.py tests/sandbox/test_registry.py tests/sandbox/test_registry_purity.py`** all green (the last two are S1-05's; this story's additions must not break them).
- [ ] **AC-PG-3 — Coverage floor:** line ≥ 95% AND branch ≥ 90% on the **new + edited code** in `src/codegenie/sandbox/registry.py` (`auto_detect`, `_DefaultKvmProber`, `KvmProber`, `KvmStatus`). Matches the S1-05 / S3-02 / S6-01 / S6-03 phase-5 standard.
- [ ] **AC-PG-4 — No new dependencies.** `pyproject.toml` and `uv.lock` are byte-identical to pre-story state. No `subprocess` calls; no new external binaries.

### K. Forward seams + maintainability

- [ ] **AC-K1 — `KvmStatus` widens additively.** Module docstring documents: "New backend kinds (Phase 7 gVisor; Phase 7.5 third backend) add a new `Literal` member to `KvmStatus` (or a sibling sum type if the probe is unrelated to KVM) — never edit an existing member." Pinned in the module docstring; AST walker checks the docstring substring.
- [ ] **AC-K2 — `_BACKEND_*` constants extend via S1-02 `SandboxRun.backend` Literal widening.** When Phase 7 adds the third backend, the closed-Literal mirror on `SandboxRun.backend` widens via ADR-0001 amendment; this story's `_BACKEND_*` constants gain a sibling at that point. Documented in Notes.

## Implementation outline

1. **Edit `src/codegenie/sandbox/registry.py`** (existing file from S1-05; do not create a new module):
   - Update the module docstring to additionally cite ADR-0004, ADR-0001, ADR-0043.
   - Add stdlib imports: `os`, `sys`, `from pathlib import Path`, `from typing import Final, Literal, Protocol, runtime_checkable, get_args`.
   - Add project imports: `from codegenie.sandbox.contract import SandboxClient`, `from codegenie.sandbox.did.client import DockerInDockerClient` (TYPE_CHECKING-only OK if circularity bites; the runtime `isinstance` check in AC-C3 is the only true dependency), `from codegenie.sandbox.firecracker.client import FirecrackerClient`, `from codegenie.digests import load_pinned_digests`, `from codegenie.utils.paths import find_project_root` (or wherever S6-03 placed it), `from codegenie.sandbox.logging import EVENT_SANDBOX_AUTO_DETECT_FALLBACK, EVENT_SANDBOX_REGISTRY_SELECTED`.
   - Add `KvmStatus = Literal[...]` (the four namespaced members) and the `_NAMESPACE_REGEX` self-check (run once at module import via `for m in get_args(KvmStatus): if not _NAMESPACE_REGEX.fullmatch(m): raise CodegenieError(...)` — fail-loud on a future typo).
   - Add `@runtime_checkable class KvmProber(Protocol): ...` and `class _DefaultKvmProber: ...` and `_default_kvm_prober: Final[KvmProber] = _DefaultKvmProber()`.
   - Add `_BACKEND_FIRECRACKER`, `_BACKEND_DIND`, `_DEFAULT_DIGESTS_YAML`, `_DEFAULT_ARTIFACTS_ROOT` module-level `Final` constants.
   - **Replace** the S1-05-stub `auto_detect()` body with the AC-C1 shape (preserves the function name + the signature additively widens via keyword-only ports with defaults — no caller breakage).
   - Update `__all__` additively: alphabetize the union of S1-05's names + the three new public names (`auto_detect` already present from S1-05 stub; the new ones are `KvmProber`, `KvmStatus`).
2. **Edit `src/codegenie/sandbox/logging.py`** — append one row to S1-01's canonical constants table:
   ```python
   EVENT_SANDBOX_REGISTRY_SELECTED: Final[str] = "sandbox.registry.selected"
   ```
   Update `__all__` (alphabetized). S1-05's `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` is reused unchanged.
3. **Create `tests/sandbox/test_auto_detect.py`** — five parametrized cases per AC-TDD-3 + the log-before-construction test (AC-TDD-5) + the no-monkey-patch AST walker (AC-TDD-1) + the construction-error propagation table (AC-F5).
4. **Create `tests/sandbox/test_default_kvm_prober.py`** — five cases per AC-TDD-4 (the only place where `os.access` / `Path.exists` / `sys.platform` are exercised — and they're exercised against the REAL syscalls + spies, not the registry-module mocks the draft pattern used).
5. **Re-run** `tests/sandbox/test_registry.py` (from S1-05) — it must stay green; the S1-05 stub `auto_detect()` test (`test_auto_detect_returns_sandbox_client_AC_AD_2`) gets superseded by the new tests in this story but its **assertion** (returns a `SandboxClient` when `docker_in_docker` is registered + emits the fallback log) is now covered by AC-C3 + AC-E3 case 4 (`sandbox.platform_not_linux` → DinD). Update or delete the superseded test if it relies on the old "always falls back" semantics; document the change in the S1-05 attempt log if applicable.
6. **Update story status** in this file to `Ready (HARDENED 2026-05-25)` — already done by this validation pass.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/sandbox/test_auto_detect.py
"""auto_detect — AC-A*, AC-B*, AC-C*, AC-D*, AC-E*, AC-F*, AC-G*, AC-TDD-*."""
from __future__ import annotations

import ast
import logging as _logging
import pathlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from codegenie.sandbox.contract import SandboxClient
from codegenie.sandbox.did.client import DockerInDockerClient
from codegenie.sandbox.firecracker.client import FirecrackerClient
from codegenie.sandbox.errors import (
    FirecrackerBinaryMissing,
    FirecrackerKvmMissing,
    FirecrackerRootfsMissing,
)
from codegenie.sandbox.logging import (
    EVENT_SANDBOX_AUTO_DETECT_FALLBACK,
    EVENT_SANDBOX_REGISTRY_SELECTED,
)
from codegenie.sandbox.registry import (
    KvmProber,
    KvmStatus,
    auto_detect,
)

_LOGGER_NAME = "codegenie.sandbox.registry"
_NS_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass
class FakeKvmProber:
    """AC-TDD-2 — minimal `KvmProber` impl for injection."""
    status: KvmStatus
    platform: str = "linux"
    probe_call_count: int = 0

    def probe(self) -> tuple[KvmStatus, str]:
        self.probe_call_count += 1
        return (self.status, self.platform)


# ---------- AC-D1 — namespace regex on every KvmStatus member ----------
def test_every_kvm_status_member_matches_namespace_regex_AC_D1():
    import typing
    members = typing.get_args(KvmStatus)
    assert len(members) == 4
    for m in members:
        assert _NS_RE.fullmatch(m), f"{m!r} violates CLAUDE.md regex"


# ---------- AC-D2 — reuse of S1-05 constant ----------
def test_fallback_event_constant_reused_from_S1_05_AC_D2():
    assert EVENT_SANDBOX_AUTO_DETECT_FALLBACK == "sandbox.auto_detect.fallback"


# ---------- AC-D3 — new constant ----------
def test_registry_selected_event_constant_AC_D3():
    assert EVENT_SANDBOX_REGISTRY_SELECTED == "sandbox.registry.selected"


# ---------- AC-C3 + AC-E3 — fallback paths × three statuses × two platforms ----------
@pytest.mark.parametrize(
    "status,platform",
    [
        ("sandbox.kvm_missing", "linux"),
        ("sandbox.kvm_not_accessible", "linux"),
        ("sandbox.platform_not_linux", "darwin"),
    ],
)
def test_fallback_returns_dind_and_logs_AC_C3_AC_E3(caplog, status, platform):
    caplog.set_level(_logging.INFO, logger=_LOGGER_NAME)
    fake = FakeKvmProber(status=status, platform=platform)
    client = auto_detect(kvm_prober=fake)
    assert isinstance(client, DockerInDockerClient)
    assert fake.probe_call_count == 1
    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert len(records) == 1
    rec = records[0]
    assert rec.message == EVENT_SANDBOX_AUTO_DETECT_FALLBACK
    assert getattr(rec, "selected_backend") == "docker_in_docker"
    assert getattr(rec, "reason") == status
    assert getattr(rec, "platform") == platform


# ---------- AC-C2 + AC-E2 — happy path returns Firecracker + selection event ----------
def test_happy_path_returns_firecracker_and_logs_selection_AC_C2_AC_E2(
    caplog, monkeypatch, tmp_path
):
    caplog.set_level(_logging.INFO, logger=_LOGGER_NAME)
    fake_fc = object()   # sentinel — duck-typed; we assert is-identity below
    monkeypatch.setattr(
        "codegenie.sandbox.firecracker.client.FirecrackerClient.from_pinned_digests",
        classmethod(lambda cls, digests, *, artifacts_root: fake_fc),
    )
    monkeypatch.setattr(
        "codegenie.sandbox.registry.load_pinned_digests",
        lambda *, digests_yaml: object(),
    )
    fake = FakeKvmProber(status="sandbox.kvm_available", platform="linux")
    result = auto_detect(
        kvm_prober=fake,
        digests_yaml=tmp_path / "digests.yaml",
        artifacts_root=tmp_path / "artifacts",
    )
    assert result is fake_fc
    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert len(records) == 1
    rec = records[0]
    assert rec.message == EVENT_SANDBOX_REGISTRY_SELECTED
    assert getattr(rec, "selected_backend") == "firecracker"
    assert getattr(rec, "reason") == "sandbox.kvm_available"
    assert getattr(rec, "platform") == "linux"


# ---------- AC-E4 — log emitted BEFORE construction failure ----------
def test_log_emitted_before_construction_failure_AC_E4(
    caplog, monkeypatch, tmp_path
):
    caplog.set_level(_logging.INFO, logger=_LOGGER_NAME)

    def _raising_factory(cls, digests, *, artifacts_root):
        raise FirecrackerBinaryMissing(reason="sandbox.firecracker.binary_digest_mismatch")

    monkeypatch.setattr(
        "codegenie.sandbox.firecracker.client.FirecrackerClient.from_pinned_digests",
        classmethod(_raising_factory),
    )
    monkeypatch.setattr(
        "codegenie.sandbox.registry.load_pinned_digests",
        lambda *, digests_yaml: object(),
    )
    fake = FakeKvmProber(status="sandbox.kvm_available", platform="linux")
    with pytest.raises(FirecrackerBinaryMissing):
        auto_detect(
            kvm_prober=fake,
            digests_yaml=tmp_path / "digests.yaml",
            artifacts_root=tmp_path / "artifacts",
        )
    records = [r for r in caplog.records
               if r.name == _LOGGER_NAME and r.message == EVENT_SANDBOX_REGISTRY_SELECTED]
    assert len(records) == 1, "selection log must be emitted BEFORE the construction call raises"


# ---------- AC-F5 — construction-error propagation table ----------
@pytest.mark.parametrize(
    "err_cls",
    [FirecrackerBinaryMissing, FirecrackerKvmMissing, FirecrackerRootfsMissing],
)
def test_no_silent_fallback_on_construction_failure_AC_F5(
    monkeypatch, tmp_path, err_cls
):
    monkeypatch.setattr(
        "codegenie.sandbox.firecracker.client.FirecrackerClient.from_pinned_digests",
        classmethod(lambda cls, digests, *, artifacts_root:
                    (_ for _ in ()).throw(err_cls(reason="sandbox.kvm_missing"))),
    )
    monkeypatch.setattr(
        "codegenie.sandbox.registry.load_pinned_digests",
        lambda *, digests_yaml: object(),
    )
    fake = FakeKvmProber(status="sandbox.kvm_available", platform="linux")
    with pytest.raises(err_cls):
        auto_detect(
            kvm_prober=fake,
            digests_yaml=tmp_path / "digests.yaml",
            artifacts_root=tmp_path / "artifacts",
        )


# ---------- AC-C4 — idempotency, no caching ----------
def test_auto_detect_returns_distinct_instances_AC_C4():
    fake = FakeKvmProber(status="sandbox.kvm_missing", platform="linux")
    a = auto_detect(kvm_prober=fake)
    b = auto_detect(kvm_prober=fake)
    assert a is not b
    assert type(a) is type(b) is DockerInDockerClient


# ---------- AC-G1 — determinism property ----------
@given(status=st.sampled_from(["sandbox.kvm_missing",
                                "sandbox.kvm_not_accessible",
                                "sandbox.platform_not_linux"]))
def test_same_prober_state_same_class_AC_G1(status):
    fake = FakeKvmProber(status=status, platform="linux")
    a = auto_detect(kvm_prober=fake)
    b = auto_detect(kvm_prober=fake)
    assert type(a) is type(b)


# ---------- AC-TDD-1 — no monkeypatching of Path/os/sys inside this test file ----------
def test_no_monkeypatch_of_path_os_sys_in_this_file_AC_TDD_1():
    """AST walker — banned patterns in auto_detect tests."""
    src = pathlib.Path(__file__).read_text()
    tree = ast.parse(src)
    banned_targets = {"Path", "os", "sys", "Path.exists", "os.access"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "setattr":
                # monkeypatch.setattr / mock.patch.object → check first arg
                if node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        s = first.value
                        for b in banned_targets:
                            assert b not in s, (
                                f"monkey-patching {s!r} forbidden in auto_detect tests; "
                                f"use FakeKvmProber via kvm_prober=... instead (AC-TDD-1)"
                            )
            if isinstance(func, ast.Attribute) and func.attr == "patch":
                if node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        s = first.value
                        for b in banned_targets:
                            assert b not in s, (
                                f"mock.patch({s!r}) forbidden in auto_detect tests (AC-TDD-1)"
                            )
```

```python
# tests/sandbox/test_default_kvm_prober.py
"""_DefaultKvmProber — AC-B*, AC-TDD-4."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegenie.sandbox.registry import KvmProber, _default_kvm_prober


def test_default_kvm_prober_is_kvm_prober_AC_B3():
    assert isinstance(_default_kvm_prober, KvmProber)


def test_macos_short_circuits_path_and_access_AC_B7(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    path_exists_spy = MagicMock(return_value=True)
    os_access_spy = MagicMock(return_value=True)
    monkeypatch.setattr(Path, "exists", path_exists_spy)
    monkeypatch.setattr(os, "access", os_access_spy)
    status, platform = _default_kvm_prober.probe()
    assert status == "sandbox.platform_not_linux"
    assert platform == "darwin"
    assert path_exists_spy.call_count == 0
    assert os_access_spy.call_count == 0


def test_linux_no_kvm_returns_missing_AC_TDD_4b(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "exists", lambda self: False)
    status, platform = _default_kvm_prober.probe()
    assert status == "sandbox.kvm_missing"
    assert platform == "linux"


def test_linux_kvm_present_not_accessible_AC_TDD_4c(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(os, "access", lambda path, mode: False)
    status, _ = _default_kvm_prober.probe()
    assert status == "sandbox.kvm_not_accessible"


def test_linux_kvm_access_raises_AC_B5_AC_TDD_4d(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    def _raise(path, mode):
        raise PermissionError("denied")
    monkeypatch.setattr(os, "access", _raise)
    status, _ = _default_kvm_prober.probe()
    assert status == "sandbox.kvm_not_accessible"


def test_linux_kvm_available_and_mode_pinned_to_R_OK_W_OK_AC_B6_AC_TDD_4e(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "exists", lambda self: True)
    calls: list[tuple[object, int]] = []
    def _record(path, mode):
        calls.append((path, mode))
        return True
    monkeypatch.setattr(os, "access", _record)
    status, _ = _default_kvm_prober.probe()
    assert status == "sandbox.kvm_available"
    assert len(calls) == 1
    _, mode = calls[0]
    assert mode == os.R_OK | os.W_OK, (
        "AC-B6: default prober must request both read + write; "
        "a weaker mode (e.g. R_OK only) would silently pass earlier drafts."
    )
```

Run the new test files; confirm `ImportError` / `AttributeError` / red. Commit red. Then implement.

### Green — make it pass

Implement per the Implementation outline — exactly the AC-C1 body shape; `_DefaultKvmProber.probe()` exactly the AC-B4 body shape. Three pitfalls (fail-loud, NOT silent):

- **Do not catch any exception from `load_pinned_digests` / `from_pinned_digests`** — AC-F5 forces propagation. A defensive `except Exception` would silently degrade to DinD on Firecracker construction failure, invalidating the audit chain (S2-01) and `gate_isolation_class` (ADR-0004).
- **Emit the selection log BEFORE the construction call**, on its own statement. AC-E4 tests this against forced construction failure.
- **Use the `_BACKEND_FIRECRACKER` / `_BACKEND_DIND` `Final` constants** everywhere in the function body — never inline string literals. AC-PURE-5 AST walker pins it.

### Refactor — clean up

- Module docstring: append paragraph naming ADR-0004, ADR-0001, ADR-0043 and the S1-05 stub-replacement lineage.
- Pull the `_DEFAULT_DIGESTS_YAML` resolution into a module-level helper that handles `find_project_root() is None` gracefully (fall back to `Path("tools/digests.yaml")`). Document in Notes.
- Add a single sentence docstring on `auto_detect` citing ADR-0004 + the on-macOS fallback contract.
- Move the `_NAMESPACE_REGEX` self-check into a module-level `_assert_kvm_status_namespace_regex()` that runs at import time — fail-loud on a future typo (a contributor adding a non-namespaced status member crashes at module load, before any test runs).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/registry.py` | EDIT — replace S1-05-stub `auto_detect` body; add `KvmStatus`, `KvmProber`, `_DefaultKvmProber`, `_default_kvm_prober`, `_BACKEND_*` and `_DEFAULT_*` constants; widen module docstring + `__all__` + imports additively. |
| `src/codegenie/sandbox/logging.py` | EDIT — append `EVENT_SANDBOX_REGISTRY_SELECTED: Final[str] = "sandbox.registry.selected"`; update `__all__` (alphabetized). Reuses S1-05's `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` unchanged. |
| `tests/sandbox/test_auto_detect.py` | New — AC-D*, AC-C2/3/4, AC-E2/3/4, AC-F5, AC-G1, AC-TDD-1/2/3/5. |
| `tests/sandbox/test_default_kvm_prober.py` | New — AC-B3/5/6/7, AC-TDD-4. The ONLY file where `Path.exists` / `os.access` / `sys.platform` are monkey-patched; the default prober is exercised directly. |
| `tests/sandbox/test_registry.py` | Possibly EDIT — S1-05's `test_auto_detect_returns_sandbox_client_AC_AD_2` and `test_auto_detect_raises_when_docker_in_docker_missing_AC_AD_4` were written against the stub; their assertions are superseded by AC-C3 + AC-E3 case 4 here. Coordinate: either keep them green by ensuring `docker_in_docker` is registered + the prober defaults to a non-Linux platform on CI, or supersede them with a short note in `_attempts/S6-04.md`. |

## Out of scope

- Orchestrator wiring of `--sandbox-backend auto` → `auto_detect()` — **S8-02**.
- `codegenie sandbox health` surfacing `auto_detect_dry_run` — **S8-01**. The wishy-washy "Consider exposing" line from the draft Refactor section is explicitly removed; do NOT ship `auto_detect_dry_run` in this story (Rule 2 — no premature abstraction).
- KVM-gated integration smoke test — **S6-05**.
- Firecracker construction errors during health checks — surfaced by S6-01 / S6-03; this story propagates them, does not handle them.
- Allowing operators to *force* Firecracker on a non-KVM host via env-var fallback — explicit non-goal; the CLI `--sandbox-backend firecracker` is the override (S8-02).
- WSL2-specific test fixture — implicitly covered by the Linux+`sandbox.kvm_available` test path (WSL2's `sys.platform == "linux"`).
- A shared `_default_*_port` kernel-extract across DI ports — deferred (the divergent port shapes argue against the extract; revisit when Phase 7 adds the third backend).

## Notes for the implementer

- **`KvmProber` is the sixth concrete consumer of the Phase-5 Hexagonal-DI port pattern** (S3-01 `filter_fn` / `host_env_source` / `catalog`; S3-02 `docker_factory`; S3-06 `backend_provider`/`policy_path_resolver`/`digest_loader`; S6-01 `api_socket_factory` / `process_handle_factory` / `vsock_exec_port`; S6-03 `fs: FsPort`). Long past the rule-of-three threshold; **resisting the pattern here would silently retire it**. Mirror the S3-06 `backend_provider` shape exactly.
- **`KvmStatus` is a closed `Literal`, not an enum.** Codebase convention (S1-02 / S6-01 / S6-03) prefers `Literal` for closed sum-type discriminators because it composes with Pydantic's discriminator-tag tooling and mypy `--strict` narrowing. Reaching for `enum.StrEnum` here would diverge.
- **No `from_digests_yaml` anywhere.** S6-03 HARDENED removed it (not `_internal`-tagged — actually removed). Use `FirecrackerClient.from_pinned_digests(load_pinned_digests(digests_yaml=...), artifacts_root=...)`. The convenience `FirecrackerClient.from_project(...)` from S6-03 AC-FACTORY-4 is the CLI's path — this story explicitly does NOT use it because we want the `digests_yaml=` / `artifacts_root=` ports exposed for tests.
- **`get_backend` returns the class, not an instance.** S3-02 HARDENED AC-REG-1 pins `get_backend("docker_in_docker") is DockerInDockerClient`. S1-05's "fresh instance" framing is the contradicting older statement — for this story we follow S3-02 HARDENED (the more recent contract). DinD construction is `get_backend(_BACKEND_DIND)()` — works because `DockerInDockerClient.__init__` has all-default kwargs.
- **`os.access` is *advisory* under POSIX** — it answers the access question for the *real* (not effective) user, and on some systems can return `True` while the open still fails. We accept the imprecision: `auto_detect` is a hint, `FirecrackerClient._assert_kvm()` (S6-01) is the authoritative gate. Do not bolt on a second check here.
- **The selection log MUST be emitted BEFORE the construction call**, on a separate statement. A `finally:`-block implementation would NOT emit the log when `FirecrackerClient.from_pinned_digests(...)` raises mid-statement; AC-E4 forces emission to happen first. This is the operator's only signal that auto-detect selected Firecracker when construction subsequently fails.
- **Do not catch any exception in `auto_detect`.** The default `KvmProber.probe()` is total (`AC-B5` — `OSError` / `PermissionError` from `os.access` are folded into `"sandbox.kvm_not_accessible"` inside the prober, not in `auto_detect`). Beyond that, every error from `load_pinned_digests` / `from_pinned_digests` propagates. A wider catch in `auto_detect` hides real bugs and would re-introduce the mid-run-swap pattern ADR-0004 forbids.
- **The four `reason` strings are part of the structured-logging contract** — they will be grepped by operators and ingested by Phase 13's cost dashboard. They are pinned by the `KvmStatus` Literal; an implementer adding a fifth without updating the Literal fails mypy `--strict`.
- **`structlog.testing.LogCapture` is NOT used here.** S1-05 HARDENED established `caplog.set_level(_stdlib_logging.INFO, logger="codegenie.sandbox.registry")` as the canonical Phase-5 test idiom. The draft's `structlog.testing.LogCapture` is inconsistent.
- **Resist building a "tier" system** (try Firecracker → on `FirecrackerKvmMissing` swap to DinD mid-run). The decision is made once at `auto_detect` time and is final. Mid-run swaps would invalidate the audit chain (S2-01) and `gate_isolation_class` annotation (ADR-0004). AC-F5 + AC-C5 lock this.
- **`sys.platform` is `"linux"` on every Linux distro (including WSL2** — which does have KVM through Hyper-V's hypervisor-platform feature). The default prober checks `sys.platform != "linux"`; WSL2 falls into the Linux branch and gets the `Path("/dev/kvm").exists()` check. Do NOT switch to `platform.system()` — `sys.platform` is the project-standard discriminator.
- **`KvmStatus` widens additively.** Phase 7 gVisor / Phase 7.5 third backend may add new probe outcomes (`sandbox.gvisor_misconfigured`, `sandbox.kvm_locked_by_other_vmm`, etc.). The convention: add a new `Literal` member, add a new `if status == ...` branch in `auto_detect` (or pattern-match), add `_BACKEND_*` constant sibling. Never edit an existing member.
- **Kernel-extract for shared DI-port defaults is tempting** (`_default_kvm_prober` is the seventh DI-port default in the phase) but **deferred** — the divergent port shapes (kvm probe vs digest loader vs docker factory vs api socket factory) still argue against the extract. Revisit when the eighth or ninth lands.
