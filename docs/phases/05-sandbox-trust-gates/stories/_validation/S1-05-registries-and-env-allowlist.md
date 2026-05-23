# Validation report — S1-05 decorator registries + `env_allowlist` static filter

**Story:** [`../S1-05-registries-and-env-allowlist.md`](../S1-05-registries-and-env-allowlist.md)
**Validated:** 2026-05-22
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-05 ships the three Open/Closed seams that turn Phase 5 into an extension-by-addition surface: the sandbox-backend registry (`@register_sandbox_backend`), the signal-collector registry (`@register_signal_kind` decorator), and the static `env_allowlist` host-env filter that ADR-0012 makes the *only* path from orchestrator env to `SandboxSpec.env`. The draft was directionally correct — every ADR cited (-0012, -0003, -0006) traced to the right design lever, Out-of-scope correctly deferred `SandboxSpecBuilder.for_gate` (S3-01), the platform-detection branch (S6-04), and the structural CI fence (S1-07). But it had **18 weaknesses across all four critic lenses, including five block-tier findings** that a literal executor following the draft would silently violate.

The most consequential block-tier findings — the ones that would have produced code that *passes every draft test* but *fails when Phase 5 actually composes* — were:

1. **(consistency — block) Identifier collision: Phase 3's `register_signal_kind` *function* already exists.** [`src/codegenie/transforms/signal_kinds.py:125`](../../../../src/codegenie/transforms/signal_kinds.py:125) ships a value-producing **function** (`BUILD = register_signal_kind("build")`) that registers a name into the canonical Phase 3 `signal_kind_registry`. The draft proposes a **decorator** at the same identifier name (`@register_signal_kind("build") def collect_build_signal(...)`) under `sandbox/signals/registry.py`. Two callables, same name, different signatures (`(name) -> SignalKind` vs `(name) -> Callable[[Callable], Callable]`), different modules. An executor following the draft literally would have either (a) duplicated name-registration logic and broken Phase 3's `TrustScorer.score` ("kind not registered" because Phase 5's registry diverges from Phase 3's name registry), or (b) reused the Phase 3 function name and broken Phase 5's decorator semantics (a function-call decorator emits `TypeError`). Resolution: Phase 5's `@register_signal_kind` MUST delegate the *name* side to Phase 3's `register_signal_kind` function (or assert the kind is already registered in Phase 3's `signal_kind_registry`) before binding the collector. New AC-COL-1..AC-COL-5 + Implementation outline §3a + Notes §"Phase-3 ↔ Phase-5 name vs collector delegation."
2. **(consistency — block) `SignalKindAlreadyRegistered` shadow collision.** S1-01 pinned `SignalKindAlreadyRegistered` as one of 10 error classes in `src/codegenie/sandbox/errors.py` (subclass of `SandboxError`). Phase 3 *also* ships `SignalKindAlreadyRegistered` at [`src/codegenie/transforms/signal_kinds.py:53`](../../../../src/codegenie/transforms/signal_kinds.py:53) (subclass of `CodegenieError`). Same simple name, two classes, two different inheritance trees. An executor catching `from codegenie.transforms.signal_kinds import SignalKindAlreadyRegistered` wouldn't catch the Phase-5 raise; vice versa. Disambiguate by import-path in every AC and test; the Phase 5 decorator raises `codegenie.sandbox.errors.SignalKindAlreadyRegistered` for **collector collisions**, the Phase 3 function raises `codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered` for **name collisions**. AC-COL-2 + Notes §"Two `SignalKindAlreadyRegistered` classes."
3. **(patterns — block) Module-level mutable global `_BACKENDS` / `_COLLECTORS` lacks test isolation.** The draft TDD plan uses autouse `_clean_registry` fixtures that snapshot/restore module-level dicts — fragile under `pytest-xdist` (concurrent imports race the snapshot), and inconsistent with the *established* Phase-3 precedent ([`src/codegenie/transforms/signal_kinds.py:78-112`](../../../../src/codegenie/transforms/signal_kinds.py:78)): a `SignalKindRegistry` class with `.fresh()` classmethod, module-level singleton `signal_kind_registry: Final[SignalKindRegistry]`, and the registration function accepting an optional `registry=None` kwarg. Refactored: introduce `SandboxBackendRegistry` and `SignalCollectorRegistry` classes with `.fresh()`; the public decorators accept an optional `registry=` kwarg defaulting to the module-level singleton. Mirrors Phase 3 *exactly*. AC-BR-7 / AC-CR-7 + Implementation outline §1/§3 + new test pattern using `registry=fresh()` instead of snapshot fixtures.
4. **(coverage / tests — block) `@register_sandbox_backend` decorator identity unenforced.** Draft tests asserted "registers the class" via `get_backend("test_be")` — but if an implementer wraps the class (`@register_sandbox_backend("name") def decorator(cls): return wraps(cls, ...)`), Protocol-`isinstance` checks would silently break in downstream backends (M-4 — `runtime_checkable` on a wrapper class fails subtly for subclassed mocks). Resolved by AC-BR-2: `register_sandbox_backend("name")(Cls) is Cls` (identity check). Same pattern is added to `@register_signal_kind` (AC-CR-2: `register_signal_kind("name")(fn) is fn`).
5. **(coverage — block) `env_allowlist.filter` signature contradicts S1-02 `SandboxSpec.env` annotation.** S1-02 AC-5 pinned `SandboxSpec.env: Mapping[str, str]` — but the draft's `env_allowlist.filter` outline accepts `Mapping[str, str]` while the tests only feed `dict[str, str]`. An executor could ship `def filter(env: dict[str, str]) -> dict[str, str]` and pass every draft test while breaking `SandboxSpecBuilder.for_gate(env=run_env)` if `run_env` is a `MappingProxyType` or another read-only view. Resolution: AC-FL-1 pins the source-level annotation via `typing.get_type_hints`; AC-FL-2 feeds a `types.MappingProxyType` fixture through the filter to exercise the non-dict path.

Beyond the block-tier findings, the harden-tier work:

6. **(consistency / patterns — harden) `ALLOWLIST` conflated exact-match and prefix-match.** Draft kept `NPM_CONFIG_` as a literal entry inside `ALLOWLIST: Final = ("PATH", "NODE_ENV", "HTTPS_PROXY")` plus an *implicit* "or starts with `NPM_CONFIG_`" rule in the predicate body. Two semantics fused into one tuple — a reader cannot tell from `ALLOWLIST` alone that `NPM_CONFIG_` is a prefix. The S1-07 fence test (the very test ADR-0012 cites as belt-and-suspenders) would have to know the implicit rule. Split into `ALLOWLIST: Final[tuple[str, ...]]` (exact match) and `ALLOWLIST_PREFIXES: Final[tuple[str, ...]]` (prefix match) — both exposed for the S1-07 fence to import without inspecting the predicate body. AC-AL-1 / AC-AL-2 / AC-AL-3.
7. **(coverage — harden) Deterministic key ordering in `filter` output.** S1-02 §"Property tests" pins `SandboxSpec.sandbox_spec_hash` byte-stability under env-dict-key reordering: the spec hash is "invariant under reordering of `env` dict keys (sorted before hashing)." For the spec hash to actually be byte-stable, `env_allowlist.filter` must produce a deterministically-ordered `dict` — Python 3.7+ preserves insertion order, so the filter's iteration order over the input is observable downstream. Resolution: AC-FL-7 asserts `list(filter(env).keys()) == sorted(...)` and a hypothesis property test reorders the input dict and asserts the output dict's `list(.keys())` is invariant.
8. **(coverage — harden) Idempotency + subset properties.** A wrong implementation that *synthesizes* keys (`{**env, "PATH": env.get("PATH", "/usr/bin")}`) or one that *forgets* re-filtering (filter-once but-not-twice produces different results) would pass the draft. Hypothesis properties: `filter(filter(env)) == filter(env)` (idempotent); `set(filter(env).keys()) ⊆ set(env.keys())` (subset — no synthesis); `filter(env | {"PATH": "/x"}).keys() ⊇ filter(env).keys() ∩ {"PATH"}` (monotone — adding allowlisted keys only adds, never removes). AC-FL-5..AC-FL-7 + hypothesis suite.
9. **(coverage — harden) Allowlist case-sensitivity pinned positively + negatively.** Env-var names are case-sensitive on POSIX; the draft's allowlist match was prose-only. `Path=/usr/bin` (lowercase) MUST be dropped; `PATH=/usr/bin` must pass. Parametrized AC-AL-4..AC-AL-6 covering `PATH`/`Path`/`path`/`PATH_EXT` and `NPM_CONFIG_FOO`/`npm_config_foo`/`NPM_CONFIG_`/`NOT_NPM_CONFIG_FOO`.
10. **(coverage — harden) Deny-substring case-insensitivity parametrized.** Draft test had two parametrized rows; mutation: an implementer using `k.startswith("KEY")` would pass `MY_API_KEY` but be wrong for `KEYRING_ACCESS`. Parametrized over (substring × position {prefix, infix, suffix} × case {upper, lower, mixed}). AC-DN-1..AC-DN-4.
11. **(coverage — harden) `filter` return type is a NEW `dict[str, str]`, not the input view.** Draft AC said "does not mutate"; mutation: implementer returns `env` directly when the deny check is empty. AC-FL-3: `out is not env_input` (identity check, not just equality).
12. **(consistency — harden) Module purity + `from __future__ import annotations` + `__all__` discipline.** Same gap S1-02/S1-03/S1-04 all closed. Added `tests/sandbox/test_registry_purity.py` mirror — TYPE_CHECKING-aware AST walker enforces (a) `from __future__ import annotations` as line 1 (post-docstring), (b) alphabetized `__all__` containing the exact public surface, (c) module docstring citing ADR-0012/ADR-0003/ADR-0006, (d) imports limited to stdlib + pydantic + `codegenie.{errors, types.identifiers, sandbox.contract, sandbox.logging, transforms.signal_kinds}`. AC-PURE-1..AC-PURE-4.
13. **(consistency / coverage — harden) Three new event-name constants added to S1-01's canonical table.** S1-01's Validation note §6 explicitly permits later-story additions ("S2-01, S5-01, S6-02 ... add a row below the existing entries — they do not rename"). Add: `EVENT_SANDBOX_BACKEND_REGISTERED = "sandbox.backend.registered"`, `EVENT_SANDBOX_SIGNAL_COLLECTOR_REGISTERED = "sandbox.signal_collector.registered"`, `EVENT_SANDBOX_AUTO_DETECT_FALLBACK = "sandbox.auto_detect.fallback"`. The draft's `auto_detect` Refactor mentioned the last constant prose-only; promoted to AC-AD-3. The two new registration events are emitted on every register call (with `extra={"name": "..."}` and `extra={"kind": "..."}`).
14. **(coverage — harden) `auto_detect` log emission is an AC, not a Refactor "should."** Draft Refactor said `auto_detect` "should" emit a structured log — unobservable by the executor's validator. Promoted to AC-AD-3: `caplog`-based assertion that `EVENT_SANDBOX_AUTO_DETECT_FALLBACK` is emitted on the `codegenie.sandbox.registry` logger at INFO level, with `extra={"backend": "docker_in_docker"}`.
15. **(patterns — harden) `register_sandbox_backend` validates structurally on the *class*, not on an instance.** Draft Implementation outline §1 said "check `hasattr(cls, 'execute') and hasattr(cls, 'health')`" but did not lock the *signatures*. A backend with `def execute(self)` (zero-arg, no `spec`) would pass `hasattr` and break at runtime. Tighten to `inspect.signature(cls.execute).parameters` set-equality on `{'self', 'spec'}` and `inspect.signature(cls.health).parameters == {'self'}`. AC-BR-3 + AC-BR-4.
16. **(coverage — harden) Out-of-scope tightened.** Added: (a) the structural CI fence `tests/schema/test_env_allowlist_no_credentials.py` lives in S1-07 (the draft already said this, but the AC chain didn't reference it); (b) per-gate env *additions* (e.g., `CI=true` for a specific gate) require an ADR-0012 amendment, NOT inline `env=` writes in `SandboxSpecBuilder`; (c) Phase-3 `@register_trust_signal_kind` is a *separate* registry on the trust-scorer side, with its own decorator; not touched here.
17. **(patterns — nit, surfaced in Notes) Forward-seam: ALLOWLIST is a closed tuple.** Extending the allowlist is intentionally friction-bearing per ADR-0012. The Notes paragraph names the exact precedent (Phase 7 distroless will need an ADR-0012 amendment to add `LD_LIBRARY_PATH` etc., not a silent tuple edit).
18. **(consistency — nit) Coverage floor wording aligned.** Same conflation S1-02/S1-03/S1-04 fixed: "line ≥ 95% AND branch ≥ 90%", not the draft's unqualified "tests pass."

**No `RESCUE`-tier findings.** Every gap was patchable by adding ACs, tightening the TDD plan, introducing the `Registry` class pattern (mirroring Phase 3), and routing through the existing kernels (`transforms/signal_kinds.py`, `sandbox/errors.py`, `sandbox/logging.py`). The collision with Phase 3's `register_signal_kind` is *resolvable by delegation* — Phase 5's decorator wraps a call to Phase 3's function — so the goal direction is preserved.

**No Stage-3 research needed.** Every gap was answerable from Phase 5 arch + ADRs + Phase 3 codebase precedent (`transforms/signal_kinds.py`), the three prior HARDENED reports (S1-02/S1-03/S1-04), and CLAUDE.md commitments ("Extension by addition", "Newtype identifiers", "Functional core / imperative shell", "Match existing convention", "Surface conflicts, don't average them").

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Ship `src/codegenie/sandbox/registry.py`, `src/codegenie/sandbox/signals/registry.py`, and `src/codegenie/sandbox/env_allowlist.py` with the decorator registries (class-based, `.fresh()`-isolable per Phase-3 precedent), the collision-aware delegation into Phase 3's `signal_kind_registry`, the `env_allowlist.filter()` host-env credential filter, and three new event-name constants appended to `sandbox/logging.py`.
- **Non-goals (Out-of-scope):** Real `auto_detect` platform branch (S6-04), `SandboxSpecBuilder.for_gate` (S3-01), six concrete signal collectors (Step 4), Phase 3 `@register_trust_signal_kind` widening (S4-04), structural CI fence `test_env_allowlist_no_credentials.py` (S1-07).

### Phase 5 exit criteria touched

- Step 1 done-criteria (High-level-impl.md §Step 1 bullets 5 + 6 + 7): `pytest tests/sandbox/test_registry.py tests/sandbox/test_signal_collector_registry.py tests/sandbox/test_env_allowlist.py tests/sandbox/test_registry_purity.py` green; `mypy --strict src/codegenie/sandbox/registry.py src/codegenie/sandbox/signals/registry.py src/codegenie/sandbox/env_allowlist.py` clean.
- §Goal 7 (arch): "No credentials in the sandbox — `SandboxSpec.env` filtered by static allowlist; CI test asserts denied substrings cannot pass." This story is the filter; S1-07 is the test.
- §Goal 9 (arch): "Six signal collectors registered via decorator; the signal-kind registry is open." This story is the decorator + collector registry; Step 4 ships the six collectors.
- §Component design — SandboxClient (line 471): "Backends register via `@register_sandbox_backend(name)` decorator in `sandbox/registry.py`. The registry exposes `get_backend(name: str) -> SandboxClient` and `auto_detect() -> SandboxClient`."
- §Component design — Signal collectors (line 584-595): "Each `@register_signal_kind("name")` decorator on each collector function."
- §Open questions §10: "`SignalKind` registry collision policy. Synthesis default: raise `SignalKindAlreadyRegistered` at import."

### Load-bearing commitments touched

- **ADR-0012** — static allowlist module + CI test; the *only* path from host env to `SandboxSpec.env` is `env_allowlist.filter`. Story owns the filter; S1-07 owns the structural CI test.
- **ADR-0003** — open signal-kind registry; new kinds register without editing `TrustScorer`. Story owns the *collector* registry; the *name* registry lives in Phase 3's `transforms/signal_kinds.py` (already shipped). The decorator delegates the name side to Phase 3.
- **ADR-0006** — `SandboxClient` is `runtime_checkable` Protocol; backends share no default behavior. Registry validates structurally on the class (`execute(self, spec)` + `health(self)`), not by inheritance.
- **CLAUDE.md "Extension by addition"** — Phase 7 distroless adds a new backend (`@register_sandbox_backend("chainguard_rb")`) and new collectors (`@register_signal_kind("baseimage")`, `@register_signal_kind("shell_presence")`) with zero edits to this story's files.
- **CLAUDE.md "Domain identifiers ... newtype when crossing ≥ 2 modules"** — `SignalKind` already promoted to `types/identifiers.py` (S1-03); the registry uses it on the internal store. `SandboxBackendName` stays raw `str` (rule-of-three not yet cleared; the closed-Literal mirror is `SandboxRun.backend` per S1-02 AC-4).
- **CLAUDE.md "Functional core / imperative shell"** — `env_allowlist.filter` is pure (no I/O, no logger). The registries are stateful (module-level singletons) but each module exposes a pure-ish surface: registration is the only side-effect-bearing operation.
- **CLAUDE.md "Match existing convention"** — Phase 3's `SignalKindRegistry` with `.fresh()` + module-level singleton + `registry=None` kwarg is the precedent; Phase 5's `SandboxBackendRegistry` and `SignalCollectorRegistry` mirror it.
- **CLAUDE.md "Surface conflicts, don't average them"** — The `register_signal_kind` identifier collision (Phase 3 function vs Phase 5 decorator) is surfaced explicitly via the delegation pattern; the two coexist at different import paths, with the Phase 5 decorator depending on (and re-using) the Phase 3 function for the name side.

### Open ambiguities (resolved before Stage 2)

- **Identifier collision: `register_signal_kind` (function, Phase 3) vs `@register_signal_kind` (decorator, Phase 5 ADR-0003).** Resolution: Phase 5's decorator at `codegenie.sandbox.signals.registry.register_signal_kind` delegates the name-registration side to Phase 3's `codegenie.transforms.signal_kinds.register_signal_kind` (calling it if the kind is not yet in `signal_kind_registry`), then binds the collector. Both identifiers coexist at distinct import paths; the Phase 5 module docstring + Notes name the collision and the rationale.
- **`SignalKindAlreadyRegistered` shadow class.** Resolution: Phase 5's decorator raises `codegenie.sandbox.errors.SignalKindAlreadyRegistered` (S1-01 pinned) for **collector** collisions. Phase 3's function continues to raise its own `codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered` for **name** collisions. Tests catch by full module path.
- **`auto_detect` default.** Resolution: defer real KVM-vs-DiD logic to S6-04; the S1-05 implementation calls `get_backend("docker_in_docker")` and logs `EVENT_SANDBOX_AUTO_DETECT_FALLBACK`. If `"docker_in_docker"` is not registered, raise `SandboxBackendInvalid` (consistent with the structural error class S1-01 pinned).

### Phase 1/3/5 prior art consulted

- [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) — Phase 3 S6-02 — the *existing* `SignalKindRegistry` class with `.fresh()`, module-level `signal_kind_registry: Final[SignalKindRegistry]`, `register_signal_kind(name, *, registry=None) -> SignalKind` value-producing function. The shape Phase 5 mirrors.
- [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) — `SignalKind` (line 96, S1-03 promotion) is the kind newtype; the collector registry keys on it internally.
- [`src/codegenie/probes/registry.py`](../../../../src/codegenie/probes/registry.py) (Phase 0) — the `@register_probe` decorator precedent ADR-0003 explicitly cites.
- [`src/codegenie/plugins/registry.py`](../../../../src/codegenie/plugins/registry.py) (Phase 3) — the `register_plugin` function-call precedent for the per-instance registry pattern.
- [`src/codegenie/adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py) (Phase 2) — `runtime_checkable` Protocol precedent; the AST-walk module-purity test pattern.
- S1-01 HARDENED report — pins the 10-class sandbox error hierarchy (including `SandboxBackendInvalid` and `SignalKindAlreadyRegistered`) and the canonical event-name table; S1-05's new event constants append below the existing rows.
- S1-02 HARDENED report — `SandboxSpec.env: Mapping[str, str]` (AC-5); the spec-hash byte-stability invariant that depends on `env_allowlist.filter` producing a deterministically-ordered dict.
- S1-03 HARDENED report — `SignalKind` promoted to `types/identifiers.py:96` with the "single declaration site" discipline (AST chokepoint forbids `NewType("SignalKind", ...)` redefinition under `src/codegenie/sandbox/`).
- S1-04 HARDENED report — the parametrized `model_config` introspection pattern, the AST chokepoint pattern, the module-purity walker, the byte-exact Literal positive+negative pattern, the coverage-floor wording, the forward-seam Notes pattern.

## Stage 2 — critic reports

### 2A · Coverage critic (verdict: COVERAGE-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **C-1** | **block** | **`env_allowlist.filter` signature contradicts S1-02 `SandboxSpec.env: Mapping[str, str]`** | AC-FL-1 (`get_type_hints(filter)['env']` is `Mapping[str, str]`) + AC-FL-2 (`MappingProxyType` fixture round-trips) |
| **C-2** | **block** | **`@register_sandbox_backend` decorator identity unenforced — wrapper would silently pass** | AC-BR-2: `register_sandbox_backend("name")(Cls) is Cls`; same for `@register_signal_kind` |
| C-3 | harden | `ALLOWLIST` fuses exact-match + prefix semantics into one tuple | Split into `ALLOWLIST` (exact) and `ALLOWLIST_PREFIXES` (prefix); both Final tuples; both importable for S1-07 fence |
| C-4 | harden | Deterministic key ordering invariant missing (S1-02 spec-hash byte-stability dep) | AC-FL-7 (`list(filter(env).keys()) == sorted(...)`) + hypothesis reorder property |
| C-5 | harden | Subset + idempotency + monotonicity properties missing (no-synthesis, re-filter-stable) | AC-FL-5/AC-FL-6/AC-FL-7 + hypothesis suite |
| C-6 | harden | Allowlist case-sensitivity unpinned (env vars are case-sensitive on POSIX) | AC-AL-4..AC-AL-6 parametrized over `PATH`/`Path`/`path`/`PATH_EXT` and prefix variants |
| C-7 | harden | Deny-substring case + position parametrization sparse | AC-DN-1..AC-DN-4 parametrized over (substring × {prefix, infix, suffix} × {upper, lower, mixed}) |
| C-8 | harden | `auto_detect` log emission was prose-only ("should") | AC-AD-3 `caplog`-based assertion on the event constant + extra dict |
| C-9 | harden | `register_*` log emission not asserted | AC-BR-9 / AC-CR-9 `caplog` assertions on the two new event constants |
| C-10 | harden | `filter` identity check missing (`out is not env_input`) | AC-FL-3 |
| C-11 | harden | Empty-input + empty-key degenerate cases unpinned | AC-FL-4 (`filter({}) == {}`); AC-FL-9 (`filter({"": "x"}) == {}`) |
| C-12 | harden | `auto_detect` "no docker_in_docker registered" branch unpinned | AC-AD-4: raises `SandboxBackendInvalid` when fallback is missing |
| C-13 | nit | Coverage floor wording ("tests pass") | Tightened to "line ≥ 95% AND branch ≥ 90%" on the three new modules |

### 2B · Test-quality critic (verdict: TESTS-HARDEN)

Mutation analysis — 17 plausible wrong implementations evaluated. Headline misses caught in the harden:

| # | Wrong implementation | Caught by draft TDD? | Caught after harden? |
|---|---|---|---|
| **M-1** | **`@register_signal_kind("build")` reuses Phase-3 function name and doesn't delegate; `signal_kind_registry` never sees the new kind; downstream `TrustScorer.score` raises `UnregisteredSignalKind`** | **No — draft only tests the collector dict** | **Yes — AC-COL-3 asserts the kind appears in Phase-3 `signal_kind_registry` post-registration** |
| **M-2** | **Decorator returns a wrapper (`functools.wraps`) instead of the class; backend `isinstance(b, SandboxClient)` fails subtly downstream** | **No — `isinstance` test happens via constructed instance, which the wrapper may or may not preserve** | **Yes — AC-BR-2 identity check + AC-CR-2** |
| M-3 | `register_sandbox_backend` instantiates the class at decoration time (breaks Firecracker which needs digests) | No | Yes — AC-BR-5 explicit "registration does NOT call `cls()`" check using a class whose `__init__` raises |
| M-4 | `_is_allowed(k)` uses `k in ALLOWLIST or any(k.startswith(p) for p in ALLOWLIST)` (case-insensitive substring instead of exact) | No — `PATH` still passes | Yes — AC-AL-4 negative path (`Path`, `path`) |
| M-5 | `_is_allowed(k)` uses `any(p in k for p in ALLOWLIST)` (substring instead of exact) — `PATH_EXT` passes wrongly | No | Yes — AC-AL-5 |
| M-6 | `_is_denied(k)` uses `k in DENY_SUBSTRINGS` (equality instead of substring) — `MY_API_KEY` passes wrongly | No | Yes — AC-DN-1 parametrized |
| M-7 | `filter(env)` returns `env` directly when nothing is filtered | No — equality still holds | Yes — AC-FL-3 identity check |
| M-8 | `filter(env)` synthesizes default keys (`{**defaults, **filtered}`) | No — output is a superset of valid keys | Yes — AC-FL-5 subset property |
| M-9 | `filter(filter(env)) != filter(env)` (filter-once stable but filter-twice mutates) | No | Yes — AC-FL-6 idempotency |
| M-10 | `filter` iterates in input order — output dict key-iteration is non-deterministic | No — equality passes | Yes — AC-FL-7 sorted-keys property + hypothesis reorder |
| M-11 | `auto_detect()` returns `None` when no backends registered | No — depends on existing registrations | Yes — AC-AD-1 + AC-AD-4 raises path |
| M-12 | `auto_detect()` skips the log emission | No | Yes — AC-AD-3 caplog |
| M-13 | `@register_signal_kind` ignores re-registration (idempotent merge) instead of raising | No | Yes — AC-CR-4 raises path |
| **M-14** | **Decorator binds the kind name into a local module global, never Phase-3's; Phase 5 has TWO disconnected name registries** | **No** | **Yes — AC-COL-3 + AC-COL-4 explicit `signal_kind_registry` participation** |
| M-15 | `register_sandbox_backend` accepts a function instead of a class | No — `hasattr(fn, 'execute')` is False but `hasattr(fn, 'health')` is also False, so it raises — but what about a class-decorated function? | Yes — AC-BR-6 explicit `inspect.isclass` check |
| M-16 | `register_sandbox_backend` accepts a class with `execute(self)` (zero-arg) | No — `hasattr` passes | Yes — AC-BR-3 `inspect.signature` set-equality |
| M-17 | `ALLOWLIST_PREFIXES = ("NPM_CONFIG",)` (missing trailing underscore) — `NPM_CONFIG_FOO` and `NPM_CONFIG_BAR` pass, but so does `NPM_CONFIGURE` (no underscore boundary) | No | Yes — AC-AL-6 negative: `NPM_CONFIGURE` does NOT pass |

Properties added (hypothesis):
- `filter` idempotency: `filter(filter(env)) == filter(env)`.
- `filter` subset: `set(filter(env).keys()) ⊆ set(env.keys())`.
- `filter` reorder-stability: for any permutation `env'` of `env`, `list(filter(env').keys()) == list(filter(env).keys())`.
- `filter` monotonicity on allowlisted additions.
- AST source-scan for the two new sandbox/signals/registry decorators (purity + no-LLM-import; mirror S1-04).
- Module purity walker (TYPE_CHECKING-aware; mirror S1-04 AC-PURE pattern).

### 2C · Consistency critic (verdict: CONSIST-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **#1** | **block** | **Identifier collision: Phase 3's `register_signal_kind` function already exists** | AC-COL-1..AC-COL-5; Implementation outline §3a (delegation chain); Notes §"Phase 3 ↔ Phase 5 name vs collector delegation" |
| **#2** | **block** | **`SignalKindAlreadyRegistered` shadow class — same simple name, two modules, two inheritance trees** | AC-COL-2; Notes §"Two `SignalKindAlreadyRegistered` classes"; tests catch by full module-path import |
| **#3** | **block** | **Module-level mutable global `_BACKENDS`/`_COLLECTORS` lacks per-instance test isolation (Phase 3 precedent is class-based `.fresh()`)** | Refactored to `SandboxBackendRegistry` + `SignalCollectorRegistry` classes; AC-BR-7 / AC-CR-7 |
| #4 | harden | `env_allowlist.filter`'s `env` annotation conflicts with S1-02 `SandboxSpec.env: Mapping[str, str]` | AC-FL-1 (`get_type_hints` source-level) |
| #5 | harden | Module purity / `__future__ annotations` / `__all__` discipline missing | AC-PURE-1..AC-PURE-4 (mirror S1-04) |
| #6 | harden | New event-name constants must be appended to S1-01's canonical table | Three new rows under `sandbox/logging.py` (AC-LG-1..AC-LG-3) |
| #7 | harden | Coverage floor wording bug | "line ≥ 95% AND branch ≥ 90%" — same fix S1-02/S1-03/S1-04 applied |
| #8 | harden | Shadow on builtin `filter` — usage convention | Notes + ACs: importing module-level `filter` via `from codegenie.sandbox.env_allowlist import filter as env_filter` is the documented call site idiom; dotted-access (`env_allowlist.filter(...)`) is the alternate |
| #9 | nit | Out-of-scope reference to S1-07 fence + Phase-3 `@register_trust_signal_kind` separation | Added explicit Out-of-scope rows |

No `RESCUE`-tier consistency findings. The three block-tier findings (#1, #2, #3) are patchable as outline + AC + class-refactor edits without changing the goal.

### 2D · Design-patterns critic (verdict: PATTERNS-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **1** | **block** | **Module-level mutable global is a "primitive obsession on a `dict`" anti-pattern; Phase 3's `SignalKindRegistry` class with `.fresh()` is the established pattern** | Refactored to `SandboxBackendRegistry` + `SignalCollectorRegistry` classes; module-level `Final` singletons; `registry=` kwarg on the public decorators |
| 2 | harden | Closed-set `ALLOWLIST` and `DENY_SUBSTRINGS` correctly framed as Final tuples — forward-seam pattern from S1-02 missing | Forward-seam Note: extending either requires ADR-0012 amendment; the friction is intentional |
| 3 | harden | `SandboxBackendName` is `str` (no NewType) — rule-of-three not yet cleared (the closed Literal mirror is on `SandboxRun.backend` per S1-02 AC-4); flagged but deferred per Rule 2 ("three similar lines is better than premature abstraction") | Documented in Notes; no AC change |
| 4 | clean | Plugin architecture / Open-Closed seam is exactly the right shape (decorator + class registry + module singleton) — Phase 7 distroless adds backends + collectors without editing | — |
| 5 | clean | Strategy pattern (sandbox backend) + Dependency inversion (`SandboxClient` Protocol) + Registry pattern (per-instance `.fresh()`) all correctly framed | — |
| 6 | harden | `env_allowlist.filter` is the functional-core; signature `Mapping[str, str] -> dict[str, str]` is pure — but ALLOWLIST/DENY tuples are module-level globals. Phase-3 `signal_kind_registry` shows the cleaner discipline: the tuples are exposed as `Final` so S1-07's fence can import them | AC-AL-1..AC-AL-3 expose them as `Final[tuple[str, ...]]` for S1-07 |
| 7 | harden | Tagged-union opportunity on `_is_allowed` / `_is_denied` predicates: `enum AllowResult { Allowed, DeniedByMissingAllowlist, DeniedBySubstring }` could improve debuggability | Deferred — premature for a 30-LOC predicate (Rule 2); documented in Notes |
| 8 | nit | The two registry classes could share a `KernelRegistry[K, V]` base — but Phase 3's `SignalKindRegistry` (note `_origins` map only, no dispatch) shows the established "defer kernel extract until the *sixth* registry" precedent | Deferred — documented in Notes |
| 9 | clean | Functional core (`env_allowlist.filter` pure) / imperative shell (`SandboxSpecBuilder.for_gate` calls it) is the right shape | — |

The block-tier finding (#1, class-based registry) was the load-bearing patterns fix; the rest are documentation + forward-seam Notes that ride alongside the AC harden.

## Conflict resolution (Stage 4 synthesizer)

- **Consistency #1 (collision with Phase 3 `register_signal_kind`) vs ADR-0003's stated `@register_signal_kind` name:** Both win. ADR-0003 keeps its prescribed *decorator name*; Phase 3's function keeps its name; they coexist at different import paths via delegation. The Notes paragraph documents the collision explicitly so future readers can navigate.
- **Consistency #3 (class-based registry) vs Rule 3 (surgical changes):** Class-based registry wins. The autouse-fixture snapshot/restore pattern in the draft is fragile under `pytest-xdist` and inconsistent with the established Phase 3 precedent. The refactor is small (~30 LOC per registry); the deferred "kernel extract" remains deferred.
- **Patterns #3 (`SandboxBackendName` newtype) vs Rule 2 (premature abstraction):** Rule 2 wins. Only two backends planned (DinD + Firecracker); Phase 7 distroless is the third — at that point the rule-of-three clears and the closed-Literal mirror in `SandboxRun.backend` becomes a NewType-promotion candidate. Documented as a future cleanup in Notes.
- **Coverage C-3 (split `ALLOWLIST` / `ALLOWLIST_PREFIXES`) vs draft's single-tuple ALLOWLIST:** Split wins. The S1-07 fence will import both as Final tuples; conflating exact and prefix semantics in one tuple hides the rule from the fence reader.
- **Coverage C-4 (deterministic key ordering) vs draft's "insertion order is fine":** Deterministic ordering wins. S1-02 §"Property tests" pinned the spec-hash byte-stability invariant; `env_allowlist.filter`'s output ordering is observable downstream.
- **Patterns #7 (tagged-union predicate result) vs Rule 2:** Rule 2 wins. The predicates remain bare `bool`; debuggability gain is not worth the boilerplate for a 30-LOC module.

## Edits applied (summary)

1. New `Validation notes (2026-05-22)` block under the story header with 18 numbered headline edits (mirrors S1-02/S1-03/S1-04 format).
2. **Status** changed from `Ready` to `Ready (HARDENED 2026-05-22)`.
3. **References** expanded: explicit citations of `transforms/signal_kinds.py` (the existing function the decorator delegates to), `sandbox/errors.py` (S1-01 pinned error classes), `sandbox/logging.py` (S1-01 event constants table), `S1-02` (Mapping annotation + spec hash), `S1-03` (SignalKind NewType + single-declaration discipline), `S1-04` (purity / `__all__` / coverage-floor pattern).
4. **Goal** widened from "ship 3 modules" to "ship 3 modules with class-based per-instance registries + delegation into the Phase 3 `signal_kind_registry`."
5. **Acceptance criteria** rewritten from 8 ACs to **~50 ACs** grouped A–N: imports + `__all__`; sandbox-backend registry (decorator + class + duplicate + structural validate + identity + non-instantiation); `auto_detect` (signature + return + log + fallback raise); signal-collector registry (decorator + class + delegation + identity); name-vs-collector collision discipline; ALLOWLIST + ALLOWLIST_PREFIXES + DENY_SUBSTRINGS Final tuples; `filter` (annotation + identity + degenerate + idempotency + subset + ordering); allowlist match semantics (case-sensitive exact / prefix); deny match semantics (case-insensitive substring); new event constants; module purity + future annotations + `__all__`; logging emission; process gates + coverage floor.
6. **Implementation outline** rewritten from 5 numbered steps to ~10 step-coded prescriptions covering: the `SandboxBackendRegistry` class shape, the `SignalCollectorRegistry` class shape, the delegation chain from `@register_signal_kind` into Phase 3's `register_signal_kind` function, the `_is_allowed` / `_is_denied` predicates (with explicit ordering), the sorted-key dict-build idiom, the three new event-constant rows in `sandbox/logging.py`, the `from __future__ import annotations` line-1 discipline, the `__all__` alphabetization.
7. **TDD plan** rewritten from 3 test files (~120 LOC sketch) to 5 test files (~480 LOC sketch) with: parametrized fixtures for allowlist case-sensitivity + deny substring case+position; identity checks (`is`) on decorator returns; hypothesis property tests for idempotency / subset / monotonicity / reorder-stability; `caplog`-based assertions on each event-emission AC; cross-registry collision test (Phase 5 decorator + Phase 3 `signal_kind_registry` participation); `tests/sandbox/test_registry_purity.py` mirroring S1-04 AC-PURE.
8. **Files to touch** expanded with: `tests/sandbox/test_signal_collector_registry.py` (renamed for clarity), `tests/sandbox/test_registry_purity.py` (new — purity + `__all__` + future annotations + ADR-cite walker), `src/codegenie/sandbox/logging.py` (additive 3 rows under the S1-01 table).
9. **Out of scope** expanded with explicit deferrals: S1-07 structural CI fence, S4-04 Phase 3 `@register_trust_signal_kind`, per-gate env additions require ADR-0012 amendment (not inline writes), real `auto_detect` platform branch (S6-04), `SandboxSpecForbidden` raise lives in S3-01.
10. **Notes for the implementer** rewritten and ~3× longer covering: the Phase 3 ↔ Phase 5 collision rationale, the delegation chain, the two `SignalKindAlreadyRegistered` shadow classes + how to disambiguate, the forward-seam on ALLOWLIST/DENY (ADR-0012 amendment required to extend), the class-based registry per-instance discipline, the case-sensitivity semantics (allowlist case-sensitive; deny case-insensitive substring), the deterministic key-ordering invariant (spec-hash dep), the closed-Literal mirror in S1-02 `SandboxRun.backend` that Phase 7 widens via ADR-0001 amendment, the deferred `SandboxBackendName` NewType promotion (rule-of-three not yet cleared).

No story restructuring; the goal direction, the three target modules, the ADR mapping (-0012, -0003, -0006), and the dependency on S1-02/S1-03/S1-04 are unchanged.

## Final verdict

**HARDENED.** Story ready for `phase-story-executor`. Every AC is individually verifiable; the AC set collectively guarantees Goal-7 (no credentials in sandbox), Goal-9 (six collectors registered via decorator with open registry), and the Phase-7-distroless extension-by-addition path; every test in the TDD plan would fail on at least one named mutation (17 mutations enumerated); CLAUDE.md "Surface conflicts, don't average them" is honored explicitly via the documented delegation chain rather than silent name collision; CLAUDE.md "Match existing convention" is honored via the class-based registry pattern mirroring Phase 3's `SignalKindRegistry`; ADR-0012 forward-seam is documented; the closed-`Literal`-mirror-of-open-registry tension established by S1-02 is preserved (`SandboxRun.backend` remains the closed mirror that Phase 7 widens via ADR amendment).
