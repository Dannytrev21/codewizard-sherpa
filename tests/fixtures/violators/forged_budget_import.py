# This file is a deliberate test fixture; not imported by production code.
# It exists so the import-linter positive control in
# ``tests/fence/test_budget_token_scope.py`` has a known violator — any non-
# test code performing this import outside the three sanctioned frames
# (``codegenie.fallback.budget``, ``codegenie.fallback.tier``,
# ``codegenie.fallback.leaf.anthropic_adapter``) breaks the two-frame
# capability scope (Phase-4 ADR-0010).
from codegenie.fallback.budget_token import BudgetToken

_ = BudgetToken
