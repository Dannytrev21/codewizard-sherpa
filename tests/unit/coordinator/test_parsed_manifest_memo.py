"""Unit tests for ``ParsedManifestMemo`` — S1-07.

Each test is annotated with the AC it pins and the mutation it catches.
The harness uses ``structlog.testing.capture_logs`` for event assertions
(matches the S1-02..S1-05 hardened precedent); failure paths use
:class:`pytest.raises` for the four typed parser exceptions exposed by
:mod:`codegenie.errors`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import MappingProxyType

import pytest
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.coordinator.parsed_manifest_memo import ParsedManifestMemo


def _write(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload))
    return p


# AC-2 — allowlist injection (kernel/policy split; Open/Closed seam)
def test_init_accepts_default_allowlist() -> None:
    m = ParsedManifestMemo()
    assert "package.json" in m._allowlist  # noqa: SLF001 — internal contract pinned


def test_init_accepts_custom_allowlist() -> None:
    m = ParsedManifestMemo(allowlist=frozenset({"package.json", "scip-index.json"}))
    assert "scip-index.json" in m._allowlist  # noqa: SLF001


@pytest.mark.parametrize(
    "allowlist",
    [
        frozenset({"package.json"}),
        frozenset({"package.json", "scip-index.json"}),
    ],
)
def test_allowlist_is_kwarg_only_with_injection_path(allowlist: frozenset[str]) -> None:
    m = ParsedManifestMemo(allowlist=allowlist)
    assert m._allowlist == allowlist  # noqa: SLF001


# AC-3, AC-5 — first call parses, wraps result in MappingProxyType
def test_first_call_parses_and_returns_mappingproxy(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})
    out = ParsedManifestMemo().get(p)
    assert isinstance(out, MappingProxyType)
    assert out is not None
    assert out["name"] == "x"


# AC-6 — identity contract on cache hit (S2-04 warm-path test depends on this)
def test_second_call_returns_same_instance(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    a = m.get(p)
    b = m.get(p)
    # Mutation: ``return MappingProxyType(dict(hit))`` (rewrap on hit) would
    # break this assertion. The identity contract is load-bearing for the
    # warm-path memo.hit==1 invariant across the four package.json consumers.
    assert a is b


# AC-7 — mtime change triggers re-parse
def test_mtime_change_triggers_reparse(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    a = m.get(p)
    time.sleep(0.01)
    now_ns = time.time_ns()
    os.utime(p, ns=(now_ns, now_ns))
    b = m.get(p)
    assert a is not b
    # Mutation dropping ``st_mtime_ns`` from the key tuple would let ``b is a``.


# AC-8 — size change triggers re-parse
def test_size_change_triggers_reparse(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    a = m.get(p)
    p.write_text(json.dumps({"name": "xxxxxxxxxxxxxxxxxxxxxx"}))
    b = m.get(p)
    assert a is not b
    # Mutation dropping ``st_size`` from the key tuple would let ``b is a``
    # whenever the rewritten file shares the prior mtime (file-system mtime
    # resolution is finite; for tests this can flake without size in the key).


# AC-5, AC-9 — key shape pinned (str, int, int) with ns mtime
def test_key_shape_is_str_int_int_ns_mtime(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    m.get(p)
    (key,) = m._cache.keys()  # noqa: SLF001
    assert isinstance(key[0], str)
    assert isinstance(key[1], int)  # ns mtime; a float-seconds mutant fails type
    assert isinstance(key[2], int)  # size
    assert key[0] == str(p.resolve())
    assert key[1] == p.stat().st_mtime_ns
    assert key[2] == p.stat().st_size


# AC-4 — non-allowlisted path returns None
def test_non_allowlisted_path_returns_none(tmp_path: Path) -> None:
    p = _write(tmp_path, "yarn.lock", {"k": 1})
    assert ParsedManifestMemo().get(p) is None


# AC-4 — allowlist comparison is case-sensitive
def test_allowlist_is_case_sensitive(tmp_path: Path) -> None:
    p = _write(tmp_path, "Package.json", {"name": "x"})  # capital P
    assert ParsedManifestMemo().get(p) is None
    # Mutation: ``path.name.lower() in allowlist`` would pass this as not-None.


# AC-10 — malformed JSON propagates and does not cache
def test_parse_failure_does_not_cache(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text("{not json}")
    m = ParsedManifestMemo()
    with pytest.raises(e.MalformedJSONError):
        m.get(p)
    assert m._cache == {}  # noqa: SLF001
    # Repair + retry returns parsed value (failure does not poison the memo).
    p.write_text(json.dumps({"name": "ok"}))
    out = m.get(p)
    assert out is not None
    assert out["name"] == "ok"


# AC-10 — SizeCapExceeded propagates and does not cache
def test_size_cap_exceeded_does_not_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write(tmp_path, "package.json", {"k": "x" * 100})
    m = ParsedManifestMemo()

    def _raise(*_a: object, **_kw: object) -> object:
        raise e.SizeCapExceeded("simulated cap breach")

    monkeypatch.setattr("codegenie.coordinator.parsed_manifest_memo.safe_json.load", _raise)
    with pytest.raises(e.SizeCapExceeded):
        m.get(p)
    assert m._cache == {}  # noqa: SLF001


# AC-10 — DepthCapExceeded propagates and does not cache
def test_depth_cap_exceeded_does_not_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write(tmp_path, "package.json", {"k": 1})
    m = ParsedManifestMemo()

    def _raise(*_a: object, **_kw: object) -> object:
        raise e.DepthCapExceeded("simulated depth breach")

    monkeypatch.setattr("codegenie.coordinator.parsed_manifest_memo.safe_json.load", _raise)
    with pytest.raises(e.DepthCapExceeded):
        m.get(p)
    assert m._cache == {}  # noqa: SLF001


# AC-11 — symlink path: stat() succeeds, safe_json refuses; failure not cached,
# replacement file at same path retries cleanly
def test_symlink_path_raises_and_does_not_cache(tmp_path: Path) -> None:
    target = _write(tmp_path, "real_package.json", {"name": "x"})
    link = tmp_path / "package.json"
    link.symlink_to(target)
    m = ParsedManifestMemo()
    with pytest.raises(e.SymlinkRefusedError):
        m.get(link)
    assert m._cache == {}  # noqa: SLF001
    link.unlink()
    link.write_text(json.dumps({"name": "ok"}))
    out = m.get(link)
    assert out is not None
    assert out["name"] == "ok"


# AC-12 — missing file returns None (no raise)
def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert ParsedManifestMemo().get(tmp_path / "no-such" / "package.json") is None


# AC-12 — PermissionError on stat() propagates (only FileNotFoundError is swallowed)
def test_permission_error_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})

    def _raise(_self: Path) -> object:
        raise PermissionError("simulated")

    monkeypatch.setattr(Path, "stat", _raise)
    with pytest.raises(PermissionError):
        ParsedManifestMemo().get(p)


# AC-13 — structured event shape on miss + hit
def test_emits_memo_hit_and_miss_events_with_structured_fields(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})
    m = ParsedManifestMemo()
    with capture_logs() as logs:
        m.get(p)  # miss
        m.get(p)  # hit

    miss = next(r for r in logs if r["event"] == "probe.memo.miss")
    hit = next(r for r in logs if r["event"] == "probe.memo.hit")
    assert miss["path"] == str(p.resolve())
    assert miss["allowlist_match"] == "package.json"
    assert hit["path"] == str(p.resolve())
    assert hit["allowlist_match"] == "package.json"


# AC-13 — no event on parse failure
def test_no_event_on_parse_failure(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text("{not json}")
    m = ParsedManifestMemo()
    with capture_logs() as logs, pytest.raises(e.MalformedJSONError):
        m.get(p)
    assert not any(r["event"].startswith("probe.memo.") for r in logs)


# AC-14 — no-disk-write invariant
def test_memo_does_not_write_to_disk(tmp_path: Path) -> None:
    p = _write(tmp_path, "package.json", {"name": "x"})

    def _snapshot() -> set[tuple[str, int, int]]:
        return {
            (str(q.relative_to(tmp_path)), q.stat().st_size, q.stat().st_mtime_ns)
            for q in tmp_path.rglob("*")
            if q.is_file()
        }

    before = _snapshot()
    ParsedManifestMemo().get(p)
    after = _snapshot()
    assert before == after


# AC-1, AC-20 — module surface is closed for modification: only ParsedManifestMemo is public
def test_module_only_public_symbol_is_parsedmanifestmemo() -> None:
    import codegenie.coordinator.parsed_manifest_memo as mod

    assert mod.__all__ == ["ParsedManifestMemo"]


# AC-1 — module docstring names the three required reference anchors
def test_module_docstring_names_arch_adr_and_msgpack_rejection() -> None:
    import codegenie.coordinator.parsed_manifest_memo as mod

    doc = mod.__doc__ or ""
    assert "Component design" in doc
    assert "ADR-0002" in doc
    assert "msgpack" in doc


# ---------------------------------------------------------------------------
# S1-08 — AC-14: memo dual-key shapes coexist; identity preserved per key
# ---------------------------------------------------------------------------
def test_memo_dual_keys_coexist(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x"}))
    memo = ParsedManifestMemo()
    a = memo.get(p, content_hash="blake3:abc")
    b = memo.get(p)  # content_hash=None → legacy stat-tuple key
    assert a is not None
    assert b is not None
    # Two distinct cache entries — one per key shape.
    assert len(memo._cache) == 2  # noqa: SLF001 — internal contract pinned
    # Identity under the same key.
    a2 = memo.get(p, content_hash="blake3:abc")
    b2 = memo.get(p)
    assert a is a2
    assert b is b2
    # Mutation that conflates the two key shapes is caught.


# ---------------------------------------------------------------------------
# S1-08 — AC-15: sentinel content_hash bypasses the memo
# ---------------------------------------------------------------------------
def test_memo_sentinel_content_hash_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text("{}")
    memo = ParsedManifestMemo()
    assert memo.get(p, content_hash="<refused>") is None
    assert memo.get(p, content_hash="<oversize>") is None
    # Cache stays empty — sentinel inputs do not write entries.
    assert len(memo._cache) == 0  # noqa: SLF001 — internal contract pinned
