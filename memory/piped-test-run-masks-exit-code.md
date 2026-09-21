---
created: "2026-08-06 11:20"
session: "5d852636-9449-426d-a518-ead3afd0a980"
source: claude-mem
source_table: both
source_ids: [31915]
---

# Piped test run masks the real exit code

`npm test 2>&1 | tail -40` (likewise `| grep`, or `gh pr checks --watch | ...`) returns the exit status of the last command in the pipe, so the harness notice "completed (exit code 0)" says nothing about whether the suite passed; this nearly produced a false green on PR #466 and forced a full rerun. `npm test` in this repo chains fifteen subcommands (see `scripts.test` in `package.json`), which is what makes tailing tempting. Capture the real status with `npm test > <log> 2>&1; echo "EXIT=$?" >> <log>` and grep the log for `EXIT=0` (or use `set -o pipefail`) before claiming the suite passed.
