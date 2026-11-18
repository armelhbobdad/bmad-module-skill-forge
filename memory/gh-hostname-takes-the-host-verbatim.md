---
created: "2026-11-17 14:48"
session: "ebc4edf5-1536-4f23-a3e9-90b0b13c44e9"
---

# gh --hostname takes the host verbatim while --repo normalises it

gh normalises the host of a `--repo HOST/OWNER/REPO` value before it uses one: it drops one leading lower-case `www.` (ghrepo's `normalizeHostname`, `strings.ToLower(strings.TrimPrefix(h, "www."))`), then lower-cases, and maps any `*.github.com` to `github.com`, any `*.github.localhost` to `github.localhost` and `api.TENANT.ghe.com` to `TENANT.ghe.com`. So `www.WWW.ghe.example.com/o/r` reaches `www.ghe.example.com` (one trim), `WWW.` and `Www.` keep their `www.` in lower case, and `www./o/r` names no host and goes to gh's default host. The trim belongs to the `--repo` parser only: `--hostname` takes its value as written, so `gh api --hostname WWW.GitHub.com` failed, `gh auth status --hostname WWW.GitHub.com` exited 1, and `gh auth login --hostname www.HOST` validates against `https://www.HOST/api/v3/` (gh 2.104.0, 2026-11-17). A host that goes to `--hostname` must be normalised first, or the `--hostname` calls of a run miss the host its `--repo` calls reach; docs naming that HOST say "one leading lower-case `www.` dropped, then in lower case", since "lower case and without a leading `www.`" names the wrong host for `WWW.HOST` and `www.www.HOST`. `_normalize_host`, `_named_host` and `split_repo` in `src/shared/scripts/skf-health-check-seen.py` do it for the health check's `host`, `host_flag` and `lookup` (PRs #1240 and #1243), as `health_check_fp.py` does in UltraCode Goal (its PR #245).
