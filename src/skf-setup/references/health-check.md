---
# `shared/health-check.md` resolves relative to the SKF module root
# (`{project-root}/_bmad/skf/` when installed, `{project-root}/src/` during
# development), NOT relative to this step file.
nextStepFile: 'shared/health-check.md'
---

<!-- Config: communicate in {communication_language}. -->

# Step 5: Workflow Health Check

Load `{nextStepFile}`, read it fully, then execute it; setup is done when it returns.
