---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/`
# during development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 6: Workflow Health Check

This is the terminal step of brief-skill. Load `{nextStepFile}`, read it fully, then execute it — do nothing else here (no user-facing reports, file writes, or result contracts; those were step 5). After `{nextStepFile}` returns control, the brief-skill workflow is fully complete: do not re-enter step 5 or step 6, load any further step file, or loop back into the workflow.
