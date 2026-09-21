---
created: "2026-03-06 14:28"
session: "16eaf640-7cea-416c-ab4d-6238288a3fd9"
source: claude-mem
source_table: both
source_ids: [495, 1928]
---

# SKF input scope: code repositories, documentation websites and developer discourse

SKF is not a source-code-only tool. The narrow phrasing "Skill Forge transforms source code into ... skills" / "reads your actual source code" crept in twice (module.yaml/skf.agent.yaml, then README.md and docs/*.md after a restructuring rewrite); the user corrected it: "The documentation says SKF transforms source code. In reality, we are not limited to source code, we transform code repositories, documentation websites, and developer discourse." The three sources map to the confidence tiers: code repositories (T1, `file:line@SHA`, incl. package-to-repo resolution via npm/PyPI/crates.io), documentation websites (T3, `[EXT:url]`, docs-only skills) and developer discourse (T2, QMD over issues/PRs/changelogs). Keep the wide phrasing whenever rewriting README.md, docs/*.md, src/module.yaml or the Ferris description in src/skf-forger/SKILL.md and docs/agents.md; the canonical sentence is in src/module.yaml:5 and README.md:21.
