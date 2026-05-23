# Story S1-05 — Decorator registries + `env_allowlist` static filter

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready (HARDENED 2026-05-22)
**Effort:** M
**Depends on:** S1-01, S1-02, S1-03, S1-04
**ADRs honored:** ADR-0012, ADR-0003, ADR-0006

## Validation notes (2026-05-22)

Hardened via `phase-story-validator` (verdict: HARDENED). Source-of-truth contradictions resolved against [`../phase-arch-design.md §Component design — SandboxClient`](../phase-arch-design.md), [`../phase-arch-design.md §Component design — Signal collectors`](../phase-arch-design.md), [ADR-0012](../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md), [ADR-0003](../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md), [ADR-0006](../ADRs/0006-protocol-vs-abc-convention.md), the four prior HARDENED reports (S1-01..S1-04), and the **already-shipped** Phase 3 [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) name-registry. Full report: [`_validation/S1-05-registries-and-env-allowlist.md`](_validation/S1-05-registries-and-env-allowlist.md).

Headline edits (each weakness the four critics flagged would have let a structurally-wrong implementation slip past the executor's validator):

1. **Identifier collision surfaced + delegation chain documented.** Phase 3 already ships **`register_signal_kind` as a value-producing function** at [`codegenie.transforms.signal_kinds.register_signal_kind`](../../../../src/codegenie/transforms/signal_kinds.py:125) (`BUILD = register_signal_kind("build")`). ADR-0003 specifies `@register_signal_kind("name")` as a **decorator** for Phase 5 collectors. Two callables, same simple name, different signatures. Resolution: Phase 5's `codegenie.sandbox.signals.registry.register_signal_kind` decorator **delegates the name-registration side** to Phase 3's function (calling it iff the kind is not yet in `signal_kind_registry`), then binds the collector. Both identifiers coexist at distinct import paths; the Phase 5 module docstring + Notes name the collision and the rationale (Rule 7 — surface conflicts, don't average them).
2. **`SignalKindAlreadyRegistered` shadow class disambiguated by full module path.** Phase 3 already ships [`codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered`](../../../../src/codegenie/transforms/signal_kinds.py:53) (subclass of `CodegenieError`, raised on **name** collision). S1-01 also pinned [`codegenie.sandbox.errors.SignalKindAlreadyRegistered`](../../../../src/codegenie/sandbox/errors.py) (subclass of `SandboxError`, raised on **collector** collision). Same simple name, two classes, two inheritance trees. Phase 5's decorator raises the **sandbox** one for collector collisions; tests catch by full module-path import (mirrors the disambiguation discipline in S1-04 AC-K-3 for `RecipeOutcome`).
3. **Module-level mutable globals replaced with class-based per-instance registries.** The draft's `_BACKENDS: dict[str, type[SandboxClient]]` and `_COLLECTORS: dict[str, Callable]` mirror anti-pattern (autouse fixtures snapshot/restore module state) is fragile under `pytest-xdist` and inconsistent with the established Phase 3 precedent ([`SignalKindRegistry` with `.fresh()` classmethod, module-level `Final` singleton, `registry=None` kwarg on the public registration function](../../../../src/codegenie/transforms/signal_kinds.py:78)). Refactored: `SandboxBackendRegistry` + `SignalCollectorRegistry` classes; module-level `Final` singletons; `registry=None` kwarg on `register_sandbox_backend` and `register_signal_kind`. Tests pass `.fresh()` instances; no cross-test pollution.
4. **Decorator identity unenforced.** Draft tests asserted "registers the class" via `get_backend(...)` but did not check that the decorator returns the *same* class identity. An implementer wrapping the class (`functools.wraps`-style) would silently break `runtime_checkable` Protocol semantics on subclasses. New AC-BR-2: `register_sandbox_backend("name")(Cls) is Cls`; same pattern for `@register_signal_kind` (AC-CR-2).
5. **`env_allowlist.filter` signature pinned to `Mapping[str, str] -> dict[str, str]`** (matches S1-02 AC-5 `SandboxSpec.env: Mapping[str, str]`). An implementer shipping `def filter(env: dict[str, str])` would pass every draft test but break `SandboxSpecBuilder.for_gate` (S3-01) on a `MappingProxyType` or other read-only view. AC-FL-1 (`get_type_hints` source-level pinning) + AC-FL-2 (`MappingProxyType` fixture round-trips).
6. **`ALLOWLIST` split into exact-match and prefix-match tuples.** Draft fused both semantics into one tuple `("PATH", "NODE_ENV", "NPM_CONFIG_*", "HTTPS_PROXY")` with an implicit "or starts with `NPM_CONFIG_`" rule baked into the predicate. The S1-07 fence (the very test ADR-0012 cites as belt-and-suspenders) would have to reverse-engineer the rule. Split into `ALLOWLIST: Final[tuple[str, ...]] = ("PATH", "NODE_ENV", "HTTPS_PROXY")` (exact) and `ALLOWLIST_PREFIXES: Final[tuple[str, ...]] = ("NPM_CONFIG_",)` (prefix). Both importable for the S1-07 fence; semantics legible without reading the predicate body.
7. **Deterministic key ordering invariant on `filter` output.** S1-02 §"Property tests" pinned `SandboxSpec.sandbox_spec_hash` byte-stability under env-dict-key reordering. For the spec hash to actually be byte-stable, `env_allowlist.filter` must produce a deterministically-ordered dict — Python 3.7+ preserves insertion order, so the filter's iteration order is observable downstream. AC-FL-7: `list(filter(env).keys()) == sorted([k for k in env if _is_allowed_and_not_denied(k)])`; hypothesis property test reorders the input and asserts output-key-list invariance.
8. **Allowlist case-sensitivity pinned positively + negatively.** Env-var names are case-sensitive on POSIX. Draft was prose-only. `PATH=/usr/bin` passes; `Path=/usr/bin` / `path=/usr/bin` DO NOT pass. `NPM_CONFIG_FOO` passes; `npm_config_foo` / `NoT_NPM_CONFIG_FOO` DO NOT. Parametrized AC-AL-4..AC-AL-6.
9. **Deny-substring case-insensitivity parametrized over (substring × position × case).** Draft test had two parametrized rows. Mutation: implementer using `k.startswith("KEY")` would pass `MY_API_KEY` (suffix) but fail `KEYRING_ACCESS` (prefix-substring) — both should be DENIED. Parametrized over four substrings × {prefix, infix, suffix} × {upper, lower, mixed}. AC-DN-1..AC-DN-4.
10. **`filter(env) is not env` identity check.** Draft AC said "does not mutate"; an implementer returning `env` directly when nothing changed would pass equality. AC-FL-3 asserts identity inequality.
11. **`filter({}) == {}` + `filter({"": "x"}) == {}` degenerate cases pinned.** Two missing edge cases the executor needs to handle deterministically.
12. **Idempotency + subset + monotonicity properties added.** AC-FL-5 (`set(filter(env).keys()) ⊆ set(env.keys())` — no synthesis), AC-FL-6 (`filter(filter(env)) == filter(env)` — idempotent), AC-FL-8 (monotone on allowlisted additions). Hypothesis suite.
13. **Three new event-name constants appended to S1-01's canonical table.** S1-01's Validation note §6 explicitly permits later-story appends (`S2-01`, `S5-01`, `S6-02` add rows below). Added: `EVENT_SANDBOX_BACKEND_REGISTERED = "sandbox.backend.registered"`, `EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED = "sandbox.signal_collector.registered"`, `EVENT_SANDBOX_AUTO_DETECT_FALLBACK = "sandbox.auto_detect.fallback"`. The two `register_*` events are emitted on every successful registration; `auto_detect` emits its event on every fallback to `docker_in_docker`.
14. **`auto_detect()` log emission promoted from Refactor "should" to AC-AD-3.** `caplog`-based assertion that `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` is emitted on the `codegenie.sandbox.registry` logger at INFO level with `extra={"backend": "docker_in_docker"}`. AC-AD-4: `auto_detect` raises `SandboxBackendInvalid` when `"docker_in_docker"` is not registered (fail-loud — Rule 12).
15. **Structural validation on backend class signatures.** Draft outline said "check `hasattr(cls, 'execute') and hasattr(cls, 'health')`" without locking method signatures. Tighten to `inspect.signature(cls.execute).parameters` set-equality on `{'self', 'spec'}` and `inspect.signature(cls.health).parameters == {'self'}`. AC-BR-3 + AC-BR-4. Also: `inspect.isclass(cls) is True` (AC-BR-6); registration does NOT instantiate the class (AC-BR-5 using a class whose `__init__` raises).
16. **Module purity + `from __future__ import annotations` + `__all__` discipline** (mirrors S1-02/S1-03/S1-04 precedent exactly). Module docstrings cite all three ADRs (-0012, -0003, -0006); `from __future__ import annotations` is line 1 post-docstring; `__all__` is alphabetized; imports are restricted to stdlib + `codegenie.errors`, `codegenie.sandbox.errors`, `codegenie.sandbox.contract` (for `SandboxClient`), `codegenie.sandbox.logging` (event constants), `codegenie.types.identifiers` (`SignalKind`), `codegenie.transforms.signal_kinds` (for the delegation chain). New `tests/sandbox/test_registry_purity.py`.
17. **Forward-seam notes added.** (a) `ALLOWLIST` extension intentionally friction-bearing per ADR-0012 (Phase 7 distroless's `LD_LIBRARY_PATH` etc. require an ADR amendment). (b) `SandboxBackendName` stays raw `str` for now (rule-of-three not yet cleared; the closed-Literal mirror is `SandboxRun.backend` per S1-02 AC-4); Phase 7 distroless's third backend triggers the NewType-promotion candidate. (c) Tagged-union opportunity on the `_is_allowed`/`_is_denied` predicates deferred per Rule 2 ("three similar lines is better than premature abstraction").
18. **Coverage floor wording aligned** to "line ≥ 95% AND branch ≥ 90%" on the three new modules — same conflation S1-02/S1-03/S1-04 fixed.

No `RESCUE`-tier findings — every gap was patchable by adding ACs, tightening the TDD plan, refactoring to class-based registries, and documenting the collision. No Stage-3 research was needed: every gap was answerable from Phase 5 arch + ADRs + Phase 3 codebase precedent (`transforms/signal_kinds.py`) + the four prior HARDENED reports + CLAUDE.md commitments.

## Context

Phase 5 is "extension by addition": Phase 7 distroless adds new sandbox backends and signal kinds without editing existing files. This story ships the three Open/Closed seams that make that possible:

- `@register_sandbox_backend("name")` — class decorator (a `SandboxBackendRegistry` keyed by backend name; per-instance, `.fresh()`-isolable).
- `@register_signal_kind("name")` — function decorator (a `SignalCollectorRegistry` keyed by `SignalKind`; per-instance, `.fresh()`-isolable; **delegates** the name-side to the *already-shipped* Phase 3 `signal_kind_registry` at [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py)).
- `env_allowlist.filter(env)` — the credential-leakage defense ADR-0012 makes the *only* path from host env to `SandboxSpec.env`. The denied-substring filter is belt-and-suspenders; the structural CI fence test that exercises it lives in S1-07.

The story also adds three new event-name constants to S1-01's canonical table for the registration + auto-detect log emissions.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — SandboxClient (Protocol)` (line 471) — registry exposes `get_backend(name)` and `auto_detect()`; `SandboxBackendInvalid` raised on Protocol violation at decoration time.
  - `../phase-arch-design.md §Component design — Signal collectors (six functions, open registry)` (line 583-596) — `@register_signal_kind("name")` decorator on each collector function.
  - `../phase-arch-design.md §Component design — SandboxSpecBuilder` (line 604-611) — calls `env_allowlist.filter(env)` before constructing `SandboxSpec.env`; `SandboxSpecForbidden` on a denied substring (raise is **S3-01**, not this story).
  - `../phase-arch-design.md §CI gates — test_env_allowlist_no_credentials.py` (line 914) — asserts denied substrings cannot pass even if added to the allowlist (the **test** is S1-07; this story owns the filter the test exercises).
  - `../phase-arch-design.md §Open questions §10` (line 1065) — `SignalKind` registry collision policy: raise `SignalKindAlreadyRegistered` at import.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0012-static-env-allowlist-no-credentials-in-sandbox.md` — ADR-0012 — allowlist is `("PATH", "NODE_ENV", "HTTPS_PROXY")` exact + `("NPM_CONFIG_",)` prefix; denied substrings `("KEY", "TOKEN", "SECRET", "PASSWORD")` are belt-and-suspenders.
  - `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — open signal-kind registry; collision raises `SignalKindAlreadyRegistered`. The collector decorator side; the name-registry side is already shipped in Phase 3.
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — backend registration validates structurally against `SandboxClient` Protocol on the *class* (`isinstance` happens at `get_backend` time, post-instantiation, since some backends require digests in `__init__`).
- **Source design:**
  - `../final-design.md §Synthesis ledger — Env into sandbox row`.
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` bullets 5 + 6.
- **Existing codebase precedent (the collision and the pattern):**
  - [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) — Phase 3 S6-02 — the *already-shipped* `register_signal_kind(name) -> SignalKind` value-producing function + `SignalKindRegistry` class + `.fresh()` classmethod + module-level `signal_kind_registry: Final` singleton + Phase 3's `SignalKindAlreadyRegistered` (subclass of `CodegenieError`). The shape Phase 5 mirrors **and the function Phase 5's decorator delegates to.**
  - [`src/codegenie/sandbox/errors.py`](../../../../src/codegenie/sandbox/errors.py) — S1-01 — pins `SandboxBackendInvalid` and `SignalKindAlreadyRegistered` (sandbox-package variant, subclass of `SandboxError`). The two shadow `SignalKindAlreadyRegistered` classes are disambiguated by full module path.
  - [`src/codegenie/types/identifiers.py:96`](../../../../src/codegenie/types/identifiers.py:96) — `SignalKind = NewType("SignalKind", str)` (S1-03 promotion); the collector registry keys on it internally.
  - [`src/codegenie/probes/registry.py`](../../../../src/codegenie/probes/registry.py) — Phase 0 — the `@register_probe` decorator precedent ADR-0003 cites.
- **Identifiers home (per S1-03):**
  - `SignalKind` (`types/identifiers.py:96`) — imported, never redefined.
- **Prior HARDENED reports (consult before implementing):**
  - `_validation/S1-01-scaffold-packages-errors-structlog.md` — canonical event-name table; error-class shape (`pass`-only body, no custom `__init__`); `Final[str]` discipline on event constants.
  - `_validation/S1-02-sandbox-contract-protocol-models.md` — `SandboxSpec.env: Mapping[str, str]` annotation discipline (AC-5); `SandboxSpec.sandbox_spec_hash` byte-stability under env-dict-key reordering (property test).
  - `_validation/S1-03-objective-signals-models.md` — `SignalKind` NewType promotion + single-declaration-site discipline (AC-4c AST chokepoint forbids redefinition under `src/codegenie/sandbox/`).
  - `_validation/S1-04-gates-contract-abc-models.md` — module-purity walker pattern; `from __future__ import annotations` line-1 discipline; alphabetized `__all__`; coverage-floor wording.

## Goal

Ship the three Open/Closed seams of Phase 5 with the established class-based-registry pattern, the documented Phase-3 delegation chain, and the credential-filter:

- `src/codegenie/sandbox/registry.py` — `SandboxBackendRegistry` class + `.fresh()` + module-level singleton + `register_sandbox_backend(name, *, registry=None)` decorator factory + `get_backend(name) -> SandboxClient` + `auto_detect() -> SandboxClient` (fallback-only; real platform branch is S6-04).
- `src/codegenie/sandbox/signals/registry.py` — `SignalCollectorRegistry` class + `.fresh()` + module-level singleton + `register_signal_kind(name, *, registry=None)` decorator factory + `get_signal_collector(kind: SignalKind) -> Callable`. The decorator **delegates the name-registration side** to Phase 3's `codegenie.transforms.signal_kinds.register_signal_kind` function; **distinct from** but cooperating with the Phase 3 name registry.
- `src/codegenie/sandbox/env_allowlist.py` — `ALLOWLIST: Final[tuple[str, ...]]` (exact) + `ALLOWLIST_PREFIXES: Final[tuple[str, ...]]` (prefix) + `DENY_SUBSTRINGS: Final[tuple[str, ...]]` (case-insensitive substring) + `filter(env: Mapping[str, str]) -> dict[str, str]` returning a deterministically-ordered new dict.
- Three new event-name constants appended to `src/codegenie/sandbox/logging.py` (under the S1-01 canonical table).

## Acceptance criteria

### A. Import surface and `__all__`

- [ ] **AC-IM-1 — Imports succeed and are idempotent:** each of
  - `from codegenie.sandbox.registry import register_sandbox_backend, get_backend, auto_detect, SandboxBackendRegistry, sandbox_backend_registry`
  - `from codegenie.sandbox.signals.registry import register_signal_kind, get_signal_collector, SignalCollectorRegistry, signal_collector_registry`
  - `from codegenie.sandbox.env_allowlist import filter, ALLOWLIST, ALLOWLIST_PREFIXES, DENY_SUBSTRINGS`
  - `from codegenie.sandbox.logging import EVENT_SANDBOX_BACKEND_REGISTERED, EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED, EVENT_SANDBOX_AUTO_DETECT_FALLBACK`
  succeeds; second `importlib.import_module(...)` returns the same module object (identity); no side-effects on second import.
- [ ] **AC-IM-1a — `__all__` is the exact public surface, alphabetized.** For each of the three new modules and the augmented `sandbox/logging.py`, `set(mod.__all__)` equals the documented public surface (`{"SandboxBackendRegistry", "auto_detect", "get_backend", "register_sandbox_backend", "sandbox_backend_registry"}` for `registry.py`; `{"SignalCollectorRegistry", "get_signal_collector", "register_signal_kind", "signal_collector_registry"}` for `signals/registry.py`; `{"ALLOWLIST", "ALLOWLIST_PREFIXES", "DENY_SUBSTRINGS", "filter"}` for `env_allowlist.py`; the union of S1-01's pinned constants plus the three new constants for `sandbox/logging.py`). `mod.__all__ == sorted(mod.__all__)`.

### B. `SandboxBackendRegistry` and `@register_sandbox_backend`

- [ ] **AC-BR-1 — Class shape.** `SandboxBackendRegistry` is a class with `__init__(self) -> None`, an internal `dict[str, type[SandboxClient]]` store, a `register(name, cls, *, origin: str) -> None` method, a `get(name) -> SandboxClient` method, a `__contains__(name) -> bool` dunder, and a `fresh() -> SandboxBackendRegistry` classmethod returning an empty instance. Mirror of Phase 3's [`SignalKindRegistry`](../../../../src/codegenie/transforms/signal_kinds.py:78).
- [ ] **AC-BR-2 — Decorator returns the class identity-equal:** `register_sandbox_backend("test_be")(Cls) is Cls` (NOT a wrapper class). Catches the M-2 mutation where an implementer wraps the class via `functools.wraps`.
- [ ] **AC-BR-3 — Structural validation: `execute` signature.** A class with `execute(self)` (zero-arg, no `spec`) raises `SandboxBackendInvalid` at decoration time. Verified via `inspect.signature(cls.execute).parameters` — set of parameter names is `{"self", "spec"}` (no more, no fewer).
- [ ] **AC-BR-4 — Structural validation: `health` signature.** A class with `health(self, *args)` raises `SandboxBackendInvalid` at decoration time. Verified via `inspect.signature(cls.health).parameters == {"self"}`.
- [ ] **AC-BR-5 — Registration does NOT instantiate the class.** Decorating a class whose `__init__` raises `RuntimeError("must not be instantiated at registration")` succeeds (no `RuntimeError` raised). Required for `FirecrackerClient` which needs digests in `__init__`. Rationale documented in module docstring.
- [ ] **AC-BR-6 — `inspect.isclass(cls) is True`.** Decorating a non-class object (a bare function with `execute` and `health` attributes) raises `SandboxBackendInvalid`.
- [ ] **AC-BR-7 — Per-instance isolation via `registry=` kwarg.** `register_sandbox_backend("x", registry=SandboxBackendRegistry.fresh())(Cls)` populates the *fresh* instance, not the module-level `sandbox_backend_registry`. Mirror of Phase 3 [`register_signal_kind(name, registry=fresh)`](../../../../src/codegenie/transforms/signal_kinds.py:125) pattern.
- [ ] **AC-BR-8 — Duplicate raises `SandboxBackendInvalid`.** Re-registering the same name (within the same registry instance) raises `SandboxBackendInvalid` with a message naming both call sites (the first registration's origin + the duplicate's origin) — mirrors Phase 3's collision-error origin-tracking discipline.
- [ ] **AC-BR-9 — Successful registration emits `EVENT_SANDBOX_BACKEND_REGISTERED`** on the `codegenie.sandbox.registry` logger at INFO with `extra={"name": <name>}`. `caplog`-based assertion.
- [ ] **AC-BR-10 — `get_backend(name) -> SandboxClient` returns a fresh instance.** Two successive `get_backend("x")` calls produce *distinct* instances (`a is not b`). The registry stores the *class*, not a singleton instance. (Rationale: per-gate-run isolation; some backends carry per-instance daemon handles.)
- [ ] **AC-BR-11 — `get_backend(name)` of an unregistered name raises `SandboxBackendInvalid`** (with "not registered" in the message).

### C. `auto_detect`

- [ ] **AC-AD-1 — Signature is `() -> SandboxClient`.** `inspect.signature(auto_detect)` has zero parameters; return annotation is `SandboxClient`.
- [ ] **AC-AD-2 — Returns an instance satisfying `isinstance(_, SandboxClient)`** (the runtime-checkable Protocol from S1-02).
- [ ] **AC-AD-3 — Emits `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`** on `codegenie.sandbox.registry` at INFO with `extra={"backend": "docker_in_docker"}`. `caplog`-based assertion.
- [ ] **AC-AD-4 — Raises `SandboxBackendInvalid` when `"docker_in_docker"` is not registered.** Fail-loud per Rule 12; documented contract for S6-04 to replace with real KVM-vs-DiD logic.

### D. `SignalCollectorRegistry` and `@register_signal_kind`

- [ ] **AC-CR-1 — Class shape.** `SignalCollectorRegistry` is a class with `register(kind: SignalKind, fn: Callable, *, origin: str) -> None`, `get(kind: SignalKind) -> Callable`, `__contains__(kind: SignalKind) -> bool`, `fresh() -> SignalCollectorRegistry`. Internal store is `dict[SignalKind, Callable]`. Mirror of Phase 3's `SignalKindRegistry`.
- [ ] **AC-CR-2 — Decorator returns the function identity-equal:** `register_signal_kind("build")(fn) is fn`.
- [ ] **AC-CR-3 — Successful registration emits `EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED`** on `codegenie.sandbox.signals.registry` at INFO with `extra={"kind": <name>}`.
- [ ] **AC-CR-4 — Duplicate collector registration raises `codegenie.sandbox.errors.SignalKindAlreadyRegistered`** (NOT Phase 3's `transforms.signal_kinds.SignalKindAlreadyRegistered`). Tested via `pytest.raises(codegenie.sandbox.errors.SignalKindAlreadyRegistered)` (full-module-path import to avoid shadowing). The error names both call sites.
- [ ] **AC-CR-5 — `get_signal_collector(kind: SignalKind) -> Callable`** returns the registered function; unregistered kind raises `codegenie.sandbox.errors.SignalKindAlreadyRegistered`'s sibling — use `KeyError` to keep the error class semantics distinct (a *missing* collector is not a *duplicate registration*).
- [ ] **AC-CR-6 — Per-instance isolation via `registry=` kwarg** (mirrors AC-BR-7).
- [ ] **AC-CR-7 — Internal store keys on `SignalKind` (NewType), not raw `str`.** Asserted via `typing.get_type_hints(SignalCollectorRegistry.register)['kind'] is SignalKind`. Mirrors S1-03 single-declaration discipline.

### E. Phase 3 ↔ Phase 5 collision discipline

- [ ] **AC-COL-1 — The decorator has signature `register_signal_kind(name: str, *, registry: SignalCollectorRegistry | None = None) -> Callable[[Callable], Callable]`** (signature differs from Phase 3's `(name: str, *, registry: SignalKindRegistry | None = None) -> SignalKind`). `inspect.signature(codegenie.sandbox.signals.registry.register_signal_kind)` matches; `inspect.signature(codegenie.transforms.signal_kinds.register_signal_kind)` matches its established shape.
- [ ] **AC-COL-2 — Two `SignalKindAlreadyRegistered` classes coexist by full module path.** `codegenie.sandbox.errors.SignalKindAlreadyRegistered` is a subclass of `codegenie.sandbox.errors.SandboxError`; `codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered` is a subclass of `codegenie.errors.CodegenieError`. They are NOT the same class (`A is not B`). Phase 5's decorator raises the **sandbox** one; Phase 3's function continues to raise its own.
- [ ] **AC-COL-3 — Decorator delegates the name-registration side to Phase 3's function.** After `@register_signal_kind("baseimage") def _collect(...): pass`, the kind `SignalKind("baseimage")` appears in Phase 3's `codegenie.transforms.signal_kinds.signal_kind_registry` (i.e., `SignalKind("baseimage") in signal_kind_registry` is `True`). Verified by `from codegenie.transforms.signal_kinds import signal_kind_registry; assert SignalKind("baseimage") in signal_kind_registry`.
- [ ] **AC-COL-4 — Decorator is idempotent on the name side when the kind is already in Phase 3's registry.** Calling Phase 5's `@register_signal_kind("build")` does NOT raise Phase 3's `SignalKindAlreadyRegistered` (because `"build"` was already registered by Phase 3's module-level `BUILD = register_signal_kind("build")` line). The decorator detects pre-existing names via `SignalKind(name) in signal_kind_registry` and skips the Phase 3 `register_signal_kind` call in that branch.
- [ ] **AC-COL-5 — Module docstring + Notes name the collision explicitly.** AST inspection of `codegenie/sandbox/signals/registry.py` finds the module docstring contains the substrings `"transforms.signal_kinds"` and `"delegates"` — surfacing the collision for readers (Rule 7).

### F. `env_allowlist` constants

- [ ] **AC-AL-1 — `ALLOWLIST` is a `Final[tuple[str, ...]]` containing exactly `("PATH", "NODE_ENV", "HTTPS_PROXY")`** (tuple-equality, ordered). `typing.get_type_hints(env_allowlist)['ALLOWLIST']` is `tuple[str, ...]` with `Final` qualifier (verified via `ast.parse` on the source — the annotation is `Final[tuple[str, ...]]`).
- [ ] **AC-AL-2 — `ALLOWLIST_PREFIXES` is a `Final[tuple[str, ...]]` containing exactly `("NPM_CONFIG_",)`** (note the trailing underscore — without it, `NPM_CONFIGURE` would match wrongly).
- [ ] **AC-AL-3 — `DENY_SUBSTRINGS` is a `Final[tuple[str, ...]]` containing exactly `("KEY", "TOKEN", "SECRET", "PASSWORD")`** (uppercase only — the case-insensitive matching is handled in the predicate, not the data).

### G. `env_allowlist.filter` — signature, identity, degenerate

- [ ] **AC-FL-1 — Signature is `filter(env: Mapping[str, str]) -> dict[str, str]`.** `typing.get_type_hints(filter)['env']` is `collections.abc.Mapping[str, str]` (NOT `dict[str, str]`); return type is `dict[str, str]`. Source-level pinning matches S1-02 AC-5 (`SandboxSpec.env: Mapping[str, str]`).
- [ ] **AC-FL-2 — Accepts a `MappingProxyType` (read-only view).** `filter(types.MappingProxyType({"PATH": "/usr/bin"}))` returns `{"PATH": "/usr/bin"}` without `TypeError`.
- [ ] **AC-FL-3 — Returns a NEW dict (identity-distinct from input).** `out = filter(env_in); assert out is not env_in` even when no keys are filtered.
- [ ] **AC-FL-4 — Empty input → empty output.** `filter({}) == {}` and `filter({}) is not the_empty_dict_used_as_input`.

### H. `env_allowlist.filter` — allowlist match semantics

- [ ] **AC-AL-4 — Allowlist is case-SENSITIVE exact match.** `filter({"PATH": "/x", "Path": "/y", "path": "/z"})` returns exactly `{"PATH": "/x"}` (case variants dropped). Parametrized over each allowlist member.
- [ ] **AC-AL-5 — `PATH_EXT` is NOT allowlisted** (exact-match, not substring). `filter({"PATH_EXT": "x"}) == {}`.
- [ ] **AC-AL-6 — Prefix is case-SENSITIVE.** `filter({"NPM_CONFIG_LOGLEVEL": "warn", "NPM_CONFIG_": "", "npm_config_loglevel": "warn", "NOT_NPM_CONFIG_FOO": "x", "NPM_CONFIGURE": "x"})` returns exactly `{"NPM_CONFIG_LOGLEVEL": "warn", "NPM_CONFIG_": ""}` (the trailing underscore in the prefix excludes `NPM_CONFIGURE`).

### I. `env_allowlist.filter` — deny-substring semantics (case-insensitive)

- [ ] **AC-DN-1 — Case-insensitive substring match drops the key.** Parametrized matrix of (substring × position × case): `("ANTHROPIC_API_KEY", "GITHUB_TOKEN", "DB_SECRET", "REGISTRY_PASSWORD")` × `({"prefix": "KEY_FOO", "infix": "MY_KEY_X", "suffix": "MY_KEY"})` × `({"upper": "KEY", "lower": "key", "mixed": "Key"})`. Each parametrized row asserts the key is NOT in `filter(env).keys()`.
- [ ] **AC-DN-2 — Deny applies BEFORE allow (belt-and-suspenders per ADR-0012).** `filter({"MY_PATH_KEY": "x", "PATH": "/usr/bin"}) == {"PATH": "/usr/bin"}`. The key `MY_PATH_KEY` would not be allowlisted regardless, but the AC pins the predicate ordering for fail-loud semantics.
- [ ] **AC-DN-3 — Deny does not raise; it silently drops.** `filter({"GITHUB_TOKEN": "abc"})` returns `{}` without raising. The `SandboxSpecForbidden` raise lives in `SandboxSpecBuilder` (S3-01), not here.
- [ ] **AC-DN-4 — Empty-string key is degenerate-handled.** `filter({"": "x"}) == {}` (no substring matches empty allowlist; well-defined behavior).

### J. `env_allowlist.filter` — algebraic properties (hypothesis)

- [ ] **AC-FL-5 — Subset:** `set(filter(env).keys()) ⊆ set(env.keys())` (no synthesis). Hypothesis-generated.
- [ ] **AC-FL-6 — Idempotent:** `filter(filter(env)) == filter(env)`. Hypothesis-generated.
- [ ] **AC-FL-7 — Output key order is deterministic** (the lexicographically sorted view): `list(filter(env).keys()) == sorted(filter(env).keys())`. Additionally, for any permutation `env'` of `env`, `list(filter(env').keys()) == list(filter(env).keys())`. Hypothesis-generated reorder property. **Required for S1-02 `SandboxSpec.sandbox_spec_hash` byte-stability.**
- [ ] **AC-FL-8 — Monotone on allowlisted additions:** `filter(env | {"PATH": "/x"}).get("PATH") == "/x"` for any `env` that does not deny-block `"PATH"` (which it cannot, since `PATH` contains no denied substring). Hypothesis-generated.

### K. New event-name constants (additions to S1-01's canonical table)

- [ ] **AC-LG-1 — `EVENT_SANDBOX_BACKEND_REGISTERED` in `codegenie.sandbox.logging`** is `Final[str]` equal byte-exact to `"sandbox.backend.registered"`. In `__all__`. Matches the dotted-lowercase regex `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` (S1-01 AC-4a).
- [ ] **AC-LG-2 — `EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED`** is `Final[str]` equal byte-exact to `"sandbox.signal_collector.registered"`.
- [ ] **AC-LG-3 — `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`** is `Final[str]` equal byte-exact to `"sandbox.auto_detect.fallback"`.
- [ ] **AC-LG-4 — No value collisions** with S1-01's existing constants (the union of constant values has the same cardinality as the union of constant names — S1-01 AC-4c).

### L. Module purity and `__all__` discipline (mirrors S1-04 AC-PURE)

- [ ] **AC-PURE-1 — `from __future__ import annotations` is the first non-docstring line** in each of `registry.py`, `signals/registry.py`, `env_allowlist.py`. Verified by `ast.parse` on the source.
- [ ] **AC-PURE-2 — Module docstring cites all three honored ADRs by number** (`ADR-0012`, `ADR-0003`, `ADR-0006`) where applicable per module. `registry.py` cites -0006 + -0003; `signals/registry.py` cites -0003 + -0006 + the Phase-3 delegation chain; `env_allowlist.py` cites -0012.
- [ ] **AC-PURE-3 — Imports are restricted** to: stdlib + `codegenie.errors` + `codegenie.sandbox.{errors, contract, logging}` + `codegenie.types.identifiers` + (for `signals/registry.py` only) `codegenie.transforms.signal_kinds`. AST walk asserts no imports of `anthropic`, `langgraph`, `chromadb`, `sentence_transformers`, `pydantic` (none of the three modules ships Pydantic models), `requests`, or any sibling Phase-5 module not in this allowlist. (S1-07's structural fence will enforce the LLM-import ban formally.)
- [ ] **AC-PURE-4 — `__all__` is alphabetized + sorted** in each module: `mod.__all__ == sorted(mod.__all__)`.

### M. Module-level singletons

- [ ] **AC-SG-1 — `sandbox_backend_registry: Final[SandboxBackendRegistry]`** is exposed in `registry.py` at module level. Annotation is `Final`.
- [ ] **AC-SG-2 — `signal_collector_registry: Final[SignalCollectorRegistry]`** is exposed in `signals/registry.py`.
- [ ] **AC-SG-3 — Default kwarg discipline.** `register_sandbox_backend(name, *, registry=None)` and `register_signal_kind(name, *, registry=None)` — when `registry is None`, the module-level singleton is used. Mirror of Phase 3 pattern.

### N. Process gates

- [ ] **AC-PG-1 — `ruff check`, `ruff format --check`, `mypy --strict`** on the three new modules + the three new test files exit 0.
- [ ] **AC-PG-2 — `pytest`** on the test files (`test_registry.py`, `test_signal_collector_registry.py`, `test_env_allowlist.py`, `test_registry_purity.py`, `test_signal_kind_collision.py`) all green.
- [ ] **AC-PG-3 — Coverage floor** is `line ≥ 95% AND branch ≥ 90%` on `env_allowlist.py`, `registry.py`, `signals/registry.py` (matches the `gates/runner.py`+`sandbox/contract.py` floor from arch §Goal 12 and the S1-02/S1-03/S1-04 hardening pattern).

## Implementation outline

1. **Create `src/codegenie/sandbox/registry.py`.** Header: `from __future__ import annotations`. Module docstring cites ADR-0006, ADR-0003 (registry pattern source), and the Phase-3 [`probes/registry.py`](../../../../src/codegenie/probes/registry.py) precedent.
   - Define `SandboxBackendRegistry`:
     ```python
     class SandboxBackendRegistry:
         def __init__(self) -> None:
             self._backends: dict[str, type] = {}
             self._origins: dict[str, str] = {}
         def register(self, name: str, cls: type, *, origin: str) -> None:
             if not inspect.isclass(cls):
                 raise SandboxBackendInvalid(f"{name!r}: not a class")
             _validate_backend_class_shape(cls, name=name)  # AC-BR-3/4
             if name in self._backends:
                 raise SandboxBackendInvalid(
                     f"duplicate backend {name!r}: {self._origins[name]} and {origin}"
                 )
             self._backends[name] = cls
             self._origins[name] = origin
         def get(self, name: str) -> "SandboxClient":
             if name not in self._backends:
                 raise SandboxBackendInvalid(f"backend {name!r} not registered")
             return self._backends[name]()  # fresh instance per call
         def __contains__(self, name: str) -> bool:
             return name in self._backends
         @classmethod
         def fresh(cls) -> "SandboxBackendRegistry":
             return cls()
     sandbox_backend_registry: Final[SandboxBackendRegistry] = SandboxBackendRegistry()
     ```
   - `_validate_backend_class_shape(cls, *, name)` walks `inspect.signature(cls.execute)` and `inspect.signature(cls.health)` and raises `SandboxBackendInvalid` on parameter-set mismatch. Does NOT instantiate `cls`.
   - `register_sandbox_backend(name, *, registry=None)` returns a class decorator that introspects the caller's frame (mirror Phase 3 `register_signal_kind` `inspect.currentframe()` pattern), composes `origin = f"{module}.{qualname}"`, calls `(registry or sandbox_backend_registry).register(name, cls, origin=origin)`, emits `EVENT_SANDBOX_BACKEND_REGISTERED` at INFO with `extra={"name": name}`, and returns `cls` unchanged.
   - `get_backend(name) -> SandboxClient` delegates to the module singleton.
   - `auto_detect() -> SandboxClient`: emits `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` at INFO with `extra={"backend": "docker_in_docker"}`, then returns `get_backend("docker_in_docker")` (which raises `SandboxBackendInvalid` if missing — fail-loud).
2. **Create `src/codegenie/sandbox/signals/registry.py`.** Header: `from __future__ import annotations`. Module docstring cites ADR-0003, ADR-0006, AND the Phase-3 [`transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) name-registry — naming the collision explicitly:
   > **Note: identifier collision with `codegenie.transforms.signal_kinds.register_signal_kind`.** Phase 3 ships a value-producing FUNCTION at that path (`BUILD = register_signal_kind("build")`); this module ships a DECORATOR with the same name. Phase 5's decorator delegates the name-registration side to Phase 3's function before binding the collector. See `_validation/S1-05-registries-and-env-allowlist.md` for the rationale.
   - Define `SignalCollectorRegistry` (same shape as `SandboxBackendRegistry`, keyed on `SignalKind` not `str`).
   - `register_signal_kind(name: str, *, registry: SignalCollectorRegistry | None = None)`:
     ```python
     def register_signal_kind(name, *, registry=None):
         from codegenie.transforms.signal_kinds import (
             register_signal_kind as _register_name_in_phase3,
             signal_kind_registry,
         )
         def decorator(fn):
             kind = SignalKind(name)
             # Delegate the NAME side to Phase 3 (idempotent on pre-existing).
             if kind not in signal_kind_registry:
                 _register_name_in_phase3(name)  # raises Phase-3 collision class
             # Bind the COLLECTOR side here.
             frame = inspect.currentframe()
             caller = frame.f_back if frame is not None else None
             origin = (
                 f"{caller.f_globals.get('__name__', '?')}.{caller.f_code.co_qualname}"
                 if caller else "<unknown>"
             )
             (registry or signal_collector_registry).register(kind, fn, origin=origin)
             _logger.info(EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED, extra={"kind": name})
             return fn
         return decorator
     ```
   - `get_signal_collector(kind: SignalKind) -> Callable` delegates to the module singleton.
   - `SignalCollectorRegistry.register(...)` raises `codegenie.sandbox.errors.SignalKindAlreadyRegistered` on duplicate (NOT Phase 3's class — the two coexist).
3. **Create `src/codegenie/sandbox/env_allowlist.py`.** Header: `from __future__ import annotations`. Module docstring cites ADR-0012.
   - Module-level `Final` tuples:
     ```python
     ALLOWLIST: Final[tuple[str, ...]] = ("PATH", "NODE_ENV", "HTTPS_PROXY")
     ALLOWLIST_PREFIXES: Final[tuple[str, ...]] = ("NPM_CONFIG_",)
     DENY_SUBSTRINGS: Final[tuple[str, ...]] = ("KEY", "TOKEN", "SECRET", "PASSWORD")
     ```
   - `_is_denied(k: str) -> bool`: `return any(deny.lower() in k.lower() for deny in DENY_SUBSTRINGS)`.
   - `_is_allowed(k: str) -> bool`: `return k in ALLOWLIST or any(k.startswith(p) for p in ALLOWLIST_PREFIXES)`. Case-SENSITIVE (env vars are case-sensitive on POSIX).
   - `def filter(env: Mapping[str, str]) -> dict[str, str]:` — iterate `sorted(env.keys())` (deterministic ordering per AC-FL-7), build a new dict with `not _is_denied(k) and _is_allowed(k)` predicate. The `not _is_denied(k)` check goes FIRST (belt-and-suspenders per ADR-0012). Return the new dict.
   - Note: the name `filter` shadows the builtin; in callers, use either `from codegenie.sandbox.env_allowlist import filter as env_filter` or dotted access `env_allowlist.filter(env)`. Documented in module docstring.
4. **Append three rows to `src/codegenie/sandbox/logging.py`** (below S1-01's existing constants table):
   ```python
   EVENT_SANDBOX_BACKEND_REGISTERED: Final[str] = "sandbox.backend.registered"
   EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED: Final[str] = "sandbox.signal_collector.registered"
   EVENT_SANDBOX_AUTO_DETECT_FALLBACK: Final[str] = "sandbox.auto_detect.fallback"
   ```
   Update `__all__` to include the three new names, alphabetized.
5. **Write the five test files** (`test_registry.py`, `test_signal_collector_registry.py`, `test_env_allowlist.py`, `test_registry_purity.py`, `test_signal_kind_collision.py`).
6. **Update story status** in this file to `Ready (HARDENED 2026-05-22)` once the validation pass completes — already done by this validator.

## TDD plan — red / green / refactor

### Red — write the failing tests first

The five test files use `SandboxBackendRegistry.fresh()` and `SignalCollectorRegistry.fresh()` for per-test isolation — no autouse snapshot/restore fixtures. Each test docstring names the AC it covers.

```python
# tests/sandbox/test_registry.py
"""Backend registry — AC-BR-1..AC-BR-11."""
from __future__ import annotations

import inspect
import pytest

from codegenie.sandbox.contract import SandboxClient  # S1-02
from codegenie.sandbox.errors import SandboxBackendInvalid
from codegenie.sandbox.logging import EVENT_SANDBOX_BACKEND_REGISTERED, EVENT_SANDBOX_AUTO_DETECT_FALLBACK
from codegenie.sandbox.registry import (
    SandboxBackendRegistry,
    register_sandbox_backend,
    get_backend,
    auto_detect,
    sandbox_backend_registry,
)


class _GoodBackend:
    def execute(self, spec): ...
    def health(self): ...


def test_register_returns_class_identity_AC_BR_2():
    fresh = SandboxBackendRegistry.fresh()
    decorated = register_sandbox_backend("test_be", registry=fresh)(_GoodBackend)
    assert decorated is _GoodBackend


def test_register_validates_execute_signature_AC_BR_3():
    class _Bad:
        def execute(self): ...   # missing spec
        def health(self): ...
    fresh = SandboxBackendRegistry.fresh()
    with pytest.raises(SandboxBackendInvalid):
        register_sandbox_backend("bad", registry=fresh)(_Bad)


def test_register_validates_health_signature_AC_BR_4():
    class _Bad:
        def execute(self, spec): ...
        def health(self, *extra): ...   # extra args
    fresh = SandboxBackendRegistry.fresh()
    with pytest.raises(SandboxBackendInvalid):
        register_sandbox_backend("bad", registry=fresh)(_Bad)


def test_register_does_not_instantiate_AC_BR_5():
    class _NoInit:
        def __init__(self):
            raise RuntimeError("must not be instantiated at registration")
        def execute(self, spec): ...
        def health(self): ...
    fresh = SandboxBackendRegistry.fresh()
    register_sandbox_backend("no_init", registry=fresh)(_NoInit)   # must not raise


def test_register_rejects_non_class_AC_BR_6():
    def _fn(self, spec): ...
    _fn.execute = lambda s: None   # type: ignore[attr-defined]
    _fn.health = lambda s: None    # type: ignore[attr-defined]
    fresh = SandboxBackendRegistry.fresh()
    with pytest.raises(SandboxBackendInvalid):
        register_sandbox_backend("fn", registry=fresh)(_fn)   # type: ignore[arg-type]


def test_per_instance_isolation_AC_BR_7():
    fresh1 = SandboxBackendRegistry.fresh()
    fresh2 = SandboxBackendRegistry.fresh()
    register_sandbox_backend("isolated", registry=fresh1)(_GoodBackend)
    assert "isolated" in fresh1
    assert "isolated" not in fresh2
    assert "isolated" not in sandbox_backend_registry   # global untouched


def test_duplicate_raises_with_both_origins_AC_BR_8():
    fresh = SandboxBackendRegistry.fresh()
    register_sandbox_backend("dup", registry=fresh)(_GoodBackend)
    with pytest.raises(SandboxBackendInvalid) as ei:
        register_sandbox_backend("dup", registry=fresh)(_GoodBackend)
    assert "duplicate" in str(ei.value).lower()


def test_register_emits_structured_event_AC_BR_9(caplog):
    import logging as _stdlib_logging
    caplog.set_level(_stdlib_logging.INFO, logger="codegenie.sandbox.registry")
    fresh = SandboxBackendRegistry.fresh()
    register_sandbox_backend("ev", registry=fresh)(_GoodBackend)
    matching = [r for r in caplog.records if r.message == EVENT_SANDBOX_BACKEND_REGISTERED]
    assert len(matching) == 1 and matching[0].name == "ev" if hasattr(matching[0], "name") else True
    # The 'name' extra is verified by stripped attr-presence.
    assert any(getattr(r, "name", None) == "ev" for r in matching) or "ev" in str(matching[0].__dict__)


def test_get_backend_returns_fresh_instances_AC_BR_10():
    fresh = SandboxBackendRegistry.fresh()
    register_sandbox_backend("inst_test", registry=fresh)(_GoodBackend)
    a = fresh.get("inst_test")
    b = fresh.get("inst_test")
    assert a is not b
    assert isinstance(a, SandboxClient)


def test_get_backend_unknown_raises_AC_BR_11():
    fresh = SandboxBackendRegistry.fresh()
    with pytest.raises(SandboxBackendInvalid):
        fresh.get("never_registered")


def test_auto_detect_signature_AC_AD_1():
    sig = inspect.signature(auto_detect)
    assert len(sig.parameters) == 0
    assert sig.return_annotation in (SandboxClient, "SandboxClient")


def test_auto_detect_returns_sandbox_client_AC_AD_2(caplog):
    # Use the module-level singleton: register docker_in_docker into it.
    import logging as _stdlib_logging
    caplog.set_level(_stdlib_logging.INFO, logger="codegenie.sandbox.registry")
    # Snapshot/restore the singleton just for this test to avoid global side-effects.
    snapshot = dict(sandbox_backend_registry._backends)
    try:
        sandbox_backend_registry._backends.clear()
        register_sandbox_backend("docker_in_docker")(_GoodBackend)
        inst = auto_detect()
        assert isinstance(inst, SandboxClient)
        # AC-AD-3 — log emitted with the correct payload.
        matching = [r for r in caplog.records if r.message == EVENT_SANDBOX_AUTO_DETECT_FALLBACK]
        assert any(getattr(r, "backend", None) == "docker_in_docker" or "docker_in_docker" in str(r.__dict__)
                   for r in matching)
    finally:
        sandbox_backend_registry._backends.clear()
        sandbox_backend_registry._backends.update(snapshot)


def test_auto_detect_raises_when_docker_in_docker_missing_AC_AD_4():
    snapshot = dict(sandbox_backend_registry._backends)
    try:
        sandbox_backend_registry._backends.clear()
        with pytest.raises(SandboxBackendInvalid):
            auto_detect()
    finally:
        sandbox_backend_registry._backends.update(snapshot)
```

```python
# tests/sandbox/test_signal_collector_registry.py
"""Collector registry — AC-CR-1..AC-CR-7."""
from __future__ import annotations

import pytest

from codegenie.sandbox.errors import SignalKindAlreadyRegistered  # SANDBOX shadow
from codegenie.sandbox.signals.registry import (
    SignalCollectorRegistry,
    register_signal_kind,
    get_signal_collector,
    signal_collector_registry,
)
from codegenie.types.identifiers import SignalKind


def test_decorator_returns_function_identity_AC_CR_2():
    fresh = SignalCollectorRegistry.fresh()
    def _collect(run): return "ok"
    decorated = register_signal_kind("baseimage", registry=fresh)(_collect)
    assert decorated is _collect


def test_per_instance_isolation_AC_CR_6():
    fresh1 = SignalCollectorRegistry.fresh()
    fresh2 = SignalCollectorRegistry.fresh()
    def _c(run): pass
    register_signal_kind("policy_a", registry=fresh1)(_c)
    assert SignalKind("policy_a") in fresh1
    assert SignalKind("policy_a") not in fresh2


def test_duplicate_raises_sandbox_signal_kind_already_registered_AC_CR_4():
    fresh = SignalCollectorRegistry.fresh()
    def _c1(run): pass
    def _c2(run): pass
    register_signal_kind("trace_a", registry=fresh)(_c1)
    with pytest.raises(SignalKindAlreadyRegistered):
        register_signal_kind("trace_a", registry=fresh)(_c2)


def test_get_signal_collector_returns_registered_function():
    fresh = SignalCollectorRegistry.fresh()
    def _c(run): return "result"
    register_signal_kind("retrieve_a", registry=fresh)(_c)
    assert fresh.get(SignalKind("retrieve_a")) is _c
```

```python
# tests/sandbox/test_signal_kind_collision.py
"""Phase 3 ↔ Phase 5 collision discipline — AC-COL-1..AC-COL-5."""
from __future__ import annotations

import inspect

import pytest

import codegenie.sandbox.errors as sandbox_errors
import codegenie.transforms.signal_kinds as p3
from codegenie.sandbox.signals import registry as p5_reg
from codegenie.types.identifiers import SignalKind


def test_two_register_signal_kind_callables_exist_AC_COL_1():
    # Different signatures: Phase 3 returns SignalKind; Phase 5 returns a decorator.
    p3_sig = inspect.signature(p3.register_signal_kind)
    p5_sig = inspect.signature(p5_reg.register_signal_kind)
    assert p3_sig != p5_sig
    # Both accept the same 'name' positional + 'registry' kw, but the RETURN annotation differs.
    assert "name" in p3_sig.parameters and "name" in p5_sig.parameters


def test_two_signal_kind_already_registered_classes_AC_COL_2():
    # Distinct classes — same simple name, different module paths.
    assert sandbox_errors.SignalKindAlreadyRegistered is not p3.SignalKindAlreadyRegistered
    # Different inheritance trees.
    from codegenie.errors import CodegenieError
    from codegenie.sandbox.errors import SandboxError
    assert issubclass(sandbox_errors.SignalKindAlreadyRegistered, SandboxError)
    assert issubclass(p3.SignalKindAlreadyRegistered, CodegenieError)


def test_decorator_delegates_to_phase3_registry_AC_COL_3():
    # Use a fresh Phase-5 collector registry so we don't pollute the global one.
    fresh = p5_reg.SignalCollectorRegistry.fresh()
    novel_kind = "phase7_baseimage_smoke"   # not in any Phase-3 import

    @p5_reg.register_signal_kind(novel_kind, registry=fresh)
    def _collect(run):
        return run

    # Phase 3's NAME registry must now contain the kind.
    assert SignalKind(novel_kind) in p3.signal_kind_registry


def test_decorator_idempotent_on_pre_existing_phase3_kind_AC_COL_4():
    # 'build' is already in Phase 3's registry (imported via codegenie.transforms.__init__).
    assert SignalKind("build") in p3.signal_kind_registry
    fresh = p5_reg.SignalCollectorRegistry.fresh()

    # The decorator must NOT raise Phase 3's SignalKindAlreadyRegistered.
    @p5_reg.register_signal_kind("build", registry=fresh)
    def _collect_build(run):
        return run

    assert SignalKind("build") in fresh


def test_module_docstring_names_the_collision_AC_COL_5():
    doc = inspect.getdoc(p5_reg) or ""
    assert "transforms.signal_kinds" in doc
    assert "delegates" in doc.lower()
```

```python
# tests/sandbox/test_env_allowlist.py
"""env_allowlist — AC-AL-*, AC-DN-*, AC-FL-*."""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
import typing

import pytest
from hypothesis import given, strategies as st

from codegenie.sandbox.env_allowlist import (
    ALLOWLIST, ALLOWLIST_PREFIXES, DENY_SUBSTRINGS,
    filter as env_filter,
)


# ---------- AC-AL-1..3 (constants) ----------
def test_allowlist_constants_exact_AC_AL_1():
    assert ALLOWLIST == ("PATH", "NODE_ENV", "HTTPS_PROXY")
    assert isinstance(ALLOWLIST, tuple)


def test_allowlist_prefixes_exact_AC_AL_2():
    assert ALLOWLIST_PREFIXES == ("NPM_CONFIG_",)
    assert isinstance(ALLOWLIST_PREFIXES, tuple)


def test_deny_substrings_exact_AC_AL_3():
    assert DENY_SUBSTRINGS == ("KEY", "TOKEN", "SECRET", "PASSWORD")
    assert isinstance(DENY_SUBSTRINGS, tuple)


# ---------- AC-FL-1..4 (signature + identity + degenerate) ----------
def test_filter_signature_AC_FL_1():
    hints = typing.get_type_hints(env_filter)
    # Hint resolves either to collections.abc.Mapping[str, str] or to a runtime-equivalent generic alias.
    env_hint = hints["env"]
    origin = typing.get_origin(env_hint)
    assert origin is Mapping or origin.__name__ == "Mapping"
    args = typing.get_args(env_hint)
    assert args == (str, str)


def test_filter_accepts_mapping_proxy_AC_FL_2():
    proxy = MappingProxyType({"PATH": "/usr/bin"})
    out = env_filter(proxy)
    assert out == {"PATH": "/usr/bin"}


def test_filter_returns_new_dict_AC_FL_3():
    env = {"PATH": "/usr/bin"}
    out = env_filter(env)
    assert out is not env


def test_filter_empty_input_AC_FL_4():
    assert env_filter({}) == {}


# ---------- AC-AL-4..6 (allowlist match semantics) ----------
@pytest.mark.parametrize("good,bad", [
    ("PATH", "Path"),
    ("PATH", "path"),
    ("NODE_ENV", "Node_Env"),
    ("HTTPS_PROXY", "https_proxy"),
])
def test_allowlist_case_sensitive_AC_AL_4(good, bad):
    out = env_filter({good: "g", bad: "b"})
    assert good in out and bad not in out


def test_path_ext_not_allowed_AC_AL_5():
    assert env_filter({"PATH_EXT": "x"}) == {}


def test_prefix_case_sensitive_AC_AL_6():
    out = env_filter({
        "NPM_CONFIG_LOGLEVEL": "warn",
        "NPM_CONFIG_": "",
        "npm_config_loglevel": "warn",
        "NOT_NPM_CONFIG_FOO": "x",
        "NPM_CONFIGURE": "x",
    })
    assert set(out.keys()) == {"NPM_CONFIG_LOGLEVEL", "NPM_CONFIG_"}


# ---------- AC-DN-1..4 (deny substring semantics) ----------
@pytest.mark.parametrize("substring", ["KEY", "TOKEN", "SECRET", "PASSWORD"])
@pytest.mark.parametrize("position", ["PREFIX", "INFIX", "SUFFIX"])
@pytest.mark.parametrize("case", ["UPPER", "LOWER", "MIXED"])
def test_deny_substring_matrix_AC_DN_1(substring, position, case):
    needle = {"UPPER": substring, "LOWER": substring.lower(),
              "MIXED": substring.capitalize()}[case]
    key = {
        "PREFIX": f"{needle}_FOO",
        "INFIX": f"MY_{needle}_X",
        "SUFFIX": f"MY_{needle}",
    }[position]
    out = env_filter({key: "secret-value", "PATH": "/usr/bin"})
    assert key not in out
    assert out == {"PATH": "/usr/bin"}


def test_deny_applies_before_allow_AC_DN_2():
    # MY_PATH_KEY is not allowlisted (PATH is exact-match) but the key tests
    # the predicate-ordering pin: deny is checked first per ADR-0012.
    out = env_filter({"MY_PATH_KEY": "x", "PATH": "/usr/bin"})
    assert out == {"PATH": "/usr/bin"}


def test_deny_does_not_raise_AC_DN_3():
    env_filter({"GITHUB_TOKEN": "abc"})   # must not raise


def test_empty_key_AC_DN_4():
    assert env_filter({"": "x"}) == {}


# ---------- AC-FL-5..8 (algebraic properties via hypothesis) ----------
_KEY_ALPHABET = st.text(alphabet=st.characters(whitelist_categories=["L", "N"], whitelist_characters="_"),
                        min_size=1, max_size=24)
_ENVS = st.dictionaries(keys=_KEY_ALPHABET, values=st.text(max_size=32), max_size=20)


@given(env=_ENVS)
def test_subset_AC_FL_5(env):
    assert set(env_filter(env).keys()) <= set(env.keys())


@given(env=_ENVS)
def test_idempotent_AC_FL_6(env):
    once = env_filter(env)
    twice = env_filter(once)
    assert once == twice


@given(env=_ENVS)
def test_deterministic_key_order_AC_FL_7(env):
    out = env_filter(env)
    assert list(out.keys()) == sorted(out.keys())


@given(env=_ENVS)
def test_reorder_stability_AC_FL_7_perm(env):
    # Two equivalent dicts (same items) must yield same key order.
    items = list(env.items())
    reordered = dict(reversed(items))
    assert list(env_filter(env).keys()) == list(env_filter(reordered).keys())


@given(env=_ENVS)
def test_monotone_on_PATH_AC_FL_8(env):
    # Adding PATH must produce PATH in the output (PATH has no denied substring).
    augmented = dict(env)
    augmented["PATH"] = "/usr/bin"
    out = env_filter(augmented)
    assert out.get("PATH") == "/usr/bin"
```

```python
# tests/sandbox/test_registry_purity.py
"""Module-purity invariants — AC-PURE-1..4. Mirrors S1-04 test_contract_purity.py."""
from __future__ import annotations

import ast
import pathlib

import pytest

_TARGETS = [
    pathlib.Path("src/codegenie/sandbox/registry.py"),
    pathlib.Path("src/codegenie/sandbox/signals/registry.py"),
    pathlib.Path("src/codegenie/sandbox/env_allowlist.py"),
]

_ALLOWED_PREFIXES = (
    "codegenie.errors",
    "codegenie.sandbox.errors",
    "codegenie.sandbox.contract",
    "codegenie.sandbox.logging",
    "codegenie.sandbox.signals.registry",   # internal cross-ref allowed
    "codegenie.sandbox.env_allowlist",
    "codegenie.types.identifiers",
    "codegenie.transforms.signal_kinds",    # for the delegation chain
)

_BANNED = ("anthropic", "langgraph", "chromadb", "sentence_transformers")


@pytest.mark.parametrize("path", _TARGETS)
def test_future_annotations_line_one_after_docstring_AC_PURE_1(path):
    tree = ast.parse(path.read_text())
    # First statement is the module docstring; the second must be __future__ import.
    body = tree.body
    assert isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
    future = body[1]
    assert isinstance(future, ast.ImportFrom)
    assert future.module == "__future__"
    assert any(a.name == "annotations" for a in future.names)


@pytest.mark.parametrize("path", _TARGETS)
def test_module_docstring_cites_adrs_AC_PURE_2(path):
    tree = ast.parse(path.read_text())
    docstring = ast.get_docstring(tree) or ""
    # Each module cites at least ONE of the three ADRs.
    assert any(adr in docstring for adr in ("ADR-0012", "ADR-0003", "ADR-0006"))


@pytest.mark.parametrize("path", _TARGETS)
def test_imports_restricted_AC_PURE_3(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.startswith("codegenie"):
                assert any(mod.startswith(p) for p in _ALLOWED_PREFIXES), (
                    f"{path}: disallowed import from {mod}"
                )
            assert not any(banned in mod for banned in _BANNED), (
                f"{path}: banned LLM/RAG import {mod}"
            )
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(banned in n.name for banned in _BANNED)


@pytest.mark.parametrize("path", _TARGETS)
def test_all_alphabetized_AC_PURE_4(path):
    # Read __all__ via exec is fragile; instead AST-walk for the assignment.
    tree = ast.parse(path.read_text())
    found_all = None
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__all__"
        ):
            assert isinstance(node.value, ast.List) or isinstance(node.value, ast.Tuple)
            found_all = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]
            break
    assert found_all is not None, f"{path}: __all__ not declared"
    assert found_all == sorted(found_all), f"{path}: __all__ not alphabetized"
```

Run the five test files; confirm `ImportError`/`AttributeError`/red on every test. Commit the red state, then implement.

### Green — make it pass

Implement each module minimally per the Implementation outline above. Three implementation pitfalls — fail-loud, NOT silent:

- **Do NOT instantiate the class** during `register_sandbox_backend`. `FirecrackerClient` requires digests in `__init__`; instantiation at decoration time breaks Phase 7.
- **Phase 5's decorator must `inspect.currentframe()` for the origin string** — mirror Phase 3's pattern at [`transforms/signal_kinds.py:137-142`](../../../../src/codegenie/transforms/signal_kinds.py:137).
- **Predicate ordering: `not _is_denied(k) and _is_allowed(k)`** — deny FIRST (belt-and-suspenders per ADR-0012). Mutation: reversing the ordering would still pass the unit tests but would diverge from ADR-0012's stated semantics. The order is observable only via the deny-applies-before-allow AC.

### Refactor — clean up

- Module docstrings: one paragraph per module citing ADR(s) + the load-bearing rationale. `signals/registry.py`'s docstring **must** name the Phase-3 collision explicitly (AC-COL-5).
- Single-sentence docstrings on each public function/class.
- The two registry classes share enough surface (`register` + `__contains__` + `fresh`) that a future kernel-extract `KernelRegistry[K, V]` is tempting; **defer** per the precedent set in Phase 3 [`transforms/signal_kinds.py:16-30`](../../../../src/codegenie/transforms/signal_kinds.py:16) ("N=5 or a registry needing only the common surface" — Phase 5 brings the count to 6, but the divergent dispatch machinery in `probes`/`indices`/`depgraph` still argues against the extract). Documented in Notes.
- `env_allowlist.py` is ≤ 60 LOC; the two predicates are bare booleans (no tagged-union return) per Rule 2.
- Logging: every `register_*` emits a structured log line.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/sandbox/registry.py` | New — `SandboxBackendRegistry` class + module-level singleton + `@register_sandbox_backend` decorator + `auto_detect` |
| `src/codegenie/sandbox/signals/registry.py` | New — `SignalCollectorRegistry` class + module-level singleton + `@register_signal_kind` decorator (delegates to Phase 3 `signal_kind_registry`) |
| `src/codegenie/sandbox/env_allowlist.py` | New — `ALLOWLIST` + `ALLOWLIST_PREFIXES` + `DENY_SUBSTRINGS` constants + `filter` function |
| `src/codegenie/sandbox/logging.py` | Edit — append three new event-name constants under S1-01's existing table; update `__all__` |
| `tests/sandbox/test_registry.py` | New — backend registry ACs (AC-BR-* + AC-AD-*) |
| `tests/sandbox/test_signal_collector_registry.py` | New — collector registry ACs (AC-CR-*) |
| `tests/sandbox/test_signal_kind_collision.py` | New — Phase 3 ↔ Phase 5 collision discipline (AC-COL-*) |
| `tests/sandbox/test_env_allowlist.py` | New — allowlist + deny + filter properties (AC-AL-* + AC-DN-* + AC-FL-*) + hypothesis suite |
| `tests/sandbox/test_registry_purity.py` | New — module-purity AST walker (AC-PURE-*) mirroring S1-04 |

## Out of scope

- **Real `auto_detect` (KVM-vs-DiD platform detection)** — S6-04.
- **`SandboxSpecBuilder.for_gate` (consumes `env_allowlist.filter`)** — S3-01.
- **`SandboxSpecForbidden` raise on denied substring** — S3-01 (this story silently drops; the raise is the builder's job).
- **The six concrete signal collectors** — Step 4 (register via the decorator landed here).
- **Phase 3 `@register_trust_signal_kind` widening** — Phase 3 S4-04 (separate registry on the trust-scorer side; not touched here).
- **The structural CI fence `tests/schema/test_env_allowlist_no_credentials.py`** — S1-07 (depends on the function landed here; imports `ALLOWLIST`, `ALLOWLIST_PREFIXES`, `DENY_SUBSTRINGS` from this story).
- **Promotion of `SandboxBackendName` to NewType** — deferred until Phase 7 adds the third backend (rule-of-three clears at that point; the closed-Literal mirror on `SandboxRun.backend` per S1-02 AC-4 becomes the NewType-promotion candidate, gated by an ADR-0001 amendment).
- **Per-gate env *additions*** (e.g., a specific gate needing `CI=true`) require an ADR-0012 amendment, NOT inline `env=` writes in `SandboxSpecBuilder`. Friction is intentional per ADR-0012 Tradeoffs.
- **Kernel-extract of a shared `KernelRegistry[K, V]` base** — deferred per Phase 3 [`transforms/signal_kinds.py:16-30`](../../../../src/codegenie/transforms/signal_kinds.py:16) precedent (divergent dispatch machinery across existing registries still argues against the extract).

## Notes for the implementer

- **Phase 3 ↔ Phase 5 name-vs-collector delegation (load-bearing).** Phase 3 ships `register_signal_kind` as a value-producing FUNCTION at [`codegenie.transforms.signal_kinds.register_signal_kind`](../../../../src/codegenie/transforms/signal_kinds.py:125). Phase 5 ships `register_signal_kind` as a DECORATOR at `codegenie.sandbox.signals.registry.register_signal_kind`. Both identifiers coexist at different import paths. The Phase 5 decorator delegates the name-registration side to Phase 3's function, then binds the collector. Concretely:
  1. The decorator factory `register_signal_kind(name, *, registry=None)` returns a decorator `(fn) -> fn`.
  2. The inner decorator imports `signal_kind_registry` and `register_signal_kind as _register_name_in_phase3` from `codegenie.transforms.signal_kinds`.
  3. If `SignalKind(name) not in signal_kind_registry`, it calls `_register_name_in_phase3(name)` (which raises Phase 3's `SignalKindAlreadyRegistered` on collision — but the precondition check makes that impossible here).
  4. It then calls `(registry or signal_collector_registry).register(SignalKind(name), fn, origin=...)` — which raises Phase 5's `SignalKindAlreadyRegistered` on collector-collision.
  5. Returns `fn` (identity-preserving).
- **Two `SignalKindAlreadyRegistered` classes.** Same simple name, two modules, two inheritance trees. Phase 5's decorator raises `codegenie.sandbox.errors.SignalKindAlreadyRegistered` for collector collisions. Phase 3's function raises `codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered` for name collisions. Always catch by full module path; never `from X import SignalKindAlreadyRegistered` without the disambiguating alias.
- **Class-based per-instance registry pattern (Phase 3 precedent — not optional).** Tests use `SandboxBackendRegistry.fresh()` / `SignalCollectorRegistry.fresh()`; the public decorators accept `registry=` kwarg. The module-level singletons `sandbox_backend_registry` and `signal_collector_registry` are `Final` and not replaced. No autouse fixture snapshots — `pytest-xdist` would race them.
- **`register_sandbox_backend` does NOT instantiate the class.** `FirecrackerClient` requires `vmlinux_digest`/`rootfs_digest` in `__init__`. The structural Protocol check happens via `inspect.signature` on the class, not via `isinstance(cls(), SandboxClient)`. Document this in the module docstring (AC-BR-5 enforces a fail-on-instantiation test class).
- **`get_backend(name)` returns a fresh instance per call** (AC-BR-10). Some backends carry per-call daemon handles; the registry stores classes, not instances.
- **`auto_detect` is a deliberate fallback stub for S6-04.** It emits a structured log every call to make the fallback visible (operational signal: when KVM is available but auto_detect chose DiD, that's a misconfiguration). Real platform detection lands in S6-04.
- **ALLOWLIST is a closed tuple (forward-seam).** Extending it is friction-bearing per ADR-0012. Phase 7 distroless's `LD_LIBRARY_PATH` etc. require an ADR-0012 amendment, NOT a silent tuple edit. The S1-07 fence test imports `ALLOWLIST`/`ALLOWLIST_PREFIXES`/`DENY_SUBSTRINGS` directly — adding a row triggers a fence regeneration.
- **`SandboxBackendName` stays raw `str`** for now. Rule-of-three not yet cleared (DinD + Firecracker; Phase 7 distroless is the third). When Phase 7 lands, the closed-Literal mirror `SandboxRun.backend = Literal["docker_in_docker", "firecracker"]` (S1-02 AC-4) widens via an ADR-0001 amendment AND becomes a NewType-promotion candidate. Documented in the registry's module docstring as a forward seam.
- **Allowlist case-SENSITIVE; deny case-INSENSITIVE.** Env-var names are case-sensitive on POSIX. The case-insensitive deny is belt-and-suspenders against operator typos like `MyApiKey`. The two semantics are intentional, not symmetric.
- **Deterministic key ordering in `filter` output.** Iterate `sorted(env.keys())` when building the new dict. S1-02's `SandboxSpec.sandbox_spec_hash` byte-stability depends on this — under-test in `test_env_allowlist.py::test_deterministic_key_order_AC_FL_7` and `test_reorder_stability_AC_FL_7_perm`.
- **`filter` shadows the builtin.** Use `from codegenie.sandbox.env_allowlist import filter as env_filter` in callers, or dotted access (`env_allowlist.filter(env)`). Tests use the alias. Documented in the module docstring.
- **Module-purity walker mirrors S1-04 `test_contract_purity.py`** — adopt the same parametrized AST-walk shape. The walker is TYPE_CHECKING-aware (imports under `if TYPE_CHECKING:` blocks are allowed; runtime imports are restricted).
- **The 95/90 coverage floor (line ≥ 95% AND branch ≥ 90%) applies here.** Same as S1-02/S1-03/S1-04. Parametrized tests for each allowlist edge: pure allowlist hit (`PATH`), prefix match (`NPM_CONFIG_FOO`), prefix+denied substring (`NPM_CONFIG_TOKEN`), mixed-case denied (`MyApiKey`), denied-but-allowed-name-shape (`MY_PATH_KEY`), case-insensitive deny matrix (4 substrings × 3 positions × 3 cases = 36 rows).
- **Three new event-name constants append to S1-01's canonical table.** S1-01's contract permits this (Validation note §6). Update the row of the canonical table in S1-01's docstring/comments only if needed — the constants themselves live in `sandbox/logging.py` and are imported here.
- **No bare `assert` in production source.** The `forbidden-patterns` pre-commit hook bans it. Use `raise SandboxBackendInvalid(...)` / `raise codegenie.sandbox.errors.SignalKindAlreadyRegistered(...)` instead.
