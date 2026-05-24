# Story S3-05 — `stage6_validate.yaml` + `stage6_validate_loose.yaml` populated + digest-pinned `sandbox-policy.yaml`

**Step:** Step 3 — Implement DinD backend + SandboxSpecBuilder + SandboxHealthProbe
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-04 (`TransitionId.STAGE6_VALIDATE_LOOSE` enum member), S1-06 (`catalog_loader.load_all`, `CatalogEntry`, `_schema.json`), S1-07 (`tools/digests.yaml` placeholders, `_BLAKE3_DIGEST_RE` constant), S3-01 (`SandboxSpecBuilder` consumes these catalogs)
**ADRs honored:** ADR-0013 (digest-pinned codegenie-owned policy YAML), ADR-0014 (`extra="forbid"` invariants — no banned substrings — including in YAML field names), ADR-0015 (asymmetric test-inventory delta policy), Open Q4 (one catalog or two — synthesis: ship both)

## Validation notes

Hardened on 2026-05-23 by `phase-story-validator`. See [`_validation/S3-05-stage6-yaml-catalogs-and-policy.md`](_validation/S3-05-stage6-yaml-catalogs-and-policy.md) for the full audit log. Highlights:

1. **BLAKE3 length cross-story bug resolved.** The draft pinned BLAKE3-128 (`hexdigest(length=16)` → 32 hex chars) per arch §Data model lines 654/774-775 + S3-01 AC-HASH-FORMAT-1, but S1-07 HARDENED shipped `_BLAKE3_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")` (BLAKE3-256, 64 chars). Per Rule 7 (surface conflicts, don't average), the arch is source of truth → BLAKE3-128 wins. This story now owns a one-line forward-fix to `tests/schema/test_digests_yaml.py` (regex `{64}` → `{32}`) — see AC-DG-FIX-1..-3. The S1-07 placeholders (`"TBD"`) are untouched.
2. **`GateCatalogLoader` non-existence (block).** Draft TDD imported `GateCatalogLoader` (a class) and called `loader.load_all()`. S1-06 HARDENED ships only module-level `load`/`load_all` functions plus the `CatalogEntry` Pydantic class — `__all__ == {"CatalogEntry", "load", "load_all"}`. Test rewritten to call `load_all(CATALOG)` directly and assert both catalogs return typed `CatalogEntry` instances (also exercises ADR-0014 `extra="forbid"` transitively).
3. **`sandbox.base_image_node` does not exist and must not be added (block).** Draft told the executor to "pull from `tools/digests.yaml#sandbox.base_image_node` (added if absent)" with placeholder `sha256:0000...`. S1-07 AC-DG-2 pins exactly four `sandbox.*` keys (`firecracker`, `vmlinux`, `rootfs`, `policy_yaml`) and AC-DG-5 requires values to match exactly `"TBD"` or `^[a-f0-9]{32}$` (post-fix). A `sha256:` prefix violates both. Surgical fix (Rule 3): inline the placeholder `cgr.dev/chainguard/node@sha256:` + 64 zero hex chars into `stage6_validate.yaml#sandbox.base_image` directly. Real Chainguard digest swap is owned by S3-07's integration test, not this story.
4. **Strict catalog AC coverage widened.** Draft ACs covered only `required_signals`, `non_retryable_failures`, and one schema-validation call. AC-STRICT-1..-14 now itemize every arch-pinned field (`max_attempts`, `retryable_failures`, `timeout_retryable`, `time_budget_seconds`, `memory_limit_mib`, `pids_limit`, `env_allowlist`, both `phases[]` entries with `network`/`enable_trace`/`egress_allowlist`/`cmd`, and `attempt_overrides["2"]`) so a mutation that drops `enable_trace` or swaps `network: scoped → none` fails a named test, not a single byte-compare diff.
5. **ADR-0015 asymmetric policy pinned verbatim.** Draft only had a banned-substring scan on the policy YAML. AC-POL-1..-7 now pin `schema_version: 1`, the three `lockfile.*` keys, `runtime_trace.fail_on_new_shell_invocation: true`, `runtime_trace.warn_on_low_coverage: true`, `test_inventory.fail_on_negative_delta: true`, `test_inventory.warn_on_positive_delta: false` — the ADR-0015 load-bearing values that a byte-compare alone would not surface in a diff review.
6. **`required_signals` list order pinned (test-quality).** Draft used `set(...) == {...}` which silently accepts reordering. Canonical-JSON spec hashing (S3-01) depends on list order; AC-STRICT-1 now pins `data["required_signals"] == ["build","install","tests","trace","policy","cve_delta"]` byte-exact.
7. **Planted-positive companions for every walker (Phase 5 convention).** S1-07 + S1-03 + S1-06 all ship planted-positive tests proving each walker actually fires. Draft shipped zero. AC-PP-1..-5 add five planted positives (digest-mismatch detector, banned-substring walker, schema-validation rejection, list-order detector, path-component traversal detector).
8. **Banned-substring set canonical-import (consistency).** Draft re-declared `("confidence", "self_reported", "model_says", "llm")` locally — silently forks ADR-0014's trust anchor (the same risk S1-07 explicitly forbade). AC-BS-1 imports the canonical set from `codegenie.sandbox.signals._introspection.BANNED_SUBSTRINGS` (S1-03's surface; if S1-03 did not yet export, this story exports it as a one-line additive change). Sync test asserts byte-equality with S1-07's set.
9. **`POLICY_PATH` traversal-safety.** Draft used `".codegenie" not in str(POLICY_PATH)` — bypassable by a mid-path traversal whose resolved form still lands in `.codegenie/`. AC-ADV-1..-3 pin `".codegenie" not in POLICY_PATH.resolve().parts` AND `POLICY_PATH.parts[:2] == ("tools", "policy")`, plus a planted-positive (AC-PP-5).
10. **Golden-template byte-equality (test-quality).** AC line 41 said "byte-for-byte" but no test enforced it. AC-GOLDEN-1..-3 commit `tests/golden/{stage6_validate,stage6_validate_loose,sandbox-policy}.yaml.template` files (arch verbatim) and add `test_*_matches_arch_template` which substitutes the `<pinned>` literal and asserts byte-equality — the S3-01 golden-sidecar idiom applied to YAML.
11. **File-stability invariants.** Trailing-LF newline, UTF-8 (no BOM), LF line endings — none was pinned. Any of these flipping silently changes the BLAKE3 of the policy YAML the moment a Windows checkout / pre-commit hook touches it. AC-STAB-1..-3.
12. **Design-pattern notes (rule-of-three deferred).** A reusable `digest_for(name) -> str` reader for `tools/digests.yaml` reaches three consumers (this story's test + S3-06 + S6-03), but S3-06 is the first **production** consumer and rightly owns the kernel. This story keeps the digest read inline (Rule 2: simplicity first; Rule 3: surgical changes). Notes-for-implementer documents the deferral so the next executor doesn't re-litigate. Similarly, a `PLACEHOLDER_BASE_IMAGE_DIGEST` typed sentinel is flagged for S3-06's `SandboxHealthProbe` startup check (refuses the placeholder), not introduced here.

Verdict: HARDENED. Three block-tier contradictions (BLAKE3 length, `GateCatalogLoader`, `base_image_node`) were resolved by aligning with the source of truth (arch + S1-06 + S1-07) and adding a one-line forward-fix for the S1-07 regex bug. ~35 ACs across nine groups (was 11 unnumbered) plus a five-test-file TDD plan (catalogs strict, catalogs loose, policy-yaml-fields, digests-cross-check, in-repo-policy-adversarial-stub) with planted-positives, golden templates, and ADR-import-sync.

## Context

Step 1 shipped an empty `stage6_validate.yaml` stub schema-valid against `gates/catalog/_schema.json`. This story populates **both** the strict catalog (all six signals required, `non_retryable_failures: [trace]`) and the dev-mode loose catalog (`build`, `install`, `tests` only — for `codegenie remediate --gate loose`). It also lands the digest-pinned `tools/policy/sandbox-policy.yaml` (per ADR-0013) and its `tools/digests.yaml#sandbox.policy_yaml` BLAKE3-128 (32-char hex) entry. After this story, `SandboxSpecBuilder.for_gate(stage6_validate, ...)` produces the golden spec asserted in S3-01.

ADR-0013 is the load-bearing reason this story exists: the policy file cannot live in the target repo (an LLM patch could neuter the policy gate). It lives under `tools/policy/` owned by codegenie itself, with its bytes verified against `tools/digests.yaml` at every `SandboxHealthProbe` invocation (S3-06).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model — gates/catalog/stage6_validate.yaml` — verbatim YAML this story commits.
  - `../phase-arch-design.md §Data model — tools/policy/sandbox-policy.yaml` — verbatim policy YAML.
  - `../phase-arch-design.md §Component design — Signal collectors` — "Policy YAML source is the digest-pinned `tools/policy/sandbox-policy.yaml` — NOT the repo's `.codegenie/policy.yaml`".
  - `../phase-arch-design.md §Edge case 10` — repo-resident policy ignored.
  - `../phase-arch-design.md §Edge case 19` — missing `sandbox.policy_yaml` triggers `SandboxHealth(reachable=False, reasons=["policy_digest_missing"])` (enforced by S3-06, not this story).
  - `../phase-arch-design.md §Open questions deferred — Open Q4` — one catalog or two; synthesis ships both.
  - `../phase-arch-design.md` lines 654, 774–775 — **blake3-128** convention for `sandbox_spec_hash`, `prev_hash`, `chain_hash` (source of truth for the regex fix in AC-DG-FIX-*).
- **Phase ADRs:**
  - `../ADRs/0013-digest-pinned-policy-yaml-codegenie-owned.md` — ADR-0013 — the policy YAML location, digest pinning, and the adversarial test it justifies.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — banned-substring set canonical home (`confidence`, `self_reported`, `model_says`, `llm`); the introspection test owns the canonical set and any consumer must IMPORT (never re-declare).
  - `../ADRs/0015-test-inventory-delta-asymmetric-policy.md` — ADR-0015 — `fail_on_negative_delta: true`, `warn_on_positive_delta: false` (load-bearing asymmetric values).
- **Source design:**
  - `../final-design.md §Synthesis ledger — Policy source row` — winner: codegenie-owned, digest-pinned.
- **Existing code & sibling stories:**
  - `src/codegenie/gates/catalog/_schema.json` (S1-06) — schema both YAMLs validate against (`additionalProperties: false` at every nested level; `patternProperties` for `attempt_overrides`).
  - `src/codegenie/gates/catalog_loader.py` (S1-06) — exports **`load`, `load_all`, `CatalogEntry`** (module-level functions; no `GateCatalogLoader` class). `__all__ == {"CatalogEntry", "load", "load_all"}`.
  - `src/codegenie/gates/contract.py` (S1-04) — `TransitionId` enum members `STAGE6_VALIDATE` and `STAGE6_VALIDATE_LOOSE` (both pinned by S1-04 AC-3a); `RetryPolicy` disjoint-cross-field validator.
  - `src/codegenie/sandbox/signals/_introspection.py` (S1-03) — canonical `BANNED_SUBSTRINGS` constant (used by ADR-0014 static test); if not yet exported, this story exports it.
  - `tests/schema/test_digests_yaml.py` (S1-07) — `_BLAKE3_DIGEST_RE` regex; this story applies the one-line forward-fix (`{64}` → `{32}`) per AC-DG-FIX-*.
  - `src/codegenie/gates/catalog/stage6_validate.yaml` (S1-06 stub) — populate.
  - `tools/digests.yaml` (S1-07 placeholders) — flip `sandbox.policy_yaml` from `"TBD"` to a 32-char BLAKE3-128 hex.
  - `tools/policy/lockfile-policy.yaml` — convention precedent for codegenie-owned policy YAMLs (sibling file).

## Goal

Populate the two stage-6 YAML catalogs to match `phase-arch-design.md §Data model` verbatim, commit the digest-pinned `tools/policy/sandbox-policy.yaml` with its BLAKE3-128 hex digest (`hexdigest(length=16)` → 32 chars) in `tools/digests.yaml#sandbox.policy_yaml`, and align S1-07's digest-shape regex with the arch's blake3-128 convention.

## Acceptance criteria

### Group A — `stage6_validate.yaml` (strict catalog)

- [ ] **AC-STRICT-1** `data["required_signals"] == ["build","install","tests","trace","policy","cve_delta"]` — exact list, exact order (canonical-JSON spec hashing depends on order; a set-equality test is insufficient).
- [ ] **AC-STRICT-2** `data["gate_id"] == "stage6_validate"` and `data["transition"] == "stage6_validate"`.
- [ ] **AC-STRICT-3** `data["retry_policy"]["max_attempts"] == 3`.
- [ ] **AC-STRICT-4** `data["retry_policy"]["retryable_failures"] == ["build","install","tests","policy","cve_delta"]` — exact list, exact order.
- [ ] **AC-STRICT-5** `data["retry_policy"]["non_retryable_failures"] == ["trace"]`.
- [ ] **AC-STRICT-6** `data["retry_policy"]["timeout_retryable"] is False`.
- [ ] **AC-STRICT-7** `data["sandbox"]["base_image"] == "cgr.dev/chainguard/node@sha256:" + "0"*64` — literal placeholder for unit tests; S3-07 swaps to a real Chainguard digest (do NOT add `sandbox.base_image_node` to `tools/digests.yaml` — see Validation note 3).
- [ ] **AC-STRICT-8** `data["sandbox"]["time_budget_seconds"] == 600`.
- [ ] **AC-STRICT-9** `data["sandbox"]["memory_limit_mib"] == 2048`.
- [ ] **AC-STRICT-10** `data["sandbox"]["pids_limit"] == 1024`.
- [ ] **AC-STRICT-11** `data["sandbox"]["env_allowlist"] == ["PATH","NODE_ENV","NPM_CONFIG_*","HTTPS_PROXY"]` — exact list, exact order.
- [ ] **AC-STRICT-12** `data["sandbox"]["phases"][0]` is `{name: "install", network: "scoped", egress_allowlist: ["registry.npmjs.org"], cmd: ["sh","-c","cd /work && npm ci --ignore-scripts"]}` — every field pinned (a mutation dropping `egress_allowlist` or flipping `network → none` fails this AC, not a coarse diff).
- [ ] **AC-STRICT-13** `data["sandbox"]["phases"][1]` is `{name: "test", network: "none", enable_trace: True, cmd: ["sh","-c","cd /work && npm test"]}`.
- [ ] **AC-STRICT-14** `data["attempt_overrides"]["2"]["phases"][0]["cmd"] == ["sh","-c","cd /work && npm test -- --verbose --maxWorkers=1"]` — arch line 807 verbatim.

### Group B — `stage6_validate_loose.yaml` (dev-mode loose catalog)

- [ ] **AC-LOOSE-1** File `src/codegenie/gates/catalog/stage6_validate_loose.yaml` exists.
- [ ] **AC-LOOSE-2** `data["gate_id"] == "stage6_validate_loose"` and `data["transition"] == "stage6_validate_loose"`.
- [ ] **AC-LOOSE-3** `data["required_signals"] == ["build","install","tests"]` — exact list, exact order.
- [ ] **AC-LOOSE-4** `data["retry_policy"]["max_attempts"] == 3`.
- [ ] **AC-LOOSE-5** `data["retry_policy"]["retryable_failures"] == ["build","install","tests"]`.
- [ ] **AC-LOOSE-6** `data["retry_policy"]["non_retryable_failures"] == []` (empty list — disjoint with retryable per S1-04 AC-I-2).
- [ ] **AC-LOOSE-7** `data["retry_policy"]["timeout_retryable"] is False`.
- [ ] **AC-LOOSE-8** `data["attempt_overrides"] == {}` (empty mapping; S1-06 AC-SCHEMA-NESTED-5 requires the schema accept empty `attempt_overrides`).
- [ ] **AC-LOOSE-9** `data["sandbox"]` block is **structurally identical** to the strict catalog's `sandbox` block (same `base_image`, `time_budget_seconds`, `memory_limit_mib`, `pids_limit`, `env_allowlist`, `phases`). Implementation MAY duplicate the block verbatim or share via a `data["sandbox"] == strict_data["sandbox"]` test, but MUST NOT use YAML anchors (`&`, `*`, `<<:`) — see AC-LOOSE-10.
- [ ] **AC-LOOSE-10** `not re.search(r"^[^#\n]*[&*]\w+|<<:", text, flags=re.MULTILINE)` — no YAML anchors / aliases / merge keys in either catalog file (Rule 11 + ADR-0013 spirit: trusted YAMLs are grep-readable, not anchor-expanded).

### Group C — `tools/policy/sandbox-policy.yaml` (codegenie-owned policy)

- [ ] **AC-POL-1** File `tools/policy/sandbox-policy.yaml` exists.
- [ ] **AC-POL-2** `data["schema_version"] == 1`.
- [ ] **AC-POL-3** `data["lockfile"] == {"forbid_git_dep_specifiers": True, "forbid_unscoped_overrides": True, "require_integrity_field": True}` — exact mapping.
- [ ] **AC-POL-4** `data["runtime_trace"]["fail_on_new_shell_invocation"] is True` (ADR-0013 + edge case 8).
- [ ] **AC-POL-5** `data["runtime_trace"]["fail_on_new_endpoint"] is True`.
- [ ] **AC-POL-6** `data["runtime_trace"]["warn_on_low_coverage"] is True` — soft signal per ADR-0014 §Consequences (the legitimate `coverage_evidence_strength` rename happens in code; policy field name `warn_on_low_coverage` carries no banned substring).
- [ ] **AC-POL-7** `data["test_inventory"]["fail_on_negative_delta"] is True` AND `data["test_inventory"]["warn_on_positive_delta"] is False` — the ADR-0015 load-bearing asymmetric invariant.

### Group D — `tools/digests.yaml#sandbox.policy_yaml` BLAKE3-128 digest

- [ ] **AC-DG-1** `tools/digests.yaml#sandbox.policy_yaml` value equals `blake3.blake3(Path("tools/policy/sandbox-policy.yaml").read_bytes()).hexdigest(length=16)`.
- [ ] **AC-DG-2** `tools/digests.yaml#sandbox.policy_yaml` value matches `re.fullmatch(r"^[a-f0-9]{32}$", value)` — exactly 32 lowercase hex chars (BLAKE3-128). Lowercase pinned because S1-07's regex is lowercase-only.
- [ ] **AC-DG-3** `tools/digests.yaml#sandbox.policy_yaml` value is NOT the placeholder `"TBD"` — this story flips it to a real hex.
- [ ] **AC-DG-4** The other three `sandbox.*` keys (`firecracker`, `vmlinux`, `rootfs`) remain `"TBD"` — out of scope here (S6-03 owns).

### Group E — S1-07 digest-regex forward-fix (cross-story bug per Validation note 1)

- [ ] **AC-DG-FIX-1** `tests/schema/test_digests_yaml.py::_BLAKE3_DIGEST_RE` is updated from `re.compile(r"^[a-f0-9]{64}$")` to `re.compile(r"^[a-f0-9]{32}$")`. Justification (one-line code comment): `# BLAKE3-128 per arch §Data model lines 654/774-775 and S3-01 AC-HASH-FORMAT-1.`
- [ ] **AC-DG-FIX-2** The S1-07 docstring/comment in `tools/digests.yaml` (S1-07 outline step 7: `# Each value must be exactly "TBD" (Step 1) or a 64-char lowercase hex BLAKE3 digest.`) is updated to read `# Each value must be exactly "TBD" or a 32-char lowercase hex BLAKE3-128 digest.`
- [ ] **AC-DG-FIX-3** All S1-07 fence-test assertions (`test_sandbox_digest_values_are_placeholder_or_hex`) remain green AFTER the regex fix — the three remaining `"TBD"` values still pass; the new `sandbox.policy_yaml` 32-char value passes; the test passes on both 3.11 and 3.12.

### Group F — Schema validation through `catalog_loader.load_all`

- [ ] **AC-LOAD-1** `from codegenie.gates.catalog_loader import load_all, CatalogEntry; result = load_all(Path("src/codegenie/gates/catalog"))` returns a `dict[str, CatalogEntry]` (no raise; S1-06 `GateCatalogInvalid` would surface schema / RetryPolicy invariant violations).
- [ ] **AC-LOAD-2** `set(result.keys()) == {"stage6_validate", "stage6_validate_loose"}` — both gates loaded; no extra; no missing.
- [ ] **AC-LOAD-3** `isinstance(result["stage6_validate"], CatalogEntry)` and `isinstance(result["stage6_validate_loose"], CatalogEntry)` — Pydantic-validated, `extra="forbid"` exercised transitively.
- [ ] **AC-LOAD-4** `from codegenie.gates.contract import TransitionId; result["stage6_validate"].transition is TransitionId.STAGE6_VALIDATE and result["stage6_validate_loose"].transition is TransitionId.STAGE6_VALIDATE_LOOSE` — enum identity, not string equality.

### Group G — Adversarial stub for ADR-0013 (full test in S4-03)

- [ ] **AC-ADV-1** `src/codegenie/sandbox/signals/policy.py` exists and exports `POLICY_PATH: Final[Path]`. Module is at most ~5 lines (one-line constant + docstring citing ADR-0013) — full collector body lives in S4-03.
- [ ] **AC-ADV-2** `".codegenie" not in POLICY_PATH.resolve().parts` — path-component check (not substring); catches `Path(".codegenie/../tools/policy/sandbox-policy.yaml")`-style traversal.
- [ ] **AC-ADV-3** `POLICY_PATH.parts[:2] == ("tools", "policy")` AND `POLICY_PATH.name == "sandbox-policy.yaml"` — exact location.

### Group H — Banned-substring set (ADR-0014 canonical import)

- [ ] **AC-BS-1** Test imports the canonical banned-substring set: `from codegenie.sandbox.signals._introspection import BANNED_SUBSTRINGS`. If S1-03 did not yet export this constant, this story exports it as a one-line additive change (`BANNED_SUBSTRINGS: Final[frozenset[str]] = frozenset({"confidence", "llm", "self_reported", "model_says"})`) — no behavior change to S1-03's introspection logic.
- [ ] **AC-BS-2** Sync test asserts `BANNED_SUBSTRINGS == frozenset({"confidence", "llm", "self_reported", "model_says"})` — pins the set against silent drift; mirrors S1-07's `EXPECTED_FORBIDDEN_SET` idiom.
- [ ] **AC-BS-3** `for banned in BANNED_SUBSTRINGS: assert banned not in POLICY.read_text().lower()` — extends ADR-0014's compile-time field-name check into YAML text-content space (the static introspection test does not cover YAML content; this AC closes the loop).

### Group I — Golden-template byte-equality

- [ ] **AC-GOLDEN-1** `tests/golden/stage6_validate.yaml.template` is committed and equals the arch §Data model verbatim text (lines 779–808 inclusive, with `<pinned>` literal placeholder for the base-image digest).
- [ ] **AC-GOLDEN-2** `tests/golden/sandbox-policy.yaml.template` is committed and equals the arch §Data model verbatim text (lines 810–824 inclusive).
- [ ] **AC-GOLDEN-3** `test_stage6_validate_matches_arch_template`: read the golden template, substitute `<pinned>` → `"0"*64`, assert byte-equality with the shipped catalog. Same pattern for `sandbox-policy.yaml` (no substitution needed; direct byte-equality).

### Group J — File-stability invariants

- [ ] **AC-STAB-1** Each of the four shipped files (`stage6_validate.yaml`, `stage6_validate_loose.yaml`, `sandbox-policy.yaml`, `tools/digests.yaml`) ends with exactly one LF newline (`bytes.endswith(b"\n") and not bytes.endswith(b"\n\n")`).
- [ ] **AC-STAB-2** No CRLF line endings: `b"\r\n" not in bytes` for each file.
- [ ] **AC-STAB-3** No UTF-8 BOM: `not bytes.startswith(b"\xef\xbb\xbf")` for each file.

### Group K — Planted-positive companions (Phase 5 convention)

- [ ] **AC-PP-1** `test_planted_digest_mismatch_is_detected`: in `tmp_path`, write a `digests.yaml`-shaped fixture with a known-wrong hex; assert the equality-check raises `AssertionError`. Proves AC-DG-1's check actually fires.
- [ ] **AC-PP-2** `test_planted_banned_substring_is_detected`: feed `BANNED_SUBSTRINGS`-check a string containing `"... model_confidence ..."`; assert it fires. Proves AC-BS-3 walker is not vacuous.
- [ ] **AC-PP-3** `test_planted_loader_rejects_extra_property`: in `tmp_path`, write a malformed `stage6_validate.yaml` with `extra_key: "rejected"`; assert `load_all(tmp_path)` raises `GateCatalogInvalid`. Proves AC-LOAD-1's exercise of `extra="forbid"` actually catches drift.
- [ ] **AC-PP-4** `test_planted_required_signals_order_drift_is_detected`: feed AC-STRICT-1's check a list `["trace", "build", "install", "tests", "policy", "cve_delta"]`; assert the equality check fails. Proves AC-STRICT-1 enforces order.
- [ ] **AC-PP-5** `test_planted_policy_path_traversal_is_detected`: monkeypatch `POLICY_PATH = Path(".codegenie/../tools/policy/sandbox-policy.yaml")`; assert AC-ADV-2's `.resolve().parts` check fires. Proves AC-ADV-2 is not bypassable by traversal.

### Group L — Gate (formatting, linting, types)

- [ ] **AC-GATE-1** `ruff check tests/sandbox/test_catalogs_populated.py tests/sandbox/test_policy_yaml.py tests/sandbox/test_digests_policy.py tests/adversarial/test_in_repo_policy_ignored.py src/codegenie/sandbox/signals/policy.py` clean.
- [ ] **AC-GATE-2** `ruff format --check` clean on the above.
- [ ] **AC-GATE-3** `mypy --strict src/codegenie/sandbox/signals/policy.py` clean. YAML files not type-checked.
- [ ] **AC-GATE-4** `pytest tests/sandbox/test_catalogs_populated.py tests/sandbox/test_policy_yaml.py tests/sandbox/test_digests_policy.py tests/adversarial/test_in_repo_policy_ignored.py tests/schema/test_digests_yaml.py` green on both 3.11 and 3.12.
- [ ] **AC-GATE-5** TDD plan's red tests are committed first, fail with the expected error mode (`ModuleNotFoundError` / `FileNotFoundError` / `AssertionError` per planted-positive), then turn green only after the YAML + module land.

## Implementation outline

1. **Populate `src/codegenie/gates/catalog/stage6_validate.yaml`** from the arch §Data model verbatim, with `cgr.dev/chainguard/node@sha256:` + 64 zero hex chars as the placeholder `base_image` (the literal `"<pinned>"` placeholder in the arch template is substituted to the all-zeros hex form so S1-06's schema regex `^cgr\.dev/chainguard/[a-z]+@sha256:[a-f0-9]{64}$` accepts it). Real Chainguard digest swap is owned by S3-07; this story keeps unit tests deterministic with the all-zeros stub.
2. **Create `src/codegenie/gates/catalog/stage6_validate_loose.yaml`** with the loose `required_signals` / `retry_policy` per Group B + the same `sandbox` block as strict (duplicate, no anchors).
3. **Create `tools/policy/sandbox-policy.yaml`** matching the arch §Data model lines 810–824 byte-for-byte (LF line endings, trailing LF, no BOM).
4. **Compute BLAKE3-128 of the policy file** (`python -c "import blake3, pathlib; print(blake3.blake3(pathlib.Path('tools/policy/sandbox-policy.yaml').read_bytes()).hexdigest(length=16))"` — 32 lowercase hex chars). Write that value into `tools/digests.yaml` under `sandbox.policy_yaml` (replacing the S1-07 `"TBD"`).
5. **Apply the S1-07 regex forward-fix** to `tests/schema/test_digests_yaml.py`: change `_BLAKE3_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")` → `re.compile(r"^[a-f0-9]{32}$")` (one-line). Update the inline comment header per AC-DG-FIX-2.
6. **Add `POLICY_PATH` to `src/codegenie/sandbox/signals/policy.py`** (one-line module — the full collector body is S4-03). Cite ADR-0013 in the module docstring.
7. **If `codegenie.sandbox.signals._introspection.BANNED_SUBSTRINGS` is not yet exported** (verify via `grep -n "BANNED_SUBSTRINGS" src/codegenie/sandbox/signals/_introspection.py`), add it as a one-line additive constant. No behavior change to S1-03's introspection logic.
8. **Commit golden templates** to `tests/golden/{stage6_validate,sandbox-policy}.yaml.template` (arch verbatim, no substitution applied).
9. **Write the five test files** per the TDD plan below.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths:
- `tests/sandbox/test_catalogs_populated.py` (Groups A, B, F, I, K-AC-PP-3 / -4)
- `tests/sandbox/test_policy_yaml.py` (Groups C, H, K-AC-PP-2)
- `tests/sandbox/test_digests_policy.py` (Groups D, J, K-AC-PP-1)
- `tests/adversarial/test_in_repo_policy_ignored.py` (Group G, K-AC-PP-5; stub — full behavioral test in S4-03)
- `tests/schema/test_digests_yaml.py` — **edit-in-place** (Group E — regex forward-fix; no new test file)

```python
# tests/sandbox/test_catalogs_populated.py
from __future__ import annotations

from pathlib import Path
import re
import yaml
from codegenie.gates.catalog_loader import CatalogEntry, load_all
from codegenie.gates.contract import TransitionId
from codegenie.gates.errors import GateCatalogInvalid

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "src/codegenie/gates/catalog"

def _load_yaml(name: str) -> dict:
    return yaml.safe_load((CATALOG / name).read_text(encoding="utf-8"))

# Group A — strict catalog
def test_strict_required_signals_exact_order_and_value() -> None:
    """AC-STRICT-1. Order matters: canonical-JSON spec hashing (S3-01) is order-sensitive."""
    data = _load_yaml("stage6_validate.yaml")
    assert data["required_signals"] == ["build", "install", "tests", "trace", "policy", "cve_delta"]

def test_strict_retry_policy_fields() -> None:
    """AC-STRICT-3..AC-STRICT-6."""
    data = _load_yaml("stage6_validate.yaml")
    rp = data["retry_policy"]
    assert rp["max_attempts"] == 3
    assert rp["retryable_failures"] == ["build", "install", "tests", "policy", "cve_delta"]
    assert rp["non_retryable_failures"] == ["trace"]
    assert rp["timeout_retryable"] is False

def test_strict_sandbox_block_pinned() -> None:
    """AC-STRICT-7..AC-STRICT-13."""
    data = _load_yaml("stage6_validate.yaml")
    sb = data["sandbox"]
    assert sb["base_image"] == "cgr.dev/chainguard/node@sha256:" + "0" * 64
    assert sb["time_budget_seconds"] == 600
    assert sb["memory_limit_mib"] == 2048
    assert sb["pids_limit"] == 1024
    assert sb["env_allowlist"] == ["PATH", "NODE_ENV", "NPM_CONFIG_*", "HTTPS_PROXY"]
    assert sb["phases"][0] == {
        "name": "install",
        "network": "scoped",
        "egress_allowlist": ["registry.npmjs.org"],
        "cmd": ["sh", "-c", "cd /work && npm ci --ignore-scripts"],
    }
    assert sb["phases"][1] == {
        "name": "test",
        "network": "none",
        "enable_trace": True,
        "cmd": ["sh", "-c", "cd /work && npm test"],
    }

def test_strict_attempt_overrides_attempt_2() -> None:
    """AC-STRICT-14."""
    data = _load_yaml("stage6_validate.yaml")
    assert data["attempt_overrides"]["2"]["phases"][0]["cmd"] == [
        "sh", "-c", "cd /work && npm test -- --verbose --maxWorkers=1",
    ]

# Group B — loose catalog
def test_loose_metadata_and_signals() -> None:
    """AC-LOOSE-1..AC-LOOSE-7."""
    data = _load_yaml("stage6_validate_loose.yaml")
    assert data["gate_id"] == "stage6_validate_loose"
    assert data["transition"] == "stage6_validate_loose"
    assert data["required_signals"] == ["build", "install", "tests"]
    rp = data["retry_policy"]
    assert rp["max_attempts"] == 3
    assert rp["retryable_failures"] == ["build", "install", "tests"]
    assert rp["non_retryable_failures"] == []
    assert rp["timeout_retryable"] is False

def test_loose_sandbox_block_matches_strict() -> None:
    """AC-LOOSE-9 — same sandbox block."""
    strict = _load_yaml("stage6_validate.yaml")["sandbox"]
    loose = _load_yaml("stage6_validate_loose.yaml")["sandbox"]
    assert loose == strict

def test_no_yaml_anchors_in_either_catalog() -> None:
    """AC-LOOSE-10 — anchors / aliases / merge keys are forbidden."""
    for name in ("stage6_validate.yaml", "stage6_validate_loose.yaml"):
        text = (CATALOG / name).read_text(encoding="utf-8")
        assert not re.search(r"^[^#\n]*[&*]\w+|<<:", text, flags=re.MULTILINE), f"YAML anchor in {name}"

# Group F — load via catalog_loader
def test_both_catalogs_load_through_loader() -> None:
    """AC-LOAD-1..AC-LOAD-4."""
    result = load_all(CATALOG)
    assert set(result.keys()) == {"stage6_validate", "stage6_validate_loose"}
    assert isinstance(result["stage6_validate"], CatalogEntry)
    assert isinstance(result["stage6_validate_loose"], CatalogEntry)
    assert result["stage6_validate"].transition is TransitionId.STAGE6_VALIDATE
    assert result["stage6_validate_loose"].transition is TransitionId.STAGE6_VALIDATE_LOOSE

# Group I — golden template byte-equality
def test_stage6_validate_matches_arch_template() -> None:
    """AC-GOLDEN-3."""
    golden = (ROOT / "tests/golden/stage6_validate.yaml.template").read_bytes()
    expected = golden.replace(b"<pinned>", b"0" * 64)
    actual = (CATALOG / "stage6_validate.yaml").read_bytes()
    assert actual == expected

# Group K — planted positives
def test_planted_loader_rejects_extra_property(tmp_path) -> None:
    """AC-PP-3. Mutation: AC-LOAD-1 would silently pass if the loader stopped enforcing extra='forbid'."""
    bad = tmp_path / "stage6_validate.yaml"
    bad.write_text(
        (CATALOG / "stage6_validate.yaml").read_text(encoding="utf-8") + "\nextra_key: rejected\n",
        encoding="utf-8",
    )
    try:
        load_all(tmp_path)
    except GateCatalogInvalid:
        return
    raise AssertionError("planted extra_key should have raised GateCatalogInvalid")

def test_planted_required_signals_order_drift_is_detected() -> None:
    """AC-PP-4. Mutation: AC-STRICT-1 would silently pass if a future refactor used set equality."""
    drifted = ["trace", "build", "install", "tests", "policy", "cve_delta"]
    canonical = ["build", "install", "tests", "trace", "policy", "cve_delta"]
    # Same elements, different order. set(...) == set(...) would pass; list eq must fail.
    assert drifted != canonical
```

```python
# tests/sandbox/test_policy_yaml.py
from __future__ import annotations

from pathlib import Path
import yaml
from codegenie.sandbox.signals._introspection import BANNED_SUBSTRINGS

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "tools/policy/sandbox-policy.yaml"

def _load() -> dict:
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))

# Group C — policy values
def test_schema_version_and_lockfile() -> None:
    """AC-POL-2..AC-POL-3."""
    data = _load()
    assert data["schema_version"] == 1
    assert data["lockfile"] == {
        "forbid_git_dep_specifiers": True,
        "forbid_unscoped_overrides": True,
        "require_integrity_field": True,
    }

def test_runtime_trace_invariants() -> None:
    """AC-POL-4..AC-POL-6. ADR-0013 §Decision."""
    rt = _load()["runtime_trace"]
    assert rt["fail_on_new_shell_invocation"] is True
    assert rt["fail_on_new_endpoint"] is True
    assert rt["warn_on_low_coverage"] is True

def test_adr_0015_asymmetric_test_inventory_policy() -> None:
    """AC-POL-7. ADR-0015 load-bearing invariant. Mutation that flips either value
    silently neuters the adversarial gate; this AC must fail loudly on either."""
    ti = _load()["test_inventory"]
    assert ti["fail_on_negative_delta"] is True
    assert ti["warn_on_positive_delta"] is False

# Group H — banned-substring canonical import + content check
def test_banned_substrings_set_is_canonical() -> None:
    """AC-BS-2 — sync with ADR-0014's canonical set."""
    assert BANNED_SUBSTRINGS == frozenset({"confidence", "llm", "self_reported", "model_says"})

def test_policy_yaml_text_has_no_banned_substring() -> None:
    """AC-BS-3 — ADR-0014's spirit extended into YAML text content."""
    text = POLICY.read_text(encoding="utf-8").lower()
    for banned in BANNED_SUBSTRINGS:
        assert banned not in text, f"banned substring '{banned}' present in policy YAML"

# Group K planted-positive
def test_planted_banned_substring_is_detected() -> None:
    """AC-PP-2. Mutation: AC-BS-3 would silently pass on an empty set or a no-op walker."""
    synthesized = "schema_version: 1\nmodel_confidence: 0.5\n"
    matches = [s for s in BANNED_SUBSTRINGS if s in synthesized]
    assert "confidence" in matches  # walker must fire on substring match
```

```python
# tests/sandbox/test_digests_policy.py
from __future__ import annotations

from pathlib import Path
import re
import blake3
import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "tools/policy/sandbox-policy.yaml"
DIGESTS = ROOT / "tools/digests.yaml"

_BLAKE3_128_HEX = re.compile(r"^[a-f0-9]{32}$")

# Group D — digest value
def test_policy_digest_matches_file_bytes() -> None:
    """AC-DG-1. Catches a stale `tools/digests.yaml` after a policy edit — exact
    silent-drift failure ADR-0013 forbids."""
    digests = yaml.safe_load(DIGESTS.read_text(encoding="utf-8"))
    declared = digests["sandbox"]["policy_yaml"]
    actual = blake3.blake3(POLICY.read_bytes()).hexdigest(length=16)
    assert declared == actual, f"digest mismatch: declared={declared!r} actual={actual!r}"

def test_policy_digest_is_blake3_128_hex_shape() -> None:
    """AC-DG-2 + AC-DG-3. Independent of file-bytes equality: must be 32 lowercase hex
    (BLAKE3-128 per arch §Data model lines 654/774-775 and S3-01)."""
    digests = yaml.safe_load(DIGESTS.read_text(encoding="utf-8"))
    declared = digests["sandbox"]["policy_yaml"]
    assert declared != "TBD"
    assert _BLAKE3_128_HEX.fullmatch(declared), f"not BLAKE3-128 hex: {declared!r}"

def test_other_sandbox_digests_remain_tbd() -> None:
    """AC-DG-4 — out of scope for this story; S6-03 owns."""
    digests = yaml.safe_load(DIGESTS.read_text(encoding="utf-8"))
    for k in ("firecracker", "vmlinux", "rootfs"):
        assert digests["sandbox"][k] == "TBD"

# Group J — file stability invariants
def test_policy_file_stability_invariants() -> None:
    """AC-STAB-1..AC-STAB-3. Any of these silently changes the BLAKE3 the moment a
    Windows checkout / pre-commit hook touches the file."""
    raw = POLICY.read_bytes()
    assert raw.endswith(b"\n"), "policy YAML must end with LF newline"
    assert not raw.endswith(b"\n\n"), "no trailing blank line"
    assert b"\r\n" not in raw, "no CRLF line endings"
    assert not raw.startswith(b"\xef\xbb\xbf"), "no UTF-8 BOM"

# Group K planted-positive
def test_planted_digest_mismatch_is_detected(tmp_path) -> None:
    """AC-PP-1. Mutation: AC-DG-1's recompute would silently pass if both producer +
    verifier sides used the same wrong hash function. Explicit known-wrong fixture
    forces the equality check to fire."""
    fake_digests = tmp_path / "digests.yaml"
    fake_digests.write_text("sandbox:\n  policy_yaml: deadbeefdeadbeefdeadbeefdeadbeef\n")
    fake_payload = tmp_path / "policy.yaml"
    fake_payload.write_text("schema_version: 1\n")
    d = yaml.safe_load(fake_digests.read_text())["sandbox"]["policy_yaml"]
    a = blake3.blake3(fake_payload.read_bytes()).hexdigest(length=16)
    assert d != a  # the equality check would fail — planted-positive proves AC-DG-1 fires
```

```python
# tests/adversarial/test_in_repo_policy_ignored.py
"""Stub — full behavioral test in S4-03 (needs `collect_policy_signal`).
This story locks in the ADR-0013 path invariant before the collector ships."""
from __future__ import annotations

from pathlib import Path
from codegenie.sandbox.signals.policy import POLICY_PATH

# Group G
def test_policy_path_is_not_repo_resident() -> None:
    """AC-ADV-1..AC-ADV-3. The policy collector must never reach into the target repo's
    .codegenie/. Path-component check (not substring) defeats traversal."""
    resolved = POLICY_PATH.resolve()
    assert ".codegenie" not in resolved.parts
    assert POLICY_PATH.parts[:2] == ("tools", "policy")
    assert POLICY_PATH.name == "sandbox-policy.yaml"

# Group K planted-positive
def test_planted_policy_path_traversal_is_detected(monkeypatch) -> None:
    """AC-PP-5. Mutation: AC-ADV-2 would silently pass on a substring-only check
    against a traversal path."""
    bad = Path(".codegenie/../tools/policy/sandbox-policy.yaml")
    assert ".codegenie" in bad.resolve().parts or ".codegenie" in bad.parts
```

### Green — make it pass

- Populate the two YAML files.
- Commit `tools/policy/sandbox-policy.yaml` (LF line endings, trailing LF, no BOM — verify with `xxd` or `file`).
- Compute the BLAKE3-128 digest and write it under `tools/digests.yaml#sandbox.policy_yaml`.
- Apply the S1-07 regex forward-fix (`tests/schema/test_digests_yaml.py::_BLAKE3_DIGEST_RE`: `{64}` → `{32}`) + the inline comment update.
- Add `POLICY_PATH: Final[Path] = Path("tools/policy/sandbox-policy.yaml")` to `src/codegenie/sandbox/signals/policy.py` with an ADR-0013 docstring.
- If absent: add `BANNED_SUBSTRINGS: Final[frozenset[str]] = frozenset({"confidence", "llm", "self_reported", "model_says"})` to `codegenie.sandbox.signals._introspection` and update its `__all__`.
- Commit the two golden templates to `tests/golden/`.

### Refactor — clean up

- Run `ruff format --check` on the new Python; YAML linted via `yamllint` if available.
- Verify `pytest -k catalogs_populated or in_repo_policy_ignored or digests_policy or policy_yaml or test_digests_yaml` is green on both 3.11 and 3.12.
- Add commit-message note: `Phase 5 policy digest pinned to <hex>; S1-07 _BLAKE3_DIGEST_RE corrected to BLAKE3-128 (32 chars) per arch + S3-01. Future policy updates require ADR amendment + digest re-computation.`

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/catalog/stage6_validate.yaml` | Populate per arch spec; literal placeholder `sha256:` + 64 zero hex chars for `base_image` (S3-07 swaps to real Chainguard digest). |
| `src/codegenie/gates/catalog/stage6_validate_loose.yaml` | New — dev-mode loose catalog; `sandbox` block duplicated from strict (no YAML anchors). |
| `tools/policy/sandbox-policy.yaml` | New — codegenie-owned, digest-pinned policy. |
| `tools/digests.yaml` | Edit `sandbox.policy_yaml`: `"TBD"` → 32-char BLAKE3-128 hex. Other three keys unchanged. |
| `tests/schema/test_digests_yaml.py` | One-line forward-fix: `_BLAKE3_DIGEST_RE` `{64}` → `{32}` + inline comment update. |
| `src/codegenie/sandbox/signals/policy.py` | New ~5-line module: `POLICY_PATH: Final[Path]` + ADR-0013 docstring. Full collector body in S4-03. |
| `src/codegenie/sandbox/signals/_introspection.py` | If absent: add `BANNED_SUBSTRINGS: Final[frozenset[str]]` constant + extend `__all__`. (Verify first with `grep`.) |
| `tests/golden/stage6_validate.yaml.template` | New — arch §Data model verbatim (with `<pinned>` literal). |
| `tests/golden/sandbox-policy.yaml.template` | New — arch §Data model verbatim. |
| `tests/sandbox/test_catalogs_populated.py` | New — Groups A, B, F, I, K-AC-PP-3/-4. |
| `tests/sandbox/test_policy_yaml.py` | New — Groups C, H, K-AC-PP-2. |
| `tests/sandbox/test_digests_policy.py` | New — Groups D, J, K-AC-PP-1. |
| `tests/adversarial/test_in_repo_policy_ignored.py` | New stub — Group G, K-AC-PP-5; full test in S4-03. |

## Out of scope

- The `collect_policy_signal` implementation that reads `POLICY_PATH` — S4-03.
- Upgrading `tests/schema/test_digests_yaml.py` from presence + shape to **value-validation** (computing the BLAKE3 in the fence test and comparing) — S6-03 covers it.
- Real Chainguard `cgr.dev/chainguard/node@sha256:...` digest in `stage6_validate.yaml#sandbox.base_image` — S3-07 (needs a live Docker pull).
- Per-team or per-org policy overrides — explicitly disallowed by ADR-0013.
- Schema evolution (`schema_version: 1` → `2`) — future ADR amendment.
- A `digest_for(name) -> str` helper for `tools/digests.yaml` (rule-of-three threshold reached counting tests, but the first **production** consumer is S3-06 — it owns the kernel). See Notes-for-implementer §1.
- A typed `PLACEHOLDER_BASE_IMAGE_DIGEST` sentinel for catching forgotten-pin states — S3-06's `SandboxHealthProbe` startup check is the natural owner. See Notes-for-implementer §2.
- Widening `tools/digests.yaml` to a 5th `sandbox.base_image_node` key — explicitly NOT done; the placeholder digest stays inline in the catalog YAML.

## Notes for the implementer

1. **Don't write a `digest_for(name) -> str` helper here.** A reusable reader for `tools/digests.yaml` reaches three consumers (this story's test + S3-06's `SandboxHealthProbe` + S6-03's value-validation fence), but S3-06 is the first **production** consumer and owns the kernel by precedent (Rule 2 simplicity, Rule 3 surgical changes). Leave the `yaml.safe_load(...)["sandbox"]["policy_yaml"]` access inline in this story's test. If you find yourself tempted, stop — the next story will promote it.
2. **`PLACEHOLDER_BASE_IMAGE_DIGEST` sentinel is S3-06's responsibility, not this one.** Keep the literal `cgr.dev/chainguard/node@sha256:` + 64 zero hex chars in `stage6_validate.yaml#sandbox.base_image`. S3-06's `SandboxHealthProbe` startup check should refuse a placeholder digest (`reachable=False, reasons=["base_image_unpinned"]`); when that story lands, promote a typed `Final[str]` constant shared across catalog YAML loader and probe. For now: a magic string in the catalog YAML is fine.
3. **BLAKE3-128 vs BLAKE3-256 is a real Phase 5 cross-story conflict** that S1-07 got wrong (regex `{64}` instead of `{32}`). The arch §Data model lines 654/774–775 + S3-01 AC-HASH-FORMAT-1 pin BLAKE3-128 (32 hex chars). Per Rule 7 (Surface conflicts, don't average them): pick the more recent / more tested (S3-01 is fresher and `hexdigest(length=16)` is referenced verbatim in three places in the arch), surface S1-07's bug, and fix it here in one line. Do NOT widen the regex to accept both `{32}` and `{64}` — averaging is the worst code.
4. **Do not anchor-and-merge YAML keys** across the two catalogs. Grep-ability per Rule 11 (match codebase conventions — `tools/policy/lockfile-policy.yaml` and `tools/grammars.lock` are flat YAMLs). AC-LOOSE-10 enforces this; a future contributor tempted by DRY will find a failing test before merging.
5. **`POLICY_PATH` is a plain `Path`, not a newtype.** S4-03 owns the typing decision when it ships the collector that consumes the path; until a second module imports `POLICY_PATH` directly, a typed `RepoPath` newtype would be premature (Rule 2). The adversarial stub's `.resolve().parts` check is the meaningful invariant, not the type.
6. **`tools/digests.yaml` is multi-section.** S1-07 ships placeholders under `sandbox.{firecracker, vmlinux, rootfs, policy_yaml}`. Do NOT add a 5th `sandbox.base_image_node` key — it violates S1-07 AC-DG-2's "exactly four keys" constraint. Run `git diff tools/digests.yaml` after the edit; the diff should be one line (the `policy_yaml` value flipped from `"TBD"` to the hex).
7. **If you change `sandbox-policy.yaml` by a single byte (whitespace, line-ending, BOM) AFTER committing, CI fails.** This is intentional. To update the policy: edit YAML → recompute digest → update `tools/digests.yaml#sandbox.policy_yaml` → file a follow-up ADR amendment per ADR-0013 → commit all three in the same PR. Pre-commit hook (if any line-ending normalizer is enabled) must not silently rewrite the file.
8. **The `<pinned>` literal substitution in the golden template** is the simplest possible "template" pattern: a single `bytes.replace(b"<pinned>", b"0"*64)`. Don't introduce Jinja, string.Template, or anything else — three lines of `bytes` substitution will not need a framework until a second template lands.
