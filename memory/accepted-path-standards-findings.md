---
created: "2026-05-16 00:06"
session: "368f6026-a320-4e3c-ab70-9bedb28ba90c"
source: claude-mem
source_table: observations
source_ids: [9904, 14779, 14781, 14795]
---

# Path-standards findings that must stay as-is in SKF skills

bmad-workflow-builder's `scan-path-standards.py` flags every `_bmad/` not preceded by `{project-root}/` (`BARE_BMAD_RE`), every home-directory absolute path and every `../` reference, but several of its high-severity hits in this repo are intentional and must not be "fixed" when driving a skill to an Excellent quality report. The `_bmad/custom/<skill>.toml` / `<skill>.user.toml` mentions in each SKILL.md customization paragraph (e.g. src/skf-create-skill/SKILL.md:79) stay bare because `npm run validate:refs` (`tools/validate-file-refs.js --strict`, a required CI check) maps `{project-root}/_bmad/<x>` to `src/<x>` and reports `{project-root}/_bmad/custom/...` as `Broken references: 1` — the scanner's preference loses to the CI gate. Also intentional: `~/.skf/workspace/` at src/skf-create-skill/references/source-resolution-protocols.md:85 (the documented `SKF_WORKSPACE` default), the `../shared/types.ts` and `../../../etc/passwd` examples in src/skf-test-skill/references/coherence-check.md (they describe what the validator checks), and the `nextStepFile: '../extract.md'` / `'../enrich.md'` hops in src/skf-create-skill/references/sub/ (correct relative chains that validate:refs resolves). Genuinely fixable hits have been cross-directory `./references/{library}.md` templates and similar; treat the rest as accepted findings.
