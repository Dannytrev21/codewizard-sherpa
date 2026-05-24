# This file is a deliberate test fixture; not imported by production code.
# It exists so the AST-walking sole-mint test in
# ``tests/unit/fallback/test_prompt_builder_sole_mint_site.py`` has a known
# positive control — a forged ``TrustedPrompt`` minter the visitor must flag.
from codegenie.fallback.fence.prompt_builder import TrustedPrompt

_ = TrustedPrompt("evil")
