---
created: "2026-05-01 11:43"
session: "5bc16144-c3f0-47e8-831a-23395e5c40a5"
source: claude-mem
source_table: both
source_ids: [8078, 8079, 9847, 9851, 9852, 9855]
---

# Path-standards rules for skf step files (no bare _bmad, ~/, ../ or /tmp)

The bmad-workflow-builder quality scan's path-standards scanner (`.claude/skills/bmad-workflow-builder/scripts/scan-path-standards.py`, a local BMAD install — untracked and not in CI) fails skf-* skill files at high severity for bare `_bmad/...` without `{project-root}/` (write `{project-root}/_bmad/skf/...` for installed, `{project-root}/src/...` for dev), `~/` home paths, `../` parent references, and hardcoded absolute paths such as `/tmp/...`, and at critical severity for `{project-root}/{config-var}` double prefixes. The `/tmp` rule came from a real regression: `src/skf-create-skill/references/sub/fetch-temporal.md` captured `gh release view` stderr in `/tmp/.gh-err`, which does not exist on Windows and races across concurrent runs; it now uses `ERR_FILE="{staging}/.gh-release-err"` with `rm -f "$ERR_FILE"` cleanup. For scratch files in step prose use a `{staging}/` path or `mktemp`. Known hits deliberately left in place: `~/.skf/workspace/` as the documented default in `source-resolution-protocols.md`, and the `../` in the `references/sub/` stages.
