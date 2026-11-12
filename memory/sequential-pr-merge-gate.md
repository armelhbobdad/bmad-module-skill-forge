---
created: "2026-05-02 19:58"
session: "1c92fc56-30b2-43db-93ac-d43c959b2a1e"
source: claude-mem
source_table: observations
source_ids: [8278, 8280, 8308]
---

# Sequential PR merge gate for multi-PR batches

When PRs in one batch touch the same files, open the next one only after the user has merged the current one, so overlapping PRs never stack on one base. Batches with disjoint files may be built in parallel worktrees cut from the current `origin/main` and stay open together, still opened in the order the user gave. The rule came on 2026-05-02, after five skf-brief-skill PRs (#272 to #276) branched from one `main` collided in `src/skf-brief-skill/SKILL.md`, the step-01 §8 GATE, step-05 and `package.json`, forcing manual rebases of #275 and #276 (#275 paused at d393ecd9). The user first said "Always wait until I merge the current PR before you continue with the next PR", then on 2026-10-09 narrowed it: "Start each batch from an up-to-date main, and only after the previous PR is merged when they touch the same files." So #701 and #704 stayed open together, while #705 waited for #701 because both edit `src/skf-create-skill/references/extract.md`. CONTRIBUTING.md ("Workflow for Changes") says to branch from `main` but records no sequencing rule.
