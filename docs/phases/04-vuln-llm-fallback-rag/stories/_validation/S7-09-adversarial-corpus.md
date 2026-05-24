# Validation report: S7-09 — Adversarial corpus + red-team suite

**Validated:** 2026-05-24
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S7-09 is Phase-4 Step-7's portfolio adversarial gate: 200+ injection payloads
through `FenceWrapper` + `CanaryGuard`, 50+ red-team `PlanProposal*` scenarios,
two RAG-poisoning paths (chain-orphan + runtime in-body inject), the
plan-path-escape smart-constructor test, and the extended scan-before-truncate
canary test. The goal is correct — it traces verbatim to
`phase-arch-design.md §"Adversarial tests"` (lines 1002–1010), to
`High-level-impl.md §Step 7 §Done criteria` ("200+ injection payloads → 0
escapes; 50+ red-team prompts → 0 successes"), and to the threat-model framing
in the phase context (Phase 4 is the first phase where an LLM produces
applied bytes).

The story body, however, contained **ten block-class drifts** against
already-hardened sibling stories, plus fifteen harden-class mutation-resistance
holes and three nits. Every one was fixable in place; the goal and scope are
unchanged. Verdict: **HARDENED**. Status flipped from `Ready` to `HARDENED`.

## Method note

Stage 1 loaded: the story file in full;
`phase-arch-design.md §"Adversarial tests"` + §Edge cases #6/#8/#12/#14/#15
+ §Component 3 (FenceWrapper/CanaryGuard) + §Component 15 (EgressGuard);
`High-level-impl.md §Step 7`; ADR-0001 / ADR-0006 / ADR-0012 / ADR-0013 /
ADR-0016 (decision sections only); the hardened stories S2-02 (`FenceWrapper`),
S2-03 (`CanaryGuard.scan` + `INJECTION_PATTERNS`), S1-02 (`PlanProposal` +
`ValidationError` distinct-keyword discipline), S4-05 (module-level `verify`),
S5-01 (`SolvedExampleRetriever.query` + per-record orphan emission), S3-03
(EgressGuard — already-shipped adversarial); their validation reports for
sibling-lineage framing; `tests/adv/` directory listing; the `adv` /
`phase02_adv` marker registration in `pyproject.toml`; and the prior
`_validation/S7-07-e2e-replay-lands-rag.md` + `_validation/S7-08-final-kernel-frozen-verification.md`
to mirror the typed-event-parser + Open/Closed-at-the-file-boundary +
extension-by-addition conventions.

Stage 2 critics were synthesized inline rather than spawned as four parallel
subagents — every cross-cutting finding was identifiable from a single read of
the sibling stories, and four subagents would have re-read the same files
without context-window protection benefit (Global Rule 6 token budget; the same
choice S7-08's HARDENED validation made for the same reason).

Stage 3 (Researcher) was not invoked. No finding required canonical-pattern
research; every fix has a verbatim sibling-story precedent (typed-event parser
from S7-06, distinct-keyword discipline from S1-02 F9, per-row expected-outcome
parametrization from S2-03 V8, Open/Closed at the file boundary from
S7-06 AC-18, `nonce_source` seam from S2-02 AC-7, in-body backstop pattern_id
from S2-02 AC-6 step 2, `get_args(SourceKind)` parametrization from S2-02 AC-3).

Open ambiguities surfaced at Stage 1: none requiring user input. The arch
explicitly names `tests/adversarial/`; the codebase reality is `tests/adv/`;
S2-03's V6 hardening already resolved this for the bypass-via-truncation seed,
so S7-09 follows the codebase, with the arch text flagged as a known doc-vs-code
drift that other stories have already absorbed.

## Context brief

**Story snapshot.** Six gating adversarial tests under `tests/adv/`, marked
`@pytest.mark.adv`, asserting 0 injection escapes from 200+ payloads and 0
successes from 50+ red-team scenarios. Last story in Step 7's adversarial
column; closes Phase-4's prompt-injection / RAG-poisoning / path-escape /
truncation-bypass threat surfaces.

**Sibling-family lineage carrying convention forward.**

- **S2-02 (HARDENED)** ships `FenceWrapper.fence(payload, source_kind) -> FencedSegment`
  with `FencedSegment.content: str`, the load-bearing **`nonce_source: Callable[[], HexNonce]`**
  constructor seam (AC-7), `_TRUNCATION_CAPS: Final[dict[SourceKind, int]]`,
  `SourceKind: TypeAlias = Literal[7 names]`, the `CanaryResult = Annotated[CanaryClean | CanaryCollision, Field(discriminator="kind")]`
  discriminated union, and the AC-15 in-body delimiter backstop emitting
  `CanaryCollision(pattern_id="fence.delimiter_in_body")` when the close-tag
  for the per-invocation nonce appears verbatim in the payload body. The
  nonce-no-escape Hypothesis property (AC-8) is the per-call invariant S7-09's
  corpus test extends across hundreds of payloads.
- **S2-03 (HARDENED)** ships `CanaryGuard.scan(payload: str, nonce: HexNonce) -> CanaryResult`
  over `INJECTION_PATTERNS: Final[tuple[tuple[str, bytes], ...]]` (≥ 50 entries
  with `(pattern_id, bytes)` shape), `scan_pure(payload, patterns) -> CanaryResult`,
  the import-time `_validate_patterns` guard (V4 no-shadowing), and the
  `tests/adv/test_canary_bypass_via_truncation.py` seed (V6 relocated from
  `tests/adversarial/`). S2-03 explicitly defers the 200+ adversarial corpus to S7-09.
- **S1-02 (HARDENED)** ships the closed `PlanProposal` discriminated union
  with `PlanProposalDepBump.manifest_path: SandboxedRelativePath`. The smart
  constructor raises `pydantic.ValidationError` with **distinct, stable**
  keywords (F9) — `path` / `escape` for path-escape, `64 KB` / `exceeds` for
  size, `binary`, `no-op`, `empty`, etc. **`LeafProtocolViolation` is the leaf
  adapter's exception** (S3-02), not the smart constructor's — confusing them
  is exactly the mistake S7-09's draft made.
- **S4-05 (HARDENED)** ships `codegenie.rag.provenance.verify(record, spanning_log) -> bool`
  as a **module-level pure function** — there is no `RecordProvenance.verify(...)`
  staticmethod (B3 in S4-05's own validation). The `RagRecordChainOrphan`
  `WorkflowInternalEvent` variant carries `record_id`, `record_event_chain_head`,
  `spanning_log_head` (S4-05 AC-3).
- **S5-01 (HARDENED)** ships `SolvedExampleRetriever.query(advisory, repo_ctx) -> RetrievalOutcome`
  using `RagHitEvent`/`RagDegradedEvent`/`RagMissEvent`/`RagCandidateSelectedEvent`
  /`RagRecordChainOrphan`. **Orphan events are emitted per excluded record
  (NOT collapsed)** — AC-6/AC-7. The discriminator literal is `kind: Literal["hit","miss","degraded"]`
  (S1-04), **not** the `"rag_miss"` / `"rag_degraded"` shape S7-09's draft used.
  `RagHit.few_shot` carries a `FencedSegment` whose body is `.content` (S2-02 AC-4),
  not `.fenced_content`.
- **S7-06 (HARDENED)** ships `tests/integration/_phase4_e2e_helpers.py` with
  the typed `WorkflowInternalEvent` parser kernel; S7-07/S7-08 inherited the
  "extend additively, no kernel edits" Open/Closed-at-the-file-boundary
  framing. S7-09 carries it forward as AC-11.

**Codebase reality verified 2026-05-24.**

- `tests/adv/` exists with Phase-2 adversarial work (`tests/adv/phase02/`),
  `_helpers.py`, `conftest.py`, and ~12 test files. `tests/adversarial/`
  does **not** exist; the arch's mention of it is the same doc-vs-code drift
  S2-03 V6 already absorbed.
- `adv` and `phase02_adv` are registered markers in `pyproject.toml`
  (`addopts = -m "not bench and not phase_7_preview" --strict-markers`).
- `src/codegenie/fallback/` and `src/codegenie/rag/` do not yet exist —
  S7-09's predecessors (S2-02/S2-03/S4-05/S5-01) are HARDENED but unshipped.
  S7-09's executor will land after the predecessors green.

**Phase / arch constraints (in-scope for this story).**

- ADR-0013: scan-untruncated-first; in-body delimiter backstop; functional-core/
  imperative-shell — already shipped by S2-02/S2-03; S7-09 asserts on the
  observable consequences.
- ADR-0001: `PlanProposal` smart constructor rejects illegal shapes at the
  Pydantic boundary, not after engine dispatch.
- ADR-0016: chain-head provenance verification — the chain-orphan path.
- ADR-0006 + ADR-0012: out-of-scope adversarial coverage (S3-03 ships
  EgressGuard tests; S7-06 ships ProvenanceGate end-to-end).

**Phase exit criteria S7-09 contributes to.** `High-level-impl.md §Step 7
§Done criteria`: "Adversarial suite (`-m adv`): 200+ injection payloads → 0
escapes; 50+ red-team prompts → 0 successes (any `PlanProposal` outside
`SandboxedPath` is a failure)." The phrasing "outside `SandboxedPath`" should
have been "fails `SandboxedRelativePath` smart-constructor validation" in the
draft (S1-02 F1: `SandboxedRelativePath` is the LLM-emittable string type, not
`SandboxedPath` which is the sandbox-jailed capability).

**Open ambiguities at Stage 1:** none.

## Findings by critic

### Coverage critic

- **CO-B1 (block)** — AC-1's "(a) or (b)" disjunction is structurally vacuous.
  Per S2-02 AC-6 step 4 the close-delimiter `</UNTRUSTED_INPUT id={nonce}>`
  always appears once at the end of `result.content`; `tag not in out.content`
  is always `False`. The test passes for any implementation, including one that
  does no fencing at all (any string suffix would satisfy the substring check).
  **Fix:** rewrite to S2-02 AC-8 nonce-no-escape semantics — open count == 1
  and close count == 1, with the `nonce_source` seam pinning the test nonce
  deterministically.
- **CO-B2 (block)** — `RetrievalOutcome` discriminator literals: `"rag_miss"`
  / `"rag_degraded"` / `"rag_hit"` are wrong; S1-04 ships `kind: Literal["hit","miss","degraded"]`.
- **CO-B3 (block)** — Orphan event count: S5-01 emits ONE event PER excluded
  record (not collapsed); AC-3's "exactly once" is well-defined only for a
  single seeded orphan. Multi-orphan companion needed for the all-orphan path.
- **CO-H1 (harden)** — No per-row `expected_outcome` parametrization. The
  OR-disjunction in the original AC-1 silently swallows drift. Same pattern as
  S2-03 V8's per-pattern_id assertion.
- **CO-H2 (harden)** — No event-payload assertion on `RagRecordChainOrphan`
  beyond presence; the typed payload (`record_id`, `record_event_chain_head`,
  `spanning_log_head`) is the contract S4-05 AC-3 shipped.
- **CO-H3 (harden)** — No event-absence companion on the orphan test
  (`RagHitEvent` / `RagDegradedEvent` must NOT fire for an orphan record).
- **CO-H4 (harden)** — `test_canary_bypass_via_truncation.py` hardcoded "seven
  source kinds" instead of `get_args(SourceKind)` — adding a literal regresses
  coverage silently. Same root as S2-02 AC-3 hardening.
- **CO-H5 (harden)** — No happy-path row in `test_plan_path_escape.py` — an
  over-zealous validator rejecting all paths would silently pass AC-5.
- **CO-H6 (harden)** — No deliberate delimiter-backstop corpus row (AC-13).
  Hypothesis random text reaches the literal close-delimiter with
  probability ≈ 2⁻¹²⁸; deliberate construction is the only way.

### Test-Quality critic

- **TQ-B1 (block)** — `CanaryGuard.scan(text, nonce).is_collision()` —
  there is no `is_collision()` method and no `is_collision` attribute. The
  result is a discriminated union: `isinstance(result, CanaryCollision)` or
  `result.kind == "collision"` per S2-02 AC-5.
- **TQ-B2 (block)** — `FenceWrapper()` constructed with no arguments — S2-02
  AC-7 requires `scanner`, `event_log`, and (for deterministic tests) the
  `nonce_source` seam. The fixture's `HexNonce("0" * 32)` is dead code: the
  fence's internal nonce is whatever the (missing) `nonce_source` returns.
- **TQ-B3 (block)** — `pytest.raises(LeafProtocolViolation, match="path_escape")`
  on `PlanProposalDepBump.model_validate` — never fires; the actual exception
  is `pydantic.ValidationError` with keyword `path` / `escape` per S1-02 AC-4 F9.
- **TQ-B4 (block)** — `event_log.events` and `e.kind == "..."` — dict-shuffling
  through an untyped attribute. The real `EventLog` exposes `replay()` and
  events are typed `WorkflowInternalEvent` variants. Use
  `pydantic.TypeAdapter(WorkflowInternalEvent)` per S7-06 / S7-07 precedent +
  CLAUDE.md "no untyped `dict` shuffling" load-bearing commitment.
- **TQ-B5 (block)** — Corpus rows as bare `dict`s. Per CLAUDE.md + S7-06 AC-15,
  use typed Pydantic models loaded via `TypeAdapter`.
- **TQ-H1 (harden)** — `[evt] = ...` unpacking fails with cryptic
  `ValueError: not enough values to unpack` on 0/2+ events. Use explicit
  `len(...) == 1, f"diagnostic"` per Global Rule 12 (fail loud with a typed
  message).
- **TQ-H2 (harden)** — `outcome.few_shot.fenced_content` — field name is
  `content` per S2-02 AC-4. Even after the type fix, the assertion
  `payload_tag.count(...) <= 1` is a count-comparison-trap: a single
  attacker-injected close-tag plus the fence's own one would yield 2, but a
  payload with multiple injection attempts could push to 3+ and the test
  silently allows up to 1.
- **TQ-H3 (harden)** — `_load_corpus()` called at parametrize time — a
  malformed YAML row fails collection with `KeyError`, not a typed parsing
  error. AC-10 pins typed loading.
- **TQ-H4 (harden)** — No assertion that the in-body backstop fires (`CanaryCollision`
  event with `pattern_id="fence.delimiter_in_body"`) for the runtime-inject
  test. Without it, AC-4 passes for an implementation where the canary never
  fires on the rag-retrieved record.

### Consistency critic

- **CN-B1 (block)** — `tests/adversarial/` is the wrong directory; codebase
  ships `tests/adv/` (S2-03 V6). Every path in ACs, TDD, Files-to-touch,
  Out-of-scope, and Notes needs correction.
- **CN-B2 (block)** — `RecordProvenance.verify` in Depends-on is wrong. S4-05
  ships `codegenie.rag.provenance.verify` as a module-level function.
- **CN-B3 (block)** — `LeafProtocolViolation(sub_reason="path_escape")` is
  not the exception or attribute shape the smart constructor raises (S1-02 F9).
- **CN-B4 (block)** — `kind in {"rag_miss", "rag_degraded"}` — literals are
  `"miss"` / `"degraded"` (S1-04).
- **CN-B5 (block)** — `(any PlanProposal outside SandboxedPath is a failure)`
  in the goal — `SandboxedRelativePath` is the LLM-emittable string type
  (S1-02 F1); `SandboxedPath` is the sandbox-jailed capability and cannot be
  emitted by an LLM. (Minor framing; not a TDD bug.)
- **CN-B6 (block)** — Files-to-touch `package_id` / `from_version` field names
  on `PlanProposalDepBump` — per S1-02 AC-3 the fields are `package` /
  `target_version` (no `from_version`).
- **CN-H1 (harden)** — Out-of-scope claims `tests/adversarial/test_egress_guard.py`
  exists. The S3-03 test is at `tests/adv/test_egress_guard.py`.
- **CN-H2 (harden)** — Arch doc says `tests/adversarial/`; codebase says
  `tests/adv/`. Surface as a known drift in the story's narrative, not silently.

### Design-Patterns critic

- **DP-B1 (block)** — Dict-shuffling event parsing — typed-union `match` is
  the established convention per S7-06 / S7-07 / S8-02. Same root as TQ-B4.
- **DP-H1 (harden)** — `_corpora/_load.py` introduced as a refactor afterthought.
  Rule-of-three is reached at S7-09 (three corpora: injection, red-team,
  truncation-probes). Promote to AC-11 with the kernel-extract observable
  AC ("adding a new corpus requires zero edits to existing loader bodies").
- **DP-H2 (harden)** — Per-row `expected_outcome` parametrization is the
  type-system-driven extension. Same root as CO-H1.
- **DP-H3 (harden)** — No extension-by-addition assertion against
  `_phase4_e2e_helpers.py`. Mirrors S7-06 AC-18 / S7-07 DP-6. Add to AC-11.
- **DP-H4 (harden)** — Exception-class discipline (`ValidationError` vs
  `LeafProtocolViolation`) — surface in Notes as the layer-discriminator. Same
  root as TQ-B3 / CN-B3, but the design framing prevents drift in future stories.
- **DP-H5 (harden)** — `isinstance` vs `.kind` literal-comparison ergonomics —
  prefer `isinstance` (mypy --strict typed), surface in Notes.
- **DP-N1 (nit)** — `_corpora/` framed as an Open/Closed extension point in
  Notes (Phase 5/7/7.5 future-loaders) — not an AC; the rule-of-three threshold
  on YAML corpora is not yet reached; only the loader-kernel is mandated now.

## Research briefs

None — Stage 3 not invoked (every fix has a verbatim sibling-story precedent).

## Conflict resolutions

No critic-vs-critic conflicts. Coverage and Design-Patterns harmonised on
per-row `expected_outcome` (CO-H1 ≡ DP-H2). Coverage and Test-Quality harmonised
on event-payload assertions. Design-Patterns' rule-of-three call (three corpora)
is a clean upgrade of the original refactor-step; Rule 2 (Simplicity First)
does not override because three concrete consumers exist at story-land time
(not speculative).

The arch doc says `tests/adversarial/`; the codebase says `tests/adv/`; this
is a Consistency-vs-Consistency near-conflict resolved by source-of-truth
priority: the codebase wins, the arch is flagged as known drift (the same
resolution S2-03 V6 made; this story honors that precedent rather than
re-litigating it). A follow-up cleanup task to update the arch doc is left
for a documentation pass — out of scope for S7-09 (Rule 3 — surgical changes).

## Edits applied

### Edit 1 — Status + Depends on
- Source: CN-B1, CN-B2
- Before: `Status: Ready` + Depends-on naming `RecordProvenance.verify`
- After: `Status: HARDENED` + Depends-on enumerates exact API names from each
  HARDENED sibling story, including the `nonce_source` seam, the
  `(pattern_id, bytes)` shape, the per-record orphan emission contract, and
  the smart-constructor `ValidationError` discipline
- Rationale: explicit API anchors prevent the executor from regressing to the
  drafts' incorrect names

### Edit 2 — Validation notes block (new)
- Source: editor.md format
- Inserted: full `Validation notes` block under the header listing V1–V10
  blocking fixes + hardenings + nits, with cross-references to the sibling
  validation reports

### Edit 3 — Context paragraph
- Source: CN-B1, CN-B2, CN-B5
- Before: `tests/adversarial/` paths; `PlanProposal.diff` field reference;
  ambiguous reference to `SandboxedPath`
- After: `tests/adv/` everywhere; `PlanProposal.manifest_path`; explicit note
  on the arch's `tests/adversarial/` drift; clarification that the smart
  constructor catches at `model_validate` time, not at engine dispatch

### Edit 4 — References block
- Source: CN-B1, CN-B2, CN-B6, DP-H3
- Before: incorrect paths, wrong field names, wrong helper-module classification
- After: corrected paths; field names from each HARDENED sibling story;
  explicit "do not edit" line on `tests/integration/_phase4_e2e_helpers.py`
  (S7-06 Open/Closed framing)

### Edit 5 — Goal paragraph
- Source: CN-B5
- Before: "outside `SandboxedPath` is a failure"
- After: "any malicious-shaped `PlanProposal` that survives `model_validate`
  is a failure" — anchored on the actual observable

### Edit 6 — AC list (full rewrite of 11 ACs → 15 ACs)
- Source: every critic finding
- Before: 11 ACs (numbered as 13 by the original "all six tests" / "corpus
  attribution" / "meta-test" / "no network" / "make check" / "TDD red tests"
  rows; in practice 12 distinct ACs)
- After: 15 ACs (AC-1..AC-15) — every original concern preserved with stricter
  observables; new ACs for typed corpus models (AC-10), corpus-loader kernel
  + extension-by-addition (AC-11), source-attribution structural meta-test
  (AC-12), delimiter-backstop deliberate row (AC-13), no-network AST-walker
  (AC-14), `make check` clean (AC-15)
- Rationale: each AC is now individually verifiable and the suite collectively
  closes the threat surface. The OR-disjunction smell, the `is_collision()`
  method, the `LeafProtocolViolation`, the wrong literals, the wrong directory,
  the dict-shuffling, and the unguarded helper-kernel are all closed.

### Edit 7 — Implementation outline
- Source: DP-H1, DP-H3, TQ-B4, TQ-B5
- Before: corpus-loader extract listed as a refactor afterthought; YAML rows
  loaded as dicts; no typed-event-parser callout
- After: ordered nine-step plan starting with reading the precedent files,
  building `_models.py` + `_load.py` + the three YAML corpora, then the six
  test files (each described concretely), then the three meta-tests, then
  green-iteration + Global-Rule-12 fail-loud discipline

### Edit 8 — TDD plan (red snippets)
- Source: every TQ/CN block
- Before: snippets referenced `is_collision()`, `LeafProtocolViolation`,
  `outcome.kind in {"rag_miss", ...}`, `event_log.events`, untyped dicts,
  `outcome.few_shot.fenced_content`, `tests/adversarial/`
- After: snippets use the `nonce_source` seam, typed `isinstance` /
  `pydantic.TypeAdapter(WorkflowInternalEvent)` event parser, `pytest.raises(ValidationError, match=...)`,
  the correct literal `"miss"`, the typed corpus loader, `outcome.few_shot.content`,
  `tests/adv/`. The `test_canary_bypass_via_truncation.py` snippet is annotated
  "EXTEND, do not rewrite" so the executor preserves the S2-03 seed rows.
- Added: `_models.py`, `_load.py`, `test_red_team_prompts.py`,
  `test_adversarial_corpus_sizes.py` snippets (the original only had four)

### Edit 9 — Green + Refactor sections
- Source: DP-H1, fail-loud rules
- Before: refactor mentioned `_load.py` and a README
- After: green section explicitly directs executor to surface escapes via
  Global Rule 12 (no row deletion); refactor section drops `_load.py`
  (now AC-11) and pins the synthetic-corpus extension test (`test_corpora_open_closed.py`)
  as the Open/Closed proof

### Edit 10 — Files to touch
- Source: CN-B1, DP-H3, AC list rewrite
- Before: 10 rows, all under `tests/adversarial/`
- After: 16 rows, all under `tests/adv/`; explicit `_models.py` / `_load.py` /
  `conftest.py` / the three meta-tests + the synthetic-corpus extension test;
  "no edits to" footer listing S7-06 helpers + S2-02/S2-03/S4-05/S5-01 source
  files (extension-by-addition + Open/Closed at the file boundary)

### Edit 11 — Out of scope
- Source: CN-H1, DP-H3
- Before: ambiguous "live red-team" + S3-03's egress at the wrong path
- After: corrected paths; explicit "no edits to S7-06 helpers"; multi-orphan
  corpus row scoped as a parametrized companion (not a YAML row)

### Edit 12 — Notes for the implementer
- Source: DP-H4, DP-H5, DP-N1
- Before: brief notes on payload-as-finding, sizes, citations, RAG model digest
- After: same plus exception-class discipline (`ValidationError` vs
  `LeafProtocolViolation` — layer-discriminator); `isinstance` over `.kind`
  literal; extension-by-addition framing of `tests/adv/_corpora/` for
  future-phase corpora; cross-link to S7-05 for model-digest pinning;
  red-team scenario YAML format example

## Verdict rationale

**HARDENED.** Ten block-class drifts + fifteen harden-class mutation-resistance
holes + three nits, all in-place-fixable. The goal traces verbatim to
`phase-arch-design.md §"Adversarial tests"` + `High-level-impl.md §Step 7`;
the AC set after hardening covers the phase exit-criterion observable ("200+
injection payloads → 0 escapes; 50+ red-team prompts → 0 successes") at the
right layer (smart constructor + fence/canary chain + retriever) with
per-row `expected_outcome` discipline that the original OR-disjunction
masked.

The story now (a) consumes the existing kernels (`FenceWrapper.fence` +
`nonce_source` seam, `CanaryGuard.scan` + `CanaryResult` discriminated union,
`PlanProposal*.model_validate` + `ValidationError` distinct-keyword,
`SolvedExampleRetriever.query` + per-record orphan emission,
`codegenie.rag.provenance.verify`, the S7-06 typed `WorkflowInternalEvent`
parser); (b) introduces exactly one new kernel at the rule-of-three threshold
(the corpus loader); and (c) leaves an Open/Closed extension path
(`_corpora/` + `_models.py` + `_load._MODELS` dispatch dict) for Phase 5/7/7.5
adversarial corpora without kernel-helper edits.

## Recommended next step

`phase-story-executor` to implement. The story is now ready: every AC is
individually verifiable, the TDD red snippets compile against the actual
shipped sibling APIs, the typed corpus models prevent the dict-shuffling
trap, the `nonce_source` seam pins determinism, the in-body backstop is
deliberately exercised (AC-13), and the Open/Closed property is exercised
in CI (AC-11). The executor should attend to the per-row `expected_outcome`
parametrization in particular — a corpus row whose actual outcome diverges
from its declared expectation is a security finding that must surface per
Global Rule 12.
