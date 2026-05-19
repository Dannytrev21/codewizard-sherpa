# Execution — safe-run rules

The skill runs real commands against a real working tree. The
defaults below keep that safe; flags relax them when the operator
explicitly accepts the trade.

## Stage 0 — Environment doctor (before anything else)

Verify these tools exist on `PATH` before any plan command runs:

| Tool | Why required |
|---|---|
| `ruff` | All gate / lint commands route through it |
| `mypy` | Type-checking gate |
| `pytest` | Every test command |
| `make` | The discovered plan uses `make check` / `make fence` / etc. |
| `mkdocs` | Doc-build gate; many phases include it |
| `codegenie` (or the project's CLI binary) | Smoke gather + audit verify |

Resolution: `shutil.which(tool)` for each. If any are missing, bail
with a structured error that names every missing tool AND the most
likely cause:

- **No `.venv` on PATH and the cwd is a git worktree** — most common.
  Tell the operator to prepend the *parent* repo's `.venv/bin/`:
  `PATH="<parent-repo>/.venv/bin:$PATH" <re-invocation>`
- **`make bootstrap` exists and the venv is genuinely missing** —
  tell them to run it consciously.
- **A tool exists but isn't in `pyproject.toml`** — that's a finding,
  not an execution error; route it as sub-system.

Stage 0 does NOT auto-install or auto-bootstrap. Asymmetric cost:
auto-installing the wrong tool in someone's wrong environment is much
worse than a clean bail with instructions.

## Read-only by default

The default execution policy is: every command in the discovered plan
must be *either* (a) a read-only test/check or (b) a documented
write that lands inside one of the allowlisted paths. If a command
falls outside both, mark it ⚠️ in the execution plan and skip it
unless `--auto-confirm` is set OR the operator answered yes inline.

### Allowlisted write paths

The skill expects its own commands to touch only:

- `.codegenie/` inside the analyzed repo (the gather pipeline writes
  here by design; the OS namespace is per-repo and gitignored)
- `docs/phases/{phase}/_e2e/` (the report)
- `docs/phases/{phase}/stories/_drafts/` (draft stories)
- `docs/phases/{phase}/ADRs/_drafts/` (draft ADRs)
- `FINDINGS.md` at repo root (critical-class only)
- For trivial-class inline edits: the exact files the finding names

Anything else triggers an inline confirmation prompt or a
`bounded` finding ("the discovery cascade proposed a command that
writes outside the allowlist — confirm or recategorise").

### Forbidden actions (always)

These are blocked regardless of flag combination, because their cost
is asymmetric and recovery is expensive:

- `git push` (humans always merge)
- `git reset --hard`, `git clean -fd`, `git checkout .` (destructive)
- `gh pr create`, `gh pr merge`, `gh issue close` (publishing)
- `rm -rf` outside `.codegenie/` and `_drafts/` (data loss)
- `pip install`, `uv pip install`, `npm install` outside venv tooling
  (state mutation of the host)
- Anything that requires credentials the local repo doesn't have
  (production deploy, registry push, secrets manager calls)
- `subprocess.run(..., shell=True)` even inside scripts the skill
  generates (the codebase's `forbidden-patterns` hook blocks it
  repo-wide; the skill respects the same rule)

## Capturing command output

Every command runs through a structured-capture wrapper. For each
command, record into the report:

```
{
  "command": "make check",
  "exit_code": 0,
  "wall_clock_ms": 105632,
  "stdout_path": "/tmp/shakedown-<run-id>/cmd-01.stdout",
  "stderr_path": "/tmp/shakedown-<run-id>/cmd-01.stderr",
  "files_created": ["/path/repo/.codegenie/context/repo-context.yaml", ...],
  "files_modified": []
}
```

Long stdout/stderr are written to the temp dir and *referenced* in
the report (path + tail-100-lines snippet), not pasted inline — the
report stays readable.

## Timeouts

- Per-command timeout: 10 minutes (matches the `Bash` tool default)
- Per-stage timeout: 30 minutes (whole-stage envelope)
- Per-shakedown timeout: 90 minutes (the operator's patience floor)

A timeout is a finding (class: bounded; route: spawn a task "command X
timed out on phase Y — investigate whether it's a regression or
whether the timeout floor should rise").

## Concurrency

- Commands run sequentially by default (predictable ordering matters
  for the report; parallel runs interleave stderr unhelpfully)
- The skill respects the existing test suite's parallelism config
  (`pytest -n auto` if the suite is xdist-aware) but doesn't
  parallelise *across* the discovered plan items

## Idempotence

Every command in the plan should be idempotent when re-run on the
same tree. If a command isn't (it writes a non-deterministic artifact,
it depends on cold-cache state), flag it as a sub-system finding
("non-idempotent step in the shakedown plan — wrap or fix").

## Logging

Use the existing project logging (`structlog`) when calling into
codegenie modules; capture the JSON-structured log lines separately
from stdout/stderr so the triage stage can grep for known event names
(`probe.failure`, `audit.write.ok`, `cache.miss`, etc.).

## Re-runnability

The skill can be re-run multiple times on the same phase. Each run
produces a distinct report file (`e2e-report-{ISO}.md`); the previous
reports are not deleted or overwritten. Discovery's "previous-report
check" step (see `triage.md`) reads the most-recent file to compute
recurrence promotions.

## What NOT to do in execution

- Do not invoke `pytest --collect-only` to "discover" tests; use the
  test names the discovery cascade derived from doc Done-criteria.
  Discovery without docs is hallucinatory.
- Do not re-run `make check` ten times to make it pass on the second
  try; one run, one outcome, route the failure.
- Do not write to the analyzed repo's `.git/` directory.
- Do not start a long-running background process unless it's explicitly
  in the plan (and you have a wired-up cleanup); shakedown is a finite
  one-shot run.
- Do not exec into a container, sandbox, or microVM; shakedown runs in
  the operator's existing shell environment. Sandbox decisions belong
  to the trust-gate layer downstream.
