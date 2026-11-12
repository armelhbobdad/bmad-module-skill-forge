---
# Note: `shared/health-check.md` resolves relative to the SKF module root
# ({project-root}/_bmad/skf/ when installed, {project-root}/src/ during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

Load `{nextStepFile}`, read it fully, then execute it. Do nothing else here: user-facing reports, file writes and result contracts belong to step 6. This is the terminal step of verify-stack: after the shared health check completes, the workflow is fully done. If `{nextStepFile}` cannot be resolved or loaded (a partial installation, a module root that does not resolve, or a removed file), log exactly `health-check unavailable at {path}`, with the resolved path you tried, and exit cleanly: step 6 already wrote the feasibility report, and a missing optional hook must not fail a CI or headless run.
