---
nextStepFile: 'quick-extract.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Ecosystem Check

## Rules

- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).

## Steps

agentskills.io has no registry API to ask whether an official skill already covers `{repo_name}`, so make no query and no web search (a search hit cannot show that a skill is official), say nothing, and go on as IF P does.

- IF P: when `{headless_mode}` is true, print this step's `done` event and step 3's `start` event (`references/halt-contract.md`); then load, read entire file, then execute {nextStepFile}
