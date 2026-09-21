---
created: "2026-06-03 18:56"
session: "ab575e86-8acf-4f61-85b2-5e9d5bed1496"
source: claude-mem
source_table: observations
source_ids: [14721, 14778, 14780, 14781]
---

# Stale .analysis dirs inflate scan-path-standards findings

bmad-workflow-builder's `scan-path-standards.py` (run by the quality-analysis workflow) walks a skill with `skill_path.rglob('*.md')` + `rglob('*.json')` and offers only `--output` and `--include-fenced` — no exclude — so the gitignored `.analysis/<timestamp>/` directories and `.decision-log.md` that earlier quality runs leave under `src/<skill>/` (`.gitignore`: `**/.analysis`, `**/.decision-log.md`) are scanned too. Their JSON carries absolute `/home/...` paths and `.decision-log.md` sits at the skill root, so a re-scan reports absolute-path findings, `Prompt file at skill root: .decision-log.md`, and even its own `path-standards-temp.json`; one all-skills run dropped from 89 raw findings to 34 once those artifacts were discounted, and skf-campaign scored 0 on a clean tree. Delete or move aside `src/<skill>/.analysis/` and `.decision-log.md` before scanning, then read what remains against the accepted findings in `memory/accepted-path-standards-findings`. The sibling `prepass-workflow-integrity.py` has its own false criticals on the `references/step-NN-*.md` layout — see `memory/prepass-missing-stage-false-positives`.
