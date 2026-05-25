"""Phase-4 S4-04 — YAML-canonical + manifest.yaml + chain_head.

Pins AC-1..AC-5, AC-7, AC-9, AC-10, AC-12, AC-13, AC-14, AC-15 of
``docs/phases/04-vuln-llm-fallback-rag/stories/S4-04-yaml-canonical-and-manifest.md``.

Each test name targets a specific AC; the per-test docstring carries the
Ralph-Wiggum restatement so Stage-3 validation can match runtime evidence
to literal AC intent without spelunking.
"""

from __future__ import annotations

from pathlib import Path

import blake3
import pydantic
import pytest
import yaml

from codegenie.rag.errors import StoreCorrupted
from codegenie.rag.models import SolvedExample
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import StoreDigest, WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

_EMPTY_BLAKE3 = "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262"


# ---------------------------------------------------------------------------
# AC-1 — canonical YAML record written first; sorted keys (full ordering)
# ---------------------------------------------------------------------------


async def test_add_writes_canonical_yaml_record(tmp_path: Path) -> None:
    """ADR-0016: YAML is canonical, chromadb is derived. ``add()`` MUST
    leave a ``<root>/records/<id>.yaml`` on disk."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-canonical-001"))
    example = make_solved_example(id_="ex-canonical-001", cve_id="CVE-2026-1111")
    await store.add(example, cap)

    yaml_path = tmp_path / "records" / "ex-canonical-001.yaml"
    assert yaml_path.is_file(), "canonical YAML record must be written"

    raw = yaml_path.read_text(encoding="utf-8")
    body = yaml.safe_load(raw)
    assert body["id"] == "ex-canonical-001"
    assert body["cve_id"] == "CVE-2026-1111"
    assert raw.endswith("\n"), "trailing newline required"
    store.close()


async def test_add_writes_top_level_keys_in_sorted_order(tmp_path: Path) -> None:
    """AC-1 sorted-key discipline — FULL top-level key ordering on the raw
    text. A ``sort_keys=False`` mutant on a model with multiple top-level
    fields must fail here."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-sort-001"))
    example = make_solved_example(id_="ex-sort-001")
    await store.add(example, cap)

    raw = (tmp_path / "records" / "ex-sort-001.yaml").read_text(encoding="utf-8")
    top_level_keys = [
        ln.split(":", 1)[0]
        for ln in raw.splitlines()
        if ln and not ln.startswith((" ", "#", "-", "\t"))
    ]
    assert len(top_level_keys) >= 2, "expected multiple top-level keys"
    assert top_level_keys == sorted(top_level_keys), (
        f"top-level keys must be sorted; got {top_level_keys}"
    )
    store.close()


# ---------------------------------------------------------------------------
# AC-2 + AC-5 — manifest.yaml chain_head matches digest()
# ---------------------------------------------------------------------------


async def test_chain_head_equals_digest_after_add(tmp_path: Path) -> None:
    """AC-5 consistency invariant: ``manifest.chain_head == store.digest()``
    after every successful add. Necessary but NOT sufficient on its own —
    both sides delegate to ``_compute_chain_head``; the next test is the
    independent oracle."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-chain-001"))
    await store.add(make_solved_example(id_="ex-a"), cap)
    await store.add(make_solved_example(id_="ex-b"), cap)

    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["chain_head"] == store.digest()
    assert manifest["records"] == ["ex-a", "ex-b"]
    assert manifest["schema_version"] == 1
    store.close()


async def test_chain_head_is_blake3_of_concatenated_canonical_yaml(tmp_path: Path) -> None:
    """AC-5 independent oracle — recomputes the expected hash from a
    different code path (read the YAML bytes directly, concatenate,
    hash). Catches rolls-over-IDs, sorted-order, hash-each-then-XOR
    mutants. Insertion order deliberately NOT sorted (b before a) so a
    ``sorted()`` mutant produces a||b and fails."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-oracle"))
    await store.add(make_solved_example(id_="ex-b"), cap)  # insert b FIRST
    await store.add(make_solved_example(id_="ex-a"), cap)  # then a

    expected = blake3.blake3(
        (tmp_path / "records" / "ex-b.yaml").read_bytes()
        + (tmp_path / "records" / "ex-a.yaml").read_bytes()
    ).hexdigest()
    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["chain_head"] == expected
    assert manifest["records"] == ["ex-b", "ex-a"]  # insertion order, not sorted
    assert store.digest() == StoreDigest(expected)
    store.close()


# ---------------------------------------------------------------------------
# AC-3 — _record_ids loaded from manifest, not chromadb
# ---------------------------------------------------------------------------


async def test_load_existing_record_ids_from_manifest(tmp_path: Path) -> None:
    """A fresh store seeded with two adds; close & reopen: ``_record_ids``
    must reflect manifest-order (which is insertion order)."""
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-reopen"))
    store_a = ChromaPersistentStore(root_dir=tmp_path)
    await store_a.add(make_solved_example(id_="ex-first"), cap)
    await store_a.add(make_solved_example(id_="ex-second"), cap)
    seeded_digest = store_a.digest()
    store_a.close()

    store_b = ChromaPersistentStore(root_dir=tmp_path)
    assert store_b._record_ids == ["ex-first", "ex-second"]  # noqa: SLF001 — fence
    assert store_b.digest() == seeded_digest
    store_b.close()


# ---------------------------------------------------------------------------
# AC-4 — chromadb-write failure leaves YAML orphan, no manifest update
# ---------------------------------------------------------------------------


class _ChromaAddFailure(RuntimeError):
    """Named subclass so ``pytest.raises`` catches a precise type, not bare
    Exception (AC-4 test-quality discipline)."""


async def test_chromadb_failure_on_first_add_leaves_yaml_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First-ever add fails inside chromadb: YAML record exists,
    ``manifest.yaml`` does NOT exist, ``_record_ids`` unchanged, the
    named exception is re-raised."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-fail-first"))
    example = make_solved_example(id_="ex-fail-first")

    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise _ChromaAddFailure("simulated chroma failure")

    monkeypatch.setattr("codegenie.rag.store.asyncio.to_thread", _raise)

    with pytest.raises(_ChromaAddFailure):
        await store.add(example, cap)

    assert (tmp_path / "records" / "ex-fail-first.yaml").is_file()
    assert not (tmp_path / "manifest.yaml").exists()
    assert "ex-fail-first" not in store._record_ids  # noqa: SLF001
    store.close()


async def test_chromadb_failure_on_nth_add_leaves_manifest_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nth add fails: snapshot manifest bytes BEFORE failing add, then
    assert byte-unchanged AFTER (a manifest that *was* rewritten would
    differ even when listing the same ids)."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-nth"))
    await store.add(make_solved_example(id_="ex-good"), cap)

    manifest_bytes_before = (tmp_path / "manifest.yaml").read_bytes()

    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise _ChromaAddFailure("simulated chroma failure on Nth add")

    monkeypatch.setattr("codegenie.rag.store.asyncio.to_thread", _raise)
    with pytest.raises(_ChromaAddFailure):
        await store.add(make_solved_example(id_="ex-fail-nth"), cap)

    assert (tmp_path / "manifest.yaml").read_bytes() == manifest_bytes_before
    assert (tmp_path / "records" / "ex-fail-nth.yaml").is_file()  # orphan
    assert "ex-fail-nth" not in store._record_ids  # noqa: SLF001
    store.close()


# ---------------------------------------------------------------------------
# AC-7 — chain_head deterministic across two stores in same order
# ---------------------------------------------------------------------------


async def test_two_stores_same_order_produce_identical_manifest_bytes(
    tmp_path: Path,
) -> None:
    """AC-7 byte-identity — raw ``read_bytes()`` comparison, NEVER
    ``safe_load`` of both sides (parsing into dicts hides ``sort_keys`` /
    float-format divergence)."""
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-determ"))
    root_a = tmp_path / "store-a"
    root_b = tmp_path / "store-b"

    for root in (root_a, root_b):
        store = ChromaPersistentStore(root_dir=root)
        for rid in ("ex-1", "ex-2", "ex-3"):
            await store.add(make_solved_example(id_=rid), cap)
        store.close()

    assert (root_a / "manifest.yaml").read_bytes() == (root_b / "manifest.yaml").read_bytes()


# ---------------------------------------------------------------------------
# AC-9 — malformed manifests fail loud with StoreCorrupted
# ---------------------------------------------------------------------------


def test_unknown_schema_version_raises_store_corrupted(tmp_path: Path) -> None:
    """A manifest with ``schema_version: 999`` MUST fail loud as
    ``StoreCorrupted`` — NEVER a raw ``pydantic.ValidationError``."""
    (tmp_path / "records").mkdir(parents=True)
    (tmp_path / "manifest.yaml").write_text(
        "schema_version: 999\nrecords: []\nchain_head: deadbeef\n",
        encoding="utf-8",
    )
    with pytest.raises(StoreCorrupted, match="schema_version"):
        ChromaPersistentStore(root_dir=tmp_path)


@pytest.mark.parametrize(
    ("manifest_text", "match_fragment"),
    [
        ("not: [valid: yaml", "valid YAML"),  # truncated/malformed YAML
        ("just_a_scalar_value", "manifest"),  # non-mapping top level
        ("records: []\nchain_head: deadbeef\n", "schema_version"),  # missing schema_version
        ("schema_version: 1\nchain_head: deadbeef\n", "manifest"),  # missing records
        ("schema_version: 1\nrecords: []\n", "manifest"),  # missing chain_head
        ("schema_version: 1\nrecords: 'not_a_list'\nchain_head: x\n", "manifest"),  # wrong type
    ],
)
def test_malformed_manifest_raises_store_corrupted(
    tmp_path: Path, manifest_text: str, match_fragment: str
) -> None:
    """Every corrupt-manifest case translates to ``StoreCorrupted`` —
    NEVER ``yaml.YAMLError`` / ``pydantic.ValidationError`` leak through."""
    (tmp_path / "records").mkdir(parents=True)
    (tmp_path / "manifest.yaml").write_text(manifest_text, encoding="utf-8")
    with pytest.raises(StoreCorrupted, match=match_fragment):
        ChromaPersistentStore(root_dir=tmp_path)


# ---------------------------------------------------------------------------
# AC-10 — SolvedExample.from_yaml round-trip + negative
# ---------------------------------------------------------------------------


async def test_from_yaml_roundtrips_a_written_record(tmp_path: Path) -> None:
    """``SolvedExample.from_yaml`` on a record written by ``add()``
    reproduces the original ``SolvedExample`` (Pydantic structural
    equality)."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-from-yaml"))
    original = make_solved_example(id_="ex-roundtrip")
    await store.add(original, cap)

    restored = SolvedExample.from_yaml(tmp_path / "records" / "ex-roundtrip.yaml")
    assert restored == original
    store.close()


def test_from_yaml_raises_validation_error_on_malformed(tmp_path: Path) -> None:
    """``from_yaml`` on a YAML file with a missing required field surfaces
    a ``pydantic.ValidationError`` for S4-07 to wrap."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: only-id-no-other-fields\n", encoding="utf-8")
    with pytest.raises(pydantic.ValidationError):
        SolvedExample.from_yaml(bad)


# ---------------------------------------------------------------------------
# AC-12 — manifest-write failure leaves YAML + chroma on disk, manifest stale
# ---------------------------------------------------------------------------


async def test_manifest_write_failure_leaves_yaml_and_chroma_intact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-12 — if manifest write fails *after* chromadb succeeded: YAML
    record present, chromadb has the record, ``manifest.yaml`` does NOT
    list ``example.id``, ``add()`` re-raised the named exception."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-manifest-fail"))
    await store.add(make_solved_example(id_="ex-pre"), cap)

    real_write = Path.write_text

    class _ManifestWriteFail(RuntimeError):
        pass

    def _selective_fail(self: Path, *a: object, **kw: object) -> int:
        if self.name == "manifest.yaml.tmp":
            raise _ManifestWriteFail("simulated manifest write failure")
        return real_write(self, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", _selective_fail)
    with pytest.raises(_ManifestWriteFail):
        await store.add(make_solved_example(id_="ex-post"), cap)

    assert (tmp_path / "records" / "ex-post.yaml").is_file()
    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert "ex-post" not in manifest["records"]
    assert manifest["records"] == ["ex-pre"]
    store.close()


# ---------------------------------------------------------------------------
# AC-13 — manifest references a missing record file → StoreCorrupted
# ---------------------------------------------------------------------------


def test_manifest_references_missing_record_file_raises_store_corrupted(
    tmp_path: Path,
) -> None:
    """A manifest listing ``ex-missing`` with no ``ex-missing.yaml`` on
    disk MUST raise ``StoreCorrupted`` — NEVER ``FileNotFoundError``."""
    (tmp_path / "records").mkdir(parents=True)
    (tmp_path / "manifest.yaml").write_text(
        "schema_version: 1\nrecords:\n  - ex-missing\nchain_head: deadbeef\n",
        encoding="utf-8",
    )
    with pytest.raises(StoreCorrupted, match="missing record"):
        ChromaPersistentStore(root_dir=tmp_path)


# ---------------------------------------------------------------------------
# AC-14 — record id is filesystem-path-safe (path-traversal rejection)
# ---------------------------------------------------------------------------


async def test_record_id_with_path_traversal_rejected_before_write(
    tmp_path: Path,
) -> None:
    """``id="../../etc/passwd"`` MUST NOT reach a filesystem write. Bare
    ``NewType`` accepts any str so this guard lives in ``add()``."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-traversal"))

    for danger in ("../../etc/passwd", "a/b", "..", ".hidden", "", "ok\x00"):
        example = make_solved_example(id_=danger)
        with pytest.raises(ValueError):
            await store.add(example, cap)
    # NO sibling/escape files created anywhere outside records/
    sibling = tmp_path.parent / "etc"
    assert not sibling.exists()
    store.close()


# ---------------------------------------------------------------------------
# AC-15 — empty-store invariants
# ---------------------------------------------------------------------------


def test_empty_store_has_no_manifest_and_empty_chain_digest(tmp_path: Path) -> None:
    """Fresh store: ``_record_ids == []``, NO ``manifest.yaml``,
    ``digest()`` equals the empty-chain BLAKE3 constant."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    assert store._record_ids == []  # noqa: SLF001
    assert not (tmp_path / "manifest.yaml").exists()
    assert store.digest() == StoreDigest(_EMPTY_BLAKE3)
    store.close()


async def test_empty_store_writes_manifest_on_first_add(tmp_path: Path) -> None:
    """After the first ``add()``, ``manifest.yaml`` exists and lists the
    single new record."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-empty-first"))
    await store.add(make_solved_example(id_="ex-only"), cap)

    assert (tmp_path / "manifest.yaml").is_file()
    manifest = yaml.safe_load((tmp_path / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["records"] == ["ex-only"]
    assert manifest["schema_version"] == 1
    store.close()
