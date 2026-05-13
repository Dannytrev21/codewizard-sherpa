"""``codegenie.config`` — Phase 0 four-source config loader.

Public surface:

- :class:`Config` — frozen dataclass with the three Phase 0 fields.
- :func:`load_config` — merges ``defaults < ~/.codegenie/config.yaml <
  <repo>/.codegenie/config.yaml < cli_overrides`` into a ``Config``.

See ``docs/phases/00-bullet-tracer-foundations/stories/S3-04-config-loader.md``
for the full contract.
"""

from .defaults import Config
from .loader import load_config

__all__ = ["Config", "load_config"]
