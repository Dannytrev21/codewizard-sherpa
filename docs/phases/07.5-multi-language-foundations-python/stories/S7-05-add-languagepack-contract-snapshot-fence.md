# Story S7-05 — Add the `LanguagePack` contract-snapshot fence (G9)

**Step:** Step 7 — Land the `tests/conformance/` tier and the `LanguagePack` contract-snapshot fence
**Status:** Ready
**Effort:** S
**Depends on:** S1-02
**ADRs honored:** ADR-0012, ADR-0001

## Context
The roadmap's Phase 7.5 exit criterion "the category-based fence rejects a planted silent edit" is realized — per ADR-0043 commitment 3 and ADR-0012 — as a *contract + snapshot test*, not a per-phase byte-edit allowlist (Phase 7's allowlist is the last). This story lands `tests/fence/test_language_pack_contract.py` + `tests/fence/snapshots/language_pack_contract.v1.json`, pinning the `LanguagePack` field set and types exactly as `tests/unit/test_probe_contract.py` pins the probe ABC. The `LanguagePack` *file* stays freely editable; the snapshot test fails iff the *contract* — field names and types — changes, the desired loud signal when a genuinely new capability category is added.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack contract-snapshot fence` — a snapshot test pinning the `LanguagePack` field set + types into `language_pack_contract.v1.json`; the pack file stays editable; no allowlist rows.
- **Architecture:** `../phase-arch-design.md §Goals G9` — the category-based fence goes red on a planted `LanguagePack` field-add; a planted Node-probe-body edit goes red against the G3 regression gate; both planted-edit levels in the test plan.
- **Architecture:** `../phase-arch-design.md §Scenarios — Scenario 4` — two levels: (a) a `LanguagePack` field-add → snapshot red; (b) a Node-probe-body change → regression suite red.
- **Architecture:** `../phase-arch-design.md §Data model — LanguagePack contract` — the exact six required fields + `probes_self_registered: bool = False` the snapshot pins.
- **Phase ADRs:** `../ADRs/0012-languagepack-contract-snapshot-fence-not-byte-edit-allowlist.md` — ADR-0012 — Option C: a contract + snapshot test, the probe-ABC pattern; no allowlist rows; the snapshot file is `language_pack_contract.v1.json` (the `v1` anticipates a `v2`).
- **Phase ADRs:** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — `LanguagePack` is `Provisional Accepted`; the snapshot pins the provisionally-frozen contract; a field-add may also fire the third-language review trigger.
- **Production ADRs:** `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — commitment 2 (allowlist accretion stops — Phase 7's is the last) and commitment 3 (the contract + snapshot test is the buildable form).
- **Production ADRs:** `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — the probe contract pinned by a snapshot test — the exemplar.
- **Existing code:** `tests/unit/test_probe_contract.py` + `tests/snapshots/probe_contract.v1.json` — the exact pattern to mirror: a `structural_signature` rebuilt from the live class, compared to a committed JSON snapshot, with a drift message routing to an ADR.
- **Existing code:** `src/codegenie/languages/pack.py` (S1-02) — the `LanguagePack` model whose contract this fence pins.

## Goal
Land `tests/fence/test_language_pack_contract.py` plus the `language_pack_contract.v1.json` snapshot so a planted `LanguagePack` field-add turns the fence red.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and was observed failing before the snapshot JSON / fence existed.
- [ ] `tests/fence/snapshots/language_pack_contract.v1.json` pins the `LanguagePack` field set — field names, types, and the `probes_self_registered` default — derived from the live `LanguagePack` model.
- [ ] `tests/fence/test_language_pack_contract.py` rebuilds the contract signature from `codegenie.languages.pack.LanguagePack` and compares it to the committed snapshot; a mismatch fails with a message routing the reader to ADR-0012 / ADR-0001 and naming the deliberate-re-snapshot path.
- [ ] A planted field-add to `LanguagePack` turns the fence **red** — verified by a planted-edit test (or a documented manual planted-edit check committed as a guard test) per G9 Scenario 4(a).
- [ ] The fence pins the *contract* only — editing the `LanguagePack` *file* (docstrings, helper methods, `@property` bodies) without changing field names/types leaves it green.
- [ ] No allowlist rows are added anywhere — this is a contract+snapshot test, not a byte-edit allowlist (ADR-0012 / ADR-0043 commitment 2).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on the new fence; `make fence` runs it and stays green; `import-linter` clean.

## Implementation outline
1. Write a small contract-signature extractor — a pure function rebuilding the `LanguagePack` field set (names + types + defaults) from the live Pydantic model (`model_fields`).
2. Generate `tests/fence/snapshots/language_pack_contract.v1.json` from that extractor (a regen script mirroring `scripts/regen_probe_contract_snapshot.py`, or an inline first-run dump committed deliberately).
3. Write `tests/fence/test_language_pack_contract.py` — rebuild the signature, load the snapshot, assert equality; on drift fail with an ADR-routing message.
4. Add a planted-edit guard test demonstrating a field-add turns the fence red (or a committed test that adds a field to a *copy* of the model and asserts the extractor diverges).
5. Confirm `make fence` picks up the new `tests/fence/` module.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/fence/test_language_pack_contract.py`.
- `test_language_pack_contract_matches_snapshot` — the live `LanguagePack` field set equals the committed snapshot.
```python
def test_language_pack_contract_matches_snapshot() -> None:
    # arrange: rebuild the contract signature from the live model
    live = language_pack_contract_signature(LanguagePack)
    snapshot = json.loads(SNAPSHOT_PATH.read_text())
    # act + assert: the contract has not drifted
    assert live == snapshot, CONTRACT_DRIFT_MESSAGE  # routes to ADR-0012 / ADR-0001
```
This fails first because `language_pack_contract.v1.json` does not exist; it stays meaningful once the snapshot is committed.
- `test_planted_field_add_turns_fence_red` — adding a field to a model derived from `LanguagePack` makes `language_pack_contract_signature` diverge from the snapshot — the teeth proof (Rule 9, G9).

### Green — make it pass
Write the `language_pack_contract_signature` extractor over `LanguagePack.model_fields`, generate and commit `language_pack_contract.v1.json`, and make the snapshot-match test green. The planted-field-add test passes once the extractor genuinely reflects the field set.

### Refactor — clean up
Mirror `test_probe_contract.py`'s structure — a `REPO_ROOT` anchor, a `SNAPSHOT_PATH` constant, a clear `CONTRACT_DRIFT_MESSAGE` naming the *deliberate* re-snapshot path (bump `v1`→`v2`, review ADR-0001's third-language review trigger). Add a docstring stating the fence catches a *`LanguagePack`-contract* change only — a planted Node-probe-body edit is caught by the G3 regression gate, not here.

## Files to touch
| Path | Why |
|---|---|
| `tests/fence/test_language_pack_contract.py` | New — the contract+snapshot fence over `LanguagePack`. |
| `tests/fence/snapshots/language_pack_contract.v1.json` | New — the committed `LanguagePack` contract snapshot. |
| `scripts/regen_language_pack_contract_snapshot.py` | New (optional) — the regen helper, mirroring `regen_probe_contract_snapshot.py`. |

## Out of scope
- The planted Node-probe-body-edit gate — that is the existing Phase 1–7 regression suite (G3), exercised in S7-04's planted-edit context; this fence covers only the `LanguagePack` *contract* level.
- Any new per-phase byte-edit allowlist — explicitly forbidden by ADR-0012 / ADR-0043 commitment 2.
- Closing out `make fence` / `import-linter` for the phase — S8-02.

## Notes for the implementer
- This fence pins a *contract*, not a *file*. Editing `pack.py` (docstrings, the `package_managers` `@property`, a new helper) must leave it green — only field name/type/default changes turn it red. Pin the field *set*, not the file bytes.
- A red fence is the *desired* loud signal when a genuine new capability category is added (a seventh field). The resolution is a *deliberate* re-snapshot (`v1`→`v2`) plus reviewing ADR-0001's `Review trigger`, never a silent re-snapshot — say so in the drift message.
- `arbitrary_types_allowed=True` means some fields are `type[Probe]` / callables — the extractor must capture these field types robustly (Pydantic `FieldInfo.annotation`), not choke on non-trivial annotations.
- Mirror `tests/unit/test_probe_contract.py` closely — it is the proven exemplar (a regen script + a structural signature + a committed JSON + an ADR-routing drift message). Do not invent a new snapshot mechanism.
- The snapshot file is `language_pack_contract.v1.json` deliberately — the `v1` anticipates the `v2` the third-language review trigger (Java/Maven) will force.
- This story depends only on S1-02 (`LanguagePack` exists) — it can land early in Step 7, in parallel with S7-02/03/04; sequence it whenever convenient.
