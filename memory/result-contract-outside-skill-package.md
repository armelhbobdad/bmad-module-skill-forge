---
created: "2026-04-09 22:52"
session: "3f373a49-0cdd-4599-b4f8-6b8214af3f47"
source: claude-mem
source_table: session_summaries
source_ids: [1533, 1534]
---

# Result contract JSON lives in forge-data, not the skill package

Pipeline result contracts (`<skill>-result-{YYYYMMDD-HHmmss}.json` plus the `-latest.json` copy per `src/shared/references/output-contract-schema.md`) are workspace artifacts and belong under `{forge_version}` (`{forge_data_folder}/{skill-name}/{version}/`), `{forge_data_folder}` or `{sidecar_path}` — never inside `{skill_package}` (`{skills_output_folder}/{skill-name}/{version}/{skill-name}/`), which is the agentskills.io package that `npx skills add` installs and export ships. The v1.0 release audit found skf-create-skill writing `create-skill-result.json` into the package and commit `5b8fa4a5` moved it to `{forge_version}/`; `output-contract-schema.md` still only says the two files go to an undefined `{output_dir}`, and `src/knowledge/version-paths.md:110-112` only implies the split (deliverables to `{skill_package}`, workspace artifacts to `{forge_version}`). `skf-quick-skill` is the one skill that still writes `{skill_package}/quick-skill-result-*.json` (`references/finalize.md:75`, `references/halt-contract.md:36`) because Quick tier has no `{forge_version}` — treat that as the exception, not the pattern to copy into forge-tier skills.
