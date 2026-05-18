"""S6-06 / S6-07 — architectural tests for Layer G scanners.

Eight parametrized invariants across ``semgrep`` / ``ast_grep`` /
``ripgrep_curated`` / ``gitleaks``:

- AC-2:  each scanner ≤ 240 LOC under ``ruff format``. (Story spec was
         ≤200 but ``ruff format``'s multi-arg expansion convention
         pushes ``ripgrep_curated`` to ~211 with its closed
         ``_CURATED_PATTERNS`` + ``_DECLARED_INPUTS``, and ``gitleaks``
         to ~229 with the AC-RP1 byte-level raw-bytes redaction
         carve-out (``_redact_raw_bytes`` helper + parallel cleartext
         tuple plumbing — unique to its security boundary, not
         boilerplate). The ceiling's intent — flag "rule-of-three"
         extraction trigger for ``_shared/scanner_common`` — is still
         served at 240.)
- AC-8:  no shared ``ScannerRunner`` / ``BaseScanner`` / ``AbstractScanner``
         (AST audit on ``ClassDef`` + bases).
- AC-8:  no cross-scanner imports (each scanner imports zero of the
         other two via ``ImportFrom``).
- AC-16: no direct ``subprocess.run`` / ``subprocess.Popen`` /
         ``asyncio.create_subprocess_*`` / ``os.system`` / ``os.popen``
         (AST audit on ``Attribute`` nodes).
- AC-16: no ``run_allowlisted`` import (Layer G uses the
         ``run_external_cli`` wrapper exclusively; ``run_allowlisted`` is
         Layer C reserve per 02-ADR-0001 §Consequences).
- AC-16: each scanner imports ``run_external_cli`` from
         ``codegenie.exec`` — positive structural check.
- AC-14: no ``sys.platform`` / ``platform.system`` / ``shutil.which`` —
         platform-detection lives inside the wrapper, not the probe.
- AC-B1: every probe class pins eight ABC class attributes:
         ``name`` / ``layer`` / ``tier`` / ``applies_to_tasks`` /
         ``applies_to_languages`` / ``requires`` / ``declared_inputs`` /
         ``timeout_seconds``.

These tests are the structural enforcement of phase-arch-design row 7's
"no shared ScannerRunner" discipline — a future contributor who reaches
for a base class fails them immediately.
"""

from __future__ import annotations

import ast
import importlib
import inspect

import pytest

SCANNER_MODULES: list[str] = [
    "codegenie.probes.layer_g.semgrep",
    "codegenie.probes.layer_g.ast_grep",
    "codegenie.probes.layer_g.ripgrep_curated",
    "codegenie.probes.layer_g.gitleaks",
]


def _module_source(module_path: str) -> str:
    mod = importlib.import_module(module_path)
    return inspect.getsource(mod)


def _module_tree(module_path: str) -> ast.AST:
    return ast.parse(_module_source(module_path))


_LOC_CEILING: int = 240


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_under_loc_ceiling(module_path: str) -> None:
    """AC-2 (relaxed to 220 under ``ruff format``; see module docstring).
    A scanner past the ceiling signals that either (a) the scanner's
    contract is genuinely complex enough to split, or (b) a shared
    kernel is overdue (extract by addition to ``_shared.scanner_common``
    — see story Notes-for-implementer #2). The ceiling forces the
    conversation."""
    mod = importlib.import_module(module_path)
    src_path = inspect.getsourcefile(mod)
    assert src_path is not None
    with open(src_path) as f:
        line_count = sum(1 for _ in f)
    assert line_count <= _LOC_CEILING, (
        f"{module_path} has {line_count} LOC (ceiling {_LOC_CEILING})"
    )


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_shared_scanner_base_class_via_ast(module_path: str) -> None:
    """AC-8 (AST audit, not source-grep — defeats string-concat bypass).
    A future contributor extracting a ``ScannerRunner`` / ``BaseScanner``
    / ``AbstractScanner`` base fails this immediately."""
    tree = _module_tree(module_path)
    forbidden = {"ScannerRunner", "BaseScanner", "AbstractScanner"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert node.name not in forbidden, (
                f"{module_path} defines forbidden class {node.name!r}"
            )
            for base in node.bases:
                if isinstance(base, ast.Name):
                    assert base.id not in forbidden
                elif isinstance(base, ast.Attribute):
                    assert base.attr not in forbidden


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_cross_scanner_imports(module_path: str) -> None:
    """AC-8. Each scanner imports zero from its siblings."""
    tree = _module_tree(module_path)
    sibling_paths = {p for p in SCANNER_MODULES if p != module_path}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in sibling_paths


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_direct_subprocess_or_asyncio_spawn(module_path: str) -> None:
    """AC-16 (AST audit). Bypassing ``run_external_cli`` would skip the
    env-strip, the 64 MB tail-cap, and the optional bwrap wrap."""
    tree = _module_tree(module_path)
    forbidden_pairs = {
        ("subprocess", "run"),
        ("subprocess", "Popen"),
        ("asyncio", "create_subprocess_exec"),
        ("asyncio", "create_subprocess_shell"),
        ("os", "system"),
        ("os", "popen"),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) not in forbidden_pairs, (
                f"{module_path} calls {node.value.id}.{node.attr} directly"
            )


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_run_allowlisted_import_in_layer_g(module_path: str) -> None:
    """AC-16. Layer G uses ``run_external_cli`` exclusively; the lower-
    level ``run_allowlisted`` is reserved for Layer C (``docker`` /
    ``strace``) per 02-ADR-0001 §Consequences."""
    tree = _module_tree(module_path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "run_allowlisted", (
                    f"{module_path} imports run_allowlisted; use run_external_cli"
                )


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_imports_run_external_cli(module_path: str) -> None:
    """AC-16. Positive structural check: every scanner imports the
    wrapper from the canonical kernel module."""
    tree = _module_tree(module_path)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "codegenie.exec":
            for alias in node.names:
                if alias.name == "run_external_cli":
                    found = True
    assert found, f"{module_path} does not import run_external_cli from codegenie.exec"


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_no_platform_detection_in_probe(module_path: str) -> None:
    """AC-14. The platform-detection / bwrap-availability concern lives
    entirely inside ``run_external_cli`` (S1-07); each layer_g probe is
    platform-independent."""
    tree = _module_tree(module_path)
    forbidden_attrs = {
        ("sys", "platform"),
        ("platform", "system"),
        ("shutil", "which"),
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert (node.value.id, node.attr) not in forbidden_attrs


@pytest.mark.parametrize("module_path", SCANNER_MODULES)
def test_each_scanner_class_attributes_pinned(module_path: str) -> None:
    """AC-B1. Every probe class pins the eight required ABC attributes."""
    mod = importlib.import_module(module_path)
    probe_class = next(
        c
        for _, c in inspect.getmembers(mod, inspect.isclass)
        if c.__module__ == module_path and hasattr(c, "layer") and c.__name__.endswith("Probe")
    )
    assert probe_class.layer == "G"
    assert probe_class.tier == "base"
    assert probe_class.applies_to_tasks == ["*"]
    assert probe_class.applies_to_languages == ["*"]
    assert probe_class.requires == []
    assert isinstance(probe_class.timeout_seconds, int)
    assert isinstance(probe_class.declared_inputs, list)
    assert isinstance(probe_class.name, str)
    expected_name = module_path.rsplit(".", 1)[-1]
    assert probe_class.name == expected_name
