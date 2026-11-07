---
created: "2026-11-06 10:54"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Parallel full-suite runs exhaust the /tmp inodes

`/tmp` on this machine is a tmpfs capped at 1,048,576 inodes, and one full `npm test` run leaves about 99,000 files in its `TMPDIR` (pytest's `/tmp/pytest-of-armel/` when `TMPDIR` is unset). A few full-suite runs in parallel (subagents, worktrees, background reviews) fill every inode while disk space is still free, and then every shell command fails before it starts: `/bin/bash: line 1: /tmp/claude-2295-cwd: No space left on device`, with `df -i /tmp` showing `1048576 1048576 0 100%`. It hit on 2026-11-02, 2026-11-05 and 2026-11-06, the last time during the 7.0.0 series, when the maintainer chose to delete that session's temp folders. Give each full-suite run its own `TMPDIR` folder under the session scratchpad, delete it after the run (`chmod -R u+w` first), never delete another run's folder, and check `df -i /tmp` before starting suites in parallel.
