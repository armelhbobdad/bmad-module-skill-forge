---
# Note: `shared/health-check.md` resolves relative to the SKF module root
# ({project-root}/_bmad/skf/ when installed, {project-root}/src/ during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
stateFile: '{campaignWorkspacePath}/_campaign-state.yaml'
---

<!-- Config: communicate in {communication_language}. -->

# Workflow Health Check

## STEP GOAL:

Apply the operator's findings-routing consent, then chain to the shared workflow self-improvement health check at `{nextStepFile}`. This is the terminal step of skf-campaign — after the shared health check completes, the workflow is fully done.

## Rules

- No user-facing reports, file writes, or result contracts in this step — those belong in step 11.
- The ONLY processing permitted here is reading the routing preference (below) and carrying it into `{nextStepFile}`; otherwise delegate directly with no additional commentary.

## MANDATORY SEQUENCE

### 1. Apply findings-routing consent

Read `campaign.health_findings_queue` from `{stateFile}` and carry it into the shared health check as the operator's **already-decided** routing consent (so the shared step does not re-prompt, satisfying its "explicit opt-in" requirement for non-bug findings):

- `"improvement"` — the operator opted in at setup: route this campaign's friction/gap findings to the shared improvement queue (the shared step's opt-in is pre-satisfied; do not re-prompt).
- `"local"` (default) — keep findings in the local queue only; do not submit to the shared queue.

If the state file is unreadable, default to `"local"` (never submit without consent).

### 2. Delegate

Load `{nextStepFile}`, read it fully, then execute it — applying the routing consent from step 1.
