---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file: it is the `{healthCheckFile}`
# report.md §4c found before it published anything.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 7: Workflow Health Check

Load `{nextStepFile}`, read it fully, then execute it. This is the terminal step of test-skill: report.md §7 already released the run lock and removed the run folder, and in headless mode the shared health check displays the bound `{result_envelope_line}` as the run's last line.
