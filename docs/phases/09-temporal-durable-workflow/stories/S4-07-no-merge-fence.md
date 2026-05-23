# Story S4-07 — No-merge-activity fence + typed-credential adversarial

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** S
**Depends on:** S4-02 (system activities exist; `_ACTIVITIES` registry populated), S4-04 (`github_open_pr` exists — the positive control that the fence does NOT reject)
**ADRs honored:** production ADR-0009 (humans always merge — the autonomy boundary of the whole system, rendered here as a fence); ADR-0008 (typed-credential blocklist — adversarial proves the seal-time check fires; `RedactionFired` lands in the canonical log)

## Context

Production ADR-0009 ("Humans always merge") is **the autonomy boundary of the whole system**. The autonomous agent opens PRs (`github_open_pr` — S4-04); humans review, approve, merge. The agent NEVER merges. This story is the fence that makes the discipline structurally undefeatable: a contributor proposing a `merge_pr` Activity will see the fence fail in CI before the PR even hits review.

Phase 9 ships THREE complementary defenses for the secret-leakage attack model (ADR-0008's three layers — see S4-06):
1. **Static** — `mypy --strict` (S4-06's design-time check).
2. **Fence (this story)** — no `merge_pr`-shaped activity exists; typed-credential return shapes are statically rejected.
3. **Runtime** — `seal()` rejects at runtime; `RedactionFired` event lands in the canonical log; S8-03 is the cross-process G9 blast-radius adversarial.

The two adversarial tests in this story exercise the SEAL layer specifically (S3-06's machinery):
- `test_typed_credential_blocklist`: an Activity declared with a `GitHubToken`-typed return field is rejected by `seal()` at first invocation — runtime defense.
- `test_secret_leakage_in_history`: every known credential value shape (AWS, GitHub PAT, JWT) lands in an Activity return; `seal()` rejects via the regex backstop; `RedactionFired` lands in the event log; the workflow can never persist the secret to Temporal history.

Both adversarial tests are **belt-and-braces** with S4-06's static fence — independent layers, none on a single trust path (ADR-0004's pattern again).

**Scope reminder.** This story ships THREE files:
1. `tests/fence/test_no_merge_activity.py` — the structural fence.
2. `tests/adv/test_typed_credential_blocklist.py` — the seal-time defense.
3. `tests/adv/test_secret_leakage_in_history.py` — the value-shape regex backstop + `RedactionFired` emission test.

The fence file does NOT need S4-04 fully landed; the fence asserts a NEGATIVE (no merge activity exists), which trivially passes when the activities catalog is small. But the adversarial tests DO consume the `seal()` machinery from S3-06 + the event log from S3-04.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Tool-use safety` (line 934) — "`github_open_pr` is the only Activity that calls a side-effectful external API. … **No `github_merge_pr` Activity exists** — enforced by `tests/fence/test_no_merge_activity.py` (greps `@activity.defn(name=...)` for `merge_pr|approve_pr|self_merge`). This is the [ADR-0009](../../production/adrs/0009-humans-always-merge.md) commitment rendered as a fence."
  - `../phase-arch-design.md §Sequence diagrams Scenario 4 — Adversarial` (lines 416-431) — the typed-credential adversarial flow.
- **Phase ADRs:**
  - `../ADRs/0008-typed-credential-blocklist-not-regex.md` §Decision — the three layers at seal time.
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — the layered-defense pattern.
- **Production ADRs:**
  - `../../../production/adrs/0009-humans-always-merge.md` (full) — the autonomy boundary.
  - `../../../production/adrs/0008-secret-redaction.md` — the secret-redaction discipline this story exercises.
- **Existing precedent:**
  - `tests/fence/` directory — other fence-test idioms in this codebase (e.g., `test_pyproject_fence.py` from Phase 0 — greps for forbidden LLM SDK imports).
- **Sibling stories:**
  - `S4-06-activity-payload-typing-fence.md` — the static counterpart.
  - `S4-08-one-way-import-fence.md` — the third fence in Step 4.
  - `S8-03-worker-blast-radius.md` — the cross-process G9 adversarial.

## Goal

Ship THREE files:
1. `tests/fence/test_no_merge_activity.py` — greps `src/codegenie/durable/activities/*.py` for `@activity.defn(name=...)` decorators whose name matches `^(merge_pr|approve_pr|self_merge|merge|approve)$` (case-insensitive) and asserts zero matches.
2. `tests/adv/test_typed_credential_blocklist.py` — declares a deliberate-violation Activity with a `GitHubToken`-typed return field and asserts `seal()` rejects at first invocation with a typed `SealError`.
3. `tests/adv/test_secret_leakage_in_history.py` — exercises every known credential shape (AWS, GitHub PAT, JWT) as a string field in an Activity return; asserts `seal()` rejects each via the regex backstop; asserts `RedactionFired(field_path, redaction_kind)` lands in the canonical event log.

## Acceptance criteria

- [ ] **AC-1 — `test_no_merge_activity.py` fence shape.** The fence (a) walks `src/codegenie/durable/activities/*.py` via `pathlib.Path("src/codegenie/durable/activities").glob("*.py")`; (b) for each file, reads its source and uses an `ast`-based walker (NOT regex over source — see Notes §1) to find every `@activity.defn(name=...)` decorator; (c) extracts the `name` keyword argument's literal value; (d) asserts none match `{"merge_pr", "approve_pr", "self_merge", "merge", "approve"}` (case-insensitive). The fence's failure message names the offending file + line number + the matched name + cites ADR-0009.
- [ ] **AC-2 — Fence-grep robustness.** The fence MUST NOT false-positive on:
    - A comment containing `merge_pr` (handled by AST walker — comments not in the AST).
    - A docstring containing `merge_pr` (handled by AST walker).
    - A function named `merge_pr` that is NOT `@activity.defn`-decorated (handled by walker filtering on `@activity.defn`).
    - A variable assignment `x = "merge_pr"` (handled by walker scope).
    Tests cover each false-positive shape with a small fixture file in `tests/fence/_fixtures/`.
- [ ] **AC-3 — Fence positive control (`github_open_pr` is NOT rejected).** A separate assertion confirms the fence inspects `github_open_pr` and does NOT flag it. Catches an over-eager regex that would match `pr` anywhere; ensures the fence is specific to merge-shaped names.
- [ ] **AC-4 — Deliberate-violation xfail fixture for the fence.** `tests/fence/_violations/test_no_merge_activity_violation.py` contains an `@activity.defn(name="merge_pr")` function NOT under `src/codegenie/durable/activities/`. The fence does NOT consume this file (per AC-1, the fence walks only `src/codegenie/durable/activities/*.py`). A separate test asserts that if the fence's walker is pointed at this file directly, it would flag the violation — proving the fence's assertion logic is correct even when the path narrowing changes.
- [ ] **AC-5 — `test_typed_credential_blocklist.py` shape.** Declares `class _BadActivityReturn(RedactedActivityResult)` with a field `token: GitHubToken`; constructs an instance via `_BadActivityReturn(token=GitHubToken("ghp_..."))`; asserts `_BadActivityReturn.seal(instance)` raises `SealError` whose `.field_path == "token"` and `.reason == "typed-credential-class"`. The test names the seal's three-layer pattern in the docstring; this exercises layer (b).
- [ ] **AC-6 — `test_secret_leakage_in_history.py` covers AWS, GitHub PAT, JWT shapes.** A Hypothesis property test generates secrets of each shape: AWS access key (`AKIA[0-9A-Z]{16}`), GitHub PAT (`ghp_[A-Za-z0-9]{36}`), JWT (`eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}`); for each, constructs an Activity return with the secret in a `str` field; `seal()` rejects via the regex backstop; the test asserts a `RedactionFired(field_path=..., redaction_kind="aws"|"github_pat"|"jwt")` event lands in the canonical event log via the test's fake `EventLog`.
- [ ] **AC-7 — `RedactionFired` events surface in the log.** A test asserts that after a regex-backstop rejection, the canonical event log has at least one `RedactionFired` row. The reason it matters: the regex backstop emits an event so we LEARN which contributors near-miss; without the event, the seal silently rejects and we don't feed the typed-credential registry over time. This is the "we learn from every contributor" feedback loop in ADR-0008.
- [ ] **AC-8 — Adversarial tests fast & deterministic.** Both adversarial tests run under `tests/adv/` (the Phase-1+ adversarial marker convention); they MUST NOT depend on Postgres or Temporal — use the in-memory `FakeEventLog` fixture. Total runtime <2 s.
- [ ] **AC-9 — `tests/adv/__init__.py` exists.** If `tests/adv/` doesn't yet exist for Phase 9's test tree, this story creates it. The `pyproject.toml` `[tool.pytest.ini_options]` already names `adv` as a marker (Phase 1 ADR-0006); this story does NOT amend it.
- [ ] **AC-10 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on all three files. `make check` green with the new tests in scope.

## Implementation outline

1. **Fence file `tests/fence/test_no_merge_activity.py`**: AST walker scoped to `src/codegenie/durable/activities/*.py`. Walks each module's AST; visits `FunctionDef` and `AsyncFunctionDef` nodes; for each, inspects `node.decorator_list` for `@activity.defn(name=...)` shape; extracts the `name` kwarg's `ast.Constant.value`; checks against the forbidden set.
2. **Fence fixtures `tests/fence/_fixtures/`**: tiny `.py` files demonstrating the false-positive shapes the fence MUST tolerate. Used by AC-2's positive tests.
3. **Adversarial `tests/adv/test_typed_credential_blocklist.py`**: imports `GitHubToken` from `codegenie.types.credentials`, declares `_BadActivityReturn`, calls `seal()`, asserts `SealError`.
4. **Adversarial `tests/adv/test_secret_leakage_in_history.py`**: Hypothesis-based; uses the `from hypothesis import given, strategies as st` machinery; generates strings matching each regex; asserts `seal()` + `RedactionFired` emission.
5. **`tests/adv/__init__.py`**: empty marker if not present.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/fence/test_no_merge_activity.py
import ast
from pathlib import Path

import pytest

_ACTIVITY_DIR = Path("src/codegenie/durable/activities")
_FORBIDDEN = {"merge_pr", "approve_pr", "self_merge", "merge", "approve"}


@pytest.mark.fence
def test_no_merge_activity_defined():
    """Production ADR-0009 — humans always merge; the autonomous agent
    NEVER calls a merge_pr-shaped Activity. The reason this is the red test:
    if a contributor lands `merge_pr` as an Activity (mistakenly or
    maliciously), the autonomy boundary of the whole system collapses —
    the agent could approve+merge its own PRs in production. The fence is
    the structural guarantee."""
    offenders: list[str] = []
    for module_path in _ACTIVITY_DIR.glob("*.py"):
        if module_path.name.startswith("_"):
            continue  # skip _idempotence.py etc.
        tree = ast.parse(module_path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                # Match @activity.defn(name="...") shape:
                if not (isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "defn"):
                    continue
                for kw in dec.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        if kw.value.value.lower() in _FORBIDDEN:
                            offenders.append(
                                f"{module_path}:{node.lineno} declares "
                                f"@activity.defn(name={kw.value.value!r}) — "
                                f"forbidden by production ADR-0009"
                            )
    assert not offenders, "\n".join(offenders)
```

Why it fails today: the activities directory may not yet have the merge activity to test against, BUT the test fixture file (AC-4's violation file) exists OUTSIDE the activities directory; this is correct.

### Green — minimal pass

- Ship the fence file with the AST walker.
- Ship the violation file outside the activities directory (per AC-4) so the fence stays green and the violation is testable in isolation.

### Required follow-on tests (per AC)

```python
# tests/fence/test_no_merge_activity.py (continued)

def test_fence_does_not_flag_github_open_pr():
    """AC-3 — positive control: `github_open_pr` is the only side-effectful
    GitHub Activity; the fence MUST NOT flag it. Catches an over-eager
    regex that matches 'pr' anywhere."""
    offenders = _run_fence()  # extracted helper
    assert "github_open_pr" not in " ".join(offenders)


def test_fence_tolerates_merge_pr_in_a_comment(tmp_path):
    """AC-2 — false-positive resistance: a comment mentioning merge_pr is
    fine; the AST walker doesn't see comments."""
    fixture = tmp_path / "ok_with_comment.py"
    fixture.write_text(
        "# This activity opens PRs; humans then merge_pr manually.\n"
        "from temporalio import activity\n"
        "@activity.defn(name='github_open_pr')\n"
        "async def f(input): ...\n"
    )
    offenders = _run_fence_against([fixture])
    assert not offenders


def test_fence_tolerates_function_named_merge_pr_without_decorator(tmp_path):
    """AC-2 — a function NAMED merge_pr but NOT @activity.defn-decorated is
    fine. The fence only flags decorated activities."""
    fixture = tmp_path / "ok_no_decorator.py"
    fixture.write_text(
        "def merge_pr(): pass  # private helper, not an activity\n"
    )
    offenders = _run_fence_against([fixture])
    assert not offenders
```

```python
# tests/adv/test_typed_credential_blocklist.py
import pytest
from codegenie.durable.sanitizer import RedactedActivityResult, SealError
from codegenie.types.credentials import GitHubToken


def test_seal_rejects_github_token_typed_field():
    """ADR-0008 layer (b) — typed-credential-class blocklist. The reason:
    a naive activity that returns `GitHubToken` as a field writes the
    token into Temporal history forever; anyone with read access to the
    cluster can see it. The typed blocklist catches at SEAL time —
    runtime defense complementing S4-06's static fence."""
    class _BadActivityReturn(RedactedActivityResult):
        token: GitHubToken

    bad = _BadActivityReturn(token=GitHubToken("ghp_" + "x" * 36))
    with pytest.raises(SealError) as exc_info:
        _BadActivityReturn.seal(bad)
    assert exc_info.value.field_path == "token"
    assert exc_info.value.reason == "typed-credential-class"
```

```python
# tests/adv/test_secret_leakage_in_history.py
import pytest
from hypothesis import given, strategies as st

from codegenie.durable.sanitizer import RedactedActivityResult, SealError
from codegenie.events.payloads import RedactionFired


@given(token=st.from_regex(r"ghp_[A-Za-z0-9]{36}", fullmatch=True))
def test_seal_rejects_github_pat_value_shape(token, fake_event_log):
    """ADR-0008 layer (c) — value-shape regex backstop catches the well-typed
    case where a contributor accepts a token as a generic `str` field. The
    backstop fires AND emits RedactionFired so we learn from the near-miss
    and update the typed-credential registry over time."""
    class _PossiblyBadActivityReturn(RedactedActivityResult):
        opaque_field: str

    instance = _PossiblyBadActivityReturn(opaque_field=token)
    with pytest.raises(SealError):
        _PossiblyBadActivityReturn.seal(instance)
    # AC-7 — RedactionFired lands in the canonical event log:
    redactions = [e for e in fake_event_log.events() if isinstance(e, RedactionFired)]
    assert any(e.redaction_kind == "github_pat" for e in redactions)


@given(key=st.from_regex(r"AKIA[0-9A-Z]{16}", fullmatch=True))
def test_seal_rejects_aws_access_key_value_shape(key, fake_event_log):
    """ADR-0008 layer (c) — AWS access keys. Same mechanism as GitHub PAT."""
    class _Bad(RedactedActivityResult):
        opaque: str
    with pytest.raises(SealError):
        _Bad.seal(_Bad(opaque=key))


@given(jwt=st.from_regex(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", fullmatch=True))
def test_seal_rejects_jwt_value_shape(jwt, fake_event_log):
    """ADR-0008 layer (c) — JWT shapes. The dot-separated structure makes
    the regex specific enough to avoid false-positives on base64 blobs."""
    class _Bad(RedactedActivityResult):
        opaque: str
    with pytest.raises(SealError):
        _Bad.seal(_Bad(opaque=jwt))
```

### Refactor

- Fence file's module docstring cites ADR-0009 + names the AST walker shape as the "robust-against-comments-and-strings" replacement for a regex grep.
- Adversarial files' module docstrings cite ADR-0008's three layers + map each test to the layer it exercises (layer b in `test_typed_credential_blocklist`, layer c in `test_secret_leakage_in_history`).
- Helper `_run_fence_against(paths)` extracted from the main fence body so AC-2's fixture tests can reuse it.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_no_merge_activity.py` | AST-walker fence + positive-control assertions. |
| `tests/fence/_fixtures/__init__.py` | Namespace marker. |
| `tests/fence/_fixtures/ok_with_comment.py` | False-positive resistance fixture (used inline via tmp_path; this file may not be needed if tests construct the fixture via `tmp_path.write_text(...)`). |
| `tests/fence/_violations/test_no_merge_activity_violation.py` | Deliberate-violation `@activity.defn(name="merge_pr")` OUTSIDE the activities directory. |
| `tests/adv/__init__.py` | Namespace marker (if not present). |
| `tests/adv/test_typed_credential_blocklist.py` | Seal-layer (b) defense. |
| `tests/adv/test_secret_leakage_in_history.py` | Seal-layer (c) defense + `RedactionFired` emission. |
| `tests/adv/conftest.py` | `fake_event_log` fixture if not already shared (likely lives in `tests/unit/durable/activities/conftest.py` — share via a higher-level conftest or duplicate; default to duplicate). |

## Out of scope

- The `RedactedActivityResult.seal()` implementation — S3-06.
- The `SECRET_TYPES` registry expansion — S1-01 ships the credential newtypes; ADR-0008 says expansion is one-line additive.
- The `RedactionFired` event variant — S1-02 ships it.
- The cross-process G9 adversarial (worker compromise, capability-token blast radius) — S8-03.
- The `make check` wiring of fences + adversarial — S8-06.
- The activity payload-typing fence — S4-06.
- The one-way-import fence — S4-08.

## Notes for the implementer

### §1 — AST walker over regex grep

A naive regex `re.search(r"@activity\.defn\(name=['\"]merge_pr['\"]", source)` is brittle:
- Misses `@activity.defn(name='merge_pr', ...)` if the regex doesn't allow trailing args.
- False-positives on comments (`# TODO: never use @activity.defn(name='merge_pr')`).
- False-positives on docstrings.
- Misses multi-line decoration: `@activity.defn(\n    name="merge_pr",\n)`.

The AST walker handles all four trivially. The cost is ~50 LOC vs 5 LOC for the regex, but the robustness pays its own rent.

### §2 — Why the fence walks `src/codegenie/durable/activities/*.py` only

A broader walk across `src/codegenie/**/*.py` would catch a `merge_pr` Activity declared in a misnamed file (e.g., `src/codegenie/temporal/merge.py`). But it would also force every contributor adding any test fixture mentioning `@activity.defn` to think about it. The narrow walk maps cleanly to "where Activities live"; a misnamed file is an organizational drift that other CI assertions catch (e.g., import-linter contracts in S4-08).

If a future story adds Activities in a second directory (Phase 10's `vuln-remediation-python-pip` activities under a new package), the fence's `_ACTIVITY_DIR` constant becomes a list. One-line additive change.

### §3 — Hypothesis is a dev dependency

Phase 9's `pyproject.toml` already pulls Hypothesis (Phase 1+ adversarial conventions). The `from hypothesis import given, strategies as st` import is safe. If `from_regex` rejects the regex shape (Hypothesis has some quirks on character classes), fall back to a manual `st.lists(st.sampled_from(...))`-based generator.

### §4 — `RedactionFired` is the feedback loop

The architect explicitly carries the "regex backstop emits an event so contributors LEARN" rationale (ADR-0008 §Decision row 25). Without `RedactionFired`, the regex backstop silently rejects and the typed-credential registry never grows — every novel-shape credential the system encounters is rejected by the regex layer, the contributor edits the field type, and we never update the typed registry. With `RedactionFired`, every near-miss flows to the canonical event log; S7-01's audit trail surfaces them; the typed-credential registry grows additively. The discipline applies broadly: every defensive layer that rejects something MUST also emit a learnable signal.

### §5 — Don't catch on the *type-instance check* at runtime

A temptation: "let's also assert at runtime that `isinstance(return_value, RedactedActivityResult)`." This is wrong for the same reason S4-06 carries: the static check is the typing fence; the runtime check is the seal; this story is the *third* layer. Conflating layers re-creates the single-trust-path failure mode. Keep `test_typed_credential_blocklist` focused on the seal's runtime rejection; let S4-06 own the static check.

### §6 — The fence's failure message is debuggable

A contributor seeing the fence fail should know exactly:
- WHICH file declared the forbidden activity.
- WHICH line number.
- WHAT name was used.
- WHICH ADR forbade it.

The current message: `f"{module_path}:{node.lineno} declares @activity.defn(name={kw.value.value!r}) — forbidden by production ADR-0009"`. Reviewers can copy this verbatim into a PR comment; the contributor knows exactly what to change.

### §7 — Phase 10's first commit and the drain window

When Phase 10 lands new task queues (Python/Java), this fence's `_ACTIVITY_DIR` may become a list (per Notes §2). The forbidden-set stays the same. ADR-0009 is **inviolable** for the foreseeable future; if it's ever amended, every consumer story re-validates against the new boundary.
