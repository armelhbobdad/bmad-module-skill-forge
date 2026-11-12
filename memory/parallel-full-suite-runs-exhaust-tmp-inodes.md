---
created: "2026-11-06 10:54"
session: "76fdf8e2-4067-429c-80c2-b3ed2b66e2e2"
---

# Former /tmp inode cap and per-run TMPDIR folders for parallel full-suite runs

Through 2026-11-06 `/tmp` was a tmpfs capped at 1,048,576 inodes, and a few parallel full `npm test` or `npm run quality` runs (each leaving 30,000 to 99,000 files, mostly in `/tmp/pytest-of-armel/pytest-N`) filled it while `df -h /tmp` still showed free space. Every tool then failed with `/bin/bash: line 1: /tmp/claude-2295-cwd: No space left on device` or `ENOSPC: no space left on device, open '/proc/self/fd/43/<id>.output'`. `tmp.mount` is now masked (`/etc/systemd/system/tmp.mount -> /dev/null`) and `/tmp` sits on the root ext4 (`df -i /tmp` shows `/dev/nvme0n1p2` with 119,955,456 inodes), so the cap is gone. If `findmnt /tmp` ever shows a tmpfs again, set `PYTEST_ADDOPTS="-o tmp_path_retention_policy=failed -o tmp_path_retention_count=1"` (no repo config does) and run at most two heavy suites at once. Isolation still matters: give each run its own lane-named `TMPDIR` (`mktemp -d -p <scratchpad>/verify-runs <lane>.XXXX`), delete only that exact path (`chmod -R u+w` first), and never glob-delete `tmp.*` in a shared scratchpad. On 2026-11-06 a subagent's cleanup ran `rm -rf` on `tmp.as7tfXzhJM`, the live TMPDIR of the pr889 worktree's pytest run, and two suites had to be rerun.
