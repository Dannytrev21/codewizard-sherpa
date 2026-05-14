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

## L-3 — Long ADR-path docstring references must wrap to 100 cols (S1-02)

ADR filenames in this repo run ~80 chars and the docstring reference
form (` - ``docs/phases/.../ADRs/0008-….md`` `) is ~105 — six chars
over `ruff`'s 100-col limit. Mirror the `errors.py` pattern: cite the
ADRs *directory* once, then list per-ADR filenames on continuation
lines (` - ``docs/.../ADRs/`` — ``0008-…``, ``0009-…`` `). The
contract is the substrings each docstring must contain (e.g.,
`adr-0008`, `adr-0009`); the wrapping is style.

## L-4 — TDD parametrize values are contract, not guidance (S1-02)

When a hardened story's TDD plan prescribes specific parametrize
values for a boundary AC (e.g., `[0, 1, 63, 64]` pass / `[65, 70,
200]` fail), those values *are* the boundary the AC ratifies. If the
green impl fails at a prescribed param, the impl is wrong — don't
relax the parametrize to fit the impl. Trace the depth/offset
semantic the story author had in mind, fix the walker, then keep the
story's parametrize verbatim. (Rule 9 — tests verify intent.)

## L-5 — Lift-into-shared-primitive may break tests pinning message text (S1-03)

When a story prescribes lifting an inline defense (e.g., O_NOFOLLOW +
size-cap I/O) into a shared `parsers/_io.py` / `parsers/_depth.py`
primitive, the *typed-exception* contract survives the move but the
*literal exception message* may not — the primitive's message format
becomes the new baseline. Downstream tests that pin
`"short read" in exc.args[0]` will fail. Resolution: relax to
type-only assertions (`pytest.raises(MalformedJSONError)`) where the
test's actual intent is "the right typed exception fires"; keep the
message check only when the message *content* is itself the contract
(e.g., AC asserts the path appears in `args[0]`). Rule 9: tests
verify intent, not implementation strings.

## L-6 — Story field-name values can drift from shipped convention (S1-03)

S1-03 AC-14 prescribed `cap_kind ∈ {"bytes","depth"}`; S1-02 shipped
`cap_kind="size"`. The implementer kept "size" (Rule 11 — match the
codebase) and surfaced the drift as a "Deviations" entry rather than
splitting the cap_kind vocabulary across two parsers. Lesson for the
next validator-and-executor cycle: when a hardened story's literal
field value disagrees with shipped code, the *intent* (a structured
discriminator) is the contract; the *spelling* is conventional. If
the divergence matters, surface it as a deviation in the attempt log
and propose a one-line story-file edit so the next story doesn't
re-litigate.
