---
created: "2026-05-15 14:52"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9589, 9591]
---

# skf-setup index banner leaks into --quiet stdout

`src/skf-setup/references/ccc-index.md:96` displays "**Building semantic index — this can take several minutes on large codebases (1000+ files). Run `ccc status` in another terminal to monitor progress.**" before `ccc index` with no `{quiet_mode}`/`{headless_mode}` guard; `{quiet_mode}` is only consulted in `references/report.md`, `references/write-config.md` (the blocked-envelope path) and the SKILL.md halt contract. `src/skf-setup/SKILL.md:50` and `docs/workflows.md:30` promise that under `--quiet` the single-line `SKF_SETUP_RESULT_JSON: {…}` envelope is the only stdout line, so a pipeline that captures stdout on a first-run index (or after `ccc_index_fresh` is false) gets two lines. Flagged as item E-1a in the 2026-05-15 skf-setup quality scan (E-1b was the lack of any heartbeat during 5–15 minute indexing runs) and still open at v2.1.0. Guard the banner when touching ccc-index.md, and have pipelines grep for the `SKF_SETUP_RESULT_JSON:` prefix rather than assuming a single line.
