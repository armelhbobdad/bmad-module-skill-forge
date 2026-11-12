---
created: "2026-11-03 23:09"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# pgrep -f matching its own watcher and the Bash tool wrapper

`pgrep -f '<script> <PR>'` also matches every shell whose command line contains that string, which broke both ways of driving the gitignored stacked-PR ship scripts (`_bmad-output/implementation-artifacts/ship-merge.sh`, `ship-after.sh`). On 2026-11-03 a Monitor loop `while pgrep -f 'ship-merge.sh 860' >/dev/null; do ...; done` matched its own `bash -c` line and never exited, so it expired after 30 minutes with no event although #860 had merged (`merged: #860 as bb489e8e`). On 2026-11-04 `p=$(pgrep -f "ship-merge.sh 869" | head -1); kill $p` killed pid 665545, the Bash tool's own `/bin/bash -c source ~/.claude/shell-snapshots/...` wrapper, twice, so the commands chained after it never ran and the reversal commit 6b5494a7 was left unpushed. Use a pattern that cannot match itself (`pgrep -f '[s]hip-merge.sh 869'`), keep each background job's `$!`, or poll the log the job writes (such as `merge-860.log`) and `gh pr view <N> --json state` instead of the process list. Check `ps -o cmd= -p <pid>` before killing a pgrep hit, and confirm afterwards that the rest of the command ran.
