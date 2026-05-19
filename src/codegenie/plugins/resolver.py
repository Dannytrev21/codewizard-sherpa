"""Phase-3 S2-04 — plugin resolver.

Implements :func:`PluginRegistry.resolve` via the algorithm pinned by
Phase-3 ADR-0003 §Decision steps 1–4: filter registered plugins by the
incoming :class:`PluginScope`, sort by
``(specificity desc, precedence desc, name asc)``, walk the head
plugin's ``extends`` chain (cycle-checked, max depth 4), and compose
``TCCM`` + ``adapters`` left-to-right. When the sorted head is the
canonical universal-fallback plugin (``universal--*--*``) — or when
nothing matches but the universal plugin is registered — return
:class:`UniversalFallbackResolution` instead of :class:`ConcreteResolution`.

The return type is the typed tagged union
:data:`PluginResolution = ConcreteResolution | UniversalFallbackResolution`,
not ``Plugin | None``. Production ADR-0009 (humans always merge) is
*statically* enforced by this discriminated union: the "no concrete
match" path is type-impossible to silently drop because the variant has
to be handled in every dispatch site's ``match`` block — checked at
``mypy --strict`` time via the ``assert_never`` arm.

Module-purity invariant (Phase-3 ADR-0001 chokepoint hygiene
generalised): imports only the closed allowlist —
``__future__, dataclasses, typing, pydantic`` and four sibling
``codegenie.plugins.*`` modules + ``codegenie.types.identifiers``. No
``os``, no ``pathlib``, no ``logging``, no I/O. AST source-scan test in
``tests/unit/plugins/test_resolver_purity.py`` enforces.

Functional core / imperative shell: the public :func:`resolve` composes
small pure helpers (``_lift_dim``, :func:`lift_manifest_scope`,
``_lift_candidates``, ``_filter_matches``, ``_sort_key``,
``_candidates_considered``, :func:`compose_extends_chain``). The only
I/O is whatever the registry holds in memory; resolution itself is
deterministic given identical inputs.

Sources:

- Phase-3 ADR-0003 §Decision + §Consequences row 5 — algorithm and
  ``candidates_considered`` semantics.
- Phase-3 ADR-0010 §Decision §1 / §3 — sum-type discipline; tagged
  union with discriminator.
- Phase-3 phase-arch-design.md §C2 / §C3 / §Data model (lines 775–791)
  — ``ConcreteResolution.matched_scope``, ``UniversalFallbackResolution``.
- production ADR-0031 §Inheritance and override — left-to-right
  later-wins ``extends`` composition.
- production ADR-0009 — humans always merge; the typed union is the
  static enforcement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Final, Literal, TypeAlias, assert_never

from pydantic import BaseModel, ConfigDict, Field

from codegenie.plugins.errors import (
    PluginExtendsCycle,
    PluginExtendsDepthExceeded,
    PluginNotRegistered,
    PluginRegistryCorrupted,
)
from codegenie.plugins.manifest import ManifestScope
from codegenie.plugins.protocols import Adapter, Plugin
from codegenie.plugins.scope import Concrete, PluginScope, ScopeDim, Wildcard
from codegenie.types.identifiers import PluginId, PrimitiveName

if TYPE_CHECKING:  # pragma: no cover — break registry ↔ resolver import cycle
    from codegenie.plugins.registry import PluginRegistry

__all__: Final[tuple[str, ...]] = (
    "ComposedTccm",
    "ConcreteResolution",
    "PluginResolution",
    "ScopedCandidate",
    "UNIVERSAL_FALLBACK_ID",
    "UniversalFallbackResolution",
    "compose_extends_chain",
    "lift_manifest_scope",
    "resolve",
)

# Single source of truth for the universal-fallback plugin name. The
# literal MUST live in exactly one place inside ``src/codegenie/``; the
# AST scan ``tests/static/test_universal_fallback_id_single_source.py``
# enforces. ``Final[PluginId]`` doubles as the smart-constructor lift —
# the ``NewType`` is identity-to-``str`` at runtime so the ``PluginId``
# call is structural typing only. ADR-0003 §Decision step 3 names this
# literal as the no-match-fallback discriminator.
UNIVERSAL_FALLBACK_ID: Final[PluginId] = PluginId("universal--*--*")

# Empirical cap per Phase-3 ADR-0003 §Tradeoffs — no production plugin
# chain is expected to exceed four levels of ``extends``. Raising the
# cap is an ADR amendment, not a code-time tweak. AST scan asserts the
# integer literal ``4`` appears at most once in this module so a future
# refactor that mutates only one site fails loudly.
_MAX_EXTENDS_DEPTH: Final[int] = 4


# ---------------------------------------------------------------------------
# Value types — frozen + extra="forbid" everywhere (ADR-0010 §Decision 3).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScopedCandidate:
    """One plugin paired with **one** lifted :class:`PluginScope`.

    A plugin whose ``manifest.scope`` declares lists on multiple dims
    (e.g., ``languages=["node", "python"]``) fans out into multiple
    ``ScopedCandidate`` instances — one per element of the cross
    product. The resolver scores each independently so the ``language``
    dim's specificity reflects the *single* concrete value the candidate
    is being matched against, not the union.
    """

    plugin: Plugin
    lifted_scope: PluginScope


class ComposedTccm(BaseModel):
    """Minimal :class:`TCCM` placeholder for Step 2.

    Step 3 (S3-01) replaces this with the real ``TCCM`` Pydantic per
    Phase-3 ADR-0004 (private capabilities). The shapes line up — the
    resolver's left-to-right merge logic stays identical — only the
    field set on the underlying model widens. This story documents the
    substitution point so a future contributor doesn't accidentally
    fork the merge code into the new model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provides: dict[str, dict[str, str]] = Field(default_factory=dict)
    requires: dict[str, tuple[str, ...]] = Field(default_factory=dict)


class ConcreteResolution(BaseModel):
    """A concrete plugin matched and composed its ``extends`` chain.

    ``extends_chain`` is the root-to-leaf ordered tuple of every
    :class:`Plugin` walked, **with the head plugin itself at the tail**.
    ``matched_scope`` is the single lifted :class:`PluginScope` that
    filtered through (one of the cross-product expansions of
    ``plugin.manifest.scope``); arch §Data model line 779 names this
    field.

    ``composed_tccm`` and ``composed_adapters`` are the left-to-right
    later-wins merge over the chain (production ADR-0031 §Inheritance
    and override). For ``composed_tccm.provides`` — a
    ``dict[str, dict[str, str]]`` — the inner dicts are also merged
    later-wins per key (one level deep). Two levels deep is out of
    scope; the real merge semantics land with the real ``TCCM`` in
    S3-01.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    kind: Literal["concrete"] = "concrete"
    plugin: Plugin
    extends_chain: tuple[Plugin, ...]
    matched_scope: PluginScope
    composed_tccm: ComposedTccm
    composed_adapters: dict[PrimitiveName, Adapter]


class UniversalFallbackResolution(BaseModel):
    """No concrete plugin matched the incoming scope.

    ``candidates_considered`` is the alphabetised tuple of every
    *concrete* (non-universal) :class:`PluginId` registered at resolve
    time. The universal fallback itself is intentionally excluded —
    the resolver already narrowed *to* it, so naming it in this list
    would be debug noise. Per ADR-0003 §Consequences row 5: "concrete
    plugins were filtered out".

    Pydantic ``frozen=True`` plus the discriminated-union ``kind``
    literal mean a consumer's ``match`` over :data:`PluginResolution`
    cannot accidentally treat this variant as a concrete resolution at
    the type level. Production ADR-0009 (humans always merge) is the
    invariant; this variant is its structural enforcement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["universal_fallback"] = "universal_fallback"
    reason: Literal["no_concrete_match"]
    candidates_considered: tuple[PluginId, ...]


# Discriminated union — the public return type of :func:`resolve`.
# Annotated with the Pydantic ``Field(discriminator="kind")`` so a
# future consumer that validates from JSON dispatches by ``kind``
# automatically. The ``TypeAlias`` keeps mypy narrowing flowing
# through the alias name rather than re-deriving the union shape at
# every call site.
PluginResolution: TypeAlias = Annotated[
    ConcreteResolution | UniversalFallbackResolution,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Pure helpers — flat-mapping and per-dim lift. No side effects.
# ---------------------------------------------------------------------------


def _lift_dim(raw: str) -> ScopeDim:
    """Lift a raw manifest dim string to a :class:`ScopeDim` variant.

    ``"*"`` → :class:`Wildcard`; everything else → :class:`Concrete`.
    The manifest YAML loader already validates input shape (S2-02), so
    this helper is a structural lift — no defensive re-parse. Mirrors
    the S2-04 hardening note "construct directly, do not round-trip
    through ``PluginScope.parse``".
    """
    if raw == "*":
        return Wildcard()
    return Concrete(value=raw)


def lift_manifest_scope(
    manifest_scope: ManifestScope,
) -> tuple[PluginScope, ...]:
    """Lift a manifest scope (raw ``str | list[str]`` per dim) into the
    cross product of single-dim :class:`PluginScope` instances.

    Examples (the AC-7 parametrized table):

    - ``(task="vuln", languages="node", builds="npm")`` → 1 PluginScope.
    - ``(task="vuln", languages=["node", "python"], builds="*")`` → 2.
    - ``(task=["vuln", "distroless"], languages="*", builds=["npm", "pip"])``
      → 4.
    - ``(task="*", languages="*", builds="*")`` → 1 (universal).

    The fan-out is deterministic across the three dims in declaration
    order (``task_class``, ``language``, ``build_system``) — the
    resolver's downstream sort is independent of fan-out order, but
    pinning it here keeps the property test reproducible.
    """
    tasks = _as_list(manifest_scope.task_class)
    languages = _as_list(manifest_scope.languages)
    builds = _as_list(manifest_scope.build_systems)

    scopes: list[PluginScope] = []
    for task in tasks:
        for language in languages:
            for build in builds:
                scopes.append(
                    PluginScope(
                        task_class=_lift_dim(task),
                        language=_lift_dim(language),
                        build_system=_lift_dim(build),
                    )
                )
    return tuple(scopes)


def _as_list(value: str | list[str]) -> list[str]:
    """Normalise a manifest dim to a non-empty list[str].

    The manifest's Pydantic ``str | list[str]`` lift already guarantees
    non-empty strings inside the list (S2-02 validators); this helper
    is a typing-shim, not a validator.
    """
    if isinstance(value, str):
        return [value]
    return list(value)


def _lift_candidates(plugins: tuple[Plugin, ...]) -> tuple[ScopedCandidate, ...]:
    """Flat-map every plugin into its lifted candidates.

    A multi-scope manifest contributes multiple :class:`ScopedCandidate`
    rows; the resolver's filter+sort operates on the post-flatten tuple
    so the per-row specificity reflects exactly one Concrete-vs-Wildcard
    pattern per dim.
    """
    out: list[ScopedCandidate] = []
    for plugin in plugins:
        for lifted in lift_manifest_scope(plugin.manifest.scope):
            out.append(ScopedCandidate(plugin=plugin, lifted_scope=lifted))
    return tuple(out)


def _unpack(dim: ScopeDim) -> str:
    """Materialise a :class:`ScopeDim` as the string form S1-02's
    :meth:`PluginScope.matches` consumes.

    ``Wildcard()`` becomes ``"*"`` — the operator did not specify; any
    plugin dim admits it. ``Concrete(value=v)`` materialises as ``v``.
    Mutation defence: a tempting "return empty string for Wildcard"
    refactor fails the property test (which exercises wildcard incoming
    scopes against concrete plugin dims).
    """
    match dim:
        case Wildcard():
            return "*"
        case Concrete(value=v):
            return v
        case _:  # pragma: no cover — exhaustiveness guarantee.
            assert_never(dim)


def _filter_matches(
    candidates: tuple[ScopedCandidate, ...], scope: PluginScope
) -> tuple[ScopedCandidate, ...]:
    """Keep only the candidates whose lifted scope admits ``scope``.

    Incoming wildcards are treated as "operator did not specify" — they
    admit every plugin dim. The match call goes through
    :meth:`PluginScope.matches` (S1-02) so the per-dim semantics are
    shared with the rest of the kernel.
    """
    return tuple(
        c
        for c in candidates
        if c.lifted_scope.matches(
            task=_unpack(scope.task_class),
            language=_unpack(scope.language),
            build=_unpack(scope.build_system),
        )
    )


def _sort_key(candidate: ScopedCandidate) -> tuple[int, int, str]:
    """Return the ADR-0003 §Decision step 2 sort key for a candidate.

    Tuple form is ``(-specificity, -precedence, name)`` — Python's
    natural ascending tuple sort then yields ``(specificity desc,
    precedence desc, name asc)`` without per-tuple ``key=`` gymnastics.

    Pinned as a named helper so the mutation kill-list test
    (``test_exact_match_beats_wildcard``,
    ``test_precedence_breaks_specificity_tie``,
    ``test_name_breaks_precedence_tie``) can each kill its
    corresponding mutation.
    """
    return (
        -candidate.lifted_scope.specificity(),
        -candidate.plugin.manifest.precedence,
        candidate.plugin.manifest.name,
    )


def _candidates_considered(registry: PluginRegistry) -> tuple[PluginId, ...]:
    """Return the alphabetised tuple of every *concrete* registered
    :class:`PluginId` — i.e., every ``plugin.manifest.name`` except
    :data:`UNIVERSAL_FALLBACK_ID`.

    Per ADR-0003 §Consequences row 5 — "concrete plugins were filtered
    out". Tuple (not list) so the field is hashable + immutable.
    Excludes the universal plugin since the caller narrowed *to* it;
    re-naming it in the operator-visible list would be debug noise.
    """
    names = sorted(
        p.manifest.name for p in registry.all() if p.manifest.name != UNIVERSAL_FALLBACK_ID
    )
    return tuple(names)


# ---------------------------------------------------------------------------
# Extends-chain walker — cycle-checked, depth-capped, left-to-right merge.
# ---------------------------------------------------------------------------


def compose_extends_chain(
    plugin: Plugin,
    registry: PluginRegistry,
    *,
    max_depth: int = _MAX_EXTENDS_DEPTH,
) -> ConcreteResolution:
    """Walk ``plugin.manifest.extends`` depth-first, left-to-right;
    compose ``composed_tccm`` and ``composed_adapters`` left-to-right
    (later wins on collision); return the resulting
    :class:`ConcreteResolution` with ``matched_scope`` left as a stub
    for the caller (:func:`resolve`) to fill in.

    Raises:

    - :class:`PluginExtendsCycle` when the same plugin id is visited
      twice in one walk. ``chain`` carries the visited sequence with
      the cycle-entry repeated at the tail.
    - :class:`PluginExtendsDepthExceeded` when the walk would descend
      past ``max_depth`` levels (``len(visited) >= max_depth`` and
      another ``extends`` link awaits). ``chain`` carries the visited
      sequence at the point of refusal.
    - :class:`codegenie.plugins.errors.PluginNotRegistered` when an
      ``extends`` target is not in ``registry``. Propagated unchanged
      from :meth:`PluginRegistry.get`; the resolver does NOT translate
      it (the loader's startup integrity check, S2-03, is the right
      place to fail-fast for missing extends targets).
    """
    chain_tuple: list[Plugin] = []
    composed_tccm = ComposedTccm()
    composed_adapters: dict[PrimitiveName, Adapter] = {}

    def walk(
        current: Plugin,
        visited: frozenset[PluginId],
        visited_path: tuple[PluginId, ...],
    ) -> None:
        nonlocal composed_tccm, composed_adapters
        current_name: PluginId = current.manifest.name
        if current_name in visited:
            raise PluginExtendsCycle(chain=(*visited_path, current_name))
        if len(visited) >= max_depth:
            raise PluginExtendsDepthExceeded(chain=(*visited_path, current_name))
        new_visited = visited | {current_name}
        new_path = (*visited_path, current_name)
        for extends_id in current.manifest.extends:
            walk(registry.get(extends_id), new_visited, new_path)
        chain_tuple.append(current)
        composed_tccm = _merge_tccm(composed_tccm, _plugin_tccm(current))
        composed_adapters = _merge_adapters(composed_adapters, current.adapters())

    walk(plugin, frozenset(), ())

    # ``matched_scope`` filled by caller — the walker has no view of the
    # incoming scope. Sentinel: the lifted plugin scope's first entry.
    placeholder_scope = lift_manifest_scope(plugin.manifest.scope)[0]
    return ConcreteResolution(
        plugin=plugin,
        extends_chain=tuple(chain_tuple),
        matched_scope=placeholder_scope,
        composed_tccm=composed_tccm,
        composed_adapters=composed_adapters,
    )


def _plugin_tccm(plugin: Plugin) -> ComposedTccm:
    """Return the plugin's :class:`ComposedTccm` contribution.

    Step 2's placeholder: the real :class:`TCCM` loader (S3-01) reads a
    plugin's ``tccm.yaml``. Until then, every fake plugin defaults to
    an empty :class:`ComposedTccm`; tests that exercise the merge
    semantics monkey-patch via ``transforms_map`` keyed by the
    informal ``provides`` shape. The substitution point is documented
    on :class:`ComposedTccm`.
    """
    raw = getattr(plugin, "_composed_tccm", None)
    if isinstance(raw, ComposedTccm):
        return raw
    return ComposedTccm()


def _merge_tccm(left: ComposedTccm, right: ComposedTccm) -> ComposedTccm:
    """Left-to-right later-wins merge for the placeholder
    :class:`ComposedTccm`.

    ``provides`` is a ``dict[str, dict[str, str]]``; the outer key
    merge is later-wins; the inner per-key dict merge is also
    later-wins (one level deep). ``requires`` is a flat
    ``dict[str, tuple[str, ...]]`` — outer-key later-wins. Production
    ADR-0031 §Inheritance and override pins this.
    """
    merged_provides: dict[str, dict[str, str]] = {k: dict(v) for k, v in left.provides.items()}
    for outer_key, inner in right.provides.items():
        if outer_key in merged_provides:
            merged_provides[outer_key] = {**merged_provides[outer_key], **inner}
        else:
            merged_provides[outer_key] = dict(inner)
    merged_requires = {**left.requires, **right.requires}
    return ComposedTccm(provides=merged_provides, requires=merged_requires)


def _merge_adapters(
    left: dict[PrimitiveName, Adapter], right: dict[PrimitiveName, Adapter]
) -> dict[PrimitiveName, Adapter]:
    """Single-level later-wins dict merge for adapter maps.

    Production ADR-0031 §Inheritance and override pins this. Each
    plugin contributes one adapter per :class:`PrimitiveName`; a child
    plugin's adapter for a primitive replaces its parent's entirely
    (the child can wrap the parent at the Plugin layer if it wants
    delegation).
    """
    return {**left, **right}


# ---------------------------------------------------------------------------
# Public surface — :func:`resolve`. Composes the helpers above.
# ---------------------------------------------------------------------------


def resolve(registry: PluginRegistry, scope: PluginScope) -> PluginResolution:
    """Map an incoming :class:`PluginScope` to a typed
    :data:`PluginResolution`.

    The algorithm pinned by Phase-3 ADR-0003 §Decision steps 1–4:

    1. Lift every registered plugin's manifest scope into the
       cross-product of single-dim :class:`PluginScope` instances.
    2. Keep only the candidates whose lifted scope admits ``scope``.
    3. If no candidate matched: return
       :class:`UniversalFallbackResolution` (with empty
       ``candidates_considered``) if the universal plugin is
       registered, else raise :class:`PluginRegistryCorrupted`.
    4. Sort matches by
       ``(specificity desc, precedence desc, name asc)``.
    5. If the sorted head IS the universal plugin: return
       :class:`UniversalFallbackResolution` with the operator-visible
       :func:`_candidates_considered` debug list.
    6. Else: walk the head's ``extends`` chain via
       :func:`compose_extends_chain`; return the resulting
       :class:`ConcreteResolution` with ``matched_scope`` set to the
       head's lifted scope.

    Totality: this function never returns ``None`` and never raises
    on a well-formed registry. The Hypothesis property test in
    ``tests/unit/plugins/test_resolver_property.py`` proves this.
    """
    if not registry.all():
        raise PluginRegistryCorrupted(reason="empty_registry")

    candidates = _lift_candidates(registry.all())
    matches = _filter_matches(candidates, scope)

    if not matches:
        if _universal_registered(registry):
            return UniversalFallbackResolution(
                reason="no_concrete_match",
                candidates_considered=(),
            )
        raise PluginRegistryCorrupted(reason="missing_universal")

    sorted_matches = sorted(matches, key=_sort_key)
    head = sorted_matches[0]
    if head.plugin.manifest.name == UNIVERSAL_FALLBACK_ID:
        return UniversalFallbackResolution(
            reason="no_concrete_match",
            candidates_considered=_candidates_considered(registry),
        )

    composed = compose_extends_chain(head.plugin, registry)
    return composed.model_copy(update={"matched_scope": head.lifted_scope})


def _universal_registered(registry: PluginRegistry) -> bool:
    """True iff the canonical universal-fallback plugin is registered.

    Cheap membership check via ``registry.get``; the exception path
    when absent is the deliberate fall-through to
    :class:`PluginRegistryCorrupted`.
    """
    try:
        registry.get(UNIVERSAL_FALLBACK_ID)
    except PluginNotRegistered:
        return False
    return True
