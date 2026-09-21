---
created: "2026-05-24 13:28"
session: "7d4a5235-113d-4703-a34b-84d89fa4295a"
source: claude-mem
source_table: observations
source_ids: [11616, 11618, 11632, 11638]
---

# Three-way sync of SKILL.md heading vocabularies

Two independent scripts gate SKILL.md headings with different matching: `src/shared/scripts/skf-validate-output.py:109` hardcodes `required_sections = ["Overview", "Description", "Key Exports", "Usage"]` and matches each as a case-insensitive substring of a `## ` line (`^##\s+.*{section}`, so `Usage Patterns` satisfies `Usage`), while `skf-scan-skill-md-structure.py:109` matches the full heading text against its `REQUIRED_SYNONYMS` dict, which mirrors the synonym lists in `src/skf-test-skill/references/coherence-check.md` §2.1. The quick-skill template (`src/skf-quick-skill/assets/skill-template.md`: `Overview`/`Description`/`Key Exports`/`Usage Patterns`) and the create-skill template (`src/skf-create-skill/assets/skill-sections.md`: `Quick Start`/`Common Workflows`/`Key API Summary`/`Key Types`) are separate vocabularies. When the scanner lacked `Usage Patterns` and `Key Exports`, every Tier-B quick skill passed the output validator but carried a spurious `naive-coherence — missing required section` finding from skf-test-skill (Medium then; the rule now emits High) despite `npx skill-check` scoring 100/100 (PR #381). No test enforces the mirror, so adding or renaming a template heading means updating `REQUIRED_SYNONYMS` (additively), the `tried[]` lists in coherence-check.md §2.1 and `skf-validate-output.py`'s `required_sections` in the same change.
