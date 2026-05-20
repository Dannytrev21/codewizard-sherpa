# Contributing to codewizard-sherpa

This is the operational handbook. The [`README.md`](README.md) covers strategy and architecture; this file covers **how the work actually gets done** day-to-day.

The repo is built around a story-driven, red-green-refactor TDD discipline executed by a five-stage skill pipeline (`roadmap-phase-designer` → `phase-architect` → `phase-story-writer` → `phase-story-validator` → `phase-story-executor`). A sixth skill, `phase-shakedown`, runs phases end-to-end for audit/closeout outside that linear chain. Stories live under [`docs/phases/NN-<slug>/stories/`](docs/phases/) and are the atomic unit of work — one story, one PR-shaped commit triple.

---

## Setup

```console
$ make bootstrap        # uv venv + [dev] extras (pip fallback if uv missing)
$ pre-commit install    # arms the commit-time firewall
$ make check            # lint → typecheck → test → fence
```

You need Python 3.11+ and `git`. `uv` is optional but recommended. External runtime tools (`node`, `semgrep`, `syft`, `grype`, `gitleaks`, …) are listed in [`docs/localv2.md` §6](docs/localv2.md); `codegenie` checks `$PATH` at startup and prints actionable install errors for the missing ones.

---

## The story workflow

Stories are the unit of work. A typical contribution flow is:

```
┌──────────────┐   ┌──────────────────┐   ┌─────────────────┐   ┌─────────────────────┐
│ Pick a story │ → │ Harden (optional)│ → │ RED → GREEN →   │ → │ Mark Done +         │
│ from stories/│   │ phase-story-     │   │ Sweep           │   │ attempt log +       │
│  S<n>-<k>.md │   │ validator        │   │ phase-story-    │   │ lessons + commit    │
└──────────────┘   └──────────────────┘   │ executor        │   └─────────────────────┘
                                          └─────────────────┘
```

### 1. Pick a story

Look for the next `**Status:** Ready` (or `HARDENED`) story under the active phase. Story status vocabulary is `Ready` / `HARDENED` / `GREEN` / `Done` / `BLOCKED`. Stories run sequentially within a step; check `Depends on:` in the frontmatter and the phase's `High-level-impl.md` for ordering.

### 2. Harden (only if the story isn't already hardened)

If the status line says just `Ready` and the validator hasn't passed yet, run `/phase-story-validator <story>` first. It runs four parallel critics (coverage, test-quality, consistency, design-patterns) plus an optional researcher, then a synthesizer edits the story in place. Output: a `_validation/<story>.md` report and a story whose ACs and TDD plan would actually catch a wrong implementation. **Do not skip this on weak stories** — re-litigating gaps mid-execution burns attempt budget.

### 3. Execute — RED → GREEN → Sweep

Three commits, in this order:

1. **RED** (`test(phase<N>/<S<n>-<k>>): RED — <what>`). Write the failing tests prescribed by the story's TDD plan. Run them and confirm they fail for the right reason. Commit before touching any production code.
2. **GREEN** (`feat(phase<N>/<S<n>-<k>>): GREEN — <what>`). Minimum code to make the RED tests pass. No refactors, no adjacent cleanup, no speculative features. Rule 3 (Surgical Changes) is load-bearing here.
3. **Sweep / refactor** (`refactor(phase<N>/<S<n>-<k>>): <what>`). Optional. Use this for cleanups the story explicitly authorizes (e.g., replacing module-local constants with a registry import) so the change is independently revertible if review pushes back.

Use `/phase-story-executor <story>` to run this loop with ReAct + a Ralph Wiggum naive-verification pass. It loops up to 3 implementer attempts and appends to `_attempts/<story-id>.md` each time.

### 4. Mark Done + write the attempt log

When all acceptance criteria are verified and CI is green:

- Update the story's `**Status:**` line to `Done — <YYYY-MM-DD>` with a one-paragraph evidence summary (test counts, lint state, file paths, deviations).
- Create or append `_attempts/<story-id>.md` with the full attempt log: outcome, three-commit hashes, verification table, deviations from the prescribed TDD plan, files touched.
- If you learned something that would help the **next** story, append to `_attempts/_lessons.md`. Format: `## L-<N> — <one-line title> (<story>)` followed by 1–3 paragraphs. Lessons are append-only; never edit prior entries.

### 5. Commit the docs and push

Final docs commit: `docs(phase<N>/<S<n>-<k>>): mark Done + attempt log + lesson L-<N>`. Push to `master` (or open a PR if you'd like review).

---

## Rules of engagement

These apply globally and are restated in [`CLAUDE.md`](CLAUDE.md):

- **Rule 1 — Think Before Coding.** Surface assumptions; don't guess.
- **Rule 2 — Simplicity First.** Minimum code that solves the problem.
- **Rule 3 — Surgical Changes.** Don't "improve" adjacent code, formatting, or comments.
- **Rule 4 — Goal-Driven Execution.** Define success criteria; loop until verified.
- **Rule 9 — Tests verify intent, not just behavior.** Every test must encode WHY the behavior matters.
- **Rule 11 — Match the codebase's conventions, even if you disagree.** snake_case stays snake_case; structlog idioms stay structlog idioms.
- **Rule 12 — Fail loud.** Surface uncertainty, never hide it. "Tests pass" is wrong if you skipped any.

Hardened stories are contracts. Don't re-litigate decisions the validator already settled (L-11). Surface *new* defects (one the validator didn't see) as deviations in the attempt log.

---

## The pre-commit hook stack

The local commit-time firewall is defined in [`.pre-commit-config.yaml`](.pre-commit-config.yaml). Every hook is SHA-pinned. `pre-commit install` arms it; `pre-commit run --files <paths>` runs against staged files.

| Hook | Source | What it catches |
|---|---|---|
| `ruff (legacy alias)` | astral-sh/ruff-pre-commit | Lint errors (E, F, I, B, UP, RUF, …) |
| `ruff format` | astral-sh/ruff-pre-commit | Format drift (Black-compatible) |
| `mypy` | pre-commit/mirrors-mypy | `--strict` type-check |
| `Detect hardcoded secrets` | gitleaks/gitleaks | Secret leaks |
| `check yaml` / `check toml` | pre-commit-hooks | Malformed YAML / TOML |
| `fix end of files` / `trim trailing whitespace` | pre-commit-hooks | File hygiene |
| `forbidden-patterns` | **local** ([`scripts/check_forbidden_patterns.py`](scripts/check_forbidden_patterns.py)) | Executable enforcement of ADR-0008 (no `print()` in `src/`, no bare `yaml.load(` without `Loader=`) + ADR-0012 (no ad-hoc `subprocess.run` outside `src/codegenie/exec/`) |

**Never skip hooks** (`--no-verify`) unless explicitly told to. If a hook fails, fix the root cause. If a pre-commit fails *after* you've already committed, fix the issue and **create a new commit** — never amend (Rule 12: amending after a failed hook risks destroying earlier work).

---

## How to add a probe

Probes are the unit of evidence-gathering. Adding one is the prototypical "extension by addition" change — never edit a central list or the coordinator. Steps:

1. **Pick a sprint / story.** New probes belong in a `phase-architect`-produced `High-level-impl.md` step. If you're inventing a new probe, draft a story under the relevant phase's `stories/` directory and run `phase-story-writer` + `phase-story-validator` against it first.

2. **Implement the probe class** under `src/codegenie/probes/<probe_name>.py`
   (or a `layer_<x>/` subpackage). Match the frozen `Probe` ABC in
   [`src/codegenie/probes/base.py`](src/codegenie/probes/base.py):

   ```python
   from typing import Literal

   from codegenie import exec as _exec
   from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
   from codegenie.probes.registry import register_probe

   @register_probe                                      # or @register_probe(heaviness="medium")
   class MyProbe(Probe):
       name: str = "my_probe"
       layer: Literal["A"] = "A"
       tier: Literal["base", "task_specific"] = "task_specific"
       applies_to_tasks: list[str] = ["*"]              # ["*"] means "all"
       applies_to_languages: list[str] = ["typescript"] # ["*"] means "all"
       requires: list[str] = []                         # other probe names
       declared_inputs: list[str] = ["package.json"]    # globs / special tokens
       timeout_seconds: int = 10

       async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
           # Read evidence; never write conclusions.
           # External binaries: _exec.run_allowlisted(...).
           # Parsed JSON manifests: ctx.parsed_manifest(path).
           ...
   ```

3. **Add the sub-schema** at `src/codegenie/schema/probes/<probe_name>.schema.json`. It MUST set `"additionalProperties": false` at its own root (ADR-0004) and any `warnings[]` / `errors[]` entries MUST match the `WarningId` pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` (ADR-0007). See [`src/codegenie/schema/probes/_subschema_convention.md`](src/codegenie/schema/probes/_subschema_convention.md) for the canonical fragment.

4. **Wire the slice into the envelope** at `src/codegenie/schema/repo_context.schema.json` — declare it optional under `probes.*` (ADR-0010).

5. **Add the unit tests** under `tests/unit/probes/test_<probe_name>.py`. RED first: cover at minimum (a) the happy path, (b) skipped-when-inputs-missing, (c) the schema slice validates, (d) every emitted lifecycle event uses a `Final[str]` constant from `codegenie.logging` (never an inline literal — the literal-drift guard at [`tests/unit/test_no_event_literal_drift.py`](tests/unit/test_no_event_literal_drift.py) will block you otherwise), (e) deterministic re-run produces an identical artifact.

6. **External binaries** — if your probe shells out, route through [`codegenie.exec`](src/codegenie/exec/)'s `run_allowlisted(...)`. **Do not call `subprocess.run` or `asyncio.create_subprocess_exec` directly anywhere outside the `exec/` package**; the `forbidden-patterns` hook will reject the commit. To add a new binary to `ALLOWED_BINARIES`, write a phase-level ADR first (see [Phase 1 ADR 0001](docs/phases/01-context-gather-layer-a-node/ADRs/0001-add-node-to-allowed-binaries.md) as a worked example) — the closed-set negative regression at `tests/unit/test_exec.py::test_allowed_binaries_closed_set_regression` keeps drift honest.

7. **No LLM, ever.** The gather pipeline is deterministic end-to-end. `import-linter` (CI `lint` job + the `fence` job) refuses any module under `src/codegenie/` that imports an LLM SDK. This is ADR-0002 and it's load-bearing.

---

## Probes, parsers, memos — design-pattern cheatsheet

The patterns we lean on hard. If you find yourself fighting the codebase, the pattern is probably one of these:

- **Plugin architecture / Registry pattern.** `@register_probe` makes probes additive. Never edit a central list.
- **Strategy pattern + Open/Closed at the file boundary.** Catalog kinds, event names, sub-schema shapes — adding a new one is one new file or one new constant in a registry module, never a coordinated multi-file rename.
- **Dependency inversion.** The memo kernel knows nothing about *which* paths are memoizable — the allowlist is injected via the constructor (`ParsedManifestMemo(allowlist=...)`).
- **Hexagonal / ports-and-adapters.** `exec.run_allowlisted` is the single port to the OS; everything probe-side stays pure-Python.
- **Newtype / smart constructor.** Domain identifiers (`ProbeName`, `RunId`, …) are typed wrappers, not bare `str` / `int`.
- **Sum types over anaemic strings.** Status discriminators (`status ∈ {"ok", "skipped", "error"}`) are JSON-Schema enums; in Python they're `Literal[...]`, not bare `str`.
- **Functional core, imperative shell.** Parsers + memos are pure; the coordinator + CLI are the imperative shell.

When a refactor temptation arises, ask: "would this turn N edit sites into 1?" If yes, lift to a registry. If it would turn 1 site into 2, you're probably going the wrong way.

---

## Validation gates

Before marking a story Done, all of these MUST be green:

```console
$ ruff check src tests
$ ruff format --check src tests
$ mypy --strict src
$ pytest                            # full unit suite
$ pre-commit run --files <touched>  # all hooks on every touched file
```

CI runs a SHA-pinned job set across four workflow files (see [`README.md` § CI pipeline](README.md#ci-pipeline)). The `fence` job is non-negotiable — it asserts no LLM SDK ever enters the gather-pipeline runtime closure. Story authors who break `fence` have introduced a structural defect, not a flaky test.

**Pre-existing failures.** A small handful of pre-existing CI advisory failures are documented in prior `_attempts/*.md` logs (e.g., the S1-05 `yaml.load(` forbidden-pattern false positive). When you encounter one, confirm against the prior attempt logs and surface it as "pre-existing" in your own log rather than papering over it. Fixing them is its own story.

---

## Filing a PR (when you want review)

We mostly push to `master` directly because every story arrives green; PRs are for changes that span multiple stories or alter load-bearing infrastructure. When you do open one:

- **Title:** mirror the lead commit subject. Convention: `<type>(phase<N>/<S<n>-<k>>): <summary>`.
- **Body:** summary + test plan. Reference the story file by path. Link the attempt log.
- **CI must be fully green** before requesting review.
- **No force-push to `master`.** Use new commits to fix review feedback.

---

## Where to ask questions

There's no chat channel yet; the answer to "how does X work?" is almost always somewhere in `docs/`. The reading order is in the [README](README.md#reading-order-for-the-design-docs). If you find yourself reading more than three docs without an answer, the gap probably wants to be a new ADR or a phase-arch-design clarification — file a story.
