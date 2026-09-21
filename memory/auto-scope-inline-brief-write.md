---
created: "2026-06-04 16:11"
session: "e58f8523-4c6a-4a67-9908-4211ba413cd7"
source: claude-mem
source_table: session_summaries
source_ids: [3581]
---

# step-auto-scope §8 writes skill-brief.yaml inline, not via skf-write-skill-brief.py

`src/skf-analyze-source/references/step-auto-scope.md` §8 "Write Skill Brief" emits `{forge_data_folder}/{skill_name}/skill-brief.yaml` as an inline YAML block and declares no `writeSkillBriefProbeOrder`, while every other brief writer — `skf-brief-skill/references/write-brief.md`, `step-auto-brief.md`, and the carved-out docs-only path `skf-analyze-source/references/auto-docs-only.md` — resolves `src/shared/scripts/skf-write-skill-brief.py`, whose docstring calls itself "the single source of truth". The June 2026 health-fix pass (PR #440, commit 63c157e9) wired only the docs-only branch and left §8 alone because switching it is a larger behavioural change deserving its own finding. §8 is where the `doc_urls` companion-corpus seeds from §6b, the `--pin` data from §0b (`target_version` / `target_ref`), and the N-boundary decomposition briefs are wired, so moving it onto the canonical writer means carrying all of that through the script's `--from-flat` context payload, not a drop-in swap.
