---
created: "2026-04-08 19:20"
session: "22de972c-e2c4-42f6-8273-847aae2f80d7"
source: claude-mem
source_table: observations
source_ids: [4782, 4784, 4797]
---

# Double {project-root} prefix on resolved config variables

`src/module.yaml` resolves `skills_output_folder`, `forge_data_folder` and `sidecar_path` as `result: "{project-root}/{value}"`, and runtime variables such as `{context_file}`/`{target-file}` in skf-export-skill's `references/update-context.md` are likewise already absolute. Writing `{project-root}/{context_file}` or `{project-root}/{sidecar_path}/preferences.yaml` in step prose therefore renders a doubled path like `/home/user/project//home/user/project/CLAUDE.md` and the file write fails. This was found in April 2026 at four places in skf-export-skill's update-context step and in skf-drop-skill and skf-rename-skill, and fixed by using the bare variable. Nothing in `npm run quality` catches it — only bmad-workflow-builder's untracked `scan-path-standards.py` (`DOUBLE_PREFIX_RE = \{project-root\}/\{[^}]+\}`) reports it — so never re-prefix a variable that module.yaml already resolves, and keep `grep -rn '{project-root}/{' src` empty apart from module.yaml itself.
