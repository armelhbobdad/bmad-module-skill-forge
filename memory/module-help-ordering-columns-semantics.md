---
created: "2026-04-12 01:26"
session: "b0c4aaa4-1c77-4b7b-8bc9-2c63f31f7583"
source: claude-mem
source_table: both
source_ids: [5805, 5826]
---

# module-help.csv ordering columns are reciprocal and meta rows stay empty

The `preceded-by`/`followed-by` columns of `src/module-help.csv` encode the SKF lifecycle for bmad-help routing (setup → analyze/brief/quick/campaign → create/stack → test → export → update/audit/rename/drop, plus setup → verify-stack → refine-architecture), and every edge is written twice: if skill A lists B under `followed-by`, B lists A under `preceded-by` (adding the optional AN→BS path meant adding `skf-analyze-source` to skf-brief-skill's `preceded-by`, not only `skf-brief-skill` to AN's `followed-by`). Nothing enforces this — the BMB `validate-module.py` only checks that `skill:action` refs resolve — so a one-sided edit silently breaks the guidance. The three `skf-forger` meta-action rows (FF, KI, WS) leave both columns empty on purpose because they are invocable at any time; they are not missing data to be filled in.
