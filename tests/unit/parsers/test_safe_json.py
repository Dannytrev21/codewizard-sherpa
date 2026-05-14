"""Unit tests for ``codegenie.parsers.safe_json`` (S1-02).

Pins the contract from
``docs/phases/01-context-gather-layer-a-node/stories/S1-02-safe-json-parser.md``
and arch §"Component design" #8 + ADR-0008 / ADR-0009. The Phase-0
markers-only invariant means every raised typed exception is constructed
with **exactly one positional formatted message string** and carries no
instance state — recoverable detail lives in ``args[0]``.
"""

from __future__ import annotations

import inspect
import json
import os
import tracemalloc
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.parsers import JSONValue, safe_json  # noqa: F401  # AC-2 surface
from codegenie.parsers.safe_json import load

# --- Happy path & surface --------------------------------------------------


def test_happy_path_returns_dict(tmp_path: Path) -> None:
    p = tmp_path / "package.json"
    p.write_text(json.dumps({"name": "x", "version": "1.0.0"}))
    out = load(p, max_bytes=5_242_880)
    assert isinstance(out, dict)
    assert out["name"] == "x"
    assert out["version"] == "1.0.0"


def test_module_docstring_references_arch_and_adrs() -> None:
    # AC-3 — module docstring is part of the contract; a mutation that drops
    # it or strips the references regresses an audit invariant.
    doc = (safe_json.__doc__ or "").lower()
    assert "component design" in doc and "#8" in doc
    assert "adr-0008" in doc
    assert "adr-0009" in doc


def test_parsers_package_docstring_references_arch_and_adr() -> None:
    # AC-1 — parsers/__init__.py module docstring names arch + ADR-0008.
    import codegenie.parsers as pkg

    doc = (pkg.__doc__ or "").lower()
    assert "component design" in doc and "#8" in doc
    assert "adr-0008" in doc


def test_load_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    sig = inspect.signature(load)
    params = sig.parameters
    assert params["path"].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )
    assert params["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].default == 64


# --- Open / O_NOFOLLOW / errno mapping -------------------------------------


def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    # AC-5 + TQ2 — symlink target carries a sentinel that would be visible if
    # O_NOFOLLOW were dropped. A mutation using plain os.open(O_RDONLY) would
    # return the sentinel dict instead of raising.
    target = tmp_path / "outside_sentinel.json"
    target.write_text(json.dumps({"sentinel": "leaked"}))
    link = tmp_path / "package.json"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError) as exc_info:
        load(link, max_bytes=5_000)
    assert str(link) in exc_info.value.args[0]
    assert "O_NOFOLLOW" in exc_info.value.args[0]
    # Phase-0 markers-only invariant — exception exposes no instance state.
    for forbidden in ("path", "cap", "detail"):
        assert not hasattr(exc_info.value, forbidden)


def test_file_not_found_passes_through_unchanged(tmp_path: Path) -> None:
    # AC-5 — FileNotFoundError is OSError(errno=ENOENT); it must NOT be
    # smuggled into SymlinkRefusedError. Concrete type assertion guards
    # against a too-broad except OSError.
    with pytest.raises(FileNotFoundError) as exc_info:
        load(tmp_path / "missing.json", max_bytes=5_000)
    assert not isinstance(exc_info.value, e.SymlinkRefusedError)


def test_is_a_directory_passes_through(tmp_path: Path) -> None:
    # AC-5 — EISDIR must NOT be translated into SymlinkRefusedError.
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(OSError) as exc_info:
        load(d, max_bytes=5_000)
    assert not isinstance(exc_info.value, e.SymlinkRefusedError)


# --- Size cap pre-parse ----------------------------------------------------


def test_size_cap_raises_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-6 + TQ3 — size check must precede os.read. Monkey-patch os.read to
    # raise; the SizeCapExceeded path must still fire (because os.read was
    # never called).
    p = tmp_path / "big.json"
    p.write_text("0" * 1024)
    read_calls: list[int] = []

    def _trap_read(fd: int, n: int) -> bytes:  # pragma: no cover - asserted
        read_calls.append(n)
        raise RuntimeError("os.read must not be called when size cap exceeded")

    monkeypatch.setattr(os, "read", _trap_read)
    with pytest.raises(e.SizeCapExceeded) as exc_info:
        load(p, max_bytes=100)
    assert read_calls == []
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "cap=100" in msg
    assert "size=1024" in msg


def test_short_read_translates_to_malformed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-7 — forced short read must raise MalformedJSONError; no silent retry.
    # After S1-03 lifted the open+read primitive into ``parsers/_io``, a short
    # ``os.read`` returns truncated bytes; ``json.loads`` then raises and is
    # translated to ``MalformedJSONError``. The behavioural contract — short
    # read surfaces as a typed parse error, not a silent partial dict — is
    # preserved; the error message changed from "short read" to the underlying
    # ``json.JSONDecodeError`` detail.
    p = tmp_path / "small.json"
    p.write_text(json.dumps({"k": "v"}))
    real_read = os.read

    def _short(fd: int, n: int) -> bytes:
        return real_read(fd, max(1, n // 2))  # always short

    monkeypatch.setattr(os, "read", _short)
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert str(p) in exc_info.value.args[0]


# --- Malformed / shape -----------------------------------------------------


def test_malformed_json_translates_typed(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json}")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert str(p) in exc_info.value.args[0]
    # AC-8 — raw bytes (`exc.doc`) MUST NOT appear in the message.
    assert "{not json}" not in exc_info.value.args[0]


def test_malformed_json_detail_truncated_to_200_chars(tmp_path: Path) -> None:
    # AC-8 — detail is bounded by ~200 chars (prevents log-bloat / secret-leak).
    p = tmp_path / "bad.json"
    p.write_text("{")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    # Total message = "{path}: {detail}" — detail bounded at 200; path is
    # short here, so total stays under 200 + path-len + 2.
    msg = exc_info.value.args[0]
    detail = msg.split(": ", 1)[1]
    assert len(detail) <= 200


def test_top_level_non_object_is_malformed(tmp_path: Path) -> None:
    # AC-9 — function returns dict[str, JSONValue]; non-object roots must
    # raise rather than silently returning a list.
    p = tmp_path / "arr.json"
    p.write_text("[1, 2, 3]")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "expected JSON object" in exc_info.value.args[0]


def test_top_level_scalar_is_malformed(tmp_path: Path) -> None:
    # AC-9 — scalar root also rejected.
    p = tmp_path / "scalar.json"
    p.write_text("42")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


def test_top_level_null_is_malformed(tmp_path: Path) -> None:
    # AC-9 — null root also rejected.
    p = tmp_path / "null.json"
    p.write_text("null")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


def test_empty_file_is_malformed(tmp_path: Path) -> None:
    # AC-10 — never silently return {}.
    p = tmp_path / "empty.json"
    p.write_text("")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


# --- Depth walker — boundary + mixed shapes --------------------------------


def _nested_dicts(depth: int) -> dict[str, Any]:
    """Produce a dict with a leaf at the given nesting depth.

    Depth is counted as the number of dict-edges between the top-level dict
    and the leaf. depth=0 means a flat dict with a scalar leaf.
    """
    out: dict[str, Any] = {}
    cur: dict[str, Any] = out
    for _ in range(depth):
        nxt: dict[str, Any] = {}
        cur["x"] = nxt
        cur = nxt
    cur["leaf"] = True
    return out


def _mixed_nesting(depth: int) -> dict[str, Any]:
    """A dict whose leaf sits inside `depth` alternating list/dict layers."""
    leaf: object = "leaf"
    for i in range(depth):
        leaf = [leaf] if i % 2 == 0 else {"k": leaf}
    return {"root": leaf}


@pytest.mark.parametrize("inner_depth", [0, 1, 63, 64])
def test_depth_at_or_below_cap_passes(tmp_path: Path, inner_depth: int) -> None:
    # AC-12 — depth at/below cap is accepted. The walker counts container
    # nesting (dicts + lists) only; the terminal scalar leaf does not
    # increment depth. `_nested_dicts(N)` produces N nested "x" containers
    # plus the innermost dict that holds the leaf — its deepest container
    # sits at depth N, exactly matching the cap when inner_depth == 64.
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    out = load(p, max_bytes=10_000_000, max_depth=64)
    assert isinstance(out, dict)


@pytest.mark.parametrize("inner_depth", [65, 70, 200])
def test_depth_above_cap_raises(tmp_path: Path, inner_depth: int) -> None:
    # AC-11 + AC-12 — depth above cap raises.
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    with pytest.raises(e.DepthCapExceeded) as exc_info:
        load(p, max_bytes=10_000_000, max_depth=64)
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "depth>64" in msg


def test_depth_walker_descends_into_lists(tmp_path: Path) -> None:
    # AC-11 / CV1 / TQ4 — a dict-only walker would miss this.
    p = tmp_path / "list_bomb.json"
    p.write_text(json.dumps(_mixed_nesting(100)))
    with pytest.raises(e.DepthCapExceeded):
        load(p, max_bytes=10_000_000, max_depth=64)


def test_depth_walker_handles_pure_list_nesting(tmp_path: Path) -> None:
    # AC-11 — list-of-list bomb wrapped in a top-level object.
    p = tmp_path / "lol.json"
    deep: object = "leaf"
    for _ in range(100):
        deep = [deep]
    p.write_text(json.dumps({"root": deep}))
    with pytest.raises(e.DepthCapExceeded):
        load(p, max_bytes=10_000_000, max_depth=64)


# --- Markers-only contract preserved (Phase-0 invariant) -------------------


def test_raised_markers_carry_no_instance_state(tmp_path: Path) -> None:
    # AC-16, AC-17 — every Phase-1 typed exception this module raises is a
    # marker; path/cap/detail are recoverable from args[0] only.
    fixtures: list[tuple[Path, int, int, type[BaseException]]] = []
    big = tmp_path / "big.json"
    big.write_text("0" * 1024)
    fixtures.append((big, 100, 64, e.SizeCapExceeded))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json}")
    fixtures.append((bad, 5_000, 64, e.MalformedJSONError))
    deep = tmp_path / "deep.json"
    deep.write_text(json.dumps(_nested_dicts(70)))
    fixtures.append((deep, 10_000_000, 64, e.DepthCapExceeded))
    for path, cap, depth, exc_type in fixtures:
        with pytest.raises(exc_type) as exc_info:
            load(path, max_bytes=cap, max_depth=depth)
        assert isinstance(exc_info.value.args, tuple)
        assert len(exc_info.value.args) == 1
        assert isinstance(exc_info.value.args[0], str)
        assert str(path) in exc_info.value.args[0]
        for forbidden in ("path", "cap", "detail", "warning_id"):
            assert not hasattr(exc_info.value, forbidden), (
                f"{exc_type.__name__} must remain a marker; instance must not carry {forbidden!r}"
            )


# --- FD lifecycle ----------------------------------------------------------


def test_fd_closed_on_every_exit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-4 — every load that opened an fd must close it. Tracks open/close
    # symmetry across happy, size-cap, malformed, and depth-cap paths.
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def _open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def _close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "open", _open)
    monkeypatch.setattr(os, "close", _close)

    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"a": 1}))
    load(ok, max_bytes=5_000)

    big = tmp_path / "big.json"
    big.write_text("0" * 1024)
    with pytest.raises(e.SizeCapExceeded):
        load(big, max_bytes=100)

    bad = tmp_path / "bad.json"
    bad.write_text("{not json}")
    with pytest.raises(e.MalformedJSONError):
        load(bad, max_bytes=5_000)

    deep = tmp_path / "deep.json"
    deep.write_text(json.dumps(_nested_dicts(70)))
    with pytest.raises(e.DepthCapExceeded):
        load(deep, max_bytes=10_000_000, max_depth=64)

    assert opened == closed, f"fd leak: opened={opened} closed={closed}"


def test_symlink_path_opens_no_fd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-4 — symlink refusal never opens an fd, so closes nothing.
    opened: list[int] = []
    closed: list[int] = []
    real_open = os.open
    real_close = os.close

    def _open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    def _close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "open", _open)
    monkeypatch.setattr(os, "close", _close)

    target = tmp_path / "t.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError):
        load(link, max_bytes=5_000)
    assert opened == []
    assert closed == []


# --- Cap event emission ----------------------------------------------------


def test_size_cap_emits_event(tmp_path: Path) -> None:
    # AC-13.
    p = tmp_path / "big.json"
    p.write_text("0" * 1024)
    with capture_logs() as logs:
        with pytest.raises(e.SizeCapExceeded):
            load(p, max_bytes=100)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1, f"expected exactly one cap event; got {cap_events}"
    ev = cap_events[0]
    assert ev["cap_kind"] == "size"
    assert ev["path"] == str(p)
    assert ev["parser"] == "safe_json"
    assert ev["parser_kind"] == "safe_json"


def test_depth_cap_emits_event(tmp_path: Path) -> None:
    # AC-14.
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(_nested_dicts(70)))
    with capture_logs() as logs:
        with pytest.raises(e.DepthCapExceeded):
            load(p, max_bytes=10_000_000, max_depth=64)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["cap_kind"] == "depth"
    assert ev["path"] == str(p)
    assert ev["parser"] == "safe_json"
    assert ev["parser_kind"] == "safe_json"


def test_no_cap_event_on_happy_path(tmp_path: Path) -> None:
    # AC-15.
    p = tmp_path / "ok.json"
    p.write_text(json.dumps({"a": 1}))
    with capture_logs() as logs:
        load(p, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]


def test_no_cap_event_on_malformed_or_symlink(tmp_path: Path) -> None:
    # AC-15 — cap-exceeded event must not fire for non-cap failures.
    bad = tmp_path / "bad.json"
    bad.write_text("{not json}")
    with capture_logs() as logs:
        with pytest.raises(e.MalformedJSONError):
            load(bad, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    target = tmp_path / "t.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with capture_logs() as logs:
        with pytest.raises(e.SymlinkRefusedError):
            load(link, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]


# --- Read-budget bound (RAM-safety canary) ---------------------------------


def test_size_cap_bounds_memory_allocation(tmp_path: Path) -> None:
    # AC-6 (anti-mutation TQ3) — a 50 MB sparse file with a 1 KB cap must not
    # cause the parser to allocate ~50 MB; if read were ordered before the
    # cap check, tracemalloc would catch it.
    p = tmp_path / "sparse.json"
    with open(p, "wb") as f:
        f.seek(50 * 1024 * 1024 - 1)
        f.write(b"\x00")  # sparse where the FS supports it
    tracemalloc.start()
    try:
        with pytest.raises(e.SizeCapExceeded):
            load(p, max_bytes=1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 2 * 1024 * 1024, f"peak alloc {peak} bytes exceeded 2 MB cap"


# --- S1-01 follow-up — SymlinkRefusedError docstring extension -------------


def test_symlink_refused_error_doc_names_parsers() -> None:
    # AC-18 — the Phase-0 marker's raise inventory now also covers parsers.
    doc = (e.SymlinkRefusedError.__doc__ or "").lower()
    assert "parsers" in doc or "safe_json" in doc
    # Slug still in DOCUMENTED_MODULE_SLUGS; pre-existing writer/sanitizer
    # callers must still be named so the slug test continues to pass.
    assert "writer" in doc or "sanitizer" in doc
