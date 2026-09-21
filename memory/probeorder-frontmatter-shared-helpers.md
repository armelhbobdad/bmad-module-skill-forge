---
created: "2026-05-15 16:59"
session: "849d3685-4017-4409-abbc-3ec7fd4d3b07"
source: claude-mem
source_table: observations
source_ids: [9664, 9681, 14803, 14810]
---

# ProbeOrder frontmatter for every shared helper script invocation

Every `uv run` of a `src/shared/scripts/*.py` helper (and every load of a `src/shared/references/*.md` schema) from a `src/skf-*/references/*.md` step is wired through a frontmatter `<name>ProbeOrder` array that lists `{project-root}/_bmad/skf/shared/scripts/<script>.py` (installed module) first and `{project-root}/src/shared/scripts/<script>.py` (dev checkout) second, resolved in prose as "Resolve `{<name>Helper}` from `{<name>ProbeOrder}`; first existing path wins. HALT if no candidate exists", and then invoked only as `uv run {<name>Helper}` (see `src/skf-setup/references/write-config.md` frontmatter for the canonical shape; 71 step files carry a ProbeOrder). The rule exists because an installed module lives under `_bmad/skf/` with no `src/` tree: a bare `uv run src/shared/scripts/skf-detect-docs.py` or an undeclared placeholder such as `{forgeTierRw}` or `{compileAssemblyRules}` passes every `npm run quality` gate (`validate:refs` maps `_bmad/skf/` to `src/` for file references but no validator checks helper placeholders) and then silently degrades or halts in the installed layout — the defect recurred in June 2026 (commit 2ebc7a45) in skf-create-skill (`generate-artifacts.md`, `step-doc-sources.md`, `validate.md`), skf-brief-skill (`step-auto-brief.md`) and skf-analyze-source (`step-auto-scope.md`). The frontmatter is the single source of truth: prose references the variable and never re-enumerates paths, and the HALT is deliberate — do not fall back to prose-driven LLM computation for what the helper does (content hashes, symlink flips, drift guards, manifest counts, scope classification), because two runs would then disagree. The one remaining in-prompt fallback is the Quick-tier metadata renderer in `src/skf-quick-skill/references/compile.md`; do not copy it into forge-tier steps.
