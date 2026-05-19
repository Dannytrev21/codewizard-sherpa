"""S3-05 — :class:`BundleCacheStore` round-trip / atomicity / mode / corruption tests.

Covers AC-14..AC-19 — annotation pin, key validation, atomic write,
file mode discipline, idempotence, ``get`` semantics, corrupt-survives,
``Bundle`` JSON-roundtrip canary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.adapters.confidence import Trusted
from codegenie.plugins.bundle import Bundle, BundleEntry
from codegenie.plugins.cache import (
    BundleCacheRaise,
    BundleCacheStore,
)
from codegenie.transforms._forward import SandboxedPath
from codegenie.types.identifiers import BundleCacheKey, PluginId, PrimitiveName

_VALID_KEY = BundleCacheKey("blake3:" + "a" * 64)


@pytest.fixture
def sample_bundle() -> Bundle:
    """Multi-entry Bundle so the JSON-roundtrip canary exercises the tuple field."""
    entries = (
        BundleEntry(
            primitive=PrimitiveName("scip.refs"),
            args_canonical='{"symbol":"x"}',
            payload={"hits": 1},
            confidence=Trusted(),
            fallback_used=False,
            adapter_name="scip",
        ),
        BundleEntry(
            primitive=PrimitiveName("scip.defs"),
            args_canonical='{"symbol":"y"}',
            payload={"hits": 0},
            confidence=Trusted(),
            fallback_used=False,
            adapter_name="scip",
        ),
    )
    return Bundle(
        entries=entries,
        plugin_id=PluginId("vuln-node-npm"),
        vuln_index_digest="blake3:" + "d" * 64,  # type: ignore[arg-type]
    )


class TestPutGetRoundTrip:
    def test_put_then_get_round_trips(self, tmp_path: Path, sample_bundle: Bundle) -> None:
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        store.put(_VALID_KEY, sample_bundle)
        got = store.get(_VALID_KEY)
        assert got == sample_bundle
        assert got is not None
        assert type(got.entries) is type(sample_bundle.entries)

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        assert (
            BundleCacheStore(SandboxedPath(absolute=tmp_path)).get(
                BundleCacheKey("blake3:" + "b" * 64)
            )
            is None
        )

    def test_get_on_missing_cache_dir_returns_none(self, tmp_path: Path) -> None:
        nowhere = tmp_path / "does-not-exist"
        assert BundleCacheStore(SandboxedPath(absolute=nowhere)).get(_VALID_KEY) is None


class TestPutAtomicityAndMode:
    def test_put_writes_atomically_no_residual_tmp(
        self, tmp_path: Path, sample_bundle: Bundle
    ) -> None:
        """AC-16 — no ``*.tmp`` lingers in ``bundles/`` after a successful put."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        store.put(_VALID_KEY, sample_bundle)
        assert list((tmp_path / "bundles").glob("*.tmp")) == []

    def test_put_file_mode_0600_and_dir_mode_0700(
        self, tmp_path: Path, sample_bundle: Bundle
    ) -> None:
        """AC-16 — Phase-0 ADR-0011 cache-permission discipline."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        store.put(_VALID_KEY, sample_bundle)
        blob = tmp_path / "bundles" / ("a" * 64 + ".json")
        assert blob.stat().st_mode & 0o777 == 0o600
        assert (tmp_path / "bundles").stat().st_mode & 0o777 == 0o700

    def test_idempotent_put_same_bundle(self, tmp_path: Path, sample_bundle: Bundle) -> None:
        """AC-17 — identical ``(key, bundle)`` twice → byte-identical content."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        store.put(_VALID_KEY, sample_bundle)
        blob = tmp_path / "bundles" / ("a" * 64 + ".json")
        first = blob.read_bytes()
        store.put(_VALID_KEY, sample_bundle)
        assert blob.read_bytes() == first

    def test_overwrite_with_different_bundle(self, tmp_path: Path, sample_bundle: Bundle) -> None:
        """AC-17 — same key, different Bundle ⇒ clean overwrite."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        store.put(_VALID_KEY, sample_bundle)
        other = Bundle(
            entries=(),
            plugin_id=PluginId("vuln-node-yrn"),
            vuln_index_digest="blake3:" + "e" * 64,  # type: ignore[arg-type]
        )
        store.put(_VALID_KEY, other)
        got = store.get(_VALID_KEY)
        assert got == other


class TestCorruptSurvives:
    def test_corrupt_file_returns_none_and_file_survives(self, tmp_path: Path) -> None:
        """AC-18 — corrupt-on-read does NOT delete the file (operator inspection)."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        (tmp_path / "bundles").mkdir(parents=True)
        corrupt = tmp_path / "bundles" / ("c" * 64 + ".json")
        corrupt.write_text("{not valid json")
        assert store.get(BundleCacheKey("blake3:" + "c" * 64)) is None
        assert corrupt.exists(), "Rule 12: do NOT delete the file"

    def test_partial_json_returns_none(self, tmp_path: Path) -> None:
        """AC-18 — schema-mismatching JSON triggers Pydantic ValidationError path."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        (tmp_path / "bundles").mkdir(parents=True)
        bad = tmp_path / "bundles" / ("e" * 64 + ".json")
        bad.write_text('{"not": "a bundle"}')
        assert store.get(BundleCacheKey("blake3:" + "e" * 64)) is None
        assert bad.exists()


@pytest.mark.parametrize(
    "bad_key",
    [
        "",
        "blake3:",
        "blake3:" + "z" * 64,
        "blake3:../../etc/passwd",
        "blake3:" + "a" * 63,
        "blake3:" + "a" * 65,
        "sha256:" + "a" * 64,
        "a" * 64,
        "blake3:" + "A" * 64,
    ],
)
class TestKeyValidation:
    def test_put_rejects_malformed(
        self, tmp_path: Path, bad_key: str, sample_bundle: Bundle
    ) -> None:
        """AC-15 — path-traversal + uppercase + length variants rejected."""
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        with pytest.raises(BundleCacheRaise) as exc:
            store.put(BundleCacheKey(bad_key), sample_bundle)
        assert exc.value.model.reason == "invalid_key"

    def test_get_rejects_malformed(self, tmp_path: Path, bad_key: str) -> None:
        store = BundleCacheStore(SandboxedPath(absolute=tmp_path))
        with pytest.raises(BundleCacheRaise) as exc:
            store.get(BundleCacheKey(bad_key))
        assert exc.value.model.reason == "invalid_key"


class TestBundleJsonRoundtripCanary:
    """AC-19 — if this fails, S3-04 normalises ``tuple → list`` and S3-05 is unblocked."""

    def test_bundle_json_round_trip(self, sample_bundle: Bundle) -> None:
        rehydrated = type(sample_bundle).model_validate_json(sample_bundle.model_dump_json())
        assert rehydrated == sample_bundle


class TestAnnotations:
    """AC-14 — ``cache_dir`` annotation is ``SandboxedPath`` (name-pinned).

    ``from __future__ import annotations`` keeps the annotation as the
    source-text spelling; pinning the string is what catches a regression
    swapping it for ``pathlib.Path``. Mirrors S3-04's annotation test.
    """

    def test_cache_dir_annotation_is_sandboxed_path(self) -> None:
        annotation = BundleCacheStore.__init__.__annotations__["cache_dir"]
        assert annotation == "SandboxedPath"
        # S4-04 flipped the TypeAlias: SandboxedPath is now the real
        # Pydantic BaseModel from codegenie.plugins.sandbox_path
        # (re-exported via codegenie.transforms._forward).
        assert SandboxedPath.__name__ == "SandboxedPath"
