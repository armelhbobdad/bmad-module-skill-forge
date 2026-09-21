---
created: "2026-05-15 13:33"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: observations
source_ids: [9480, 9492, 9493, 9494]
---

# Parent-directory nextStepFile in skf-create-skill sub/ branch stages

`src/skf-create-skill/references/sub/` holds the conditional branch stages (ccc-discover.md, fetch-temporal.md, fetch-docs.md); the two that return to the main chain are the only step files in `src/` whose `nextStepFile` uses parent navigation — `'../extract.md'` and `'../enrich.md'` — while every other nextStepFile is a bare sibling path. A bulk regex rewrite that sequentially stripped `./` and `step-NN-` prefixes turned them into `'.extract.md'` / `'.enrich.md'`, which nothing but `node tools/validate-file-refs.js --strict` (`npm run validate:refs`, part of `npm run quality`) caught. After any bulk path rewrite of step frontmatter, run `npm run validate:refs` before committing and expect the sub/ files to need `../`, not the bare form.
