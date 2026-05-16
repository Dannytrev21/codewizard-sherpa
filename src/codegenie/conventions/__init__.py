"""``codegenie.conventions`` — kernel-side conventions catalog loader (Phase 2 S2-02).

Loads YAML conventions catalogs from ``~/.codegenie/conventions/`` and
``.codegenie/conventions/`` through the :mod:`codegenie.parsers.safe_yaml`
chokepoint. Validates each rule against a Pydantic discriminated union over
four pattern types (``dockerfile_pattern``, ``dockerfile_pattern_inverted``,
``file_pattern``, ``missing_file``). Applies a loaded :class:`Catalog`
against a :class:`~codegenie.probes.base.RepoSnapshot` to produce one
:class:`Pass` / :class:`Fail` / :class:`NotApplicable` per rule.

02-ADR-0007 keeps Phase 2 kernel-only — no plugin loader yet. Phase 4+
``Catalog`` consumers (the Layer-D :class:`ConventionsProbe`, the Layer-E
``Ownership`` / ``ServiceTopologyStub`` / ``SloStub`` stubs) read this
surface.
"""

from codegenie.conventions.catalog import Catalog
from codegenie.conventions.loader import (
    CatalogFileUnreadable,
    CatalogLoadOutcome,
    ConventionsCatalogLoader,
    ConventionsError,
    DepthCapExceeded,
    FatalLoadError,
    SchemaError,
    SizeCapExceeded,
    SymlinkRefused,
    UnknownPatternType,
    UnsafeYaml,
)
from codegenie.conventions.model import (
    ConventionResult,
    ConventionRule,
    ConventionRuleDockerfilePattern,
    ConventionRuleDockerfilePatternInverted,
    ConventionRuleFilePattern,
    ConventionRuleMissingFile,
    Fail,
    NotApplicable,
    Pass,
)

__all__ = [
    "Catalog",
    "CatalogFileUnreadable",
    "CatalogLoadOutcome",
    "ConventionRule",
    "ConventionRuleDockerfilePattern",
    "ConventionRuleDockerfilePatternInverted",
    "ConventionRuleFilePattern",
    "ConventionRuleMissingFile",
    "ConventionResult",
    "ConventionsCatalogLoader",
    "ConventionsError",
    "DepthCapExceeded",
    "Fail",
    "FatalLoadError",
    "NotApplicable",
    "Pass",
    "SchemaError",
    "SizeCapExceeded",
    "SymlinkRefused",
    "UnknownPatternType",
    "UnsafeYaml",
]
