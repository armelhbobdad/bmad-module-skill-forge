---
created: "2026-04-08 10:18"
session: "02f8c828-1c77-4b73-a8f1-4a12a461890e"
source: claude-mem
source_table: observations
source_ids: [4701, 4702, 4704]
---

# Setup skill directory must end in -setup

The BMad module builder's `validate-module.py` (invoked as `bmad:bmb:modules:validate-module`, per `src/README.md`; lives in the git-ignored `.claude/skills/bmad-module-builder/scripts/`) locates a module's setup skill with `d.name.endswith("-setup")`. `src/skf-setup-forge/` failed validation for exactly this reason and was renamed to `src/skf-setup/` (commit f670a117), touching ~60 references across step files, knowledge files, docs, `.claude-plugin/marketplace.json` and tests. Nothing in the repo states the constraint, so do not rename `skf-setup` to something more descriptive — the module will stop validating. (`module.yaml` and `module-help.csv` were later restored to the `src/` root by d698194a; only the directory name matters.)
