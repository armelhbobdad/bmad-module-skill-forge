---
created: "2026-03-14 18:02"
session: "399dba32-15e7-4ca7-b421-c491359347a7"
source: claude-mem
source_table: observations
source_ids: [1159, 1163]
---

# Letter-suffix naming for inserted workflow steps

A step inserted between two existing numbered steps takes the previous step's number plus a letter suffix and is wired through the previous step's `nextStepFile`; the steps after it are never renumbered. The user chose this when temporal fetching was added to create-skill: "insert a new `step-03b-fetch-temporal.md`. This gives us the best of both worlds: it adheres perfectly to the micro-file principle (keeping `step-04` focused strictly on semantic enrichment) while avoiding the massive churn of renaming steps `05` through `08`." Most skills now keep numbering only in the SKILL.md step table (create-skill lists 2b, 3b, 3c, 3d, 5a, 5b, 5c; test-skill 4b, 4c), while `src/skf-campaign/references/` still uses `step-NN-<slug>.md` filenames chained by `nextStepFile`, so an insertion there is `step-05b-<slug>.md`, not a renumbering of steps 06-11. `tools/validate-skills.js` STEP-01 accepts the optional letter suffix, and `CONTRIBUTING.md` line 102 only states the `step-NN-<slug>.md` pattern — nothing there says not to renumber.
