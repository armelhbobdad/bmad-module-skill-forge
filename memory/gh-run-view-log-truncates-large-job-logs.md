---
created: "2026-09-30 12:37"
session: "1eac7d31-a255-4a86-b7ad-388ffb7624ab"
---

# gh run view --log truncates large job logs

`gh run view --job <id> --log` silently returns only part of a large job log: on 2026-09-30, for PR #617's `python (windows-latest)` job, it gave about 380 KB of a 2 MB log, cut at `[ 34%]` with no pytest summary and no `##[error]` line, which read as a six-minute hang. The full log comes from the REST API: `curl -sSL -H "Authorization: Bearer $(gh auth token)" https://api.github.com/repos/<owner>/<repo>/actions/jobs/<job_id>/logs` (`gh api .../logs` refuses the body because it holds terminal escape sequences, unless given `--allow-escape-sequences`); it showed `5702 passed, 103 skipped, 101 warnings, 2 errors`. The job's annotations (`gh api repos/<owner>/<repo>/check-runs/<job_id>/annotations`) carry the real exit, here `Process completed with exit code 1`. When a CI log stops mid-run or has no test summary, fetch the full log through the API before diagnosing a hang or a crash.
