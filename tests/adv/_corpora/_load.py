"""Phase-4 S7-09 AC-11 — corpus-loader kernel.

Single :func:`load_corpus` entry point backed by the typed Pydantic
models from :mod:`._models`. Rule-of-three reached at S7-09 (three
corpus types: injection, red-team, truncation). Open/Closed at the
file boundary: adding a new corpus YAML + a new model in
:mod:`._models` requires **zero edits** to existing corpus-loading
test bodies — they all read through this kernel.

The ``name`` argument is a closed ``Literal`` discriminator;
``_MODEL_DISPATCH`` is a ``Final[dict]`` of data, not branches —
mirrors the codebase's registry pattern (see Phase-1 ``@register_*``
decorators).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Literal, cast

import yaml
from pydantic import BaseModel, TypeAdapter

from tests.adv._corpora._models import (
    InjectionPayload,
    RedTeamScenario,
    TruncationProbe,
)

CorpusName = Literal["injection_payloads", "red_team_scenarios", "truncation_probes"]


_MODEL_DISPATCH: Final[dict[CorpusName, type[BaseModel]]] = {
    "injection_payloads": InjectionPayload,
    "red_team_scenarios": RedTeamScenario,
    "truncation_probes": TruncationProbe,
}


_CORPORA_DIR: Final[Path] = Path(__file__).parent


def _corpus_path(name: CorpusName) -> Path:
    """Return the YAML path for ``name`` — colocated with this module."""
    return _CORPORA_DIR / f"{name}.yaml"


def load_corpus(name: CorpusName) -> list[BaseModel]:
    """Load + typed-validate a corpus YAML.

    Returns a ``list`` of the appropriate frozen Pydantic model. A
    corrupt YAML row (missing field, unknown extra key, wrong type)
    raises :class:`pydantic.ValidationError` at load time — never a
    ``KeyError`` mid-test.

    Empty / missing corpus file returns an empty list. The
    corpus-size meta-test (AC-9) is the gate that rejects the empty
    case — it lives at the **test** layer, not here, so a future
    corpus-loader-only smoke test doesn't double-fail on size.
    """
    model = _MODEL_DISPATCH[name]
    path = _corpus_path(name)
    if not path.exists():
        return []
    raw_text = path.read_text()
    if not raw_text.strip():
        return []
    raw = yaml.safe_load(raw_text)
    if raw is None:
        return []
    # ``cast`` the runtime type because Pydantic's TypeAdapter generic
    # binding doesn't narrow through the dispatch dict at static time.
    adapter: TypeAdapter[list[BaseModel]] = TypeAdapter(list[model])  # type: ignore[valid-type]
    return cast(list[BaseModel], adapter.validate_python(raw))


__all__ = [
    "CorpusName",
    "load_corpus",
]
