"""Unit tests for ``codegenie.parsers.jsonc``.

Pinned to the acceptance criteria in
``docs/phases/01-context-gather-layer-a-node/stories/S1-04-jsonc-parser.md``.
"""

from __future__ import annotations

import ast
import errno
import inspect
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.parsers import JSONValue, jsonc  # noqa: F401  # AC-2 surface
from codegenie.parsers.jsonc import _strip_comments, load

# --- Module surface & invariants -------------------------------------------


def test_module_docstring_references_arch_and_adrs() -> None:
    # AC-3.
    doc = (jsonc.__doc__ or "").lower()
    assert "component design" in doc and "#8" in doc
    assert "adr-0008" in doc
    assert "adr-0009" in doc


def test_load_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    # AC-1.
    sig = inspect.signature(load)
    params = sig.parameters
    assert params["path"].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )
    assert params["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["max_depth"].default == 64


def test_module_all_exports_load() -> None:
    # AC-2.
    assert "load" in jsonc.__all__


def test_module_does_not_import_re() -> None:
    # AC-4 / TQ16 — regex on hostile input is exactly what ADR-0008 mitigates.
    src = Path(jsonc.__file__).read_text()
    tree = ast.parse(src)
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    assert "re" not in imports, f"jsonc module must not import re; got imports={imports}"


# --- Open / O_NOFOLLOW / errno mapping -------------------------------------


def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    # AC-5 + AC-6 + TQ2 — symlink target carries a sentinel. A mutation that
    # drops O_NOFOLLOW would silently dereference and return the sentinel dict.
    target = tmp_path / "outside_sentinel.json"
    target.write_text(json.dumps({"sentinel": "leaked"}))
    link = tmp_path / "tsconfig.json"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError) as exc_info:
        load(link, max_bytes=5_000)
    assert str(link) in exc_info.value.args[0]
    assert "O_NOFOLLOW" in exc_info.value.args[0]
    for forbidden in ("path", "cap", "detail"):
        assert not hasattr(exc_info.value, forbidden)


def test_file_not_found_passes_through_unchanged(tmp_path: Path) -> None:
    # AC-5 — FileNotFoundError (ENOENT) must NOT be smuggled into SymlinkRefusedError.
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


def test_eloop_translates_to_symlink_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-5 — narrow check: only errno == ELOOP translates.
    real_open = os.open

    def _fake_open(path: Any, *args: Any, **kwargs: Any) -> int:
        if str(path).endswith("eloop.json"):
            raise OSError(errno.ELOOP, "synthetic ELOOP")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", _fake_open)
    p = tmp_path / "eloop.json"
    p.write_text("{}")
    with pytest.raises(e.SymlinkRefusedError) as exc_info:
        load(p, max_bytes=5_000)
    assert "O_NOFOLLOW" in exc_info.value.args[0]


# --- Size cap pre-parse ----------------------------------------------------


def test_size_cap_raises_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-7 + TQ3 — size check must precede os.read.
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
    # AC-9 — forced short read raises MalformedJSONError; no silent retry.
    p = tmp_path / "small.json"
    p.write_text(json.dumps({"k": "v"}))
    real_read = os.read

    def _short(fd: int, n: int) -> bytes:
        return real_read(fd, max(1, n // 2))

    monkeypatch.setattr(os, "read", _short)
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "short read" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]


# --- Stripper purity & invariants ------------------------------------------


def test_strip_comments_is_pure_bytes_to_bytes() -> None:
    # AC-10 — _strip_comments is a pure function callable without a Path.
    out = _strip_comments(b'{"k": 1} // tail')
    assert isinstance(out, bytes)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"// line comment only\n",
        b'{"k": "all string"}',
        b"/* all comment */",
    ],
)
def test_strip_comments_length_invariant(data: bytes) -> None:
    # AC-11.
    out = _strip_comments(data)
    assert len(out) <= len(data)


# --- Stripper — comments ---------------------------------------------------


def test_line_comments_stripped(tmp_path: Path) -> None:
    # AC-12 — line comments to EOL stripped; terminating newline preserved.
    p = tmp_path / "tsconfig.json"
    p.write_text('{\n  "compilerOptions": {} // trailing comment\n}\n')
    out = load(p, max_bytes=10_000)
    assert out == {"compilerOptions": {}}


def test_block_comments_stripped(tmp_path: Path) -> None:
    # AC-13.
    p = tmp_path / "tsconfig.json"
    p.write_text('{\n  /* block */ "k": 1\n}\n')
    out = load(p, max_bytes=10_000)
    assert out == {"k": 1}


def test_nested_block_comments(tmp_path: Path) -> None:
    # AC-13 — nested block comments.
    p = tmp_path / "x.json"
    p.write_text('{ /* outer /* inner */ outer */ "k": 1 }')
    out = load(p, max_bytes=10_000)
    assert out["k"] == 1


# --- Stripper — strings: //, /*, */, escapes -------------------------------


def test_strings_containing_slash_slash_preserved(tmp_path: Path) -> None:
    # AC-14 — // inside a string is NOT a comment.
    p = tmp_path / "x.json"
    p.write_text('{"u": "https://example.com/path"}')
    out = load(p, max_bytes=10_000)
    assert out["u"] == "https://example.com/path"


def test_strings_containing_block_open_preserved(tmp_path: Path) -> None:
    # AC-14 — /* inside a string is NOT a block open.
    p = tmp_path / "x.json"
    p.write_text('{"k": "/* not a comment */"}')
    out = load(p, max_bytes=10_000)
    assert out["k"] == "/* not a comment */"


def test_escaped_quote_in_string(tmp_path: Path) -> None:
    # AC-14 — \" inside a string is NOT a terminator.
    p = tmp_path / "x.json"
    p.write_text(r'{"k": "she said \"hi\""}')
    out = load(p, max_bytes=10_000)
    assert out["k"] == 'she said "hi"'


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Each case: a JSONC payload where the string's terminator is correctly
        # identified despite various backslash patterns. Each is followed by a
        # real JSON token (`, "b": 0`) to catch mutations that misclassify
        # the closing quote.
        (r'{"a": "x\\\\y", "b": 0}', {"a": r"x\\y", "b": 0}),
        (r'{"a": "x\\\"y", "b": 0}', {"a": r"x\"y", "b": 0}),
        (r'{"a": "trail\\\\", "b": 0}', {"a": "trail\\\\", "b": 0}),
        (r'{"a": "\"", "b": 0}', {"a": '"', "b": 0}),
    ],
)
def test_string_with_backslash_escapes(tmp_path: Path, raw: str, expected: dict[str, Any]) -> None:
    # AC-14 — backslash-escape state-machine correctness.
    p = tmp_path / "x.json"
    p.write_text(raw)
    out = load(p, max_bytes=10_000)
    assert out == expected


def test_block_comment_containing_double_quote_is_inert(tmp_path: Path) -> None:
    # AC-15 / TQ6 — " in a block comment must NOT enter STRING state.
    p = tmp_path / "x.json"
    p.write_text('/* "fake" */ {"k": 1}')
    out = load(p, max_bytes=10_000)
    assert out["k"] == 1


# --- Stripper — unterminated paths -----------------------------------------


def test_unterminated_string_raises_typed_in_bounded_time(tmp_path: Path) -> None:
    # AC-16 + TQ11 — typed error + wall-clock budget.
    p = tmp_path / "x.json"
    p.write_text('{"k": "' + "x" * 1_000_000)
    t0 = time.monotonic()
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=2_000_000)
    elapsed = time.monotonic() - t0
    assert "unterminated string" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]
    assert elapsed <= 0.5, f"unterminated-string detection took {elapsed:.3f}s; expected ≤ 0.5s"


def test_unterminated_block_comment_raises_typed_in_bounded_time(tmp_path: Path) -> None:
    # AC-16 + TQ12 — typed error + wall-clock budget.
    p = tmp_path / "x.json"
    p.write_text("{ /* " + ("x" * 1_000_000))
    t0 = time.monotonic()
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=2_000_000)
    elapsed = time.monotonic() - t0
    assert "unterminated block comment" in exc_info.value.args[0]
    assert str(p) in exc_info.value.args[0]
    assert elapsed <= 0.5, f"unterminated-block detection took {elapsed:.3f}s; expected ≤ 0.5s"


# --- Decode / shape --------------------------------------------------------


def test_malformed_json_message_truncated_and_no_doc_bytes(tmp_path: Path) -> None:
    # AC-17 — JSONDecodeError detail bounded; exc.doc bytes never included.
    p = tmp_path / "bad.json"
    p.write_text("// hi\n{not json}\n")
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "{not json}" not in msg  # raw source bytes must not appear


@pytest.mark.parametrize("payload", ["[1, 2, 3]", "42", '"a string"', "null"])
def test_top_level_non_object_is_malformed(tmp_path: Path, payload: str) -> None:
    # AC-18 — non-object roots raise.
    p = tmp_path / "x.json"
    p.write_text(payload)
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=5_000)
    assert "expected JSON object" in exc_info.value.args[0]


def test_empty_file_is_malformed(tmp_path: Path) -> None:
    # AC-19 — never silently return {}.
    p = tmp_path / "empty.json"
    p.write_text("")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


def test_only_comments_is_malformed(tmp_path: Path) -> None:
    # AC-19 follow-on — file that strips to b'' is empty JSON; must raise.
    p = tmp_path / "only_comments.json"
    p.write_text("// only a comment\n/* and a block */\n")
    with pytest.raises(e.MalformedJSONError):
        load(p, max_bytes=5_000)


# --- Depth walker — boundary + mixed shapes --------------------------------


def _nested_dicts(depth: int) -> dict[str, Any]:
    out: dict[str, Any] = {"leaf": True} if depth == 0 else {}
    cur = out
    for _ in range(depth):
        cur["x"] = {}
        cur = cur["x"]
    cur["leaf"] = True
    return out


def _mixed_nesting(depth: int) -> dict[str, Any]:
    leaf: object = "leaf"
    for i in range(depth):
        leaf = [leaf] if i % 2 == 0 else {"k": leaf}
    return {"root": leaf}


@pytest.mark.parametrize("inner_depth", [0, 1, 63, 64])
def test_depth_at_or_below_cap_passes(tmp_path: Path, inner_depth: int) -> None:
    # AC-21.
    p = tmp_path / "ok.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    out = load(p, max_bytes=10_000_000, max_depth=64)
    assert isinstance(out, dict)


@pytest.mark.parametrize("inner_depth", [65, 70, 200])
def test_depth_above_cap_raises(tmp_path: Path, inner_depth: int) -> None:
    # AC-20 + AC-21.
    p = tmp_path / "deep.json"
    p.write_text(json.dumps(_nested_dicts(inner_depth)))
    with pytest.raises(e.DepthCapExceeded) as exc_info:
        load(p, max_bytes=10_000_000, max_depth=64)
    msg = exc_info.value.args[0]
    assert str(p) in msg
    assert "depth>64" in msg


def test_depth_walker_descends_into_lists(tmp_path: Path) -> None:
    # AC-20 — a dict-only walker would miss this.
    p = tmp_path / "list_bomb.json"
    p.write_text(json.dumps(_mixed_nesting(100)))
    with pytest.raises(e.DepthCapExceeded):
        load(p, max_bytes=10_000_000, max_depth=64)


# --- FD lifecycle ----------------------------------------------------------


def test_fd_closed_on_every_exit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-8 — every load that opened an fd must close it exactly once.
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
        return real_close(fd)

    monkeypatch.setattr(os, "open", _open)
    monkeypatch.setattr(os, "close", _close)

    # happy
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"a": 1}))
    load(ok, max_bytes=5_000)
    # size cap
    big = tmp_path / "big.json"
    big.write_text("0" * 1024)
    with pytest.raises(e.SizeCapExceeded):
        load(big, max_bytes=100)
    # malformed JSON (after strip)
    bad = tmp_path / "bad.json"
    bad.write_text("// hi\n{not json}")
    with pytest.raises(e.MalformedJSONError):
        load(bad, max_bytes=5_000)
    # malformed from strip stage (unterminated block)
    unterm = tmp_path / "unterm.json"
    unterm.write_text("/* never closes")
    with pytest.raises(e.MalformedJSONError):
        load(unterm, max_bytes=5_000)
    # depth cap
    deep = tmp_path / "deep.json"
    deep.write_text(json.dumps(_nested_dicts(70)))
    with pytest.raises(e.DepthCapExceeded):
        load(deep, max_bytes=10_000_000, max_depth=64)

    assert opened == closed, f"fd leak: opened={opened} closed={closed}"


def test_symlink_path_opens_no_fd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AC-8 — the symlink-refusal path never opens an fd (open raises before
    # returning a descriptor; the finally block must not run on a non-fd).
    real_open = os.open
    opened: list[int] = []

    def _trapped_open(*args: Any, **kwargs: Any) -> int:
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(os, "open", _trapped_open)
    target = tmp_path / "t.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError):
        load(link, max_bytes=5_000)
    assert opened == [], f"symlink-refusal path should not open any fd; got {opened}"


# --- Cap event emission ----------------------------------------------------


def test_size_cap_emits_event_with_jsonc_parser_kind(tmp_path: Path) -> None:
    # AC-22.
    p = tmp_path / "big.json"
    p.write_text("0" * 1024)
    with capture_logs() as logs:
        with pytest.raises(e.SizeCapExceeded):
            load(p, max_bytes=100)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["cap_kind"] == "size"
    assert ev["path"] == str(p)
    assert ev["parser"] == "jsonc"
    assert ev["parser_kind"] == "jsonc"


def test_depth_cap_emits_event_with_jsonc_parser_kind(tmp_path: Path) -> None:
    # AC-23.
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
    assert ev["parser"] == "jsonc"
    assert ev["parser_kind"] == "jsonc"


def test_no_cap_event_on_happy_or_malformed_or_symlink(tmp_path: Path) -> None:
    # AC-24.
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"a": 1}))
    with capture_logs() as logs:
        load(ok, max_bytes=5_000)
    assert not [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]

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


# --- Markers-only contract preserved (Phase-0 invariant) -------------------


def test_markers_only_positional_args0(tmp_path: Path) -> None:
    # AC-25, AC-26 — every typed exception this module raises is a marker;
    # path/cap/detail are recoverable from args[0] only.
    fixtures: list[tuple[Path, int, int, type[BaseException], str]] = []
    big = tmp_path / "big.json"
    big.write_text("0" * 1024)
    fixtures.append((big, 100, 64, e.SizeCapExceeded, "cap=100"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json}")
    fixtures.append((bad, 5_000, 64, e.MalformedJSONError, ""))
    deep = tmp_path / "deep.json"
    deep.write_text(json.dumps(_nested_dicts(70)))
    fixtures.append((deep, 10_000_000, 64, e.DepthCapExceeded, "depth>64"))
    unterm = tmp_path / "unterm.json"
    unterm.write_text('{"k": "never closed')
    fixtures.append((unterm, 5_000, 64, e.MalformedJSONError, "unterminated string"))
    for path, cap, depth, exc_type, substr in fixtures:
        with pytest.raises(exc_type) as exc_info:
            load(path, max_bytes=cap, max_depth=depth)
        assert isinstance(exc_info.value.args, tuple)
        assert len(exc_info.value.args) == 1
        assert isinstance(exc_info.value.args[0], str)
        assert str(path) in exc_info.value.args[0]
        if substr:
            assert substr in exc_info.value.args[0]
        for forbidden in ("path", "cap", "detail", "warning_id"):
            assert not hasattr(exc_info.value, forbidden), (
                f"{exc_type.__name__} must remain a marker; instance must not carry {forbidden!r}"
            )


# --- Pathological inputs — wall-clock --------------------------------------


def test_well_balanced_5000_nested_block_comments_parses_under_1s(tmp_path: Path) -> None:
    # AC-28 — 5,000-deep well-balanced nested block comments parse in < 1 s.
    # Implementer note: the story-prescribed payload "{ " + "/* " * 5000 +
    # '"k": 1 ' + " */" * 5000 + " }" places "k": 1 *inside* 5000 levels of
    # nested block comments, which (per AC-13's nested-comment semantics)
    # strips the payload to {}. No correct implementation can satisfy
    # `out["k"] == 1` from that shape. We preserve AC-28's intent ("5,000
    # well-balanced nested block comments parse in < 1 s") by moving the
    # payload outside the comment block so the assertion is reachable.
    payload = "{ " + "/* " * 5000 + " */" * 5000 + ' "k": 1 }'
    p = tmp_path / "evil_balanced.json"
    p.write_text(payload)
    t0 = time.monotonic()
    out = load(p, max_bytes=1_000_000)
    elapsed = time.monotonic() - t0
    assert out["k"] == 1
    assert elapsed < 1.0, f"balanced pathological took {elapsed:.3f}s; expected < 1s"


def test_unbalanced_1mb_unterminated_block_comment_raises_under_1s(tmp_path: Path) -> None:
    # AC-29.
    payload = "/* " + ("x" * 1_000_000)
    p = tmp_path / "evil_unbalanced.json"
    p.write_text(payload)
    t0 = time.monotonic()
    with pytest.raises(e.MalformedJSONError) as exc_info:
        load(p, max_bytes=2_000_000)
    elapsed = time.monotonic() - t0
    assert "unterminated block comment" in exc_info.value.args[0]
    assert elapsed < 1.0, f"unbalanced pathological took {elapsed:.3f}s; expected < 1s"


# --- S1-01 / S1-02 / S1-03 follow-up — SymlinkRefusedError docstring -------


def test_symlink_refused_error_doc_names_jsonc() -> None:
    # AC-27.
    doc = (e.SymlinkRefusedError.__doc__ or "").lower()
    assert "jsonc" in doc or "parsers/jsonc" in doc
    # Pre-existing callers remain named so the slug test continues to pass.
    assert "writer" in doc or "sanitizer" in doc
    assert "safe_json" in doc  # S1-02 already added this; do not regress.
