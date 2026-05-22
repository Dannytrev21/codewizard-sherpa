# Story S1-01 — Newtype + smart-constructor substrate

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Done — 2026-05-22 (phase-story-executor; see [`_attempts/S1-01.md`](_attempts/S1-01.md) for the per-AC evidence table + gate log — Phase-4 identifier substrate landed with 11 new NewTypes, 8 smart constructors, exact `__all__` / `_NEWTYPE_REGISTRY` reconciliation, mypy swap-negative tests, Hypothesis parser properties, and the raw-domain-annotation fence. Story-scoped gates green: 419 type tests, 374 fence tests, `mypy --strict src/codegenie/types`, `ruff`, and `lint-imports`. Full `make check` reached 6085 passed / 40 skipped / 9 xfailed but failed on a pre-existing local timing threshold in `tests/adv/test_tsconfig_pathological.py::test_gather_under_pathological_tsconfig_silently_swallows_under_two_seconds` at 2.06–2.65s on macOS, outside this story's touched surface.)
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001 (closed-sum `PlanProposal` consumes `SandboxedRelativePath`, `SemverString`, `PackageId` — never raw `str`), ADR-0010 (Phase-4 `BudgetToken` is capability-typed — `BudgetTokenId` newtype), ADR-0014 (cassette discipline — `CassetteId` newtype), ADR-0016 (chromadb/YAML canonical — `StoreDigest`, `ChainHead`, `BlobDigest`)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 12 — 3 blocks, 6 hardens, 3 nits

Changes applied:
- **F1 (block)** — AC-15 rewritten: Phase 4 appends to the **existing** shared `_NEWTYPE_REGISTRY`; a separate `_PHASE4_NEWTYPE_REGISTRY` would fork an established convention (Phase 7 extended the same dict) and break the existing `test_identifiers_phase3.py::test_newtype_registry_matches_all`.
- **F2 (block)** — AC-19 added + Files-to-touch extended: adding 11 names to `identifiers.__all__` breaks the existing `test_all_is_exact_set` and `test_newtype_registry_matches_all`; the story MUST update `tests/unit/types/test_identifiers_phase3.py` or AC-18 (`pytest` passes) is unsatisfiable.
- **F3 (block)** — AC-2 fixed: `EmbeddingVector` is `NewType("EmbeddingVector", tuple)` over the **bare** `tuple`. `NewType` over a *parametrized* `tuple[float, ...]` is unsupported by `mypy --strict` — the same file already proves this (`ProvenanceAdapterId` is a `TypeAlias` for exactly this reason). The original AC-2 failed AC-18.
- **F4 (harden)** — AC-3 + outline: `parse_budget_token_id` and `parse_model_id`'s regex match route through `_regex_parser` closures; a direct `.fullmatch` breaks the existing `test_only_one_fullmatch_outside_helper`.
- **F5 (harden)** — AC-8 mypy-negative test mirrors the precedent's `_ctor_arg` helper and adds non-`str`-backed swap pairs (`Similarity`, `TokenCount`).
- **F6 (harden)** — AC-13 fence skeleton also walks function-arg + return annotations (the AC prose promises "function signature" coverage).
- **F7 (harden)** — AC-13 `_DOMAIN_KEYWORDS` roster reconciled between prose and skeleton code.
- **F8 (harden)** — AC-16 references the existing `test_module_purity.py` instead of re-listing a stale import set (it omitted `collections.abc`); Phase 4 adds no new imports to `parsers.py`.
- **F9 (harden)** — "twelve" corrected to **eleven** new newtypes throughout; `BlobDigest`/`WorkflowId` are Phase-3-owned and reused.
- **F10 (harden)** — `parse_token_count` rejects `bool` (mirrors `parse_attempt_number`; `True`/`False` are `int` instances).
- **F11 (nit)** — AC-12 parametrizes over all eleven newtypes (all `NewType`s raise `TypeError` under `isinstance`).
- **F12 (nit)** — AC-11 clarified: the exact-set guard lives in the updated `test_identifiers_phase3.py`.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S1-01-newtype-smart-constructor-substrate.md

## Context

Phase 4 introduces the first LLM-produced bytes the system applies and the first vector substrate the system reads — both surfaces are dense with identifier-shaped strings (response ids, budget tokens, model digests, cassette paths, embedding vectors, chain heads, similarity scores) that the existing Phase-2 `codegenie.types.identifiers` roster has no entries for. Production ADR-0033 (and Phase-3 S1-01's precedent) is unambiguous: a `BudgetTokenId ↔ LeafResponseId` swap at any call site is a runtime bug `mypy --strict` cannot catch when both are raw `str`. This story lands every Phase-4 newtype + smart constructor in **one** canonical home so every later Step 1 story (S1-02 `PlanProposal`, S1-03 `PlanOutcome`, S1-04 RAG models, S1-05 fence amendment) imports its typed primitives from there.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model` — the exhaustive newtype roster (`SolvedExampleId`, `EmbeddingVector`, `StoreDigest`, `Similarity`, `ModelId`, `TokenCount`, `LeafResponseId`, `BudgetTokenId`, `CassetteId`, `HexNonce`, `BlobDigest`, `ChainHead`) and `WorkflowId` re-export note.
  - `../phase-arch-design.md §Goals — G6` — "Newtype discipline at every domain primitive."
  - `../phase-arch-design.md §Design patterns applied` row 4 — Newtype pattern justification.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` — `PlanProposal` fields are typed against these newtypes; raw `str` defeats the closure.
  - `../ADRs/0010-llm-invocation-guard-budget-token-capability.md` — `BudgetTokenId` is the capability's identity; uuid4-shaped.
  - `../ADRs/0014-cassette-discipline-security-control.md` — `CassetteId` is the relpath key in `cassettes.lock`.
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — `StoreDigest`, `ChainHead`, `BlobDigest` are BLAKE3 hex strings.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — the parent rule this story instantiates for Phase 4.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/types/identifiers.py` — Phase 2 home. **Append**, do not fork. Match the existing `NewType("X", str)` + module-level `__all__` + docstring-naming-ADR convention.
  - `src/codegenie/result.py` — canonical `Result[T, E] = Ok[T] | Err[E]` (Phase-2 S1-04). Smart constructors return `Result`.
  - `src/codegenie/types/errors.py` (created by Phase-3 S1-01) — canonical `ParseError`. Re-use; do not fork.
  - `src/codegenie/types/parsers.py` (created by Phase-3 S1-01) — precedent for the `_regex_parser` helper + `parse_<x>` shape.
  - `tests/unit/types/test_identifiers.py`, `tests/unit/types/test_identifiers_phase3.py` — family-symmetric closures (round-trip, pairwise distinctness, `__name__` pinning, exact-set `__all__`, identity passthrough, `isinstance` TypeError, NFKC adversarial, AST source-scan).
- **Source design:**
  - `../final-design.md §Synthesis ledger row 1` — newtype-everywhere is the synthesis decision; Phase 4 is where the LLM/RAG primitives enter the catalog.

## Goal

Extend `codegenie.types.identifiers` with twelve Phase-4 newtypes and pair each one with a smart-constructor returning `Result[T, ParseError]` (where well-defined), so every later Step 1 story (and every Phase-4 module) imports its typed primitives from one canonical home and `mypy --strict` rejects cross-newtype swaps.

## Acceptance criteria

### Catalog + module shape

- [ ] AC-1 — `src/codegenie/types/identifiers.py` exports **eleven new** names: `SolvedExampleId`, `EmbeddingVector`, `StoreDigest`, `Similarity`, `ModelId`, `TokenCount`, `LeafResponseId`, `BudgetTokenId`, `CassetteId`, `HexNonce`, `ChainHead`. `BlobDigest` **and** `WorkflowId` already exist (Phase-3 S1-01 shipped both — verified present in `identifiers.py.__all__` + `_NEWTYPE_REGISTRY` as of 2026-05-21) — **do not redefine**. This story re-uses `BlobDigest` for `advisory_digest` / `transform_digest` / `trust_outcome_digest` / `Embedder.model_digest()` and `WorkflowId` as-is; both are no-ops here. The roster constant `PHASE4_NAMES` (in the TDD plan below) therefore has exactly **eleven** members and excludes `BlobDigest`/`WorkflowId`. (validator: corrected — original said "twelve" and listed `BlobDigest` as new; F9)
- [ ] AC-2 — Each newtype's runtime backing type is the simplest faithful one: `EmbeddingVector` is `NewType("EmbeddingVector", tuple)` over the **bare, unparametrized** `tuple` — **not** `NewType("EmbeddingVector", "tuple[float, ...]")`. `NewType` over a *parametrized* generic (`tuple[float, ...]`, quoted or not) is rejected by `mypy --strict` ("NewType cannot be used with a parameterized type"); the same module already proves this — `ProvenanceAdapterId` is a `TypeAlias`, not a `NewType`, with an in-file comment stating "`NewType` over a generic tuple is unsupported in mypy --strict". Backing it with the bare `tuple` keeps `EmbeddingVector` a true `NewType` (distinct, has `.__name__`, `isinstance`-raises) so it stays family-symmetric with the other ten — a `TypeAlias` would silently fail AC-9/AC-10. The `float` element type and 384-dim shape are documented in the newtype's docstring; `tuple` (not `tuple[float, ...]`) at the kernel keeps `identifiers.py` stdlib-only (numpy stays out of the kernel) and shape/dtype validation is S4-01's job (AC-4). `Similarity` is `NewType("Similarity", float)`; `TokenCount` is `NewType("TokenCount", int)`; every other name is `NewType("X", str)`. (validator: corrected — original `NewType("EmbeddingVector", "tuple[float, ...]")` fails AC-18 `mypy --strict`; F3)
- [ ] AC-3 — `src/codegenie/types/parsers.py` ships eight new smart constructors, each a pure function returning `Result[<X>, ParseError]`:
  - `parse_solved_example_id(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex of canonical YAML body; lowercase only).
  - `parse_store_digest(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex; same shape as `SolvedExampleId`).
  - `parse_chain_head(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex).
  - `parse_similarity(x: float)` — `Ok` iff `-1.0 <= x <= 1.0`; otherwise `Err`. **NaN and ±inf rejected.** Also rejects `bool` (`True`/`False` are `int` instances; `parse_similarity(True)` would otherwise pass the range check — mirror the `isinstance(n, bool)` guard `parse_attempt_number` already ships).
  - `parse_model_id(s)` — `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?:-\d{8})?$` (vendor model slugs like `claude-sonnet-4-5-20250929`); lowercase; max length 128. NFKC-preflight per AC-14, **then** the regex `.fullmatch` runs through a `_regex_parser` closure (`_model_id_match`) — exactly the `parse_branch_name` shape (NFKC preflight + `_branch_match` closure). A direct `.fullmatch` is forbidden by the existing `test_only_one_fullmatch_outside_helper`.
  - `parse_token_count(n: int)` — `Ok` iff `n >= 0` and `n <= 2**31 - 1` (non-negative; sentinel-friendly upper bound). Rejects non-`int` and `bool` — `not isinstance(n, int) or isinstance(n, bool)` — byte-for-byte the guard `parse_attempt_number` ships, so `parse_token_count(True)` is `Err`, not `Ok(TokenCount(True))`.
  - `parse_budget_token_id(s)` — uuid4 canonical form `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`. This is a regex parser — it routes through a `_regex_parser` closure (`_uuid4_match = _regex_parser(_UUID4_RX, max_len=36, name="BudgetTokenId")`), **not** a hand-written `.fullmatch` (which would break `test_only_one_fullmatch_outside_helper`).
  - `parse_hex_nonce(s)` — `^[0-9a-f]{32}$` (16 bytes hex; canary nonce per arch §3 truncation table).

  (validator: hardened — `parse_budget_token_id`/`parse_model_id` are regex parsers and must route through `_regex_parser`; `parse_token_count`/`parse_similarity` reject `bool`; F4 + F10)
- [ ] AC-4 — Three newtypes have **no parser this story** — `EmbeddingVector` (constructed only inside `rag/embedder.py` from ONNX output and shape-validated there, S4-01); `LeafResponseId` (constructed only by `AnthropicLeafAdapter` from the SDK response, S3-02); `CassetteId` (constructed only by `CassetteSanitizer` from relpath, S3-04). Document the deferral in the docstring of each newtype with the consumer story id.
- [ ] AC-5 — `src/codegenie/types/__init__.py` re-exports all twelve new names so `from codegenie.types import SolvedExampleId, BudgetTokenId, ...` resolves. Identity passthrough — `codegenie.types.X is codegenie.types.identifiers.X` for every new name.

### Verification — family-symmetric closures (from Phase-3 S1-01 precedent)

- [ ] AC-6 — **Round-trip:** for every parser and every happy-path input `s`, `parse_<x>(s) == Ok(value=X(s))`.
- [ ] AC-7 — **Rejection:** every parser has ≥ 1 parametrized deliberately-bad input → `Err(ParseError(value=...))`. The table covers (at minimum):
  - `parse_solved_example_id`: uppercase hex; wrong length; non-hex char.
  - `parse_similarity`: `1.0001`, `-1.0001`, `float("nan")`, `float("inf")`, `float("-inf")`, `True` (bool-not-float). (validator: added `True` — F10)
  - `parse_token_count`: `-1`, `2**31`, `"1"` (str-not-int), `True` (bool-not-int — `True` would otherwise become `TokenCount(True)`). (validator: added `True` — F10)
  - `parse_budget_token_id`: uuid1, uuid5, non-`4` version nibble, non-`[89ab]` variant nibble.
  - `parse_model_id`: uppercase letters; leading hyphen; trailing dot; > 128 chars.
  - `parse_hex_nonce`: 30 chars; 34 chars; uppercase hex.
- [ ] AC-8 — **Cross-newtype substitution = mypy error (executed in CI):** `tests/unit/types/test_phase4_identifiers_mypy_negative.py` writes a temp `.py` file per swap pair and subprocess-invokes `mypy --strict`, asserting non-zero exit and an `argument`/`incompatible type` diagnostic on stdout. Parametrized over ≥ 12 distinct Phase-4 swap pairs, **including the non-`str`-backed newtypes** — `Similarity ← raw float literal` (`0.9`), `TokenCount ← raw int literal` (`5`), and at least one swap each for `Similarity`/`TokenCount` against a `str`-backed newtype. Because the swap pairs mix `str`/`float`/`int`/`tuple` backings, the test **must** carry a per-name constructor-argument helper (`_ctor_arg(name)` → `"1"` for `TokenCount`, `"0.9"` for `Similarity`, `"()"` for `EmbeddingVector`, `'"x"'` for `str`-backed) — byte-for-byte the pattern the existing `test_identifiers_phase3_mypy_negative.py` already uses for its mixed `str`/`int` rows. A hardcoded `B("dummy")` template silently masks the intended diagnostic for non-`str` newtypes (it would fail with a *different* mypy error). `str`-backed pairs to cover at minimum: `BudgetTokenId ← LeafResponseId`, `StoreDigest ← ChainHead`, `HexNonce ← ChainHead`, `ModelId ← CassetteId`, `SolvedExampleId ← BlobDigest`, `BudgetTokenId ← CassetteId`, `LeafResponseId ← StoreDigest`, `CassetteId ← ModelId`, `ChainHead ← SolvedExampleId`, `HexNonce ← BudgetTokenId`. (validator: hardened — original `≥ 10` list named non-`str` newtypes the hardcoded `"dummy"` template could not exercise; F5)
- [ ] AC-9 — **`__name__` pinning:** for every new newtype `X`, `getattr(identifiers, "X").__name__ == "X"`.
- [ ] AC-10 — **Pairwise distinctness:** parametrized test over `PHASE2_NAMES | PHASE3_NAMES | PHASE4_NAMES` — every distinct pair `(A, B)` satisfies `A is not B`. Catches `BudgetTokenId = LeafResponseId = NewType("Id", str)` aliasing.
- [ ] AC-11 — **Exact-set `__all__`:** the exact-equality guard is the **existing** `test_identifiers_phase3.py::test_all_is_exact_set`, updated per AC-19 to fold in `PHASE4_NAMES` — i.e. `set(identifiers.__all__) == PHASE2_NAMES | PHASE3_NAMES | PHASE3_LITERAL_NAMES | PHASE7_NEWTYPE_NAMES | PHASE7_TYPE_ALIAS_NAMES | PHASE4_NAMES` (exact equality, not `⊇`; stowaway exports fail) **and** `identifiers.__all__ == sorted(identifiers.__all__)`. The new `tests/unit/types/test_phase4_identifiers.py::test_all_is_exact_superset_with_phase4` is a Phase-4-local *subset* sanity-check only (`PHASE4_NAMES <= set(__all__)`) — it does **not** stand in for the exact-set test, which already exists and must be amended, not duplicated. (validator: clarified — original implied a 3-roster equality that does not match the real 5-roster `__all__`; F12 + F2)
- [ ] AC-12 — **`isinstance` runtime TypeError pin:** for **every** one of the eleven Phase-4 newtypes, `with pytest.raises(TypeError): isinstance("foo", X)`. A `NewType` is a callable, not a class — `isinstance` against it raises `TypeError` regardless of the backing type, so `Similarity`/`TokenCount`/`EmbeddingVector` are covered identically to the `str`-backed eight. (validator: hardened — original excluded those three from the parametrized test for no functional reason, dropping three names from coverage; F11)
- [ ] AC-13 — **AST source-scan discipline (load-bearing for the "newtypes everywhere" cross-cutting rule):** new test `tests/fence/test_phase4_no_raw_str_for_domain_ids.py` walks every `.py` file under `src/codegenie/fallback/` and `src/codegenie/rag/` (once they exist) and asserts no raw `str`/`int`/`float`/`bytes` annotation is used for any name in the domain-id keyword roster, scanning **all three** annotation sites: (a) attribute / Pydantic-field / `dataclass`-field annotations (`ast.AnnAssign`), (b) **function-parameter annotations** (`ast.arg.annotation` on `ast.FunctionDef` / `ast.AsyncFunctionDef`), and (c) **function return annotations** (`FunctionDef.returns`). The skeleton in the TDD plan walks only `ast.AnnAssign`; it MUST be extended to (b) + (c) — the AC prose explicitly promises "function signature" coverage and a `def foo(cve_id: str)` would otherwise slip through every later Phase-4 story. The domain-id keyword roster is exactly (prose and skeleton code MUST agree — they currently disagree on `package`): `response_id`, `budget_token`, `cassette`, `chain_head`, `store_digest`, `embedding_model`, `similarity`, `tokens_in`, `tokens_out`, `nonce`, `solved_example_id`, `cve_id`, `package`, `manifest_path`. Story S1-01 lands the test skeleton with the offender list initially empty (`fallback/` and `rag/` don't exist yet); each subsequent Phase-4 story re-runs it. (validator: hardened — skeleton under-covered the AC's "function signature" promise and disagreed with the prose roster; F6 + F7)
- [ ] AC-14 — **NFKC + ASCII-only on `parse_model_id`:** `parse_model_id` NFKC-normalizes input before regex match and rejects any post-normalization byte > 0x7F (vendor slugs are ASCII; non-ASCII look-alike is an injection signal).
- [ ] AC-15 — The eleven Phase-4 newtypes are appended as new rows to the **existing single** `_NEWTYPE_REGISTRY: Final[Mapping[str, str]]` in `identifiers.py` — **not** a new `_PHASE4_NEWTYPE_REGISTRY` constant. `identifiers.py` has exactly one shared registry; Phase 7 S1-01 already extended this same dict (see its `# Phase-7 (S1-01 ...)` rows), and the existing `test_identifiers_phase3.py::test_newtype_registry_matches_all` asserts `set(_NEWTYPE_REGISTRY.keys()) == set(__all__) - PHASE7_TYPE_ALIAS_NAMES` — a forked `_PHASE4_NEWTYPE_REGISTRY` would both break that test and fork an established convention (Rule 7 / Rule 11). Each new row's value is a one-line docstring naming the relevant Phase-4 ADR (`ADR-0001`/`ADR-0010`/`ADR-0014`/`ADR-0016`) + consumer story. A Phase-4-local test asserts `PHASE4_NAMES <= _NEWTYPE_REGISTRY.keys()` and that every Phase-4 row's value contains a Phase-4 ADR citation; the existing `test_newtype_registry_matches_all` — updated per AC-19 — keeps the registry exact against `__all__`. (validator: rewritten — original prescribed a forked registry that breaks an existing test; F1)
- [ ] AC-16 — **Module purity:** Phase 4 adds **no new imports** to `parsers.py` — the eight new parsers need only `re`, `unicodedata`, `Result`/`Ok`/`Err`, `ParseError`, and the identifiers, all already imported. The guard is the **existing** `tests/unit/types/test_module_purity.py::test_parsers_module_imports_only_allowed` (it already pins the correct allowlist — note it includes `collections.abc`, which the originally-drafted AC-16 set omitted). Do **not** create a new purity test; just confirm the existing one stays green. No sibling-package imports; no logger; no filesystem. (validator: corrected — original re-listed a stale/incomplete import set and implied a duplicate test; F8)
- [ ] AC-17 — **Hypothesis property tests** in `tests/unit/types/test_phase4_parsers_properties.py`:
  - **Totality:** for any `s: str` drawn from `st.text(max_size=300)` (and any `x: float` for `parse_similarity`, `n: int` for `parse_token_count`), the parser never raises (`try/except Exception: pytest.fail(...)`).
  - **Determinism:** `parse_<x>(s) == parse_<x>(s)` for any drawn input.
  - **Round-trip identity for happy inputs:** for `s` drawn from `st.from_regex(parser_rx, fullmatch=True)`, `parse_<x>(s).unwrap() == <X>(s)`. For `parse_similarity`, draw `x` from `st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False)`.
  - **Similarity rejects non-finite:** `parse_similarity(float("nan"))` and `parse_similarity(float("inf"))` both `Err` (explicit Hypothesis case).
- [ ] AC-18 — `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files **and** the full `make check` gate is green (this story edits `identifiers.__all__`, which is fenced cross-file — see AC-19).
- [ ] AC-19 — **Cross-file fence reconciliation (load-bearing — without this, AC-18 cannot pass):** appending eleven names to `identifiers.__all__` and eleven rows to `_NEWTYPE_REGISTRY` breaks two assertions in the existing `tests/unit/types/test_identifiers_phase3.py`: `test_all_is_exact_set` (exact-set equality over the phase rosters) and `test_newtype_registry_matches_all` (`_NEWTYPE_REGISTRY.keys()` exact against `__all__`). This story MUST update that file: add a `PHASE4_NAMES` roster constant (the eleven names) and fold it into both assertions, mirroring how `PHASE7_NEWTYPE_NAMES` was added. The update is mechanical and additive — no existing Phase-2/3/7 roster entry changes. (validator: added — original Files-to-touch silently omitted this cross-file coupling, making AC-18 unsatisfiable; F2)

## Implementation outline

1. Append **eleven** `NewType` lines to `src/codegenie/types/identifiers.py`, each with a docstring naming the relevant Phase-4 ADR + consumer story (e.g., `# BudgetTokenId — landed for S2-05 LlmInvocationGuard issuer; ADR-0010.`). `BlobDigest` and `WorkflowId` are already exported (Phase-3 S1-01) — do not touch them. `EmbeddingVector` is `NewType("EmbeddingVector", tuple)` over the bare `tuple` (AC-2).
2. Append the eleven Phase-4 rows to the **existing** `_NEWTYPE_REGISTRY` dict in `identifiers.py` (AC-15) — do not create `_PHASE4_NEWTYPE_REGISTRY`.
3. Update `identifiers.__all__` to the sorted exact set (Phase-2 ∪ Phase-3 ∪ Phase-3-literals ∪ Phase-7 ∪ Phase-4).
4. Extend `src/codegenie/types/parsers.py` with the eight new `parse_<x>` smart constructors. Re-use the existing `_regex_parser` helper for **every** regex-shaped parser — the four hex-shaped (`parse_solved_example_id`, `parse_store_digest`, `parse_chain_head`, `parse_hex_nonce`), **plus** `parse_budget_token_id` (`_uuid4_match`) and the regex inside `parse_model_id` (`_model_id_match`, layered after NFKC preflight — the `parse_branch_name` shape). Only `parse_similarity` and `parse_token_count` (numeric range checks, no regex) are direct functions; `parse_token_count` reuses the `parse_attempt_number` `isinstance(n, int)/isinstance(n, bool)` guard. `.fullmatch(` must not appear outside `_regex_parser` (existing `test_only_one_fullmatch_outside_helper`).
5. Update `src/codegenie/types/__init__.py` to re-export the **eleven** new names (keep `__all__` sorted).
6. Update `tests/unit/types/test_identifiers_phase3.py` (AC-19): add a `PHASE4_NAMES` roster constant and fold it into `test_all_is_exact_set` and `test_newtype_registry_matches_all` — mechanical, additive, mirrors how `PHASE7_NEWTYPE_NAMES` was added.
7. Land `tests/unit/types/test_phase4_identifiers.py`: parametrized happy + sad paths; `__name__` pinning; pairwise distinctness across all phase rosters; identity-passthrough; `isinstance` TypeError over all eleven; the `PHASE4_NAMES <= _NEWTYPE_REGISTRY.keys()` registry check; NFKC on `parse_model_id`.
8. Land `tests/unit/types/test_phase4_identifiers_mypy_negative.py`: subprocess `mypy --strict` over a tmp swap file; parametrized over ≥ 12 Phase-4 swap pairs with a per-name `_ctor_arg` helper (AC-8).
9. Land `tests/unit/types/test_phase4_parsers_properties.py`: Hypothesis totality + determinism + round-trip-identity + non-finite-similarity rejection (AC-17).
10. Land `tests/fence/test_phase4_no_raw_str_for_domain_ids.py`: AST source-scan skeleton scanning `AnnAssign` **and** function-arg **and** return annotations (AC-13). `tests/fence/` already exists with `__init__.py` (Phase-3 S1-05 created it) — reuse it; only add `__init__.py` if absent.
11. Run `mypy --strict src/codegenie/types/` + `make check` locally — `make check` (not just the touched-file subset) is the real gate because of the AC-19 cross-file coupling.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/types/test_phase4_identifiers.py`

```python
from __future__ import annotations

import pytest

from codegenie.result import Err, Ok
from codegenie.types.errors import ParseError
from codegenie.types.identifiers import (
    BudgetTokenId, CassetteId, ChainHead, EmbeddingVector, HexNonce,
    LeafResponseId, ModelId, Similarity, SolvedExampleId, StoreDigest,
    TokenCount,
)
from codegenie.types.parsers import (
    parse_budget_token_id, parse_chain_head, parse_hex_nonce,
    parse_model_id, parse_similarity, parse_solved_example_id,
    parse_store_digest, parse_token_count,
)


PHASE4_NAMES = {
    "BudgetTokenId", "CassetteId", "ChainHead", "EmbeddingVector",
    "HexNonce", "LeafResponseId", "ModelId", "Similarity",
    "SolvedExampleId", "StoreDigest", "TokenCount",
}
# Plus BlobDigest if Phase 4 owns it; otherwise inherited from Phase 3.


# --- Happy paths (AC-6) ---

@pytest.mark.parametrize(
    "parser,good,wrapper",
    [
        (parse_solved_example_id, "a" * 64, SolvedExampleId),
        (parse_store_digest, "0" * 64, StoreDigest),
        (parse_chain_head, "f" * 64, ChainHead),
        (parse_hex_nonce, "0" * 32, HexNonce),
        (parse_model_id, "claude-sonnet-4-5-20250929", ModelId),
        (parse_budget_token_id, "12345678-1234-4abc-89ab-1234567890ab", BudgetTokenId),
    ],
)
def test_str_parser_happy(parser, good, wrapper):
    r = parser(good)
    assert isinstance(r, Ok)
    assert r.value == wrapper(good)


def test_similarity_happy_path():
    for x in (-1.0, -0.5, 0.0, 0.5, 0.85, 1.0):
        r = parse_similarity(x)
        assert isinstance(r, Ok)
        assert r.value == Similarity(x)


def test_token_count_happy_path():
    r = parse_token_count(0)
    assert isinstance(r, Ok) and r.value == TokenCount(0)
    r = parse_token_count(2**31 - 1)
    assert isinstance(r, Ok) and r.value == TokenCount(2**31 - 1)


# --- Rejection cases (AC-7) ---

@pytest.mark.parametrize(
    "parser,bad",
    [
        (parse_solved_example_id, "A" * 64),       # uppercase
        (parse_solved_example_id, "0" * 63),       # wrong length
        (parse_solved_example_id, "g" * 64),       # non-hex
        (parse_chain_head, ""),                    # empty
        (parse_hex_nonce, "0" * 30),               # short
        (parse_hex_nonce, "0" * 34),               # long
        (parse_hex_nonce, "A" * 32),               # uppercase
        (parse_model_id, "Claude-Sonnet"),         # uppercase
        (parse_model_id, "-leading-hyphen"),       # leading hyphen
        (parse_model_id, "trailing-dot."),         # trailing dot
        (parse_model_id, "x" * 129),               # too long
        (parse_budget_token_id, "12345678-1234-1abc-89ab-1234567890ab"),  # version=1
        (parse_budget_token_id, "12345678-1234-4abc-79ab-1234567890ab"),  # variant 7
    ],
)
def test_str_parser_rejects(parser, bad):
    r = parser(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


@pytest.mark.parametrize(
    "x",
    [1.0001, -1.0001, float("nan"), float("inf"), float("-inf")],
)
def test_similarity_rejects(x):
    r = parse_similarity(x)
    assert isinstance(r, Err)


@pytest.mark.parametrize("n", [-1, 2**31, -(2**31)])
def test_token_count_rejects(n):
    r = parse_token_count(n)
    assert isinstance(r, Err)


def test_token_count_rejects_non_int():
    r = parse_token_count("1")  # type: ignore[arg-type]
    assert isinstance(r, Err)


# --- Family-symmetric (AC-9..AC-12, AC-15) ---

def test_name_pinning():
    import codegenie.types.identifiers as ids
    for name in PHASE4_NAMES:
        assert getattr(ids, name).__name__ == name


def test_pairwise_distinct_across_all_phases():
    import codegenie.types.identifiers as ids
    # Build full roster — Phase-4 must not collide with Phase-2 or Phase-3.
    all_names = sorted({n for n in ids.__all__ if n != "PackageManager"})
    objs = [getattr(ids, n) for n in all_names]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            assert a is not b


def test_all_is_exact_superset_with_phase4():
    import codegenie.types.identifiers as ids
    assert PHASE4_NAMES.issubset(set(ids.__all__))
    # Exactness checked against the union of all phase rosters; this assertion
    # is the Phase-4 fragment.


def test_identity_passthrough_via_init():
    import codegenie.types as pkg
    import codegenie.types.identifiers as ids
    for name in PHASE4_NAMES:
        assert getattr(pkg, name) is getattr(ids, name)


@pytest.mark.parametrize("name", sorted(PHASE4_NAMES))
def test_isinstance_raises_typeerror(name):
    # AC-12 — every NewType (any backing) is a callable, not a class;
    # isinstance against it raises TypeError uniformly.
    import codegenie.types.identifiers as ids
    nt = getattr(ids, name)
    with pytest.raises(TypeError):
        isinstance("foo", nt)  # type: ignore[arg-type]


def test_phase4_rows_in_shared_registry():
    # AC-15 — Phase 4 appends to the EXISTING single _NEWTYPE_REGISTRY;
    # there is no separate _PHASE4_NEWTYPE_REGISTRY.
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY
    assert PHASE4_NAMES <= set(_NEWTYPE_REGISTRY.keys()), (
        f"Phase-4 names missing from _NEWTYPE_REGISTRY: {PHASE4_NAMES - set(_NEWTYPE_REGISTRY)}"
    )
    for name in PHASE4_NAMES:
        doc = _NEWTYPE_REGISTRY[name]
        assert any(adr in doc for adr in ("ADR-0001", "ADR-0010", "ADR-0014", "ADR-0016")), (
            f"{name} registry entry missing Phase-4 ADR citation: {doc!r}"
        )
```

The subprocess-mypy meta-test goes in `tests/unit/types/test_phase4_identifiers_mypy_negative.py` (mirror Phase-3 S1-01's `test_identifiers_phase3_mypy_negative.py`):

```python
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# (accepts_<A>) parameter swapped for a value of type <B>; mypy --strict must reject.
# Mixed backings: str / float / int / tuple. The per-name _ctor_arg helper
# mirrors test_identifiers_phase3_mypy_negative.py — a hardcoded B("dummy")
# would fail with the WRONG diagnostic for non-str newtypes.
SWAP_PAIRS = [
    ("BudgetTokenId", "LeafResponseId"),
    ("StoreDigest", "ChainHead"),
    ("SolvedExampleId", "BlobDigest"),
    ("HexNonce", "ChainHead"),
    ("ModelId", "CassetteId"),
    ("BudgetTokenId", "CassetteId"),
    ("LeafResponseId", "StoreDigest"),
    ("CassetteId", "ModelId"),
    ("ChainHead", "SolvedExampleId"),
    ("HexNonce", "BudgetTokenId"),
    ("Similarity", "TokenCount"),   # float param <- int newtype
    ("TokenCount", "Similarity"),   # int param <- float newtype
]
# Raw-literal swaps: a bare numeric literal leaking where a newtype is
# expected is the real bug class for the float/int-backed newtypes.
RAW_LITERAL_SWAPS = [
    ("Similarity", "0.9"),
    ("TokenCount", "5"),
]


def _ctor_arg(name: str) -> str:
    """Literal argument expression for ``name(...)`` — backing-type aware."""
    return {
        "Similarity": "0.9",
        "TokenCount": "1",
        "EmbeddingVector": "()",
    }.get(name, '"x"')


def _run_mypy(tmp_path: Path, src: str) -> subprocess.CompletedProcess[str]:
    tmp = tmp_path / "swap.py"
    tmp.write_text(textwrap.dedent(src))
    return subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("a,b", SWAP_PAIRS)
def test_mypy_rejects_phase4_swap(tmp_path: Path, a: str, b: str) -> None:
    result = _run_mypy(tmp_path, f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept(_x: {a}) -> None: ...

        _accept({b}({_ctor_arg(b)}))
    """)
    assert result.returncode != 0, f"mypy --strict accepted {a} <- {b}: {result.stdout}"
    assert "incompatible type" in result.stdout.lower() or "argument" in result.stdout.lower()


@pytest.mark.parametrize("a,literal", RAW_LITERAL_SWAPS)
def test_mypy_rejects_raw_literal(tmp_path: Path, a: str, literal: str) -> None:
    result = _run_mypy(tmp_path, f"""
        from codegenie.types.identifiers import {a}

        def _accept(_x: {a}) -> None: ...

        _accept({literal})
    """)
    assert result.returncode != 0, f"mypy --strict accepted raw {literal} as {a}: {result.stdout}"
    assert "incompatible type" in result.stdout.lower() or "argument" in result.stdout.lower()
```

Hypothesis properties go in `tests/unit/types/test_phase4_parsers_properties.py`:

```python
from __future__ import annotations

import math
import pytest
from hypothesis import given, strategies as st

from codegenie.result import Err, Ok
from codegenie.types import parsers as P

STR_PARSERS = [
    P.parse_solved_example_id, P.parse_store_digest, P.parse_chain_head,
    P.parse_hex_nonce, P.parse_model_id, P.parse_budget_token_id,
]


@pytest.mark.parametrize("parser", STR_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_total(parser, s):
    try:
        r = parser(s)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{parser.__name__}({s!r}) raised: {e!r}")
    assert isinstance(r, (Ok, Err))


@pytest.mark.parametrize("parser", STR_PARSERS, ids=lambda p: p.__name__)
@given(s=st.text(max_size=300))
def test_deterministic(parser, s):
    assert parser(s) == parser(s)


@given(x=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_similarity_round_trip(x):
    r = P.parse_similarity(x)
    assert isinstance(r, Ok) and r.value == x


@given(x=st.one_of(
    st.just(float("nan")), st.just(float("inf")), st.just(float("-inf")),
))
def test_similarity_rejects_non_finite(x):
    r = P.parse_similarity(x)
    assert isinstance(r, Err)


@given(n=st.integers(min_value=0, max_value=2**31 - 1))
def test_token_count_round_trip(n):
    r = P.parse_token_count(n)
    assert isinstance(r, Ok) and r.value == n
```

The AST source-scan skeleton goes in `tests/fence/test_phase4_no_raw_str_for_domain_ids.py`:

```python
from __future__ import annotations

import ast
import pathlib

import codegenie

_ROOT = pathlib.Path(codegenie.__file__).parent
_PHASE4_PATHS = (_ROOT / "fallback", _ROOT / "rag")

# Domain-id-shaped names that MUST be typed against a newtype. This roster
# MUST match the AC-13 prose roster exactly (14 entries, incl. "package").
_DOMAIN_KEYWORDS = frozenset({
    "response_id", "budget_token", "cassette", "chain_head", "store_digest",
    "embedding_model", "similarity", "tokens_in", "tokens_out", "nonce",
    "solved_example_id", "cve_id", "package", "manifest_path",
})
_FORBIDDEN_BASE_ANNOTATIONS = frozenset({"str", "int", "float", "bytes"})


def _is_offender(name: str | None, annotation: ast.expr | None) -> bool:
    if name is None or annotation is None:
        return False
    if not any(kw in name for kw in _DOMAIN_KEYWORDS):
        return False
    return ast.unparse(annotation) in _FORBIDDEN_BASE_ANNOTATIONS


def test_no_raw_primitive_for_domain_ids() -> None:
    offenders: list[tuple[str, int, str]] = []
    for root in _PHASE4_PATHS:
        if not root.exists():
            continue  # Skeleton — fallback/ + rag/ land in later Step 1 stories.
        for py in root.rglob("*.py"):
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                # (a) attribute / Pydantic-field / dataclass-field annotations
                if isinstance(node, ast.AnnAssign):
                    target = node.target
                    name = (
                        target.id if isinstance(target, ast.Name)
                        else target.attr if isinstance(target, ast.Attribute)
                        else None
                    )
                    if _is_offender(name, node.annotation):
                        offenders.append((str(py), node.lineno, name or "?"))
                # (b) + (c) function-parameter and return annotations —
                # the AC-13 "function signature" promise.
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    args = node.args
                    every_arg = (
                        args.posonlyargs + args.args + args.kwonlyargs
                        + ([args.vararg] if args.vararg else [])
                        + ([args.kwarg] if args.kwarg else [])
                    )
                    for arg in every_arg:
                        if _is_offender(arg.arg, arg.annotation):
                            offenders.append((str(py), arg.lineno, arg.arg))
                    if _is_offender(node.name, node.returns):
                        offenders.append((str(py), node.lineno, f"{node.name}()->"))
    assert not offenders, (
        "Domain-id-shaped name annotated as raw primitive (use a NewType): "
        f"{offenders}"
    )
```

State why it fails: `ImportError` — the eleven new names in `identifiers.py` and the eight new `parse_<x>` functions don't exist yet. (Note: the `test_phase4_rows_in_shared_registry` test imports `_NEWTYPE_REGISTRY`, which *does* exist — that test fails on the `PHASE4_NAMES <= keys()` assertion until the rows are appended.)

### Green — make it pass

- Append **eleven** `NewType` lines + eleven rows to the **existing** `_NEWTYPE_REGISTRY` in `identifiers.py`. Update `__all__` to the sorted exact set.
- Append eight `parse_<x>` functions to `parsers.py`. Route every regex-shaped parser (the four hex-shaped + `parse_budget_token_id` + the regex inside `parse_model_id`) through `_regex_parser` closures; `parse_similarity`/`parse_token_count` are direct numeric checks.
- Update `codegenie.types.__init__` re-exports.
- Update `tests/unit/types/test_identifiers_phase3.py` — add `PHASE4_NAMES` to `test_all_is_exact_set` + `test_newtype_registry_matches_all` (AC-19). Without this, `make check` fails.
- `tests/fence/` already exists — no `__init__.py` to add.

### Refactor — clean up

- **Reuse the existing `_HEX64_RX`** (already in `parsers.py`, `^[0-9a-f]{64}$`) for `parse_solved_example_id` / `parse_store_digest` / `parse_chain_head` — they have the identical shape as `parse_blob_digest` / `parse_transform_id`. Add per-newtype closures (`_solved_example_id_match = _regex_parser(_HEX64_RX, ...)`, etc.) so `Err.message` names the right type, exactly the `_image_digest_match` / `_layer_digest_match` precedent. Do **not** introduce a duplicate `_BLAKE3_HEX_RX`.
- New module-level `Final` regex constants needed: `_HEX_NONCE_RX` (`^[0-9a-f]{32}$`), `_UUID4_RX`, `_VENDOR_MODEL_RX`.
- Docstring each parser with a one-liner naming its boundary and consumer story (e.g., `"""External boundary: chromadb digest output; ADR-0016; consumer S4-03."""`).
- Confirm `_regex_parser` remains the sole `.fullmatch(` callsite in the module (existing `test_only_one_fullmatch_outside_helper` enforces this — `parse_budget_token_id` and `parse_model_id` must therefore go through closures, not hand-written `.fullmatch`).
- Edge cases enumerated in arch §Edge cases that touch this code: #19 (model-mismatch — `ModelId` equality on `embedding_model` field).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append **eleven** Phase-4 newtypes + eleven rows to the **existing** `_NEWTYPE_REGISTRY`; update `__all__`. |
| `src/codegenie/types/parsers.py` | Append eight Phase-4 smart constructors (regex parsers route through `_regex_parser`). |
| `src/codegenie/types/__init__.py` | Re-export **eleven** new names. |
| `tests/unit/types/test_identifiers_phase3.py` | **MODIFY (AC-19)** — add `PHASE4_NAMES` roster; fold into `test_all_is_exact_set` + `test_newtype_registry_matches_all`. Without this, `make check` fails. |
| `tests/unit/types/test_phase4_identifiers.py` | NEW — happy/sad/distinctness/identity/registry/isinstance. |
| `tests/unit/types/test_phase4_identifiers_mypy_negative.py` | NEW — subprocess `mypy --strict` swap-rejection meta-test (≥ 12 pairs, `_ctor_arg` helper). |
| `tests/unit/types/test_phase4_parsers_properties.py` | NEW — Hypothesis totality + determinism + round-trip + non-finite rejection. |
| `tests/fence/test_phase4_no_raw_str_for_domain_ids.py` | NEW — AST source-scan skeleton (`AnnAssign` + function-arg + return annotations; re-runs as `fallback/`+`rag/` are landed). |

`tests/fence/` already exists (with `__init__.py`) — verified 2026-05-21; do **not** re-create it. `tests/unit/types/test_module_purity.py` is **not** touched (AC-16 reuses it as-is).

## Out of scope

- **`PlanProposal` / `UnifiedDiff` smart constructor** — handled by S1-02 (consumes `SandboxedRelativePath`/`PackageId`/`SemverString` from Phase 3 + the newtypes this story ships).
- **`PlanOutcome` sum type** — handled by S1-03.
- **`SolvedExample` / `Query` / `RetrievalOutcome` / `BudgetSnapshot` / `BudgetToken` Pydantic models** — handled by S1-04.
- **`EmbeddingVector` shape validation (384-dim BGE-small)** — handled by S4-01 (the runtime carrier is `np.ndarray`; the kernel-side `EmbeddingVector` is a tuple alias to keep `identifiers.py` stdlib-only).
- **Smart constructors for `EmbeddingVector`, `LeafResponseId`, `CassetteId`** — deferred to their first-consumer stories (S4-01, S3-02, S3-04). This story ships the newtypes alone, with docstrings naming the deferral.
- **Path-scoped fence amendment / `import-linter` contracts** — S1-05 / S1-06.

## Notes for the implementer

- **Do not create `src/codegenie/types/errors.py` or `src/codegenie/types/result.py`** — Phase-3 S1-01 already ships `ParseError` (canonical at `codegenie.types.errors`) and the canonical `Result` lives at `codegenie.result`. Re-use, do not fork (Rule 7).
- **`EmbeddingVector` as `tuple[float, ...]` at the kernel layer is deliberate.** numpy is a `rag/` dep (path-scoped under S1-05's fence amendment); making `EmbeddingVector` a numpy-annotated newtype would either pull numpy into the kernel (breaks the fence) or require a forward-string annotation. The tuple alias is the simplest faithful kernel-tier shape; `rag/embedder.py` (S4-01) constructs `EmbeddingVector(tuple(ndarray.tolist()))` at the boundary.
- **`BlobDigest` may already exist (Phase-3 S1-01).** Check before adding. If present, this story re-uses it for both `advisory_digest` and `transform_digest`; the docstring registry entry naming the Phase-4 consumer goes alongside the Phase-3 entry (the registry is keyed on the newtype name, so the docstring carries multi-phase consumer citations).
- **`WorkflowId` is Phase-3-owned.** Phase 4 imports it from `codegenie.types.identifiers`; the arch §Data model lists it for completeness but it's not part of this story's twelve new names.
- **`Similarity` rejects NaN/±inf explicitly.** A retrieval scoring `nan` against a poisoned record is a real failure mode — the type-level check is cheaper than the runtime guard.
- **`BudgetTokenId` is uuid4-canonical** because S2-05's non-reuse property (`tests/property/test_budget_token_non_reuse.py`) wants a syntactic guarantee in addition to the runtime check; uuid4 collisions are vanishingly unlikely at the scale of one process, but the canonical form catches uuid1-leak bugs (clock-MAC-based) that would weaken the non-reuse claim.
- **`tests/fence/` already exists** (with `__init__.py`, ~20 fence tests as of 2026-05-21 — Phase-3 created it). Add the new `test_phase4_no_raw_str_for_domain_ids.py` into it; do not re-create the directory.
- **One shared registry — extend, do not fork.** `identifiers.py` has exactly one `_NEWTYPE_REGISTRY`; Phase 2, 3, and 7 all appended rows to it. Phase 4 does the same — eleven new rows in the existing dict (AC-15). Creating a parallel `_PHASE4_NEWTYPE_REGISTRY` would (a) break the existing `test_newtype_registry_matches_all`, and (b) be the precise "two patterns contradict" anti-pattern Rule 7 / Rule 11 forbid. This is the Open/Closed seam working as designed: a new phase's identifiers are *additive rows*, never a new structure.
- **`identifiers.__all__` is a fenced surface.** It is asserted exact (not ⊇) by `test_identifiers_phase3.py::test_all_is_exact_set` and mirrored into `_NEWTYPE_REGISTRY` by `test_newtype_registry_matches_all`. Any story that adds a name to `__all__` *must* update those two assertions in the same commit — this is why AC-19 + the `test_identifiers_phase3.py` Files-to-touch row exist. The executor that forgets this will see `make check` fail on a Phase-3 test and may misdiagnose it as unrelated breakage.
- **`_regex_parser` is the single regex chokepoint.** Every regex-shaped parser routes its `.fullmatch` through a `_regex_parser` closure — the module's deliberate design (Phase-3 AC-18). `parse_budget_token_id` (uuid4) and the regex half of `parse_model_id` are regex parsers and must use closures (`_uuid4_match`, `_model_id_match`); `parse_model_id` layers NFKC preflight on top, identical to `parse_branch_name`. This keeps "add a new regex parser = one closure row" true and keeps `test_only_one_fullmatch_outside_helper` green.
- **Path-scoped fence-CI lands WITH this step's package introduction (ADR-0003)** — the newtypes here are pure stdlib so the fence does not apply yet, but the AST source-scan skeleton (AC-13) is positioned so it gates every subsequent Step-1 story's `fallback/`/`rag/` additions from regressing.
