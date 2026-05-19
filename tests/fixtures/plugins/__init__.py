"""Test fixture package — minimal stand-ins for the Phase 3 Plugin contract.

Owns ``make_fake_plugin``, the single boundary lift from raw ``str`` to
:data:`codegenie.types.identifiers.PluginId`. Production code never imports
from this package.
"""
