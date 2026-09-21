---
created: "2026-05-24 11:19"
session: "8614f40a-7bf6-4911-8fad-b9036c883f2a"
source: claude-mem
source_table: both
source_ids: [11578, 11579, 11592, 11595]
---

# SKF workspace artifacts use {forge_data_folder}, never {output_folder}

`{output_folder}` is a BMad Core Config variable (`_bmad-output` in core/BMM/CIS, listed under "Variables from Core Config inserted" in `src/module.yaml` and still loaded by every SKF SKILL.md activation) whose value depends on which co-installed module's config is active. `src/shared/health-check.md` once set `localFallbackFolder = {output_folder}/improvement-queue`, so findings landed sometimes in `forge-data/improvement-queue/` and sometimes in `_bmad-output/improvement-queue/`; the user asked "check why the health check something write the local issue in forge-data/improvement-queue and sometime in _bmad-output/improvement-queue (may be it is also a bug". It now reads `{forge_data_folder}/improvement-queue` (health-check.md:6, PR #380). Rule: SKF workspace artifacts always build on `{forge_data_folder}` and deliverables on `{skills_output_folder}`, both singly defined in `src/module.yaml` (see `src/knowledge/version-paths.md`); `{output_folder}` is only for BMad planning documents. The only in-repo statement of this is the inline comment at health-check.md:6.
