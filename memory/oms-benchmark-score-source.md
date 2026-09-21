---
created: "2026-04-19 22:58"
session: "ea09087a-7af6-46b9-bc15-c2ccf78c6b47"
source: claude-mem
source_table: observations
source_ids: [6341, 6342, 6344, 6346]
---

# Authoritative source for oms-* benchmark scores

`docs/_data/pinned.yaml` `test_score` is what the docs cite for each oms-* reference skill, and `tools/validate-docs-drift.js` checks version/commit/tier/authority against oh-my-skills `metadata.json` but never checks `test_score`. When refreshing a score after a recompile, take it from the `score:` frontmatter field of `forge-data/<skill>/<version>/test-report-<skill>*.md` in the oh-my-skills clone (`oh_my_skills_path` in pinned.yaml, default `../oh-my-skills`) — not from `skf-test-skill-result*.json` (an intermediate run: oms-cognee 1.0.0's `-latest.json` holds 97.98 while the report holds 99.00%) and not from `metadata.json` (coverage stats only). An announcement draft once cited a fabricated 99.22% for oms-cocoindex whose real score is 99.0%. As of 2026-09 oh-my-skills already ships oms-cocoindex 1.0.0 (99.00%) while pinned.yaml still anchors 0.3.37; the drift validator does not flag that because 0.3.37 still resolves.
