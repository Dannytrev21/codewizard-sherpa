# Validation report — S1-10 — `node` allowlist + sub-schema convention + event constants

**Story:** [`S1-10-node-allowlist-subschema-convention.md`](../S1-10-node-allowlist-subschema-convention.md)
**Validator run:** 2026-05-14 (scheduled `story-validation-corrector`)
**Verdict:** **HARDENED** — real fixable weaknesses found and patched in place.
**Depth:** standard (no Stage 3 research required; all findings resolvable from in-repo evidence).

## Context Brief

S1-10 is the final Phase-1 Step 1 story. It bundles three small landings:

1. **ADR-0001 allowlist edit** — `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` → `frozenset({"git", "node"})` so `NodeBuildSystemProbe` (S2-02) can run `node --version`.
2. **`_subschema_convention.md`** — in-tree note documenting ADR-0004 (`additionalProperties: false` at sub-schema root), ADR-0010 (slices optional at envelope `probes.*`), ADR-0007 (`WarningId` pattern).
3. **Five `Final[str]` event-name constants** in `codegenie/logging.py` so the literals scattered across S1-02 → S1-09 collapse to typed references.

The phase arch (`phase-arch-design.md` §"Component design" #2, #11; §"Harness engineering" → "Logging strategy") and the four named ADRs constrain the goal. The Phase 0 exec chokepoint (`src/codegenie/exec.py`) and existing logging-constant registry (`src/codegenie/logging.py`) are the surfaces being extended.

## Stage 2 — Critic findings (in-line audit across the four lenses)

### Coverage critic

| # | Finding | Severity | Resolution |
|---|---|---|---|
| C-1 | AC-3 doesn't pin the canonical JSON Schema fragment beyond "code-blocks showing the canonical JSON Schema fragment" — a future doc-only edit could quietly drop the example. | harden | New AC-3b: doc must contain literal `"additionalProperties": false` substring. |
| C-2 | No closed-set negative regression on `ALLOWED_BINARIES`. Equality assertion catches a widening mutant on the day-of, but a future PR can stealthily add `"bash"` and the equality test gets "fixed" to match. | harden | New AC-2b: parametrized negative-membership over six dangerous binaries (`bash`, `sh`, `python`, `curl`, `wget`, `ssh`). The discipline is "every new entry needs an ADR"; the test makes the ADR conversation mechanically required. |
| C-3 | Chokepoint invariants (`stdin=DEVNULL`, no `shell` kwarg) are pinned by Phase 0 Test 3 for `git` only. A mutant that special-cases `node` to relax one of the six invariants would pass Phase 1's existing coverage. | harden | New AC-2e: parametrize Phase 0 Test 3 over `git` and `node` argv. |
| C-4 | The "Optional follow-up cleanup" AC offers do-it-or-don't with PR-body documentation as the discipline. Rule 12 violation — the test suite cannot distinguish "consciously deferred" from "forgotten". | block | Replaced with a deterministic rule: the sweep IS in scope for the four event literals that have existing call-sites; `probe.raw_artifact.truncated` lands as a constant only. `git grep` discipline AC (AC-5) + `tests/unit/test_no_event_literal_drift.py` enforce the registry. |

### Test-quality critic

| # | Finding | Severity | Resolution |
|---|---|---|---|
| TQ-1 | **Critical.** `test_env_strip_drops_secrets_for_node_invocation` cannot run against the Phase 0 implementation: (a) `run_allowlisted` is `async`; the test calls it sync. (b) Patches `subprocess.run`; the impl uses `asyncio.create_subprocess_exec`. (c) Sets parent-env vars expecting strip behavior; the impl never copies parent env at all (env-by-omission). (d) Passes `cwd="."`; the impl requires `Path` and `resolve(strict=True)`. The test as written would either error out (sync call to async function) or pass trivially against a no-op (because the parent env never reaches the child regardless). | block | TDD plan rewritten end-to-end to mirror [`tests/unit/test_exec.py`](../../../../../tests/unit/test_exec.py) Test 2 (env-keyset subset assertion) and Test 3 (parametrized chokepoint kwargs). All async; spy on `asyncio.create_subprocess_exec`; assertion is over the captured env passed to the spawn. |
| TQ-2 | Test path `tests/unit/exec/test_allowed_binaries.py` does not exist; Phase 0 exec tests are at `tests/unit/test_exec.py`. Per Rule 3 (surgical) + Rule 11 (match conventions), extend the existing file instead of inventing a new directory. | block | Files-to-touch updated; TDD plan now extends `tests/unit/test_exec.py`. |
| TQ-3 | The `EVENT_PROBE_*` family already has a closure assertion in `tests/unit/test_logging.py` ("every module attribute starting with `EVENT_PROBE_` appears in `EXPECTED_EVENT_NAMES`"). The story's standalone `test_phase1_event_constants` doesn't exercise that closure — a future PR adding a sixth `EVENT_PROBE_*` without dict update would NOT fail. | harden | New AC-4b: extend `EXPECTED_EVENT_NAMES` so the closure check propagates. Targeted per-name assertion remains for value-pin clarity + `type(x) is str` pin. |
| TQ-4 | Convention-doc test asserts ADR references and pattern verbatim but doesn't pin the canonical fragment OR the back-pointer to the enforcing test. The doc becomes load-bearing alone if the structural test (`tests/unit/test_sub_schemas.py`) doesn't land in S2-01 on time. | harden | New AC-3b: assert `"additionalProperties": false` literal + `test_sub_schemas.py` mention + 80-line cap. |
| TQ-5 | Mutation-resistance for the sweep is zero in the original story — the "optional" framing means no test guards against literal regression. A future PR can re-add `_EVENT_CAP_EXCEEDED: Final[str] = "probe.parser.cap_exceeded"` to a parser module and nothing catches it. | harden | New `tests/unit/test_no_event_literal_drift.py` walks `src/codegenie/**/*.py`, asserts no string-literal occurrence of the four registered values outside `logging.py`. |

### Consistency critic

| # | Finding | Severity | Resolution |
|---|---|---|---|
| CN-1 | Story names ADRs 0001/0004/0010 in the header but AC-3 requires the doc to reference ADR-0007 too. Header should include 0007. | nit | Header `ADRs honored` line extended to include ADR-0007. |
| CN-2 | The "Optional follow-up cleanup" AC contradicts ADR-0007's "Open/Closed at the file boundary" framing implicitly assumed by the registry pattern. If event-name discipline is structural, it's not optional. | harden | Folded into TQ-5 / C-4 resolution. |
| CN-3 | Story implementer note claims `mkdocs build --strict` ignores `src/`. Verified against `mkdocs.yml` (`docs_dir: docs`). Note retained; verification mentioned in updated note. | confirmed | n/a |
| CN-4 | ADR-0001 Consequences says future binaries (`python --version`, `go version`) follow same workflow. Story's closed-set negative regression (`"python"`, `"sh"`, etc.) does NOT contradict — it pins discipline; future ADR-gated additions update the test alongside the set. | confirmed | n/a |
| CN-5 | No contradiction found between story and `production/design.md` "facts, not judgments" — the `WarningId` pattern enforces facts-not-prose structurally and the story documents it correctly. | confirmed | n/a |

### Design-patterns critic

| # | Finding | Severity | Resolution |
|---|---|---|---|
| DP-1 | The five constants formalize a **registry pattern** that was previously emergent (three parser modules each redefining `_EVENT_CAP_EXCEEDED` as a private `Final[str]`, plus two raw-literal call-sites in `parsed_manifest_memo.py`). Centralization is the right move; this is the third concrete consumer (Rule of Three crossed) — kernel extraction is *justified*, not premature. | harden | Captured in Notes-for-implementer + AC-5 sweep made mandatory. |
| DP-2 | The Open/Closed property of the registry is only as strong as its enforcement. Module-local constants make the **vocabulary** typed but don't prevent literal-drift; the sweep + `test_no_event_literal_drift.py` give the registry teeth. **This is the Open/Closed at the file boundary** the project's CLAUDE.md "Extension by addition" commitment implies. | harden | AC-5 + new test file added. |
| DP-3 | `ALLOWED_BINARIES` is already `frozenset` (closed for in-process mutation) + ADR-gated (closed for casual extension). The story preserves this. The negative-membership regression makes the "every new entry needs an ADR" property mechanically required, not just culturally. | harden | AC-2b added. |
| DP-4 | The docstring in `logging.py` says explicitly: *"plain `str` values (not `StrEnum`) because Phase 13's cost ledger destructures via `type(x) is str`."* Rule 11 + load-bearing — do NOT propose `StrEnum`. Original story didn't propose it; new tests assert `type(x) is str` to pin the contract. | confirmed | Pin added in AC-4 + TDD plan. |
| DP-5 | The convention doc is a **specification artifact** (prose); its structural enforcement is the per-sub-schema test in S2-01. Story should explicitly name where the enforcement lives so the doc isn't load-bearing alone. | harden | AC-3b's back-pointer requirement + Notes for implementer. |
| DP-6 | Three independent landings in one story violates INVEST "Independent" if read strictly, but they're all sub-rule-of-three primitives that close out Step 1; bundling reduces ceremony. Keep as-is; the three-commit boundary inside the PR gives reverter granularity. | nit | Implementer note updated to require three-commit boundary. |
| DP-7 | A future stronger guard is a pre-commit `forbidden-patterns` hook (AST-precision); leave as a flag for S6-03's adversarial sweep, not in scope here. | nit | Flagged in Notes-for-implementer. |

### Stage 3 — Research

Not invoked. No `NEEDS RESEARCH` findings; every weakness was resolvable from the in-repo evidence (Phase 0 `test_exec.py`, `logging.py` docstring, ADR text, existing call-site grep).

## Stage 4 — Edits applied

The story file was edited in place. Diff at a glance:

- **Header:** ADRs honored line extended to include ADR-0007. `Status` updated to `Ready — hardened`.
- **New section:** `Validation notes (2026-05-14)` directly under the header documenting every change and its rationale (block-promoted and harden-promoted findings each get a sentence).
- **Acceptance criteria:** rewritten from 8 ACs to 13 numbered ACs (AC-1, AC-2a, AC-2b, AC-2c, AC-2d, AC-2e, AC-3, AC-3b, AC-4, AC-4b, AC-5, AC-6, AC-7, AC-8). The "optional follow-up cleanup" line is gone; the sweep is mandatory and instrumented by a grep-discipline AC plus a new test file.
- **TDD plan — Red:** five test sketches rewritten/added:
  1. `test_node_in_allowed_binaries` — positive + equality (mutation-resistance for set widening).
  2. `test_allowed_binaries_closed_set_regression` (parametrized) — negative regression.
  3. `test_node_invocation_env_keyset_subset_of_safe_baseline` — env-by-omission invariant for `node` argv, spy on `asyncio.create_subprocess_exec`.
  4. `test_node_invocation_env_extra_drops_sensitive_keys` — `env_extra` drop + structlog event.
  5. `test_spawn_kwargs_pin_stdin_devnull_and_no_shell_for_each_binary` (parametrized) — chokepoint invariants for both binaries.
  Plus `tests/unit/test_logging.py` extension via `EXPECTED_EVENT_NAMES.update(...)` so the existing closure assertion propagates.
  Plus `tests/unit/schema/test_subschema_convention_doc.py` extended with the canonical-fragment + back-pointer + line-cap assertions.
  Plus new `tests/unit/test_no_event_literal_drift.py` for AC-5 registry discipline.
- **Green section:** clarified one-line exec.py edit; logging.py `__all__` update; convention-doc required structure including back-pointer.
- **New section:** `Registry sweep — call-site discipline (commit #3, separable)` with the five files to flip and the grep discipline.
- **Files to touch:** corrected from `tests/unit/exec/test_allowed_binaries.py` to `tests/unit/test_exec.py`; sweep targets moved from "Optional" row to mandatory rows; new test file added.
- **Notes for the implementer:** rewritten to call out async + env-by-omission + Phase 0 test idiom; explicit registry-pattern framing connecting AC-5 + new test to Open/Closed at the file boundary; flag for future pre-commit hook deferred to S6-03.

## Outcomes

The hardened story is now safe for `phase-story-executor` to run:

- Every AC is individually verifiable with a concrete check.
- Every AC has a test that would fail under an obviously-wrong implementation (mutation-resistance).
- The TDD plan's red tests are syntactically + semantically compatible with the Phase 0 codebase (`async`, `asyncio.create_subprocess_exec`, `Path` cwd, env-by-omission).
- The three landings keep their bundling but commit at three-commit granularity so the sweep is independently revertible.
- The registry-pattern enforcement (centralized `Final[str]` + literal-drift test) makes Phase 2+ extension-by-addition mechanically safe (Open/Closed at the file boundary).
- No conflict with `production/design.md` "facts, not judgments", "no LLM in gather", or "extension by addition" load-bearing commitments.
- No ADR contradicted; one ADR added to the honored set (ADR-0007).

## Open items surfaced to user / executor

None. All findings resolved by in-place edits. One forward-looking note: a stronger AST-based literal-drift guard (pre-commit `forbidden-patterns` hook) is deferred to S6-03's adversarial sweep; this is flagged in Notes-for-implementer.
