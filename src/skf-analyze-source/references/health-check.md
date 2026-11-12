---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `src/` during development),
# NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

Load `{nextStepFile}`, read it fully, then execute it. Do nothing else here: user-facing reports, file writes and result contracts belong to step 6. This is the terminal step of analyze-source: after the shared health check completes, the workflow is fully done. In a headless run the step that ended it (generate-briefs.md §9, step-auto-scope.md §9 or auto-docs-only.md §5) bound `{result_envelope_line}` to the `SKF_ANALYZE_RESULT_JSON` line without displaying it: the shared health check displays that line verbatim as the run's last line wherever it stops, so a `claude -p` caller reads the envelope as the final message.
