---
created: "2026-04-09 14:14"
session: "43564723-f0c6-47d6-826c-097212da743c"
source: claude-mem
source_table: observations
source_ids: [5024]
---

# skf-test-skill outputFile must route through {forge_version}

Every skf-test-skill stage file under `src/skf-test-skill/references/` (init.md, detect-mode.md, coverage-check.md, coherence-check.md, score.md, step-hard-gate.md, external-validators.md, report.md) declares `outputFile: '{forge_version}/test-report-{skill_name}-{run_id}.md'`; `{forge_version}` resolves to `{forge_data_folder}/{skill-name}/{version}/` per `src/knowledge/version-paths.md` ("Write all workspace artifacts to `{forge_version}`"). The trap: the readers — `src/skf-update-skill/references/init.md` (`--from-test-report` lookup) and `src/skf-export-skill/references/load-skill.md` §4b — glob the versioned path first and then fall back to the flat `{forge_data_folder}/{skill_name}/test-report-*.md`, so a stage that writes to the flat path still appears to work and nothing fails; every step file was in exactly that state until 2026-04-09, when the versioned contract was dead code. Only `test/test-skf-step-hard-gate.py` asserts `outputFile:.*\{forge_version\}` for a test-skill stage (step-hard-gate.md; `test/test-skf-step-doc-drift.py` makes the same assertion for the audit-skill step), so the other stage files are unguarded. When adding or copying stage frontmatter, route the output path through `{forge_version}`, never `{forge_data_folder}/{skill_name}/`.
