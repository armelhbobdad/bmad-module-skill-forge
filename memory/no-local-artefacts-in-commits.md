---
created: "2026-05-15 13:27"
session: "aa307bf9-20a5-4395-aa9d-821b8dc28003"
source: claude-mem
source_table: both
source_ids: [9467, 9468, 10945]
---

# No local or gitignored artefacts in commit and PR messages

Commit messages, PR titles and bodies, issue text and code comments in this public repo must not reference anything that exists only on the maintainer's machine or is gitignored: improvement-queue finding fingerprints (`fp-xxxxxxx`) and `hc-*.md` health-check files, run-ids, `forge-data/`, `_bmad-output/`, `**/.analysis`, `**/.decision-log.md` and `.claude/` paths, consumer-repo names and checkout paths, `/tmp` fixture paths, quality-report or planning-doc paths, and internal todo IDs. Describe the fix in user-visible terms, name the documented rule or contract that was missing, and summarize quality-analysis findings in plain language instead of citing a report path. The user restated this in every improvement-queue fix session: "The commit and PRs messages should not content local artefacts." `CONTRIBUTING.md:59` records only the internal-todo-ID half of this (`_bmad-output/todo/`); the rest is nowhere in the repo, so check the draft before `git commit` and `gh pr create`. Related: `memory/no-bmad-terms-in-commits`.
