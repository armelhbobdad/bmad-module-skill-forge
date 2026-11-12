---
created: "2026-10-09 13:59"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# uv run failures that reuse helper exit codes 2 and 1

A helper started with `uv run` can exit with a code that comes from uv, not the script, and write no JSON. A spawn failure prints `error: Failed to spawn: ...` then a `cause: ...` line and exits 2; a dependency uv cannot resolve (offline, empty cache) prints `error: No solution found when resolving script dependencies` and exits 1 (seen with uv 0.12.15). So a branch on a helper's exit code cannot read every exit 1 as the helper's own result. Update Skill's `src/skf-update-skill/references/detect-changes.md` (Category B) and `src/skf-update-skill/references/gap-driven.md` tie the recipe runner's exit 1 to "`incomplete`, its JSON written" and add "`uv` failing to start it exits 2 too" to the exit 2 halt. When writing such a branch for any `uv run` helper, key its exit 1 on the JSON being there and take the stderr line holding `error:` as the reason, since uv may print an `Installed N packages` or second `cause:` line around it.
