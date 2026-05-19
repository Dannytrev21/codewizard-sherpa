"""Fence test package — every fence here is **audit + lint** enforcement,
NOT a runtime guarantee (ADR-0011 framing).

Each fence file pins one structural property of the Phase 3 contract surface;
the canonical catalogue lives below so the documentation seam stays close to
the code (Rule 8). Adding a fence = new module here + one row in the
catalogue. There is intentionally no ``FenceRule`` ABC — the planned fences
share *category* (CI gate, source-of-truth = ``src/``) but not *input/output
shape* (git-diff vs. AST walk vs. JSON snapshot vs. ruff custom rule),
so a forced Protocol would degrade each (Rule 2).

Catalogue (one line per fence, owning ADR named):

* ``test_phase3_importlinter_contracts_shape.py`` — P3-ADR-0010 +
  P3-ADR-0011: pins the shape (forbidden modules, ``as_packages``, sources)
  of the two Phase 3 import-linter contracts in ``pyproject.toml``.
* ``test_lint_imports_catches_planted_leak.py`` — P3-ADR-0010: subprocess
  test proves ``lint-imports`` actually fires on an injected LLM-SDK leak.
* ``test_fence_target_wiring.py`` — P3-ADR-0011: pins the ``Makefile``
  ``fence:`` recipe to invoke the full Phase 3 fence set, not just the
  Phase 0 scan.
* ``test_no_llm_in_transforms.py`` — P3-ADR-0010 (runtime-closure scan
  for ``FORBIDDEN_LLM_SDKS`` under ``codegenie.{plugins,transforms}``).
* ``test_no_any_in_plugin_surface.py`` — P3-ADR-0010 + P3-ADR-0011
  (AST-walk for ``Any`` / ``dict[str, Any]`` annotations).
* ``test_kernel_frozen.py`` — P3-ADR-0011 (git-diff Phase 0/1/2 file list
  against an ADR-anchored allowlist).
* ``test_transforms_module_purity.py`` — S1-04 (per-module import allowlist
  for ``transforms/_forward.py``, ``transform.py``, ``apply_context.py``).
"""
