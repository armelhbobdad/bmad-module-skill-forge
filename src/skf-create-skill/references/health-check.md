---
# `shared/health-check.md` resolves from the SKF module root, not from this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 9: Workflow Health Check

Load `{nextStepFile}`, read it fully, then execute it. Do nothing else here: user-facing reports, file writes and result contracts belong to step 8. This is the terminal step of create-skill: after the shared health check completes, the workflow is fully done. Under `--batch`, `references/batch-mode.md` §4 loads this step once, after the batch summary; report.md §6 sends each brief back to batch-mode.md §3 instead of here. In a headless run that is not `--batch`, report.md §5 bound `{result_envelope_line}` to the brief's `SKF_CREATE_SKILL_RESULT_JSON` line without displaying it: the shared health check displays that line verbatim as the run's last line wherever it stops, so a `claude -p` caller reads the envelope as the final message.
