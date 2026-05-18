# Fixture — `secret_in_source`

Load-bearing adversarial fixture for Phase 2 S6-07
(`tests/adv/phase02/test_secret_in_source.py`).

This repository contains two deliberate occurrences of a fake AWS Access
Key ID of the form `AKIA<sixteen-uppercase-alphanumerics>`:

- `src/config.ts` — source-code occurrence (gitleaks rule-pack target).
- `docs/internal-notes.md` — prose occurrence (entropy-fallback / regex
  sweep target in `SecretRedactor`).

Do **NOT** "fix" either file — the test depends on the seed being
present. The literal seed is intentionally absent from this README so
that gitleaks' working-tree scan does not contaminate the fixture with a
third finding.

If a future contributor "rotates" the literal seed pattern, every
fingerprint downstream of the redactor changes too — update the test's
expected fingerprint to match.
