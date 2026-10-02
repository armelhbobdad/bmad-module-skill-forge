---
created: "2026-04-23 20:07"
session: "2996b99e-cec1-4e04-9f2b-9909cb46aeb6"
source: claude-mem
source_table: observations
source_ids: [7070, 7077, 7105, 7106]
---

# Untagged version bump left on main by a release run that fails before tagging

On the main-dispatch path of `.github/workflows/release.yaml` the bot PR is merged (`Wait for PR approval or admin-bypass merge` / `Auto-merge bot PR`) **before** `Create and push tag`. A run that dies in that window (e.g. run 24845860915, a transient GitHub `HTTP 500` on the tag step's `git fetch origin main`) leaves the `release: bump to vX.Y.Z` commit and its CHANGELOG entry on main with no tag, no npm publish and no GitHub Release. Finish that version with `gh workflow run release.yaml --ref main -f version_bump=resume` (`docs/_internal/RELEASING.md` Scenario H): it tags the merged bump, publishes it and creates the Release, each only if missing, and never bumps. Until then the `Refuse to bump past an unpublished release` step refuses a `minor` or `major` dispatch past it (`patch` stays allowed as the ship-forward). Before the resume path existed, the next dispatch bumped past the stranded number, because `Bump version` runs `npm version prerelease` from main's `package.json`: that is why `CHANGELOG.md` carries `## [1.0.0-rc.1]` and `## [1.0.0-rc.2]` entries while `git tag` and `npm view` show only `v1.0.0-rc.3`, a history that lives only in `release-audits/v1.0.0-launch-audit.md:401`.
