"""Phase 3 fence helpers — the load-bearing ADR-0010 / ADR-0011 audit-and-lint
enforcement seam for ``src/codegenie/{plugins,transforms}/``.

This module is private (leading-underscore name) and is called from
``tests/fence/test_no_any_in_plugin_surface.py`` and from any future planted-
violation harness that needs to re-prove the AST walker. Keeping the walker
here (not in tests) is what makes the deliberate-negative tests mutation-
resistant — the live ``scan_phase3_surface()`` and the parametrized planted-
shape tests invoke the SAME ``walk_any_annotations()`` function, so any
regression in the production visitor kills both the canary and the live
check (parity with ``codegenie._fence`` precedent, see that module's docstring).

ADR-0011 framing posture: these fences are **audit + lint** enforcement, NOT
runtime guarantees. A PR that edits both the fence file and the violation
defeats the fence — CODEOWNERS on ``tests/fence/`` is the social anchor.

Documented limitations (registered in ``KNOWN_BYPASSES`` rather than left
floating in prose):

* Type-comment annotations (``# type: dict[str, Any]``) — out of the AST
  annotation grammar; ``ast.parse`` records them on a separate ``type_comment``
  attribute and the walker does not descend into them.
* Aliased imports (``from typing import Any as _Any``) followed by use as
  ``_Any`` — Step-1 PRs introducing the aliasing fail review by convention
  (ADR-0011 CODEOWNERS anchor).
* ``from typing_extensions import Any`` — same aliasing failure mode.

See ``docs/phases/03-vuln-deterministic-recipe/stories/S1-05-phase3-fence-tests.md``
for the story that owns this module.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

PHASE3_ROOTS: Final[tuple[Path, ...]] = (
    Path("src/codegenie/plugins"),
    Path("src/codegenie/transforms"),
)
"""The two Phase 3 contract-surface roots the AST walker scans.

Extension is by **one-line append** at Phase-7 time (``plugins/`` lands real
Python under ``vulnerability-remediation--node--npm/recipes/``). Surface that
forward dependency to the S7-01 author via the story's _attempts log.
"""

ALLOWED_MARKER_RE: Final[re.Pattern[str]] = re.compile(
    r"#\s*fence:\s*any-allowed\s*\[(?P<adr>P3-ADR-\d{4})\]\s*$"
)
"""Inline allowlist marker grammar.

A line bearing this marker is exempt from the ``Any`` annotation fence.
The bracketed token MUST be a Phase-3 ADR reference (``P3-ADR-NNNN``); a
bare marker, an empty ``[]``, or a malformed bracket is treated as a
violation (see ``walk_any_annotations``). Zero markers exist at S1-05 GREEN
time; new markers require an ADR amendment.
"""

KNOWN_BYPASSES: Final[frozenset[str]] = frozenset(
    {
        "type-comment-annotation",
        "from-typing-import-any-as-alias",
        "from-typing-extensions-import-any",
    }
)
"""Documented limitations of the AST walker.

Each bypass is exercised by ``tests/fence/_fixtures/_known_bypasses.py`` to
prove the limitation is real (not a regression). New bypass shapes either
get caught by the walker OR added here with a tracking-issue reference.
"""


ViolationKind = Literal[
    "any-name",
    "any-attribute",
    "any-forward-ref",
    "malformed-marker",
]


@dataclass(frozen=True)
class Violation:
    """A single fence hit — primary type for the AST walker's output.

    Replaces an ad-hoc ``tuple[Path, int, str]`` so future fences (S4-05
    capability, S9-02 event-taxonomy) can aggregate violations across walkers
    without per-row tuple-unpacking. ``kind`` is a closed ``Literal`` so
    ``match``-based dispatch is exhaustive.
    """

    file: Path
    line: int
    kind: ViolationKind
    snippet: str


class _AnyAnnotationVisitor(ast.NodeVisitor):
    """Visit ONLY annotation contexts and flag ``Any`` references.

    Annotation contexts:

    * ``ast.AnnAssign.annotation``
    * ``ast.arg.annotation`` (positional / keyword-only / kwarg / vararg)
    * ``ast.FunctionDef.returns`` / ``ast.AsyncFunctionDef.returns``

    The visitor deliberately does NOT descend into ``ast.Call`` (``isinstance(x, Any)``
    is a runtime check, not an annotation) or ``ast.ImportFrom`` (``from typing
    import Any`` is an import, not an annotation). This narrow scope kills the
    obvious false-positive class — over-fence kills credibility.
    """

    def __init__(self, file: Path) -> None:
        self.file = file
        self.violations: list[Violation] = []

    def _scan_annotation_subtree(self, node: ast.AST) -> None:
        """Walk an annotation subtree and emit violations for ``Any`` shapes.

        Three shapes are caught:

        1. ``ast.Name(id="Any")`` — bare ``Any``, ``list[Any]``, ``Callable[..., Any]``.
        2. ``ast.Attribute(attr="Any")`` — ``typing.Any``, ``typing_extensions.Any``.
        3. ``ast.Constant(value=str)`` — string forward-ref ``"Any"`` or
           ``"dict[str, Any]"``. The string is re-parsed in ``mode="eval"``
           and the inner tree is walked the same way.
        """
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and sub.id == "Any":
                self.violations.append(
                    Violation(
                        file=self.file,
                        line=sub.lineno,
                        kind="any-name",
                        snippet="Any",
                    )
                )
            elif isinstance(sub, ast.Attribute) and sub.attr == "Any":
                self.violations.append(
                    Violation(
                        file=self.file,
                        line=sub.lineno,
                        kind="any-attribute",
                        snippet=ast.unparse(sub),
                    )
                )
            elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                # String forward-ref: re-parse and re-walk for Any-shaped refs.
                forward_ref_text = sub.value.strip()
                try:
                    inner = ast.parse(forward_ref_text, mode="eval")
                except SyntaxError:
                    continue
                for inner_sub in ast.walk(inner):
                    if (isinstance(inner_sub, ast.Name) and inner_sub.id == "Any") or (
                        isinstance(inner_sub, ast.Attribute) and inner_sub.attr == "Any"
                    ):
                        self.violations.append(
                            Violation(
                                file=self.file,
                                line=sub.lineno,
                                kind="any-forward-ref",
                                snippet=forward_ref_text,
                            )
                        )
                        break

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._scan_annotation_subtree(node.annotation)
        # Do NOT generic_visit — the RHS (``node.value``) is runtime code, not
        # an annotation. Descending there would catch ``isinstance(x, Any)`` etc.
        # Class bodies and function bodies recurse via visit_ClassDef/FunctionDef.

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scan_function_def(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scan_function_def(node)

    def _scan_function_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if node.returns is not None:
            self._scan_annotation_subtree(node.returns)
        for arg in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            if arg.annotation is not None:
                self._scan_annotation_subtree(arg.annotation)
        if node.args.vararg is not None and node.args.vararg.annotation is not None:
            self._scan_annotation_subtree(node.args.vararg.annotation)
        if node.args.kwarg is not None and node.args.kwarg.annotation is not None:
            self._scan_annotation_subtree(node.args.kwarg.annotation)
        # Recurse into the body so nested classes / functions are still visited.
        for child in node.body:
            self.visit(child)


def _line_has_allowed_marker(source_lines: list[str], lineno: int) -> bool:
    """True iff ``source_lines[lineno-1]`` carries a valid ``# fence:`` marker."""
    if lineno < 1 or lineno > len(source_lines):
        return False
    line = source_lines[lineno - 1]
    # Find the comment marker text after any ``#``. The full-line regex matches
    # the trailing comment plus optional whitespace.
    comment_idx = line.find("#")
    if comment_idx == -1:
        return False
    tail = line[comment_idx:].rstrip("\n")
    return ALLOWED_MARKER_RE.search(tail) is not None


def _find_malformed_markers(file: Path, source_lines: list[str]) -> list[Violation]:
    """Catch shapes that *look* like a fence marker but fail the grammar.

    Bare ``# fence: any-allowed``, empty ``# fence: any-allowed []``, or
    ``# fence: any-allowed [garbage]`` is a violation (with a distinct kind
    so the error message can point at the regex). The grammar is
    intentionally strict — sloppy markers would silently degrade the fence.
    """
    out: list[Violation] = []
    suspicious = re.compile(r"#\s*fence:\s*any-allowed\b")
    for idx, line in enumerate(source_lines, start=1):
        if not suspicious.search(line):
            continue
        comment_idx = line.find("#")
        tail = line[comment_idx:].rstrip("\n")
        if not ALLOWED_MARKER_RE.search(tail):
            out.append(
                Violation(
                    file=file,
                    line=idx,
                    kind="malformed-marker",
                    snippet=tail.strip(),
                )
            )
    return out


def walk_any_annotations(src: str, path: Path) -> list[Violation]:
    """Parse ``src`` and return sorted ``Violation`` list for the ``Any`` fence.

    Pure function. ``mode="exec"`` parse; visitor restricted to annotation
    contexts. Inline ``# fence: any-allowed [P3-ADR-NNNN]`` markers on the
    same line suppress the hit (but their grammar is independently fenced
    via ``_find_malformed_markers``).
    """
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise AssertionError(
            f"Phase-3 fence walker could not parse {path}: {exc}. "
            f"Fix the import / syntax error before re-running the fence."
        ) from exc
    visitor = _AnyAnnotationVisitor(file=path)
    visitor.visit(tree)
    source_lines = src.splitlines()
    filtered = [v for v in visitor.violations if not _line_has_allowed_marker(source_lines, v.line)]
    filtered.extend(_find_malformed_markers(path, source_lines))
    return sorted(filtered, key=lambda v: (str(v.file), v.line, v.kind))


def _iter_python_files(root: Path) -> list[Path]:
    """Return non-``__init__.py`` ``*.py`` files under ``root``, sorted."""
    return sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")


def scan_phase3_surface() -> list[Violation]:
    """Live scan over ``PHASE3_ROOTS``; raises if a root is missing or empty.

    The floor guard (AC-5.a) catches the case where a Phase 3 package gets
    deleted or accidentally emptied — silent green is the worst failure
    mode. The error message names the missing-or-empty root.
    """
    out: list[Violation] = []
    for root in PHASE3_ROOTS:
        if not root.is_dir():
            raise AssertionError(
                f"Phase-3 fence root {root} does not exist. The fence requires "
                f"every entry in PHASE3_ROOTS to be a directory; if the package "
                f"was intentionally removed, edit PHASE3_ROOTS via ADR amendment."
            )
        files = _iter_python_files(root)
        if not files:
            raise AssertionError(
                f"Phase-3 fence root {root} contains no non-__init__.py modules. "
                f"This would silently green the fence; refusing to proceed."
            )
        for file in files:
            text = file.read_text(encoding="utf-8")
            out.extend(walk_any_annotations(text, file))
    return out
