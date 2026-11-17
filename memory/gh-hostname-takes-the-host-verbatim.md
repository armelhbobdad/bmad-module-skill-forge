---
created: "2026-11-17 14:48"
session: "ebc4edf5-1536-4f23-a3e9-90b0b13c44e9"
---

# gh --hostname takes the host verbatim while --repo normalises it

gh normalises the host of a `--repo HOST/OWNER/REPO` value (lower case, any `*.github.com` to `github.com`, any `*.github.localhost` to `github.localhost`, `api.TENANT.ghe.com` to `TENANT.ghe.com`), so `gh issue list --repo WWW.GitHub.com/o/r` reaches github.com, but it uses a `--hostname` value as written: `gh api --hostname WWW.GitHub.com` failed and `gh auth status --hostname WWW.GitHub.com` exited 1 (gh 2.104.0, 2026-11-17). A host that goes to `--hostname` must be normalised first, or the `--hostname` calls of a run miss the host its `--repo` calls reach. `_normalize_host` and `split_repo` in `src/shared/scripts/skf-health-check-seen.py` do it for the health check's `host` and `host_flag` (PR #1240).
