---
created: "2026-04-23 17:41"
session: "2996b99e-cec1-4e04-9f2b-9909cb46aeb6"
source: claude-mem
source_table: both
source_ids: [7029, 7032, 7041, 7099]
---

# Repository Actions setting that gates bot PR creation in release.yaml

The `Open bot PR` step of `.github/workflows/release.yaml` (`gh pr create` under `GITHUB_TOKEN`) fails with `GitHub Actions is not permitted to create or approve pull requests (createPullRequest)` (run 24838486851) even though the workflow declares `permissions: pull-requests: write`. The gate is a repository-level setting, not the YAML: Settings > Actions > General > Workflow permissions > 'Allow GitHub Actions to create and approve pull requests', i.e. `gh api -X PUT repos/armelhbobdad/bmad-module-skill-forge/actions/permissions/workflow -F can_approve_pull_request_reviews=true`; `default_workflow_permissions` can stay `read` because the YAML grants its scopes explicitly. As of 2026-09 `gh api repos/armelhbobdad/bmad-module-skill-forge/actions/permissions/workflow` returns `{"default_workflow_permissions":"read","can_approve_pull_request_reviews":true}`. `docs/_internal/RELEASING.md` documents the ruleset, the `release` environment and the npm trusted publisher but not this toggle, and release.yaml's own error hint covers only the sibling `allow_auto_merge` setting, so a fork, transfer or settings reset will break the pipeline at this step again; the only record is one row in `release-audits/v1.0.0-launch-audit.md`, and the 'approve' wording makes the setting easy to overlook.
