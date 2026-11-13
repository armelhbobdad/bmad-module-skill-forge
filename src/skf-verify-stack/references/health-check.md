---
# Note: `shared/health-check.md` resolves relative to the SKF module root
# ({project-root}/_bmad/skf/ when installed, {project-root}/src/ during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

Load `{nextStepFile}`, read it fully, then execute it. Do nothing else here: user-facing reports, file writes and result contracts belong to step 6. This is the terminal step of verify-stack: after the shared health check completes, the workflow is fully done. In a headless run report.md §5, after the on_complete instruction, bound `{result_envelope_line}` to the `SKF_VERIFY_STACK_RESULT_JSON` line without displaying it: the shared health check displays that line verbatim as the run's last line wherever it stops, so a `claude -p` caller reads the envelope as the final message. If `{nextStepFile}` cannot be resolved or loaded (a partial installation, a module root that does not resolve, or a removed file), log exactly `health-check unavailable at {path}`, with the resolved path you tried, then display `{result_envelope_line}` verbatim after it when it is bound and not empty, with no code fence and nothing after it, and exit cleanly: step 6 already wrote the feasibility report, and a missing optional hook must not fail a CI or headless run.
