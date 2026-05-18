# ADR-0041: Model and prompt release qualification

**Status:** Accepted  
**Date:** 2026-05-18  
**Tags:** llm · release · reproducibility  
**Related:** ADR-0011, ADR-0015, ADR-0020

## Context

As soon as LLM fallback becomes production-relevant, behavior depends on both model identity and prompt template version. The design had no explicit release gate for changing either.

## Decision

Treat `(model_id, prompt_template_version, retrieval_config_version)` as a qualified release tuple. Any change requires benchmark evidence, cassette refresh discipline, and an explicit rollout record before becoming the default for a task class.

## Tradeoffs

| Gain | Cost |
|---|---|
| Makes regressions attributable and reproducible | Slows prompt iteration slightly |
| Aligns model changes with eval evidence | Adds one more version axis to audit records |

## Consequences

- `SutDigest` and future workflow audit records include the release tuple.
- Unqualified tuples may be tested, but not promoted to production defaults.
