---
created: "2026-11-17 15:01"
session: "ebc4edf5-1536-4f23-a3e9-90b0b13c44e9"
---

# Bare gh auth status fails on any stale login

`gh auth status` with no `--hostname` checks every host in gh's config and exits 1 when any one of them has a bad token or cannot be reached (`X Failed to log in to ghe.example.com`), even with `GH_HOST` set; only `gh auth status --hostname HOST` limits the check to one host. With gh 2.104.0 and a temporary `GH_CONFIG_DIR` holding a valid github.com login and a stale Enterprise host, the bare call exited 1 while `gh issue list --repo OWNER/REPO` and `gh api` both worked (#1237 review, PR #1240). The health check (`src/shared/health-check.md`, section 5a sub-step 2) still runs the bare form for an `OWNER/REPO` `health_check_repo`, as 11.1.0 did, so such a user sees every finding queued as "GitHub CLI is not available."; it passes `--hostname` only through `host_flag`, for a value that names a host. `gh auth status --active` would narrow the check to active accounts, but it no longer matches the `Bash(gh auth status)` allow rule headless runs use.
