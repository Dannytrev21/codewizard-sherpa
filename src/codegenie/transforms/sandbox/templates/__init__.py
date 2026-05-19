"""Packaged static profile templates for :mod:`codegenie.transforms.sandbox`.

Sub-package exists solely so that
``importlib.resources.files("codegenie.transforms.sandbox.templates")``
resolves at runtime; module body is intentionally empty (ADR-0011 — packaged
static asset surface, not a code surface).
"""
