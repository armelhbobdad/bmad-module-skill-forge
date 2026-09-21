---
created: "2026-03-26 22:51"
session: "2ea0daa0-0587-489f-a85e-4d1485fabebf"
source: claude-mem
source_table: observations
source_ids: [2703, 2704, 2747, 2771]
---

# Report template must declare every field a later step reads

Every frontmatter or summary-table field that a later step parses must be initialised in the report template and actually written by the step that owns it. The verify-stack template once lacked `recommendationCount` (written by synthesize, read by report) and the `deltaImproved/deltaRegressed/deltaNew/deltaUnchanged` fields (read by report, never written), and refine-architecture's report step parsed `skill_count` from a Changes Made table row that compile never emitted — the same class of bug surfaced three times on 2026-03-26/27. Requirements counters must initialise to `null`, not `0`, because the report step's `{x or 'N/A'}` fallback treats `0` as a real value. `test/test-workflow-state.js` (`npm run test:workflow`) now pins the VS template fields and the RA `<!-- [RA-*] -->` blocks, but only for verify-stack, refine-architecture and compose mode — when adding a field consumed by a later step in any skill, add it to the template, to the producer step, and to that test.
