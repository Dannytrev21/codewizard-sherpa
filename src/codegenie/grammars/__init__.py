"""``codegenie.grammars`` — typed boundary for tree-sitter grammar loading.

Per 02-ADR-0011, grammars are sourced from PyPI wheels
(``tree-sitter-typescript``, ``tree-sitter-javascript``, future
``tree-sitter-python`` / ``tree-sitter-java``). The kernel
(:mod:`codegenie.grammars.lock`) exposes
:func:`~codegenie.grammars.lock.language_for` so probes never import
the per-grammar PyPI package directly; the indirection is the
Ports-&-Adapters seam that keeps the consumer surface stable when
Phase 8+ adds new languages.

The legacy ``tools/grammars.lock`` BLAKE3-of-binary model from
02-ADR-0002 has been removed; supply-chain pinning is now
``pip --require-hashes`` against the wheel SHA256 (Phase 0 ADR-0006).
"""

__all__: list[str] = []
