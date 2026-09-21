---
created: "2026-03-08 21:20"
session: "292552a2-2332-4b44-af2d-d4e5299688e0"
source: claude-mem
source_table: both
source_ids: [653, 661, 680]
---

# qmd collection add has no exclude flag

`qmd collection add <path> [--name NAME] [--mask GLOB]` takes only an inclusion mask: there is no `--exclude`, negated globs are not a documented feature, and per-collection `ignore` patterns are YAML-only (`@tobilu/qmd` 2.8.3 README: 'no CLI command sets this'). When setup once indexed the project root with `**/*.md`, it pulled 131 `_bmad/` module-internal files into search on a project that held nothing but the SKF module (fix 27fdd69f 'smart auto-index excludes module internals', then the whole auto-index was replaced by the progressive collection registry in 4d74d96a). Exclusion is therefore done by choosing the directory: every current producer points its collection at a dedicated folder — `{forge_data_folder}/{skill}` for `-brief`, `{skill_package}` for `-extraction`, `_bmad-output/{skill}-temporal|-docs` staging — and `src/skf-setup/references/auto-index.md` creates no collections at all. Never index the project root or `_bmad/` into QMD; `src/knowledge/qmd-registry.md` 'Rationale' records why blind auto-index was dropped but not this CLI limit.
