---
created: "2026-04-20 13:47"
session: "891c9aa5-5f44-4eb4-8d03-9e262ebd1b1d"
source: claude-mem
source_table: observations
source_ids: [6403, 6404, 6783, 6827]
---

# workflow_dispatch 404 for workflows not on main

`gh workflow run <file>.yaml --ref <feature-branch>` returns HTTP 404 (workflow not found on the default branch) when the workflow file does not yet exist on `main`: GitHub only indexes `workflow_dispatch` workflows from the default branch, whatever `--ref` says, so it is not a permissions or allow-list problem. This hit `env-gate-test.yaml` (2026-04-20) and then `release.yaml` (2026-04-21) before each was merged. To exercise an unmerged workflow, push a throwaway commit adding `on: push: branches: [<branch>]` and default the dispatch input in the script (`BUMP="${BUMP:-alpha}"`, because `github.event.inputs` is empty on push events), then revert that commit before merging — commits e4705018 and its revert 7208ff48 on `.github/workflows/release.yaml` are the precedent. `docs/_internal/RELEASING.md` § Temporarily allowing a feature branch covers the `release` environment allow-list for `release.yaml` (now on main) but not this constraint for new workflows.
