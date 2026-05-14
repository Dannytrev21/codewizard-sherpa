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

## L-7 — Hardened-story test snippets can have self-inconsistent payloads (S1-04)

The S1-04 story's TDD plan included
`test_well_balanced_5000_nested_block_comments_parses_under_1s` with the
payload `"{ " + "/* " * 5000 + '"k": 1 ' + " */" * 5000 + " }"` and the
assertion `assert out["k"] == 1`. Under the AC-13 nested-block-comment
contract the `"k": 1` token lives inside the comment block and gets
stripped to `{}` — no correct implementation can satisfy the assertion.
The story author's *intent* (AC-28: "5,000 well-balanced nested block
comments parse in < 1 s") is reachable by moving the payload outside
the comment block; the test's *literal* payload was wrong. Lesson for
the executor: a hardened test snippet is the contract for **what the
test verifies**, not the contract for **what the payload looks like** —
preserve the AC's intent and the asserted post-state; fix the input
shape when it logically contradicts itself. Surface as a deviation in
the attempt log and propose a one-line story-file edit so the next
re-read doesn't re-litigate. (Sibling to L-4: "TDD parametrize values
are contract, not guidance"; L-7 is the inverse — when the payload
itself is impossible, the *intent* is the contract.)

## L-8 — Shared kernel modules can have hidden short-read silences (S1-04)

`parsers/_io.open_capped` returns `os.read(fd, size)` without verifying
`len(data) == size`. For `safe_json` and `safe_yaml` a truncated read
surfaces as `MalformedJSONError` / `MalformedYAMLError` via
`json.loads` / `yaml.load`'s own decode failure, which is "close
enough" to a typed error — S1-03's hardening explicitly relaxed the
safe_json short-read test to a type-only assertion. S1-04's AC-9
demanded the literal `"short read"` substring back. Two options:

1. Add short-read detection to `_io.open_capped` so all three parsers
   surface a uniform typed error. Changes existing parsers' observable
   error path; needs re-tightening their tests; potentially a new
   kernel-level marker.
2. Inline the open + cap + read + close in `jsonc.py` so it detects
   short reads itself. ~10 lines of duplication.

S1-04 picked option 2 (Rule 3: surgical changes; the story's
implementation outline showed inline code). Lesson: when a story's AC
requires a typed-error identity the shared kernel can't deliver,
inlining wins unless the kernel-refactor cost is bounded enough for
the same story. File the kernel-refactor as a follow-up.
