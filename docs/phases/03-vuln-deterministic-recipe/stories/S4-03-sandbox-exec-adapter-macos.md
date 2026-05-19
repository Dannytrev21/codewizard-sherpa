# Story S4-03 — `SandboxExecAdapter` (macOS) + `templates/macos-npm.sb` profile

**Step:** Step 4 — SubprocessJail Port + Bwrap + sandbox-exec + ALLOWED_BINARIES amendment
**Status:** HARDENED
**Effort:** M
**Depends on:** S4-01 (`SubprocessJail` Protocol, `JailedSubprocessSpec`, `JailedSubprocessResult` variants including `SubstrateSetupFailed` per validation coordination, `NetworkPolicy`); S4-02 (`src/codegenie/transforms/sandbox/_classify.py::_classify_outcome` kernel + `Syscall` `StrEnum`); S4-04 (`SandboxedPath` real type, consumed via `from codegenie.transforms import SandboxedPath`); transitively S1-03
**Coordinates with:** S4-05 (admits `sandbox-exec` to `ALLOWED_BINARIES` + closed-set deny-list adjustment)
**ADRs honored:** 03-ADR-0006 (`SandboxExecAdapter` is the macOS Adapter; §Decision pins `sandbox-exec -f <generated.sb>` with `deny default` + explicit allows; §Consequences pins the nightly-only CI cadence and deprecation-flagged-but-accepted-for-Phase-3 framing); 03-ADR-0010 (sum-type `match` discipline); 03-ADR-0011 (`importlib.resources` for packaged static assets); 03-ADR-0012 (`sandbox-exec` added to `ALLOWED_BINARIES` — S4-05's data change)

## Validation notes (2026-05-18)

Validator pass converted this story from `Ready` to `HARDENED`. The macOS Adapter is the **2nd concrete consumer** of the `SubprocessJail` Port; the **rule-of-three threshold for substrate-agnostic logic is REACHED** (Phase 5 Firecracker/DinD is the 3rd, in-roadmap). Key changes:

- **Chokepoint:** `run_external_cli` → `run_allowlisted`. The former has no `env_extra` parameter and lives behind the closed-set regression; the latter is the correct port-of-call. (ADR-0012 §Decision wording drift coordinated with S4-02's pending doc-debt follow-up.)
- **Protocol conformance:** `hasattr(adapter, "run")` is mutation-trivial — replaced with `inspect.signature` + `_StubJail` call-site test + companion subprocess-mypy negative test (S4-01 forbids `@runtime_checkable`).
- **`_classify_outcome` kernel:** `SandboxExecAdapter` **consumes** S4-02's extracted classifier; only the macOS-specific stderr-denial parser is local. Meta-test pins kernel-identity across adapter import sites.
- **Template location:** moved from `tooling/sandbox/macos-npm.sb` → `src/codegenie/transforms/sandbox/templates/macos-npm.sb`; loaded via `importlib.resources` (survives wheel install).
- **Placeholder mechanism:** `{{JAIL}}` / `{{ALLOWLIST_HOSTS}}` → `$JAIL` / `$ALLOWLIST_HOSTS` + `string.Template.safe_substitute` + post-substitute residual regex (fails loud on typo).
- **Sum-type dispatch:** `_render_allowlist_clauses` uses `match spec.network` with `assert_never` exhaustiveness; mypy proves total dispatch.
- **`str(spec.cwd.absolute)` bug:** `.absolute` is a method (not property) — corrected to `str(spec.cwd)`.
- **Substrate-setup failure:** typed `SubstrateSetupFailed(reason, stderr_excerpt)` variant (NOT the original "sentinel `Completed(exit_code=...)`" framing — Rule 12 violation).
- **macOS 14+ gate:** typed `SubstrateUnsupportedError` raised at construction time on older macOS.
- **Nightly-runner fail-not-skip:** missing `sandbox-exec` on a darwin runner → `pytest.fail`, not skip (silent-skip is exactly the Rule 12 anti-pattern).
- **AC-12 marker check:** `subprocess.run(["pytest","--markers"])` → `pytestconfig.getini("markers")` / `tomllib`.
- **`Hostname` smart-constructor:** `_extract_hostname(url: RegistryUrl) -> Hostname` preserves the newtype discipline; `_render_allow_network_clause(host: Hostname, port: int) -> str` consumes it.
- New ACs for typed-error fence (AC-16), determinism (AC-17), property tests (AC-18), cleanup-on-exception (AC-19), concurrent-run safety (AC-20), substrate-setup failure (AC-21), statelessness (AC-22), kernel consumption (AC-23), `match` exhaustiveness (AC-24), `Hostname` smart-constructor (AC-25), packaged-template load (AC-26), macOS-version gate (AC-27), placeholder residual check (AC-28), hexagonal-shape parity (AC-29).

Full per-finding decisions in `_validation/S4-03-sandbox-exec-adapter-macos.md`.

## Context

The macOS sibling of S4-02. The architecture spec (`phase-arch-design.md §Component design C8` — SandboxExecAdapter bullet) commits to `sandbox-exec -f <generated.sb>` with a `deny default` Scheme-syntax profile carrying explicit allow-rules for (a) the jail directory itself and (b) every host in the `NetworkPolicy.RegistryAllowlist`. The same `SubprocessJail` Port S4-02 implements on Linux is implemented here on macOS — operator-laptop developers (most of whom are on Mac) get a working substrate without waiting for Phase 5's Lima / DinD.

**Three macOS-specific framings the implementer must internalize:**

1. **`sandbox-exec` is deprecation-flagged by Apple.** ADR-0006 §Tradeoffs row 3 names this explicitly: "macOS `sandbox-exec` is deprecation-flagged by Apple; Phase 5 substitutes Lima/DinD on macOS. Phase 3 carries the tech-debt explicitly (sized as ~150 LOC of `.sb` profile generation)." The architecture *accepts* this — there is no workaround within Phase 3's scope. The Adapter ships, works on `macOS 14+` (AC-27 gates older versions with a typed `SubstrateUnsupportedError`), and the deprecation is documented at the symbol.

2. **Nightly-only integration cadence.** ADR-0006 §Consequences row 4: "macOS CI runs as a nightly smoke job (not per-PR) — sandbox-exec adapter is exercised once per day; Linux bwrap path is the per-PR substrate." Phase 3 unit tests run on every PR (mocked substrate); the live `sandbox-exec` invocation runs only on the nightly macOS runner.

3. **Online-mode-default rejection of security's offline-prefetch flow.** Per ADR-0006 §Context and `critique.md §Issue 2`, the original security-lens design proposed an "online prefetch then offline npm" flow that creates a second, unjailed trust boundary. Both Adapters reject it; this story's `.sb` profile carries network-allow rules for the registry allowlist, not network-deny + offline-cache assumptions.

The `.sb` profile content is implementation-defined per ADR-0006 §Consequences. This story picks and writes that profile, packages it under `src/codegenie/transforms/sandbox/templates/` for wheel-install survival, documents its load-bearing clauses, and ships a pure renderer that produces per-`JailedSubprocessSpec` instantiations.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C8` — `SandboxExecAdapter` bullet.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — substrate-cost row.
  - `../phase-arch-design.md §Physical view` — macOS substrate placement; nightly cadence.
  - `../phase-arch-design.md §Edge case E7` — `.npmrc` redirect → `NetworkDenied(host)`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md` — §Decision pins the Adapter shape; §Tradeoffs row 3 documents macOS deprecation acceptance; §Consequences pin nightly cadence + profile-content scope.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `match` exhaustiveness; newtype discipline.
  - `../ADRs/0011-honest-framing-capability-sandboxedpath-pluginslock.md` — `importlib.resources` precedent.
  - `../ADRs/0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md` — `sandbox-exec` admitted to `ALLOWED_BINARIES` (S4-05).
- **Source design:**
  - `../final-design.md §Open questions deferred to implementation` — bullet 3.
  - `../High-level-impl.md §Step 4 features delivered` — pins `src/codegenie/transforms/sandbox/sandbox_exec.py`.
- **Sibling validation:**
  - `_validation/S4-02-bwrap-adapter-linux.md` — established kernel-extraction (`_classify_outcome`), structural-Protocol pattern, hardened AC parity targets.
- **Existing code:**
  - `src/codegenie/exec/__init__.py::run_allowlisted` — chokepoint the Adapter calls.
  - `src/codegenie/transforms/sandbox/_classify.py` (S4-02) — the substrate-agnostic outcome classifier; CONSUMED here.
  - `src/codegenie/transforms/sandbox/bwrap.py` (S4-02) — the sibling Adapter; mirror helper-verb names.
  - `src/codegenie/transforms/_forward.py` — `SandboxedPath` re-export shim; `from codegenie.transforms import SandboxedPath` is the canonical import.
  - Phase 2 nightly-marker precedent: search `pyproject.toml [tool.pytest.ini_options] markers`.

## Goal

Land:

1. `src/codegenie/transforms/sandbox/templates/macos-npm.sb` — the static template `.sb` profile with `deny default`, allow-rules for the jail directory (placeholder `$JAIL` substituted at instantiation), file-read of system frameworks needed for `npm`/`node` to run, and an `$ALLOWLIST_HOSTS` substitution token whose body is rendered from the `NetworkPolicy` sum-type per spec. **Packaged under `src/`** for wheel-install survival.
2. `src/codegenie/transforms/sandbox/sandbox_exec.py` — `SandboxExecAdapter(SubprocessJail)` that:
   - Loads the `.sb` template via `importlib.resources` (cached via `@functools.cache`).
   - Renders per-spec values through a pure `_render_profile(template: str, spec) -> str`.
   - Writes the rendered profile to a per-invocation temp file (`tempfile.NamedTemporaryFile(dir=spec.cwd, suffix=".sb", delete=False)`) cleaned up in `try/finally`.
   - Invokes `sandbox-exec -f <generated.sb> <inner-argv>` through `run_allowlisted`.
   - Translates the substrate's exit code + stderr signature into `JailedSubprocessResult` variants by **consuming** `_classify_outcome` from `src/codegenie/transforms/sandbox/_classify.py` (S4-02 kernel); substrate-specific `_parse_sandbox_denial(stderr) -> Hostname | None` is the only translator local to this module.
   - Raises typed `SubstrateUnsupportedError` on `macOS < 14`.
3. `tests/integration/transforms/test_sandbox_exec_hello_world.py` — macOS-only, **nightly-only** (gated via `@pytest.mark.nightly_macos` and `sys.platform == "darwin"`).
4. `tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` — cross-platform mocked unit tests (renderer purity, kernel consumption, AST-based forbidden-subprocess fence, property tests, etc.).

`mypy --strict` clean. Online-mode default. `--ignore-scripts` enforced (the env half rides on `NpmEnv.to_env_mapping()` per S4-01; the CLI half is consumer responsibility per S4-05).

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/transforms/sandbox/templates/macos-npm.sb` exists with a `(version 1)` header, `(deny default)`, explicit allow-rules for: (a) `(allow file-read*)` on `/usr/lib`, `/usr/bin`, `/usr/local/bin`, `/Library/Developer/CommandLineTools`, `/System/Library/Frameworks`; (b) `(allow file-read* file-write*)` on the substituted jail directory token (`$JAIL`); (c) `(allow process-exec)` for `npm` and `node` paths; (d) `$ALLOWLIST_HOSTS` substitution body (rendered by the generator). A unit test (`test_macos_sb_profile_template_well_formed`) loads the template via `importlib.resources.files("codegenie.transforms.sandbox.templates").joinpath("macos-npm.sb").read_text()` and asserts `(version 1)` is the first non-comment line, `(deny default)` is the second non-comment line, `$JAIL` and `$ALLOWLIST_HOSTS` placeholder tokens are both present.
- [ ] **AC-2.** `src/codegenie/transforms/sandbox/sandbox_exec.py` exists and exports `SandboxExecAdapter`. Conformance to `SubprocessJail` is asserted **structurally** (S4-01 forbids `@runtime_checkable`): (i) `inspect.signature(SandboxExecAdapter.run)` matches `(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult` (parameter names + return annotation pinned); (ii) a `_StubJail`-style call-site test binds `adapter: SubprocessJail = SandboxExecAdapter()` and invokes `await adapter.run(spec)` end-to-end against a mock chokepoint — a mutant `class SandboxExecAdapter: run = None` raises `TypeError` at dispatch; (iii) a companion `tests/unit/transforms/sandbox/test_sandbox_exec_mypy_negative.py` runs `mypy --strict` over a fixture file that mis-typechecks the adapter and asserts a specific error code is reported (mirrors `test_outcomes_mypy_negative.py` precedent).
- [ ] **AC-3.** `_render_profile(template: str, spec: JailedSubprocessSpec) -> str` is pure (no I/O). A unit test (`test_generated_sb_substitution`) calls `_render_profile(template_str, spec)` directly with `cwd=<tmp_path>` and `network=RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` and asserts:
  - No `$JAIL` or `$ALLOWLIST_HOSTS` (or any `re.search(r"\$[A-Z_]+", rendered)`) residuals remain.
  - The string `str(tmp_path)` appears in the output (jail substituted).
  - `registry.npmjs.org` appears in an `(allow network*` clause as `(remote tcp "registry.npmjs.org:443")`.
  - Non-comment lines: `lines[0] == "(version 1)"`, `lines[1] == "(deny default)"` (ordering pinned).
  - Balanced parentheses (`rendered.count("(") == rendered.count(")")`) — catches missing-paren mutants.
- [ ] **AC-4.** Generated `.sb` for `NetworkPolicy.DenyAll` contains no `(allow network*` clause referencing any external host. A unit test passes `network=DenyAll()` and asserts `re.findall(r"\(allow network[^)]*remote tcp[^)]+\)", rendered) == []`.
- [ ] **AC-5.** `SandboxExecAdapter.run` invokes `run_allowlisted` with full-shape argv `("sandbox-exec", "-f", <generated-sb-path>, *spec.cmd)` — a unit test asserts `argv[:3] == ("sandbox-exec", "-f", <path>)`, `tuple(argv[3:]) == spec.cmd` (no leftover tokens between prefix and `spec.cmd`).
- [ ] **AC-6.** `SandboxExecAdapter` NEVER calls forbidden subprocess primitives. An **AST-based** check (not substring grep) walks `sandbox_exec.py`'s AST and rejects any `ast.Call` whose callee resolves (via name + alias map built from `ast.Import` / `ast.ImportFrom`) to anything in `{subprocess.*, os.system, os.popen, os.exec*, os.spawn*, os.posix_spawn*, asyncio.create_subprocess_*, multiprocessing.Process}`; also rejects `getattr(<name resolving to subprocess>, ...)` and `importlib.import_module("subprocess"|"os")` literals. Reuses or imports the AST helper from S4-02's AC-4.
- [ ] **AC-7.** Result-variant translation parametric. A unit test mocks `run_allowlisted` with **real-shape** `ProcessResult` (no `_fakes_for_tests` sentinel-string indirection) and asserts each `JailedSubprocessResult` variant is reachable: `Completed(exit_code=0)` on clean exit; `TimedOut` when `elapsed_s >= spec.time_budget_s` + returncode=-9; `NetworkDenied(host="github.com")` when stderr matches `Sandbox: .* deny.* network-outbound github\.com:\d+` — `.host` field asserted equal to `"github.com"` (and parametric over `pypi.org` to prove the parser is not hard-coded).
- [ ] **AC-8.** `NpmEnv.to_env_mapping()` is passed to `run_allowlisted`'s `env_extra` — the `npm_config_ignore_scripts="true"` defense rides through verbatim. A unit test mocks `run_allowlisted`, captures the `env_extra` kwarg, and asserts the key. Mirror of S4-02 AC-8 (hardened).
- [ ] **AC-9.** `spec.cmd` is preserved verbatim including any `--ignore-scripts` CLI token (`tuple(argv[-len(cmd):]) == cmd`).
- [ ] **AC-10.** **Nightly-only macOS hello-world integration test.** `tests/integration/transforms/test_sandbox_exec_hello_world.py` is marked `@pytest.mark.nightly_macos`. Test body:
  - Skip ONLY if `sys.platform != "darwin"` (non-darwin runners aren't macOS — legitimate skip).
  - On darwin: if `shutil.which("sandbox-exec") is None` → `pytest.fail("nightly macOS runner is broken: sandbox-exec missing — built-in to macOS")` (NOT skip — silent-skip violates Rule 12).
  - Run `SandboxExecAdapter().run(spec)` with `spec.cmd = ("/bin/echo", "hello")`, `network=DenyAll()`, and assert `isinstance(result, Completed) and result.exit_code == 0`.
- [ ] **AC-11.** **Nightly-only network-policy live test.** `tests/integration/transforms/test_sandbox_exec_network_policy.py` (same nightly-macOS gating; fail-not-skip on darwin runner with missing `sandbox-exec`) runs two cases:
  - `RegistryAllowlist(hosts=frozenset({RegistryUrl("https://registry.npmjs.org")}))` + `cmd=("/usr/bin/curl", "--max-time", "5", "-o", "/dev/null", "-s", "https://registry.npmjs.org/")` → `Completed`.
  - Same allowlist + `cmd=("/usr/bin/curl", "--max-time", "5", "https://github.com/")` → `NetworkDenied(host="github.com")`.
- [ ] **AC-12.** `pyproject.toml [tool.pytest.ini_options] markers` declares `nightly_macos` (or reuses an existing marker — verify Phase 2 precedent first). A pytest meta-test uses `pytestconfig.getini("markers")` (NO `subprocess.run` shell-out) and asserts `"nightly_macos"` is among the registered marker names; equivalently parses `pyproject.toml` via `tomllib`.
- [ ] **AC-13.** `mypy --strict src/codegenie/transforms/sandbox/sandbox_exec.py tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` clean. `ruff check` + `ruff format --check` clean on touched files.
- [ ] **AC-14.** `make lint-imports` Phase 3 contract (S1-05): no LLM SDK appears in `src/codegenie/transforms/sandbox/sandbox_exec.py`'s import closure.
- [ ] **AC-15.** Profile-template safety regression: a unit test (`test_sb_template_does_not_allow_default_writes`) asserts:
  - Literal substring `(allow default)` does NOT appear in the template.
  - `(deny default)` appears exactly once.
  - No `(allow file-write*` clause exists without an immediately-following `(subpath ...)` target on the same s-expression (regex over balanced parens — catches a mutant template with sweeping unrestricted writes).
  - No `(allow network*` clause exists without a `(remote ...)` restriction.
- [ ] **AC-16.** **Typed-error fence.** A parametric failure-injection unit test makes the mocked `run_allowlisted` raise `OSError`, `asyncio.TimeoutError`, and a generic `Exception` in turn; for each, `SandboxExecAdapter.run` returns a typed `JailedSubprocessResult` variant — no bare exception escapes the Port boundary. Mirrors S4-02 AC-16.
- [ ] **AC-17.** **Determinism.** Calling `_render_profile(template, spec)` twice with the same inputs produces byte-identical output. The renderer sorts `RegistryAllowlist.hosts` (a `frozenset`) before emitting clauses, so frozenset iteration order does not perturb output bytes. A unit test asserts byte-equality across two consecutive calls and across `frozenset({a, b})` vs `frozenset({b, a})` constructions.
- [ ] **AC-18.** **Property-based tests** (Hypothesis). Three properties over `network ∈ {DenyAll(), RegistryAllowlist(hosts=H)}` where `H` is a `st.sets(st.sampled_from(["registry.npmjs.org", "pypi.org", "files.pythonhosted.org", "github.com"]), min_size=0, max_size=4)`:
  - `DenyAll → re.findall(r"\(allow network[^)]*remote tcp[^)]+\)", rendered) == []`
  - `∀ host ∈ H → f'"{host}:443"' in rendered`
  - `_render_profile(t, spec) == _render_profile(t, spec)` byte-identical.
- [ ] **AC-19.** **Cleanup-on-exception.** The per-invocation profile path uses `tempfile.NamedTemporaryFile(dir=spec.cwd, suffix=".sb", delete=False)`, wrapped in `try/finally` that `Path.unlink(missing_ok=True)`s it. A unit test injects an exception in mocked `run_allowlisted`; the adapter still returns a typed variant (AC-16) AND no `.sb` file remains under `spec.cwd` after `run()` returns.
- [ ] **AC-20.** **Concurrent-run safety.** Eight `asyncio.gather`-ed `SandboxExecAdapter().run()` calls against the same `cwd` produce eight distinct profile paths and eight independent `.sb` files (each captured argv recorded by the mock; all profile paths distinct; no policy cross-contamination because the writes don't share a fixed filename).
- [ ] **AC-21.** **Substrate-setup failure is typed.** When mocked `run_allowlisted` returns a non-zero exit BEFORE child argv invocation AND stderr matches `Sandbox: .*error:` (substrate parse error), the adapter returns `SubstrateSetupFailed(reason: str, stderr_excerpt: str)` — NOT `Completed(exit_code=N)`. Coordination: if `SubstrateSetupFailed` is not yet in `JailedSubprocessResult` (S4-01), surface as pre-executor blocker.
- [ ] **AC-22.** **Stateless across calls.** An AST meta-test walks `src/codegenie/transforms/sandbox/sandbox_exec.py` and asserts no module-level mutable globals (`list`, `dict`, `set` literals) at module scope; only `Final[...]` typed constants and `@functools.cache`-wrapped template loader. Mirrors S4-02 AC-22.
- [ ] **AC-23.** **Consume `_classify_outcome` kernel.** `SandboxExecAdapter` imports `_classify_outcome` from `codegenie.transforms.sandbox._classify` (extracted by S4-02). The macOS-specific `_parse_sandbox_denial(stderr: bytes) -> Hostname | None` helper is local to `sandbox_exec.py` and is passed into the classifier as the substrate-specific denial parser. A meta-test imports both `BwrapAdapter` and `SandboxExecAdapter`, accesses their classifier reference, and asserts `id(...)` is identical (proves no shadow copy).
- [ ] **AC-24.** **`match` exhaustiveness on `NetworkPolicy`.** `_render_allowlist_clauses(network: NetworkPolicy) -> str` uses `match network: case DenyAll(): ...; case RegistryAllowlist(hosts): ...; case _: assert_never(network)`. `mypy --strict` proves the match is exhaustive over the sum; a unit test passing a `cast(NetworkPolicy, object())` asserts `assert_never` fires at runtime.
- [ ] **AC-25.** **`Hostname` smart-constructor.** `_extract_hostname(url: RegistryUrl) -> Hostname` is a pure helper (use `Hostname = NewType("Hostname", str)`) that round-trips through `urllib.parse.urlparse` and validates `^[a-z0-9.-]+$` (raises `ValueError` on failure). `_render_allow_network_clause(host: Hostname, port: int) -> str` consumes the newtype; a `mypy` negative fixture proves passing a raw `str` is rejected.
- [ ] **AC-26.** **Packaged-template load.** Template is at `src/codegenie/transforms/sandbox/templates/macos-npm.sb`; loaded via `importlib.resources.files("codegenie.transforms.sandbox.templates").joinpath("macos-npm.sb").read_text()`. A wheel-install survival unit test: removes the repo root from `sys.path` (or uses `tox -e wheel-smoke` precedent), reimports the package, asserts the load still succeeds.
- [ ] **AC-27.** **macOS 14+ gate.** `SandboxExecAdapter.__init__` checks `platform.mac_ver()[0]` and raises typed `SubstrateUnsupportedError(version: str, "Phase 5 Lima/DinD substitutes here")` if version < `"14.0"` (or `platform.mac_ver()` reports empty on non-darwin — only checked when `sys.platform == "darwin"`). A unit test monkey-patches `platform.mac_ver` to `("13.6.0", ...)` and asserts the typed raise; second case `("14.0.0", ...)` constructs successfully.
- [ ] **AC-28.** **Placeholder residual check.** `_render_profile` asserts (before return) `re.search(r"\$[A-Z_]+", rendered) is None`; raises `ProfilePlaceholderUnresolved(token: str)` on regression. A unit test deletes the `$ALLOWLIST_HOSTS` line from the template fixture and asserts the typed raise — proves a typo in placeholder mechanism fails loud, per Rule 12.
- [ ] **AC-29.** **Hexagonal-shape parity.** Each adapter module exposes a module-level `_HELPER_VERBS: Final[frozenset[str]]` declaring its public helper verbs (e.g., `{"build_argv", "render", "translate"}`). A meta-test imports `bwrap` and `sandbox_exec` modules and asserts `_HELPER_VERBS` is the same `frozenset` on both — making the Hexagonal-Port symmetry observable at the file boundary.

## Implementation outline

1. Move (or write fresh) the `.sb` template to `src/codegenie/transforms/sandbox/templates/macos-npm.sb` (~80–150 lines). Skeleton:
   ```
   (version 1)
   (deny default)

   ;; Read system frameworks node/npm need to start
   (allow file-read*
     (subpath "/usr/lib")
     (subpath "/usr/bin")
     (subpath "/usr/local/bin")
     (subpath "/Library/Developer/CommandLineTools")
     (subpath "/System/Library/Frameworks"))

   ;; Read + write inside the jail
   (allow file-read* file-write*
     (subpath "$JAIL"))

   ;; /tmp is per-user on macOS
   (allow file-read* file-write*
     (subpath "/private/tmp"))

   ;; Process invocation (npm shells out to node)
   (allow process-exec
     (subpath "/usr/local/bin")
     (subpath "/usr/bin"))

   ;; Network policy — body substituted per spec (empty for DenyAll)
   $ALLOWLIST_HOSTS

   ;; Required syscall surface — minimal
   (allow mach-lookup)
   (allow sysctl-read)
   (allow process-fork)
   (allow signal (target self))
   ```
   Note placeholders use `$JAIL` / `$ALLOWLIST_HOSTS` (consumed by `string.Template.safe_substitute`), NOT `{{JAIL}}` / `{{ALLOWLIST_HOSTS}}`. Also include a `src/codegenie/transforms/sandbox/templates/__init__.py` to make it an importable package for `importlib.resources`.
2. Create `src/codegenie/transforms/sandbox/sandbox_exec.py`. Imports:
   ```python
   from __future__ import annotations
   import functools
   import platform
   import string
   import sys
   import tempfile
   import typing
   from importlib import resources
   from pathlib import Path
   from typing import Final

   from codegenie.exec import run_allowlisted
   from codegenie.transforms.sandbox._classify import _classify_outcome
   from codegenie.transforms.sandbox_jail import (
       JailedSubprocessSpec, JailedSubprocessResult,
       NetworkPolicy, DenyAll, RegistryAllowlist,
       SubstrateSetupFailed, SubstrateUnsupportedError,
   )
   from codegenie.types.identifiers import RegistryUrl
   ```
3. Declare `Hostname = typing.NewType("Hostname", str)` at module scope. Declare `_HELPER_VERBS: Final[frozenset[str]] = frozenset({"build_argv", "render", "translate"})`.
4. `@functools.cache` template loader:
   ```python
   @functools.cache
   def _load_template() -> string.Template:
       text = resources.files("codegenie.transforms.sandbox.templates").joinpath("macos-npm.sb").read_text()
       return string.Template(text)
   ```
5. Pure `_render_profile(template: string.Template, spec: JailedSubprocessSpec) -> str`:
   - `clauses = _render_allowlist_clauses(spec.network)` — uses `match` + `assert_never`.
   - `rendered = template.safe_substitute(JAIL=str(spec.cwd), ALLOWLIST_HOSTS=clauses)` — note `str(spec.cwd)`, NOT `str(spec.cwd.absolute)` (the latter is a bound-method repr bug).
   - `if re.search(r"\$[A-Z_]+", rendered):` → raise `ProfilePlaceholderUnresolved(...)` (AC-28).
   - Return rendered.
6. `_render_allowlist_clauses(network: NetworkPolicy) -> str`:
   ```python
   match network:
       case DenyAll():
           return ""
       case RegistryAllowlist(hosts=hosts):
           # Sort for determinism (AC-17) — hosts is a frozenset
           clauses = []
           for url in sorted(hosts):
               host = _extract_hostname(url)
               port = _extract_port(url)  # default 443
               clauses.append(_render_allow_network_clause(host, port))
           return "\n".join(clauses)
       case _:
           typing.assert_never(network)
   ```
7. `_extract_hostname(url: RegistryUrl) -> Hostname` (AC-25): pure smart-constructor — `urllib.parse.urlparse`, validate regex, return `Hostname(parsed.hostname)` or raise `ValueError`. `_render_allow_network_clause(host: Hostname, port: int) -> str` returns the `(allow network* (remote tcp "host:port"))` literal.
8. `class SandboxExecAdapter:` with:
   ```python
   def __init__(self) -> None:
       if sys.platform == "darwin":
           ver_str = platform.mac_ver()[0]
           if ver_str and tuple(int(x) for x in ver_str.split(".")[:2]) < (14, 0):
               raise SubstrateUnsupportedError(ver_str, "Phase 5 Lima/DinD substitutes here")

   async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult: ...
   ```
9. In `run`:
   - Render the profile (pure).
   - Open a `tempfile.NamedTemporaryFile(dir=str(spec.cwd), suffix=".sb", delete=False)`; write rendered text; capture path. Wrap subsequent work in `try`/`finally` that unlinks the temp file.
   - Compose argv: `("sandbox-exec", "-f", str(profile_path), *spec.cmd)`.
   - `env_extra = spec.env.to_env_mapping()`.
   - `try:` `outcome = await run_allowlisted(argv, cwd=str(spec.cwd), timeout_s=spec.time_budget_s, env_extra=env_extra)`.
   - Translate via `_classify_outcome(outcome, spec, denial_parser=_parse_sandbox_denial)`.
   - `except OSError as e:` / `asyncio.TimeoutError` / `Exception`: convert each to a typed variant per AC-16 (do not propagate bare exceptions).
   - `finally:` `Path(profile_path).unlink(missing_ok=True)`.
10. `_parse_sandbox_denial(stderr: bytes) -> Hostname | None` (local helper): regex `re.search(rb"Sandbox: .*deny.*network-outbound\s+([a-z0-9.-]+):\d+", stderr, re.MULTILINE)` → return `Hostname(m.group(1).decode())` or `None`.
11. Register `nightly_macos` pytest marker in `pyproject.toml` if not present (Phase 2 may already have it — verify).
12. Write unit tests (AC-1..AC-9, AC-12..AC-29). Write nightly integration tests (AC-10..AC-11).
13. Run `mypy --strict`, `ruff`, full unit suite.

## TDD plan — red / green / refactor

### Red — write the failing tests first

`tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` (cross-platform):

```python
from __future__ import annotations

import ast
import re
import tomllib
from importlib import resources
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import given, strategies as st

from codegenie.transforms.sandbox.sandbox_exec import (  # RED
    Hostname, ProfilePlaceholderUnresolved, SandboxExecAdapter,
    _extract_hostname, _load_template, _render_allowlist_clauses,
    _render_profile, _HELPER_VERBS,
)
from codegenie.transforms.sandbox._classify import _classify_outcome
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessSpec, NetworkDenied, NpmEnv,
    RegistryAllowlist, SubprocessJail, SubstrateSetupFailed,
    SubstrateUnsupportedError, TimedOut,
)
from codegenie.types.identifiers import RegistryUrl
from tests.unit.transforms.sandbox._fakes import FakeSandboxedPath


# AC-1: template well-formed
def test_macos_sb_profile_template_well_formed() -> None:
    text = resources.files("codegenie.transforms.sandbox.templates").joinpath(
        "macos-npm.sb"
    ).read_text()
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(";;")]
    assert lines[0].strip() == "(version 1)"
    assert lines[1].strip() == "(deny default)"
    assert "$JAIL" in text
    assert "$ALLOWLIST_HOSTS" in text


# AC-15: polarity + sweeping-write guard
def test_sb_template_polarity_and_no_sweeping_writes() -> None:
    text = resources.files("codegenie.transforms.sandbox.templates").joinpath(
        "macos-npm.sb"
    ).read_text()
    assert "(allow default)" not in text
    assert text.count("(deny default)") == 1
    # No (allow file-write*) without a (subpath ...) target in the same form
    for m in re.finditer(r"\(allow [^()]*file-write\*[^()]*\)", text):
        # Each allow-file-write* must contain a target sub-clause; absent target → bug
        assert "(subpath" in m.group(0), f"sweeping allow file-write*: {m.group(0)!r}"


# AC-2: structural Protocol conformance
def test_sandbox_exec_adapter_signature() -> None:
    import inspect
    sig = inspect.signature(SandboxExecAdapter.run)
    params = list(sig.parameters)
    assert params == ["self", "spec"]
    # Return annotation pinned (may be string-forward or class)
    assert "JailedSubprocessResult" in str(sig.return_annotation)


async def test_sandbox_exec_adapter_call_site_typechecks(tmp_path) -> None:
    adapter: SubprocessJail = SandboxExecAdapter()  # binds to Protocol-typed var
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    async def fake(*a, **k):
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b"", "elapsed_s": 0.0})()
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        result = await adapter.run(spec)
    assert isinstance(result, Completed)


# AC-3: pure renderer
def test_generated_sb_substitution(tmp_path: Path) -> None:
    template = _load_template()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({
            RegistryUrl("https://registry.npmjs.org"),
        })),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    rendered = _render_profile(template, spec)
    assert re.search(r"\$[A-Z_]+", rendered) is None
    assert str(tmp_path) in rendered
    assert '"registry.npmjs.org:443"' in rendered
    lines = [ln.strip() for ln in rendered.splitlines() if ln.strip() and not ln.strip().startswith(";;")]
    assert lines[0] == "(version 1)"
    assert lines[1] == "(deny default)"
    assert rendered.count("(") == rendered.count(")")


# AC-4: DenyAll has no allow-network
def test_generated_sb_deny_all_has_no_allow_network(tmp_path: Path) -> None:
    template = _load_template()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(),
        network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    rendered = _render_profile(template, spec)
    assert re.findall(r"\(allow network[^)]*remote tcp[^)]+\)", rendered) == []


# AC-5: argv full-shape
async def test_argv_full_shape(tmp_path) -> None:
    captured: dict = {}
    async def fake(argv, **k):
        captured["argv"] = argv
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b"", "elapsed_s": 0.0})()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        await SandboxExecAdapter().run(spec)
    argv = captured["argv"]
    assert argv[0] == "sandbox-exec"
    assert argv[1] == "-f"
    assert Path(argv[2]).suffix == ".sb"
    assert tuple(argv[3:]) == spec.cmd


# AC-6: AST-based forbidden-subprocess check
def test_module_has_no_forbidden_subprocess_calls() -> None:
    src = Path("src/codegenie/transforms/sandbox/sandbox_exec.py").read_text()
    tree = ast.parse(src)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name] = a.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                aliases[a.asname or a.name] = f"{mod}.{a.name}"
    BAD_ROOTS = {"subprocess", "os.system", "os.popen", "asyncio.create_subprocess_exec",
                 "asyncio.create_subprocess_shell", "multiprocessing.Process"}
    BAD_PREFIXES = ("os.exec", "os.spawn", "os.posix_spawn")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            resolved = aliases.get(name.split(".")[0], name.split(".")[0]) + name[len(name.split(".")[0]):]
            assert not any(resolved.startswith(p) for p in BAD_PREFIXES), f"forbidden: {resolved}"
            assert resolved.split("(")[0] not in BAD_ROOTS, f"forbidden: {resolved}"
            # import_module("subprocess"|"os") literal check
            if name.endswith("import_module") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and first.value in {"subprocess", "os"}:
                    pytest.fail(f"dynamic import of {first.value!r} forbidden")


# AC-7: result variant translation via real-shape mock
@pytest.mark.parametrize(
    "returncode, elapsed_s, stderr, expected_type, expected_host",
    [
        (0, 0.1, b"", Completed, None),
        (-9, 6.0, b"", TimedOut, None),
        (1, 0.5, b"Sandbox: npm(1234) deny(1) network-outbound github.com:443\n", NetworkDenied, "github.com"),
        (1, 0.5, b"Sandbox: npm(1234) deny(1) network-outbound pypi.org:443\n", NetworkDenied, "pypi.org"),
    ],
)
async def test_result_variant_translation(
    returncode: int, elapsed_s: float, stderr: bytes,
    expected_type: type, expected_host: str | None, tmp_path,
) -> None:
    async def fake(*a, **k):
        return type("R", (), {"returncode": returncode, "stdout": b"", "stderr": stderr, "elapsed_s": elapsed_s})()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"),
        cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, expected_type)
    if expected_host is not None:
        assert result.host == expected_host


# AC-8: env mapping
async def test_env_mapping_reaches_chokepoint(tmp_path) -> None:
    captured: dict = {}
    async def fake(argv, **k):
        captured["env_extra"] = k.get("env_extra", {})
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b"", "elapsed_s": 0.0})()
    spec = JailedSubprocessSpec(
        cmd=("npm", "--version"),
        cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        await SandboxExecAdapter().run(spec)
    assert captured["env_extra"].get("npm_config_ignore_scripts") == "true"


# AC-12: marker registered (pytestconfig, no shell-out)
def test_nightly_macos_marker_registered(pytestconfig) -> None:
    markers = pytestconfig.getini("markers")
    assert any(m.split(":", 1)[0].strip() == "nightly_macos" for m in markers)


# AC-16: typed-error fence
@pytest.mark.parametrize("exc", [OSError("disk"), TimeoutError("budget"), Exception("oops")])
async def test_typed_error_fence(exc, tmp_path) -> None:
    async def fake(*a, **k):
        raise exc
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        result = await SandboxExecAdapter().run(spec)  # must NOT raise
    assert result is not None
    # Variant must be typed — TimedOut for TimeoutError, SubstrateSetupFailed for OSError, etc.


# AC-17: determinism
def test_render_is_deterministic(tmp_path) -> None:
    template = _load_template()
    spec1 = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({
            RegistryUrl("https://registry.npmjs.org"),
            RegistryUrl("https://pypi.org"),
        })),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    spec2 = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(),
        network=RegistryAllowlist(hosts=frozenset({
            RegistryUrl("https://pypi.org"),
            RegistryUrl("https://registry.npmjs.org"),
        })),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    assert _render_profile(template, spec1) == _render_profile(template, spec2)
    assert _render_profile(template, spec1) == _render_profile(template, spec1)


# AC-18: Hypothesis properties
@given(st.sets(st.sampled_from([
    "https://registry.npmjs.org", "https://pypi.org",
    "https://files.pythonhosted.org", "https://github.com",
]), min_size=0, max_size=4))
def test_allowlist_property_all_hosts_appear(host_strings, tmp_path_factory) -> None:
    tmp_path = tmp_path_factory.mktemp("hp")
    template = _load_template()
    hosts = frozenset({RegistryUrl(s) for s in host_strings})
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=RegistryAllowlist(hosts=hosts),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    rendered = _render_profile(template, spec)
    for s in host_strings:
        from urllib.parse import urlparse
        host = urlparse(s).hostname
        assert host in rendered


# AC-19: cleanup-on-exception
async def test_cleanup_on_exception(tmp_path) -> None:
    async def fake(*a, **k):
        raise OSError("disk full")
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        await SandboxExecAdapter().run(spec)
    leftover = list(Path(tmp_path).glob("*.sb"))
    assert leftover == [], f"leaked profile files: {leftover}"


# AC-20: concurrent-run safety
async def test_concurrent_runs_use_distinct_profiles(tmp_path) -> None:
    import asyncio
    captured_paths: list[str] = []
    async def fake(argv, **k):
        captured_paths.append(argv[2])
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b"", "elapsed_s": 0.0})()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        await asyncio.gather(*[SandboxExecAdapter().run(spec) for _ in range(8)])
    assert len(set(captured_paths)) == 8


# AC-21: substrate-setup failure typed
async def test_substrate_setup_failure_typed(tmp_path) -> None:
    async def fake(*a, **k):
        return type("R", (), {
            "returncode": 65,
            "stdout": b"",
            "stderr": b"Sandbox: sandbox-exec error: parse failure at line 3\n",
            "elapsed_s": 0.05,
        })()
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with mock.patch("codegenie.transforms.sandbox.sandbox_exec.run_allowlisted", side_effect=fake):
        result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, SubstrateSetupFailed)
    assert "parse failure" in result.stderr_excerpt


# AC-22: stateless across calls (no module-level mutable globals)
def test_module_has_no_module_level_mutable_globals() -> None:
    src = Path("src/codegenie/transforms/sandbox/sandbox_exec.py").read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    pytest.fail(f"module-level non-Final assignment: {target.id}")
        # AnnAssign with Final[...] annotation is fine; other AnnAssign at module scope must be Final
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            ann = ast.unparse(node.annotation) if node.annotation else ""
            if "Final" not in ann and not node.target.id.startswith("_"):
                pytest.fail(f"non-Final module-level annotation: {node.target.id}")


# AC-23: classifier kernel identity
def test_classifier_kernel_is_shared_with_bwrap() -> None:
    from codegenie.transforms.sandbox import bwrap, sandbox_exec
    # Both adapters resolve to the same _classify_outcome function reference
    assert bwrap._classify_outcome is sandbox_exec._classify_outcome


# AC-24: match exhaustiveness
def test_match_assert_never_fires_on_synthetic(tmp_path) -> None:
    from typing import cast
    from codegenie.transforms.sandbox_jail import NetworkPolicy
    class _Bogus: pass
    with pytest.raises((AssertionError, TypeError)):  # assert_never raises
        _render_allowlist_clauses(cast(NetworkPolicy, _Bogus()))


# AC-25: Hostname smart-constructor
def test_extract_hostname_validates() -> None:
    h = _extract_hostname(RegistryUrl("https://registry.npmjs.org"))
    assert h == "registry.npmjs.org"
    with pytest.raises(ValueError):
        _extract_hostname(RegistryUrl("not-a-url"))


# AC-26: packaged template (wheel-install survival is also a deferred fixture)
def test_template_loads_via_importlib_resources() -> None:
    # Smoke: the template loads regardless of CWD
    import os
    cwd = os.getcwd()
    try:
        os.chdir("/tmp")
        text = resources.files("codegenie.transforms.sandbox.templates").joinpath(
            "macos-npm.sb"
        ).read_text()
        assert "(deny default)" in text
    finally:
        os.chdir(cwd)


# AC-27: macOS 14+ gate
def test_macos_13_raises_substrate_unsupported(monkeypatch) -> None:
    if sys.platform != "darwin":
        pytest.skip("non-darwin: gate not exercised")
    monkeypatch.setattr("platform.mac_ver", lambda: ("13.6.0", ("", "", ""), ""))
    with pytest.raises(SubstrateUnsupportedError):
        SandboxExecAdapter()


def test_macos_14_constructs(monkeypatch) -> None:
    if sys.platform != "darwin":
        pytest.skip("non-darwin: gate not exercised")
    monkeypatch.setattr("platform.mac_ver", lambda: ("14.0.0", ("", "", ""), ""))
    SandboxExecAdapter()  # must not raise


# AC-28: placeholder residual check
def test_placeholder_residual_raises_typed(tmp_path) -> None:
    bad_template = string.Template("(deny default)\n$UNRESOLVED_TOKEN\n")
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hi"), cwd=FakeSandboxedPath(str(tmp_path)),
        env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=128, pids_max=64,
    )
    with pytest.raises(ProfilePlaceholderUnresolved):
        _render_profile(bad_template, spec)


# AC-29: hexagonal-shape parity
def test_helper_verb_parity() -> None:
    from codegenie.transforms.sandbox import bwrap, sandbox_exec
    assert bwrap._HELPER_VERBS == sandbox_exec._HELPER_VERBS
```

`tests/integration/transforms/test_sandbox_exec_hello_world.py` (AC-10):

```python
from __future__ import annotations
import shutil
import sys

import pytest

from codegenie.transforms.sandbox.sandbox_exec import SandboxExecAdapter
from codegenie.transforms import SandboxedPath  # canonical import per _forward.py
from codegenie.transforms.sandbox_jail import (
    Completed, DenyAll, JailedSubprocessSpec, NpmEnv,
)


@pytest.mark.nightly_macos
@pytest.mark.asyncio
async def test_sandbox_exec_hello_world(tmp_path) -> None:
    if sys.platform != "darwin":
        pytest.skip("non-darwin: macOS substrate; Linux uses bwrap (S4-02)")
    # On darwin, sandbox-exec is built-in — absence means the runner is broken.
    if shutil.which("sandbox-exec") is None:
        pytest.fail("nightly macOS runner is broken: sandbox-exec missing (built-in to macOS)")
    sp = SandboxedPath.create(tmp_path, ".").unwrap() if hasattr(SandboxedPath, "create") else tmp_path
    spec = JailedSubprocessSpec(
        cmd=("/bin/echo", "hello"),
        cwd=sp, env=NpmEnv(), network=DenyAll(),
        time_budget_s=5.0, memory_mib=64, pids_max=32,
    )
    result = await SandboxExecAdapter().run(spec)
    assert isinstance(result, Completed)
    assert result.exit_code == 0
```

Run — all RED (module + template missing). Commit.

### Green — make it pass

1. Write `src/codegenie/transforms/sandbox/templates/macos-npm.sb` + `__init__.py`. Run AC-1 + AC-15 — green.
2. Implement `_extract_hostname`, `_render_allow_network_clause`, `_render_allowlist_clauses`, `_render_profile` (pure). Run AC-3, AC-4, AC-17, AC-18, AC-24, AC-25, AC-28 — green.
3. Implement `SandboxExecAdapter.__init__` (macOS gate) + `run` (chokepoint + tempfile + try/finally + classifier consumption). Run AC-2, AC-5..AC-9, AC-16, AC-19, AC-20, AC-21, AC-23, AC-27 — green.
4. Implement template-loader via `importlib.resources`. Run AC-26 — green.
5. Declare `_HELPER_VERBS` parallel to bwrap's. Run AC-29 — green.
6. Register `nightly_macos` marker in `pyproject.toml`. Run AC-12 — green.
7. AST checks: AC-6, AC-22.
8. On a macOS dev box (or wait for nightly), run AC-10 + AC-11 — green.

### Refactor — clean up

- Both adapters now share helper-verb names (`build_argv`, `render`, `translate`) — Hexagonal Port symmetry visible at file boundary (AC-29).
- Module docstring cites ADR-0006 §Decision + §Tradeoffs row 3 (deprecation acceptance) + ADR-0011 (`importlib.resources` precedent).
- `ruff format`, `mypy --strict`, full unit suite green.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/sandbox/templates/macos-npm.sb` | New: `.sb` profile template with `(deny default)`, system-framework reads, `$JAIL` bind, `$ALLOWLIST_HOSTS` substitution slot. Packaged under `src/` for wheel-install survival. |
| `src/codegenie/transforms/sandbox/templates/__init__.py` | New: empty `__init__.py` so `importlib.resources.files("codegenie.transforms.sandbox.templates")` resolves. |
| `src/codegenie/transforms/sandbox/sandbox_exec.py` | New: `SandboxExecAdapter(SubprocessJail)` — template render + `sandbox-exec` invocation via `run_allowlisted` + `_classify_outcome` consumption + macOS-14+ gate + cleanup-on-exception. |
| `pyproject.toml` | Add `nightly_macos` marker under `[tool.pytest.ini_options] markers` if not already present (AC-12). Add `codegenie.transforms.sandbox.templates` to `[tool.hatch.build]` (or equivalent packaging table) so the `.sb` is shipped in wheels. |
| `tests/unit/transforms/sandbox/test_sandbox_exec_unit.py` | New: AC-1..AC-9, AC-12, AC-15..AC-29. Cross-platform; mocks the substrate. |
| `tests/unit/transforms/sandbox/test_sandbox_exec_mypy_negative.py` | New (AC-2 companion): subprocess-mypy negative test pinning the structural-Protocol fence. |
| `tests/integration/transforms/test_sandbox_exec_hello_world.py` | New: AC-10. Nightly + macOS-only; fail-not-skip on darwin missing sandbox-exec. |
| `tests/integration/transforms/test_sandbox_exec_network_policy.py` | New: AC-11. Nightly + macOS-only. |

**Do NOT touch:**
- `src/codegenie/transforms/sandbox/_classify.py` (S4-02's kernel — consumed read-only here).
- `tests/unit/transforms/sandbox/_fakes.py` (authored by S4-02 hardening; reused).
- `tooling/sandbox/` (old template location — deleted by this story if present).

## Out of scope

- **`BwrapAdapter`** — S4-02.
- **`SubprocessJail` Protocol + `JailedSubprocessSpec` + variants + `SubstrateSetupFailed` + `SubstrateUnsupportedError`** — S4-01 (this story coordinates if any variant is missing).
- **`SandboxedPath` real implementation** — S4-04 (`FakeSandboxedPath` shim used in unit tests; `from codegenie.transforms import SandboxedPath` in integration tests works before AND after S4-04).
- **`ALLOWED_BINARIES` amendment for `sandbox-exec` / `npm` / `curl`** — S4-05.
- **Lima / DinD substitution** — Phase 5 (`05-ADR-0004`). Documented at the symbol; not implemented.
- **`.sb` profile content evolution for OpenRewrite JVM invocation** — Phase 7. This story's profile covers `npm` + `node` only.
- **Per-PR macOS CI runner cost optimization** — explicitly out per ADR-0006 §Consequences row 4.
- **Full postinstall-canary adversarial test on macOS** — S8-04 (`@pytest.mark.phase03_adv`).
- **ADR-0012 §Decision wording drift** (`run_external_cli` → `run_allowlisted`) — doc-debt; surface in `_attempts/S4-03.md` Attempt 1 (shared with S4-02 attempt log). Doc-only follow-up amends ADR-0012.
- **Goal §3 wording drift** ("exit signals" is Linux-flavored — macOS denial path is stderr-parsed) — doc-debt; deferred to phase-arch-design refresh.

## Notes for the implementer

- **Deprecation acceptance is real.** ADR-0006 §Tradeoffs row 3 names it explicitly. Resist any urge to switch to a "more modern" macOS sandbox API (App Sandbox, com.apple.developer.sandbox.* entitlements) — those are GUI-app-tier; Phase 5 owns the proper substitution. Write the `.sb` profile, document the deprecation in the module docstring, move on.
- **`.sb` profile is Scheme-syntax.** Apple's profile language is a small Scheme dialect documented in `man sandbox-exec` and Apple's archived "App Sandbox Design Guide." Allowed forms: `(version 1)`, `(deny default)`, `(allow <action> <args>)`, `(deny <action> <args>)`. Common actions: `file-read*`, `file-write*`, `network*`, `process-exec`, `mach-lookup`, `sysctl-read`. Target forms: `(subpath "/path")`, `(remote tcp "host:port")`. Get the syntax right or the substrate refuses to start — and per **AC-21** this surfaces as a typed `SubstrateSetupFailed`, NOT a sentinel `Completed(exit_code=...)`. Rule 12: fail loud.
- **No substrate registry.** Resist any pull toward `@register_jail("darwin")` decorator. Constructor injection at the recipe-engine layer (recipe picks `BwrapAdapter()` or `SandboxExecAdapter()` based on `sys.platform`) is the right shape for a closed set of three substrates with wildly different constructors. Phase 5 adds Firecracker / DinD the same way.
- **`string.Template` discipline.** Placeholders are `$JAIL` and `$ALLOWLIST_HOSTS` — substituted via `string.Template.safe_substitute({...})`. After substitute, `_render_profile` asserts `re.search(r"\$[A-Z_]+", rendered) is None` and raises `ProfilePlaceholderUnresolved(token)` on regression (AC-28). This is the loud-failure mechanism for a typo'd placeholder name; it replaces ad-hoc `.replace()` calls that fail silently.
- **`str(spec.cwd)`, not `str(spec.cwd.absolute)`.** `Path.absolute` is a method, not a property — `str(spec.cwd.absolute)` yields `"<bound method ...>"`. `SandboxedPath` is already absolute by S4-04 construction; the bare `str()` suffices.
- **Nightly marker convention.** Phase 2 may or may not have an existing `nightly_macos` / `nightly` marker — check `pyproject.toml [tool.pytest.ini_options] markers` and `grep -r "@pytest.mark.nightly" tests/` before declaring a new one. If Phase 2 uses a different name, follow that precedent (Rule 11).
- **NetworkDenied(host) extraction from stderr.** sandbox-exec writes denial messages in a recognizable format: `Sandbox: <process>(<pid>) deny(1) network-outbound <host>:<port>`. The local helper `_parse_sandbox_denial(stderr: bytes) -> Hostname | None` regex-extracts the host; consumed by `_classify_outcome` as the `denial_parser` argument. If multiple denies occurred, the first is canonical.
- **`/usr/bin/curl` is preinstalled on macOS.** Use it in AC-11 directly. If a CI matrix has a stripped runner, fall back to `node -e "fetch(...)"` (node is in `ALLOWED_BINARIES`).
- **Mirror S4-02 helper shapes.** Both adapters should read in parallel — same helper-verb names (`build_argv`, `render`, `translate`), enforced observably by AC-29's `_HELPER_VERBS` parity. A reviewer comparing the two files side-by-side should see the only differences are substrate-specific. This is the Hexagonal-Port pattern's payoff (ADR-0006 §Pattern fit) — preserve it stylistically AND structurally.
- **Pre-flight: kernel + S4-05.** Before starting Green, confirm `src/codegenie/transforms/sandbox/_classify.py::_classify_outcome` exists (S4-02 hardening). If `SubstrateSetupFailed` / `SubstrateUnsupportedError` are missing from `JailedSubprocessResult`'s sum (S4-01), surface as pre-executor blocker — both are load-bearing for AC-21 / AC-27.
- **S4-05's `--ignore-scripts` static fence will close on the CLI half.** This Adapter does not enforce the CLI `--ignore-scripts` token; per ADR-0006 the env half is structural (`NpmEnv`) and the CLI half is the consumer's responsibility. Don't preempt that fence here.
