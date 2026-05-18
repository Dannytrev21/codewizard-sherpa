"""Structural boundary test — Gap 5, Risk #6, 02-ADR-0010.

The smart-constructor invariant: :class:`RedactedSlice` may only be
constructed from the documented two-site closed set inside the
``codegenie.output`` redaction pipeline, plus the ``tests/unit/output/``
allowlist for the model's own anti-regression tests.

Adding a third production-code construction site silently breaks the
type-level "redactor was called" guarantee — this test fails loudly if
that happens.

The two documented production sites:

* ``codegenie.output.sanitizer.redact_secrets`` — per-probe-slice path.
* ``codegenie.output.envelope_redactor._build_redacted_slice_pass`` —
  envelope path the CLI uses via
  ``cli._seam_redact_envelope`` → ``envelope_redactor._redact_envelope``.

Adding a third site requires an explicit ADR amendment to 02-ADR-0010,
then editing ``ALLOWED_CONSTRUCTOR_SITES`` below.

This is a **structural** test, not a behavioral one — it reads source AST
+ signatures rather than executing the pipeline. The behavioural
counterpart for end-to-end secret-leak detection lives in
``tests/adv/phase02/test_secret_in_source.py`` (S6-07) and
``tests/golden/test_no_plaintext_in_goldens.py`` (S7-03).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final, NamedTuple

_HERE = Path(__file__).resolve()
# tests/adv/phase02/ → repo root is three .parent hops.
_REPO_ROOT: Final[Path] = _HERE.parents[3]
_SRC: Final[Path] = _REPO_ROOT / "src"
_TESTS: Final[Path] = _REPO_ROOT / "tests"

_REDACTED_SLICE_QUALNAME: Final[str] = "codegenie.output.redacted_slice.RedactedSlice"

# Closed two-site set. Adding a third entry = ADR amendment to 02-ADR-0010.
ALLOWED_CONSTRUCTOR_SITES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("src/codegenie/output/sanitizer.py", "redact_secrets"),
        ("src/codegenie/output/envelope_redactor.py", "_build_redacted_slice_pass"),
    }
)

# Test-only directories that may legitimately construct ``RedactedSlice``
# in fixtures (the model's own anti-regression tests live under
# ``tests/unit/output/`` and exercise the smart-constructor's invariants
# directly — they are the canonical anti-regression for ``RedactedSlice``).
ALLOWED_TEST_CONSTRUCTOR_DIRS: Final[frozenset[str]] = frozenset(
    {
        "tests/unit/output",
        # The audit suite reconstructs RedactedSlice values when verifying
        # already-written envelopes (verify path); not a redaction call site.
        "tests/unit/audit",
    }
)

# AC-17: closed set of Writer.write production call sites.
# Adding a third entry = explicit edit to this constant + ADR amendment.
ALLOWED_WRITER_CALL_SITES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("src/codegenie/cli.py", "_seam_write_envelope"),
    }
)


class _CallSite(NamedTuple):
    file: str  # POSIX-relative to repo root
    line: int
    enclosing_func: str  # nearest enclosing FunctionDef / AsyncFunctionDef
    call_text: str


def _build_alias_map(tree: ast.Module) -> dict[str, str]:
    """Return ``{local_name: real_qualified_name}`` for every import in ``tree``.

    Resolves ``from codegenie.output.redacted_slice import RedactedSlice as _RS``
    to ``{'_RS': 'codegenie.output.redacted_slice.RedactedSlice'}`` so the
    walker is not fooled by aliasing (AC-30).
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _resolves_to_redacted_slice(call: ast.Call, aliases: dict[str, str]) -> bool:
    """Return True iff ``call.func`` constructs ``RedactedSlice``.

    Covers bare-name construction (``RedactedSlice(...)``,
    ``_RS(...)`` where ``_RS`` aliases it) and ``model_validate`` /
    ``model_validate_json`` / ``model_construct`` factory calls on
    ``RedactedSlice``.
    """
    func = call.func
    if isinstance(func, ast.Name):
        return aliases.get(func.id, "") == _REDACTED_SLICE_QUALNAME
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        base_qual = aliases.get(func.value.id, "")
        return base_qual == _REDACTED_SLICE_QUALNAME and func.attr in {
            "model_validate",
            "model_validate_json",
            "model_construct",
        }
    return False


def _build_parent_map(tree: ast.Module) -> dict[int, ast.AST]:
    """Return ``{id(child_node): parent_node}`` for every node in ``tree``.

    Used to climb to the nearest enclosing FunctionDef. We key on ``id()``
    because :class:`ast.AST` is not hashable.
    """
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _enclosing_func_name(node: ast.AST, parents: dict[int, ast.AST]) -> str:
    cur: ast.AST | None = node
    while cur is not None:
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cur.name
        cur = parents.get(id(cur))
    return "<module>"


def _iter_python_sources(root: Path) -> list[Path]:
    skip = {"_validation", "_attempts", "__pycache__", ".venv", "node_modules"}
    out: list[Path] = []
    for py in root.rglob("*.py"):
        if any(part in skip for part in py.parts):
            continue
        if py == _HERE:
            continue
        out.append(py)
    return out


def _find_construction_sites(root: Path) -> list[_CallSite]:
    sites: list[_CallSite] = []
    for py in _iter_python_sources(root):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (SyntaxError, UnicodeDecodeError):
            continue
        aliases = _build_alias_map(tree)
        parents = _build_parent_map(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _resolves_to_redacted_slice(node, aliases):
                rel = py.relative_to(_REPO_ROOT).as_posix()
                sites.append(
                    _CallSite(
                        file=rel,
                        line=node.lineno,
                        enclosing_func=_enclosing_func_name(node, parents),
                        call_text=ast.unparse(node),
                    )
                )
    return sites


def _is_allowed_construction(site: _CallSite) -> bool:
    if (site.file, site.enclosing_func) in ALLOWED_CONSTRUCTOR_SITES:
        return True
    return any(site.file.startswith(d + "/") for d in ALLOWED_TEST_CONSTRUCTOR_DIRS)


def test_redacted_slice_construction_is_restricted_to_documented_sites() -> None:
    """AC-15 + AC-19 + AC-30 — closed two-site set, with aliased-import resilience."""
    sites = _find_construction_sites(_SRC) + _find_construction_sites(_TESTS)
    offending = [s for s in sites if not _is_allowed_construction(s)]
    if offending:
        lines = [
            (
                f"RedactedSlice constructed at {s.file}:{s.line} (call to "
                f"{s.call_text!r}) is outside the documented two-site closed "
                f"set (sanitizer.redact_secrets + "
                f"envelope_redactor._build_redacted_slice_pass) and the "
                f"tests/unit/output/ allowlist. The smart-constructor "
                f"invariant (02-ADR-0010, S3-02, Gap 4) requires construction "
                f"to be restricted to the redaction pipeline. To add a third "
                f"construction site, amend 02-ADR-0010 and update "
                f"ALLOWED_CONSTRUCTOR_SITES in this test file. See "
                f"docs/phases/02-context-gather-layers-b-g/ADRs/"
                f"0010-redacted-slice-smart-constructor-at-writer-boundary.md."
            )
            for s in offending
        ]
        raise AssertionError("\n".join(lines))

    # Defense-in-depth: each documented production site must contain at
    # least one construction (regression guard against silent removal of
    # either redaction path — silent removal would defeat 02-ADR-0005).
    for file, func in ALLOWED_CONSTRUCTOR_SITES:
        present = [s for s in sites if s.file == file and s.enclosing_func == func]
        assert present, (
            f"Expected at least one RedactedSlice construction inside "
            f"{file}::{func}; the redactor at this site appears to have "
            f"been removed. Either redaction path silently disappearing "
            f"breaks 02-ADR-0005 + 02-ADR-0010."
        )


def test_writer_signature_pins_redacted_slice() -> None:
    """AC-16a — :meth:`Writer.write` first non-self parameter is ``RedactedSlice``."""
    writer_py = _SRC / "codegenie" / "output" / "writer.py"
    tree = ast.parse(writer_py.read_text(encoding="utf-8"), filename=str(writer_py))
    class_node = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "Writer"),
        None,
    )
    assert class_node is not None, "class Writer not found in output/writer.py"
    write_fn = next(
        (
            m
            for m in class_node.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == "write"
        ),
        None,
    )
    assert write_fn is not None, "Writer.write not found"
    args = write_fn.args.args
    assert len(args) >= 2, "Writer.write should accept at least (self, envelope, ...)"
    first_non_self = args[1]
    annotation = first_non_self.annotation
    assert annotation is not None, "Writer.write first non-self parameter must be annotated"
    annot_text = ast.unparse(annotation)
    assert annot_text == "RedactedSlice", (
        f"Writer.write first non-self parameter must be annotated RedactedSlice "
        f"(02-ADR-0010); got {annot_text!r}. A dict-typed parameter would let "
        f"unredacted artifacts reach the writer."
    )


def test_envelope_redactor_returns_redacted_slice() -> None:
    """AC-16b — ``envelope_redactor._redact_envelope`` returns ``RedactedSlice``."""
    er_py = _SRC / "codegenie" / "output" / "envelope_redactor.py"
    tree = ast.parse(er_py.read_text(encoding="utf-8"), filename=str(er_py))
    redact = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_redact_envelope"
        ),
        None,
    )
    assert redact is not None, "_redact_envelope not found in envelope_redactor.py"
    assert redact.returns is not None, "_redact_envelope must declare a return annotation"
    annot_text = ast.unparse(redact.returns)
    assert annot_text == "RedactedSlice", (
        f"envelope_redactor._redact_envelope return annotation must be "
        f"RedactedSlice; got {annot_text!r}. A dict-typed return would "
        f"bypass the writer's type-level redaction guarantee."
    )


def test_writer_call_sites_are_closed_set() -> None:
    """AC-17 — production ``Writer.write`` call sites form a closed allowlist."""
    found: list[_CallSite] = []
    for py in _iter_python_sources(_SRC):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (SyntaxError, UnicodeDecodeError):
            continue
        parents = _build_parent_map(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr != "write":
                continue
            # The reachable forms inside production code are
            # ``writer.write(...)`` (local instance) and ``Writer().write(...)``.
            # Both surface as ast.Attribute whose .value is a Name or a Call
            # on the ``Writer`` class. We conservatively accept any ``.write``
            # whose enclosing function ALSO mentions ``Writer`` or ``writer``
            # near the call — captured by checking the enclosing seam name.
            base_text = ast.unparse(func.value)
            if "writer" not in base_text.lower() and "Writer" not in base_text:
                continue
            rel = py.relative_to(_REPO_ROOT).as_posix()
            found.append(
                _CallSite(
                    file=rel,
                    line=node.lineno,
                    enclosing_func=_enclosing_func_name(node, parents),
                    call_text=ast.unparse(node),
                )
            )
    offending = [s for s in found if (s.file, s.enclosing_func) not in ALLOWED_WRITER_CALL_SITES]
    if offending:
        lines = [
            (
                f"Writer.write called at {s.file}:{s.line} ({s.call_text!r}) "
                f"is outside the documented closed call-site set "
                f"(cli._seam_write_envelope). Adding a third call site "
                f"requires updating ALLOWED_WRITER_CALL_SITES in this test "
                f"file AND filing an ADR amendment to 02-ADR-0010."
            )
            for s in offending
        ]
        raise AssertionError("\n".join(lines))
    # Defense-in-depth: the documented seam must still call writer.write.
    for file, func in ALLOWED_WRITER_CALL_SITES:
        present = [s for s in found if s.file == file and s.enclosing_func == func]
        assert present, (
            f"Expected Writer.write to be called from {file}::{func}; "
            f"the documented seam appears to have been removed."
        )


def test_model_construct_banned_under_output_package() -> None:
    """AC-18 — ``model_construct`` is forbidden under ``src/codegenie/output/``.

    Two-part guarantee:

    1. The pre-commit ban (``scripts/check_forbidden_patterns.py``)
       lists ``"output"`` in its ``_PHASE2_BANNED_PACKAGES`` set.
    2. AST walk over ``src/codegenie/output/`` finds zero call sites and
       zero ``model_construct=`` kwarg/assignment occurrences.

    The pre-commit hook is the front-line; this test catches the
    ``--no-verify`` bypass case.
    """
    checker = _REPO_ROOT / "scripts" / "check_forbidden_patterns.py"
    src = checker.read_text(encoding="utf-8")
    assert "_PHASE2_BANNED_PACKAGES" in src, (
        "scripts/check_forbidden_patterns.py must declare _PHASE2_BANNED_PACKAGES "
        "(S1-11 / 02-ADR-0010); the constant is missing."
    )
    # Defensive: confirm "output" is among the banned packages.
    # The declaration is ``_PHASE2_BANNED_PACKAGES: frozenset[str] = frozenset({...})``
    # — an ``ast.AnnAssign`` whose value is a ``Call`` to ``frozenset(...)``
    # around a set literal. ``ast.literal_eval`` cannot evaluate the
    # ``frozenset(...)`` call, so we manually unwrap one layer.
    tree = ast.parse(src, filename=str(checker))
    banned_value: tuple[str, ...] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets: list[ast.expr] = (
            list(node.targets) if isinstance(node, ast.Assign) else [node.target]
        )
        for tgt in targets:
            if not (isinstance(tgt, ast.Name) and tgt.id == "_PHASE2_BANNED_PACKAGES"):
                continue
            value_node: ast.expr | None = node.value
            if value_node is None:
                continue
            # Unwrap a single ``frozenset(<literal>)`` / ``set(<literal>)`` call.
            if (
                isinstance(value_node, ast.Call)
                and isinstance(value_node.func, ast.Name)
                and value_node.func.id in {"frozenset", "set"}
                and len(value_node.args) == 1
            ):
                value_node = value_node.args[0]
            try:
                literal = ast.literal_eval(value_node)
            except (ValueError, SyntaxError):
                continue
            if isinstance(literal, (set, frozenset, tuple, list)):
                banned_value = tuple(str(x) for x in literal)
    assert banned_value is not None, (
        "Could not locate _PHASE2_BANNED_PACKAGES literal in check_forbidden_patterns.py"
    )
    assert "output" in banned_value, (
        f"'output' must be in _PHASE2_BANNED_PACKAGES (currently {banned_value!r}); "
        f"the model_construct ban for src/codegenie/output/ has been weakened."
    )

    # AST scan for any model_construct invocation under output/
    output_root = _SRC / "codegenie" / "output"
    bad_sites: list[tuple[str, int, str]] = []
    for py in output_root.rglob("*.py"):
        try:
            file_tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(file_tree):
            # Call form: anything.model_construct(...)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "model_construct"
            ):
                bad_sites.append(
                    (
                        py.relative_to(_REPO_ROOT).as_posix(),
                        node.lineno,
                        ast.unparse(node),
                    )
                )
            # Keyword: foo(model_construct=...) — vanishingly unlikely but cheap
            elif isinstance(node, ast.keyword) and node.arg == "model_construct":
                # Synthesize a deterministic line number from the parent call's
                # location when available; ast.keyword has no .lineno attribute.
                bad_sites.append(
                    (
                        py.relative_to(_REPO_ROOT).as_posix(),
                        getattr(node.value, "lineno", -1),
                        f"<kwarg> model_construct={ast.unparse(node.value)}",
                    )
                )
    assert not bad_sites, (
        "model_construct usage detected under src/codegenie/output/ — "
        "the 02-ADR-0010 ban has been bypassed. Sites: "
        + "; ".join(f"{f}:{ln} ({txt})" for f, ln, txt in bad_sites)
    )


def test_walker_resolves_aliased_imports() -> None:
    """AC-30 — inline regression that aliased imports are correctly classified.

    Without alias resolution, the walker would silently miss
    ``from codegenie.output.redacted_slice import RedactedSlice as _RS;
    _RS(...)`` and let a contributor "dodge" the structural check by
    renaming the import.
    """
    sample = """
from codegenie.output.redacted_slice import RedactedSlice as _RS

def offender():
    return _RS(slice={}, findings_count=0, fingerprints=[])
"""
    tree = ast.parse(sample)
    aliases = _build_alias_map(tree)
    assert aliases.get("_RS") == _REDACTED_SLICE_QUALNAME, (
        "Alias map failed to resolve `_RS` → RedactedSlice qualname"
    )
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert any(_resolves_to_redacted_slice(c, aliases) for c in calls), (
        "Walker failed to classify `_RS(...)` as a RedactedSlice construction "
        "after alias resolution — AC-30 regression"
    )

    # Negative: a same-name local that does NOT alias to the qualname must
    # not be classified as a construction.
    negative = """
class RedactedSlice:  # shadow — local class with same name
    def __init__(self, **kw): ...

def benign():
    return RedactedSlice(foo=1)
"""
    n_tree = ast.parse(negative)
    n_aliases = _build_alias_map(n_tree)
    n_calls = [n for n in ast.walk(n_tree) if isinstance(n, ast.Call)]
    assert not any(_resolves_to_redacted_slice(c, n_aliases) for c in n_calls), (
        "Walker incorrectly classified a same-name local class as RedactedSlice"
    )
