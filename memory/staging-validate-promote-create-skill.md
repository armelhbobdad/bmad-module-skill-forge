---
created: "2026-03-14 17:29"
session: "399dba32-15e7-4ca7-b421-c491359347a7"
source: claude-mem
source_table: both
source_ids: [1131, 1133, 1144, 1156]
---

# Staging-validate-promote pattern for skf-create-skill compilation

skf-create-skill writes every compiled artifact to the staging directory `_bmad-output/{skill-name}/` in step 5 (`src/skf-create-skill/references/compile.md`), runs `npx skill-check check <staging-skill-dir> --fix`, tessl and the description guard against that directory in step 6 (`validate.md`), and only step 7 (`generate-artifacts.md`) promotes the files to `{skills_output_folder}/{name}/{version}/{name}/` and `{forge_data_folder}/{name}/{version}/`. The pattern exists because multi-agent compilation cannot be held inside a single-context "FORBIDDEN to write files" boundary — sub-agents cannot share in-context compiled content and skill-check/tessl need files on disk — so the earlier blanket no-write rules were self-contradictory. The maintainer chose staging (Option A) over reordering steps (Option B): "Option A is definitely the way to go. Multi-agent processing inherently breaks the single-context boundary. Writing to a staging area (`_bmad-output/{name}/`), validating/auto-fixing it there, and then promoting it to the final `skills/` and `forge-data/` directories accurately reflects reality and creates a cleaner build process." The staging directory name must equal the frontmatter `name` exactly or skill-check's `frontmatter.name_matches_directory` rule rejects it (`validate.md`).
