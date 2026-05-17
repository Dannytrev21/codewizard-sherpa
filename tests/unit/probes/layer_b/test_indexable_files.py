"""Regression guard for the S4-06 ``_indexable_files`` extraction (AC-M4).

Confirms the walker / counter / Merkle helpers extracted out of
``scip_index.py`` retain their original semantics: same suffix set,
same exclude set, same deterministic ordering. A copy-paste divergence
between this module and ``scip_index.py`` would cause B2 / SCIP /
SemanticIndexMeta to disagree on file counts — silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes.layer_b._indexable_files import (
    _EXCLUDE_DIRS,
    _INDEXABLE_SUFFIXES,
    _count_indexable_files,
    _read_exclude_file,
    _walk_indexable_files,
)


def test_indexable_suffix_set_is_typescript_only() -> None:
    """SCIP's program scope is .ts/.tsx only (localv2 §5.2 B1). Adding
    .js/.jsx here would make B2's Stale(CoverageGap) fire on every
    healthy mixed JS+TS repo."""
    assert _INDEXABLE_SUFFIXES == frozenset({".ts", ".tsx"})


def test_exclude_dirs_match_s4_03_canonical_set() -> None:
    """The canonical SCIP exclude set. ``out`` is NOT here — it lives
    in GeneratedCodeProbe's separate _BUILD_OUTPUT_DIRS constant
    (different concept, different consumer)."""
    assert _EXCLUDE_DIRS == frozenset({"node_modules", "dist", "build", ".git"})


def test_walker_yields_sorted_paths(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "z.ts").write_text("")
    (tmp_path / "src" / "a.ts").write_text("")
    (tmp_path / "src" / "m.tsx").write_text("")
    yielded = [p.relative_to(tmp_path).as_posix() for p in _walk_indexable_files(tmp_path)]
    assert yielded == sorted(yielded)
    assert yielded == ["src/a.ts", "src/m.tsx", "src/z.ts"]


def test_walker_skips_excluded_dirs(tmp_path: Path) -> None:
    (tmp_path / "src" / "ok.ts").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "ok.ts").write_text("")
    for excluded in _EXCLUDE_DIRS:
        d = tmp_path / excluded
        d.mkdir(exist_ok=True)
        (d / "skip.ts").write_text("")
    rels = [p.relative_to(tmp_path).as_posix() for p in _walk_indexable_files(tmp_path)]
    assert rels == ["src/ok.ts"]


def test_walker_skips_non_indexable_suffixes(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("")
    (tmp_path / "b.js").write_text("")
    (tmp_path / "c.jsx").write_text("")
    rels = [p.name for p in _walk_indexable_files(tmp_path)]
    assert rels == ["a.ts"]


def test_count_matches_walker_length(tmp_path: Path) -> None:
    for i in range(5):
        (tmp_path / f"f{i}.ts").write_text("")
    assert _count_indexable_files(tmp_path) == len(list(_walk_indexable_files(tmp_path)))


def test_read_exclude_file_missing_returns_empty(tmp_path: Path) -> None:
    assert _read_exclude_file(tmp_path) == frozenset()


def test_read_exclude_file_strips_comments_and_blanks(tmp_path: Path) -> None:
    cg = tmp_path / ".codegenie"
    cg.mkdir()
    (cg / "exclude.txt").write_text("# header\n\nfoo\n  bar  \n# trailing\n")
    assert _read_exclude_file(tmp_path) == frozenset({"foo", "bar"})


def test_user_exclude_applies(tmp_path: Path) -> None:
    cg = tmp_path / ".codegenie"
    cg.mkdir()
    (cg / "exclude.txt").write_text("vendor\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "v.ts").write_text("")
    (tmp_path / "src.ts").write_text("")
    rels = [p.relative_to(tmp_path).as_posix() for p in _walk_indexable_files(tmp_path)]
    assert rels == ["src.ts"]


def test_walker_is_deterministic_across_two_runs(tmp_path: Path) -> None:
    """Byte-identical determinism: the walker emits sorted paths so
    repeat invocations yield the exact same sequence (AC-X9 precedent)."""
    for name in ["z.ts", "a.ts", "m.tsx", "n.ts"]:
        (tmp_path / name).write_text("")
    first = [p.as_posix() for p in _walk_indexable_files(tmp_path)]
    second = [p.as_posix() for p in _walk_indexable_files(tmp_path)]
    assert first == second


def test_scip_index_re_exports_indexable_files_kernel() -> None:
    """T-M5 second leg: the scip_index module must import the shared
    helpers, not redefine them. Mechanically forbids copy-paste."""
    import ast

    src = Path("src/codegenie/probes/layer_b/scip_index.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == (
            "codegenie.probes.layer_b._indexable_files"
        ):
            names = {alias.name for alias in node.names}
            assert {"_count_indexable_files", "_walk_indexable_files"} <= names
            found = True
    assert found, "scip_index.py must import from codegenie.probes.layer_b._indexable_files"


@pytest.mark.parametrize("excluded", sorted(_EXCLUDE_DIRS))
def test_each_excluded_dir_skipped(tmp_path: Path, excluded: str) -> None:
    d = tmp_path / excluded / "nested"
    d.mkdir(parents=True)
    (d / "x.ts").write_text("")
    (tmp_path / "ok.ts").write_text("")
    rels = [p.relative_to(tmp_path).as_posix() for p in _walk_indexable_files(tmp_path)]
    assert rels == ["ok.ts"]
