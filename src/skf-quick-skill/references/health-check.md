---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), not relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

## STEP GOAL:

Chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of quick-skill: after the shared health check completes, the workflow is fully done. Under `--batch` it runs once per batch, after `references/batch-mode.md` §4 wrote the batch summary, never after a single target.

In a headless single-target run step 6 §3 bound `{result_envelope_line}` to the `SKF_QUICK_SKILL_RESULT_JSON` line without displaying it: the shared health check displays that line verbatim as the run's last line wherever it stops, so a `claude -p` caller reads the envelope as the final message.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 6
- Delegate directly to `{nextStepFile}` with no additional commentary or other action, except the headless `done` event below

## Steps

When `{headless_mode}` is true, print this step's `done` event (`references/halt-contract.md`). Load `{nextStepFile}`, read it fully, then proceed to execute it.
