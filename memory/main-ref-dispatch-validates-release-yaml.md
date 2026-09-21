---
created: "2026-04-23 20:39"
session: "2996b99e-cec1-4e04-9f2b-9909cb46aeb6"
source: claude-mem
source_table: both
source_ids: [7088, 7099]
---

# Main-ref dispatch validation for release.yaml changes

`.github/workflows/release.yaml` has two distinct paths: a main-ref dispatch (release commit to `release/bot/vX.Y.Z-<run_id>`, bot PR, forced status checks, environment and review gates, push to main — every such step is guarded by `if: github.ref == 'refs/heads/main'`) and a non-main dispatch that takes the `Skip PR flow (non-main dispatch ref)` step and only tags and publishes (docs/\_internal/RELEASING.md:667). The v0.10.1-alpha.0 alpha cut was dispatched from a feature branch, so the main path had never run; the v1.0.0-rc cut then needed 7 dispatch attempts to surface 5 distinct defects — branch-protection ruleset rejection, PR creation blocked by `can_approve_pull_request_reviews`, workflow_dispatch check-run visibility, bash IFS word-splitting in the jq step, an invalid `gh pr view` field (release-audits/v1.0.0-launch-audit.md:224, :417). Any release.yaml change whose primary path is the main-ref dispatch is validated with a main-ref dispatch (staging repo or throwaway version), with ShellCheck and end-to-end path tracing in review; a green feature-branch run proves nothing about the main path. RELEASING.md does not say this, and the launch audit is a forensic record that must not be extended.
