---
created: "2026-06-03 13:28"
session: "56051077-ffb7-41ac-a86a-8e9182d7c6a8"
source: claude-mem
source_table: observations
source_ids: [14571, 14572, 14613]
---

# doc_urls entry shape is a lockstep contract

`src/shared/scripts/skf-write-skill-brief.py` (lines 448-456) rebuilds every `doc_urls` entry field-by-field and emits only `{url, label}` plus `source` when present; any other key on an input entry is silently dropped, never rejected (before #432 this is why `skf-detect-docs.py`'s `detected_via`/`content_type`/`content_hash` never reached the brief). `skill-brief.v1.json` puts no `additionalProperties: false` on `doc_urls[]`, so `skf-validate-brief-schema.py` will not flag the extra key either — a new field simply vanishes. Any change to the entry shape therefore has to land together across `skill-brief.v1.json`, `skf-write-skill-brief.py`, `skf-validate-brief-schema.py`, `skf-validate-brief-inputs.py`, `skf-merge-doc-urls.py`, `skf-language-corpora.py`, `skf-derive-assembly-shape.py`, the producers `skf-analyze-source/references/step-auto-scope.md` §6b/§8 and `skf-brief-skill/references/step-auto-brief.md` §3 (which maps `detected_via` onto the `source` enum), and their `test/test-skf-*.py` suites. The user's instruction for #432: "Treat it as a lockstep change — find EVERY schema, validator, ...".
