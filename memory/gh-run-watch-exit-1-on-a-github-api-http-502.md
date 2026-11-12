---
created: "2026-10-13 22:25"
session: "060dd6d3-2607-49df-93d3-74db880c67b5"
---

# gh run watch exit 1 on a GitHub API HTTP 502

A CI wait built on `gh run watch` can exit 1 because the GitHub API failed, not CI: on 2026-10-13 the watch on #757's run 38462202731 exited 1 with `HTTP 502: Server Error (https://api.github.com/repos/<owner>/<repo>/actions/runs/38462202731/jobs?per_page=100)` while the run was still in progress. The run later finished `completed success` with all 10 jobs green. A PR-chain script that reads only the watch's exit code (that session's log showed `ci exit=1`) would report red, re-push or hold back `gh pr ready` for nothing. When a watch exits non-zero, re-poll `gh run view <id> --json status,conclusion` until the status is `completed`. Then check every job's conclusion and that `headSha` matches the PR head (`--json headSha,jobs`) before calling CI green or red.
