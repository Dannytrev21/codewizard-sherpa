# Validator — Stage 3: Ralph Wiggum Naive Verification

Stage 3 is the skeptical fresh-eyes pass that fights the Implementer's confirmation bias. The Implementer's mindset is "I just built this; of course it works." The Validator's mindset is "show me — slowly, literally, no benefit of the doubt."

The technique is named after Ralph Wiggum — the Simpsons character known for childlike directness. The frame is deliberately naive: re-explain each claim in the simplest possible terms, then verify that literal claim against runtime behavior, not against the code itself.

## The Ralph Wiggum frame

For every acceptance criterion in the story:

1. **Read the AC verbatim** (don't rely on memory)
2. **Restate it the way Ralph would** — literal, simple, no jargon, no assumptions
3. **Locate the evidence** — file:line of code, test name, runtime artifact path
4. **Run the evidence** — don't trust static reads. Run the test. Invoke the CLI. Inspect the output.
5. **Compare what you saw at runtime to what Ralph said** — match or not?
6. **Mark PASS / FAIL with the runtime evidence**

### Example

> **AC-4:** "The CLI exits with code 1 when no probes are registered."
>
> **Ralph's restatement:** "If there's no probes, the program goes bye-bye with the number 1."
>
> **Evidence located:** `src/codegenie/cli.py:42` has `sys.exit(1)`; test `tests/test_cli.py::test_exits_one_when_no_probes` asserts it.
>
> **Run it:**
> ```bash
> pytest tests/test_cli.py::test_exits_one_when_no_probes -v
> # then independently:
> python -m codegenie.cli gather /tmp/empty-dir
> echo $?
> ```
>
> **Compare:** Test passes. CLI exits with 1 when invoked manually. Ralph is satisfied. **PASS.**

The redundant manual run is on purpose. Tests can be wrong — Rule 9 (tests verify intent, not just behavior). Running the CLI independently is the second witness.

## Per-AC validation checklist

For every AC, run through:

- [ ] **Restate** literally
- [ ] **Locate** evidence (test name or runtime artifact)
- [ ] **Run** the evidence and capture output
- [ ] **Compare** runtime to restatement
- [ ] **Mark** pass/fail with the runtime line as evidence

If you can't find evidence for an AC, it's a **fail**. If the evidence exists but doesn't actually demonstrate the AC, it's a **fail**. "Test passes" ≠ "AC met" — the test could be encoding the code's current behavior instead of the AC's intent.

## Cross-cutting gates

Beyond per-AC checks, run these gates and record exit codes + summaries:

| Gate | Command (or equivalent) | Pass condition |
|---|---|---|
| Full test suite | `pytest` (or project runner) | All green, no unexpected skips |
| Lint | `ruff check` | No warnings unless already-existing in baseline |
| Format | `ruff format --check` | No drift |
| Type-check | `mypy` (if configured) | No new errors |
| Pre-commit | `pre-commit run --all-files` (if wired) | All hooks pass |
| Files-to-touch | shell `ls` on every path in story's section | Every file exists with non-trivial content |
| Design quality | walk [`design-patterns.md`](design-patterns.md) §"Anti-patterns the validator should flag" against code this story added | No anti-pattern smells in story-added code; project-aligned patterns (Plugin/Registry, Capability, chokepoint modules, Markers-only exceptions, strict typing) reinforced rather than worked around |

If any gate fails, the validation result is **FAIL** — return to Stage 2.

### Design-quality gate — what to look for

Open [`design-patterns.md`](design-patterns.md) and skim the
anti-pattern table against the files this story *added or modified*
(not the rest of the codebase — Rule 3). Specifically:

- `Any` in any new function signature on `src/`? → FAIL.
- Raw `str` / `int` for an identifier with a semantic (e.g., a probe
  name, a warning id, a cache key)? → FAIL — should be a `NewType` or
  a frozen dataclass.
- New `if/elif` ladder over a closed set of subclasses or string tags?
  → FAIL — tagged union or strategy dispatch.
- A dangerous operation (`os.open`, `subprocess.run`, `hashlib.*`,
  `yaml.load`, …) used directly when a chokepoint module exists
  (`safe_json`, `exec.run_allowlisted`, `hashing.content_hash`, …)?
  → FAIL — route through the chokepoint.
- `except Exception` / `except BaseException` introduced? → FAIL —
  narrow to the specific subclass that's actually expected.
- New mutable module-level state without `Final` typing? → FAIL.
- New class inherits from a class that already has its own non-ABC
  parent (two-level concrete inheritance)? → FAIL — favor composition.
- Comments that explain *what* the code does instead of a non-obvious
  *why*? → FAIL — rename / extract a function / delete the comment.
- A new public `__all__` that exports symbols no caller needs? → FAIL
  — trim the surface (deep interface, not wide).

If you find any of the above in code *the story added*, that's a
RETURN to Stage 2 with the gap named. If you find any in pre-existing
code the story touched only incidentally, log it as a follow-up — do
not fold the fix in (Rule 3 — surgical changes).

## Validator report format

Output a single markdown block (and save it as the latest attempt's validator block in the journal):

```markdown
## Validator report: {STORY-ID} attempt {N}

### Per-AC results
- [x] AC-1 ({restatement}) → PASS — evidence: tests/test_foo.py::test_bar (output: "OK")
- [x] AC-2 ({restatement}) → PASS — evidence: src/codegenie/cli.py:42 runtime-verified
- [ ] AC-3 ({restatement}) → FAIL — {what's missing or wrong}
- [ ] AC-4 ({restatement}) → FAIL — test exists but assertion is too permissive (test passes even if the code returns None)

### Gates
- pytest: PASS (37 passed, 0 failed, 0 skipped)
- ruff check: PASS
- ruff format --check: FAIL (1 file)
- mypy: PASS
- pre-commit: not configured
- Files-to-touch: PASS (all 7 files exist)
- Design quality: PASS — no anti-pattern smells in story-added code; chokepoints reinforced (safe_json, exec); `WarningId` newtype used; markers-only invariant preserved.

### Diagnosis
- AC-3 missing — no test exercises the empty-input case
- AC-4 test exists but assertion is wrong (Rule 9) — see tests/test_foo.py:18, change `assert result is not None` to `assert result == expected`

### Recommendation
RETURN to Stage 2 with gaps:
1. Add a test for the empty-input case (AC-3)
2. Tighten AC-4 test assertion
3. Run `ruff format` on the one file
```

If all per-AC results pass and all gates green: **Recommendation: PROCEED to Stage 4.**

Otherwise: **Recommendation: RETURN to Stage 2 with these gaps.**

## The hardest validator case

The trickiest failure mode: **tests pass but the AC isn't actually met.** This usually means the test was written to match what the code happened to do, not what the AC asked for.

To catch it:

- Read the test's *assertion line*, not its setup. Does the assertion encode the AC's intent or just the code's current behavior?
- **Thought experiment:** if you swapped the production code for a different reasonable implementation (or a deliberately wrong one), would the test still pass? If yes, the test is too permissive. Rule 9 violation.

When you catch this, the RETURN message to Stage 2 should be: "test for AC-{N} is too permissive — tighten the assertion before re-running."

## Retry cap

Three RETURN cycles per story is the default. If Stage 3 issues a third RETURN, the skill stops:

1. Write the full Stage 3 report into the attempt log
2. Mark the attempt log entry as `Attempt N — FAILED (escalated)`
3. Surface to the user with: "Story {STORY-ID} could not be completed in 3 attempts. The validator's open issues are: {list}. The attempt log is at {path}. Suggested next steps: {one or two ideas}."

Do not proceed silently. Do not push partial work. Rule 12 — fail loud.

## Where Ralph Wiggum stops and Chain-of-Verification starts

Ralph Wiggum is the *frame* (naive, literal). For complex ACs with multiple parts, supplement with **Chain-of-Verification** (Dhuliawala et al. 2023):

1. Generate 2-4 verification questions about the AC ("what input does this take?", "what does it do when input is empty?", "what does it return?")
2. Answer each question independently from the code
3. Check that the answers are consistent with each other and with the AC

CoV is just a more structured Ralph Wiggum for ACs with hidden corners. See [`techniques.md`](techniques.md) for when to escalate from one to the other.
