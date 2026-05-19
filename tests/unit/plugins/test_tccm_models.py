"""Phase-3 S3-01 — unit + parametrized negatives for ``codegenie.plugins.tccm``.

Pins AC-1..AC-16, AC-20. Each test docstring names the AC it pins and the
regression class it catches (Rule 9 — tests verify intent, not just
behaviour).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.plugins.tccm import (
    _IMPORT_PATH_RE,
    _KNOWN_PRIMITIVES,
    _NAMESPACE_RE,
    _PRIMITIVE_RE,
    TCCM,
    ContextQuery,
    TCCMParseError,
)

# --- ContextQuery -------------------------------------------------------


class TestContextQuery:
    """AC-2 / AC-7 / AC-8 / AC-9 / AC-10 / AC-15 / AC-20."""

    def test_known_primitive_accepted(self) -> None:
        """AC-7 / AC-8 — membership check accepts every primitive in the closed set."""
        result = ContextQuery.create(primitive="scip.refs", args={"symbol": "express.urlencoded"})
        assert result.is_ok()
        assert result.unwrap().primitive == "scip.refs"

    def test_unknown_primitive_rejected(self) -> None:
        """AC-8 — unknown primitive lifts to ``Err(unknown_primitive, ...)``."""
        result = ContextQuery.create(primitive="grep.adhoc", args={})
        assert result.is_err()
        err = result.unwrap_err()
        assert err.reason == "unknown_primitive"
        assert err.details == {"primitive": "grep.adhoc"}

    @pytest.mark.parametrize("bad", [0, -1, -(2**31)])
    def test_negative_max_files_rejected(self, bad: int) -> None:
        """AC-20 — boundary parametrization for non-positive ``max_files``."""
        r = ContextQuery.create(primitive="scip.refs", args={}, max_files=bad)
        assert r.is_err()
        err = r.unwrap_err()
        assert err.reason == "negative_max_files"
        assert err.details == {"max_files": bad}

    @pytest.mark.parametrize("good", [1, 1024, None])
    def test_valid_max_files_accepted(self, good: int | None) -> None:
        """AC-20 — positive integers + ``None`` are valid."""
        assert ContextQuery.create(primitive="scip.refs", args={}, max_files=good).is_ok()

    def test_fallback_round_trip_depth_3(self) -> None:
        """AC-15 — three-deep fallback chain survives dump/validate."""
        deep = ContextQuery.create(primitive="dep_graph.consumers", args={"pkg": "x"}).unwrap()
        mid = ContextQuery.create(
            primitive="import_graph.reverse_lookup",
            args={"module": "x"},
            fallback=deep,
        ).unwrap()
        primary = ContextQuery.create(
            primitive="scip.refs", args={"symbol": "x"}, fallback=mid
        ).unwrap()
        assert primary.fallback is not None
        assert primary.fallback.fallback is not None
        assert primary.fallback.fallback.primitive == "dep_graph.consumers"
        rt = ContextQuery.model_validate(primary.model_dump())
        assert rt == primary
        assert rt.fallback is not None
        assert rt.fallback.fallback is not None
        assert rt.fallback.fallback.primitive == "dep_graph.consumers"

    def test_extra_field_forbidden(self) -> None:
        """AC-2 — ``extra='forbid'`` rejects unknown keys."""
        with pytest.raises(ValidationError):
            ContextQuery.model_validate({"primitive": "scip.refs", "args": {}, "rogue": "x"})

    def test_empty_args_accepted(self) -> None:
        """AC-10 — empty args dict is intentionally valid."""
        assert ContextQuery.create(primitive="scip.refs", args={}).is_ok()

    @pytest.mark.parametrize(
        "bad_args",
        [
            {"k": None},
            {"k": 3.14},
            {"k": {"nested": "dict"}},
            {"k": [1, 2]},
            {"k": (1, 2)},
        ],
    )
    def test_args_rejects_non_primitive_values(self, bad_args: dict[str, object]) -> None:
        """AC-9 — relaxing the union to ``dict[str, Any]`` would silently regress."""
        with pytest.raises(ValidationError):
            ContextQuery.model_validate({"primitive": "scip.refs", "args": bad_args})

    def test_create_does_not_swallow_unrelated_validation_errors(self) -> None:
        # AC-8 — Pydantic ``ValidationError`` propagates; ``create`` only
        # wraps the two enumerated reasons.
        with pytest.raises(ValidationError):
            ContextQuery.create(
                primitive="scip.refs",
                args={"k": {"nested": "x"}},  # type: ignore[dict-item]
            )

    def test_frozen_assignment_rejected(self) -> None:
        """AC-2 — ``frozen=True`` rejects mutation."""
        cq = ContextQuery.create(primitive="scip.refs", args={}).unwrap()
        with pytest.raises(ValidationError):
            cq.primitive = "dep_graph.consumers"  # type: ignore[misc]


# --- TCCMParseError shape ------------------------------------------------


def test_tccm_parse_error_is_frozen_pydantic_with_literal_reason() -> None:
    """AC-4 — NOT a ``CodegenieError`` subclass; frozen Pydantic with closed reason set."""
    from codegenie.errors import CodegenieError

    assert not issubclass(TCCMParseError, CodegenieError)
    err = TCCMParseError(reason="unknown_primitive", details={"primitive": "x"})
    assert err.reason == "unknown_primitive"
    # Closed set: invalid reason rejected
    with pytest.raises(ValidationError):
        TCCMParseError(reason="totally_made_up", details={})  # type: ignore[arg-type]
    # ``details`` value union: float is not in ``str | int``
    with pytest.raises(ValidationError):
        TCCMParseError(
            reason="unknown_primitive",
            details={"x": 3.14},  # type: ignore[dict-item]
        )


def test_tccm_parse_error_frozen() -> None:
    """AC-4 — frozen=True rejects mutation."""
    err = TCCMParseError(reason="unknown_primitive", details={"primitive": "x"})
    with pytest.raises(ValidationError):
        err.reason = "negative_max_files"  # type: ignore[misc]


# --- _KNOWN_PRIMITIVES discipline ---------------------------------------


def test_known_primitives_exact_set() -> None:
    """AC-5 — exact set equality + cardinality; a 6th primitive must edit this test."""
    assert _KNOWN_PRIMITIVES == frozenset(
        {
            "scip.refs",
            "import_graph.reverse_lookup",
            "import_graph.transitive_callers",
            "dep_graph.consumers",
            "test_inventory.tests_exercising",
        }
    )
    assert len(_KNOWN_PRIMITIVES) == 5


def test_primitive_grammar_fence_matches_known_primitives() -> None:
    """AC-6 — every known primitive matches ``_PRIMITIVE_RE.fullmatch``."""
    for p in _KNOWN_PRIMITIVES:
        assert _PRIMITIVE_RE.fullmatch(p), p


def test_primitive_re_rejects_drift() -> None:
    """AC-6 mutation pin — a missing dot or two-dot variant must NOT match."""
    assert _PRIMITIVE_RE.fullmatch("scip") is None
    assert _PRIMITIVE_RE.fullmatch("scip.refs.deep") is None
    assert _PRIMITIVE_RE.fullmatch("Scip.refs") is None


def test_namespace_re_basics() -> None:
    """AC-11 / AC-17 — pin the namespace regex shape."""
    assert _NAMESPACE_RE.fullmatch("vuln_index_capabilities") is not None
    assert _NAMESPACE_RE.fullmatch("a") is not None
    assert _NAMESPACE_RE.fullmatch("1ns") is None
    assert _NAMESPACE_RE.fullmatch("NS") is None
    assert _NAMESPACE_RE.fullmatch("ns-x") is None


def test_import_path_re_basics() -> None:
    """AC-11 — pin the import-path regex shape."""
    assert _IMPORT_PATH_RE.fullmatch("a:B") is not None
    assert _IMPORT_PATH_RE.fullmatch("pkg.sub_pkg.mod:ClassName") is not None
    assert _IMPORT_PATH_RE.fullmatch("mod:lowercase") is None
    assert _IMPORT_PATH_RE.fullmatch("no_colon_here") is None


# --- TCCM ----------------------------------------------------------------


class TestTCCM:
    """AC-3 / AC-11 / AC-12 / AC-13 / AC-14."""

    BASE_MUST = [{"primitive": "scip.refs", "args": {}}]

    @pytest.mark.parametrize(
        "bad_ns",
        [
            "1vuln",
            "Vuln",
            "vuln-index",
            "vuln.index",
            "Vuln-Index",
            "",
            " spaces ",
            "_leading_underscore",
        ],
    )
    def test_provides_namespace_grammar_rejects_bad(self, bad_ns: str) -> None:
        """AC-11 — negative corpus for outer namespace key."""
        with pytest.raises(ValidationError):
            TCCM.model_validate(
                {
                    "must_read": self.BASE_MUST,
                    "provides": {bad_ns: {"nvd_parser": "x:Y"}},
                }
            )

    @pytest.mark.parametrize(
        "bad_path",
        [
            ":NoModule",
            "mod:lowercase",
            "1mod:Class",
            "mod:1Class",
            "mod:",
            "mod::Class",
            "no_colon_here",
            "",
        ],
    )
    def test_provides_import_path_rejects_bad(self, bad_path: str) -> None:
        """AC-11 — negative corpus for inner import path."""
        with pytest.raises(ValidationError):
            TCCM.model_validate(
                {
                    "must_read": self.BASE_MUST,
                    "provides": {"vuln_index_capabilities": {"nvd_parser": bad_path}},
                }
            )

    @pytest.mark.parametrize(
        "good_path",
        [
            "a:B",
            "codegenie.x.y:NvdParser",
            "_mod:Cls",
            "pkg.sub_pkg.mod:ClassName",
        ],
    )
    def test_provides_import_path_accepts_happy_corpus(self, good_path: str) -> None:
        """AC-11 — positive corpus for inner import path."""
        m = TCCM.model_validate(
            {
                "must_read": self.BASE_MUST,
                "provides": {"vuln_index_capabilities": {"nvd_parser": good_path}},
            }
        )
        assert m.provides["vuln_index_capabilities"]["nvd_parser"] == good_path

    def test_provides_multi_namespace_second_invalid_caught(self) -> None:
        # AC-12 — validator iterates ALL outer keys (mutation: an
        # early-return after the first failure would survive single-NS tests).
        with pytest.raises(ValidationError) as ei:
            TCCM.model_validate(
                {
                    "must_read": self.BASE_MUST,
                    "provides": {
                        "valid_ns": {"ok": "a:B"},
                        "Bad-NS": {"x": "a:B"},
                    },
                }
            )
        joined = str(ei.value)
        assert "Bad-NS" in joined or "provides" in joined

    def test_requires_multi_namespace_second_invalid_caught(self) -> None:
        """AC-12 — same iteration discipline mirrored on ``requires``."""
        with pytest.raises(ValidationError):
            TCCM.model_validate(
                {
                    "must_read": self.BASE_MUST,
                    "requires": {
                        "valid_ns": ["ok_name"],
                        "Bad-NS": ["ok_name"],
                    },
                }
            )

    def test_provides_two_namespaces_round_trip(self) -> None:
        """AC-13 — two namespaces side-by-side both validate AND round-trip."""
        original = TCCM.model_validate(
            {
                "must_read": [
                    {
                        "primitive": "dep_graph.consumers",
                        "args": {"pkg": "express"},
                    }
                ],
                "should_read": [
                    {
                        "primitive": "test_inventory.tests_exercising",
                        "args": {"symbol": "urlencoded"},
                    }
                ],
                "may_read": [],
                "provides": {
                    "vuln_index_capabilities": {
                        "nvd_parser": "codegenie.vuln_index.parsers:NvdParser",
                        "ghsa_parser": "codegenie.vuln_index.parsers:GhsaParser",
                    },
                    "telemetry_capabilities": {
                        "emitter": "codegenie.telemetry:Emitter",
                    },
                },
                "requires": {},
            }
        )
        rt = TCCM.model_validate(original.model_dump())
        assert rt == original
        assert set(rt.provides) == {
            "vuln_index_capabilities",
            "telemetry_capabilities",
        }

    @pytest.mark.parametrize("bad_inner", ["BadName", "1foo", "with-hyphen", "with.dot"])
    def test_requires_inner_grammar_rejects_bad(self, bad_inner: str) -> None:
        """AC-14 — list elements must match the namespace regex."""
        with pytest.raises(ValidationError):
            TCCM.model_validate(
                {
                    "must_read": self.BASE_MUST,
                    "requires": {"valid_ns": [bad_inner]},
                }
            )

    def test_requires_empty_list_allowed(self) -> None:
        """AC-14 positive — empty inner list is explicitly allowed."""
        m = TCCM.model_validate(
            {
                "must_read": self.BASE_MUST,
                "requires": {"valid_ns": []},
            }
        )
        assert m.requires == {"valid_ns": []}

    def test_must_read_required_and_loc_pinned(self) -> None:
        """AC-3 — ``must_read`` has no default; missing surfaces at ``loc=('must_read',)``."""
        with pytest.raises(ValidationError) as ei:
            TCCM.model_validate({"should_read": []})
        locs = [tuple(e["loc"]) for e in ei.value.errors()]
        assert ("must_read",) in locs

    def test_defaults_for_optional_lists_and_maps(self) -> None:
        """AC-3 — ``should_read``, ``may_read``, ``provides``, ``requires`` default empty."""
        m = TCCM.model_validate({"must_read": self.BASE_MUST})
        assert m.should_read == []
        assert m.may_read == []
        assert m.provides == {}
        assert m.requires == {}


# --- Module surface (AC-1) ----------------------------------------------


def test_module_all_pins_exactly_three_names() -> None:
    """AC-1 — ``__all__`` is set-equal to the three public types."""
    import codegenie.plugins.tccm as mod

    assert set(mod.__all__) == {"ContextQuery", "TCCM", "TCCMParseError"}


# --- Cache-key + hashability honesty (AC-16) -----------------------------


def test_context_query_is_not_hashable_due_to_dict_args() -> None:
    """AC-16 — ``args: dict`` makes ``ContextQuery`` unhashable; pinned explicitly."""
    cq = ContextQuery.create(primitive="scip.refs", args={"k": "v"}).unwrap()
    with pytest.raises(TypeError):
        hash(cq)


def test_context_query_model_dump_json_is_deterministic_for_cache_key() -> None:
    """AC-16 — ``model_dump_json()`` is the cache-key surface; byte-equal for equal inputs."""
    cq_a = ContextQuery.create(primitive="scip.refs", args={"symbol": "x"}).unwrap()
    cq_b = ContextQuery.create(primitive="scip.refs", args={"symbol": "x"}).unwrap()
    assert cq_a.model_dump_json() == cq_b.model_dump_json()
