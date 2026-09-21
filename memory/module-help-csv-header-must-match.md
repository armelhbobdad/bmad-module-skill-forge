---
created: "2026-04-07 23:00"
session: "8bcb9111-b354-4301-ab90-f1e2a73bbfdf"
source: claude-mem
source_table: observations
source_ids: [4510, 4520, 4704, 4705]
---

# module-help.csv header must match the installed bmad-help.csv exactly

`src/module-help.csv` is copied by the installer and merged positionally into the consumer's `_bmad/_config/bmad-help.csv`, so its header has to reproduce that file's 13 columns verbatim: `module,skill,display-name,menu-code,description,action,args,phase,preceded-by,followed-by,required,output-location,outputs`. Two misalignments have already shipped: an extra column inserted after `module` made a 14-column file that shifted every SKF value from `phase` onward and corrupted every SKF entry in bmad-help lookups; and omitting the empty `action`/`args` columns shifted the literal `false` from `required` into the ordering column, so the BMB `validate-module.py` flagged every row with a medium `invalid-ref` ("references 'false' which is not a valid capability … Expected format: skill-name:action-name") — the fix was `,,anytime` → `,,,anytime`, not hunting references. When that validator complains about references or reports a `csv-header` mismatch, count columns per row (a Python `csv.reader` one-liner) before anything else. `npm test` has no assertion on this file, and older BMAD spec documents describe a different column order, so the installed `bmad-help.csv` header is the only reference to trust.
