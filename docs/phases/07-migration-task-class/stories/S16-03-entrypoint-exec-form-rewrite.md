# Story S16-03 — Shell-form `ENTRYPOINT`/`CMD` → exec-form deterministic rewrite (gap G5)

**Step:** Step 16 — Refusal taxonomy + recipe transformation contract (G5, M2)
**Status:** Ready
**Effort:** M
**Depends on:** S16-02 (the recipe transformation contract amendment — `DockerfileBaseImageSwapTransform` / `DockerfileMultiStageRefactorTransform` already consume typed gather inputs and can return `RemediationOutcome.PendingHumanReview`; this story adds one more transformation + one more refusal path to that amended contract)

**ADRs honored:** [Phase 7 ADR-0025](../ADRs/0025-migration-refusal-taxonomy.md) (gap **G5**: "the recipe transformation contract applies *deterministic* rewrites where the form is unambiguous; cases that cannot be deterministically rewritten refuse via `RefusedNonDeterministicEntrypoint` rather than guessing"), [Phase 7 ADR-0013](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) (pure-Python `dockerfile-parse`; **NO `docker build` in the recipe**), [Phase 7 ADR-0014](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) (the multi-stage recipe stays synchronous)

## Context

`final-design.md §Amendment A §A.2` gap **G5** names shell-form `ENTRYPOINT`/`CMD`, `sh -c` wrappers, and `npm start` as a migration hazard: **GATHER + REFUSE (non-deterministic)**. The disposition is split — deterministic forms are *rewritten*, non-deterministic forms *refuse*.

Why it matters for distroless. A distroless runtime image has **no `/bin/sh`**. A *shell-form* Docker directive — `CMD node server.js` (note: no JSON array) — is executed by Docker as `/bin/sh -c "node server.js"`. On `cgr.dev/chainguard/node`, `/bin/sh` does not exist, so the container exits immediately with `exec: "/bin/sh": no such file or directory`. The *exec-form* — `CMD ["node", "server.js"]` — runs the binary directly with no shell. **Every** shell-form `ENTRYPOINT`/`CMD` that survives into a distroless runtime stage is a runtime failure waiting to happen.

The fix is a deterministic rewrite — `CMD node server.js` → `CMD ["node", "server.js"]` — applied **only** where the recipe can *prove* the rewrite preserves semantics. The cases it cannot prove safe:

- **env-substituted `CMD`** — `CMD $START_CMD` or `CMD node ${ENTRY}`. Docker's shell-form does variable substitution; exec-form does not. The recipe does not know the value of `$START_CMD` at transform time — splitting it into a JSON array would freeze a substitution the runtime expects to be dynamic. Refuse.
- **`npm start`** — `CMD npm start` resolves to whatever `scripts.start` says in `package.json`, which may itself be a shell pipeline. The exec-form `CMD ["npm", "start"]` is *not* equivalent if `scripts.start` relies on shell features (and `npm` itself spawns a shell to run the script). Refuse — the safe rewrite is to inline `scripts.start`'s actual command, but only if *that* is itself deterministic, which is a deeper analysis than G5's scope.
- **`sh -c "..."` with shell features** — `CMD ["sh", "-c", "node a.js && node b.js"]` (already JSON array, but the payload is a shell program using `&&`). Splitting this is rewriting a shell program, not a command. Refuse.

Each refusal emits `RefusedNonDeterministicEntrypoint` (from the **S16-01** taxonomy) carrying the directive (`ENTRYPOINT` | `CMD`), the raw form, and the source location. The deterministic rewrite and the refusal both live inside the recipe's `apply()` — this story extends the **S16-02**-amended transformation contract with one more transformation and one more refusal trigger. An already-exec-form directive is left **untouched** (idempotence).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Amendment A §22` — the refusal taxonomy; `RefusedNonDeterministicEntrypoint` is the gap-G5 variant.
  - `../phase-arch-design.md §Component design §11` — `DockerfileBaseImageSwapTransform`'s multi-stage runner adjustments already include "conversion of shell-form `ENTRYPOINT` to exec-form" — this story makes that conversion *correct and refusal-aware* rather than naive.
  - `../phase-arch-design.md §Edge cases` — exotic Dockerfile syntax → `dockerfile_parse_failed`; the entrypoint rewrite inherits the same parse-failure path.
- **Phase ADRs:**
  - [`../ADRs/0025-migration-refusal-taxonomy.md`](../ADRs/0025-migration-refusal-taxonomy.md) — §Decision "Gap G5 — shell-form `ENTRYPOINT`/`CMD`": "the recipe rewrites deterministic shell-form `CMD`/`ENTRYPOINT` and refuses the rest." `RefusedNonDeterministicEntrypoint` is the variant. §Consequences names it closing gap G5.
  - [`../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md`](../ADRs/0013-dockerfile-recipe-engine-dockerfile-parse.md) — `dockerfile-parse` is the recipe engine; the directive structure (`instruction`, `value`, `startline`) is what the rewrite reads.
  - [`../ADRs/0014-multi-stage-refactor-recipe-synchronous.md`](../ADRs/0014-multi-stage-refactor-recipe-synchronous.md) — synchronous; the AST-walk fence stays green.
- **Source design:**
  - `../final-design.md §Amendment A §A.2` gap G5 row (GATHER + REFUSE, non-deterministic), §A.3 departure #2 (the recipe can refuse).
- **Existing code:**
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` (post-S16-02) — the recipe this story extends; S10-01 already does a naive shell-form→exec-form conversion in its multi-stage runner adjustments (S10-01 AC-7) — this story *replaces* that naive conversion with the deterministic-or-refuse logic.
  - `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` (post-S16-02) — S10-02 AC-9 also rewrites shell-form `CMD`; same replacement applies.
  - `src/codegenie/transforms/outcomes.py` (post-S16-01) — `RefusedNonDeterministicEntrypoint`, `RefusalSourceLocation`, `PendingHumanReview`.
  - `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` + `multi-stage-refactor.diff` — the goldens whose `CMD`/`ENTRYPOINT` lines this story may regenerate.

## Goal

Extend the S16-02-amended recipe transformation contract with the gap-G5 `ENTRYPOINT`/`CMD` rewrite. Land a pure, independently-tested rewrite function — `rewrite_entrypoint_directive(instruction, value, startline, dockerfile_path) -> EntrypointRewrite` — that classifies a Dockerfile `ENTRYPOINT`/`CMD` directive into exactly one of three outcomes:

1. **deterministic rewrite** — shell-form with a provably-safe argv (`CMD node server.js` → `CMD ["node", "server.js"]`);
2. **refusal** — non-deterministic form (`RefusedNonDeterministicEntrypoint`): env-substituted argv, `npm start`, or `sh -c "..."` with shell features;
3. **unchanged** — already exec-form (`CMD ["node", "server.js"]` — JSON array, no shell-feature payload).

Wire this into both recipes' `apply()`: for each `ENTRYPOINT`/`CMD` in the runtime stage, apply the classification; a refusal short-circuits `apply()` to `PendingHumanReview(refusal=RefusedNonDeterministicEntrypoint(...))`; a deterministic rewrite contributes to the diff; an already-exec-form directive contributes nothing. This *replaces* the naive shell-form→exec-form conversion S10-01 AC-7 / S10-02 AC-9 shipped — those naive conversions guessed; this one proves or refuses.

## Acceptance criteria

### The classification function

- [ ] **AC-1 — `rewrite_entrypoint_directive` is a pure function.** A module-level pure function (no I/O, no `dockerfile-parse` instantiation inside it — it takes the already-parsed directive fields) classifies one `ENTRYPOINT`/`CMD` directive. Signature, e.g.: `rewrite_entrypoint_directive(*, directive: Literal["ENTRYPOINT", "CMD"], raw_value: str, instruction_index: int, dockerfile_path: str) -> EntrypointRewrite`. It is tested in isolation, independently of any recipe.
- [ ] **AC-2 — `EntrypointRewrite` is a three-variant sum type.** The return type is a closed discriminated union: `ExecFormRewrite` (carries the rewritten exec-form text), `EntrypointRefusal` (carries a `RefusedNonDeterministicEntrypoint`), `EntrypointUnchanged` (already exec-form, no change). `match`/`assert_never` exhaustiveness; mirrors the `outcomes.py` discriminated-union style.
- [ ] **AC-3 — Deterministic shell-form rewrite.** `rewrite_entrypoint_directive(directive="CMD", raw_value="node server.js", ...)` returns `ExecFormRewrite` whose rewritten text is exactly `CMD ["node", "server.js"]`. Parametrized over: `CMD node server.js`, `ENTRYPOINT node /app/index.js`, `CMD node --enable-source-maps server.js` (flags preserved as separate argv elements), `CMD ./bin/start` (a bare executable). Each rewrite is byte-exact and the argv split is shell-word-correct.
- [ ] **AC-4 — Env-substituted `CMD` refused.** `rewrite_entrypoint_directive(directive="CMD", raw_value="$START_CMD", ...)` and `raw_value="node ${ENTRY_POINT}"` and `raw_value="node $APP_ENTRY"` each return `EntrypointRefusal` carrying `RefusedNonDeterministicEntrypoint`. The refusal's `raw_form` is the original directive text, `directive` is `"CMD"`, and `source` names the Dockerfile + the instruction index. Test pins all three substitution syntaxes (`$VAR`, `${VAR}`, `$VAR` mid-argv), each with a docstring naming why exec-form would freeze a runtime-dynamic value.
- [ ] **AC-5 — `npm start` refused.** `rewrite_entrypoint_directive(directive="CMD", raw_value="npm start", ...)` returns `EntrypointRefusal`. Parametrized to also cover `CMD npm run start`, `CMD yarn start`, `ENTRYPOINT npm start` — every `npm`/`yarn` script-runner invocation refuses (the script's body is in `package.json` and may itself be a shell pipeline; G5's scope does not chase it). Docstring names why `CMD ["npm", "start"]` is not equivalent.
- [ ] **AC-6 — `sh -c "..."` with shell features refused.** `rewrite_entrypoint_directive(directive="CMD", raw_value='sh -c "node a.js && node b.js"', ...)` returns `EntrypointRefusal` — the `sh -c` payload uses `&&`, a shell feature. Parametrized to also cover a shell-form `CMD node a.js && node b.js` (shell-form, `&&` operator), `CMD node a.js | tee log` (pipe), `CMD node a.js > /tmp/out` (redirect). Any shell metacharacter (`&&`, `||`, `|`, `;`, `>`, `<`, `` ` ``, `$(`) in the would-be argv triggers refusal.
- [ ] **AC-7 — Already-exec-form left unchanged.** `rewrite_entrypoint_directive(directive="CMD", raw_value='["node", "server.js"]', ...)` returns `EntrypointUnchanged`. Parametrized over `ENTRYPOINT ["node", "/app/index.js"]` and the dumb-init wrapper `ENTRYPOINT ["dumb-init", "--", "node", "server.js"]`. An exec-form directive contributes nothing to the diff — applying the recipe to its own output does not re-rewrite (idempotence).
- [ ] **AC-8 — `sh -c` with NO shell features rewritten, not refused.** `rewrite_entrypoint_directive(directive="CMD", raw_value='["sh", "-c", "node server.js"]', ...)` — exec-form `sh -c` wrapping a *plain* command with no shell metacharacters — returns `ExecFormRewrite` rewriting to `CMD ["node", "server.js"]` (the `sh -c` wrapper is removable when its payload is a single shell-feature-free command). This is the one case where `sh -c` is *un*wrapped rather than refused; pin it with a docstring distinguishing it from AC-6.

### Wiring into the recipes

- [ ] **AC-9 — Both recipes route `ENTRYPOINT`/`CMD` through the classifier.** `DockerfileBaseImageSwapTransform.apply()` and `DockerfileMultiStageRefactorTransform.apply()` call `rewrite_entrypoint_directive` for every `ENTRYPOINT`/`CMD` directive in the runtime stage. The naive shell-form→exec-form conversion S10-01 AC-7 / S10-02 AC-9 shipped is **removed** — superseded by this classifier (state this supersession in the recipe module docstring).
- [ ] **AC-10 — A refusal short-circuits `apply()` to `PendingHumanReview`.** When `rewrite_entrypoint_directive` returns `EntrypointRefusal` for any runtime-stage directive, `apply()` returns `RemediationOutcome.PendingHumanReview(refusal=<the RefusedNonDeterministicEntrypoint>)` — no diff. Consistent with S16-02's refuse-first control flow: the entrypoint refusal is checked alongside the opaque-secret / unclassified-native-module refusals.
- [ ] **AC-11 — A deterministic rewrite contributes to the diff.** When every runtime-stage directive classifies as `ExecFormRewrite` or `EntrypointUnchanged`, `apply()` returns a `TransformOutcome.Applied(diff)` whose diff includes the shell-form→exec-form line change for each `ExecFormRewrite`. An end-to-end test asserts a fixture Dockerfile with `CMD node server.js` produces a diff line `-CMD node server.js` / `+CMD ["node", "server.js"]`.
- [ ] **AC-12 — Idempotence.** Applying either recipe to its own output does not re-rewrite the already-exec-form `CMD`/`ENTRYPOINT` — a second `apply()` produces no entrypoint diff line. Test: `tests/unit/transforms/recipes/test_entrypoint_rewrite.py::test_exec_form_idempotent`.
- [ ] **AC-13 — Multiple directives: refusal wins over rewrite.** A Dockerfile with both a deterministically-rewritable `ENTRYPOINT node init.js` AND a non-deterministic `CMD npm start` refuses (the whole `apply()` returns `PendingHumanReview`) — a partial diff that rewrites one directive and silently leaves the other shell-form would ship a half-broken image. Test pins this with a docstring: refusal is all-or-nothing per `apply()`.

### Source-location accuracy

- [ ] **AC-14 — Refusal names the exact directive.** For every refusal path, `RefusedNonDeterministicEntrypoint.source.file_path` is the Dockerfile path and `.source.index` is the 0-based instruction index of the offending `ENTRYPOINT`/`CMD` (mapped from `dockerfile-parse`'s `startline`). `.directive` is `"ENTRYPOINT"` or `"CMD"` correctly; `.raw_form` is the original directive text verbatim. Test asserts the exact `index` against the known fixture line.

### Invariants preserved

- [ ] **AC-15 — No `docker build`.** The S10-01 / S10-02 AST-walk fences (`no_docker_build`) stay green — the entrypoint rewrite is pure string/AST work; no subprocess.
- [ ] **AC-16 — Synchronous shape preserved.** The S10-02 `no_asyncio_gather` AST-walk fence stays green (ADR-0014).
- [ ] **AC-17 — Goldens regenerated where the entrypoint line changes.** If a S10-01 / S10-02 golden-fixture Dockerfile carries a shell-form `CMD`/`ENTRYPOINT`, the golden diff is regenerated (hand-reviewed) to reflect the corrected exec-form rewrite. If a golden fixture's directive was already exec-form, its golden is byte-equal — no change.

### Gates

- [ ] **AC-18** — `mypy --strict` clean on the touched recipe modules, the new classifier module, and `src/`.
- [ ] **AC-19** — `ruff check` + `ruff format --check` clean on every touched file.
- [ ] **AC-20** — `make lint-imports` green; `make check` end-to-end green; Phase 3–6.5 regression suite passes; `bench/vuln-remediation/` cassette replay byte-equal.

## Implementation outline

1. **Land the classifier module** — `plugins/distroless-migration--node--npm/recipes/_entrypoint_rewrite.py`. Define the three-variant `EntrypointRewrite` sum type (`ExecFormRewrite`, `EntrypointRefusal`, `EntrypointUnchanged`) and the pure `rewrite_entrypoint_directive(...)` function.
2. **Classification logic** — inside `rewrite_entrypoint_directive`:
   - If `raw_value` is already a JSON array (exec-form): inspect the argv. If it is `["sh", "-c", "<plain command>"]` with no shell metacharacters in the payload → `ExecFormRewrite` unwrapping it (AC-8). Otherwise → `EntrypointUnchanged` (AC-7).
   - If `raw_value` is shell-form: check for env substitution (`$VAR` / `${VAR}` via a `Final` regex) → refuse (AC-4). Check for `npm`/`yarn` script-runner argv[0] → refuse (AC-5). Check for shell metacharacters (`&&`, `||`, `|`, `;`, `>`, `<`, `` ` ``, `$(`) → refuse (AC-6). Otherwise, `shlex.split` the value into argv and emit `ExecFormRewrite` with the JSON-array text (AC-3).
3. **Build the refusal** — `EntrypointRefusal` wraps a `RefusedNonDeterministicEntrypoint` (S16-01) carrying `directive`, `raw_form`, and a `RefusalSourceLocation(file_path, index)`.
4. **Wire into both recipes** — in `dockerfile_base_image_swap.py` and `dockerfile_multi_stage.py`, replace the naive S10-01 AC-7 / S10-02 AC-9 shell-form→exec-form conversion with a loop over runtime-stage `ENTRYPOINT`/`CMD` directives calling `rewrite_entrypoint_directive`. Collect rewrites; if any is `EntrypointRefusal`, short-circuit `apply()` to `PendingHumanReview` (AC-10, AC-13). Otherwise apply the `ExecFormRewrite` text edits and continue to the diff (AC-11).
5. **Module-level `Final` constants** — the env-substitution regex, the script-runner argv[0] set (`{"npm", "yarn"}` — `pnpm` too if S14-02's ecosystem set includes it), and the shell-metacharacter set. Each iterated, not branched ad-hoc.
6. **Fixtures + tests** — `tests/fixtures/recipes/entrypoint/` with one Dockerfile per case (deterministic, env-substituted, `npm start`, `sh -c` shell-feature, already-exec-form, `sh -c` plain, multi-directive). Paired unit tests; the classifier's own unit tests are red-first.
7. **Regenerate goldens** — any S10-01 / S10-02 golden whose fixture carried a shell-form directive (AC-17); hand-review.
8. **Run the fences** — `no_docker_build`, `no_asyncio_gather` stay green.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/recipes/test_entrypoint_rewrite.py`

```python
from __future__ import annotations

import pytest


def _rewrite(directive: str, raw_value: str):
    from plugins.distroless_migration__node__npm.recipes._entrypoint_rewrite import (
        rewrite_entrypoint_directive,
    )

    return rewrite_entrypoint_directive(
        directive=directive,
        raw_value=raw_value,
        instruction_index=7,
        dockerfile_path="Dockerfile",
    )


@pytest.mark.parametrize(
    ("raw", "expected_text"),
    [
        ("node server.js", 'CMD ["node", "server.js"]'),
        ("node --enable-source-maps server.js",
         'CMD ["node", "--enable-source-maps", "server.js"]'),
        ("./bin/start", 'CMD ["./bin/start"]'),
    ],
)
def test_deterministic_shell_form_rewritten(raw, expected_text):
    """G5 / ADR-0025: a shell-form CMD with a provably-safe argv is rewritten
    to exec-form — distroless has no /bin/sh, so shell-form CMD ENOENTs."""
    from plugins.distroless_migration__node__npm.recipes._entrypoint_rewrite import (
        ExecFormRewrite,
    )

    result = _rewrite("CMD", raw)
    assert isinstance(result, ExecFormRewrite)
    assert result.rewritten_text == expected_text


@pytest.mark.parametrize("raw", ["$START_CMD", "node ${ENTRY}", "node $APP_ENTRY"])
def test_env_substituted_cmd_refused(raw):
    """G5 / ADR-0025: env-substituted CMD cannot be rewritten — exec-form does
    no variable substitution, so splitting it would freeze a runtime-dynamic
    value. Refuse with RefusedNonDeterministicEntrypoint, do not guess."""
    from codegenie.transforms import RefusedNonDeterministicEntrypoint
    from plugins.distroless_migration__node__npm.recipes._entrypoint_rewrite import (
        EntrypointRefusal,
    )

    result = _rewrite("CMD", raw)
    assert isinstance(result, EntrypointRefusal)
    assert isinstance(result.refusal, RefusedNonDeterministicEntrypoint)
    assert result.refusal.directive == "CMD"
    assert result.refusal.raw_form == raw
    assert result.refusal.source.index == 7


def test_npm_start_refused():
    """G5 / ADR-0025: `npm start` resolves to scripts.start in package.json,
    which may itself be a shell pipeline — CMD ["npm","start"] is not
    equivalent. Refuse; inlining scripts.start is out of G5 scope."""
    from plugins.distroless_migration__node__npm.recipes._entrypoint_rewrite import (
        EntrypointRefusal,
    )

    assert isinstance(_rewrite("CMD", "npm start"), EntrypointRefusal)


def test_sh_c_with_shell_features_refused():
    """G5 / ADR-0025: `sh -c "a && b"` is a shell program using &&, not a
    command — splitting it is rewriting a program. Refuse."""
    from plugins.distroless_migration__node__npm.recipes._entrypoint_rewrite import (
        EntrypointRefusal,
    )

    result = _rewrite("CMD", 'sh -c "node a.js && node b.js"')
    assert isinstance(result, EntrypointRefusal)


def test_already_exec_form_unchanged():
    """G5: an already-exec-form CMD is left untouched — the rewrite is
    idempotent; a second apply() must not re-rewrite it."""
    from plugins.distroless_migration__node__npm.recipes._entrypoint_rewrite import (
        EntrypointUnchanged,
    )

    result = _rewrite("CMD", '["node", "server.js"]')
    assert isinstance(result, EntrypointUnchanged)
```

State why it fails: `ModuleNotFoundError` — `plugins/distroless-migration--node--npm/recipes/_entrypoint_rewrite.py` and the `ExecFormRewrite` / `EntrypointRefusal` / `EntrypointUnchanged` / `rewrite_entrypoint_directive` symbols do not exist.

### Green — minimal pass

- Land `_entrypoint_rewrite.py` with the three-variant `EntrypointRewrite` sum type and `rewrite_entrypoint_directive`.
- Implement the classification: exec-form detection (JSON-array parse), `sh -c` plain-payload unwrap (AC-8), env-substitution detection, script-runner detection, shell-metacharacter detection, and the `shlex.split`-based deterministic rewrite.
- Wire the classifier into both recipes' `apply()`, replacing the naive S10-01/S10-02 conversions; refuse-first short-circuit.
- Add the fixtures + paired tests; regenerate any affected golden.

### Refactor

- Pin the env-substitution regex, the script-runner argv[0] set, and the shell-metacharacter set as module-level `Final` constants — each with a one-line comment naming the case it guards.
- Confirm the classifier is genuinely pure: an AST-walk or a focused test asserts `rewrite_entrypoint_directive` does no I/O and instantiates no `DockerfileParser` (it takes pre-parsed fields).
- Confirm `match`/`assert_never` over `EntrypointRewrite` is exhaustive — temporarily comment one `case` arm, confirm `mypy --strict` flags it, restore.
- Confirm the `no_docker_build` and `no_asyncio_gather` fences are green after the wiring edits.
- Add a docstring to `_entrypoint_rewrite.py` naming gap G5, ADR-0025, and the deterministic-or-refuse contract; add a recipe-module-docstring line noting the naive S10-01 AC-7 / S10-02 AC-9 conversion is superseded by this classifier.

## Files to touch

| Path | Why |
|---|---|
| `plugins/distroless-migration--node--npm/recipes/_entrypoint_rewrite.py` | NEW — pure `rewrite_entrypoint_directive` + the `EntrypointRewrite` three-variant sum type (`ExecFormRewrite` / `EntrypointRefusal` / `EntrypointUnchanged`). Gap G5 / ADR-0025. |
| `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` | Replace the naive S10-01 AC-7 shell-form→exec-form conversion with a loop over `rewrite_entrypoint_directive`; refuse-first short-circuit. |
| `plugins/distroless-migration--node--npm/recipes/dockerfile_multi_stage.py` | Replace the naive S10-02 AC-9 shell-form `CMD` rewrite with the classifier; refuse-first short-circuit. |
| `tests/fixtures/recipes/entrypoint/deterministic/Dockerfile` | NEW — `CMD node server.js` (deterministic rewrite). |
| `tests/fixtures/recipes/entrypoint/env-substituted/Dockerfile` | NEW — `CMD node ${ENTRY}` (refusal). |
| `tests/fixtures/recipes/entrypoint/npm-start/Dockerfile` | NEW — `CMD npm start` (refusal). |
| `tests/fixtures/recipes/entrypoint/sh-c-shell-features/Dockerfile` | NEW — `CMD sh -c "a && b"` (refusal). |
| `tests/fixtures/recipes/entrypoint/already-exec-form/Dockerfile` | NEW — `CMD ["node", "server.js"]` (unchanged). |
| `tests/fixtures/recipes/entrypoint/multi-directive/Dockerfile` | NEW — `ENTRYPOINT node init.js` + `CMD npm start` (refusal wins — AC-13). |
| `tests/unit/transforms/recipes/test_entrypoint_rewrite.py` | NEW — anchors TDD red; AC-1..AC-8 classifier suite + AC-12 idempotence. |
| `tests/unit/transforms/recipes/test_dockerfile_base_image_swap.py` | Extend — AC-9, AC-10, AC-11, AC-13, AC-14 (recipe-level wiring). |
| `tests/unit/transforms/recipes/test_dockerfile_multi_stage.py` | Extend — AC-9, AC-10 (recipe-level wiring for the multi-stage recipe). |
| `tests/golden/dockerfile-diffs/alpine-to-chainguard.diff` | Regenerate ONLY IF the S10-01 fixture carried a shell-form directive (AC-17); hand-reviewed. |
| `tests/golden/dockerfile-diffs/multi-stage-refactor.diff` | Regenerate ONLY IF the S10-02 fixture carried a shell-form directive (AC-17); hand-reviewed. |

## Out of scope

- **The refusal taxonomy types** — `RefusedNonDeterministicEntrypoint`, `RefusalSourceLocation`, `PendingHumanReview` are landed by **S16-01**. This story *constructs* `RefusedNonDeterministicEntrypoint`.
- **The gather-input plumbing** — the three slices (`SecretPatternSlice`, `TargetImageContentSlice`, `native_modules`) and the opaque-secret / unclassified-native-module refusal paths are **S16-02**. This story adds the *entrypoint* refusal path on top of that amended contract.
- **Inlining `scripts.start` from `package.json`** — `CMD npm start` refuses; chasing `package.json`'s `scripts.start` to a deterministic command is a deeper analysis explicitly outside gap G5's scope. A future ADR could ship it; this story refuses.
- **`HEALTHCHECK` directive rewriting** — healthcheck shell-out is gap G6 (`ContainerProbeCompatProbe`, ADR-0022, Step 15), not G5. This story only touches `ENTRYPOINT`/`CMD`.
- **`RUN`-line shell rewriting** — the multi-stage shell-relocation is S10-02's territory; this story does not touch `RUN`.
- **`docker build` / `docker buildx`** — `DistrolessBuildGate` (S10-04), unchanged.

## Notes for the implementer

- **Deterministic-or-refuse is the whole point of gap G5.** ADR-0025 §Decision: "applies *deterministic* rewrites where the form is unambiguous; cases that cannot be deterministically rewritten refuse rather than guessing." The classifier must never guess. If you cannot *prove* the exec-form preserves semantics, refuse. A guessed rewrite that is subtly wrong ships a broken image — the exact failure mode Amendment A exists to prevent (Rule 12: fail loud).
- **This story supersedes the naive S10-01 AC-7 / S10-02 AC-9 conversion.** Those ACs shipped a naive shell-form→exec-form conversion (e.g. `ENTRYPOINT npm start` → `ENTRYPOINT ["npm", "start"]`). That conversion is *wrong* for `npm start` (AC-5) and for env-substituted forms (AC-4) — it freezes a runtime-dynamic value or a shell pipeline into a static argv. Remove the naive conversion; route every directive through `rewrite_entrypoint_directive`. State the supersession in the recipe module docstring so a future reader does not "restore" the naive path.
- **`shlex.split` is the argv splitter — but only after the shell-feature gate.** Use `shlex.split(raw_value)` to turn `node --enable-source-maps server.js` into `["node", "--enable-source-maps", "server.js"]`. But `shlex.split` will *also* happily split `node a.js && node b.js` into `["node", "a.js", "&&", "node", "b.js"]` — a nonsense argv. So the shell-metacharacter gate (AC-6) must run *before* `shlex.split`: if any metacharacter is present, refuse; only then split. Order is load-bearing.
- **Env substitution: `$VAR` and `${VAR}` both.** Docker's shell-form does `$VAR` and `${VAR}` substitution. The detection regex must catch both — `\$\{?\w+\}?` is the shape. Test all three syntaxes (AC-4). An exec-form `CMD ["node", "$ENTRY"]` does NOT substitute — but if a directive is already exec-form, you are in the `EntrypointUnchanged` path anyway and do not rewrite it; the env-substitution check only matters for shell-form input.
- **`sh -c` has two faces — AC-6 vs AC-8.** `CMD sh -c "node a && node b"` and `CMD ["sh", "-c", "node a && node b"]` both refuse (shell-feature payload). But `CMD ["sh", "-c", "node server.js"]` — exec-form `sh -c` wrapping a *plain* single command — is *unwrappable* to `CMD ["node", "server.js"]` (AC-8). The distinguishing test is: parse the `sh -c` payload; if it contains a shell metacharacter, refuse; if it is a plain command, unwrap and rewrite. Do not blanket-refuse all `sh -c` — that would leave removable shell wrappers in place.
- **Refusal is all-or-nothing per `apply()` (AC-13).** A Dockerfile can have both an `ENTRYPOINT` and a `CMD`. If one is deterministically rewritable and the other refuses, the *whole* `apply()` refuses — do not emit a diff that rewrites one directive and silently leaves the other shell-form. A half-rewritten Dockerfile still `ENOENT`s on the un-rewritten directive. Collect all directive classifications first; if *any* is `EntrypointRefusal`, return `PendingHumanReview` with that refusal (the first one, deterministically ordered by instruction index).
- **The classifier is pure; the recipe is the impure shell.** `rewrite_entrypoint_directive` takes pre-parsed directive fields (string `raw_value`, int `instruction_index`) and returns a value — no `dockerfile-parse` instantiation, no I/O. The recipe's `apply()` does the parsing and feeds the classifier. This is the functional-core / imperative-shell discipline the codebase enforces (CLAUDE.md). It also makes AC-1..AC-8 testable without constructing a whole recipe.
- **Source-location accuracy (AC-14).** `dockerfile-parse`'s `structure` entries carry `startline`; the `RefusedNonDeterministicEntrypoint.source.index` must be the correct 0-based instruction index of the offending `ENTRYPOINT`/`CMD`. A wrong index points the human reviewer at innocent code — worse than no index. Test the exact value against the known fixture line.
- **`EntrypointRewrite` is a closed three-variant sum type.** Mirror the `outcomes.py` discriminated-union style (`ConfigDict(frozen=True, extra="forbid")`, `kind` literal, `Annotated[..., Field(discriminator="kind")]`) — or, if the module is plugin-internal and does not need Pydantic round-tripping, a frozen `@dataclass` per variant with a `match`-able union is acceptable; pick the style the sibling recipe-internal helpers use and stay with it (Rule 11). `match`/`assert_never` exhaustiveness either way.
- **No `docker build`, synchronous.** AC-15 / AC-16. The entrypoint rewrite is pure string and AST work — no subprocess, no `async`. The S10-01 / S10-02 fences are mechanical; they will refuse a regression.
- **Goldens: regenerate only what actually changes (AC-17).** If a S10-01 / S10-02 golden fixture's `CMD`/`ENTRYPOINT` was already exec-form, this story changes nothing for it — its golden stays byte-equal. Only regenerate a golden whose fixture carried a *shell-form* directive that this classifier now rewrites correctly (or whose naive S10-01/S10-02 rewrite this story corrects). Hand-review every regenerated golden — a golden change is a contract change.
