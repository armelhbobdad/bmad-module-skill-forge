---
created: "2026-06-03 13:25"
session: "56051077-ffb7-41ac-a86a-8e9182d7c6a8"
source: claude-mem
source_table: observations
source_ids: [14568, 14569]
---

# Brief schema carries no shape field

`src/shared/scripts/schemas/skill-brief.v1.json` has a `scope.type` enum (full-library, specific-modules, public-api, component-library, reference-app, docs-only) but no shape field: the shape `skf-shape-detect.py` classifies (language-reference, library-API, reference-app, stack-compose) is written into the analysis-report frontmatter (`confirmed_units[].shape`, `skf-analyze-source/references/step-auto-scope.md` §7) and only appears in the brief as free text inside `scope.notes` (`Auto-scoped from shape detection (shape: {shape}, ...)`), never as a structured field. `full-library` is shared by language-reference, small library-API and stack-compose repos, so `skf-brief-skill/references/step-auto-brief.md` and skf-create-skill cannot recover the shape from `scope.type`, and step-auto-brief.md's rule "Do NOT re-derive scope fields from the upstream brief" forbids reconstructing it. Any shape-conditional logic therefore runs in step-auto-scope.md (e.g. §6b Seed Companion Corpora, the `skf-language-corpora.py` lookup), and downstream steps branch only on a structured marker AN wrote into the brief — today `doc_urls[].source: "language-registry"`, which `skf-derive-assembly-shape.py` gates the whole-language layout on. Putting shape logic in BS or CS instead would need a breaking brief-schema change. Related: `doc_urls` `minItems: 1` applies only when the key is present, so a DEGRADED brief (no corpora found) omits `doc_urls` rather than emitting an empty array.
