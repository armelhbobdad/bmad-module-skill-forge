---
created: "2026-05-27 05:58"
session: "c1e950ee-8504-48fd-887f-92c4df6f355a"
source: claude-mem
source_table: observations
source_ids: [13993, 14084, 14086, 14103]
---

# Alias removals leave live examples stale across docs

Pipeline alias names live in many files with no validator: `src/skf-forger/scripts/parse-pipeline.py` (`ALIASES`, `DEPRECATED_ALIASES`, `REMOVED_ALIASES`), the alias table in `src/shared/references/pipeline-contracts.md`, `src/skf-forger/SKILL.md`, `src/skf-forger/references/init.md` §1b (the forge-auto -> 90 threshold lookup), README.md Quick Start, docs/agents.md (Ferris menu and alias list), docs/index.md, docs/getting-started.md, docs/examples.md, docs/workflows.md, docs/troubleshooting.md and website/astro.config.mjs. When the `onboard` alias was removed, four files were updated but `@Ferris onboard` survived as a copy-paste example in docs/examples.md and in the docs/agents.md alias list until a doc review a week later caught it. After any alias rename or removal, finish with `grep -rn '<old-name>' README.md docs/ website/ src/` and leave only the intentional migration notes (docs/forge-auto.md, docs/troubleshooting.md, the forger HALT message in `src/skf-forger/SKILL.md`).
