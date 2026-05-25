# Cassette discipline — operator runbook

> Source-of-truth for cassette workflow: who owns cassettes, when to refresh
> them, how the discipline holds together, and what to do when CI flags a
> cassette problem. The four discipline layers below are documented end-to-end
> here; the *byte-level* contracts (sanitizer rules, `cassettes.lock` format)
> live in their respective source modules — this runbook links rather than
> restates them so the two specs cannot drift.

## What cassettes are and why we care

A *cassette* is a VCR-recorded HTTP request/response pair stored at
`tests/cassettes/anthropic/*.yaml`. Replaying cassettes is how Phase-4
LLM-fallback tests exercise the real `anthropic` SDK code path *deterministically
and tokenlessly* in CI. The discipline that protects that property is laid out
in [ADR-0014](../phases/04-vuln-llm-fallback-rag/ADRs/0014-cassette-discipline-security-control.md):
cassettes that leak secrets into the repo are a credential-exfiltration vector;
cassettes that quietly drift from the live API are a correctness vector.
Cassettes are useful *only if* both vectors are closed; the rest of this page
documents how.

## The four discipline layers

| Layer | Source | Purpose | Story |
|---|---|---|---|
| 1. **Sanitize at record** | [`src/codegenie/fallback/cassette/sanitizer.py`](../../src/codegenie/fallback/cassette/sanitizer.py) (`vcr_config` fixture wires the hooks in `tests/conftest.py`) | Strips `Authorization` / `X-API-Key` / `Cookie` / `Set-Cookie` / `anthropic-version` headers and scrubs `sk-ant-*` / `claude_*` body patterns *before* bytes hit disk. | S3-04 |
| 2. **CI security scanner** | [`tests/security/test_cassettes_clean.py`](../../tests/security/test_cassettes_clean.py) | Walks `tests/cassettes/` and fails CI on any leaked pattern (header, body, or shaped token). Backstop for layer 1. | S3-05 |
| 3. **Content-addressed manifest** | [`src/codegenie/fallback/cassette/manifest.py`](../../src/codegenie/fallback/cassette/manifest.py) — `tests/cassettes/anthropic/cassettes.lock` | Per-cassette BLAKE3 digest; CI rejects any cassette change that doesn't update the lock in the same commit. | S3-05 |
| 4. **Human ownership (this runbook)** | `.github/CODEOWNERS` + this file + `make refresh-cassettes` | Names the cassette-steward; documents refresh triggers; provides the explicit-acknowledgement operator path. | S3-06 |

The four layers are independent and load-bearing. Layer 1 is a sieve, not a
guarantee. Layer 2 is the assertion. Layer 3 is the audit log. Layer 4 is the
accountability — without a named human, the first three rot under SDK upgrades
([ADR-0014 §Gap analysis Gap 2](../phases/04-vuln-llm-fallback-rag/phase-arch-design.md)).

## Refresh triggers

There are exactly three sanctioned triggers for cassette refresh. Each has a
named role-owner. (Roles are stable; humans rotate — `.github/CODEOWNERS` is the
roster.)

- **(a) Nightly drift job flags a cassette.** The Phase-4 nightly job runs a
  representative case against the live Anthropic API with a budget-capped key
  and annotates drift on a tracking PR
  ([ADR-0005 §Decision item 3](../phases/04-vuln-llm-fallback-rag/ADRs/0005-no-spki-pin-egress-defense-in-depth.md)).
  → **Cassette-steward** investigates within 7 days. If the drift is real, refresh
  the affected cassettes per the workflow below.
- **(b) Anthropic SDK upgrade.** Any PR bumping the `anthropic` pin (or any
  transitive change that alters request/response shape) is responsible for
  re-recording affected cassettes *in the same PR*. → **PR author**.
- **(c) Prompt template change in `plugins/.../skills/`.** Changing a prompt
  body inevitably changes the request → the cassette must be re-recorded.
  → **PR author**.

Any refresh outside these three triggers should be questioned: cassettes are
the deterministic spine of the replay suite, and ad-hoc regeneration silently
masks real bugs.

## How to record a new cassette

The **only** sanctioned recording path is:

```sh
make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1
```

The `I_UNDERSTAND_THIS_SPENDS_TOKENS=1` make variable is the explicit
acknowledgement that recording will spend real Anthropic API tokens. Without
it, `make refresh-cassettes` exits with code 2 and prints the recovery
incantation.

(ADR-0014 §Decision item 6 writes this as a CLI flag `--i-understand-this-spends-tokens`;
`make` targets cannot accept `--flags`, so the same operator-acknowledgement
contract is rendered as a make variable. Both render the *intent* — an explicit,
command-line-visible acknowledgement — identically. The gate is intentional
friction, **not** an isolation boundary: `make` resolves environment variables
and command-line variables to `$(VAR)` identically, so exporting
`I_UNDERSTAND_THIS_SPENDS_TOKENS=1` in your shell satisfies the gate just as
the command-line form does. The command-line form is preferred for readability
in shell history.)

What the recipe does, in order:

1. Runs `pytest --record-mode=all -m "uses_anthropic_cassette"` with
   `CODEGENIE_LIVE_LLM=1`. The S3-04 `vcr_config` fixture intercepts and
   re-records the cassettes named by tests carrying that marker. Sanitizer
   hooks fire **during** recording — bytes on disk are already redacted.
2. Runs `python -m codegenie cassette rebuild-lockfile` so
   `tests/cassettes/anthropic/cassettes.lock` is regenerated alongside the new
   cassettes.
3. Reminds the operator to commit both the cassette YAML(s) and `cassettes.lock`
   together, and to request review from the current cassette-steward.

After the recording, every CODEOWNERS-gated cassette diff requires the
cassette-steward's approval before it can land (see the CODEOWNERS gate
section below).

## cassettes.lock format

Each line is `<relpath>  <blake3-hex>` — a POSIX relpath and a 64-character
lowercase hex BLAKE3 digest separated by two spaces. The full byte-level
specification (sort order, separator width, trailing newline, bootstrap-empty
shape, malformed-line rejection rules) is documented as the module docstring
of [`src/codegenie/fallback/cassette/manifest.py`](../../src/codegenie/fallback/cassette/manifest.py)
and pinned in the Phase-6.5-consumed stable-contracts list in
[`docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Stable contracts`](../phases/04-vuln-llm-fallback-rag/phase-arch-design.md).
This runbook documents *that* a format exists and *where the spec lives* — the
write path (`python -m codegenie cassette rebuild-lockfile`) is the single
source of truth, and two normative copies would drift.

## Sanitizer behaviour

What gets stripped from a cassette and why is the module docstring of
[`src/codegenie/fallback/cassette/sanitizer.py`](../../src/codegenie/fallback/cassette/sanitizer.py).
That module is the source of truth; restating its rules here would create a
drift hazard. Briefly: header allowlist (everything else stripped), body
pattern scan for `sk-ant-*` / `claude_*` / 40+-char base64-shaped values.
Failures surface as `Violation` records on `CassetteVerification`; the CI
scanner (layer 2) fails the build with those records.

## CODEOWNERS gate

`.github/CODEOWNERS` names a **single human** as the cassette-steward for these
three paths:

- `tests/cassettes/anthropic/` — the cassette directory itself.
- `tests/cassettes/anthropic/cassettes.lock` — the per-cassette BLAKE3 manifest.
- `docs/operations/cassettes.md` — this runbook.

Single-human ownership is load-bearing accountability: the steward is one
human, not a team, not an on-call alias substitute. Rotation happens
**quarterly** via this file's CODEOWNERS handle — the outgoing steward updates
the three `@handle` lines as part of handoff. Renewal mechanism: Phase 13.5
operator portal.

For the CODEOWNERS gate to bite, the repository's branch-protection rule must
include **"Require review from Code Owners"** on the default branch. That
setting is operator-administered (it requires GitHub repo admin), and this
runbook documents the requirement; the story that landed this runbook does
**not** depend on having admin access to flip the setting.

## Nightly drift job

The nightly drift job is a Phase-4 CI surface (per
[ADR-0005 §Consequences](../phases/04-vuln-llm-fallback-rag/ADRs/0005-no-spki-pin-egress-defense-in-depth.md)
and [ADR-0014 §Decision item 5](../phases/04-vuln-llm-fallback-rag/ADRs/0014-cassette-discipline-security-control.md)).
Its purpose is to detect drift between cassettes and the live API across four
dimensions:

- **TLS chain shape** (cert rotation against the pinned trust roots).
- **SDK request shape** (new headers / removed headers in the `anthropic` SDK).
- **API response shape** (Anthropic changes the response envelope without bumping
  the SDK).
- **Prompt-vs-response semantic drift** (model updates change response text
  for a fixed prompt).

The job runs against a representative bench case
(`fixtures/vuln-major-bump/express-cve-2026-1234/`) with a budget-capped CI key.
**The job is not workflow-blocking**: it annotates drift on a tracking PR
rather than failing main-branch CI. The recovery is operator-administered —
the cassette-steward investigates the annotation, decides if a refresh is
warranted (trigger (a)), and either refreshes or marks the annotation false-positive.

(The workflow YAML file (`.github/workflows/cassette-drift-nightly.yml`) is
landed by a separate Phase-4 CI-wiring story; this runbook documents the
job's *purpose* and *recovery semantics*, not its implementation.)

## Troubleshooting

Three CI-emitted diagnostics map to three named recovery paths:

### "Cassette miss — run `make refresh-cassettes`"

The test asked VCR to replay a cassette and VCR found none on disk that matched
the request. Either a test was added without a cassette, or a request shape
changed silently.

→ **Recovery:** `make refresh-cassettes I_UNDERSTAND_THIS_SPENDS_TOKENS=1`.
Review the diff, commit cassette + lock together, request review from the
cassette-steward.

### "Lock drift — `cassettes.lock` does not match disk"

The on-disk cassette bytes have changed without a corresponding update to
`cassettes.lock`. Most often this means someone hand-edited a cassette or
re-recorded without running `rebuild-lockfile`.

→ **Recovery:** `python -m codegenie cassette rebuild-lockfile` and commit
the updated lock alongside the cassette change.

### "Sanitizer violation — a secret pattern leaked into a cassette"

This *should* be impossible: the S3-04 sanitizer hooks fire during recording,
so secrets are stripped before bytes hit disk. Hitting this diagnostic in CI
means the hook didn't fire — most likely because the test did not request the
`vcr_config` fixture (or `tests/conftest.py`'s `vcr_config` was disabled
locally).

→ **Recovery:** Stop. Do **not** commit. Investigate why the sanitizer hook
didn't fire. Check `tests/conftest.py`'s `vcr_config` fixture is present and
the test recording the cassette is collecting it. If a real secret leaked,
rotate the key (Anthropic key rotation is the operator's responsibility) and
purge the cassette from git history.
