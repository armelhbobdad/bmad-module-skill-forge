---
created: "2026-05-25 20:28"
session: "6d814a59-aa1c-4ac6-8dd3-377aa63a7d45"
source: claude-mem
source_table: observations
source_ids: [12784, 12789]
---

# Multi-repo analyze-source attributes every unit to project_paths[0]

When `skf-analyze-source` is run with several `--project-path` repos, `src/skf-analyze-source/references/generate-briefs.md:51` sets `source_repo` to `{project_paths[0]}` for every brief (the "(or per-unit path if multi-repo)" parenthetical is a hint, not an implemented step) and `identify-units.md:65` passes `--source-root {project_paths[0]}` to `skf-disqualify-candidates.py` for all boundaries, so units from the second repo onward get the first repo's source path and their files are resolved against the wrong root. `scan-project.md:41` iterates every path (and resolves per-path `constituent_refs`, added for #405/#406), but no step carries a per-unit repo mapping from scan through classification to brief generation, and the disqualify script accepts a single `--source-root`. Still present at v2.1.0; a real fix threads a per-boundary source path through scan → identify-units → generate-briefs rather than patching either line alone.
