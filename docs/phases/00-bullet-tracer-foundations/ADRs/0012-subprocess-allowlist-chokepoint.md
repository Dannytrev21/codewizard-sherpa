# ADR-0012: Subprocess allowlist — single chokepoint at `codegenie/exec.py`

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** security · chokepoint · tool-use · phase-evolution
**Related:** [ADR-0008](0008-output-sanitizer-two-pass-chokepoint.md)

## Context

Phase 0 has one subprocess call site (`git rev-parse HEAD` for `RepoSnapshot.git_commit`). Phase 1 adds `tree-sitter`, `scip-typescript`. Phase 2 adds `semgrep`, `syft`, `grype`, `gitleaks`. Phase 5 adds `docker buildx`, `dive`. Phase 7 adds `dockerfile-parse`. By Phase 7 the codebase has 30+ subprocess callsites.

`../critique.md §1.3` and `../critique.md §3.3` both name the absence of a subprocess allowlist as the load-bearing omission in `[P]` and `[B]`: retrofitting an allowlist over a codebase that already shells out everywhere is not bounded work. The security lens proposed an allowlist from day one and made it load-bearing.

The cost of the allowlist in Phase 0 is trivial — one `frozenset` and one wrapper function. The cost of *not* having it is unbounded by Phase 7. The hostile environment for tool use is real: an LLM in Phase 4 could be prompted into emitting `subprocess.run(["bash", "-c", ...])`; a malicious repo could plant a binary on `$PATH`; an env-var injection could substitute `GIT_SSH_COMMAND` for a remote shell.

The chokepoint has to land in Phase 0 or the discipline is gone.

## Options considered

- **No allowlist (`[P]`, `[B]`).** Direct `subprocess.run` calls scattered through probes. Phase 7's 30 callsites is "30 places to audit." Retrofitting after Phase 4 (when LLM-emitted code enters the loop) is not bounded.
- **Allowlist enforced by lint rule.** Block direct `subprocess` import in `src/codegenie/` (except in `exec.py`). Catches direct usage; doesn't enforce the env-stripping and timeout discipline at every callsite.
- **Allowlist via single chokepoint `exec.py` (synth).** `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` at module scope. `async def run_allowlisted(argv, *, cwd, timeout_s, env_extra) -> ProcessResult` is the *only* path. `forbidden-patterns` pre-commit hook + AST scan test (`test_no_shell_true.py`) blocks `shell=True`, `os.system`, `os.popen`, `subprocess.run` with shell, `pickle.loads`, etc., in `src/codegenie/`. Every binary addition is a one-line PR adding to the frozen set.

## Decision

**`src/codegenie/exec.py` is the only path from `codegenie` source to an external binary.** `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` in Phase 0. `async def run_allowlisted(argv, *, cwd: Path, timeout_s: float, env_extra: dict[str, str] = {}) -> ProcessResult` is the public API. The wrapper enforces:

- `argv[0] not in ALLOWED_BINARIES` → `DisallowedSubprocessError`.
- `shell=False` always (explicit for code-review visibility).
- `stdin=DEVNULL` unless explicitly overridden.
- Env filtered to `{PATH, HOME, LANG, LC_ALL}` ∪ `env_extra`; strips `SSH_AUTH_SOCK`, `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- `cwd` mandatory; resolved; must be under the analyzed-repo root.
- Timeout mandatory; SIGKILL at `1.5 × timeout_s`.
- Weakref process-tracking table for SIGKILL on coordinator cancel.

`forbidden-patterns` pre-commit hook + `tests/adv/test_no_shell_true.py` AST scan block `shell=True`, `os.system`, `os.popen`, `subprocess.run` shell variants, `pickle.loads`, `yaml.load(` without `Loader=`, `eval(`, `exec(`, `__import__(` from `src/codegenie/`.

Every binary added to `ALLOWED_BINARIES` is a deliberate-PR change with mandatory review.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7's 30 subprocess callsites all flow through one wrapper — environment hygiene, timeout, allowlist enforced once | The wrapper's signature constraints (timeout mandatory, cwd mandatory) feel heavy for a "just run git" use case in Phase 0 |
| Env-stripping ensures `OPENAI_API_KEY` / `AWS_*` / `SSH_AUTH_SOCK` never reach a child process — even if leaked into the parent | Tools requiring those env vars (e.g., a hypothetical probe that needs `AWS_SECRET_ACCESS_KEY` for SCIP) must explicitly pass via `env_extra` — friction is the point |
| Adding `tree-sitter` in Phase 1 is a one-line PR: `frozenset({"git", "tree-sitter"})`. The change is visible in code review; never a buried implementation detail | Every binary addition requires the deliberate PR and (per convention) an ADR-amendment for the rationale |
| Phase 4's LLM-fallback agent — if it ever emits subprocess code — can only succeed against the chokepoint or fail closed | The LLM might generate code that *imports* the chokepoint correctly but uses unsafe arguments (e.g., `cwd` outside the repo); the wrapper validates that case too |
| Coordinator cancel + SIGKILL of tracked children prevents zombie subprocesses on probe timeout | The weakref process-tracking table is per-process state — concurrent CLI invocations don't share it (acceptable; each owns its own children) |

## Consequences

- `src/codegenie/exec.py` is the **only** file in `src/codegenie/` that imports `asyncio.create_subprocess_exec`. The `forbidden-patterns` hook enforces this.
- The single Phase 0 call site is `RepoSnapshot.git_commit` via `await exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_s=10)`.
- Phase 1's additions (`tree-sitter`, `scip-typescript`, etc.) are PRs against `ALLOWED_BINARIES`. Each addition expects (a) a callsite using the wrapper, (b) a test asserting the binary's failure modes are caught by the wrapper, (c) a brief ADR amendment or note explaining why the binary is needed.
- The `tool-readiness` check (`~/.codegenie/.tool-cache.json`) populates from `ALLOWED_BINARIES` — only checked binaries are in the cache. Phase 0 checks just `git`; the infrastructure scales.
- `tests/adv/test_no_shell_true.py` and `tests/adv/test_env_var_strip.py` are part of the Phase 0 adversarial suite. They pin the structural invariants.
- Phase 11's GitHub PR-opening could plausibly route through `gh` CLI — added to `ALLOWED_BINARIES` then.

## Reversibility

**Medium.** Removing the chokepoint and allowing direct `subprocess` calls is mechanically possible (delete `exec.py`'s wrapper requirement, relax the `forbidden-patterns` hook), but every probe written Phase 1+ uses the wrapper. Reverting means rewriting every callsite, plus losing the env-strip and timeout discipline. By Phase 5 the cost is high; by Phase 14 the cost is impractical. Adding back is harder than the original Phase 0 cost.

## Evidence / sources

- `../final-design.md §2.5` (Subprocess allowlist — adopted as load-bearing)
- `../critique.md §1.3` (Critic flags `[P]`'s omission)
- `../critique.md §3.3` (Critic flags `[B]`'s omission — by Phase 7 the codebase has 30+ callsites)
- `../phase-arch-design.md §Component design / Subprocess allowlist`
- `../phase-arch-design.md §Agentic best practices` (Tool-use safety)
- `../phase-arch-design.md §Edge cases` (Subprocess allowlist violation handling)
