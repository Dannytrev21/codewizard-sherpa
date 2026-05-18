# Story S1-01 — Newtype + smart-constructor substrate

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001 (closed-sum `PlanProposal` consumes `SandboxedRelativePath`, `SemverString`, `PackageId` — never raw `str`), ADR-0010 (Phase-4 `BudgetToken` is capability-typed — `BudgetTokenId` newtype), ADR-0014 (cassette discipline — `CassetteId` newtype), ADR-0016 (chromadb/YAML canonical — `StoreDigest`, `ChainHead`, `BlobDigest`)

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

- [ ] AC-1 — `src/codegenie/types/identifiers.py` exports twelve **new** names: `SolvedExampleId`, `EmbeddingVector`, `StoreDigest`, `Similarity`, `ModelId`, `TokenCount`, `LeafResponseId`, `BudgetTokenId`, `CassetteId`, `HexNonce`, `BlobDigest`, `ChainHead`. `BlobDigest` and `WorkflowId` may already exist (Phase-3 S1-01 ships `BlobDigest`; `WorkflowId` likewise) — **do not redefine**. If `BlobDigest` is already present, this story re-uses it for `advisory_digest` / `transform_digest`; document the no-op in the implementation notes.
- [ ] AC-2 — Each newtype's runtime backing type is the simplest faithful one: `EmbeddingVector` is `NewType("EmbeddingVector", "tuple[float, ...]")` (immutable; ndarray is the runtime carrier but the kernel-side type is a tuple to keep `identifiers.py` stdlib-only — numpy stays out of the kernel); `Similarity` is `NewType("Similarity", float)`; `TokenCount` is `NewType("TokenCount", int)`; every other name is `NewType("X", str)`.
- [ ] AC-3 — `src/codegenie/types/parsers.py` ships eight new smart constructors, each a pure function returning `Result[<X>, ParseError]`:
  - `parse_solved_example_id(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex of canonical YAML body; lowercase only).
  - `parse_store_digest(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex; same shape as `SolvedExampleId`).
  - `parse_chain_head(s)` — `^[0-9a-f]{64}$` (BLAKE3 hex).
  - `parse_similarity(x: float)` — `Ok` iff `-1.0 <= x <= 1.0`; otherwise `Err`. **NaN and ±inf rejected**.
  - `parse_model_id(s)` — `^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*(?:-\d{8})?$` (vendor model slugs like `claude-sonnet-4-5-20250929`); lowercase; max length 128.
  - `parse_token_count(n: int)` — `Ok` iff `n >= 0` and `n <= 2**31 - 1` (non-negative; sentinel-friendly upper bound).
  - `parse_budget_token_id(s)` — uuid4 canonical form `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`.
  - `parse_hex_nonce(s)` — `^[0-9a-f]{32}$` (16 bytes hex; canary nonce per arch §3 truncation table).
- [ ] AC-4 — Three newtypes have **no parser this story** — `EmbeddingVector` (constructed only inside `rag/embedder.py` from ONNX output and shape-validated there, S4-01); `LeafResponseId` (constructed only by `AnthropicLeafAdapter` from the SDK response, S3-02); `CassetteId` (constructed only by `CassetteSanitizer` from relpath, S3-04). Document the deferral in the docstring of each newtype with the consumer story id.
- [ ] AC-5 — `src/codegenie/types/__init__.py` re-exports all twelve new names so `from codegenie.types import SolvedExampleId, BudgetTokenId, ...` resolves. Identity passthrough — `codegenie.types.X is codegenie.types.identifiers.X` for every new name.

### Verification — family-symmetric closures (from Phase-3 S1-01 precedent)

- [ ] AC-6 — **Round-trip:** for every parser and every happy-path input `s`, `parse_<x>(s) == Ok(value=X(s))`.
- [ ] AC-7 — **Rejection:** every parser has ≥ 1 parametrized deliberately-bad input → `Err(ParseError(value=...))`. The table covers (at minimum):
  - `parse_solved_example_id`: uppercase hex; wrong length; non-hex char.
  - `parse_similarity`: `1.0001`, `-1.0001`, `float("nan")`, `float("inf")`, `float("-inf")`.
  - `parse_token_count`: `-1`, `2**31`, `"1"` (str-not-int).
  - `parse_budget_token_id`: uuid1, uuid5, non-`4` version nibble, non-`[89ab]` variant nibble.
  - `parse_model_id`: uppercase letters; leading hyphen; trailing dot; > 128 chars.
  - `parse_hex_nonce`: 30 chars; 34 chars; uppercase hex.
- [ ] AC-8 — **Cross-newtype substitution = mypy error (executed in CI):** `tests/unit/types/test_phase4_identifiers_mypy_negative.py` writes a temp `.py` file per swap pair and subprocess-invokes `mypy --strict`, asserting non-zero exit and an `argument`/`incompatible type` diagnostic on stdout. Parametrized over ≥ 10 distinct Phase-4 swap pairs (e.g., `BudgetTokenId ← LeafResponseId`, `StoreDigest ← ChainHead`, `Similarity ← float-literal`, `TokenCount ← int-literal`, `HexNonce ← BlobDigest`, `ModelId ← str`, `SolvedExampleId ← BlobDigest`, `CassetteId ← str`, `BudgetTokenId ← str`, `EmbeddingVector ← tuple[float, ...]`).
- [ ] AC-9 — **`__name__` pinning:** for every new newtype `X`, `getattr(identifiers, "X").__name__ == "X"`.
- [ ] AC-10 — **Pairwise distinctness:** parametrized test over `PHASE2_NAMES | PHASE3_NAMES | PHASE4_NAMES` — every distinct pair `(A, B)` satisfies `A is not B`. Catches `BudgetTokenId = LeafResponseId = NewType("Id", str)` aliasing.
- [ ] AC-11 — **Exact-set `__all__`:** `set(identifiers.__all__) == PHASE2_NAMES | PHASE3_NAMES | PHASE4_NAMES` (exact equality, not `⊇`). Stowaway exports fail.
- [ ] AC-12 — **`isinstance` runtime TypeError pin:** for every str-backed Phase-4 newtype, `with pytest.raises(TypeError): isinstance("foo", X)`. (`Similarity`/`TokenCount`/`EmbeddingVector` are typed against `float`/`int`/`tuple`; they are likewise non-isinstance-able under `NewType`.)
- [ ] AC-13 — **AST source-scan discipline (load-bearing for the "newtypes everywhere" cross-cutting rule):** new test `tests/fence/test_phase4_no_raw_str_for_domain_ids.py` walks every `.py` file under `src/codegenie/fallback/` and `src/codegenie/rag/` (once they exist) and asserts no function signature, attribute annotation, Pydantic field, or `dataclass` field uses a raw `str`/`int`/`float`/`bytes` annotation for any name in a roster of domain-id keywords (`response_id`, `budget_token`, `cassette`, `chain_head`, `store_digest`, `embedding_model`, `similarity`, `tokens_in`, `tokens_out`, `nonce`, `solved_example_id`, `cve_id`, `package`, `manifest_path`). Story S1-01 lands the test skeleton with the offender list initially empty (`fallback/` and `rag/` don't exist yet); each subsequent Phase-4 story re-runs it.
- [ ] AC-14 — **NFKC + ASCII-only on `parse_model_id`:** `parse_model_id` NFKC-normalizes input before regex match and rejects any post-normalization byte > 0x7F (vendor slugs are ASCII; non-ASCII look-alike is an injection signal).
- [ ] AC-15 — `_PHASE4_NEWTYPE_REGISTRY: Final[Mapping[str, str]]` module-level constant in `identifiers.py` mapping each of the twelve names → a one-line docstring naming the relevant Phase-4 ADR + consumer story. Test asserts `_PHASE4_NEWTYPE_REGISTRY.keys() == PHASE4_NAMES` and every value contains a Phase-4 ADR citation.
- [ ] AC-16 — **Module purity:** AST-walk on `parsers.py` asserts the import set is exactly `{__future__, typing, re, unicodedata, codegenie.result, codegenie.types.errors, codegenie.types.identifiers}`. No sibling-package imports; no logger; no filesystem.
- [ ] AC-17 — **Hypothesis property tests** in `tests/unit/types/test_phase4_parsers_properties.py`:
  - **Totality:** for any `s: str` drawn from `st.text(max_size=300)` (and any `x: float` for `parse_similarity`, `n: int` for `parse_token_count`), the parser never raises (`try/except Exception: pytest.fail(...)`).
  - **Determinism:** `parse_<x>(s) == parse_<x>(s)` for any drawn input.
  - **Round-trip identity for happy inputs:** for `s` drawn from `st.from_regex(parser_rx, fullmatch=True)`, `parse_<x>(s).unwrap() == <X>(s)`. For `parse_similarity`, draw `x` from `st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False)`.
  - **Similarity rejects non-finite:** `parse_similarity(float("nan"))` and `parse_similarity(float("inf"))` both `Err` (explicit Hypothesis case).
- [ ] AC-18 — `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline

1. Append twelve `NewType` lines to `src/codegenie/types/identifiers.py`, each with a docstring naming the relevant Phase-4 ADR + consumer story (e.g., `# BudgetTokenId — landed for S2-05 LlmInvocationGuard issuer; ADR-0010.`). Skip `BlobDigest` and `WorkflowId` if already exported by Phase-3 S1-01.
2. Add the `_PHASE4_NEWTYPE_REGISTRY: Final[Mapping[str, str]]` module-level constant (AC-15).
3. Update `identifiers.__all__` to sorted exact set.
4. Extend `src/codegenie/types/parsers.py` with the eight new `parse_<x>` smart constructors. Re-use the existing `_regex_parser` helper from Phase-3 S1-01 for the four hex-shaped parsers (`parse_solved_example_id`, `parse_store_digest`, `parse_chain_head`, `parse_hex_nonce`). `parse_similarity`, `parse_token_count`, `parse_model_id`, `parse_budget_token_id` are direct functions.
5. Update `src/codegenie/types/__init__.py` to re-export the twelve new names.
6. Land `tests/unit/types/test_phase4_identifiers.py`: parametrized happy + sad paths; `__name__` pinning; pairwise distinctness across all phase rosters; exact-set `__all__`; identity-passthrough; `isinstance` TypeError; docstring registry; NFKC on `parse_model_id`.
7. Land `tests/unit/types/test_phase4_identifiers_mypy_negative.py`: subprocess `mypy --strict` over a tmp swap file; parametrized over ≥ 10 Phase-4 swap pairs (AC-8).
8. Land `tests/unit/types/test_phase4_parsers_properties.py`: Hypothesis totality + determinism + round-trip-identity + non-finite-similarity rejection (AC-17).
9. Land `tests/fence/test_phase4_no_raw_str_for_domain_ids.py`: AST source-scan skeleton (AC-13). `tests/fence/` is a new directory — add an `__init__.py` if the repo convention requires.
10. Run `mypy --strict src/codegenie/types/` + `make check` locally.

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


@pytest.mark.parametrize(
    "name",
    sorted(PHASE4_NAMES - {"EmbeddingVector", "Similarity", "TokenCount"}),
)
def test_isinstance_str_raises_typeerror(name):
    import codegenie.types.identifiers as ids
    nt = getattr(ids, name)
    with pytest.raises(TypeError):
        isinstance("foo", nt)  # type: ignore[arg-type]


def test_phase4_registry_matches_phase4_names():
    from codegenie.types.identifiers import _PHASE4_NEWTYPE_REGISTRY
    assert set(_PHASE4_NEWTYPE_REGISTRY.keys()) == PHASE4_NAMES
    for name, doc in _PHASE4_NEWTYPE_REGISTRY.items():
        assert any(adr in doc for adr in ("ADR-0001", "ADR-0010", "ADR-0014", "ADR-0016")), (
            f"{name} docstring missing Phase-4 ADR citation: {doc!r}"
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
]


@pytest.mark.parametrize("a,b", SWAP_PAIRS)
def test_mypy_rejects_phase4_swap(tmp_path: Path, a: str, b: str) -> None:
    src = textwrap.dedent(
        f"""
        from codegenie.types.identifiers import {a}, {b}

        def _accept(_x: {a}) -> None: ...

        _accept({b}("dummy"))
        """
    )
    tmp = tmp_path / "swap.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, f"mypy --strict accepted {a} <- {b}: {result.stdout}"
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

# Domain-id-shaped attribute names that MUST be typed against a newtype.
_DOMAIN_KEYWORDS = frozenset({
    "response_id", "budget_token", "cassette", "chain_head", "store_digest",
    "embedding_model", "similarity", "tokens_in", "tokens_out", "nonce",
    "solved_example_id", "cve_id", "manifest_path",
})
_FORBIDDEN_BASE_ANNOTATIONS = frozenset({"str", "int", "float", "bytes"})


def test_no_raw_primitive_for_domain_ids() -> None:
    offenders: list[tuple[str, int, str, str]] = []
    for root in _PHASE4_PATHS:
        if not root.exists():
            continue  # Skeleton — fallback/ + rag/ land in later Step 1 stories.
        for py in root.rglob("*.py"):
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.AnnAssign):
                    target = node.target
                    name = target.id if isinstance(target, ast.Name) else (
                        target.attr if isinstance(target, ast.Attribute) else None
                    )
                    if name is None:
                        continue
                    if not any(kw in name for kw in _DOMAIN_KEYWORDS):
                        continue
                    ann = ast.unparse(node.annotation)
                    if ann in _FORBIDDEN_BASE_ANNOTATIONS:
                        offenders.append((str(py), node.lineno, name, ann))
    assert not offenders, (
        "Domain-id-shaped attribute annotated as raw primitive (use a NewType): "
        f"{offenders}"
    )
```

State why it fails: `ImportError` — the twelve new names in `identifiers.py` and the eight new `parse_<x>` functions don't exist yet.

### Green — make it pass

- Append twelve `NewType` lines + `_PHASE4_NEWTYPE_REGISTRY` to `identifiers.py`. Update `__all__` exact set.
- Append eight `parse_<x>` functions to `parsers.py`. Re-use existing `_regex_parser` helper for the four hex-shaped parsers.
- Update `codegenie.types.__init__` re-exports.
- `tests/fence/__init__.py` if the repo convention requires.

### Refactor — clean up

- Lift shared regex patterns to module-level `Final` constants (`_BLAKE3_HEX_RX`, `_UUID4_RX`, `_VENDOR_MODEL_RX`, `_HEX_NONCE_RX`).
- Docstring each parser with a one-liner naming its boundary and consumer story (e.g., `"""External boundary: chromadb digest output; ADR-0016; consumer S4-03."""`).
- Confirm `_regex_parser` is the sole `.fullmatch(` callsite outside the URL helper from Phase-3 S1-01.
- Edge cases enumerated in arch §Edge cases that touch this code: #19 (model-mismatch — `ModelId` equality on `embedding_model` field).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append twelve Phase-4 newtypes + `_PHASE4_NEWTYPE_REGISTRY`; update `__all__`. |
| `src/codegenie/types/parsers.py` | Append eight Phase-4 smart constructors. |
| `src/codegenie/types/__init__.py` | Re-export twelve new names. |
| `tests/unit/types/test_phase4_identifiers.py` | NEW — happy/sad/distinctness/identity/docstring/isinstance. |
| `tests/unit/types/test_phase4_identifiers_mypy_negative.py` | NEW — subprocess `mypy --strict` swap-rejection meta-test. |
| `tests/unit/types/test_phase4_parsers_properties.py` | NEW — Hypothesis totality + determinism + round-trip + non-finite rejection. |
| `tests/fence/__init__.py` | NEW — package marker for `tests/fence/`. |
| `tests/fence/test_phase4_no_raw_str_for_domain_ids.py` | NEW — AST source-scan skeleton (re-runs as fallback/+rag/ are landed). |

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
- **`tests/fence/` is a new directory.** Add `tests/fence/__init__.py`. Subsequent Step-1 stories (S1-05, S1-06, S1-07) add more files here; this story is the first occupant.
- **Match the existing docstring convention** in `identifiers.py` — `_PHASE4_NEWTYPE_REGISTRY` formalizes the "each newtype names its ADR + consumer" practice and makes it AST-verifiable (AC-15). Mirror Phase-3 S1-01's `_NEWTYPE_REGISTRY` shape.
- **Path-scoped fence-CI lands WITH this step's package introduction (ADR-0003)** — the newtypes here are pure stdlib so the fence does not apply yet, but the AST source-scan skeleton (AC-13) is positioned so it gates every subsequent Step-1 story's `fallback/`/`rag/` additions from regressing.
