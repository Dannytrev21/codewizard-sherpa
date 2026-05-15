# Story S1-07 — `run_external_cli` wrapper with optional bubblewrap + 64 MB cap + env strip

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready (HARDENED 2026-05-15)
**Effort:** M
**Depends on:** S1-06
**ADRs honored:** 02-ADR-0001 (allowlist; §Consequences last bullet pins `bwrap`/`bubblewrap` as intentionally NOT in `ALLOWED_BINARIES`), 02-ADR-0003 (registry annotations) — composes; this story does not itself author an ADR.

## Validation notes (2026-05-15 — phase-story-validator Pass 1)

This story was hardened in-place. Audit log at `_validation/S1-07-run-external-cli.md`. The major changes:

- **BLOCK fix (Consistency).** Original AC-3 said the wrapper passes `["bwrap", ...] + argv` through `run_allowlisted`, but `run_allowlisted`'s first action is an allowlist check that would reject `bwrap` (which is intentionally NOT in `ALLOWED_BINARIES` per 02-ADR-0001 §Consequences last bullet, pinned by the green regression test `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` from merged S1-06 AC-15). The original Refactor "Reconcile" paragraph and Notes §1 then proposed *adding* `bwrap` to `ALLOWED_BINARIES` — which would break the merged regression test and roll back S1-06. **Resolution:** invoke `bwrap` via a private `_spawn_bwrap_wrapped` helper inside `exec.py` itself (same file, same trust tier as `run_allowlisted`); the helper reuses the six Phase 0 invariants by delegating to a shared private `_spawn_with_invariants` extraction. `bwrap` stays out of `ALLOWED_BINARIES`. New AC-3b pins the regression. The Refactor "Reconcile" paragraph and Notes §1 are struck and replaced.
- **BLOCK fix (Consistency).** Original AC-5 said "truncate to the last `max_stdout_bytes // 2` bytes" but the Implementation outline §3 and green sketch both used `cap - len(_TRUNC_MARKER)` (i.e. ~all of `cap`). The executor would not have been able to satisfy both. **Resolution:** pin `cap - len(_TRUNC_MARKER)` (the sketch's formula); strike `// 2`. Rationale: maximizes useful tail, matches the architecture's "tail-included" wording.
- **BLOCK fix (Consistency).** Original AC-7 pinned env to the 4-key Phase 0 `_filter_env` baseline, but `phase-arch-design.md §"Component design" #3` line 506 enumerated 6 keys (`PATH, HOME, LANG, LC_ALL, TERM, CODEGENIE_*`). **Resolution:** pin the 4-key Phase 0 baseline (it is what is merged, has zero downstream demand for `TERM`/`CODEGENIE_*`, and matches the story's "no `env_extra` parameter" policy). A one-line arch-doc edit is added to Files to touch to narrow line 506.
- **BLOCK fix (Consistency).** Original AC-5 said cap "on exceed" only; arch line 510 said "tail-included in failures" (success was unstated). The story implicitly capped on every call. **Resolution:** explicit AC-5 wording — cap on every call regardless of `returncode`; a one-line arch-doc edit narrows line 510.
- **HARDEN (Test quality).** Original AC-8 last assertion `result.stdout.endswith(b"A" * 1024)` could not distinguish head-truncation from tail-truncation (input was uniform `A` bytes). **Resolution:** new test uses head=`A` × N + tail=`B` × N input and asserts the suffix is exclusively `B` bytes — kills head-vs-tail mutants.
- **HARDEN (Coverage).** Original story mentioned tmpdir cleanup in passing but no AC pinned it; no test exercised it. **Resolution:** new AC-3c + three sub-tests covering clean-exit, non-zero-exit, and timeout paths.
- **HARDEN (Test quality).** Original AC-10 named three structured log events but the TDD plan asserted none of them; AC-4's warn-once claim was tested only by argv inspection (mutant-passable). **Resolution:** TDD plan adds `structlog.testing.capture_logs()` assertions for each event (the codebase's existing idiom; see `tests/unit/test_exec.py` line ~285) and a serial warn-once test that counts emissions.
- **HARDEN (Test quality).** Original cap test allocated 100 MB to verify an algorithmic invariant. **Resolution:** primary cap test uses `max_stdout_bytes=128` synthetic input (sub-ms, readable); the 100 MB case is removed (the property test covers the size-independence claim).
- **HARDEN (Test quality).** Added `tests/property/test_truncate_tail.py` Hypothesis test (the codebase's established idiom for invariant tests; see `tests/property/test_index_freshness_roundtrip.py`) covering `_truncate_tail`'s three invariants — kills off-by-one, head-bug, and missing-marker mutants in one pass.
- **HARDEN (Consistency).** Original AC-9 referenced `tests/adv/test_no_shell_true.py` (Phase 0 S4-05). That test file does not exist in the merged repo — the actual structural defense is the `forbidden-patterns` pre-commit hook in `scripts/check_forbidden_patterns.py` (banning `shell=True`, `subprocess.run(shell=)`, `os.system`, `os.popen`, etc., scoped to `\.py$` excluding `tests/`, `scripts/`, `tools/`). **Resolution:** AC-9 rewritten to reference the actual mechanism; the gap in the Phase 0 AST scan (which would also need to ban `asyncio.create_subprocess_exec` outside `exec.py`) is recorded as out-of-scope for this story (a Phase 0 S4-05 backlog item).
- **HARDEN (Test quality).** Tests originally passed bare strings where `probe_name: ProbeId` was required. Under `mypy --strict` (AC-12) those would fail. **Resolution:** all test invocations wrap `ProbeId(...)` per the S1-04/S1-05 family precedent.
- **HARDEN (Design patterns).** `probe_name: ProbeId` flows into `tempfile.mkdtemp(prefix=f"{probe_name}-")`; `ProbeId` is an unconstrained `NewType[str]`. **Resolution:** new AC-14 — `_maybe_wrap_with_bwrap` validates `probe_name` against `^[a-z][a-z0-9_]{0,63}$` before passing to `mkdtemp` and raises `ValueError` on mismatch (defensive at the boundary). A red test exercises the rejection.
- **DESIGN-PATTERNS opportunity** (not an AC). Phase 5 will introduce a second sandbox wrapper (microVM); seccomp is a likely third. The current `_maybe_wrap_with_bwrap` is a Command-pattern wrapper, not a registry — that is correct under the rule of three (only one wrapper today). Notes-for-implementer flags the future seam: if/when wrapper #2 lands, split `_maybe_wrap_with_bwrap` into `_build_bwrap_argv` (pure) + `_create_bwrap_session` (impure) and introduce `@register_sandbox_wrapper(name=...)`. Do NOT pre-build the registry now; that is a Phase 5 concern.
- **CONFLICT RESOLUTION.** Two critics disagreed on the bwrap reconciliation: Critic 1 (Consistency) said keep `bwrap` out of the allowlist per the merged ADR; Critic 2 (Test-Quality+Design-Patterns) said add `bwrap` to the allowlist as "the simpler path." Per the synthesizer priority `Consistency > Coverage > Test-Quality > Design-Patterns`, Consistency wins — the merged ADR-0001 amendment and S1-06 AC-15 regression test are the source of truth. Critic 2's path would require rolling back already-merged work, which is out of this story's scope.

## Context

Layer B/G probes (`SemgrepProbe`, `SyftProbe`, `GrypeProbe`, `GitleaksProbe`, `ScipIndexProbe`, `AstGrepProbe`, `RipgrepCuratedProbe`, `TestCoverageMapping`) all need the same shape of subprocess invocation: a name-bound `ProbeId`, env stripped to the Phase 0 baseline, optional `bubblewrap` egress containment on Linux, a 64 MB stdout/stderr cap with tail-included on failure. `run_external_cli` is the one place that shape lives. Layer C (`docker`, `strace`) uses `run_allowlisted` directly — those probes need to construct hardening argv at the call site and the wrapper would obscure that.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 — run_external_cli` — public interface, internal structure, env strip, optional `bubblewrap` wrap, 64 MB stdout cap.
  - `../phase-arch-design.md §"Tradeoffs (consolidated)"` row "`bubblewrap` opt-in-on-availability" — Linux best-effort, macOS no-op.
  - `../phase-arch-design.md §"Anti-patterns avoided"` row "Hexagonal sandbox that smuggles subprocess into the core" — `run_external_cli` is honestly a Command-pattern wrapper; do not invent a `Port` abstraction.
  - `../phase-arch-design.md §"Goals"` G6 — "One subprocess port for Layer B/G external CLIs; Layer C keeps using `run_allowlisted` directly."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — 02-ADR-0001 §Consequences — `run_external_cli` wraps for seven Layer B/G binaries; `RuntimeTraceProbe` calls `run_allowlisted("docker", …)` directly.
- **Source design:**
  - `../final-design.md §"Components" §3 _run_external_cli` — composition rationale.
- **Existing code:**
  - `src/codegenie/exec.py` — Phase 0 `run_allowlisted` is the delegate; reuse `_filter_env`, `_RUNNING_PROCS`, the SIGTERM→SIGKILL escalation. **Extend the same module — do not create a new file** (`run_external_cli` is the second function in `exec.py`).
  - S1-06's extension to `ALLOWED_BINARIES` — already present when this story lands (depends-on).
- **External docs (only if directly relevant):**
  - https://man7.org/linux/man-pages/man1/bwrap.1.html — `bubblewrap` flags (`--unshare-net`, `--ro-bind`, `--bind`).

## Goal

Extend `src/codegenie/exec.py` with `async def run_external_cli(probe_name: ProbeId, argv: list[str], *, cwd: Path, timeout_s: float, allowlisted_egress: frozenset[str] = frozenset(), max_stdout_bytes: int = 64 * 1024 * 1024) -> ProcessResult` — a Layer-B/G subprocess port that (a) allowlist-checks the *inner* probe binary (i.e. `argv[0]`) against `ALLOWED_BINARIES`; (b) on Linux when `shutil.which("bwrap") is not None`, wraps `argv` with `bubblewrap --unshare-net --ro-bind <cwd> /work --bind <tmp> /tmp/probe --` and invokes via a *private direct-spawn helper inside `exec.py`* (NOT via `run_allowlisted`, because `bwrap` is intentionally outside `ALLOWED_BINARIES` per 02-ADR-0001 §Consequences); (c) on macOS or when `bwrap` is missing, routes the unwrapped argv through `run_allowlisted`; (d) strips env to the Phase 0 baseline; (e) caps stdout/stderr at `max_stdout_bytes` on every call (success or failure) with tail-preservation; (f) propagates `ProbeTimeoutError` / `ToolMissingError` per Phase 0; (g) returns non-zero exits as `ProcessResult` (no raise). Six Phase 0 invariants (no shell, stdin DEVNULL, `_filter_env`, mandatory `cwd`, mandatory `timeout`, SIGTERM→SIGKILL escalation) are preserved through a shared private extraction `_spawn_with_invariants` reused by both `run_allowlisted` and `_spawn_bwrap_wrapped`.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/exec.py` exports `run_external_cli` via `__all__`. Signature exactly matches the architecture: `probe_name: ProbeId`, `argv: list[str]`, `*`, `cwd: Path`, `timeout_s: float`, `allowlisted_egress: frozenset[str] = frozenset()`, `max_stdout_bytes: int = 64 * 1024 * 1024`. Return type is `ProcessResult`.
- [ ] **AC-2.** All six Phase 0 invariants (allowlist check on the *inner* probe argv, no shell, stdin DEVNULL, `_filter_env` env-by-omission, cwd hygiene, SIGTERM→100 ms→SIGKILL escalation) hold on every path through `run_external_cli`. The non-bwrap path delegates to `run_allowlisted` unchanged. The bwrap path invokes the inner spawn via a shared private helper `_spawn_with_invariants(argv, cwd, timeout_s, env)` that both `run_allowlisted` and `_spawn_bwrap_wrapped` use; the allowlist check happens at the boundary of `run_external_cli` itself against `argv[0]` (the inner probe binary), not against the bwrap-prefixed argv.
- [ ] **AC-3.** When `sys.platform.startswith("linux")` AND `shutil.which("bwrap") is not None`: `run_external_cli` allowlist-checks the *inner* `argv[0]` (raising `DisallowedSubprocessError` if not in `ALLOWED_BINARIES`), then invokes `bwrap` via the private `_spawn_bwrap_wrapped(probe_name, argv, cwd, timeout_s, allowlisted_egress)` helper. That helper constructs `["bwrap", "--unshare-net", "--ro-bind", str(cwd_resolved), "/work", "--bind", str(tmpdir), "/tmp/probe", "--"] + argv` (one tmpdir per call via `tempfile.mkdtemp(prefix=f"{probe_name}-")`), then calls `_spawn_with_invariants(wrapped_argv, cwd=cwd_resolved, timeout_s=timeout_s, env=_filter_env(env_extra=None))`. When `allowlisted_egress` is non-empty, `--unshare-net` is omitted from the bwrap prefix (egress needed for that call); `--ro-bind`/`--bind` and the `--` separator are still present.
- [ ] **AC-3a.** **`bwrap` / `bubblewrap` are intentionally NOT in `ALLOWED_BINARIES`** (02-ADR-0001 §Consequences last bullet; S1-06 AC-10/AC-15). The bwrap spawn lives *inside `src/codegenie/exec.py`* (same trust tier as `run_allowlisted` and same file as the chokepoint). The wrapper-pattern exception is the load-bearing decision recorded in the ADR; this story does NOT amend the ADR or `ALLOWED_BINARIES`. A red regression test asserts `"bwrap" not in ALLOWED_BINARIES` and `"bubblewrap" not in ALLOWED_BINARIES` after S1-07 lands (companion to the closed-set test from S1-06).
- [ ] **AC-3b.** The bwrap argv shape is deterministic and observable. A test mocks `tempfile.mkdtemp` to return a fixed path and `shutil.which("bwrap")` to return `"/usr/bin/bwrap"`, then asserts the argv passed to the inner spawn (captured via a monkeypatched `_spawn_with_invariants`) equals exactly `["bwrap", "--unshare-net", "--ro-bind", "<cwd>", "/work", "--bind", "<tmpdir>", "/tmp/probe", "--", <inner_argv...>]` (or without `--unshare-net` when egress is non-empty). No shell metacharacters; no string interpolation; argv is value-typed.
- [ ] **AC-3c.** Tmpdir cleanup: after each `run_external_cli` invocation on the Linux+bwrap path (clean exit, non-zero exit, OR timeout/exception propagation), the per-call `mkdtemp` directory is removed via `shutil.rmtree(d, ignore_errors=True)` in a `finally:` block. Three tests assert `not Path(stubbed_tmpdir).exists()` post-call across all three exit paths. Tmpdir does NOT leak when the inner spawn raises.
- [ ] **AC-4.** When `sys.platform == "darwin"` OR `shutil.which("bwrap") is None`: the unwrapped `argv` is passed to `run_allowlisted(argv, cwd=cwd, timeout_s=timeout_s)`; no bwrap wrapping; no tmpdir is created. A module-level `_BWRAP_WARNED: bool` gate emits `subproc.bwrap.skipped` at WARNING level **exactly once per process** (the first call observes a `False` flag, emits, then sets to `True`; subsequent calls see `True` and skip). A serial test invokes `run_external_cli` twice on the macOS path and asserts the `subproc.bwrap.skipped` event count via `structlog.testing.capture_logs()` is `1`, not `2`.
- [ ] **AC-5.** Stdout/stderr are capped at `max_stdout_bytes` (default 64 MB) **on every call** — success or failure. On exceed, `_truncate_tail(buf, cap)` returns `_TRUNC_MARKER + buf[-(cap - len(_TRUNC_MARKER)):]` where `_TRUNC_MARKER = b"...[TRUNCATED]..."`. The full byte length of the returned tail is exactly `cap` (the marker plus the kept tail bytes). When `len(buf) <= cap`, `_truncate_tail` returns the input unchanged (identity, not equality). A new arch-doc edit on `phase-arch-design.md` line 510 narrows "tail-included in failures" → "tail-included on truncation (every call)".
- [ ] **AC-6.** Non-zero exit codes from the child are **not** raised — `run_external_cli` returns `ProcessResult(returncode=N, stdout=tail, stderr=tail)` and the *caller* (a scanner probe) wraps it into `ScannerOutcome.ScannerFailed`. Timeouts and tool-missing continue to raise `ProbeTimeoutError` / `ToolMissingError` per Phase 0 (`run_allowlisted` and `_spawn_with_invariants` both raise; `run_external_cli` does not suppress).
- [ ] **AC-7.** Env-strip: the env passed to the child is exactly `_filter_env(env_extra=None)` from Phase 0 — the **4-key baseline** `{PATH, HOME, LANG, LC_ALL}` (matches the merged `src/codegenie/exec.py` lines 161-166). The architecture text at `phase-arch-design.md` line 506 lists six keys (`PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM`, `CODEGENIE_*`); this story narrows the arch to match the merged Phase 0 implementation via a one-line edit (strike `TERM, CODEGENIE_*`). If a future probe needs `TERM` or `CODEGENIE_*`, it lands as a per-binary ADR amendment (story's stated policy). `run_external_cli` exposes no `env_extra` parameter. A test asserts the captured env keyset passed to the child is `{"PATH", "HOME", "LANG", "LC_ALL"}` exactly (no extras, no missing).
- [ ] **AC-8.1.** Happy path: mock `run_allowlisted` to return `ProcessResult(0, b"ok", b"")`; `run_external_cli` (macOS path, no bwrap) returns the same; `run_allowlisted` is awaited exactly once with the unwrapped argv.
- [ ] **AC-8.2.** Small-cap algorithmic test: with `max_stdout_bytes=128` and a mocked `ProcessResult(0, b"A" * 500, b"")`, the returned `result.stdout` has `len(result.stdout) == 128`, `result.stdout.startswith(b"...[TRUNCATED]...")`, and `result.stdout.endswith(b"A" * (128 - len(b"...[TRUNCATED]...")))`. (Replaces the original 100 MB allocation — the property-based test in AC-13 covers size-independence; the realistic 64 MB constant is the default but not the inner-loop test.)
- [ ] **AC-8.3.** Head-vs-tail discrimination test: with `max_stdout_bytes=64`, mock returns `b"A" * 50 + b"B" * 50` (100 bytes; head=`A`, tail=`B`); the returned `result.stdout` ends in `b"B" * (64 - len(_TRUNC_MARKER))` and **contains zero `A` bytes after the marker prefix**. This kills the head-bug mutant that AC-8.2 alone cannot distinguish.
- [ ] **AC-8.4.** macOS path (`monkeypatch.setattr(sys, "platform", "darwin")` + `_BWRAP_WARNED` reset): `bwrap` wrap is skipped; argv reaches `run_allowlisted` unwrapped; two sequential calls produce exactly one `subproc.bwrap.skipped` event in `structlog.testing.capture_logs()` (warn-once).
- [ ] **AC-8.5.** Linux + `bwrap` present: argv shape per AC-3b; `subproc.bwrap.wrapped` emitted at DEBUG level on each call with `probe_name=` and `egress=` fields.
- [ ] **AC-8.6.** Linux + `allowlisted_egress={"github.com"}`: `--unshare-net` is absent from the wrapped argv; `--ro-bind`/`--bind`/`--` separator are still present.
- [ ] **AC-8.7.** Linux + `bwrap` missing (`shutil.which("bwrap") -> None`): graceful no-op; argv reaches `run_allowlisted` unwrapped; warn-once across two calls via `capture_logs()`.
- [ ] **AC-8.8.** Timeout: when `run_allowlisted` (or `_spawn_with_invariants`) raises `ProbeTimeoutError`, it propagates through `run_external_cli` unchanged; if the bwrap path was taken, the tmpdir is still cleaned (AC-3c covers).
- [ ] **AC-8.9.** Non-zero exit returned not raised: `run_external_cli` returns `ProcessResult(returncode=2, stdout=b"out", stderr=b"err")` when the inner spawn returns the same; no exception.
- [ ] **AC-8.10.** Inner-argv allowlist enforcement: when called with an inner `argv[0]` that is not in `ALLOWED_BINARIES` (e.g., `run_external_cli(ProbeId("p1"), ["nmap", "-sV"], ...)`), `run_external_cli` raises `DisallowedSubprocessError` **before** any spawn (bwrap-wrapped or not) and **before** any tmpdir is created.
- [ ] **AC-9.** No new `asyncio.create_subprocess_exec` or `subprocess.run` callsite outside `src/codegenie/exec.py`. The structural enforcement today is the `forbidden-patterns` pre-commit hook (`scripts/check_forbidden_patterns.py`) plus the single-file convention; both `run_external_cli` and the private `_spawn_bwrap_wrapped` / `_spawn_with_invariants` helpers live inside `exec.py`. (The hook bans `shell=True`, `os.system`, `os.popen`, etc.; extending it to also ban `asyncio.create_subprocess_exec` outside `exec.py` is a Phase 0 S4-05 backlog item — out-of-scope for this story.) A code-search test (or AST scan) asserts only `src/codegenie/exec.py` contains `asyncio.create_subprocess_exec(`.
- [ ] **AC-10.** Structured log emission — verified by `structlog.testing.capture_logs()`:
  - `subproc.bwrap.wrapped` at DEBUG, per call on the Linux+bwrap path, with fields `probe_name: str`, `egress: bool` (true iff `allowlisted_egress` is non-empty).
  - `subproc.bwrap.skipped` at WARNING, **once per process**, with field `reason ∈ {"not_linux", "not_installed"}` (test asserts the field value matches the platform/path).
  - `subproc.stdout.truncated` at WARNING, per call when truncation occurred, with fields `probe_name: str`, `stream: Literal["stdout", "stderr"]`. (Emit one event per stream that was truncated — both streams may truncate independently.)
- [ ] **AC-11.** The TDD plan's red test exists, was committed (one commit before the implementation), and is green after implementation.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/exec/ tests/property/test_truncate_tail.py` all pass on the touched files. Tests use `ProbeId(...)` wrappers (per S1-04/S1-05 family precedent) on every `run_external_cli` call site; bare strings would fail `mypy --strict` (`NewType` is nominal).
- [ ] **AC-13.** Property test at `tests/property/test_truncate_tail.py` (Hypothesis) covers `_truncate_tail`'s three invariants over arbitrary `buf: bytes` and `cap: int`:
  1. `len(_truncate_tail(buf, cap)) <= max(cap, len(_TRUNC_MARKER))`.
  2. `len(buf) <= cap` ⇒ `_truncate_tail(buf, cap) is buf` (identity, not equality — guards unneeded copies).
  3. `len(buf) > cap` ⇒ `result.startswith(_TRUNC_MARKER)` AND `result.endswith(buf[-(cap - len(_TRUNC_MARKER)):])` AND `len(result) == cap`.
  Strategy: `st.binary(min_size=0, max_size=2048)` × `st.integers(min_value=len(_TRUNC_MARKER)+1, max_value=4096)`. Place file under `tests/property/` (codebase convention; see `tests/property/test_index_freshness_roundtrip.py`).
- [ ] **AC-14.** `probe_name` is validated against `^[a-z][a-z0-9_]{0,63}$` at the start of `_maybe_wrap_with_bwrap` (and again at the boundary of `run_external_cli` for safety). A malformed `probe_name` (e.g., `ProbeId("../bad")`, `ProbeId("foo bar")`, `ProbeId("")`) raises `ValueError("invalid probe_name: ...")` *before* any `mkdtemp` call. Rationale: `ProbeId = NewType("ProbeId", str)` is unconstrained at runtime; `tempfile.mkdtemp(prefix=f"{probe_name}-")` would either fail noisily (path separators) or accept surprising input (whitespace). A red test exercises three malformed inputs and asserts `pytest.raises(ValueError, match="invalid probe_name")`. (A constructor-level validator for `ProbeId` itself is a separate follow-up story — out-of-scope here; flag in Notes.)

## Implementation outline

1. **Extract `_spawn_with_invariants`** from the existing `run_allowlisted` body in `src/codegenie/exec.py`. The new private async helper signature: `async def _spawn_with_invariants(argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]) -> ProcessResult`. It owns the six invariants except the allowlist check: no shell (uses `asyncio.create_subprocess_exec`), `stdin=DEVNULL`, accepts pre-built `env`, asserts `cwd` is a resolved directory (resolves with `strict=True` if not already), `asyncio.wait_for(timeout_s)`, SIGTERM→100 ms→SIGKILL escalation via `_escalate_and_kill`, `_RUNNING_PROCS` registration. Refactor `run_allowlisted` to: validate `argv[0] in ALLOWED_BINARIES` → resolve cwd → build env via `_filter_env(env_extra)` → delegate to `_spawn_with_invariants(argv, cwd=resolved_cwd, timeout_s=timeout_s, env=env)`. Public signature and behavior unchanged; `run_allowlisted`'s six invariants are preserved by composition. The existing `tests/unit/test_exec.py` suite must stay green untouched.
2. Add module-level constants/state: `_BWRAP_WARNED: bool = False`, `_TRUNC_MARKER: bytes = b"...[TRUNCATED]..."`, `_PROBE_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,63}$")`.
3. Add `_validate_probe_name(probe_name: str) -> None` — raises `ValueError(f"invalid probe_name: {probe_name!r}")` if `_PROBE_NAME_RE.match(probe_name) is None`.
4. Add `_truncate_tail(buf: bytes, cap: int) -> bytes`. Contract:
   - `if len(buf) <= cap: return buf` (identity).
   - else: `keep = cap - len(_TRUNC_MARKER); return _TRUNC_MARKER + buf[-keep:]`.
   - Length invariant: `len(result) == cap` when truncated.
5. Add `_maybe_wrap_with_bwrap(probe_name: str, argv: list[str], cwd: Path, allowlisted_egress: frozenset[str]) -> tuple[list[str], list[Path], Literal["wrapped","skipped_not_linux","skipped_not_installed"]]` — returns `(maybe_wrapped_argv, tmpdirs_to_clean, status)`. The third element drives the log event. Calls `_validate_probe_name(probe_name)` first. On non-Linux or missing `bwrap`: emits `subproc.bwrap.skipped` at WARNING with appropriate `reason=` exactly once via `_BWRAP_WARNED`; returns `(argv, [], "skipped_*")`. On Linux + `bwrap`: `tmpdir = Path(tempfile.mkdtemp(prefix=f"{probe_name}-"))`; build `wrap = ["bwrap"]`; if `not allowlisted_egress`: append `"--unshare-net"`; append `["--ro-bind", str(cwd), "/work", "--bind", str(tmpdir), "/tmp/probe", "--"]`; emit `subproc.bwrap.wrapped` at DEBUG with `probe_name=`, `egress=bool(allowlisted_egress)`; return `(wrap + argv, [tmpdir], "wrapped")`.
6. Add `async def _spawn_bwrap_wrapped(probe_name: str, argv: list[str], cwd: Path, timeout_s: float, allowlisted_egress: frozenset[str]) -> ProcessResult` — Linux+bwrap-present-only helper. Calls `_maybe_wrap_with_bwrap` (must return `status="wrapped"`), then `_spawn_with_invariants(wrapped_argv, cwd=cwd_resolved, timeout_s=timeout_s, env=_filter_env(env_extra=None))`. The bwrap binary is NOT allowlist-checked here (the spawn lives inside `exec.py`; 02-ADR-0001 §Consequences last bullet); the *inner* `argv[0]` has already been allowlist-checked by `run_external_cli` at its boundary.
7. Add `async def run_external_cli(probe_name: ProbeId, argv: list[str], *, cwd: Path, timeout_s: float, allowlisted_egress: frozenset[str] = frozenset(), max_stdout_bytes: int = 64 * 1024 * 1024) -> ProcessResult`. Body:
   - `_validate_probe_name(probe_name)` (boundary defense; redundant with `_maybe_wrap_with_bwrap`'s call but guards the macOS/no-bwrap path too).
   - Allowlist-check the *inner* `argv[0]` against `ALLOWED_BINARIES`; raise `DisallowedSubprocessError` on miss (AC-8.10).
   - Resolve `cwd` via `cwd.resolve(strict=True)`; assert `is_dir()`.
   - Determine dispatch: if `sys.platform.startswith("linux")` AND `shutil.which("bwrap") is not None`, take the bwrap path; else the unwrapped path. Use a single helper call to `_maybe_wrap_with_bwrap` so the side-effect of warn-once + tmpdir creation lives in one place.
   - If wrapped: try `result = await _spawn_with_invariants(wrapped_argv, cwd=cwd_resolved, timeout_s=timeout_s, env=_filter_env(env_extra=None))`; finally `shutil.rmtree(d, ignore_errors=True)` for each tmpdir.
   - If unwrapped: `result = await run_allowlisted(argv, cwd=cwd_resolved, timeout_s=timeout_s)` (the public Phase 0 path; preserves the existing six-invariant contract one-to-one).
   - Apply `_truncate_tail` to both `result.stdout` and `result.stderr` against `max_stdout_bytes`; emit `subproc.stdout.truncated` per truncated stream (with `stream="stdout"` or `stream="stderr"`); return new `ProcessResult` if either was truncated, else return the original.
8. Append `"run_external_cli"` to `__all__`.
9. Update the module docstring at the top of `exec.py`: add a paragraph naming `run_external_cli` as the Layer-B/G wrapper, the bwrap-not-allowlisted policy (cite 02-ADR-0001 §Consequences last bullet), and pointing at `phase-arch-design.md §"Component design" #3`.
10. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/exec/test_run_external_cli.py`. The codebase's established idioms used here: `structlog.testing.capture_logs()` for log events (see `tests/unit/test_exec.py` ~line 285); `ProbeId(...)` wrappers per S1-04/S1-05 family precedent; `monkeypatch` to reset `_BWRAP_WARNED`.

```python
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import structlog
import structlog.testing

from codegenie.errors import DisallowedSubprocessError, ProbeTimeoutError
from codegenie.exec import (
    ALLOWED_BINARIES,
    ProcessResult,
    _TRUNC_MARKER,
    run_external_cli,
)
from codegenie.types.identifiers import ProbeId

P_SEMGREP = ProbeId("semgrep_probe")


@pytest.fixture
def fake_cwd(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture(autouse=True)
def reset_bwrap_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with `_BWRAP_WARNED = False` so warn-once is observable."""
    import codegenie.exec as ex
    monkeypatch.setattr(ex, "_BWRAP_WARNED", False, raising=False)


# AC-3a — regression: bwrap stays out of ALLOWED_BINARIES (pins 02-ADR-0001 §Consequences)
def test_bwrap_not_in_allowed_binaries() -> None:
    assert "bwrap" not in ALLOWED_BINARIES
    assert "bubblewrap" not in ALLOWED_BINARIES


# AC-8.1 — happy path on macOS (no bwrap)
async def test_happy_path_macos_delegates_to_run_allowlisted(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    expected = ProcessResult(returncode=0, stdout=b"ok", stderr=b"")
    fake = AsyncMock(return_value=expected)
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake)
    result = await run_external_cli(
        P_SEMGREP, ["semgrep", "--version"], cwd=fake_cwd, timeout_s=5.0,
    )
    assert result == expected
    fake.assert_awaited_once()
    # Inner argv reaches run_allowlisted unwrapped.
    call_args = fake.await_args
    assert call_args is not None
    assert call_args.args[0] == ["semgrep", "--version"]


# AC-8.2 — small-cap algorithmic truncation
async def test_small_cap_truncates_tail(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    payload = b"A" * 500
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, payload, b"")),
    )
    result = await run_external_cli(
        P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0,
        max_stdout_bytes=128,
    )
    assert len(result.stdout) == 128
    assert result.stdout.startswith(_TRUNC_MARKER)
    assert result.stdout.endswith(b"A" * (128 - len(_TRUNC_MARKER)))


# AC-8.3 — head-vs-tail discrimination (kills head-bug mutant)
async def test_truncation_keeps_tail_not_head(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    payload = b"A" * 50 + b"B" * 50  # head=A, tail=B
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, payload, b"")),
    )
    result = await run_external_cli(
        P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0,
        max_stdout_bytes=64,
    )
    assert result.stdout.startswith(_TRUNC_MARKER)
    # Tail bytes are exclusively B — head bytes (A) are gone after the marker prefix.
    body = result.stdout[len(_TRUNC_MARKER):]
    assert body == b"B" * (64 - len(_TRUNC_MARKER))
    assert b"A" not in body


# AC-8.4 — macOS warn-once via structlog capture
async def test_macos_warns_once_across_two_calls(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, b"", b"")),
    )
    with structlog.testing.capture_logs() as events:
        await run_external_cli(P_SEMGREP, ["semgrep", "a"], cwd=fake_cwd, timeout_s=5.0)
        await run_external_cli(P_SEMGREP, ["semgrep", "b"], cwd=fake_cwd, timeout_s=5.0)
    skipped = [e for e in events if e.get("event") == "subproc.bwrap.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "not_linux"
    assert skipped[0]["log_level"] == "warning"


# AC-8.5 + AC-3b — Linux+bwrap wraps argv; spawn captured via _spawn_with_invariants
async def test_linux_with_bwrap_wraps_argv(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    import codegenie.exec as ex
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "codegenie.exec.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    monkeypatch.setattr(
        "codegenie.exec.tempfile.mkdtemp",
        lambda prefix: str(fake_cwd / f"{prefix}fixed"),
    )
    seen: list[tuple[list[str], dict[str, str]]] = []
    async def fake_spawn(argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]) -> ProcessResult:
        seen.append((argv, env))
        return ProcessResult(0, b"", b"")
    monkeypatch.setattr(ex, "_spawn_with_invariants", fake_spawn)

    with structlog.testing.capture_logs() as events:
        await run_external_cli(P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)

    argv, env = seen[0]
    assert argv[0] == "bwrap"
    assert "--unshare-net" in argv
    assert "--ro-bind" in argv
    assert "--" in argv
    sep = argv.index("--")
    assert argv[sep + 1:] == ["semgrep", "x"]
    # AC-7 — env is the 4-key Phase 0 baseline exactly
    assert set(env.keys()) == {"PATH", "HOME", "LANG", "LC_ALL"}
    # AC-10 — wrapped event at DEBUG with probe_name + egress fields
    wrapped = [e for e in events if e.get("event") == "subproc.bwrap.wrapped"]
    assert len(wrapped) == 1
    assert wrapped[0]["probe_name"] == "semgrep_probe"
    assert wrapped[0]["egress"] is False


# AC-8.6 — egress omits --unshare-net
async def test_linux_with_bwrap_egress_omits_unshare_net(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    import codegenie.exec as ex
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "codegenie.exec.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    monkeypatch.setattr(
        "codegenie.exec.tempfile.mkdtemp",
        lambda prefix: str(fake_cwd / f"{prefix}fixed"),
    )
    seen: list[list[str]] = []
    async def fake_spawn(argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]) -> ProcessResult:
        seen.append(argv)
        return ProcessResult(0, b"", b"")
    monkeypatch.setattr(ex, "_spawn_with_invariants", fake_spawn)

    await run_external_cli(
        P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0,
        allowlisted_egress=frozenset({"github.com"}),
    )
    assert "--unshare-net" not in seen[0]
    # ro-bind/bind/-- separator are still present
    assert "--ro-bind" in seen[0]
    assert "--bind" in seen[0]
    assert "--" in seen[0]


# AC-8.7 — Linux + bwrap missing — graceful no-op + warn-once with reason="not_installed"
async def test_linux_without_bwrap_warns_once(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("codegenie.exec.shutil.which", lambda name: None)
    fake = AsyncMock(return_value=ProcessResult(0, b"", b""))
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake)
    with structlog.testing.capture_logs() as events:
        await run_external_cli(P_SEMGREP, ["semgrep", "a"], cwd=fake_cwd, timeout_s=5.0)
        await run_external_cli(P_SEMGREP, ["semgrep", "b"], cwd=fake_cwd, timeout_s=5.0)
    skipped = [e for e in events if e.get("event") == "subproc.bwrap.skipped"]
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "not_installed"
    # inner argv reaches run_allowlisted unwrapped
    assert fake.await_args is not None
    assert fake.await_args.args[0] == ["semgrep", "b"]


# AC-8.8 — timeout propagates
async def test_timeout_propagates(monkeypatch: pytest.MonkeyPatch, fake_cwd: Path) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    async def fake_run_allowlisted(argv: list[str], **kwargs: object) -> ProcessResult:
        raise ProbeTimeoutError("semgrep exceeded timeout_s=5 (elapsed_ms=5001)")
    monkeypatch.setattr("codegenie.exec.run_allowlisted", fake_run_allowlisted)
    with pytest.raises(ProbeTimeoutError):
        await run_external_cli(P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)


# AC-8.9 — non-zero exit returned, not raised
async def test_nonzero_exit_returned_not_raised(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(2, b"out", b"err")),
    )
    result = await run_external_cli(P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)
    assert result.returncode == 2
    assert result.stdout == b"out"
    assert result.stderr == b"err"


# AC-8.10 — inner-argv allowlist enforcement: rejects before any spawn or tmpdir
async def test_inner_argv_must_be_in_allowed_binaries(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    mkdtemp_called = {"v": False}
    def fake_mkdtemp(prefix: str) -> str:
        mkdtemp_called["v"] = True
        raise AssertionError("mkdtemp must not run for a disallowed inner binary")
    monkeypatch.setattr("codegenie.exec.tempfile.mkdtemp", fake_mkdtemp)
    with pytest.raises(DisallowedSubprocessError):
        await run_external_cli(P_SEMGREP, ["nmap", "-sV"], cwd=fake_cwd, timeout_s=5.0)
    assert mkdtemp_called["v"] is False


# AC-3c — tmpdir cleanup across all three exit paths (success / non-zero / exception)
@pytest.mark.parametrize(
    "outcome,raises",
    [
        ("success", False),  # returncode=0
        ("nonzero", False),  # returncode=2
        ("timeout", True),   # raises ProbeTimeoutError
    ],
)
async def test_bwrap_tmpdir_cleaned_up(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path, outcome: str, raises: bool,
) -> None:
    import codegenie.exec as ex
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(
        "codegenie.exec.shutil.which",
        lambda name: "/usr/bin/bwrap" if name == "bwrap" else None,
    )
    tmpdir = fake_cwd / "stub_tmp"
    tmpdir.mkdir()
    assert tmpdir.exists()
    monkeypatch.setattr("codegenie.exec.tempfile.mkdtemp", lambda prefix: str(tmpdir))

    async def fake_spawn(argv: list[str], *, cwd: Path, timeout_s: float, env: dict[str, str]) -> ProcessResult:
        if outcome == "success":
            return ProcessResult(0, b"", b"")
        if outcome == "nonzero":
            return ProcessResult(2, b"out", b"err")
        raise ProbeTimeoutError("timed out (elapsed_ms=5001)")
    monkeypatch.setattr(ex, "_spawn_with_invariants", fake_spawn)

    if raises:
        with pytest.raises(ProbeTimeoutError):
            await run_external_cli(P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)
    else:
        await run_external_cli(P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0)

    assert not tmpdir.exists(), f"tmpdir leaked on outcome={outcome}"


# AC-10 — subproc.stdout.truncated emitted per truncated stream
async def test_truncation_emits_log_event(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        "codegenie.exec.run_allowlisted",
        AsyncMock(return_value=ProcessResult(0, b"A" * 500, b"B" * 500)),
    )
    with structlog.testing.capture_logs() as events:
        await run_external_cli(
            P_SEMGREP, ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0,
            max_stdout_bytes=128,
        )
    truncated = [e for e in events if e.get("event") == "subproc.stdout.truncated"]
    streams = {e["stream"] for e in truncated}
    assert streams == {"stdout", "stderr"}


# AC-14 — probe_name regex validation
@pytest.mark.parametrize("bad_name", ["../bad", "foo bar", "", "Foo", "1abc"])
async def test_invalid_probe_name_rejected(
    monkeypatch: pytest.MonkeyPatch, fake_cwd: Path, bad_name: str,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(ValueError, match="invalid probe_name"):
        await run_external_cli(
            ProbeId(bad_name), ["semgrep", "x"], cwd=fake_cwd, timeout_s=5.0,
        )
```

Run — confirm `ImportError: cannot import name 'run_external_cli' from 'codegenie.exec'` and `ImportError: cannot import name '_TRUNC_MARKER' from 'codegenie.exec'`. Commit.

#### Companion property test (AC-13) — `tests/property/test_truncate_tail.py`

```python
from __future__ import annotations

from hypothesis import given, strategies as st

from codegenie.exec import _TRUNC_MARKER, _truncate_tail

MARKER_LEN = len(_TRUNC_MARKER)


@given(
    buf=st.binary(min_size=0, max_size=2048),
    cap=st.integers(min_value=MARKER_LEN + 1, max_value=4096),
)
def test_truncate_tail_length_bound(buf: bytes, cap: int) -> None:
    result = _truncate_tail(buf, cap)
    assert len(result) <= max(cap, MARKER_LEN)


@given(
    buf=st.binary(min_size=0, max_size=2048),
    cap=st.integers(min_value=MARKER_LEN + 1, max_value=4096),
)
def test_truncate_tail_identity_when_under_cap(buf: bytes, cap: int) -> None:
    if len(buf) <= cap:
        assert _truncate_tail(buf, cap) is buf  # identity, not equality


@given(
    buf=st.binary(min_size=0, max_size=2048),
    cap=st.integers(min_value=MARKER_LEN + 1, max_value=4096),
)
def test_truncate_tail_preserves_marker_prefix_and_tail(buf: bytes, cap: int) -> None:
    if len(buf) > cap:
        result = _truncate_tail(buf, cap)
        assert result.startswith(_TRUNC_MARKER)
        assert result.endswith(buf[-(cap - MARKER_LEN):])
        assert len(result) == cap
```

### Green — make it pass

Sketch (extension of `exec.py`):

```python
# src/codegenie/exec.py — additions
import re
import shutil
import sys
import tempfile
from typing import Literal

_BWRAP_WARNED: bool = False
_TRUNC_MARKER: bytes = b"...[TRUNCATED]..."
_PROBE_NAME_RE: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _validate_probe_name(probe_name: str) -> None:
    if _PROBE_NAME_RE.match(probe_name) is None:
        raise ValueError(f"invalid probe_name: {probe_name!r}")


def _truncate_tail(buf: bytes, cap: int) -> bytes:
    if len(buf) <= cap:
        return buf
    keep = cap - len(_TRUNC_MARKER)
    return _TRUNC_MARKER + buf[-keep:]


async def _spawn_with_invariants(
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    env: dict[str, str],
) -> ProcessResult:
    """Shared private spawn used by run_allowlisted and _spawn_bwrap_wrapped.

    Inherits five Phase 0 invariants (no shell, stdin DEVNULL, env from caller,
    mandatory cwd, mandatory timeout, SIGTERM→SIGKILL escalation). The allowlist
    check is the *caller's* responsibility (run_allowlisted does it on argv[0];
    run_external_cli does it on the inner argv[0] before bwrap wrapping).
    """
    # ... extracted from existing run_allowlisted body (lines ~252-310) ...


def _maybe_wrap_with_bwrap(
    probe_name: str,
    argv: list[str],
    cwd: Path,
    allowlisted_egress: frozenset[str],
) -> tuple[list[str], list[Path], Literal["wrapped", "skipped_not_linux", "skipped_not_installed"]]:
    global _BWRAP_WARNED
    _validate_probe_name(probe_name)
    if not sys.platform.startswith("linux"):
        if not _BWRAP_WARNED:
            _log.warning("subproc.bwrap.skipped", reason="not_linux", platform=sys.platform)
            _BWRAP_WARNED = True
        return argv, [], "skipped_not_linux"
    if shutil.which("bwrap") is None:
        if not _BWRAP_WARNED:
            _log.warning("subproc.bwrap.skipped", reason="not_installed")
            _BWRAP_WARNED = True
        return argv, [], "skipped_not_installed"
    tmpdir = Path(tempfile.mkdtemp(prefix=f"{probe_name}-"))
    wrap = ["bwrap"]
    if not allowlisted_egress:
        wrap.append("--unshare-net")
    wrap += ["--ro-bind", str(cwd), "/work", "--bind", str(tmpdir), "/tmp/probe", "--"]
    _log.debug("subproc.bwrap.wrapped", probe_name=probe_name, egress=bool(allowlisted_egress))
    return wrap + argv, [tmpdir], "wrapped"


async def run_external_cli(
    probe_name: ProbeId,
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float,
    allowlisted_egress: frozenset[str] = frozenset(),
    max_stdout_bytes: int = 64 * 1024 * 1024,
) -> ProcessResult:
    _validate_probe_name(probe_name)
    if not argv:
        raise DisallowedSubprocessError("empty argv is not allowlisted")
    inner_binary = argv[0]
    if inner_binary not in ALLOWED_BINARIES:
        raise DisallowedSubprocessError(
            f"binary {inner_binary!r} is not in ALLOWED_BINARIES (allowed: {sorted(ALLOWED_BINARIES)})"
        )
    resolved_cwd = cwd.resolve(strict=True)
    if not resolved_cwd.is_dir():
        raise NotADirectoryError(f"cwd is not a directory: {resolved_cwd}")

    wrapped_argv, tmpdirs, status = _maybe_wrap_with_bwrap(
        probe_name, argv, resolved_cwd, allowlisted_egress,
    )
    try:
        if status == "wrapped":
            # bwrap path: spawn directly inside exec.py (bwrap NOT in ALLOWED_BINARIES).
            result = await _spawn_with_invariants(
                wrapped_argv,
                cwd=resolved_cwd,
                timeout_s=timeout_s,
                env=_filter_env(env_extra=None),
            )
        else:
            # macOS / no-bwrap path: full Phase 0 chokepoint including allowlist re-check.
            result = await run_allowlisted(argv, cwd=resolved_cwd, timeout_s=timeout_s)
    finally:
        for d in tmpdirs:
            shutil.rmtree(d, ignore_errors=True)

    truncated_out = _truncate_tail(result.stdout, max_stdout_bytes)
    truncated_err = _truncate_tail(result.stderr, max_stdout_bytes)
    if truncated_out is not result.stdout:
        _log.warning("subproc.stdout.truncated", probe_name=probe_name, stream="stdout")
    if truncated_err is not result.stderr:
        _log.warning("subproc.stdout.truncated", probe_name=probe_name, stream="stderr")
    if truncated_out is not result.stdout or truncated_err is not result.stderr:
        return ProcessResult(
            returncode=result.returncode, stdout=truncated_out, stderr=truncated_err,
        )
    return result
```

Extend `__all__` to include `"run_external_cli"`. Also export `_TRUNC_MARKER` (or expose via a public `TRUNC_MARKER`) so tests can refer to it without re-defining the literal.

### Refactor — clean up

- Update the module docstring of `exec.py`: a paragraph naming `run_external_cli` as the Layer-B/G port, the bwrap-not-allowlisted wrapper-pattern exception (cite 02-ADR-0001 §Consequences last bullet), and pointing at `../phase-arch-design.md §"Component design" #3`. Add one sentence: *"`bwrap`/`bubblewrap` are deliberately NOT in `ALLOWED_BINARIES`; the bwrap spawn lives inside this module via the private `_spawn_bwrap_wrapped` (or equivalent) helper. The closed-set regression `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` pins this."*
- Confirm: only `src/codegenie/exec.py` contains `asyncio.create_subprocess_exec`. The single-file invariant is preserved because `_spawn_with_invariants` lives in `exec.py` (the same module as `run_allowlisted` and `run_external_cli`).
- Verify the merged closed-set regression test `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` from S1-06 stays green — this story does NOT amend the test or `ALLOWED_BINARIES`.
- Apply the one-line arch-doc edits noted in Files to touch (env baseline 6→4 keys at line 506; truncation wording at line 510).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/exec.py tests/unit/exec/test_run_external_cli.py tests/property/test_truncate_tail.py`, `pytest tests/unit/exec/ tests/unit/test_exec.py tests/property/test_truncate_tail.py -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/exec.py` | Add `run_external_cli` + `_spawn_with_invariants` (extracted from `run_allowlisted`) + `_maybe_wrap_with_bwrap` + `_truncate_tail` + `_validate_probe_name` + `_BWRAP_WARNED` + `_TRUNC_MARKER` + `_PROBE_NAME_RE`. Append `run_external_cli` (and optionally `_TRUNC_MARKER`) to `__all__`. Refactor `run_allowlisted` to delegate to `_spawn_with_invariants` after its allowlist + cwd + env-build steps. Public signature unchanged. |
| `tests/unit/exec/test_run_external_cli.py` | All AC-8.* + AC-3a/3b/3c + AC-14 tests above. |
| `tests/property/test_truncate_tail.py` | AC-13 Hypothesis property tests. |
| `docs/phases/02-context-gather-layers-b-g/phase-arch-design.md` | One-line arch-doc edit on line 506 (narrow env baseline from 6 keys to 4 — strike `, TERM, CODEGENIE_*`) and on line 510 (narrow "tail-included in failures" to "tail-included on truncation (every call, success or failure)"). Reflects the synthesizer's Consistency resolution. |

**Explicitly NOT touched** (preserves S1-06 and 02-ADR-0001 as merged):

- `src/codegenie/exec.py` `ALLOWED_BINARIES` — frozenset stays unchanged. **Do NOT add `bwrap` or `bubblewrap`.** The S1-06 closed-set regression test would fail; the 02-ADR-0001 §Consequences last bullet would be contradicted.
- `docs/phases/02-context-gather-layers-b-g/ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — ADR stays as merged.
- `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` — stays as merged (it pins `bwrap`/`bubblewrap` as NOT allowlisted).

## Out of scope

- **`docker` / `strace` wrapping** — explicitly NOT routed through `run_external_cli` (per 02-ADR-0001 §Tradeoffs and `../phase-arch-design.md §"Component design" #3`); Layer C probes (S5-02 onward) call `run_allowlisted` directly with hardening flags.
- **Adding `bwrap` to `ALLOWED_BINARIES`** — the merged 02-ADR-0001 §Consequences pins this as forbidden. The wrapper-pattern exception is structural: the bwrap spawn lives inside `exec.py`, same trust tier as `run_allowlisted` itself.
- **`ProbeId` constructor-level validation** — AC-14 validates at the `run_external_cli` boundary. A constructor validator on `ProbeId` (e.g., a Pydantic-validated wrapper or `__new__`-checked NewType) is a separate follow-up story under Phase 2 S1-05's domain — flagged in Notes.
- **Per-probe egress policy enforcement** — `allowlisted_egress` is the **caller**'s declaration; this story neither validates nor enforces it. The `--unshare-net` flag is the structural defense; the egress hostnames are advisory metadata for logs.
- **Network namespaces beyond `bwrap`** — Linux network namespaces / nftables rules are Phase 5 (microVM) work.
- **Per-tool retry policy** — bare-metal "is the tool flaking" is the caller's concern; `run_external_cli` runs once.
- **Streaming output processing** — buffered, then capped. If a future tool needs streaming (>>64 MB stdout for SBOM JSON?), that's a separate ADR.
- **Extending the `forbidden-patterns` pre-commit hook to ban `asyncio.create_subprocess_exec` outside `exec.py`** — Phase 0 S4-05 backlog. AC-9 is satisfied today by convention + single-file practice + the AST-scan code-search test in the TDD plan.
- **Sandbox-wrapper registry** — Phase 5 may add a microVM wrapper as the second hardening shape; that's when the rule-of-three threshold is hit and `@register_sandbox_wrapper(name=...)` becomes warranted. Do NOT introduce the registry now (one wrapper, one no-op fallback = below threshold).

## Notes for the implementer

- **`bwrap` policy is settled — do not amend it.** 02-ADR-0001 §Consequences last bullet (merged 2026-05-15) explicitly states `bwrap`/`bubblewrap` are NOT in `ALLOWED_BINARIES`; S1-06 AC-15 shipped the closed-set regression test that pins this. The wrapper-pattern exception is the recorded decision: `bwrap` is invoked from inside `src/codegenie/exec.py` via the private `_spawn_with_invariants` helper, which shares the spawn primitive with `run_allowlisted` itself. Use the bwrap path **without** going through the public `run_allowlisted` allowlist check. The inner probe binary (`argv[0]` of the caller's argv) IS allowlist-checked at the boundary of `run_external_cli`.
- **G6 alignment.** The architecture's Goal G6 says "one subprocess port for Layer B/G external CLIs." "Port" here means one *public* function (`run_external_cli`), not one *spawn site*. The new private spawn sites (`_spawn_with_invariants`, used by both `run_allowlisted` and the bwrap path) are an implementation detail inside `exec.py`. The single-file invariant — only `src/codegenie/exec.py` contains `asyncio.create_subprocess_exec` — is preserved.
- **Refactoring `run_allowlisted` is in-scope.** Extracting `_spawn_with_invariants` is the cleanest way to satisfy AC-2 (six invariants preserved on every path) without duplicating the SIGTERM-escalation + `_RUNNING_PROCS` registration logic. The extraction is value-preserving: `run_allowlisted` keeps the same public signature, the same docstring, and `tests/unit/test_exec.py`'s ~30 tests must stay green untouched. Confirm by running the full pre-existing `tests/unit/test_exec.py` after extraction with NO source changes to it.
- **Warn-once flag is module-level.** `_BWRAP_WARNED: bool` is the simplest correct shape; a `threading.Lock` is unnecessary (the race is benign — at most two duplicate warnings on the very first concurrent pair; subsequent calls observe the flag set). Tests reset it via `monkeypatch.setattr(ex, "_BWRAP_WARNED", False)` and the autouse fixture in the TDD plan.
- **Tail truncation, not head.** When stdout is huge, the tail is what matters (final error message, last finding). The cap is `cap - len(_TRUNC_MARKER)` bytes of tail prefixed with the marker; AC-8.3's head=A/tail=B test discriminates head-bug mutants.
- **Length invariant.** `len(_truncate_tail(buf, cap)) == cap` when truncated (and `== len(buf)` when not). This means the public effective cap is `cap` bytes total *including* the marker — the AC-13 property test pins this; don't write a variant that returns `cap + len(marker)`.
- **No `env_extra` on `run_external_cli`.** Phase 2 scanners do not need supplemental env. If a future probe does (e.g., `GIT_SSH_COMMAND` for a hypothetical signed-fetch use case), that's a per-probe-ADR amendment; do not preemptively widen the signature. AC-7 pins env to the 4-key Phase 0 baseline.
- **`run_external_cli` is the per-call-site decoration, not a sandbox.** The architecture is explicit: `bubblewrap` is opt-in-on-availability hardening, NOT a substitute for the Phase 5 microVM. Do not market it as one in docstrings.
- **Layer C does not call this function.** S5-02's `RuntimeTraceProbe` calls `run_allowlisted("docker", […, "run", "--network=none", "--cap-drop=ALL", "--security-opt=no-new-privileges", …])` directly — those flags are hardening, not generic. The wrapper's `--unshare-net` is not equivalent to `docker run --network=none`; that's why Layer C bypasses.
- **Cleanup discipline.** Per-call `mkdtemp` MUST be `rmtree`-cleaned in `finally`. AC-3c pins this with three parametrized exit-path tests. Leaking tmpdirs is a slow-burning resource leak that surfaces only in CI long after.
- **`probe_name` boundary defense.** `ProbeId = NewType("ProbeId", str)` has no character-class constraint at runtime. Passing `ProbeId("../bad")` or `ProbeId("foo bar")` would otherwise reach `tempfile.mkdtemp` as a filename prefix and either fail noisily or succeed surprisingly. AC-14 pins the `^[a-z][a-z0-9_]{0,63}$` validator. A constructor-level validator on `ProbeId` itself is a separate follow-up (see Out of scope).
- **Future sandbox-wrapper registry (deferred).** If Phase 5 adds a microVM as the second wrapper (and seccomp as a likely third), the rule-of-three threshold is hit. At that point, split `_maybe_wrap_with_bwrap` into `_build_bwrap_argv` (pure) + `_create_bwrap_session` (impure) and introduce `@register_sandbox_wrapper(name=..., precedence=...)`. Do NOT pre-build this now — one wrapper with a no-op fallback is below the threshold; premature pluggability is the exact anti-pattern the arch-doc rejects (see `phase-arch-design.md §"Anti-patterns avoided"` row "Premature pluggability"). Flag the seam in a TODO comment instead.
- **Log-event reasoning.** `subproc.bwrap.skipped` at WARNING (rare, operator-visible); `subproc.bwrap.wrapped` at DEBUG (per-call, would spam at info); `subproc.stdout.truncated` at WARNING (rare; the operator wants to see it). Emit *one* `subproc.stdout.truncated` per truncated stream so the operator can tell which of stdout/stderr blew the cap.
