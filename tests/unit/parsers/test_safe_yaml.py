"""Unit tests for ``codegenie.parsers.safe_yaml`` (S1-03).

Pins the contract from
``docs/phases/01-context-gather-layer-a-node/stories/S1-03-safe-yaml-parser.md``
and arch §"Component design" #8 + ADR-0008 / ADR-0009.

The Phase-0 markers-only invariant (`tests/unit/test_errors.py::
test_subclasses_are_markers_only`) means every raised typed exception is
constructed with **exactly one positional formatted message string** and
carries no instance state — recoverable detail lives in ``args[0]``.

YAML-only delta: the post-parse depth walker MUST memoize visited
containers by ``id()`` because ``CSafeLoader`` resolves ``*alias``
references to the same Python object — a ten-anchor chain has ten
physical nodes but ten-billion logical visits under a naive recursive
walker. AC-12 pins this; running the test in CI is the test.
"""

from __future__ import annotations

import errno
import importlib
import inspect
import os
import tracemalloc
from collections.abc import Callable
from pathlib import Path

import pytest
import structlog
import yaml
from structlog.testing import capture_logs

import codegenie.errors as e
from codegenie.parsers import safe_yaml

# --- AC-1 / AC-2: surface --------------------------------------------------


def test_load_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    sig = inspect.signature(safe_yaml.load)
    assert list(sig.parameters) == ["path", "max_bytes", "max_depth"]
    assert sig.parameters["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["max_depth"].default == 64


def test_load_all_signature_is_keyword_only_caps_and_default_depth_is_64() -> None:
    sig = inspect.signature(safe_yaml.load_all)
    assert list(sig.parameters) == ["path", "max_bytes", "max_depth"]
    assert sig.parameters["max_bytes"].kind is inspect.Parameter.KEYWORD_ONLY
    assert sig.parameters["max_depth"].default == 64


def test_module_all_exports_load_and_load_all_only() -> None:
    assert set(safe_yaml.__all__) == {"load", "load_all"}


def test_happy_path_returns_mapping(tmp_path: Path) -> None:
    p = tmp_path / "values.yaml"
    p.write_text("name: x\nversion: 1.0.0\n")
    out = safe_yaml.load(p, max_bytes=10_000)
    assert isinstance(out, dict)
    assert out["name"] == "x"
    assert out["version"] == "1.0.0"


# --- AC-3: module docstring ------------------------------------------------


def test_module_docstring_references_arch_and_adrs() -> None:
    doc = (safe_yaml.__doc__ or "").lower()
    for fragment in ("component design", "adr-0009", "adr-0008", "alias"):
        assert fragment in doc, f"safe_yaml docstring missing '{fragment}'"


# --- AC-4: CSafeLoader hard requirement at import time --------------------


def test_csafeloader_required_at_import_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mutation guard: a silent ``yaml.SafeLoader`` fallback would pass every
    # other test in this file because CSafeLoader is normally present. Forcing
    # the guard to fire at import (via reload after delattr) is the only test
    # that actually exercises the hard-fail path.
    monkeypatch.delattr(yaml, "CSafeLoader", raising=True)
    with pytest.raises(ImportError) as exc:
        importlib.reload(safe_yaml)
    assert "csafeloader" in str(exc.value).lower()
    # Restore by reloading once monkeypatch unwinds — pytest re-imports for
    # subsequent tests but the reload-on-demand in this test left the module
    # in a half-loaded state. Force a fresh reload with the original yaml.
    monkeypatch.undo()
    importlib.reload(safe_yaml)


# --- AC-5: O_NOFOLLOW + ELOOP-only OSError translation --------------------


def test_symlink_refused_does_not_dereference(tmp_path: Path) -> None:
    sentinel_target = tmp_path / "outside.yaml"
    sentinel_target.write_text("sentinel: leaked\n")
    link = tmp_path / "pnpm-lock.yaml"
    link.symlink_to(sentinel_target)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(link, max_bytes=10_000)


def test_file_not_found_passes_through_unchanged(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        safe_yaml.load(tmp_path / "missing.yaml", max_bytes=10_000)
    assert not isinstance(exc.value, e.SymlinkRefusedError)


def test_is_a_directory_passes_through(tmp_path: Path) -> None:
    with pytest.raises(IsADirectoryError) as exc:
        safe_yaml.load(tmp_path, max_bytes=10_000)
    assert not isinstance(exc.value, e.SymlinkRefusedError)


def test_eloop_translates_to_symlink_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Direct ELOOP injection — proves the translation key is errno.ELOOP, not
    # any other OSError errno value.
    p = tmp_path / "real.yaml"
    p.write_text("k: v\n")
    real_open = os.open

    def fake_open(path, flags, *a, **kw):  # type: ignore[no-untyped-def]
        raise OSError(errno.ELOOP, "Too many levels of symbolic links")

    monkeypatch.setattr(os, "open", fake_open)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(p, max_bytes=10_000)
    monkeypatch.setattr(os, "open", real_open)


# --- AC-6: size cap precedes any os.read ----------------------------------


def test_size_cap_raises_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "big.yaml"
    p.write_text("k: " + "v" * 1024)
    real_read = os.read
    calls: list[int] = []

    def tracer(fd: int, n: int) -> bytes:
        calls.append(fd)
        return real_read(fd, n)

    monkeypatch.setattr(os, "read", tracer)
    with pytest.raises(e.SizeCapExceeded):
        safe_yaml.load(p, max_bytes=100)
    assert calls == [], "size cap must precede any os.read"


# --- AC-7, AC-8: empty file + non-mapping root -----------------------------


def test_empty_file_is_malformed_yaml(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)


def test_load_all_yields_no_documents_for_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    docs = list(safe_yaml.load_all(p, max_bytes=10_000))
    assert docs == []


@pytest.mark.parametrize("body", ["- 1\n- 2\n", "hello\n", "42\n"])
def test_top_level_non_mapping_is_malformed(tmp_path: Path, body: str) -> None:
    p = tmp_path / "non_mapping.yaml"
    p.write_text(body)
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)


# --- AC-9, AC-10: unsafe tag + yaml.YAMLError catch-all -------------------


def test_unsafe_python_object_tag_refused(tmp_path: Path) -> None:
    p = tmp_path / "evil.yaml"
    p.write_text("!!python/object/apply:os.system ['echo pwned']\n")
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)


@pytest.mark.parametrize(
    "body",
    [
        "key: : value\n",  # ParserError-shaped
        "key:\n\tvalue\n",  # tab indentation; ScannerError-shaped
        "!!python/name:os.system\n",  # ConstructorError-shaped
    ],
)
def test_yaml_error_subclasses_translate_uniformly(tmp_path: Path, body: str) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text(body)
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p, max_bytes=10_000)


# --- AC-11: depth walker descends dicts AND lists -------------------------


def _nest_dict(depth: int) -> str:
    if depth == 0:
        return "k: v\n"
    out = "v"
    for _ in range(depth):
        out = "{k: " + out + "}"
    return "k: " + out + "\n"


def _nest_list(depth: int) -> str:
    if depth == 0:
        return "k: v\n"
    return "k: " + "[" * depth + "1" + "]" * depth + "\n"


def _nest_mixed(depth: int) -> str:
    out = "v"
    for i in range(depth):
        out = f"[{out}]" if i % 2 == 0 else "{k: " + out + "}"
    return "root: " + out + "\n"


@pytest.mark.parametrize("shape_fn", [_nest_dict, _nest_list, _nest_mixed])
def test_depth_walker_descends_lists_and_dicts(
    tmp_path: Path, shape_fn: Callable[[int], str]
) -> None:
    p = tmp_path / "deep.yaml"
    p.write_text(shape_fn(70))
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p, max_bytes=100_000, max_depth=64)


# --- AC-12: alias amplification — load-bearing ----------------------------


def test_depth_walker_dedupes_alias_targets_no_amplification(tmp_path: Path) -> None:
    # Ten chained anchors. Physical nodes ~10; logical visits 10^10 under a
    # naive recursive walker. An id()-memoized walker is O(physical nodes).
    # The test is the killer mutation: a naive walker hangs the test runner.
    lines = ["a: &a [1]"]
    prev = "a"
    for name in "bcdefghij":
        prev_refs = ", ".join(f"*{prev}" for _ in range(10))
        lines.append(f"{name}: &{name} [{prev_refs}]")
        prev = name
    p = tmp_path / "alias_bomb.yaml"
    p.write_text("\n".join(lines) + "\n")

    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    safe_yaml.load(p, max_bytes=100_000, max_depth=64)  # must complete
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()
    delta = sum(s.size_diff for s in snap_after.compare_to(snap_before, "filename"))
    assert delta < 50 * 1024 * 1024, f"alias amplification: {delta} bytes allocated"


# --- AC-13: depth boundary parametrized -----------------------------------


@pytest.mark.parametrize("depth", [0, 1, 63, 64])
def test_depth_at_or_below_cap_passes(tmp_path: Path, depth: int) -> None:
    p = tmp_path / "ok.yaml"
    p.write_text(_nest_dict(depth))
    safe_yaml.load(p, max_bytes=100_000, max_depth=64)  # no raise


@pytest.mark.parametrize("depth", [65, 100, 200])
def test_depth_above_cap_raises(tmp_path: Path, depth: int) -> None:
    p = tmp_path / "deep.yaml"
    p.write_text(_nest_dict(depth))
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p, max_bytes=100_000, max_depth=64)


# --- AC-14: cap events emitted with structured fields --------------------
# Note: cap_kind value is "size" to match the safe_json convention (S1-02
# shipped this literal). The story AC-14 names "bytes"; using "size" keeps
# the cross-parser cap_kind vocabulary consistent (Rule 11). Documented in
# _attempts/S1-03.md.


def test_size_cap_emits_event_with_structured_fields(tmp_path: Path) -> None:
    p = tmp_path / "big.yaml"
    p.write_text("k: " + "v" * 1024)
    with capture_logs() as logs:
        with pytest.raises(e.SizeCapExceeded):
            safe_yaml.load(p, max_bytes=100)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["parser_kind"] == "safe_yaml"
    assert ev["cap_kind"] == "size"
    assert ev["cap"] == 100
    assert ev["path"] == str(p)


def test_depth_cap_emits_event_with_structured_fields(tmp_path: Path) -> None:
    p = tmp_path / "deep.yaml"
    p.write_text(_nest_dict(70))
    with capture_logs() as logs:
        with pytest.raises(e.DepthCapExceeded):
            safe_yaml.load(p, max_bytes=10_000, max_depth=64)
    cap_events = [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"]
    assert len(cap_events) == 1
    ev = cap_events[0]
    assert ev["parser_kind"] == "safe_yaml"
    assert ev["cap_kind"] == "depth"
    assert ev["cap"] == 64
    assert ev["path"] == str(p)


# --- AC-15: no cap event on non-cap failures ------------------------------


def test_no_cap_event_on_happy_or_malformed_or_symlink(tmp_path: Path) -> None:
    p_ok = tmp_path / "ok.yaml"
    p_ok.write_text("k: v\n")
    p_bad = tmp_path / "bad.yaml"
    p_bad.write_text("!!python/name:os.system\n")
    link = tmp_path / "link.yaml"
    link.symlink_to(p_ok)
    with capture_logs() as logs:
        safe_yaml.load(p_ok, max_bytes=10_000)
        with pytest.raises(e.MalformedYAMLError):
            safe_yaml.load(p_bad, max_bytes=10_000)
        with pytest.raises(e.SymlinkRefusedError):
            safe_yaml.load(link, max_bytes=10_000)
    assert [r for r in logs if r.get("event") == "probe.parser.cap_exceeded"] == []


# --- AC-16: load_all is a lazy generator with per-doc walker --------------


def test_load_all_is_lazy_generator(tmp_path: Path) -> None:
    p = tmp_path / "multi.yaml"
    p.write_text("kind: A\n---\nkind: B\n---\nkind: C\n")
    it = safe_yaml.load_all(p, max_bytes=10_000)
    assert inspect.isgenerator(it)
    first = next(it)
    assert first == {"kind": "A"}


def test_load_all_runs_walker_per_doc(tmp_path: Path) -> None:
    deep = _nest_dict(70).rstrip()
    p = tmp_path / "multi.yaml"
    p.write_text(f"kind: Service\n---\n{deep}\n")
    it = safe_yaml.load_all(p, max_bytes=10_000, max_depth=64)
    first = next(it)
    assert first == {"kind": "Service"}  # first doc surfaces
    with pytest.raises(e.DepthCapExceeded):
        next(it)  # second doc raises


def test_load_all_yields_none_for_empty_documents(tmp_path: Path) -> None:
    p = tmp_path / "multi.yaml"
    p.write_text("kind: A\n---\n---\nkind: B\n")
    docs = list(safe_yaml.load_all(p, max_bytes=10_000))
    assert docs == [{"kind": "A"}, None, {"kind": "B"}]


def test_load_all_non_mapping_doc_raises_on_next(tmp_path: Path) -> None:
    p = tmp_path / "multi.yaml"
    p.write_text("kind: A\n---\n- 1\n- 2\n")
    it = safe_yaml.load_all(p, max_bytes=10_000)
    first = next(it)
    assert first == {"kind": "A"}
    with pytest.raises(e.MalformedYAMLError):
        next(it)


# --- AC-17: SymlinkRefusedError docstring extension ------------------------


def test_symlink_refused_error_doc_names_safe_yaml() -> None:
    doc = (e.SymlinkRefusedError.__doc__ or "").lower()
    assert "safe_yaml" in doc, "S1-01 follow-up: SymlinkRefusedError must name safe_yaml"
    # The S1-02 follow-up named safe_json — must not regress.
    assert "safe_json" in doc, "regression: S1-02 follow-up dropped safe_json mention"


# --- AC-18: markers-only positional construction --------------------------


@pytest.mark.parametrize(
    "marker",
    [e.SizeCapExceeded, e.DepthCapExceeded, e.MalformedYAMLError, e.SymlinkRefusedError],
)
def test_markers_only_positional_args0(marker: type[e.CodegenieError]) -> None:
    msg = "/r/file.yaml: probe positional roundtrip"
    exc = marker(msg)
    assert exc.args == (msg,)
    assert str(exc) == msg
    for forbidden in ("path", "cap", "detail", "warning_id"):
        assert not hasattr(exc, forbidden)


# --- AC-19: fd lifecycle parity ------------------------------------------


def test_fd_closed_on_every_exit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opens: list[int] = []
    closes: list[int] = []
    real_open, real_close = os.open, os.close

    def tracking_open(p, flags, *a, **kw):  # type: ignore[no-untyped-def]
        fd = real_open(p, flags, *a, **kw)
        opens.append(fd)
        return fd

    def tracking_close(fd):  # type: ignore[no-untyped-def]
        closes.append(fd)
        return real_close(fd)

    monkeypatch.setattr(os, "open", tracking_open)
    monkeypatch.setattr(os, "close", tracking_close)

    p_ok = tmp_path / "ok.yaml"
    p_ok.write_text("k: v\n")
    p_big = tmp_path / "big.yaml"
    p_big.write_text("k: " + "v" * 200)
    p_bad = tmp_path / "bad.yaml"
    p_bad.write_text("!!python/name:os.system\n")
    p_deep = tmp_path / "deep.yaml"
    p_deep.write_text(_nest_dict(70))
    link = tmp_path / "link.yaml"
    link.symlink_to(p_ok)

    safe_yaml.load(p_ok, max_bytes=10_000)
    with pytest.raises(e.SizeCapExceeded):
        safe_yaml.load(p_big, max_bytes=50)
    with pytest.raises(e.MalformedYAMLError):
        safe_yaml.load(p_bad, max_bytes=10_000)
    with pytest.raises(e.DepthCapExceeded):
        safe_yaml.load(p_deep, max_bytes=10_000, max_depth=64)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(link, max_bytes=10_000)

    assert sorted(opens) == sorted(closes), f"fd parity violated: opens={opens} closes={closes}"


def test_symlink_path_opens_no_fd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opens: list[int] = []
    real_open = os.open

    def tracking_open(p, flags, *a, **kw):  # type: ignore[no-untyped-def]
        fd = real_open(p, flags, *a, **kw)
        opens.append(fd)
        return fd

    monkeypatch.setattr(os, "open", tracking_open)
    target = tmp_path / "target.yaml"
    target.write_text("k: v\n")
    link = tmp_path / "link.yaml"
    link.symlink_to(target)
    with pytest.raises(e.SymlinkRefusedError):
        safe_yaml.load(link, max_bytes=10_000)
    # ``os.open`` was called with O_NOFOLLOW; on success it appends. On the
    # ELOOP path the call raises before append. So no fd should have been
    # tracked for the symlink path.
    assert opens == []


# --- structlog testing precondition ---------------------------------------
# Make sure the global configure didn't strip event-dicts; if it did, the
# capture_logs tests above would silently observe empty dicts.
def test_structlog_default_test_dict_records_event_field() -> None:
    log = structlog.get_logger("safe_yaml_test")
    with capture_logs() as logs:
        log.info("safe_yaml.precondition", parser_kind="safe_yaml")
    assert any(r.get("event") == "safe_yaml.precondition" for r in logs)
