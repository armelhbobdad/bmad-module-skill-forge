---
nextStepFile: 'quick-extract.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 2: Ecosystem Check

## Rules

- A HARD HALT prints, after its envelope, this step's `halt` event when `{headless_mode}` is true. Under `--batch` it ends only this target: then return to `references/batch-mode.md` §3, even when the halt reads as the end of the run (`references/halt-contract.md`).

## Steps

agentskills.io has no registry API to ask whether an official skill already covers `{repo_name}`, so make no query and no web search (a search hit cannot show that a skill is official), say nothing, and go on as IF P does.

Once a registry API lists an official skill for `{repo_name}`, name it and offer: [P] Proceed, compiling a custom community skill anyway · [I] Install the official skill instead, which ends this workflow · [A] Abort. Answer anything else by helping, then offer again.

- IF P: when `{headless_mode}` is true, print this step's `done` event and step 3's `start` event (`references/halt-contract.md`); then load, read entire file, then execute {nextStepFile}
- IF I: Display install instructions for the official skill, then HARD HALT with **exit code 8 (ecosystem-redirect)**: stage `{"phase": "ecosystem-check", "halt_reason": "ecosystem-redirect", "reason": "User opted to install existing official skill instead of compiling a custom community skill.", "skill_package": null}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"` (`references/halt-contract.md`). The skill package is unknown at this phase, so no result file is written.
- IF A: Display "Compilation cancelled.", then HARD HALT with **exit code 6 (user-cancelled)**: stage `{"phase": "ecosystem-check", "halt_reason": "user-cancelled", "reason": "User aborted at ecosystem-match gate.", "skill_package": null}` as `{run_dir}/halt.json` and run `uv run {emitEnvelopeHelper} emit-halt --workflow skf-quick-skill --run-dir "{run_dir}" --target stderr < "{run_dir}/halt.json"`. No result file is written.
- **GATE [default: P]**: if `{headless_mode}` and match found, auto-proceed with [P] Proceed (compile custom skill anyway), log "headless: ecosystem match found, auto-proceeding with custom compilation", and record the decision: stage `{"gate": "ecosystem-check.ecosystem-match", "default_action": "P", "taken_action": "P", "reason": "headless: compiled a custom skill beside the official one"}` as `{run_dir}/decision.json` and run `uv run {emitEnvelopeHelper} record --workflow skf-quick-skill --run-dir "{run_dir}" --decision < "{run_dir}/decision.json"`, then go on as IF P does, its events included.
