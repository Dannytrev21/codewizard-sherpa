"""S3-05 — composer tests for :func:`codegenie.plugins.cache.compose_bundle_cache_key`.

Covers AC-6..AC-12 — keyword-only signature, declared-order byte
layout, mutation-resistant input participation, boundary-shift
collision defence, separator-poisoning rejection, ``args_canonical``
opacity, determinism N=100.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.hashing import content_hash_bytes
from codegenie.plugins.cache import (
    BundleCacheErrorModel,
    BundleCacheRaise,
    compose_bundle_cache_key,
)

# Same-length, distinct-equivalence-class fixtures so mutation tests cannot
# pass for the wrong reason (string-length-induced hash divergence).
_SAMPLE: dict[str, str] = {
    "plugin_id": "vuln-node-npm",
    "plugin_version": "0.1.0",
    "primitive": "scip.refs",
    "args_canonical": '{"symbol":"x"}',
    "repo_ctx_digest": "blake3:" + "a" * 64,
    "scip_digest": "blake3:" + "b" * 64,
    "dep_graph_digest": "blake3:" + "c" * 64,
    "vuln_index_digest": "blake3:" + "d" * 64,
}
_MUTATION: dict[str, str] = {
    "plugin_id": "vuln-node-yrn",
    "plugin_version": "0.1.1",
    "primitive": "scip.defs",
    "args_canonical": '{"symbol":"y"}',
    "repo_ctx_digest": "blake3:" + "e" * 64,
    "scip_digest": "blake3:" + "f" * 64,
    "dep_graph_digest": "blake3:" + "0" * 64,
    "vuln_index_digest": "blake3:" + "1" * 64,
}


class TestComposeBundleCacheKey:
    """AC-6..AC-12 — pure composer behaviour."""

    def test_returns_blake3_prefixed_64_hex(self) -> None:
        key = compose_bundle_cache_key(**_SAMPLE)
        assert key.startswith("blake3:") and len(key) == len("blake3:") + 64

    def test_declared_order_byte_layout(self) -> None:
        """AC-7 — pin the on-the-wire order against an alphabetic-sort mutant."""
        payload = "\x1f".join(
            [
                _SAMPLE["plugin_id"],
                _SAMPLE["plugin_version"],
                _SAMPLE["primitive"],
                _SAMPLE["args_canonical"],
                _SAMPLE["repo_ctx_digest"],
                _SAMPLE["scip_digest"],
                _SAMPLE["dep_graph_digest"],
                _SAMPLE["vuln_index_digest"],
            ]
        ).encode("utf-8")
        assert compose_bundle_cache_key(**_SAMPLE) == content_hash_bytes(payload)

    def test_boundary_shift_collisions_blocked(self) -> None:
        """AC-9 — \\x1f separator defuses (``"ab","c"``) vs (``"a","bc"``)."""
        rest = {k: v for k, v in _SAMPLE.items() if k not in ("plugin_id", "plugin_version")}
        k1 = compose_bundle_cache_key(plugin_id="ab", plugin_version="c", **rest)
        k2 = compose_bundle_cache_key(plugin_id="a", plugin_version="bc", **rest)
        assert k1 != k2

    @pytest.mark.parametrize("vary", list(_SAMPLE))
    def test_each_input_participates_mutation_resistant(self, vary: str) -> None:
        """AC-8 — ADR-0008 correctness: omitting any one input changes the key.

        Mutation strategy is same-length distinct-class, NOT append-``"x"``.
        A buggy impl that silently omits ``vuln_index_digest`` from the
        concatenation is caught by the row that varies it.
        """
        modified = {**_SAMPLE, vary: _MUTATION[vary]}
        assert compose_bundle_cache_key(**_SAMPLE) != compose_bundle_cache_key(**modified)

    def test_kwargs_only_signature(self) -> None:
        """AC-6 — positional call raises ``TypeError``."""
        with pytest.raises(TypeError):
            compose_bundle_cache_key(  # type: ignore[misc]
                "vuln-node-npm",
                "0.1.0",
                "scip.refs",
                "{}",
                "blake3:" + "a" * 64,
                "blake3:" + "b" * 64,
                "blake3:" + "c" * 64,
                "blake3:" + "d" * 64,
            )

    def test_determinism_n_100(self) -> None:
        """AC-11 — 100 calls produce one unique key (catches ``os.urandom`` reads)."""
        keys = {compose_bundle_cache_key(**_SAMPLE) for _ in range(100)}
        assert len(keys) == 1

    def test_args_canonical_passthrough_verbatim(self) -> None:
        """AC-12 — composer is opaque; whitespace differences produce different keys."""
        k_tight = compose_bundle_cache_key(**{**_SAMPLE, "args_canonical": '{"a":1}'})
        k_loose = compose_bundle_cache_key(**{**_SAMPLE, "args_canonical": '{"a": 1}'})
        assert k_tight != k_loose

    @pytest.mark.parametrize("poisoned_field", list(_SAMPLE))
    def test_separator_poisoning_rejected(self, poisoned_field: str) -> None:
        """AC-10 — ``\\x1f`` embedded in any input raises ``BundleCacheRaise``."""
        kw = {**_SAMPLE, poisoned_field: _SAMPLE[poisoned_field] + "\x1ftrailer"}
        with pytest.raises(BundleCacheRaise) as exc:
            compose_bundle_cache_key(**kw)
        assert exc.value.model.reason == "separator_in_input"
        assert exc.value.model.details["input"] == poisoned_field


class TestBundleCacheErrorModel:
    """AC-3 — frozen Pydantic model + closed-Literal reason."""

    def test_frozen_and_extra_forbid(self) -> None:
        m = BundleCacheErrorModel(reason="invalid_key", details={"key_prefix": "blake3:"})
        with pytest.raises(ValidationError):
            m.reason = "separator_in_input"  # type: ignore[misc]

    def test_unknown_reason_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BundleCacheErrorModel(reason="not_a_known_reason")  # type: ignore[arg-type]
