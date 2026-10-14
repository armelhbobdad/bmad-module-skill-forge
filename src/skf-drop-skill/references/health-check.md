---
# Note: `shared/health-check.md` resolves relative to the SKF module root
# ({project-root}/_bmad/skf/ when installed, {project-root}/src/ during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 4: Workflow Health Check

This is the terminal step of drop-skill. Load `{nextStepFile}`, read it fully, then execute it — do nothing else here (no user-facing reports, file writes, or result contracts; those were step 3). After the shared health check completes, the workflow is done.

In a headless run report.md bound `{result_envelope_line}` to the `SKF_DROP_SKILL_RESULT_JSON` line without displaying it: the shared health check displays that line verbatim as the run's last line wherever it stops, so a `claude -p` caller reads the envelope as the final message.
