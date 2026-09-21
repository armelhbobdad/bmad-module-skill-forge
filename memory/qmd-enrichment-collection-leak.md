---
created: "2026-05-22 09:29"
session: "03d49b85-5cc9-4a04-999c-15467644f08b"
source: claude-mem
source_table: observations
source_ids: [10801, 10803, 10805]
---

# QMD enrichment results are not scoped to a collection

A downstream health-check (fp-a277146, SKF 1.6.0, 2026-05-21) reported that the qmd plugin's collection parameter did not scope queries — hits came back from other collections. SKF never guards against this: the four `qmd_bridge.query(searches=[...])` calls in `src/skf-create-skill/references/enrich.md` §3 pass only `type`/`query`/`intent` and no `collections` filter, while §2 merely inventories which `temporal`/`docs` collections exist in `forge-tier.yaml`. So a Deep-tier run can annotate an export with `[QMD:{collection}:{doc}]` taken from a `{name}-extraction` or brief collection, or from another skill's collection, and nothing checks the returned document's collection before the T2 citation is written. The improvement queue's suggested workaround (verify the hit's collection/file prefix matches the intended collection, fall back to a direct file read otherwise) was never applied. When debugging wrong or self-referential T2 citations, or editing enrich.md, validate result provenance explicitly; the current plugin's `query` tool accepts a `collections` array, but whether the upstream leak is fixed has not been re-verified.
