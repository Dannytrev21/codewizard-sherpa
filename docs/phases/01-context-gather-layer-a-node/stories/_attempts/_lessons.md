# Phase 1 — Cross-story lessons learned

Append-only. Short, reusable takeaways the next story can apply.

---

## L-1 — Verbatim story examples may exceed line-length lint (S1-01)

When a story includes complete code examples (test bodies, class
definitions), the prose-style docstrings can exceed `ruff`'s 100-column
default. Phase 0 conventions (e.g., `ProbeBudgetExceeded`) wrap long
docstrings across 2–4 lines. Match the *Phase 0 wrapping pattern* rather
than the literal example formatting in the story file. The contract is
the substrings the docstring must contain (slug, hard-fail marker), not
the line breaks.

## L-2 — `make fence` fails locally but is green in CI (S1-01)

The local `make fence` target inherits pyproject's `--cov-fail-under=85`
addopt and trips on the 9-test fence subset. CI's fence job overrides
with `-o "addopts="`. Don't try to "fix" this from a story; it's
intentional Phase 0 plumbing. Validate with `make lint typecheck test`
plus `pytest tests/unit/test_pyproject_fence.py -o "addopts="` if needed.
