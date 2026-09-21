---
created: "2026-05-15 14:20"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: session_summaries
source_ids: []
---

# Excellent-grade baseline every skf-* workflow must meet

Every `src/skf-*` workflow was elevated to an 'Excellent' bar (commits 2daf8b03, c765391b, 81fff73c) and new or edited ones must keep it: a `customize.toml` whose canonical `[workflow]` block is resolved in On Activation through the three-layer merge (bundled → `_bmad/custom/<skill>.toml` → `_bmad/custom/<skill>.user.toml`); `{communication_language}`/`{document_output_language}` headers in every carved reference file so they survive context compaction; an exit-code table (SKILL.md `## Exit Codes`, or `references/invocation-contract.md` for skf-brief-skill) plus a stdout `SKF_<X>_RESULT_JSON` envelope on every terminal path including halts (`skf-emit-result-envelope.py emit-blocked` in headless/quiet mode, see src/skf-setup/SKILL.md:55); `[X] Cancel` on every interactive menu; and deterministic work (hashing, manifest scans, file-list intersections) done by helpers in `src/shared/scripts/` rather than prose. `skf-brief-skill` is the calibration reference. `CONTRIBUTING.md § Adding a New Workflow Skill` lists only frontmatter, manifest, knowledge and registration, and `src/shared/references/output-contract-schema.md` covers only the result file, so this checklist is otherwise unwritten and a new workflow that misses any item silently drops below the bar.
