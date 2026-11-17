---
created: "2026-11-17 13:35"
session: "ebc4edf5-1536-4f23-a3e9-90b0b13c44e9"
---

# gh search issues cannot reach a GitHub Enterprise Server host

`gh search issues --repo` is a search filter in `OWNER/REPO` form on gh's default host, not a repository selector: `gh search issues --repo ghe.example.com/acme/skills --state open "fp-1234567 in:title" --json number,url,title --limit 1` exits 1 with `Invalid search query "( fp-1234567 in:title ) repo:ghe.example.com/acme/skills state:open type:issue"`, and a `github.com/OWNER/REPO` value fails the same way. `gh issue list --repo HOST/OWNER/REPO --state open --search "..."` searches the named host with the same qualifiers (`in:title`, `in:title,body`) and JSON fields, so the health check's dedup searches moved to it in PR #1240; #1237's own note had assumed `gh search issues` took the host. `src/shared/scripts/skf-fetch-temporal.py` still runs `gh search issues --repo`, so it cannot target an Enterprise host either.
