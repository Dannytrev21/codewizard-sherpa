# Validation report: S2-04 — Subprocess allowlist chokepoint

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S2-04-exec-allowlist.md`](../S2-04-exec-allowlist.md)

## Summary

S2-04 implements ADR-0012's subprocess-allowlist chokepoint at `src/codegenie/exec.py` — the only path from `codegenie` source to an external binary, ever. The original story was substantively correct (six invariants, correct file path, working error hierarchy) but its TDD plan had four mutation-survivable holes that would have let an obviously-wrong implementation pass executor validation: the "before spawn" claim was not pinned with a spy, env-strip was tested at the helper boundary rather than the chokepoint boundary, the timeout test depended on flaky network behavior, and `stdin=DEVNULL` had no test at all. Additionally, the story silently narrowed two ADR-0012 invariants (cwd-under-repo-root → caller responsibility; `env_extra: dict = {}` → `| None = None`). Three critics returned 25 findings; the validator applied edits in place that strengthen 8 existing ACs, add 5 new ACs (AC-10–AC-14), and rewrite the TDD plan from six thin tests into ten mutation-resistant tests built around spying `asyncio.create_subprocess_exec` at the chokepoint boundary. The two ADR deviations are surfaced for a follow-up amendment but do not block the executor; the wrapper as specified is internally consistent and Phase-0-callsite-safe.

## Findings by critic

### Coverage critic

10 findings:

- **F1 (harden)** — Goal claim "before spawning anything" not pinned by test (no spy on `create_subprocess_exec`). Spawn-then-kill mutant passes.
- **F2 (harden)** — SIGKILL `1.5 × timeout_s` grace timing not observable; mutant with immediate-SIGKILL passes.
- **F3 (harden)** — `ProbeTimeoutError` elapsed-ms message asserted nowhere; bare `raise ProbeTimeoutError("timeout")` passes.
- **F4 (block)** — AC-4(b) "caller responsibility" contradicts ADR-0012 §Decision and arch §Edge cases row 4.
- **F5 (harden)** — Env-strip AC tests `_filter_env` directly, not child-process reality; `env=os.environ.copy()` mutant passes.
- **F6 (harden)** — Negative-space gaps: empty argv, non-string argv, `env_extra` collision/sensitive-key behavior.
- **F7 (harden)** — Weakref table never asserted to clear on exception.
- **F8 (harden)** — Absolute-path `argv[0]` behavior unspecified (`["/usr/bin/git", ...]`).
- **F9 (nit)** — Large stdout/stderr behavior unspecified.
- **F10 (nit)** — Out-of-scope healthy, no smell.

### Test-Quality critic

9 findings:

- **F1 (block)** — `test_disallowed_binary_rejected_before_spawn` does not install the spy its docstring claims; spawn-then-kill mutant survives.
- **F2 (block)** — `test_env_strips_secret_shaped_vars` tests the helper, not the chokepoint; bypass mutant survives.
- **F3 (block)** — Timeout test depends on network behavior at `10.255.255.1`; flaky; doesn't verify SIGTERM-then-SIGKILL order, 1.5× ceiling, or `elapsed_ms`.
- **F4 (block)** — No test pins `stdin=DEVNULL` or `shell=False` kwargs.
- **F5 (harden)** — No test pins `ProcessResult` frozen-dataclass invariants.
- **F6 (harden)** — No test pins the mutable-default footgun via `inspect.signature`.
- **F7 (harden)** — `ToolMissingError` test under-asserts the message; bare error passes.
- **F8 (harden)** — `_RUNNING_PROCS` weakref table unpinned; removing it entirely passes all tests.
- **F9 (NEEDS RESEARCH → resolved inline)** — Env-strip is a property. `hypothesis` is not a dev dep. Resolved within the critic's own report: use an allowlist-keys-set assertion (`set(captured_env.keys()) <= {"PATH","HOME","LANG","LC_ALL"} ∪ env_extra.keys()`) which subsumes the property without adding a dependency. No external research consulted.

### Consistency critic

6 findings:

- **F1 (block)** — AC-4(b) explicitly offloads under-repo-root check; contradicts ADR-0012 §Decision bullet 5 and arch line 537 + Edge cases row 4. Same finding as Coverage F4.
- **F2 (harden)** — `env_extra: dict[str, str] | None = None` deviates from arch line 534 and ADR-0012 line 26 (both show `= {}`). Arch line 271 names this a "stable contract"; deviation needs to land in writing.
- **F3 (nit)** — `stdin=DEVNULL` "unless explicitly overridden" reserved by ADR-0012; story narrows to no-override. Acceptable in Phase 0 (YAGNI), should be acknowledged.
- **F4 (informational)** — All path references resolve; `errors.py` exports verified; `pytest-asyncio` in `dev` extra confirmed via `pyproject.toml`.
- **F5 (informational)** — All seven CLAUDE.md load-bearing commitments traceable; no violations.
- **F6 (informational)** — All ACs trace to goal; no orphans.

## Research briefs

**None.** Stage 3 was skipped — the only `NEEDS RESEARCH` tag (Test-Quality F9) was resolved within the critic's own report by recommending an allowlist-keys-set structural assertion in place of adopting `hypothesis`. No external lookups required.

## Conflict resolutions

**Coverage F4 ≡ Consistency F1** (the cwd-under-repo-root deviation): both critics flagged the same architectural contradiction independently. Per [`editor.md`](../../../.claude/skills/phase-story-validator/references/editor.md) Step 2, **Consistency wins over Coverage**. Consistency offered two reconciliations: (a) add `analyzed_repo_root: Path` to the wrapper signature and have the wrapper enforce; (b) amend ADR-0012 and arch to read "caller responsibility."

The validator picked **(b)** for these reasons (recorded for the next reader):

1. Adding a wrapper parameter for Phase 0's single callsite (`RepoSnapshot.git_commit`) is YAGNI; the CLI already resolves and validates the repo root upstream.
2. Phase 1+ probes will resolve their cwd via the same upstream path (`Path.resolve(strict=True)` on inputs), so the caller-responsibility split is structurally consistent across phases.
3. Choice (a) would require a coordinated edit to the arch, ADR-0012, AND the story signature — choice (b) requires an arch + ADR amendment but leaves the story signature stable.

The choice is surfaced in the story's `Validation notes` block as a follow-up ADR-amendment action item so the deviation is not silent. The validator did **not** auto-amend the ADR (out of scope per `editor.md` §"What Stage 4 must NOT do" — surgical changes only, no fold-in of adjacent improvements).

## Edits applied

### Edit 1 — `Validation notes` block added under the story header
- **Source:** validator convention
- **What:** New `## Validation notes` block recording validation date, verdict, finding totals, the two surfaced ADR-amendment action items, and a list of changes applied.
- **Rationale:** Breadcrumb for the next reader; per `editor.md` template.

### Edit 2 — AC-3 (`run_allowlisted` signature) breadcrumb added
- **Source:** Consistency F2
- **Before:** signature spec with no note about the arch/ADR deviation
- **After:** trailing parenthetical: *"this signature differs from arch line 534 / ADR-0012 line 26 which both show the literal `{}` mutable default. The deviation is the safer Python form; see Validation notes for the ADR-amendment action item."*
- **Rationale:** Stable-contract deviation per arch line 271 must land in writing.

### Edit 3 — AC-4(a) hardened to pin "no spawn"
- **Source:** Coverage F1 + Test-Quality F1
- **Before:** `DisallowedSubprocessError raised **before** any process spawn` — no test mechanism.
- **After:** explicit spy pattern (`mock.AsyncMock(side_effect=AssertionError("must not spawn"))`) and `spy.assert_not_awaited()`.
- **Rationale:** Spawn-then-kill mutant is the load-bearing failure mode (the chokepoint is "no disallowed binary ever runs," not "no disallowed binary completes"). Mutation-resistant pin.

### Edit 4 — AC-4(b) reworded; the deviation is now explicit
- **Source:** Coverage F4 + Consistency F1
- **Before:** "must not be a symlink that escapes the analyzed-repo root (caller responsibility ...)"
- **After:** *"Under-repo-root enforcement is the caller's responsibility, not the wrapper's, in Phase 0 — see Validation notes for the ADR-amendment action item that reconciles this with ADR-0012 §Decision bullet 5 and arch line 537."*
- **Rationale:** Deviation surfaced rather than hidden.

### Edit 5 — AC-4(c)+(d) hardened with kwarg-spy test
- **Source:** Test-Quality F4
- **Before:** `shell=False explicit; stdin=DEVNULL` — no test.
- **After:** explicit kwarg-spy pattern asserting `captured_kwargs["stdin"] is asyncio.subprocess.DEVNULL` and `"shell" not in captured_kwargs`.
- **Rationale:** A switch to `subprocess.run(..., shell=True)` would otherwise pass every test in the original story.

### Edit 6 — AC-4(e)+(f) rewritten as a chokepoint-level assertion
- **Source:** Coverage F5 + Test-Quality F2 + Test-Quality F9
- **Before:** test calls `_filter_env(None)` directly and asserts secret keys absent.
- **After:** kwarg-spy captures the actual `env=` passed to `create_subprocess_exec`; asserts `set(captured_env.keys()) <= {"PATH","HOME","LANG","LC_ALL"} ∪ env_extra.keys()` (allowlist-by-keyset, omission-based).
- **Rationale:** Catches the `env=os.environ.copy()` bypass mutant. Allowlist-keys-set subsumes the property without adding `hypothesis` (per Test-Quality F9's resolution).

### Edit 7 — AC-5 rewritten with deterministic timeout-escalation pin
- **Source:** Coverage F2 + Coverage F3 + Test-Quality F3
- **Before:** flaky `ls-remote https://10.255.255.1/` test; only `pytest.raises(ProbeTimeoutError)`.
- **After:** deterministic event-gated fake `Process`; spies on `terminate`/`kill`/`wait`; assertions: terminate called once, kill called after, wall-time bound `[timeout_s, 1.5·timeout_s + 0.2s]`, `elapsed_ms=` substring in error, weakref table cleared.
- **Rationale:** Catches immediate-SIGKILL, missing-elapsed-ms, leaked-child, and missing-finally-pop mutants. Network-independent (CI-safe).

### Edit 8 — AC-6 hardened with regex match on error message
- **Source:** Test-Quality F7
- **Before:** "with an install hint in the message" — no test inspection.
- **After:** `pytest.raises(ToolMissingError, match=r"git.*(install|PATH)")`.
- **Rationale:** Bare `raise ToolMissingError()` mutant survived before; now blocked.

### Edit 9 — AC-7 (weakref table) hardened with four-path cleanup pin
- **Source:** Coverage F7 + Test-Quality F8
- **Before:** "module-level constant, not per-instance" — no observable assertion.
- **After:** four observable invariants: register-during-run, clear-after-success, clear-after-timeout, clear-after-tool-missing; pin via fake-`Process` with `seen_during_run` capture and post-call membership check.
- **Rationale:** Removing the weakref table entirely was a silent-mutation. Now any of four exit paths fail loudly.

### Edit 10 — AC-10 added: `ProcessResult` immutability + typed fields
- **Source:** Test-Quality F5
- **Rationale:** A mutant typing `stderr: str` or omitting `frozen=True` would have passed the original happy-path test.

### Edit 11 — AC-11 added: signature-default sentinel pin
- **Source:** Test-Quality F6
- **Rationale:** Implementer-note prose isn't a test. `inspect.signature` one-liner makes a regression to `= {}` a build-breaker.

### Edit 12 — AC-12 added: argv shape validation
- **Source:** Coverage F6 + Coverage F8
- **Rationale:** `argv=[]`, `argv=["/usr/bin/git", ...]`, and `argv=["./git", ...]` all rejected with `DisallowedSubprocessError`. The "match `argv[0]` against `ALLOWED_BINARIES` as-is, no basename" choice is recorded explicitly so a future basename-stripping change is a deliberate decision.

### Edit 13 — AC-13 added: `env_extra` hygiene
- **Source:** Coverage F6
- **Rationale:** Closes the backdoor where a caller could re-introduce `OPENAI_API_KEY` via `env_extra`. The sensitive-key set is filtered from `env_extra` too, not just `os.environ`. Structlog WARNING event names the dropped key.

### Edit 14 — AC-8 (test inventory) expanded from 6 to 10 tests
- **Source:** validator synthesis
- **Rationale:** Every new and strengthened AC has at least one mutation-resistant test in the inventory.

### Edit 15 — TDD plan section rewritten end-to-end
- **Source:** Test-Quality F1–F8
- **What:** Replaced the six-test stub with ten parametrized/mock-based tests; rewrote prose to name the unifying pattern (*"spy `asyncio.create_subprocess_exec` to observe what the chokepoint actually passes to the OS"*); each test carries a one-line "Catches X mutant" comment.
- **Rationale:** Makes the mutation-resistance pattern legible to the executor and the next validator.

### Edit 16 — Implementation outline step 1 updated (six → ten)
- **Source:** validator synthesis (consequence of Edit 14/15)
- **Rationale:** Consistency.

### Edit 17 — Green section updated to reflect the new tests and `env_extra` filtering
- **Source:** validator synthesis (consequence of Edit 13)
- **Rationale:** The implementer now sees the sensitive-key-filtering of `env_extra` and the `try/finally:` for `_RUNNING_PROCS` as explicit deliverables.

## Verdict rationale

**HARDENED.** The story's goal is intact and the wrapper specification is internally consistent. The findings were of two kinds: (1) test-mechanism gaps that would have let mutated implementations pass executor validation — fixable in place by rewriting the TDD plan around chokepoint-boundary spying; (2) two architectural deviations from ADR-0012 — surgically surfaced rather than rewritten, with a follow-up amendment action item documented so the deviations are not silent. No `block` finding required rewriting the story's goal or scope, so RESCUE was not warranted. The story is now mutation-resistant on the dimensions ADR-0012 makes load-bearing (no-spawn-before-allowlist-check, `stdin=DEVNULL`, env-by-omission, SIGTERM-then-SIGKILL escalation order, weakref cleanup), and the two known-debt items are tracked.

## Recommended next step

`phase-story-executor` to implement.

**Follow-up (separate work — not blocking this story):** open an ADR-0012 amendment + arch §Component design + arch §Edge cases row 4 edit reconciling (a) "caller-responsibility for cwd-under-repo-root" and (b) `env_extra: dict[str, str] | None = None` as the canonical signature. Both deviations are recorded in the story's `Validation notes` block.
