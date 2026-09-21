---
created: "2026-05-15 22:42"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9835, 9837, 9839, 14754]
---

# validate:refs truncation of {placeholder} inside {project-root}/_bmad/ paths

`tools/validate-file-refs.js` (`npm run validate:refs`, strict inside `npm run quality` and CI) extracts references with `PROJECT_ROOT_REF = /\{project-root\}\/_bmad\/([^\s'"<>})\]`]+)/g`(tools/validate-file-refs.js:52), whose character class stops at`}```. Documenting a customize.toml override as `` ```{project-root}/\_bmad/custom/{skill-name}.toml``` `` therefore reports ```UNRESOLVED`for the truncated path`custom/{skill-name`, and the literal form `{project-root}/\_bmad/custom/skf-campaign.toml`fails too because`custom/`is not in`INSTALL_ONLY_PATHS`and resolves to a nonexistent`src/custom/...`; only `{{mustache}}`, `node_modules`and the`UNRESOLVABLE_VARS``` list are skipped, there is no general placeholder exclusion. The convention now used in 14 skills (src/skf-brief-skill/SKILL.md:54-55, src/skf-campaign/SKILL.md:41-42) is a bulleted list of `` ```\_bmad/custom/<skill-name>.toml`under`{project-root}``` `` — angle-bracket placeholder and no ```{project-root}/\_bmad/`prefix — which the regex never matches. Write new customization docs in that shape rather than editing the validator;`.toml`is not in`SCAN_EXTENSIONS`, so comments inside `customize.toml` may keep the full path.
