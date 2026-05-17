"""``NodeReflectionProbe`` (B3, S4-06) — Node dynamic-pattern detector.

Detects Node-ecosystem dynamic patterns that erode SCIP confidence:
``eval``, ``new Function(...)``, dynamic ``require(varName)``, dynamic
``import(specifier)``, prototype manipulation, decorator usage,
``process.env.X`` reads. Reports the ``reflection`` slice consumed by
Phase 3+ adapters that need to know "how much do dynamic patterns
limit static-analysis confidence in this repo?".

The probe is grammar-accurate — every detection is a tree-sitter
``Query`` against the parsed AST, not a regex against source text.
Adding a new pattern (e.g., ``with`` statements, ``Object.assign``
prototype writes) is a tuple-entry insertion in
:data:`_REFLECTION_QUERIES`; zero edits to dispatch logic.

Grammar loading goes through :func:`codegenie.grammars.lock.language_for`
(02-ADR-0011) — the probe does NOT import ``tree_sitter_typescript`` or
``tree_sitter_javascript`` directly. On any kernel failure surface
(:class:`GrammarLoadRefused`), the probe emits an honest "could not
measure" slice with ``confidence_impact="high"`` (inverted-semantics:
high impact means we cannot prove the absence of reflection) and the
``node_reflection.grammar_unavailable`` error.

**Inverted semantics on ``confidence_impact``** (per ``localv2.md §5.2 B3``):

- ``"low"`` impact = HIGH confidence (no reflection detected; SCIP can
  trust the static analysis).
- ``"high"`` impact = LOW confidence (dynamic patterns prevent static
  reasoning).

The module-level :data:`_ConfidenceImpact` alias is distinct from the
standard :data:`_Confidence` envelope field so mypy `--strict` rejects
accidental mixing.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S4-06-layer-b-marker-probes.md``
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md``
- ``docs/localv2.md §5.2 B3``
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias

import structlog

from codegenie.errors import (
    DepthCapExceeded,
    MalformedJSONError,
    SizeCapExceeded,
    SymlinkRefusedError,
)
from codegenie.grammars.lock import GrammarLoadRefused, SupportedLanguage, language_for
from codegenie.logging import EVENT_PROBE_START, EVENT_PROBE_SUCCESS
from codegenie.parsers import safe_json
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task
from codegenie.probes.language_filter import _admits_node_project
from codegenie.probes.layer_b._indexable_files import _EXCLUDE_DIRS
from codegenie.probes.registry import register_probe

__all__ = ["NodeReflectionProbe"]


_log = structlog.get_logger(__name__)


_WARNING_IDS: Final[frozenset[str]] = frozenset(
    {
        "node_reflection.package_json_unparseable",
    }
)
_ERROR_IDS: Final[frozenset[str]] = frozenset(
    {
        "node_reflection.grammar_unavailable",
        "node_reflection.parse_error",
    }
)
_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
for _id in _WARNING_IDS | _ERROR_IDS:
    if not _ID_PATTERN.match(_id):
        raise AssertionError(f"ADR-0007 violation: {_id!r}")


# Query catalog — extension by tuple insertion (Open/Closed at file
# boundary; mirrors GeneratedCodeProbe's _GENERATOR_HEADER_MARKERS).
_REFLECTION_QUERIES: Final[Mapping[str, str]] = {
    "eval_usage": '(call_expression function: (identifier) @id (#eq? @id "eval"))',
    "function_constructor_usage": (
        '(new_expression constructor: (identifier) @id (#eq? @id "Function"))'
    ),
    "dynamic_require": (
        "(call_expression function: (identifier) @id "
        'arguments: (arguments (identifier))  (#eq? @id "require"))'
    ),
    "dynamic_import": ("(call_expression function: (import) arguments: (arguments (identifier)))"),
    "prototype_manipulation": (
        "(member_expression property: (property_identifier) @p "
        '(#match? @p "^(prototype|__proto__)$"))'
    ),
    "decorator": "(decorator) @dec",
    "env_read": (
        "(member_expression "
        "object: (member_expression "
        "object: (identifier) @o property: (property_identifier) @p) "
        '(#eq? @o "process") (#eq? @p "env"))'
    ),
}


_DECORATOR_DEP_TRUTH_TABLE: Final[tuple[tuple[str, str], ...]] = (
    ("nestjs", "@nestjs/core"),
    ("typeorm", "typeorm"),
    ("class_validator", "class-validator"),
)


_SOURCE_SUFFIX_TO_LANGUAGE: Final[Mapping[str, SupportedLanguage]] = {
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
}


_PKG_JSON_MAX_BYTES: Final[int] = 5 * 1024 * 1024
_FILE_MAX_BYTES: Final[int] = 2 * 1024 * 1024


_Confidence: TypeAlias = Literal["high", "medium", "low"]
"""Envelope-level confidence (high/medium/low)."""

_ConfidenceImpact: TypeAlias = Literal["low", "medium", "high"]
"""Inverted-semantics slice-level field: low=no impact (good),
high=large impact (bad). Distinct alias so mypy rejects accidental
assignment of an envelope-shaped value to the slice field."""


# ---------------------------------------------------------------------------
# Pure helpers (functional core — no I/O, no ctx)
# ---------------------------------------------------------------------------


def _decorator_flags(pkg: Mapping[str, Any] | None) -> dict[str, bool]:
    """Return the {nestjs, typeorm, class_validator} truth table from
    ``package.json`` deps. Falsy / missing pkg → all False."""
    if pkg is None:
        return {key: False for key, _ in _DECORATOR_DEP_TRUTH_TABLE}
    deps = pkg.get("dependencies") if isinstance(pkg.get("dependencies"), Mapping) else {}
    dev_deps = pkg.get("devDependencies") if isinstance(pkg.get("devDependencies"), Mapping) else {}
    all_deps: set[str] = set()
    if isinstance(deps, Mapping):
        all_deps.update(str(k) for k in deps)
    if isinstance(dev_deps, Mapping):
        all_deps.update(str(k) for k in dev_deps)
    return {flag_name: dep_name in all_deps for flag_name, dep_name in _DECORATOR_DEP_TRUTH_TABLE}


def _derive_confidence_impact(
    counts: Mapping[str, int],
    flags: Mapping[str, bool],
) -> _ConfidenceImpact:
    """Three-arm derivation (AC-R7) over counts + decorator flags.

    - ``eval > 0`` OR ``Function > 0`` → ``"high"`` (rare, high-signal).
    - All counts == 0 AND all decorator flags False → ``"low"``.
    - Otherwise → ``"medium"``.
    """
    if counts.get("eval_usage", 0) > 0 or counts.get("function_constructor_usage", 0) > 0:
        return "high"
    if all(v == 0 for v in counts.values()) and not any(flags.values()):
        return "low"
    return "medium"


def _is_dynamic_property_access(node: Any) -> bool:
    """A ``subscript_expression`` (``obj[key]``) is "dynamic" when the
    bracket-index is NOT a literal string/number — i.e., an identifier,
    template_string, or call_expression. Pure structural test on the
    tree-sitter ``Node``."""
    if node.type != "subscript_expression":
        return False
    index_node = node.child_by_field_name("index")
    if index_node is None:
        return False
    return index_node.type not in {"string", "number"}


def _walk_node_source_files(root: Path) -> Iterator[Path]:
    """Yield ``.ts``/``.tsx``/``.js``/``.jsx`` files under *root*,
    excluding the canonical exclude dirs. Sorted for determinism."""
    matches: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SOURCE_SUFFIX_TO_LANGUAGE:
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in _EXCLUDE_DIRS for part in rel.parts):
            continue
        matches.append(path)
    matches.sort(key=lambda p: p.as_posix())
    yield from matches


def _empty_counts() -> dict[str, int]:
    """Zero-initialized count map covering every query in
    :data:`_REFLECTION_QUERIES` plus the bracket-access scan."""
    counts: dict[str, int] = {key: 0 for key in _REFLECTION_QUERIES}
    counts["dynamic_property_access"] = 0
    counts["env_read_code_path_affecting"] = 0
    return counts


# ---------------------------------------------------------------------------
# Probe class (imperative shell)
# ---------------------------------------------------------------------------


@register_probe(heaviness="medium")
class NodeReflectionProbe(Probe):
    """Layer B — Node dynamic-pattern detector (medium heaviness).

    Per-file tree-sitter Query scan across the .ts/.tsx/.js/.jsx
    glob; same workload shape as S4-04's TreeSitterImportGraphProbe.
    """

    name: str = "node_reflection"
    version: str = "0.1.0"
    layer = "B"
    tier = "base"
    applies_to_languages: list[str] = ["javascript", "typescript"]
    applies_to_tasks: list[str] = ["*"]
    requires: list[str] = ["language_detection"]
    timeout_seconds: int = 60
    cache_strategy: Literal["content"] = "content"
    declared_inputs: list[str] = [
        "**/*.ts",
        "**/*.tsx",
        "**/*.js",
        "**/*.jsx",
        "package.json",
    ]

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return _admits_node_project(self.applies_to_languages, repo.detected_languages, repo.root)

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        _log.info(EVENT_PROBE_START, probe=self.name)
        t0 = time.perf_counter()

        try:
            from tree_sitter import Parser, Query, QueryCursor
        except ImportError as exc:
            return self._emit_grammar_unavailable(repo, str(exc), t0)

        try:
            languages: dict[SupportedLanguage, Any] = {
                "typescript": language_for("typescript"),
                "tsx": language_for("tsx"),
                "javascript": language_for("javascript"),
            }
        except GrammarLoadRefused as exc:
            return self._emit_grammar_unavailable(repo, str(exc), t0)

        # Pre-compile every (language, query) once — every file reuses
        # the compiled QueryCursors.
        compiled_queries: dict[tuple[str, str], Query] = {}
        for lang_name, lang in languages.items():
            for query_name, query_text in _REFLECTION_QUERIES.items():
                compiled_queries[(lang_name, query_name)] = Query(lang, query_text)

        counts = _empty_counts()
        affected_files: set[str] = set()
        warnings: list[str] = []
        parse_errors = 0

        pkg = self._read_package_json(repo.root / "package.json", ctx, warnings)

        for path in _walk_node_source_files(repo.root):
            language_name = _SOURCE_SUFFIX_TO_LANGUAGE[path.suffix]
            try:
                file_bytes = path.read_bytes()
            except OSError:
                continue
            if len(file_bytes) > _FILE_MAX_BYTES:
                continue
            parser = Parser(languages[language_name])
            try:
                tree = parser.parse(file_bytes)
            except (ValueError, RuntimeError):
                parse_errors += 1
                continue

            file_hits = 0
            rel_path = path.relative_to(repo.root).as_posix()
            for query_name in _REFLECTION_QUERIES:
                query = compiled_queries[(language_name, query_name)]
                matches = QueryCursor(query).matches(tree.root_node)
                if matches:
                    counts[query_name] += len(matches)
                    file_hits += len(matches)

            # Bracket access (dynamic property access) — pure structural
            # check; tree-sitter does not capture "the index is not a
            # literal" inside a single query.
            for node in _iter_subscript_expressions(tree.root_node):
                if _is_dynamic_property_access(node):
                    counts["dynamic_property_access"] += 1
                    file_hits += 1

            # process.env reads inside if/switch conditions — heuristic
            # via parent-chain walk on already-matched env_read captures.
            env_query = compiled_queries[(language_name, "env_read")]
            for _, captures in QueryCursor(env_query).matches(tree.root_node):
                for nodes in captures.values():
                    for node in nodes:
                        if _is_in_condition_context(node):
                            counts["env_read_code_path_affecting"] += 1

            if file_hits > 0:
                affected_files.add(rel_path)

        decorator_flags = _decorator_flags(pkg)
        confidence_impact = _derive_confidence_impact(counts, decorator_flags)
        envelope_confidence: _Confidence = "high" if parse_errors == 0 else "low"
        errors: list[str] = []
        if parse_errors > 0:
            errors.append("node_reflection.parse_error")

        slice_payload: dict[str, Any] = {
            "eval_usage": counts["eval_usage"],
            "function_constructor_usage": counts["function_constructor_usage"],
            "dynamic_require_count": counts["dynamic_require"],
            "dynamic_import_count": counts["dynamic_import"],
            "dynamic_property_access_count": counts["dynamic_property_access"],
            "prototype_manipulation_count": counts["prototype_manipulation"],
            "decorator_usage": {
                "nestjs": decorator_flags["nestjs"],
                "typeorm": decorator_flags["typeorm"],
                "class_validator": decorator_flags["class_validator"],
                "custom_decorators_detected": counts["decorator"],
            },
            "env_var_reads": {
                "count": counts["env_read"],
                "code_path_affecting": counts["env_read_code_path_affecting"],
            },
            "confidence_impact": confidence_impact,
            "affected_files": sorted(affected_files),
        }

        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        _log.info(
            EVENT_PROBE_SUCCESS,
            probe=self.name,
            confidence=envelope_confidence,
            confidence_impact=confidence_impact,
            affected=len(affected_files),
        )
        return ProbeOutput(
            schema_slice={"reflection": slice_payload},
            raw_artifacts=[],
            confidence=envelope_confidence,
            duration_ms=duration_ms,
            warnings=sorted(set(warnings)),
            errors=sorted(set(errors)),
        )

    def _read_package_json(
        self,
        pkg_path: Path,
        ctx: ProbeContext,
        warnings: list[str],
    ) -> Mapping[str, Any] | None:
        if not pkg_path.is_file():
            return None
        try:
            if ctx.parsed_manifest is not None:
                return ctx.parsed_manifest(pkg_path)
            return safe_json.load(pkg_path, max_bytes=_PKG_JSON_MAX_BYTES)
        except (MalformedJSONError, SizeCapExceeded, DepthCapExceeded, SymlinkRefusedError):
            warnings.append("node_reflection.package_json_unparseable")
            return None

    def _emit_grammar_unavailable(self, repo: RepoSnapshot, reason: str, t0: float) -> ProbeOutput:
        """AC-R8 honest-absence slice. Inverted semantics on
        ``confidence_impact``: "high" because we could not measure, so
        the gather output must NOT claim low impact."""
        _log.warning("probe.failure", probe=self.name, reason=reason)
        slice_payload: dict[str, Any] = {
            "eval_usage": 0,
            "function_constructor_usage": 0,
            "dynamic_require_count": 0,
            "dynamic_import_count": 0,
            "dynamic_property_access_count": 0,
            "prototype_manipulation_count": 0,
            "decorator_usage": {
                "nestjs": False,
                "typeorm": False,
                "class_validator": False,
                "custom_decorators_detected": 0,
            },
            "env_var_reads": {"count": 0, "code_path_affecting": 0},
            "confidence_impact": "high",
            "affected_files": [],
        }
        duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
        # ``repo`` is part of the failure signature so structured logs
        # carry the root path; not embedded in the slice (would leak abs
        # paths through the writer's sanitizer if not careful).
        del repo
        return ProbeOutput(
            schema_slice={"reflection": slice_payload},
            raw_artifacts=[],
            confidence="low",
            duration_ms=duration_ms,
            warnings=[],
            errors=["node_reflection.grammar_unavailable"],
        )


# ---------------------------------------------------------------------------
# AST iteration helpers (module-level — no I/O, no ctx)
# ---------------------------------------------------------------------------


def _iter_subscript_expressions(root: Any) -> Iterator[Any]:
    """Yield every ``subscript_expression`` node in the tree (pure)."""
    stack: list[Any] = [root]
    while stack:
        node = stack.pop()
        if node.type == "subscript_expression":
            yield node
        stack.extend(node.children)


def _is_in_condition_context(node: Any) -> bool:
    """Walk up to two AST levels checking whether *node* is inside an
    ``if_statement`` or ``switch_statement`` condition. Pure structural
    check — same semantics as AC-R6 heuristic."""
    current = node
    for _ in range(4):  # generous bound — covers paren/member chains
        parent = current.parent
        if parent is None:
            return False
        if parent.type in {"if_statement", "switch_statement", "while_statement"}:
            return True
        current = parent
    return False
