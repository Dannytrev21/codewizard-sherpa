# Validation report — S4-03 `SandboxExecAdapter` (macOS) + `tooling/sandbox/macos-npm.sb`

**Verdict:** HARDENED
**Validated:** 2026-05-18
**Story file:** `../S4-03-sandbox-exec-adapter-macos.md`

## Summary

Story is the macOS sibling of S4-02 and inherits most of S4-02's hardening surface as parallel BLOCK / HARDEN findings. Four critics surfaced 4 BLOCK-grade structural issues (chokepoint API mismatch with `run_external_cli`; `hasattr(adapter, "run")` mutation-trivial Protocol check; missing rule-of-three consumption of S4-02-extracted `_classify_outcome` kernel; brittle `tooling/`-relative template-load path that fails wheel install), plus 12 HARDEN-grade gaps (substrate-parse-failure swallowed; concurrent .sb race; cleanup-on-exception untested; hostname-extraction primitive obsession; missing determinism / property / typed-error / stateless ACs; ordering check promised by AC-3 not enforced; `subprocess.run(["pytest","--markers"])` brittle; macOS 14+ gate missing) and 4 NIT-grade items.

All BLOCKs are fixable through AC rewriting + Implementation-outline correction + a doc-debt note coordinated with S4-02's pending ADR-0012 amendment. No `phase-story-writer` re-run needed. Edits applied in place; the hardened story now consumes the S4-02 `_classify_outcome` kernel (rule-of-three threshold REACHED), mirrors S4-02's hardened ACs for parity, and pins the macOS-specific failure surface (substrate-setup, denial-stderr parsing, version gating).

## Context Brief

- **What the story promises:** `tooling/sandbox/macos-npm.sb` template + `SandboxExecAdapter(SubprocessJail)` at `src/codegenie/transforms/sandbox/sandbox_exec.py` + unit tests + nightly-only macOS integration tests. Mirror of S4-02 on the macOS substrate.
- **Phase exit criterion this serves:** Goal G1 on macOS operator laptops; Hexagonal Port pattern's second-Adapter payoff.
- **Sibling-family lineage:** This is the **2nd concrete Adapter** of `SubprocessJail`; Phase 5's Firecracker/DinD is the 3rd. **Rule-of-three threshold REACHED** at this story — kernel extraction is no longer hypothetical, it is mandatory. S4-02 already extracted `_classify_outcome` to `src/codegenie/transforms/sandbox/_classify.py` and a `Syscall` `StrEnum`; this story must consume them, not duplicate.
- **Arch + ADR constraints:** ADR-0006 pins `sandbox-exec -f <generated.sb>` + `deny default` + macOS 14+ + nightly-only CI; ADR-0012 admits `sandbox-exec` to `ALLOWED_BINARIES` (S4-05's data change); ADR-0010 mandates `match` on sum-types; ADR-0011 mandates `importlib.resources` for packaged static assets.
- **CLAUDE.md commitments:** "Extension by addition" (rule-of-three kernel must be consumed); "Functional core / imperative shell" (renderer pure, writer impure, no entanglement); "Newtype identifiers" (hostname extraction must not collapse `RegistryUrl` to bare `str`); "Match the existing convention" (mirror S4-02 helper shapes + hardened AC parity).

## Stage 2 — Critic reports

Four critics ran in parallel. Severity legend: `block` = must rewrite/coordinate before executor; `harden` = real gap a mutant would survive; `nit` = small polish.

### Critic A — Coverage

| # | Severity | Title |
|---|---|---|
| B1 | block | `run_external_cli` chokepoint inherited from S4-02 BLOCK — `env_extra` not on signature; closed-set deny still in regression. |
| B2 | block | Profile-parse-failure (substrate setup non-zero) has no AC; Notes L405 swallows it into a sentinel `Completed`. |
| B3 | block | Cleanup-on-exception untested — `.sb` file leaks on `run_external_cli` raise. |
| H1 | harden | Concurrent-run race: fixed `<spec.cwd>/.sandbox-exec.sb` filename collides on shared `cwd`. |
| H2 | harden | Hostname extraction edge cases (port, IPv6, userinfo) unspecified. |
| H3 | harden | Determinism + property tests missing (parallel to S4-02 AC-17/18). |
| H4 | harden | Stateless-across-calls AC missing (parallel to S4-02 AC-22). |
| H5 | harden | `_classify_outcome` consumption not pinned (parallel to S4-02 AC-23). |
| H6 | harden | `match spec.network` exhaustiveness not pinned (parallel to S4-02 AC-25). |
| H7 | harden | macOS 14+ version gate per ADR-0006 untested; older macOS silently produces a broken profile. |
| H8 | harden | AC-10/AC-11 "skip if sandbox-exec missing" violates fail-not-skip discipline on the nightly macOS runner. |
| H9 | harden | AC-12 `subprocess.run(["pytest","--markers"])` is brittle (PATH-dependent, shell-spawn from tests). |
| N1 | nit | AC-1 wording lists `/usr`, `/Library/Developer/CommandLineTools`, `/System`; template skeleton (L92) lists `/usr/lib`, `/usr/bin`, `/usr/local/bin`, etc. Mismatch. |
| N2 | nit | AC-7 NetworkDenied tested via `_fakes_for_tests` indirection (parallel TQ-3 finding). |
| N3 | nit | `(allow network* (local unix))` not addressed — macOS npm uses unix-domain IPC. |
| N4 | nit | Empty `spec.cmd` and zero-host `RegistryAllowlist` edge cases unspecified. |

### Critic B — Test Quality (mutation-resistance)

| # | Severity | Title |
|---|---|---|
| F1 | block | AC-2 `hasattr(adapter, "run")` mutation-trivial; passes for `run = None`. |
| F2 | block | AC-6 substring grep escapable (`from subprocess import run`, `getattr`, `os.exec*`, `os.spawn*`, `posix_spawn`, `importlib.import_module("subprocess")`). |
| F3 | block | AC-7 result-variant translation via `_fakes_for_tests.inject_fake_outcome` indirection — pins nothing concrete. |
| F4 | harden | AC-3 prose promises ordering of `(version 1)` + `(deny default)`; test only asserts substring presence. |
| F5 | harden | AC-12 shells out to `pytest --markers`; use `pytestconfig` / `tomllib`. |
| F6 | harden | Hypothesis property tests missing (DenyAll → no network*, allowlist coverage, determinism). |
| F7 | harden | Typed-error fence, cleanup-on-exception, concurrent-run ACs entirely absent. |
| F8 | harden | Profile-syntax validity untested at any tier; balanced-paren or nightly `sandbox-exec -p` check would catch dumb mutants. |
| F9 | harden | Notes L405 "translate substrate-setup failure to sentinel `Completed(exit_code=...)`" violates Rule 12 ("Fail loud") — caller can't distinguish jail-failure from child-failure. |
| F10 | nit | AC-15 polarity check is good but doesn't catch a mutant with sweeping `(allow file-write*)` without target. |
| F11 | nit | `FakeSandboxedPath` import path stale; `# type: ignore[arg-type]` everywhere is a structural-Protocol smell. |
| F12 | nit | AC-7 NetworkDenied asserts only `isinstance`, not `.host == "github.com"` — host field uncovered. |

### Critic C — Consistency

| # | Severity | Title |
|---|---|---|
| C-1 | block | `run_external_cli` is the wrong chokepoint (mirrors S4-02 C-1) — `env_extra` not on signature; `run_allowlisted` is the corrected target. |
| C-2 | block | AC-2 uses `hasattr` for Protocol check; S4-01 forbids `@runtime_checkable`, but S4-02 hardened to structural mypy + `inspect.signature` + `_StubJail` call-site test. |
| C-3 | block | Kernel-consumption AC missing — `_classify_outcome` extracted by S4-02 must be consumed (rule-of-three reached). |
| C-4 | harden | `str(spec.cwd.absolute)` is a bound-method-repr bug; `.absolute` is a method, not a property (mirrors S4-02 C-4). |
| C-5 | harden | `codegenie.transforms.sandbox._fakes_for_tests` places test scaffolding under `src/` — S4-02 moved this to `tests/unit/transforms/sandbox/_fakes.py`. |
| C-6 | harden | Integration-test import `from codegenie.plugins.sandbox_path import SandboxedPath` — that module does not exist; today's canonical import is `from codegenie.transforms import SandboxedPath` per `transforms/_forward.py`. |
| C-7 | harden | Template at `tooling/sandbox/macos-npm.sb` loaded via four-`.parent` hops breaks on wheel install. Use `importlib.resources` + package the template under `src/codegenie/transforms/sandbox/templates/`. |
| C-8 | harden | `_render_profile` switches via `isinstance` ladder; ADR-0010 / S1-03 mandate `match` exhaustiveness. |
| C-9 | harden | Hostname extraction collapses `RegistryUrl` newtype to raw `str`; smart-constructor `_extract_hostname` needed. |
| C-10 | harden | `{{JAIL}}` / `{{ALLOWLIST_HOSTS}}` placeholders are bare strings — `string.Template` (`$JAIL`/`$ALLOWLIST_HOSTS` + `safe_substitute` + post-substitute residual check) is the stdlib idiom that fails loud on a typo. |
| C-11 | harden | AC-12 `subprocess.run(["pytest","--markers"])` — `tests/adv/test_no_shell_true.py` family bans broad subprocess from tests; use `pytestconfig`. |
| C-12 | nit | ADR-0012 §Decision wording drift acknowledgment missing (sibling S4-02 carries it). |
| C-13 | nit | Goal §3 reads "exit signals" — macOS denial is stderr-parsed, not signal-borne. |

### Critic D — Design Patterns

| # | Severity | Title |
|---|---|---|
| D-1 | block | Rule-of-three kernel `_classify_outcome` REACHED — second adapter MUST consume, not duplicate. |
| D-2 | block | `NetworkPolicy` `isinstance` ladder — must be `match` with `assert_never` exhaustiveness. |
| D-3 | block | Template-file location anti-pattern (`tooling/` outside wheel); use `importlib.resources` + packaged template. |
| D-4 | harden | Hidden state: module-level `_TEMPLATE = Path(...).read_text()` at import; use `@functools.cache`. |
| D-5 | harden | Pure-impure tangle: AC-3 captures rendered text via monkeypatched file-write. Renderer should be a pure `str → str` callable in tests with zero I/O. |
| D-6 | harden | Concurrency + cleanup-on-exception missing (parallel to S4-02 AC-19/20). |
| D-7 | harden | Bare hostname `str` flows through profile emission; `_extract_hostname(url) -> Hostname` smart-constructor needed. |
| D-8 | nit | Placeholder tokens as bare strings — `string.Template` mechanism preferred (overlaps C-10). |
| D-9 | harden | Hexagonal-shape parity not pinned at file boundary — AC needed asserting both adapters share helper-name set. |
| D-10 | nit | Generator-emitted network clauses must go through typed `AllowNetworkClause` helper, not f-string interpolation. |
| D-11 | nit | Resist substrate-registry pattern (`@register_jail`) — constructor injection at recipe-engine layer is the right shape (parallel to S4-02 D-N1). |
| D-12 | harden | Module-level statelessness AC parity (S4-02 AC-22). |

## Stage 3 — Researcher

**Skipped.** No critic finding tagged `NEEDS RESEARCH`. Every fix has either an in-codebase precedent (S4-02 hardened story; `test_outcomes_mypy_negative.py`; ADR-0011 grammar-wheel `importlib.resources` precedent; Phase 2 ADR-0006 sum-type discipline; Phase 0 `Syscall`-like `StrEnum` patterns) or a standard library tool (`string.Template`, `inspect.signature`, `ast`, `hypothesis`, `tomllib`).

## Stage 4 — Synthesis + edits applied

**Conflict-resolution decisions:**

- **Consistency C-1 / Coverage B1 / TQ-implicit / D-H6 — chokepoint:** Apply S4-02's resolved decision — replace `run_external_cli` with `run_allowlisted` throughout. ADR-0012 §Decision wording is doc-debt (shared with S4-02 attempt log).
- **Pure-impure tangle (D-5) vs AC-3-as-written:** D-5 wins — rewrite AC-3 to call `_render_profile(template_str, spec) -> str` directly with no monkey-patch. A separate AC covers the impure writer.
- **`string.Template` vs `{{JAIL}}`:** Adopt `string.Template` (`$JAIL`, `$ALLOWLIST_HOSTS` + `safe_substitute` + post-substitute residual regex assertion). Fails loud on placeholder typo per Rule 12.
- **AC-10/AC-11 skip vs fail (H8):** Fail wins (mirrors S4-02 hardened-AC discipline). On `sys.platform == "darwin"` + missing sandbox-exec → `pytest.fail("nightly macOS runner broken")`. Only non-darwin path skips.
- **Substrate-setup failure (F9 / B2):** Add typed `SubstrateSetupFailed(reason: str, stderr_excerpt: str)` variant coordination note (story surfaces it as pre-executor coordination with S4-01 if not present yet; otherwise consumes the existing variant). Rejects the "sentinel `Completed(exit_code=...)`" framing entirely.
- **Design-pattern D-11 (substrate registry guard):** Add to Notes-for-implementer (NOT an AC — anti-pattern guard is contextual).

**Story edits applied (summary):**

1. `Validation notes` block prepended under the story header.
2. **Header**: Status `Ready` → `HARDENED`; Depends-on enumerates S4-01 + S4-02 (`_classify_outcome` kernel) + S1-03; ADRs honored extended to ADR-0010 (sum-type discipline) + ADR-0011 (importlib.resources).
3. **Goal §3 wording**: "exit signals" → "substrate's exit code + stderr signature".
4. **AC-1** (template well-formed): path moved to `src/codegenie/transforms/sandbox/templates/macos-npm.sb`; placeholders changed to `$JAIL` + `$ALLOWLIST_HOSTS`; framework-allow-list aligned with template skeleton (N1); ordering check on `(version 1)` → `(deny default)` first.
5. **AC-2** (Protocol conformance): rewritten as structural `inspect.signature` check + `_StubJail`-style call-site test + companion `test_sandbox_exec_mypy_negative.py` subprocess-mypy test. No `hasattr`.
6. **AC-3** (substitution): rewritten as pure-function test — calls `_render_profile(template_str, spec)` directly, no monkeypatching; asserts ordering (`(version 1)` first non-comment line, `(deny default)` second), placeholder residuals absent, jail substituted, host substituted, ports rendered.
7. **AC-4** (DenyAll → no allow-network): kept; strengthened with a balanced-paren scan + property test (Hypothesis).
8. **AC-5** (argv prefix): rewritten against `run_allowlisted`; full-shape argv assertion (no leftover tokens between `["sandbox-exec","-f",<sb>]` and `spec.cmd`).
9. **AC-6** (no direct subprocess): rewritten as AST-based check covering `subprocess.*`, `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `os.posix_spawn*`, `asyncio.create_subprocess_*`, `multiprocessing.Process`, `getattr(<subprocess>,...)`, `importlib.import_module("subprocess"|"os")`.
10. **AC-7** (result-variant translation): rewritten as direct `run_allowlisted` mock with real-shape `ProcessResult`; pins denial-stderr regex; asserts `.host` field on `NetworkDenied`; parametric over 2+ host fixtures.
11. **AC-8** (env mapping): chokepoint → `run_allowlisted` (which DOES have `env_extra`); test mocks `run_allowlisted` directly.
12. **AC-9** (cmd preserved): kept; chokepoint corrected.
13. **AC-10 / AC-11** (nightly integration): rewritten to `pytest.fail` (not skip) on darwin runner with missing sandbox-exec; only non-darwin path skips.
14. **AC-12** (marker registered): rewritten to use `pytestconfig.getini("markers")` / `tomllib` parse of pyproject.toml; no shell-out.
15. **AC-13 / AC-14** (mypy/ruff/import-linter fence): kept verbatim.
16. **AC-15** (template polarity): kept; strengthened with "no sweeping `(allow file-write*)` without `(subpath ...)` target" check.
17. **New AC-16** (typed-error fence): parametric failure injection — `run_allowlisted` raises `OSError`/`asyncio.TimeoutError`/generic `Exception` → each → typed `JailedSubprocessResult` variant; no bare exception escapes `run()`.
18. **New AC-17** (determinism): `_render_profile(template, spec) == _render_profile(template, spec)` byte-identical across two calls; frozenset host iteration sorted for stability.
19. **New AC-18** (property-based tests): three Hypothesis properties (DenyAll → no allow-network; ∀ host in allowlist → host in render; determinism over shuffled frozensets).
20. **New AC-19** (cleanup-on-exception): per-invocation profile path uses `tempfile.NamedTemporaryFile(dir=spec.cwd, suffix=".sb", delete=False)` + `try/finally` unlink; injected exception → no leaked `.sb`.
21. **New AC-20** (concurrent-run safety): 8 `asyncio.gather`-ed adapter calls against the same `cwd` produce distinct profile paths; no policy cross-contamination.
22. **New AC-21** (substrate-setup failure typed): malformed profile or sandbox-exec exits non-zero before child argv → typed `SubstrateSetupFailed(reason, stderr_excerpt)` variant (NOT `Completed(exit_code=N)`); coordination note with S4-01 if variant not present.
23. **New AC-22** (stateless across calls): AST grep asserts no module-level mutable globals in `sandbox_exec.py`; only `Final[...]` constants + `@functools.cache`-wrapped template loader.
24. **New AC-23** (consume `_classify_outcome` kernel): `SandboxExecAdapter` imports `_classify_outcome` from `src/codegenie/transforms/sandbox/_classify.py` (S4-02); substrate-specific `_parse_sandbox_denial(stderr: bytes) -> Hostname | None` is the only translator in `sandbox_exec.py`; meta-test asserts `id(_classify._classify_outcome)` is identical across both adapter import sites.
25. **New AC-24** (`match` exhaustiveness): `_render_allowlist_clauses(network: NetworkPolicy) -> str` uses `match` + `assert_never`; mypy `--strict` proves exhaustiveness.
26. **New AC-25** (`Hostname` smart-constructor): `_extract_hostname(url: RegistryUrl) -> Hostname` validates `^[a-z0-9.-]+(:\d+)?$` and round-trips through `urllib.parse.urlparse`; `_render_allow_network_clause(host: Hostname, port: int) -> str` consumes `Hostname`, not `str`; mypy refuses `_render_allow_network_clause(some_str)`.
27. **New AC-26** (template loading via importlib.resources): template lives at `src/codegenie/transforms/sandbox/templates/macos-npm.sb` and loads via `importlib.resources.files("codegenie.transforms.sandbox.templates").joinpath("macos-npm.sb").read_text()`; wheel-install survival test (remove repo root from `sys.path`, assert load succeeds).
28. **New AC-27** (macOS 14+ gate): adapter construction (or first `run`) checks `platform.mac_ver()[0] >= "14.0"`; else raises typed `SubstrateUnsupportedError(version, "Phase 5 Lima/DinD substitutes here")`.
29. **New AC-28** (placeholder residual check): post-substitute `_render_profile` asserts `re.search(r"\$[A-Z_]+", rendered)` returns None; raises `ProfilePlaceholderUnresolved(token)` on regression.
30. **New AC-29** (hexagonal-shape parity): both adapter modules expose the same helper-verb intersection (`build_argv`, `render`, `translate`); meta-test asserts the symmetry via a stable `_EXPECTED_HELPER_VERBS: Final[frozenset[str]]` declared per adapter.
31. **Implementation outline** rewritten: chokepoint → `run_allowlisted`; `str(spec.cwd.absolute)` → `str(spec.cwd)`; template-load via `importlib.resources`; `_render_profile` decomposed into `_render_allowlist_clauses` (pure, `match`-dispatched) + `_extract_hostname` (smart-constructor) + `_render_allow_network_clause` (typed); per-invocation profile path via `tempfile.NamedTemporaryFile`; classifier-consumption via S4-02 `_classify_outcome` import; macOS-version gate at constructor.
32. **TDD plan** rewritten: import paths corrected (`tests.unit.transforms.sandbox._fakes`, `codegenie.transforms.SandboxedPath`); `run_external_cli` mocks → `run_allowlisted` mocks; AC-3 test invokes `_render_profile` directly; result-variant test uses real-shape `ProcessResult` not `_fakes_for_tests`; Hypothesis properties added; AC-12 uses `pytestconfig`.
33. **Files to touch** updated: template moves to `src/codegenie/transforms/sandbox/templates/macos-npm.sb`; `src/codegenie/transforms/sandbox/_classify.py` is *consumed*, not authored; no `_fakes_for_tests.py` under `src/`; `tests/unit/transforms/sandbox/_fakes.py` is the test scaffolding location (authored by S4-02 hardening).
34. **Out-of-scope** kept; appended doc-debt note for ADR-0012 §Decision rewording (shared with S4-02 attempt log).
35. **Notes-for-implementer** updated: drop "sentinel `Completed(exit_code=...)`" framing (anti-pattern per Rule 12); add anti-registry guard for substrates (D-11); add `string.Template` placeholder discipline; pin denial-stderr regex with example; add macOS-14+ gate guidance.

## Files written

- `docs/phases/03-vuln-deterministic-recipe/stories/S4-03-sandbox-exec-adapter-macos.md` — edited in place (HARDENED).
- `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S4-03-sandbox-exec-adapter-macos.md` — this report.

## Pre-executor coordination (must read)

Before executing this story, the implementer (or their pre-flight) MUST:

1. Confirm S4-02 has landed (with HARDENED edits) — `src/codegenie/transforms/sandbox/_classify.py` and the `Syscall` `StrEnum` must exist; this story consumes them.
2. Confirm S4-05 has landed (or land it as a precondition) — `sandbox-exec` admitted to `ALLOWED_BINARIES`; closed-set deny-list adjusted.
3. Confirm S4-04 has landed — `SandboxedPath` real type via `from codegenie.transforms import SandboxedPath` (the forward-shim still works pre-S4-04, returning `pathlib.Path`).
4. Confirm S4-01 carries `SubstrateSetupFailed(reason, stderr_excerpt)` as a `JailedSubprocessResult` variant. If not, surface as pre-executor coordination (AC-21 depends on it).
5. Surface in `_attempts/S4-03.md` Attempt 1: ADR-0012 §Decision wording drift acknowledgment (shared with S4-02 attempt log) + "Two doc-debt items: (a) ADR-0012 §Decision says 'route through `run_external_cli`'; both adapters route through `run_allowlisted`. (b) Goal §3 'exit signals' is Linux-flavored — macOS denial path is stderr-parsed."
