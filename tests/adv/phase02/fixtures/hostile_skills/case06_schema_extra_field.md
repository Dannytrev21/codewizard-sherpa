---
id: hostile-extra-field
applies_to_tasks: ["*"]
applies_to_languages: ["*"]
malicious_extra: "an attacker-crafted field that should be rejected by extra=forbid"
---
Case 6 — valid YAML, valid required fields, but `Skill.model_config` has
`extra="forbid"`; an unknown field triggers a Pydantic validation error
the loader surfaces as `schema`.
