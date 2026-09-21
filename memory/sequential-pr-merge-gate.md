---
created: "2026-05-02 19:58"
session: "1c92fc56-30b2-43db-93ac-d43c959b2a1e"
source: claude-mem
source_table: observations
source_ids: [8278, 8280, 8308]
---

# Sequential PR merge gate for multi-PR batches

When a set of PRs is cut from the same `main`, open the next PR only after the user has merged the current one; never leave several PRs stacked on one base. On 2026-05-02 five skf-brief-skill PRs (#272–#276) branched together collided in `src/skf-brief-skill/SKILL.md` (exit-code table and the `input-invalid` halt_reason wording), the step-01 §8 GATE, step-05 and `package.json`, and #275/#276 needed manual rebases (the #275 rebase paused at commit d393ecd9 on the step-01 GATE conflict). The user then stated the rule: "Always wait until I merge the current PR before you continue with the next PR on top of the previous one to avoid multiples merge conflicts." CONTRIBUTING.md ("Workflow for Changes") says to branch from `main` but does not record this sequencing rule.
