"""Phase 3 plugin namespace — discovered by :func:`codegenie.plugins.loader.load_plugins`.

This empty marker exists so ``importlib.import_module("plugins.{slug}.api")``
resolves. Per-plugin trees ship as ``plugins/{slug}/`` siblings of this
file; the first concrete plugin lands in S7-01
(``vulnerability-remediation--node--npm``).

Discovery is filesystem-walk-based (``plugins/*/plugin.yaml``); this
package does **not** re-export concrete plugins or otherwise enumerate
them. Adding a plugin = a new sibling directory plus a row in
``plugins/PLUGINS.lock`` (ADR-0011).
"""
