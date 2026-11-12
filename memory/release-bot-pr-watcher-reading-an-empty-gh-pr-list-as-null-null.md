---
created: "2026-11-07 18:27"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Release bot PR watcher reading an empty gh pr list as null null

A watcher polling for the release bot PR with `gh pr list --state open --search "head:release/bot/vX.Y.Z" --json number,headRefOid -q '.[0] | "\(.number) \(.headRefOid)"'` prints `null null` while the bot PR does not exist yet, because jq's `.[0]` of an empty array is null and string interpolation renders it as `null`. A `[ -n "$B" ] && break` loop then exits on its first pass and polls the check-runs of a commit named null, failing with `gh: No commit found for SHA: null (HTTP 422)` (8.1.0 cut, release run 42386452833). Left running, such a watcher never sees the bot PR, so nobody merges it and the `Wait for PR approval or admin-bypass merge` step in `release.yaml` times out after 30 minutes. Use a query that prints nothing on an empty list, such as `-q '.[] | .number' | head -1`, and loop until a number appears. Only then read its `headRefOid` for the check-runs watch in [A release bot PR's checks live on its commit, and GitHub can drop some of them](release-bot-pr-checks-live-on-its-commit.md).
