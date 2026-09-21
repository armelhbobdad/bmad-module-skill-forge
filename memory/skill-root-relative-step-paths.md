---
created: "2026-04-08 18:47"
session: "22de972c-e2c4-42f6-8273-847aae2f80d7"
source: claude-mem
source_table: both
source_ids: [4763, 4764, 4780, 4805]
---

# Skill-root-relative paths in step frontmatter, no ../ traversal

Step-file frontmatter and prose reference resources without `../`: sibling stages as bare names (`nextStepFile: 'coverage-check.md'`), skill-local files skill-root-relative (`references/x.md`, `assets/x.md`, `scripts/compute-score.py`), and module-level files from the `src/` root (`knowledge/version-paths.md`, `shared/health-check.md`). `tools/validate-file-refs.js` encodes the resolution: a `<name>Data:` bare path whose first segment is a real directory under `src/` resolves from `src/`, otherwise from the workflow root (parent of `references/`); the `../references/…` and `../../shared/…` forms (47 occurrences across 13 skills in the 2026-04-08 path-standards scan) were all rewritten and are flagged high severity by the bmad-workflow-builder path-standards scanner. The one accepted exception is the sub-stage directory `src/skf-create-skill/references/sub/`, whose `nextStepFile: '../extract.md'` / `'../enrich.md'` must climb back to `references/`. Note that validate-file-refs does not check a bare `nextStepFile` value at all (its STEP_META pattern only matches paths starting with `.`), so a typo there passes `npm run validate:refs`.
