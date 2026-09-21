---
created: "2026-05-24 13:39"
session: "7d4a5235-113d-4703-a34b-84d89fa4295a"
source: claude-mem
source_table: session_summaries
source_ids: [3086, 3087]
---

# Template headings are frozen; widen validators additively

The quick-skill template (`src/skf-quick-skill/assets/skill-template.md`) emits `## Key Exports` and `## Usage Patterns`, and skills already forged into users' repos carry those exact headings, so renaming a canonical template heading retroactively breaks every shipped instance. When a structural gate rejects a template heading (`src/shared/scripts/skf-scan-skill-md-structure.py` checks the `description` / `usage` / `api_surface` synonym families; `skf-validate-output.py` requires Overview/Description/Key Exports/Usage), the fix is to add the heading to the scanner's `REQUIRED_SYNONYMS` list, as was done (see the comment block at `skf-scan-skill-md-structure.py:98-108` and `src/skf-test-skill/references/coherence-check.md` §2.1), never to change the template. The same holds for the Deep template headings (`Quick Start`, `Common Workflows`, `Key API Summary`) and the reference-app overrides (`Adoption Steps`, `Pattern Surface`).
