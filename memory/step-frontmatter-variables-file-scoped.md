---
created: "2026-04-11 16:40"
session: "46347c9c-0a52-490c-88b6-7cd05aef3ee1"
source: claude-mem
source_table: session_summaries
source_ids: [1648, 1650]
---

# Step-file frontmatter variables are file-scoped

A key declared in the YAML frontmatter of a step file under `src/skf-*/references/*.md` (`nextStepFile`, `forgeTierFile`, `atomicWriteProbeOrder`, …) is visible only inside that file — nothing inherits through the `nextStepFile` chain, which is why skf-create-skill re-declares `atomicWriteProbeOrder` in `extract.md`, `validate.md`, `generate-artifacts.md` and `report.md`. `{headless_mode}` and the customization scalars such as `{onCompleteCommand}` span steps only because each SKILL.md "On Activation" section resolves them into workflow context ("Stash all four as workflow-context variables") and Ferris passes `headless_mode` to every workflow it dispatches (`src/skf-forger/SKILL.md`). A new cross-step routing variable (a `{finish_gate}` was once attempted) therefore needs that resolver plumbing before any step can read it. The cheaper pattern is to encode the decision in the `nextStepFile` path itself or a second frontmatter key such as `ratifyTargetFile`, and branch at the gate.
