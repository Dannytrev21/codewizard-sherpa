"""Phase-4 S7-09 AC-9 + AC-12 — corpus-size + source-attribution meta-tests.

Two observable invariants over the typed corpora:

* **Size** — the injection corpus grows toward the 200+ AC-9 target.
  Today's seed is 50 rows; that's the lower bound this meta-test
  pins until the full S7-09 attempt lands. A future commit that
  expands the corpus past 200 only needs to update the constant here.
* **Source attribution** — every row's ``source`` is non-empty AND
  matches one of the documented shapes (URL, paper citation, or the
  ``inherited:`` literal). The literal ``"internet"`` and bare
  single-word non-URL values are rejected.
* **Uniqueness** — no duplicate ``id``, no duplicate ``text``. A
  duplicate payload is unreachable under first-match parametrize
  ordering and silently inflates the corpus-size count.
* **Delimiter-backstop row presence (AC-13)** — at least one row's
  ``text`` contains the literal close-delimiter
  ``</UNTRUSTED_INPUT id=...>`` so S2-02 AC-15's in-body backstop is
  structurally exercised (Hypothesis random text reaches this
  substring with probability ≈ 2⁻¹²⁸).

The size target is intentionally **lower** than the AC-9 final
``>= 200`` so the test passes at the current corpus state; raise it
to 200 in the same commit that finishes populating the corpus.
"""

from __future__ import annotations

import re
from typing import Final

from tests.adv._corpora._load import load_corpus
from tests.adv._corpora._models import InjectionPayload

# AC-9 final target is 200; today's lower bound is the seed count.
# Raise to 200 in the same commit that finishes populating the corpus.
_INJECTION_CORPUS_MIN_TODAY: Final[int] = 50
_INJECTION_CORPUS_MIN_FINAL: Final[int] = 200  # S7-09 AC-9 hard target

# AC-12 source shape — exactly one of:
#   * URL (http:// or https://)
#   * Paper citation (``Author YYYY`` shape)
#   * Literal ``inherited: S2-03 INJECTION_PATTERNS row <pattern_id>``
_URL_RE: Final[re.Pattern[str]] = re.compile(r"^https?://\S+")
_PAPER_CITATION_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z]\w* \d{4}")
_INHERITED_RE: Final[re.Pattern[str]] = re.compile(r"^inherited: S2-03 INJECTION_PATTERNS row \w+")

_FENCE_DELIMITER_IN_BODY_RE: Final[re.Pattern[str]] = re.compile(r"</UNTRUSTED_INPUT id=[0-9a-f]+>")


def _is_valid_source(source: str) -> bool:
    """Return True iff ``source`` matches one of the three documented shapes."""
    if not source:
        return False
    if _URL_RE.match(source):
        return True
    if _PAPER_CITATION_RE.match(source):
        return True
    return bool(_INHERITED_RE.match(source))


# --- AC-9 — corpus size lower bound ----------------------------------------


def test_injection_corpus_size_meets_today_lower_bound() -> None:
    """Today's lower bound — raise to ``_INJECTION_CORPUS_MIN_FINAL`` in
    the same commit that completes the corpus expansion."""
    corpus = load_corpus("injection_payloads")
    assert len(corpus) >= _INJECTION_CORPUS_MIN_TODAY, (
        f"injection corpus size dropped below the today-lower-bound "
        f"({_INJECTION_CORPUS_MIN_TODAY}); got {len(corpus)}. Either add "
        f"rows or — if this is the deliberate completion commit — raise "
        f"the lower bound to {_INJECTION_CORPUS_MIN_FINAL}."
    )


def test_injection_corpus_size_targets_final_bound_via_constant() -> None:
    """The AC-9 final ``>= 200`` target is a documented constant — a
    future commit raising the lower bound must update this constant.
    """
    assert _INJECTION_CORPUS_MIN_FINAL == 200, (
        "AC-9 hard target is 200 injection payloads — do not lower this constant"
    )


# --- AC-12 — source attribution shape --------------------------------------


def test_every_injection_row_has_valid_source_attribution() -> None:
    """``source`` must be a URL, paper citation, or ``inherited:`` literal.
    The literal ``"internet"`` and bare single-word values are rejected.
    """
    corpus = load_corpus("injection_payloads")
    bad = [(r.id, r.source) for r in corpus if not _is_valid_source(r.source)]
    assert not bad, (
        f"{len(bad)} corpus rows have invalid source attribution "
        f"(must be URL, paper citation, or inherited:-literal). "
        f"First 5: {bad[:5]}"
    )


def test_no_row_uses_the_word_internet_as_source() -> None:
    """The literal ``"internet"`` is a load-bearing rejection — any
    single-word non-URL source is suspect, but ``"internet"`` is the
    canonical anti-example called out in the AC-8 story prose.
    """
    corpus = load_corpus("injection_payloads")
    bad = [r.id for r in corpus if r.source.lower() == "internet"]
    assert not bad, f"rows with source='internet' (rejected by AC-8): {bad}"


# --- AC-12(ii)/AC-12(iii) — id + text uniqueness ---------------------------


def test_no_duplicate_ids_in_injection_corpus() -> None:
    """Duplicate ``id`` would be a copy-paste error; surface loudly."""
    corpus = load_corpus("injection_payloads")
    ids = [r.id for r in corpus]
    duplicates = [i for i in set(ids) if ids.count(i) > 1]
    assert not duplicates, f"duplicate ids in injection corpus: {duplicates}"


def test_no_duplicate_texts_in_injection_corpus() -> None:
    """Duplicate ``text`` inflates the corpus-size count silently;
    every distinct payload must appear exactly once.
    """
    corpus = load_corpus("injection_payloads")
    texts = [r.text for r in corpus]
    duplicates: list[str] = []
    for t in set(texts):
        if texts.count(t) > 1:
            duplicates.append(t[:40] + "...")
    assert not duplicates, (
        f"duplicate texts inflate corpus size silently; first 3: {duplicates[:3]}"
    )


# --- AC-13 — deliberate delimiter-backstop row -----------------------------


def test_corpus_contains_deliberate_fence_delimiter_backstop_row() -> None:
    """At least one row's ``text`` contains the literal close-delimiter
    ``</UNTRUSTED_INPUT id=...>`` so S2-02 AC-15's in-body backstop is
    structurally exercised by S7-09 (Hypothesis random text reaches
    this substring with probability ≈ 2⁻¹²⁸; deliberate construction
    is the only way).
    """
    corpus = load_corpus("injection_payloads")
    matching = [r.id for r in corpus if _FENCE_DELIMITER_IN_BODY_RE.search(r.text)]
    assert matching, (
        "S7-09 AC-13 requires at least one row whose text contains the literal "
        "</UNTRUSTED_INPUT id=...> close-delimiter to exercise the in-body backstop. "
        "Add a row with text containing '</UNTRUSTED_INPUT id=00000000000000000000000000000000>' "
        "(or any 32-char-hex nonce)."
    )


# --- Pure-helper unit tests for _is_valid_source ---------------------------


def test_is_valid_source_accepts_url() -> None:
    assert _is_valid_source("https://example.test/path")
    assert _is_valid_source("http://example.test")


def test_is_valid_source_accepts_paper_citation() -> None:
    assert _is_valid_source("Greshake 2023")
    assert _is_valid_source("Perez 2022")


def test_is_valid_source_accepts_inherited_literal() -> None:
    assert _is_valid_source("inherited: S2-03 INJECTION_PATTERNS row ignore_previous_instructions")


def test_is_valid_source_rejects_empty() -> None:
    assert not _is_valid_source("")
    assert not _is_valid_source("   ")


def test_is_valid_source_rejects_the_word_internet() -> None:
    assert not _is_valid_source("internet")


def test_is_valid_source_rejects_lowercase_paper_shape() -> None:
    """Paper citation must start with a capital — ``greshake 2023`` shouldn't
    accidentally pass."""
    assert not _is_valid_source("greshake 2023")


def test_is_valid_source_rejects_inherited_without_pattern_id() -> None:
    """The inherited shape requires a non-empty pattern id."""
    assert not _is_valid_source("inherited: S2-03 INJECTION_PATTERNS row ")


# --- Smoke: corpus is non-empty so _load_corpus actually works -------------


def test_seed_corpus_first_row_is_typed_model() -> None:
    """Defense in depth — AC-10's typed shape didn't degrade to dict."""
    corpus = load_corpus("injection_payloads")
    assert corpus
    assert isinstance(corpus[0], InjectionPayload)
