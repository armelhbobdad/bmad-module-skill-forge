---
created: "2026-04-23 20:07"
session: "2996b99e-cec1-4e04-9f2b-9909cb46aeb6"
source: claude-mem
source_table: observations
source_ids: [7070, 7077, 7105, 7106]
---

# Untagged version bump left on main by a release run that fails before tagging

On the main-dispatch path of `.github/workflows/release.yaml` the bot PR is merged (`Wait for PR approval or admin-bypass merge` / `Auto-merge bot PR`) **before** `Create and push tag`, and that tag step deliberately fails when `git fetch origin main` errors (`::error::git fetch origin main failed. Cannot safely anchor release tag. Check network/auth and re-run.`). A run that dies in that window — e.g. run 24845860915, a transient GitHub `HTTP 500` on the fetch — leaves the `release: bump to vX.Y.Z` commit and its CHANGELOG entry on main with no tag, no npm publish and no GitHub Release. Because `Bump version` runs `npm version prerelease` from main's `package.json`, the next dispatch produces the *following* number: that is why `CHANGELOG.md` carries `## [1.0.0-rc.1]` and `## [1.0.0-rc.2]` entries while `git tag` and `npm view` show only `v1.0.0-rc.3`. Skipped numbers are expected fallout, not missing releases to recover: just re-dispatch and never reuse the burned number (RELEASING.md Scenario D do-NOT clause). `docs/_internal/RELEASING.md`'s Rollback Playbook A–G has no scenario for this window; the rc.1/rc.2 history lives only in `release-audits/v1.0.0-launch-audit.md:401`.
