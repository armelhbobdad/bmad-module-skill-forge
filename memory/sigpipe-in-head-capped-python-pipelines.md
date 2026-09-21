---
created: "2026-03-20 01:55"
session: "e750a5a3-084c-4319-808a-736b145f86b8"
source: claude-mem
source_table: observations
source_ids: [1950]
---

# SIGPIPE default in head-capped inline Python pipelines

The CLI streaming fallback in `src/skf-create-skill/references/extraction-patterns.md` pipes `ast-grep run ... --json=stream` through an inline `python3 -c` filter into `| head -{HEAD_CAP}`. Once `head` has its N lines it closes the pipe, and Python's default SIGPIPE handling then ends the run with `Exception ignored on flushing sys.stdout:` / `BrokenPipeError: [Errno 32] Broken pipe` instead of exiting quietly — hit on large repos (over 500 files in scope, where the 200-line cap is reached) and easily misread as a failed extraction. The uncommented line `signal.signal(signal.SIGPIPE, signal.SIG_DFL)` at the top of that inline script (commit 8917330a) is what makes it exit silently: do not drop it as unused, and copy it into any new `python3 -c ... | head -N` pipeline.
