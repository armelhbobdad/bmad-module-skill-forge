---
created: "2026-04-09 00:24"
session: "4a1c1afc-7896-4732-8b7d-d05e14e39405"
source: claude-mem
source_table: both
source_ids: [4912, 4926]
---

# Stale invocations after moving or porting a script

Porting `compute-score.js` to `compute-score.py` and folding `workflow.md` into `SKILL.md` left three silent breaks that no gate caught: the test-skill scoring stage still ran `node {scoringScript}` on a `.py` file (now `uv run {scoringScript} --stdin` at `src/skf-test-skill/references/score.md:99`), `docs/` linked the deleted `compute-score.js` on GitHub, and `tools/cli/commands/status.js` counted installed skills by the presence of `workflow.md` so `skf:status` reported 0 forever (it now checks `SKILL.md` and excludes `skf-forger`); docstrings in `test/test-compute-score-contract.py` and `tools/validate-skills.js` kept the old names too (fix commit 70854d77). `validate:refs` only resolves frontmatter and relative path references and `validate:docs-links` only checks `.md` targets and built-site hrefs, so an interpreter name in prose, a github.com blob link, or a filename baked into CLI logic passes `npm run quality`. When a script or skill file is moved, renamed or changes language, grep `tools/`, `src/*/references/` and `docs/` for the old name and the old command before calling the migration done.
